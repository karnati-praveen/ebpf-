#!/usr/bin/env python3
"""Summarize and plot uniquely tagged thermal benchmark repetitions."""

import argparse
import csv
import glob
import json
import os
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


PHASE_SECONDS = {"clean": 20.0, "fault": 60.0, "recover": 20.0}


def read_csv(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def normalize_layout(layout):
    return "|".join(part.rsplit(":", 1)[-1] for part in layout.split("|") if part)


def in_window(row, start, duration):
    t = float(row["t"])
    return start <= t < start + duration


def mean(values):
    return statistics.fmean(values) if values else None


def summarize_run(prefix):
    requests = read_csv(prefix + "_requests.csv")
    series = read_csv(prefix + "_series.csv")
    phases = {r["phase"]: float(r["t"]) for r in read_csv(prefix + "_phases.csv")}
    tag = os.path.basename(prefix)
    mode = "dynamic" if "_dynamic_" in tag else "static"

    clean_series = [r for r in series if in_window(r, phases["clean"], PHASE_SECONDS["clean"])]
    clean_layout = normalize_layout(clean_series[0]["layout"]) if clean_series else ""
    recovery_time = None
    for row in series:
        if not in_window(row, phases["recover"], PHASE_SECONDS["recover"]):
            continue
        speeds = dict(item.rsplit(":", 1) for item in row["speeds"].split("|") if item)
        if (normalize_layout(row["layout"]) == clean_layout and
                speeds.get("kubeedgeinfer-worker2") == "1.00"):
            recovery_time = float(row["t"]) - phases["recover"]
            break

    rows = []
    for phase, duration in PHASE_SECONDS.items():
        req = [r for r in requests if in_window(r, phases[phase], duration)]
        ok = [r for r in req if r["ok"] == "1"]
        samples = [r for r in series if in_window(r, phases[phase], duration)]
        layouts = []
        for row in samples:
            layout = normalize_layout(row.get("layout", ""))
            if layout and layout not in layouts:
                layouts.append(layout)
        rows.append({
            "tag": tag,
            "mode": mode,
            "phase": phase,
            "requests_ok": len(ok),
            "requests_total": len(req),
            "success_rate_pct": 100.0 * len(ok) / len(req) if req else None,
            "tokens_per_sec_mean": mean([float(r["tokens_per_sec"]) for r in ok]),
            "ttft_ms_mean": mean([float(r["ttft_ms"]) for r in ok]),
            "worst_idle_mean": mean([float(r["worst_idle"]) for r in samples
                                      if r.get("worst_idle") not in (None, "")]),
            "layouts": " -> ".join(layouts),
            "recovery_time_s": recovery_time if phase == "recover" else None,
            "recovery_censored_s": (PHASE_SECONDS["recover"]
                                      if phase == "recover" and recovery_time is None
                                      else None),
        })
    return rows


def aggregate(rows):
    metrics = ["success_rate_pct", "tokens_per_sec_mean", "ttft_ms_mean",
               "worst_idle_mean"]
    out = []
    for phase in PHASE_SECONDS:
        modes = {}
        for mode in ("dynamic", "static"):
            selected = [r for r in rows if r["phase"] == phase and r["mode"] == mode]
            modes[mode] = {metric: mean([r[metric] for r in selected
                                         if r[metric] is not None]) for metric in metrics}
        delta = {}
        for metric in metrics:
            dynamic, static = modes["dynamic"][metric], modes["static"][metric]
            delta[metric] = ((dynamic - static) / static * 100.0
                             if dynamic is not None and static not in (None, 0) else None)
        out.append({"phase": phase, "dynamic": modes["dynamic"],
                    "static": modes["static"], "dynamic_vs_static_pct": delta})
    return out


def write_outputs(results_dir, name, rows, aggregate_rows):
    csv_path = os.path.join(results_dir, name + ".csv")
    fields = list(rows[0])
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    json_path = os.path.join(results_dir, name + ".json")
    with open(json_path, "w") as f:
        json.dump({"phase_seconds": PHASE_SECONDS, "runs": rows,
                   "aggregate": aggregate_rows}, f, indent=2)

    metrics = [("tokens_per_sec_mean", "Mean tokens/sec"),
               ("ttft_ms_mean", "Mean TTFT (ms)"),
               ("worst_idle_mean", "Mean worst-stage idle fraction")]
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    phases = list(PHASE_SECONDS)
    x = list(range(len(phases)))
    width = 0.34
    colors = {"dynamic": "#2563eb", "static": "#dc2626"}
    for ax, (metric, label) in zip(axes, metrics):
        for offset, mode in ((-width / 2, "dynamic"), (width / 2, "static")):
            values = [next(a[mode][metric] for a in aggregate_rows if a["phase"] == p)
                      for p in phases]
            ax.bar([v + offset for v in x], values, width, label=mode,
                   color=colors[mode], alpha=0.8)
            for xi, phase in zip(x, phases):
                points = [r[metric] for r in rows
                          if r["mode"] == mode and r["phase"] == phase]
                ax.scatter([xi + offset] * len(points), points, color="black", s=12, zorder=3)
        ax.set_xticks(x, phases)
        ax.set_ylabel(label)
        ax.grid(axis="y", alpha=0.25)
    axes[0].legend()
    fig.suptitle("Thermal scenario: three measured repetitions (simulated heat, single-host kind)")
    fig.tight_layout()
    png_path = os.path.join(results_dir, name + ".png")
    fig.savefig(png_path, dpi=140)
    plt.close(fig)
    return csv_path, json_path, png_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default=os.path.join(os.path.dirname(__file__), "results"))
    parser.add_argument("--prefix", default="thermal_codespace")
    args = parser.parse_args()
    prefixes = sorted(path.removesuffix("_phases.csv") for path in
                      glob.glob(os.path.join(args.results, args.prefix + "_*_r*_phases.csv")))
    if not prefixes:
        raise SystemExit("no matching tagged runs")
    rows = [row for prefix in prefixes for row in summarize_run(prefix)]
    aggregates = aggregate(rows)
    paths = write_outputs(args.results, args.prefix + "_comparison", rows, aggregates)
    print(json.dumps(aggregates, indent=2))
    for path in paths:
        print("wrote", path)


if __name__ == "__main__":
    main()
