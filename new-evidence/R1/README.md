# R1 evidence package

Read summary.md first. The five requested deliverables are at this directory root. Supplementary per-agent CSV/BibTeX/notes and sources retain provenance; the combined files are authoritative. build_root.py, fetch_extra.py and finish.py are working audit scripts, not a fully reproducible crawler (they require saved metadata and sources).

Research date: 6 October 2026; bounded approximately twenty-minute window with three parallel agents, shortened at the user’s follow-up request. Source discovery used web searches targeting arXiv, ACM, IEEE and USENIX plus primary proceedings, author pages, Crossref and reference lists. Google Scholar coverage was not independently verified; do not claim that database was exhaustively searched. Publisher and ScienceDirect access restrictions prevented some full-text and current author-guide verification. All such gaps are explicitly labelled UNVERIFIED.

The CSV provides selected exact quotations and page/section locators. It does not yet supply an exact sentence for every individual field. This limitation is repeated in summary.md and claims-open-vs-taken.md. Abstract-only and metadata-only entries must not be used as fully verified technical evidence.

BibTeX may cite an arXiv version using its first-posting year even where the CSV records the later peer-reviewed venue year. Prefer the peer-reviewed record when integrating into the manuscript. No DOI was inferred from a plausible conference identifier. All six initial existing modified repository files and the existing untracked demo/app.py were preserved.
