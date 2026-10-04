#!/usr/bin/env python3
"""Render descriptive figures and a report from analyze_objectives.py outputs."""
import argparse
import csv
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("experiment", type=Path)
    args = ap.parse_args()
    out = args.experiment / "analysis"
    with (out / "summary.csv").open() as f:
        rows = list(csv.DictReader(f))
    with (out / "per-run.csv").open() as f:
        runs = list(csv.DictReader(f))
    status = json.loads((out / "status.json").read_text())
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), constrained_layout=True)
    panels = [("objective", "stable", "Stable: 32 output tokens"),
              ("objective", "network", "Network +120 ms: 32 tokens"),
              ("demand", "stable", "Workload-aware: 64 tokens")]
    colors = {"latency": "#2878b5", "throughput": "#e88724",
              "auto-fixed": "#438b54", "auto-remaining": "#8259a6"}
    for ax, (matrix, scenario, title) in zip(axes, panels):
        selected = [r for r in rows if r["matrix"] == matrix and r["scenario"] == scenario]
        arms = sorted(set(r["arm"] for r in selected))
        width = .75 / max(1, len(arms))
        for i, arm in enumerate(arms):
            for c in (1, 2):
                group = [r for r in selected if r["arm"] == arm and int(r["concurrency"]) == c]
                if not group:
                    continue
                x = c + (i - (len(arms) - 1) / 2) * width
                ax.bar(x, float(group[0]["median_tokens_per_second"]), width,
                       color=colors[arm], label=arm if c == 1 else None, alpha=.8)
                values = [float(r["tokens_per_second_including_drain"]) for r in runs
                          if r["matrix"] == matrix and r["scenario"] == scenario
                          and r["arm"] == arm and int(r["concurrency"]) == c]
                ax.scatter([x] * len(values), values, color="black", s=12, zorder=3)
        ax.set(title=title, xlabel="Concurrent requests", xticks=[1, 2], ylim=(0, None))
        ax.set_ylabel("Successful output tokens / second")
        ax.legend(fontsize=8)
        ax.grid(axis="y", alpha=.2)
    fig.suptitle("Azure Qwen3-0.6B CPU: run medians and individual runs; includes drain")
    for suffix in ("png", "svg", "pdf"):
        fig.savefig(out / f"throughput.{suffix}", dpi=180)
    text = ["# Live objective and remaining-work experiments", "",
            f"Completed **{status['completed_runs']}/32 runs**; "
            f"**{status['total_requests']} measured requests**, "
            f"**{status['failed_requests']} failed**; {status['excluded']} excluded runs.", "",
            "![Run-level throughput](throughput.png)", "",
            "Bars show median whole-run throughput including request drain; dots show individual runs. "
            "The two output budgets are separate workloads. Client completion is measured externally.", "",
            "| Matrix | Condition | Concurrency | Arm | Runs | Tokens/s | Client p50 (s) | Moves | Rejections |",
            "|---|---|---:|---|---:|---:|---:|---:|---:|"]
    for r in rows:
        text.append(f"| {r['matrix']} | {r['scenario']} | {r['concurrency']} | {r['arm']} | "
                    f"{r['repeats']} | {float(r['median_tokens_per_second']):.2f} | "
                    f"{float(r['median_client_p50_ms'])/1000:.2f} | {r['voluntary_moves']} | {r['voluntary_rejections']} |")
    by_group = {(r['matrix'], r['scenario'], int(r['concurrency']), r['arm']): r for r in rows}
    def rate(matrix, scenario, c, arm):
        return float(by_group[matrix, scenario, c, arm]['median_tokens_per_second'])
    text += ["", "## Observations", "",
             f"In stable 32-token trials at concurrency two, throughput placement delivered "
             f"{100*(rate('objective','stable',2,'throughput')/rate('objective','stable',2,'latency')-1):.1f}% "
             "more tokens per second than latency placement (ratio of group medians). "
             "At concurrency one, latency placement avoided an extra stage and hop.", "",
             f"Under the +120 ms network condition at concurrency one, latency placement delivered "
             f"{100*(rate('objective','network',1,'latency')/rate('objective','network',1,'throughput')-1):.1f}% "
             "more tokens per second than throughput placement. These are descriptive results from two repeats."]
    if all(('demand','stable',2,a) in by_group for a in ('throughput','auto-fixed','auto-remaining')):
        text += ["", "In the short stable 64-token matrix at concurrency two, the fixed-throughput "
                 f"arm reached {rate('demand','stable',2,'throughput'):.2f} tokens/s, compared with "
                 f"{rate('demand','stable',2,'auto-fixed'):.2f} for auto-fixed and "
                 f"{rate('demand','stable',2,'auto-remaining'):.2f} for auto-remaining. "
                 "Automatic arms pay for starting with latency placement and switching during the run. "
                 "The gate's accepted/rejected decisions demonstrate its live behavior; this matrix "
                 "does not establish that automatic selection or remaining-work gating improves performance."]
    checks = [r for r in runs if r['matrix'] == 'demand']
    verified = sum(r['correctness_verified'] == 'True' for r in checks)
    text += ["", f"Fixed-input eight-token greedy checks matched the shared reference in **{verified}/{len(checks)} demand runs**.", "",
             "These small repeated trials demonstrate an objective tradeoff and exercise automatic selection "
             "and remaining-work gating. They do not establish statistical significance or a universal advantage. "
             "Auto arms start with latency placement; transition cost, cooldown and measured remaining budget "
             "can delay switching. Compare them as complete policies, including that starting behavior.", "",
             "Inspect [per-run metrics](per-run.csv), [paired repeats](paired-comparisons.json), "
             "and each raw decisions.json for accepted and rejected transitions. "
             "Probabilistic gates, oracle arms and calibration remain separate analytical replay evidence.", ""]
    (out / "REPORT.md").write_text("\n".join(text))


if __name__ == "__main__":
    main()
