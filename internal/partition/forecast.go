package partition

import (
	"fmt"
	"math"
)

// GateSample is one paired cost scenario. Pairing retains correlation between
// stay and adapt; callers must avoid treating autocorrelated telemetry ticks as
// independent observations. These are predictive samples, not confidence bounds.
type GateSample struct {
	CurrentMs, CandidateMs, TransitionMs float64
}

// ForecastGate is an experimental gate alongside the existing fixed-horizon
// decider. RemainingTokens caps the planning horizon using current throughput.
// The token forecasts measure service capacity over that horizon, rather than
// promising to generate more tokens than a finite workload contains. Nil leaves
// the time horizon unchanged; zero means done. It is not a makespan optimizer.
type ForecastGate struct {
	HorizonS            float64
	RemainingTokens     *float64
	Margin              float64
	RequiredProbability float64
	MinSamples          int
}

type ForecastVerdict struct {
	HorizonS    float64 `json:"horizon_s"`
	TokensStay  float64 `json:"tokens_stay"`
	TokensAdapt float64 `json:"tokens_adapt"`
	Probability float64 `json:"empirical_probability"`
	Samples     int     `json:"samples"`
	Accept      bool    `json:"accept"`
	Reason      string  `json:"reason"`
}

func finiteNonnegative(x float64) bool { return x >= 0 && !math.IsNaN(x) && !math.IsInf(x, 0) }

// Evaluate uses the point forecast when RequiredProbability is zero. Otherwise
// it requires enough paired scenarios and the configured fraction to clear the
// token-advantage margin. This empirical probability is not a calibrated promise.
func (g ForecastGate) Evaluate(point GateSample, samples []GateSample) (ForecastVerdict, error) {
	v := ForecastVerdict{HorizonS: g.HorizonS, Samples: len(samples)}
	if !finiteNonnegative(g.HorizonS) || !finiteNonnegative(g.Margin) ||
		!finiteNonnegative(g.RequiredProbability) || g.RequiredProbability > 1 || g.MinSamples < 0 {
		return v, fmt.Errorf("invalid forecast gate parameters")
	}
	if g.RemainingTokens != nil && !finiteNonnegative(*g.RemainingTokens) {
		return v, fmt.Errorf("invalid remaining work")
	}
	valid := func(s GateSample) bool {
		return finiteNonnegative(s.CurrentMs) && s.CurrentMs > 0 && finiteNonnegative(s.CandidateMs) && s.CandidateMs > 0 && finiteNonnegative(s.TransitionMs)
	}
	if !valid(point) {
		return v, fmt.Errorf("invalid point forecast")
	}
	if g.RemainingTokens != nil {
		v.HorizonS = math.Min(v.HorizonS, *g.RemainingTokens*point.CurrentMs/1000)
	}
	h := v.HorizonS * 1000
	work := func(s GateSample) (float64, float64) {
		stay, adapt := h/s.CurrentMs, math.Max(0, h-s.TransitionMs)/s.CandidateMs
		return stay, adapt
	}
	v.TokensStay, v.TokensAdapt = work(point)
	if h == 0 {
		v.Reason = "no-remaining-horizon"
		return v, nil
	}
	if g.RequiredProbability == 0 {
		v.Accept = v.TokensAdapt > v.TokensStay*(1+g.Margin)
		v.Reason = "point-rejects"
		if v.Accept {
			v.Reason = "point-accepts"
		}
		return v, nil
	}
	minimum := g.MinSamples
	if minimum < 2 {
		minimum = 2
	}
	for _, s := range samples {
		if !valid(s) {
			return v, fmt.Errorf("invalid predictive sample")
		}
	}
	if len(samples) < minimum {
		v.Reason = "insufficient-samples"
		return v, nil
	}
	for _, s := range samples {
		stay, adapt := work(s)
		if adapt > stay*(1+g.Margin) {
			v.Probability++
		}
	}
	v.Probability /= float64(len(samples))
	v.Accept = v.Probability >= g.RequiredProbability
	v.Reason = "probability-rejects"
	if v.Accept {
		v.Reason = "probability-accepts"
	}
	return v, nil
}

// TransitionCalibration updates only after an observed request completes.
// The caller must keep recovery and voluntary moves separate, and must not
// count overlapping requests for one transition as independent transitions.
type TransitionCalibration struct {
	N          int
	MeanMs, M2 float64
}

func (c *TransitionCalibration) Observe(ms float64) error {
	if !finiteNonnegative(ms) {
		return fmt.Errorf("invalid observed transition")
	}
	c.N++
	delta := ms - c.MeanMs
	c.MeanMs += delta / float64(c.N)
	c.M2 += delta * (ms - c.MeanMs)
	return nil
}

func (c TransitionCalibration) StdDevMs() float64 {
	if c.N < 2 {
		return 0
	}
	return math.Sqrt(c.M2 / float64(c.N-1))
}

func (c TransitionCalibration) PredictMs(fallback float64, minimum int) float64 {
	if minimum < 2 {
		minimum = 2
	}
	if c.N < minimum {
		return fallback
	}
	return c.MeanMs
}
