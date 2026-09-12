#!/usr/bin/env python3
"""Build the KubeEdgeInfer code + live-demo deck (section 11).

    python3 ppt/make_code_deck.py

Kept separate from the main deck so it can be driven at demo speed, with the
full Docker / VM / cluster configuration in one place.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from deckkit import *                                            # noqa: F401,F403
from deckkit import _emit
from pptx.enum.text import PP_ALIGN

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "ppt", "KubeEdgeInfer_Code_Demo.pptx")

prs = new_deck()

# ===========================================================================
title_slide(
    prs,
    "Code & Live Demo",
    "Repository walkthrough, full Docker / VM / cluster configuration, and the "
    "exact commands run during the demonstration",
    [
        "KubeEdgeInfer  ·  Karnati Praveen",
        "github.com/karnati-praveen/ebpf-",
        "Companion to the main presentation",
    ],
    kicker="SECTION 11  ·  DEMO DECK",
)

# ---------------------------------------------------------------- map ------
s, y = slide(prs, "Repository map", kicker="Code Walkthrough",
             subtitle="Where each stage of the WATCH - DECIDE - ACT - HEAL "
                      "loop actually lives.")
code_box(s, MARGIN, y, 6.15, 4.45, """ebpf-/
├── proto/pipeline.proto        gRPC contract (Worker, Router, Telemetry)
├── internal/
│   ├── ebpf/bpf/tcpmon.c       WATCH  - CO-RE BPF programs
│   ├── ebpf/                   cilium/ebpf loader + flow map reader
│   ├── partition/              DECIDE - exact DP + hysteresis Decider
│   ├── controller/             ACT/HEAL - reconcile loop, CRD status
│   └── gpu/                    sim.go | cputherm.go | nvml.go
├── cmd/
│   ├── nodeagent/              per-node DaemonSet binary
│   └── controller/             cluster controller binary
├── worker/
│   ├── server.py               stateless shard worker
│   ├── router.py               HTTP front door + stage driver
│   └── backends/               sim | gpt2
├── deploy/
│   ├── docker/*.Dockerfile     three images
│   ├── manifests/*.yaml        namespace, CRD, RBAC, workloads
│   └── kind-config.yaml        1 control-plane + 3 workers
├── bench/                      ablation harness, plots, verification
├── demo/                       live dashboard (serve.py + dashboard.html)
├── scripts/                    real-hardware deployment
└── run-demo.sh                 one command: build → deploy → dashboard""",
         size=9.5)
bullets(s, MARGIN + 6.6, y - 0.05, 6.1, [
    (0, "**Go** for anything in the control path - the node agent, the "
        "partitioner and the controller. Static binaries, distroless images."),
    (0, "**C (CO-RE BPF)** for the two kernel programs. Compiled against the "
        "host BTF; the generated object is committed so a clone builds without "
        "clang."),
    (0, "**Python** for the data path - shard workers and router - because the "
        "gpt2 backend is HuggingFace transformers."),
    (0, "**Generated gRPC stubs are committed** (gen/, worker/gen/) so "
        "`git clone && ./run-demo.sh` works with no protoc toolchain."),
    (0, "3 images total: worker, controller, nodeagent."),
], size=12.5, gap=10)

# ------------------------------------------------------------ one command --
s, y = slide(prs, "The demo in one command", kicker="Live Demo",
             subtitle="What ./run-demo.sh does, in order.")
code_box(s, MARGIN, y, 6.3, 1.5, """$ git clone https://github.com/karnati-praveen/ebpf-
$ cd ebpf-
$ ./run-demo.sh

# then open http://localhost:8000""", size=12)
steps = [
    ("1", "Preflight", "checks Docker, kind, kubectl, Python and BTF"),
    ("2", "Build", "three images, only if they are not already present"),
    ("3", "Cluster", "kind create cluster - 1 control-plane + 3 workers"),
    ("4", "Deploy", "namespace, CRD, RBAC, workers, node agents, controller, CR"),
    ("5", "Wait", "blocks until every pod reports Ready"),
    ("6", "Forward", "self-healing port-forwards for router :18080 and "
                     "controller :18081"),
    ("7", "Dashboard", "serves demo/dashboard.html on :8000 with a built-in "
                       "load generator"),
]
yy = y + 1.78
for n, head, what in steps:
    rect(s, MARGIN, yy, 0.34, 0.34, fill=WASH)
    tf = tb(s, MARGIN, yy + 0.07, 0.34, 0.26)
    para(tf, n, size=10, color=BLUE, bold=True, align=PP_ALIGN.CENTER,
         first=True, after=0)
    tf = tb(s, MARGIN + 0.5, yy + 0.03, 1.25, 0.3)
    para(tf, head, size=12, color=NAVY, bold=True, first=True, after=0)
    tf = tb(s, MARGIN + 1.85, yy + 0.04, 4.4, 0.4)
    para(tf, what, size=11, color=MUTED, first=True, after=0, spacing=1.14)
    yy += 0.40

rect(s, MARGIN + 6.75, y, 5.95, 4.4, fill=WHITE, line=LINE)
tf = tb(s, MARGIN + 6.98, y + 0.2, 5.5, 0.3)
para(tf, "WHAT THE DASHBOARD SHOWS (2 s POLL)", size=10, color=BLUE, bold=True,
     first=True, after=8)
panels = [
    ("Generation & bottleneck", "current assignment version and the DP's "
                                "predicted bottleneck in ms"),
    ("Layer assignment", "stacked bar - which node holds which layer range, "
                         "updating live on repartition"),
    ("Tokens/sec and TTFT", "windowed over the last ~12 s of polls, so the "
                            "numbers move every tick"),
    ("Per-stage utilisation", "busy fraction per shard - the bubble-time "
                              "source"),
    ("Node telemetry", "temperature, throttle state and effective speed "
                       "factor per node"),
    ("eBPF flow table", "live per-flow sRTT straight out of the BPF map"),
    ("Event log", "every repartition decision, with the reason"),
    ("Fault buttons", "inject / clear a thermal fault without leaving the "
                      "page"),
]
yy = y + 0.56
for head, what in panels:
    rect(s, MARGIN + 6.98, yy + 0.09, 0.07, 0.07, fill=BLUE)
    tf = tb(s, MARGIN + 7.2, yy, 5.15, 0.46)
    p = para(tf, head + " — ", size=11, color=NAVY, bold=True, first=True,
             after=0, spacing=1.16)
    _emit(p, what, 11, MUTED, SANS, False, False)
    yy += 0.47

# ===========================================================================
# CONFIGURATION
# ===========================================================================
section_slide(prs, "CONFIGURATION", "Docker, VM and cluster",
              "Every configuration file used to produce the results in the "
              "main deck.")

s, y = slide(prs, "Host / VM configuration", kicker="Configuration",
             subtitle="The machine the reported results were measured on - "
                      "read directly off the box.")
code_box(s, MARGIN, y, 6.3, 2.55, """$ uname -a
Linux codespaces-831891 6.8.0-1052-azure #58~22.04.1-Ubuntu
  SMP Thu Mar 26 05:02:21 UTC 2026 x86_64 GNU/Linux

$ cat /etc/os-release | head -1
PRETTY_NAME="Ubuntu 24.04.4 LTS"

$ lscpu | grep "Model name"
Model name:   AMD EPYC 7763 64-Core Processor
$ nproc
2
$ free -h | head -2
              total   used   free  shared  buff/cache
Mem:          7.8Gi  3.3Gi  160Mi    97Mi      4.7Gi""", size=10)
code_box(s, MARGIN + 6.75, y, 5.95, 2.55, """$ ls -la /sys/kernel/btf/vmlinux
-r--r--r-- 1 root root 6020051  /sys/kernel/btf/vmlinux
# BTF present -> CO-RE eBPF is supported

$ docker info | grep -E 'Version|Driver|Cgroup'
Server Version:   29.3.0-1
Storage Driver:   overlayfs
Cgroup Driver:    cgroupfs
Cgroup Version:   2
Kernel Version:   6.8.0-1052-azure

$ kind --version      kind version 0.29.0
$ kubectl version     Client Version: v1.35.2
$ go version          go1.26.1 linux/amd64
$ python3 --version   Python 3.12.1""", size=10)
callout(s, MARGIN, y + 2.82, BODY_W, 1.55,
        "Two constraints follow from this box and shape the whole evaluation. "
        "**BTF is present**, so the real CO-RE eBPF programs load and the "
        "WATCH stage is genuine. But there is **no GPU and only 2 vCPU**, so "
        "GPU telemetry defaults to the simulated Reader and every kind node "
        "shares one kernel over loopback. That is exactly why the main deck "
        "reports the single-host testbed as a stated limitation rather than "
        "claiming real inter-node network measurements.",
        accent=ORANGE, size=13, label="what this hardware does and does not prove")

# ------------------------------------------------------------- docker ------
s, y = slide(prs, "Docker image configuration: worker",
             kicker="Configuration")
code_box(s, MARGIN, y, 7.3, 4.4, """FROM python:3.12-slim

ARG WITH_GPT2=0
ARG WITH_CUDA=0
ARG TORCH_CUDA_INDEX=https://download.pytorch.org/whl/cu121

WORKDIR /app
COPY worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \\
    if [ "$WITH_GPT2" = "1" ] && [ "$WITH_CUDA" = "1" ]; then \\
      pip install --no-cache-dir \\
        --index-url ${TORCH_CUDA_INDEX} torch && \\
      pip install --no-cache-dir transformers; \\
    elif [ "$WITH_GPT2" = "1" ]; then \\
      pip install --no-cache-dir \\
        --index-url https://download.pytorch.org/whl/cpu torch && \\
      pip install --no-cache-dir transformers; \\
    fi

COPY worker/ /app/
CMD ["python3", "server.py"]

# requirements.txt
#   grpcio>=1.60   protobuf>=4.25   numpy>=1.26""",
         size=10, caption="deploy/docker/worker.Dockerfile")
bullets(s, MARGIN + 7.75, y - 0.05, 4.95, [
    (0, "**Torch is opt-in at build time.** The default image carries only "
        "grpcio, protobuf and numpy, so the ablation matrix builds in seconds "
        "on the sim backend."),
    (0, "**WITH_GPT2=1** adds the CPU torch wheel plus transformers for the "
        "real-model runs."),
    (0, "**WITH_CUDA=1** swaps in the cu121 wheel instead. The base image stays "
        "python:3.12-slim either way - the host NVIDIA driver plus "
        "nvidia-container-toolkit is what exposes the device; the wheel just "
        "bundles the CUDA runtime it links against."),
    (0, "Built as:", INK),
], size=12, gap=9)
code_box(s, MARGIN + 7.75, y + 3.35, 4.95, 1.0, """docker build \\
  --build-arg WITH_GPT2=1 \\
  --build-arg WITH_CUDA=1 \\
  -t kubeedgeinfer/worker:dev \\
  -f deploy/docker/worker.Dockerfile .""", size=9.5)

# ---------------------------------------------------------------------------
s, y = slide(prs, "Docker images (2 / 2): controller & node agent",
             kicker="Configuration")
code_box(s, MARGIN, y, 6.1, 2.3, """FROM golang:1.26 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /controller ./cmd/controller

FROM gcr.io/distroless/static-debian12
COPY --from=build /controller /controller
ENTRYPOINT ["/controller"]""", size=10.5,
         caption="deploy/docker/controller.Dockerfile")
code_box(s, MARGIN, y + 2.55, 6.1, 2.0, """FROM golang:1.26 AS build
WORKDIR /src
ARG GO_BUILD_TAGS=""
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN if [ -n "$GO_BUILD_TAGS" ]; then \\
      CGO_ENABLED=1 go build -tags "$GO_BUILD_TAGS" \\
        -o /nodeagent ./cmd/nodeagent; \\
    else \\
      CGO_ENABLED=0 go build -o /nodeagent ./cmd/nodeagent; \\
    fi

FROM gcr.io/distroless/base-debian12
COPY --from=build /nodeagent /nodeagent
ENTRYPOINT ["/nodeagent"]""", size=10.5,
         caption="deploy/docker/nodeagent.Dockerfile")
bullets(s, MARGIN + 6.55, y - 0.05, 6.15, [
    (0, "**Both are multi-stage.** Build on golang:1.26, ship only the binary "
        "on a distroless base - no shell, no package manager in the runtime "
        "image."),
    (0, "**The controller is fully static** (CGO_ENABLED=0) so it runs on "
        "distroless/**static**-debian12."),
    (0, "**The node agent cannot be.** The real-NVML build needs cgo, because "
        "go-nvml dlopens libnvidia-ml.so at runtime. That forces "
        "CGO_ENABLED=1 and a glibc-bearing base, hence "
        "distroless/**base**-debian12."),
    (0, "The plain non-GPU build runs on that same base image, so one "
        "Dockerfile covers both cases:", INK),
], size=12, gap=9)
code_box(s, MARGIN + 6.55, y + 3.5, 6.15, 0.95, """# GPU node: real NVML telemetry
docker build --build-arg GO_BUILD_TAGS=gpu \\
  -t kubeedgeinfer/nodeagent:dev \\
  -f deploy/docker/nodeagent.Dockerfile .""", size=9.5)

# ------------------------------------------------------------- cluster -----
s, y = slide(prs, "Cluster configuration", kicker="Configuration")
code_box(s, MARGIN, y, 5.9, 2.35, """kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: kubeedgeinfer
nodes:
  - role: control-plane
  - role: worker
    labels:
      kubeedgeinfer.io/worker: "true"
      kubeedgeinfer.io/node-id: "w1"
  - role: worker
    labels:
      kubeedgeinfer.io/worker: "true"
      kubeedgeinfer.io/node-id: "w2"
  - role: worker
    labels: { kubeedgeinfer.io/worker: "true",
              kubeedgeinfer.io/node-id: "w3" }""", size=10,
         caption="deploy/kind-config.yaml")
code_box(s, MARGIN, y + 2.6, 5.9, 1.85, """$ kubectl get nodes
NAME                          STATUS   ROLES
kubeedgeinfer-control-plane   Ready    control-plane
kubeedgeinfer-worker          Ready    <none>
kubeedgeinfer-worker2         Ready    <none>
kubeedgeinfer-worker3         Ready    <none>""", size=10)
code_box(s, MARGIN + 6.35, y, 6.35, 4.45, """spec:
  nodeSelector:
    kubeedgeinfer.io/worker: "true"
  hostNetwork: true                # kernel-global tracepoints
  dnsPolicy: ClusterFirstWithHostNet
  containers:
    - name: nodeagent
      image: kubeedgeinfer/nodeagent:dev
      securityContext:
        privileged: true           # required to load BPF
      env:
        - name: GPU_MODE
          value: "sim"             # sim | cputherm | nvml
        - name: PORT_MIN
          value: "50051"           # in-kernel flow filter
        - name: PORT_MAX
          value: "50052"
      volumeMounts:
        - { name: btf,     mountPath: /sys/kernel/btf,   readOnly: true }
        - { name: bpffs,   mountPath: /sys/fs/bpf }
        - { name: thermal, mountPath: /sys/class/thermal, readOnly: true }
  volumes:
    - name: btf
      hostPath: { path: /sys/kernel/btf }
    - name: bpffs
      hostPath: { path: /sys/fs/bpf }""", size=9.5,
         caption="deploy/manifests/nodeagent.yaml  (WATCH DaemonSet)")

# ===========================================================================
# CODE
# ===========================================================================
section_slide(prs, "CODE", "The four stages, in source",
              "One slide per stage of the control loop.")

# --------------------------------------------------------------- WATCH -----
s, y = slide(prs, "WATCH — the eBPF programs", kicker="Code  ·  Stage 1",
             subtitle="internal/ebpf/bpf/tcpmon.c — compiled CO-RE, loaded "
                      "with cilium/ebpf from the privileged DaemonSet.")
code_box(s, MARGIN, y, 7.0, 4.35, """char LICENSE[] SEC("license") = "GPL";

struct flow_key { __u32 saddr, daddr; __u16 sport, dport; };
struct flow_val { __u32 srtt_us; __u64 srtt_samples,
                  bytes, last_seen_ns; };

struct { __uint(type, BPF_MAP_TYPE_HASH);
         __type(key, struct flow_key);
         __type(value, struct flow_val); } flows SEC(".maps");

SEC("tp_btf/tcp_probe")
int BPF_PROG(tcp_probe_hook, struct sock *sk, struct sk_buff *skb)
{
    struct flow_key key = {};
    if (flow_from_sock(sk, &key))          // filters to worker ports
        return 0;
    struct tcp_sock *tp = (struct tcp_sock *)sk;
    __u32 srtt = BPF_CORE_READ(tp, srtt_us) >> 3;

    struct flow_val *val = flow_lookup_or_init(&key);
    if (!val) return 0;
    val->srtt_us = srtt;
    __sync_fetch_and_add(&val->srtt_samples, 1);
    val->last_seen_ns = bpf_ktime_get_ns();
    return 0;
}

SEC("fentry/tcp_sendmsg")
int BPF_PROG(tcp_sendmsg_hook, struct sock *sk,
             struct msghdr *msg, size_t size)
{ /* ... __sync_fetch_and_add(&val->bytes, size); ... */ }""", size=9.5)
bullets(s, MARGIN + 7.45, y - 0.05, 5.25, [
    (0, "**tp_btf/tcp_probe** is a BTF-typed tracepoint - it reads the "
        "kernel's own smoothed RTT estimate rather than timing anything in "
        "userspace."),
    (0, "**srtt_us >> 3** because the kernel stores sRTT shifted left by 3 "
        "with a fractional part."),
    (0, "**BPF_CORE_READ** is what makes this CO-RE: field offsets are relocated "
        "against the running kernel's BTF at load time, so one compiled object "
        "works across kernel versions."),
    (0, "**Filtering happens in-kernel** - flow_from_sock rejects anything "
        "outside PORT_MIN..PORT_MAX, so userspace only ever sees pipeline "
        "traffic."),
    (0, "The node agent reads this map once per second and ships it to the "
        "controller as LinkStat entries - which double as the liveness "
        "heartbeat.", INK),
], size=12, gap=9)

# -------------------------------------------------------------- DECIDE -----
s, y = slide(prs, "DECIDE — the optimiser and the gate",
             kicker="Code  ·  Stage 2")
code_box(s, MARGIN, y, 6.4, 2.5, """// An empty stage is skipped by the router entirely, so it
// costs nothing -- not even its hop. This lets the partitioner
// bypass a worker whose link degraded so badly that
// redistributing its layers is cheaper than the hop.
func stageCost(in Input, worker, layers int) float64 {
    if layers == 0 { return 0 }
    cost := float64(layers) * in.PerLayerMs /
            math.Max(in.Workers[worker].Speed, 0.01)
    if worker > 0 { cost += in.LinkMs[worker-1] }
    return cost
}""", size=10, caption="internal/partition/partition.go")
code_box(s, MARGIN, y + 2.75, 6.4, 1.7, """// Optimal solves the linear partition exactly, O(N^2 * K).
for w := 1; w <= k; w++ {
  for j := 0; j <= n; j++ {
    for split := 0; split <= j; split++ {
      cost := math.Max(f[split][w-1], stageCost(in, w-1, j-split))
      if cost < f[j][w] { f[j][w] = cost; choice[j][w] = split }
    }
  }
}""", size=10)
code_box(s, MARGIN + 6.85, y, 5.85, 3.05, """func (d *Decider) Decide(now time.Time, in Input,
                         force bool) (*Result, bool, error) {
    opt, err := Optimal(in)
    if err != nil { return nil, false, err }

    // A node joined or died: repartition immediately,
    // bypassing both gates. Healing must not wait.
    if d.current == nil || force ||
       workersChanged(d.current, in.Workers) {
        d.current, d.lastChange = opt, now
        return opt, true, nil
    }

    currentCost := Evaluate(in, d.current.Splits())
    improved := opt.BottleneckMs <
                currentCost*(1-d.ImprovementFrac)
    if improved && now.Sub(d.lastChange) >= d.Cooldown {
        d.current, d.lastChange = opt, now
        return opt, true, nil
    }
    // Keep the split; refresh its bottleneck for status.
    kept := &Result{Assignments: d.current.Assignments,
                    BottleneckMs: currentCost}
    d.current = kept
    return kept, false, nil
}""", size=9.5, caption="the hysteresis gate")
callout(s, MARGIN + 6.85, y + 3.3, 5.85, 1.15,
        "NewDecider(0.15, 30*time.Second) — the 15% / 30 s figures quoted "
        "throughout the main deck are these two constructor arguments, and are "
        "overridable live via IMPROVEMENT_FRAC and COOLDOWN_S.",
        accent=GREEN, size=12, label="where the numbers come from")

# ----------------------------------------------------------------- ACT -----
s, y = slide(prs, "ACT — the gRPC contract behind a live repartition",
             kicker="Code  ·  Stage 3")
code_box(s, MARGIN, y, 6.3, 4.4, """service Worker {
  rpc AssignLayers(AssignLayersRequest) returns (AssignLayersReply);
  rpc Forward(ForwardRequest) returns (ForwardReply);
  rpc Stats(StatsRequest) returns (StatsReply);
}

message AssignLayersRequest {
  int32 start_layer  = 1;   // inclusive
  int32 end_layer    = 2;   // exclusive
  int32 total_layers = 3;
  string backend     = 4;   // "sim" | "gpt2"
  string model       = 5;
  int64  generation  = 6;   // monotonic assignment version
}

message ForwardRequest {
  int64 request_id   = 1;
  int32 step         = 2;   // 0 = prefill
  repeated int32 input_ids = 3;
  bytes hidden       = 4;   // fp32 LE activations
  repeated int32 shape = 5;
  int64 generation   = 6;   // MUST match the worker's assignment
}

service Router {
  rpc SetPipeline(SetPipelineRequest) returns (Ack);
}""", size=9.5, caption="proto/pipeline.proto")
bullets(s, MARGIN + 6.75, y - 0.05, 5.95, [
    (0, "**AssignLayers is the whole mechanism.** Changing the partition is one "
        "gRPC call per worker - no pod restart, no model reload, no state "
        "transfer."),
    (0, "**generation appears in both messages.** That is the fence: a worker "
        "rejects any Forward whose generation does not match its current "
        "assignment."),
    (0, "**The router reacts to rejection by replaying**, not by failing. It "
        "refetches the layout and re-sends the full accumulated context."),
    (0, "**This is only correct because workers are stateless** - each "
        "recomputes from the whole context every step, so replay on a new "
        "split is indistinguishable from having started with it.", GREEN),
    (0, "The Telemetry service closes the loop in the other direction: node "
        "agents push NodeTelemetry (GpuStat + LinkStat) to the controller "
        "roughly once a second, doubling as the heartbeat."),
], size=12, gap=9)

# ---------------------------------------------------------------- HEAL -----
s, y = slide(prs, "HEAL — reconciliation and re-assertion",
             kicker="Code  ·  Stage 4")
code_box(s, MARGIN, y, 6.5, 2.35, """// Every applied split bumps the generation under lock.
func (c *Controller) apply(ctx context.Context, sp spec,
                           res *partition.Result) error {
    c.mu.Lock()
    c.generation++
    gen := c.generation
    c.mu.Unlock()
    return c.push(ctx, sp, res, gen)
}""", size=10, caption="internal/controller/controller.go")
code_box(s, MARGIN, y + 2.6, 6.5, 1.85, """// A router or worker that restarts comes up with an empty
// layout. Re-push the CURRENT generation periodically so it
// is reconciled back in, without inventing a new generation.
func (c *Controller) reassertDue(now time.Time) (int64, bool) {
    c.mu.Lock(); defer c.mu.Unlock()
    if c.lastApplied == nil || c.cfg.ReassertInterval <= 0 {
        return 0, false
    }
    return c.generation, now.Sub(c.lastPush) >= c.cfg.ReassertInterval
}""", size=10)
bullets(s, MARGIN + 6.95, y - 0.05, 5.75, [
    (0, "**Heartbeat timeout is 3 s.** A node whose telemetry goes stale is "
        "dropped from the worker set, which makes workersChanged() true, which "
        "forces a repartition past the hysteresis gate."),
    (0, "**Re-assertion every 10 s** fixes a real bug found during testing: a "
        "router restarting mid-run was pushed to while terminating, and was "
        "then never pushed to again - wedging the pipeline permanently."),
    (0, "**Stage ordering is deterministic**, sorted by (node, pod name). "
        "Before that fix, an unstable sort could reorder identical stages and "
        "trigger spurious repartitions."),
    (0, "**The CRD is the observable output.** Assignments, predicted "
        "bottleneck and generation are written to .status every reconcile.", INK),
], size=12, gap=9)
code_box(s, MARGIN + 6.95, y + 3.55, 5.75, 0.9, """$ kubectl -n kubeedgeinfer get ipl demo
NAME   PHASE     BOTTLENECK   GENERATION
demo   Serving   121.4        7""", size=10)

# ===========================================================================
# DEMO SCRIPT
# ===========================================================================
section_slide(prs, "LIVE DEMO", "The demonstration, step by step",
              "Exact commands, in the order they will be run.")

s, y = slide(prs, "Demo 1 — bring up the pipeline and watch the loop",
             kicker="Live Demo")
demo1 = [
    ("Start everything", "./run-demo.sh", "Builds if needed, creates the kind "
     "cluster, deploys, opens the dashboard on :8000."),
    ("Show the declared intent", "kubectl -n kubeedgeinfer get ipl demo -o yaml",
     "spec is what the user asked for; status is what the controller decided."),
    ("Show the live split", "curl -s localhost:18080/pipeline | jq",
     "Three stages, contiguous layer ranges, current generation."),
    ("Send a real request", "curl -s -X POST localhost:18080/generate \\\n"
     "  -d '{\"prompt_len\":16,\"max_new_tokens\":8}'",
     "Returns tokens plus per-stage timing."),
]
yy = y
for head, cmd, why in demo1:
    tf = tb(s, MARGIN, yy, 3.3, 0.7)
    para(tf, head, size=13.5, color=NAVY, bold=True, first=True, after=4)
    para(tf, why, size=10.5, color=MUTED, after=0, spacing=1.16)
    nlines = cmd.count("\n") + 1
    code_box(s, MARGIN + 3.5, yy - 0.04, 9.2, 0.30 + 0.22 * nlines, cmd,
             size=11)
    yy += 1.10
callout(s, MARGIN, yy + 0.05, BODY_W, 0.78,
        "At this point the dashboard is already updating every 2 s: "
        "generation, layer assignment, per-stage utilisation, node "
        "temperatures and live eBPF flow sRTTs.",
        accent=BLUE, size=12.5, label="what to point at on screen")

# ---------------------------------------------------------------------------
s, y = slide(prs, "Demo 2 — inject a thermal fault, watch it heal",
             kicker="Live Demo")
code_box(s, MARGIN, y, 6.35, 2.0, """# find the node agent on worker2
W2=$(docker inspect -f \\
  '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' \\
  kubeedgeinfer-worker2)

# inject: force the simulated GPU to 92 C
curl -X POST http://$W2:9101/gpu/override -d '{"temp_c": 92}'""",
         size=10, caption="inject")
code_box(s, MARGIN, y + 2.25, 6.35, 1.15, """# recover
curl -X POST http://$W2:9101/gpu/override -d '{"clear": true}'""",
         size=10, caption="clear")
callout(s, MARGIN, y + 3.6, 6.35, 0.85,
        "Or just press the Inject / Clear buttons on the dashboard - they call "
        "exactly these endpoints.",
        accent=GREEN, size=12)
watch = [
    ("t + 0 s", "worker2 temperature jumps to 92 °C; the node agent marks it "
                "throttled and drops speed_factor to 0.4", ORANGE),
    ("t + 2 s", "controller tick: the DP finds a materially better split", BLUE),
    ("t + 2 s", "hysteresis gate passes - >15% improvement, cooldown elapsed",
     BLUE),
    ("t + 2 s", "generation increments; the layer-assignment bar on the "
                "dashboard visibly redraws", GREEN),
    ("t + 3 s", "layers have moved off worker2 onto the two healthy nodes; "
                "tokens/sec recovers", GREEN),
    ("~35 s", "after clearing, the node cools, the gate passes again and "
              "layers migrate back", GREEN),
]
rect(s, MARGIN + 6.8, y, 5.9, 4.45, fill=WHITE, line=LINE)
tf = tb(s, MARGIN + 7.03, y + 0.2, 5.4, 0.3)
para(tf, "WHAT THE AUDIENCE SEES", size=10, color=BLUE, bold=True, first=True,
     after=10)
yy = y + 0.6
for tstamp, what, col in watch:
    rect(s, MARGIN + 7.03, yy + 0.06, 0.075, 0.075, fill=col)
    tf = tb(s, MARGIN + 7.24, yy - 0.02, 0.82, 0.26)
    para(tf, tstamp, size=9.5, color=col, bold=True, font=MONO, first=True,
         after=0)
    tf = tb(s, MARGIN + 8.18, yy - 0.02, 4.35, 0.62)
    para(tf, what, size=11, color=INK, first=True, after=0, spacing=1.16)
    yy += 0.63

# ---------------------------------------------------------------------------
s, y = slide(prs, "Demo 3 — kill a node, and prove correctness",
             kicker="Live Demo")
code_box(s, MARGIN, y, 6.3, 1.5, """# stop the node holding the last pipeline stage
docker stop kubeedgeinfer-worker3

# ... 3 s heartbeat timeout -> forced repartition
# ... requests keep completing on the two survivors

docker start kubeedgeinfer-worker3   # it rejoins and is used again""",
         size=10, caption="node failure")
bullets(s, MARGIN, y + 1.75, 6.3, [
    (0, "The static baseline cannot do this: with STATIC_MODE=1 the same "
        "scenario dropped **18 requests**."),
    (0, "The dynamic loop completed **126 requests with 0 errors**.", GREEN),
], size=12, gap=8)

code_box(s, MARGIN + 6.75, y, 5.95, 1.65, """$ python3 bench/verify_gpt2.py
distributed : [11, 314, 716, 257, 1263, 4336]
single-proc : [11, 314, 716, 257, 1263, 4336]
MATCH""", size=10.5, caption="token-identical to single-process HF GPT-2")
code_box(s, MARGIN + 6.75, y + 1.9, 5.95, 1.5, """$ make test
ok  kubeedgeinfer/internal/partition
    TestOptimalMatchesBruteForce  (200 random cases)
    TestDeciderHysteresis""", size=10.5, caption="optimiser vs brute force")
callout(s, MARGIN + 6.75, y + 3.55, 5.95, 0.9,
        "Repartitioning is only interesting if the answer does not change. "
        "These two commands are the proof that it does not.",
        accent=GREEN, size=12)

# ---------------------------------------------------------------------------
s, y = slide(prs, "Demo 4 — reproduce the full result set",
             kicker="Live Demo",
             subtitle="Every figure in the main deck comes from these "
                      "commands.")
repro = [
    ["Command", "Produces"],
    ["python3 bench/run.py --all",
     "10 runs: 5 scenarios × {dynamic, static} → results/*_requests.csv, "
     "_series.csv, _phases.csv, summary.json"],
    ["python3 bench/run.py --mode profileonly --scenario netem",
     "The offline-profiling ablation: repartitions like dynamic but freezes "
     "telemetry at the first reading"],
    ["python3 bench/plot.py",
     "baseline.png, netem.png, thermal.png, failure.png, combo.png, "
     "summary.png"],
    ["python3 bench/run.py --sweep-hysteresis netem",
     "δ ∈ {0.05, 0.30} × τ ∈ {10 s, 60 s} grid → hysteresis_sweep.json"],
    ["python3 bench/plot_sweep.py", "hysteresis_sweep.png"],
    ["python3 bench/fidelity.py",
     "fidelity.png - predicted vs measured bottleneck cost; needs no new run"],
    ["python3 bench/verify_gpt2.py",
     "Prints MATCH on token-identical distributed vs single-process output"],
]
table(s, MARGIN, y, BODY_W, (5.0, 7.7), repro, font=10.5, row_h=0.55,
      head_h=0.34, mono_cols=(0,))

# ===========================================================================
# REAL HARDWARE
# ===========================================================================
section_slide(prs, "REAL HARDWARE", "Beyond the single-host demo",
              "The same code on physical machines: multi-laptop k3s, and a "
              "single GPU box.")

s, y = slide(prs, "Path A — a real multi-machine k3s cluster",
             kicker="Real Hardware",
             subtitle="Real inter-node latency and real thermal telemetry. "
                      "Two machines cover netem and thermal; a third is "
                      "needed for the failure scenario.")
code_box(s, MARGIN, y, 6.4, 2.6, """# on the machine that becomes the k3s server
./scripts/join-node.sh server
#   installs k3s (or the raw binary if there is no systemd)
#   installs nvidia-container-toolkit if a GPU is present
#   labels the node and prints the exact agent command

# on every other machine
./scripts/join-node.sh agent <server-ip> <node-token>

# back on the server, once all nodes are joined
./scripts/deploy-real-hardware.sh""", size=10)
bullets(s, MARGIN, y + 2.85, 6.4, [
    (0, "Builds and distributes images via a local registry (multi-node) or "
        "imports straight into containerd (single node)."),
    (0, "Auto-selects **GPU_MODE=nvml** on GPU-labeled nodes and "
        "**GPU_MODE=cputherm** on GPU-less laptops - which reads real "
        "/sys/class/thermal, so throttling observed there is genuine hardware.",
     GREEN),
], size=12, gap=8)

gotchas = [
    ["Requirement", "Why"],
    ["Same CPU architecture on every node",
     "One image tag cannot serve mixed arches; the deploy script fails fast "
     "rather than producing exec-format errors"],
    ["/sys/kernel/btf/vmlinux on each node",
     "CO-RE needs BTF. Without it the agent still runs but drops network "
     "telemetry (the thermal loop keeps working)"],
    ["Firewall: 6443/tcp, 8472/udp, 10250/tcp, 5000/tcp",
     "API server, flannel VXLAN, kubelet, and the local image registry"],
    ["A privileged container or a real VM",
     "The node agent must load BPF programs; rootless or unprivileged "
     "containers cannot"],
    ["node-role.kubernetes.io/control-plane",
     "Router and controller select on it with operator: Exists - k3s sets a "
     "different value than kind, which is why nodeSelector was replaced with "
     "nodeAffinity"],
]
table(s, MARGIN + 6.85, y, 5.85, (2.35, 3.5), gotchas, font=9.5, row_h=0.80,
      head_h=0.32)

# ---------------------------------------------------------------------------
s, y = slide(prs, "Path B — one GPU machine, with or without K8s",
             kicker="Real Hardware",
             subtitle="Worked example: a single NVIDIA L4.")
code_box(s, MARGIN, y, 6.3, 1.9, """# with k3s: 3 shards share the one L4
./scripts/join-node.sh server
WITH_GPT2=1 ./scripts/deploy-real-hardware.sh
kubectl -n kubeedgeinfer delete ds keinfer-worker
kubectl apply -f deploy/manifests/workers-singlenode.yaml""",
         size=10, caption="Kubernetes path")
code_box(s, MARGIN, y + 2.15, 6.3, 1.55, """# no Kubernetes at all -- for unprivileged containers
./scripts/run-single-gpu.sh          # 3 shards, real GPT-2, CUDA
SHARDS=4 ./scripts/run-single-gpu.sh
BACKEND=sim ./scripts/run-single-gpu.sh""",
         size=10, caption="fallback path")
callout(s, MARGIN, y + 3.85, 6.3, 0.6,
        "Rented GPU boxes are often unprivileged containers where k3s cannot "
        "run at all. The fallback needs none of it.",
        accent=ORANGE, size=11.5)

got = [
    ["What one GPU box gives", "Yes / No"],
    ["Real CUDA inference, real GPT-2 tokens", "^Yes"],
    ["Real NVML thermal and throttle telemetry", "^Yes"],
    ["Pipeline parallelism, token-identical output", "^Yes"],
    ["Real inter-node network latency", "!No - every hop is loopback"],
    ["Cross-node repartitioning being useful",
     "!Limited - all shards share one GPU, so a throttle slows all of them "
     "equally"],
    ["Node-failure healing", "!No - needs multiple machines"],
]
table(s, MARGIN + 6.75, y, 5.95, (3.5, 2.45), got, font=10, row_h=0.50,
      head_h=0.32)
callout(s, MARGIN + 6.75, y + 3.75, 5.95, 0.7,
        "So: use the GPU box for the real-model claims, and kind or a second "
        "machine for the control-loop claims.",
        accent=BLUE, size=11.5)

# ---------------------------------------------------------------------------
s, y = slide(prs, "Design decisions worth defending in questions",
             kicker="Code Walkthrough")
qa = [
    ("Why is the DP not the contribution?",
     "It is textbook chain partitioning - Skiena, Pınar & Aykanat - and "
     "EdgeShard and Alpa use the same family. Saying so directly pre-empts the "
     "most likely objection. The contribution is re-invoking it continuously "
     "from live kernel telemetry."),
    ("Why stateless workers instead of KV caching?",
     "Stateless recompute makes a mid-generation repartition provably correct "
     "with zero migration-consistency bugs. It costs redundant compute that "
     "grows with context length - the crossover point is measured future work, "
     "and is stated as such rather than hidden."),
    ("Why eBPF rather than application-level timing?",
     "sRTT from tcp_probe is the kernel's own estimate of the transport path, "
     "measured below the application, at no sampling cost to the data path. It "
     "cannot be skewed by Python GIL scheduling the way an app-level timer can."),
    ("Why a CRD instead of a config file?",
     "It makes the partition an observable, reconciled cluster object: "
     "kubectl get ipl shows the live split, and every repartition is a status "
     "transition rather than an opaque internal event."),
    ("Why hysteresis at all?",
     "Without it the optimiser would chase telemetry noise and move layers "
     "constantly. The sweep in the main deck shows behaviour is monotonic in "
     "both parameters and that no thrashing occurs at any tested setting."),
]
yy = y - 0.05
for q, a in qa:
    rect(s, MARGIN, yy, BODY_W, 0.94, fill=WHITE, line=LINE)
    rect(s, MARGIN, yy, 0.05, 0.94, fill=BLUE)
    tf = tb(s, MARGIN + 0.25, yy + 0.15, 3.75, 0.76)
    para(tf, q, size=12.5, color=NAVY, bold=True, first=True, after=0,
         spacing=1.15)
    tf = tb(s, MARGIN + 4.15, yy + 0.13, 8.35, 0.76)
    para(tf, a, size=10.5, color=INK, first=True, after=0, spacing=1.18)
    yy += 1.02

# ---------------------------------------------------------------------------
s = blank(prs)
rect(s, 0, 0, SLIDE_W, SLIDE_H, fill=NAVY)
rect(s, 0, 0, 0.19, SLIDE_H, fill=BLUE)
tf = tb(s, 1.4, 2.35, 10.6, 1.0)
para(tf, "Demo", size=42, color=WHITE, bold=True, first=True, after=0)
tf = tb(s, 1.4, 3.35, 10.2, 2.0)
para(tf, "Clone, one command, live dashboard:", size=15,
     color=RGBColor(0xB9, 0xCC, 0xDE), first=True, after=10)
para(tf, "git clone https://github.com/karnati-praveen/ebpf-", size=16,
     color=WHITE, font=MONO, after=4)
para(tf, "cd ebpf- && ./run-demo.sh", size=16, color=WHITE, font=MONO, after=10)
para(tf, "→  http://localhost:8000", size=16,
     color=RGBColor(0x8F, 0xBC, 0xEE), font=MONO, after=0)

paginate(prs, "KubeEdgeInfer  ·  code & live demo")
prs.save(OUT)
print(f"wrote {OUT}")
