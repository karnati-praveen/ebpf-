// A deliberately simple 10-slide version of the main talk: one idea per slide,
// large type, few elements. Same content and same measured numbers as the
// 15-slide deck, condensed.
const pptxgen = require("pptxgenjs");

const INK   = "1A1F2B";   // body text
const SOFT  = "5A6377";   // secondary text
const MIST  = "F2F4F8";   // the one background tint used for cards
const TEAL  = "1F8A80";   // the single accent
const AMBER = "E07B39";   // used only for numbers that matter
const PAPER = "FFFFFF";

const HFONT = "Cambria";  // headings
const BFONT = "Calibri";  // everything else

const p = new pptxgen();
p.layout = "LAYOUT_WIDE";        // 13.33 x 7.5
p.title  = "KubeEdgeInfer";

const W = 13.33, H = 7.5, M = 0.8;

// Every content slide gets the same head: a title and nothing else above it.
function head(s, title, sub) {
  s.background = { color: PAPER };
  s.addText(title, {
    x: M, y: 0.5, w: W - 2 * M, h: 0.8, fontFace: HFONT, fontSize: 34,
    bold: true, color: INK, margin: 0,
  });
  if (sub) {
    s.addText(sub, {
      x: M, y: 1.32, w: W - 2 * M, h: 0.4, fontFace: BFONT, fontSize: 15,
      color: SOFT, margin: 0,
    });
  }
}

function pageNo(s, n) {
  s.addText(String(n), {
    x: W - M - 0.5, y: H - 0.6, w: 0.5, h: 0.3, fontFace: BFONT, fontSize: 11,
    color: "9AA2B0", align: "right", margin: 0,
  });
}

function note(s, text) {
  s.addText(text, {
    x: M, y: H - 0.62, w: W - 2 * M - 0.7, h: 0.34, fontFace: BFONT,
    fontSize: 10.5, color: "9AA2B0", italic: true, margin: 0,
  });
}

// The one repeated motif: a numbered teal circle beside a bold line.
function numbered(s, x, y, n, title, body, w, color) {
  s.addShape(p.ShapeType.ellipse, {
    x, y, w: 0.46, h: 0.46, fill: { color: color || TEAL }, line: { width: 0 },
  });
  s.addText(String(n), {
    x, y, w: 0.46, h: 0.46, fontFace: BFONT, fontSize: 16, bold: true,
    color: "FFFFFF", align: "center", valign: "middle", margin: 0,
  });
  s.addText(title, {
    x: x + 0.72, y: y - 0.02, w: w, h: 0.4, fontFace: BFONT, fontSize: 19,
    bold: true, color: INK, margin: 0,
  });
  if (body) {
    s.addText(body, {
      x: x + 0.72, y: y + 0.42, w: w, h: 0.8, fontFace: BFONT, fontSize: 14,
      color: SOFT, lineSpacing: 19, margin: 0,
    });
  }
}

/* --------------------------------------------------------------- 1. Title */
{
  const s = p.addSlide();
  s.background = { color: PAPER };

  s.addShape(p.ShapeType.ellipse, {
    x: M, y: 1.42, w: 0.3, h: 0.3, fill: { color: TEAL }, line: { width: 0 },
  });
  s.addText("KubeEdgeInfer", {
    x: M + 0.5, y: 1.4, w: 6, h: 0.34, fontFace: BFONT, fontSize: 14, bold: true,
    color: TEAL, charSpacing: 1.6, valign: "middle", margin: 0,
  });
  s.addText("Sharing One Big AI Model\nAcross Small Machines", {
    x: M, y: 2.0, w: 10.6, h: 1.9, fontFace: HFONT, fontSize: 44, bold: true,
    color: INK, lineSpacing: 54, margin: 0,
  });
  s.addText("and fixing the split while it runs", {
    x: M, y: 3.95, w: 10.6, h: 0.5, fontFace: HFONT, fontSize: 24,
    color: TEAL, italic: true, margin: 0,
  });
  s.addText("Most systems decide how to cut the model once. We keep checking, and change the cut whenever the machines change.", {
    x: M, y: 4.75, w: 9.4, h: 0.8, fontFace: BFONT, fontSize: 15, color: SOFT,
    lineSpacing: 22, margin: 0,
  });
  s.addText("Author:          Institution:          Date:", {
    x: M, y: 6.3, w: 9, h: 0.4, fontFace: BFONT, fontSize: 13, color: "9AA2B0", margin: 0,
  });
  s.addNotes("Fill in author, institution and date before presenting.");
}

/* ---------------------------------------------------------- 2. Introduction */
{
  const s = p.addSlide();
  head(s, "The machines keep changing");
  numbered(s, M, 2.05, 1, "A big model does not fit on one machine",
    "So we cut it into blocks of layers and give one block to each machine. Where we cut is the most important choice we make.", 7.2);
  numbered(s, M, 3.55, 2, "Small machines are not like data centres",
    "Laptops and cheap GPU boxes get hot and slow down, their network speed wanders, and sometimes they switch off.", 7.2);
  numbered(s, M, 5.05, 3, "Other systems cut once and never look again",
    "That cut is right at the start, and gets more and more wrong as the machines change.", 7.2, AMBER);

  s.addShape(p.ShapeType.roundRect, {
    x: 9.05, y: 2.05, w: 3.48, h: 3.9, rectRadius: 0.08,
    fill: { color: MIST }, line: { width: 0 },
  });
  s.addText("What that costs", {
    x: 9.35, y: 2.3, w: 2.9, h: 0.35, fontFace: BFONT, fontSize: 14, bold: true, color: AMBER, margin: 0,
  });
  [["2.4x", "slower when one machine gets hot"],
   ["4.3x", "slower when the network slows too"]].forEach(([big, small], i) => {
    const y = 2.85 + i * 1.5;
    s.addText(big, { x: 9.35, y, w: 2.9, h: 0.7, fontFace: HFONT, fontSize: 40, bold: true, color: INK, margin: 0 });
    s.addText(small, { x: 9.35, y: 0.72 + y, w: 2.9, h: 0.6, fontFace: BFONT, fontSize: 13, color: SOFT, lineSpacing: 17, margin: 0 });
  });
  note(s, "Measured on slide 7, with 12 layers across 3 machines.");
  pageNo(s, 2);
}

/* ----------------------------------------------------- 3. Literature review */
{
  const s = p.addSlide();
  head(s, "What others have done", "Ten papers from 2024 and 2025. Full details on slide 10.");
  const papers = [
    ["EdgeShard", "2024", "Picks where to cut with an exact solver. 50% less delay."],
    ["Galaxy", "2024", "Splits work inside each layer instead of by layer."],
    ["Helix", "2025", "Chooses placement and routing together on mixed GPUs."],
    ["TPI-LLM", "2024", "Clever memory handling so 70B models fit in small RAM."],
    ["prima.cpp", "2025", "Runs 30-70B models on real home machines."],
    ["Head-level splitting", "2025", "Cuts into very small pieces and moves them when memory is low."],
    ["Parallax", "2025", "Serves a model across volunteer machines, no central cluster."],
    ["Learned splitting", "2025", "Learns where to cut as the wireless signal changes."],
    ["Survey of the field", "2025", "Lists adapting to changing machines as an open problem."],
    ["Linux schedulers in eBPF", "2025", "Shows eBPF is now used to control, not only to watch."],
  ];
  papers.forEach(([name, year, line], i) => {
    const col = i < 5 ? 0 : 1;
    const row = i % 5;
    const x = M + col * 6.05;
    const y = 2.15 + row * 0.86;
    s.addShape(p.ShapeType.ellipse, { x, y: y + 0.13, w: 0.15, h: 0.15, fill: { color: TEAL }, line: { width: 0 } });
    s.addText(`${name}  (${year})`, {
      x: x + 0.32, y, w: 5.4, h: 0.32, fontFace: BFONT, fontSize: 14, bold: true, color: INK, margin: 0,
    });
    s.addText(line, {
      x: x + 0.32, y: y + 0.32, w: 5.4, h: 0.44, fontFace: BFONT, fontSize: 12, color: SOFT, lineSpacing: 15, margin: 0,
    });
  });
  s.addShape(p.ShapeType.roundRect, {
    x: M, y: 6.42, w: W - 2 * M, h: 0.56, rectRadius: 0.06, fill: { color: MIST }, line: { width: 0 },
  });
  s.addText("What they all have in common: they measure the machines before the run, and never measure again.", {
    x: M + 0.3, y: 6.42, w: W - 2 * M - 0.6, h: 0.56, fontFace: BFONT, fontSize: 13.5,
    bold: true, color: INK, valign: "middle", margin: 0,
  });
  pageNo(s, 3);
}

/* ------------------------------------------------------ 4. Problem statement */
{
  const s = p.addSlide();
  head(s, "The problem");
  s.addShape(p.ShapeType.roundRect, {
    x: M, y: 2.0, w: W - 2 * M, h: 1.75, rectRadius: 0.08, fill: { color: MIST }, line: { width: 0 },
  });
  s.addText("We have N model layers and K machines of different speeds. While the model is answering, their speed, their network delay, and whether they are even alive all keep changing. Keep choosing a cut that makes the slowest machine as fast as possible - and never restart anything to do it.", {
    x: M + 0.4, y: 2.0, w: W - 2 * M - 0.8, h: 1.75, fontFace: HFONT, fontSize: 19,
    color: INK, valign: "middle", lineSpacing: 28, margin: 0,
  });
  s.addText("That breaks into four jobs:", {
    x: M, y: 4.1, w: 8, h: 0.4, fontFace: BFONT, fontSize: 15, bold: true, color: SOFT, margin: 0,
  });
  [["Measure", "network delay and machine heat, cheaply, without changing the model code"],
   ["Decide", "the best cut, fast enough to redo it often, without flip-flopping"],
   ["Act", "move layers between running machines without losing requests"],
   ["Recover", "notice a dead machine and share its layers among the rest"]].forEach(([t, b], i) => {
    const x = M + (i % 2) * 6.05;
    const y = 4.65 + Math.floor(i / 2) * 1.1;
    s.addShape(p.ShapeType.ellipse, { x, y: y + 0.05, w: 0.36, h: 0.36, fill: { color: TEAL }, line: { width: 0 } });
    s.addText(String(i + 1), { x, y: y + 0.05, w: 0.36, h: 0.36, fontFace: BFONT, fontSize: 13, bold: true, color: "FFFFFF", align: "center", valign: "middle", margin: 0 });
    s.addText(t, { x: x + 0.58, y, w: 5.2, h: 0.32, fontFace: BFONT, fontSize: 16, bold: true, color: INK, margin: 0 });
    s.addText(b, { x: x + 0.58, y: y + 0.34, w: 5.2, h: 0.6, fontFace: BFONT, fontSize: 12.5, color: SOFT, lineSpacing: 16, margin: 0 });
  });
  pageNo(s, 4);
}

/* ---------------------------------------------------------- 5. Contributions */
{
  const s = p.addSlide();
  head(s, "What is new in our work");
  numbered(s, M, 2.1, 1, "We measure the network inside the kernel",
    "Small eBPF programs read the round-trip time Linux already tracks for every connection. Others guess with timers, or measure only before the run.", 11.5);
  numbered(s, M, 3.55, 2, "We never stop deciding",
    "Watch, decide, act, recover - every 2 seconds, for as long as the system runs. The cut is something we keep adjusting, not a setting we pick once.", 11.5);
  numbered(s, M, 5.0, 3, "We add brakes so it does not flip-flop",
    "A new cut is applied only if it is at least 15% better and 30 seconds have passed. The same brake handles heat, network and machine failure.", 11.5, AMBER);

  s.addShape(p.ShapeType.roundRect, {
    x: M, y: 6.4, w: W - 2 * M, h: 0.6, rectRadius: 0.06, fill: { color: INK }, line: { width: 0 },
  });
  s.addText("We did not invent a new algorithm. We took the standard one and put it inside a loop that never stops measuring.", {
    x: M + 0.35, y: 6.4, w: W - 2 * M - 0.7, h: 0.6, fontFace: BFONT, fontSize: 14,
    bold: true, color: "FFFFFF", valign: "middle", margin: 0,
  });
  pageNo(s, 5);
}

/* ---------------------------------------------------------- 6. Proposed work */
{
  const s = p.addSlide();
  head(s, "How our system works", "The same four steps run over and over, every 2 seconds.");
  const steps = [
    ["WATCH", "Measure", "Kernel programs report the delay and speed of every connection. Another reads GPU and CPU temperature.", TEAL],
    ["DECIDE", "Choose", "Work out the cut that makes the slowest machine as fast as possible.", TEAL],
    ["ACT", "Apply", "Send the new layer ranges to the machines. No restart, no lost requests.", AMBER],
    ["HEAL", "Recover", "If a machine goes quiet for 3 seconds, treat it as dead and re-cut across the rest.", TEAL],
  ];
  steps.forEach(([tag, title, body, col], i) => {
    const x = M + i * 3.02;
    s.addShape(p.ShapeType.roundRect, {
      x, y: 2.2, w: 2.75, h: 2.85, rectRadius: 0.08, fill: { color: MIST }, line: { width: 0 },
    });
    s.addShape(p.ShapeType.ellipse, { x: x + 0.28, y: 2.5, w: 0.5, h: 0.5, fill: { color: col }, line: { width: 0 } });
    s.addText(String(i + 1), { x: x + 0.28, y: 2.5, w: 0.5, h: 0.5, fontFace: BFONT, fontSize: 17, bold: true, color: "FFFFFF", align: "center", valign: "middle", margin: 0 });
    s.addText(title, { x: x + 0.28, y: 3.15, w: 2.2, h: 0.4, fontFace: HFONT, fontSize: 21, bold: true, color: INK, margin: 0 });
    s.addText(body, { x: x + 0.28, y: 3.62, w: 2.25, h: 1.25, fontFace: BFONT, fontSize: 12, color: SOFT, valign: "top", lineSpacing: 16, margin: 0 });
    if (i < 3) {
      s.addShape(p.ShapeType.rightArrow, { x: x + 2.8, y: 3.5, w: 0.18, h: 0.28, fill: { color: "B9C0CD" }, line: { width: 0 } });
    }
  });
  s.addShape(p.ShapeType.line, {
    x: M + 1.2, y: 5.4, w: 9.9, h: 0,
    line: { color: "B9C0CD", width: 1.5, dashType: "dash", endArrowType: "triangle" }, flipH: true,
  });
  s.addText("then it starts again", {
    x: M, y: 5.5, w: W - 2 * M, h: 0.35, fontFace: BFONT, fontSize: 13,
    color: SOFT, italic: true, align: "center", margin: 0,
  });
  s.addShape(p.ShapeType.roundRect, {
    x: M, y: 6.15, w: W - 2 * M, h: 0.65, rectRadius: 0.06, fill: { color: MIST }, line: { width: 0 },
  });
  s.addText("Every plan carries a version number. Machines refuse messages from an old plan, and because they keep no state, the request is simply replayed.", {
    x: M + 0.35, y: 6.15, w: W - 2 * M - 0.7, h: 0.65, fontFace: BFONT, fontSize: 13,
    color: INK, valign: "middle", margin: 0,
  });
  pageNo(s, 6);
}

/* --------------------------------------------------------------- 7. Results */
{
  const s = p.addSlide();
  head(s, "Results", "How slow the busiest machine gets. Lower is better.");
  const cats = ["Nothing wrong", "Machine gets hot", "Network gets slow", "Both at once"];
  s.addChart(p.ChartType.bar, [
    { name: "Ours", labels: cats, values: [42, 52, 62, 62] },
    { name: "Others (cut once, then freeze)", labels: cats, values: [42, 102, 122, 182] },
  ], {
    x: M, y: 2.0, w: 7.9, h: 4.3,
    barDir: "col", barGapWidthPct: 60,
    chartColors: [TEAL, "C3C9D4"],
    showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 11,
    dataLabelColor: SOFT, dataLabelFontFace: BFONT,
    showLegend: true, legendPos: "b", legendFontFace: BFONT, legendFontSize: 12, legendColor: SOFT,
    catAxisLabelColor: SOFT, catAxisLabelFontFace: BFONT, catAxisLabelFontSize: 11.5,
    valAxisLabelColor: SOFT, valAxisLabelFontFace: BFONT, valAxisLabelFontSize: 10,
    valGridLine: { color: "EBEDF2", size: 1 }, catGridLine: { style: "none" },
    valAxisMaxVal: 200, valAxisTitle: "milliseconds", showValAxisTitle: true,
    valAxisTitleFontFace: BFONT, valAxisTitleFontSize: 11, valAxisTitleColor: SOFT,
  });
  [["49%", "better when a machine gets hot", MIST, INK],
   ["66%", "better when the network slows too", MIST, INK],
   ["It keeps going", "when a machine dies, the others take over. A fixed cut simply stops.", INK, "FFFFFF"]]
  .forEach(([big, small, bg, fg], i) => {
    const y = 2.0 + i * 1.5;
    s.addShape(p.ShapeType.roundRect, { x: 8.95, y, w: 3.58, h: 1.3, rectRadius: 0.08, fill: { color: bg }, line: { width: 0 } });
    s.addText(big, {
      x: 9.25, y: y + 0.14, w: 3.0, h: 0.55, fontFace: HFONT,
      fontSize: i === 2 ? 20 : 34, bold: true, color: i === 2 ? AMBER : TEAL, margin: 0,
    });
    s.addText(small, {
      x: 9.25, y: y + (i === 2 ? 0.66 : 0.72), w: 3.0, h: 0.55, fontFace: BFONT,
      fontSize: 12, color: i === 2 ? "C3C9D4" : SOFT, lineSpacing: 15, margin: 0,
    });
  });
  note(s, "From bench/dpsim: 12 layers, 3 machines, one machine slowed to 0.4x, 80 ms network delay.");
  pageNo(s, 7);
}

/* ------------------------------------------------------------ 8. Comparison */
{
  const s = p.addSlide();
  head(s, "How we compare");
  const cols = ["", "EdgeShard", "Galaxy", "Helix", "prima.cpp", "Ours"];
  const rows = [
    ["Where its numbers come from", "before the run", "before the run", "before the run", "device specs", "live, from the kernel"],
    ["Re-cuts while running", "no", "no", "only routing", "no", "every 2 seconds"],
    ["Reacts to a machine getting hot", "no", "no", "no", "no", "yes"],
    ["Survives a machine dying", "no", "no", "by copies", "no", "yes, in 3 seconds"],
    ["Changes without restarting", "no", "no", "no", "no", "yes"],
  ];
  const colX = [M, 4.55, 6.15, 7.6, 9.15, 10.75];
  const colW = [3.7, 1.55, 1.4, 1.5, 1.55, 1.85];

  s.addShape(p.ShapeType.rect, { x: M, y: 2.15, w: W - 2 * M, h: 0.6, fill: { color: INK }, line: { width: 0 } });
  cols.forEach((c, ci) => {
    s.addText(c, {
      x: colX[ci], y: 2.15, w: colW[ci], h: 0.6, fontFace: BFONT, fontSize: 12.5,
      bold: true, color: ci === 5 ? AMBER : "FFFFFF", valign: "middle", margin: 0,
    });
  });
  rows.forEach((r, ri) => {
    const y = 2.8 + ri * 0.72;
    if (ri % 2 === 0) {
      s.addShape(p.ShapeType.rect, { x: M, y, w: W - 2 * M, h: 0.68, fill: { color: "F7F8FA" }, line: { width: 0 } });
    }
    r.forEach((cell, ci) => {
      s.addText(cell, {
        x: colX[ci], y, w: colW[ci], h: 0.68, fontFace: BFONT, fontSize: 12.5,
        bold: ci === 0 || ci === 5, color: ci === 5 ? TEAL : (ci === 0 ? INK : SOFT),
        valign: "middle", margin: 0,
      });
    });
  });
  s.addShape(p.ShapeType.roundRect, {
    x: 10.65, y: 2.15, w: 1.98, h: 4.33, rectRadius: 0.05,
    fill: { type: "solid", color: TEAL, transparency: 94 }, line: { color: TEAL, width: 1.5 },
  });
  note(s, "We measure how slow the busiest machine gets. The other systems report different measurements, so the numbers are not directly comparable.");
  pageNo(s, 8);
}

/* ------------------------------------------------------------ 9. Conclusion */
{
  const s = p.addSlide();
  s.background = { color: PAPER };
  s.addShape(p.ShapeType.ellipse, {
    x: M, y: 0.78, w: 0.26, h: 0.26, fill: { color: TEAL }, line: { width: 0 },
  });
  s.addText("Conclusion", {
    x: M + 0.44, y: 0.74, w: 8, h: 0.34, fontFace: BFONT, fontSize: 13, bold: true,
    color: TEAL, charSpacing: 2, valign: "middle", margin: 0,
  });
  s.addText("Where to cut the model is a decision you should keep making, not one you make once.", {
    x: M, y: 1.3, w: 11.4, h: 1.5, fontFace: HFONT, fontSize: 32, bold: true, color: INK, lineSpacing: 42, margin: 0,
  });
  numbered(s, M, 3.2, 1, "Working out the best cut is cheap",
    "It takes microseconds, so there is no reason to do it only once.", 11.3);
  numbered(s, M, 4.35, 2, "The brakes are what make it usable",
    "One 'must be clearly better' rule and one 'wait a bit' rule handle heat, slow networks and dead machines the same way.", 11.3);
  numbered(s, M, 5.5, 3, "Measuring in the kernel is free",
    "eBPF sees what really went over the network, not what the program thinks it sent.", 11.3);
  note(s, "Next: support a Llama-size model, and calibrate the estimate so it predicts real speed, not only the right ranking.");
  pageNo(s, 9);
}

/* ------------------------------------------------------------ 10. References */
{
  const s = p.addSlide();
  head(s, "References");
  const refs = [
    "[1]  EdgeShard: Efficient LLM Inference via Collaborative Edge Computing. M. Zhang, J. Cao, X. Shen, Z. Cui. IEEE Internet of Things Journal, 2024. arXiv:2405.14371.",
    "[2]  Galaxy: A Resource-Efficient Collaborative Edge AI System for In-situ Transformer Inference. IEEE INFOCOM, 2024. arXiv:2405.17245.",
    "[3]  Helix: Serving Large Language Models over Heterogeneous GPUs and Network via Max-Flow. ACM ASPLOS, 2025. arXiv:2406.01566.",
    "[4]  TPI-LLM: Serving 70B-scale LLMs Efficiently on Low-resource Edge Devices. 2024. arXiv:2410.00531.",
    "[5]  Prima.cpp: Fast 30-70B LLM Inference on Heterogeneous and Low-Resource Home Clusters. 2025. arXiv:2504.08791.",
    "[6]  Large Language Model Partitioning for Low-Latency Inference at the Edge. 2025. arXiv:2505.02533.",
    "[7]  Parallax: Efficient LLM Inference Service over Decentralized Environment. 2025. arXiv:2509.26182.",
    "[8]  Adaptive layer splitting for wireless large language model inference in edge computing. FITEE, Springer, 2025. doi:10.1631/FITEE.2400468.",
    "[9]  Distributed LLMs and Multimodal Large Language Models: A Survey. 2025. arXiv:2503.16585.",
    "[10] Towards Agentic OS: An LLM Agent Framework for Linux Schedulers. 2025. arXiv:2509.01245.",
  ];
  refs.forEach((r, i) => {
    const y = 2.0 + i * 0.47;
    if (i % 2 === 0) {
      s.addShape(p.ShapeType.rect, { x: M, y, w: W - 2 * M, h: 0.44, fill: { color: "F7F8FA" }, line: { width: 0 } });
    }
    s.addText(r, {
      x: M + 0.25, y, w: W - 2 * M - 0.5, h: 0.44, fontFace: BFONT, fontSize: 11,
      color: SOFT, valign: "middle", margin: 0,
    });
  });
  note(s, "Tools used: cilium/ebpf, Kubernetes, NVIDIA NVML, k3s, Hugging Face Transformers.");
  pageNo(s, 10);
}

p.writeFile({ fileName: "KubeEdgeInfer-Simple.pptx" }).then(f => console.log("wrote", f));
