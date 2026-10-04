package partition

import (
	"math"
	"math/rand"
	"testing"
	"time"
)

func TestLatencyAvoidsHopWhileThroughputSplits(t *testing.T) {
	in := twoWorkers(1)
	in.LinkMs = []float64{20}
	lat, e := OptimalForObjective(in, ObjectiveLatency)
	if e != nil {
		t.Fatal(e)
	}
	thru, e := Optimal(in)
	if e != nil {
		t.Fatal(e)
	}
	if lat.Assignments[0].End != 28 || lat.Assignments[1].End != lat.Assignments[1].Start {
		t.Fatalf("latency must stay local: %+v", lat)
	}
	if thru.Assignments[1].End == thru.Assignments[1].Start || !(thru.BottleneckMs < lat.BottleneckMs) || !(lat.PipelineMs < thru.PipelineMs) {
		t.Fatalf("objectives not distinct: latency=%+v throughput=%+v", lat, thru)
	}
}

func TestLatencyDPMatchesExhaustiveThreeWorkerLayouts(t *testing.T) {
	rng := rand.New(rand.NewSource(20261004))
	for trial := 0; trial < 100; trial++ {
		in := Input{TotalLayers: 8, PerLayerMs: 2 + rng.Float64()*10, EmbedMs: rng.Float64() * 5, HeadMs: rng.Float64() * 20,
			Workers: []Worker{{Name: "a", Speed: .2 + rng.Float64()}, {Name: "b", Speed: .2 + rng.Float64()}, {Name: "c", Speed: .2 + rng.Float64()}}, LinkMs: []float64{rng.Float64() * 10, rng.Float64() * 10}}
		got, e := OptimalForObjective(in, ObjectiveLatency)
		if e != nil {
			t.Fatal(e)
		}
		best := math.Inf(1)
		for a := 0; a <= 8; a++ {
			for b := a; b <= 8; b++ {
				best = math.Min(best, EvaluatePipeline(in, [][2]int{{0, a}, {a, b}, {b, 8}}))
			}
		}
		if math.Abs(got.PipelineMs-best) > 1e-8 {
			t.Fatalf("trial %d got %.9f exhaustive %.9f", trial, got.PipelineMs, best)
		}
		if got.BottleneckMs != Evaluate(in, got.Splits()) {
			t.Fatal("bottleneck reporting changed")
		}
	}
}

func TestLatencyGatePricesPipelineAndRecoveryBypassesGate(t *testing.T) {
	d := NewDecider(.15, 0)
	d.Objective = ObjectiveLatency
	d.Policy = PolicyGate
	d.Gate = GateParams{HorizonS: 30, TransitionFixedMs: 1000}
	in := twoWorkers(.5)
	now := time.Now()
	if _, changed, e := d.Decide(now, in, false); e != nil || !changed {
		t.Fatal(e)
	}
	in.Workers[0].Speed = .4
	in.Workers[1].Speed = 1
	_, changed, e := d.Decide(now.Add(time.Minute), in, false)
	if e != nil || !changed {
		t.Fatalf("latency move not accepted: %v %+v", e, d.LastDecision())
	}
	dec := d.LastDecision()
	if dec.Objective != ObjectiveLatency || dec.TokensStay != 30000/dec.CurrentObjectiveMs || dec.TokensAdapt != 29000/dec.OptimalObjectiveMs {
		t.Fatalf("gate used wrong units: %+v", dec)
	}
	in.Workers = in.Workers[:1]
	in.LinkMs = nil
	d.Gate.HorizonS = 0
	if _, changed, e := d.Decide(now.Add(2*time.Minute), in, false); e != nil || !changed || d.LastDecision().Reason != "recovery-or-initial" {
		t.Fatalf("recovery blocked: %v %+v", e, d.LastDecision())
	}
}

func TestObjectiveRejectsUnknownMode(t *testing.T) {
	if _, e := OptimalForObjective(twoWorkers(1), "typo"); e == nil {
		t.Fatal("unknown objective accepted")
	}
}

func TestLiveRemainingBudgetShortensGateAndRecoveryStillWorks(t *testing.T) {
	d := deciderFor(PolicyGate, 600)
	remaining := 1.0
	d.Gate.RemainingTokens = &remaining
	dec, changed := settleThenDerate(t, d)
	if changed || dec.GateAccepts || dec.RemainingTokens == nil || dec.HorizonS > 1 {
		t.Fatalf("short job paid a long transition: %+v", dec)
	}
	d.HoldVoluntary = true
	in := twoWorkers(1)
	in.Workers = in.Workers[:1]
	in.LinkMs = nil
	if _, changed, e := d.Decide(time.Now().Add(time.Hour), in, false); e != nil || !changed {
		t.Fatalf("idle hold blocked recovery: %v", e)
	}
}
