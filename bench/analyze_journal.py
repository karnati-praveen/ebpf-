#!/usr/bin/env python3
"""Analyze tagged journal runs without inventing unavailable measurements."""

import csv
import glob
import json
import math
import os
import statistics
from collections import Counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
DOCS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
DURATIONS = {"netem": {"clean": 20, "fault": 60, "recover": 20},
             "failure": {"clean": 20, "fault": 60, "recover": 60}}
TOKENS = 8


def read_csv(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def fnum(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def pctile(values, fraction):
    values = sorted(values)
    return values[int(fraction * (len(values) - 1))] if values else None


def mean(values):
    return statistics.fmean(values) if values else None


def layout(row):
    return row.get("layout", "")


def target_ip(evidence, node):
    assignments = evidence.get("controller_before", {}).get("assignments", [])
    worker = next((a["worker"] for a in assignments if a.get("node") == node), None)
    for stage in evidence.get("pipeline_before", {}).get("stages", []):
        if stage.get("name") == worker:
            return stage["addr"].rsplit(":", 1)[0]
    return None


def flow_srtt(row, dst):
    try:
        flows = json.loads(row.get("flows_json") or "[]")
    except json.JSONDecodeError:
        return None
    values = [fnum(f.get("srtt_ms")) for f in flows
              if f.get("port") == 50051 and (not dst or f.get("dst") == dst)]
    return max((v for v in values if v is not None and v > 0), default=None)


def summarize(prefix):
    tag = os.path.basename(prefix)
    scenario = "failure" if tag.startswith("failure_") else "netem"
    mode = next(m for m in ("profileonly", "dynamic", "static") if f"_{m}_" in tag)
    reqs, series = read_csv(prefix + "_requests.csv"), read_csv(prefix + "_series.csv")
    phases = {r["phase"]: float(r["t"]) for r in read_csv(prefix + "_phases.csv")}
    with open(prefix + "_evidence.json") as f:
        evidence = json.load(f)
    node = "kubeedgeinfer-worker3" if scenario == "failure" else "kubeedgeinfer-worker2"
    dst = target_ip(evidence, node)
    baseline_rows = [r for r in series if phases["clean"] <= float(r["t"]) < phases["fault"]]
    baseline_layout = Counter(layout(r) for r in baseline_rows if layout(r)).most_common(1)[0][0]
    fault_change = next((float(r["t"]) - phases["fault"] for r in series
                         if phases["fault"] <= float(r["t"]) < phases["recover"] and layout(r)
                         and layout(r) != baseline_layout), None)
    layout_restored = next((float(r["t"]) for r in series
                            if float(r["t"]) >= phases["recover"]
                            and layout(r) == baseline_layout), None)
    recovery_request = next((float(r["t"]) for r in reqs
                             if r.get("ok") == "1" and float(r["t"]) >= phases["recover"]
                             and (layout_restored is None or float(r["t"]) >= layout_restored)), None)
    recovery = (recovery_request - phases["recover"]
                if layout_restored is not None and recovery_request is not None else None)
    generations = [r.get("ctrl_generation") for r in series if r.get("ctrl_generation")]
    transitions = sum(a != b for a, b in zip(generations, generations[1:]))
    out = []
    for phase in ("clean", "fault", "recover"):
        start, duration = phases[phase], DURATIONS[scenario][phase]
        rr = [r for r in reqs if start <= float(r["t"]) < start + duration]
        ok = [r for r in rr if r.get("ok") == "1"]
        ss = [r for r in series if start <= float(r["t"]) < start + duration]
        tps = [fnum(r.get("tokens_per_sec")) for r in ok]
        ttft = [fnum(r.get("ttft_ms")) for r in ok]
        idle = [fnum(r.get("worst_idle")) for r in ss]
        srtt = [flow_srtt(r, dst) for r in ss]
        layouts = list(dict.fromkeys(layout(r) for r in ss if layout(r)))
        out.append({
            "tag": tag, "scenario": scenario, "mode": mode, "phase": phase,
            "requests_ok": len(ok), "requests_total": len(rr),
            "success_rate_pct": 100 * len(ok) / len(rr) if rr else None,
            "tokens_per_sec_mean": mean([v for v in tps if v is not None]),
            "delivered_tokens_per_sec": len(ok) * TOKENS / duration,
            "ttft_ms_mean": mean([v for v in ttft if v is not None]),
            "ttft_ms_p95": pctile([v for v in ttft if v is not None], .95),
            "worst_idle_mean": mean([v for v in idle if v is not None]),
            "replay_count": sum(int(float(r.get("replays") or 0)) for r in ok),
            "layouts": " -> ".join(layouts), "generation_transitions": transitions,
            "fault_to_layout_change_s": fault_change,
            "recovery_time_s": recovery if phase == "recover" else None,
            "recovery_right_censored_s": (duration if phase == "recover" and recovery is None else None),
            "target_srtt_ms_mean": mean([v for v in srtt if v is not None]),
        })
    return out, reqs, series, phases


def stats(values):
    values = [v for v in values if v is not None]
    if not values:
        return {"n": 0}
    result = {"n": len(values), "mean": mean(values), "median": statistics.median(values),
              "stddev": statistics.stdev(values) if len(values) > 1 else None,
              "ci95_low": None, "ci95_high": None}
    if len(values) > 1:
        tcrit = 4.303 if len(values) == 3 else 1.96
        half = tcrit * result["stddev"] / math.sqrt(len(values))
        result["ci95_low"], result["ci95_high"] = result["mean"] - half, result["mean"] + half
    return result


def aggregate(rows):
    metrics = ("success_rate_pct", "tokens_per_sec_mean", "delivered_tokens_per_sec",
               "ttft_ms_mean", "ttft_ms_p95", "worst_idle_mean", "replay_count",
               "generation_transitions", "target_srtt_ms_mean")
    groups = []
    for scenario in sorted({r["scenario"] for r in rows}):
        for phase in ("clean", "fault", "recover"):
            for mode in ("dynamic", "static", "profileonly"):
                selected = [r for r in rows if (r["scenario"], r["phase"], r["mode"]) ==
                            (scenario, phase, mode)]
                if selected:
                    groups.append({"scenario": scenario, "phase": phase, "mode": mode,
                                   "metrics": {m: stats([r[m] for r in selected]) for m in metrics}})
    comparisons = []
    for scenario in sorted({r["scenario"] for r in rows}):
        for phase in ("clean", "fault", "recover"):
            for other in ("static", "profileonly"):
                d = [r for r in rows if (r["scenario"], r["phase"], r["mode"]) == (scenario, phase, "dynamic")]
                o = [r for r in rows if (r["scenario"], r["phase"], r["mode"]) == (scenario, phase, other)]
                if d and o:
                    vals = {}
                    for m in metrics:
                        dm, om = mean([r[m] for r in d if r[m] is not None]), mean([r[m] for r in o if r[m] is not None])
                        vals[m] = (dm - om) / om * 100 if dm is not None and om not in (None, 0) else None
                    comparisons.append({"scenario": scenario, "phase": phase,
                                        "comparison": f"dynamic_vs_{other}_pct", "metrics": vals})
    return groups, comparisons


def plot(runs, path):
    fig, axes = plt.subplots(len(runs), 1, figsize=(11, 2.5 * len(runs)), squeeze=False)
    for ax, (tag, series, phases) in zip((r[0] for r in axes), runs):
        x = [float(r["t"]) - phases["clean"] for r in series]
        y = [fnum(r.get("worst_idle")) for r in series]
        ax.plot(x, y, linewidth=1)
        for phase in ("fault", "recover"):
            ax.axvline(phases[phase] - phases["clean"], color="black", linestyle="--", linewidth=.8)
        ax.set_ylim(bottom=0); ax.set_ylabel("worst idle"); ax.set_title(tag, fontsize=8); ax.grid(alpha=.2)
    axes[-1][0].set_xlabel("seconds since clean phase start")
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def plot_real_srtt(rows, path):
    rows = [r for r in rows if r["scenario"] == "netem"]
    phases, modes = ("clean", "fault", "recover"), ("dynamic", "static", "profileonly")
    colors = {"dynamic": "#2563eb", "static": "#dc2626", "profileonly": "#16a34a"}
    fig, ax = plt.subplots(figsize=(9, 5))
    width = .23
    for mi, mode in enumerate(modes):
        xpos, values = [], []
        for pi, phase in enumerate(phases):
            selected = [r["target_srtt_ms_mean"] for r in rows
                        if r["mode"] == mode and r["phase"] == phase]
            x = pi + (mi - 1) * width
            xpos.append(x); values.append(mean(selected))
            ax.scatter([x] * len(selected), selected, color="black", s=18, zorder=3)
        ax.bar(xpos, values, width, color=colors[mode], alpha=.78, label=mode)
    ax.set_xticks(range(3), phases); ax.set_ylim(bottom=0)
    ax.set_ylabel("real eBPF target-flow sRTT (ms)")
    ax.set_title("Real kernel netem measurement (bars: n=3 mean; dots: runs)")
    ax.grid(axis="y", alpha=.25); ax.legend(); fig.tight_layout()
    fig.savefig(path, dpi=150); plt.close(fig)


def main():
    prefixes = sorted(p.removesuffix("_phases.csv") for p in glob.glob(
        os.path.join(RESULTS, "*_4cpu_20260913_*_r1_phases.csv") + ""))
    prefixes += sorted(p.removesuffix("_phases.csv") for p in glob.glob(
        os.path.join(RESULTS, "netem_4cpu_20260913_*_r[23]_phases.csv")))
    rows, plots = [], []
    for prefix in prefixes:
        run_rows, _, series, phases = summarize(prefix); rows.extend(run_rows)
        plots.append((os.path.basename(prefix), series, phases))
    fields = list(rows[0])
    for path in (os.path.join(RESULTS, "journal_4cpu_per_run.csv"),
                 os.path.join(DOCS, "journal-benchmark-4cpu-2026-09-13.csv")):
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
            w.writeheader(); w.writerows(rows)
    groups, comparisons = aggregate(rows)
    with open(os.path.join(RESULTS, "journal_4cpu_summary.json"), "w") as f:
        json.dump({"runs": rows, "aggregates": groups, "comparisons": comparisons}, f, indent=2)
    with open(os.path.join(DOCS, "journal-benchmark-4cpu-2026-09-13.json"), "w") as f:
        json.dump({"runs": rows, "aggregates": groups, "comparisons": comparisons}, f, indent=2)
    plot(plots, os.path.join(RESULTS, "journal_4cpu_idle_timeseries.png"))
    plot_real_srtt(rows, os.path.join(RESULTS, "journal_4cpu_real_ebpf_srtt.png"))
    print(f"analyzed {len(prefixes)} runs into {len(rows)} phase rows")


if __name__ == "__main__":
    main()
