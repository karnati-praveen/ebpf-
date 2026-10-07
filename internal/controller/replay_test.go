package controller

import (
	"context"
	"encoding/json"
	"math"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"kubeedgeinfer/internal/partition"
)

func TestLiveReplayContextAndLegacyRouter(t *testing.T) {
	contextTokens := 384.0
	w := WorkloadSnapshot{ActiveRequests: 2, RemainingTokens: 64, ReplayContextTokens: &contextTokens}
	server := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		w.ObservedAt = float64(time.Now().UnixNano()) / 1e9
		json.NewEncoder(response).Encode(w)
	}))
	defer server.Close()
	c := New(Config{WorkloadURL: server.URL, LiveReplayContext: true,
		Gate: partition.GateParams{TransitionFixedMs: 1000, PrefillMsPerTokenLayer: .2, ContextLen: 64}}, nil, NewTelemetryStore())
	c.observeWorkload(context.Background())
	if c.decider.HoldVoluntary || math.Abs(c.decider.Gate.TransitionMs(28)-3150.4) > 1e-9 {
		t.Fatalf("all contexts not priced: %+v", c.decider.Gate)
	}
	// An old router lacking the new field must not silently use one context.
	w.ReplayContextTokens = nil
	c.observeWorkload(context.Background())
	if !c.decider.HoldVoluntary {
		t.Fatal("missing replay budget allowed voluntary move")
	}
	// Recovery still bypasses a workload hold.
	in := partition.Input{TotalLayers: 2, PerLayerMs: 1, Workers: []partition.Worker{{Name: "survivor", Speed: 1}}}
	_, changed, err := c.decider.Decide(time.Now(), in, true)
	if err != nil || !changed {
		t.Fatal("workload hold prevented recovery")
	}
}
