# Novelty comparison and ablation study

Companion to `docs/RESEARCH_PLAN.md`. Every "ours" cell below describes what is
**built and verified in this repository**, with the evidence file named.
Nothing here is an abstract claim; nothing enters an abstract before the
experiments in the plan have run.

**Verification status of the comparison columns**

| Work | Status |
|---|---|
| arXiv 2505.02533 | **Read directly** (method §III-D2 and evaluation). Cells are quotes or close paraphrases. |
| EdgeShard | **Not re-read in this project.** Cells marked *(verify)* restate how this repo's own docs describe it (`docs/gpu-hardware.md`, `README.md`). Check each against the paper before submission. |
| Petals | General description only *(verify)*. |
| SparKV (2604.21231) | **Withdrawn** by its authors: "incorrect assumption in the model definition in Section 4, which affects the conclusions". Withdrawal invalidates its conclusions, not its disclosure. Not used as evidence either way. |

---

## 1. Comparison with the base paper and the closest prior work

| Dimension | EdgeShard (base paper) | arXiv 2505.02533 (closest) | **This work** |
|---|---|---|---|
| Partition granularity | Layers *(verify)* | Attention heads + blocks (finer) | Contiguous layers (coarser than 2505.02533) |
| When partitioning happens | Once, from offline profiling *(verify)* | Online, every interval τ | Online, every 2 s, gated by an explicit decision policy |
| Placement algorithm | DP *(verify)* | Per-interval heuristic (Algorithm 1), described as myopic | Exact linear-partition DP; brute-force cross-checked (500 randomized instances incl. endpoint costs) |
| Reconfiguration cost | None — never reconfigures *(verify)* | Migration delay `m_i / R_jk`, **including K/V cache** in `m_i` (transfer) | Weight reload + **KV reconstruction by full-chain replay**, measured end to end |
| Decides whether a move pays | n/a | Minimises inference + migration delay per interval | Transition gate: tokens delivered over a planning horizon, with live **break-even horizon** per decision |
| Compute-capacity input | Offline profile *(verify)* | **Sampled** (log-normal 5–50 GFLOPS) | **Measured** from the worker's own decode timing vs a reference profile |
| Network input | Profiled *(verify)* | **Sampled** (random 1–10 Gbps) | **Measured**: kernel sRTT (eBPF) and application transport time, selectable separately |
| Endpoint modules (embedding, LM head) | *(verify)* | Projection blocks modelled as blocks | Measured: LM head + final norm = **33–49 % of a 14-layer stage**; modelled as endpoint terms |
| Context dependence of layer cost | *(verify)* | Via K/V footprint growth | Measured per-layer decode cost **+71 %** from ctx 128→2048; interpolated table |
| Evaluation substrate | Real devices *(verify)* | **Discrete-event simulator** | Real machines (Azure VMs now; laptops needed for thermal) |
| Fault classes evaluated | *(verify)* | Background compute load only | Compute cap, CPU contention, network delay, device loss |
| Thermal throttling | *(verify)* | Not evaluated | Supported on laptops (`GPU_MODE=cputherm`); **not claimable on VMs** |
| Device failure / healing | *(verify)* | Not evaluated | Verified: node killed mid-request, healed onto survivor, output identical |
| Output correctness under repartition | *(verify)* | n/a (simulation) | Teacher-forced logits vs HuggingFace, max \|Δ\| **2.2e-5**, 12 configs; mid-request relayout **token-identical** |
| Counterfactual for rejected moves | n/a | n/a | `gate-force` arm: same verdict, always executes |
| Needs an orchestrator | *(verify)* | n/a | No — standalone mode; Kubernetes optional |

Evidence: `docs/data/qwen3-validation/`, `docs/data/standalone-e2e/`,
`docs/data/azure-d4-2026-09/`, `internal/partition/*_test.go`.

---

## 2. What is and is not claimable

| Candidate claim | Status | Why |
|---|---|---|
| "Online, migration-cost-aware repartitioning" | **Not claimable** | 2505.02533 does it, including K/V cache in migration size |
| "Context-dependent transition cost is missing from prior work" | **Not claimable** | 2505.02533's migration size grows with the K/V cache |
| "No prior system does X" | **Not claimable** without a literature check | Rule adopted after it caught two errors |
| Measured break-even horizon for repartitioning on real machines, as a function of context | **Candidate — primary** | 2505.02533 names real testbeds as its own future work; needs the Phase 6 runs to measure, not predict, the crossover |
| Endpoint modules are a third to a half of a stage; a layer-proportional model mis-partitions by 10.7–15 % | **Candidate** | Measured on this hardware; a finding about cost modelling, not a claim that others omit it |
| Transfer vs reconstruction as a *decision* | **Unestablished** | Requires comparing against transfer at several contexts/bandwidths; pending CacheGen check |
| Simulation-based results do not transfer to real hardware | **Contingent** | Needs demonstrated prediction error AND matched-condition performance loss AND attribution to a named assumption |
| Kernel telemetry adds value | **Open — H3** | Observed confound: kernel sRTT on RPC traffic absorbs ACK delay / server compute (see §4) |

---

## 3. Ablation study

Every arm changes **one** component; all else identical. All arms run on the
same counterbalanced fault schedule (`bench/vmrun.py`), paired by repeat.

| # | Component removed / changed | How | Tests | Compared against |
|---|---|---|---|---|
| A1 | Adaptation | `--policies static` (initially-optimized split, never moves) | **H1** | `hysteresis` |
| A2 | Hysteresis | `--policies none` (move on any strict improvement) | **H2a** | `hysteresis` |
| A3 | Transition gate | `--policies hysteresis` vs `gate` | **H2b** | `gate` |
| A4 | Gate verdict ignored | `--policies gate-force` | outcome of *rejected* moves | `gate` |
| A5 | Continuous telemetry | `--policies profileonly` (freeze at first reading) | value of live vs one-shot measurement — **not** a reproduction of EdgeShard | `hysteresis` |
| A6 | Kernel telemetry | `--link-source app`, nodes with `EBPF=off` | **H3** | `ebpf+app` |
| A7 | Application telemetry | `--link-source ebpf` | **H3** | `ebpf+app` |
| A8 | All link telemetry | `--link-source none` | floor for H3 | `ebpf+app` |
| A9 | Endpoint cost terms | `COST_MODEL=layer-proportional` | value of endpoint modelling | full model |
| A10 | Context-dependent cost | `COST_MODEL=layer-proportional` (scalar per-layer) | value of context term | full model |
| A11 | KV cache | `KV_CACHE=0` on router and all workers | why reconstruction cost exists at all | `KV_CACHE=1` |
| A12 | Planning horizon | `--gate-horizon-s 10/30/60/120` | horizon sensitivity of H2b | each other |
| A13 | Distribution | 1 worker, `--policies static` | the single-device baseline every arm must beat | all |

A9 and A10 are one switch together in the current config generator; separating
them needs one more knob. Offline, both are also answerable with
`cmd/dpsweep` against the measured tables (already done for A9:
`docs/phase4-dpsweep-measured-*.csv`).

Decision rules for every comparison are fixed in `docs/RESEARCH_PLAN.md` §2:
paired difference against a pre-registered SESOI, four exhaustive outcomes
(benefit / positive-not-meaningful / harm / inconclusive), equivalence only via
TOST. `bench/vmanalyze.py` implements them.

---

## 4. Observations so far that the ablations must account for

- **Kernel sRTT on RPC traffic is not pure network latency.** In the local
  rehearsal, eBPF sRTT on loopback read ~11 ms while application transport
  time read 4.5–8.2 ms. A plausible cause: an RPC request's ACK is piggybacked
  on the response, so the kernel's RTT sample absorbs server compute. If
  confirmed on the VMs, H3 must report it — it changes what "kernel telemetry"
  measures for an inference pipeline.
- **Full-chain replay makes reconstruction ~2× costlier** than a
  moved-layers-only estimate: break-even for a 0.7× derate at ctx 2048 is
  77.9 s, not 26.4 s (`internal/partition/decider_test.go`).
- **Weight reload dominates short-context transitions**: 2435 ms total vs
  426 ms reconstruction in the measured mid-request relayout.
- **The cost model is well calibrated in the right units**: median error
  −2.2 % to −7.9 % against aggregate throughput; the old "3× gap" was the
  stage count (`docs/phase0-findings.md`).
