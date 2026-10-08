#!/usr/bin/env python3
"""Build and verify the editable IEEE conference draft; make portable assets."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT/"docs/publication"


def main():
    (HERE/"figures").mkdir(exist_ok=True)
    for name in ("objective-frontier.pdf", "adaptation-comparison.pdf", "transition-forecast.pdf"):
        destination = HERE/"figures"/name
        if not destination.exists():
            shutil.copyfile(ROOT/"docs/paper/elsevier"/name, destination)
    def run(*args):
        subprocess.run(args, cwd=HERE, check=True)
    run("pandoc", "ieee-manuscript.md", "--from=markdown", "--to=latex", "--natbib",
        "--template=ieee-template.tex", "--output=main.tex")
    run("latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", "main.tex")
    log = (HERE/"main.log").read_text()
    forbidden = ("There were undefined references", "Citation `", "Missing character:", "Float too large", "Overfull")
    for pattern in forbidden:
        if pattern in log:
            raise RuntimeError(f"LaTeX validation failed: {pattern}")
    metadata = subprocess.check_output(["pdfinfo", "main.pdf"], cwd=HERE, text=True)
    pages = int(re.search(r"Pages:\s+(\d+)", metadata)[1])
    # Keep the user informed if the draft needs reduction; do not manipulate
    # margins or fonts to manufacture compliance.
    names = ["ieee-manuscript.md", "ieee-template.tex", "main.tex", "main.pdf", "main.bbl", "references.bib"]
    names += [str(p.relative_to(HERE)) for folder in ('figures', 'demo-screenshots') for p in sorted((HERE/folder).glob('*')) if p.suffix in ('.pdf', '.png')]
    manifest = {"format": "IEEEtran conference writing draft", "pages": pages,
                "venue_limit_verified": False,
                "sha256": {name: hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in names}}
    (HERE/"build-manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    print(f"Verified IEEE draft: {HERE/'main.pdf'} ({pages} pages)")


if __name__ == "__main__":
    main()
