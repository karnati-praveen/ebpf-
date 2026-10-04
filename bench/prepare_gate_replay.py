#!/usr/bin/env python3
"""Prepare candidate-only research replay from completed vmrun artifacts.

No requests or VM mutations. Telemetry lacks flow timestamps, so reconstructed
inputs use maximum available eBPF SRTT (app fallback), not an exact controller
snapshot. Observed candidate point costs remain those recorded by the decider.
"""
import argparse
import csv
import datetime
import json
import math
from pathlib import Path


def timestamp(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def number(v):
    try:
        n = float(v)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def rows(p):
    with p.open() as f:
        return list(csv.DictReader(f))


def snapshot(row):
    try:
        speeds = dict(x.split(":", 1) for x in row["speeds"].split("|"))
        if not all(number(speeds.get(n)) and number(speeds[n]) > 0 for n in ("vm2", "vm3")):
            return None
        flows = json.loads(row["flows_json"])
        valid = [f for f in flows if f["dst"] == "10.10.1.5" and int(f["port"]) == 50051 and number(f["srtt_ms"]) is not None]
        ebpf = [float(f["srtt_ms"]) for f in valid if f["src"] != "app"]
        app = [float(f["srtt_ms"]) for f in valid if f["src"] == "app"]
        return {"At": float(row["t"]), "Input": {
            "TotalLayers": 28, "PerLayerMs": 6.567, "EmbedMs": .071, "HeadMs": 50.49,
            "ContextLen": 128,
            "Workers": [{"Name": n, "Addr": n + ":50051", "Node": n, "Speed": float(speeds[n])} for n in ("vm2", "vm3")],
            "LinkMs": [max(ebpf or app or [.5])],
        }}
    except (KeyError, ValueError, TypeError):
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("raw", type=Path)
    ap.add_argument("out", type=Path)
    args = ap.parse_args()
    cases, observations, skipped = [], [], []
    for directory in sorted(args.raw.glob("vm/*")):
        if not (directory / "meta.json").exists():
            continue
        meta = json.loads((directory / "meta.json").read_text())
        if meta["scenario"] not in ("network", "compute") or meta.get("contaminated_by_unexpected_worker_restart"):
            skipped.append({"run": directory.name, "reason": "recovery/loss or contamination; excluded from voluntary gate replay"})
            continue
        series = [s for r in rows(directory / "series.csv") if (s := snapshot(r)) is not None]
        series.sort(key=lambda s: s["At"])
        decisions = json.loads((directory / "decisions.json").read_text())
        executed = [d for d in decisions if d["executed"]]
        faults = rows(directory / "faults.csv")
        boundaries = sorted(float(f["t_local"]) for f in faults) + [meta["t_end"]]
        # At most one observation per voluntary decision, using the maximum
        # disruption reported by overlapping requests. Only unambiguous single-
        # move request intervals are admitted; the timestamp is completion.
        groups = {}
        for req in rows(directory / "requests.csv"):
            ms = number(req.get("transition_ms"))
            if req.get("ok") != "1" or not ms or ms <= 0:
                continue
            inside = [d for d in executed if float(req["t_start"]) <= timestamp(d["time"]) <= float(req["t_end"])]
            if len(inside) != 1 or inside[0]["reason"] == "recovery-or-initial":
                continue
            key = inside[0]["time"]
            prev = groups.get(key, {"At": 0, "Ms": 0})
            groups[key] = {"Run": directory.name, "Scenario": meta["scenario"],
                           "At": max(prev["At"], float(req["t_end"])), "Ms": max(prev["Ms"], ms)}
        observations.extend(groups.values())
        for d in decisions:
            if d["reason"] == "recovery-or-initial" or not d.get("from_splits") or d["current_bottleneck_ms"] <= 0:
                continue
            if len(d["from_splits"]) != 2 or len(d["to_splits"]) != 2:
                continue
            t = timestamp(d["time"])
            # One predictive snapshot per completed five-second block, from
            # the prior 60 seconds. Blocks are still correlated; no IID claim.
            blocks = {}
            for s in series:
                if t - 60 <= s["At"] < t - 5:
                    blocks[int((s["At"] - meta["t0"]) // 5)] = s
            future = [s for s in series if s["At"] >= t]
            predecessor = [s for s in series if s["At"] <= t]
            if predecessor:
                future.insert(0, predecessor[-1])
            cases.append({"Run": directory.name, "Scenario": meta["scenario"], "Reason": d["reason"], "At": t,
                          "Point": {"CurrentMs": d["current_bottleneck_ms"], "CandidateMs": d["optimal_bottleneck_ms"],
                                    "TransitionMs": 1740 + 128 * .3667 * 28},
                          "From": d["from_splits"], "To": d["to_splits"],
                          "Past": list(blocks.values()), "Future": future,
                          "PhaseEnd": next((b for b in boundaries if b > t), meta["t_end"]),
                          "RunEnd": meta["t_end"],
                          "Eligible": d["improvement_frac"] > .15 and d["reason"] != "cooldown" and meta["t0"] <= t < meta["t_end"]})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"Cases": cases, "Observations": observations}, separators=(",", ":"), allow_nan=False))
    (args.out.parent / "preparation.json").write_text(json.dumps({"candidates": len(cases), "eligible": sum(c["Eligible"] for c in cases),
        "transition_observations": len(observations), "excluded": skipped,
        "warning": "Candidate replay only; inferred flow costs, hypothetical remaining work, correlated history, endogenous future trace. No measured new-policy outcomes."}, indent=2))
    print(f"Prepared {len(cases)} recorded candidates, {len(observations)} voluntary transition observations")


if __name__ == "__main__":
    main()
