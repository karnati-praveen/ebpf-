# Running KubeEdgeInfer across real laptops

The kind cluster in this repo runs everything as containers on one host —
useful for development, but it fakes two of the three signals the project's
novelty depends on: network latency (via `tc netem`, not real WiFi) and GPU
thermal throttling (via a simulated model, not real hardware heat). This doc
is the concrete path to a testbed where both are real, using consumer
hardware you already own instead of a datacenter GPU lab — which is the
whole point of the project.

## Why not just scale up kind

kind's multi-node clusters are multiple containers on **one kernel and one
NIC**. The eBPF programs are real, but every "node" shares the same physical
CPU package and the same loopback-speed network — so there is no real
thermal isolation between "nodes" and no real WiFi variance to measure.
Moving to actual separate machines is a Kubernetes distribution change, not
a code change: none of `internal/`, `worker/`, or the CRD care whether a
node is a kind container or a physical laptop on the same LAN.

## Recommended distribution: k3s

[k3s](https://k3s.io) is a single ~70MB binary, needs no separate etcd
cluster for a handful of nodes, and — critically — ships a CNI and works
fine on constrained laptops (2GB RAM minimum). `kubeadm` also works if you
already run it; k3s is recommended here purely because it's the fastest path
from "four laptops on a LAN" to "a working cluster."

### 1. Pick a control-plane laptop and join the rest

On the control-plane machine:

```bash
curl -sfL https://get.k3s.io | sh -
sudo cat /var/lib/rancher/k3s/server/node-token   # copy this
```

On each worker laptop (needs the control-plane's LAN IP and the token above):

```bash
curl -sfL https://get.k3s.io | \
  K3S_URL=https://<control-plane-ip>:6443 \
  K3S_TOKEN=<token> sh -
```

Label the workers exactly as `deploy/kind-config.yaml` does for kind, so the
existing manifests' `nodeSelector` keeps working unchanged:

```bash
kubectl label node <worker-hostname> kubeedgeinfer.io/worker=true
```

Pull the kubeconfig to your workstation:

```bash
scp control-plane:/etc/rancher/k3s/k3s.yaml ~/.kube/config
sed -i "s/127.0.0.1/<control-plane-ip>/" ~/.kube/config
```

### 2. BTF and eBPF requirements per laptop

Every worker laptop needs `/sys/kernel/btf/vmlinux` (kernel ≥5.8 with
`CONFIG_DEBUG_INFO_BTF=y`, true of most distro kernels since ~2021) and a
mounted tracefs — the same requirement the kind nodes already satisfy by
sharing the codespace host kernel. Check with:

```bash
ls /sys/kernel/btf/vmlinux   # must exist
mount | grep tracefs || sudo mount -t tracefs tracefs /sys/kernel/tracing
```

The node-agent DaemonSet is already `privileged: true` with `hostNetwork:
true` (see `deploy/manifests/nodeagent.yaml`) — required for the CO-RE eBPF
attach and for tcpmon to see real inter-node traffic. No changes needed
there; the same manifest applies to k3s nodes.

### 3. Build images for the right architecture

Laptops are frequently a mix of x86_64 and arm64 (Apple Silicon, some
Chromebooks). Build multi-arch and push to a registry both machines can
reach (a local one is fine — e.g. `docker run -d -p 5000:5000 registry:2` on
the control-plane laptop):

```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  -t <control-plane-ip>:5000/kubeedgeinfer/worker:dev \
  -f deploy/docker/worker.Dockerfile --push .
# repeat for nodeagent.Dockerfile and controller.Dockerfile
```

Update the `image:` fields in `deploy/manifests/*.yaml` to point at that
registry instead of the bare `kubeedgeinfer/*:dev` tags kind resolves
locally via `kind load docker-image`.

### 4. Turn on real telemetry

Two independent env-var switches (added specifically to support this):

**Real network latency** — nothing to switch on; the moment nodes are on
separate physical machines connected by real WiFi/Ethernet, `tp_btf/tcp_probe`
measures genuine sRTT instead of loopback-speed localhost traffic. This is
the free win of moving off kind.

**Real thermal telemetry** — most laptops have no discrete NVIDIA GPU, so
`GPU_MODE=nvml` doesn't apply to them; instead use the CPU-thermal reader
added for exactly this case, which reads `/sys/class/thermal` and derates
speed on real CPU package throttling (Intel/AMD laptop CPUs throttle under
sustained load exactly like a GPU does — same physics, same control problem):

```bash
kubectl -n kubeedgeinfer set env ds/keinfer-nodeagent GPU_MODE=cputherm
```

Tune the throttle thresholds to your actual chassis if the defaults
(throttle at 85°C, recover at 78°C, derate to 0.5×) don't match — check what
your laptop actually does under load first:

```bash
watch -n1 'cat /sys/class/thermal/thermal_zone*/temp'  # while running a CPU stress test
kubectl -n kubeedgeinfer set env ds/keinfer-nodeagent \
  CPU_THROTTLE_C=<observed throttle temp> \
  CPU_UNTHROTTLE_C=<observed recovery temp>
```

If a laptop *does* have an NVIDIA GPU (some Windows/Linux gaming laptops),
build the nodeagent image with `-tags gpu` (`make images` doesn't do this by
default — add the tag in `deploy/docker/nodeagent.Dockerfile`'s `go build`
line) and set `GPU_MODE=nvml` on that node only; mixed-fleet is fine, the
`Reader` interface is per-node.

### 5. Sustain real load to actually observe throttling

Consumer laptop CPUs/GPUs often don't reach their throttle point from a
single request at a time — you need `bench/run.py`'s sustained
multi-threaded load (`LOAD_THREADS = 3` by default) for long enough that
your chassis's actual thermal time constant (usually 60-300s, much slower
than the simulated model's 20s `TauS`) plays out. Increase scenario
durations in `bench/run.py`'s `SCENARIOS["thermal"]` fault phase from 60s to
match your hardware if 60s isn't enough to see real throttling.

### 6. What changes about the results

Once this is running: the plots you already have (netem/thermal/failure vs.
static) become the *real-hardware* validation item 3 from the novelty
punch list, not a simulated stand-in — directly answering the reviewer
question "is any of this measured on real hardware?" Re-run
`python3 bench/run.py --all` unchanged; the harness doesn't know or care
whether `NODE_MID`/`NODE_LAST` are kind containers or laptop hostnames, as
long as `docker exec <node> tc qdisc ...` in `bench/run.py`'s `netem_start`
is replaced with an SSH-based equivalent (kind's fault injection uses
`docker exec` because the "nodes" are containers; on real laptops that
becomes `ssh <node> sudo tc qdisc ...` — the one part of the harness that is
kind-specific and needs a one-line swap for a physical testbed).

## Minimum viable version: two laptops

You don't need four machines to get real signal. Two laptops (one
control-plane + one worker, or both as workers with a k3s control-plane
elsewhere/in a VM) already gives you: real network RTT between exactly two
points, and real thermal throttling on whichever one you load. That's
enough to regenerate the `netem` and `thermal` ablation plots with genuine
hardware backing — the `failure` scenario needs at least 3 worker nodes
(the pipeline is a 3-stage split) to have a "surviving nodes" set for HEAL
to redistribute onto.
