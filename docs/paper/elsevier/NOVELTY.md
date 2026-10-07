# Novelty and contribution audit

The strongest defensible story is **objective-dependent performance and the
limits of finite-work adaptation in a small standalone runtime**. This focused
primary-source comparison, checked on 4 October 2026, is not an exhaustive
systematic review or proof that no other paper has the same combination.

| Proposed contribution | Evidence | Safe claim and boundary |
|---|---|---|
| Runtime with objective selection and live remaining-work input | Standalone code, tested snapshots, 32 later CPU trials | We implement and evaluate this combination. Firstness and integration novelty remain provisional. |
| Objective-dependent operating regions | Stable/network Q=1/2 live matrix | Characterize the observed reversal across load/network conditions. The latency/throughput distinction is established. |
| Adaptation accounting and negative finite-work result | 30 fault runs, 12 demand runs, gate logs | Quantify startup/transition penalties and unestablished benefit. Remaining-work gating has no demonstrated speedup here. |
| Measurement and forecast diagnostics | Synthetic queue/calibration windows, cost sweep, recorded-candidate replay | Diagnose this implementation's contaminated residuals and underestimated transitions. The diagnostic techniques themselves are established. |

The current contribution is principally **empirical characterization and
inspectable system integration**, rather than a proven new optimizer.

## Primary literature comparison

| Source | Overlap | Consequence for writing |
|---|---|---|
| [EdgeShard, 2405.14371](https://arxiv.org/html/2405.14371v1) | Separate latency/throughput optimization using DP | Credit the objective distinction. Ordered workers and empty assignments narrow our implementation; they do not establish algorithmic novelty. |
| [Kafetzis et al., 2505.02533](https://arxiv.org/html/2505.02533v1) | Online partitioning with migration and inference delays; attention-head/KV placement | No first migration-aware edge-partitioning claim. Explain our layer-level/full-replay scope without claiming superiority. |
| [Petals, 2312.08361](https://arxiv.org/abs/2312.08361) | Heterogeneity, changing participation, reliable distributed inference | Worker-loss recovery and uneven devices are established concerns. Two small VMs do not match its scale/capacity validation. |
| [Llumnix, OSDI 2024](https://www.usenix.org/system/files/osdi24-sun-biao.pdf) | Runtime request/state migration | Distinguish layer relayout from request migration; no first stateful rescheduling claim. |
| [ServerlessLLM, OSDI 2024](https://www.usenix.org/system/files/osdi24-fu.pdf) | Live inference migration and startup-sensitive placement | Loading penalties and migration are established. No reproduced performance comparison exists. |
| [SpotServe, 2311.15566](https://arxiv.org/abs/2311.15566) | Dynamic parallelization, migration communication, preemption recovery | No first fault-tolerant reconfiguration claim. Our exact budget experiment is a narrower candidate distinction. |
| [Parallax, 2509.26182](https://arxiv.org/abs/2509.26182) | Decentralized allocation and routing | Standalone deployment is insufficient novelty alone. Consumer positioning needs consumer measurements. |
| [ATSInfer, 2607.10183v2](https://arxiv.org/html/2607.10183v2) | Consumer CPU/GPU placement; load-aware transfer; threshold/minimum-interval rescheduling | Adaptation suppression already has close precedent, including a reported 15% deviation threshold. Our setting is cross-VM with full-chain replay. |
| [EdgeFlow KV migration, ICDCS 2026](https://ieeexplore.ieee.org/document/11619197/) | KV transmission plus activation-based recomputation in collaborative edge inference | Do not claim the transfer/recompute choice as new. Publisher abstract/DOI checked; full text and complete author metadata still need review. |
| [ETCInfer, 2609.15230](https://arxiv.org/abs/2609.15230) | Thermal/cooling-aware inference scheduling | Our simulated-temperature report is not physical thermal validation. |

The KV-migration EdgeFlow differs from mobile cold-start and earlier DAG-inference
papers sharing its name. Use title and DOI `10.1109/2575-8411.2026.00033` when
expanding that citation. Do not substitute an unrelated EdgeFlow paper.

Twelve checked primary-paper records are in `references.bib`. arXiv DOIs identify
preprints, not final publisher DOIs. ATSInfer and ETCInfer are marked preprints.
Full text was inspected for the closest objective/partitioning and consumer
rescheduling overlaps; abstract-level evidence restricts finer absence claims
for other systems. Extend the submission review through references/citations
and published versions. No prior system was reproduced in these experiments.

## Claim language

Use: "We implement an optional remaining-work horizon and characterize its
behavior in a small standalone deployment." Use: "In this matrix, throughput
placement increases the ratio of stable Q=2 run medians by 80.5%." Use:
"The live remaining-work experiment does not establish a benefit."

Avoid: "first eBPF-driven inference orchestrator," "novel DP," "optimal
finite-work scheduler," "guaranteed migration benefit," "thermal-aware consumer
validation," "production-ready Kubernetes replacement," or "outperforms prior
systems." Neither literature nor the current measurements supports these claims.

## Stronger research direction

Connect **finite-work completion cost** to measured reconfiguration, queueing,
and pipeline overlap, then compare against matched-start fixed-horizon and
no-adaptation controls. The current `remaining_tokens × current_objective_cost`
horizon is a heuristic surrogate, not a concurrent-request makespan predictor
or future-arrival forecast. This limitation offers a research question.

Collect explicit transition IDs, per-request progress, admission timestamps,
streaming token times, and independent calibration. State workload assumptions
and choose finite completion cost or an explicit SLO as the objective. Freeze
a predictor/policy using pilots and assess prediction error and real serving
outcomes on held-out matched trials. Negative results remain useful evidence;
favorable replay counts cannot replace measured outcomes.

## Added primary comparisons

- [TPI-LLM](https://arxiv.org/html/2410.00531v1): tensor parallelism, memory scheduling, and consumer-device evidence for larger models. Stronger capacity evidence than this prototype.
- [MDI-LLM](https://arxiv.org/html/2505.18164v1): recurrent pipeline and per-sequence KV state; physical Jetson evidence with NanoLlama and TinyLlama. Its memory-limited model demonstration is outside our evidence.
- [Galaxy](https://arxiv.org/abs/2405.17245): heterogeneity-aware hybrid parallelism and communication overlap; broader parallelization than our stage proxy.

The new propositions formalize established optimization/amortization principles;
they are not claimed as original theorems. The concrete added empirical finding
is that an active-cohort budget can suppress a move before closed-loop admission
replenishes demand, interacting with cooldown and initial placement. It is an
observed mechanism, not an isolated causal treatment effect or a global ranking.
