#!/usr/bin/env python3
"""Check completed matrix ledgers, correctness checks and source file hashes."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("experiment", type=Path)
    args = ap.parse_args()
    root = args.experiment.resolve()
    validation = {"matrices": {}, "all_verified": False}
    for matrix, expected in (("objective", 20), ("demand", 12)):
        data = root / "raw" / matrix
        events = json.loads((data / "events.json").read_text())
        schedule = json.loads((data / "schedule.json").read_text())
        metas = list(data.glob("runs/*/meta.json"))
        assert len(events) == len(schedule) == len(metas) == expected, f"incomplete {matrix}"
        assert all(e["returncode"] == 0 for e in events), f"failed {matrix}"
        verified = 0
        for line in (data / "SOURCE_SHA256SUMS").read_text().splitlines():
            digest, relative = line.split("  ", 1)
            path = (data / relative).resolve()
            assert path.is_relative_to(data.resolve()), f"invalid source path {relative}"
            assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, f"hash mismatch {path}"
            verified += 1
        expected_files = sum(p.is_file() for p in data.rglob("*")) - 1
        assert verified == expected_files, f"missing source hashes {matrix}"
        if matrix == "demand":
            assert all(json.loads((p.parent / "correctness.json").read_text())["exact_match"] for p in metas)
        validation["matrices"][matrix] = {"completed_runs": expected, "source_files_verified": verified}
    status = json.loads((root / "analysis/status.json").read_text())
    assert status["completed_runs"] == 32 and status["excluded"] == 0 and status["failed_requests"] == 0
    snapshots = root / "provenance"
    for line in (snapshots / "SOURCE_ARCHIVES_SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        assert hashlib.sha256((snapshots / name).read_bytes()).hexdigest() == digest
    validation["tested_source_archives_verified"] = 2
    validation["all_verified"] = True
    validation["measured_requests"] = status["total_requests"]
    (root / "transfer-validation.json").write_text(json.dumps(validation, indent=2) + "\n")
    print(json.dumps(validation, indent=2))


if __name__ == "__main__":
    main()
