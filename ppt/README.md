# Presentation deck

Three deliverables, all generated from the repository so they cannot drift
from the code or the measurements.

| File | What it is |
|---|---|
| `KubeEdgeInfer_Presentation.pptx` | Main deck, 41 slides — sections 1–10 (title → references) |
| `KubeEdgeInfer_Code_Demo.pptx` | Section 11, 23 slides — code walkthrough + live demo, kept separate so it can be driven at demo speed |
| `KubeEdgeInfer.tex` | The same content as one Beamer deck (50 frames), for anyone who wants LaTeX |

## Regenerating

```bash
pip install python-pptx
python3 ppt/make_main_deck.py      # -> KubeEdgeInfer_Presentation.pptx
python3 ppt/make_code_deck.py      # -> KubeEdgeInfer_Code_Demo.pptx

pdflatex ppt/KubeEdgeInfer.tex     # twice; needs texlive-latex-recommended + -extra
```

`deckkit.py` holds the shared styling primitives (title, bullets, table, code
box, figure). Code boxes auto-shrink their font to fit their frame, and slide
titles auto-shrink to stay on one line, so edits to the text do not silently
produce overflowing slides.

## Where the content comes from

- **Every result number** is read at build time from `bench/results/summary.json`.
  Edit the benchmarks, re-run `python3 bench/run.py --all && python3 bench/plot.py`,
  regenerate, and the deck updates itself.
- **Figures** are the PNGs in `bench/results/` — the same ones the harness produces.
- **Testbed / Docker / VM configuration slides** were read off the machine the
  reported runs executed on (`uname`, `docker info`, `lscpu`, `kind --version`).
- **Code excerpts** are copied from the actual source files, with the path shown
  as the caption on each listing.

## Before you present

**Verify the citations.** The ten surveyed papers are real and the venue/year
for each is given as accurately as I could state it, but confirm the exact
volume, page numbers and DOI/arXiv IDs against the publisher before submitting
anything graded. Reference [1] carries its arXiv ID for that reason.

The deck deliberately reports two results that are *not* flattering — the
neutral `netem` outcome and the inconclusive `profileonly` ablation — and
names the evaluation gap against EdgeShard on the comparison slide. Keep them.
They are much easier to defend than the alternative if a reviewer reads
`summary.json`.
