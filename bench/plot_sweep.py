#!/usr/bin/env python3
"""Plot the hysteresis sensitivity sweep (results/hysteresis_sweep.json):
repartition count and throughput/TTFT vs. improvement threshold and cooldown.

Usage: python3 bench/plot_sweep.py
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


def main():
    path = os.path.join(RESULTS, "hysteresis_sweep.json")
    if not os.path.exists(path):
        print("no sweep data at", path)
        return
    with open(path) as f:
        rows = json.load(f)

    labels = [f"imp={r['improvement']:.2f}\ncd={r['cooldown_s']}s" for r in rows]
    reparts = [r["repartitions"] for r in rows]
    tps = [r["overall"]["tokens_per_sec_mean"] for r in rows]
    ttft = [r["overall"]["ttft_ms_p95"] for r in rows]

    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    axes[0].bar(labels, reparts, color="#2563eb")
    axes[0].set_title("repartitions triggered", fontsize=10)
    axes[0].grid(alpha=0.3, axis="y")

    axes[1].bar(labels, tps, color="#16a34a")
    axes[1].set_title("mean tokens/sec", fontsize=10)
    axes[1].grid(alpha=0.3, axis="y")

    axes[2].bar(labels, ttft, color="#dc2626")
    axes[2].set_title("TTFT p95 (ms)", fontsize=10)
    axes[2].grid(alpha=0.3, axis="y")

    for ax in axes:
        ax.tick_params(axis="x", labelsize=7)

    fig.suptitle("Hysteresis sensitivity sweep (netem scenario, dynamic mode)")
    fig.tight_layout()
    out = os.path.join(RESULTS, "hysteresis_sweep.png")
    fig.savefig(out, dpi=120)
    print("wrote", out)


if __name__ == "__main__":
    main()
