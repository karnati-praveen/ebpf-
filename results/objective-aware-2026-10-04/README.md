# Objective-aware placement and live remaining-work gate

The implemented product-direction hypothesis is that **the placement objective
should match admitted demand, and a voluntary transition should repay its cost
within the work still admitted**. This is a candidate systems contribution,
not a claim that sum/minimax partition algorithms or workload routing are new.

## Implementation

- `throughput` retains the original exact minimax partitioner.
- `latency` minimizes the sum of compute, endpoint and incoming-hop costs using
  the same contiguous-layer DP; empty stages allow whole-model execution.
- `auto` reads the router's admitted workload: one request selects latency,
  multiple requests select throughput. Initial placement prefers latency.
- The gate compares capacity using the selected objective's cost, including
  reload/full-chain reconstruction downtime and the existing safety margin.
- `remaining-work-aware` caps the horizon at
  `min(configured_horizon, remaining_output_tokens * current_objective_ms / 1000)`.
- Idle or unavailable workload data holds voluntary changes. Worker-set changes
  still force recovery. Request failure/completion releases its budget, and
  replay retains progress already made toward the output-token limit.

Defaults retain throughput placement and the original fixed-horizon gate.
The new behavior is opt-in. See the standalone deployment instructions.

## Real-model experiment design

Both Azure VMs have 2 vCPUs and about 8 GiB RAM. The engine is the existing
Hugging Face Qwen/Qwen3-0.6B CPU worker, with KV cache and one Torch thread.
The coordinator and controller run on vm2; the second worker runs on vm3.
The measured profile has per-layer costs 128:6.567, 512:7.662, 1024:9.071,
2048:12.681 ms, embedding .071 ms, head 50.49 ms, fixed transition 1740 ms,
and replay .3667 ms/token/layer. The default gate horizon/margin are 30 s/.13.

Two matrices run sequentially to avoid competing controllers:

| Matrix | Conditions | Planned runs |
|---|---|---:|
| `raw/objective/` | latency/throughput × concurrency 1/2 × stable (3 repeats) or network +120 ms on vm3 (2 repeats) | 20 |
| `raw/demand/` | fixed throughput/auto with fixed horizon/auto with live remaining horizon × concurrency 1/2 × stable (2 repeats) | 12 |

Run order is shuffled deterministically: seeds 20261004 and 20261014.
Each run admits closed-loop requests for 10 s before, 40 s during and 10 s after
the selected condition, then includes completion through drain in the whole-run
throughput analysis. Stable runs have no fault. Prompt length is 64 tokens;
output limits are 32 for the objective matrix and 64 for the demand matrix.
One warm-up request precedes measurement. Demand runs additionally compare an
eight-token greedy output for a fixed input against the shared reference.
Do not pool the matrices' different output-length workloads.

The alternate controllers and test sources are installed in separate remote
directories. Existing worker processes are reused; the original controller
binary/source are preserved. Each matrix clears the injected network fault and
restores the original static single-worker coordinator in its cleanup.

## Results and analysis

Both matrices completed: **32 runs, 240 measured requests, zero failed
requests**, with all 12 demand-run greedy checks matching the shared reference.
All 179 source raw files and both tested source archives passed hash checks.
The original static coordinator was restored and the vm3 network fault cleared.

Collected artifacts:

- [Measured report and run-level plots](analysis/REPORT.md).
- [Per-run metrics](analysis/per-run.csv).
- [Grouped descriptive metrics](analysis/summary.csv).
- [Matched-repeat comparisons](analysis/paired-comparisons.json).
- [Completion status and failure counts](analysis/status.json).
- [Excluded observations](analysis/excluded.json).
- Raw `requests.csv`, `series.csv`, `faults.csv`, `decisions.json`, `meta.json`
  and demand-matrix `correctness.json` inside each run directory.

The status file distinguishes completed runs from planned runs. The measured
report is generated from the exported runs. Copied raw artifacts are verified
against source hashes in [transfer-validation.json](transfer-validation.json);
tested source snapshots and VM test logs are in `provenance/`.

Metrics include successful output tokens divided by the whole window including
drain, client-observed completion time, internal router TTFT, executed/rejected
voluntary moves, reported gate horizons, and live workload snapshots. Reported
group medians aggregate per-run observations rather than treating every request
or telemetry tick as an independent trial.

## Validation and limitations

Go tests check additive DP against exhaustive three-worker layouts, objective
tradeoffs, objective-consistent gate accounting, remaining-work rejection,
recovery bypass, stale workload rejection, auto-objective selection and
controller reset behavior. Race checks cover the partition and controller.
Four Python tests on vm3 check concurrent budget accounting and router cleanup
and replay semantics.

This is an exploratory small-repeat experiment on two CPU cloud VMs. The output
budget is the unproduced portion of admitted requests; future arrivals are
unknown. It is a horizon proxy, not a makespan guarantee. Prefill/queue effects,
runtime batching, capacity constraints and predictive uncertainty are not fully
modeled. Automatic mode can retain a layout when the improvement threshold or
gate rejects switching. The worker still needs transient memory for the full
model; no pooled-memory loading claim is made. Synthetic prompt IDs measure
execution, not semantic chat quality. Router TTFT is not streamed client TTFT.

The new real-model matrices are separate from the earlier 710 analytical replay
rows in `results/azure-vm-2026-10-04/`. No paper novelty or universal performance
advantage follows solely from passing these tests.

## Reproduce

Local checks:

```bash
go test -race ./internal/partition ./internal/controller
go test ./cmd/controller ./cmd/gate-replay
python3 -m unittest discover -s worker -p 'test_*workload.py'
python3 bench/analyze_objectives.py results/objective-aware-2026-10-04
python3 bench/report_objectives.py results/objective-aware-2026-10-04
python3 bench/verify_objective_export.py results/objective-aware-2026-10-04
python3 scripts/index-results.py
```

Python router tests need the worker environment's gRPC dependencies.
`bench/objective_matrix.py` documents the Azure coordinator run commands and
cleanup; it requires the existing SSH worker alias and prepared engine/agents.
`bench/run-demand-after-objective.sh` serializes the two controlled matrices.
