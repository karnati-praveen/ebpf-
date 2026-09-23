#!/usr/bin/env python3
"""Experiment driver for the standalone (no Kubernetes) deployment.

Runs on the COORDINATOR VM (VM1). Faults are injected on worker VMs over SSH
with deploy/standalone/fault.sh, so they degrade a pipeline stage and never
the control path.

Each run:
  1. clears every fault on every worker VM (restoring a lost node if needed)
  2. restarts the controller AND router with this run's policy and link
     source, so no state -- generation, app-link averages -- carries over
  3. waits for the controller to assign every worker, then warms up
  4. drives closed-loop load at the given concurrency
  5. samples controller /state once a second (layout, predictions, speeds,
     link measurements by source, and every recorded decision)
  6. pre-fault phase -> fault on -> fault phase -> fault off -> recovery phase,
     recording fault on/off with both local and remote timestamps
  7. records node-agent CPU time on every VM before and after (H3 overhead)

Run order across a matrix is shuffled with a fixed seed, so repeats are
counterbalanced and the schedule is reproducible. Nothing is overwritten:
every run gets its own directory.

  python3 bench/vmrun.py --workers 2 --hosts vm2 --target vm2 \\
      --scenarios network:120,compute:1.0,stable:0,loss:0 \\
      --policies static,none,hysteresis,gate,gate-force --repeats 3 --out results/

Single-device baseline: stop the worker nodes on VM2/VM3, then run with
--workers 1 --scenarios stable:0 --policies static.
"""

import argparse
import csv
import json
import os
import random
import subprocess
import sys
import threading
import time
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPLOY = os.path.join(REPO, "deploy", "standalone")

POLICIES = {
    # name        -> controller environment
    "static":      {"STATIC_MODE": "1", "POLICY": "hysteresis"},   # initial-optimized, never moves
    "profileonly": {"PROFILE_ONCE": "1", "POLICY": "hysteresis"},  # internal ablation only
    "none":        {"POLICY": "none"},
    "hysteresis":  {"POLICY": "hysteresis"},
    "gate":        {"POLICY": "gate"},
    "gate-force":  {"POLICY": "gate-force"},
}

SCENARIOS = {"stable", "compute", "contention", "network", "loss"}


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def http_json(url, body=None, timeout=10):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def ssh(host, cmd, check=True):
    """Run a command on a worker VM. Requires key-based SSH from VM1."""
    full = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=10", host, cmd]
    p = subprocess.run(full, capture_output=True, text=True, timeout=600)
    if check and p.returncode != 0:
        raise RuntimeError(f"ssh {host} {cmd!r} failed ({p.returncode}): {p.stderr.strip()}")
    return p.stdout


def fault_events(output):
    """Parse 'FAULT_EVENT <epoch> <what>' lines printed by fault.sh."""
    out = []
    for line in output.splitlines():
        if line.startswith("FAULT_EVENT "):
            _, ts, what = line.split(" ", 2)
            out.append((float(ts), what))
    return out


def private_ip():
    out = subprocess.run(["ip", "-4", "route", "get", "1.1.1.1"], capture_output=True, text=True).stdout
    parts = out.split()
    return parts[parts.index("src") + 1] if "src" in parts else ""


def agent_cpu_seconds(host, local):
    """Cumulative CPU seconds used by the node agent on a VM (utime+stime)."""
    cmd = ("pid=$(pgrep -x nodeagent | head -1); [ -n \"$pid\" ] && "
           "awk -v hz=$(getconf CLK_TCK) '{print ($14+$15)/hz}' /proc/$pid/stat || echo nan")
    try:
        out = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True).stdout if local \
            else ssh(host, cmd, check=False)
        return float(out.strip() or "nan")
    except Exception:
        return float("nan")


# ----------------------------------------------------------------------------
# one run
# ----------------------------------------------------------------------------
class Run:
    def __init__(self, args, scenario, magnitude, policy, repeat):
        self.a = args
        self.scenario, self.magnitude, self.policy, self.repeat = scenario, magnitude, policy, repeat
        stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
        mag = f"-{magnitude}" if scenario != "stable" else ""
        cm = "" if args.cost_model == "full" else f"_{args.cost_model}"
        self.name = (f"{scenario}{mag}_{policy}_{args.link_source}{cm}"
                     f"_c{args.concurrency}_r{repeat}_{stamp}")
        self.dir = os.path.join(args.out, self.name)
        os.makedirs(self.dir, exist_ok=False)
        self.router = f"http://127.0.0.1:{args.router_port}"
        self.ctrl = f"http://127.0.0.1:{args.controller_port}"
        self.requests, self.series, self.decisions, self.faults = [], [], {}, []
        self.stop = threading.Event()
        self.lock = threading.Lock()

    # -- setup ----------------------------------------------------------------
    # Prints the worker's PID if it is running, else "dead".
    WORKER_PID = ('f=${KEINFER_STATE:-$HOME/keinfer}/pids/worker.child; '
                  '[ -f "$f" ] && p=$(cat "$f") && kill -0 "$p" 2>/dev/null && echo "$p" || echo dead')

    def worker_pids(self):
        """Worker PID on every VM, VM1 included. Compared at the start and end
        of a run: a change means a worker died or restarted mid-run."""
        local = subprocess.run(["bash", "-c", self.WORKER_PID], capture_output=True,
                               text=True).stdout.strip()
        out = {"local": local}
        for h in self.a.hosts:
            out[h] = ssh(h, self.WORKER_PID, check=False).strip()
        return out

    def reset_cluster(self):
        coord = private_ip()
        # Check workers are actually running rather than trusting what an
        # earlier run intended: a run that failed mid-loss leaves one stopped,
        # and memory pressure can kill one. VM1's own worker is checked too.
        pids = self.worker_pids()
        if pids["local"] == "dead":
            print("    restoring stopped local node")
            subprocess.run([os.path.join(DEPLOY, "start-worker-node.sh"), coord], check=True,
                           stdout=subprocess.DEVNULL)
        for h in self.a.hosts:
            ssh(h, f"{self.a.remote_repo}/deploy/standalone/fault.sh clear", check=False)
            if pids[h] == "dead":
                print(f"    restoring stopped node on {h}")
                ssh(h, f"{self.a.remote_repo}/deploy/standalone/start-worker-node.sh {coord}")

    def restart_coordinator(self):
        env = dict(os.environ)
        env.update(POLICIES[self.policy])
        env.update({"LINK_SOURCE": self.a.link_source, "CONTEXT_LEN": str(self.a.context_len),
                    "COST_MODEL": self.a.cost_model, "ROUTER": "1"})
        for k in ("GATE_HORIZON_S", "GATE_MARGIN", "COOLDOWN_S", "IMPROVEMENT_FRAC"):
            v = getattr(self.a, k.lower())
            if v is not None:
                env[k] = str(v)
        subprocess.run([os.path.join(DEPLOY, "start-coordinator.sh"), str(self.a.workers)],
                       env=env, check=True, stdout=subprocess.DEVNULL)

    def wait_ready(self, timeout=600):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                st = http_json(f"{self.ctrl}/state", timeout=3)
                pl = http_json(f"{self.router}/pipeline", timeout=3)
                n_assigned = sum(1 for a in (st.get("assignments") or []) if a["end"] > a["start"])
                if len(st.get("assignments") or []) == self.a.workers and \
                        len(pl.get("stages") or []) == n_assigned and n_assigned > 0:
                    return st
            except Exception:
                pass
            time.sleep(2)
        raise RuntimeError("controller/router never became ready")

    def warmup(self):
        # Enough decode steps for every worker's speed probe to settle and for
        # first-call costs (allocator, thread pools) to be paid before t0.
        for _ in range(self.a.warmup_requests):
            http_json(f"{self.router}/generate",
                      {"prompt_len": self.a.prompt_len, "max_new_tokens": 16}, timeout=900)

    # -- load and sampling --------------------------------------------------------
    def load_worker(self):
        while not self.stop.is_set():
            t0 = time.time()
            row = {"t_start": t0}
            try:
                o = http_json(f"{self.router}/generate",
                              {"prompt_len": self.a.prompt_len, "max_new_tokens": self.a.new_tokens},
                              timeout=1800)
                n = len(o["tokens"])
                row.update(ok=1, tokens=n, ttft_ms=o["ttft_ms"], duration_ms=o["duration_ms"],
                           itl_ms=((o["duration_ms"] - o["ttft_ms"]) / (n - 1)) if n > 1 else "",
                           replays=o["replays"], transition_ms=o.get("transition_ms", ""),
                           reconstruct_ms=o.get("reconstruct_ms", ""), generation=o["generation"],
                           error="")
            except Exception as e:
                row.update(ok=0, tokens=0, ttft_ms="", duration_ms=(time.time() - t0) * 1000,
                           itl_ms="", replays="", transition_ms="", reconstruct_ms="",
                           generation="", error=str(e)[:200])
                time.sleep(1)
            row["t_end"] = time.time()
            with self.lock:
                self.requests.append(row)

    def sampler(self):
        while not self.stop.is_set():
            t = time.time()
            row = {"t": t}
            try:
                st = http_json(f"{self.ctrl}/state", timeout=3)
                row.update(
                    generation=st.get("generation"),
                    bottleneck_ms=st.get("bottleneck_ms", ""),
                    pipeline_ms=st.get("pipeline_ms", ""),
                    layout="|".join(f"{a['node']}:{a['start']}-{a['end']}"
                                    for a in (st.get("assignments") or [])),
                    speeds="|".join(f"{n}:{v.get('speed_factor')}"
                                    for n, v in sorted(st["telemetry"]["nodes"].items())),
                    flows_json=json.dumps(st["telemetry"]["flows"], sort_keys=True,
                                          separators=(",", ":")),
                    last_error=st.get("last_error", ""))
                for d in st.get("decisions") or []:
                    self.decisions[d["time"]] = d
            except Exception as e:
                row["last_error"] = f"sample failed: {e}"
            with self.lock:
                self.series.append(row)
            time.sleep(max(0.0, 1.0 - (time.time() - t)))

    # -- faults -----------------------------------------------------------------
    def fault(self, action):
        s, m, tgt = self.scenario, self.magnitude, self.a.target
        f = f"{self.a.remote_repo}/deploy/standalone/fault.sh"
        if s == "stable":
            cmd = None
        elif action == "on":
            cmd = {"compute": f"{f} compute {m}", "contention": f"{f} contention {int(m)}",
                   "network": f"{f} network {m}", "loss": f"{f} loss"}[s]
        else:
            cmd = f"{f} restore {private_ip()}" if s == "loss" else f"{f} clear"
        t_local = time.time()
        out = ssh(tgt, cmd) if cmd else ""
        ev = fault_events(out)
        self.faults.append({"action": action, "t_local": t_local,
                            "t_remote": ev[0][0] if ev else "", "detail": ev[0][1] if ev else "none"})

    # -- orchestration -----------------------------------------------------------
    def execute(self):
        print(f"\n=== {self.name}")
        self.reset_cluster()
        self.restart_coordinator()
        st0 = self.wait_ready()
        print(f"    ready: gen={st0.get('generation')} layout="
              + "|".join(f"{a['node']}:{a['start']}-{a['end']}" for a in st0['assignments']))
        self.warmup()

        hosts = [(h, False) for h in self.a.hosts] + [("local", True)]
        cpu0 = {h: agent_cpu_seconds(h, loc) for h, loc in hosts}
        self.pids_start = self.worker_pids()

        threads = [threading.Thread(target=self.sampler, daemon=True)]
        threads += [threading.Thread(target=self.load_worker, daemon=True)
                    for _ in range(self.a.concurrency)]
        t0 = time.time()
        for th in threads:
            th.start()
        time.sleep(self.a.pre_s)
        self.fault("on")
        time.sleep(self.a.fault_s)
        self.fault("off")
        time.sleep(self.a.post_s)
        t_end = time.time()
        self.stop.set()
        for th in threads[1:]:
            th.join(timeout=self.a.drain_s)
        cpu1 = {h: agent_cpu_seconds(h, loc) for h, loc in hosts}
        self.pids_end = self.worker_pids()

        # A worker whose PID changed or which is dead at the end died mid-run.
        # In a loss run that is expected for the target only (it is restored
        # with a new PID); anywhere else the run measured an unrelated failure
        # and must not be pooled with clean runs.
        unexpected = []
        for h, p0 in self.pids_start.items():
            if p0 != self.pids_end.get(h):
                if self.scenario == "loss" and h == self.a.target:
                    continue
                unexpected.append(h)
        self.contaminated = unexpected

        self.write(t0, t_end, st0, cpu0, cpu1)
        ok = sum(r["ok"] for r in self.requests)
        flag = f"  CONTAMINATED: worker restarted on {self.contaminated}" if self.contaminated else ""
        print(f"    done: {ok}/{len(self.requests)} requests ok, "
              f"{len(self.decisions)} decisions -> {self.dir}{flag}")

    def write(self, t0, t_end, st0, cpu0, cpu1):
        def dump(name, rows, fields):
            with open(os.path.join(self.dir, name), "w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
                w.writeheader()
                for r in rows:
                    w.writerow(r)

        dump("requests.csv", self.requests,
             ["t_start", "t_end", "ok", "tokens", "ttft_ms", "itl_ms", "duration_ms", "replays",
              "transition_ms", "reconstruct_ms", "generation", "error"])
        dump("series.csv", self.series,
             ["t", "generation", "bottleneck_ms", "pipeline_ms", "layout", "speeds", "flows_json",
              "last_error"])
        dump("faults.csv", self.faults, ["action", "t_local", "t_remote", "detail"])
        with open(os.path.join(self.dir, "decisions.json"), "w") as fh:
            json.dump([self.decisions[k] for k in sorted(self.decisions)], fh, indent=1)
        meta = {
            "run": self.name, "scenario": self.scenario, "magnitude": self.magnitude,
            "policy": self.policy, "policy_env": POLICIES[self.policy],
            "link_source": self.a.link_source, "cost_model": self.a.cost_model,
            "kv_cache": os.environ.get("KV_CACHE", "1"), "repeat": self.repeat,
            "workers": self.a.workers, "target": self.a.target, "hosts": self.a.hosts,
            "concurrency": self.a.concurrency, "prompt_len": self.a.prompt_len,
            "new_tokens": self.a.new_tokens, "context_len": self.a.context_len,
            "phases_s": {"pre": self.a.pre_s, "fault": self.a.fault_s, "post": self.a.post_s},
            "t0": t0, "t_end": t_end,
            "gate": {"horizon_s": self.a.gate_horizon_s, "margin": self.a.gate_margin},
            "initial_state": {k: st0.get(k) for k in ("generation", "assignments",
                                                       "bottleneck_ms", "pipeline_ms")},
            "agent_cpu_s": {h: {"start": cpu0[h], "end": cpu1[h]} for h in cpu0},
            "worker_pids": {"start": self.pids_start, "end": self.pids_end},
            "contaminated_by_unexpected_worker_restart": self.contaminated,
            "git": subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"],
                                  capture_output=True, text=True).stdout.strip(),
        }
        with open(os.path.join(self.dir, "meta.json"), "w") as fh:
            json.dump(meta, fh, indent=2)


def parse_scenarios(spec):
    out = []
    for part in spec.split(","):
        name, _, mag = part.partition(":")
        if name not in SCENARIOS:
            sys.exit(f"unknown scenario {name!r}; choose from {sorted(SCENARIOS)}")
        out.append((name, mag or "0"))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, required=True)
    ap.add_argument("--hosts", default="", help="comma-separated SSH hosts of worker VMs (not VM1)")
    ap.add_argument("--target", default="", help="SSH host to inject faults on")
    ap.add_argument("--scenarios", required=True, help="e.g. network:120,compute:1.0,stable:0,loss:0")
    ap.add_argument("--policies", default="static,none,hysteresis,gate,gate-force")
    ap.add_argument("--link-source", default="ebpf+app", choices=["ebpf", "app", "ebpf+app", "none"])
    ap.add_argument("--cost-model", default="full", choices=["full", "layer-proportional"],
                    help="ablation A9/A10: drop endpoint and context-dependent cost terms")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--seed", type=int, default=20260923)
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--prompt-len", type=int, default=64)
    ap.add_argument("--new-tokens", type=int, default=64)
    ap.add_argument("--context-len", type=int, default=128,
                    help="operating context for the cost model; match prompt_len + new_tokens")
    ap.add_argument("--pre-s", type=float, default=60)
    ap.add_argument("--fault-s", type=float, default=120)
    ap.add_argument("--post-s", type=float, default=90)
    ap.add_argument("--drain-s", type=float, default=300)
    ap.add_argument("--warmup-requests", type=int, default=3)
    ap.add_argument("--gate-horizon-s", type=float, default=None)
    ap.add_argument("--gate-margin", type=float, default=None)
    ap.add_argument("--cooldown-s", type=float, default=None)
    ap.add_argument("--improvement-frac", type=float, default=None)
    ap.add_argument("--router-port", type=int, default=8080)
    ap.add_argument("--controller-port", type=int, default=8081)
    ap.add_argument("--remote-repo", default=REPO, help="repo path on the worker VMs")
    ap.add_argument("--out", default=os.path.join(REPO, "bench", "results", "vm"))
    ap.add_argument("--dry-run", action="store_true", help="print the shuffled schedule and exit")
    args = ap.parse_args()

    args.hosts = [h for h in args.hosts.split(",") if h]
    scenarios = parse_scenarios(args.scenarios)
    policies = [p for p in args.policies.split(",") if p]
    for p in policies:
        if p not in POLICIES:
            sys.exit(f"unknown policy {p!r}; choose from {sorted(POLICIES)}")
    if any(s != "stable" for s, _ in scenarios) and not args.target:
        sys.exit("--target is required for fault scenarios")
    if args.target and args.target not in args.hosts:
        sys.exit("--target must be one of --hosts")

    schedule = [(s, m, p, r) for s, m in scenarios for p in policies
                for r in range(1, args.repeats + 1)]
    random.Random(args.seed).shuffle(schedule)
    print(f"{len(schedule)} runs, seed {args.seed}; est. "
          f"{len(schedule) * (args.pre_s + args.fault_s + args.post_s + 90) / 3600:.1f} h")
    for i, (s, m, p, r) in enumerate(schedule, 1):
        print(f"  {i:3d}. {s}:{m} {p} r{r}")
    if args.dry_run:
        return 0

    os.makedirs(args.out, exist_ok=True)
    for s, m, p, r in schedule:
        try:
            Run(args, s, m, p, r).execute()
        except Exception as e:
            # A failed run is recorded, never silently skipped.
            print(f"    RUN FAILED: {e}")
            with open(os.path.join(args.out, "failed_runs.log"), "a") as fh:
                fh.write(f"{time.time()} {s}:{m} {p} r{r} {e}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
