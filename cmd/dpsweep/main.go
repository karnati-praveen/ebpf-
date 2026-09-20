// dpsweep is the Phase 1 instrumentation and power check: it asks, offline,
// how much a given fault would change the partitioner's chosen split and what
// benefit repartitioning is predicted to deliver.
//
// It is NOT a filter for selecting favourable experimental conditions. Runs
// where the optimum does not move, or where predicted benefit is ~0, are the
// "staying put is correct" conditions the study exists to characterise, and
// are reported as first-class rows.
//
// Predictions here come from the DP's own cost model, which is unvalidated
// until Phase 4. They establish the predicted range only. They cannot
// establish measurement noise -- that requires repeated real runs -- and must
// not be used on their own to justify hardware procurement.
//
//	go run ./cmd/dpsweep                      # table to stdout
//	go run ./cmd/dpsweep -csv out.csv         # also write CSV
//	go run ./cmd/dpsweep -layers 12 -workers 3
package main

import (
	"encoding/csv"
	"flag"
	"fmt"
	"log"
	"os"
	"strconv"

	"kubeedgeinfer/internal/partition"
)

// measuredQwen3_06B is the decode-time per-layer cost table measured on an
// Azure 4-vCPU Xeon 8272CL, FP32. See docs/phase4-prelim-findings.md.
var measuredQwen3_06B = []partition.CtxCost{
	{ContextLen: 128, PerLayerMs: 5.55},
	{ContextLen: 512, PerLayerMs: 6.25},
	{ContextLen: 1024, PerLayerMs: 7.18},
	{ContextLen: 2048, PerLayerMs: 9.49},
}

var (
	gEmbedMs, gHeadMs float64
	gContextLen       int
	gMeasured         bool
)

func baseInput(layers, workers int, perLayerMs, linkMs float64) partition.Input {
	in := partition.Input{
		TotalLayers: layers, PerLayerMs: perLayerMs,
		EmbedMs: gEmbedMs, HeadMs: gHeadMs, ContextLen: gContextLen,
	}
	if gMeasured {
		in.PerLayerByCtx = measuredQwen3_06B
	}
	for i := 0; i < workers; i++ {
		in.Workers = append(in.Workers, partition.Worker{
			Name: fmt.Sprintf("w%d", i), Node: fmt.Sprintf("n%d", i), Speed: 1,
		})
	}
	in.LinkMs = make([]float64, max(0, workers-1))
	for i := range in.LinkMs {
		in.LinkMs[i] = linkMs
	}
	return in
}

func splitsEqual(a, b [][2]int) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

func describe(s [][2]int) string {
	out := ""
	for i, r := range s {
		if i > 0 {
			out += "/"
		}
		out += fmt.Sprintf("%d-%d", r[0], r[1])
	}
	return out
}

type row struct {
	fault     string
	magnitude string
	baseSplit string
	faultSplit string
	moved     bool
	stayMs    float64 // predicted bottleneck if we keep the baseline split
	adaptMs   float64 // predicted bottleneck after repartitioning
	benefitMs float64
	benefitPct float64
	note      string
}

func main() {
	var (
		layers     = flag.Int("layers", 28, "total transformer layers (Qwen3-0.6B = 28, GPT-2 = 12)")
		workers    = flag.Int("workers", 2, "number of pipeline workers")
		perLayerMs = flag.Float64("per-layer-ms", 30, "base per-layer compute cost at Speed=1")
		linkMs     = flag.Float64("link-ms", 0.5, "baseline per-hop transfer cost")
		csvPath    = flag.String("csv", "", "also write results here")
		embedMs    = flag.Float64("embed-ms", 0, "endpoint cost on the stage holding layer 0")
		headMs     = flag.Float64("head-ms", 0, "endpoint cost on the stage holding the last layer (lm_head + final norm)")
		contextLen = flag.Int("ctx", 0, "context length, for the measured per-layer table")
		measured   = flag.Bool("measured", false, "use the measured Qwen3-0.6B per-layer table instead of -per-layer-ms")
	)
	flag.Parse()
	gEmbedMs, gHeadMs, gContextLen, gMeasured = *embedMs, *headMs, *contextLen, *measured

	base := baseInput(*layers, *workers, *perLayerMs, *linkMs)
	baseRes, err := partition.Optimal(base)
	if err != nil {
		log.Fatalf("baseline: %v", err)
	}
	baseSplits := baseRes.Splits()

	// Candidate allocations, stated explicitly: zero-layer stages are allowed
	// (partition.go stageCost/Optimal), so for L layers across 2 workers the
	// space is k = 0..L, i.e. L+1.
	if *measured {
		fmt.Printf("layers=%d workers=%d per-layer=MEASURED@ctx%d link=%.2fms embed=%.1fms head=%.1fms\n",
			*layers, *workers, *contextLen, *linkMs, *embedMs, *headMs)
	} else {
		fmt.Printf("layers=%d workers=%d per-layer=%.1fms link=%.2fms embed=%.1fms head=%.1fms\n",
			*layers, *workers, *perLayerMs, *linkMs, *embedMs, *headMs)
	}
	if *workers == 2 {
		fmt.Printf("candidate contiguous allocations: %d (k=0..%d; zero-layer stages allowed)\n",
			*layers+1, *layers)
	}
	fmt.Printf("baseline optimum: %s  bottleneck=%.2fms\n\n",
		describe(baseSplits), baseRes.BottleneckMs)

	var rows []row

	// --- Thermal derate on the last worker ---
	for _, speed := range []float64{1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1} {
		in := baseInput(*layers, *workers, *perLayerMs, *linkMs)
		in.Workers[len(in.Workers)-1].Speed = speed
		rows = append(rows, evaluate("thermal", fmt.Sprintf("speed=%.1f", speed), in, baseSplits, baseRes))
	}

	// --- Network delay on the last hop ---
	if *workers > 1 {
		for _, d := range []float64{0.5, 5, 10, 20, 40, 80, 120, 200} {
			in := baseInput(*layers, *workers, *perLayerMs, *linkMs)
			in.LinkMs[len(in.LinkMs)-1] = d
			rows = append(rows, evaluate("network", fmt.Sprintf("delay=%.0fms", d), in, baseSplits, baseRes))
		}
	}

	// --- Device loss ---
	if *workers > 1 {
		in := baseInput(*layers, *workers-1, *perLayerMs, *linkMs)
		res, err := partition.Optimal(in)
		if err != nil {
			log.Fatalf("loss: %v", err)
		}
		rows = append(rows, row{
			fault: "device loss", magnitude: fmt.Sprintf("%d->%d workers", *workers, *workers-1),
			baseSplit: describe(baseSplits), faultSplit: describe(res.Splits()),
			moved: true, adaptMs: res.BottleneckMs,
			note: "not optional: the baseline split is unservable, so 'stay' has no defined cost",
		})
	}

	hdr := []string{"fault", "magnitude", "baseline_split", "fault_split", "optimum_moved",
		"stay_bottleneck_ms", "adapt_bottleneck_ms", "predicted_benefit_ms", "predicted_benefit_pct", "note"}
	fmt.Printf("%-12s %-14s %-12s %-12s %-6s %10s %10s %10s %8s\n",
		"FAULT", "MAGNITUDE", "BASE SPLIT", "FAULT SPLIT", "MOVED", "STAY ms", "ADAPT ms", "BENEFIT", "BENEFIT%")
	for _, r := range rows {
		moved := "no"
		if r.moved {
			moved = "YES"
		}
		if r.note != "" {
			fmt.Printf("%-12s %-14s %-12s %-12s %-6s %10s %10.2f %10s %8s  (%s)\n",
				r.fault, r.magnitude, r.baseSplit, r.faultSplit, moved, "-", r.adaptMs, "-", "-", r.note)
			continue
		}
		fmt.Printf("%-12s %-14s %-12s %-12s %-6s %10.2f %10.2f %10.2f %7.1f%%\n",
			r.fault, r.magnitude, r.baseSplit, r.faultSplit, moved,
			r.stayMs, r.adaptMs, r.benefitMs, r.benefitPct)
	}

	fmt.Printf("\nno-benefit conditions (predicted benefit < 1%%) are retained for Phase 6, not discarded.\n")
	fmt.Printf("these are cost-model predictions, not measurements; noise must come from repeated real runs.\n")

	if *csvPath != "" {
		f, err := os.Create(*csvPath)
		if err != nil {
			log.Fatal(err)
		}
		defer f.Close()
		w := csv.NewWriter(f)
		defer w.Flush()
		w.Write(hdr)
		for _, r := range rows {
			w.Write([]string{r.fault, r.magnitude, r.baseSplit, r.faultSplit,
				strconv.FormatBool(r.moved),
				fmt.Sprintf("%.4f", r.stayMs), fmt.Sprintf("%.4f", r.adaptMs),
				fmt.Sprintf("%.4f", r.benefitMs), fmt.Sprintf("%.4f", r.benefitPct), r.note})
		}
		fmt.Printf("wrote %s\n", *csvPath)
	}
}

// evaluate compares keeping the baseline split against repartitioning, both
// scored under the faulted conditions. The difference is the DP's predicted
// benefit of adapting -- the quantity the Phase 5 gate must exceed.
func evaluate(fault, magnitude string, in partition.Input, baseSplits [][2]int, baseRes *partition.Result) row {
	res, err := partition.Optimal(in)
	if err != nil {
		log.Fatalf("%s %s: %v", fault, magnitude, err)
	}
	stay := partition.Evaluate(in, baseSplits)
	benefit := stay - res.BottleneckMs
	pct := 0.0
	if stay > 0 {
		pct = benefit / stay * 100
	}
	return row{
		fault: fault, magnitude: magnitude,
		baseSplit: describe(baseSplits), faultSplit: describe(res.Splits()),
		moved:     !splitsEqual(baseSplits, res.Splits()),
		stayMs:    stay, adaptMs: res.BottleneckMs,
		benefitMs: benefit, benefitPct: pct,
	}
}
