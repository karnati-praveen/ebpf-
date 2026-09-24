// Kubernetes implementation of the substrate contract. Every k8s.io import in
// this package lives in this file; controller.go is substrate-independent.
package controller

import (
	"context"
	"fmt"
	"log"
	"sort"
	"time"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/client-go/dynamic"
	"k8s.io/client-go/kubernetes"
)

var PipelineGVR = schema.GroupVersionResource{
	Group:    "kubeedgeinfer.io",
	Version:  "v1alpha1",
	Resource: "inferencepipelines",
}

// K8sSource reads the InferencePipeline CR, discovers worker pods, and writes
// status back to the CR it last read.
type K8sSource struct {
	kube       kubernetes.Interface
	dyn        dynamic.Interface
	store      *TelemetryStore
	namespace  string
	selector   string
	workerPort int
	heartbeat  time.Duration

	cr *unstructured.Unstructured // last CR read by Spec; target for Report
}

func NewK8sSource(kube kubernetes.Interface, dyn dynamic.Interface, store *TelemetryStore,
	namespace, selector string, workerPort int, heartbeat time.Duration) *K8sSource {
	return &K8sSource{
		kube: kube, dyn: dyn, store: store, namespace: namespace,
		selector: selector, workerPort: workerPort, heartbeat: heartbeat,
	}
}

func (k *K8sSource) Spec(ctx context.Context) (PipelineSpec, bool, error) {
	crs, err := k.dyn.Resource(PipelineGVR).Namespace(k.namespace).List(ctx, metav1.ListOptions{})
	if err != nil {
		return PipelineSpec{}, false, fmt.Errorf("list pipelines: %w", err)
	}
	if len(crs.Items) == 0 {
		return PipelineSpec{}, false, nil
	}
	k.cr = &crs.Items[0]
	sp := PipelineSpec{
		Model:       str(k.cr, "spec", "model"),
		Backend:     str(k.cr, "spec", "backend"),
		TotalLayers: int(num(k.cr, "spec", "totalLayers")),
		PerLayerMs:  fnum(k.cr, "spec", "perLayerMs"),
		Workers:     num(k.cr, "spec", "workers"),
		RouterAddr:  str(k.cr, "spec", "routerAddr"),
	}
	sp.applyDefaults()
	return sp, true, nil
}

// Workers returns Running worker pods whose node agent heartbeat is fresh, in a
// deterministic pipeline order. Dropping a pod whose heartbeat went stale is
// the HEAL trigger: the Decider sees a changed worker set and forces a
// repartition across survivors.
//
// Ordering is (node, pod name), not node alone: sort.Slice is not stable, so
// with several workers on one node -- the single-machine GPU layout, where
// every pod shares a node -- ordering by node alone leaves ties to be broken
// arbitrarily. The Decider compares worker identity position-by-position, so a
// reshuffle would look like a changed worker set and force a pointless
// repartition on every tick.
func (k *K8sSource) Workers(ctx context.Context) ([]WorkerRef, error) {
	list, err := k.kube.CoreV1().Pods(k.namespace).List(ctx, metav1.ListOptions{
		LabelSelector: k.selector,
	})
	if err != nil {
		return nil, fmt.Errorf("list pods: %w", err)
	}
	var out []WorkerRef
	for i := range list.Items {
		p := &list.Items[i]
		if p.Status.Phase != corev1.PodRunning || p.Status.PodIP == "" || p.DeletionTimestamp != nil {
			continue
		}
		if !podReady(p) {
			continue
		}
		if _, alive := k.store.Node(p.Spec.NodeName, k.heartbeat); !alive {
			continue
		}
		out = append(out, WorkerRef{
			Name: p.Name,
			Addr: fmt.Sprintf("%s:%d", p.Status.PodIP, k.workerPort),
			Node: p.Spec.NodeName,
		})
	}
	sortWorkers(out)
	return out, nil
}

func (k *K8sSource) Report(ctx context.Context, st Status) error {
	if k.cr == nil {
		return nil
	}
	status := map[string]any{
		"phase":      st.Phase,
		"generation": st.Generation,
	}
	if st.LastError != "" {
		status["lastError"] = st.LastError
	}
	if st.Result != nil {
		status["bottleneckMs"] = fmt.Sprintf("%.2f", st.Result.BottleneckMs)
		var assignments []any
		for _, a := range st.Result.Assignments {
			assignments = append(assignments, map[string]any{
				"worker":     a.Worker.Name,
				"node":       a.Worker.Node,
				"startLayer": int64(a.Start),
				"endLayer":   int64(a.End),
			})
		}
		status["assignments"] = assignments
	}
	cr := k.cr.DeepCopy()
	unstructured.SetNestedMap(cr.Object, status, "status")
	if _, err := k.dyn.Resource(PipelineGVR).Namespace(k.namespace).Update(ctx, cr, metav1.UpdateOptions{}); err != nil {
		// Non-fatal by design: losing status must not stop the control loop.
		log.Printf("status update failed (non-fatal): %v", err)
	}
	return nil
}

func podReady(p *corev1.Pod) bool {
	for _, cond := range p.Status.Conditions {
		if cond.Type == corev1.PodReady {
			return cond.Status == corev1.ConditionTrue
		}
	}
	return false
}

// sortWorkers imposes the deterministic (node, name) order both substrates
// rely on. See the Workers doc comment for why node alone is not enough.
func sortWorkers(w []WorkerRef) {
	sort.Slice(w, func(i, j int) bool {
		if w[i].Node != w[j].Node {
			return w[i].Node < w[j].Node
		}
		return w[i].Name < w[j].Name
	})
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
