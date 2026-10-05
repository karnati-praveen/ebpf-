// gate-replay evaluates recorded candidates. It does not drive any workers.
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"shardwise/internal/partition"
	"math"
	"os"
	"sort"
)

type Snapshot struct {
	At    float64
	Input partition.Input
}
type Case struct {
	Run, Scenario, Reason string
	At                    float64
	Point                 partition.GateSample
	From, To              [][2]int
	Past, Future          []Snapshot
	PhaseEnd, RunEnd      float64
	Eligible              bool
}
type Observation struct {
	Run, Scenario string
	At, Ms        float64
}
type Dataset struct {
	Cases        []Case
	Observations []Observation
}
type Row struct {
	Run                     string                    `json:"run"`
	Scenario                string                    `json:"scenario"`
	At                      float64                   `json:"at"`
	Arm                     string                    `json:"arm"`
	Budget                  float64                   `json:"hypothetical_remaining_tokens,omitempty"`
	Verdict                 partition.ForecastVerdict `json:"verdict"`
	CalibrationN            int                       `json:"calibration_n"`
	TransitionMs            float64                   `json:"transition_ms"`
	OracleStay, OracleAdapt float64
}

func futureCapacity(c Case) (float64, float64) {
	stay, adapt := 0.0, 0.0
	for i, s := range c.Future {
		end := c.RunEnd
		if i+1 < len(c.Future) {
			end = c.Future[i+1].At
		}
		end = math.Min(end, c.RunEnd)
		start := math.Max(c.At, s.At)
		cur, cand := partition.Evaluate(s.Input, c.From), partition.Evaluate(s.Input, c.To)
		if cur <= 0 || cand <= 0 || math.IsInf(cur, 0) || math.IsInf(cand, 0) {
			continue
		}
		stay += math.Max(0, end-start) * 1000 / cur
		adapt += math.Max(0, end-math.Max(start, c.At+c.Point.TransitionMs/1000)) * 1000 / cand
	}
	return stay, adapt
}

func main() {
	in := flag.String("input", "", "prepared dataset JSON")
	out := flag.String("out", "", "JSONL output")
	flag.Parse()
	b, e := os.ReadFile(*in)
	if e != nil {
		panic(e)
	}
	var data Dataset
	if e = json.Unmarshal(b, &data); e != nil {
		panic(e)
	}
	sort.Slice(data.Cases, func(i, j int) bool { return data.Cases[i].At < data.Cases[j].At })
	sort.Slice(data.Observations, func(i, j int) bool { return data.Observations[i].At < data.Observations[j].At })
	f, e := os.Create(*out)
	if e != nil {
		panic(e)
	}
	defer f.Close()
	enc := json.NewEncoder(f)
	cal := map[string]*partition.TransitionCalibration{}
	history := map[string][]float64{}
	obs := 0
	rows := 0
	for _, c := range data.Cases {
		for obs < len(data.Observations) && data.Observations[obs].At < c.At {
			o := data.Observations[obs]
			if cal[o.Scenario] == nil {
				cal[o.Scenario] = &partition.TransitionCalibration{}
			}
			if e := cal[o.Scenario].Observe(o.Ms); e != nil {
				panic(e)
			}
			history[o.Scenario] = append(history[o.Scenario], o.Ms)
			obs++
		}
		if !c.Eligible {
			continue
		}
		state := cal[c.Scenario]
		if state == nil {
			state = &partition.TransitionCalibration{}
		}
		point := c.Point
		samples := []partition.GateSample{}
		for _, s := range c.Past {
			cur, cand := partition.Evaluate(s.Input, c.From), partition.Evaluate(s.Input, c.To)
			if cur > 0 && cand > 0 && !math.IsInf(cur, 0) && !math.IsInf(cand, 0) {
				samples = append(samples, partition.GateSample{CurrentMs: cur, CandidateMs: cand, TransitionMs: point.TransitionMs})
			}
		}
		write := func(arm string, g partition.ForecastGate, p partition.GateSample, budget float64) {
			v, e := g.Evaluate(p, samples)
			if e != nil {
				panic(e)
			}
			r := Row{Run: c.Run, Scenario: c.Scenario, At: c.At, Arm: arm, Budget: budget, Verdict: v, CalibrationN: state.N, TransitionMs: p.TransitionMs}
			if e := enc.Encode(r); e != nil {
				panic(e)
			}
			rows++
		}
		base := partition.ForecastGate{HorizonS: 30, Margin: .13}
		write("fixed", base, point, 0)
		for _, budget := range []float64{16, 64, 256, 1024} {
			g := base
			g.RemainingTokens = &budget
			write("remaining-work", g, point, budget)
		}
		g := base
		g.RequiredProbability = .9
		g.MinSamples = 8
		write("probabilistic", g, point, 0)
		// Cross past paired-cost blocks with completed transition observations.
		// This assumes transition duration is independent of cost-block noise;
		// the product rows are predictive scenarios, not independent trials.
		transitionVerdict := partition.ForecastVerdict{HorizonS: 30, Reason: "insufficient-transition-history"}
		if state.N >= 3 && len(samples) >= 8 {
			joint := []partition.GateSample{}
			for _, s := range samples {
				for _, ms := range history[c.Scenario] {
					s.TransitionMs = ms
					joint = append(joint, s)
				}
			}
			transitionVerdict, e = g.Evaluate(point, joint)
			if e != nil {
				panic(e)
			}
		}
		if e := enc.Encode(Row{Run: c.Run, Scenario: c.Scenario, At: c.At, Arm: "probabilistic-transition", Verdict: transitionVerdict, CalibrationN: state.N, TransitionMs: state.PredictMs(point.TransitionMs, 3)}); e != nil {
			panic(e)
		}
		rows++
		p := point
		p.TransitionMs = state.PredictMs(point.TransitionMs, 3)
		write("online-calibrated", base, p, 0)
		g = base
		g.HorizonS = math.Max(0, c.PhaseEnd-c.At)
		write("oracle-phase-horizon", g, point, 0)
		// Privileged future telemetry; conditional on the recorded trace and
		// a single proposed move. This is not a globally optimal policy oracle.
		stay, adapt := futureCapacity(c)
		r := Row{Run: c.Run, Scenario: c.Scenario, At: c.At, Arm: "oracle-future-trace", TransitionMs: point.TransitionMs, OracleStay: stay, OracleAdapt: adapt, Verdict: partition.ForecastVerdict{HorizonS: math.Max(0, c.RunEnd-c.At), TokensStay: stay, TokensAdapt: adapt, Accept: adapt > stay*1.13, Reason: "future-trace-model"}}
		if e := enc.Encode(r); e != nil {
			panic(e)
		}
		rows++
	}
	fmt.Printf("%d candidates, %d calibration observations, %d arm rows\n", len(data.Cases), len(data.Observations), rows)
}
