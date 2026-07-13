// Package partition computes the optimal contiguous layer split for a
// pipeline of heterogeneous workers from a live telemetry snapshot. It is
// the classical linear partition problem: minimize the bottleneck stage,
// where a stage's cost is its compute time plus the transfer cost of the
// hop feeding it.
package partition

import (
	"fmt"
	"math"
	"time"
)

// Worker is one pipeline stage candidate with its live effective speed.
type Worker struct {
	Name  string
	Addr  string
	Node  string
	Speed float64 // effective compute multiplier (0, 1]; includes throttling
}

// Input is one telemetry snapshot for the partitioner.
type Input struct {
	TotalLayers int
	PerLayerMs  float64  // base per-layer compute cost at Speed == 1
	Workers     []Worker // in pipeline order
	LinkMs      []float64 // LinkMs[i] = transfer cost of hop i -> i+1; len(Workers)-1
}

// Assignment maps one worker to a half-open layer range [Start, End).
type Assignment struct {
	Worker Worker
	Start  int
	End    int
}

// Result is an optimal (or evaluated) split.
type Result struct {
	Assignments  []Assignment
	BottleneckMs float64
}

func (r *Result) Splits() [][2]int {
	out := make([][2]int, len(r.Assignments))
	for i, a := range r.Assignments {
		out[i] = [2]int{a.Start, a.End}
	}
	return out
}

// stageCost is the per-token-step cost of a stage: receive + compute.
// An empty stage is skipped by the router entirely, so it costs nothing —
// not even its hop. This lets the partitioner bypass a worker whose link
// degraded so badly that redistributing its layers is cheaper than the hop.
func stageCost(in Input, worker, layers int) float64 {
	if layers == 0 {
		return 0
	}
	cost := float64(layers) * in.PerLayerMs / math.Max(in.Workers[worker].Speed, 0.01)
	if worker > 0 {
		cost += in.LinkMs[worker-1]
	}
	return cost
}

// Optimal solves the linear partition exactly via DP in O(N^2 * K).
// Workers may receive zero layers (stage dropped from the chain).
func Optimal(in Input) (*Result, error) {
	n, k := in.TotalLayers, len(in.Workers)
	if k == 0 {
		return nil, fmt.Errorf("no workers")
	}
	if n < 1 {
		return nil, fmt.Errorf("no layers")
	}
	if len(in.LinkMs) != k-1 {
		return nil, fmt.Errorf("need %d link costs, got %d", k-1, len(in.LinkMs))
	}

	// f[j][w] = minimal bottleneck assigning the first j layers to the
	// first w workers; choice[j][w] = start layer of worker w-1's range.
	f := make([][]float64, n+1)
	choice := make([][]int, n+1)
	for j := range f {
		f[j] = make([]float64, k+1)
		choice[j] = make([]int, k+1)
		for w := range f[j] {
			f[j][w] = math.Inf(1)
		}
	}
	f[0][0] = 0
	for w := 1; w <= k; w++ {
		for j := 0; j <= n; j++ {
			for split := 0; split <= j; split++ {
				if math.IsInf(f[split][w-1], 1) {
					continue
				}
				cost := math.Max(f[split][w-1], stageCost(in, w-1, j-split))
				if cost < f[j][w] {
					f[j][w] = cost
					choice[j][w] = split
				}
			}
		}
	}

	res := &Result{
		Assignments:  make([]Assignment, k),
		BottleneckMs: f[n][k],
	}
	j := n
	for w := k; w >= 1; w-- {
		start := choice[j][w]
		res.Assignments[w-1] = Assignment{Worker: in.Workers[w-1], Start: start, End: j}
		j = start
	}
	return res, nil
}

// Evaluate computes the bottleneck of an existing split under new telemetry.
// Returns +Inf if the split does not fit the input's worker count or layers.
func Evaluate(in Input, splits [][2]int) float64 {
	if len(splits) != len(in.Workers) || len(in.LinkMs) != len(in.Workers)-1 {
		return math.Inf(1)
	}
	bottleneck := 0.0
	expect := 0
	for i, s := range splits {
		if s[0] != expect || s[1] < s[0] {
			return math.Inf(1)
		}
		expect = s[1]
		bottleneck = math.Max(bottleneck, stageCost(in, i, s[1]-s[0]))
	}
	if expect != in.TotalLayers {
		return math.Inf(1)
	}
	return bottleneck
}

// Decider adds hysteresis: it repartitions only when the optimal split beats
// the current one by ImprovementFrac and Cooldown has elapsed — unless the
// worker set changed (healing), which always forces a new split.
type Decider struct {
	ImprovementFrac float64
	Cooldown        time.Duration

	current    *Result
	lastChange time.Time
}

func NewDecider(improvementFrac float64, cooldown time.Duration) *Decider {
	return &Decider{ImprovementFrac: improvementFrac, Cooldown: cooldown}
}

func (d *Decider) Current() *Result { return d.current }

// Decide returns the split to apply and whether it is a change.
func (d *Decider) Decide(now time.Time, in Input, force bool) (*Result, bool, error) {
	opt, err := Optimal(in)
	if err != nil {
		return nil, false, err
	}
	if d.current == nil || force || workersChanged(d.current, in.Workers) {
		d.current = opt
		d.lastChange = now
		return opt, true, nil
	}
	currentCost := Evaluate(in, d.current.Splits())
	improved := opt.BottleneckMs < currentCost*(1-d.ImprovementFrac)
	if improved && now.Sub(d.lastChange) >= d.Cooldown {
		d.current = opt
		d.lastChange = now
		return opt, true, nil
	}
	// Keep the current split; refresh its evaluated bottleneck for status.
	kept := &Result{Assignments: d.current.Assignments, BottleneckMs: currentCost}
	d.current = kept
	return kept, false, nil
}

func workersChanged(cur *Result, workers []Worker) bool {
	if len(cur.Assignments) != len(workers) {
		return true
	}
	for i, a := range cur.Assignments {
		if a.Worker.Name != workers[i].Name || a.Worker.Addr != workers[i].Addr {
			return true
		}
	}
	return false
}
