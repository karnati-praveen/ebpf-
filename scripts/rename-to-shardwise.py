#!/usr/bin/env python3
"""Rename the project from KubeEdgeInfer to Shardwise across a checkout.

    python3 scripts/rename-to-shardwise.py          # rewrite the current checkout
    python3 scripts/rename-to-shardwise.py --check  # list what still uses the old name

Kept on purpose so a branch created before the rename (e.g. demo/laptop-app)
can be brought over with the same rules, then `make proto` regenerates stubs.

Recorded evidence is never rewritten: everything under results/, docs/data/
and bench/results/ (except Go sources, whose imports must compile), data
files (csv/json/log), and any path pointing into
those trees keep the old names, because they record what actually ran.
Generated protobuf stubs are skipped here and regenerated with `make proto`
(their embedded descriptors are length-prefixed, so text edits corrupt them).
"""

import re
import subprocess
import sys

# Order matters: longest/most specific first.
RULES = [
    ("KubeEdgeInfer", "Shardwise"),
    ("kubeedgeinfer", "shardwise"),
    ("KEINFER", "SHARDWISE"),
    ("keinfer", "shardwise"),
]
OLD = re.compile("|".join(re.escape(o) for o, _ in RULES))
NEW = dict(RULES)

SKIP_DIRS = ("results/", "docs/data/", "bench/results/", "gen/", "worker/gen/")
SKIP_SUFFIX = (".csv", ".json", ".log", ".jsonl", ".pptx", ".png", ".pdf", ".o")
SKIP_FILES = {"scripts/rename-to-shardwise.py"}
# Paths into recorded evidence inside prose: leave them pointing at real files.
PROTECT = re.compile(r"(?:docs/data|bench/results|results)/[^\s)`\"'\]>|,]*")

FILE_RENAMES = {
    "docs/paper/kubeedgeinfer-draft.md": "docs/paper/shardwise-draft.md",
    "ppt/KubeEdgeInfer.tex": "ppt/Shardwise.tex",
    "ppt/KubeEdgeInfer_Code_Demo.pptx": "ppt/Shardwise_Code_Demo.pptx",
    "ppt/KubeEdgeInfer_Presentation.pptx": "ppt/Shardwise_Presentation.pptx",
    "ppt/KubeEdgeInfer_Presentation_Full.pptx": "ppt/Shardwise_Presentation_Full.pptx",
}


def rewrite(text):
    out, pos = [], 0
    for m in PROTECT.finditer(text):
        out.append(OLD.sub(lambda x: NEW[x.group(0)], text[pos:m.start()]))
        out.append(m.group(0))
        pos = m.end()
    out.append(OLD.sub(lambda x: NEW[x.group(0)], text[pos:]))
    return "".join(out)


def candidates():
    files = subprocess.run(["git", "grep", "-I", "-l", "-E", OLD.pattern],
                           capture_output=True, text=True).stdout.split()
    # Go sources are always rewritten, even inside data trees: an import of
    # the old module path would break `go build ./...`.
    return [f for f in files if f not in SKIP_FILES and (
        f.endswith(".go") and not f.startswith(("gen/",))
        or not f.startswith(SKIP_DIRS) and not f.endswith(SKIP_SUFFIX))]


def main():
    check = "--check" in sys.argv
    changed = 0
    for f in candidates():
        src = open(f, encoding="utf-8").read()
        dst = rewrite(src)
        if dst != src:
            changed += 1
            if check:
                print(f)
            else:
                open(f, "w", encoding="utf-8").write(dst)
    for old, new in FILE_RENAMES.items():
        r = subprocess.run(["git", "ls-files", "--error-unmatch", old], capture_output=True)
        if r.returncode == 0:
            print(f"rename {old} -> {new}" if check else "", end="\n" if check else "")
            if not check:
                subprocess.run(["git", "mv", old, new], check=True)
    print(f"{'would change' if check else 'changed'} {changed} files")


if __name__ == "__main__":
    main()
