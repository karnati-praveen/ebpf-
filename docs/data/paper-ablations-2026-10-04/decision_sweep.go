// Decision-only ablations using the production partitioner and decider.
// Cost estimates parameterize predictions; they are not runtime outcomes.
package main

import (
	"encoding/csv"
	"encoding/json"
	"flag"
	"fmt"
	"shardwise/internal/partition"
	"math"
	"os"
	"path/filepath"
	"strconv"
	"time"
)

var table = []partition.CtxCost{{ContextLen: 128, PerLayerMs: 5.55}, {ContextLen: 512, PerLayerMs: 6.25}, {ContextLen: 1024, PerLayerMs: 7.18}, {ContextLen: 2048, PerLayerMs: 9.49}}

func input(ctx int, speed, link float64, endpoints, context bool) partition.Input {
	in := partition.Input{TotalLayers: 28, PerLayerMs: 5.55, ContextLen: ctx,
		Workers: []partition.Worker{{Name: "a", Addr: "a:1", Speed: 1}, {Name: "b", Addr: "b:1", Speed: speed}}, LinkMs: []float64{link}}
	if endpoints {
		in.EmbedMs = .09
		in.HeadMs = 43.8
	}
	if context {
		in.PerLayerByCtx = table
	}
	return in
}
func num(x float64) string             { return strconv.FormatFloat(x, 'g', 12, 64) }
func integer(x int) string             { return strconv.Itoa(x) }
func boolean(x bool) string            { return strconv.FormatBool(x) }
func split(r *partition.Result) string { b, _ := json.Marshal(r.Splits()); return string(b) }
func owner(s [][2]int, layer int) int {
	for i, r := range s {
		if layer >= r[0] && layer < r[1] {
			return i
		}
	}
	return -1
}
func moved(a, b [][2]int) int {
	n := 0
	for l := 0; l < 28; l++ {
		if owner(a, l) != owner(b, l) {
			n++
		}
	}
	return n
}
func mustOptimal(in partition.Input) *partition.Result {
	r, e := partition.Optimal(in)
	if e != nil {
		panic(e)
	}
	return r
}

func main() {
	out := flag.String("out", "", "fresh output directory")
	flag.Parse()
	if *out == "" {
		panic("--out required")
	}
	if _, err := os.Stat(*out); !os.IsNotExist(err) {
		panic("output directory exists")
	}
	if err := os.MkdirAll(*out, 0755); err != nil {
		panic(err)
	}
	f, e := os.Create(filepath.Join(*out, "cost-model.csv"))
	if e != nil {
		panic(e)
	}
	w := csv.NewWriter(f)
	w.Write([]string{"context", "speed_b", "link_ms", "endpoints", "context_table", "chosen_split", "oracle_split", "estimated_bottleneck_ms", "reference_evaluated_bottleneck_ms", "reference_optimal_bottleneck_ms", "reference_regret_frac", "reference_pipeline_ms"})
	for _, ctx := range []int{128, 512, 1024, 2048} {
		for _, speed := range []float64{1, .93, .8, .7, .5} {
			for _, link := range []float64{.5, 10, 80} {
				truth := input(ctx, speed, link, true, true)
				oracle := mustOptimal(truth)
				for _, endpoints := range []bool{false, true} {
					for _, context := range []bool{false, true} {
						r := mustOptimal(input(ctx, speed, link, endpoints, context))
						cost := partition.Evaluate(truth, r.Splits())
						w.Write([]string{integer(ctx), num(speed), num(link), boolean(endpoints), boolean(context), split(r), split(oracle), num(r.BottleneckMs), num(cost), num(oracle.BottleneckMs), num(cost/oracle.BottleneckMs - 1), num(partition.EvaluatePipeline(truth, r.Splits()))})
					}
				}
			}
		}
	}
	w.Flush()
	if w.Error() != nil {
		panic(w.Error())
	}
	f.Close()
	f, e = os.Create(filepath.Join(*out, "policy.csv"))
	if e != nil {
		panic(e)
	}
	w = csv.NewWriter(f)
	w.Write([]string{"context", "speed_b", "link_ms", "horizon_s", "margin", "transition_model", "policy", "initial_split", "candidate_split", "chosen_split", "moved_layers", "changed", "reason", "current_ms", "optimal_ms", "estimated_transition_ms", "full_chain_transition_ms", "zero_margin_break_even_s", "margin_acceptance_boundary_s", "gate_accepts", "predicted_tokens_stay_full_chain", "predicted_tokens_adapt_full_chain"})
	for _, ctx := range []int{128, 512, 1024, 2048} {
		for _, speed := range []float64{1, .93, .8, .7, .5} {
			for _, link := range []float64{.5, 10, 80} {
				base := input(ctx, 1, .5, true, true)
				fault := input(ctx, speed, link, true, true)
				initial := mustOptimal(base)
				candidate := mustOptimal(fault)
				count := moved(initial.Splits(), candidate.Splits())
				current := partition.Evaluate(fault, initial.Splits())
				optimal := candidate.BottleneckMs
				fullT := 2000 + float64(ctx)*.21*28
				for _, h := range []float64{10, 30, 60, 120, 240, 600} {
					for _, margin := range []float64{0, .13} {
						for _, tm := range []string{"full-chain", "moved-layers-only", "no-replay", "no-fixed", "zero-transition"} {
							fixed, prefill := 2000.0, .21
							switch tm {
							case "moved-layers-only":
								prefill *= float64(count) / 28
							case "no-replay":
								prefill = 0
							case "no-fixed":
								fixed = 0
							case "zero-transition":
								fixed = 0
								prefill = 0
							}
							transition := fixed + float64(ctx)*prefill*28
							boundary := math.Inf(1)
							if current > (1+margin)*optimal {
								boundary = transition * current / (current - (1+margin)*optimal) / 1000
							}
							be := math.Inf(1)
							if current > optimal {
								be = transition * current / (current - optimal) / 1000
							}
							for _, policy := range []string{"static", "none", "hysteresis", "gate", "gate-force"} {
								chosen := initial
								changed := false
								reason := "static-initial"
								accepts := false
								if policy != "static" {
									d := partition.NewDecider(.15, 0)
									d.Policy = partition.Policy(policy)
									d.Gate = partition.GateParams{HorizonS: h, TransitionFixedMs: fixed, PrefillMsPerTokenLayer: prefill, ContextLen: ctx, SafetyMargin: margin}
									t := time.Unix(0, 0)
									if _, _, err := d.Decide(t, base, false); err != nil {
										panic(err)
									}
									var err error
									chosen, changed, err = d.Decide(t.Add(time.Minute), fault, false)
									if err != nil {
										panic(err)
									}
									dec := d.LastDecision()
									reason = "no-improving-candidate"
									if dec != nil && dec.Reason != "recovery-or-initial" {
										reason = dec.Reason
										accepts = dec.GateAccepts
									}
								}
								w.Write([]string{integer(ctx), num(speed), num(link), num(h), num(margin), tm, policy, split(initial), split(candidate), split(chosen), integer(count), boolean(changed), reason, num(current), num(optimal), num(transition), num(fullT), num(be), num(boundary), boolean(accepts), num(h * 1000 / current), num(math.Max(0, h*1000-fullT) / optimal)})
							}
						}
					}
				}
			}
		}
	}
	w.Flush()
	if w.Error() != nil {
		panic(w.Error())
	}
	f.Close()
	fmt.Println("Wrote 240 cost-model rows and 18000 decision-only policy rows; no runtime gain measured")
}
