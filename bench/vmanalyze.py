#!/usr/bin/env python3
"""Turn bench/vmrun.py run directories into the results table and the
pre-registered hypothesis verdicts.

Per run, per phase (pre / fault / post, split at the recorded fault on/off
times on the coordinator's clock):
  throughput      completed tokens / phase seconds (aggregate)
  TTFT, ITL,      p50 and p95 over requests completing in the phase
  completion      latency
  completion rate completed / submitted, by completion time

Per run:
  recovery_s      fault onset -> sustained successful service: the earliest time
                  after onset from which every request completing in the next
                  --sustain-s seconds succeeded. Not "back to pre-fault
                  throughput" -- losing a worker can permanently reduce capacity.
  thru_restored   post-phase throughput as a fraction of pre-phase, reported
                  separately and allowed never to reach 1
  moves           executed / rejected decisions after the initial placement
  transition_ms   median measured transition cost over disrupted requests
  detect_s        H3: fault onset -> first sample where a link source's cost
                  into some stage rose by at least half the injected delay,
                  per source (ebpf, app)
  agent_cpu_pct   node-agent CPU over the run, per VM (H3 overhead)

Paired comparisons use repeat index as the pairing key (the same fault
schedule, run in counterbalanced order) and a bootstrap CI on the paired
difference. Each is classified into exactly one of the four pre-registered
outcomes against --sesoi:
  benefit            CI entirely above +SESOI
  positive-not-meaningful   CI entirely within (0, +SESOI)
  harm               CI entirely below 0
  inconclusive       anything else -- never reported as "no effect"

  python3 bench/vmanalyze.py bench/results/vm --sesoi 0.10
"""

import argparse
import csv
import glob
import json
import math
import os
import random
import statistics
from collections import defaultdict


def fnum(v):
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def pct(xs, q):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    return xs[min(len(xs) - 1, max(0, int(round(q * (len(xs) - 1)))))]


def load_run(d):
    meta = json.load(open(os.path.join(d, "meta.json")))
    reqs = list(csv.DictReader(open(os.path.join(d, "requests.csv"))))
    series = list(csv.DictReader(open(os.path.join(d, "series.csv"))))
    faults = list(csv.DictReader(open(os.path.join(d, "faults.csv"))))
    decisions = json.load(open(os.path.join(d, "decisions.json")))
    return meta, reqs, series, faults, decisions


def phase_bounds(meta, faults):
    on = next((fnum(f["t_local"]) for f in faults if f["action"] == "on"), None)
    off = next((fnum(f["t_local"]) for f in faults if f["action"] == "off"), None)
    return {"pre": (meta["t0"], on), "fault": (on, off), "post": (off, meta["t_end"])}


def phase_metrics(reqs, lo, hi):
    inw = [r for r in reqs if lo <= fnum(r["t_end"]) < hi]
    ok = [r for r in inw if r["ok"] == "1"]
    dur = hi - lo
    return {
        "throughput": sum(int(r["tokens"]) for r in ok) / dur if dur > 0 else None,
        "ttft_p50": pct([fnum(r["ttft_ms"]) for r in ok], 0.5),
        "ttft_p95": pct([fnum(r["ttft_ms"]) for r in ok], 0.95),
        "itl_p50": pct([fnum(r["itl_ms"]) for r in ok], 0.5),
        "itl_p95": pct([fnum(r["itl_ms"]) for r in ok], 0.95),
        "completion_p95": pct([fnum(r["duration_ms"]) for r in ok], 0.95),
        "completion_rate": len(ok) / len(inw) if inw else None,
        "n": len(inw),
    }


def recovery_s(reqs, onset, sustain):
    """Earliest t >= onset from which every request completing within the next
    `sustain` seconds succeeded (and at least one did)."""
    ends = sorted((fnum(r["t_end"]), r["ok"] == "1") for r in reqs if fnum(r["t_end"]) >= onset)
    for i, (t, ok) in enumerate(ends):
        if not ok:
            continue
        window = [o for tt, o in ends[i:] if tt < t + sustain]
        if window and all(window) and ends[-1][0] >= t + sustain:
            return t - onset
    return None


def detection_s(series, onset, magnitude_ms):
    """Per link source, seconds from onset until its cost into any stage rose by
    at least half the injected delay over that stage's pre-onset median."""
    base = defaultdict(list)
    samples = []
    for row in series:
        t = fnum(row["t"])
        try:
            flows = json.loads(row["flows_json"] or "[]")
        except ValueError:
            continue
        for f in flows:
            src = "app" if f["src"] == "app" else "ebpf"
            key = (src, f["dst"], f["port"])
            if t < onset:
                base[key].append(f["srtt_ms"])
            else:
                samples.append((t, key, f["srtt_ms"]))
    out = {}
    for t, key, v in sorted(samples):
        if key[0] in out or key not in base:
            continue
        if v - statistics.median(base[key]) >= 0.5 * magnitude_ms:
            out[key[0]] = t - onset
    return out


def analyse(d, sustain):
    meta, reqs, series, faults, decisions = load_run(d)
    b = phase_bounds(meta, faults)
    # "variant" keeps ablation arms that share a policy apart: link source
    # (H3), cost model (A9/A10) and KV cache (A11) must never be pooled.
    variant = f"{meta['link_source']},{meta.get('cost_model', 'full')},kv{meta.get('kv_cache', '1')}"
    row = {"run": meta["run"], "scenario": meta["scenario"], "magnitude": meta["magnitude"],
           "policy": meta["policy"], "link_source": variant,
           "concurrency": meta["concurrency"], "repeat": meta["repeat"]}
    for ph, (lo, hi) in b.items():
        if lo is None or hi is None:
            continue
        for k, v in phase_metrics(reqs, lo, hi).items():
            row[f"{ph}_{k}"] = v
    onset = b["fault"][0]
    if meta["scenario"] != "stable" and onset is not None:
        row["recovery_s"] = recovery_s(reqs, onset, sustain)
    pre, post = row.get("pre_throughput"), row.get("post_throughput")
    row["thru_restored"] = post / pre if pre and post is not None else None
    moves = [x for x in decisions if x["reason"] != "recovery-or-initial"]
    row["moves_executed"] = sum(1 for x in moves if x["executed"])
    row["moves_rejected"] = sum(1 for x in moves if not x["executed"])
    row["recoveries"] = sum(1 for x in decisions if x["reason"] == "recovery-or-initial") - 1
    tr = [fnum(r["transition_ms"]) for r in reqs if r["ok"] == "1" and (fnum(r["replays"]) or 0) > 0]
    row["transition_ms_median"] = statistics.median([x for x in tr if x]) if any(tr) else None
    rc = [fnum(r["reconstruct_ms"]) for r in reqs if r["ok"] == "1" and (fnum(r["replays"]) or 0) > 0]
    row["reconstruct_ms_median"] = statistics.median([x for x in rc if x]) if any(rc) else None
    if meta["scenario"] == "network" and onset is not None:
        for src, v in detection_s(series, onset, float(meta["magnitude"])).items():
            row[f"detect_s_{src}"] = v
    dur = meta["t_end"] - meta["t0"]
    for h, c in meta["agent_cpu_s"].items():
        s0, s1 = fnum(c["start"]), fnum(c["end"])
        row[f"agent_cpu_pct_{h}"] = 100 * (s1 - s0) / dur if s0 is not None and s1 is not None else None
    return row


def bootstrap_ci(xs, iters=5000, seed=7):
    rng = random.Random(seed)
    means = sorted(statistics.mean(rng.choices(xs, k=len(xs))) for _ in range(iters))
    return means[int(0.025 * iters)], means[int(0.975 * iters) - 1]


def classify(lo, hi, sesoi):
    if lo > sesoi:
        return "benefit"
    if lo > 0 and hi < sesoi:
        return "positive-not-meaningful"
    if hi < 0:
        return "harm"
    return "inconclusive"


def paired(rows, metric, arm, ref, sesoi):
    """Relative paired difference (arm - ref) / ref per repeat, per scenario."""
    by = defaultdict(dict)
    for r in rows:
        v = r.get(metric)
        if v is not None:
            by[(r["scenario"], r["magnitude"], r["link_source"], r["concurrency"],
                r["policy"])][r["repeat"]] = v
    out = []
    for (sc, mag, ls, c, pol), reps in by.items():
        if pol != arm:
            continue
        base = by.get((sc, mag, ls, c, ref), {})
        diffs = [(reps[k] - base[k]) / base[k] for k in reps if k in base and base[k]]
        if len(diffs) < 2:
            out.append((sc, mag, ls, c, len(diffs), None, None, None, "insufficient-pairs"))
            continue
        lo, hi = bootstrap_ci(diffs)
        out.append((sc, mag, ls, c, len(diffs), statistics.mean(diffs), lo, hi,
                    classify(lo, hi, sesoi)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results")
    ap.add_argument("--sesoi", type=float, default=0.10,
                    help="smallest effect size of interest, relative; freeze from the pilot")
    ap.add_argument("--sustain-s", type=float, default=30)
    ap.add_argument("--metric", default="fault_throughput")
    args = ap.parse_args()

    dirs = sorted(d for d in glob.glob(os.path.join(args.results, "*")) if
                  os.path.exists(os.path.join(d, "meta.json")))
    rows, excluded = [], []
    for d in dirs:
        try:
            meta = json.load(open(os.path.join(d, "meta.json")))
            bad = meta.get("contaminated_by_unexpected_worker_restart")
            if bad:
                # A worker died for reasons unrelated to the injected fault;
                # the run measured that failure, not the policy.
                excluded.append((os.path.basename(d), bad))
                continue
            rows.append(analyse(d, args.sustain_s))
        except Exception as e:
            print(f"skip {os.path.basename(d)}: {e}")
    for name, hosts in excluded:
        print(f"EXCLUDED (unexpected worker restart on {hosts}): {name}")
    if not rows:
        print("no runs")
        return 1

    fields = sorted({k for r in rows for k in r}, key=lambda k: (k not in rows[0], k))
    out = os.path.join(args.results, "runs_summary.csv")
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {out} ({len(rows)} runs)\n")

    def cell(v, f="{:.2f}"):
        return "-" if v is None else f.format(v)

    groups = defaultdict(list)
    for r in rows:
        groups[(r["scenario"], r["magnitude"], r["link_source"], r["concurrency"], r["policy"])].append(r)
    print("RESULTS TABLE (median across repeats)")
    hdr = ("scenario", "policy", "n", "thru pre", "thru fault", "thru post", "TTFT p95",
           "ITL p95", "compl rate", "recovery s", "restored", "moves ok/rej", "transition ms")
    print(" | ".join(hdr))
    for (sc, mag, ls, c, pol), rs in sorted(groups.items()):
        med = lambda k: statistics.median([r[k] for r in rs if r.get(k) is not None]) \
            if any(r.get(k) is not None for r in rs) else None  # noqa: E731
        print(" | ".join([
            f"{sc}{'' if sc == 'stable' else ':' + str(mag)} [{ls},c{c}]", pol, str(len(rs)),
            cell(med("pre_throughput")), cell(med("fault_throughput")), cell(med("post_throughput")),
            cell(med("fault_ttft_p95"), "{:.0f}"), cell(med("fault_itl_p95"), "{:.0f}"),
            cell(med("fault_completion_rate")), cell(med("recovery_s"), "{:.1f}"),
            cell(med("thru_restored")),
            f"{cell(med('moves_executed'), '{:.0f}')}/{cell(med('moves_rejected'), '{:.0f}')}",
            cell(med("transition_ms_median"), "{:.0f}"),
        ]))

    comparisons = [
        ("H1  adaptation vs initially-optimized", "hysteresis", "static"),
        ("H2a hysteresis vs no hysteresis", "hysteresis", "none"),
        ("H2b gate vs hysteresis", "gate", "hysteresis"),
        ("    gate-force vs gate (rejected-move counterfactual)", "gate-force", "gate"),
    ]
    print(f"\nPAIRED COMPARISONS on {args.metric}, SESOI={args.sesoi:.0%} "
          "(relative difference, bootstrap 95% CI)")
    for label, arm, ref in comparisons:
        res = paired(rows, args.metric, arm, ref, args.sesoi)
        if not res:
            continue
        print(f"\n{label}")
        for sc, mag, ls, c, n, mean, lo, hi, verdict in sorted(res):
            ci = "-" if lo is None else f"[{lo:+.1%}, {hi:+.1%}]"
            m = "-" if mean is None else f"{mean:+.1%}"
            print(f"  {sc}:{mag} [{ls},c{c}] pairs={n} mean={m} CI={ci} -> {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
