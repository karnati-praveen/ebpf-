package main

import (
	"kubeedgeinfer/internal/partition"
	"math"
	"testing"
)

func TestOracleChargesDowntimeAcrossSnapshotBoundary(t *testing.T) {
	in := partition.Input{TotalLayers: 2, PerLayerMs: 100, Workers: []partition.Worker{{Name: "a", Speed: 1}, {Name: "b", Speed: 1}}, LinkMs: []float64{0}}
	c := Case{At: 10, RunEnd: 20, Point: partition.GateSample{TransitionMs: 3000}, From: [][2]int{{0, 2}, {2, 2}}, To: [][2]int{{0, 1}, {1, 2}}, Future: []Snapshot{{At: 9, Input: in}, {At: 12, Input: in}, {At: 18, Input: in}}}
	stay, adapt := futureCapacity(c)
	if math.Abs(stay-50) > 1e-9 || math.Abs(adapt-70) > 1e-9 {
		t.Fatalf("stay=%v adapt=%v", stay, adapt)
	}
	c.Point.TransitionMs = 11000
	_, adapt = futureCapacity(c)
	if adapt != 0 {
		t.Fatalf("downtime exceeds remaining trace: %v", adapt)
	}
	c.Future = append(c.Future, Snapshot{At: 25, Input: in})
	stay, _ = futureCapacity(c)
	if stay != 50 {
		t.Fatalf("integrated past run end: %v", stay)
	}
}
