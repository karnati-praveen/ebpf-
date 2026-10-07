package partition

import (
	"math"
	"math/rand"
	"testing"
)

func TestCapacityThreeWorkersTwoRequests(t *testing.T) {
	in := Input{TotalLayers: 9, PerLayerMs: 1, Workers: workers(1, 1, 1), LinkMs: []float64{1, 1}, Concurrency: 2}
	saturated, err := Optimal(in)
	if err != nil {
		t.Fatal(err)
	}
	finite, err := OptimalForObjective(in, ObjectiveCapacity)
	if err != nil {
		t.Fatal(err)
	}
	if cost := ObjectiveCost(in, saturated.Splits(), ObjectiveCapacity); cost != 5.5 {
		t.Fatalf("saturated layout envelope = %v, want 5.5", cost)
	}
	if cost := ObjectiveCost(in, finite.Splits(), ObjectiveCapacity); cost != 5 {
		t.Fatalf("capacity layout envelope = %v, want 5", cost)
	}
}

// Independent exhaustive enumeration checks the crossing search, empty
// workers, endpoint placement, heterogeneity, and Q above/below stage count.
func TestCapacityAgainstExhaustive(t *testing.T) {
	rng := rand.New(rand.NewSource(20261007))
	for trial := 0; trial < 1000; trial++ {
		n, k := 1+rng.Intn(9), 1+rng.Intn(4)
		in := Input{TotalLayers: n, PerLayerMs: rng.Float64() * 4, EmbedMs: rng.Float64() * 3, HeadMs: rng.Float64() * 5, Concurrency: rng.Intn(9)}
		for w := 0; w < k; w++ {
			in.Workers = append(in.Workers, Worker{Speed: .1 + rng.Float64()*2})
			if w > 0 {
				in.LinkMs = append(in.LinkMs, rng.Float64()*10)
			}
		}
		best := math.Inf(1)
		splits := make([][2]int, k)
		var enumerate func(int, int)
		enumerate = func(w, start int) {
			if w == k-1 {
				splits[w] = [2]int{start, n}
				// Calculate directly rather than using ObjectiveCost.
				b, p := 0.0, 0.0
				for i, s := range splits {
					if s[0] == s[1] {
						continue
					}
					cost := float64(s[1]-s[0]) * in.PerLayerMs / in.Workers[i].Speed
					if s[0] == 0 {
						cost += in.EmbedMs / in.Workers[i].Speed
					}
					if s[1] == n {
						cost += in.HeadMs / in.Workers[i].Speed
					}
					if i > 0 {
						cost += in.LinkMs[i-1]
					}
					b, p = math.Max(b, cost), p+cost
				}
				best = math.Min(best, math.Max(b, p/float64(max(1, in.Concurrency))))
				return
			}
			for end := start; end <= n; end++ {
				splits[w] = [2]int{start, end}
				enumerate(w+1, end)
			}
		}
		enumerate(0, 0)
		res, err := OptimalForObjective(in, ObjectiveCapacity)
		if err != nil {
			t.Fatal(err)
		}
		got := ObjectiveCost(in, res.Splits(), ObjectiveCapacity)
		if math.Abs(got-best) > 1e-9 {
			t.Fatalf("trial %d: got %g want %g; input=%+v splits=%v", trial, got, best, in, res.Splits())
		}
	}
}

func TestCapacityRejectsNonfiniteCosts(t *testing.T) {
	for _, value := range []float64{math.NaN(), math.Inf(1), -1} {
		in := Input{TotalLayers: 2, PerLayerMs: value, Workers: workers(1)}
		if _, err := OptimalForObjective(in, ObjectiveCapacity); err == nil {
			t.Fatal("accepted invalid cost")
		}
	}
}
