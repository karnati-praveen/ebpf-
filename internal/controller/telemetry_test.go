package controller

import (
	"context"
	"testing"
	"time"

	"kubeedgeinfer/gen/pipelinepb"
)

// The H3 comparison is only valid if kernel and application measurements of
// the same link are never mixed. Each source must see only its own flows.
func TestLinkCostSelectsSourceWithoutMixing(t *testing.T) {
	s := NewTelemetryStore()
	ctx := context.Background()
	s.Report(ctx, &pipelinepb.NodeTelemetry{Node: "vm1", Links: []*pipelinepb.LinkStat{
		{SrcIp: "10.0.0.4", DstIp: "10.0.0.5", DstPort: 50051, SrttMs: 80.4, Samples: 9},
	}})
	s.Report(ctx, &pipelinepb.NodeTelemetry{Node: "router-app", Links: []*pipelinepb.LinkStat{
		{SrcIp: "app", DstIp: "10.0.0.5", DstPort: 50051, SrttMs: 83.1, Samples: 30},
	}})

	cases := []struct {
		src    LinkSource
		want   float64
		wantOK bool
	}{
		{LinkSourceEBPF, 80.4, true},
		{LinkSourceApp, 83.1, true},
		{LinkSourceEBPFThenApp, 80.4, true},
		{LinkSourceNone, 0, false},
	}
	for _, c := range cases {
		got, ok := s.LinkCost(c.src, "10.0.0.5", 50051, time.Minute)
		if ok != c.wantOK || got != c.want {
			t.Errorf("%s: got (%v, %v) want (%v, %v)", c.src, got, ok, c.want, c.wantOK)
		}
	}
}

// With no fresh kernel sample, ebpf+app must fall back to the application
// measurement, and ebpf alone must report nothing rather than borrowing it.
func TestLinkCostFallbackAndIsolation(t *testing.T) {
	s := NewTelemetryStore()
	s.Report(context.Background(), &pipelinepb.NodeTelemetry{Node: "router-app",
		Links: []*pipelinepb.LinkStat{{SrcIp: "app", DstIp: "10.0.0.6", DstPort: 50051, SrttMs: 12.5, Samples: 4}}})
	if v, ok := s.LinkCost(LinkSourceEBPFThenApp, "10.0.0.6", 50051, time.Minute); !ok || v != 12.5 {
		t.Errorf("ebpf+app fallback: got (%v, %v)", v, ok)
	}
	if _, ok := s.LinkCost(LinkSourceEBPF, "10.0.0.6", 50051, time.Minute); ok {
		t.Error("ebpf must not borrow an application measurement")
	}
}

// The router reports under node "router-app" with no worker address; it must
// never be discovered as a worker.
func TestRouterTelemetryIsNotAWorker(t *testing.T) {
	s := NewTelemetryStore()
	s.Report(context.Background(), &pipelinepb.NodeTelemetry{Node: "router-app"})
	s.Report(context.Background(), &pipelinepb.NodeTelemetry{Node: "vm2", WorkerAddr: "10.0.0.5:50051"})
	w := s.LiveWorkers(time.Minute)
	if len(w) != 1 || w[0].Node != "vm2" || w[0].Addr != "10.0.0.5:50051" {
		t.Fatalf("LiveWorkers = %+v", w)
	}
}
