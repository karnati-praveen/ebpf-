package controller

import (
	"context"
	"net"
	"strconv"

	"kubeedgeinfer/internal/partition"
)

// The controller's substrate -- Kubernetes or standalone -- is reached only
// through these three interfaces. Everything else (the DP, hysteresis, the
// gRPC actuation path) is substrate-independent and must stay that way.

// PipelineSpec is the controller's configuration input. Under Kubernetes it
// comes from the InferencePipeline CR; standalone, from a config file.
type PipelineSpec struct {
	Model       string
	Backend     string
	TotalLayers int
	PerLayerMs  float64
	Workers     int64 // expected count; static mode waits for all
	RouterAddr  string

	// Measured cost model (all optional; zero keeps the layer-proportional
	// model). See partition.Input for why each term exists.
	EmbedMs       float64
	HeadMs        float64
	ContextLen    int // operating context length; also sizes the transition gate
	PerLayerByCtx []partition.CtxCost
}

// applyDefaults is shared by every source so both substrates agree.
func (s *PipelineSpec) applyDefaults() {
	if s.Backend == "" {
		s.Backend = "sim"
	}
	if s.PerLayerMs == 0 {
		s.PerLayerMs = 30
	}
	if s.RouterAddr == "" {
		s.RouterAddr = "router:50052"
	}
}

// WorkerRef is one discovered shard worker.
//
// Addr is a full host:port, not an IP: several workers can share a machine on
// different ports (the single-GPU layout), so there is no single global worker
// port. Node is the telemetry correlation key -- it must match the NODE_NAME
// the node agent reports.
type WorkerRef struct {
	Name string
	Addr string
	Node string
}

// ip returns the host part of Addr, for keying link telemetry.
func (w WorkerRef) ip() string {
	host, _, err := net.SplitHostPort(w.Addr)
	if err != nil {
		return w.Addr
	}
	return host
}

// port returns the port part of Addr, for keying link telemetry.
func (w WorkerRef) port() uint32 {
	_, p, err := net.SplitHostPort(w.Addr)
	if err != nil {
		return 0
	}
	n, err := strconv.Atoi(p)
	if err != nil {
		return 0
	}
	return uint32(n)
}

// Status is what the controller publishes after each reconcile.
type Status struct {
	Phase      string
	Generation int64
	LastError  string
	Result     *partition.Result // nil when there is no current assignment
}

type SpecSource interface {
	// Spec returns the pipeline configuration. ok is false when none is
	// configured yet, which is not an error -- the controller idles.
	Spec(ctx context.Context) (spec PipelineSpec, ok bool, err error)
}

type WorkerSource interface {
	// Workers returns live shard workers in deterministic pipeline order.
	// Dropping a worker whose heartbeat went stale is the HEAL trigger.
	Workers(ctx context.Context) ([]WorkerRef, error)
}

type StatusSink interface {
	// Report publishes status. Implementations should treat failure as
	// non-fatal: losing status must not stop the control loop.
	Report(ctx context.Context, st Status) error
}

// Source is the full substrate contract. A single type implements all three so
// that, under Kubernetes, the status write targets the same CR the spec was
// read from.
type Source interface {
	SpecSource
	WorkerSource
	StatusSink
}
