#!/usr/bin/env python3
"""KubeEdgeInfer ablation harness.

Runs four scenarios (baseline, netem, thermal, failure) against the dynamic
controller and the static baseline, driving sustained load through the router
while sampling per-stage idle fractions (bubble time), controller decisions,
and node telemetry. Faults are injected from outside the cluster:

  netem    tc qdisc on a kind node's eth0 (network degradation)
  thermal  simulated-GPU temperature override via the node agent
  failure  docker stop / start of a kind node

Outputs per run: results/<scenario>_<mode>_requests.csv, _series.csv,
_phases.csv, plus results/summary.json across all runs.

Usage:
  python3 bench/run.py --all
  python3 bench/run.py --scenario netem --mode dynamic
  python3 bench/run.py --scenario thermal --mode dynamic --tag thermal_dynamic_r1
"""

import argparse
import csv
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request

NS = "kubeedgeinfer"
CLUSTER = "kubeedgeinfer"
NODE_MID = f"{CLUSTER}-worker2"   # netem / thermal target (middle stage)
NODE_LAST = f"{CLUSTER}-worker3"  # failure target (last stage)
RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")

ROUTER_PORT = 18080
CTRL_PORT = 18081

LOAD_THREADS = 3
PROMPT_LEN = 16
NEW_TOKENS = 8


def sh(cmd, check=True, quiet=False, timeout=None):
    if not quiet:
        print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd, check=check, capture_output=True, text=True, timeout=timeout)


def kubectl(*args, check=True, timeout=120):
    return sh(["kubectl", "-n", NS, *args], check=check, quiet=True, timeout=timeout)


def http_json(url, body=None, timeout=5):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data)
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def wait_local_port(port, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1).close()
            return True
        except OSError:
            time.sleep(0.3)
    return False


class PortForward:
    def __init__(self, target, local, remote):
        self.args = ["kubectl", "-n", NS, "port-forward", target, f"{local}:{remote}"]
        self.local = local
        self.proc = None

    def __enter__(self):
        self.proc = subprocess.Popen(self.args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not wait_local_port(self.local):
            raise RuntimeError(f"port-forward {self.args} did not come up")
        return self

    def __exit__(self, *exc):
        self.proc.send_signal(signal.SIGTERM)
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def node_ip(node):
    out = sh(["docker", "inspect", "-f",
              "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", node],
             quiet=True).stdout.strip()
    if not out:
        raise RuntimeError(f"no IP for node {node} (is it running?)")
    return out


# --- fault injection --------------------------------------------------------

def netem_start(node, delay_ms=80):
    sh(["docker", "exec", node, "tc", "qdisc", "add", "dev", "eth0",
        "root", "netem", "delay", f"{delay_ms}ms"])


def netem_stop(node):
    sh(["docker", "exec", node, "tc", "qdisc", "del", "dev", "eth0", "root"],
       check=False)


def thermal_start(node, temp=92.0):
    http_json(f"http://{node_ip(node)}:9101/gpu/override", {"temp_c": temp})


def thermal_stop(node):
    try:
        http_json(f"http://{node_ip(node)}:9101/gpu/override", {"clear": True})
    except Exception as e:
        print(f"  (thermal clear failed: {e})")


def node_stop(node):
    sh(["docker", "stop", node])


def node_start(node):
    sh(["docker", "start", node])
    # Wait for the node to rejoin and its daemonset pods to recover.
    deadline = time.time() + 180
    while time.time() < deadline:
        out = sh(["kubectl", "get", "node", node,
                  "-o", "jsonpath={.status.conditions[?(@.type=='Ready')].status}"],
                 check=False, quiet=True).stdout.strip()
        if out == "True":
            return
        time.sleep(2)
    print(f"  WARNING: node {node} not Ready after restart")


# --- workload + sampling ----------------------------------------------------

class LoadGen:
    def __init__(self, url):
        self.url = url
        self.rows = []
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.threads = []

    def _loop(self):
        while not self.stop.is_set():
            t0 = time.time()
            try:
                out = http_json(self.url, {
                    "prompt_len": PROMPT_LEN, "max_new_tokens": NEW_TOKENS,
                }, timeout=120)
                row = dict(t=time.time(), ok=1, ttft_ms=out["ttft_ms"],
                           duration_ms=out["duration_ms"],
                           tokens_per_sec=out["tokens_per_sec"],
                           replays=out["replays"], generation=out["generation"])
            except Exception as e:
                row = dict(t=time.time(), ok=0, ttft_ms="", duration_ms="",
                           tokens_per_sec="", replays="", generation="",
                           error=str(e)[:80])
                time.sleep(1)
            with self.lock:
                self.rows.append(row)
            _ = t0

    def start(self):
        for _ in range(LOAD_THREADS):
            t = threading.Thread(target=self._loop, daemon=True)
            t.start()
            self.threads.append(t)

    def finish(self):
        self.stop.set()
        for t in self.threads:
            t.join(timeout=130)
        return self.rows


class Sampler:
    def __init__(self, router_url, ctrl_url):
        self.router_url = router_url
        self.ctrl_url = ctrl_url
        self.rows = []
        self.stop = threading.Event()
        self.thread = None

    def _sample(self):
        row = {"t": time.time()}
        try:
            stats = http_json(f"{self.router_url}/stats", timeout=3)
            idles, layers = [], []
            for st in stats.get("stages", []):
                idles.append(st.get("idle_fraction"))
                layers.append(f"{st['name']}:{st['layers'][0]}-{st['layers'][1]}")
            row["idle_fractions"] = "|".join("" if v is None else f"{v:.4f}" for v in idles)
            row["worst_idle"] = max((v for v in idles if v is not None), default="")
            row["layout"] = "|".join(layers)
            row["router_generation"] = stats.get("generation")
        except Exception:
            pass
        try:
            state = http_json(f"{self.ctrl_url}/state", timeout=3)
            row["ctrl_generation"] = state.get("generation")
            row["bottleneck_ms"] = state.get("bottleneck_ms")
            temps, speeds = [], []
            for node, st in sorted(state.get("telemetry", {}).get("nodes", {}).items()):
                temps.append(f"{node}:{st['temp_c']:.1f}")
                speeds.append(f"{node}:{st['speed_factor']:.2f}")
            row["temps"] = "|".join(temps)
            row["speeds"] = "|".join(speeds)
        except Exception:
            pass
        self.rows.append(row)

    def _loop(self):
        while not self.stop.is_set():
            self._sample()
            time.sleep(1)

    def start(self):
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def finish(self):
        self.stop.set()
        self.thread.join(timeout=10)
        return self.rows


# --- scenario orchestration -------------------------------------------------

def combo_start():
    netem_start(NODE_MID)
    thermal_start(NODE_MID)


def combo_stop():
    netem_stop(NODE_MID)
    thermal_stop(NODE_MID)


SCENARIOS = {
    "baseline": [("steady", 60, None, None)],
    "netem":    [("clean", 20, None, None),
                 ("fault", 60, lambda: netem_start(NODE_MID), None),
                 ("recover", 20, lambda: netem_stop(NODE_MID), None)],
    "thermal":  [("clean", 20, None, None),
                 ("fault", 60, lambda: thermal_start(NODE_MID), None),
                 ("recover", 20, lambda: thermal_stop(NODE_MID), None)],
    "failure":  [("clean", 20, None, None),
                 ("fault", 60, lambda: node_stop(NODE_LAST), None),
                 ("recover", 60, lambda: node_start(NODE_LAST), None)],
    # Joint-fault: netem delay AND thermal throttle on the same node at the
    # same time. Backs claim 3 of the novelty writeup (one trigger, multiple
    # fault classes) with an actual experiment rather than an architectural
    # assertion.
    "combo":    [("clean", 20, None, None),
                 ("fault", 60, combo_start, None),
                 ("recover", 20, combo_stop, None)],
}

# Modes: "dynamic" (full loop), "static" (one-time split, baseline),
# "profileonly" (repartitions like dynamic, but its telemetry inputs are
# frozen at the first reading -- an offline-profiling ablation that
# approximates EdgeShard/PipeEdge/Galaxy's "decide once from a profile"
# design using KubeEdgeInfer's own DP/apply/heal machinery, isolating the
# value of *continuous* eBPF telemetry specifically).
MODES = ["dynamic", "static", "profileonly"]


def set_mode(mode, improvement=None, cooldown=None):
    static = "1" if mode == "static" else "0"
    profile_once = "1" if mode == "profileonly" else "0"
    env = {
        "STATIC_MODE": static,
        "PROFILE_ONCE": profile_once,
        "IMPROVEMENT_FRAC": str(improvement if improvement is not None else 0.15),
        "COOLDOWN_S": str(cooldown if cooldown is not None else 30),
    }
    print(f"  switching controller to {mode} mode ({env}) and restarting pipeline pods")
    kubectl("set", "env", "deploy/controller", *[f"{k}={v}" for k, v in env.items()])
    kubectl("rollout", "restart", "deploy/controller", "deploy/router", "ds/keinfer-worker")
    for target in ["deploy/controller", "deploy/router", "ds/keinfer-worker"]:
        kubectl("rollout", "status", target, "--timeout=180s", timeout=200)


def wait_pipeline_ready(router_url, stages=3, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            p = http_json(f"{router_url}/pipeline", timeout=3)
            if len(p.get("stages", [])) >= stages:
                return
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError("pipeline did not become ready")


def write_csv(path, rows, fields):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def run_one(scenario, mode, improvement=None, cooldown=None, tag=None):
    print(f"=== {scenario} / {mode} ===")
    os.makedirs(RESULTS, exist_ok=True)
    set_mode(mode, improvement, cooldown)

    with PortForward("svc/router", ROUTER_PORT, 8080), \
         PortForward("svc/controller", CTRL_PORT, 8081):
        router_url = f"http://127.0.0.1:{ROUTER_PORT}"
        ctrl_url = f"http://127.0.0.1:{CTRL_PORT}"
        wait_pipeline_ready(router_url)
        # Warm the pipeline (and the eBPF flow table) before measuring. Right
        # after a mode-switch rollout the pipeline can report itself ready
        # (stage count reached) before every worker has actually loaded its
        # backend, so a transient 500 here is expected, not fatal.
        for _ in range(3):
            for attempt in range(6):
                try:
                    http_json(f"{router_url}/generate",
                              {"prompt_len": PROMPT_LEN, "max_new_tokens": 4}, timeout=120)
                    break
                except Exception as e:
                    if attempt == 5:
                        raise
                    print(f"  warmup request failed ({e}), retrying...")
                    time.sleep(3)

        load = LoadGen(f"{router_url}/generate")
        sampler = Sampler(router_url, ctrl_url)
        phases = []
        t_start = time.time()
        load.start()
        sampler.start()
        try:
            for name, duration, inject, _ in SCENARIOS[scenario]:
                if inject:
                    inject()
                phases.append({"phase": name, "t": time.time()})
                print(f"  phase {name} ({duration}s)")
                time.sleep(duration)
        finally:
            requests = load.finish()
            series = sampler.finish()
            # Always clean up fault state, even on failure.
            if scenario == "netem":
                netem_stop(NODE_MID)
            elif scenario == "thermal":
                thermal_stop(NODE_MID)
            elif scenario == "failure":
                node_start(NODE_LAST)
            elif scenario == "combo":
                combo_stop()

    name = tag or f"{scenario}_{mode}"
    prefix = os.path.join(RESULTS, name)
    write_csv(f"{prefix}_requests.csv", requests,
              ["t", "ok", "ttft_ms", "duration_ms", "tokens_per_sec",
               "replays", "generation", "error"])
    write_csv(f"{prefix}_series.csv", series,
              ["t", "idle_fractions", "worst_idle", "layout",
               "router_generation", "ctrl_generation", "bottleneck_ms",
               "temps", "speeds"])
    write_csv(f"{prefix}_phases.csv", phases, ["phase", "t"])

    return summarize(scenario, mode, requests, series, phases, t_start)


def summarize(scenario, mode, requests, series, phases, t_start):
    oks = [r for r in requests if r["ok"] == 1]
    errors = len(requests) - len(oks)
    wall = (max((r["t"] for r in requests), default=t_start) - t_start) or 1

    fault_t = next((p["t"] for p in phases if p["phase"] == "fault"), None)
    fault_end = next((p["t"] for p in phases if p["phase"] == "recover"), None)

    def agg(rows):
        if not rows:
            return {"n": 0}
        tps = [r["tokens_per_sec"] for r in rows]
        ttft = sorted(r["ttft_ms"] for r in rows)
        return {
            "n": len(rows),
            "tokens_per_sec_mean": round(sum(tps) / len(tps), 3),
            "ttft_ms_mean": round(sum(ttft) / len(ttft), 1),
            "ttft_ms_p95": round(ttft[int(0.95 * (len(ttft) - 1))], 1),
        }

    # Repartition count: distinct controller generations observed in the
    # sampled series. Feeds the hysteresis sensitivity sweep (thrashing
    # count vs. improvement/cooldown thresholds).
    gens = sorted({r["ctrl_generation"] for r in series
                   if r.get("ctrl_generation") not in (None, "")})
    repartitions = max(len(gens) - 1, 0)

    out = {
        "scenario": scenario, "mode": mode,
        "requests_ok": len(oks), "requests_error": errors,
        "throughput_tokens_per_sec": round(len(oks) * NEW_TOKENS / wall, 3),
        "repartitions": repartitions,
        "overall": agg(oks),
    }
    if fault_t and fault_end:
        out["during_fault"] = agg([r for r in oks if fault_t <= r["t"] < fault_end])
        out["after_recovery"] = agg([r for r in oks if r["t"] >= fault_end])
    print(f"  -> {json.dumps(out, indent=2)}")
    return out


def sweep(scenario, improvements, cooldowns):
    """Hysteresis sensitivity sweep: run `scenario` in dynamic mode across a
    grid of (improvement fraction, cooldown) and record repartition count vs.
    throughput/TTFT, so the 15%/30s defaults are justified by data instead of
    asserted. Writes results/hysteresis_sweep.json."""
    rows = []
    for imp in improvements:
        for cd in cooldowns:
            tag = f"{scenario}_sweep_imp{imp}_cd{cd}"
            result = run_one(scenario, "dynamic", improvement=imp, cooldown=cd, tag=tag)
            result["improvement"] = imp
            result["cooldown_s"] = cd
            rows.append(result)
            path = os.path.join(RESULTS, "hysteresis_sweep.json")
            with open(path, "w") as f:
                json.dump(rows, f, indent=2)
    print(f"sweep written to {os.path.join(RESULTS, 'hysteresis_sweep.json')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--scenario", choices=list(SCENARIOS))
    ap.add_argument("--mode", choices=MODES)
    ap.add_argument("--tag",
                    help="unique output prefix for a single scenario/mode run")
    ap.add_argument("--sweep-hysteresis", metavar="SCENARIO", choices=list(SCENARIOS),
                     help="run a hysteresis sensitivity sweep on this scenario instead of a normal run")
    args = ap.parse_args()

    if args.tag and (args.all or args.sweep_hysteresis or
                     not (args.scenario and args.mode)):
        ap.error("--tag requires exactly one --scenario/--mode run")

    if args.sweep_hysteresis:
        # 0.15/30s (the shipped default) is already covered by the existing
        # <scenario>_dynamic run; sweep the extremes around it to keep this
        # tractable in a single sitting.
        sweep(args.sweep_hysteresis,
              improvements=[0.05, 0.30],
              cooldowns=[10, 60])
        return

    runs = []
    if args.all:
        for scenario in SCENARIOS:
            for mode in ["dynamic", "static"]:
                runs.append((scenario, mode))
    elif args.scenario and args.mode:
        runs = [(args.scenario, args.mode)]
    else:
        ap.error("use --all, --sweep-hysteresis SCENARIO, or both --scenario and --mode")

    summaries = []
    summary_path = os.path.join(RESULTS, "summary.json")
    if os.path.exists(summary_path):
        with open(summary_path) as f:
            summaries = json.load(f)
    for scenario, mode in runs:
        result = run_one(scenario, mode, tag=args.tag)
        if args.tag:
            result["tag"] = args.tag
            summaries = [s for s in summaries if s.get("tag") != args.tag]
        else:
            summaries = [s for s in summaries
                         if not (s["scenario"] == scenario and s["mode"] == mode
                                 and "tag" not in s)]
        summaries.append(result)
        with open(summary_path, "w") as f:
            json.dump(summaries, f, indent=2)
    print(f"summary written to {summary_path}")


if __name__ == "__main__":
    main()
