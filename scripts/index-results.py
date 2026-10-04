#!/usr/bin/env python3
"""Expose historical experiments in results/ while preserving existing links."""
import csv
import hashlib
import os
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "results"


def alias(target, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_symlink():
        assert dest.resolve() == target.resolve(), f"conflicting alias {dest}"
    elif not dest.exists():
        dest.symlink_to(os.path.relpath(target, dest.parent), target_is_directory=target.is_dir())


def main():
    DEST.mkdir(exist_ok=True)
    for directory in (ROOT / "docs/data").iterdir():
        if directory.is_dir() and any(directory.iterdir()):
            experiment = DEST / directory.name
            if experiment.is_symlink():
                assert experiment.resolve() == directory.resolve()
                experiment.unlink()
            experiment.mkdir(exist_ok=True)
            for artifact in directory.iterdir():
                dest = experiment / artifact.name
                if artifact.name == "README.md" and dest.exists() and not dest.is_symlink():
                    text = dest.read_text()
                    if "Relative artifact links preserve the original research files." in text:
                        dest.rename(experiment / "INDEX.md")
                alias(artifact, dest)
            if not (experiment / "INDEX.md").exists():
                link = f"../../docs/data/{directory.name}/README.md"
                detail = f"[Method, evidence and reproduction]({link}).\n\n" if (directory / "README.md").exists() else ""
                (experiment / "INDEX.md").write_text(f"# {directory.name}\n\n{detail}Artifacts are listed in this experiment folder. Relative artifact links preserve the original research files.\n")
    legacy = DEST / "journal-benchmark-2026-09-13"
    for src in (ROOT / "bench/results").glob("*"):
        if not src.is_file():
            continue
        category = "network" if src.name.startswith("netem_") else "worker-loss" if src.name.startswith("failure_") else "analysis"
        dest = legacy / category / src.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            assert hashlib.sha256(dest.read_bytes()).digest() == hashlib.sha256(src.read_bytes()).digest(), f"historical result changed: {src}"
        else:
            shutil.copy2(src, dest)
    for src in (ROOT / "docs").glob("journal-benchmark*2026-09-13.*"):
        alias(src, legacy / "reports" / src.name)
    for src in (ROOT / "docs").glob("phase*-dpsweep*.csv"):
        phase = src.name.split("-", 1)[0]
        alias(src, DEST / "partition-sweeps-2026-09" / phase / src.name)
    for src in (ROOT / "docs").glob("phase*-findings.md"):
        alias(src, DEST / "partition-sweeps-2026-09" / "reports" / src.name)
    alias(ROOT / "docs/thermal-benchmark-codespace-2026-09-12.md", DEST / "thermal-2026-09-12" / "report.md")
    with (DEST / "catalog.csv").open("w", newline="") as f:
        w = csv.writer(f); w.writerow(["experiment", "artifact", "source"])
        # Walk through experiment aliases as well as physical directories.
        for experiment in sorted(p for p in DEST.iterdir() if p.is_dir()):
            paths = [Path(directory) / name for directory, _, files in os.walk(experiment, followlinks=True) for name in files]
            for p in sorted(paths):
                w.writerow([experiment.name, str(p.relative_to(experiment)), str(p.resolve().relative_to(ROOT))])
    broken = [str(p) for p in DEST.rglob("*") if p.is_symlink() and not p.exists()]
    assert not broken, f"broken result links: {broken}"
    print(f"Indexed {sum(p.is_dir() for p in DEST.iterdir())} experiments in {DEST}")


if __name__ == "__main__":
    main()
