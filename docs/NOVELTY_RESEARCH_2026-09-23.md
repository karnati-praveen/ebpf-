# Novelty research update — 2026-09-23

This memo checks the current novelty position against primary papers and the
implemented system. It is a research update, not a claim that the Phase 6
experiments have run. The project state is in `docs/HANDOFF.md`; the original
assessment is `docs/NOVELTY_ASSESSMENT.md`.

## Decision in one paragraph

The strongest defensible paper is a **measured decision boundary for live,
stateful, whole-layer repartitioning**: under what context lengths, fault
durations, and workloads does a move deliver more useful tokens than staying
put, after weight reload and full-chain KV replay? The controller and a
`gate-force` comparison arm already exist. The boundary is currently **predicted
from component measurements**, not observed in paired distributed runs. The
first priority is to measure and validate it. An algorithmic extension could
account for uncertainty in fault duration and transition cost, but it earns a
novelty claim only if implemented and compared with the existing gate.

## Corrections to the current novelty assessment

| Current wording or implication | Evidence and correction |
|---|---|
| “Measuring it on real machines” is new. | Too broad. [EdgeShard](https://arxiv.org/html/2405.14371v1) evaluated layer placement on a heterogeneous physical prototype. [Llumnix](https://www.usenix.org/conference/osdi24/presentation/sun-biao) and [ServerlessLLM](https://www.usenix.org/conference/osdi24/presentation/fu) implemented live request migration. The narrower candidate is a measured **break-even boundary for mid-request whole-layer redistribution on constrained nodes**, with all transition costs counted. That candidate still needs a wider literature search before any “first” claim. |
| Transfer versus recomputation might be open after CacheGen. | The broad idea is already covered. [CacheGen](https://arxiv.org/abs/2310.07240) can fall back to text and recompute when bandwidth is low; [ServerlessLLM](https://www.usenix.org/system/files/osdi24-fu.pdf) sends tokens and recomputes KV state during live inference migration; [EdgeFlow (ICDCS 2026)](https://ieeexplore.ieee.org/document/11619197/) explicitly combines KV transfer and activation-based recomputation on a real edge platform. Do not frame a simple transfer/recompute selector as novel. |
| The closest paper is only arXiv:2505.02533. | [Kafetzis et al.](https://arxiv.org/html/2505.02533v1) is closest for online partitioning with migration cost, but models a **single decoder layer**, head-level movement, and simulated resources. [BanaServe](https://arxiv.org/abs/2510.13223) migrates layer weights and KV state dynamically in disaggregated serving. [EdgeFlow](https://ieeexplore.ieee.org/document/11619197/) is the closest edge-state-migration result found here. All belong in related work. |
| The `gate-force` arm observes what rejected moves would have done. | It executes rejected moves in separate matched runs. This is a **paired experimental proxy**, not the unobservable exact counterfactual of the same run: queueing, fault duration, and request arrivals can diverge. Preserve the pairing and report run-to-run variation. |
| The 77.9 s break-even value is a measured crossover. | It is a **model prediction** using measured cost components in `internal/partition/decider_test.go`. The distributed crossover and calibration error have not been measured. `docs/phase4-partb-findings.md` also warns that its older 26.4 s estimate omitted full-chain replay and reload. |
| eBPF sRTT reveals server compute in RTT. | This is a plausible explanation for a local observation, not established causality. Verify with packet-level timing, controlled server delay, and independent link delay before making a systems claim. |

The phrase “EdgeShard never reconfigures” should be presented as a description
of its **reported method and experiments**, not a claim about every possible
implementation. Its [method](https://arxiv.org/html/2405.14371v1) takes
profiled traces and computes placement; I found no reported live migration
protocol or cost measurement in that paper. The paper uses “adaptive” for
placement under differing conditions, so simply saying EdgeShard is “static”
without this qualification is likely to mislead.

## Prior-work map

| Work | What the primary source establishes | Boundary for this project |
|---|---|---|
| [EdgeShard, 2024/2025](https://arxiv.org/html/2405.14371v1) | Layer placement via DP; Llama 2 evaluation on physical heterogeneous devices. | Real edge hardware and DP are established. Live move economics are not the result it reports. |
| [Ong, 2024 technical report](https://www2.eecs.berkeley.edu/Pubs/TechRpts/2024/EECS-2024-108.html) | A working inference engine switches partitioning strategies at inference time on L4/A100 GPUs. | “Dynamic partitioning on real GPUs” is also too broad. Its strategy switching differs from moving a contiguous layer boundary mid-request. |
| [Kafetzis et al., 2025](https://arxiv.org/html/2505.02533v1) | Online head/block placement; migration cost includes KV bytes over link bandwidth; resource values sampled for numerical experiments; future work names real testbeds and multilayer models. | The project's edge is real multilayer behavior and measured transition cost, not migration awareness itself. |
| [SpotServe, ASPLOS 2024](https://arxiv.org/abs/2311.15566) | Dynamically changes LLM parallelization as preemptible instances and workloads change; optimizes migration plans and stateful recovery. | Dynamic reparallelization with migration cost is established; its cloud preemption objective differs from this project’s fault-duration break-even question. |
| [Llumnix, OSDI 2024](https://www.usenix.org/conference/osdi24/presentation/sun-biao) | Live migration of requests and their in-memory state between model instances. | Migration and rescheduling are established in datacenter serving; layer redistribution is a different unit of action. |
| [ServerlessLLM, OSDI 2024](https://www.usenix.org/system/files/osdi24-fu.pdf) | Live inference migration by sending tokens and recomputing KV state; checkpoint-aware scheduling. | KV reconstruction for migration is prior art; compare transition accounting and hardware regime. |
| [CacheGen, SIGCOMM 2024](https://arxiv.org/abs/2310.07240) | KV compression/streaming; low-bandwidth fallback to recomputation. | A binary transfer/recompute choice alone is not enough. |
| [BanaServe, 2025/2026](https://arxiv.org/abs/2510.13223) | Dynamic layer-weight and KV migration for disaggregated serving. | Do not claim first dynamic layer migration. Distinguish architecture and decision objective. |
| [EdgeFlow, ICDCS 2026](https://ieeexplore.ieee.org/document/11619197/) | Hybrid direct transfer and activation-based recomputation for KV migration in collaborative edge inference, evaluated on a real platform. | It closes a broad “edge transfer versus recompute” novelty claim. Its exact comparison with moving layer boundaries needs the full paper, if available. |

The survey is focused, not exhaustive. In particular, the full EdgeFlow paper
was not accessible from the publisher page during this pass; the row above is
supported by the publisher abstract. Do not convert a missing feature in an
abstract into an absence claim about the paper.

## Most promising research questions

### 1. Measure the break-even surface (priority: immediate)

**Question.** For a healthy but degraded worker, how long must the degradation
last before moving the layer boundary pays, at context `C`, concurrency `Q`,
and fault magnitude `F`? Measure both the duration needed and the sign of the
net benefit. Include predicted-no-benefit points deliberately.

**Why this is useful.** The implemented router replays the entire chain after
relayout, and a move reloads weights. The current gate uses
`T = fixed_reload + C × per_token_per_layer_prefill × total_layers`
(`internal/partition/partition.go`). That is more realistic for this runtime
than pricing only the moved layers. It may reveal a broad region where the
throughput-optimal split is *not* the best action because the fault ends first.

**Minimum experiment.** On two or three real machines, use the same workload
and injected fault schedule in counterbalanced runs for `static`, `none`,
`hysteresis`, `gate`, and `gate-force`. Sweep context (at least 128, 512, 2048),
fault duration on both sides of each predicted break-even, fault severity,
and concurrency (1, 2, 4 where memory allows). For each run record actual
transition start/end, weight reload, replay, blocked requests, completed
tokens, TTFT, ITL, and post-fault recovery. Compare integrated completed-token
count over the **whole fault plus recovery window**, not a steady-state rate
sample. Keep a feasible single-device baseline. Predefine the effect threshold
and use the paired decision rules already in `docs/RESEARCH_PLAN.md`.

**Claim gate.** The contribution is strong if an observed crossover exists,
its location tracks the predicted boundary within stated uncertainty, and
`gate` improves net useful work or SLOs over plain hysteresis on marginal
cases. If adaptation never pays at this scale, report the measured region and
why; do not claim a universal no-benefit result.

### 2. Calibrate the *decision*, then extend it for uncertainty (priority: next)

The current `GateParams` has one fixed `HorizonS` and `SafetyMargin`; it does
not estimate how long a fault will persist, or give uncertainty intervals for
reload/replay cost. A stronger **candidate** mechanism is to accept a voluntary
move only when a conservative estimate of useful work with the move exceeds
staying put over the predicted remaining fault duration. For instance, estimate
the distribution of transition time `T` and remaining fault life `D`, then
compare `E[max(D-T,0) × r_new]` with `E[D × r_old]`, with a calibrated risk
margin. This equation is a design proposal, not implemented or novel by
itself. It must account for prefill and decode load, queueing, and changes
after the fault ends; otherwise it could optimize the wrong window.

First measure **decision-level calibration** of the existing gate: predicted
versus observed transition cost, predicted versus observed throughput gain,
fraction of accepted moves that actually repay cost, and fraction of rejected
moves that would have repaid it in paired `gate-force` runs. Use held-out fault
traces. If the fixed gate already has few decision errors, an uncertainty model
is unlikely to justify its implementation. If errors cluster around short
faults or noisy telemetry, implement the smallest duration/uncertainty model
that targets those errors, then compare against fixed-horizon gate, hysteresis,
and an offline oracle. Never use the oracle as an online baseline.

### 3. Test what eBPF adds to a decision (priority: conditional)

The observed loopback sRTT versus application transport discrepancy is a
measurement hypothesis. Establish whether sRTT includes delayed/piggybacked
ACK time by varying server compute while holding network delay constant, then
varying `tc netem` delay while holding compute constant. Capture request,
response, and ACK timestamps at both endpoints. Finally compare the decisions
and completed-token outcomes of application-only, eBPF-only, and combined
telemetry arms. A sensor can be inaccurate as a pure RTT estimator yet useful
as a congestion signal; evaluate its effect on decisions rather than just
correlation. A credible null result is possible, but it should not be marketed
as a kernel telemetry improvement.

## What would strengthen or weaken the paper

1. **Run Phase 6 before building another mechanism.** A clean empirical
   crossover is the fastest route to a paper. The current 77.9 s point tells
   where to center the first duration sweep, but it cannot substitute for it.
2. **Keep scope in the title.** CPU Azure VMs test controlled compute and
   network faults. They do not demonstrate consumer-device thermals, Wi-Fi,
   or physical heterogeneity. Add laptop/edge GPU runs before using those
   claims, or call the VM paper “resource-constrained distributed inference.”
3. **Include a larger model or explicit scale argument if feasible.** Qwen3-0.6B
   on two CPU VMs may make the transition-to-benefit ratio unusual. Report
   bytes moved, cache size, bandwidth, replay time, and normalized ratios so
   readers can judge transfer to other regimes. Do not extrapolate a measured
   crossover beyond tested models and hardware without validation.
4. **Treat transition cost as a distribution.** Report median and tails, peak
   memory during relayout, requests interrupted, and repeatability. The
   current cost formula assumes a single deterministic downtime and may fail
   under concurrent requests or cache pressure.
5. **Do not call `gate-force` a perfect counterfactual.** Match trace, fault,
   and random seeds; compare paired runs; report how much they diverged.

## Suggested paper claim, conditional on data

> We characterize the net benefit of live contiguous-layer repartitioning in
> stateful distributed LLM inference. Measurements on [actual hardware] show
> how context, fault duration, and workload shift the break-even boundary once
> weight reload and full-chain KV replay are counted. A transition-aware
> controller [observed outcome] relative to matched static and hysteresis
> baselines.

Fill every bracket only from Phase 6 data. Avoid “first,” a numeric novelty
score, and venue predictions until the comparison and results are complete.

## Immediate research checklist

- Read the full EdgeFlow paper and the migration sections of SpotServe,
  Llumnix, and BanaServe; record exact state moved, source/destination model
  placement, measured transition time, and decision rule.
- Audit the Phase 6 harness for the complete fault-plus-recovery window and
  per-transition timestamps; test one paired marginal case around 77.9 s.
- Freeze pilot-derived SESOI and H3 threshold before confirmatory runs.
- Update `docs/NOVELTY_AND_ABLATIONS.md` and the paper introduction after the
  observed crossover, including negative or inconclusive outcomes.
