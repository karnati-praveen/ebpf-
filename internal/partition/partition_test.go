package partition

import (
	"math"
	"math/rand"
	"testing"
	"time"
)

func workers(speeds ...float64) []Worker {
	out := make([]Worker, len(speeds))
	for i, s := range speeds {
		out[i] = Worker{Name: string(rune('a' + i)), Addr: "x", Speed: s}
	}
	return out
}

func layerCounts(r *Result) []int {
	out := make([]int, len(r.Assignments))
	for i, a := range r.Assignments {
		out[i] = a.End - a.Start
	}
	return out
}

func TestOptimalHomogeneous(t *testing.T) {
	in := Input{
		TotalLayers: 12, PerLayerMs: 30,
		Workers: workers(1, 1, 1), LinkMs: []float64{1, 1},
	}
	res, err := Optimal(in)
	if err != nil {
		t.Fatal(err)
	}
	for i, n := range layerCounts(res) {
		if n != 4 {
			t.Fatalf("stage %d got %d layers, want 4 (split %v)", i, n, layerCounts(res))
		}
	}
	if math.Abs(res.BottleneckMs-121) > 1e-9 { // 4*30 + 1ms link
		t.Fatalf("bottleneck = %v, want 121", res.BottleneckMs)
	}
}

func TestOptimalThrottledWorkerGetsFewerLayers(t *testing.T) {
	in := Input{
		TotalLayers: 12, PerLayerMs: 30,
		Workers: workers(1, 0.4, 1), LinkMs: []float64{1, 1},
	}
	res, err := Optimal(in)
	if err != nil {
		t.Fatal(err)
	}
	counts := layerCounts(res)
	if counts[1] >= counts[0] || counts[1] >= counts[2] {
		t.Fatalf("throttled middle worker should hold fewest layers, got %v", counts)
	}
}

func TestOptimalSlowLinkShrinksDownstream(t *testing.T) {
	fast := Input{
		TotalLayers: 12, PerLayerMs: 30,
		Workers: workers(1, 1, 1), LinkMs: []float64{1, 1},
	}
	slow := fast
	slow.LinkMs = []float64{80, 1} // degraded hop into worker 2
	rFast, _ := Optimal(fast)
	rSlow, _ := Optimal(slow)
	if rSlow.BottleneckMs <= rFast.BottleneckMs {
		t.Fatalf("slow link must raise bottleneck: %v <= %v", rSlow.BottleneckMs, rFast.BottleneckMs)
	}
	// Stage 2's cost includes the 80ms hop, so it must hold fewer layers.
	if c := layerCounts(rSlow); c[1] >= c[0] {
		t.Fatalf("stage after slow link should shrink, got %v", c)
	}
}

func TestOptimalDropsStageOnSevereLinkDegradation(t *testing.T) {
	// A 300ms hop into the middle worker costs more than redistributing
	// its layers: the optimal split gives it zero layers (stage bypassed).
	in := Input{
		TotalLayers: 12, PerLayerMs: 30,
		Workers: workers(1, 1, 1), LinkMs: []float64{300, 1},
	}
	res, err := Optimal(in)
	if err != nil {
		t.Fatal(err)
	}
	counts := layerCounts(res)
	if counts[1] != 0 {
		t.Fatalf("expected middle stage dropped, got %v", counts)
	}
	if res.BottleneckMs >= 300 {
		t.Fatalf("bottleneck %v should beat any split that keeps the 300ms hop", res.BottleneckMs)
	}
}

// TestOptimalMatchesBruteForce cross-checks the DP against exhaustive search.
func TestOptimalMatchesBruteForce(t *testing.T) {
	rng := rand.New(rand.NewSource(42))
	for trial := 0; trial < 200; trial++ {
		k := 2 + rng.Intn(3)
		n := k + rng.Intn(14)
		in := Input{TotalLayers: n, PerLayerMs: 5 + rng.Float64()*50}
		for i := 0; i < k; i++ {
			in.Workers = append(in.Workers, Worker{
				Name: string(rune('a' + i)), Speed: 0.2 + rng.Float64()*0.8,
			})
		}
		for i := 0; i < k-1; i++ {
			in.LinkMs = append(in.LinkMs, rng.Float64()*100)
		}

		res, err := Optimal(in)
		if err != nil {
			t.Fatal(err)
		}
		best := bruteForce(in)
		if math.Abs(res.BottleneckMs-best) > 1e-6 {
			t.Fatalf("trial %d: DP=%v brute=%v input=%+v", trial, res.BottleneckMs, best, in)
		}
		if got := Evaluate(in, res.Splits()); math.Abs(got-res.BottleneckMs) > 1e-6 {
			t.Fatalf("Evaluate(optimal splits)=%v != %v", got, res.BottleneckMs)
		}
	}
}

func bruteForce(in Input) float64 {
	n, k := in.TotalLayers, len(in.Workers)
	best := math.Inf(1)
	var rec func(worker, start int, worst float64)
	rec = func(worker, start int, worst float64) {
		if worker == k-1 {
			cost := math.Max(worst, stageCost(in, worker, n-start))
			if cost < best {
				best = cost
			}
			return
		}
		for take := 0; start+take <= n; take++ {
			rec(worker+1, start+take, math.Max(worst, stageCost(in, worker, take)))
		}
	}
	rec(0, 0, 0)
	return best
}

func TestDeciderHysteresis(t *testing.T) {
	d := NewDecider(0.15, 30*time.Second)
	t0 := time.Now()
	in := Input{
		TotalLayers: 12, PerLayerMs: 30,
		Workers: workers(1, 1, 1), LinkMs: []float64{1, 1},
	}

	_, changed, err := d.Decide(t0, in, false)
	if err != nil || !changed {
		t.Fatalf("first decision must apply: changed=%v err=%v", changed, err)
	}

	// Tiny perturbation: below the 15% improvement bar, keep the split.
	in.Workers = workers(1, 0.95, 1)
	_, changed, _ = d.Decide(t0.Add(time.Minute), in, false)
	if changed {
		t.Fatal("sub-threshold improvement must not repartition")
	}

	// Heavy throttle: improvement is large, but cooldown not yet elapsed.
	in.Workers = workers(1, 0.3, 1)
	_, changed, _ = d.Decide(t0.Add(time.Minute + time.Second), in, false)
	if !changed {
		t.Fatal("cooldown elapsed since t0; large improvement must repartition")
	}
	_, changed, _ = d.Decide(t0.Add(time.Minute+10*time.Second), Input{
		TotalLayers: 12, PerLayerMs: 30,
		Workers: workers(1, 1, 1), LinkMs: []float64{1, 1},
	}, false)
	if changed {
		t.Fatal("second repartition within cooldown must be suppressed")
	}
}

func TestDeciderWorkerSetChangeForces(t *testing.T) {
	d := NewDecider(0.15, time.Hour)
	t0 := time.Now()
	in := Input{
		TotalLayers: 12, PerLayerMs: 30,
		Workers: workers(1, 1, 1), LinkMs: []float64{1, 1},
	}
	d.Decide(t0, in, false)

	// A worker died: only two remain. Must repartition immediately even
	// though the bottleneck gets worse and cooldown is an hour.
	two := Input{
		TotalLayers: 12, PerLayerMs: 30,
		Workers: workers(1, 1), LinkMs: []float64{1},
	}
	res, changed, err := d.Decide(t0.Add(time.Second), two, false)
	if err != nil || !changed {
		t.Fatalf("healing must force repartition: changed=%v err=%v", changed, err)
	}
	if len(res.Assignments) != 2 {
		t.Fatalf("want 2 stages, got %d", len(res.Assignments))
	}
}
