# Presentation

Two decks, in both PowerPoint and LaTeX/Beamer form. Same content, same
palette — use whichever the venue wants.

| Deck | PowerPoint | LaTeX | Slides |
|---|---|---|---|
| **Simple talk** | `KubeEdgeInfer-Simple.pptx` | `kubeedgeinfer-simple.tex` | 10 |
| Full talk | `KubeEdgeInfer.pptx` | `kubeedgeinfer.tex` | 15 |
| Code walkthrough | `KubeEdgeInfer-CodeDemo.pptx` | `kubeedgeinfer-code.tex` | 6 |

**Start with the simple deck.** It is the same talk in ten slides: one idea per
slide, larger type, a single accent colour, and no slide that needs more than a
glance. The 15-slide version is the same material with the detail left in — the
maths, the implementation breakdown, and a second results slide — for a longer
slot or a reader who wants the full argument. Both quote the same measured
numbers.

The code walkthrough is deliberately a separate deck: present it only if there
is time for the live demo.

Simple deck contents, one per slide: title, introduction, literature review
(all 10 papers on one slide), the problem, what is new, how the system works,
results, comparison, conclusion, references.

The 15-slide deck splits the literature review over two slides and adds a
research-gap table, the maths and hysteresis rules, an implementation
breakdown, and a second results slide on what the solver actually decides.

The wording throughout is deliberately plain English — short sentences and
everyday words — so the talk works for an audience that does not already know
eBPF or pipeline parallelism. The technical terms that do appear (eBPF,
Kubernetes, layer, GPU) are explained where they are first used.

## Building

```bash
make          # both PDFs via XeLaTeX
make pptx     # both .pptx decks via pptxgenjs
```

LaTeX needs XeLaTeX or LuaLaTeX plus `beamer`, `pgfplots`, `makecell`,
`booktabs` and `listings`. Fonts default to Carlito and Caladea — the
metric-compatible open equivalents of Calibri and Cambria, which is what the
`.pptx` decks use. On Debian/Ubuntu:

```bash
sudo apt-get install texlive-xetex texlive-latex-extra texlive-pictures \
                     fonts-crosextra-carlito fonts-crosextra-caladea
```

The preamble documents two swaps: use the real Calibri/Cambria if you have
them, or drop to `lmodern` to build with plain pdfLaTeX.

`make pptx` needs Node and `pptxgenjs` (`npm install pptxgenjs`).

## Where the numbers come from

The results and comparison slides quote **partitioner-level** figures produced
by `bench/dpsim`, which replays each fault scenario's telemetry snapshot
through the same `internal/partition` code the controller runs and compares
the bottleneck-stage cost achieved by three policies:

```bash
go run ./bench/dpsim          # prints the table, writes bench/dpsim_results.json
```

| Scenario | KubeEdgeInfer | Profile-once | Static split |
|---|---|---|---|
| baseline | 42.0 ms | 42.0 ms | 42.0 ms |
| thermal throttle | 52.0 ms | 102.0 ms | 102.0 ms |
| network degradation | 62.0 ms | 122.0 ms | 122.0 ms |
| node failure | 62.0 ms | 62.0 ms | pipeline down |
| thermal + network | 62.0 ms | 182.0 ms | 182.0 ms |

This isolates partitioning quality from cluster overheads and needs no
cluster. **End-to-end tokens/sec, TTFT and measured bubble time are a
different measurement** and come from `bench/run.py --all`, which requires a
live kind or k3s cluster — the slides that quote them say so.

Both the deck and `bench/dpsim` treat the two baselines the way the repo does:
`static` keeps one equal split over the worker set it started with and never
re-plans, while `profileonly` still runs the DP and still heals on a
membership change but freezes its speed and link inputs at the first healthy
reading, approximating an offline-profiling system.

## Before presenting

Fill in author, institution and date on the title slide of whichever format
you use — they are left blank in both.
