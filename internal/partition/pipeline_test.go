package partition

import (
	"math"
	"math/rand"
	"testing"
)

func balanced(layers, workers int, perLayerMs, linkMs float64) Input {
	in := Input{TotalLayers: layers, PerLayerMs: perLayerMs}
	for i := 0; i < workers; i++ {
		in.Workers = append(in.Workers, Worker{Name: string(rune('a' + i)), Speed: 1})
	}
	in.LinkMs = make([]float64, workers-1)
	for i := range in.LinkMs {
		in.LinkMs[i] = linkMs
	}
	return in
}

// PipelineMs must equal the sum of stage costs, and Evaluate/EvaluatePipeline
// must agree with Optimal's two fields on the split Optimal chose.
func TestPipelineMsIsSumOfStages(t *testing.T) {
	for _, workers := range []int{1, 2, 3, 4} {
		in := balanced(24, workers, 10, 2)
		res, err := Optimal(in)
		if err != nil {
			t.Fatalf("workers=%d: %v", workers, err)
		}
		var sum float64
		for i, a := range res.Assignments {
			sum += stageCost(in, perLayerCost(in), i, a.Start, a.End)
		}
		if math.Abs(res.PipelineMs-sum) > 1e-9 {
			t.Errorf("workers=%d: PipelineMs=%.6f want %.6f", workers, res.PipelineMs, sum)
		}
		if got := EvaluatePipeline(in, res.Splits()); math.Abs(got-res.PipelineMs) > 1e-9 {
			t.Errorf("workers=%d: EvaluatePipeline=%.6f want %.6f", workers, got, res.PipelineMs)
		}
		if got := Evaluate(in, res.Splits()); math.Abs(got-res.BottleneckMs) > 1e-9 {
			t.Errorf("workers=%d: Evaluate=%.6f want %.6f", workers, got, res.BottleneckMs)
		}
	}
}

// The regression this whole correction exists for: with k balanced stages and
// negligible link cost, PipelineMs is ~k x BottleneckMs. Comparing the DP's
// bottleneck against a measured per-request per-token cost therefore yields a
// ratio near the STAGE COUNT, which is not model error.
func TestBottleneckVersusPipelineIsStageCount(t *testing.T) {
	for _, workers := range []int{2, 3, 4} {
		in := balanced(24, workers, 10, 0) // 24 divides evenly; no link cost
		res, err := Optimal(in)
		if err != nil {
			t.Fatalf("workers=%d: %v", workers, err)
		}
		ratio := res.PipelineMs / res.BottleneckMs
		if math.Abs(ratio-float64(workers)) > 1e-6 {
			t.Errorf("workers=%d: PipelineMs/BottleneckMs=%.4f want %d",
				workers, ratio, workers)
		}
	}
}

// EvaluatePipeline must reject malformed splits exactly as Evaluate does.
func TestEvaluatePipelineRejectsBadSplits(t *testing.T) {
	in := balanced(12, 2, 10, 1)
	bad := [][][2]int{
		{{0, 6}},          // wrong worker count
		{{1, 6}, {6, 12}}, // does not start at 0
		{{0, 6}, {7, 12}}, // not contiguous
		{{0, 6}, {6, 11}}, // does not cover all layers
	}
	for i, splits := range bad {
		if got := EvaluatePipeline(in, splits); !math.IsInf(got, 1) {
			t.Errorf("case %d: got %.4f, want +Inf", i, got)
		}
	}
}

// TestOptimalMatchesBruteForceWithEndpoints re-runs the exhaustive cross-check
// with non-zero endpoint costs and a context-dependent per-layer table. The DP
// assumes a stage's cost depends only on its own layer range, and endpoint
// attribution keys off start==0 / end==TotalLayers, so that assumption still
// holds -- but it is cheap to prove rather than assume.
func TestOptimalMatchesBruteForceWithEndpoints(t *testing.T) {
	rng := rand.New(rand.NewSource(1337))
	for trial := 0; trial < 300; trial++ {
		k := 2 + rng.Intn(3)
		n := k + rng.Intn(14)
		in := Input{
			TotalLayers: n,
			PerLayerMs:  5 + rng.Float64()*50,
			EmbedMs:     rng.Float64() * 30,
			HeadMs:      rng.Float64() * 60,
		}
		// Half the trials also exercise the context-interpolated cost table.
		if trial%2 == 0 {
			base := 3 + rng.Float64()*8
			in.ContextLen = 1 + rng.Intn(3000)
			in.PerLayerByCtx = []CtxCost{
				{ContextLen: 2048, PerLayerMs: base * 1.7},
				{ContextLen: 128, PerLayerMs: base}, // deliberately unsorted
				{ContextLen: 1024, PerLayerMs: base * 1.3},
			}
		}
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
			t.Fatalf("trial %d: %v", trial, err)
		}
		if best := bruteForce(in); math.Abs(res.BottleneckMs-best) > 1e-6 {
			t.Fatalf("trial %d: DP=%v brute=%v input=%+v", trial, res.BottleneckMs, best, in)
		}
		if got := Evaluate(in, res.Splits()); math.Abs(got-res.BottleneckMs) > 1e-6 {
			t.Fatalf("trial %d: Evaluate=%v != %v", trial, got, res.BottleneckMs)
		}
	}
}

// TestEndpointCostSkewsSplitAwayFromLastStage pins the measured finding: with
// Qwen3-0.6B numbers at ctx 2048, a layer-proportional model picks 14/14 while
// the true optimum is 16/12, a 10.7% bottleneck error. See
// docs/phase4-prelim-findings.md.
func TestEndpointCostSkewsSplitAwayFromLastStage(t *testing.T) {
	const layers, perLayer, head = 28, 9.49, 43.8
	mk := func(headMs float64) Input {
		return Input{
			TotalLayers: layers, PerLayerMs: perLayer, HeadMs: headMs,
			Workers: []Worker{{Name: "a", Speed: 1}, {Name: "b", Speed: 1}},
			LinkMs:  []float64{0},
		}
	}
	naive, err := Optimal(mk(0))
	if err != nil {
		t.Fatal(err)
	}
	if got := naive.Splits(); got[0] != [2]int{0, 14} {
		t.Fatalf("without endpoint cost expected an even 0-14 split, got %v", got)
	}

	withHead := mk(head)
	tuned, err := Optimal(withHead)
	if err != nil {
		t.Fatal(err)
	}
	first := tuned.Assignments[0].End
	if first <= 14 {
		t.Errorf("endpoint cost must skew layers AWAY from the last stage, got %d/%d",
			first, layers-first)
	}

	// The even split, scored under the true (endpoint-aware) cost.
	evenCost := Evaluate(withHead, naive.Splits())
	loss := (evenCost - tuned.BottleneckMs) / evenCost
	if loss < 0.05 {
		t.Errorf("expected the mis-split to cost materially, got %.2f%%", loss*100)
	}
	t.Logf("even split %v -> %.1fms; optimum %v -> %.1fms; mis-split costs %.1f%%",
		naive.Splits(), evenCost, tuned.Splits(), tuned.BottleneckMs, loss*100)
}
