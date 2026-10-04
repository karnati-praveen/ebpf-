# A "Kubernetes for everyday users" for LLM inference: landscape and positioning

Research pass on 2026-10-04. This complements `docs/NOVELTY_RESEARCH_2026-09-23.md`,
which covers datacenter migration work (Llumnix, SpotServe, ServerlessLLM,
CacheGen, BanaServe, EdgeFlow). This document covers what that memo did not:
**tools and papers for clusters of everyday home devices**, plus the 2026
live-reconfiguration papers. Rows marked *(abstract)* were checked only
against the abstract or a summary, not the full paper.

---

## 1. Why Kubernetes is the wrong tool for everyday users

Kubernetes assumes:
- an administrator,
- always-on Linux servers,
- a stable network,
- etcd quorum, and
- containers everywhere.

A home cluster is the opposite:
- laptops that sleep and throttle,
- Wi-Fi,
- mixed operating systems,
- nobody to run `kubectl`.

K3s and KubeEdge shrink Kubernetes, but keep the same model. LMEdge (Euro-Par
2026) evaluates edge LLM orchestration *on* Kubernetes, which shows the
research community still uses it as the substrate for edge clusters, not for
home ones.

Our standalone mode already replaces every part of Kubernetes that this
project used:

| Kubernetes piece | Our standalone equivalent | File |
|---|---|---|
| kubelet (per-node agent) | node agent: heartbeat, worker health, measured speed, eBPF telemetry | `cmd/nodeagent` |
| scheduler + controller-manager | controller: DP placement, decision policy, healing | `cmd/controller`, `internal/partition` |
| etcd / API server | JSON config + in-memory state from heartbeats | `internal/controller/localsource.go` |
| restart policy | `supervise` loop | `deploy/standalone/common.sh` |
| `kubectl get` | `GET /state` | controller HTTP |

**So we don't need to build a new Kubernetes. We already have a small,
purpose-built one.** What we have is a control plane whose single job is to
keep an LLM pipeline healthy on unreliable devices. That is the "Kubernetes
for everyday users" idea, narrowed to the one workload that matters here.

## 2. What already exists for home and consumer clusters

| System | What it does | Adapts at runtime? | Source |
|---|---|---|---|
| **exo** (open source) | Auto-discovers devices on the LAN; splits layers in proportion to memory; ChatGPT-compatible API; Mac/Linux/phones | Partitioning is based on device capacity. Users report "ghost" nodes that stay in the topology after a link drops, and nodes disappearing during model download (GitHub issues #775, #1139). These are anecdotal, not a measured study. | [deep dive](https://medium.com/@leif.markthaler/deep-dive-exo-distributed-ai-inference-on-consumer-hardware-068e341d8e3c), [issue #775](https://github.com/exo-explore/exo/issues/775), [issue #1139](https://github.com/exo-explore/exo/issues/1139) |
| **prima.cpp** (ICLR 2026) | 30–70B models on home clusters: Mac M1, i9 laptop, i9 desktop, Android phone, **over Wi-Fi**, mixed operating systems. The Halda scheduler solves layer assignment as an ILP from device profiles. | **Repartitions only when the task queue is empty.** It states that "no cross-device layer migration is required". Profiling is done at startup. A summary of the full paper found no detection of throttling or Wi-Fi changes; check this before citing. | [arXiv 2504.08791](https://arxiv.org/abs/2504.08791) |
| **GPUStack** | Cluster manager for heterogeneous GPUs across Mac, Windows and Linux; llama.cpp-based distributed inference | Deployment-time placement | [GitHub](https://github.com/gpustack/gpustack) |
| **Intel AI-PC fleets** (2608.19147) | Pipeline shards pre-compiled with OpenVINO across Intel AI PCs; micro-batching across users | Static, pre-compiled partitioning *(abstract)* | [arXiv 2608.19147](https://arxiv.org/abs/2608.19147) |
| Petals, distributed-llama, llama.cpp RPC | Swarm (Petals) or static (the others) layer distribution | Petals rebalances across an internet swarm; the others are static | — |

**The gap.** In this survey, the consumer systems are either static
(exo, GPUStack, AI-PC fleets) or repartition only when **idle** (prima.cpp).
None that we found decides *during* a request whether moving layers is worth
it, or measures what that costs.

## 3. 2026 live-reconfiguration papers (datacenter GPUs)

| System | What it does | Decides *whether* to move? | Source |
|---|---|---|---|
| **PipeLive** | Live, in-place pipeline-parallel reconfiguration; KV resizing; reconfiguration overhead under 10 ms | No: the paper is about *how* to reconfigure cheaply | [arXiv 2604.12171](https://arxiv.org/abs/2604.12171) |
| **ReMP** | Runtime TP/PP switching in 1.0–7.4 s on 7B–70B models; 2-D KV migration | Focus is on the mechanism *(abstract)* | [arXiv 2606.18741](https://arxiv.org/abs/2606.18741) |
| **FlexPipe** | In-flight pipeline refactoring in serverless clusters | *(abstract)* | [arXiv 2510.11938](https://arxiv.org/abs/2510.11938) |
| **OrionInfer** (KDD 2026) | Low-overhead parallelism switching and live migration | *(not read)* | — |
| **DynoPipe** (ISCA 2026) | Edge-cloud serving with dynamically orchestrated pipeline boundaries | *(could not retrieve the abstract; must read before submission)* | ISCA 2026, pp. 969–984 |
| **E2LLM** | Edge/fog: replicas with prefill/decode roles; genetic algorithm + DP placement | *(abstract)* | [arXiv 2606.03770](https://arxiv.org/abs/2606.03770) |
| **Pallas** | AI-RAN handover: recompute the stable prefix at the target while streaming the evolving suffix's KV | Proactive migration on predicted handover | [arXiv 2608.16477](https://arxiv.org/abs/2608.16477) |

## 4. The argument this landscape gives us

1. **On datacenter GPUs, reconfiguration has become cheap.** PipeLive reports
   under 10 ms. When moving is that cheap, "should we move?" hardly matters.
2. **On consumer devices it is expensive.** We measured a 2,435 ms relayout
   for a 0.6B model on CPU (weight reload plus 426 ms of KV replay), and the
   predicted break-even reaches tens of seconds as context grows.
3. **The consumer systems sidestep the question.** They never move (exo), or
   move only when idle (prima.cpp).
4. Therefore **when mid-request repartitioning pays on consumer-class
   hardware is an open, regime-specific question.** Our system is built to
   answer it: measured telemetry, a transition gate, `gate-force`, and
   token-identical correctness.

This is stronger than "we measured on real machines", because it explains
*why* the answer differs between the datacenter regime and the home regime.

## 5. What to add, in order of value per hour

| # | Addition | Why | Effort |
|---|---|---|---|
| 1 | **`idle` policy arm**: repartition only when no request is in flight | A direct comparison with prima.cpp's policy, the closest consumer-cluster system. It answers "is moving mid-request better than waiting until idle?" | ~1–2 h: the router reports in-flight count to the controller; the Decider defers until it is 0 |
| 2 | **Fault-duration sweep** around the predicted break-even | Turns the 77.9 s *prediction* into a *measured* crossover. This is the primary result. | Harness only (`vmrun.py` fault duration) |
| 3 | **Memory-proportional static split** (exo-style) as a baseline | A fair consumer-tool baseline instead of our own DP | ~30 min (config) |
| 4 | Remaining-work-aware horizon | Matters only for finite jobs. Under steady closed-loop load there is always more work, so it collapses to the fixed horizon. | ~1 h; lower priority |
| 5 | Uncertainty-aware gate | Worth building only if Phase 6 shows the fixed gate making errors near the boundary | Later |

**Do not build for this deadline:** mDNS zero-config discovery, Windows/Mac
support, authentication, or a UI. They matter for a product, not for the paper.

## 6. Claims to avoid

- "First consumer/home distributed LLM system": exo and prima.cpp exist.
- "First live pipeline reconfiguration": PipeLive, ReMP, FlexPipe, SpotServe.
- "prima.cpp cannot handle failures": it adds or removes devices at runtime
  (between tasks). Say precisely that it **repartitions only when idle**.
- Anything about DynoPipe or OrionInfer before reading them.
