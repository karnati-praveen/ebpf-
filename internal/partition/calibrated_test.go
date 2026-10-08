package partition

import (
	"math"
	"testing"
	"time"
)

func TestCompletedBlocksAndReset(t *testing.T) {
	g := CalibratedGate{MinBlocks: 12}
	in := Input{Workers: []Worker{{Name: "a", Addr: "a:1", Speed: 1}}}
	for b := 0; b < 13; b++ {
		g.Observe(time.Unix(int64(100+b*5), 0), in, true)
	}
	if len(g.Blocks) != 12 {
		t.Fatalf("completed blocks: %d", len(g.Blocks))
	}
	in.Workers[0].Speed = 2
	if g.Blocks[0].Workers[0].Speed != 1 {
		t.Fatal("history aliased mutable input")
	}
	g.Observe(time.Unix(170, 0), in, true)
	if len(g.Blocks) != 0 {
		t.Fatal("gap retained stale history")
	}
	g.Observe(time.Unix(175, 0), in, false)
	if g.pending != nil {
		t.Fatal("stale snapshot retained")
	}
}

func TestCalibratedUsesPairedCostsLiveConcurrencyAndRatios(t *testing.T) {
	in := Input{TotalLayers: 9, PerLayerMs: 1, Concurrency: 2, Workers: []Worker{{Name: "a", Addr: "a:1", Speed: 1}, {Name: "b", Addr: "b:1", Speed: 1}, {Name: "c", Addr: "c:1", Speed: 1}}, LinkMs: []float64{1, 1}}
	from := [][2]int{{0, 9}, {9, 9}, {9, 9}}
	to := [][2]int{{0, 5}, {5, 9}, {9, 9}}
	d := NewDecider(.15, 0)
	d.Policy = PolicyGateCalibrated
	d.Objective = ObjectiveCapacity
	d.Gate = GateParams{HorizonS: 30, TransitionFixedMs: 100, SafetyMargin: .13}
	for b := 0; b < 13; b++ {
		d.Calibrated.Observe(time.Unix(int64(100+b*5), 0), in, true)
	}
	d.Calibrated.Ratios = []float64{2, 2, 2, 2, 2, 2, 2, 2, 2, 2}
	dec := &Decision{CurrentObjectiveMs: ObjectiveCost(in, from, d.Objective), OptimalObjectiveMs: ObjectiveCost(in, to, d.Objective)}
	if err := d.evaluateCalibrated(dec, in, from, to); err != nil {
		t.Fatal(err)
	}
	if !dec.GateAccepts || dec.ForecastSamples != 120 || math.Abs(dec.TransitionMs-200) > 1e-9 || dec.EmpiricalProbability != 1 {
		t.Fatalf("unexpected forecast: %+v", dec)
	}
	for _, s := range dec.ForecastScenarios {
		if s.CurrentMs != 9 || s.CandidateMs != 5 || s.TransitionMs != 200 {
			t.Fatal(s)
		}
	}
	d.Calibrated.Ratios = nil
	dec = &Decision{}
	d.evaluateCalibrated(dec, in, from, to)
	if dec.GateAccepts || dec.Reason != "insufficient-calibration-transitions" {
		t.Fatal(dec)
	}
	d.Calibrated.Ratios = []float64{math.NaN(), 1, 1, 1, 1, 1, 1, 1, 1, 1}
	if d.evaluateCalibrated(dec, in, from, to) == nil {
		t.Fatal("NaN ratio accepted")
	}
}

func TestCalibratedRecoveryBypassesColdStartAndHold(t *testing.T) {
	d := NewDecider(.15, time.Minute)
	d.Policy = PolicyGateCalibrated
	d.HoldVoluntary = true
	in := Input{TotalLayers: 2, PerLayerMs: 1, Workers: []Worker{{Name: "a", Speed: 1}, {Name: "b", Speed: 1}}, LinkMs: []float64{0}}
	if _, changed, e := d.Decide(time.Now(), in, false); e != nil || !changed {
		t.Fatal(e)
	}
	in.Workers = in.Workers[:1]
	in.LinkMs = nil
	if _, changed, e := d.Decide(time.Now(), in, false); e != nil || !changed {
		t.Fatal("recovery held", e)
	}
}
