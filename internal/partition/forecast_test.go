package partition

import (
	"math"
	"testing"
)

func TestForecastFiniteWorkAndDeadline(t *testing.T) {
	p := GateSample{CurrentMs: 200, CandidateMs: 100, TransitionMs: 3000}
	g := ForecastGate{HorizonS: 30}
	v, e := g.Evaluate(p, nil)
	if e != nil || !v.Accept {
		t.Fatalf("long horizon: %+v %v", v, e)
	}
	remaining := 10.0
	g.RemainingTokens = &remaining
	v, e = g.Evaluate(p, nil)
	if e != nil || v.Accept || v.HorizonS != 2 {
		t.Fatalf("small admitted workload: %+v %v", v, e)
	}
	remaining = 0
	v, _ = g.Evaluate(p, nil)
	if v.Accept || v.Reason != "no-remaining-horizon" {
		t.Fatal(v)
	}
	g.RemainingTokens = nil
	g.HorizonS = 0
	v, _ = g.Evaluate(p, nil)
	if v.Accept {
		t.Fatal(v)
	}
}

func TestForecastProbabilityRetainsPairedScenarios(t *testing.T) {
	g := ForecastGate{HorizonS: 30, RequiredProbability: .9, MinSamples: 3}
	p := GateSample{200, 100, 3000}
	v, _ := g.Evaluate(p, []GateSample{p, p})
	if v.Accept || v.Reason != "insufficient-samples" {
		t.Fatal(v)
	}
	v, _ = g.Evaluate(p, []GateSample{p, p, {200, 195, 3000}})
	if v.Accept || math.Abs(v.Probability-2.0/3) > 1e-9 {
		t.Fatal(v)
	}
	v, _ = g.Evaluate(p, []GateSample{p, p, p})
	if !v.Accept || v.Probability != 1 {
		t.Fatal(v)
	}
}

func TestForecastRejectsInvalidInputs(t *testing.T) {
	p := GateSample{200, 100, 3000}
	for _, g := range []ForecastGate{{HorizonS: -1}, {HorizonS: 30, RequiredProbability: 1.1}, {HorizonS: math.NaN()}} {
		if _, e := g.Evaluate(p, nil); e == nil {
			t.Fatal("invalid configuration accepted")
		}
	}
	if _, e := (ForecastGate{HorizonS: 30}).Evaluate(GateSample{}, nil); e == nil {
		t.Fatal("zero costs accepted")
	}
}

func TestTransitionCalibrationWarmupAndVariance(t *testing.T) {
	c := TransitionCalibration{}
	if c.PredictMs(3000, 2) != 3000 {
		t.Fatal("missing cold start")
	}
	c.Observe(1000)
	if c.PredictMs(3000, 2) != 3000 {
		t.Fatal("premature calibration")
	}
	c.Observe(3000)
	if c.PredictMs(3000, 2) != 2000 || math.Abs(c.StdDevMs()-math.Sqrt(2000000)) > 1e-6 {
		t.Fatal(c)
	}
	if e := c.Observe(math.NaN()); e == nil || c.N != 2 {
		t.Fatal("invalid observation changed calibration")
	}
}
