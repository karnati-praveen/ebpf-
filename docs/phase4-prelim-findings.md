# Phase 4 (preliminary) — measured cost model, Qwen3-0.6B on Azure CPU

Source: single-process spike on one Azure VM. Raw data `docs/per-layer-cost.csv`,
machine `docs/machine_info.json`.

Machine: 4 vCPU Intel Xeon Platinum 8272CL @2.6GHz, torch 2.14.0+cpu,
torch_threads=2, FP32. Model: Qwen3-0.6B, 28 layers, hidden 1024, vocab 151936,
tied embeddings (verified), 8 KV heads, head_dim 128.

**Scope.** Single-process, one machine. No network, no serialization, no pipeline
effects. These parameterise the cost model; they are not end-to-end results.

## Measured values (medians)

| ctx | decode ms/layer (0–26) | layer_27 | lm_head ms/tok | decode total ms/tok | prefill ms/tok/layer |
|---|---|---|---|---|---|
| 128 | 5.55 | 5.89 | 37.63 | 195.6 | 0.2624 |
| 512 | 6.25 | 11.53 | 37.23 | 219.2 | 0.2088 |
| 1024 | 7.18 | 13.41 | 36.87 | 245.1 | 0.1912 |
| 2048 | 9.49 | 16.38 | 36.92 | 315.2 | 0.2103 |

KV cache: **8192 B/token/layer**, exactly `2 × 8 heads × 128 dim × 4 B`. Measured
matches theory, so the instrumentation is trustworthy. 224 KB/token across all 28
layers; 448 MB at 2048 tokens.

## Finding 1 — endpoint cost is 2–3× the hysteresis gate, and the DP ignores it

`lm_head` costs ~37 ms/token and is **constant in context** — it is an endpoint
module on the last stage, not a per-layer cost. Adding the `layer_27` excess
(plausibly final norm) gives a total endpoint cost of 38–44 ms/token.

| ctx | endpoint | 14-layer stage | endpoint / stage |
|---|---|---|---|
| 128 | 38.0 ms | 77.7 ms | **48.9%** |
| 512 | 42.5 ms | 87.5 ms | **48.6%** |
| 1024 | 43.1 ms | 100.5 ms | **42.9%** |
| 2048 | 43.8 ms | 132.9 ms | **33.0%** |

`internal/partition/partition.go` models stage cost as `layers × PerLayerMs / speed`
plus a hop. There is no endpoint term. Consequence — the DP picks an even split
when the true optimum is skewed away from the last stage:

| ctx | DP picks | bottleneck | true optimum | bottleneck | cost of mis-split |
|---|---|---|---|---|---|
| 128 | 14/14 | 115.7 ms | 17/11 | 99.0 ms | **14.4%** |
| 512 | 14/14 | 130.0 ms | 17/11 | 111.3 ms | **14.4%** |
| 1024 | 14/14 | 143.6 ms | 17/11 | 122.1 ms | **15.0%** |
| 2048 | 14/14 | 176.7 ms | 16/12 | 157.7 ms | **10.7%** |

The error is at or near the controller's own 15% improvement threshold, so it is
not a rounding detail — it is a systematic mis-partition on every run to date.

## Finding 2 — per-layer decode cost is context-dependent

5.55 → 9.49 ms/layer from ctx 128 to 2048, **+71%**. `Input.PerLayerMs` is a
scalar constant. The cost model needs a context term; a single profiled value will
mis-predict by up to 71% across the working range.

## Finding 3 — Phase 1 Finding B resolved: the network arm has signal

Phase 1 swept per-layer costs of 3 / 10 / 30 ms and found the 80 ms netem fault
yields 32.0% / 18.2% / 6.0% predicted benefit. Measured cost is **5.5–9.5 ms**,
inside the 3–10 band, so 80 ms netem gives roughly 20–32% predicted benefit —
**above the 15% gate.** The network scenario is viable at this model size. The
feared null-by-gate-calibration does not occur.

## Finding 4 — KV reconstruction cost, and a measured crossover

Reconstruction = re-prefill C tokens through the moved layers:

| ctx | move 14 layers |
|---|---|
| 128 | 0.47 s |
| 512 | 1.50 s |
| 1024 | 2.74 s |
| 2048 | **6.03 s** |

Against a 30 s horizon, assuming a 20% per-token improvement from repartitioning:

| ctx | reconstruction | tokens in 30 s | benefit | payback | verdict |
|---|---|---|---|---|---|
| 128 | 0.47 s | 153 | 6.00 s | 12 tok | **pays** |
| 512 | 1.50 s | 137 | 6.00 s | 34 tok | **pays** |
| 1024 | 2.74 s | 122 | 6.00 s | 56 tok | **pays** |
| 2048 | 6.03 s | 95 | 6.00 s | 96 tok | **does not pay** |

**This is the study's question answered with measurements: repartitioning pays at
short context and stops paying near 2048 tokens**, because reconstruction cost
grows with context while the per-token benefit does not grow fast enough to keep
up within a fixed horizon. A simulator with sampled compute and bandwidth cannot
produce this curve, because the crossover is set by the ratio of real prefill
throughput to real decode throughput on real silicon.

## Caveats — do not overstate

- The 20% improvement figure is a **placeholder**, not measured. The crossover
  point moves with it. Re-run once real improvement is measured end-to-end.
- Single-process, single-machine. No network, serialization or pipeline effects.
- `layer_27` is anomalous: +0.3 ms excess at ctx 128 but +5.3 to +6.9 ms at
  ctx ≥ 512. Attributing all of it to endpoint cost may over-attribute at short
  context. Needs isolation before publication.
- Prefill `lm_head` reaches 2473 ms at ctx 2048 (~17% of prefill), which implies
  logits are computed over **all** positions. Real systems compute only the last.
  This inflates measured prefill and means reconstruction cost should **exclude**
  `lm_head` — fixing it will lower the reconstruction numbers above.

## Consequences for the plan

1. Add endpoint (`embed`, `lm_head`, final-norm) terms to `partition.Input` and
   `stageCost`. Currently absent; magnitude ~15%.
2. Make `PerLayerMs` context-dependent.
3. Re-run `cmd/dpsweep` with measured values once (1) and (2) land.
4. The crossover is the headline candidate. It needs the real improvement figure
   and the `lm_head` prefill fix before it can be claimed.
