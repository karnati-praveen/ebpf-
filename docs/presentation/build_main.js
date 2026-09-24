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
  s.addText("Sharing One Big AI Model Across Small Machines - and Fixing the Split While It Runs", {
    x: M, y: 2.0, w: 8.5, h: 1.9, fontFace: HFONT, fontSize: 30, bold: true,
    color: "FFFFFF", lineSpacing: 36, margin: 0,
  });
  s.addText("Most systems choose how to cut the model once. We keep checking, and change the cut whenever the machines change.", {
    x: M, y: 4.05, w: 8.4, h: 0.8, fontFace: BFONT, fontSize: 15, color: "B9C0CC",
    lineSpacing: 22, margin: 0,
  });

  const chips = ["Kernel measuring (eBPF)", "Kubernetes", "Split by layer", "Everyday machines"];
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
  head(s, "Introduction", "The machines keep changing");
  const items = [
    ["Why we split the model at all", "A big AI model is too large for one laptop or small PC. So we cut it into blocks of layers and give one block to each machine. Where we cut is the most important choice we make."],
    ["Small machines are not like data centres", "Data centre servers are all the same and stay cool. Our machines are laptops and cheap GPU boxes on WiFi. They get hot and slow down, their network speed wanders, and sometimes they switch off."],
    ["What other systems do today", "They measure the machines once, pick a cut, and never look again. That cut is right at the start and gets more and more wrong as the machines change."],
  ];
  items.forEach(([t, b], i) => {
    const y = 1.62 + i * 1.62;
    card(s, M, y, 7.5, 1.42);
    dot(s, M + 0.3, y + 0.3, String(i + 1), i === 2 ? AMBER : TEAL);
    s.addText(t, { x: M + 0.78, y: y + 0.22, w: 6.5, h: 0.32, fontFace: BFONT, fontSize: 14.5, bold: true, color: INK, margin: 0 });
    s.addText(b, { x: M + 0.78, y: y + 0.56, w: 6.5, h: 0.78, fontFace: BFONT, fontSize: 11.5, color: "3E4658", lineSpacing: 15, margin: 0 });
  });

  card(s, 8.62, 1.62, 4.09, 4.62, INK);
  s.addText("What that costs", {
    x: 8.92, y: 1.92, w: 3.5, h: 0.3, fontFace: BFONT, fontSize: 11, bold: true, color: AMBER, charSpacing: 1.6, margin: 0,
  });
  const stats = [
    ["2.4x", "slower on the busiest machine when one machine gets hot and the cut never changes"],
    ["4.3x", "slower when a slow network and a hot GPU happen at the same time"],
    ["0", "answers given after one machine dies, if nothing is re-planned"],
  ];
  stats.forEach(([n, l], i) => {
    const y = 2.36 + i * 1.32;
    s.addText(n, { x: 8.92, y, w: 3.5, h: 0.62, fontFace: HFONT, fontSize: 40, bold: true, color: "FFFFFF", margin: 0 });
    s.addText(l, { x: 8.92, y: y + 0.6, w: 3.5, h: 0.62, fontFace: BFONT, fontSize: 10, color: "9AA3B4", lineSpacing: 13, margin: 0 });
  });
  foot(s, 2, "Numbers from the test on slide 11 (12 layers, 3 machines).");
  s.addNotes("Main point: the cut is chosen once, but the machines it was chosen for do not stay the same.");
}

/* ------------------------------------------------ 3-4. Literature review */
const papers = [
  ["EdgeShard", "IEEE IoT-J, 2024", "arXiv:2405.14371",
   "Picks which devices to use and where to cut, with an exact solver. Up to 50% less delay and 2x more work done, tested on 15 real devices.",
   "Measures the devices once, before running. The plan never changes after that."],
  ["Galaxy", "IEEE INFOCOM, 2024", "arXiv:2405.17245",
   "Splits the work inside each layer instead of by layer, and overlaps computing with sending. Up to 2.5x less delay.",
   "The plan is made once, before running. Nothing is re-planned while it runs."],
  ["Helix", "ACM ASPLOS, 2025", "arXiv:2406.01566",
   "Treats serving on mixed GPUs as a flow problem, and chooses placement and routing together. Up to 3.3x more work done on 24-42 machines.",
   "Built for data centre GPUs. Its solver is far too slow to re-run every few seconds."],
  ["TPI-LLM", "arXiv, 2024", "arXiv:2410.00531",
   "Argues that splitting inside layers beats splitting by layer on small devices. Clever memory handling lets 70B models run in small RAM.",
   "Improves memory use, but does not react when a machine slows down."],
  ["prima.cpp", "arXiv, 2025", "arXiv:2504.08791",
   "Runs 30-70B models on real home machines. Shares work between CPU and GPU and hides slow disk reads. 5-17x faster per token than llama.cpp.",
   "Decides the plan when loading, from fixed device specs."],
  ["LLM Partitioning at the Edge", "arXiv, 2025", "arXiv:2505.02533",
   "Cuts the model into much smaller pieces (single attention heads) and moves them when memory runs low. Within 15-20% of the best possible answer.",
   "Only reacts to memory running low - not to heat or to a slow network."],
  ["Parallax", "arXiv, 2025", "arXiv:2509.26182",
   "Serves a model across a pool of volunteer machines of all shapes, with no central cluster in charge.",
   "Spreads the work out well, but measures nothing inside the kernel."],
  ["Adaptive Layer Splitting (MBRL)", "FITEE, Springer, 2025", "doi:10.1631/FITEE.2400468",
   "Learns where to cut, and moves the cut as the wireless signal changes. It does keep adapting, which is rare.",
   "The policy must be trained first, and cannot promise the best answer. Only one cut point."],
  ["Distributed LLMs & MLLMs Survey", "arXiv, 2025", "arXiv:2503.16585",
   "Reviews the whole field, and lists 'adapting to machines that keep changing' as an open problem.",
   "Confirms the gap we are filling. It does not fill it."],
  ["Agentic OS / sched_ext", "arXiv, 2025", "arXiv:2509.01245",
   "Loads custom Linux schedulers as eBPF programs while the system runs. Shows eBPF is now used to control things, not only to watch them.",
   "Works on one machine's CPU tasks. Nothing about splitting a model across machines."],
];

[0, 1].forEach((half) => {
  const s = p.addSlide();
  head(s, `Literature review (${half + 1} of 2)`,
       half === 0 ? "How other systems split the model"
                  : "Adapting, sharing out, and eBPF as a control tool");
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
  s.addText("What it does not do", {
    x: 8.58, y: 1.31, w: 3.5, h: 0.24, fontFace: BFONT, fontSize: 9, bold: true, color: AMBER, charSpacing: 1.2, margin: 0,
  });
  s.addText("Contribution", {
    x: M + 2.92, y: 1.31, w: 3, h: 0.24, fontFace: BFONT, fontSize: 9, bold: true, color: MUTED, charSpacing: 1.2, margin: 0,
  });
  foot(s, 3 + half, "All ten papers are from 2024-2025. Full list on slide 15.");
  s.addNotes("Each row: what the paper does, and the gap we fill.");
});

/* ------------------------------------------------ 5. Research gap */
{
  const s = p.addSlide();
  head(s, "What is missing", "What past work is missing");
  const rows = [
    ["Capability", "Data centre serving\n(Helix)", "Splitting on small devices\n(EdgeShard, Galaxy, prima.cpp)", "Learned splitting\n(MBRL, head-level)", "KubeEdgeInfer"],
    ["Handles machines of different speed", "yes", "yes", "yes", "yes"],
    ["Finds the best cut for the moment", "yes, heavy solver", "yes", "no (learned or rule of thumb)", "yes, checked against brute force"],
    ["Changes the cut while running", "only where requests go", "no", "yes", "yes, every 2 seconds"],
    ["Measures the network in the kernel", "no", "app-level timers", "signal estimate", "yes, reads TCP directly"],
    ["Knows when a machine gets hot", "no", "no", "no", "yes, reads GPU and CPU heat"],
    ["Survives a machine dying", "by keeping copies", "no", "no", "yes, re-cuts in 3 seconds"],
    ["Changes without restarting", "not applicable", "no", "no", "yes, moves layers live"],
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
  foot(s, 5, "No earlier system measures the machines in the kernel and feeds that straight back into the cut, while the model is still answering.");
  s.addNotes("The gap slide: each column has some of what is needed. None has all of it together.");
}

/* ------------------------------------------------ 6. Problem statement */
{
  const s = p.addSlide(); darkBg(s);
  s.addShape(p.ShapeType.ellipse, { x: 10.4, y: -1.2, w: 4.6, h: 4.6, fill: { color: INK2 }, line: { width: 0 } });
  s.addText("THE PROBLEM", {
    x: M, y: 0.75, w: 8, h: 0.3, fontFace: BFONT, fontSize: 11.5, bold: true, color: AMBER, charSpacing: 2.6, margin: 0,
  });
  s.addText("We have N model layers and K machines of different speeds. While the model is answering, their speed, their network delay, and whether they are even alive all keep changing. Keep choosing a cut that makes the slowest machine as fast as possible - and never restart anything to do it.",
    { x: M, y: 1.25, w: 8.5, h: 2.0, fontFace: HFONT, fontSize: 21, color: "FFFFFF", lineSpacing: 30, margin: 0 });

  const subs = [
    ["Measure", "Measure network delay and machine heat cheaply, without changing the model code."],
    ["Decide", "Work out the best cut fast enough to redo it often, without flip-flopping when a reading is just noisy."],
    ["Act", "Move layers between running machines without losing requests or restarting anything."],
    ["Heal", "Notice when a machine dies and share its layers among the machines that are left."],
  ];
  subs.forEach(([t, b], i) => {
    const y = 3.55 + Math.floor(i / 2) * 1.5;
    const x = M + (i % 2) * 4.3;
    dot(s, x, y, String(i + 1), i % 2 === 0 ? AMBER : TEAL);
    s.addText(t, { x: x + 0.48, y: y - 0.02, w: 3.5, h: 0.32, fontFace: BFONT, fontSize: 14, bold: true, color: "FFFFFF", margin: 0 });
    s.addText(b, { x: x + 0.48, y: y + 0.33, w: 3.6, h: 0.9, fontFace: BFONT, fontSize: 10.5, color: "9AA3B4", lineSpacing: 14, margin: 0 });
  });

  s.addShape(p.ShapeType.roundRect, { x: 9.5, y: 3.35, w: 3.2, h: 3.0, rectRadius: 0.08, fill: { color: INK2 }, line: { color: "3A4356", width: 1 } });
  s.addText("The rules we set ourselves", { x: 9.8, y: 3.6, w: 2.6, h: 0.28, fontFace: BFONT, fontSize: 10.5, bold: true, color: AMBER, charSpacing: 1.4, margin: 0 });
  s.addText("Ordinary Linux only.\n\nNo special data centre network, no vendor software, no changes to the model code, and no assuming a machine stays alive.",
    { x: 9.8, y: 3.95, w: 2.6, h: 2.2, fontFace: BFONT, fontSize: 11, color: "C2C9D6", lineSpacing: 16, margin: 0 });
  foot(s, 6, "");
  s.addNotes("State the problem, then break it into four jobs - one for each stage of the loop.");
}

/* ------------------------------------------------ 7. Contributions */
{
  const s = p.addSlide();
  head(s, "What is new", "What is new in our work");
  const cs = [
    ["We measure the network inside the kernel", "Small eBPF programs read the round-trip time Linux already tracks for every connection, and we feed that straight into the cut decision. Other systems guess with app-level timers, or use readings taken before the run.", true],
    ["We never stop deciding", "Watch, decide, act, heal - every 2 seconds, for as long as the system runs. The cut is something we keep adjusting, not a setting we pick once.", true],
    ["We add brakes so it does not flip-flop", "The solver gives the exact best cut every time. We only apply a new one if it is at least 15% better and 30 seconds have passed. The same brake handles heat, network and machine failure.", true],
    ["We move layers without a restart", "Layers move between machines while requests are still in flight. Each plan carries a version number, machines refuse messages from an old plan, and because machines keep no state we can simply replay the request.", false],
    ["We show the gain comes from live measuring", "We built a 'measure once' mode that uses the same solver and the same code, but freezes what it measured. So the improvement we report comes from measuring all the time, not from a better solver.", false],
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
  s.addText("The main new idea", { x: M + 6.63, y: 5.0, w: 5.4, h: 0.3, fontFace: BFONT, fontSize: 10.5, bold: true, color: AMBER, charSpacing: 1.4, margin: 0 });
  s.addText("We did not invent a new splitting algorithm. We took the standard one and put it inside a loop that keeps measuring the real machines and never stops.",
    { x: M + 6.63, y: 5.34, w: 5.5, h: 0.85, fontFace: BFONT, fontSize: 11.5, color: "D3D9E2", lineSpacing: 15.5, margin: 0 });
  foot(s, 7, "The orange-numbered items are the main new ideas.");
  s.addNotes("Say clearly that the algorithm is standard. What is new is the loop around it and the live data feeding it.");
}

/* ------------------------------------------------ 8. Architecture */
{
  const s = p.addSlide();
  head(s, "Our system", "How the loop works");
  const stages = [
    ["WATCH", "measure", "Two small kernel programs report the delay and speed of every connection. Another reads GPU or CPU temperature and how much the machine has slowed down.", "internal/ebpf + cmd/nodeagent", AMBER],
    ["DECIDE", "choose", "Works out the cut that makes the slowest machine as fast as possible. Applied only if it is 15% better and 30 seconds have passed.", "internal/partition", TEAL],
    ["ACT", "apply", "Sends the new layer ranges to the machines with no restart, and saves the plan in Kubernetes with a version number.", "cmd/controller", AMBER],
    ["HEAL", "recover", "If a machine stops reporting for 3 seconds, treat it as dead and re-cut across the machines left, ignoring the brakes.", "internal/controller", TEAL],
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
  s.addText("the loop repeats every 2 seconds", {
    x: M, y: 5.5, w: 12.1, h: 0.3, fontFace: BFONT, fontSize: 10.5, color: MUTED, italic: true, align: "center", margin: 0,
  });
  s.addShape(p.ShapeType.roundRect, { x: M, y: 5.95, w: W - 2 * M, h: 0.72, rectRadius: 0.06, fill: { color: MIST }, line: { width: 0 } });
  s.addText("Staying correct: every plan carries a version number. Machines refuse messages from an old plan. The router then fetches the new plan and replays the request from the start. Machines keep no state, so replaying is always safe.",
    { x: M + 0.28, y: 6.05, w: 11.6, h: 0.55, fontFace: BFONT, fontSize: 10.5, color: "3E4658", valign: "middle", lineSpacing: 14, margin: 0 });
  foot(s, 8, "");
  s.addNotes("Walk left to right, then point at the dashed arrow going back - that is what the other systems do not have.");
}

/* ------------------------------------------------ 9. Formulation */
{
  const s = p.addSlide();
  head(s, "Our system", "The maths, and how we keep it steady");
  card(s, M, 1.58, 6.1, 2.5);
  s.addText("The goal", { x: M + 0.3, y: 1.78, w: 5, h: 0.3, fontFace: BFONT, fontSize: 12.5, bold: true, color: AMBER, margin: 0 });
  s.addText("make the slowest machine\nas fast as possible", {
    x: M + 0.3, y: 2.12, w: 5.5, h: 0.62, fontFace: MFONT, fontSize: 13, bold: true, color: INK, lineSpacing: 16, margin: 0 });
  s.addText("machine time  =  layers x time per layer / speed  +  delay", {
    x: M + 0.3, y: 2.82, w: 5.6, h: 0.3, fontFace: MFONT, fontSize: 9, color: "3E4658", margin: 0 });
  s.addText("Each machine gets a block of layers next to each other, and together they cover all N layers. A machine given zero layers costs nothing at all - so the solver can skip a machine whose network has become too slow to be worth using.",
    { x: M + 0.3, y: 3.18, w: 5.55, h: 0.78, fontFace: BFONT, fontSize: 10.5, color: "3E4658", lineSpacing: 14, margin: 0 });

  card(s, M, 4.24, 6.1, 2.0);
  s.addText("How we solve it", { x: M + 0.3, y: 4.42, w: 5, h: 0.3, fontFace: BFONT, fontSize: 12.5, bold: true, color: TEAL, margin: 0 });
  s.addText("best[j][w]  =  best possible for the first j layers on w machines", {
    x: M + 0.3, y: 4.76, w: 5.6, h: 0.3, fontFace: MFONT, fontSize: 9, color: INK, margin: 0 });
  s.addText("This is a classic problem with a known exact answer. For 12 layers and 3 machines it takes about 1,700 steps, so redoing it every 2 seconds costs nothing. We checked it against brute force on 200 random cases.",
    { x: M + 0.3, y: 5.12, w: 5.55, h: 1.0, fontFace: BFONT, fontSize: 10.5, color: "3E4658", lineSpacing: 14, margin: 0 });

  card(s, 7.05, 1.58, 5.66, 4.66, INK);
  s.addText("Why a solver alone is not enough", {
    x: 7.35, y: 1.82, w: 5.0, h: 0.3, fontFace: BFONT, fontSize: 12.5, bold: true, color: AMBER, margin: 0 });
  s.addText("Measurements jump around. If we applied the best answer every 2 seconds, the system would keep moving layers for tiny gains. Three rules fix that:",
    { x: 7.35, y: 2.2, w: 5.06, h: 0.85, fontFace: BFONT, fontSize: 10.5, color: "AEB6C4", lineSpacing: 14, margin: 0 });
  const rules = [
    ["Must be clearly better", "Only change if the new cut beats the current one, measured right now, by 15%."],
    ["Wait between changes", "At most one change every 30 seconds, so a short spike cannot start a wobble."],
    ["Except when a machine dies", "If the set of machines changes, ignore both rules and re-cut at once. Being correct matters more than being steady."],
  ];
  rules.forEach(([t, b], i) => {
    const y = 3.2 + i * 1.02;
    s.addShape(p.ShapeType.ellipse, { x: 7.35, y: y + 0.04, w: 0.26, h: 0.26, fill: { color: i === 2 ? AMBER : TEAL }, line: { width: 0 } });
    s.addText(t, { x: 7.73, y, w: 4.6, h: 0.28, fontFace: BFONT, fontSize: 11.5, bold: true, color: "FFFFFF", margin: 0 });
    s.addText(b, { x: 7.73, y: y + 0.3, w: 4.65, h: 0.62, fontFace: BFONT, fontSize: 10, color: "9AA3B4", lineSpacing: 13, margin: 0 });
  });
  s.addText("Both numbers can be changed while the system is running.", {
    x: 7.05, y: 6.34, w: 5.06, h: 0.28, fontFace: BFONT, fontSize: 9.5, italic: true, color: MUTED, margin: 0 });
  foot(s, 9, "");
  s.addNotes("The solver is textbook. What matters on this slide is the brakes that make it safe to redo it constantly.");
}

/* ------------------------------------------------ 10. What we built */
{
  const s = p.addSlide();
  head(s, "Our system", "What we built");
  const comps = [
    ["Agent on each machine", "Go and C", "Runs on every machine with kernel access. Loads the eBPF programs, watches only the ports we care about, and reports network delay plus GPU state. GPU readings can be simulated, taken from CPU heat sensors, or read from a real NVIDIA card.", AMBER],
    ["Central controller", "Go", "Collects all the readings, runs the decider, saves the plan in Kubernetes and sends it to the machines. A watchdog forces a re-cut if a machine goes quiet for 3 seconds.", TEAL],
    ["Workers and router", "Python", "Each worker holds a block of layers and keeps no state. Two backends: a fake one for testing, and real GPT-2. Runs on CPU or GPU. The router sends each request through the machines in order.", AMBER],
    ["Test harness", "Python", "Five fault situations x three modes. Measures idle time, tokens per second, and time to the first word. Also tries different brake settings.", TEAL],
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
  s.addText("What is real, what is not", { x: 8.8, y: 1.82, w: 3.6, h: 0.3, fontFace: BFONT, fontSize: 12, bold: true, color: AMBER, margin: 0 });
  const facts = [
    "The eBPF part is real, not simulated. It is built against the running kernel and loaded into it.",
    "On a single test host you get real eBPF, but a fake network and a fake GPU.",
    "Our scripts turn a few laptops and GPU boxes on the same network into one cluster, with no config editing.",
    "Real NVIDIA readings on GPU machines; real CPU heat readings on laptops with no GPU.",
    "The split-up GPT-2 gives exactly the same text as running it on one machine.",
  ];
  facts.forEach((f, i) => {
    const y = 2.28 + i * 0.79;
    s.addShape(p.ShapeType.ellipse, { x: 8.8, y: y + 0.06, w: 0.11, h: 0.11, fill: { color: TEAL }, line: { width: 0 } });
    s.addText(f, { x: 9.04, y, w: 3.42, h: 0.72, fontFace: BFONT, fontSize: 9.5, color: "AEB6C4", lineSpacing: 12.5, margin: 0 });
  });
  foot(s, 10, "");
  s.addNotes("Stress that eBPF really runs in the kernel. Only the GPU reading has a simulated option.");
}

/* ------------------------------------------------ 11. Results: chart */
{
  const s = p.addSlide();
  head(s, "Results", "How slow the busiest machine gets");
  const cats = ["Nothing\nwrong", "Machine\ngets hot", "Network\ngets slow", "Both at\nonce"];
  s.addChart(p.ChartType.bar, [
    { name: "Ours - measures all the time", labels: cats, values: [42, 52, 62, 62] },
    { name: "Measure once, then freeze", labels: cats, values: [42, 102, 122, 182] },
    { name: "Fixed equal cut", labels: cats, values: [42, 102, 122, 182] },
  ], {
    x: M, y: 1.5, w: 7.75, h: 4.95,
    barDir: "col", barGapWidthPct: 55,
    chartColors: [TEAL, AMBER, "B6BDCA"],
    showTitle: true, title: "Time on the slowest machine, per word (ms) - lower is better",
    titleFontFace: BFONT, titleFontSize: 12, titleColor: INK,
    showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 8.5,
    dataLabelColor: "4A5264", dataLabelFontFace: BFONT,
    showLegend: true, legendPos: "b", legendFontFace: BFONT, legendFontSize: 9.5, legendColor: "4A5264",
    catAxisLabelColor: "4A5264", catAxisLabelFontFace: BFONT, catAxisLabelFontSize: 9.5,
    valAxisLabelColor: "4A5264", valAxisLabelFontFace: BFONT, valAxisLabelFontSize: 9,
    valGridLine: { color: "E8EAEF", size: 1 }, catGridLine: { style: "none" },
    valAxisMaxVal: 200,
  });
  const gains = [["49%", "better than both\nwhen a machine gets hot"], ["49%", "better than both\nwhen the network slows"], ["66%", "better than both\nwhen both happen at once"]];
  gains.forEach(([n, l], i) => {
    const y = 1.72 + i * 1.36;
    card(s, 8.55, y, 4.16, 1.2, i === 2 ? INK : MIST);
    s.addText(n, { x: 8.85, y: y + 0.14, w: 1.5, h: 0.6, fontFace: HFONT, fontSize: 32, bold: true, color: i === 2 ? AMBER : TEAL, margin: 0 });
    s.addText(l, { x: 10.3, y: y + 0.24, w: 2.2, h: 0.75, fontFace: BFONT, fontSize: 10, color: i === 2 ? "AEB6C4" : "3E4658", lineSpacing: 13, margin: 0 });
  });
  card(s, 8.55, 5.8, 4.16, 0.9, "FBEDE2");
  s.addText("When a machine dies, the fixed cut has no plan for the machines left, so everything stops. Ours re-cuts and keeps going at 62 ms.",
    { x: 8.82, y: 5.9, w: 3.65, h: 0.72, fontFace: BFONT, fontSize: 9.5, color: "7A4A22", valign: "middle", lineSpacing: 12, margin: 0 });
  foot(s, 11, "Measured with bench/dpsim: 12 layers, 3 machines, 10 ms per layer, one machine slowed to 0.4x, 80 ms network delay.");
  s.addNotes("These are the solver's own numbers, reproducible with `go run ./bench/dpsim`. Measure-once matches the fixed cut here because all machines start equal - the difference is that it still recovers when a machine dies.");
}

/* ------------------------------------------------ 12. Results: behaviour */
{
  const s = p.addSlide();
  head(s, "Results", "What the solver actually decides");
  const splits = [
    ["All machines healthy", "3 machines, all fine", ["0-4", "4-8", "8-12"], "42 ms", TEAL],
    ["Machine 2 gets hot", "speed drops to 0.4x", ["0-5", "5-7", "7-12"], "52 ms", AMBER],
    ["Network to machine 2 slows down", "delay 2 ms -> 82 ms", ["0-6", "empty", "6-12"], "62 ms", AMBER],
    ["Machine 3 dies", "3 machines -> 2", ["0-6", "6-12", ""], "62 ms", AMBER],
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
  s.addText("layers given to machine 1 / 2 / 3", {
    x: M + 3.75, y: 1.26, w: 3.2, h: 0.24, fontFace: BFONT, fontSize: 8.5, color: MUTED, margin: 0 });

  card(s, 8.55, 1.55, 4.16, 2.34, INK);
  s.addText("It can skip a machine", { x: 8.85, y: 1.78, w: 3.5, h: 0.3, fontFace: BFONT, fontSize: 12.5, bold: true, color: AMBER, margin: 0 });
  s.addText("When the network to machine 2 slows to 80 ms, the solver gives it zero layers. A machine with no layers costs nothing at all, so the router skips it and the other two take all 12 layers. Nobody told it to do this - it falls out of the maths.",
    { x: 8.85, y: 2.16, w: 3.6, h: 1.6, fontFace: BFONT, fontSize: 10, color: "AEB6C4", lineSpacing: 13.5, margin: 0 });

  const checks = [
    ["It finds the best answer", "The solver matched brute force on 200 random test cases."],
    ["It gives the same answers", "GPT-2 split over 3 machines produces exactly the same text as one machine."],
    ["How good the estimate is", "Our predicted time is always about 3x lower than the real time. Good for ranking cuts, not for predicting real speed."],
  ];
  checks.forEach(([t, b], i) => {
    const y = 4.06 + i * 0.78;
    s.addShape(p.ShapeType.ellipse, { x: 8.55, y: y + 0.04, w: 0.26, h: 0.26, fill: { color: TEAL }, line: { width: 0 } });
    s.addText(t, { x: 8.93, y, w: 3.6, h: 0.26, fontFace: BFONT, fontSize: 11, bold: true, color: INK, margin: 0 });
    s.addText(b, { x: 8.93, y: y + 0.27, w: 3.72, h: 0.5, fontFace: BFONT, fontSize: 9, color: "4A5264", lineSpacing: 11.5, margin: 0 });
  });
  foot(s, 12, "Tokens per second, time to the first word, and real idle time come from bench/run.py, which needs a running cluster.");
  s.addNotes("The network row is the best result: the solver drops a machine all by itself.");
}

/* ------------------------------------------------ 13. Comparison */
{
  const s = p.addSlide();
  head(s, "Comparison", "How we compare with the closest systems");
  const cols = ["", "EdgeShard\n(IoT-J 24)", "Galaxy\n(INFOCOM 24)", "Helix\n(ASPLOS 25)", "prima.cpp\n(2025)", "KubeEdgeInfer"];
  const rows = [
    ["How the model is split", "by layer", "inside layers", "by layer + routing", "ring of layers", "by layer"],
    ["How the cut is chosen", "exact solver", "rule of thumb", "heavy solver", "custom scheduler", "exact solver"],
    ["Where its numbers come from", "measured before", "measured before", "measured before", "device specs", "kernel + GPU, live"],
    ["Re-cuts while running", "no", "no", "only routing", "no", "every 2 seconds"],
    ["Reacts to machines getting hot", "no", "no", "no", "no", "yes"],
    ["Survives a machine dying", "no", "no", "by keeping copies", "no", "yes, within 3 seconds"],
    ["What it runs on", "15 small devices", "small devices", "24-42 GPU servers", "home machines", "laptops + GPU boxes"],
    ["Improvement they report", "50% less delay", "2.5x less delay", "3.3x more work", "5-17x faster words", "49-66% better*"],
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
  foot(s, 13, "* We measure how slow the busiest machine gets, against a fixed cut and a measure-once version of our own system. That is not the same measurement as the other columns.");
  s.addNotes("Be honest here: the last row measures different things in different columns. Say so out loud.");
}

/* ------------------------------------------------ 14. Conclusion */
{
  const s = p.addSlide(); darkBg(s);
  s.addShape(p.ShapeType.ellipse, { x: -1.4, y: 4.6, w: 4.4, h: 4.4, fill: { color: INK2 }, line: { width: 0 } });
  s.addText("CONCLUSION", { x: M, y: 0.72, w: 8, h: 0.3, fontFace: BFONT, fontSize: 11.5, bold: true, color: AMBER, charSpacing: 2.6, margin: 0 });
  s.addText("Where to cut the model is a decision you should keep making, not one you make once.", {
    x: M, y: 1.2, w: 8.3, h: 1.35, fontFace: HFONT, fontSize: 28, bold: true, color: "FFFFFF", lineSpacing: 36, margin: 0 });
  s.addText("We keep a standard, exact solver running all the time. It is fed by network delays read from the kernel and by real temperature readings, and it moves layers on a live system with no restart. On a set of ordinary machines, that is the difference between a plan that was right once and a plan that stays right.",
    { x: M, y: 2.66, w: 8.3, h: 1.3, fontFace: BFONT, fontSize: 13, color: "AEB6C4", lineSpacing: 20, margin: 0 });

  const takeaways = [
    ["The exact answer is cheap", "Working out the best cut takes microseconds. There is no reason to do it only once."],
    ["The brakes are what make it usable", "One 'must be clearly better' rule and one 'wait a bit' rule handle heat, network and machine failure all the same way."],
    ["Kernel measuring is free", "eBPF sees what really went over the network, not what the program thinks it sent."],
  ];
  takeaways.forEach(([t, b], i) => {
    const y = 4.28 + i * 0.86;
    dot(s, M, y, String(i + 1), i === 0 ? AMBER : TEAL);
    s.addText(t, { x: M + 0.48, y: y - 0.02, w: 7.6, h: 0.28, fontFace: BFONT, fontSize: 12, bold: true, color: "FFFFFF", margin: 0 });
    s.addText(b, { x: M + 0.48, y: y + 0.27, w: 7.7, h: 0.44, fontFace: BFONT, fontSize: 10, color: "9AA3B4", lineSpacing: 12.5, margin: 0 });
  });

  s.addShape(p.ShapeType.roundRect, { x: 9.25, y: 2.66, w: 3.46, h: 3.92, rectRadius: 0.08, fill: { color: INK2 }, line: { color: "3A4356", width: 1 } });
  s.addText("Next steps", { x: 9.55, y: 2.9, w: 2.9, h: 0.3, fontFace: BFONT, fontSize: 12, bold: true, color: AMBER, margin: 0 });
  const fw = [
    "Support a Llama-size model, so two 8 GB cards can hold a real modern model between them.",
    "Run heavy load for a long time, to see a GPU really slow down instead of flat lines.",
    "Allow cuts that are not one solid block per machine, as in arXiv:2505.02533.",
    "Calibrate the cost estimate so it predicts real speed, not only the right ranking.",
  ];
  fw.forEach((f, i) => {
    const y = 3.32 + i * 0.8;
    s.addShape(p.ShapeType.ellipse, { x: 9.55, y: y + 0.06, w: 0.11, h: 0.11, fill: { color: TEAL }, line: { width: 0 } });
    s.addText(f, { x: 9.79, y, w: 2.72, h: 0.72, fontFace: BFONT, fontSize: 9.5, color: "AEB6C4", lineSpacing: 12.5, margin: 0 });
  });
  foot(s, 14, "");
  s.addNotes("End on the one-line message, then the honest limits.");
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
  s.addText("Tools used: cilium/ebpf · Kubernetes controller-runtime · NVIDIA NVML · k3s · Hugging Face Transformers (GPT-2).", {
    x: M, y: 6.65, w: 11.6, h: 0.3, fontFace: BFONT, fontSize: 9, color: MUTED, italic: true, margin: 0 });
  foot(s, 15, "");
  s.addNotes("Ten papers, all from 2024-2025.");
}

p.writeFile({ fileName: "KubeEdgeInfer.pptx" }).then(f => console.log("wrote", f));
