#!/usr/bin/env python3
"""Independent, read-only source audit and run-level paper analysis.

Run from any directory. Writes only beside this script. Python 3.10+ and
matplotlib are required. Does not rerun inference or overwrite old analyses.
"""
import csv
import gzip
import hashlib
import json
import statistics as st
import subprocess
import tarfile
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = HERE / "analysis"
OUT.mkdir(exist_ok=True)
VERIFIED = []


def load(p):
    return json.loads(p.read_text())


def rows(p):
    with p.open(newline="") as f:
        return list(csv.DictReader(f))


def write_csv(name, data):
    assert data, name
    with (OUT / name).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(data[0]))
        w.writeheader()
        w.writerows(data)


def verify_manifest(p):
    n = 0
    for line in p.read_text().splitlines():
        digest, rel = line.split("  ", 1)
        f = (p.parent / rel).resolve()
        assert f.is_relative_to(p.parent.resolve()), f"escaping manifest: {p}"
        assert hashlib.sha256(f.read_bytes()).hexdigest() == digest, f"hash mismatch: {f}"
        n += 1
    VERIFIED.append({"manifest": str(p.relative_to(ROOT)), "files_verified": n})


def quantile(v, q):
    v = sorted(v)
    return v[round(q * (len(v) - 1))] if v else None


def measure(meta_path, matrix):
    m = load(meta_path)
    rq = rows(meta_path.parent / "requests.csv")
    assert not m.get("contaminated_by_unexpected_worker_restart"), meta_path
    assert rq and all(r["ok"] in ("0", "1") for r in rq)
    good = [r for r in rq if r["ok"] == "1"]
    assert all(float(r["t_end"]) >= float(r["t_start"]) >= m["t0"] for r in rq)
    end = max(m["t_end"], *(float(r["t_end"]) for r in rq))
    seconds = end - m["t0"]
    obj = m.get("objective", "throughput")
    arm = ("auto-remaining" if m.get("remaining_work_aware") else "auto-fixed") if obj == "auto" else obj
    if matrix in ("vm", "baseline"):
        arm = m["policy"]
    dec = load(meta_path.parent / "decisions.json")
    voluntary = [d for d in dec if d["reason"] != "recovery-or-initial"]
    faults = rows(meta_path.parent / "faults.csv")
    fault_start = next(float(f["t_local"]) for f in faults if f["action"] == "on")
    fault_end = next(float(f["t_local"]) for f in faults if f["action"] == "off")
    assert m["t0"] <= fault_start < fault_end <= m["t_end"]
    fault_rows = [r for r in rq if fault_start <= float(r["t_end"]) < fault_end]
    # Completion attribution is explicit: this is not token timestamps or an
    # admission-cohort success rate. Whole-window metrics include final drain.
    return {"run": m["run"], "matrix": matrix, "scenario": m["scenario"], "arm": arm,
            "concurrency": m["concurrency"], "output_tokens": m["new_tokens"], "repeat": m["repeat"],
            "requests": len(rq), "successful": len(good), "failed": len(rq) - len(good),
            "duration_s": seconds, "throughput_tps": sum(int(r["tokens"]) for r in good) / seconds,
            "client_p50_ms": quantile([(float(r["t_end"]) - float(r["t_start"])) * 1000 for r in good], .5),
            "client_p95_ms": quantile([(float(r["t_end"]) - float(r["t_start"])) * 1000 for r in good], .95),
            "fault_completions": len(fault_rows), "fault_successful": sum(r["ok"] == "1" for r in fault_rows),
            "fault_completion_tps": sum(int(r["tokens"]) for r in fault_rows if r["ok"] == "1") / (fault_end - fault_start),
            "moves": sum(bool(d["executed"]) for d in voluntary), "rejections": sum(not d["executed"] for d in voluntary),
            "initial_layout": json.dumps([[a["start"], a["end"]] for a in m["initial_state"]["assignments"]]),
            "source_meta": str(meta_path.relative_to(ROOT))}


def main():
    objective = ROOT / "results/objective-aware-2026-10-04"
    vm = ROOT / "docs/data/azure-vm-2026-10-04"
    for p in [vm / "SHA256SUMS", objective / "provenance/SOURCE_ARCHIVES_SHA256SUMS"]:
        verify_manifest(p)
    all_runs = []
    for matrix, count in (("objective", 20), ("demand", 12)):
        d = objective / "raw" / matrix
        verify_manifest(d / "SOURCE_SHA256SUMS")
        metas = sorted(d.glob("runs/*/meta.json"))
        events, schedule = load(d / "events.json"), load(d / "schedule.json")
        assert len(metas) == len(events) == len(schedule) == count
        assert all(e["returncode"] == 0 for e in events)
        for m in metas:
            if matrix == "demand":
                assert load(m.parent / "correctness.json")["exact_match"]
            all_runs.append(measure(m, matrix))
    for matrix, p, count in (("vm", vm / "raw/vm", 30), ("baseline", vm / "raw/vm-single", 3)):
        metas = sorted(p.rglob("meta.json"))
        assert len(metas) == count
        all_runs.extend(measure(m, matrix) for m in metas)
    assert len({r["run"] for r in all_runs}) == len(all_runs) == 65
    groups = defaultdict(list)
    for r in all_runs:
        groups[r["matrix"], r["scenario"], r["concurrency"], r["output_tokens"], r["arm"]].append(r)
    summaries = []
    for (matrix, scenario, q, tokens, arm), rs in sorted(groups.items()):
        summaries.append({"matrix": matrix, "scenario": scenario, "concurrency": q, "output_tokens": tokens,
                          "arm": arm, "n": len(rs), "requests": sum(r["requests"] for r in rs),
                          "failed": sum(r["failed"] for r in rs),
                          "whole_window_tps_median": st.median(r["throughput_tps"] for r in rs),
                          "whole_window_tps_min": min(r["throughput_tps"] for r in rs),
                          "whole_window_tps_max": max(r["throughput_tps"] for r in rs),
                          "fault_completion_tps_median": st.median(r["fault_completion_tps"] for r in rs),
                          "client_p50_ms_median": st.median(r["client_p50_ms"] for r in rs),
                          "moves": sum(r["moves"] for r in rs), "rejections": sum(r["rejections"] for r in rs)})
    contrasts = []
    for key, rs in sorted(groups.items()):
        matrix, scenario, q, tokens, arm = key
        refs = ["throughput"] if arm in ("latency", "auto-fixed") else ["auto-fixed"] if arm == "auto-remaining" else []
        if matrix == "vm" and arm in ("gate", "hysteresis", "gate-force"):
            refs = ["static"] if arm == "hysteresis" else ["hysteresis"] if arm == "gate" else ["gate"]
        for ref in refs:
            bs = groups.get((matrix, scenario, q, tokens, ref), [])
            by_repeat = {r["repeat"]: r for r in bs}
            metric = "fault_completion_tps" if matrix == "vm" else "throughput_tps"
            differences = [r[metric] / by_repeat[r["repeat"]][metric] - 1 for r in rs
                           if r["repeat"] in by_repeat and by_repeat[r["repeat"]][metric] > 0]
            am, bm = st.median(r[metric] for r in rs), st.median(r[metric] for r in bs)
            contrasts.append({"matrix": matrix, "scenario": scenario, "concurrency": q, "output_tokens": tokens,
                              "arm": arm, "reference": ref, "metric": metric,
                              "ratio_of_medians_pct": 100 * (am / bm - 1) if bm else None,
                              "paired_n": len(differences), "paired_mean_pct": 100 * st.mean(differences) if differences else None,
                              "paired_min_pct": 100 * min(differences) if differences else None,
                              "paired_max_pct": 100 * max(differences) if differences else None})
    # Check retained synthetic request data independently of aggregate files.
    ablation = ROOT / "docs/data/paper-ablations-2026-10-04"
    for entry in load(ablation / "raw-data-manifest.json"):
        f = ablation / entry["path"]
        compressed = f.read_bytes()
        decoded = gzip.decompress(compressed)
        assert hashlib.sha256(compressed).hexdigest() == entry["compressed_sha256"]
        assert hashlib.sha256(decoded).hexdigest() == entry["decoded_sha256"]
        assert len(decoded.splitlines()) == entry["records"]
        directory = f.parent
        calibration = directory.name == "calibration-results"
        keys = ("service_ms", "concurrency", "instrumented" if calibration else "mode", "repeat")
        window_data = defaultdict(list)
        for line in decoded.splitlines():
            r = json.loads(line)
            window_data[tuple(r[k] for k in keys)].append(r)
        windows = load(directory / "windows.json")
        assert len(windows) == (24 if calibration else 54) == len(window_data)
        for w in windows:
            rq = window_data[tuple(w[k] for k in keys)]
            assert len(rq) == w["requests"]
            assert sum(not r["ok"] for r in rq) == w["failures"] == 0
            for metric in ("rpc_ms", "compute_ms", "residual_ms"):
                assert abs(st.mean(r[metric] for r in rq) - w["mean_" + metric]) < 1e-8
        VERIFIED.append({"manifest": str(f.relative_to(ROOT)), "records_verified": entry["records"]})
    costs = rows(ablation / "decision-results/cost-model.csv")
    policy = rows(ablation / "decision-results/policy.csv")
    assert len(costs) == 240 and len(policy) == 18000
    cost_example = [r for r in costs if r["context"] == "2048" and r["speed_b"] == "1" and r["link_ms"] == "0.5"]
    synthetic_summary = {"queue_windows_verified": 54, "calibration_windows_verified": 24,
                         "analytical_cost_rows": len(costs), "analytical_policy_rows": len(policy),
                         "context_2048_cost_example": cost_example}
    (OUT / "ablation-audit.json").write_text(json.dumps(synthetic_summary, indent=2) + "\n")
    replay = [json.loads(line) for line in (vm / "replay/replay-results.jsonl").read_text().splitlines()]
    inp = load(vm / "replay/input.json")
    assert len(inp["Cases"]) == 71 and len(replay) == 710
    archives = []
    for archive in sorted((objective / "provenance").glob("*-tested-source.tgz")):
        with tarfile.open(archive) as t:
            for member in t.getmembers():
                if member.isfile() and member.name in ("internal/controller/workload.go", "internal/partition/partition.go", "worker/router.py"):
                    data = t.extractfile(member).read()
                    current = ROOT / member.name
                    archives.append({"archive": archive.name, "member": member.name,
                                     "sha256": hashlib.sha256(data).hexdigest(),
                                     "matches_current": current.exists() and current.read_bytes() == data})
    write_csv("per-run.csv", all_runs)
    write_csv("summary.csv", summaries)
    write_csv("contrasts.csv", contrasts)
    tables(summaries)
    audit = {"scope": "Exploratory; run-level summaries; no significance or superiority inference",
             "source_commit_at_analysis": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
             "manifests": VERIFIED, "real_model_runs": len(all_runs),
             "real_model_requests": sum(r["requests"] for r in all_runs),
             "real_model_failed_requests": sum(r["failed"] for r in all_runs),
             "objective_and_demand_requests": sum(r["requests"] for r in all_runs if r["matrix"] in ("objective", "demand")),
             "live_demand_correctness_checks": 12, "replay_candidates": 71, "analytical_replay_rows": 710,
             "tested_source_comparison": archives,
             "experiment_registry": load(ROOT / "results/experiments.json")}
    (OUT / "audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    # Assert independent recomputation agrees with existing objective summaries.
    old = rows(objective / "analysis/summary.csv")
    for s in old:
        ours = next(r for r in summaries if (r["matrix"], r["scenario"], r["concurrency"], r["arm"]) ==
                    (s["matrix"], s["scenario"], int(s["concurrency"]), s["arm"]))
        assert abs(ours["whole_window_tps_median"] - float(s["median_tokens_per_second"])) < 1e-10
    for p in (vm / "raw/vm/runs_summary.csv", vm / "raw/vm-single/runs_summary.csv"):
        for old_run in rows(p):
            ours = next(r for r in all_runs if r["run"] == old_run["run"])
            assert abs(ours["fault_completion_tps"] - float(old_run["fault_throughput"])) < 1e-10
    figure(groups)
    print(json.dumps({k: audit[k] for k in ("real_model_runs", "real_model_requests", "real_model_failed_requests", "live_demand_correctness_checks")}, indent=2))


def figure(groups):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 9, "pdf.fonttype": 42, "svg.fonttype": "none"})
    fig, axs = plt.subplots(1, 3, figsize=(10.8, 3.3), constrained_layout=True)
    panels = [("objective", "stable", 2, 32, ["latency", "throughput"], "Stable, Q=2, 32 output tokens"),
              ("objective", "network", 1, 32, ["latency", "throughput"], "+120 ms, Q=1, 32 output tokens"),
              ("demand", "stable", 2, 64, ["throughput", "auto-fixed", "auto-remaining"], "Stable, Q=2, 64 output tokens")]
    for ax, (matrix, sc, q, tok, arms, title) in zip(axs, panels):
        for i, arm in enumerate(arms):
            vals = [r["throughput_tps"] for r in groups[matrix, sc, q, tok, arm]]
            ax.bar(i, st.median(vals), color="#427c9a" if arm == "throughput" else "#c48649", alpha=.7)
            ax.scatter([i + (j - (len(vals) - 1) / 2) * .08 for j in range(len(vals))], vals, color="black", s=17, zorder=5)
        ax.set_xticks(range(len(arms)), [a.replace("-", "\n") for a in arms])
        ax.set_title(title)
        ax.set_ylabel("Output tokens/s (including drain)")
        ax.set_ylim(0, 9)
        ax.spines[["top", "right"]].set_visible(False)
    for ext in ("pdf", "svg", "png"):
        fig.savefig(HERE / f"objective-results.{ext}", dpi=200)
    plt.close(fig)


def tables(summaries):
    objective = [r for r in summaries if r["matrix"] in ("objective", "demand")]
    adaptation = [r for r in summaries if r["matrix"] in ("vm", "baseline")]
    for name, data, caption in (
        ("objective-table.tex", objective,
         "Whole-run objective and demand results. Q denotes closed-loop concurrency; N is requested output tokens. Medians use runs as units; drain is included."),
        ("adaptation-table.tex", adaptation,
         "Adaptation and separate baseline results. Phase throughput attributes tokens at completion between logged on/off times. Whole-run throughput includes drain. Failures are retained.")):
        lines = [r"\begin{table}[htbp]", r"\centering\small", r"\caption{" + caption + "}"]
        if name.startswith("objective"):
            lines += [r"\begin{tabular}{lllrrrr}", r"\toprule", r"Matrix & Condition & Arm & Q & N & Runs & Tokens/s \\", r"\midrule"]
            for r in data:
                lines.append(f'{r["matrix"]} & {r["scenario"]} & {r["arm"]} & {r["concurrency"]} & {r["output_tokens"]} & {r["n"]} & {r["whole_window_tps_median"]:.3f} ' + r"\\")
        else:
            lines += [r"\begin{tabular}{llrrrr}", r"\toprule", r"Condition & Arm & Runs & Phase TPS & Whole TPS & Failures \\", r"\midrule"]
            for r in data:
                lines.append(f'{r["scenario"] if r["matrix"]=="vm" else "single-device"} & {r["arm"]} & {r["n"]} & {r["fault_completion_tps_median"]:.3f} & {r["whole_window_tps_median"]:.3f} & {r["failed"]} ' + r"\\")
        lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
        (HERE / name).write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
