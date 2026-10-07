# Elsevier working manuscript — 4 October 2026

Start with [manuscript.pdf](manuscript.pdf). This general `elsarticle` draft
includes the abstract, related work, decision model, protocols, results,
ablations, limitations, and references. It is prepared for review, not submitted.
The source is [manuscript.md](manuscript.md); edit it and rebuild to keep the
LaTeX/PDF synchronized. Author and publication declarations remain placeholders.

The dedicated Overleaf project is at `overleaf-paper/` in the repository root;
upload `overleaf-paper.zip` with `main.tex` as the main document and pdfLaTeX
as the compiler. These exports and this draft directory are ignored by Git.
The build command refreshes the export, or run `export_overleaf.py` to package
the current compiled manuscript without repeating analysis.

| File | Purpose |
|---|---|
| [RESULTS_AUDIT.md](RESULTS_AUDIT.md) | All ten evidence collections, corrected metrics, positive and negative findings |
| [NOVELTY.md](NOVELTY.md) | Claim boundaries and primary-source comparison |
| [VENUES_AND_NEXT_EXPERIMENTS.md](VENUES_AND_NEXT_EXPERIMENTS.md) | FGCS/JPDC fit and prioritized experiment designs |
| [analysis/audit.json](analysis/audit.json) | Hash audit, run totals, source snapshot comparison |
| [analysis/per-run.csv](analysis/per-run.csv) | Independently recomputed 65 real-model observations |
| [analysis/summary.csv](analysis/summary.csv) | Condition medians, ranges, requests and failures |
| [analysis/contrasts.csv](analysis/contrasts.csv) | Ratio-of-medians and paired descriptive comparisons |
| [references.bib](references.bib) | Twelve primary-paper citations; preprints identified |
| [abstract.md](abstract.md) | Current abstract, generated from the manuscript |
| [validation.json](validation.json) | Build, artifact and test verification record |
| [elsevier-source.zip](elsevier-source.zip) | Flat source bundle for import into a LaTeX editor |

Build from the repository root:

```sh
python3 docs/paper/elsevier/build.py
```

Requirements: Python 3.10+, matplotlib, Pandoc, latexmk, and a TeX Live installation
with `elsarticle`, microtype, graphics, and standard math/table packages.
These tools are installed in this Codespace. The build checks retained source
hashes, complete matrices, correctness checks, unique runs, agreement with
existing summaries, and unresolved LaTeX references. It does not rerun inference
or modify the canonical datasets. The source archive uses a single folder level,
following [Elsevier's LaTeX instructions](https://www.elsevier.com/researcher/author/policies-and-guidelines/latex-instructions).
Numerical style is provisional until a target journal's current guide is checked.

The package uses the standard Elsevier class installed by TeX Live, with its
license retained. `elsarticle.cls` and `elsarticle-num.bst` are copied into the
export for portability; they are upstream files, not project contributions.
The ten figures and three tables are regenerated from raw data. Keep analytical/synthetic
counts separate from real-model run counts.

Plugin search for Zotero, Mendeley, and Overleaf returned no matching available
integrations in this session. No plugin was installed. Local BibTeX and the
build command provide a working workflow without an external account.

## Substantial revision in this research session

The manuscript now includes three mathematical propositions and proofs, the exact
ordered-partition recurrence, an ideal concurrency capacity envelope, finite-budget
payback conditions, sensitivity derivatives, and personal-chat/shared-service
scenario analysis. Ten figures cover architecture, measured tradeoffs, model
capacity diagnosis, fault contrasts/traces, demand decisions, analytical
sensitivity, synthetic queueing/routing, and transition forecast mismatch.
The application analysis uses service proxies; it does not claim a semantic chat
benchmark or a human usability study. No new remote model trials were run.

Manuscript host labels are **vm1** (coordinator/local worker) and **vm2** (remote
worker). Original raw artifact labels are vm2 and vm3, respectively. Raw source
files retain their names and hashes.

Additional reproducibility artifacts:

- `figures.py` and `analysis/figure-provenance.json`: every figure's data source and evidence type.
- `analysis/demand-move-timing.json`: initial assignment, cooldown, and move timestamps.
- `analysis/representative-traces.json`: deterministic trace-selection rule and run IDs.
- `analysis/capacity-proxy.json`: startup-profile predictions alongside observed throughput.
- `checks/placement.go`: independent exhaustive verification of both objectives on 1,000 random inputs.
- `checks/gate.py`: 20,000 numerical checks of fixed and finite-budget payback inequalities.
- `SUBMISSION_READINESS.md`: concrete remaining research and author requirements.

All Docker containers, volumes, images, networks created for kind, and build cache
were subsequently removed at the user's request. Root filesystem usage fell to
56%; this session does not recreate Docker or download model weights.
