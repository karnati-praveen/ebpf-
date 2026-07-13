#!/usr/bin/env python3
"""Model-fidelity validation: does the DP's own predicted bottleneck cost
track what actually happens?

For every dynamic-mode run already in results/, correlates the controller's
predicted per-token bottleneck cost (bottleneck_ms, sampled into *_series.csv
every second from /state) against the measured per-token cost of real
requests (1000 / tokens_per_sec, from *_requests.csv) in the same time
window. This uses data already collected by bench/run.py -- no new run is
required for the runs that already exist; it will also pick up any new ones.

Usage: python3 bench/fidelity.py   (reads results/, writes
results/fidelity.png and prints a summary table)
"""
import csv
import glob
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load(prefix):
    reqs_path = f"{prefix}_requests.csv"
    series_path = f"{prefix}_series.csv"
    if not (os.path.exists(reqs_path) and os.path.exists(series_path)):
        return None
    with open(reqs_path) as f:
        reqs = list(csv.DictReader(f))
    with open(series_path) as f:
        series = list(csv.DictReader(f))
    return reqs, series


def nearest_predicted(t, series_sorted):
    """Predicted bottleneck_ms from the series sample closest in time to t."""
    best, best_dt = None, None
    for s in series_sorted:
        st = fnum(s["t"])
        bm = fnum(s.get("bottleneck_ms"))
        if st is None or bm is None:
            continue
        dt = abs(st - t)
        if best_dt is None or dt < best_dt:
            best, best_dt = bm, dt
    return best if best_dt is not None and best_dt < 3 else None


def points_for(prefix):
    loaded = load(prefix)
    if not loaded:
        return []
    reqs, series = loaded
    series_sorted = sorted(series, key=lambda s: fnum(s["t"]) or 0)
    out = []
    for r in reqs:
        if r.get("ok") != "1":
            continue
        tps = fnum(r.get("tokens_per_sec"))
        t = fnum(r.get("t"))
        if not tps or tps <= 0 or t is None:
            continue
        measured_ms = 1000.0 / tps
        predicted_ms = nearest_predicted(t, series_sorted)
        if predicted_ms is None or predicted_ms <= 0:
            continue
        out.append((predicted_ms, measured_ms))
    return out


def main():
    runs = []
    for path in sorted(glob.glob(os.path.join(RESULTS, "*_dynamic_requests.csv"))):
        name = os.path.basename(path)[: -len("_requests.csv")]
        runs.append(name)

    all_points = []
    fig, ax = plt.subplots(figsize=(6, 6))
    colors = plt.cm.tab10.colors
    print(f"{'run':<28} {'n':>5} {'mean predicted (ms)':>20} {'mean measured (ms)':>20} {'ratio':>8}")
    for i, name in enumerate(runs):
        pts = points_for(os.path.join(RESULTS, name))
        if not pts:
            continue
        all_points.extend(pts)
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        mp, mm = sum(xs) / len(xs), sum(ys) / len(ys)
        print(f"{name:<28} {len(pts):>5} {mp:>20.1f} {mm:>20.1f} {mm / mp if mp else 0:>8.2f}")
        ax.scatter(xs, ys, s=10, alpha=0.5, label=name, color=colors[i % len(colors)])

    if all_points:
        lo = 0
        hi = max(max(p) for p in all_points) * 1.05
        ax.plot([lo, hi], [lo, hi], "k--", linewidth=1, label="predicted == measured")
    ax.set_xlabel("predicted bottleneck cost (ms/token, from the DP's cost model)")
    ax.set_ylabel("measured cost (ms/token, 1000/tokens_per_sec)")
    ax.set_title("Model fidelity: predicted vs. measured bottleneck cost")
    ax.legend(fontsize=7, loc="upper left")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    out = os.path.join(RESULTS, "fidelity.png")
    fig.savefig(out, dpi=120)
    print("wrote", out)


if __name__ == "__main__":
    main()
