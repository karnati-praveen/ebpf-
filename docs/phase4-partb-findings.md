# Phase 4 (Part B) — measured reconstruction cost and single-device baseline

Raw data: `docs/data/azure-d4-2026-09/` (kv-reconstruction.csv, single-device-baseline.csv,
per-layer-cost.csv, machine_info.json, run_meta.json).
Machine: Azure 4-vCPU Xeon Platinum 8272CL, torch 2.14.0+cpu, `torch_threads=2`,
FP32, Qwen3-0.6B. Single process, one machine.

## 1. The derived reconstruction cost was right

Phase 4's preliminary numbers were derived from prefill per-layer cost rather than
measured end to end. Direct measurement confirms them:

| ctx | measured (14 layers) | derived | error |
|---|---|---|---|
| 128 | 448 ms | 470 ms | +4.8% |
| 512 | 1410 ms | 1497 ms | +6.2% |
| 1024 | 2738 ms | 2741 ms | +0.1% |
| 2048 | 5804 ms | 6030 ms | +3.9% |

Reconstruction scales close to linearly in **both** layers and context — 1.86–1.90×
for double the layers, 3.67–3.79× for quadruple — so `recon ≈ k · L · C` is an
adequate model, slightly sublinear from fixed overhead.

## 2. Break-even horizon — the result to report

A binary "does it pay at 30 s" hides the structure. The useful quantity is **how
long conditions must hold for a move to repay its reconstruction cost**:

    break-even = reconstruction × adapt_ms / (stay_ms − adapt_ms)

Using measured reconstruction and the endpoint-corrected DP predictions:

| fault | ctx | stay | adapt | gain/token | reconstruction | **break-even** |
|---|---|---|---|---|---|---|
| network 80 ms | 128 | 179.3 ms | 140.4 ms | 38.9 ms | 0.45 s | **1.6 s** |
| network 80 ms | 512 | 186.3 ms | 150.1 ms | 36.2 ms | 1.41 s | **5.8 s** |
| network 80 ms | 1024 | 202.8 ms | 165.2 ms | 37.6 ms | 2.74 s | **12.0 s** |
| network 80 ms | 2048 | 237.7 ms | 199.4 ms | 38.3 ms | 5.80 s | **30.2 s** |
| thermal 0.7× | 128 | 142.4 ms | 118.6 ms | 23.8 ms | 0.45 s | **2.2 s** |
| thermal 0.7× | 512 | 152.4 ms | 131.3 ms | 21.0 ms | 1.41 s | **8.8 s** |
| thermal 0.7× | 1024 | 175.9 ms | 145.1 ms | 30.8 ms | 2.74 s | **12.9 s** |
| thermal 0.7× | 2048 | 225.8 ms | 185.1 ms | 40.7 ms | 5.80 s | **26.4 s** |

The break-even horizon grows roughly linearly with context — from under 2 s at 128
tokens to 26–30 s at 2048 — because reconstruction grows with context while the
per-token gain does not. Against a 30 s planning horizon the network case lands at
30.2 s: **exactly break-even, by construction of nothing.** That is a far more
informative statement than a pass/fail, and it is the shape the paper should report.

**This is still a prediction.** `stay` and `adapt` come from the DP's cost model,
not from measured end-to-end runs. Phase 0 puts that model's error at a median
−2.2% to −7.9% with ~13% IQR, which at ctx 2048 is comparable to the margin. The
curve's *shape* is robust; its crossing point is not yet measured.

## 3. Single-device baseline — throughput saturates at 1.19×, then degrades

| concurrency | aggregate tok/s | speedup | ITL | TTFT | peak RSS |
|---|---|---|---|---|---|
| 1 | 4.39 | 1.00× | 213 ms | 4.0 s | 4.53 GB |
| 2 | 5.05 | 1.15× | 368 ms | 7.0 s | 4.53 GB |
| 4 | **5.22** | **1.19×** | 711 ms | 14.5 s | 4.64 GB |
| 8 | 4.45 | 1.01× | 1691 ms | 28.9 s | 6.70 GB |

Three consequences:

**The concurrency sweep should be 1/2/4, not 1/2/3/8.** Beyond 4 on a 4-vCPU box
throughput *falls* and RSS jumps 4.64 → 6.70 GB. Concurrency 8 measures memory
pressure and scheduler contention, not pipeline behaviour. The plan's 1/2/3/8 sweep
would have spent a quarter of its runs on an artefact.

**8 GB VMs are not viable** at concurrency 8 — 6.70 GB before counting a second
process. Confirms the 16 GB sizing.

**There is real headroom for H1.** A single device saturates at 5.22 tok/s and
cannot use more concurrency. A 2-stage pipeline is bottleneck-limited rather than
device-limited, so distributing has somewhere to go — but only at concurrency ≥ 2,
since TTFT scales linearly (4.0 → 28.9 s), showing requests queue rather than
overlap on one device.

## 4. What this changes

- Report the **break-even horizon curve**, not a binary verdict.
- Concurrency sweep: **1/2/4**.
- The 2048 network case is the marginal one and should be presented as such.
- Horizon sensitivity (plan §5) is now clearly load-bearing: at ctx 2048 the
  verdict flips between a 26 s and a 31 s horizon.

## 5. Still outstanding

- `lm_head`-over-all-prefill-positions unresolved. Reconstruction here is pure
  layer prefill and already excludes it, so these numbers are unaffected — but
  measured *prefill* totals in `per-layer-cost.csv` remain inflated.
- Thread-scaling unmeasured; `torch_threads=2` on 4 vCPU means every cost number
  here is for that specific configuration.
- `stay`/`adapt` are model predictions, not end-to-end measurements.
