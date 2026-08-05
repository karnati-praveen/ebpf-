// Package controller implements KubeEdgeInfer's DECIDE/ACT/HEAL loop: it
// aggregates node-agent telemetry, computes the optimal layer split, and
// applies it to workers and router over gRPC, tracking everything in the
// InferencePipeline custom resource.
package controller

import (
	"context"
	"fmt"
	"log"
	"sort"
	"sync"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/client-go/dynamic"
	"k8s.io/client-go/kubernetes"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	"kubeedgeinfer/gen/pipelinepb"
	"kubeedgeinfer/internal/partition"
)

var PipelineGVR = schema.GroupVersionResource{
	Group:    "kubeedgeinfer.io",
	Version:  "v1alpha1",
	Resource: "inferencepipelines",
}

type Config struct {
	Namespace        string
	WorkerSelector   string // label selector for shard worker pods
	WorkerPort       int
	Static           bool
	HeartbeatTimeout time.Duration
	DefaultLinkMs    float64
	ImprovementFrac  float64
	Cooldown         time.Duration
	Interval         time.Duration
	// ReassertInterval is how often the controller re-pushes the current
	// assignment even when nothing changed. Workers and the router hold
	// their layout in memory only, so a restarted pod comes back empty; the
	// worker set looks unchanged to the Decider, so without this the
	// pipeline would stay broken forever. Re-pushing is idempotent and
	// carries the *current* generation, so it does not disturb in-flight
	// requests.
	ReassertInterval time.Duration
	// ProfileOnce freezes each node's speed factor and each link's cost at
	// its first observed eBPF/GPU reading, then reuses that snapshot forever
	// instead of tracking live telemetry. This reproduces the "offline
	// profiling pass, decided once" pattern used by EdgeShard/PipeEdge/Galaxy
	// so it can be compared head-to-head against KubeEdgeInfer's own
	// continuous-telemetry DECIDE loop under the same fault injection.
	ProfileOnce bool
}

type Controller struct {
	cfg     Config
	kube    kubernetes.Interface
	dyn     dynamic.Interface
	store   *TelemetryStore
	decider *partition.Decider

	mu             sync.Mutex
	generation     int64
	staticApplied  bool
	lastApplied    *partition.Result
	lastPush       time.Time
	lastError      string
	conns          map[string]*grpc.ClientConn
	frozenSpeed    map[string]float64 // node -> speed, captured once when ProfileOnce
	frozenLinkMs   map[string]float64 // dst ip -> link ms, captured once when ProfileOnce
}

func New(cfg Config, kube kubernetes.Interface, dyn dynamic.Interface, store *TelemetryStore) *Controller {
	return &Controller{
		cfg:          cfg,
		kube:         kube,
		dyn:          dyn,
		store:        store,
		decider:      partition.NewDecider(cfg.ImprovementFrac, cfg.Cooldown),
		conns:        map[string]*grpc.ClientConn{},
		frozenSpeed:  map[string]float64{},
		frozenLinkMs: map[string]float64{},
	}
}

func (c *Controller) Run(ctx context.Context) {
	ticker := time.NewTicker(c.cfg.Interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if err := c.reconcile(ctx); err != nil {
				c.mu.Lock()
				c.lastError = err.Error()
				c.mu.Unlock()
				log.Printf("reconcile: %v", err)
			}
		}
	}
}

type spec struct {
	model       string
	backend     string
	totalLayers int
	perLayerMs  float64
	workers     int64
	routerAddr  string
}

func specFrom(u *unstructured.Unstructured) spec {
	s := spec{
		model:       str(u, "spec", "model"),
		backend:     str(u, "spec", "backend"),
		totalLayers: int(num(u, "spec", "totalLayers")),
		perLayerMs:  fnum(u, "spec", "perLayerMs"),
		workers:     num(u, "spec", "workers"),
		routerAddr:  str(u, "spec", "routerAddr"),
	}
	if s.backend == "" {
		s.backend = "sim"
	}
	if s.perLayerMs == 0 {
		s.perLayerMs = 30
	}
	if s.routerAddr == "" {
		s.routerAddr = "router:50052"
	}
	return s
}

func (c *Controller) reconcile(ctx context.Context) error {
	crs, err := c.dyn.Resource(PipelineGVR).Namespace(c.cfg.Namespace).List(ctx, metav1.ListOptions{})
	if err != nil {
		return fmt.Errorf("list pipelines: %w", err)
	}
	if len(crs.Items) == 0 {
		return nil
	}
	cr := &crs.Items[0]
	sp := specFrom(cr)

	pods, err := c.livePods(ctx)
	if err != nil {
		return err
	}
	if len(pods) == 0 {
		return c.updateStatus(ctx, cr, nil, "NoWorkers")
	}

	input := c.buildInput(sp, pods)

	if c.cfg.Static {
		return c.reconcileStatic(ctx, cr, sp, input)
	}

	res, changed, err := c.decider.Decide(time.Now(), input, false)
	if err != nil {
		return c.updateStatus(ctx, cr, nil, "PartitionError: "+err.Error())
	}
	if changed {
		if err := c.apply(ctx, sp, res); err != nil {
			// Force a fresh decision next tick rather than believing the
			// half-applied split is active.
			c.decider = partition.NewDecider(c.cfg.ImprovementFrac, c.cfg.Cooldown)
			return fmt.Errorf("apply: %w", err)
		}
		log.Printf("applied gen=%d bottleneck=%.1fms: %s",
			c.generation, res.BottleneckMs, describe(res))
	} else if gen, due := c.reassertDue(time.Now()); due {
		// Repair a worker or router that restarted and lost its layout.
		if err := c.push(ctx, sp, res, gen); err != nil {
			return fmt.Errorf("reassert: %w", err)
		}
	}
	return c.updateStatus(ctx, cr, res, "Running")
}

// reconcileStatic applies one equal split when all expected workers are up,
// then never touches the pipeline again — the ablation baseline.
func (c *Controller) reconcileStatic(ctx context.Context, cr *unstructured.Unstructured, sp spec, input partition.Input) error {
	c.mu.Lock()
	applied := c.staticApplied
	last := c.lastApplied
	c.mu.Unlock()
	if applied {
		// Static never repartitions, but it must still repair a restarted
		// worker or router — otherwise the baseline arm of a benchmark dies
		// on a pod restart for reasons unrelated to the ablation.
		if gen, due := c.reassertDue(time.Now()); due && last != nil {
			if err := c.push(ctx, sp, last, gen); err != nil {
				log.Printf("static reassert: %v", err)
			}
		}
		return c.updateStatus(ctx, cr, last, "RunningStatic")
	}
	if sp.workers > 0 && int64(len(input.Workers)) < sp.workers {
		return c.updateStatus(ctx, cr, nil, "WaitingForWorkers")
	}
	for i := range input.Workers {
		input.Workers[i].Speed = 1 // static ignores telemetry by design
	}
	for i := range input.LinkMs {
		input.LinkMs[i] = c.cfg.DefaultLinkMs
	}
	res, err := partition.Optimal(input)
	if err != nil {
		return err
	}
	if err := c.apply(ctx, sp, res); err != nil {
		return fmt.Errorf("apply static: %w", err)
	}
	c.mu.Lock()
	c.staticApplied = true
	c.mu.Unlock()
	log.Printf("applied static split gen=%d: %s", c.generation, describe(res))
	return c.updateStatus(ctx, cr, res, "RunningStatic")
}

type podInfo struct {
	name, ip, node string
}

// livePods returns Running worker pods whose node agent heartbeat is fresh,
// in a deterministic pipeline order. Dropping a pod whose heartbeat went
// stale is the HEAL trigger: the Decider sees a changed worker set and
// forces a repartition across survivors.
//
// Ordering is (node, pod name), not node alone: sort.Slice is not stable, so
// with several workers on one node -- the single-machine GPU layout, where
// every pod shares a node -- ordering by node alone leaves ties to be broken
// arbitrarily. The Decider compares worker identity position-by-position, so
// a reshuffle would look like a changed worker set and force a pointless
// repartition on every tick.
func (c *Controller) livePods(ctx context.Context) ([]podInfo, error) {
	list, err := c.kube.CoreV1().Pods(c.cfg.Namespace).List(ctx, metav1.ListOptions{
		LabelSelector: c.cfg.WorkerSelector,
	})
	if err != nil {
		return nil, fmt.Errorf("list pods: %w", err)
	}
	var pods []podInfo
	for _, p := range list.Items {
		if p.Status.Phase != corev1.PodRunning || p.Status.PodIP == "" || p.DeletionTimestamp != nil {
			continue
		}
		if !podReady(&p) {
			continue
		}
		if _, alive := c.store.Node(p.Spec.NodeName, c.cfg.HeartbeatTimeout); !alive {
			continue
		}
		pods = append(pods, podInfo{name: p.Name, ip: p.Status.PodIP, node: p.Spec.NodeName})
	}
	sort.Slice(pods, func(i, j int) bool {
		if pods[i].node != pods[j].node {
			return pods[i].node < pods[j].node
		}
		return pods[i].name < pods[j].name
	})
	return pods, nil
}

func podReady(p *corev1.Pod) bool {
	for _, cond := range p.Status.Conditions {
		if cond.Type == corev1.PodReady {
			return cond.Status == corev1.ConditionTrue
		}
	}
	return false
}

func (c *Controller) buildInput(sp spec, pods []podInfo) partition.Input {
	input := partition.Input{
		TotalLayers: sp.totalLayers,
		PerLayerMs:  sp.perLayerMs,
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	for _, p := range pods {
		speed := 1.0
		if gpu, ok := c.store.Node(p.node, c.cfg.HeartbeatTimeout); ok && gpu.GetSpeedFactor() > 0 {
			speed = gpu.GetSpeedFactor()
		}
		if c.cfg.ProfileOnce {
			if frozen, ok := c.frozenSpeed[p.node]; ok {
				speed = frozen
			} else {
				c.frozenSpeed[p.node] = speed
			}
		}
		input.Workers = append(input.Workers, partition.Worker{
			Name:  p.name,
			Addr:  fmt.Sprintf("%s:%d", p.ip, c.cfg.WorkerPort),
			Node:  p.node,
			Speed: speed,
		})
	}
	// The router drives stages hub-and-spoke, so the transfer cost feeding
	// stage i+1 is the network path into that stage's pod.
	for i := 0; i+1 < len(pods); i++ {
		ms := c.cfg.DefaultLinkMs
		if srtt, ok := c.store.LinkSRTTToDst(pods[i+1].ip, uint32(c.cfg.WorkerPort), 15*time.Second); ok {
			ms = srtt
		}
		if c.cfg.ProfileOnce {
			key := pods[i+1].ip
			if frozen, ok := c.frozenLinkMs[key]; ok {
				ms = frozen
			} else {
				c.frozenLinkMs[key] = ms
			}
		}
		input.LinkMs = append(input.LinkMs, ms)
	}
	return input
}

// apply adopts a new split: it bumps the generation and pushes it out.
func (c *Controller) apply(ctx context.Context, sp spec, res *partition.Result) error {
	c.mu.Lock()
	c.generation++
	gen := c.generation
	c.mu.Unlock()
	return c.push(ctx, sp, res, gen)
}

// reassertDue reports whether the current layout should be re-pushed.
func (c *Controller) reassertDue(now time.Time) (int64, bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.lastApplied == nil || c.cfg.ReassertInterval <= 0 {
		return 0, false
	}
	return c.generation, now.Sub(c.lastPush) >= c.cfg.ReassertInterval
}

// push sends the split to every worker, then points the router at it, at the
// given generation. Workers tolerate being assigned before the router
// switches: requests carrying the old generation are rejected and the router
// replays them on the new chain.
//
// This is idempotent, and deliberately so: workers and the router keep their
// layout in memory only, so one that restarts comes back with nothing
// assigned while still looking unchanged to the Decider (same pod name and
// IP). Re-pushing the *current* generation on a timer is what repairs that;
// without it a single router restart wedges the pipeline permanently.
func (c *Controller) push(ctx context.Context, sp spec, res *partition.Result, gen int64) error {
	for _, a := range res.Assignments {
		client := pipelinepb.NewWorkerClient(c.conn(a.Worker.Addr))
		reqCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
		reply, err := client.AssignLayers(reqCtx, &pipelinepb.AssignLayersRequest{
			StartLayer:  int32(a.Start),
			EndLayer:    int32(a.End),
			TotalLayers: int32(sp.totalLayers),
			Backend:     sp.backend,
			Model:       sp.model,
			Generation:  gen,
		})
		cancel()
		if err != nil {
			return fmt.Errorf("assign %s: %w", a.Worker.Name, err)
		}
		if !reply.Ok {
			return fmt.Errorf("assign %s: %s", a.Worker.Name, reply.Error)
		}
	}

	// Empty stages are dropped from the chain the router drives.
	var stages []*pipelinepb.StageRef
	for _, a := range res.Assignments {
		if a.End == a.Start {
			continue
		}
		stages = append(stages, &pipelinepb.StageRef{
			Name:       a.Worker.Name,
			Addr:       a.Worker.Addr,
			StartLayer: int32(a.Start),
			EndLayer:   int32(a.End),
		})
	}
	router := pipelinepb.NewRouterClient(c.conn(sp.routerAddr))
	reqCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	ack, err := router.SetPipeline(reqCtx, &pipelinepb.SetPipelineRequest{
		Stages: stages, Generation: gen,
	})
	if err != nil {
		return fmt.Errorf("router: %w", err)
	}
	if !ack.Ok {
		return fmt.Errorf("router: %s", ack.Error)
	}

	c.mu.Lock()
	c.lastApplied = res
	c.lastPush = time.Now()
	c.lastError = ""
	c.mu.Unlock()
	return nil
}

func (c *Controller) conn(addr string) *grpc.ClientConn {
	c.mu.Lock()
	defer c.mu.Unlock()
	if conn, ok := c.conns[addr]; ok {
		return conn
	}
	conn, _ := grpc.NewClient(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	c.conns[addr] = conn
	return conn
}

func (c *Controller) updateStatus(ctx context.Context, cr *unstructured.Unstructured, res *partition.Result, phase string) error {
	c.mu.Lock()
	gen := c.generation
	lastErr := c.lastError
	c.mu.Unlock()

	status := map[string]any{
		"phase":      phase,
		"generation": gen,
	}
	if lastErr != "" {
		status["lastError"] = lastErr
	}
	if res != nil {
		status["bottleneckMs"] = fmt.Sprintf("%.2f", res.BottleneckMs)
		var assignments []any
		for _, a := range res.Assignments {
			assignments = append(assignments, map[string]any{
				"worker":     a.Worker.Name,
				"node":       a.Worker.Node,
				"startLayer": int64(a.Start),
				"endLayer":   int64(a.End),
			})
		}
		status["assignments"] = assignments
	}
	cr = cr.DeepCopy()
	unstructured.SetNestedMap(cr.Object, status, "status")
	_, err := c.dyn.Resource(PipelineGVR).Namespace(c.cfg.Namespace).Update(ctx, cr, metav1.UpdateOptions{})
	if err != nil {
		log.Printf("status update failed (non-fatal): %v", err)
	}
	return nil
}

// State powers the debug endpoint consumed by the bench harness.
func (c *Controller) State() map[string]any {
	c.mu.Lock()
	defer c.mu.Unlock()
	out := map[string]any{
		"generation": c.generation,
		"static":     c.cfg.Static,
		"last_error": c.lastError,
	}
	if c.lastApplied != nil {
		var stages []map[string]any
		for _, a := range c.lastApplied.Assignments {
			stages = append(stages, map[string]any{
				"worker": a.Worker.Name, "node": a.Worker.Node,
				"start": a.Start, "end": a.End, "speed": a.Worker.Speed,
			})
		}
		out["assignments"] = stages
		out["bottleneck_ms"] = c.lastApplied.BottleneckMs
	}
	out["telemetry"] = c.store.Snapshot()
	return out
}

func describe(res *partition.Result) string {
	s := ""
	for i, a := range res.Assignments {
		if i > 0 {
			s += " -> "
		}
		s += fmt.Sprintf("%s[%d,%d)", a.Worker.Name, a.Start, a.End)
	}
	return s
}

// unstructured helpers

func str(u *unstructured.Unstructured, fields ...string) string {
	v, _, _ := unstructured.NestedString(u.Object, fields...)
	return v
}

func num(u *unstructured.Unstructured, fields ...string) int64 {
	v, _, _ := unstructured.NestedInt64(u.Object, fields...)
	return v
}

func fnum(u *unstructured.Unstructured, fields ...string) float64 {
	if v, ok, _ := unstructured.NestedFloat64(u.Object, fields...); ok {
		return v
	}
	return float64(num(u, fields...))
}
