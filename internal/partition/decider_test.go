package partition

import (
	"math"
	"testing"
	"time"
)

// twoWorkers builds a 28-layer, 2-worker input using the measured Qwen3-0.6B
// decode cost at ctx 2048 and its measured endpoint cost.
func twoWorkers(speedB float64) Input {
	return Input{
		TotalLayers: 28, PerLayerMs: 9.49, HeadMs: 43.8,
		Workers: []Worker{{Name: "a", Addr: "a:1", Speed: 1}, {Name: "b", Addr: "b:1", Speed: speedB}},
		LinkMs:  []float64{0.5},
	}
}

func deciderFor(p Policy, horizonS float64) *Decider {
	d := NewDecider(0.15, 0)
	d.Policy = p
	d.Gate = GateParams{HorizonS: horizonS, TransitionFixedMs: 2000,
		PrefillMsPerTokenLayer: 0.21, ContextLen: 2048, SafetyMargin: 0}
	return d
}

// A thermal derate to 0.7x on worker b: the optimum moves and clears the 15%
// improvement threshold, so every policy reaches its own decision point.
func settleThenDerate(t *testing.T, d *Decider) (*Decision, bool) {
	t.Helper()
	t0 := time.Now()
	if _, changed, err := d.Decide(t0, twoWorkers(1), false); err != nil || !changed {
		t.Fatalf("initial decide: changed=%v err=%v", changed, err)
	}
	_, changed, err := d.Decide(t0.Add(time.Minute), twoWorkers(0.7), false)
	if err != nil {
		t.Fatal(err)
	}
	return d.LastDecision(), changed
}

func TestGateRejectsWhenHorizonTooShort(t *testing.T) {
	// T = 2000 + 2048*0.21*28 = 14042 ms of downtime; a 10 s horizon cannot
	// repay it, so the gate must keep the current split.
	dec, changed := settleThenDerate(t, deciderFor(PolicyGate, 10))
	if changed || dec.Executed || dec.GateAccepts {
		t.Fatalf("gate should reject: changed=%v %+v", changed, dec)
	}
	if dec.Reason != "gate-rejects" {
		t.Errorf("reason=%q", dec.Reason)
	}
	if want := 2000 + 2048*0.21*28; math.Abs(dec.TransitionMs-want) > 1e-6 {
		t.Errorf("TransitionMs=%.1f want %.1f", dec.TransitionMs, want)
	}
}

func TestGateAcceptsWhenHorizonLongEnough(t *testing.T) {
	dec, changed := settleThenDerate(t, deciderFor(PolicyGate, 600))
	if !changed || !dec.Executed || !dec.GateAccepts || dec.Reason != "gate-accepts" {
		t.Fatalf("gate should accept over 600 s: changed=%v %+v", changed, dec)
	}
}

// The break-even horizon must sit exactly where stay and adapt deliver equal
// tokens: a horizon just below it rejects, just above it accepts.
func TestBreakEvenHorizonIsTheDecisionBoundary(t *testing.T) {
	probe, _ := settleThenDerate(t, deciderFor(PolicyGate, 600))
	be := probe.BreakEvenS
	if be <= 0 {
		t.Fatalf("break-even not computed: %+v", probe)
	}
	below, _ := settleThenDerate(t, deciderFor(PolicyGate, be*0.99))
	above, _ := settleThenDerate(t, deciderFor(PolicyGate, be*1.01))
	if below.GateAccepts || !above.GateAccepts {
		t.Fatalf("break-even %.2fs is not the boundary: below=%v above=%v",
			be, below.GateAccepts, above.GateAccepts)
	}
	t.Logf("break-even horizon for a 0.7x derate at ctx 2048: %.1f s", be)
}

// gate-force computes the same verdict as gate but executes anyway, so a run
// on the same trace observes what the rejected move would have done.
func TestGateForceExecutesButRecordsTheRejection(t *testing.T) {
	dec, changed := settleThenDerate(t, deciderFor(PolicyGateForce, 10))
	if !changed || !dec.Executed {
		t.Fatalf("gate-force must execute: changed=%v %+v", changed, dec)
	}
	if dec.GateAccepts || dec.Reason != "gate-rejects-forced" {
		t.Errorf("gate-force must record the gate's own verdict: %+v", dec)
	}
}

func TestHysteresisIgnoresTransitionCost(t *testing.T) {
	dec, changed := settleThenDerate(t, deciderFor(PolicyHysteresis, 10))
	if !changed || dec.Reason != "hysteresis-passed" {
		t.Fatalf("hysteresis should move regardless of horizon: changed=%v %+v", changed, dec)
	}
	if dec.TransitionMs != 0 {
		t.Errorf("hysteresis must not evaluate the gate: %+v", dec)
	}
}

// With no hysteresis a small improvement, far below 15%, still moves.
func TestNoneMovesOnAnyStrictImprovement(t *testing.T) {
	for _, p := range []Policy{PolicyNone, PolicyHysteresis} {
		d := deciderFor(p, 10)
		t0 := time.Now()
		d.Decide(t0, twoWorkers(1), false)
		_, changed, _ := d.Decide(t0.Add(time.Minute), twoWorkers(0.93), false)
		dec := d.LastDecision()
		if dec == nil || dec.Improvement <= 0 || dec.Improvement >= 0.15 {
			t.Fatalf("%s: expected a small improvement, got %+v", p, dec)
		}
		if want := p == PolicyNone; changed != want {
			t.Errorf("%s: changed=%v want %v (improvement %.1f%%)", p, changed, want, dec.Improvement*100)
		}
	}
}

// Losing a worker leaves the current split unservable: every policy must
// move, including a gate whose horizon could never repay the transition.
func TestRecoveryBypassesEveryPolicy(t *testing.T) {
	for _, p := range []Policy{PolicyNone, PolicyHysteresis, PolicyGate, PolicyGateForce} {
		d := deciderFor(p, 0.001)
		d.Cooldown = time.Hour
		t0 := time.Now()
		d.Decide(t0, twoWorkers(1), false)
		survivor := Input{TotalLayers: 28, PerLayerMs: 9.49, HeadMs: 43.8,
			Workers: []Worker{{Name: "a", Addr: "a:1", Speed: 1}}, LinkMs: []float64{}}
		res, changed, err := d.Decide(t0.Add(time.Second), survivor, false)
		if err != nil || !changed || len(res.Assignments) != 1 {
			t.Fatalf("%s: recovery must move: changed=%v err=%v", p, changed, err)
		}
		if d.LastDecision().Reason != "recovery-or-initial" {
			t.Errorf("%s: reason=%q", p, d.LastDecision().Reason)
		}
	}
}

// Keeping a split must refresh BOTH predictions, not just the bottleneck.
func TestKeptSplitRefreshesPipelineMs(t *testing.T) {
	d := deciderFor(PolicyHysteresis, 10)
	d.Decide(time.Now(), twoWorkers(1), false)
	res, changed, _ := d.Decide(time.Now(), twoWorkers(1), false)
	if changed || res.PipelineMs <= 0 {
		t.Fatalf("kept split lost PipelineMs: changed=%v %+v", changed, res)
	}
}

func TestUnknownPolicyIsAnError(t *testing.T) {
	d := deciderFor("bogus", 10)
	t0 := time.Now()
	d.Decide(t0, twoWorkers(1), false)
	if _, _, err := d.Decide(t0.Add(time.Minute), twoWorkers(0.7), false); err == nil {
		t.Fatal("unknown policy must be rejected")
	}
}
