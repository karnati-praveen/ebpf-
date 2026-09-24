const pptxgen = require("pptxgenjs");

const INK = "141821", INK2 = "232A38", PAPER = "FFFFFF", MIST = "F1F3F7";
const AMBER = "E07B39", TEAL = "1F8A80", MUTED = "6B7280";
const HFONT = "Cambria", BFONT = "Calibri", MFONT = "Courier New";

const p = new pptxgen();
p.layout = "LAYOUT_WIDE";
p.title = "KubeEdgeInfer - Code Demo";
const W = 13.33, H = 7.5, M = 0.62;

function shadow() { return { type: "outer", color: "9AA3B2", blur: 10, offset: 2, angle: 90, opacity: 0.28 }; }

function head(s, kicker, title) {
  s.background = { color: PAPER };
  s.addText(kicker.toUpperCase(), { x: M, y: 0.34, w: 9, h: 0.26, fontFace: BFONT, fontSize: 11.5, bold: true, color: AMBER, charSpacing: 2.2, margin: 0 });
  s.addText(title, { x: M, y: 0.62, w: W - 2 * M, h: 0.66, fontFace: HFONT, fontSize: 30, bold: true, color: INK, margin: 0 });
}
function foot(s, n, note) {
  if (note) s.addText(note, { x: M, y: H - 0.5, w: 10.6, h: 0.3, fontFace: BFONT, fontSize: 9.5, color: MUTED, italic: true, margin: 0 });
  s.addText(String(n), { x: W - M - 0.6, y: H - 0.5, w: 0.6, h: 0.3, fontFace: BFONT, fontSize: 10, color: MUTED, align: "right", margin: 0 });
}
function code(s, x, y, w, h, path, lines) {
  s.addShape(p.ShapeType.roundRect, { x, y, w, h, rectRadius: 0.06, fill: { color: INK }, line: { width: 0 }, shadow: shadow() });
  s.addText(path, { x: x + 0.24, y: y + 0.14, w: w - 0.48, h: 0.26, fontFace: MFONT, fontSize: 8.5, color: AMBER, margin: 0 });
  s.addText(lines, { x: x + 0.24, y: y + 0.46, w: w - 0.44, h: h - 0.66, fontFace: MFONT, fontSize: 8.5, color: "D5DAE3", lineSpacing: 12, margin: 0 });
}
function note(s, x, y, w, h, title, body, col) {
  s.addShape(p.ShapeType.roundRect, { x, y, w, h, rectRadius: 0.06, fill: { color: MIST }, line: { width: 0 } });
  s.addShape(p.ShapeType.ellipse, { x: x + 0.24, y: y + 0.22, w: 0.26, h: 0.26, fill: { color: col || TEAL }, line: { width: 0 } });
  s.addText(title, { x: x + 0.62, y: y + 0.18, w: w - 0.86, h: 0.3, fontFace: BFONT, fontSize: 12, bold: true, color: INK, margin: 0 });
  s.addText(body, { x: x + 0.62, y: y + 0.5, w: w - 0.9, h: h - 0.68, fontFace: BFONT, fontSize: 10, color: "3E4658", lineSpacing: 13.5, margin: 0 });
}

/* 1. Title */
{
  const s = p.addSlide(); s.background = { color: INK };
  s.addShape(p.ShapeType.ellipse, { x: 9.9, y: -1.4, w: 5.2, h: 5.2, fill: { color: INK2 }, line: { width: 0 } });
  s.addText("APPENDIX / LIVE DEMO", { x: M, y: 1.9, w: 8, h: 0.3, fontFace: BFONT, fontSize: 12, bold: true, color: AMBER, charSpacing: 3.2, margin: 0 });
  s.addText("A Walk Through the Code", { x: M, y: 2.4, w: 8.6, h: 1.5, fontFace: HFONT, fontSize: 40, bold: true, color: "FFFFFF", lineSpacing: 46, margin: 0 });
  s.addText("The four stages of the loop in real code, and the commands that make the machines fix themselves on stage.",
    { x: M, y: 3.9, w: 8.2, h: 0.7, fontFace: BFONT, fontSize: 14, color: "AEB6C4", lineSpacing: 20, margin: 0 });
  ["tcpmon.c", "partition.go", "controller", "run-demo.sh"].forEach((c, i) => {
    const x = M + i * 2.05;
    s.addShape(p.ShapeType.roundRect, { x, y: 4.9, w: 1.9, h: 0.44, rectRadius: 0.22, fill: { color: INK2 }, line: { color: "3A4356", width: 1 } });
    s.addText(c, { x, y: 4.9, w: 1.9, h: 0.44, fontFace: MFONT, fontSize: 9, color: "C9D0DC", align: "center", valign: "middle", margin: 0 });
  });
  s.addText("Kept separate from the main deck. Show this only if there is time for the demo.",
    { x: M, y: 6.3, w: 8.5, h: 0.3, fontFace: BFONT, fontSize: 10.5, color: "7C8698", italic: true, margin: 0 });
}

/* 2. Repo map */
{
  const s = p.addSlide();
  head(s, "Orientation", "Where each part of the loop lives");
  const rows = [
    ["WATCH", "internal/ebpf/bpf/tcpmon.c", "C (CO-RE)", "Measures delay and speed of every connection", AMBER],
    ["WATCH", "cmd/nodeagent", "Go", "Loads the kernel programs, adds GPU state, reports it all", AMBER],
    ["DECIDE", "internal/partition/partition.go", "Go", "Works out the best cut, and decides when to apply it", TEAL],
    ["ACT", "cmd/controller", "Go", "Collects the readings, saves the plan, sends it out", AMBER],
    ["HEAL", "internal/controller", "Go", "Notices a dead machine in 3 seconds and forces a re-cut", TEAL],
    ["SERVE", "worker/", "Python", "Machines that hold layers but no state, plus the router", TEAL],
    ["EVAL", "bench/run.py, bench/dpsim", "Python, Go", "The tests: full cluster runs, and solver-only runs", AMBER],
  ];
  rows.forEach(([stage, path, lang, desc, col], i) => {
    const y = 1.45 + i * 0.72;
    if (i % 2 === 0) s.addShape(p.ShapeType.rect, { x: M, y, w: W - 2 * M, h: 0.66, fill: { color: "F7F8FA" }, line: { width: 0 } });
    s.addShape(p.ShapeType.roundRect, { x: M + 0.16, y: y + 0.16, w: 0.95, h: 0.34, rectRadius: 0.17, fill: { color: col }, line: { width: 0 } });
    s.addText(stage, { x: M + 0.16, y: y + 0.16, w: 0.95, h: 0.34, fontFace: BFONT, fontSize: 8.5, bold: true, color: "FFFFFF", align: "center", valign: "middle", margin: 0 });
    s.addText(path, { x: M + 1.3, y, w: 4.0, h: 0.66, fontFace: MFONT, fontSize: 9.5, color: INK, valign: "middle", margin: 0 });
    s.addText(lang, { x: M + 5.4, y, w: 1.2, h: 0.66, fontFace: BFONT, fontSize: 9.5, color: MUTED, valign: "middle", margin: 0 });
    s.addText(desc, { x: M + 6.7, y, w: 5.2, h: 0.66, fontFace: BFONT, fontSize: 10, color: "3E4658", valign: "middle", margin: 0 });
  });
  foot(s, 2, "The generated network code and the compiled kernel program are already in the repo, so a demo needs no extra build tools.");
}

/* 3. eBPF */
{
  const s = p.addSlide();
  head(s, "1. WATCH", "Measuring network delay inside the kernel");
  code(s, M, 1.45, 7.3, 4.5, "internal/ebpf/bpf/tcpmon.c",
`struct flow_val {
    __u64 bytes;         // cumulative payload bytes
    __u64 srtt_us;       // most recent smoothed RTT
    __u64 srtt_samples;  // cumulative tcp_probe hits
};

struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __type(key,   struct flow_key);
    __type(value, struct flow_val);
} flows SEC(".maps");

SEC("tp_btf/tcp_probe")
int BPF_PROG(tcp_probe_hook, struct sock *sk,
                             struct sk_buff *skb)
{
    struct tcp_sock *tp = (struct tcp_sock *)sk;
    __u32 srtt = BPF_CORE_READ(tp, srtt_us) >> 3;
    val->srtt_us = srtt;
    __sync_fetch_and_add(&val->srtt_samples, 1);
    return 0;
}

SEC("fentry/tcp_sendmsg")
int BPF_PROG(tcp_sendmsg_hook, struct sock *sk,
             struct msghdr *msg, size_t size)`);
  note(s, 8.2, 1.45, 4.51, 1.55, "Why we use the kernel's own number",
    "Linux already tracks the round-trip time of every connection, because it needs it to manage traffic. Reading that number costs nothing, and it cannot be wrong the way a timer inside the program can.", AMBER);
  note(s, 8.2, 3.15, 4.51, 1.4, "Build once, run anywhere",
    "The program adjusts itself to the running kernel when it is loaded. So one compiled file works on any modern Linux kernel, with no rebuilding.");
  note(s, 8.2, 4.7, 4.51, 1.25, "We only watch what we need",
    "We only look at connections between our own machines. The controller then matches each connection to the machine it came from.");
  foot(s, 3, "Demo: show the live readings with kubectl logs");
}

/* 4. DP */
{
  const s = p.addSlide();
  head(s, "2. DECIDE", "The solver that picks the cut");
  code(s, M, 1.45, 7.3, 4.5, "internal/partition/partition.go",
`// stageCost: receive + compute for one stage.
// An empty stage is skipped by the router entirely,
// so it costs nothing - not even its hop.
func stageCost(in Input, worker, layers int) float64 {
    if layers == 0 {
        return 0
    }
    cost := float64(layers) * in.PerLayerMs /
            math.Max(in.Workers[worker].Speed, 0.01)
    if worker > 0 {
        cost += in.LinkMs[worker-1]
    }
    return cost
}

// Optimal solves the linear partition in O(N^2 * K).
for w := 1; w <= k; w++ {
  for j := 0; j <= n; j++ {
    for split := 0; split <= j; split++ {
      cost := math.Max(f[split][w-1],
              stageCost(in, w-1, j-split))
      if cost < f[j][w] {
        f[j][w] = cost
        choice[j][w] = split
      }
    }
  }
}`);
  note(s, 8.2, 1.45, 4.51, 1.45, "f[j][w]",
    "The best we can do for the first j layers on the first w machines. The final answer is f[N][K], and choice[][] tells us where the cuts go.", TEAL);
  note(s, 8.2, 3.05, 4.51, 1.45, "Heat is just a slower speed",
    "Each machine has one Speed number. When it gets hot, that number drops. So the solver has no special code for heat anywhere - it just sees a slower machine.");
  note(s, 8.2, 4.65, 4.51, 1.3, "A machine can get zero layers",
    "That one line is what lets the solver skip a machine with a bad network. Nobody wrote a rule for skipping - it falls out of the maths.", AMBER);
  foot(s, 4, "Demo: go test ./internal/partition/... - it checks the solver against brute force on 200 random cases.");
}

/* 5. Decider + apply */
{
  const s = p.addSlide();
  head(s, "3-4. ACT and HEAL", "From a decision to a running system");
  code(s, M, 1.45, 7.3, 3.1, "internal/partition/partition.go - Decider",
`func (d *Decider) Decide(now time.Time, in Input,
                         force bool) (*Result, bool, error) {
    opt, err := Optimal(in)
    if d.current == nil || force ||
       workersChanged(d.current, in.Workers) {
        d.current, d.lastChange = opt, now
        return opt, true, nil          // healing path
    }
    currentCost := Evaluate(in, d.current.Splits())
    improved := opt.BottleneckMs <
                currentCost*(1-d.ImprovementFrac)
    if improved && now.Sub(d.lastChange) >= d.Cooldown {
        d.current, d.lastChange = opt, now
        return opt, true, nil          // hysteresis passed
    }`);
  code(s, M, 4.75, 7.3, 1.83, "demo - make a machine hot, then cool it again",
`W2=$(docker inspect -f '{{range .NetworkSettings.Networks}}\\
     {{.IPAddress}}{{end}}' kubeedgeinfer-worker2)
curl -X POST http://$W2:9101/gpu/override -d '{"temp_c": 92}'
curl -X POST http://$W2:9101/gpu/override -d '{"clear": true}'`);
  note(s, 8.2, 1.45, 4.51, 1.55, "Three ways out, one function",
    "If a machine appears or dies, re-cut at once. If a new cut is clearly better and enough time has passed, apply it. Otherwise keep the current cut and just update its cost.", TEAL);
  note(s, 8.2, 3.15, 4.51, 1.4, "We compare fairly",
    "Before comparing, we re-score the cut we are already using with today's readings. Otherwise we would be comparing against an old number.");
  note(s, 8.2, 4.7, 4.51, 1.88, "Changing the cut with no restart",
    "The controller saves the new layer ranges in Kubernetes and sends them to the machines with a new version number. Machines refuse messages from an old version. The router then fetches the new plan and replays the request from the start. Machines keep no state, so replaying is always safe.", AMBER);
  foot(s, 5, "Layers move off the hot machine in about 35 seconds, and come back once it cools down.");
}

/* 6. Runbook */
{
  const s = p.addSlide();
  head(s, "Demo", "Runbook");
  const steps = [
    ["One command starts everything", "./run-demo.sh", "Builds everything, starts the cluster, and opens a live dashboard on localhost:8000 showing the machines, how busy each one is, the network delays, and a log of every re-cut."],
    ["Watch the plan change", "kubectl -n kubeedgeinfer get ipl demo -w", "The layer ranges and the version number update as the controller re-plans."],
    ["Send it some work", "kubectl -n kubeedgeinfer port-forward svc/router 8080:8080\ncurl -X POST localhost:8080/generate \\\n  -d '{\"prompt_len\":16,\"max_new_tokens\":8}'", "The router sends each request through the machines in order."],
    ["Break something on purpose", "curl -X POST http://$W2:9101/gpu/override \\\n  -d '{\"temp_c\": 92}'", "Or press the buttons on the dashboard. Layers move off the hot machine, then come back once it cools."],
    ["Reproduce the numbers", "go run ./bench/dpsim\npython3 bench/run.py --all && python3 bench/plot.py", "dpsim reproduces the numbers on slide 11 with no cluster at all. bench/run.py needs the running cluster and measures words per second and idle time."],
  ];
  steps.forEach(([t, cmd, b], i) => {
    const y = 1.42 + i * 1.06;
    s.addShape(p.ShapeType.ellipse, { x: M, y: y + 0.16, w: 0.34, h: 0.34, fill: { color: i % 2 === 0 ? AMBER : TEAL }, line: { width: 0 } });
    s.addText(String(i + 1), { x: M, y: y + 0.16, w: 0.34, h: 0.34, fontFace: BFONT, fontSize: 12.5, bold: true, color: "FFFFFF", align: "center", valign: "middle", margin: 0 });
    s.addText(t, { x: M + 0.5, y: y + 0.08, w: 2.2, h: 0.3, fontFace: BFONT, fontSize: 12, bold: true, color: INK, margin: 0 });
    s.addShape(p.ShapeType.roundRect, { x: M + 2.75, y: y + 0.02, w: 5.1, h: 0.92, rectRadius: 0.05, fill: { color: INK }, line: { width: 0 } });
    s.addText(cmd, { x: M + 2.92, y: y + 0.08, w: 4.85, h: 0.8, fontFace: MFONT, fontSize: 7.5, color: "D5DAE3", valign: "middle", lineSpacing: 10.5, margin: 0 });
    s.addText(b, { x: M + 8.05, y: y + 0.02, w: 4.05, h: 0.92, fontFace: BFONT, fontSize: 9, color: "3E4658", lineSpacing: 11.5, margin: 0 });
  });
  foot(s, 6, "You need: a modern Linux kernel, Docker, kind, kubectl and Python 3.11 or newer.");
}

p.writeFile({ fileName: "KubeEdgeInfer-CodeDemo.pptx" }).then(f => console.log("wrote", f));
