package controller

import (
	"context"
	"sync"
	"time"

	"kubeedgeinfer/gen/pipelinepb"
)

// TelemetryStore implements the Telemetry gRPC service and keeps the latest
// per-node GPU state plus a global flow table. Node agents share one kernel
// in kind, so every agent may report every flow; the store deduplicates by
// (src, dst, port).
type TelemetryStore struct {
	pipelinepb.UnimplementedTelemetryServer

	mu    sync.Mutex
	nodes map[string]*nodeState
	flows map[flowKey]flowStat
}

type nodeState struct {
	gpu      *pipelinepb.GpuStat
	lastSeen time.Time
}

type flowKey struct {
	src, dst string
	port     uint32
}

type flowStat struct {
	srttMs      float64
	bytesPerSec float64
	lastSeen    time.Time
}

func NewTelemetryStore() *TelemetryStore {
	return &TelemetryStore{
		nodes: map[string]*nodeState{},
		flows: map[flowKey]flowStat{},
	}
}

func (s *TelemetryStore) Report(ctx context.Context, msg *pipelinepb.NodeTelemetry) (*pipelinepb.Ack, error) {
	now := time.Now()
	s.mu.Lock()
	defer s.mu.Unlock()
	s.nodes[msg.Node] = &nodeState{gpu: msg.Gpu, lastSeen: now}
	for _, l := range msg.Links {
		key := flowKey{src: l.SrcIp, dst: l.DstIp, port: l.DstPort}
		if l.Samples == 0 && l.BytesPerSec == 0 {
			continue
		}
		s.flows[key] = flowStat{
			srttMs:      l.SrttMs,
			bytesPerSec: l.BytesPerSec,
			lastSeen:    now,
		}
	}
	return &pipelinepb.Ack{Ok: true}, nil
}

// Node returns the freshest GPU stat for a node and whether its agent
// heartbeat is within staleAfter.
func (s *TelemetryStore) Node(node string, staleAfter time.Duration) (*pipelinepb.GpuStat, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	st, ok := s.nodes[node]
	if !ok || time.Since(st.lastSeen) > staleAfter {
		return nil, false
	}
	return st.gpu, true
}

// LinkSRTT returns the observed sRTT for src->dst:port, if fresh.
func (s *TelemetryStore) LinkSRTT(src, dst string, port uint32, staleAfter time.Duration) (float64, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	f, ok := s.flows[flowKey{src: src, dst: dst, port: port}]
	if !ok || time.Since(f.lastSeen) > staleAfter {
		return 0, false
	}
	return f.srttMs, true
}

// LinkSRTTToDst returns the freshest observed sRTT of any flow into
// dst:port. The router drives the stage chain hub-and-spoke, so the hop
// feeding a stage is router->stage; matching by destination captures it
// without knowing the router's pod IP.
func (s *TelemetryStore) LinkSRTTToDst(dst string, port uint32, staleAfter time.Duration) (float64, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	var (
		best     float64
		bestSeen time.Time
		found    bool
	)
	for key, f := range s.flows {
		if key.dst != dst || key.port != port || time.Since(f.lastSeen) > staleAfter {
			continue
		}
		if !found || f.lastSeen.After(bestSeen) {
			best, bestSeen, found = f.srttMs, f.lastSeen, true
		}
	}
	return best, found
}

// Snapshot returns a JSON-friendly view for the debug endpoint.
func (s *TelemetryStore) Snapshot() map[string]any {
	s.mu.Lock()
	defer s.mu.Unlock()
	nodes := map[string]any{}
	for name, st := range s.nodes {
		nodes[name] = map[string]any{
			"temp_c":       st.gpu.GetTempC(),
			"throttled":    st.gpu.GetThrottled(),
			"speed_factor": st.gpu.GetSpeedFactor(),
			"age_s":        time.Since(st.lastSeen).Seconds(),
		}
	}
	flows := []map[string]any{}
	for key, f := range s.flows {
		if time.Since(f.lastSeen) > 15*time.Second {
			continue
		}
		flows = append(flows, map[string]any{
			"src": key.src, "dst": key.dst, "port": key.port,
			"srtt_ms": f.srttMs, "bytes_per_sec": f.bytesPerSec,
		})
	}
	return map[string]any{"nodes": nodes, "flows": flows}
}
