#!/usr/bin/env python3
"""Position-controlled real-gRPC replay checks using actual Qwen workers.

Manually orchestrates relayout or recovery at an accepted-token boundary.
This validates router replay, not heartbeat detection or controller downtime.
The router returns a final JSON token sequence; it does not stream tokens to
HTTP clients. Token timestamps describe internal acceptance, not delivery.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import random
import socket
import sys
import threading
import time
from unittest.mock import patch

from local_publication import Runtime, WORKER, reference


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--tokens", type=int, default=16)
    ap.add_argument("--positions", default="1,4,12")
    ap.add_argument("--concurrency", default="1,2")
    ap.add_argument("--model", default="Qwen/Qwen3-0.6B")
    ap.add_argument("--faults", default="relayout,worker-loss,worker-restart")
    ap.add_argument("--base-port", type=int, default=52000)
    args = ap.parse_args()
    positions = list(map(int, args.positions.split(",")))
    qs = list(map(int, args.concurrency.split(",")))
    faults = args.faults.split(",")
    if min(args.tokens, *positions, *qs) < 1 or max(positions) >= args.tokens:
        ap.error("positions must be within generated output")
    if any(f not in ("relayout", "worker-loss", "worker-restart") for f in faults):
        ap.error("unknown fault")
    args.out.mkdir(parents=True, exist_ok=True)
    if (args.out/"checks.jsonl").exists():
        ap.error("existing output; use a new directory")
    os.environ["KV_CACHE"] = "1"
    sys.path.insert(0, str(WORKER))
    import router
    import grpc
    pb, rpc = router.pb, router.rpc
    cpus = sorted(os.sched_getaffinity(0))
    rng = random.Random(20261007)
    prompt = [rng.randint(1, 1000) for _ in range(64)]
    expected = reference(args.model, {64: prompt}, args.tokens)["64"]
    metadata = {"evidence_type": "real-model single-host gRPC recovery correctness",
        "scope": "manual fault orchestration at a token boundary; controller and heartbeat recovery not measured",
        "positions": positions, "concurrency": qs, "faults": faults,
        "prompt": prompt, "expected_tokens": expected, "model": args.model,
        "tokens": args.tokens, "cpus": cpus, "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    (args.out/"manifest.json").write_text(json.dumps(metadata, indent=2)+"\n")
    all_ok = True
    with (args.out/"checks.jsonl").open("w", buffering=1) as output:
        for fault in faults:
            for q in qs:
                for position in positions:
                    directory = args.out/f"{fault}-q{q}-p{position}"
                    with Runtime("pipeline-2x1t", args.model, directory, cpus, args.base_port) as runtime:
                        # Runtime's initial pipeline is 18/10. Changing to
                        # 14/14 forces actual weights to reload on each worker.
                        def stages(layout):
                            return [pb.StageRef(name=f"w{i}", addr=f"127.0.0.1:{args.base_port+i}",
                                                start_layer=lo, end_layer=hi)
                                    for i, (lo, hi) in enumerate(layout)]
                        router.STATE = router.PipelineState()
                        router.STATE.set(stages([(0, 18), (18, 28)]), 0)
                        gate = threading.Lock()
                        triggered = False
                        event = {}
                        original = router._forward_chain
                        def forward(chain, generation, request_id, step, ids):
                            nonlocal triggered
                            inject = False
                            with gate:
                                if not triggered and step == position:
                                    triggered, inject = True, True
                            if inject:
                                event.update(fault=fault, after_tokens=position,
                                             started_monotonic=time.monotonic())
                                if fault == "worker-restart":
                                    runtime.processes[1].kill()
                                    runtime.processes[1].wait()
                                    process = runtime.spawn("worker-1-restarted", "server.py", {
                                        "PORT": str(args.base_port+1), "TORCH_THREADS": "1", "GRPC_HOST": "127.0.0.1",
                                        "INITIAL_ASSIGNMENT": f"18:28:28:qwen3:{args.model}"}, [cpus[1]])
                                    deadline = time.monotonic()+120
                                    while True:
                                        try:
                                            with socket.create_connection(("127.0.0.1", args.base_port+1), timeout=.1):
                                                break
                                        except OSError:
                                            if process.poll() is not None or time.monotonic()>deadline:
                                                raise RuntimeError("worker restart failed")
                                            time.sleep(.1)
                                else:
                                    layout = [(0, 14), (14, 28)] if fault == "relayout" else [(0, 28)]
                                    if fault == "worker-loss":
                                        runtime.processes[1].kill()
                                        runtime.processes[1].wait()
                                    for i, (lo, hi) in enumerate(layout):
                                        channel = grpc.insecure_channel(f"127.0.0.1:{args.base_port+i}", options=router.GRPC_OPTS)
                                        with channel:
                                            reply = rpc.WorkerStub(channel).AssignLayers(pb.AssignLayersRequest(
                                                start_layer=lo, end_layer=hi, total_layers=28, backend="qwen3",
                                                model=args.model, generation=1), timeout=90)
                                            if not reply.ok:
                                                raise RuntimeError(reply.error)
                                    router.STATE.set(stages(layout), 1)
                                event["orchestration_ms"] = (time.monotonic()-event["started_monotonic"])*1000
                            return original(chain, generation, request_id, step, ids)
                        with patch.object(router, "_forward_chain", side_effect=forward):
                            with ThreadPoolExecutor(max_workers=q) as pool:
                                futures = [pool.submit(router.generate, prompt, args.tokens) for _ in range(q)]
                                replies = []
                                for future in futures:
                                    try:
                                        replies.append(future.result(timeout=300))
                                    except Exception as error:
                                        replies.append({"error": str(error)})
                        success = triggered and all(r.get("tokens") == expected for r in replies) and any(r.get("replays", 0)>0 for r in replies)
                        for reply in replies:
                            times = reply.get("token_times_ms", [])
                            reply["max_token_gap_ms"] = max((b-a for a, b in zip(times, times[1:])), default=0)
                        row = {"fault": fault, "concurrency": q, "position": position,
                               "passed": success, "event": event, "replies": replies}
                        output.write(json.dumps(row)+"\n")
                        all_ok &= success
                        print(f"{fault} Q={q} position={position}: {'PASS' if success else 'FAIL'}", flush=True)
                        for channel in router.STATE._channels.values():
                            channel.close()
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
