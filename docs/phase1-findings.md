# Phase 1 — Instrumentation and power check

Tool: `cmd/dpsweep`. Data: `docs/phase1-dpsweep-qwen28-2w-plm{3,10,30}.csv`.
Configuration: 28 layers (Qwen3-0.6B), 2 workers, baseline link 0.5 ms.

**These are cost-model predictions, not measurements.** The DP's cost model is
unvalidated until Phase 4. This phase establishes the *predicted range* only. It
does not establish measurement noise — that requires repeated real runs (1.3) — and
must not on its own justify hardware procurement.

## 1.1 Candidate allocation count — settled from the code

Zero-layer assignments **are** allowed:
- `internal/partition/partition.go:52-54` — "An empty stage is skipped by the router
  entirely, so it costs nothing — not even its hop."
- `internal/partition/partition.go:66` — "Workers may receive zero layers (stage
  dropped from the chain)."

So for 28 layers across 2 workers the space is **29** contiguous allocations
(k = 0..28), not 27. Baseline optimum is `0-14/14-28`.

## Finding A — Thermal predicted benefit is scale-invariant

Predicted benefit % is essentially unchanged across per-layer costs, because a
thermal derate scales compute multiplicatively and the ratio cancels:

| Derate | benefit @3 ms | @10 ms | @30 ms |
|---|---|---|---|
| speed 0.9 | 4.6% | 3.9% | 3.7% |
| speed 0.8 | 9.4% | 8.8% | 8.7% |
| speed 0.7 | 15.7% | 15.2% | 15.1% |
| speed 0.5 | 32.5% | 32.3% | 32.2% |

**The existing 15% improvement gate therefore fires at roughly speed ≤ 0.7**,
independent of model speed. That is a stable, designable operating point, and it is
a property of the gate we can state before any hardware arrives.

## Finding B — Network predicted benefit depends entirely on an unmeasured parameter

At the repo's standard 80 ms netem fault:

| Per-layer cost | Predicted benefit @80 ms | Above the existing 15% gate? |
|---|---|---|
| 3 ms | 32.0% | Yes |
| 10 ms | 18.2% | Yes |
| **30 ms** (repo sim default) | **6.0%** | **No** |

At 30 ms/layer the optimum does not move at all until 40 ms of delay. At 3 ms/layer
the DP fully bypasses a worker by 120 ms (`0-28/28-28`).

**Consequence for experiment design.** Whether H1 can show anything under the
standard netem fault is determined by the real per-layer decode cost of
Qwen3-0.6B, which is **unmeasured**. If it is near the simulated 30 ms, the standard
fault yields ~6% predicted benefit — below the controller's own gate — and the
controller would correctly decline to move. A null H1 there would be a fact about
gate calibration at that operating point, not evidence against the hypothesis.

This is a concrete instance of the §1.4 contingent claim: a simulated parameter
choice determines the qualitative conclusion.

## Finding C — Device loss is not a benefit tradeoff

With one worker lost the baseline split is unservable, so "stay" has no defined cost.
Adaptation is mandatory, not optional; predicted benefit is undefined rather than
large. Recovery must therefore bypass the gate (Phase 5.4), and device-loss rows in
the Phase 6 table report recovery and completion rate, not benefit.

## 1.2 Predicted-no-benefit conditions — retained, not discarded

Carried into Phase 6 as first-class rows:

| Condition | Predicted benefit |
|---|---|
| thermal, speed 1.0 (no fault) | 0.0% |
| network ≤ 20 ms @30 ms/layer | 0.0%, optimum does not move |
| network ≤ 10 ms @10 ms/layer | 0.0%, optimum does not move |

These are where the "staying put is correct" finding comes from. They are not
failures of the experiment.

## Exit gate

Proceed to Phase 2 regardless. No hardware decision is taken from this phase.

**Open, resolved by measurement in Phase 4:** the real per-layer decode cost of
Qwen3-0.6B on the target devices. Finding B cannot be settled before it, and the
netem magnitudes for Phase 6 should be selected only once it is known.

**Still required for 1.3:** an empirical noise floor from repeated runs of the
unchanged system. Not derivable from this tool.
