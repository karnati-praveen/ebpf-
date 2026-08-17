// KubeEdgeInfer -- 10 slides in the supplied reference template.
//
// Mirrors kubeedgeinfer-classic.tex: navy frame-title bars, rounded blocks with
// a navy header and grey body, a red alertblock, the WATCH/DECIDE/ACT/HEAL flow,
// and a tick/cross novelty table.
const pptxgen = require("pptxgenjs");

const NAVY  = "1B2159";
const RED   = "A31D1D";
const GREY  = "ECECEC";
const GREEN = "1E7A34";
const INK   = "000000";
const PAPER = "FFFFFF";

// Beamer's default face is a Computer Modern sans; Arial is the closest thing
// that ships everywhere and renders true-to-width.
const F  = "Arial";
const FM = "Courier New";

const p = new pptxgen();
p.layout = "LAYOUT_WIDE";        // 13.33 x 7.5
p.title  = "KubeEdgeInfer";

const W = 13.33, H = 7.5, M = 0.55;

function shadow() {
  return { type: "outer", color: "808080", blur: 6, offset: 3, angle: 45, opacity: 0.55 };
}

// The navy title bar every content slide carries.
function frametitle(s, title) {
  s.background = { color: PAPER };
  s.addShape(p.ShapeType.rect, {
    x: 0, y: 0, w: W, h: 0.7, fill: { color: NAVY },
    line: { color: NAVY, width: 0 },
  });
  s.addText(title, {
    x: M, y: 0, w: W - 2 * M, h: 0.7, fontFace: F, fontSize: 19, bold: true,
    color: "FFFFFF", valign: "middle", margin: 0,
  });
}

function pageNo(s, n) {
  s.addText(`${n} / 10`, {
    x: W - M - 0.9, y: H - 0.5, w: 0.9, h: 0.28, fontFace: F, fontSize: 9,
    color: "404040", align: "right", margin: 0,
  });
}

// A beamer block: navy header strip over a grey body, rounded, with a shadow.
function block(s, x, y, w, h, title, body, alerted, bodySize) {
  const head = 0.36;
  s.addShape(p.ShapeType.roundRect, {
    x, y, w, h, rectRadius: 0.05, fill: { color: GREY },
    line: { color: GREY, width: 0 }, shadow: shadow(),
  });
  s.addShape(p.ShapeType.roundRect, {
    x, y, w, h: head, rectRadius: 0.07,
    fill: { color: alerted ? RED : NAVY },
    line: { color: alerted ? RED : NAVY, width: 0 },
  });
  // Square off the bottom of the header so it meets the body cleanly.
  s.addShape(p.ShapeType.rect, {
    x, y: y + head - 0.1, w, h: 0.1,
    fill: { color: alerted ? RED : NAVY },
    line: { color: alerted ? RED : NAVY, width: 0 },
  });
  s.addText(title, {
    x: x + 0.16, y, w: w - 0.32, h: head, fontFace: F, fontSize: 12.5,
    bold: true, color: "FFFFFF", valign: "middle", margin: 0,
  });
  s.addText(body, {
    x: x + 0.16, y: y + head + 0.06, w: w - 0.32, h: h - head - 0.14,
    fontFace: F, fontSize: bodySize || 12, color: INK, valign: "top",
    lineSpacing: (bodySize || 12) * 1.35, margin: 0,
  });
}

// A beamer itemize: navy bullet, black text, hanging indent.
function itemize(s, x, y, w, items, size, gap) {
  const fs = size || 13.5;
  let cy = y;
  items.forEach((t) => {
    const lines = Math.max(1, Math.ceil(t.replace(/\*\*/g, "").length / (w * 10.2)));
    const h = lines * fs * 1.42 / 72;
    s.addText("•", {
      x, y: cy, w: 0.2, h: fs * 1.5 / 72, fontFace: F, fontSize: fs,
      color: NAVY, margin: 0,
    });
    s.addText(runs(t, fs), {
      x: x + 0.24, y: cy, w: w - 0.24, h, fontFace: F, fontSize: fs,
      color: INK, valign: "top", lineSpacing: fs * 1.42, margin: 0,
    });
    cy += h + (gap === undefined ? 0.16 : gap);
  });
  return cy;
}

// **bold** markers -> pptx rich-text runs.
function runs(text, fs) {
  return text.split(/(\*\*[^*]+\*\*)/).filter(Boolean).map((part) => {
    const b = part.startsWith("**") && part.endsWith("**");
    return { text: b ? part.slice(2, -2) : part, options: { bold: b, fontSize: fs } };
  });
}

/* ------------------------------------------------------------- 1. Title */
{
  const s = p.addSlide();
  s.background = { color: PAPER };
  s.addShape(p.ShapeType.roundRect, {
    x: 1.05, y: 1.05, w: W - 2.1, h: 1.72, rectRadius: 0.06,
    fill: { color: NAVY }, line: { color: NAVY, width: 0 }, shadow: shadow(),
  });
  s.addText("KubeEdgeInfer", {
    x: 1.05, y: 1.2, w: W - 2.1, h: 0.5, fontFace: F, fontSize: 22, bold: true,
    color: "FFFFFF", align: "center", margin: 0,
  });
  s.addText("A Closed-Loop, eBPF-Driven Kubernetes Framework for Heterogeneous\nDistributed LLM Inference on Consumer Edge Clusters", {
    x: 1.35, y: 1.75, w: W - 2.7, h: 0.9, fontFace: F, fontSize: 14,
    color: "FFFFFF", align: "center", lineSpacing: 21, margin: 0,
  });

  s.addText("Your Name", {
    x: M, y: 3.35, w: W - 2 * M, h: 0.4, fontFace: F, fontSize: 16,
    color: INK, align: "center", margin: 0,
  });
  s.addText("Department of ________", {
    x: M, y: 3.95, w: W - 2 * M, h: 0.3, fontFace: F, fontSize: 11,
    color: INK, align: "center", margin: 0,
  });
  s.addText("Guide: Sir's Name", {
    x: M, y: 4.22, w: W - 2 * M, h: 0.3, fontFace: F, fontSize: 11,
    color: INK, align: "center", margin: 0,
  });
  s.addText("Date", {
    x: M, y: 4.75, w: W - 2 * M, h: 0.35, fontFace: F, fontSize: 14,
    color: INK, align: "center", margin: 0,
  });
  s.addText("1 / 10", {
    x: W - M - 0.9, y: H - 0.5, w: 0.9, h: 0.28, fontFace: F, fontSize: 9,
    color: "404040", align: "right", margin: 0,
  });
  s.addNotes("Fill in your name, department, guide and date before presenting.");
}

/* ------------------------------------------------------- 2. Introduction */
{
  const s = p.addSlide();
  frametitle(s, "Introduction");
  itemize(s, M + 0.35, 1.15, 11.9, [
    "Large Language Models (LLMs) are often too large to fit on a single consumer GPU.",
    "**Pipeline parallelism** solves this by splitting model layers across several machines, forming an inference assembly line.",
    "Existing frameworks are built either for stable datacenter interconnects, or they split layers **statically** and never revisit that decision.",
    "Consumer and edge hardware is inherently **heterogeneous**: different GPU generations, WiFi rather than Ethernet, and thermal variance under sustained load.",
  ], 13.5, 0.26);
  block(s, M, 5.1, W - 2 * M, 1.0, "Core Idea",
    "Continuously observe real hardware conditions at the kernel level, and let the model's layer partition adapt to them instead of staying fixed.");
  pageNo(s, 2);
}

/* -------------------------------------------------- 3. Literature Review */
{
  const s = p.addSlide();
  frametitle(s, "Literature Review");
  const cols = ["Work", "Year", "Contribution", "Gap this work addresses"];
  const rows = [
    ["EdgeShard", "2024", "DP device selection and layer partition", "Profiled offline; plan never revisited"],
    ["Galaxy", "2024", "Tensor/sequence parallelism with overlap", "One-shot planning, no adaptation"],
    ["Helix", "2025", "Max-flow MILP over mixed GPUs", "Solver too heavy for a live loop"],
    ["TPI-LLM", "2024", "Memory scheduling for 70B on small RAM", "Optimises memory, not degradation"],
    ["prima.cpp", "2025", "CPU/GPU co-scheduling on home clusters", "Schedule fixed at load time"],
    ["Head-level split", "2025", "Attention-head granularity, with migration", "Triggered by memory pressure only"],
    ["Parallax", "2025", "Serving over volunteer machines", "No kernel-level measurement"],
    ["Adaptive split (MBRL)", "2025", "Learns the split point as the channel varies", "Needs training; no optimality proof"],
    ["Distributed LLM survey", "2025", "Surveys the field", "Names adaptation as an open problem"],
    ["sched_ext (eBPF)", "2025", "Linux schedulers loaded as eBPF programs", "Single host; no model pipeline"],
  ];
  const cx = [M + 0.3, 2.85, 3.55, 8.05];
  const cw = [2.45, 0.65, 4.4, 4.3];
  const top = 1.1, rh = 0.38;

  s.addShape(p.ShapeType.line, { x: M + 0.3, y: top, w: 12.05, h: 0, line: { color: INK, width: 1.25 } });
  cols.forEach((c, i) => {
    s.addText(c, {
      x: cx[i], y: top + 0.04, w: cw[i], h: 0.32, fontFace: F, fontSize: 10.5,
      bold: true, color: INK, valign: "middle", margin: 0,
    });
  });
  s.addShape(p.ShapeType.line, { x: M + 0.3, y: top + 0.4, w: 12.05, h: 0, line: { color: INK, width: 0.75 } });
  rows.forEach((r, ri) => {
    const y = top + 0.46 + ri * rh;
    r.forEach((cell, ci) => {
      s.addText(cell, {
        x: cx[ci], y, w: cw[ci], h: rh, fontFace: F, fontSize: 10,
        color: INK, valign: "middle", margin: 0,
      });
    });
  });
  s.addShape(p.ShapeType.line, {
    x: M + 0.3, y: top + 0.46 + rows.length * rh, w: 12.05, h: 0,
    line: { color: INK, width: 1.25 },
  });
  block(s, M, 5.85, W - 2 * M, 0.8, "Common limitation",
    "Every one of these measures the hardware before the run, and never measures again.");
  pageNo(s, 3);
}

/* ---------------------------------------------------- 4. Problem Statement */
{
  const s = p.addSlide();
  frametitle(s, "Problem Statement");
  s.addText("Static partitioning ignores real-time hardware variability.", {
    x: M + 0.35, y: 1.15, w: 11, h: 0.4, fontFace: F, fontSize: 15, bold: true,
    color: INK, margin: 0,
  });
  const bw = 3.95;
  block(s, M, 2.0, bw, 1.2, "Thermal Throttling",
    "GPUs slow down mid-inference as they heat up under sustained load.");
  block(s, M + 4.14, 2.0, bw, 1.2, "Network Latency",
    "WiFi and edge links have variable latency — no InfiniBand or NVLink at home.");
  block(s, M + 8.28, 2.0, bw, 1.2, "Node Failure",
    "A laptop closes its lid or drops off the network, and its layers go with it.");
  block(s, M, 4.15, W - 2 * M, 0.95, "Consequence: Pipeline Bubble Time",
    "Fast machines sit idle waiting on slower ones. A one-time, fixed split cannot correct itself as conditions change.", true, 13);
  pageNo(s, 4);
}

/* --------------------------------------------- 5. Objectives / Contributions */
{
  const s = p.addSlide();
  frametitle(s, "Objectives and Contributions");
  const items = [
    "Capture system telemetry — network transfer latency, GPU thermal state, throttling — using **eBPF** and **NVML**, with no change to the model code.",
    "Design a **dynamic partitioning algorithm** that computes the optimal contiguous layer split from live telemetry, and prove it optimal for each snapshot.",
    "Integrate telemetry and partitioning decisions directly into a **Kubernetes** control loop, applying them without restarting pods.",
    "Enable **autonomous healing**: automatic re-partitioning on node failure or sustained thermal throttling.",
    "Stabilise the loop with **hysteresis** — a 15% improvement threshold and a 30 s cooldown — so noisy telemetry cannot cause thrashing.",
    "Evaluate bubble time, throughput and time-to-first-token empirically against static partitioning and an offline-profiling baseline.",
  ];
  let cy = 1.2;
  items.forEach((t, i) => {
    const lines = Math.ceil(t.replace(/\*\*/g, "").length / 118);
    const h = lines * 13.5 * 1.42 / 72;
    s.addShape(p.ShapeType.ellipse, {
      x: M + 0.3, y: cy + 0.02, w: 0.26, h: 0.26, fill: { color: NAVY }, line: { width: 0 },
    });
    s.addText(String(i + 1), {
      x: M + 0.3, y: cy + 0.02, w: 0.26, h: 0.26, fontFace: F, fontSize: 10,
      bold: true, color: "FFFFFF", align: "center", valign: "middle", margin: 0,
    });
    s.addText(runs(t, 13.5), {
      x: M + 0.68, y: cy, w: 11.5, h, fontFace: F, fontSize: 13.5, color: INK,
      valign: "top", lineSpacing: 19, margin: 0,
    });
    cy += h + 0.24;
  });
  pageNo(s, 5);
}

/* -------------------------------------------------------- 6. Architecture */
{
  const s = p.addSlide();
  frametitle(s, "Architecture — How It Works");
  const stages = [
    ["1. WATCH", "eBPF + NVML\nTelemetry"],
    ["2. DECIDE", "DP Partitioning\nAlgorithm"],
    ["3. ACT", "Kubernetes\nController"],
    ["4. HEAL", "Autonomous\nRecovery"],
  ];
  const bw = 2.5, gap = 0.72;
  const x0 = (W - (4 * bw + 3 * gap)) / 2;
  stages.forEach(([t, b], i) => {
    const x = x0 + i * (bw + gap);
    s.addShape(p.ShapeType.roundRect, {
      x, y: 1.2, w: bw, h: 1.15, rectRadius: 0.06,
      fill: { color: PAPER }, line: { color: "737373", width: 1 }, shadow: shadow(),
    });
    s.addText(t, {
      x, y: 1.3, w: bw, h: 0.32, fontFace: F, fontSize: 12.5, bold: true,
      color: INK, align: "center", margin: 0,
    });
    s.addText(b, {
      x, y: 1.62, w: bw, h: 0.62, fontFace: F, fontSize: 11, color: INK,
      align: "center", lineSpacing: 15, margin: 0,
    });
    if (i < 3) {
      s.addShape(p.ShapeType.line, {
        x: x + bw, y: 1.78, w: gap, h: 0,
        line: { color: NAVY, width: 1.75, endArrowType: "triangle" },
      });
    }
  });
  // The return edge: what makes the architecture a loop.
  const lastX = x0 + 3 * (bw + gap) + bw / 2;
  s.addShape(p.ShapeType.line, { x: lastX, y: 2.35, w: 0, h: 0.42, line: { color: NAVY, width: 1.75 } });
  s.addShape(p.ShapeType.line, {
    x: x0 + bw / 2, y: 2.77, w: lastX - (x0 + bw / 2), h: 0,
    line: { color: NAVY, width: 1.75 },
  });
  s.addShape(p.ShapeType.line, {
    x: x0 + bw / 2, y: 2.35, w: 0, h: 0.42,
    line: { color: NAVY, width: 1.75, endArrowType: "triangle" }, flipV: true,
  });
  s.addText("loop repeats continuously", {
    x: x0, y: 2.82, w: 4 * bw + 3 * gap, h: 0.3, fontFace: F, fontSize: 10.5,
    italic: true, color: NAVY, align: "center", margin: 0,
  });
  itemize(s, M + 0.35, 3.55, 11.9, [
    "**Watch:** kernel-level flow latency, GPU temperature, memory, throttle state.",
    "**Decide:** compute the optimal contiguous split from live metrics.",
    "**Act:** re-assign layers, reroute traffic, apply the new split with no restart.",
    "**Heal:** detect node failure within 3 s, re-partition across the survivors.",
  ], 13, 0.2);
  pageNo(s, 6);
}

/* ------------------------------------------------------------- 7. Results */
{
  const s = p.addSlide();
  frametitle(s, "Results");
  const cols = ["Injected condition", "KubeEdgeInfer", "Profile-once", "Static split"];
  const rows = [
    ["No fault", "42 ms", "42 ms", "42 ms"],
    ["Thermal throttle (0.4x)", "52 ms", "102 ms", "102 ms"],
    ["Network delay (80 ms)", "62 ms", "122 ms", "122 ms"],
    ["Thermal + network", "62 ms", "182 ms", "182 ms"],
    ["Node failure", "62 ms", "62 ms", "pipeline stops"],
  ];
  const cx = [2.6, 6.0, 7.9, 9.75];
  const cw = [3.3, 1.8, 1.8, 1.9];
  const top = 1.15, rh = 0.42;
  s.addShape(p.ShapeType.line, { x: 2.6, y: top, w: 9.05, h: 0, line: { color: INK, width: 1.25 } });
  cols.forEach((c, i) => {
    s.addText(c, {
      x: cx[i], y: top + 0.04, w: cw[i], h: 0.34, fontFace: F, fontSize: 12,
      bold: true, color: INK, align: i === 0 ? "left" : "right", valign: "middle", margin: 0,
    });
  });
  s.addShape(p.ShapeType.line, { x: 2.6, y: top + 0.42, w: 9.05, h: 0, line: { color: INK, width: 0.75 } });
  rows.forEach((r, ri) => {
    const y = top + 0.5 + ri * rh;
    r.forEach((cell, ci) => {
      s.addText(cell, {
        x: cx[ci], y, w: cw[ci], h: rh, fontFace: F, fontSize: 12,
        bold: ci === 1 && ri > 0, color: INK,
        align: ci === 0 ? "left" : "right", valign: "middle", margin: 0,
      });
    });
  });
  s.addShape(p.ShapeType.line, {
    x: 2.6, y: top + 0.5 + rows.length * rh, w: 9.05, h: 0, line: { color: INK, width: 1.25 },
  });
  s.addText("Bottleneck-stage cost per token; lower is better. 12 layers over 3 machines.", {
    x: M, y: 3.85, w: W - 2 * M, h: 0.3, fontFace: F, fontSize: 10,
    color: "404040", align: "center", margin: 0,
  });
  block(s, M, 4.35, W - 2 * M, 1.32, "Headline",
    "49% lower bottleneck cost under thermal throttling and under network degradation; 66% lower when both occur together. Under node failure the static split is undefined over the surviving set, so the pipeline stops — KubeEdgeInfer re-partitions and continues.");
  s.addText("Reproducible with go run ./bench/dpsim; end-to-end throughput comes from bench/run.py, which needs a live cluster.", {
    x: M, y: 5.85, w: W - 2 * M, h: 0.3, fontFace: F, fontSize: 9.5,
    italic: true, color: "404040", align: "center", margin: 0,
  });
  pageNo(s, 7);
}

/* ------------------------------------------------------------- 8. Novelty */
{
  const s = p.addSlide();
  frametitle(s, "Novelty");
  const cols = ["Feature", "EdgeShard", "Galaxy", "Helix", "prima.cpp", "Ours"];
  const rows = [
    ["Heterogeneous edge support", 1, 1, 0, 1, 1],
    ["Kernel-level telemetry (eBPF)", 0, 0, 0, 0, 1],
    ["Dynamic re-partitioning", 0, 0, 0, 0, 1],
    ["Thermal awareness", 0, 0, 0, 0, 1],
    ["Autonomous healing", 0, 0, 1, 0, 1],
    ["Declarative K8s API", 0, 0, 0, 0, 1],
  ];
  const cx = [2.3, 5.5, 6.95, 8.2, 9.4, 10.85];
  const cw = [3.2, 1.4, 1.2, 1.15, 1.4, 0.9];
  const top = 1.2, rh = 0.44;
  s.addShape(p.ShapeType.line, { x: 2.3, y: top, w: 9.45, h: 0, line: { color: INK, width: 1.25 } });
  cols.forEach((c, i) => {
    s.addText(c, {
      x: cx[i], y: top + 0.04, w: cw[i], h: 0.36, fontFace: F, fontSize: 12,
      bold: true, color: INK, align: i === 0 ? "left" : "center", valign: "middle", margin: 0,
    });
  });
  s.addShape(p.ShapeType.line, { x: 2.3, y: top + 0.44, w: 9.45, h: 0, line: { color: INK, width: 0.75 } });
  rows.forEach((r, ri) => {
    const y = top + 0.52 + ri * rh;
    s.addText(r[0], {
      x: cx[0], y, w: cw[0], h: rh, fontFace: F, fontSize: 12, color: INK,
      valign: "middle", margin: 0,
    });
    for (let ci = 1; ci <= 5; ci++) {
      s.addText(r[ci] ? "✓" : "✗", {
        x: cx[ci], y, w: cw[ci], h: rh, fontFace: F, fontSize: 14, bold: true,
        color: r[ci] ? GREEN : RED, align: "center", valign: "middle", margin: 0,
      });
    }
  });
  s.addShape(p.ShapeType.line, {
    x: 2.3, y: top + 0.52 + rows.length * rh, w: 9.45, h: 0, line: { color: INK, width: 1.25 },
  });
  block(s, M, 5.0, W - 2 * M, 1.05, "One-line novelty statement",
    "We turn a static, one-time model-splitting decision into a continuous, self-correcting one — driven by real kernel-level measurements instead of assumptions.");
  pageNo(s, 8);
}

/* ------------------------------------------------------------- 9. Summary */
{
  const s = p.addSlide();
  frametitle(s, "Summary");
  itemize(s, M + 0.35, 1.2, 11.9, [
    "First system to close the loop: eBPF/NVML telemetry → Kubernetes scheduling → self-healing, for edge LLM inference.",
    "The partitioner is **provably optimal** for a fixed telemetry snapshot — it reduces to the classical linear partition problem, and is unit-tested against brute force on 200 random instances.",
    "Adaptive behaviour is validated **empirically** through a staged ablation under simulated network, thermal and failure conditions.",
    "Distributed GPT-2 output is **token-identical** to single-process inference, so adaptivity costs no correctness.",
    "Fully software-based and reproducible — no proprietary hardware lab required.",
  ], 13, 0.22);
  s.addText("Thank you — Questions?", {
    x: M, y: 5.5, w: W - 2 * M, h: 0.6, fontFace: F, fontSize: 22, italic: true,
    color: INK, align: "center", margin: 0,
  });
  pageNo(s, 9);
}

/* ---------------------------------------------------------- 10. References */
{
  const s = p.addSlide();
  frametitle(s, "References");
  const refs = [
    "M. Zhang, J. Cao, X. Shen, Z. Cui. EdgeShard: Efficient LLM Inference via Collaborative Edge Computing. IEEE Internet of Things Journal, 2024. arXiv:2405.14371.",
    "Galaxy: A Resource-Efficient Collaborative Edge AI System for In-situ Transformer Inference. IEEE INFOCOM, 2024. arXiv:2405.17245.",
    "Helix: Serving Large Language Models over Heterogeneous GPUs and Network via Max-Flow. ACM ASPLOS, 2025. arXiv:2406.01566.",
    "TPI-LLM: Serving 70B-scale LLMs Efficiently on Low-resource Edge Devices. 2024. arXiv:2410.00531.",
    "Prima.cpp: Fast 30-70B LLM Inference on Heterogeneous and Low-Resource Home Clusters. 2025. arXiv:2504.08791.",
    "Large Language Model Partitioning for Low-Latency Inference at the Edge. 2025. arXiv:2505.02533.",
    "Parallax: Efficient LLM Inference Service over Decentralized Environment. 2025. arXiv:2509.26182.",
    "Adaptive layer splitting for wireless large language model inference in edge computing. FITEE, Springer, 2025. doi:10.1631/FITEE.2400468.",
    "Distributed LLMs and Multimodal Large Language Models: A Survey on Advances, Challenges, and Future Directions. 2025. arXiv:2503.16585.",
    "Towards Agentic OS: An LLM Agent Framework for Linux Schedulers. 2025. arXiv:2509.01245.",
  ];
  refs.forEach((r, i) => {
    const y = 1.12 + i * 0.5;
    s.addText(`[${i + 1}]`, {
      x: M + 0.3, y, w: 0.42, h: 0.46, fontFace: F, fontSize: 10, color: INK,
      valign: "top", lineSpacing: 12.5, margin: 0,
    });
    s.addText(r, {
      x: M + 0.78, y, w: 11.3, h: 0.46, fontFace: F, fontSize: 10, color: INK,
      valign: "top", lineSpacing: 12.5, margin: 0,
    });
  });
  s.addText("Tools: cilium/ebpf (CO-RE loader), Kubernetes controller-runtime, NVIDIA NVML, k3s, Hugging Face Transformers.", {
    x: M + 0.3, y: 6.4, w: 11.8, h: 0.3, fontFace: F, fontSize: 9.5,
    color: "404040", margin: 0,
  });
  pageNo(s, 10);
}

p.writeFile({ fileName: "KubeEdgeInfer-Classic.pptx" }).then(f => console.log("wrote", f));
