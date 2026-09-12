#!/usr/bin/env python3
"""Build the 15-slide KubeEdgeInfer presentation.

    python3 ppt/make_deck15.py

Same eleven sections as the long deck, compressed to a 15-slide limit. The
code walkthrough stays in its own demo deck (KubeEdgeInfer_Code_Demo.pptx).
Result numbers are read from bench/results/summary.json at build time.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from deckkit import *                                            # noqa: F401,F403
from deckkit import _emit
from pptx.enum.text import PP_ALIGN

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, "bench", "results")
OUT = os.path.join(ROOT, "ppt", "KubeEdgeInfer_Presentation.pptx")

with open(os.path.join(RESULTS, "summary.json")) as f:
    SUMMARY = json.load(f)


def row(scenario, mode):
    for r in SUMMARY:
        if r["scenario"] == scenario and r["mode"] == mode:
            return r
    raise KeyError(f"{scenario}/{mode}")


def tput(sc, md):
    return row(sc, md)["throughput_tokens_per_sec"]


def p95(sc, md):
    return row(sc, md)["overall"]["ttft_ms_p95"]


def pct(d, s):
    return (d - s) / s * 100.0


prs = new_deck()

# ===========================================================================
# 1 -- TITLE
# ===========================================================================
title_slide(
    prs,
    "KubeEdgeInfer",
    "A closed-loop, eBPF-driven Kubernetes framework for heterogeneous "
    "distributed LLM inference on consumer edge clusters",
    [
        "Karnati Praveen",
        "Repository:  github.com/karnati-praveen/ebpf-",
        "August 2026",
    ],
    kicker="PROJECT PRESENTATION",
)

# ===========================================================================
# 2 -- INTRODUCTION
# ===========================================================================
s, y = slide(prs, "Introduction: why this is a scheduling problem",
             kicker="1  ·  Introduction")
bullets(s, MARGIN, y, 7.0, [
    (0, "A 7B model at FP16 needs ~**14 GB** of weights. No laptop GPU, Jetson "
        "or single rented L4 holds the models users actually want."),
    (0, "**Pipeline parallelism** is the standard answer: cut the layer stack "
        "into contiguous shards, one per machine. Activations, not weights, "
        "cross the network."),
    (0, "Running it at the **edge** rather than the cloud buys privacy (prompts "
        "stay local), latency (no WAN hop per token) and cost (hardware you "
        "already own)."),
    (0, "**Kubernetes is already there** - k3s runs on laptops, Jetsons and "
        "mini-PCs - so this is built **as** a Kubernetes controller, not beside "
        "one."),
], size=13, gap=9)

seg = [("Node A", "layers 0-3", BLUE), ("Node B", "layers 4-7", ORANGE),
       ("Node C", "layers 8-11", GREEN)]
bx = MARGIN + 0.35
for i, (nm, rng, col) in enumerate(seg):
    rect(s, bx, y + 3.16, 1.5, 0.68, fill=WHITE, line=col, line_w=1.5)
    tf = tb(s, bx, y + 3.27, 1.5, 0.5)
    para(tf, nm, size=11, color=NAVY, bold=True, align=PP_ALIGN.CENTER,
         first=True, after=1)
    para(tf, rng, size=9, color=MUTED, align=PP_ALIGN.CENTER, after=0)
    if i < 2:
        arrow(s, bx + 1.56, y + 3.40, 0.32, 0.18)
    bx += 1.88
tf = tb(s, MARGIN + 6.15, y + 3.24, 0.9, 0.5)
para(tf, "12 blocks\n3 machines", size=9.5, color=MUTED, first=True, after=0,
     spacing=1.15)

cards = [
    ("THERMAL", "Devices derate under load", ORANGE),
    ("NETWORK", "Links wander by orders of magnitude", BLUE),
    ("AVAILABILITY", "Nodes are laptops - they disappear", RED),
]
tf = tb(s, MARGIN + 7.45, y - 0.04, 5.25, 0.3)
para(tf, "THE EDGE IS NOT A DATACENTER", size=10, color=BLUE, bold=True,
     first=True, after=6)
yy = y + 0.32
for tag, head, col in cards:
    rect(s, MARGIN + 7.45, yy, 5.25, 0.62, fill=WHITE, line=LINE)
    rect(s, MARGIN + 7.45, yy, 0.05, 0.62, fill=col)
    tf = tb(s, MARGIN + 7.68, yy + 0.11, 5.0, 0.5)
    para(tf, tag, size=8.5, color=col, bold=True, first=True, after=2)
    para(tf, head, size=12, color=NAVY, bold=True, after=0)
    yy += 0.70
callout(s, MARGIN + 7.45, yy + 0.12, 5.25, 1.28,
        "A partition that is optimal at deployment time is not optimal sixty "
        "seconds later. Every system surveyed computes it **once**, from an "
        "offline profile, and never revisits it.",
        accent=NAVY, size=12, label="the consequence")

# ===========================================================================
# 3 -- LITERATURE REVIEW 1/2
# ===========================================================================
lit_a = [
    ["Work (venue, year)", "Core idea", "Gap this project addresses"],
    ["[1] EdgeShard\nIEEE IoT Journal, 2024",
     "DP joint device-selection + layer partition for LLMs on 15 heterogeneous "
     "edge devices (Jetson AGX/NX, RTX 3090); Llama2-7B/13B/70B.",
     "The DP runs **once, offline**, from a one-time profiling pass. No "
     "mechanism to revisit the split after deployment - by design."],
    ["[2] Galaxy\nIEEE INFOCOM, 2024",
     "Hybrid tensor + sequence parallelism for in-situ transformer inference, "
     "with tile-based compute/communication overlap.",
     "Placement fixed at planning time; no runtime telemetry loop, no response "
     "to thermal derating or node loss."],
    ["[3] Petals\nACL 2023 (Demo)",
     "BitTorrent-style volunteer pipeline over the WAN; clients rent "
     "transformer blocks from peers.",
     "Peer selection by application-level latency probing only - no kernel "
     "telemetry, no thermal signal, no orchestration API."],
    ["[4] Helix\nACM ASPLOS, 2025",
     "Max-flow formulation for serving LLMs across heterogeneous GPUs and a "
     "heterogeneous network topology.",
     "Solves placement offline per configuration; measured drift is never fed "
     "back into the solver while serving."],
    ["[5] vLLM / PagedAttention\nACM SOSP, 2023",
     "Paged KV-cache memory manager removing fragmentation, enabling "
     "continuous batching at high throughput.",
     "Single-node memory management. Orthogonal and complementary - assumes "
     "the model already fits the node set it is given."],
]
s, y = slide(prs, "Literature review (1 / 2): edge LLM serving",
             kicker="2  ·  Literature Review")
table(s, MARGIN, y, BODY_W, (2.5, 4.6, 4.9), lit_a, font=10.5, row_h=0.86,
      head_h=0.34)

# ===========================================================================
# 4 -- LITERATURE REVIEW 2/2
# ===========================================================================
lit_b = [
    ["Work (venue, year)", "Core idea", "Gap this project addresses"],
    ["[6] DistServe\nUSENIX OSDI, 2024",
     "Disaggregates prefill and decode onto separate GPUs so each phase meets "
     "its own latency SLO.",
     "Datacenter GPUs on a stable fabric; no notion of thermal derating or of "
     "a node leaving the cluster."],
    ["[7] Splitwise\nACM/IEEE ISCA, 2024",
     "Splits prompt and token phases across two machine pools, moving KV cache "
     "over a fast interconnect.",
     "Depends on InfiniBand-class bandwidth that does not exist on a consumer "
     "edge LAN."],
    ["[8] Llumnix\nUSENIX OSDI, 2024",
     "Reschedules inference **requests** across model instances at runtime "
     "using live KV-cache migration.",
     "Migrates requests between whole replicas, not layers within one model, "
     "and the mechanism is stateful migration."],
    ["[9] ServerlessLLM\nUSENIX OSDI, 2024",
     "Locality-aware checkpoint loading and live migration to cut cold-start "
     "cost for serverless LLM inference.",
     "Focused on load/start latency; the partition of a model across nodes is "
     "never revisited during serving."],
    ["[10] Electrode\nUSENIX NSDI, 2023",
     "Offloads distributed-protocol fast paths (Paxos) into eBPF, approaching "
     "kernel-bypass performance.",
     "Establishes eBPF for **datapath acceleration**, not as a measured cost "
     "signal driving a scheduling optimiser."],
]
s, y = slide(prs, "Literature review (2 / 2): serving and kernel telemetry",
             kicker="2  ·  Literature Review")
table(s, MARGIN, y, BODY_W, (2.5, 4.6, 4.9), lit_b, font=10.5, row_h=0.80,
      head_h=0.34)
callout(s, MARGIN, y + 4.36, BODY_W, 0.62,
        "Across all ten: the layer partition is solved **once**, and the "
        "systems that do act at runtime act on requests, by migrating state.",
        accent=BLUE, size=12.5, label="synthesis")

# ===========================================================================
# 5 -- PROBLEM STATEMENT + POSITIONING
# ===========================================================================
s, y = slide(prs, "Problem statement", kicker="3  ·  Problem Statement")
rect(s, MARGIN, y, 6.5, 2.52, fill=WHITE, line=LINE)
tf = tb(s, MARGIN + 0.24, y + 0.18, 6.0, 0.3)
para(tf, "FORMALLY", size=9.5, color=BLUE, bold=True, first=True, after=7)
tf = tb(s, MARGIN + 0.24, y + 0.50, 6.0, 1.9)
para(tf, "Given **L** layers and **K** heterogeneous workers in pipeline "
         "order, where worker k has time-varying effective speed "
         "sₖ(t) ∈ (0,1] and the hop feeding it has time-varying cost "
         "rₖ(t): find the contiguous partition minimising the "
         "bottleneck stage cost - and keep it minimal **continuously**, while "
         "the pipeline is serving, without restarting a single process.",
     size=12, color=INK, first=True, after=7, spacing=1.22)
para(tf, "Existing systems solve this at t = 0 only. The variables that make "
         "it hard, sₖ(t) and rₖ(t), are exactly the ones they treat "
         "as constants.",
     size=11.5, color=MUTED, italic=True, after=0, spacing=1.2)

qs = [("RQ1", "Can kernel measurements be the optimiser's cost input, not an "
               "operator dashboard?"),
      ("RQ2", "Can a partition change on a live pipeline with no pod restart "
               "and no KV migration?"),
      ("RQ3", "Can one hysteresis-gated trigger cover thermal, network and "
               "failure uniformly?"),
      ("RQ4", "Does closing the loop beat a static split - and what does it "
               "cost when nothing is wrong?")]
yy = y + 2.74
for tag, q in qs:
    rect(s, MARGIN, yy, 0.56, 0.30, fill=NAVY)
    tf = tb(s, MARGIN, yy + 0.055, 0.56, 0.26)
    para(tf, tag, size=9.5, color=WHITE, bold=True, align=PP_ALIGN.CENTER,
         first=True, after=0)
    tf = tb(s, MARGIN + 0.70, yy - 0.01, 5.8, 0.48)
    para(tf, q, size=11, color=INK, first=True, after=0, spacing=1.16)
    yy += 0.50

gx, gy = MARGIN + 8.05, y + 0.72
cw2, ch2 = 2.28, 1.26
tf = tb(s, MARGIN + 6.95, y - 0.06, 5.75, 0.3)
para(tf, "WHY THE GAP EXISTS - THE POSITIONING GRID", size=9.5, color=BLUE,
     bold=True, first=True, after=0)
for j, lab in enumerate(["KV-cache\nmigration", "Stateless replay\n(no migration)"]):
    tf = tb(s, gx + j * (cw2 + 0.14), gy - 0.42, cw2, 0.4)
    for k, ln in enumerate(lab.split("\n")):
        para(tf, ln, size=9.5, color=NAVY, bold=True, align=PP_ALIGN.CENTER,
             first=(k == 0), after=0, spacing=1.1)
for i, lab in enumerate(["Static /\none-time", "Dynamic /\ncontinuous"]):
    tf = tb(s, MARGIN + 6.95, gy + i * (ch2 + 0.14) + 0.34, 1.02, 0.5)
    for k, ln in enumerate(lab.split("\n")):
        para(tf, ln, size=9.5, color=NAVY, bold=True, align=PP_ALIGN.RIGHT,
             first=(k == 0), after=0, spacing=1.1)
cells = [(0, 0, "not applicable", "", FAINT, WASH),
         (0, 1, "EdgeShard · PipeEdge\nGalaxy · Alpa · Petals",
          "solved once, offline", INK, WHITE),
         (1, 0, "Llumnix\nServerlessLLM · AnchorTP",
          "dynamic, but stateful", INK, WHITE),
         (1, 1, "KubeEdgeInfer\n(this work)",
          "continuous, stateless", BLUE, WASH)]
for r, c, head, sub, col, bg in cells:
    x = gx + c * (cw2 + 0.14)
    yy2 = gy + r * (ch2 + 0.14)
    ours = (r, c) == (1, 1)
    rect(s, x, yy2, cw2, ch2, fill=bg, line=BLUE if ours else LINE,
         line_w=2.0 if ours else 1.0)
    tf = tb(s, x + 0.12, yy2 + 0.24, cw2 - 0.24, 0.9)
    para(tf, head, size=10.5 if ours else 9.5, color=col, bold=ours,
         align=PP_ALIGN.CENTER, first=True, after=5, spacing=1.15)
    if sub:
        para(tf, sub, size=8.5, color=MUTED, align=PP_ALIGN.CENTER, after=0,
             spacing=1.12)
callout(s, MARGIN + 6.95, gy + 2 * ch2 + 0.34, 5.75, 1.18,
        "The dynamic + stateless cell is empty because dynamic repartitioning "
        "was **assumed** to need KV-cache migration. Making workers stateless "
        "removes that assumption - and the reason the cell was empty.",
        accent=BLUE, size=11.5, label="why nobody is here")

# ===========================================================================
# 6 -- CONTRIBUTIONS
# ===========================================================================
s, y = slide(prs, "Contributions: four narrow, defensible claims",
             kicker="4  ·  Contributions / Novelty")
contribs = [
    ("C1", "Kernel-verified telemetry as an optimiser input",
     "CO-RE eBPF (tp_btf/tcp_probe, fentry/tcp_sendmsg) feeds per-flow sRTT "
     "straight into the partition cost function, every control tick.",
     "Cilium/Hubble/Pixie collect eBPF data for humans; EdgeShard/Galaxy feed "
     "their DP from an offline profile.", BLUE),
    ("C2", "Live, generation-fenced repartition with no migration",
     "Layer ranges reassigned over gRPC on a serving pipeline. Workers are "
     "stateless, so correctness needs only full-context replay - verified "
     "token-identical to HuggingFace GPT-2.",
     "Llumnix and AnchorTP repartition at runtime too, but by migrating KV "
     "state.", GREEN),
    ("C3", "One hysteresis-gated trigger, three fault classes",
     "Thermal derating, network RTT growth and heartbeat loss all resolve to "
     "the same decision: recompute, apply if >15% better after a 30 s cooldown.",
     "TAPAS handles thermal; Tarragon/LUMEN failure; Kinitos network. None "
     "unifies all three.", ORANGE),
    ("C4", "The partition is a first-class Kubernetes resource",
     "An InferencePipeline CRD holds the desired model and layer count; the "
     "controller reconciles telemetry into a published assignment + generation.",
     "KServe, Volcano and Ray Serve orchestrate model replicas, not intra-model "
     "layer assignment.", PURPLE),
]
yy = y - 0.06
for tag, head, what, vs, col in contribs:
    rect(s, MARGIN, yy, BODY_W, 0.92, fill=WHITE, line=LINE)
    rect(s, MARGIN, yy, 0.05, 0.92, fill=col)
    tf = tb(s, MARGIN + 0.20, yy + 0.12, 0.5, 0.3)
    para(tf, tag, size=12, color=col, bold=True, first=True, after=0)
    tf = tb(s, MARGIN + 0.78, yy + 0.10, 3.5, 0.76)
    para(tf, head, size=12, color=NAVY, bold=True, first=True, after=0,
         spacing=1.14)
    tf = tb(s, MARGIN + 4.45, yy + 0.11, 4.85, 0.76)
    para(tf, what, size=9.5, color=INK, first=True, after=0, spacing=1.16)
    tf = tb(s, MARGIN + 9.5, yy + 0.11, 2.6, 0.76)
    para(tf, "vs. " + vs, size=8.5, color=MUTED, first=True, after=0,
         spacing=1.16)
    yy += 1.00

rect(s, MARGIN, yy + 0.12, BODY_W, 1.06, fill=NAVY)
tf = tb(s, MARGIN + 0.5, yy + 0.28, BODY_W - 1.0, 0.85)
para(tf, "“EdgeShard solves **where** to place each layer once, from an "
         "offline profile. We solve **when** to move it - continuously, from "
         "live kernel telemetry - while the pipeline keeps serving requests, "
         "without restarting a single pod.”",
     size=13.5, color=WHITE, first=True, after=0, spacing=1.24)

# ===========================================================================
# 7 -- PROPOSED WORK: ARCHITECTURE
# ===========================================================================
s, y = slide(prs, "Proposed work: a control loop, not a planner",
             kicker="5  ·  Proposed Work")
stages = [
    ("01", "WATCH", ["eBPF CO-RE on every node",
                     "tp_btf/tcp_probe → sRTT",
                     "fentry/tcp_sendmsg → bytes",
                     "GPU/thermal via gpu.Reader:",
                     "sim | cputherm | nvml"], BLUE),
    ("02", "DECIDE", ["Exact linear-partition DP",
                      "O(L²K), minimises bottleneck",
                      "Hysteresis gate:",
                      "≥15% better AND",
                      "≥30 s since last change"], GREEN),
    ("03", "ACT", ["New layer ranges pushed",
                   "over gRPC - no pod restart,",
                   "no model reload",
                   "Every assignment carries",
                   "a monotonic generation"], ORANGE),
    ("04", "HEAL", ["3 s stale heartbeat ⇒",
                    "node declared gone",
                    "Forced repartition across",
                    "survivors; router replays",
                    "in-flight context"], RED),
]
bw = (BODY_W - 3 * 0.40) / 4
for i, (num, head, lines, col) in enumerate(stages):
    x = MARGIN + i * (bw + 0.40)
    stage_box(s, x, y + 0.06, bw, 2.30, num, head, lines, accent=col)
    if i < 3:
        arrow(s, x + bw + 0.06, y + 1.14, 0.26, 0.2)
rect(s, MARGIN + 0.6, y + 2.54, BODY_W - 1.2, 0.03, fill=FAINT)
rect(s, MARGIN + 0.6, y + 2.54, 0.03, 0.24, fill=FAINT)
rect(s, MARGIN + BODY_W - 0.63, y + 2.54, 0.03, 0.24, fill=FAINT)
tf = tb(s, MARGIN, y + 2.62, BODY_W, 0.3)
para(tf, "loop repeats every 2 s", size=10.5, color=MUTED, italic=True,
     align=PP_ALIGN.CENTER, first=True, after=0)

impl = [
    ["Component", "Language", "Role in the loop"],
    ["internal/ebpf + cmd/nodeagent", "Go + C (CO-RE BPF)",
     "WATCH - loads BPF objects with cilium/ebpf from a privileged DaemonSet; "
     "exports flow sRTT and GPU/thermal state"],
    ["internal/partition", "Go",
     "DECIDE - exact DP plus the hysteresis Decider; unit-tested against brute "
     "force on 200 randomised instances"],
    ["cmd/controller + internal/controller", "Go",
     "ACT / HEAL - reassigns ranges over gRPC, reconciles the InferencePipeline "
     "CRD, re-asserts the layout every 10 s"],
    ["worker/ (server.py, router.py)", "Python",
     "Stateless shard workers (sim, gpt2 backends) plus the router driving "
     "stages hub-and-spoke"],
]
table(s, MARGIN, y + 3.02, BODY_W, (3.3, 2.0, 6.7), impl, font=9.5,
      row_h=0.40, head_h=0.30)

# ===========================================================================
# 8 -- PROPOSED WORK: DECIDE + ACT/HEAL
# ===========================================================================
s, y = slide(prs, "The optimiser, and what makes a live repartition safe",
             kicker="5  ·  Proposed Work")
rect(s, MARGIN, y, 6.15, 1.72, fill=WHITE, line=LINE)
tf = tb(s, MARGIN + 0.22, y + 0.15, 5.7, 0.3)
para(tf, "COST MODEL", size=9.5, color=BLUE, bold=True, first=True, after=6)
tf = tb(s, MARGIN + 0.22, y + 0.44, 5.7, 1.2)
para(tf, "Tₖ  =  (bₖ − aₖ) · c / sₖ(t)   +   rₖ₋₁(t)",
     size=13, color=NAVY, bold=True, font=MONO, first=True, after=6)
para(tf, "c is the base per-layer cost, sₖ(t) the live effective speed "
         "(throttling included), rₖ₋₁(t) the measured sRTT of the hop "
         "feeding the stage. An **empty stage costs zero** - not even its hop - "
         "so a worker whose link collapsed can be bypassed entirely.",
     size=10.5, color=MUTED, after=0, spacing=1.2)

code_box(s, MARGIN, y + 1.94, 6.15, 1.62, """// f[j][w] = minimal bottleneck assigning the first
// j layers to the first w workers.  Exact, O(L^2 K).
for w := 1; w <= k; w++ {
  for j := 0; j <= n; j++ {
    for split := 0; split <= j; split++ {
      cost := max(f[split][w-1], stageCost(w-1, j-split))
      if cost < f[j][w] { f[j][w] = cost }
    } } }""", size=10, caption="internal/partition/partition.go")

gates = [("δ = 15%", "apply only if the new bottleneck beats the current "
                          "one by >15%"),
         ("τ = 30 s", "and only after 30 s; both tunable live at "
                           "runtime"),
         ("force", "a worker joining or dying bypasses both gates - healing "
                   "must not wait")]
rect(s, MARGIN, y + 3.70, 6.15, 1.22, fill=WHITE, line=LINE)
tf = tb(s, MARGIN + 0.22, y + 3.82, 5.7, 0.3)
para(tf, "HYSTERESIS GATE - WHY THE LOOP DOES NOT THRASH", size=9.5,
     color=BLUE, bold=True, first=True, after=6)
gw = (6.15 - 0.44 - 0.4) / 3
for i, (k, v) in enumerate(gates):
    x = MARGIN + 0.22 + i * (gw + 0.2)
    tf = tb(s, x, y + 4.12, gw, 0.76)
    para(tf, k, size=11.5, color=NAVY, bold=True, font=MONO, first=True,
         after=3)
    para(tf, v, size=8.5, color=MUTED, after=0, spacing=1.14)

bullets(s, MARGIN + 6.6, y - 0.06, 6.1, [
    (0, "**Generation fencing.** Every assignment carries a monotonic "
        "generation. Workers reject stale-generation forwards; the router "
        "refetches the layout and replays."),
    (0, "**Replay is trivially correct because workers are stateless.** Each "
        "recomputes from the full accumulated context, so there is no KV cache "
        "to migrate, invalidate or reconcile - the bug class that makes "
        "migration-based repartitioning hard does not exist here."),
    (0, "**Healing.** A heartbeat older than 3 s marks a node gone; the "
        "worker-set change forces a repartition past the gate."),
    (0, "**Re-assertion.** The controller re-pushes the layout every 10 s, so a "
        "restarted router is reconciled back in rather than left empty."),
    (0, "**Declarative.** The split lives in an InferencePipeline CRD - "
        "`kubectl get ipl` shows the live layout, bottleneck and generation.",
     INK),
], size=11.5, gap=8)
callout(s, MARGIN + 6.6, y + 3.70, 6.1, 1.22,
        "No pod is restarted, no model reloaded and no KV cache moved. The "
        "entire repartition mechanism is a gRPC call plus a version check.",
        accent=GREEN, size=12, label="the whole point")

# ===========================================================================
# 9 -- RESULTS: TESTBED / DOCKER / VM CONFIGURATION
# ===========================================================================
s, y = slide(prs, "Experimental setup: VM, Docker, cluster and workload",
             kicker="6  ·  Results",
             subtitle="Read off the machine the reported runs executed on.")
host = [
    ["Layer", "Configuration"],
    ["Host / VM", "GitHub Codespaces VM (Azure), Ubuntu 24.04.4 LTS"],
    ["Kernel", "6.8.0-1052-azure, x86_64 · BTF at /sys/kernel/btf/vmlinux "
               "(6.02 MB) · cgroup v2"],
    ["CPU / memory", "AMD EPYC 7763 64-Core - 2 vCPU · 7.76 GiB"],
    ["Container runtime", "Docker 29.3.0-1 · storage driver overlayfs · cgroup "
                          "driver cgroupfs, v2"],
    ["Cluster", "kind v0.29.0 · kubectl v1.35.2 · 1 control-plane + 3 workers "
                "labeled kubeedgeinfer.io/worker=true"],
    ["Toolchain", "Go 1.26.1 · Python 3.12.1 · cilium/ebpf v0.22.0 · grpc-go "
                  "v1.82.0 · client-go v0.36.2"],
]
table(s, MARGIN, y, 6.45, (1.75, 4.7), host, font=9.5, row_h=0.42, head_h=0.30)

imgs = [
    ["Image", "Base → runtime, contents"],
    ["worker:dev", "python:3.12-slim; grpcio≥1.60, protobuf≥4.25, numpy≥1.26; "
                   "torch + transformers only with WITH_GPT2=1 (WITH_CUDA=1 → "
                   "cu121 wheel)"],
    ["controller:dev", "golang:1.26 → distroless/static-debian12; "
                       "CGO_ENABLED=0 static binary"],
    ["nodeagent:dev", "golang:1.26 → distroless/base-debian12; glibc base "
                      "because the -tags gpu NVML build needs cgo"],
]
table(s, MARGIN + 6.75, y, 5.95, (1.4, 4.55), imgs, font=9.5, row_h=0.62,
      head_h=0.30, mono_cols=(0,))

wl = [
    ["Workload / control", "Value"],
    ["Model, layers", "GPT-2, totalLayers = 12, perLayerMs = 30, 3 shards"],
    ["Load", "3 concurrent threads, prompt_len 16, max_new_tokens 8"],
    ["Control loop", "2 s tick · re-assert 10 s · δ=0.15, τ=30 s · "
                     "heartbeat 3 s"],
]
table(s, MARGIN, y + 3.02, 6.45, (1.75, 4.7), wl, font=9.5, row_h=0.42,
      head_h=0.30)

faults = [
    ["Scenario", "Injection method"],
    ["netem", "tc qdisc add dev eth0 root netem delay 80ms on worker2"],
    ["thermal", "POST /gpu/override {\"temp_c\": 92} → speed derated to 0.4×"],
    ["failure", "docker stop kubeedgeinfer-worker3 (last stage), then restart"],
    ["combo", "netem + thermal simultaneously - the joint-fault test for C3"],
]
table(s, MARGIN + 6.75, y + 3.02, 5.95, (1.4, 4.55), faults, font=9.5,
      row_h=0.36, head_h=0.30, mono_cols=(0,))

# ===========================================================================
# 10 -- RESULTS: HEADLINE + FULL MATRIX
# ===========================================================================
s, y = slide(prs, "Results: the loop matters exactly when it should",
             kicker="6  ·  Results")
deltas = [
    ("baseline", pct(tput("baseline", "dynamic"), tput("baseline", "static")),
     "no fault - cost of running the loop", MUTED),
    ("netem", pct(tput("netem", "dynamic"), tput("netem", "static")),
     "80 ms on one link - below the gate", MUTED),
    ("thermal", pct(tput("thermal", "dynamic"), tput("thermal", "static")),
     "node at 0.4× - layers migrate off", GREEN),
    ("combo", pct(tput("combo", "dynamic"), tput("combo", "static")),
     "netem + thermal - 2 repartitions", GREEN),
    ("failure", pct(tput("failure", "dynamic"), tput("failure", "static")),
     "node stopped - 18 lost vs 0", GREEN),
]
bx = MARGIN
bwid = (BODY_W - 4 * 0.22) / 5
for name, d, note, col in deltas:
    sign = "+" if d >= 0 else "−"
    stat(s, bx, y - 0.02, bwid, f"{sign}{abs(d):.0f}%", name.upper(), note,
         accent=col)
    bx += bwid + 0.22

hdr = ["Scenario", "Mode", "Req OK", "Req err", "Throughput\n(tok/s)",
       "TTFT mean\n(ms)", "TTFT p95\n(ms)", "Repart."]
order = [("baseline", "dynamic"), ("baseline", "static"),
         ("netem", "dynamic"), ("netem", "static"), ("netem", "profileonly"),
         ("thermal", "dynamic"), ("thermal", "static"),
         ("failure", "dynamic"), ("failure", "static"),
         ("combo", "dynamic"), ("combo", "static")]
rows = [hdr]
for sc, md in order:
    r = row(sc, md)
    o = r["overall"]
    err = r["requests_error"]
    rows.append([sc, md, str(r["requests_ok"]),
                 ("!" if err else "") + str(err),
                 f"{r['throughput_tokens_per_sec']:.3f}",
                 f"{o['ttft_ms_mean']:.1f}", f"{o['ttft_ms_p95']:.1f}",
                 str(r.get("repartitions", "–"))])
table(s, MARGIN, y + 1.62, 8.15, (1.4, 1.3, 0.9, 0.9, 1.35, 1.3, 1.3, 0.9),
      rows, font=9.5, row_h=0.265, head_h=0.44, mono_cols=(0, 1))

bullets(s, MARGIN + 8.5, y + 1.60, 4.2, [
    (0, f"**Thermal +{pct(tput('thermal','dynamic'), tput('thermal','static')):.0f}%** "
        f"throughput, TTFT p95 {p95('thermal','static'):.0f} → "
        f"{p95('thermal','dynamic'):.0f} ms.", GREEN),
    (0, f"**Failure {tput('failure','dynamic')/tput('failure','static'):.1f}×**, "
        "and 18 failed requests → 0.", GREEN),
    (0, f"**Baseline "
        f"{abs(pct(tput('baseline','dynamic'), tput('baseline','static'))):.1f}%** "
        "- the loop is free when nothing is wrong.", INK),
    (0, "**netem is an honest negative.** 80 ms on one link never crosses the "
        "15% gate, so no repartition fires. The gate is behaving correctly - a "
        "fault layer movement cannot fix should not move layers.", ORANGE),
    (0, "failure/static's *better* TTFT p95 (386 ms) is an artefact: it "
        "completed only 30 requests; the 18 that hit the dead node never "
        "produced a latency sample.", RED),
], size=10.5, gap=8)

# ===========================================================================
# 11 -- RESULTS: FAULT FIGURES
# ===========================================================================
s, y = slide(prs, "Results: dynamic vs static under each fault",
             kicker="6  ·  Results")
figs = [("thermal.png", "THERMAL",
         f"worker2 forced to 92 °C (0.4×). Layers migrate off the hot node "
         f"within one tick: {tput('thermal','dynamic'):.2f} vs "
         f"{tput('thermal','static'):.2f} tok/s.", GREEN),
        ("failure.png", "NODE FAILURE",
         f"worker3 stopped. 3 s heartbeat forces a repartition past the gate: "
         f"{row('failure','dynamic')['requests_ok']} requests / 0 errors vs "
         f"{row('failure','static')['requests_ok']} / "
         f"{row('failure','static')['requests_error']}.", RED),
        ("combo.png", "JOINT FAULT",
         f"netem + thermal together - the test for C3. 2 repartitions vs 0; "
         f"TTFT p95 {p95('combo','dynamic'):.0f} vs "
         f"{p95('combo','static'):.0f} ms.", ORANGE)]
fw = (BODY_W - 2 * 0.30) / 3
for i, (png, tag, cap, col) in enumerate(figs):
    x = MARGIN + i * (fw + 0.30)
    tf = tb(s, x, y - 0.04, fw, 0.28)
    para(tf, tag, size=10, color=col, bold=True, first=True, after=0)
    figure(s, os.path.join(RESULTS, png), x, y + 0.26, fw, 2.85)
    tf = tb(s, x, y + 3.22, fw, 0.9)
    para(tf, cap, size=10, color=MUTED, first=True, after=0, spacing=1.18)
callout(s, MARGIN, y + 4.06, BODY_W, 0.78,
        "The controller never learns *which* fault it is reacting to. Thermal "
        "derating, link degradation and a missing heartbeat all reduce to the "
        "same statement - the cost terms changed - and the same response: "
        "recompute the split, apply it if the gate allows.",
        accent=NAVY, size=12, label="one trigger, three fault classes")

# ===========================================================================
# 12 -- RESULTS: STABILITY, FIDELITY, CORRECTNESS
# ===========================================================================
s, y = slide(prs, "Results: stability, cost-model fidelity, correctness",
             kicker="6  ·  Results")
tf = tb(s, MARGIN, y - 0.04, 4.0, 0.28)
para(tf, "DOES IT THRASH?", size=10, color=BLUE, bold=True, first=True,
     after=0)
figure(s, os.path.join(RESULTS, "hysteresis_sweep.png"), MARGIN, y + 0.24,
       4.05, 1.55)
bullets(s, MARGIN, y + 1.95, 4.05, [
    (0, "δ ∈ {0.05, 0.30} × τ ∈ {10 s, 60 s} under netem."),
    (0, "Monotonic and stable: lower threshold and cooldown give more "
        "repartitions (max 2); δ = 0.30 never triggers."),
    (0, "**No thrashing at any setting.**", GREEN),
], size=10.5, gap=7)

tf = tb(s, MARGIN + 4.45, y - 0.04, 4.0, 0.28)
para(tf, "IS THE COST MODEL TRUSTWORTHY?", size=10, color=BLUE, bold=True,
     first=True, after=0)
figure(s, os.path.join(RESULTS, "fidelity.png"), MARGIN + 4.45, y + 0.24,
       4.05, 1.55)
bullets(s, MARGIN + 4.45, y + 1.95, 4.05, [
    (0, "Predicted per-token bottleneck vs measured 1000/tokens_per_sec."),
    (0, "**Prediction underestimates by a stable 3.0-3.24× in every "
        "scenario.**", ORANGE),
    (0, "A stable ratio means the DP ranks stages correctly - all it needs to "
        "pick the right split - but misses a near-constant gRPC/interpreter "
        "overhead. Reported as a calibration caveat, not a bug."),
], size=10.5, gap=7)

tf = tb(s, MARGIN + 8.9, y - 0.04, 3.8, 0.28)
para(tf, "DOES THE ANSWER CHANGE?", size=10, color=BLUE, bold=True, first=True,
     after=0)
code_box(s, MARGIN + 8.9, y + 0.24, 3.82, 1.32, """$ python3 bench/verify_gpt2.py
distributed : [11, 314, 716, 257, 1263]
single-proc : [11, 314, 716, 257, 1263]
MATCH""", size=9)
code_box(s, MARGIN + 8.9, y + 1.68, 3.82, 1.26, """$ make test
ok  internal/partition
  TestOptimalMatchesBruteForce
  (200 randomised cases)""", size=9)
bullets(s, MARGIN + 8.9, y + 3.06, 3.82, [
    (0, "Distributed output is **token-identical** to single-process "
        "HuggingFace GPT-2 under greedy decoding.", GREEN),
    (0, "The DP is checked against brute-force enumeration - it returns the "
        "exact optimum, not a heuristic."),
], size=10.5, gap=7)

# ===========================================================================
# 13 -- COMPARISON
# ===========================================================================
s, y = slide(prs, "Comparison: against prior systems, and against static",
             kicker="7  ·  Comparison")
cmp_rows = [
    ["Capability", "Petals", "vLLM", "EdgeShard", "Llumnix", "Ours"],
    ["Heterogeneous edge support", "partial", "✗", "✓", "✗", "✓"],
    ["Kernel-level telemetry (eBPF)", "✗", "✗", "✗", "✗", "✓"],
    ["Runtime-continuous repartition", "✗", "✗", "✗ once", "✓ req.",
     "✓ layers"],
    ["Requires no KV-cache migration", "✓", "n/a", "✓", "✗", "✓"],
    ["Thermal-aware scheduling", "✗", "✗", "✗", "✗", "✓"],
    ["Autonomous healing on node loss", "✗", "✗", "✗", "partial", "✓"],
    ["Declarative Kubernetes API", "✗", "✗", "✗", "✗", "✓"],
    ["Real heterogeneous-hardware eval", "partial", "✓", "✓ 15 dev.", "✓",
     "!✗ our gap"],
]
table(s, MARGIN, y, 6.7, (2.5, 0.85, 0.7, 1.05, 0.9, 1.05), cmp_rows,
      font=9.5, row_h=0.335, head_h=0.32,
      align=[PP_ALIGN.LEFT] + [PP_ALIGN.CENTER] * 5)
callout(s, MARGIN, y + 3.28, 6.7, 1.1,
        "The last row is included deliberately. EdgeShard evaluates on 15 "
        "physical devices with Llama2-70B; this project on a single-host kind "
        "cluster with GPT-2. That is a real gap in evaluation rigour, stated "
        "rather than omitted.",
        accent=RED, size=11, label="the row that is not in our favour")

qrows = [["Scenario", "Metric", "Static", "Dynamic", "Change"]]


def qrow(sc, label, key, better="high"):
    d, st = row(sc, "dynamic"), row(sc, "static")
    if key == "tput":
        dv, sv = d["throughput_tokens_per_sec"], st["throughput_tokens_per_sec"]
        fmt = "{:.3f}"
    else:
        dv, sv = d["overall"][key], st["overall"][key]
        fmt = "{:.1f}"
    ch = (dv - sv) / sv * 100
    good = ch > 1 if better == "high" else ch < -1
    bad = ch < -1 if better == "high" else ch > 1
    marker = "^" if good else ("!" if bad else "")
    return [sc, label, fmt.format(sv), fmt.format(dv),
            marker + f"{'+' if ch >= 0 else '−'}{abs(ch):.1f}%"]


for sc in ("baseline", "netem", "thermal", "combo", "failure"):
    qrows.append(qrow(sc, "throughput (tok/s)", "tput"))
    qrows.append(qrow(sc, "TTFT p95 (ms)", "ttft_ms_p95", better="low"))
qrows.append(["failure", "failed requests", "18", "0", "^18 → 0"])
table(s, MARGIN + 7.0, y, 5.7, (1.3, 2.1, 1.0, 1.05, 1.15), qrows, font=9.5,
      row_h=0.29, head_h=0.32, mono_cols=(0,),
      align=[PP_ALIGN.LEFT, PP_ALIGN.LEFT, PP_ALIGN.RIGHT, PP_ALIGN.RIGHT,
             PP_ALIGN.RIGHT])
tf = tb(s, MARGIN + 7.0, y + 3.55, 5.7, 0.85)
para(tf, "Same controller, same load, same hardware - STATIC_MODE=1 is the "
         "only difference. It wins on thermal, combo and failure; it is "
         "neutral on baseline and netem, which is the correct behaviour there.",
     size=10.5, color=MUTED, first=True, after=0, spacing=1.2)

# ===========================================================================
# 14 -- LIMITATIONS + CONCLUSION + FUTURE WORK
# ===========================================================================
s, y = slide(prs, "Limitations, conclusion and future work",
             kicker="8-9  ·  Limitations & Conclusion")
tf = tb(s, MARGIN, y - 0.04, 4.05, 0.28)
para(tf, "LIMITATIONS - STATED OPENLY", size=10, color=RED, bold=True,
     first=True, after=7)
bullets(s, MARGIN, y + 0.26, 4.05, [
    (0, "Evaluation runs on a **single-host kind cluster**: loopback network, "
        "simulated GPU by default. The real-hardware paths exist and are "
        "documented, but the reported numbers are from kind."),
    (0, "**No empirical EdgeShard/Petals comparison** - different testbeds. "
        "Stated rather than approximated with an unfair reimplementation."),
    (0, "**GPT-2 scale.** The crossover where stateless replay costs more than "
        "KV migration is not yet measured."),
    (0, "**Cost model is ~3× low in absolute terms** - stable ratio, so "
        "ranking is correct; a calibration caveat."),
    (0, "**The netem ablation was neutral**, and the profileonly ablation "
        "inconclusive under that fault."),
], size=10.5, gap=7)

tf = tb(s, MARGIN + 4.45, y - 0.04, 4.05, 0.28)
para(tf, "CONCLUSION", size=10, color=BLUE, bold=True, first=True, after=7)
bullets(s, MARGIN + 4.45, y + 0.26, 4.05, [
    (0, "**A working system, not a simulation.** Real CO-RE eBPF, a real "
        "Kubernetes controller and CRD, real gRPC workers, and a harness that "
        "injects real faults into a real cluster."),
    (0, "**The one-time partition assumption is removable.** Stateless workers "
        "turn repartitioning from a KV-migration problem into a gRPC call plus "
        "a version check - so it can run continuously, at 2 s granularity, on "
        "a live pipeline."),
    (0, "**It pays off under exactly the faults that motivate it** - thermal "
        f"+{pct(tput('thermal','dynamic'), tput('thermal','static')):.0f}%, "
        f"joint +{pct(tput('combo','dynamic'), tput('combo','static')):.0f}%, "
        f"node loss {tput('failure','dynamic')/tput('failure','static'):.1f}× "
        "with zero dropped requests - and costs under 0.5% when nothing is "
        "wrong.", GREEN),
    (0, "**Correctness is proved, not assumed** - token-identical output, and "
        "a partitioner checked against brute force."),
], size=10.5, gap=7)

rect(s, MARGIN + 8.9, y - 0.06, 3.82, 4.5, fill=WHITE, line=LINE)
tf = tb(s, MARGIN + 9.12, y + 0.14, 3.4, 0.28)
para(tf, "FUTURE WORK", size=10, color=BLUE, bold=True, first=True, after=8)
fut = [("1", "Measure the replay-vs-migration crossover as context length "
             "grows - the experiment that bounds C2."),
       ("2", "Re-run the telemetry-source ablation under a larger perturbation "
             "to isolate C1."),
       ("3", "Deploy on physical hardware: multi-laptop k3s with "
             "GPU_MODE=cputherm, plus an NVIDIA node with real NVML."),
       ("4", "Scale past GPT-2 to a small Llama variant, narrowing the "
             "evaluation gap against EdgeShard."),
       ("5", "Multi-tenant operation: concurrent InferencePipeline resources "
             "sharing one node set.")]
yy = y + 0.52
for n, txt in fut:
    rect(s, MARGIN + 9.12, yy + 0.02, 0.26, 0.26, fill=WASH)
    tf = tb(s, MARGIN + 9.12, yy + 0.055, 0.26, 0.24)
    para(tf, n, size=9, color=BLUE, bold=True, align=PP_ALIGN.CENTER,
         first=True, after=0)
    tf = tb(s, MARGIN + 9.5, yy, 3.05, 0.75)
    para(tf, txt, size=10, color=INK, first=True, after=0, spacing=1.16)
    yy += 0.78

# ===========================================================================
# 15 -- REFERENCES
# ===========================================================================
refs = [
    "M. Zhang, J. Cao, X. Shen and Z. Cui, “EdgeShard: Efficient LLM Inference "
    "via Collaborative Edge Computing,” IEEE Internet of Things Journal, 2024. "
    "(arXiv:2405.14371)",
    "S. Ye et al., “Galaxy: A Resource-Efficient Collaborative Edge AI System "
    "for In-situ Transformer Inference,” Proc. IEEE INFOCOM, 2024.",
    "A. Borzunov et al., “Petals: Collaborative Inference and Fine-tuning of "
    "Large Models,” Proc. ACL 2023 System Demonstrations, 2023.",
    "Y. Mei et al., “Helix: Serving Large Language Models over Heterogeneous "
    "GPUs and Network via Max-Flow,” Proc. ACM ASPLOS, 2025.",
    "W. Kwon et al., “Efficient Memory Management for Large Language Model "
    "Serving with PagedAttention,” Proc. 29th ACM SOSP, 2023.",
    "Y. Zhong et al., “DistServe: Disaggregating Prefill and Decoding for "
    "Goodput-optimized LLM Serving,” Proc. 18th USENIX OSDI, 2024.",
    "P. Patel et al., “Splitwise: Efficient Generative LLM Inference Using "
    "Phase Splitting,” Proc. 51st ACM/IEEE ISCA, 2024.",
    "B. Sun et al., “Llumnix: Dynamic Scheduling for Large Language Model "
    "Serving,” Proc. 18th USENIX OSDI, 2024.",
    "Y. Fu et al., “ServerlessLLM: Low-Latency Serverless Inference for Large "
    "Language Models,” Proc. 18th USENIX OSDI, 2024.",
    "Y. Zhou et al., “Electrode: Accelerating Distributed Protocols with "
    "eBPF,” Proc. 20th USENIX NSDI, 2023.",
    "A. Agrawal et al., “Taming Throughput-Latency Tradeoff in LLM Inference "
    "with Sarathi-Serve,” Proc. 18th USENIX OSDI, 2024.",
    "Y. Hu et al., “PipeEdge: Pipeline Parallelism for Large-Scale Model "
    "Inference on Heterogeneous Edge Devices,” Proc. 25th Euromicro DSD, 2022.",
    "L. Zheng et al., “Alpa: Automating Inter- and Intra-Operator Parallelism "
    "for Distributed Deep Learning,” Proc. 16th USENIX OSDI, 2022.",
    "A. Pınar and C. Aykanat, “Fast optimal load balancing algorithms for 1D "
    "partitioning,” J. Parallel Distrib. Comput., vol. 64, no. 8, 2004.",
    "S. S. Skiena, The Algorithm Design Manual, 2nd ed. Springer, 2008. "
    "(linear partition problem)",
    "A. Radford et al., “Language Models are Unsupervised Multitask Learners,” "
    "OpenAI Technical Report, 2019. (GPT-2)",
    "Cilium project, “cilium/ebpf: eBPF library for Go.” "
    "github.com/cilium/ebpf",
    "SUSE / Rancher, “k3s: Lightweight Kubernetes.” k3s.io",
    "Kubernetes SIG Testing, “kind: Kubernetes in Docker.” kind.sigs.k8s.io",
]
s, y = slide(prs, "References", kicker="10  ·  References")
half = 10
for col, chunk, start in ((MARGIN, refs[:half], 1),
                          (MARGIN + 6.45, refs[half:], half + 1)):
    tf = tb(s, col, y, 6.25, 4.6)
    for i, r in enumerate(chunk):
        para(tf, f"[{start + i}]   {r}", size=9.5, color=INK, first=(i == 0),
             after=6, spacing=1.14, indent=(0.42, -0.42))
tf = tb(s, MARGIN, y + 4.42, BODY_W, 0.4)
para(tf, "Section 11 (proposed-work code, Docker/VM configuration and the live "
         "demo) is in the companion deck: KubeEdgeInfer_Code_Demo.pptx",
     size=11, color=MUTED, italic=True, first=True, after=0)

paginate(prs, "KubeEdgeInfer  ·  eBPF-driven distributed LLM inference")
prs.save(OUT)
print(f"wrote {OUT}  ({len(prs.slides.__iter__.__self__._sldIdLst)} slides)")
