# Paper ablation artifacts — 4 October 2026

Companions: [study report](../../PAPER_ABLATION_STUDY_2026-10-04.md) and
[working manuscript](../../paper/kubeedgeinfer-draft.md).

## Evidence boundary

There are two new evidence strata. `decision-results/` contains **deterministic
decisions and model-derived quantities**, not measured inference outcomes.
`queue-results/` contains **measured instrumented worker RPCs with synthetic
sleep-based compute on loopback**, not real-model or multi-machine inference.
Historical real-model component measurements are in
[azure-d4-2026-09](../azure-d4-2026-09/); they were not rerun here.

The studies are exploratory. A short smoke run validated instrumentation and
cleanup before the main queue matrix. Smoke observations are excluded from the
recorded study. No preregistration, confirmatory test, real hardware procurement,
upstream-system reproduction or kernel telemetry experiment was performed.

## Decision-only experiment

The reproduction calls `partition.Optimal`, `partition.Evaluate` and
`partition.Decider` from the production Go package. It does not rewrite their
algorithms in Python. The 2×2 cost ablation independently enables endpoint terms
and context dependence; all placements are scored under the same full reference.

Parameters:

| Parameter | Value / source |
|---|---|
| Layers / ordered workers | 28 / 2; zero-layer assignments permitted |
| Context / per-layer ms | 128:5.55, 512:6.25, 1024:7.18, 2048:9.49; approximate medians from historical CPU profiles |
| Embedding / endpoint ms | .09 / 43.8; fixed measured-component approximation used by earlier committed sweeps |
| Frozen context arm | Scalar 5.55 ms/layer at every context |
| Worker-B speed | 1, .93, .8, .7, .5; hypothetical speed multipliers |
| Incoming hop | .5, 10, 80 ms; sensitivity settings, not new network measurements |
| Initial condition | Same context, both speeds 1, hop .5 ms, full model |
| Horizons / safety margins | 10,30,60,120,240,600 seconds / 0,.13 |
| Improvement / cooldown | .15 / zero; cooldown held off to isolate other effects |
| Fixed transition / replay coefficient | 2000 ms / .21 ms per token-layer; approximate component parameters |

Cost-model grid: 4 contexts × 5 speeds × 3 hops × 4 model variants = **240 rows**.
Policy grid: 60 cases × 6 horizons × 2 margins × 5 transition variants × 5
policies = **18,000 rows**. These row counts are not numbers of independent
experimental trials.

Transition variants retain full-chain replay, price ownership-changing layers
only, omit replay, omit fixed cost, or omit both. The moved-layer count is
derived from the baseline/candidate ownership, not fixed at 14. Changing an
estimate does not implement a new state-transfer strategy.

`reference_regret_frac` is the chosen placement's reference-model bottleneck
divided by the reference optimum minus one. It has a different denominator from
the earlier memo's relative reduction from the worse placement. Full-reference
zero regret is true by construction; it does not validate hardware predictions.

`margin_acceptance_boundary_s` prices the selected transition variant and gate
inequality only. The 15% improvement threshold still applies, and a context-512,
speed-.7 candidate is ineligible despite a finite inequality boundary. Infinity
is serialized as `+Inf` in CSV. `predicted_tokens_adapt_full_chain` scores the
candidate with the common full-chain estimate regardless of the selected
policy's estimate or action; it is an analytical counterfactual, not observed
tokens. Stable cases retain their initial placement.

## Queueing experiment

The scratch script imports the existing `WorkerServicer` and preserves its
Forward implementation and compute timer. A lock wrapper measures only
compute-lock acquisition, returning the duration in gRPC trailing metadata.
No production file or protobuf schema changes. Both admission arms use identical
instrumentation, with at most four clients and a 16-thread server pool.

Service sleeps: 5/20/50 ms on one assigned synthetic layer. Each RPC carries one
input ID and produces one fake token. These are RPC service costs, not true
model decode/prefill or semantic correctness. Three separate worker processes
provide the three durations; a condition uses one and leaves the others idle.
The controller, router, node-agent and eBPF are not involved.

Conditions: service duration × concurrency 1/2/4 × direct versus one-at-a-time
FIFO admission × three repeats = **54 windows**. A fixed seed (20261004)
shuffles condition order within each repeat. Each window admits closed-loop
requests for 15 seconds and drains outstanding work. Setup and three warm-up
RPCs precede each window and are excluded from timing.

For each successful RPC, raw data retain RPC duration R, compute D, server lock
waiting Q, R−D, clipped max(0,R−D), corrected R−D−Q, client admission wait and
client completion. The arithmetic corresponds to the router's residual, but
the router itself is not measured in this microbenchmark. R−D−Q still includes
RPC/serialization/scheduling/instrumentation; it is not pure link propagation.
FIFO admission relocates waiting and can change worker utilization. It is not
claimed to improve end-to-end performance. Completed RPCs per second use full
observation through drain; they are not real-model generated tokens per second.

Repeated windows are analysis units. Aggregate means average each window's mean
equally; ranges span the three window means. Paired differences match the
direct/admitted arms by service, concurrency and repeat block, not by an exact
identical arrival sequence. Raw RPCs within windows are dependent; no per-RPC
pseudoreplication, significance or equivalence test is performed.

## Reproduce

From the repository root, with Go and the existing Python gRPC/NumPy/protobuf
environment. Choose fresh output paths; both drivers refuse an existing path.
The queue script requires permission to bind local sockets and stops scratch
processes in its cleanup block. No Torch or model weights are needed.

```sh
go run docs/data/paper-ablations-2026-10-04/decision_sweep.go \
  --out /tmp/kubeedgeinfer-paper-ablation/decision-results
python docs/data/paper-ablations-2026-10-04/queue_ablation.py \
  --out /tmp/kubeedgeinfer-paper-ablation/queue-results --window 15 --repeats 3
MPLCONFIGDIR=/tmp/kubeedgeinfer-paper-matplotlib \
  python docs/data/paper-ablations-2026-10-04/analyze.py /tmp/kubeedgeinfer-paper-ablation
```

Analysis additionally requires Matplotlib. A full queue matrix takes roughly
14 minutes plus setup/drain in this environment. The Go sweeps are much faster.
Metadata records configuration, source hashes, runtime packages and the fixed
condition schedule. Source hashes are provenance, not a guarantee of future
environment reproducibility.

Supplementary instrumentation calibration compares the original worker class
against the timed-lock/trailing-metadata wrapper with the same thread-pool and
server options. It uses 5/50 ms service, concurrency 1/4, instrumented/uninstrumented
arms, three repeat blocks and eight-second windows: 24 additional windows.
It is a short exploratory overhead check, not an equivalence test.

```sh
python docs/data/paper-ablations-2026-10-04/calibration.py \
  --out /tmp/kubeedgeinfer-paper-ablation/calibration-results --window 8
MPLCONFIGDIR=/tmp/kubeedgeinfer-paper-matplotlib \
  python docs/data/paper-ablations-2026-10-04/analyze.py /tmp/kubeedgeinfer-paper-ablation
```

## File map

| Artifact | Meaning |
|---|---|
| `decision_sweep.go` | Production-code decision and cost-component ablations |
| `decision-results/cost-model.csv` | 240 placements and reference scoring |
| `decision-results/cost-model-aggregate.csv` | Descriptive model-sensitivity summaries |
| `decision-results/policy.csv` | 18,000 hypothetical decisions/counterfactuals |
| `queue_ablation.py` | Instrumented scratch worker and matrix driver |
| `queue-results/metadata.json` | Runtime provenance, sources and schedule |
| `queue-results/requests.jsonl.gz` | Every recorded success/failure and timing, losslessly compressed after completion |
| `queue-results/windows.json`, `.csv` | Per-window descriptive results |
| `queue-results/aggregate.json`, `.csv` | Equal-weight window summaries and ranges |
| `queue-results/paired-descriptive.csv` | Matched-repeat residual differences |
| `analyze.py` | Reproduction of summaries and figures |
| `calibration.py`, `calibration-results/` | Original-versus-instrumented worker overhead pilot, windows and paired descriptive differences |
| `raw-data-manifest.json` | Record counts plus compressed and decoded hashes |
| `*.png`, `*.svg`, `*.pdf` | Standalone plots; PDF/SVG suitable for export |

The main matrix completed 54 windows and 66,003 RPCs; calibration completed 24
windows and 19,113 RPCs. Total: **78 windows, 85,116 RPCs, zero RPC errors**.
The calibration is not added to the main measurement's per-condition sample size.
Drivers emit uncompressed `requests.jsonl`; the saved repository artifacts were
losslessly compressed and decoded hashes checked after all runs completed.
Python's `gzip.open(path, 'rt')` can read them. Analysis uses window summaries.
Incomplete window files during a run are partial observations and final analysis
refuses incomplete matrices. This dataset is separate from the earlier
[product-direction probe](../product-direction-2026-10-04/README.md).
