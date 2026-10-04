#!/usr/bin/env python3
"""Validate vm3's candidate-replay outputs and export descriptive summaries."""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("data", type=Path)
    args = ap.parse_args()
    root = args.data
    data = json.loads((root / "replay/input.json").read_text())
    replay = [json.loads(line) for line in (root / "replay/replay-results.jsonl").read_text().splitlines()]
    eligible = [c for c in data["Cases"] if c["Eligible"]]
    assert len(replay) == len(eligible) * 10, "incomplete replay"
    keys = [(r["run"], r["at"], r["arm"], r.get("hypothetical_remaining_tokens", 0)) for r in replay]
    assert len(keys) == len(set(keys)), "duplicate replay rows"
    fixed = {(r["run"], r["at"]): r for r in replay if r["arm"] == "fixed"}
    for r in replay:
        if r["arm"] != "oracle-future-trace":
            n = sum(o["Scenario"] == r["scenario"] and o["At"] < r["at"] for o in data["Observations"])
            assert n == r["calibration_n"], "calibration used future observations"
        if r["arm"] == "remaining-work" and r["verdict"]["accept"]:
            assert fixed[r["run"], r["at"]]["verdict"]["accept"], "shorter horizon expanded acceptance"
    groups = collections.defaultdict(list)
    for r in replay:
        groups[r["arm"], r.get("hypothetical_remaining_tokens", 0)].append(r)
    summary = []
    for (arm, budget), rs in groups.items():
        summary.append({"arm": arm, "hypothetical_remaining_tokens": budget, "candidates": len(rs),
                        "accepted": sum(r["verdict"]["accept"] for r in rs),
                        "rejected": sum(not r["verdict"]["accept"] for r in rs),
                        "calibration_warmed_candidates": sum(r["calibration_n"] >= 3 for r in rs)})
    with (root / "replay/summary.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0])); w.writeheader(); w.writerows(summary)
    runs = []
    expected = {"meta.json", "requests.csv", "series.csv", "faults.csv", "decisions.json"}
    for arm, count in (("vm", 30), ("vm-single", 3)):
        dirs = sorted(p.parent for p in (root / "raw" / arm).glob("*/meta.json"))
        assert len(dirs) == count, f"expected {count} {arm} runs"
        for d in dirs:
            assert expected <= {p.name for p in d.iterdir()}, f"missing artifacts: {d}"
            meta = json.loads((d / "meta.json").read_text())
            with (d / "requests.csv").open() as f:
                req = list(csv.DictReader(f))
            runs.append({"run": d.name, "arm": arm, "requests": len(req), "successful": sum(r["ok"] == "1" for r in req),
                         "unexpected_restarts": meta.get("contaminated_by_unexpected_worker_restart", [])})
    with (root / "run-inventory.json").open("w") as f:
        json.dump(runs, f, indent=2)
    validations = {"measured_runs": len(runs), "candidate_count": len(eligible), "replay_rows": len(replay),
                   "causal_calibration": "passed: completed observations strictly earlier than candidate",
                   "remaining_horizon_monotonicity": "passed", "required_measured_artifacts": "passed",
                   "unique_replay_rows": "passed"}
    (root / "replay/validation.json").write_text(json.dumps(validations, indent=2))
    with (root / "SHA256SUMS").open("w") as f:
        for p in sorted(root.rglob("*")):
            if p.is_file() and p.name != "SHA256SUMS":
                f.write(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(root)}\n")
    print(json.dumps(validations, indent=2))
    print("\n" + (root / "replay/summary.csv").read_text())


if __name__ == "__main__":
    main()
