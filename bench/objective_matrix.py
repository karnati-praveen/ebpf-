#!/usr/bin/env python3
"""Real-model objective comparison, run on the Azure coordinator.

Uses an alternate controller binary, existing workers, and an isolated repo.
Restores the old static single-worker coordinator and clears injected faults.
Run metadata explicitly labels objective. Results are exploratory.
"""
import argparse
import itertools
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import time
import urllib.request


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--controller", required=True)
    ap.add_argument("--original-repo", default="/home/azureuser/ebpf-")
    ap.add_argument("--seed", type=int, default=20261004)
    ap.add_argument("--matrix-kind", choices=["objective", "demand"], default="objective")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    repo = Path(__file__).resolve().parents[1]
    schedule = [(sc, obj, concurrency, rep) for sc, reps in (("stable:0", 3), ("network:120", 2))
                for obj, concurrency, rep in itertools.product(("latency", "throughput"), (1, 2), range(1, reps + 1))]
    if args.matrix_kind == "demand":
        schedule = [("stable:0", arm, c, rep) for arm,c,rep in itertools.product(("throughput", "auto-fixed", "auto-remaining"),(1,2),(1,2))]
    random.Random(args.seed).shuffle(schedule)
    (args.out / "schedule.json").write_text(json.dumps(schedule, indent=2))
    events = []
    (args.out / "provenance.json").write_text(json.dumps({"seed":args.seed,"model":"Qwen/Qwen3-0.6B",
        "controller_sha256":hashlib.sha256(Path(args.controller).read_bytes()).hexdigest(),
        "scope":"real-model exploratory objective comparison; no algorithmic novelty claim"},indent=2))
    env = dict(os.environ, CONTROLLER_BIN=args.controller)
    try:
        for i, (sc, obj, concurrency, rep) in enumerate(schedule, 1):
            print(f"MATRIX {i}/{len(schedule)} {sc} {obj} c{concurrency} r{rep}", flush=True)
            objective = "auto" if obj.startswith("auto-") else obj
            run_env = dict(env, REMAINING_WORK_AWARE="1" if obj=="auto-remaining" else "0",
                           WORKLOAD_URL="http://127.0.0.1:8080/workload" if objective=="auto" else "")
            cmd = ["python3", "-u", str(repo / "bench/vmrun.py"), "--workers", "2", "--hosts", "vm3", "--target", "vm3",
                   "--scenarios", sc, "--policies", "gate", "--objective", objective, "--concurrency", str(concurrency),
                   "--repeats", "1", "--repeat-offset", str(rep - 1), "--seed", str(args.seed + i),
                   "--prompt-len", "64", "--new-tokens", "64" if args.matrix_kind=="demand" else "32", "--context-len", "128", "--warmup-requests", "1",
                   "--pre-s", "10", "--fault-s", "40", "--post-s", "10", "--drain-s", "120",
                   "--remote-repo", args.original_repo, "--out", str(args.out / "runs")]
            if args.matrix_kind == "demand":
                cmd += ["--correctness-reference", str(args.out / "correctness-reference.json")]
            start = time.time()
            before = set((args.out / "runs").glob("*/meta.json"))
            p = subprocess.run(cmd, env=run_env, timeout=480)
            events.append({"index": i, "scenario": sc, "objective": obj, "concurrency": concurrency, "repeat": rep,
                           "start": start, "end": time.time(), "returncode": p.returncode})
            (args.out / "events.json").write_text(json.dumps(events, indent=2))
            after = set((args.out / "runs").glob("*/meta.json"))
            if p.returncode or len(after-before) != 1:
                raise RuntimeError(f"matrix run {i} failed")
    finally:
        print("Restoring original coordinator and clearing vm3 network fault", flush=True)
        subprocess.run(["ssh", "vm3", args.original_repo + "/deploy/standalone/fault.sh clear"], timeout=30, check=True)
        # Match the state left by the completed single-device baseline. The
        # old source and controller binary were never overwritten.
        restore_env = dict(os.environ, STATIC_MODE="1", CONTEXT_LEN="128", ROUTER="1", POLICY="hysteresis")
        restore_env.pop("CONTROLLER_BIN", None)
        restore_env.pop("PLACEMENT_OBJECTIVE", None)
        # The standalone worker count is a readiness minimum, not a cap.
        # Pause only vm3 heartbeats while the old static controller freezes its
        # initial single-worker layout; leave inference workers running.
        agent_query = subprocess.run(["ssh", "vm3", "pgrep", "-x", "nodeagent"],
                                     capture_output=True, text=True, timeout=30)
        if agent_query.returncode not in (0, 1):
            raise RuntimeError("cannot discover vm3 agent for coordinator restoration")
        agents = agent_query.stdout.split()
        if not all(pid.isdigit() for pid in agents):
            raise RuntimeError("invalid vm3 agent process IDs")
        try:
            if agents:
                subprocess.run(["ssh", "vm3", "sudo", "kill", "-STOP", *agents], timeout=30, check=True)
            subprocess.run([args.original_repo + "/deploy/standalone/start-coordinator.sh", "1"], env=restore_env, timeout=60, check=True)
            for _ in range(15):
                time.sleep(1)
                try:
                    with urllib.request.urlopen("http://127.0.0.1:8081/state", timeout=2) as response:
                        state = json.load(response)
                    if state.get("static") and len(state.get("assignments") or []) == 1:
                        break
                except (OSError, ValueError):
                    pass
            else:
                raise RuntimeError("original single-worker layout was not restored")
        finally:
            if agents:
                subprocess.run(["ssh", "vm3", "sudo", "kill", "-CONT", *agents], timeout=30, check=True)
        print("Original coordinator restored", flush=True)
    print("MATRIX COMPLETE", flush=True)


if __name__ == "__main__":
    main()
