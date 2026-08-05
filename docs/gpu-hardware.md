# Testing on real GPUs (worked example: RTX 4070 8GB + RTX 5050 8GB)

## Can you test this? Yes.

Two machines with those cards is genuinely a good testbed — better than
this sandbox in every dimension that matters for the project's claims:
real network latency between two physical hosts, and (once wired up, see
below) real GPU compute and real NVML thermal telemetry instead of a
simulated model. Nothing about the architecture assumes datacenter hardware
— eBPF, the DP partitioner, and the K8s control loop are all commodity-Linux
software.

**What was NOT true until this session, and now is:** the GPT-2 worker
never actually used a GPU even when one was available — `worker/backends/gpt2.py`
had no `.to(device)` call anywhere, it was hardcoded CPU (`torch.set_num_threads(1)`).
Plugging in a 4070 would previously have gotten you real *temperature*
readings via NVML but the model would still run on CPU. This is now fixed:
the backend picks a device via `WORKER_DEVICE` (`auto` by default — uses
CUDA if `torch.cuda.is_available()`, else CPU) and moves the model and every
tensor across the forward pass onto it.

## The one honest caveat: GPT-2 won't stress an 8GB card

GPT-2 (124M params, fp32) is about 500MB. An RTX 4070 or 5050 with 8GB VRAM
has roughly 16x that headroom for a *single* shard — even running the whole
unsharded model on one of these cards leaves it nowhere near memory
pressure, and greedy single-request decoding won't sustain enough SM
utilization to meaningfully heat the die. Two consequences:

1. **You will get real NVML numbers, but may not see real throttling.**
   Modern desktop-class cooling on a 4070/5050 laptop or desktop is
   unlikely to hit its throttle point running something this small. Expect
   flat, cool temperature curves — which is itself a valid (if undramatic)
   real-hardware data point: "no throttling observed under light real load"
   is a legitimate finding, just not a dramatic plot.
2. **This is actually your best opportunity to fix the eval-rigor gap
   against EdgeShard** (which used real Llama2-7B/13B/70B on 15 physical
   devices — see the novelty report). Two 8GB cards = 16GB combined VRAM,
   comfortably enough to split a real small modern LLM (Llama 3.2 1B is
   ~2.5GB in fp16, 3B is ~6GB) across two pipeline stages. That's a real
   punch-list item 5 win, not just a GPU-utilization checkbox. Implementing
   a Llama backend (`worker/backends/llama.py`, same shape as `gpt2.py` —
   load a contiguous slice of `model.model.layers`, same stateless-replay
   design) is the natural next step if you want to go further than this
   session did; it wasn't done here since it's a genuinely new component,
   not a fix to an existing one.

To get *some* real thermal signal out of GPT-2 specifically: increase
`LOAD_THREADS` in `bench/run.py` (more concurrent generation streams raises
sustained GPU utilization) and/or run a companion GPU stress tool
(`gpu-burn`, or even a second unrelated CUDA workload) during the fault
window to simulate "something else on this shared machine is loading the
GPU" — a legitimate, common experimental design pattern, and arguably more
representative of a real multi-tenant edge box than expecting GPT-2 alone to
heat a discrete GPU.

## How: three commands, not a manual walkthrough

This was the actual ask — simplify it so anyone can run it, not just
someone comfortable hand-editing Kubernetes YAML. Two scripts do the whole
thing:

**On your machine (becomes the k3s server):**
```bash
./scripts/join-node.sh server
```
Prints a join command — send it to your friend.

**On each of your friend's two GPU machines:**
```bash
./scripts/join-node.sh agent <the-ip-and-token-it-printed>
```
Auto-detects the GPU via `nvidia-smi`, installs `nvidia-container-toolkit`
if missing, joins the cluster.

**Back on your machine, label the two GPU nodes** (the agent script prints
the exact command to run — it's just `kubectl label node <name>
kubeedgeinfer.io/worker=true kubeedgeinfer.io/gpu=true`), then:
```bash
./scripts/deploy-real-hardware.sh
```
This builds the CUDA-enabled worker image and the NVML-enabled node-agent
image, spins up a throwaway local Docker registry so the images reach every
machine, and deploys with `GPU_MODE=nvml` + `WORKER_DEVICE=cuda` set
automatically once it sees GPU-labeled nodes. It pauses once to ask you to
paste a small `registries.yaml` snippet on each machine (k3s's containerd
needs to trust the local registry — this is the one step that can't be
fully automated without assuming SSH access to machines you don't own).

Total manual YAML editing required: zero. Total machines needed: 2 is
enough for real netem + real thermal data (see `docs/laptops.md` for why 3
is needed specifically for the failure/healing scenario — you need a third
node, GPU or not, for there to be "surviving nodes" to redistribute onto).

## Verifying it actually used the GPU

```bash
kubectl -n kubeedgeinfer logs -l app=keinfer-worker | grep "loading gpt2"
# should show: loading gpt2 blocks [...] on device=cuda
```
If it says `device=cpu` on a GPU-labeled node, `WORKER_DEVICE=cuda` wasn't
picked up (check `kubectl -n kubeedgeinfer set env ds/keinfer-worker
WORKER_DEVICE=cuda` actually applied) or the CUDA torch wheel didn't
install (check the worker image was built with `WITH_CUDA=1`).

```bash
curl -s http://<gpu-node-ip>:9101/gpu | python3 -m json.tool
# temp_c should be a real, plausible number (not the simulated model's
# smooth ambient+k*load curve) and should visibly respond to nvidia-smi
# showing a concurrent workload on the same card.
```
