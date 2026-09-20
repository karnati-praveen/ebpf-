// Package controller implements KubeEdgeInfer's DECIDE/ACT/HEAL loop: it
// aggregates node-agent telemetry, computes the optimal layer split, and
// applies it to workers and router over gRPC, tracking everything in the
// InferencePipeline custom resource.
package controller

import (
	"context"
	"fmt"
	"log"
	"sync"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"kubeedgeinfer/gen/pipelinepb"
	"kubeedgeinfer/internal/partition"
)

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
	src     Source
	store   *TelemetryStore
	decider *partition.Decider

	mu            sync.Mutex
	generation    int64
	staticApplied bool
	lastApplied   *partition.Result
	lastPush      time.Time
	lastError     string
	conns         map[string]*grpc.ClientConn
	frozenSpeed   map[string]float64 // node -> speed, captured once when ProfileOnce
	frozenLinkMs  map[string]float64 // dst ip -> link ms, captured once when ProfileOnce
}

func New(cfg Config, src Source, store *TelemetryStore) *Controller {
	return &Controller{
		cfg:          cfg,
		src:          src,
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

func (c *Controller) reconcile(ctx context.Context) error {
	sp, ok, err := c.src.Spec(ctx)
	if err != nil {
		return err
	}
	if !ok {
		return nil // nothing configured yet; idle
	}

	workers, err := c.src.Workers(ctx)
	if err != nil {
		return err
	}
	if len(workers) == 0 {
		return c.report(ctx, nil, "NoWorkers")
	}

	input := c.buildInput(sp, workers)

	if c.cfg.Static {
		return c.reconcileStatic(ctx, sp, input)
	}

	res, changed, err := c.decider.Decide(time.Now(), input, false)
	if err != nil {
		return c.report(ctx, nil, "PartitionError: "+err.Error())
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
	return c.report(ctx, res, "Running")
}

// reconcileStatic applies one equal split when all expected workers are up,
// then never touches the pipeline again — the ablation baseline.
func (c *Controller) reconcileStatic(ctx context.Context, sp PipelineSpec, input partition.Input) error {
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
		return c.report(ctx, last, "RunningStatic")
	}
	if sp.Workers > 0 && int64(len(input.Workers)) < sp.Workers {
		return c.report(ctx, nil, "WaitingForWorkers")
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
	return c.report(ctx, res, "RunningStatic")
}

func (c *Controller) buildInput(sp PipelineSpec, workers []WorkerRef) partition.Input {
	input := partition.Input{
		TotalLayers: sp.TotalLayers,
		PerLayerMs:  sp.PerLayerMs,
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	for _, p := range workers {
		speed := 1.0
		if gpu, ok := c.store.Node(p.Node, c.cfg.HeartbeatTimeout); ok && gpu.GetSpeedFactor() > 0 {
			speed = gpu.GetSpeedFactor()
		}
		if c.cfg.ProfileOnce {
			if frozen, ok := c.frozenSpeed[p.Node]; ok {
				speed = frozen
			} else {
				c.frozenSpeed[p.Node] = speed
			}
		}
		input.Workers = append(input.Workers, partition.Worker{
			Name:  p.Name,
			Addr:  p.Addr, // full host:port; workers may share a machine
			Node:  p.Node,
			Speed: speed,
		})
	}
	// The router drives stages hub-and-spoke, so the transfer cost feeding
	// stage i+1 is the network path into that stage's pod.
	for i := 0; i+1 < len(workers); i++ {
		next := workers[i+1]
		ms := c.cfg.DefaultLinkMs
		if srtt, ok := c.store.LinkSRTTToDst(next.ip(), next.port(), 15*time.Second); ok {
			ms = srtt
		}
		if c.cfg.ProfileOnce {
			key := next.Addr
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
func (c *Controller) apply(ctx context.Context, sp PipelineSpec, res *partition.Result) error {
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
func (c *Controller) push(ctx context.Context, sp PipelineSpec, res *partition.Result, gen int64) error {
	for _, a := range res.Assignments {
		client := pipelinepb.NewWorkerClient(c.conn(a.Worker.Addr))
		reqCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
		reply, err := client.AssignLayers(reqCtx, &pipelinepb.AssignLayersRequest{
			StartLayer:  int32(a.Start),
			EndLayer:    int32(a.End),
			TotalLayers: int32(sp.TotalLayers),
			Backend:     sp.Backend,
			Model:       sp.Model,
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
	router := pipelinepb.NewRouterClient(c.conn(sp.RouterAddr))
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

// report publishes status through the substrate. Failure is non-fatal by
// design: losing status must not stop the control loop.
func (c *Controller) report(ctx context.Context, res *partition.Result, phase string) error {
	c.mu.Lock()
	st := Status{Phase: phase, Generation: c.generation, LastError: c.lastError, Result: res}
	c.mu.Unlock()
	return c.src.Report(ctx, st)
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
		// Two distinct predictions: bottleneck governs throughput, pipeline
		// governs per-request latency. Reporting only the first is what made
		// the old fidelity check compare a throughput quantity against a
		// latency observable.
		out["bottleneck_ms"] = c.lastApplied.BottleneckMs
		out["pipeline_ms"] = c.lastApplied.PipelineMs
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
