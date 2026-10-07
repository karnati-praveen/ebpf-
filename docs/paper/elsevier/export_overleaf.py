#!/usr/bin/env python3
"""Export the current manuscript as a flat, self-contained Overleaf project."""
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parents[2]
DESTINATION = ROOT / "overleaf-paper"
ARCHIVE = ROOT / "overleaf-paper.zip"


def main():
    files = {
        "manuscript.tex": "main.tex",
        "manuscript.bbl": "main.bbl",
        "references.bib": "references.bib",
        "elsarticle.cls": "elsarticle.cls",
        "elsarticle-num.bst": "elsarticle-num.bst",
        "objective-table.tex": "objective-table.tex",
        "adaptation-table.tex": "adaptation-table.tex",
        "prior-work-table.tex": "prior-work-table.tex",
        "manuscript.pdf": "paper-preview.pdf",
    }
    for row in json.loads((SOURCE / "analysis/figure-provenance.json").read_text()):
        name = row["figure"] + ".pdf"
        files[name] = name
    for name in files:
        assert (SOURCE / name).is_file(), f"Missing manuscript artifact: {name}"
    DESTINATION.mkdir(exist_ok=True)
    for source, target in files.items():
        shutil.copyfile(SOURCE / source, DESTINATION / target)
    (DESTINATION / "README.md").write_text(
        "# Shardwise — Overleaf project\n\n"
        "Main document: `main.tex`. Compiler: pdfLaTeX.\n\n"
        "Edit main.tex, references.bib, or the included table files in Overleaf.\n"
        "The Elsevier class and numerical bibliography style are included.\n"
        "paper-preview.pdf is the verified local reference PDF.\n\n"
        "This is a working draft: author details and final declarations remain pending.\n"
    )
    names = sorted([*files.values(), "README.md"])
    hashes = {name: hashlib.sha256((DESTINATION / name).read_bytes()).hexdigest() for name in names}
    (DESTINATION / "SHA256.json").write_text(json.dumps(hashes, indent=2) + "\n")
    names.append("SHA256.json")
    with zipfile.ZipFile(ARCHIVE, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name in names:
            bundle.write(DESTINATION / name, name)
    print(f"Overleaf folder: {DESTINATION}")
    print(f"Overleaf ZIP: {ARCHIVE}")


if __name__ == "__main__":
    main()
