#!/usr/bin/env python3
"""Audit, compile general elsarticle PDF, and export a flat source archive."""
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(*args):
    subprocess.run(args, cwd=HERE, check=True)


def main():
    run(sys.executable, "analyze.py")
    run(sys.executable, "checks/gate.py")
    run(sys.executable, "figures.py")
    run("pandoc", "manuscript.md", "--from=markdown", "--to=latex", "--natbib",
        "--template=elsarticle-template.tex", "--output=manuscript.tex")
    run("latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", "manuscript.tex")
    log = (HERE / "manuscript.log").read_text()
    for bad in ("undefined", "There were undefined references", "Missing character:", "Float too large", "Overfull"):
        assert bad not in log, f"LaTeX verification failed: {bad}"
    manuscript = (HERE / "manuscript.md").read_text()
    abstract = manuscript.split("abstract: |\n", 1)[1].split("\nkeywords:", 1)[0]
    abstract = "\n".join(line.removeprefix("  ") for line in abstract.splitlines())
    (HERE / "abstract.md").write_text(abstract + "\n")
    # Include the installed Elsevier class/style so the flat bundle is portable.
    for name in ("elsarticle.cls", "elsarticle-num.bst"):
        src = subprocess.check_output(["kpsewhich", name], text=True).strip()
        assert src, f"missing class/style: {name}"
        if Path(src).resolve() != (HERE / name).resolve():
            shutil.copyfile(src, HERE / name)
    figures = [f"{row['figure']}.pdf" for row in json.loads((HERE / "analysis/figure-provenance.json").read_text())]
    names = ["manuscript.tex", "manuscript.bbl", "references.bib", "elsarticle.cls",
             "elsarticle-num.bst", "objective-table.tex", "adaptation-table.tex", "prior-work-table.tex", *figures]
    with zipfile.ZipFile(HERE / "elsevier-source.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for name in names:
            z.write(HERE / name, name)
    manifest = {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                for name in names + ["manuscript.md", "manuscript.pdf", "elsevier-source.zip"]}
    (HERE / "build-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    run(sys.executable, "export_overleaf.py")
    print("Verified PDF and flat Elsevier source archive:", HERE)


if __name__ == "__main__":
    main()
