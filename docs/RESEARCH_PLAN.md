# Research Plan — When Does Repartitioning Pay?

**Measurement-Guided Adaptive LLM Inference on Heterogeneous Consumer Devices**

Primary goal: the journal paper.

**See also** `docs/NOVELTY_AND_ABLATIONS.md` (comparison with EdgeShard and
arXiv 2505.02533; the ablation matrix) and `docs/HANDOFF.md` (current state).
Immediate milestone: the **preliminary results table** (Phase 6). Not an
architecture rewrite.

> **Research question.** Can a controller use measured compute, communication, and
> reconfiguration costs to improve sustained inference performance under changing
> device conditions?

---

## 1. Novelty position

Stated by confidence level. Nothing here enters an abstract before experiments.

### 1.1 What is closed

| Angle | Held by |
|---|---|
| Offline-profiled DP layer partitioning | EdgeShard / PipeEdge / Galaxy |
| Online re-partitioning with migration cost | arXiv 2505.02533 |
| Migration cost that grows with context | arXiv 2505.02533 — `m_i(τ)` is "the memory footprint of block i (**including its K/V cache**, if i is an attention head)" |
| Dynamic rebalancing and failover | Petals |
| eBPF network telemetry as a mechanism | established field |

Our contiguous-layer DP is the classical linear-partition algorithm — correct,
unit-tested against brute force, and **coarser** than the head-level scheduling in
2505.02533. There is no "we invented X" claim available here, and none is needed.

### 1.2 Primary claim — defensible now (measurement / evaluation)

arXiv 2505.02533 is a discrete-event simulator: memory and compute sampled from
log-normals, bandwidth assigned randomly 1–10 Gbps, **no thermal throttling, no
network degradation, no device failure or recovery.** Its own stated future work is
"real-world testbeds."

> We implement a **transition-aware contiguous-layer controller**, measure the
> end-to-end costs of layer reassignment and KV-cache reconstruction on real
> heterogeneous devices, and evaluate when adaptation repays those costs — including
> the conditions under which staying put is correct.

This is an evaluation/measurement contribution. It can publish. It is not a
top-tier systems novelty claim, and should not be presented as one.

**Scope discipline.** That simulation-only limitation is a fact about *this paper*,
not about online partitioners in general. Keep three activities distinct:
reproducing their algorithm (we are not), comparing against their assumptions, and
evaluating our own design.

### 1.3 Secondary claim — reopened, requires a literature check

**Transfer vs. reconstruction of KV state.** SparKV (arXiv 2604.21231) is
**withdrawn** — "by the authors due to an incorrect assumption in the model
definition in Section 4, which affects the conclusions." Withdrawal invalidates its
*conclusions*; it does **not** erase the public disclosure of the approach. So this
angle is not closed by SparKV, but neither is it open: **the novelty here remains
unestablished, pending comparison with CacheGen and related transfer-vs-recomputation
work.**

A controller that chooses *per reassignment* whether to transfer cache state or
recompute it — from measured link bandwidth against measured compute — is a
*candidate* contribution, since on consumer WiFi the datacenter assumption that
transfer beats recompute may invert.

**Before claiming anything:** read CacheGen and related work properly. Making
reconstruction a *contribution* rather than an implementation choice further requires
comparing it against transfer at several context lengths and bandwidths — not merely
choosing it.

### 1.4 Contingent claim — highest ceiling, may not materialise

Different inputs producing different placements proves nothing on its own — that is
expected and trivial. To support a methodological finding, **all three** are required:

1. **Demonstrated prediction error** — the simulated parameterisation's predicted
   costs diverge measurably from measured costs on real devices.
2. **Demonstrated performance loss under matched conditions** — placements chosen
   from simulated assumptions perform worse than placements chosen from measured
   values, on the same hardware, same trace, paired runs.
3. **Attribution to specific modeling assumptions** — the loss traces to a named
   assumption (e.g. sampled compute capacity, assumed link bandwidth), not to
   unexplained residual.

Absent all three, report the divergence as an observation about parameterisation, not
as a finding about simulation methodology. This is contingent: if measurements
broadly agree with simulated assumptions, there is no finding. The plan produces the
data either way.

### 1.5 Language discipline

- "Its published evaluation does not establish this behavior" — never "it cannot
  produce this result."
- No "no prior system does X" without a literature check. This rule has already
  caught two errors in this plan.
- Identical assignments do not prove eBPF worthless; different assignments do not
  prove better performance.
- Cite SparKV only as withdrawn, if at all.

---

## 2. Hypotheses and decision rules

| # | Hypothesis | Comparison |
|---|---|---|
| H1 | Live measurements improve placement under changing conditions | Initially-optimized placement vs online adaptation |
| H2 | Accounting for transitions prevents harmful moves | Three arms: no hysteresis → hysteresis only → hysteresis + transition gate |
| H3 | Kernel telemetry improves some aspect of control | Application-only vs application+eBPF, including monitoring overhead |

H2 uses three arms because the existing 15%/30s hysteresis already suppresses many
harmful moves; a two-arm design is confounded, and the third arm answers whether the
gate adds anything over the cheap heuristic already in the code.

### Decision rules — fixed before any confirmatory run

Overlapping confidence intervals **do not falsify** anything, and "indistinguishable"
**does not establish equivalence.** Test the **paired** difference (matched runs,
same trace) against a predefined smallest effect size of interest (SESOI):

| Outcome | Criterion |
|---|---|
| Evidence of benefit | CI for the paired difference lies entirely **above the SESOI** |
| Positive but not practically meaningful | CI lies entirely **within (0, SESOI)** — the sign is established, the magnitude does not clear the threshold |
| Evidence of harm | CI lies entirely **below zero** |
| Inconclusive | CI spans zero **or** spans the SESOI boundary — report as inconclusive, **not** "no effect" |

These four are exhaustive. A CI entirely between zero and the SESOI is neither harm
nor inconclusive about the effect's *sign*, and must not be reported as either.

To claim the H2 gate is *equivalent* to hysteresis-only, use equivalence testing
(e.g. TOST) against predefined bounds. Absent that, the result is inconclusive.

- SESOI and the H3 threshold are chosen from **pilot** evidence and frozen before
  confirmatory runs. Pilot data is not reused in confirmatory analysis.
- **A null result will be reported**, and may support a contribution if the
  explanation, rigor and generality are sufficient. It is not guaranteed publishable.
  Recording this now removes the incentive to steer experiments toward a positive.

---

## 3. Platform scope

| Claim | CPU VMs (e.g. Azure) | Physical laptops |
|---|---|---|
| Correctness, recovery, scaling | Yes | Yes |
| Controlled compute contention | Yes | Yes |
| Controlled network degradation (netem) | Yes | Yes |
| Cost-model validation, compute + communication | Yes | Yes |
| **Thermal throttling behavior** | **No** | Yes |
| **Physical device heterogeneity** | **No** | Yes |
| **Real WiFi variability, sleep/wake churn** | **No** | Yes |

`docs/two-laptops.md` already records that node agents read `-1` for temperature in
VMs — there is no thermal zone. **Decide explicitly:** either frame the initial study
around VMs and drop the thermal and heterogeneity claims, or retain physical laptops
for those claims. Never report VM results under a consumer-hardware framing.

---

## 4. Phases

| Phase | Goal | Hardware | Blocks |
|---|---|---|---|
| 0 | Measurement correctness | No | everything |
| 1 | Instrumentation and power check | No | — |
| 2 | Standalone runtime | 2nd machine to verify | 3,4,5,6 |
| 3 | Qwen3-0.6B + KV cache + recovery | Yes | 4,5,6 |
| 4 | Profiling, cost model, transition cost | Yes | 5,6 |
| 5 | Decision gate | Yes | 6 |
| 6 | Experiments → results table | Yes | 7 |
| 7 | Write-up and venue | No | — |

**Phases 0 and 1 need no new hardware. Start both now; procure machines in parallel.**

### Phase 0 — Measurement correctness

Mostly re-analysis of runs already in `bench/results/`.

**0.1 Correct the fidelity comparison.** `bench/fidelity.py:77` compares the DP's
`bottleneck_ms` (slowest **single** stage) against `1000/tokens_per_sec`, which
`worker/router.py:184` computes per request as tokens ÷ end-to-end duration — **all**
stages sequentially. Three balanced stages ⇒ ratio ≈3; observed 3.0–3.24. Split into
two checks: stage service time vs measured per-stage cost, and end-to-end latency vs
sum-of-stages-plus-hops (the DP does not emit the latter — add it). Report error
**distributions** on held-out workloads and **rank correctness**, not mean ratios.
Do not calibrate any ratio toward 1.0.

**0.2 Correct the README.** Its stated cause ("likely gRPC/interpreter overhead") is
**unsupported and confounded.** Say that; do not assert a replacement cause — the
residual has not been measured.

**0.3 Harness corrections** (`bench/run.py`): separate stage service time,
per-request latency and aggregate throughput; relabel worker idle fraction a
**utilization proxy**; record real failure-onset and recovery timestamps; count
failed requests, transition downtime and recovery windows; add a best-feasible
**single-device** baseline; stop presenting profile-only as EdgeShard.

**0.4 Freeze the metric schema** (§6). Retrofitting a column means re-running
everything.

**Acceptance:** an existing netem pair re-analysed into coherent separated metrics;
fidelity reported as distributions; no metric lacks a written definition.

**Exit gate:** if fidelity resists decomposition, resolve before Phase 4 — the cost
model is contribution #1.

### Phase 1 — Instrumentation and power check (offline, hours)

*Goal: know the achievable range and whether the harness can resolve differences.
**Not** a filter selecting conditions where improvement is guaranteed.*

**This phase must not bias the study.** "When does repartitioning pay?" requires
no-benefit conditions to be studied, not discarded. Conditions where the model
predicts little or no benefit are **retained deliberately** — they are where the
"staying put is correct" finding comes from.

**1.1 Predicted range.** For each fault, recompute the DP offline over the candidate
splits and record the predicted change in optimum. With 28 layers across two workers
there are **29** contiguous allocations when zero-layer assignments are allowed
(k = 0..28), or 27 if both must be non-empty. **State which convention the DP uses.**

**1.2 Record predicted-no-benefit conditions explicitly** and carry them into Phase 6
as first-class rows.

**1.3 Harness resolution.** Establish measurement noise from **repeated real runs** of
the unchanged system — not from the cost model, which is unvalidated until Phase 4.

**1.4 Concurrency reasoning.** Estimate where pipeline gains can begin for the stage
count in play; plan a sweep rather than assuming a threshold.

**Exit gate.** Proceed regardless of whether the optimum moves. Hardware changes are
justified by **measured** noise and measured effect sizes — never by offline
predictions from an unvalidated model, and never to manufacture an effect.

### Phase 2 — Standalone runtime (minimum to reach real devices)

A means, not a milestone. Kubernetes stays working throughout.

- **2.1** `internal/controller/source.go`: `SpecSource`, `WorkerSource`, `StatusSink`.
  Existing bodies move verbatim into `k8ssource.go` so all `k8s.io` imports leave
  `controller.go`; standalone impls in `localsource.go`.
- **2.2** `cmd/controller/main.go` gains `--mode`; **client construction moves inside
  the k8s branch** — today `:52-63` `log.Fatalf`s before anything else runs.
- **2.3** `deploy/manifests/controller.yaml:34` is `args: []` — add `--mode=k8s` in
  the same commit or the existing deployment breaks.
- **2.4** Discovery: node agent becomes the per-machine registry via
  `repeated WorkerRef workers = 6` on `NodeTelemetry` (additive, wire-compatible).
  `make proto` must be re-run — stubs are committed. *Resolve
  `gen/pipelinepb/pipeline_grpc.pb.go`, already modified in the working tree, first.*
- **2.5** Per-worker ports: `controller.go:302` and `:311` assume one global
  `cfg.WorkerPort`. Remove it; advertise coordinator-reachable addresses.
- **2.6** Readiness via RPC-level health, not TCP accept.
- **2.7** Launcher `cmd/keinfer`. Reuse **only the isolated-venv portion** of
  `scripts/run-single-gpu.sh:38-85` — **not** its `--break-system-packages` fallback,
  which mutates the system interpreter. If a venv cannot be created, fail with
  instructions.
- **2.8** Preserve the deterministic `(node, name)` sort (`controller.go:263-268`) and
  its comment at `:238-242` — it exists because of a real Decider-thrash bug.

**Acceptance:** `./run-demo.sh` unchanged; `keinfer up` runs the full loop with no
Docker/kubectl; discovery and inference verified across two machines.

### Phase 3 — Qwen3-0.6B, KV caching, recovery

Contiguous Qwen3 shards with correct embeddings, positions, masks, final norm and
output projection; load **only** assigned weights plus endpoint modules; CPU FP32
first, then validated CUDA FP16. Cache keyed by `(request, generation,
processed-token position)` so duplicate or out-of-order forwards are detected.
Bound sessions and memory. Transitions apply at a generation boundary and publish
only on all-worker readiness ack.

**Persist generations.** Workers currently **accept** backward generations with a
warning (`worker/server.py:57-61`) — harmless today, unsafe once cache state exists.

**Correctness by teacher-forced logit comparison**, not a blanket token-divergence
tolerance. Separately test masking, positions, duplicate requests, recovery. Keep the
stateless path as reference and ablation. Persistent divergence is a bug signal.

### Phase 4 — Profiling, cost model, transition cost

Per-device prefill and decode measured separately including endpoint modules;
compute separated from queueing, serialization and transfer; bounded smoothing from
live requests. Replaces assigning every healthy device `Speed = 1.0`
(`controller.go:208-210`). Communication modelled from payload size against measured
transfer on real paths. Memory feasibility for weights, activations, caches and
transition overhead. **Transition cost is the *additional* cost over continuing
normally.** Capacity from measured execution slowdown — temperature is supporting
evidence only.

### Phase 5 — Decision gate

Three arms precisely defined (what is disabled in each). Consistent units: expected
useful tokens over the horizon after downtime, not ms vs tokens/sec. Uncertainty
margin before a voluntary move, from Phase 0 error distributions. Recovery bypasses
the gate. Horizon sensitivity beyond the chosen 30 s.

---

## 5. Phase 6 — Experiments and the results table

### Metric definitions (frozen in 0.4)

| Metric | Definition |
|---|---|
| TTFT | ms from admission to first token emitted |
| ITL | mean ms per token *after* the first, per request |
| Completion latency | ms from admission to final token |
| Throughput | completed tokens ÷ wall time, aggregate, at stated concurrency |
| Completion rate | completed ÷ submitted |
| Failure rate | failed ÷ submitted, by failure class |
| Transition cost | *additional* time over continuing normally |
| Recovery time | fault onset → **sustained successful service** (completion rate restored to its pre-fault level) |
| Throughput restoration | reported **separately**: fraction of pre-fault throughput reached, and time to reach it — **may never occur**, since losing a worker can permanently reduce capacity |

Every figure carries an uncertainty interval. **"p95 latency" alone is ambiguous and
must not appear** — name which of TTFT / ITL / completion latency.

### Protocol

Repeated, counterbalanced, independent runs. Fault injection scoped to the real
interfaces — loopback netem validates single-host behavior only.

**Fault reproducibility is not assumed.** Replaying the same injected workload does
**not** reproduce identical thermal conditions. Record **actual** temperatures, clock
frequencies and contention per run as covariates. Network and device-loss faults can
be trace-replayed; thermal cannot, and is analysed with measured conditions as
covariates.

**Rejected moves have no directly observed outcome.** A rejected move's benefit is not
measurable by rejecting it. Either run a **matched forced-move arm** (same trace, gate
overridden, move executed) so the counterfactual is observed, or use a counterfactual
estimator validated against forced-move runs. Absent either, report it as a **model
prediction**, never a measured outcome.

### Table

| Scenario | Policy | Throughput | TTFT | ITL | Completion rate | Recovery (s) | Thru. restored | Moves made | Moves rejected | Transition cost | Peak mem |
|---|---|---|---|---|---|---|---|---|---|---|---|
| stable | single-device | | | | | — | — | — | — | | |
| stable | initial-optimized | | | | | — | — | 0 | — | | |
| stable | adaptive, no hysteresis | | | | | | | | | | |
| stable | adaptive, hysteresis | | | | | | | | | | |
| stable | adaptive, hysteresis+gate | | | | | | | | | | |
| thermal *(laptops only)* | *(same five)* | | | | | | | | | | |
| network | *(same five)* | | | | | | | | | | |
| device loss | *(same five)* | | | | | | | | | | |
| predicted-no-benefit | *(same five)* | | | | | | | | | | |

Plus per scenario: application-only vs application+eBPF, with monitoring CPU overhead
and fault-detection latency (the H3 criterion), and a **matched forced-move arm**
wherever rejected-move benefit is reported. Concurrency sweep 1/2/3/8 where memory
permits; short and long contexts; report where gains begin.

**Failure experiments need survivors with sufficient capacity** — two machines suffice
when the survivor can hold and execute the model; add a third only when capacity
demands. Do not run capacity-aggregation and fault-recovery at the same model size by
accident.

---

## 6. Standing constraints

- `bench/results/` is **gitignored**; committed journal data is
  `docs/journal-benchmark-4cpu-*`. Preserve both; write new runs to fresh names.
- Keeping the Kubernetes path working preserves provenance of existing results.
  Standalone is an addition, not a retraction — do not re-label past results.
- Deferred until after Phase 6: desktop packaging, polished chat UI, internet
  pairing/Tailscale, additional model families.
