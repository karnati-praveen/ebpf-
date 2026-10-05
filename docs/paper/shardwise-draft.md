# Shardwise: Measurement and Ablation of Transition-Aware Local LLM Inference

Working research draft, 4 October 2026. Author names, affiliations, venue and
submission format remain to be supplied. The present evidence supports a
prototype and pilot study. It does not establish distributed real-model
performance gains, consumer-device thermal behavior or a measured migration
crossover. Detailed new results and provenance are in the
[ablation study](../PAPER_ABLATION_STUDY_2026-10-04.md).

## Abstract

<!-- ABSTRACT_START -->
Local large language model services face changing compute availability and
communication conditions, but redistributing model layers can incur weight
loading and key-value cache reconstruction costs. We present Shardwise, a
standalone prototype that combines contiguous-layer partitioning, live telemetry,
hysteresis and an explicit transition gate. The controller compares useful-token
capacity over a planning horizon rather than accepting every improved
steady-state placement. We evaluate its measurement and decision mechanisms
through separated endpoint/context cost ablations, transition-cost sensitivity,
and a controlled worker-level queueing pilot. Decision-only experiments show
that removing endpoint or context terms changes selected placements under a
common reference model; these differences are predictions rather than measured
speedups. Across 54 instrumented loopback windows and 66,003 RPCs, a 50 ms service at
four-client concurrency produces a 150.0 ms RPC-minus-compute residual,
of which 99.2% is measured lock waiting. Thus this signal can
misattribute concurrency-induced delay to communication. Bounded FIFO admission
and direct lock-wait measurements separate this effect while retaining client
waiting in end-to-end metrics. The study provides reproducible ablations and
identifies calibration requirements for adaptive inference. Demonstrating that
repartitioning improves real distributed service, including transition downtime,
remains the next experimental step.
<!-- ABSTRACT_END -->

**Keywords:** local inference; pipeline partitioning; transition costs;
measurement validity; queueing; ablation study.

## 1. Introduction

Personal computers can host local AI services, but their available resources
change as owners run foreground applications or participating machines become
unavailable. Splitting a model across devices may provide capacity or concurrent
throughput, yet each generated token still follows the pipeline's stages.
Consequently, a placement that improves a saturated pipeline's bottleneck need
not improve the latency of a single request.

Adaptation introduces a second distinction: a better steady-state placement may
deliver less useful work over a finite interval after paying for weight loading,
control operations and lost cache state. An adaptive controller therefore needs
accurate service and transition costs, a workload objective, and a reason to
leave a working placement unchanged.

Shardwise implements this control path without requiring Kubernetes. Its
standalone source discovers workers from telemetry; a Go controller evaluates
contiguous layer assignments and pushes versioned layouts to Python workers and
a router. Kubernetes remains an optional substrate. The research question is
whether measured compute, communication and transition costs can guide useful
decisions under changing conditions. This draft addresses the preceding
measurement and ablation questions; a distributed real-model benefit evaluation
has not yet been completed.

The present contributions are:

1. An implemented, inspectable transition-aware control path with explicit
   assumptions and distinct latency and throughput predictions.
2. Separated endpoint/context and transition-component ablations using the
   production partitioner and decider, with reference-model comparisons labeled
   as analytical evidence.
3. A controlled worker-level pilot that quantifies queue contamination of an
   RPC-minus-compute signal and distinguishes worker waiting from client
   admission waiting.
4. A reproducible evaluation protocol for testing whether voluntary transitions
   repay their complete service cost on real devices.

These are implementation and measurement contributions. Contiguous-layer dynamic
programming, adaptive placement and migration-aware scheduling are established
ideas; no claim of algorithmic priority is made.

## 2. Related work

[EdgeShard](https://arxiv.org/abs/2405.14371) studies collaborative model sharding
and dynamic-programming placement for latency and throughput on a physical
prototype. Our partitioner is a classical linear-partition DP and is not
presented as a new optimization algorithm.

[Kafetzis et al.](https://arxiv.org/abs/2505.02533) describe online partitioning
at attention-head/block granularity, with migration and inference delay in the
objective. Thus neither online reassignment nor accounting for cache-related
migration costs is a new claim of this work. Our implemented action is coarser:
contiguous layer ranges with cache reconstruction through full-chain replay.

[Petals](https://arxiv.org/abs/2312.08361) addresses heterogeneous distributed
inference and unpredictable device availability. [Parallax](https://arxiv.org/abs/2509.26182)
separates model allocation from request-time pipeline selection. These systems
establish substantial prior work in distributed serving, resilience and
adaptation. Their published performance numbers are not directly comparable to
this pilot's synthetic worker RPCs.

The intended distinction is the measured decision boundary for this specific
controller and replay mechanism. That distinction requires matched real-device
experiments; the current pilot does not establish novelty or superiority over
these systems. A final submission must extend the literature review beyond the
four references above, including cache transfer/recomputation and newer edge
inference systems identified in the repository's novelty review.

## 3. System and cost model

### 3.1 Partitioning objective

Let a model contain N layers assigned in order to K workers. Worker i receives
a contiguous half-open range [a_i, b_i), possibly empty. With layer cost p(C)
at context C, worker speed factor s_i, incoming-hop estimate l_i, and endpoint
terms e_i and h_i, a nonempty stage is modeled as

\[
c_i = \frac{(b_i-a_i)p(C)+e_i+h_i}{s_i}+l_i.
\]

Endpoint terms belong to the first/last nonempty stage holding the corresponding
model endpoint. Empty stages are skipped. The implementation allows zero-layer
assignments and solves the stated contiguous assignment problem in O(N²K).
Memory feasibility is not currently part of this optimization.

The bottleneck B = max_i c_i approximates saturated pipeline service cost. The
sum P = sum_i c_i approximates sequential token latency under the modeled
conditions. The two have different observables and must not be compared with
the same per-request tokens/s metric. Queueing, finite pipeline fill, runtime
batching and serialization can alter either prediction's accuracy.

### 3.2 Transition gate

For current and candidate bottlenecks B_c and B_o, horizon H and predicted
transition downtime T, the gate estimates

\[
U_{stay}=H/B_c,\qquad U_{adapt}=\max(0,H-T)/B_o.
\]

All time quantities use consistent units. After improvement and cooldown checks,
a voluntary change requires U_adapt > (1+m) U_stay, where m is a safety margin.
The implemented transition model is

\[
T=T_{fixed}+C\alpha N.
\]

The second term prices reconstruction across the whole chain, reflecting the
router's replay behavior rather than only the ownership-changing layers. With
positive denominator, the gate inequality requires

\[
H > \frac{T B_c}{B_c-(1+m)B_o}.
\]

If the denominator is nonpositive, no finite horizon satisfies that inequality
under the stationary model. For m=0 this reduces to the zero-margin break-even
H*=T B_c/(B_c-B_o). The separate improvement threshold and cooldown still apply;
clearing this inequality does not alone guarantee an executed move.

The model assumes stationary saturated rates and zero useful work during T.
Its scalar reconstruction term does not establish the actual cost of rebuilding
several concurrent sessions. Loading, draining, replay and recovery must be
measured together before interpreting these estimates as service outcomes.

### 3.3 Policies and recovery

The no-hysteresis policy changes on a strict modeled improvement. Hysteresis
adds a fractional improvement threshold and cooldown. The gate additionally
accounts for transition cost. Gate-force retains the gate verdict but executes
an eligible rejected candidate, enabling a matched-run comparison. It still
obeys preceding improvement/cooldown checks; it does not force every possible
layout change.

Worker-set changes bypass voluntary-move checks because the previous placement
may be unservable. This mechanism is not a guarantee that survivors have enough
memory. Generation-tagged requests and full-chain replay handle some layout/cache
changes, with interruption and reconstruction costs. Durable fencing, protected
membership and production reliability remain outside this pilot.

## 4. Experimental methodology

### 4.1 Evidence strata

We distinguish existing real-model component measurements, new analytical
decisions and new instrumented runtime measurements. Historical CPU Qwen3-0.6B
profiles provide approximate layer/endpoint parameters. They were collected
earlier on one Azure CPU VM and were not rerun in this session. New decision
sweeps use the production Go code, not a reimplementation of its gate. New RPC
experiments use the existing Python worker with synthetic sleep-based compute.
Neither new stratum measures distributed real-model performance.

### 4.2 Separated cost-model ablations

A 2×2 design independently enables endpoint terms and context-dependent layer
costs. The frozen-context arm uses the context-128 layer cost at all contexts.
Each chosen placement is evaluated under the same full reference model. Contexts
are 128/512/1024/2048; worker-B speed factors are 1/.93/.8/.7/.5; incoming link
costs are .5/10/80 ms. The 60 parameter cases yield 240 model/placement rows.

The metric is reference-model regret, B_reference(chosen)/B_reference(optimal)-1.
This is not measured runtime regret. Zero regret for the full reference arm is
true by construction and is not evidence that its predictions match hardware.
The frozen context, constant endpoint approximation and assumed hop values are
explicit sensitivity choices, not additional measurements.

### 4.3 Decision and transition ablations

The same 60 cases are crossed with six horizons, two margins, five transition
models and five policies, producing 18,000 deterministic decision rows. Transition
variants include full-chain replay, ownership-changing layers only, no replay,
no fixed cost and zero transition cost. The changed-layer count is computed
from the candidate's layer ownership. These variants are hypothetical estimates;
they do not implement alternative cache-migration mechanisms.

Cooldown is zero in this sweep to isolate the other components; the 15%
improvement threshold is retained. Each decider starts from the same full-model
baseline at speed 1 and hop .5 ms. No-trace static rows retain that initial
placement. Modeled useful-token quantities are counterfactual predictions and
must not be called observed throughput or migration outcomes.

### 4.4 Queueing ablation

A scratch wrapper instruments acquisition of the worker's existing compute lock.
It preserves the original Forward implementation and compute timer, returning
lock waiting as trailing RPC metadata. No production protocol or worker source
is changed. The router, controller and eBPF collector are not running in this
microbenchmark; the client evaluates the same RPC-minus-compute arithmetic used
by the router.

We cross synthetic service durations of 5/20/50 ms with 1/2/4 closed-loop clients
and two admission modes, with three repeats per condition. Direct mode permits
concurrent worker RPCs; FIFO mode admits one RPC at a time and records waiting
before RPC separately. Conditions are shuffled within repeat blocks using a
fixed seed. Each of the 54 windows admits work for 15 seconds and then drains
outstanding RPCs. Three idle/warmed worker processes supply the three service
durations on one host; each condition targets one worker.

Measured quantities include RPC duration R, worker compute D, compute-lock wait
Q, residual R-D, and queue-corrected residual R-D-Q. The corrected residual still
contains transport, serialization, handler scheduling and instrumentation costs;
it is not pure network propagation time. End-to-end client duration includes
FIFO admission wait. Throughput counts completed Forward RPCs over the entire
window plus drain, not real generated LLM tokens.

### 4.5 Analysis discipline

Windows are the repeated measurement units. Descriptive means and observed
three-window ranges are reported, with paired differences by repeat where both
admission arms are available. Individual RPCs are dependent samples within a
window and are not treated as thousands of independent trials. This pilot was
preceded by a short smoke check and is exploratory, not preregistered
confirmatory evidence. No significance, equivalence or generalization claim
follows from three repeats.

## 5. Results

### 5.1 Cost-model components alter modeled placement

At context 2048, equal worker speeds and .5 ms hop cost, the full reference
chooses 16/12 layers with bottleneck 158.18 ms. Removing endpoint terms chooses
14/14; evaluated under the reference it costs 177.16 ms, **12.00% higher than
the reference optimum**. Retaining endpoints but freezing context at 128
chooses 18/10, costing 170.91 ms under the reference, **8.05% higher**. Removing
both terms chooses 14/14 again.

These percentages use the reference optimum as denominator. They differ from
the earlier memo's percentage reduction relative to the worse split. They
describe the model's placement sensitivity, not an observed 12% performance
gain. Some parameter cases produce identical assignments despite prediction
error, so prediction accuracy and assignment changes must be reported separately.

![Separated analytical ablations](../data/paper-ablations-2026-10-04/cost-model-ablation.png)

### 5.2 Margin and transition assumptions change decisions

For context 2048 and a worker-B speed factor .7, the baseline 16/12 split has
modeled cost 225.757 ms after slowdown; the candidate 19/9 split has cost
185.086 ms. Full-chain downtime is predicted as 14.042 s. Zero-margin break-even
is 77.945 s, whereas a 13% safety margin requires approximately 190.854 s.
The default 30-second horizon rejects the move.

At that horizon/margin, removing replay reduces estimated downtime to 2 s and
the gate accepts; removing all transition cost also accepts. Pricing only the
three ownership-changing layers estimates 3.290 s and still rejects with the
13% margin, but it accepts at zero margin. These are decisions of the actual
decider under changed estimates, not measured outcomes of those moves.

The margin-derived horizon is not necessarily monotonic in context. Under the
same .7 speed factor and .5 ms hop, the context-512 candidate improves bottleneck
by only 13.79%; the separate 15% threshold blocks it even at a long horizon.
Ignoring this precondition would misstate the acceptance curve.

![Analytical horizon sensitivity](../data/paper-ablations-2026-10-04/gate-horizon-sensitivity.png)

### 5.3 Queueing contaminates the communication proxy

The complete main matrix contains **54 windows, 66,003 worker RPCs and zero
RPC errors**. Each cell below averages three window means; values describe the
instrumented synthetic loopback setup, not real-model serving.

| Simulated service | Clients | Admission | Mean RPC−compute | Mean lock wait | Mean corrected residual |
|---|---:|---|---:|---:|---:|
| 5 ms | 4 | direct | 15.561 ms | 14.765 ms | 0.797 ms |
| 5 ms | 4 | admitted | 0.798 ms | 0.001 ms | 0.797 ms |
| 50 ms | 1 | direct | 1.129 ms | 0.001 ms | 1.128 ms |
| 50 ms | 2 | direct | 50.253 ms | 49.040 ms | 1.214 ms |
| 50 ms | 4 | direct | 149.984 ms | 148.804 ms | 1.180 ms |
| 50 ms | 4 | admitted | 1.154 ms | 0.001 ms | 1.153 ms |


At 50 ms service, increasing concurrency from one to four raises the uncorrected
residual from 1.129 to 149.984 ms while the
loopback path/payload configuration is unchanged. Directly measured lock waiting
accounts for 99.21% of the latter mean residual. The
queue-corrected residual is 1.180 ms; its three-window mean
range is 1.158–1.223 ms.
FIFO admission produces a 1.154 ms uncorrected residual, but moves waiting
to the client. Mean client completion is 200.113 ms direct versus
204.496 ms admitted. Therefore the smaller RPC residual does not
establish better client latency.

At 5 ms service and four clients, direct/admitted throughput averages
193.40/166.98 completed RPCs/s. Admission reduces
RPC overlap and can reduce utilization; this pilot does not recommend one-at-a-time
admission as a general performance optimization. It exposes which delay component
the communication proxy includes. Three-window ranges and matched-repeat
residual differences are in the raw-data directory; no significance test is claimed.


![Instrumented queueing pilot](../data/paper-ablations-2026-10-04/queue-contamination.png)

### 5.4 Instrumentation calibration

A supplementary 24-window pilot compares the original worker class with the
instrumented wrapper at service 5/50 ms and concurrency 1/4, with three paired
repeat blocks and eight-second windows. Both servers use the same thread-pool
and transport options. It completed 19,113 RPCs with zero errors. Combined with
the primary study: **78 windows and 85,116 RPCs**, without pooling calibration
into the main per-condition repeat count.

| Simulated service | Clients | Mean wrapped−original residual | Observed paired range |
|---|---:|---:|---:|
| 5 ms | 1 | 0.014 ms | -0.026–0.052 ms |
| 5 ms | 4 | 0.082 ms | 0.062–0.109 ms |
| 50 ms | 1 | 0.045 ms | 0.023–0.060 ms |
| 50 ms | 4 | 0.064 ms | 0.054–0.073 ms |

At 50 ms and four clients, the original worker's mean residual was 149.070 ms
and the wrapped worker's was 149.134 ms in this separate short run. Thus a large
residual also exists without the wrapper. The observed paired differences are
small relative to the main queue effect in this calibration; this is descriptive
support, not an equivalence or universal negligible-overhead claim. The extra
metadata, timing calls and shared-host variability can affect small residuals.

![Instrumentation calibration](../data/paper-ablations-2026-10-04/instrumentation-calibration.png)

## 6. Discussion and threats to validity

Measurement validity precedes a placement-benefit claim. A signal correlated
with load may still be useful for scheduling, but describing queue delay as
network delay can lead to an incorrect attribution. The pilot quantifies a
mechanism already visible in source code; queueing itself is not a novel finding.
Whether separating the components improves actual controller decisions remains
unmeasured.

Likewise, a favorable candidate bottleneck and an accepted gate do not establish
user benefit. Horizon error, finite demand, several active caches, model reload
tails and a transition back after a transient fault can change the result. A
single-user latency objective and a saturated throughput objective require
different policy comparisons.

Internal validity is limited by shared-host scheduling, closed-loop arrivals,
instrumentation overhead and only three windows per condition. External
validity is limited more strongly: synthetic compute, tiny fixed RPC payloads,
loopback communication and a single OS/host do not represent real kernels,
quantization, WiFi, battery or thermal behavior. The analytical reference is
parameterized by historical component measurements and approximate endpoint
terms; it is not independently validated ground truth.

The current Qwen worker loads the full model before pruning to its assigned
layers. Therefore this prototype does not yet establish aggregate-memory serving
of a model too large for every participating device. Its token-ID benchmark API
is not a finished text/streaming product. The present studies also do not test
authenticated enrollment, protected transport or durable controller epochs.

## 7. Required real-device evaluation

The next study should compare initially optimized static placement,
no-hysteresis, hysteresis, gate and gate-force on matched stable, compute-load,
network-delay and worker-loss traces. Include faults shorter and longer than
predicted break-even, reconstruction contexts 128–2048, and concurrency 1/2/4.
Count interrupted and failed requests, replay, complete transition downtime and
the return transition when a fault ends.

Application-only, queue-separated application telemetry and optional eBPF must
be compared under the same runtime/policy. The current `ebpf+app` option is an
eBPF-first fallback, not demonstrated sensor fusion. Monitor overhead and
prediction/rank accuracy separately from service outcome. Reproducing a prior
system requires its actual implementation and assumptions; `profileonly` is
only an internal frozen-measurement baseline.

Use a strong feasible single-device engine baseline, including native batching,
and full-model replicas when every replica fits. A different optimized runtime
is a product-stack comparison, not a clean controller ablation. Measure peak
host/device memory during loading, steady serving and recovery.

Pilot data should determine variance and a practical effect threshold. Freeze
that threshold and sample-size rule before fresh confirmatory runs. Analyze
paired differences over repeated runs, with benefit, harm and inconclusive
outcomes retained. Do not infer equivalence from overlapping confidence
intervals, or omit no-benefit settings. Thermal and sleep/wake claims require
physical devices rather than CPU VMs.

## 8. Conclusion

Shardwise makes placement, transition estimates and policy decisions
inspectable in a standalone prototype. The present ablations separate cost
components and expose a queueing confound in a communication proxy. They support
careful calibration and stronger baselines before making an adaptive-performance
claim. The central question—when a real distributed transition repays its complete
cost—remains open until the matched real-model experiments are completed.

## References and artifacts

Bibliographic metadata checked against the primary arXiv records on 4 October
2026 is supplied in [references.bib](references.bib). The four papers above are
cited as their arXiv versions, without inventing journal metadata.

- [New ablation data and reproduction](../data/paper-ablations-2026-10-04/README.md).
- [Existing CPU component measurements](../data/azure-d4-2026-09/).
- [Existing research plan](../RESEARCH_PLAN.md).
- [Previous product-direction simulator study](../data/product-direction-2026-10-04/README.md), a separate exploratory dataset.
