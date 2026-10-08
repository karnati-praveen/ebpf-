# Shardwise IEEE paper and demo package

Open **main.pdf** for the paper. **main.tex**, **references.bib**, **figures/**,
and **demo-screenshots/** are the editable IEEE LaTeX sources. The portable ZIP
includes IEEEtran.cls and IEEEtranN.bst with their original license headers.

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

The paper uses standard IEEE conference fonts, letter paper and margins. It
keeps **Anonymous Authors** for the author's later audit. CCGrid 2027 is a
possible target: its [official call](https://hpcclab.org/ccgrid27-call-for-papers/)
requires double-blind IEEE conference submissions of at most ten pages including
references. This is a formatting target, not a submission or acceptance claim.

The paper includes actual CPU chat/recovery screenshots and a separate CPU/GPU
illustration. The illustration explicitly assigns 8 layers to CPU and 16 to GPU
and states that GPU execution was not measured. Visible Codespaces hostnames
are replaced with CPU host. The real demo uses Qwen2.5-0.5B-Instruct; the
research measurements use Qwen3-0.6B and a different dependency environment.

The combined archive adds **demo-package/** with the Linux amd64 .deb,
installation instructions and package provenance, plus **source/** with selected
research runtime sources, raw evidence and validation reports. Model weights,
Python environments, caches, authentication tokens and .git are excluded.
The smaller paper-only ZIP is suitable for editing in Overleaf.

In the repository, ieee-manuscript.md is the authoring source. Running
`python scripts/build-ieee.py` regenerates main.tex and validates the build.
Direct LaTeX edits should not subsequently be overwritten by that script.

Before submission, audit the claims, authorship, selected venue and track,
artifact anonymity/access, and the IEEE policies referenced by its call.
The repeated evaluation and optimized-engine baseline remain incomplete;
single-repetition local observations do not establish statistical superiority.
See READINESS.md and the supplied validation report for precise limits.
