// Standalone implementation of the substrate contract: no API server, no
// orchestrator. Configuration comes from a file; discovery comes from the
// node-agent telemetry the controller already receives.
package controller

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"sync"
	"time"

	"kubeedgeinfer/internal/partition"
)

// LocalSource reads a JSON config file for the spec and derives the worker set
// from the telemetry store. Status is held in memory and served by the
// existing GET /state endpoint, which the dashboard and bench harness already
// prefer over the CR.
type LocalSource struct {
	path      string
	store     *TelemetryStore
	heartbeat time.Duration

	mu     sync.Mutex
	status Status
}

func NewLocalSource(path string, store *TelemetryStore, heartbeat time.Duration) *LocalSource {
	return &LocalSource{path: path, store: store, heartbeat: heartbeat}
}

// localSpec mirrors the CRD's spec fields 1:1 so both substrates stay
// semantically identical and a config can be translated either way.
type localSpec struct {
	Model       string  `json:"model"`
	Backend     string  `json:"backend"`
	TotalLayers int     `json:"totalLayers"`
	PerLayerMs  float64 `json:"perLayerMs"`
	Workers     int64   `json:"workers"`
	RouterAddr  string  `json:"routerAddr"`

	// Measured cost model; optional.
	EmbedMs       float64 `json:"embedMs"`
	HeadMs        float64 `json:"headMs"`
	ContextLen    int     `json:"contextLen"`
	PerLayerByCtx []struct {
		ContextLen int     `json:"contextLen"`
		PerLayerMs float64 `json:"perLayerMs"`
	} `json:"perLayerByCtx"`
}

func (l *LocalSource) Spec(ctx context.Context) (PipelineSpec, bool, error) {
	b, err := os.ReadFile(l.path)
	if os.IsNotExist(err) {
		// Not configured yet is not an error; the controller idles, exactly as
		// it does under Kubernetes when no CR exists.
		return PipelineSpec{}, false, nil
	}
	if err != nil {
		return PipelineSpec{}, false, fmt.Errorf("read %s: %w", l.path, err)
	}
	var ls localSpec
	if err := json.Unmarshal(b, &ls); err != nil {
		return PipelineSpec{}, false, fmt.Errorf("parse %s: %w", l.path, err)
	}
	if ls.TotalLayers < 1 {
		return PipelineSpec{}, false, fmt.Errorf("%s: totalLayers must be >= 1", l.path)
	}
	sp := PipelineSpec{
		Model: ls.Model, Backend: ls.Backend, TotalLayers: ls.TotalLayers,
		PerLayerMs: ls.PerLayerMs, Workers: ls.Workers, RouterAddr: ls.RouterAddr,
		EmbedMs: ls.EmbedMs, HeadMs: ls.HeadMs, ContextLen: ls.ContextLen,
	}
	for _, c := range ls.PerLayerByCtx {
		if c.ContextLen <= 0 || c.PerLayerMs <= 0 {
			return PipelineSpec{}, false, fmt.Errorf("%s: perLayerByCtx entries need positive contextLen and perLayerMs", l.path)
		}
		sp.PerLayerByCtx = append(sp.PerLayerByCtx, partition.CtxCost{ContextLen: c.ContextLen, PerLayerMs: c.PerLayerMs})
	}
	sp.applyDefaults()
	if ls.RouterAddr == "" {
		// The Kubernetes default is a cluster DNS name, which means nothing
		// here. Standalone runs the router on the controller host.
		sp.RouterAddr = "127.0.0.1:50052"
	}
	return sp, true, nil
}

// Workers derives the live set from node-agent heartbeats. Staleness is the
// same HEAL trigger the Kubernetes path uses -- there it additionally gates on
// pod readiness, which standalone gets from the agent's own health check of
// its local worker.
func (l *LocalSource) Workers(ctx context.Context) ([]WorkerRef, error) {
	return l.store.LiveWorkers(l.heartbeat), nil
}

func (l *LocalSource) Report(ctx context.Context, st Status) error {
	l.mu.Lock()
	l.status = st
	l.mu.Unlock()
	return nil
}

// Status returns the last published status, for the HTTP state endpoint.
func (l *LocalSource) Status() Status {
	l.mu.Lock()
	defer l.mu.Unlock()
	return l.status
}
