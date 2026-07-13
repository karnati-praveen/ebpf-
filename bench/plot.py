#!/usr/bin/env python3
"""Render the ablation results: per-scenario timelines (tokens/sec + worst
stage idle, dynamic vs static, fault window shaded) and a summary bar chart.

Usage: python3 bench/plot.py   (reads bench/results/, writes PNGs there)
"""

import csv
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
SCENARIOS = ["baseline", "netem", "thermal", "failure", "combo"]
MODES = {"dynamic": "#2563eb", "static": "#dc2626", "profileonly": "#a855f7"}


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return list(csv.DictReader(f))


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def bucket(rows, t0, key, width=5.0):
    """Average `key` in fixed time buckets for a readable line."""
    out = {}
    for r in rows:
        v = fnum(r.get(key))
        t = fnum(r.get("t"))
        if v is None or t is None:
            continue
        out.setdefault(int((t - t0) / width), []).append(v)
    xs = sorted(out)
    return [x * width for x in xs], [sum(out[x]) / len(out[x]) for x in xs]


def plot_scenario(scenario):
    fig, axes = plt.subplots(2, 1, figsize=(9, 6), sharex=True)
    fig.suptitle(f"Scenario: {scenario} — dynamic vs static")
    have_any = False

    for mode, color in MODES.items():
        prefix = os.path.join(RESULTS, f"{scenario}_{mode}")
        reqs = read_csv(f"{prefix}_requests.csv")
        series = read_csv(f"{prefix}_series.csv")
        phases = read_csv(f"{prefix}_phases.csv")
        if not reqs:
            continue
        have_any = True
        t0 = min(fnum(r["t"]) for r in reqs)

        xs, ys = bucket([r for r in reqs if r["ok"] == "1"], t0, "tokens_per_sec")
        axes[0].plot(xs, ys, label=mode, color=color, linewidth=2)
        exs = [fnum(r["t"]) - t0 for r in reqs if r["ok"] == "0"]
        if exs:
            axes[0].plot(exs, [0.05] * len(exs), "x", color=color, alpha=0.5,
                         label=f"{mode} errors")

        xs, ys = bucket(series, t0, "worst_idle")
        axes[1].plot(xs, ys, label=mode, color=color, linewidth=2)

        for p in phases:
            if p["phase"] in ("fault", "recover"):
                for ax in axes:
                    ax.axvline(fnum(p["t"]) - t0, color="gray", linestyle="--", alpha=0.6)

    if not have_any:
        plt.close(fig)
        return
    axes[0].set_ylabel("tokens/sec per request")
    axes[0].legend(loc="lower left", fontsize=8)
    axes[0].grid(alpha=0.3)
    axes[1].set_ylabel("worst stage idle fraction\n(pipeline bubble)")
    axes[1].set_xlabel("seconds since scenario start")
    axes[1].legend(loc="lower left", fontsize=8)
    axes[1].grid(alpha=0.3)
    out = os.path.join(RESULTS, f"{scenario}.png")
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print("wrote", out)


def plot_summary():
    path = os.path.join(RESULTS, "summary.json")
    if not os.path.exists(path):
        return
    with open(path) as f:
        summary = {(s["scenario"], s["mode"]): s for s in json.load(f)}

    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    metrics = [
        ("throughput_tokens_per_sec", "pipeline throughput (tokens/sec)", lambda s: s.get("throughput_tokens_per_sec")),
        ("ttft_p95", "TTFT p95 (ms)", lambda s: s.get("overall", {}).get("ttft_ms_p95")),
        ("errors", "failed requests", lambda s: s.get("requests_error")),
    ]
    width = 0.25
    xs = range(len(SCENARIOS))
    for ax, (name, title, get) in zip(axes, metrics):
        for i, (mode, color) in enumerate(MODES.items()):
            vals, has_data = [], False
            for sc in SCENARIOS:
                s = summary.get((sc, mode))
                v = get(s) if s else None
                if s is not None:
                    has_data = True
                vals.append(v if v is not None else 0)
            if not has_data:
                continue
            ax.bar([x + (i - 1) * width for x in xs], vals, width,
                   label=mode, color=color)
        ax.set_title(title, fontsize=10)
        ax.set_xticks(list(xs))
        ax.set_xticklabels(SCENARIOS, fontsize=8)
        ax.grid(alpha=0.3, axis="y")
    axes[0].legend(fontsize=8)
    out = os.path.join(RESULTS, "summary.png")
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print("wrote", out)


if __name__ == "__main__":
    for scenario in SCENARIOS:
        plot_scenario(scenario)
    plot_summary()
