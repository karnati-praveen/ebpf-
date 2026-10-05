package controller

import (
	"context"
	"encoding/json"
	"shardwise/internal/partition"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestWorkloadAutoObjectiveAndUnavailableHold(t *testing.T) {
	active, remaining := 1, 64.0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(WorkloadSnapshot{ActiveRequests: active, RemainingTokens: remaining, ObservedAt: float64(time.Now().UnixNano()) / 1e9})
	}))
	defer server.Close()
	c := New(Config{Objective: partition.Objective("auto"), WorkloadURL: server.URL, RemainingWorkAware: true}, nil, NewTelemetryStore())
	c.observeWorkload(context.Background())
	if c.decider.Objective != partition.ObjectiveLatency || c.decider.HoldVoluntary || *c.decider.Gate.RemainingTokens != 64 {
		t.Fatalf("single workload: %+v", c.decider)
	}
	active = 2
	remaining = 128
	c.observeWorkload(context.Background())
	if c.decider.Objective != partition.ObjectiveThroughput || *c.decider.Gate.RemainingTokens != 128 {
		t.Fatalf("concurrent workload: %+v", c.decider)
	}
	active = 0
	remaining = 0
	c.observeWorkload(context.Background())
	if !c.decider.HoldVoluntary {
		t.Fatal("idle move permitted")
	}
	server.Close()
	c.observeWorkload(context.Background())
	if !c.decider.HoldVoluntary || c.workloadError == "" || *c.decider.Gate.RemainingTokens != 0 {
		t.Fatal("unknown demand permitted voluntary move")
	}
	reset := newDecider(c.cfg)
	if reset.Objective != partition.ObjectiveLatency {
		t.Fatal("auto reset lost initial latency objective")
	}
}

func TestWorkloadRejectsStaleAndInconsistentSnapshots(t *testing.T) {
	for _, sample := range []WorkloadSnapshot{{ActiveRequests: 1, RemainingTokens: 5, ObservedAt: 1}, {ActiveRequests: -1}, {ActiveRequests: 0, RemainingTokens: 5, ObservedAt: float64(time.Now().Unix())}} {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { json.NewEncoder(w).Encode(sample) }))
		_, err := readWorkload(context.Background(), server.URL)
		server.Close()
		if err == nil {
			t.Fatal("bad snapshot accepted")
		}
	}
}
