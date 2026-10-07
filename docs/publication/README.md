# General IEEE conference writing package

Open **main.pdf** to review the compiled paper. Edit **main.tex** and
**references.bib** for a conventional LaTeX/Overleaf workflow. `IEEEtran.cls`
and `IEEEtranN.bst` are included in the final ZIP with their upstream license
headers. The template uses normal IEEEtran conference fonts and margins.
No particular conference's eligibility or page policy is implied.

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

In the repository, Markdown is the editable authoring source. After editing
`ieee-manuscript.md`, run `python scripts/build-ieee.py`; it regenerates LaTeX.
Editing LaTeX directly and later running that script will overwrite those edits.
The root `main.bbl` is also supplied for inspection and portability.

The writing package contains:

- `figures/`: historical and newly measured figures, with scope in their captions.
- `source/`: runtime, tests, raw evidence, reports and reproduction scripts.
- `planner-checks/`: isolated cost-model checks runnable with Go, without the serving dependencies.
- `demo-screenshots/`: actual captures, captions and provenance; these are not throughput baselines.
- `revision-history/`: retained long-form writing sources before and after technical corrections.
- `SHA256SUMS`: checksums of every included file.

Read **READINESS.md** and `source/docs/PUBLICATION_REVISION.md` before writing
new claims. Pilots, interrupted hardware campaigns, historical two-VM runs,
synthetic diagnostics and complete local campaigns are kept separate. The
source archive omits weights, Python environments, caches and third-party
research-PDF downloads. Their absence is intentional for low disk usage.

For testing your laptop and your friend's laptop, start with
`source/docs/TWO_LAPTOP_TESTS.md`. The separate small test-kit ZIP contains the
needed Python runtime and scripts. Physical-laptop results become paper
evidence only when the actual runs are completed and audited.

Authors must fill in final metadata, choose a venue, review the claims and
check its formatting, page, artifact and review policies before submission.
This package does not submit or publish anything. No acceptance probability
is represented by the implementation or formatting checks.
