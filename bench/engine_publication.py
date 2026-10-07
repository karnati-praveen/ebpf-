#!/usr/bin/env python3
"""Separate optimized-engine campaign with the baseline matrix's exact prompts.

Uses F32 GGUF weights and F32 KV cache, a pinned llama.cpp executable, two
compute threads, and continuous batching. Records all mismatches. Campaign
blocks are not paired in time with the earlier same-runtime experiment.
"""
import argparse
import fcntl
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import random
import statistics
import subprocess
import time
import urllib.request
from local_publication import load_checkpoint, write_completion


def completion(url, prompt, tokens):
    body = {"prompt": prompt, "n_predict": tokens, "temperature": 0,
            "repeat_penalty": 1, "presence_penalty": 0, "frequency_penalty": 0,
            "seed": 20261007, "ignore_eos": True, "cache_prompt": False,
            "return_tokens": True, "stream": False}
    req = urllib.request.Request(url+"/completion", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as reply:
        return json.load(reply)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--server", type=Path, required=True)
    ap.add_argument("--gguf", type=Path, required=True)
    ap.add_argument("--engine-commit", required=True)
    ap.add_argument("--repetitions", type=int, default=10)
    ap.add_argument("--port", type=int, default=53000)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()
    source = json.loads((args.source/"manifest.json").read_text())
    expected = json.loads((args.source/"reference.json").read_text())
    prompts = source["prompts"]
    conditions = [(int(c), q) for c in prompts for q in (1, 2, 4, 8)]
    cpus = sorted(os.sched_getaffinity(0))
    if cpus != source["cpus"]:
        ap.error("optimized engine must retain the source campaign's CPU affinity")
    args.out.mkdir(parents=True, exist_ok=True)
    lock = (args.out/".driver.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        ap.error("another driver is live in this directory")
    if (args.out/"runs.jsonl").exists() and not args.resume:
        ap.error("output already exists")
    if not json.loads((args.source/"completion-status.json").read_text())["complete"]:
        ap.error("baseline source matrix is incomplete")
    schedule = []
    rng = random.Random(20261007)
    for repeat in range(args.repetitions):
        order = conditions[:]
        rng.shuffle(order)
        schedule.append({"mode": "llama.cpp-F32-2t", "repetition": repeat, "conditions": order})
    command = [str(args.server.resolve()), "-m", str(args.gguf.resolve()),
        "--host", "127.0.0.1", "--port", str(args.port), "-t", "2", "-tb", "2",
        "--cpu-range", f"{cpus[0]}-{cpus[1]}", "--cpu-strict", "1",
        "--cpu-range-batch", f"{cpus[0]}-{cpus[1]}", "--cpu-strict-batch", "1",
        "-np", "8", "-c", "2048", "-b", "128", "-ub", "128", "-ngl", "0",
        "-ctk", "f32", "-ctv", "f32", "-fa", "off", "--no-warmup"]
    manifest = {"evidence_type": "real-model single-host optimized engine; separate campaign",
        "cpu": next(line.split(":", 1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
                    if line.startswith("model name")),
        "engine_commit": args.engine_commit, "server_command": command,
        "weights": "F32 GGUF converted from same pinned Qwen3 checkpoint; no weight quantization",
        "kv_precision": "F32", "batching": "llama.cpp continuous batching; eight slots",
        "source_manifest_sha256": hashlib.sha256((args.source/"manifest.json").read_bytes()).hexdigest(),
        "server_sha256": hashlib.sha256(args.server.read_bytes()).hexdigest(),
        "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "gguf_sha256": hashlib.file_digest(args.gguf.open("rb"), "sha256").hexdigest(),
        "cpus": cpus, "compute_cpus": cpus[:2], "prompts": prompts, "schedule": schedule,
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scope": "practical optimized serving alternative, not an algorithm ablation; different HTTP/compute implementation"}
    completed = set()
    epoch = 0
    if args.resume:
        original = json.loads((args.out/"manifest.json").read_text())
        for key in ("engine_commit", "cpu", "server_command", "source_manifest_sha256", "server_sha256",
                    "driver_sha256", "gguf_sha256", "cpus", "compute_cpus", "prompts", "schedule"):
            if original[key] != manifest[key]:
                ap.error(f"resume environment or measured code changed: {key}")
        completed = load_checkpoint(args.out/"runs.jsonl", schedule)
        path = args.out/"resumes.jsonl"
        epoch = len(path.read_text().splitlines())+1 if path.exists() else 1
        with path.open("a") as f:
            f.write(json.dumps({"execution_epoch": epoch, "completed_before_resume": len(completed),
                "resumed_utc": manifest["started_utc"]})+"\n")
    else:
        (args.out/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
        (args.out/"reference.json").write_text(json.dumps(expected, indent=2)+"\n")
        (args.out/"driver-source.py").write_bytes(Path(__file__).read_bytes())
    url = f"http://127.0.0.1:{args.port}"
    with (args.out/"runs.jsonl").open("a" if args.resume else "w", buffering=1) as output:
        for block in schedule:
            missing = [(c, q) for c, q in block["conditions"]
                       if (block["mode"], block["repetition"], c, q) not in completed]
            if not missing:
                continue
            with (args.out/f"server-r{block['repetition']:02d}-epoch{epoch}.log").open("w") as log:
                process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
                try:
                    deadline = time.monotonic()+120
                    while True:
                        try:
                            with urllib.request.urlopen(url+"/health", timeout=1):
                                break
                        except Exception:
                            if process.poll() is not None or time.monotonic()>deadline:
                                raise RuntimeError("engine startup failed; see server log")
                            time.sleep(.2)
                    completion(url, [17, 29, 43], 4)
                    for context, q in missing:
                        prompt, golden = prompts[str(context)], expected[str(context)]
                        def request(index):
                            started = time.monotonic()
                            try:
                                reply = completion(url, prompt, len(golden))
                                tokens = reply.get("tokens", [])
                                match = tokens == golden
                                return {"index": index, "ok": len(tokens) == len(golden),
                                    "exact_reference_match": match,
                                    "client_duration_ms": (time.monotonic()-started)*1000,
                                    "reply": reply}
                            except Exception as error:
                                return {"index": index, "ok": False, "error": str(error),
                                    "client_duration_ms": (time.monotonic()-started)*1000}
                        started = time.monotonic()
                        with ThreadPoolExecutor(max_workers=q) as pool:
                            rows = list(pool.map(request, range(max(4, q))))
                        duration = time.monotonic()-started
                        completed = [r for r in rows if r["ok"]]
                        result = {"mode": "llama.cpp-F32-2t", "repetition": block["repetition"],
                            "execution_epoch": epoch,
                            "context": context, "concurrency": q, "output_tokens": len(golden),
                            "whole_run_s": duration, "whole_run_tps": sum(len(r["reply"]["tokens"]) for r in completed)/duration,
                            "failures": len(rows)-len(completed),
                            "reference_mismatches": sum(not r.get("exact_reference_match", False) for r in completed),
                            "median_client_duration_ms": statistics.median(r["client_duration_ms"] for r in rows),
                            "median_ttft_ms": None, "requests": rows}
                        output.write(json.dumps(result)+"\n")
                        output.flush()
                        os.fsync(output.fileno())
                        completed.add((block["mode"], block["repetition"], context, q))
                        write_completion(args.out, len(completed), sum(len(b["conditions"]) for b in schedule))
                        print(f"r={block['repetition']} C={context} Q={q}: {result['whole_run_tps']:.3f} TPS failures={result['failures']} mismatches={result['reference_mismatches']}", flush=True)
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
    write_completion(args.out, len(completed), sum(len(b["conditions"]) for b in schedule))


if __name__ == "__main__":
    main()
