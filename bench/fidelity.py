#!/usr/bin/env python3
"""Model-fidelity validation, as two SEPARATE checks.

The previous version of this script compared the DP's `bottleneck_ms` -- the
slowest SINGLE stage -- against `1000/tokens_per_sec`, which router.py computes
per request as tokens / end-to-end duration, i.e. traversal of ALL stages
sequentially. Those are different quantities: one governs throughput, the other
latency. For k balanced stages the ratio is ~k, which is exactly the 3.0-3.24
"gap" previously reported for 3-stage runs and attributed to gRPC/interpreter
overhead. That attribution was unsupported and confounded.

This version runs:

  CHECK L (latency)    predicted PipelineMs   vs measured per-token end-to-end
  CHECK T (throughput) predicted bottleneck   vs measured AGGREGATE tokens/sec

Both report error DISTRIBUTIONS, not mean ratios: a correct average hides large
per-sample error. Neither is calibrated toward 1.0 -- doing so would distort the
model.

CHECK T is only valid under saturated, stable execution. At low arrival rates
throughput is demand-limited, and during a transition it includes downtime, so
windows overlapping a generation change or falling below a saturation floor are
excluded and counted.

CHECK L requires `pipeline_ms` in *_series.csv, emitted by the controller only
after the Phase 0.1 change. Runs recorded before it cannot support CHECK L; for
those this script reports the stage-count diagnostic instead, which is the
evidence for the misdiagnosis rather than a fidelity result.

Usage: python3 bench/fidelity.py [--results DIR] [--window S]
"""
import argparse
import csv
import glob
import os
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

DEFAULT_RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
# A window whose aggregate throughput is below this fraction of the run's best
# observed window is treated as demand-limited, not capacity-limited.
SATURATION_FLOOR = 0.60


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def stage_count(layout):
    """Stages in a layout string 'name:0-4|name:4-8|name:8-12'."""
    if not layout:
        return None
    return len([p for p in layout.split("|") if p.strip()])


def load(prefix):
    reqs_path, series_path = f"{prefix}_requests.csv", f"{prefix}_series.csv"
    if not (os.path.exists(reqs_path) and os.path.exists(series_path)):
        return None
    with open(reqs_path) as f:
        reqs = list(csv.DictReader(f))
    with open(series_path) as f:
        series = list(csv.DictReader(f))
    return reqs, series


def nearest(series_sorted, t, field, max_dt=3.0):
    best, best_dt = None, None
    for s in series_sorted:
        st, v = fnum(s.get("t")), fnum(s.get(field))
        if st is None or v is None:
            continue
        dt = abs(st - t)
        if best_dt is None or dt < best_dt:
            best, best_dt = v, dt
    return best if best_dt is not None and best_dt < max_dt else None


def generation_changes(series_sorted):
    """Times at which the controller generation changed."""
    out, prev = [], None
    for s in series_sorted:
        g, t = s.get("ctrl_generation"), fnum(s.get("t"))
        if t is None or g in (None, ""):
            continue
        if prev is not None and g != prev:
            out.append(t)
        prev = g
    return out


def rel_errors(pairs):
    """(predicted, measured) -> signed relative error distribution."""
    return [(m - p) / p for p, m in pairs if p and p > 0]


def describe(errs):
    if not errs:
        return None
    errs = sorted(errs)
    n = len(errs)

    def q(f):
        return errs[min(n - 1, max(0, int(round(f * (n - 1)))))]

    return {
        "n": n,
        "median": statistics.median(errs),
        "p10": q(0.10),
        "p25": q(0.25),
        "p75": q(0.75),
        "p90": q(0.90),
        "iqr": q(0.75) - q(0.25),
        "frac_within_20pct": sum(1 for e in errs if abs(e) <= 0.20) / n,
    }


# --------------------------------------------------------------------------
# CHECK L -- latency. predicted PipelineMs vs measured per-token end-to-end.
# --------------------------------------------------------------------------
def check_latency(reqs, series_sorted):
    pairs, missing = [], 0
    for r in reqs:
        if r.get("ok") != "1":
            continue
        tps, t = fnum(r.get("tokens_per_sec")), fnum(r.get("t"))
        if not tps or tps <= 0 or t is None:
            continue
        pred = nearest(series_sorted, t, "pipeline_ms")
        if pred is None or pred <= 0:
            missing += 1
            continue
        pairs.append((pred, 1000.0 / tps))
    return pairs, missing


# --------------------------------------------------------------------------
# CHECK T -- throughput. predicted bottleneck vs measured AGGREGATE tokens/sec.
# --------------------------------------------------------------------------
def check_throughput(reqs, series_sorted, window):
    done = []
    for r in reqs:
        if r.get("ok") != "1":
            continue
        t, dur, tps = fnum(r.get("t")), fnum(r.get("duration_ms")), fnum(r.get("tokens_per_sec"))
        if None in (t, dur, tps) or tps <= 0:
            continue
        done.append((t, max(1.0, round(tps * dur / 1000.0))))  # completion time, tokens
    if not done:
        return [], 0, 0

    gens = generation_changes(series_sorted)
    lo, hi = min(t for t, _ in done), max(t for t, _ in done)
    raw, excl_transition = [], 0
    b = lo
    while b + window <= hi:
        toks = sum(n for t, n in done if b <= t < b + window)
        if any(b <= g < b + window for g in gens):
            excl_transition += 1
        else:
            pred = nearest(series_sorted, b + window / 2, "bottleneck_ms")
            if pred and pred > 0:
                raw.append((b, toks / window, pred))
        b += window

    if not raw:
        return [], excl_transition, 0
    peak = max(tp for _, tp, _ in raw)
    pairs, excl_unsat = [], 0
    for _, tp, pred in raw:
        if peak > 0 and tp < SATURATION_FLOOR * peak:
            excl_unsat += 1
            continue
        # Both sides in ms/token. `pred` is bottleneck_ms, ALREADY ms/token --
        # do not invert it. `tp` is aggregate tokens/sec, so it does invert.
        pairs.append((pred, 1000.0 / tp))
    return pairs, excl_transition, excl_unsat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=DEFAULT_RESULTS)
    ap.add_argument("--window", type=float, default=10.0,
                    help="aggregation window for CHECK T, seconds")
    args = ap.parse_args()

    runs = sorted(os.path.basename(p)[: -len("_requests.csv")]
                  for p in glob.glob(os.path.join(args.results, "*dynamic*_requests.csv")))
    if not runs:
        print(f"no dynamic runs under {args.results}")
        return

    lat_all, thr_all, diag = [], [], []
    print("=" * 100)
    print("CHECK L -- latency: predicted PipelineMs vs measured per-token end-to-end")
    print("=" * 100)
    hdr = f"{'run':<34} {'n':>5} {'median':>9} {'p10':>9} {'p90':>9} {'IQR':>8} {'|e|<=20%':>9}"
    print(hdr)
    for name in runs:
        loaded = load(os.path.join(args.results, name))
        if not loaded:
            continue
        reqs, series = loaded
        ss = sorted(series, key=lambda s: fnum(s.get("t")) or 0)
        pairs, missing = check_latency(reqs, ss)
        if not pairs:
            k = next((stage_count(s.get("layout")) for s in ss if stage_count(s.get("layout"))), None)
            diag.append((name, k, missing))
            continue
        lat_all.extend(pairs)
        d = describe(rel_errors(pairs))
        print(f"{name:<34} {d['n']:>5} {d['median']:>+8.1%} {d['p10']:>+8.1%} "
              f"{d['p90']:>+8.1%} {d['iqr']:>7.1%} {d['frac_within_20pct']:>8.0%}")

    if diag:
        print("\nno pipeline_ms in these runs -- CHECK L not possible. Stage-count diagnostic:")
        print(f"{'run':<34} {'stages':>7} {'expected ratio if confounded':>30}")
        for name, k, _ in diag:
            print(f"{name:<34} {k if k else '?':>7} {('~%d' % k) if k else '?':>30}")
        print("  (the old script's measured/predicted ratio tracked this number, not model error)")

    print()
    print("=" * 100)
    print(f"CHECK T -- throughput: predicted bottleneck vs measured aggregate "
          f"(window={args.window:.0f}s, saturation floor={SATURATION_FLOOR:.0%})")
    print("=" * 100)
    print(f"{'run':<34} {'n':>5} {'median':>9} {'p10':>9} {'p90':>9} {'IQR':>8} "
          f"{'excl:trans':>11} {'excl:unsat':>11}")
    for name in runs:
        loaded = load(os.path.join(args.results, name))
        if not loaded:
            continue
        reqs, series = loaded
        ss = sorted(series, key=lambda s: fnum(s.get("t")) or 0)
        pairs, ex_t, ex_u = check_throughput(reqs, ss, args.window)
        if not pairs:
            print(f"{name:<34} {'-':>5} {'-':>9} {'-':>9} {'-':>9} {'-':>8} {ex_t:>11} {ex_u:>11}")
            continue
        thr_all.extend(pairs)
        d = describe(rel_errors(pairs))
        print(f"{name:<34} {d['n']:>5} {d['median']:>+8.1%} {d['p10']:>+8.1%} "
              f"{d['p90']:>+8.1%} {d['iqr']:>7.1%} {ex_t:>11} {ex_u:>11}")

    print()
    print("RANK CORRECTNESS: not derivable from these runs. It requires several")
    print("candidate placements scored under the SAME conditions -- i.e. the Phase 6")
    print("matched forced-move arms. Not reported rather than approximated.")
    print()
    print("Reported as signed relative error (measured-predicted)/predicted.")
    print("No ratio is calibrated toward 1.0; these checks diagnose, they do not fit.")

    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    for ax, pts, title, xl in (
        (axes[0], lat_all, "CHECK L: latency", "predicted PipelineMs (ms/token)"),
        (axes[1], thr_all, "CHECK T: throughput", "predicted bottleneck (ms/token)"),
    ):
        if pts:
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            ax.scatter(xs, ys, s=10, alpha=0.45)
            hi = max(max(xs), max(ys)) * 1.05
            ax.plot([0, hi], [0, hi], "k--", linewidth=1, label="predicted == measured")
            ax.legend(fontsize=8)
        else:
            ax.text(0.5, 0.5, "no data\n(see notes above)", ha="center", va="center",
                    transform=ax.transAxes, fontsize=9)
        ax.set_title(title)
        ax.set_xlabel(xl)
        ax.set_ylabel("measured (ms/token)")
        ax.grid(alpha=0.3)
    fig.tight_layout()
    out = os.path.join(args.results, "fidelity.png")
    fig.savefig(out, dpi=120)
    print("wrote", out)


if __name__ == "__main__":
    main()
