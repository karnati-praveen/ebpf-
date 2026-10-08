package partition

import (
	"fmt"
	"math"
	"time"
)

// CalibratedGate combines completed telemetry blocks with held-out transition
// ratios. The Cartesian product is a scenario set, not IID observations.
type CalibratedGate struct {
	PointOnly                 bool
	DisableCalibration        bool
	ID                        string
	Ratios                    []float64
	RequiredProbability       float64
	MinBlocks, MinTransitions int
	Blocks                    []Input
	pending                   *Input
	bucket                    int64
}

func (g *CalibratedGate) defaults() {
	if g.RequiredProbability == 0 {
		g.RequiredProbability = .9
	}
	if g.MinBlocks == 0 {
		g.MinBlocks = 12
	}
	if g.MinTransitions == 0 {
		g.MinTransitions = 10
	}
}

func cloneInput(in Input) Input {
	in.Workers = append([]Worker(nil), in.Workers...)
	in.LinkMs = append([]float64(nil), in.LinkMs...)
	in.PerLayerByCtx = append([]CtxCost(nil), in.PerLayerByCtx...)
	return in
}

// Observe retains the last snapshot in each completed five-second block.
// Gaps, stale inputs, worker-set changes and backward time reset history.
func (g *CalibratedGate) Observe(now time.Time, in Input, fresh bool) {
	g.defaults()
	bucket := now.Unix() / 5
	same := g.pending != nil && len(g.pending.Workers) == len(in.Workers)
	if same {
		for i, w := range in.Workers {
			if w.Name != g.pending.Workers[i].Name || w.Addr != g.pending.Workers[i].Addr {
				same = false
				break
			}
		}
	}
	if !fresh || (g.pending != nil && (!same || bucket < g.bucket || bucket > g.bucket+1)) {
		g.Blocks = nil
		g.pending = nil
	}
	if !fresh {
		return
	}
	if g.pending != nil && bucket != g.bucket {
		g.Blocks = append(g.Blocks, cloneInput(*g.pending))
		if len(g.Blocks) > g.MinBlocks {
			g.Blocks = g.Blocks[len(g.Blocks)-g.MinBlocks:]
		}
	}
	snapshot := cloneInput(in)
	g.pending = &snapshot
	g.bucket = bucket
}

func (d *Decider) evaluateCalibrated(dec *Decision, live Input, from, to [][2]int) error {
	g := &d.Calibrated
	g.defaults()
	if g.MinBlocks < 1 || g.MinTransitions < 1 || !finiteNonnegative(g.RequiredProbability) || g.RequiredProbability > 1 {
		return fmt.Errorf("invalid calibrated gate configuration")
	}
	dec.CalibrationID = g.ID
	dec.TelemetryBlocks = len(g.Blocks)
	dec.CalibrationTransitions = len(g.Ratios)
	dec.RequiredProbability = g.RequiredProbability
	dec.RemainingTokens = d.Gate.RemainingTokens
	dec.BaseTransitionMs = d.Gate.TransitionMs(live.TotalLayers)
	if len(g.Blocks) < g.MinBlocks {
		dec.Reason = "insufficient-telemetry-blocks"
		return nil
	}
	if len(g.Ratios) < g.MinTransitions {
		dec.Reason = "insufficient-calibration-transitions"
		return nil
	}
	ratios := append([]float64(nil), g.Ratios...)
	if g.DisableCalibration {
		for i := range ratios {
			ratios[i] = 1
		}
	}
	ratiosMean := 0.0
	for _, ratio := range ratios {
		if ratio <= 0 || !finiteNonnegative(ratio) {
			return fmt.Errorf("invalid transition calibration ratio")
		}
		ratiosMean += ratio / float64(len(ratios))
	}
	samples := make([]GateSample, 0, len(g.Blocks)*len(g.Ratios))
	for _, historic := range g.Blocks {
		in := cloneInput(live)
		if len(historic.Workers) != len(in.Workers) {
			return fmt.Errorf("calibrated worker-set mismatch")
		}
		for i, w := range historic.Workers {
			if w.Name != in.Workers[i].Name || w.Addr != in.Workers[i].Addr {
				return fmt.Errorf("calibrated worker identity mismatch")
			}
			in.Workers[i].Speed = w.Speed
		}
		in.LinkMs = append([]float64(nil), historic.LinkMs...)
		for _, ratio := range ratios {
			samples = append(samples, GateSample{ObjectiveCost(in, from, d.Objective), ObjectiveCost(in, to, d.Objective), dec.BaseTransitionMs * ratio})
		}
	}
	point := GateSample{dec.CurrentObjectiveMs, dec.OptimalObjectiveMs, dec.BaseTransitionMs * ratiosMean}
	probability := g.RequiredProbability
	if g.PointOnly {
		probability = 0
	}
	dec.PointForecastOnly = g.PointOnly
	dec.CalibrationDisabled = g.DisableCalibration
	v, err := (ForecastGate{HorizonS: d.Gate.HorizonS, RemainingTokens: d.Gate.RemainingTokens, Margin: d.Gate.SafetyMargin, RequiredProbability: probability, MinSamples: g.MinBlocks * g.MinTransitions}).Evaluate(point, samples)
	if err != nil {
		return err
	}
	dec.ForecastSamples = len(samples)
	dec.ForecastScenarios = samples
	dec.EmpiricalProbability = v.Probability
	dec.TransitionMs = point.TransitionMs
	dec.HorizonS = v.HorizonS
	dec.TokensStay = v.TokensStay
	dec.TokensAdapt = v.TokensAdapt
	dec.GateAccepts = v.Accept
	dec.Reason = "calibrated-" + v.Reason
	if dec.CurrentObjectiveMs > dec.OptimalObjectiveMs {
		dec.BreakEvenS = point.TransitionMs * dec.CurrentObjectiveMs / (dec.CurrentObjectiveMs - dec.OptimalObjectiveMs) / 1000
	}
	if math.IsNaN(dec.BreakEvenS) {
		return fmt.Errorf("invalid break-even forecast")
	}
	return nil
}
