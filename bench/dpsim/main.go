// Command dpsim evaluates the partitioner's decision quality directly, with
// no cluster: it replays each fault scenario's telemetry snapshot through the
// same internal/partition code the controller runs, and compares the
// bottleneck-stage cost achieved by three policies.
//
//	dynamic      repartitions on the post-fault snapshot (KubeEdgeInfer)
//	static       one equal split, never revisited
//	profileonly  DP split chosen once on pre-fault telemetry, then frozen
//	             (offline-profiling systems: EdgeShard / PipeEdge / Galaxy)
//
// The reported number is the DP's per-token bottleneck cost in ms — the same
// objective the controller minimizes. It is a model-level result: it isolates
// partitioning quality from cluster overheads. End-to-end tokens/sec, TTFT and
// measured bubble time come from bench/run.py, which needs a live cluster.
//
// Usage: go run ./bench/dpsim
package main

import (
	"encoding/json"
	"fmt"
	"math"
	"os"
	"time"

	"kubeedgeinfer/internal/partition"
)

const (
	totalLayers = 12
	perLayerMs  = 10.0
	baseLinkMs  = 2.0
	netemMs     = 82.0 // 80ms tc netem delay + baseline hop
	throttled   = 0.4  // effective speed of a thermally throttled stage
)

func workers(speeds ...float64) []partition.Worker {
	ws := make([]partition.Worker, len(speeds))
	for i, s := range speeds {
		ws[i] = partition.Worker{Name: fmt.Sprintf("w%d", i+1), Addr: fmt.Sprintf("10.0.0.%d:9000", i+1), Speed: s}
	}
	return ws
}

func equalSplit(n, k int) [][2]int {
	out := make([][2]int, k)
	start := 0
	for i := 0; i < k; i++ {
		end := start + n/k
		if i < n%k {
			end++
		}
		out[i] = [2]int{start, end}
		start = end
	}
	return out
}

type scenario struct {
	name  string
	fault partition.Input
}

func base(k int) partition.Input {
	sp := make([]float64, k)
	links := make([]float64, k-1)
	for i := range sp {
		sp[i] = 1.0
	}
	for i := range links {
		links[i] = baseLinkMs
	}
	return partition.Input{TotalLayers: totalLayers, PerLayerMs: perLayerMs, Workers: workers(sp...), LinkMs: links}
}

func scenarios() []scenario {
	thermal := base(3)
	thermal.Workers[1].Speed = throttled

	netem := base(3)
	netem.LinkMs[0] = netemMs // hop feeding stage 2 degrades

	combo := base(3)
	combo.Workers[1].Speed = throttled
	combo.LinkMs[0] = netemMs

	failure := base(2) // stage 3 died; survivors must absorb its layers

	return []scenario{
		{"baseline", base(3)},
		{"thermal", thermal},
		{"netem", netem},
		{"failure", failure},
		{"combo", combo},
	}
}

type row struct {
	Scenario      string   `json:"scenario"`
	DynamicMs     float64  `json:"dynamic_bottleneck_ms"`
	StaticMs      float64  `json:"static_bottleneck_ms"`
	ProfileOnlyMs float64  `json:"profileonly_bottleneck_ms"`
	GainVsStatic  float64  `json:"gain_vs_static_pct"`
	GainVsProfile float64  `json:"gain_vs_profileonly_pct"`
	DynamicSplits [][2]int `json:"dynamic_splits"`
	StaticSplits  [][2]int `json:"static_splits"`
}

// gain is the percentage the dynamic policy shaves off a reference policy's
// bottleneck. It is undefined when the reference pipeline is down (+Inf).
func gain(ref, dyn float64) float64 {
	if math.IsInf(ref, 1) || ref == 0 {
		return math.NaN()
	}
	return 100 * (ref - dyn) / ref
}

func ms(v float64) string {
	if math.IsInf(v, 1) {
		return "down"
	}
	return fmt.Sprintf("%.1f", v)
}

func pct(v float64) string {
	if math.IsNaN(v) {
		return "n/a"
	}
	return fmt.Sprintf("%.1f%%", v)
}

// jsonable swaps +Inf/NaN (pipeline down / gain undefined) for null, which
// encoding/json cannot represent as a float.
func jsonable(rows []row) []map[string]any {
	out := make([]map[string]any, 0, len(rows))
	for _, r := range rows {
		b, _ := json.Marshal(struct {
			S  string   `json:"scenario"`
			DS [][2]int `json:"dynamic_splits"`
			SS [][2]int `json:"static_splits"`
		}{r.Scenario, r.DynamicSplits, r.StaticSplits})
		m := map[string]any{}
		_ = json.Unmarshal(b, &m)
		for k, v := range map[string]float64{
			"dynamic_bottleneck_ms":     r.DynamicMs,
			"static_bottleneck_ms":      r.StaticMs,
			"profileonly_bottleneck_ms": r.ProfileOnlyMs,
			"gain_vs_static_pct":        r.GainVsStatic,
			"gain_vs_profileonly_pct":   r.GainVsProfile,
		} {
			if math.IsInf(v, 1) || math.IsNaN(v) {
				m[k] = nil
			} else {
				m[k] = math.Round(v*10) / 10
			}
		}
		out = append(out, m)
	}
	return out
}

func main() {
	var rows []row
	fmt.Printf("%-10s %12s %12s %12s %10s %10s\n",
		"scenario", "dynamic", "static", "profileonly", "vs static", "vs prof")
	for _, sc := range scenarios() {
		preWorkers := base(3).Workers // every scenario starts from 3 healthy stages

		// dynamic: repartition on the post-fault snapshot.
		d := partition.NewDecider(0.15, 30*time.Second)
		if _, _, err := d.Decide(time.Now(), base(len(preWorkers)), false); err != nil {
			panic(err)
		}
		dyn, _, err := d.Decide(time.Now().Add(time.Minute), sc.fault, false)
		if err != nil {
			panic(err)
		}

		// static: one equal split over the worker set it started with, never
		// revisited. Under node failure that set no longer exists, so
		// Evaluate returns +Inf — the pipeline is down, which is what "no
		// repartitioning and no healing" means.
		eq := equalSplit(totalLayers, len(preWorkers))
		static := partition.Evaluate(sc.fault, eq)

		// profileonly: still runs the DP and still heals on a membership
		// change, but its speed/link inputs are frozen at the first (healthy)
		// reading — an offline-profiling system. It therefore recovers from
		// node failure and is blind to thermal and network degradation.
		stale := sc.fault
		stale.Workers = append([]partition.Worker(nil), sc.fault.Workers...)
		stale.LinkMs = append([]float64(nil), sc.fault.LinkMs...)
		for i := range stale.Workers {
			stale.Workers[i].Speed = 1.0
		}
		for i := range stale.LinkMs {
			stale.LinkMs[i] = baseLinkMs
		}
		staleOpt, err := partition.Optimal(stale)
		if err != nil {
			panic(err)
		}
		prof := partition.Evaluate(sc.fault, staleOpt.Splits())

		r := row{sc.name, dyn.BottleneckMs, static, prof,
			gain(static, dyn.BottleneckMs), gain(prof, dyn.BottleneckMs),
			dyn.Splits(), eq}
		rows = append(rows, r)
		fmt.Printf("%-10s %12s %12s %12s %9s %9s\n",
			r.Scenario, ms(r.DynamicMs), ms(r.StaticMs), ms(r.ProfileOnlyMs),
			pct(r.GainVsStatic), pct(r.GainVsProfile))
	}
	out, _ := json.MarshalIndent(jsonable(rows), "", "  ")
	if err := os.WriteFile("bench/dpsim_results.json", out, 0o644); err != nil {
		fmt.Fprintln(os.Stderr, err)
	}
}
