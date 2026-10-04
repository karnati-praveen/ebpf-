#!/usr/bin/env python3
"""Descriptive run-level analysis; include transition time and request drain.

Router TTFT is internal prefill time, not streamed client TTFT. Requests are
correlated within runs; comparisons use per-run observations and repeat pairs.
"""
import argparse
import collections
import csv
import json
import statistics
from pathlib import Path


def percentile(values, q):
    values = sorted(values)
    return values[min(len(values)-1, round(q*(len(values)-1)))] if values else None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("experiment", type=Path)
    args = ap.parse_args()
    root = args.experiment
    out = root / "analysis"; out.mkdir(parents=True, exist_ok=True)
    runs, excluded = [], []
    for matrix in ("objective", "demand"):
        for meta_file in sorted((root / "raw" / matrix).glob("runs/*/meta.json")):
            d = meta_file.parent
            meta = json.loads(meta_file.read_text())
            with (d / "requests.csv").open() as f:
                requests = list(csv.DictReader(f))
            if meta.get("contaminated_by_unexpected_worker_restart"):
                excluded.append({"run":d.name,"reason":"unexpected worker restart"});continue
            successful = [r for r in requests if r["ok"] == "1"]
            end = max([meta["t_end"]] + [float(r["t_end"]) for r in requests])
            window = end-meta["t0"]
            decisions = json.loads((d / "decisions.json").read_text())
            voluntary = [x for x in decisions if x["reason"] != "recovery-or-initial"]
            objective = meta.get("objective", "throughput")
            arm = "auto-remaining" if objective == "auto" and meta.get("remaining_work_aware") else "auto-fixed" if objective=="auto" else objective
            client_latency = [(float(r["t_end"])-float(r["t_start"]))*1000 for r in successful]
            with (d / "series.csv").open() as f:
                series = list(csv.DictReader(f))
            budgets=[]
            for r in series:
                if r.get("workload_json"):
                    workload=json.loads(r["workload_json"])
                    if workload is not None:budgets.append(workload["remaining_tokens"])
            runs.append({"run":d.name,"matrix":matrix,"arm":arm,"scenario":meta["scenario"],
                "concurrency":meta["concurrency"],"repeat":meta["repeat"],"new_tokens":meta["new_tokens"],
                "requests":len(requests),"successful":len(successful),"errors":len(requests)-len(successful),
                "window_including_drain_s":window,"tokens_per_second_including_drain":sum(int(r["tokens"]) for r in successful)/window,
                "client_completion_p50_ms":percentile(client_latency,.5),"client_completion_p95_ms":percentile(client_latency,.95),
                "internal_ttft_p50_ms":percentile([float(r["ttft_ms"]) for r in successful],.5),
                "voluntary_moves":sum(x["executed"] for x in voluntary),"voluntary_rejections":sum(not x["executed"] for x in voluntary),
                "gate_horizons_s":json.dumps([x["horizon_s"] for x in voluntary if "horizon_s" in x]),
                "observed_remaining_min":min(budgets) if budgets else None,"observed_remaining_max":max(budgets) if budgets else None,
                "initial_layout":json.dumps([[a["node"],a["start"],a["end"]] for a in meta["initial_state"]["assignments"]]),
                "correctness_verified":json.loads((d/"correctness.json").read_text())["exact_match"] if (d/"correctness.json").exists() else None})
    if not runs:
        raise SystemExit("No completed runs")
    with (out / "per-run.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(runs[0]));w.writeheader();w.writerows(runs)
    groups=collections.defaultdict(list)
    for r in runs:groups[r["matrix"],r["scenario"],r["concurrency"],r["new_tokens"],r["arm"]].append(r)
    summary=[]
    for (matrix,sc,c,tokens,arm),rs in sorted(groups.items()):
        summary.append({"matrix":matrix,"scenario":sc,"concurrency":c,"new_tokens":tokens,"arm":arm,"repeats":len(rs),
            "median_tokens_per_second":statistics.median(r["tokens_per_second_including_drain"] for r in rs),
            "median_client_p50_ms":statistics.median(r["client_completion_p50_ms"] for r in rs),
            "median_client_p95_ms":statistics.median(r["client_completion_p95_ms"] for r in rs),
            "requests":sum(r["requests"] for r in rs),"errors":sum(r["errors"] for r in rs),
            "voluntary_moves":sum(r["voluntary_moves"] for r in rs),"voluntary_rejections":sum(r["voluntary_rejections"] for r in rs)})
    with (out / "summary.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(summary[0]));w.writeheader();w.writerows(summary)
    pairs=[]
    for (matrix,sc,c,tokens,arm),rs in sorted(groups.items()):
        ref="throughput" if arm in ("latency","auto-fixed") else "auto-fixed" if arm=="auto-remaining" else None
        if not ref:continue
        reference={r["repeat"]:r for r in groups.get((matrix,sc,c,tokens,ref),[])}
        for r in rs:
            if r["repeat"] not in reference:continue
            baseline=reference[r["repeat"]]
            pairs.append({"matrix":matrix,"scenario":sc,"concurrency":c,"new_tokens":tokens,"arm":arm,"reference":ref,
                "repeat":r["repeat"],"throughput_relative_change":r["tokens_per_second_including_drain"]/baseline["tokens_per_second_including_drain"]-1,
                "client_p50_relative_change":r["client_completion_p50_ms"]/baseline["client_completion_p50_ms"]-1})
    (out/"paired-comparisons.json").write_text(json.dumps(pairs,indent=2))
    (out/"excluded.json").write_text(json.dumps(excluded,indent=2))
    (out/"status.json").write_text(json.dumps({"completed_runs":len(runs),"excluded":len(excluded),
        "expected_objective_runs":20,"expected_demand_runs":12,"total_requests":sum(r["requests"] for r in runs),
        "failed_requests":sum(r["errors"] for r in runs),"scope":"Exploratory run-level descriptive analysis; no significance or novelty claim"},indent=2))
    print((out/"summary.csv").read_text())


if __name__ == "__main__":
    main()
