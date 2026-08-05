# Running on one GPU machine (worked example: a single L4)

Commands for a **single** machine with one NVIDIA GPU. Run everything on that
machine.

## What one GPU box gives you (and what it doesn't)

| Claim | One L4 box |
|---|---|
| Real CUDA inference, real GPT-2 tokens | **Yes** |
| Real NVML thermal/throttle telemetry | **Yes** |
| Pipeline parallelism, token-identical output | **Yes** |
| Real inter-node network latency | No — every hop is loopback |
| Cross-node repartitioning being *useful* | Limited — all shards share one GPU, so a throttle slows all of them equally and moving layers between them cannot help |
| Node-failure healing | No — needs multiple machines |

So use the L4 for the **"real model on real GPU hardware"** claims, and keep
the kind demo (or a second machine, see `two-laptops.md`) for the
**control-loop** claims. Adding any second machine later turns the network
and healing rows into "yes".

## 0. Check the driver — and whether Kubernetes can run here

```bash
nvidia-smi                       # must print your L4
git clone https://github.com/karnati-praveen/ebpf- && cd ebpf-
```

Rented GPU boxes are often **containers**, not VMs, and k3s needs a
privileged one. Check before you start:

```bash
[ -d /run/systemd/system ] && echo "systemd: yes" || echo "systemd: no (container)"
ip link add dummy0 type dummy 2>/dev/null \
  && { echo "privileged: yes"; ip link del dummy0; } \
  || echo "privileged: NO -- k3s will not run here"
```

The scripts handle "no systemd" (they start k3s directly) and running as
root without `sudo`. But if **privileged is NO**, Kubernetes cannot run on
that box at all — use the no-Kubernetes fallback at the bottom of this
document, which still gives you real GPT-2 on the real GPU.

## 1. Install k3s, detect the GPU, label the node

```bash
./scripts/join-node.sh server
```

This installs k3s and nvidia-container-toolkit, and labels the node
`kubeedgeinfer.io/worker=true` plus `kubeedgeinfer.io/gpu=true`.

## 2. Build GPU images and deploy

`WITH_GPT2=1` pulls the CUDA torch wheel (~1GB, several minutes) and turns on
NVML telemetry + CUDA inference:

```bash
WITH_GPT2=1 ./scripts/deploy-real-hardware.sh
```

## 3. Give the node agent GPU visibility (needed for real NVML)

The agent runs on a minimal image; the NVIDIA runtime is what injects
`libnvidia-ml.so`. Without this it logs a warning and silently falls back to
the simulated thermal model.

```bash
kubectl -n kubeedgeinfer patch ds keinfer-nodeagent \
  -p '{"spec":{"template":{"spec":{"runtimeClassName":"nvidia"}}}}'
kubectl -n kubeedgeinfer set env ds/keinfer-nodeagent \
  NVIDIA_VISIBLE_DEVICES=all NVIDIA_DRIVER_CAPABILITIES=compute,utility

# verify -- must say "real NVML", not "falling back to sim"
kubectl -n kubeedgeinfer logs ds/keinfer-nodeagent | grep -i 'gpu telemetry'
```

## 4. Run 3 shards on the one GPU

The default worker is a DaemonSet (one pod per node), which on a single
machine gives a one-stage pipeline with nothing to partition. Swap it for a
Deployment whose replicas share the L4:

```bash
kubectl -n kubeedgeinfer delete ds keinfer-worker --ignore-not-found
kubectl apply -f deploy/manifests/workers-singlenode.yaml
kubectl -n kubeedgeinfer get pods -w      # 3 shards + router + controller
```

(On a single node the deploy script imports images straight into k3s's
containerd, so the manifests use plain `kubeedgeinfer/*:dev` tags with no
registry prefix.)

## 5. Switch to the real model

```bash
kubectl -n kubeedgeinfer patch inferencepipeline demo --type=merge \
  -p '{"spec":{"backend":"gpt2","workers":3}}'
```

## 6. Watch it

```bash
kubectl -n kubeedgeinfer port-forward svc/router 18080:8080 &
kubectl -n kubeedgeinfer port-forward svc/controller 18081:8081 &
python3 demo/serve.py            # http://localhost:8000
```

Real tokens, end to end:

```bash
curl -s -X POST localhost:18080/generate \
  -d '{"input_ids":[15496,11,616,1438,318],"max_new_tokens":10}'
```

With `backend: gpt2` the `tokens` array is real GPT-2 output (it is all zeros
only under the `sim` backend). Prove it matches single-process HuggingFace:

```bash
python3 bench/verify_gpt2.py     # prints MATCH
```

Confirm the GPU is actually working:

```bash
nvidia-smi                       # 3 python processes holding memory
kubectl -n kubeedgeinfer logs deploy/keinfer-worker-shard | grep device=
                                 # "device=cuda", not device=cpu
```

## Seeing real throttling

An L4 running GPT-2 (~500 MB, greedy decoding) will barely warm up. To get
real thermal movement, raise concurrency (`LOAD_THREADS` in `bench/run.py`)
and/or run a companion GPU stress job during the fault window. Flat, cool
curves are still a legitimate real-hardware result — just report them as
"no throttling observed under this load" rather than implying a dramatic one.

## Fallback: no Kubernetes at all

If the box is an unprivileged container, k3s cannot run. You can still get
the thing the GPU is actually for — real GPT-2 sharded across a real
pipeline on the real device:

```bash
pip install grpcio protobuf numpy torch transformers
./scripts/run-single-gpu.sh                  # 3 shards, GPT-2, uses the GPU
```

Then:

```bash
curl -s -X POST localhost:8080/generate \
  -d '{"input_ids":[15496,11,616,1438,318],"max_new_tokens":10}'
nvidia-smi                                   # 3 python processes on the GPU
```

What you lose without Kubernetes: the controller, and therefore telemetry,
repartitioning, and healing — the split is fixed at startup. Keep using the
kind demo (`./run-demo.sh`) for those claims and this box for the
"real model on real GPU" claim.

## Troubleshooting

**Shards `Pending`.** Something is requesting `nvidia.com/gpu`; one L4 is a
single allocatable device so only one pod would get it. The manifest here
deliberately requests no GPU resource.

**`RuntimeClass "nvidia" not found`.** The nvidia runtime is already the
default — delete the `runtimeClassName: nvidia` line from
`workers-singlenode.yaml` and re-apply.

**Worker crashes with `WORKER_DEVICE=cuda but torch.cuda.is_available() is
False`.** The GPU isn't visible inside the container: check step 3's env vars
and that the image was built with `WITH_CUDA=1` (i.e. `WITH_GPT2=1` with a
GPU-labeled node).
