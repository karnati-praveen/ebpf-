package partition

import (
	"math"
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
			sum += stageCost(in, i, a.End-a.Start)
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
		{{0, 6}},                 // wrong worker count
		{{1, 6}, {6, 12}},        // does not start at 0
		{{0, 6}, {7, 12}},        // not contiguous
		{{0, 6}, {6, 11}},        // does not cover all layers
	}
	for i, splits := range bad {
		if got := EvaluatePipeline(in, splits); !math.IsInf(got, 1) {
			t.Errorf("case %d: got %.4f, want +Inf", i, got)
		}
	}
}
