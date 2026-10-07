#!/usr/bin/env python3
"""Run-level analysis of local_publication.py; never pool requests as repeats."""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import random
import statistics as st


def percentile(values, p):
    values = sorted(values)
    index = (len(values)-1)*p
    low = int(index)
    high = min(low+1, len(values)-1)
    return values[low] + (values[high]-values[low])*(index-low)


def bootstrap(values, seed=20261007):
    if len(values) < 2:
        return [None, None]
    rng = random.Random(seed)
    samples = [st.mean(rng.choices(values, k=len(values))) for _ in range(10000)]
    return [percentile(samples, .025), percentile(samples, .975)]


def analyze(directory):
    manifest = json.loads((directory/"manifest.json").read_text())
    runs = [json.loads(line) for line in (directory/"runs.jsonl").read_text().splitlines()]
    keys = [(r["mode"], r["repetition"], r["context"], r["concurrency"]) for r in runs]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate run keys")
    expected = {(b["mode"], b["repetition"], c, q) for b in manifest["schedule"] for c, q in b["conditions"]}
    if set(keys)-expected:
        raise ValueError("unscheduled runs")
    groups = defaultdict(list)
    for r in runs:
        groups[r["mode"], r["context"], r["concurrency"]].append(r)
    summaries, contrasts = [], []
    contrast_arm = manifest.get("contrast_arm", "pipeline-2x1t")
    contrast_baselines = manifest.get("contrast_baselines", ["replicas-2x1t", "unsplit-2t", "unsplit-1t"])
    for (mode, context, q), rows in sorted(groups.items()):
        throughput = [r["whole_run_tps"] for r in rows]
        timing = [t for r in rows for request in r["requests"]
                  for t in request.get("reply", {}).get("decode_rpc_timing", {}).values()]
        residual = sum(t["residual_ms"] for t in timing)
        queue = sum(t["queue_ms"] for t in timing)
        summaries.append({"mode": mode, "context": context, "concurrency": q, "n_runs": len(rows),
            "requests": sum(len(r["requests"]) for r in rows), "failures": sum(r["failures"] for r in rows),
            "reference_mismatches": sum(r.get("reference_mismatches", 0) for r in rows),
            "mean_tps": st.mean(throughput), "median_tps": st.median(throughput),
            "mean_tps_ci95": bootstrap(throughput), "min_tps": min(throughput), "max_tps": max(throughput),
            "median_run_client_ms": st.median(r["median_client_duration_ms"] for r in rows),
            "median_run_ttft_ms": st.median(r["median_ttft_ms"] for r in rows if r["median_ttft_ms"] is not None) if any(r["median_ttft_ms"] is not None for r in rows) else None,
            "decode_queue_ms": queue, "decode_residual_ms": residual,
            "decode_queue_fraction_of_residual": queue/residual if residual else None})
        if mode != contrast_arm:
            continue
        for baseline in contrast_baselines:
            refs = {r["repetition"]: r for r in groups.get((baseline, context, q), [])}
            paired = [(r, refs[r["repetition"]]) for r in rows if r["repetition"] in refs]
            differences = [100*(r["whole_run_tps"]/b["whole_run_tps"]-1) for r, b in paired if b["whole_run_tps"] > 0]
            if not differences:
                continue
            interval = bootstrap(differences)
            contrasts.append({"context": context, "concurrency": q, "arm": mode, "baseline": baseline,
                "paired_n": len(differences), "paired_mean_tps_change_pct": st.mean(differences),
                "paired_mean_change_ci95": interval,
                "paired_failures": sum(r["failures"]+b["failures"] for r, b in paired),
                "interpretation": "descriptive paired block bootstrap; local host only; no equivalence claim"})
    report = {"evidence_type": manifest["evidence_type"], "completed_runs": len(runs),
        "expected_runs": len(expected), "missing_runs": sorted(expected-set(keys)),
        "total_requests": sum(len(r["requests"]) for r in runs), "failures": sum(r["failures"] for r in runs),
        "reference_mismatches": sum(r.get("reference_mismatches", 0) for r in runs),
        "analysis_unit": "independent restart block/repetition; requests within a run are not repetitions",
        "uncertainty": "percentile paired block bootstrap of mean percentage changes, 10000 resamples; unadjusted descriptive intervals",
        "raw_sha256": {name: hashlib.sha256((directory/name).read_bytes()).hexdigest() for name in ("manifest.json", "reference.json", "runs.jsonl")},
        "summaries": summaries, "contrasts": contrasts}
    (directory/"analysis.json").write_text(json.dumps(report, indent=2)+"\n")
    for name, rows in (("summary.csv", summaries), ("contrasts.csv", contrasts)):
        if not rows:
            continue
        with (directory/name).open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    optimized = "engine_commit" in manifest
    description = ("This separately timed campaign uses a pinned llama.cpp server, F32 weights converted from the same Qwen3 checkpoint, F32 KV cache, two compute threads and eight continuous-batching slots. Prompts and reference outputs come from the completed runtime matrix. It is a practical serving alternative rather than a planner ablation; numerical output mismatches are reported explicitly. No paired timing comparison with the earlier runtime campaign is justified."
        if optimized else "Each serving arm uses FP32, cached Qwen3-0.6B, fixed greedy prompts and the same HTTP/gRPC runtime. Inference workers are restricted to two CPUs; the one-thread unsplit arm leaves one unused. The pipeline layout is fixed at 18/10. Replicas use whole-request first-available dispatch. Coordination has the same remaining host CPUs in every arm.")
    limits = ("These are single-host loopback measurements, separately timed from the runtime matrix. Each repetition restarts the engine and randomizes conditions. They do not measure physical heterogeneous devices or adaptive-controller superiority."
        if optimized else "These are single-host loopback measurements. They do not measure Azure links, physical heterogeneous devices, an optimized serving engine, or adaptive-controller superiority. Repetition blocks restart workers and randomize arm order. Intervals resample blocks; request counts do not increase the independent sample size.")
    if "method_description" in manifest:
        description = manifest["method_description"]
        limits = manifest["scope"] + ". Repetition indices are the analysis blocks; intervals are descriptive and unadjusted."
    lines = ["# Local real-model baseline results", "",
        f"Completed {len(runs)}/{len(expected)} runs; {report['total_requests']} requests; {report['failures']} failures. Separate-engine reference mismatches: {report['reference_mismatches']}.", "",
        description, "", limits, "",
        "| Arm | Context | Q | Runs | Median TPS | Failures |", "|---|---:|---:|---:|---:|---:|"]
    for r in summaries:
        lines.append(f"| {r['mode']} | {r['context']} | {r['concurrency']} | {r['n_runs']} | {r['median_tps']:.3f} | {r['failures']} |")
    if contrasts:
        lines += ["", f"{contrast_arm} percentage change against each baseline (paired mean, descriptive 95% interval):", "",
              "| Baseline | Context | Q | Pairs | Change | Interval |", "|---|---:|---:|---:|---:|---|"]
    for r in contrasts:
        lo, hi = r["paired_mean_change_ci95"]
        interval = "insufficient repeats" if lo is None else f"[{lo:.1f}, {hi:.1f}]%"
        lines.append(f"| {r['baseline']} | {r['context']} | {r['concurrency']} | {r['paired_n']} | {r['paired_mean_tps_change_pct']:.1f}% | {interval} |")
    lines += ["", "`analysis.json` retains queue/compute/residual decomposition and uncertainty. The corrected residual includes serialization, dispatch, transport and measurement overhead; it is not pure network latency. Historical synthetic 99.2% queueing claims are not transferred to these measurements."]
    (directory/"REPORT.md").write_text("\n".join(lines)+"\n")
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("directory", type=Path)
    args = ap.parse_args()
    report = analyze(args.directory)
    print(f"{report['completed_runs']}/{report['expected_runs']} runs, {report['total_requests']} requests, {report['failures']} failures")


if __name__ == "__main__":
    main()
