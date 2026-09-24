# Phase 0 — Measurement correctness

Everything here is re-analysis of runs already under `bench/results/` plus the
code changes needed to make the measurements mean what they claim.

## 0.1 The fidelity comparison was category-mismatched

**Diagnosis.** `bench/fidelity.py` compared the DP's `bottleneck_ms` — the slowest
**single** stage — against `1000/tokens_per_sec`, which `worker/router.py:184`
computes per request as tokens ÷ end-to-end duration, i.e. traversal of **all**
stages sequentially. These are different quantities: one governs throughput, the
other latency.

For k balanced stages the ratio of the two is ~k. Every run tested had 3 stages.
The reported "3.0–3.24× gap" was the stage count.

Confirmed directly in the data: run `netem_4cpu_20260913_dynamic_r1` has
`bottleneck_ms = 122.508` with layout `0-4|4-8|8-12`, and a sample request reports
`tokens_per_sec = 2.735` → 365.7 ms/token. 365.7 / 122.5 = **2.99**.

Pinned as a regression test in `internal/partition/pipeline_test.go`
(`TestBottleneckVersusPipelineIsStageCount`): for k balanced stages with negligible
link cost, `PipelineMs / BottleneckMs == k` exactly.

**Code change.** `partition.Result` now carries both predictions, with the
distinction documented at the type:

| Field | Meaning | Correct observable |
|---|---|---|
| `BottleneckMs` | slowest single stage | aggregate tokens/sec under saturated load |
| `PipelineMs` | sum of all stage costs | measured per-token end-to-end cost |

`partition.EvaluatePipeline` added alongside `Evaluate`. The controller emits
`pipeline_ms` in `/state`; `bench/run.py` records it in `*_series.csv`.

**Result — the cost model was never 3× wrong.** Compared against the quantity it
actually predicts, `BottleneckMs` tracks measured aggregate throughput closely:

| Run | n | median error | p10 | p90 | IQR |
|---|---|---|---|---|---|
| failure_4cpu_20260913_dynamic_r1 | 7 | −6.9% | −14.6% | +10.4% | 15.6% |
| netem_4cpu_20260913_dynamic_r1 | 5 | −7.6% | −14.5% | +10.5% | 13.0% |
| netem_4cpu_20260913_dynamic_r2 | 5 | −7.9% | −17.0% | +14.1% | 0.4% |
| netem_4cpu_20260913_dynamic_r3 | 6 | −2.2% | −15.9% | +3.8% | 11.5% |

Windows overlapping a generation change are excluded (throughput would include
transition downtime); windows below 60% of the run's peak are excluded as
demand-limited rather than capacity-limited. Both exclusion counts are reported.

**Consequence for Phase 5.** The transition gate needs predictions calibrated in
real units. They already are, in the throughput units the gate should use. The
README's previous advice — "treat the DP's bottleneck number as a ranking signal,
not a calibrated latency prediction" — was drawn from the confounded comparison.

**Not claimed.** The residual −2 to −8% is not explained. No replacement cause is
asserted; the old gRPC/interpreter-overhead attribution is simply withdrawn as
unsupported.

**CHECK L is not yet possible.** It needs `pipeline_ms`, which the controller only
emits after this change. Existing runs predate it; `fidelity.py` reports the
stage-count diagnostic for them instead of approximating a result.

**Rank correctness is not reported.** It requires several candidate placements
scored under the same conditions — the Phase 6 matched forced-move arms. Not
approximated.

## 0.2 README corrected

The "Model fidelity" design note now states the two-prediction distinction, labels
the old attribution **unsupported and confounded**, and gives the CHECK T error
distribution. It asserts no replacement cause.

## 0.3 Harness corrections

- `pipeline_ms` recorded in `*_series.csv`.
- Idle fraction relabelled a **utilization proxy** everywhere it is displayed
  (`bench/plot.py`, `bench/analyze_tagged_thermal.py`, `bench/run.py` docstring).
  **Column names left unchanged** — renaming them would break analysis of the
  committed journal data, which the standing constraints forbid. The correction is
  to the labels and interpretation, not the schema.
- `fidelity.py` rewritten as two checks reporting error **distributions** (median,
  p10, p25/p75, p90, IQR, fraction within ±20%), never mean ratios.

Still outstanding in 0.3, and requiring new runs rather than re-analysis: real
failure-onset and recovery timestamps, failed-request counts, transition downtime,
and the single-device baseline arm.

## 0.4 Metric schema

Frozen in `docs/RESEARCH_PLAN.md` §5. "p95 latency" is banned as ambiguous; TTFT,
ITL and completion latency are separately defined; recovery is defined as time to
**sustained successful service**, with throughput restoration reported separately
because losing a worker can permanently reduce capacity.

## Exit gate

**Passed.** Fidelity decomposed cleanly; the cost model is better calibrated than
believed, in the correct units. Proceed to Phase 2.
