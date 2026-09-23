// Package partition computes the optimal contiguous layer split for a
// pipeline of heterogeneous workers from a live telemetry snapshot. It is
// the classical linear partition problem: minimize the bottleneck stage,
// where a stage's cost is its compute time plus the transfer cost of the
// hop feeding it.
package partition

import (
	"fmt"
	"math"
	"sort"
	"time"
)

// Worker is one pipeline stage candidate with its live effective speed.
type Worker struct {
	Name  string
	Addr  string
	Node  string
	Speed float64 // effective compute multiplier (0, 1]; includes throttling
}

// CtxCost is a measured per-layer compute cost at one context length.
type CtxCost struct {
	ContextLen int
	PerLayerMs float64
}

// Input is one telemetry snapshot for the partitioner.
type Input struct {
	TotalLayers int
	PerLayerMs  float64   // base per-layer compute cost at Speed == 1
	Workers     []Worker  // in pipeline order
	LinkMs      []float64 // LinkMs[i] = transfer cost of hop i -> i+1; len(Workers)-1

	// EmbedMs and HeadMs are ENDPOINT costs: compute that belongs to whichever
	// stage holds layer 0 (the embedding lookup) and whichever holds the last
	// layer (final norm + output projection), rather than scaling with layer
	// count. They are speed-scaled like any other compute on that device.
	//
	// These are not a detail. Measured on Qwen3-0.6B (CPU, FP32), lm_head plus
	// the final-norm excess is 38-44 ms/token and constant in context, which is
	// 33-49% of a 14-layer stage. Omitting them makes the DP choose an even
	// split when the true optimum is skewed away from the last stage, costing
	// 10.7-15.0% of bottleneck -- at or above the controller's own 15%
	// improvement threshold. See docs/phase4-prelim-findings.md.
	//
	// Zero (the default) reproduces the previous layer-proportional model.
	EmbedMs float64
	HeadMs  float64

	// ContextLen and PerLayerByCtx make per-layer compute context-dependent.
	// Measured decode cost rises 5.55 -> 9.49 ms/layer from 128 to 2048 tokens
	// (+71%), so a single profiled scalar mis-predicts across the working
	// range. When PerLayerByCtx is empty, PerLayerMs is used unchanged.
	ContextLen    int
	PerLayerByCtx []CtxCost
}

// perLayerCost resolves the effective per-layer cost for this input, linearly
// interpolating the measured table at ContextLen and clamping outside it.
// Falls back to the scalar PerLayerMs when no table is supplied.
func perLayerCost(in Input) float64 {
	t := in.PerLayerByCtx
	if len(t) == 0 {
		return in.PerLayerMs
	}
	sorted := append([]CtxCost(nil), t...)
	sort.Slice(sorted, func(i, j int) bool { return sorted[i].ContextLen < sorted[j].ContextLen })
	c := in.ContextLen
	if c <= sorted[0].ContextLen {
		return sorted[0].PerLayerMs
	}
	last := sorted[len(sorted)-1]
	if c >= last.ContextLen {
		return last.PerLayerMs
	}
	for i := 1; i < len(sorted); i++ {
		lo, hi := sorted[i-1], sorted[i]
		if c <= hi.ContextLen {
			span := float64(hi.ContextLen - lo.ContextLen)
			if span == 0 {
				return hi.PerLayerMs
			}
			f := float64(c-lo.ContextLen) / span
			return lo.PerLayerMs + f*(hi.PerLayerMs-lo.PerLayerMs)
		}
	}
	return last.PerLayerMs
}

// Assignment maps one worker to a half-open layer range [Start, End).
type Assignment struct {
	Worker Worker
	Start  int
	End    int
}

// Result is an optimal (or evaluated) split.
//
// BottleneckMs and PipelineMs measure different things and must not be
// compared against the same observable:
//
//   - BottleneckMs is the slowest single stage. It governs steady-state
//     THROUGHPUT once the pipeline is full, so its observable counterpart is
//     aggregate tokens/sec under saturated load.
//   - PipelineMs is the sum of every stage's cost. A token traverses all
//     stages sequentially, so it governs per-request LATENCY, and its
//     observable counterpart is measured per-token end-to-end cost.
//
// Confusing the two is what produced the spurious ~3x "fidelity gap" (it was
// roughly the stage count, not model error). See docs/phase1-findings.md.
type Result struct {
	Assignments  []Assignment
	BottleneckMs float64 // slowest stage -> predicts throughput
	PipelineMs   float64 // sum of stages  -> predicts per-request latency
}

func (r *Result) Splits() [][2]int {
	out := make([][2]int, len(r.Assignments))
	for i, a := range r.Assignments {
		out[i] = [2]int{a.Start, a.End}
	}
	return out
}

// stageCost is the per-token-step cost of a stage holding layers [start, end):
// receive + compute + any endpoint module it owns.
//
// An empty stage is skipped by the router entirely, so it costs nothing — not
// even its hop. This lets the partitioner bypass a worker whose link degraded
// so badly that redistributing its layers is cheaper than the hop.
//
// Endpoint attribution is decidable locally: the stage holding layer 0 owns the
// embedding, and the stage holding the last layer owns the final norm and output
// projection. Because an empty stage returns early, these fall through to the
// first and last NON-EMPTY stages, which is what the router actually executes.
func stageCost(in Input, perLayer float64, worker, start, end int) float64 {
	layers := end - start
	if layers <= 0 {
		return 0
	}
	speed := math.Max(in.Workers[worker].Speed, 0.01)
	cost := float64(layers) * perLayer / speed
	if start == 0 {
		cost += in.EmbedMs / speed
	}
	if end == in.TotalLayers {
		cost += in.HeadMs / speed
	}
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
	perLayer := perLayerCost(in)
	f[0][0] = 0
	for w := 1; w <= k; w++ {
		for j := 0; j <= n; j++ {
			for split := 0; split <= j; split++ {
				if math.IsInf(f[split][w-1], 1) {
					continue
				}
				cost := math.Max(f[split][w-1], stageCost(in, perLayer, w-1, split, j))
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
	for i, a := range res.Assignments {
		res.PipelineMs += stageCost(in, perLayer, i, a.Start, a.End)
	}
	return res, nil
}

// Evaluate computes the bottleneck (slowest stage) of an existing split under
// new telemetry -- the THROUGHPUT-governing quantity. For the LATENCY-governing
// quantity use EvaluatePipeline.
// Returns +Inf if the split does not fit the input's worker count or layers.
func Evaluate(in Input, splits [][2]int) float64 {
	if len(splits) != len(in.Workers) || len(in.LinkMs) != len(in.Workers)-1 {
		return math.Inf(1)
	}
	perLayer := perLayerCost(in)
	bottleneck := 0.0
	expect := 0
	for i, s := range splits {
		if s[0] != expect || s[1] < s[0] {
			return math.Inf(1)
		}
		expect = s[1]
		bottleneck = math.Max(bottleneck, stageCost(in, perLayer, i, s[0], s[1]))
	}
	if expect != in.TotalLayers {
		return math.Inf(1)
	}
	return bottleneck
}

// EvaluatePipeline computes the sum of every stage's cost for an existing
// split -- the LATENCY-governing quantity, since a token traverses all stages
// sequentially. Returns +Inf on the same validity failures as Evaluate.
func EvaluatePipeline(in Input, splits [][2]int) float64 {
	if len(splits) != len(in.Workers) || len(in.LinkMs) != len(in.Workers)-1 {
		return math.Inf(1)
	}
	perLayer := perLayerCost(in)
	total, expect := 0.0, 0
	for i, s := range splits {
		if s[0] != expect || s[1] < s[0] {
			return math.Inf(1)
		}
		expect = s[1]
		total += stageCost(in, perLayer, i, s[0], s[1])
	}
	if expect != in.TotalLayers {
		return math.Inf(1)
	}
	return total
}

// Policy selects how voluntary repartitions are gated. Recovery (a changed
// worker set) always bypasses the policy: the current split is unservable.
type Policy string

const (
	// PolicyNone moves whenever the optimum is strictly better, with no
	// threshold and no cooldown -- the "no hysteresis" arm.
	PolicyNone Policy = "none"
	// PolicyHysteresis moves only when the optimum beats the current split by
	// ImprovementFrac and Cooldown has elapsed -- the original behaviour.
	PolicyHysteresis Policy = "hysteresis"
	// PolicyGate is hysteresis plus the transition gate: a move must also
	// deliver more useful tokens over the planning horizon than staying put,
	// after paying its transition downtime, by at least SafetyMargin.
	PolicyGate Policy = "gate"
	// PolicyGateForce computes exactly the same gate verdict as PolicyGate but
	// executes the move regardless. Run on the same fault trace as
	// PolicyGate, it supplies the OBSERVED outcome of moves the gate rejects,
	// which otherwise have no counterfactual.
	PolicyGateForce Policy = "gate-force"
)

// GateParams parameterises the transition gate. Transition downtime is
//
//	T = TransitionFixedMs + ContextLen * PrefillMsPerTokenLayer * TotalLayers
//
// TransitionFixedMs covers weight reload and orchestration. The second term is
// cache reconstruction: on a relayout the router replays each in-flight
// request from step 0 through the WHOLE chain, so every layer re-prefills the
// context, not only the layers that moved.
type GateParams struct {
	HorizonS               float64
	TransitionFixedMs      float64
	PrefillMsPerTokenLayer float64
	ContextLen             int
	SafetyMargin           float64
}

// TransitionMs is the predicted downtime of one relayout.
func (g GateParams) TransitionMs(totalLayers int) float64 {
	return g.TransitionFixedMs + float64(g.ContextLen)*g.PrefillMsPerTokenLayer*float64(totalLayers)
}

// Decision records one evaluated candidate move, accepted or not, with every
// quantity the verdict used. Rejected moves are recorded too, because
// evaluating whether a rejection was justified needs them.
type Decision struct {
	Time         time.Time `json:"time"`
	Policy       Policy    `json:"policy"`
	Reason       string    `json:"reason"`
	CurrentMs    float64   `json:"current_bottleneck_ms"`
	OptimalMs    float64   `json:"optimal_bottleneck_ms"`
	Improvement  float64   `json:"improvement_frac"`
	TransitionMs float64   `json:"transition_ms,omitempty"`
	HorizonS     float64   `json:"horizon_s,omitempty"`
	TokensStay   float64   `json:"tokens_stay,omitempty"`
	TokensAdapt  float64   `json:"tokens_adapt,omitempty"`
	BreakEvenS   float64   `json:"break_even_s,omitempty"`
	GateAccepts  bool      `json:"gate_accepts"`
	Executed     bool      `json:"executed"`
	FromSplits   [][2]int  `json:"from_splits,omitempty"`
	ToSplits     [][2]int  `json:"to_splits"`
}

// Decider decides when to adopt a new split. Recovery -- a changed worker set
// -- always forces a new split, whatever the policy.
type Decider struct {
	ImprovementFrac float64
	Cooldown        time.Duration
	Policy          Policy
	Gate            GateParams

	current    *Result
	lastChange time.Time
	last       *Decision
}

// NewDecider keeps the original constructor: the hysteresis policy.
func NewDecider(improvementFrac float64, cooldown time.Duration) *Decider {
	return &Decider{ImprovementFrac: improvementFrac, Cooldown: cooldown, Policy: PolicyHysteresis}
}

func (d *Decider) Current() *Result { return d.current }

// LastDecision returns the most recent evaluated candidate move, or nil.
func (d *Decider) LastDecision() *Decision { return d.last }

// Decide returns the split to apply and whether it is a change.
func (d *Decider) Decide(now time.Time, in Input, force bool) (*Result, bool, error) {
	opt, err := Optimal(in)
	if err != nil {
		return nil, false, err
	}
	if d.current == nil || force || workersChanged(d.current, in.Workers) {
		var from [][2]int
		if d.current != nil {
			from = d.current.Splits()
		}
		d.last = &Decision{Time: now, Policy: d.policy(), Reason: "recovery-or-initial",
			OptimalMs: opt.BottleneckMs, GateAccepts: true, Executed: true,
			FromSplits: from, ToSplits: opt.Splits()}
		d.current = opt
		d.lastChange = now
		return opt, true, nil
	}

	curSplits := d.current.Splits()
	currentCost := Evaluate(in, curSplits)
	keep := func() (*Result, bool, error) {
		kept := &Result{Assignments: d.current.Assignments, BottleneckMs: currentCost,
			PipelineMs: EvaluatePipeline(in, curSplits)}
		d.current = kept
		return kept, false, nil
	}
	if splitsEqual(curSplits, opt.Splits()) || !(opt.BottleneckMs < currentCost) {
		return keep()
	}

	dec := &Decision{Time: now, Policy: d.policy(), CurrentMs: currentCost,
		OptimalMs: opt.BottleneckMs, Improvement: (currentCost - opt.BottleneckMs) / currentCost,
		FromSplits: curSplits, ToSplits: opt.Splits()}
	d.last = dec

	execute := false
	switch d.policy() {
	case PolicyNone:
		dec.Reason, dec.GateAccepts, execute = "strictly-better", true, true
	case PolicyHysteresis, PolicyGate, PolicyGateForce:
		if opt.BottleneckMs >= currentCost*(1-d.ImprovementFrac) {
			dec.Reason = "below-improvement-threshold"
			return keep()
		}
		if now.Sub(d.lastChange) < d.Cooldown {
			dec.Reason = "cooldown"
			return keep()
		}
		if d.policy() == PolicyHysteresis {
			dec.Reason, dec.GateAccepts, execute = "hysteresis-passed", true, true
			break
		}
		d.evaluateGate(dec, in.TotalLayers, currentCost, opt.BottleneckMs)
		execute = dec.GateAccepts || d.policy() == PolicyGateForce
		switch {
		case dec.GateAccepts:
			dec.Reason = "gate-accepts"
		case execute:
			dec.Reason = "gate-rejects-forced"
		default:
			dec.Reason = "gate-rejects"
		}
	default:
		return nil, false, fmt.Errorf("unknown decision policy %q", d.Policy)
	}

	if !execute {
		return keep()
	}
	dec.Executed = true
	d.current = opt
	d.lastChange = now
	return opt, true, nil
}

// evaluateGate fills in the gate's quantities. Both sides are in useful tokens
// delivered over the horizon, so the comparison has consistent units:
//
//	stay  = H / current
//	adapt = max(0, H - T) / optimal
//
// and the break-even horizon, where the two are equal, is
//
//	H* = T * current / (current - optimal)
func (d *Decider) evaluateGate(dec *Decision, totalLayers int, current, optimal float64) {
	h := d.Gate.HorizonS * 1000
	t := d.Gate.TransitionMs(totalLayers)
	dec.HorizonS = d.Gate.HorizonS
	dec.TransitionMs = t
	dec.TokensStay = h / current
	dec.TokensAdapt = math.Max(0, h-t) / optimal
	if current > optimal {
		dec.BreakEvenS = t * current / (current - optimal) / 1000
	}
	dec.GateAccepts = dec.TokensAdapt > dec.TokensStay*(1+d.Gate.SafetyMargin)
}

func (d *Decider) policy() Policy {
	if d.Policy == "" {
		return PolicyHysteresis
	}
	return d.Policy
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
