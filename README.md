# KubeEdgeInfer

A closed-loop, eBPF-driven Kubernetes framework for heterogeneous distributed
LLM inference on consumer edge clusters.

Large models are split across machines by pipeline parallelism. Existing
frameworks decide that split **once** and never revisit it — but edge hardware
is not static: GPUs thermally throttle, WiFi latency wanders, nodes die.
KubeEdgeInfer turns the one-time split into a **continuous, self-correcting
decision** driven by kernel-level measurements:

```
   ┌─────────────┐    ┌──────────────┐    ┌──────────────┐    ┌─────────────┐
   │  1. WATCH   │ →  │  2. DECIDE   │ →  │   3. ACT     │ →  │  4. HEAL    │
   │ eBPF + NVML │    │ linear-part. │    │ K8s ctrl re- │    │ heartbeat + │
   │  telemetry  │    │ DP + hyster. │    │ assigns lay- │    │ forced re-  │
   │             │    │              │    │ ers via gRPC │    │ partition   │
   └─────────────┘    └──────────────┘    └──────────────┘    └─────────────┘
          ▲                                                          │
          └────────────────── loop repeats every 2s ─────────────────┘
```

## Components

| Path | Language | Role |
|---|---|---|
| `internal/ebpf` + `cmd/nodeagent` | Go + C (CO-RE BPF) | **WATCH** — `tp_btf/tcp_probe` (per-flow sRTT) + `fentry/tcp_sendmsg` (throughput) filtered to worker ports; GPU/thermal telemetry via a selectable `gpu.Reader`: simulated (default), real CPU thermal (`GPU_MODE=cputherm`, no discrete GPU needed), or real NVML (`GPU_MODE=nvml`, `-tags gpu`) |
| `internal/partition` | Go | **DECIDE** — exact linear-partition DP (O(N²K)) minimizing the bottleneck stage; 15% improvement + 30 s cooldown hysteresis (both tunable live via `IMPROVEMENT_FRAC`/`COOLDOWN_S`) |
| `cmd/controller` + `internal/controller` | Go | **ACT/HEAL** — aggregates telemetry, hot-reassigns layer ranges over gRPC (no pod restarts), tracks state in the `InferencePipeline` CRD; a 3 s stale heartbeat forces repartition across survivors; `PROFILE_ONCE=1` freezes telemetry after the first reading (offline-profiling ablation baseline) |
| `worker/` | Python | Shard workers (pluggable `sim` and `gpt2` backends) + router. Workers are stateless — distributed GPT-2 output is token-identical to single-process HuggingFace. `gpt2` backend runs on `WORKER_DEVICE=auto\|cuda\|cpu` (real CUDA inference if available) |
| `bench/` | Python | Ablation harness: baseline / netem / thermal / node-failure / combo (netem+thermal together) × dynamic / static / profileonly, measuring bubble time (worst-stage idle), tokens/sec, TTFT; plus a hysteresis sweep and a predicted-vs-measured model-fidelity check |
| `scripts/` | Bash | `join-node.sh` / `deploy-real-hardware.sh` — turn a handful of real machines (laptops, GPU boxes) into a k3s cluster running this project, no manual YAML editing |

## Quickstart

Requirements: Linux with BTF (`/sys/kernel/btf/vmlinux`), Docker, kind,
kubectl, Python ≥3.11. (Go, protoc, and clang are only needed when *changing*
the code — images build inside Docker, and the generated gRPC stubs and BPF
object are committed.)

**One command** — builds, deploys, and opens a live dashboard at
<http://localhost:8000> showing the pipeline, per-stage utilization, node
telemetry, eBPF flow sRTTs, and a repartition event log, with buttons to
inject/clear a thermal fault and watch the loop heal:

```bash
./run-demo.sh
```

Or step by step:

```bash
make proto          # regenerate Go + Python gRPC stubs (optional: generated
                    # stubs are committed; only needed after editing proto/,
                    # requires protoc + protoc-gen-go{,-grpc} + grpcio-tools)
make test           # partitioner unit tests (incl. brute-force cross-check)
make images         # build worker / nodeagent / controller images
make cluster-up     # kind cluster: 1 control-plane + 3 workers
make deploy         # CRD, RBAC, workers, node agents, controller, pipeline CR

kubectl -n kubeedgeinfer get ipl demo        # watch assignments in the CRD
kubectl -n kubeedgeinfer port-forward svc/router 8080:8080 &
curl -X POST localhost:8080/generate -d '{"prompt_len":16,"max_new_tokens":8}'
```

Watch the loop react (thermal example — layers migrate off the hot node
within ~35 s and return after it cools):

```bash
W2=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' kubeedgeinfer-worker2)
curl -X POST http://$W2:9101/gpu/override -d '{"temp_c": 92}'   # inject
curl -X POST http://$W2:9101/gpu/override -d '{"clear": true}'  # recover
```

## Evaluation

```bash
python3 bench/run.py --all   # 8 runs: 4 scenarios x {dynamic, static}
python3 bench/plot.py        # PNGs + summary in bench/results/
```

Scenarios: **baseline** (steady load), **netem** (80 ms `tc netem` delay on a
node), **thermal** (simulated GPU throttle to 0.4× speed), **failure**
(`docker stop` a node), **combo** (netem + thermal injected simultaneously,
to exercise the "one hysteresis-gated trigger, multiple fault classes"
claim). The static baseline is the same controller with `STATIC_MODE=1`: one
equal split, no repartitioning, no healing. A third mode, `profileonly`
(`--mode profileonly`), repartitions like dynamic but freezes its telemetry
inputs at the first reading — an ablation approximating an offline-profiling
system (à la EdgeShard/PipeEdge/Galaxy) built from KubeEdgeInfer's own
DP/apply machinery, isolating the value of *continuous* telemetry
specifically.

```bash
python3 bench/run.py --sweep-hysteresis netem   # improvement x cooldown grid
python3 bench/plot_sweep.py                     # results/hysteresis_sweep.png
python3 bench/fidelity.py                       # predicted vs. measured bottleneck cost
```

The fidelity check needs no new run — it correlates the DP's own predicted
per-token cost against measured `1000/tokens_per_sec` from data any dynamic
run already collected.

GPT-2 correctness proof (3-stage distributed vs single-process greedy):

```bash
python3 bench/verify_gpt2.py          # prints MATCH on token-identical output
```

To run the real model in-cluster: `docker build --build-arg WITH_GPT2=1 ...`
for the worker image, then set `backend: gpt2` in `deploy/manifests/pipeline.yaml`.
Add `--build-arg WITH_CUDA=1` and set `WORKER_DEVICE=cuda` on the worker
DaemonSet to run real CUDA inference on a GPU node instead of CPU.

## Running on real hardware

`make cluster-up` gives you a single-host kind cluster: real eBPF, but
loopback-speed "network" and a simulated GPU. To get real inter-node latency
and real thermal telemetry, point this at actual separate machines instead —
laptops, GPU boxes, whatever's on the LAN:

```bash
# on the machine that becomes the k3s server:
./scripts/join-node.sh server

# on every other machine (prints the exact command to use):
./scripts/join-node.sh agent <server-ip> <token>

# back on the server, once all nodes are joined and labeled:
./scripts/deploy-real-hardware.sh
```

This builds and distributes GPU-enabled images automatically (CUDA torch
wheel for the worker, `-tags gpu` NVML build for the node agent) and sets
`GPU_MODE=nvml` / `WORKER_DEVICE=cuda` once it detects GPU-labeled nodes; on
GPU-less machines it falls back to `GPU_MODE=cputherm`, which reads real
`/sys/class/thermal` state and derates speed on genuine CPU throttling — a
real-hardware option for laptops with no discrete GPU. Two machines is
enough for real netem + thermal data; the failure/healing scenario needs a
third node (any kind) so there's a "surviving nodes" set to redistribute
onto. Note: GPT-2 is small enough (~500MB) that even an 8GB GPU won't come
close to thermal throttling under light load — real NVML telemetry will be
genuine but likely flat; sustained concurrent load (raise `LOAD_THREADS` in
`bench/run.py`, or run a companion GPU-stress workload during the fault
window) is what it takes to see real throttling on modern hardware.

### Running on rented online GPUs

If you rent a GPU machine (Runpod/Lambda/Paperspace/etc.), the fastest path is:

```bash
./scripts/join-node.sh server
WITH_GPT2=1 ./scripts/deploy-real-hardware.sh
kubectl apply -f deploy/manifests/workers-singlenode.yaml
```

Then set `backend: gpt2` in the `InferencePipeline` and verify `device=cuda`
in worker logs plus real NVML telemetry from the node agent. Important caveat:
many rented offerings are unprivileged containers, not full VMs; if
`./scripts/join-node.sh server` reports the host is not privileged, k3s cannot
run there. In that case use the non-Kubernetes fallback:

```bash
./scripts/run-single-gpu.sh
```

For the full worked walkthrough, see `docs/single-gpu.md`.

## Design notes

- **eBPF telemetry is real** (not simulated): CO-RE programs compiled against
  the host's BTF, loaded with cilium/ebpf from a privileged DaemonSet. kind
  nodes share the host kernel, so tracepoints are kernel-global — flow keys
  carry the source IP and the controller attributes flows to pods. Dual-stack
  gRPC sockets carry IPv4 as v4-mapped IPv6, which the BPF program unwraps.
- **GPU telemetry is simulated by default here** (no GPU in CI/codespaces):
  the node agent models temperature relaxing toward ambient + k·load with
  throttle hysteresis, fed by the worker's real busy fraction — sustained
  inference genuinely heats the simulated card. The `gpu.Reader` interface
  has two real-hardware implementations: NVML (`-tags gpu`, `GPU_MODE=nvml`)
  for machines with an NVIDIA GPU, and CPU-thermal (`GPU_MODE=cputherm`,
  reads `/sys/class/thermal`) for machines without one — most laptops
  thermal-throttle their CPU under sustained load with the same dynamics a
  GPU throttles under, so the same `Reader`/derate abstraction applies
  unchanged. See "Running on real hardware" above.
- **Model fidelity**: the DP's predicted per-token bottleneck cost tracks
  measured cost with a stable ~3.0-3.24× ratio across every scenario tested
  (`bench/fidelity.py`) — the cost model gets *relative* bottleneck
  placement right (what the DP needs to choose the correct partition) but
  underestimates *absolute* latency by a roughly constant factor, likely
  gRPC/interpreter overhead not in the cost model. Treat the DP's bottleneck
  number as a ranking signal, not a calibrated latency prediction.
- **Optimality**: for a fixed telemetry snapshot the DP solves the classical
  linear partition problem exactly (unit-tested against brute force, 200
  randomized instances).
- **Topology**: the router drives stages hub-and-spoke; the partitioner's
  per-hop cost is the measured sRTT into each stage's pod.
- **Consistency**: every assignment carries a generation. Workers reject
  stale-generation forwards; the router then refetches the layout and replays
  the full accumulated context (workers are stateless, so replay is trivially
  correct).
