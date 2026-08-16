const pptxgen = require("pptxgenjs");

const INK   = "141821";
const INK2  = "232A38";
const PAPER = "FFFFFF";
const MIST  = "F1F3F7";
const AMBER = "E07B39";
const TEAL  = "1F8A80";
const MUTED = "6B7280";
const LINE  = "D8DCE4";

const HFONT = "Cambria";
const BFONT = "Calibri";
const MFONT = "Courier New";

const p = new pptxgen();
p.layout = "LAYOUT_WIDE";   // 13.33 x 7.5
p.author = "KubeEdgeInfer";
p.title  = "KubeEdgeInfer";

const W = 13.33, H = 7.5, M = 0.62;

function shadow() { return { type: "outer", color: "9AA3B2", blur: 10, offset: 2, angle: 90, opacity: 0.28 }; }

function darkBg(s) { s.background = { color: INK }; }

// Title bar used on every light content slide.
function head(s, kicker, title) {
  s.background = { color: PAPER };
  s.addText(kicker.toUpperCase(), {
    x: M, y: 0.34, w: 9, h: 0.26, fontFace: BFONT, fontSize: 11.5,
    bold: true, color: AMBER, charSpacing: 2.2, margin: 0,
  });
  s.addText(title, {
    x: M, y: 0.62, w: W - 2 * M, h: 0.72, fontFace: HFONT, fontSize: 32,
    bold: true, color: INK, margin: 0,
  });
}

function foot(s, n, note) {
  if (note) {
    s.addText(note, {
      x: M, y: H - 0.52, w: 10.6, h: 0.3, fontFace: BFONT, fontSize: 9.5,
      color: MUTED, italic: true, margin: 0,
    });
  }
  s.addText(String(n), {
    x: W - M - 0.6, y: H - 0.52, w: 0.6, h: 0.3, fontFace: BFONT, fontSize: 10,
    color: MUTED, align: "right", margin: 0,
  });
}

// Tinted card. The motif of the deck: soft card + a coloured dot marker.
function card(s, x, y, w, h, fill) {
  s.addShape(p.ShapeType.roundRect, {
    x, y, w, h, rectRadius: 0.07, fill: { color: fill || MIST }, line: { color: "FFFFFF", width: 0 },
    shadow: shadow(),
  });
}

function dot(s, x, y, label, color) {
  s.addShape(p.ShapeType.ellipse, {
    x, y, w: 0.34, h: 0.34, fill: { color: color || AMBER }, line: { color: color || AMBER, width: 0 },
  });
  s.addText(label, {
    x, y, w: 0.34, h: 0.34, fontFace: BFONT, fontSize: 12.5, bold: true,
    color: "FFFFFF", align: "center", valign: "middle", margin: 0,
  });
}

/* ------------------------------------------------ 1. Title */
{
  const s = p.addSlide(); darkBg(s);
  s.addShape(p.ShapeType.ellipse, { x: 9.7, y: -1.5, w: 5.6, h: 5.6, fill: { color: INK2 }, line: { width: 0 } });
  s.addShape(p.ShapeType.ellipse, { x: 11.2, y: 4.2, w: 3.0, h: 3.0, fill: { color: INK2 }, line: { width: 0 } });

  s.addText("KUBEEDGEINFER", {
    x: M, y: 1.5, w: 9, h: 0.3, fontFace: BFONT, fontSize: 12, bold: true,
    color: AMBER, charSpacing: 3.4, margin: 0,
  });
  s.addText("A Closed-Loop, eBPF-Driven Kubernetes Framework for Heterogeneous Distributed LLM Inference", {
    x: M, y: 2.0, w: 8.5, h: 1.9, fontFace: HFONT, fontSize: 30, bold: true,
    color: "FFFFFF", lineSpacing: 36, margin: 0,
  });
  s.addText("Turning the one-time model split into a continuous, self-correcting decision driven by kernel-level measurements.", {
    x: M, y: 4.05, w: 8.4, h: 0.8, fontFace: BFONT, fontSize: 15, color: "B9C0CC",
    lineSpacing: 22, margin: 0,
  });

  const chips = ["eBPF / CO-RE", "Kubernetes operator", "Pipeline parallelism", "Consumer edge hardware"];
  chips.forEach((c, i) => {
    const x = M + i * 2.14;
    s.addShape(p.ShapeType.roundRect, {
      x, y: 5.25, w: 2.0, h: 0.44, rectRadius: 0.22,
      fill: { color: INK2 }, line: { color: "3A4356", width: 1 },
    });
    s.addText(c, {
      x, y: 5.25, w: 2.0, h: 0.44, fontFace: BFONT, fontSize: 9.5, color: "C9D0DC",
      align: "center", valign: "middle", margin: 0,
    });
  });

  s.addText("Research Presentation", {
    x: M, y: 6.35, w: 6, h: 0.3, fontFace: BFONT, fontSize: 12, color: TEAL, bold: true, margin: 0,
  });
  s.addText("Author:  •  Institution:  •  Date:", {
    x: M, y: 6.68, w: 8, h: 0.3, fontFace: BFONT, fontSize: 11, color: "7C8698", margin: 0,
  });
  s.addNotes("Title slide. Fill in author, institution and date before presenting.");
}

/* ------------------------------------------------ 2. Introduction */
{
  const s = p.addSlide();
  head(s, "Introduction", "Edge LLM inference is a moving target");
  const items = [
    ["Why split at all", "A 7B+ model does not fit on one consumer device. Pipeline parallelism spreads contiguous layer ranges across several machines, so the split point is the central performance decision."],
    ["Why the edge is different", "Datacenter schedulers assume stable, homogeneous, well-cooled nodes. An edge cluster is laptops and hobby GPU boxes on WiFi: they thermally throttle, their links wander, and they disappear."],
    ["What existing frameworks do", "They profile once, solve the placement problem once, and never revisit it. The plan is optimal for the machine state at t = 0 and progressively wrong afterwards."],
  ];
  items.forEach(([t, b], i) => {
    const y = 1.62 + i * 1.62;
    card(s, M, y, 7.5, 1.42);
    dot(s, M + 0.3, y + 0.3, String(i + 1), i === 2 ? AMBER : TEAL);
    s.addText(t, { x: M + 0.78, y: y + 0.22, w: 6.5, h: 0.32, fontFace: BFONT, fontSize: 14.5, bold: true, color: INK, margin: 0 });
    s.addText(b, { x: M + 0.78, y: y + 0.56, w: 6.5, h: 0.78, fontFace: BFONT, fontSize: 11.5, color: "3E4658", lineSpacing: 15, margin: 0 });
  });

  card(s, 8.62, 1.62, 4.09, 4.62, INK);
  s.addText("The consequence", {
    x: 8.92, y: 1.92, w: 3.5, h: 0.3, fontFace: BFONT, fontSize: 11, bold: true, color: AMBER, charSpacing: 1.6, margin: 0,
  });
  const stats = [
    ["2.4x", "bottleneck-stage cost inflicted by a single throttled node under a frozen split"],
    ["4.3x", "when a degraded link and a throttled GPU coincide"],
    ["0", "requests served once a node dies and nothing re-plans"],
  ];
  stats.forEach(([n, l], i) => {
    const y = 2.36 + i * 1.32;
    s.addText(n, { x: 8.92, y, w: 3.5, h: 0.62, fontFace: HFONT, fontSize: 40, bold: true, color: "FFFFFF", margin: 0 });
    s.addText(l, { x: 8.92, y: y + 0.6, w: 3.5, h: 0.62, fontFace: BFONT, fontSize: 10, color: "9AA3B4", lineSpacing: 13, margin: 0 });
  });
  foot(s, 2, "Figures from the partitioner-level evaluation on slide 11 (12 layers, 3 stages).");
  s.addNotes("Frame the problem: the split decision is made once, but the hardware it was made for does not stay still.");
}

/* ------------------------------------------------ 3-4. Literature review */
const papers = [
  ["EdgeShard", "IEEE IoT-J, 2024", "arXiv:2405.14371",
   "Joint device selection + layer partition by dynamic programming across collaborative edge devices. Up to 50% latency reduction, 2x throughput on Llama2 over 15 physical devices.",
   "Profiles device speed and bandwidth offline; the DP runs on that static profile."],
  ["Galaxy", "IEEE INFOCOM, 2024", "arXiv:2405.17245",
   "Hybrid tensor/sequence parallelism for in-situ Transformer inference, with heterogeneity-aware planning and tile-based compute/communication overlap. Up to 2.5x lower latency.",
   "Planning is a one-shot offline step; no runtime re-planning under drift."],
  ["Helix", "ACM ASPLOS, 2025", "arXiv:2406.01566",
   "Models heterogeneous GPU serving as max-flow on a weighted graph and solves placement + request scheduling jointly by MILP. Up to 3.3x throughput on 24-42 node clusters.",
   "Datacenter-scale GPUs; MILP is too heavy for a seconds-scale control loop."],
  ["TPI-LLM", "arXiv, 2024", "arXiv:2410.00531",
   "Argues tensor parallelism beats pipeline on low-resource devices; sliding-window memory scheduler and star-based allreduce keep 70B-scale weights moving through small RAM.",
   "Optimises memory and collectives, not adaptation to node degradation."],
  ["prima.cpp", "arXiv, 2025", "arXiv:2504.08791",
   "30-70B inference on real home clusters: Halda scheduler co-optimises CPU/GPU workload and device selection; pipelined-ring parallelism hides disk I/O. 5-17x lower TPOT than llama.cpp.",
   "Scheduling is decided at load time from static device capability."],
  ["LLM Partitioning at the Edge", "arXiv, 2025", "arXiv:2505.02533",
   "Partitions the decoder at attention-head granularity, co-locating each head with its K/V cache and migrating heads when memory tightens. Within 15-20% of an exact solver.",
   "Migration is triggered by memory pressure only - not thermal or network state."],
  ["Parallax", "arXiv, 2025", "arXiv:2509.26182",
   "Inference service over a decentralised pool of volunteer, non-uniform machines, addressing placement and routing without a central trusted cluster.",
   "Decentralised placement, but no kernel-level measurement substrate."],
  ["Adaptive Layer Splitting (MBRL)", "FITEE, Springer, 2025", "doi:10.1631/FITEE.2400468",
   "Model-based reinforcement learning chooses the split point for wireless LLM inference as channel quality varies - explicitly an adaptive, not one-shot, formulation.",
   "Learned policy needs training and gives no optimality guarantee; single split point."],
  ["Distributed LLMs & MLLMs Survey", "arXiv, 2025", "arXiv:2503.16585",
   "Survey of distributed inference across advances, challenges and directions; names dynamic adaptation under heterogeneity as an open problem.",
   "Confirms the gap this work targets rather than filling it."],
  ["Agentic OS / sched_ext", "arXiv, 2025", "arXiv:2509.01245",
   "Custom Linux schedulers loaded at runtime as eBPF programs (sched_ext, Linux 6.12) - evidence that eBPF is becoming a control substrate, not only an observability one.",
   "Schedules CPU tasks on one host; no notion of a distributed model pipeline."],
];

[0, 1].forEach((half) => {
  const s = p.addSlide();
  head(s, `Literature review (${half + 1} of 2)`,
       half === 0 ? "Partitioning and placement"
                  : "Adaptation, decentralisation, and eBPF as control");
  papers.slice(half * 5, half * 5 + 5).forEach((pp, i) => {
    const y = 1.58 + i * 1.06;
    card(s, M, y, W - 2 * M, 0.96, i % 2 === 0 ? MIST : "F7F8FA");
    s.addText(pp[0], { x: M + 0.26, y: y + 0.14, w: 2.5, h: 0.3, fontFace: BFONT, fontSize: 13, bold: true, color: INK, margin: 0 });
    s.addText(pp[1], { x: M + 0.26, y: y + 0.45, w: 2.5, h: 0.24, fontFace: BFONT, fontSize: 9.5, color: TEAL, bold: true, margin: 0 });
    s.addText(pp[2], { x: M + 0.26, y: y + 0.66, w: 2.5, h: 0.24, fontFace: MFONT, fontSize: 8, color: MUTED, margin: 0 });
    s.addText(pp[3], { x: M + 2.92, y: y + 0.13, w: 4.62, h: 0.74, fontFace: BFONT, fontSize: 10, color: "3E4658", lineSpacing: 13, margin: 0 });
    s.addShape(p.ShapeType.ellipse, { x: 8.34, y: y + 0.42, w: 0.13, h: 0.13, fill: { color: AMBER }, line: { width: 0 } });
    s.addText(pp[4], { x: 8.58, y: y + 0.13, w: 3.5, h: 0.74, fontFace: BFONT, fontSize: 9.5, color: "6B4A2E", italic: true, lineSpacing: 12, margin: 0 });
  });
  s.addText("Limitation relevant to this work", {
    x: 8.58, y: 1.31, w: 3.5, h: 0.24, fontFace: BFONT, fontSize: 9, bold: true, color: AMBER, charSpacing: 1.2, margin: 0,
  });
  s.addText("Contribution", {
    x: M + 2.92, y: 1.31, w: 3, h: 0.24, fontFace: BFONT, fontSize: 9, bold: true, color: MUTED, charSpacing: 1.2, margin: 0,
  });
  foot(s, 3 + half, "All ten works published 2024-2025; full citations on slide 15.");
  s.addNotes("Each row: what the paper contributes, and the specific limitation KubeEdgeInfer addresses.");
});

/* ------------------------------------------------ 5. Research gap */
{
  const s = p.addSlide();
  head(s, "Synthesis", "Where the literature stops");
  const rows = [
    ["Capability", "Datacenter serving\n(Helix)", "Edge partitioning\n(EdgeShard, Galaxy, prima.cpp)", "Adaptive splitting\n(MBRL, head-level)", "KubeEdgeInfer"],
    ["Heterogeneity-aware placement", "yes", "yes", "yes", "yes"],
    ["Exact optimum for a snapshot", "MILP", "DP", "no (learned / heuristic)", "DP, unit-tested vs brute force"],
    ["Re-plans while serving", "request routing only", "no", "yes", "yes, every 2 s"],
    ["Kernel-measured network input", "no", "user-space probes", "channel estimate", "eBPF tp_btf/tcp_probe sRTT"],
    ["Thermal / throttle input", "no", "no", "no", "NVML or /sys/class/thermal"],
    ["Survives node loss", "replication", "no", "no", "heartbeat-forced repartition"],
    ["Applies without restart", "n/a", "no", "no", "gRPC hot reassign, generation-fenced"],
  ];
  const colX = [M, 4.05, 5.75, 8.45, 10.5];
  const colW = [3.35, 1.62, 2.6, 1.98, 2.2];
  rows.forEach((r, ri) => {
    const y = 1.6 + (ri === 0 ? 0 : 0.7 + (ri - 1) * 0.62);
    const h = ri === 0 ? 0.68 : 0.58;
    if (ri === 0) {
      s.addShape(p.ShapeType.roundRect, { x: M, y, w: W - 2 * M, h, rectRadius: 0.05, fill: { color: INK }, line: { width: 0 } });
    } else if (ri % 2 === 1) {
      s.addShape(p.ShapeType.rect, { x: M, y, w: W - 2 * M, h, fill: { color: "F7F8FA" }, line: { width: 0 } });
    }
    r.forEach((cell, ci) => {
      s.addText(cell, {
        x: colX[ci], y, w: colW[ci], h,
        fontFace: BFONT, fontSize: ri === 0 ? 9.5 : 10,
        bold: ri === 0 || ci === 0 || ci === 4,
        color: ri === 0 ? "FFFFFF" : (ci === 4 ? TEAL : (ci === 0 ? INK : "4A5264")),
        valign: "middle", lineSpacing: 11, margin: 0,
        align: ci === 0 ? "left" : "left",
      });
    });
  });
  s.addShape(p.ShapeType.roundRect, {
    x: 10.4, y: 1.6, w: 2.31, h: 4.98, rectRadius: 0.05,
    fill: { type: "solid", color: TEAL, transparency: 92 }, line: { color: TEAL, width: 1.25 },
  });
  foot(s, 5, "No prior system closes the loop from kernel-level measurement back to the layer split while inference is running.");
  s.addNotes("This is the gap slide: every column has one of the four capabilities, none has all of them together.");
}

/* ------------------------------------------------ 6. Problem statement */
{
  const s = p.addSlide(); darkBg(s);
  s.addShape(p.ShapeType.ellipse, { x: 10.4, y: -1.2, w: 4.6, h: 4.6, fill: { color: INK2 }, line: { width: 0 } });
  s.addText("PROBLEM STATEMENT", {
    x: M, y: 0.75, w: 8, h: 0.3, fontFace: BFONT, fontSize: 11.5, bold: true, color: AMBER, charSpacing: 2.6, margin: 0,
  });
  s.addText("Given N transformer layers and K heterogeneous edge nodes whose compute speed, link latency and liveness all vary during inference, continuously maintain a contiguous layer assignment that minimises the bottleneck stage - without restarting the pipeline.",
    { x: M, y: 1.25, w: 8.5, h: 2.0, fontFace: HFONT, fontSize: 21, color: "FFFFFF", lineSpacing: 30, margin: 0 });

  const subs = [
    ["Measure", "Obtain per-flow latency and per-node thermal state cheaply and without instrumenting the inference code."],
    ["Decide", "Solve the placement exactly at telemetry rate, and suppress oscillation when the measurement is merely noisy."],
    ["Act", "Move layer ranges between live workers without dropping in-flight requests or restarting pods."],
    ["Heal", "Detect node loss and redistribute its layers across the survivors automatically."],
  ];
  subs.forEach(([t, b], i) => {
    const y = 3.55 + Math.floor(i / 2) * 1.5;
    const x = M + (i % 2) * 4.3;
    dot(s, x, y, String(i + 1), i % 2 === 0 ? AMBER : TEAL);
    s.addText(t, { x: x + 0.48, y: y - 0.02, w: 3.5, h: 0.32, fontFace: BFONT, fontSize: 14, bold: true, color: "FFFFFF", margin: 0 });
    s.addText(b, { x: x + 0.48, y: y + 0.33, w: 3.6, h: 0.9, fontFace: BFONT, fontSize: 10.5, color: "9AA3B4", lineSpacing: 14, margin: 0 });
  });

  s.addShape(p.ShapeType.roundRect, { x: 9.5, y: 3.35, w: 3.2, h: 3.0, rectRadius: 0.08, fill: { color: INK2 }, line: { color: "3A4356", width: 1 } });
  s.addText("Constraint", { x: 9.8, y: 3.6, w: 2.6, h: 0.28, fontFace: BFONT, fontSize: 10.5, bold: true, color: AMBER, charSpacing: 1.4, margin: 0 });
  s.addText("Commodity Linux only.\n\nNo datacenter interconnect, no vendor telemetry agent, no change to the model code, and no assumption that a node stays alive.",
    { x: 9.8, y: 3.95, w: 2.6, h: 2.2, fontFace: BFONT, fontSize: 11, color: "C2C9D6", lineSpacing: 16, margin: 0 });
  foot(s, 6, "");
  s.addNotes("State the problem formally, then break it into the four sub-problems that map onto the four loop stages.");
}

/* ------------------------------------------------ 7. Contributions */
{
  const s = p.addSlide();
  head(s, "Contributions", "What is new here");
  const cs = [
    ["Kernel telemetry as a scheduling input", "CO-RE eBPF programs (tp_btf/tcp_probe, fentry/tcp_sendmsg) feed per-flow smoothed RTT straight into a model-placement decision. Prior edge-LLM systems use user-space probes or offline profiles; none drives the partitioner from the kernel's own TCP state.", true],
    ["A closed loop, not a one-shot plan", "WATCH-DECIDE-ACT-HEAL runs every 2 s for the lifetime of the deployment. The split is a continuously maintained control variable rather than a deployment-time constant.", true],
    ["Hysteresis-gated exact optimisation", "The O(N^2 K) DP is exact for each snapshot; a 15% improvement threshold plus a 30 s cooldown converts it into a stable controller. One gate handles thermal, network and failure triggers alike.", true],
    ["Restart-free, generation-fenced reassignment", "Layer ranges move over gRPC while requests are in flight. Every assignment carries a generation; workers reject stale forwards and the stateless design makes context replay trivially correct.", false],
    ["An ablation that isolates continuous telemetry", "A profile-once mode reuses the same DP and apply path but freezes its inputs, approximating offline-profiling systems - so the measured gain is attributable to live telemetry, not to a better solver.", false],
  ];
  cs.forEach(([t, b, novel], i) => {
    const x = i < 3 ? M : M + 6.35;
    const y = i < 3 ? 1.58 + i * 1.62 : 1.58 + (i - 3) * 1.62;
    card(s, x, y, 6.1, 1.44, novel ? MIST : "F7F8FA");
    dot(s, x + 0.28, y + 0.28, String(i + 1), novel ? AMBER : TEAL);
    s.addText(t, { x: x + 0.76, y: y + 0.2, w: 5.1, h: 0.34, fontFace: BFONT, fontSize: 12.5, bold: true, color: INK, margin: 0 });
    s.addText(b, { x: x + 0.76, y: y + 0.55, w: 5.15, h: 0.82, fontFace: BFONT, fontSize: 9.5, color: "3E4658", lineSpacing: 12, margin: 0 });
  });
  s.addShape(p.ShapeType.roundRect, { x: M + 6.35, y: 4.82, w: 6.1, h: 1.44, rectRadius: 0.07, fill: { color: INK }, line: { width: 0 }, shadow: shadow() });
  s.addText("Core novelty claim", { x: M + 6.63, y: 5.0, w: 5.4, h: 0.3, fontFace: BFONT, fontSize: 10.5, bold: true, color: AMBER, charSpacing: 1.4, margin: 0 });
  s.addText("Not a better partitioning algorithm - the same classical DP the literature already uses, placed inside a kernel-measured feedback loop that never stops running.",
    { x: M + 6.63, y: 5.34, w: 5.5, h: 0.85, fontFace: BFONT, fontSize: 11.5, color: "D3D9E2", lineSpacing: 15.5, margin: 0 });
  foot(s, 7, "Amber-numbered items are the primary novelty claims.");
  s.addNotes("Be explicit that the DP itself is classical - the novelty is the loop it sits inside and the telemetry that feeds it.");
}

/* ------------------------------------------------ 8. Architecture */
{
  const s = p.addSlide();
  head(s, "Proposed work", "The closed loop");
  const stages = [
    ["WATCH", "eBPF + NVML", "tp_btf/tcp_probe gives per-flow sRTT and fentry/tcp_sendmsg gives throughput. GPU temperature and derated speed come from NVML or /sys/class/thermal.", "internal/ebpf + cmd/nodeagent", AMBER],
    ["DECIDE", "linear partition DP", "Exact O(N^2 K) minimisation of the bottleneck stage cost, gated by a 15% improvement threshold and a 30 s cooldown.", "internal/partition", TEAL],
    ["ACT", "K8s controller", "Hot-reassigns layer ranges over gRPC with no pod restart, recording state in the InferencePipeline CRD with a monotonic generation.", "cmd/controller", AMBER],
    ["HEAL", "heartbeat watchdog", "A 3 s stale heartbeat marks a node gone and forces an immediate repartition across the surviving workers, bypassing hysteresis.", "internal/controller", TEAL],
  ];
  stages.forEach(([t, sub, body, path, col], i) => {
    const x = M + i * 3.08;
    card(s, x, 1.62, 2.82, 3.5, PAPER);
    s.addShape(p.ShapeType.roundRect, { x, y: 1.62, w: 2.82, h: 3.5, rectRadius: 0.07, fill: { color: "FFFFFF" }, line: { color: LINE, width: 1 } });
    s.addShape(p.ShapeType.ellipse, { x: x + 0.26, y: 1.88, w: 0.42, h: 0.42, fill: { color: col }, line: { width: 0 } });
    s.addText(String(i + 1), { x: x + 0.26, y: 1.88, w: 0.42, h: 0.42, fontFace: BFONT, fontSize: 14, bold: true, color: "FFFFFF", align: "center", valign: "middle", margin: 0 });
    s.addText(t, { x: x + 0.8, y: 1.9, w: 1.9, h: 0.3, fontFace: HFONT, fontSize: 17, bold: true, color: INK, margin: 0 });
    s.addText(sub, { x: x + 0.8, y: 2.2, w: 1.9, h: 0.24, fontFace: BFONT, fontSize: 9, color: col, bold: true, margin: 0 });
    s.addText(body, { x: x + 0.26, y: 2.6, w: 2.32, h: 1.82, fontFace: BFONT, fontSize: 9.5, color: "3E4658", valign: "top", lineSpacing: 13, margin: 0 });
    s.addText(path, { x: x + 0.26, y: 4.55, w: 2.35, h: 0.4, fontFace: MFONT, fontSize: 7.5, color: MUTED, margin: 0 });
    if (i < 3) {
      s.addShape(p.ShapeType.rightArrow, { x: x + 2.88, y: 3.22, w: 0.16, h: 0.3, fill: { color: "B6BDCA" }, line: { width: 0 } });
    }
  });
  // return path
  s.addShape(p.ShapeType.line, { x: M + 0.6, y: 5.42, w: 11.5, h: 0, line: { color: "B6BDCA", width: 1.25, dashType: "dash", endArrowType: "triangle" }, flipH: true });
  s.addText("loop repeats every 2 s", {
    x: M, y: 5.5, w: 12.1, h: 0.3, fontFace: BFONT, fontSize: 10.5, color: MUTED, italic: true, align: "center", margin: 0,
  });
  s.addShape(p.ShapeType.roundRect, { x: M, y: 5.95, w: W - 2 * M, h: 0.72, rectRadius: 0.06, fill: { color: MIST }, line: { width: 0 } });
  s.addText("Consistency: every assignment carries a generation. Workers reject stale-generation forwards; the router refetches the layout and replays the accumulated context. Workers are stateless, so replay is trivially correct.",
    { x: M + 0.28, y: 6.05, w: 11.6, h: 0.55, fontFace: BFONT, fontSize: 10.5, color: "3E4658", valign: "middle", lineSpacing: 14, margin: 0 });
  foot(s, 8, "");
  s.addNotes("Walk the loop left to right, then emphasise that the dashed return arrow is what the related work is missing.");
}

/* ------------------------------------------------ 9. Formulation */
{
  const s = p.addSlide();
  head(s, "Proposed work", "Formulation and stability");
  card(s, M, 1.58, 6.1, 2.5);
  s.addText("Objective", { x: M + 0.3, y: 1.78, w: 5, h: 0.3, fontFace: BFONT, fontSize: 12.5, bold: true, color: AMBER, margin: 0 });
  s.addText("minimise  max   cost(i)\n           i in 1..K", {
    x: M + 0.3, y: 2.12, w: 5.5, h: 0.62, fontFace: MFONT, fontSize: 13, bold: true, color: INK, lineSpacing: 16, margin: 0 });
  s.addText("cost(i) = layers(i) x perLayerMs / speed(i)  +  linkMs(i-1)", {
    x: M + 0.3, y: 2.82, w: 5.6, h: 0.3, fontFace: MFONT, fontSize: 10, color: "3E4658", margin: 0 });
  s.addText("subject to contiguous, non-overlapping ranges covering all N layers. An empty stage costs nothing - so the DP may bypass a worker entirely when its link has degraded past the value of its compute.",
    { x: M + 0.3, y: 3.18, w: 5.55, h: 0.78, fontFace: BFONT, fontSize: 10.5, color: "3E4658", lineSpacing: 14, margin: 0 });

  card(s, M, 4.24, 6.1, 2.0);
  s.addText("Solution", { x: M + 0.3, y: 4.42, w: 5, h: 0.3, fontFace: BFONT, fontSize: 12.5, bold: true, color: TEAL, margin: 0 });
  s.addText("f[j][w] = min over split of  max( f[split][w-1], cost(w, j - split) )", {
    x: M + 0.3, y: 4.76, w: 5.6, h: 0.3, fontFace: MFONT, fontSize: 9.5, color: INK, margin: 0 });
  s.addText("The classical linear-partition recurrence: minimal bottleneck for the first j layers over the first w workers. O(N^2 K) - about 1.7k operations for N=12, K=3, so re-solving at 0.5 Hz is free. Verified against brute force on 200 randomised instances.",
    { x: M + 0.3, y: 5.12, w: 5.55, h: 1.0, fontFace: BFONT, fontSize: 10.5, color: "3E4658", lineSpacing: 14, margin: 0 });

  card(s, 7.05, 1.58, 5.66, 4.66, INK);
  s.addText("Why a bare optimiser is not a controller", {
    x: 7.35, y: 1.82, w: 5.0, h: 0.3, fontFace: BFONT, fontSize: 12.5, bold: true, color: AMBER, margin: 0 });
  s.addText("Telemetry is noisy. Re-applying the argmin on every 2 s tick would thrash the pipeline for sub-millisecond gains. Three rules turn the optimiser into a stable controller:",
    { x: 7.35, y: 2.2, w: 5.06, h: 0.85, fontFace: BFONT, fontSize: 10.5, color: "AEB6C4", lineSpacing: 14, margin: 0 });
  const rules = [
    ["Improvement threshold", "Apply only if the new split beats the current one, re-evaluated under current telemetry, by 15%."],
    ["Cooldown", "At most one change per 30 s, so a transient spike cannot start an oscillation."],
    ["Membership override", "A changed worker set bypasses both gates and repartitions immediately - correctness beats stability."],
  ];
  rules.forEach(([t, b], i) => {
    const y = 3.2 + i * 1.02;
    s.addShape(p.ShapeType.ellipse, { x: 7.35, y: y + 0.04, w: 0.26, h: 0.26, fill: { color: i === 2 ? AMBER : TEAL }, line: { width: 0 } });
    s.addText(t, { x: 7.73, y, w: 4.6, h: 0.28, fontFace: BFONT, fontSize: 11.5, bold: true, color: "FFFFFF", margin: 0 });
    s.addText(b, { x: 7.73, y: y + 0.3, w: 4.65, h: 0.62, fontFace: BFONT, fontSize: 10, color: "9AA3B4", lineSpacing: 13, margin: 0 });
  });
  s.addText("Both thresholds are tunable live via IMPROVEMENT_FRAC and COOLDOWN_S.", {
    x: 7.35, y: 6.3, w: 5.06, h: 0.28, fontFace: MFONT, fontSize: 8, color: "7C8698", margin: 0 });
  foot(s, 9, "");
  s.addNotes("The DP is textbook. The contribution on this slide is the hysteresis that makes re-solving safe to do continuously.");
}

/* ------------------------------------------------ 10. Implementation */
{
  const s = p.addSlide();
  head(s, "Proposed work", "Implementation");
  const comps = [
    ["Node agent", "Go + C (CO-RE BPF)", "Privileged DaemonSet. Attaches tp_btf/tcp_probe and fentry/tcp_sendmsg, filtered to worker ports, and exports per-flow sRTT plus GPU state through a pluggable gpu.Reader (simulated / cputherm / nvml).", AMBER],
    ["Controller", "Go, controller-runtime", "Aggregates telemetry, runs the Decider, writes assignments into the InferencePipeline CRD and pushes them to workers over gRPC. Watchdog forces repartition on a 3 s stale heartbeat.", TEAL],
    ["Workers + router", "Python", "Stateless shard servers with pluggable sim and gpt2 backends, on WORKER_DEVICE=auto|cuda|cpu. The router drives stages hub-and-spoke and replays context on a generation mismatch.", AMBER],
    ["Benchmark harness", "Python", "Five fault scenarios x three modes, measuring bubble time, tokens/s and TTFT; plus a hysteresis sweep and a predicted-vs-measured fidelity check.", TEAL],
  ];
  comps.forEach(([t, tech, b, col], i) => {
    const y = 1.58 + i * 1.18;
    card(s, M, y, 7.55, 1.04, i % 2 === 0 ? MIST : "F7F8FA");
    s.addShape(p.ShapeType.ellipse, { x: M + 0.26, y: y + 0.36, w: 0.3, h: 0.3, fill: { color: col }, line: { width: 0 } });
    s.addText(t, { x: M + 0.7, y: y + 0.16, w: 2.4, h: 0.3, fontFace: BFONT, fontSize: 12.5, bold: true, color: INK, margin: 0 });
    s.addText(tech, { x: M + 0.7, y: y + 0.46, w: 2.4, h: 0.26, fontFace: MFONT, fontSize: 8.5, color: MUTED, margin: 0 });
    s.addText(b, { x: M + 3.2, y: y + 0.14, w: 4.9, h: 0.8, fontFace: BFONT, fontSize: 9.5, color: "3E4658", lineSpacing: 12.5, margin: 0 });
  });
  card(s, 8.5, 1.58, 4.21, 4.64, INK);
  s.addText("Deployment reality", { x: 8.8, y: 1.82, w: 3.6, h: 0.3, fontFace: BFONT, fontSize: 12, bold: true, color: AMBER, margin: 0 });
  const facts = [
    "eBPF is real, not simulated - CO-RE against the host BTF, loaded with cilium/ebpf.",
    "kind gives one host: real eBPF, loopback network, simulated GPU.",
    "k3s scripts turn laptops and GPU boxes on a LAN into the same cluster with zero YAML editing.",
    "GPU_MODE=nvml on NVIDIA nodes; GPU_MODE=cputherm reads /sys/class/thermal on GPU-less laptops.",
    "Distributed GPT-2 output is token-identical to single-process HuggingFace.",
  ];
  facts.forEach((f, i) => {
    const y = 2.28 + i * 0.79;
    s.addShape(p.ShapeType.ellipse, { x: 8.8, y: y + 0.06, w: 0.11, h: 0.11, fill: { color: TEAL }, line: { width: 0 } });
    s.addText(f, { x: 9.04, y, w: 3.42, h: 0.72, fontFace: BFONT, fontSize: 9.5, color: "AEB6C4", lineSpacing: 12.5, margin: 0 });
  });
  foot(s, 10, "");
  s.addNotes("Emphasise that the eBPF layer is genuinely loaded into the kernel; only the GPU reader has a simulated option.");
}

/* ------------------------------------------------ 11. Results: chart */
{
  const s = p.addSlide();
  head(s, "Results", "Bottleneck-stage cost under injected faults");
  const cats = ["Baseline", "Thermal\nthrottle", "Network\ndegradation", "Thermal +\nnetwork"];
  s.addChart(p.ChartType.bar, [
    { name: "KubeEdgeInfer (live telemetry)", labels: cats, values: [42, 52, 62, 62] },
    { name: "Profile-once (offline profiling)", labels: cats, values: [42, 102, 122, 182] },
    { name: "Static equal split", labels: cats, values: [42, 102, 122, 182] },
  ], {
    x: M, y: 1.5, w: 7.75, h: 4.95,
    barDir: "col", barGapWidthPct: 55,
    chartColors: [TEAL, AMBER, "B6BDCA"],
    showTitle: true, title: "Per-token bottleneck cost (ms) - lower is better",
    titleFontFace: BFONT, titleFontSize: 12, titleColor: INK,
    showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 8.5,
    dataLabelColor: "4A5264", dataLabelFontFace: BFONT,
    showLegend: true, legendPos: "b", legendFontFace: BFONT, legendFontSize: 9.5, legendColor: "4A5264",
    catAxisLabelColor: "4A5264", catAxisLabelFontFace: BFONT, catAxisLabelFontSize: 9.5,
    valAxisLabelColor: "4A5264", valAxisLabelFontFace: BFONT, valAxisLabelFontSize: 9,
    valGridLine: { color: "E8EAEF", size: 1 }, catGridLine: { style: "none" },
    valAxisMaxVal: 200,
  });
  const gains = [["49%", "vs both baselines\nunder thermal throttle"], ["49%", "vs both baselines\nunder link degradation"], ["66%", "vs both baselines\nwhen the two coincide"]];
  gains.forEach(([n, l], i) => {
    const y = 1.72 + i * 1.36;
    card(s, 8.55, y, 4.16, 1.2, i === 2 ? INK : MIST);
    s.addText(n, { x: 8.85, y: y + 0.14, w: 1.5, h: 0.6, fontFace: HFONT, fontSize: 32, bold: true, color: i === 2 ? AMBER : TEAL, margin: 0 });
    s.addText(l, { x: 10.3, y: y + 0.24, w: 2.2, h: 0.75, fontFace: BFONT, fontSize: 10, color: i === 2 ? "AEB6C4" : "3E4658", lineSpacing: 13, margin: 0 });
  });
  card(s, 8.55, 5.8, 4.16, 0.9, "FBEDE2");
  s.addText("Node failure: the static split is undefined over a worker set that no longer exists - the pipeline stops. KubeEdgeInfer heals to 62 ms.",
    { x: 8.82, y: 5.9, w: 3.65, h: 0.72, fontFace: BFONT, fontSize: 9.5, color: "7A4A22", valign: "middle", lineSpacing: 12, margin: 0 });
  foot(s, 11, "Partitioner-level evaluation via bench/dpsim (N=12 layers, K=3 stages, 10 ms/layer, 0.4x throttle, 80 ms netem).");
  s.addNotes("These are the DP's own objective values, reproducible with `go run ./bench/dpsim`. Profile-once matches static here because the pre-fault cluster is homogeneous - it differs only in that it still heals on node loss.");
}

/* ------------------------------------------------ 12. Results: behaviour */
{
  const s = p.addSlide();
  head(s, "Results", "What the partitioner actually does");
  const splits = [
    ["Baseline", "3 healthy stages", ["0-4", "4-8", "8-12"], "42 ms", TEAL],
    ["Thermal throttle on stage 2", "speed 1.0 -> 0.4", ["0-5", "5-7", "7-12"], "52 ms", AMBER],
    ["80 ms delay on the hop into stage 2", "link 2 -> 82 ms", ["0-6", "empty", "6-12"], "62 ms", AMBER],
    ["Stage 3 lost", "3 workers -> 2", ["0-6", "6-12", ""], "62 ms", AMBER],
  ];
  splits.forEach(([t, sub, ranges, cost, col], i) => {
    const y = 1.55 + i * 1.16;
    card(s, M, y, 7.6, 1.02, i === 0 ? MIST : "F7F8FA");
    s.addText(t, { x: M + 0.26, y: y + 0.14, w: 3.3, h: 0.3, fontFace: BFONT, fontSize: 11.5, bold: true, color: INK, margin: 0 });
    s.addText(sub, { x: M + 0.26, y: y + 0.44, w: 3.3, h: 0.26, fontFace: MFONT, fontSize: 8.5, color: MUTED, margin: 0 });
    ranges.forEach((r, j) => {
      if (!r) return;
      const x = M + 3.75 + j * 1.02;
      const empty = r === "empty";
      s.addShape(p.ShapeType.roundRect, {
        x, y: y + 0.28, w: 0.92, h: 0.46, rectRadius: 0.06,
        fill: { color: empty ? "E6E9EF" : "FFFFFF" }, line: { color: empty ? "C3C9D4" : col, width: 1.25 },
      });
      s.addText(r, {
        x, y: y + 0.28, w: 0.92, h: 0.46, fontFace: MFONT, fontSize: empty ? 8 : 9.5,
        bold: !empty, color: empty ? MUTED : INK, align: "center", valign: "middle", margin: 0,
      });
    });
    s.addText(cost, { x: M + 6.6, y: y + 0.3, w: 0.95, h: 0.42, fontFace: HFONT, fontSize: 15, bold: true, color: col, align: "right", valign: "middle", margin: 0 });
  });
  s.addText("layer ranges assigned to stage 1 / 2 / 3", {
    x: M + 3.75, y: 1.26, w: 3.2, h: 0.24, fontFace: BFONT, fontSize: 8.5, color: MUTED, margin: 0 });

  card(s, 8.55, 1.55, 4.16, 2.34, INK);
  s.addText("Stage bypass", { x: 8.85, y: 1.78, w: 3.5, h: 0.3, fontFace: BFONT, fontSize: 12.5, bold: true, color: AMBER, margin: 0 });
  s.addText("Under an 80 ms link the DP assigns stage 2 an empty range. Because an empty stage costs nothing - not even its hop - the router skips it entirely, and the two remaining nodes absorb all 12 layers. The optimiser discovers node exclusion without any special-case rule for it.",
    { x: 8.85, y: 2.16, w: 3.6, h: 1.6, fontFace: BFONT, fontSize: 10, color: "AEB6C4", lineSpacing: 13.5, margin: 0 });

  const checks = [
    ["Optimality", "DP output matches brute force on 200 randomised instances."],
    ["Correctness", "3-stage distributed GPT-2 is token-identical to single-process greedy decoding."],
    ["Model fidelity", "Predicted vs measured bottleneck tracks at a stable 3.0-3.24x ratio: a reliable ranking signal, not a calibrated latency."],
  ];
  checks.forEach(([t, b], i) => {
    const y = 4.06 + i * 0.78;
    s.addShape(p.ShapeType.ellipse, { x: 8.55, y: y + 0.04, w: 0.26, h: 0.26, fill: { color: TEAL }, line: { width: 0 } });
    s.addText(t, { x: 8.93, y, w: 3.6, h: 0.26, fontFace: BFONT, fontSize: 11, bold: true, color: INK, margin: 0 });
    s.addText(b, { x: 8.93, y: y + 0.27, w: 3.72, h: 0.5, fontFace: BFONT, fontSize: 9, color: "4A5264", lineSpacing: 11.5, margin: 0 });
  });
  foot(s, 12, "End-to-end tokens/s, TTFT and measured bubble time come from bench/run.py, which requires a live cluster.");
  s.addNotes("The netem row is the most interesting result: the exact optimiser drops a node on its own.");
}

/* ------------------------------------------------ 13. Comparison */
{
  const s = p.addSlide();
  head(s, "Comparison", "Against the closest systems");
  const cols = ["", "EdgeShard\n(IoT-J 24)", "Galaxy\n(INFOCOM 24)", "Helix\n(ASPLOS 25)", "prima.cpp\n(2025)", "KubeEdgeInfer"];
  const rows = [
    ["Parallelism", "pipeline", "tensor + sequence", "pipeline + routing", "pipelined ring", "pipeline"],
    ["Placement method", "DP (exact)", "heuristic planner", "MILP on max-flow", "Halda scheduler", "DP (exact)"],
    ["Telemetry source", "offline profile", "offline profile", "cluster profile", "device capability", "eBPF + NVML, live"],
    ["Re-plan while serving", "no", "no", "routing only", "no", "every 2 s"],
    ["Handles thermal drift", "no", "no", "no", "no", "yes"],
    ["Handles node loss", "no", "no", "replication", "no", "yes, 3 s watchdog"],
    ["Target hardware", "15 edge devices", "edge devices", "24-42 GPU nodes", "home cluster", "consumer edge + k3s"],
    ["Reported gain", "50% latency", "2.5x latency", "3.3x throughput", "5-17x TPOT", "49-66% bottleneck*"],
  ];
  const colX = [M, 3.05, 4.75, 6.55, 8.4, 10.15];
  const colW = [2.4, 1.65, 1.75, 1.8, 1.7, 2.56];
  s.addShape(p.ShapeType.roundRect, { x: M, y: 1.5, w: W - 2 * M, h: 0.68, rectRadius: 0.05, fill: { color: INK }, line: { width: 0 } });
  cols.forEach((c, ci) => {
    s.addText(c, { x: colX[ci], y: 1.5, w: colW[ci], h: 0.68, fontFace: BFONT, fontSize: 9, bold: true, color: ci === 5 ? AMBER : "FFFFFF", valign: "middle", lineSpacing: 10.5, margin: 0 });
  });
  rows.forEach((r, ri) => {
    const y = 2.24 + ri * 0.53;
    if (ri % 2 === 0) s.addShape(p.ShapeType.rect, { x: M, y, w: W - 2 * M, h: 0.5, fill: { color: "F7F8FA" }, line: { width: 0 } });
    r.forEach((cell, ci) => {
      s.addText(cell, {
        x: colX[ci], y, w: colW[ci], h: 0.5, fontFace: BFONT, fontSize: 9.5,
        bold: ci === 0 || ci === 5, color: ci === 5 ? TEAL : (ci === 0 ? INK : "4A5264"),
        valign: "middle", margin: 0,
      });
    });
  });
  s.addShape(p.ShapeType.roundRect, {
    x: 10.05, y: 1.5, w: 2.66, h: 4.96, rectRadius: 0.05,
    fill: { type: "solid", color: TEAL, transparency: 93 }, line: { color: TEAL, width: 1.25 },
  });
  foot(s, 13, "* Bottleneck-stage cost vs a static split and a profile-once ablation; not directly comparable to the end-to-end figures in the other columns.");
  s.addNotes("Be careful and honest here: the gain column measures different quantities across systems. Say so out loud.");
}

/* ------------------------------------------------ 14. Conclusion */
{
  const s = p.addSlide(); darkBg(s);
  s.addShape(p.ShapeType.ellipse, { x: -1.4, y: 4.6, w: 4.4, h: 4.4, fill: { color: INK2 }, line: { width: 0 } });
  s.addText("CONCLUSION", { x: M, y: 0.72, w: 8, h: 0.3, fontFace: BFONT, fontSize: 11.5, bold: true, color: AMBER, charSpacing: 2.6, margin: 0 });
  s.addText("The split point should be a control variable, not a deployment constant.", {
    x: M, y: 1.2, w: 8.3, h: 1.35, fontFace: HFONT, fontSize: 28, bold: true, color: "FFFFFF", lineSpacing: 36, margin: 0 });
  s.addText("KubeEdgeInfer keeps a classical exact partitioner permanently in the loop, fed by kernel-measured latency and real thermal state, and applies its decisions to a running pipeline without a restart. On a heterogeneous edge cluster that is the difference between a plan that was right once and a plan that stays right.",
    { x: M, y: 2.66, w: 8.3, h: 1.3, fontFace: BFONT, fontSize: 13, color: "AEB6C4", lineSpacing: 20, margin: 0 });

  const takeaways = [
    ["Exactness is cheap", "The DP costs microseconds; there is no reason to solve it only once."],
    ["Hysteresis is what makes it usable", "One improvement threshold and one cooldown tame thermal, network and failure triggers alike."],
    ["Kernel telemetry needs no instrumentation", "eBPF measures the real transport, not what the application thinks it sent."],
  ];
  takeaways.forEach(([t, b], i) => {
    const y = 4.28 + i * 0.86;
    dot(s, M, y, String(i + 1), i === 0 ? AMBER : TEAL);
    s.addText(t, { x: M + 0.48, y: y - 0.02, w: 7.6, h: 0.28, fontFace: BFONT, fontSize: 12, bold: true, color: "FFFFFF", margin: 0 });
    s.addText(b, { x: M + 0.48, y: y + 0.27, w: 7.7, h: 0.44, fontFace: BFONT, fontSize: 10, color: "9AA3B4", lineSpacing: 12.5, margin: 0 });
  });

  s.addShape(p.ShapeType.roundRect, { x: 9.25, y: 2.66, w: 3.46, h: 3.92, rectRadius: 0.08, fill: { color: INK2 }, line: { color: "3A4356", width: 1 } });
  s.addText("Future work", { x: 9.55, y: 2.9, w: 2.9, h: 0.3, fontFace: BFONT, fontSize: 12, bold: true, color: AMBER, margin: 0 });
  const fw = [
    "A Llama-class backend so two 8 GB cards hold a real modern LLM across stages.",
    "Sustained multi-tenant load to observe genuine NVML throttling, not just flat curves.",
    "Non-contiguous and attention-head-level assignment, following arXiv:2505.02533.",
    "Calibrating the cost model so the DP's bottleneck becomes a latency prediction, not only a ranking.",
  ];
  fw.forEach((f, i) => {
    const y = 3.32 + i * 0.8;
    s.addShape(p.ShapeType.ellipse, { x: 9.55, y: y + 0.06, w: 0.11, h: 0.11, fill: { color: TEAL }, line: { width: 0 } });
    s.addText(f, { x: 9.79, y, w: 2.72, h: 0.72, fontFace: BFONT, fontSize: 9.5, color: "AEB6C4", lineSpacing: 12.5, margin: 0 });
  });
  foot(s, 14, "");
  s.addNotes("Close on the one-line thesis, then the honest limits.");
}

/* ------------------------------------------------ 15. References */
{
  const s = p.addSlide();
  head(s, "References", "All works cited");
  const refs = [
    "[1]  EdgeShard: Efficient LLM Inference via Collaborative Edge Computing. M. Zhang, J. Cao, X. Shen, Z. Cui. IEEE Internet of Things Journal, 2024. arXiv:2405.14371.",
    "[2]  Galaxy: A Resource-Efficient Collaborative Edge AI System for In-situ Transformer Inference. IEEE INFOCOM, 2024. arXiv:2405.17245.",
    "[3]  Helix: Serving Large Language Models over Heterogeneous GPUs and Network via Max-Flow. ACM ASPLOS, 2025. arXiv:2406.01566.",
    "[4]  TPI-LLM: Serving 70B-scale LLMs Efficiently on Low-resource Edge Devices. 2024. arXiv:2410.00531.",
    "[5]  Prima.cpp: Fast 30-70B LLM Inference on Heterogeneous and Low-Resource Home Clusters. 2025. arXiv:2504.08791.",
    "[6]  Large Language Model Partitioning for Low-Latency Inference at the Edge. 2025. arXiv:2505.02533.",
    "[7]  Parallax: Efficient LLM Inference Service over Decentralized Environment. 2025. arXiv:2509.26182.",
    "[8]  Adaptive layer splitting for wireless large language model inference in edge computing: a model-based reinforcement learning approach. Frontiers of Information Technology & Electronic Engineering, Springer, 2025. doi:10.1631/FITEE.2400468.",
    "[9]  Distributed LLMs and Multimodal Large Language Models: A Survey on Advances, Challenges, and Future Directions. 2025. arXiv:2503.16585.",
    "[10] Towards Agentic OS: An LLM Agent Framework for Linux Schedulers. 2025. arXiv:2509.01245.",
  ];
  refs.forEach((r, i) => {
    const y = 1.5 + i * 0.5;
    if (i % 2 === 0) s.addShape(p.ShapeType.rect, { x: M, y, w: W - 2 * M, h: 0.47, fill: { color: "F7F8FA" }, line: { width: 0 } });
    s.addText(r, { x: M + 0.22, y, w: W - 2 * M - 0.44, h: 0.47, fontFace: BFONT, fontSize: 9.5, color: "3E4658", valign: "middle", margin: 0 });
  });
  s.addText("Tooling: cilium/ebpf (CO-RE loader) · Kubernetes controller-runtime · NVIDIA NVML · k3s · Hugging Face Transformers (GPT-2).", {
    x: M, y: 6.65, w: 11.6, h: 0.3, fontFace: BFONT, fontSize: 9, color: MUTED, italic: true, margin: 0 });
  foot(s, 15, "");
  s.addNotes("Ten works, all 2024-2025.");
}

p.writeFile({ fileName: "KubeEdgeInfer.pptx" }).then(f => console.log("wrote", f));
