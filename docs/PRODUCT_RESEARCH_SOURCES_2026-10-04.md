# Product research evidence — 4 October 2026

Scope: primary project documentation, source code, and research papers consulted
for the companion [direction report](PRODUCT_DIRECTION_2026-10-04.md). Access date:
4 October 2026. These are documentation observations, not independently reproduced
competitor benchmarks. GitHub default branches and `latest` documentation can move.

## User requirements established in this session

- People like the project owner should be able to use it easily.
- No Kubernetes or similarly large infrastructure installation.
- Explore the strongest direction supported by the repository.
- Research for 30–45 minutes; ask about consequential uncertainties.

## Product and runtime evidence

| Source | What was checked | Implication / evidence limit |
|---|---|---|
| [Kubernetes concepts](https://kubernetes.io/docs/concepts/) | Declarative workload management and automation. | Borrow desired-state reconciliation; rebuilding its full platform is a much larger project. |
| [NVIDIA PAIR README](https://github.com/NVIDIA/Personal-AI-Router) | Device discovery, installed engines, request routing, desktop installers. Explicitly routes each request to one node. | The personal-AI-router product already exists. This does not establish its performance on the user's hardware. |
| [PAIR getting started](https://github.com/NVIDIA/Personal-AI-Router/blob/develop/docs/getting-started.mdx) | Single-machine startup, pairing, engine/model installation, stable local endpoints. | A concrete onboarding baseline. Network trust requirements and backend hardware support still matter. |
| [PAIR services](https://github.com/NVIDIA/Personal-AI-Router/blob/develop/services/readme.md) | Background-service decomposition. | Possible integration target; no extension interface has been implemented or validated here. |
| [exo README](https://github.com/exo-explore/exo) | Discovery, topology-aware placement, MLX distributed, dashboard and API compatibility. | A substantial competitor for split-model local AI. Published speedups depend on the described hardware/interconnect. |
| [exo platforms](https://github.com/exo-explore/exo/blob/main/PLATFORMS.md) | Apple Silicon is listed as maintained; Linux support appears in planned tiers. | README Linux installation instructions and this roadmap need reconciliation against a pinned release before a hardware support claim. |
| [LocalAI overview](https://localai.io/docs/overview/index.print.html) | Pluggable engines, local APIs, model management, multiple modalities. | A general local-AI runtime would duplicate established work. |
| [LocalAI P2P modes](https://localai.io/docs/features/distribute/index.print.html) | Distinction between whole-request federation and model sharding. | They are different mechanisms; mode-specific limitations cannot be generalized to every LocalAI deployment. |
| [LocalAI distributed mode](https://localai.io/docs/features/distributed-mode/index.print.html) | PostgreSQL/NATS infrastructure, placement/routing, worker resource reporting. | Capable competitor, with infrastructure that may exceed the user's desired install footprint. |
| [LocalAI MLX distributed](https://github.com/mudler/LocalAI/blob/master/docs/content/features/mlx-distributed.md) | Pipeline/ring and tensor/JACCL modes, per-node model access. | “LocalAI cannot split a model” would be incorrect. |
| [GPUStack README](https://github.com/gpustack/gpustack) | GPU cluster management, serving-engine orchestration, instance provisioning. | A cluster-manager direction is already occupied. Engine and worker prerequisites matter. |
| [GPUStack releases](https://github.com/gpustack/gpustack/releases) | Release history distinguishes stable 2.2.3 from 2.3 release candidates at access. | Do not treat default-branch documentation or an older FAQ as a stable release support guarantee. |
| [Ollama FAQ](https://docs.ollama.com/faq) | Model memory, concurrency, queueing and overload. | Existing single-machine engines are important baselines; concurrency consumes additional memory. |
| [Ollama chat](https://docs.ollama.com/api/chat), [generation](https://docs.ollama.com/api/generate), [resident models](https://docs.ollama.com/api/ps) | Streaming, load/evaluation timings, residency and reported allocation/context. | Concrete whole-model adapter inputs; client TTFT and peak capacity still require direct measurements. |
| [Open WebUI Ollama connection](https://docs.openwebui.com/getting-started/quick-start/connect-a-provider/starting-with-ollama/) | Multiple Ollama connections, random request distribution, matching model IDs. | A basic multi-server chat experience can already be assembled. |
| [LiteLLM routing](https://docs.litellm.ai/docs/routing) | Multiple routing policies, retries, cooldowns and fallbacks. | Ordinary load balancing/failover is not sufficient differentiation. |
| [LM Studio headless](https://lmstudio.ai/docs/developer/core/headless) | Standalone daemon, startup behavior, on-demand loading. | Desktop/headless single-device serving is already convenient. |
| [AnythingLLM local engine](https://docs.anythingllm.com/setup/llm-configuration/local/built-in) | Desktop model downloads and built-in local inference. | Document chat is a useful application to connect, rather than rebuild. |
| [llama.cpp RPC](https://github.com/ggml-org/llama.cpp/blob/master/tools/rpc/README.md) | Distributed backend setup and upstream warning about open/sensitive networks. | Investigate as an engine, not a ready-made secure product or assumed live-relayout API. |
| [llama.cpp server](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md) | Streaming, slots, optional processing/deferred-request metrics and slot-cache save/restore. | Useful adapter surface; native batching is a necessary baseline and saved caches are not automatically portable across shard layouts. |
| [vLLM parallelism](https://docs.vllm.ai/en/latest/serving/parallelism_scaling/) | Single-device, tensor, pipeline, and multi-node deployment guidance. | A model fitting on one GPU does not automatically need distribution. |
| [Accelerate big-model inference](https://huggingface.co/docs/accelerate/usage_guides/big_modeling) | Empty model initialization and checkpoint/device dispatch. | Useful loading primitives; `device_map=auto` does not implement this repository's networked shard protocol. |
| [Safetensors partial loading](https://huggingface.co/docs/safetensors/main/en/index) | Tensor-by-tensor access and partial tensor slices. | A way to investigate selective weight loading, not a complete shard runtime or correctness proof. |
| [Ray Serve LLM](https://docs.ray.io/en/latest/serve/llm/index.html) | Multi-node/multi-model serving and multiple parallelism modes. | Useful infrastructure baseline, with more stack than the personal product needs initially. |
| [KServe introduction](https://kserve.github.io/website/docs/intro) | Kubernetes deployment and multi-node inference. | Enterprise serving alternative; does not meet this user's no-Kubernetes requirement directly. |
| [Flock README](https://github.com/llmpy/flock) | Go control plane, routing, embedded UI, CLI, llama.cpp RPC orchestration; explicitly beta. | Particularly close conceptually. Sharded mode documents additional runtime/source-build prerequisites and naive free-RAM packing. Marketing scope exceeds verified deployment scope. |
| [Flock architecture](https://github.com/llmpy/flock/blob/main/ARCHITECTURE.md) | Control plane and engine separation. | Build-versus-integrate comparator; no integration tested in this session. |
| [Parallax project](https://github.com/GradientHQ/parallax) | Personal-device hosting, pipeline sharding, dynamic request routing. | Include it when assessing adaptive heterogeneous inference. |
| [dnet project](https://github.com/firstbatchxyz/dnet) | Apple-focused discovery, device/model profiling, heterogeneous solver. | Profiling and automatic placement are already product features elsewhere. |
| [Uncloud](https://uncloud.run/) | Multi-machine Docker Compose, WireGuard, deployment/HTTPS; deliberately no automatic rescheduling. | A useful generic-app alternative; important distinction between surviving replicas and automatic healing. |
| [Dokploy deployment options](https://docs.dokploy.com/docs/core/deployment-options) | Single host, independent remote servers, and Swarm nodes. | Easier generic app deployment already has several architectures. |
| [Coolify scaling](https://coolify.io/docs/core/infrastructure/scaling/overview) | Multi-server deployment and externally handled load balancing; Swarm marked deprecated. | Do not use older comparisons claiming every Coolify multi-server setup is Swarm. |
| [Netdata](https://github.com/netdata/netdata), [Glances](https://github.com/nicolargo/glances) | Broad system monitoring and cross-platform resource visibility. | A general monitoring pivot is also crowded; this project's existing inference actions fit a narrower continuation better. No monitoring-overhead comparison was performed. |
| [PAIR license](https://github.com/NVIDIA/Personal-AI-Router/blob/develop/LICENSE), [exo license](https://github.com/exo-explore/exo/blob/main/LICENSE) | Both inspected repository license files identify Apache 2.0. | Record this when investigating code reuse; model assets and dependencies are separate from repository code. No redistribution was performed. |
| [llama.cpp license](https://github.com/ggml-org/llama.cpp/blob/master/LICENSE), [LocalAI license](https://github.com/mudler/LocalAI/blob/master/LICENSE) | Both inspected repository license files identify MIT. | Engine/runtime choice must still be evaluated by capabilities and packaging, not just the repository license label. |

## Research papers

| Primary source | Relevance | Limit |
|---|---|---|
| [Petals, NeurIPS 2023](https://arxiv.org/abs/2312.08361) | Fault-tolerant distributed inference and heterogeneous joining/leaving devices. | Resilience and dynamic load balancing are prior art, not a new claim for this project. |
| [Parallax](https://arxiv.org/abs/2509.26182) | Memory/link-aware allocation plus request-time pipeline selection. | Evaluate its exact action/state unit before claiming a difference in live layer redistribution. |
| [EdgeFlow publisher abstract](https://ieeexplore.ieee.org/document/11619197/) | Hybrid KV transfer/recomputation on a real distributed edge platform. | Abstract accessible; full paper not established as read. No absence claim about its decision policy. |
| [Intel AI PC pipeline shards](https://arxiv.org/html/2608.19147v1) | Compiled consumer-device shards and multi-user interleaving, with reproduction artifact. | Its multi-user versus single-user comparison is not a same-concurrency speedup; do not transplant its numbers. |
| [ATSInfer](https://arxiv.org/html/2607.10183v1) | Fine-grained CPU/GPU placement and load-aware movement on consumer devices. | Single-device offloading differs from networked layer redistribution, but competes for the same user need. |
| [ETCInfer](https://arxiv.org/abs/2609.15230) | Thermal/energy-aware inference control. | Datacenter cooling regime; not evidence about laptop battery life. |
| [EdgeShard](https://arxiv.org/html/2405.14371v1) | Profiled heterogeneous layer placement on physical devices. | Real hardware and DP are established; see previous repository literature memo. |
| [Online migration-cost-aware partitioning](https://arxiv.org/html/2505.02533v1) | Migration cost includes KV state. | Avoid claiming that migration awareness is a new algorithm. |

The previous [novelty memo](NOVELTY_RESEARCH_2026-09-23.md) also maps Llumnix,
ServerlessLLM, CacheGen, SpotServe and BanaServe. This product research does not
turn that focused literature review into an exhaustive novelty search.

## Repository evidence and checks

- `internal/controller/source.go`, `localsource.go`: the controller already runs
  without Kubernetes through a small source contract.
- `internal/partition/partition.go`: exact linear partition under its cost model,
  minimizing the slowest stage; no RAM/VRAM constraints in `Input`.
- `worker/router.py`: sequential per-token stage traversal, bounded replay,
  token-ID interface, no chat text/streaming API.
- `worker/server.py`: one compute lock per worker; assignments also acquire it.
- `worker/server.py:92–108` and `worker/router.py:193`: compute timing starts
  after lock acquisition. RPC duration minus that timing includes queue wait;
  the residual is not a pure link/network measurement under concurrency.
- `worker/backends/qwen3.py`: full-model load before pruning, session KV storage,
  relative measured decoder-speed probe.
- `internal/peerconn/peerconn.go`, Python server/router: insecure RPC transport.
- `cmd/nodeagent/main.go`: a failed requested NVML reader can fall back to simulated
  readings; production telemetry needs explicit unavailable/source states.
- `deploy/standalone/setup-vm.sh`: currently assumes Linux x86_64, sudo, Go builds,
  Python/PyTorch, and model downloads.
- `docs/phase4-partb-findings.md`: real single-process CPU baseline; distributed
  break-even remains a prediction from measured components.
- `docs/journal-benchmark-4cpu-2026-09-13.md`: simulated multi-node-on-one-host
  benchmark; no observed netem speed advantage in the reported configuration.
- Existing partition/controller tests passed in this session. These checks do
  not establish physical-device inference performance.
- [Local probe evidence](data/product-direction-2026-10-04/README.md): 63
  synthetic loopback windows and 1,524 requests, zero request errors. A routing
  correction removed an apparent pipeline throughput advantage; FIFO admission
  also removed a long waiting outlier. No real-model/controller/eBPF gain was
  tested by these probes.
- Built current binaries in `/tmp`: controller approximately 65 MiB, node-agent
  approximately 21 MiB, before inference libraries/model assets. These are this
  environment's unstripped build sizes, not release installer sizes.

## Evidence classification

**Observed code:** directly inspected implementation.
**Local measured:** checks/probes performed in this session, with explicit scope.
**Upstream documented:** source's own description, not independently validated.
**Inference/proposal:** this report's reasoning or suggested future design.
**Unknown:** a material question that requires hardware, users, or deeper source
inspection. Lack of a documented feature does not establish its absence.
