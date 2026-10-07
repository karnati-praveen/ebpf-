package partition

import (
	"math"
	"sort"
)

// optimalCapacity exactly minimizes the ideal closed-network envelope
// max(B, P/Q), not measured runtime throughput. Minimizing B alone is only
// adequate when Q is large enough to fill the chosen pipeline.
//
// For each possible bottleneck cap b, a constrained sum DP finds the least P
// among splits with every stage <= b. P(b) is nonincreasing. Before the first
// b >= P(b)/Q the envelope is P(b)/Q; after it, the envelope is b. Thus only
// the crossing and its predecessor need comparison. Binary search needs
// O(log(K N^2)) sum DPs, each O(K N^2), plus sorting possible stage costs.
func optimalCapacity(in Input) (*Result, error) {
	// Share shape validation with the established DP.
	if _, err := OptimalForObjective(in, ObjectiveLatency); err != nil {
		return nil, err
	}
	n, k := in.TotalLayers, len(in.Workers)
	perLayer := perLayerCost(in)
	caps := []float64{0}
	for w := 0; w < k; w++ {
		for start := 0; start < n; start++ {
			for end := start + 1; end <= n; end++ {
				caps = append(caps, stageCost(in, perLayer, w, start, end))
			}
		}
	}
	sort.Float64s(caps)
	unique := caps[:0]
	for _, cap := range caps {
		if len(unique) == 0 || cap != unique[len(unique)-1] {
			unique = append(unique, cap)
		}
	}
	q := float64(max(1, in.Concurrency))
	under := func(cap float64) *Result {
		f := make([][]float64, k+1)
		choice := make([][]int, k+1)
		for w := range f {
			f[w] = make([]float64, n+1)
			choice[w] = make([]int, n+1)
			for j := range f[w] {
				f[w][j] = math.Inf(1)
			}
		}
		f[0][0] = 0
		for w := 1; w <= k; w++ {
			for end := 0; end <= n; end++ {
				for start := 0; start <= end; start++ {
					stage := stageCost(in, perLayer, w-1, start, end)
					cost := f[w-1][start] + stage
					if stage <= cap && cost < f[w][end] {
						f[w][end], choice[w][end] = cost, start
					}
				}
			}
		}
		if math.IsInf(f[k][n], 1) {
			return nil
		}
		res := &Result{Assignments: make([]Assignment, k), PipelineMs: f[k][n]}
		end := n
		for w := k; w > 0; w-- {
			start := choice[w][end]
			res.Assignments[w-1] = Assignment{Worker: in.Workers[w-1], Start: start, End: end}
			res.BottleneckMs = math.Max(res.BottleneckMs, stageCost(in, perLayer, w-1, start, end))
			end = start
		}
		return res
	}
	crossing := sort.Search(len(unique), func(i int) bool {
		res := under(unique[i])
		return res != nil && unique[i] >= res.PipelineMs/q
	})
	best := under(unique[crossing])
	if crossing > 0 {
		previous := under(unique[crossing-1])
		if previous != nil && math.Max(previous.BottleneckMs, previous.PipelineMs/q) < math.Max(best.BottleneckMs, best.PipelineMs/q) {
			best = previous
		}
	}
	return best, nil
}
