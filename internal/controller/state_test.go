package controller

import (
	"testing"

	"kubeedgeinfer/internal/partition"
)

func TestStateReportsLatestEvaluationWithoutMoving(t *testing.T) {
	c := New(Config{Objective: partition.Objective("auto")}, nil, NewTelemetryStore())
	c.lastApplied = &partition.Result{BottleneckMs: 2, PipelineMs: 4}
	c.lastEvaluated = &partition.Result{BottleneckMs: 5, PipelineMs: 8}
	c.workload = &WorkloadSnapshot{ActiveRequests: 2}
	c.decisionObjective = partition.ObjectiveCapacity
	s := c.State()
	if s["bottleneck_ms"] != 5.0 || s["pipeline_ms"] != 8.0 || s["objective_ms"] != 5.0 {
		t.Fatalf("stale applied-cost snapshot: %+v", s)
	}
	if c.lastApplied.BottleneckMs != 2 {
		t.Fatal("debug report changed applied layout")
	}
}
