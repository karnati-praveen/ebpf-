#!/usr/bin/env python3
"""Resource-accounted real-model baseline experiment on one Linux host.

All serving arms use the same FP32 Qwen backend, KV cache, HTTP/gRPC path,
greedy decoding and prompts. Whole-request first-available dispatch reserves
a replica until its request completes. This is a baseline dispatcher, not
continuous batching. Local loopback results cannot stand in for multi-host
network experiments. Each repetition restarts workers and randomizes arm order.
"""
import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
import fcntl
import gc
import hashlib
import json
import os
from pathlib import Path
import platform
import queue
import random
import socket
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "worker"
MODES = ("unsplit-1t", "unsplit-2t", "replicas-2x1t", "pipeline-2x1t")


def post(url, body):
    request = urllib.request.Request(url + "/generate", json.dumps(body).encode(),
                                    {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.load(response)


class Runtime:
    def __init__(self, mode, model, directory, cpus, base_port):
        self.mode, self.model, self.directory = mode, model, directory
        self.cpus, self.base_port = cpus, base_port
        self.processes, self.logs, self.urls = [], [], []
        self.process_names = []

    def spawn(self, name, script, settings, affinity):
        env = {**os.environ, "PYTHONUNBUFFERED": "1", "KV_CACHE": "1",
               "WORKER_DEVICE": "cpu", "KV_MAX_SESSIONS": "32",
               "HF_HUB_OFFLINE": "1", "TOKENIZERS_PARALLELISM": "false",
               "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", **settings}
        log = (self.directory / (name + ".log")).open("w")
        self.logs.append(log)
        # taskset avoids a Python preexec_fn in a multithreaded parent.
        process = subprocess.Popen(["taskset", "-c", ",".join(map(str, affinity)),
                                    sys.executable, str(WORKER / script)],
                                   cwd=WORKER, env=env, stdout=log, stderr=subprocess.STDOUT)
        self.processes.append(process)
        self.process_names.append(name)
        return process

    def memory_snapshot(self):
        rows = []
        for name, process in zip(self.process_names, self.processes):
            row = {"name": name, "pid": process.pid, "exit_code": process.poll()}
            try:
                status = Path(f"/proc/{process.pid}/status").read_text()
                for line in status.splitlines():
                    key, _, value = line.partition(":")
                    if key in ("VmRSS", "VmHWM", "Threads", "Cpus_allowed_list"):
                        row[key] = value.strip()
            except FileNotFoundError:
                row["unavailable"] = True
            rows.append(row)
        return rows

    def start(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        if self.mode.startswith("unsplit"):
            layouts = [(0, 28)]
        elif self.mode == "replicas-2x1t":
            layouts = [(0, 28), (0, 28)]
        else:
            layouts = [(0, 18), (18, 28)]
        for i, (lo, hi) in enumerate(layouts):
            threads = 2 if self.mode == "unsplit-2t" else 1
            affinity = self.cpus[:2] if threads == 2 else [self.cpus[i]]
            port = self.base_port + i
            self.spawn(f"worker-{i}", "server.py", {
                "PORT": str(port), "GRPC_HOST": "127.0.0.1", "TORCH_THREADS": str(threads),
                "INITIAL_ASSIGNMENT": f"{lo}:{hi}:28:qwen3:{self.model}"}, affinity)
        for i in range(len(layouts) if self.mode == "replicas-2x1t" else 1):
            stages = [(i, layouts[i])] if self.mode == "replicas-2x1t" else list(enumerate(layouts))
            self.spawn(f"router-{i}", "router.py", {
                "GRPC_PORT": str(self.base_port + 10 + i), "GRPC_HOST": "127.0.0.1",
                "HTTP_HOST": "127.0.0.1", "HTTP_PORT": str(self.base_port + 20 + i),
                "STATIC_PIPELINE": ",".join(f"w{j}=127.0.0.1:{self.base_port+j}={lo}={hi}"
                                              for j, (lo, hi) in stages)}, self.cpus[2:] or self.cpus)
            self.urls.append(f"http://127.0.0.1:{self.base_port+20+i}")
        deadline = time.monotonic() + 180
        pending = list(range(len(layouts)))
        while pending:
            for process in self.processes:
                if process.poll() is not None:
                    raise RuntimeError(f"runtime exited {process.returncode}; see {self.directory}")
            for i in pending[:]:
                try:
                    with socket.create_connection(("127.0.0.1", self.base_port+i), timeout=.1):
                        pending.remove(i)
                except OSError:
                    pass
            if time.monotonic() > deadline:
                raise TimeoutError("worker startup timed out")
            time.sleep(.1)
        for url in self.urls:
            # A warm generation also confirms router availability, cache mode
            # and usable model; readiness never resets worker statistics.
            for attempt in range(30):
                try:
                    post(url, {"input_ids": [17, 29, 43], "max_new_tokens": 4})
                    break
                except urllib.error.URLError:
                    if attempt == 29:
                        raise
                    time.sleep(.1)
        return self

    def close(self):
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
        for process in self.processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for log in self.logs:
            log.close()

    def __enter__(self):
        try:
            return self.start()
        except BaseException:
            self.close()
            raise

    def __exit__(self, *args):
        self.close()


def reference(model_name, prompts, tokens):
    import torch
    from transformers import AutoModelForCausalLM
    torch.set_num_threads(1)
    model = AutoModelForCausalLM.from_pretrained(model_name, dtype=torch.float32,
                                              attn_implementation="sdpa")
    model.eval()
    rows = {}
    with torch.inference_mode():
        for length, prompt in prompts.items():
            ids, cache, output = prompt, None, []
            for _ in range(tokens):
                result = model(torch.tensor([ids]), past_key_values=cache,
                               use_cache=True, logits_to_keep=1)
                token = int(result.logits[0, -1].argmax())
                output.append(token)
                ids, cache = [token], result.past_key_values
            rows[str(length)] = output
    del model, result, cache
    gc.collect()
    return rows


def trial(runtime, prompt, expected, concurrency, requests):
    memory_start = runtime.memory_snapshot()
    available = queue.Queue()
    for url in runtime.urls:
        available.put(url)
    def request(index):
        start = time.monotonic()
        # Only replica mode reserves an endpoint for a whole request. Pipeline
        # and unsplit arms interleave independent requests at the worker lock.
        url = available.get() if runtime.mode == "replicas-2x1t" else runtime.urls[0]
        dispatch_ms = (time.monotonic() - start) * 1000
        try:
            reply = post(url, {"input_ids": prompt, "max_new_tokens": len(expected)})
            times = reply.get("token_times_ms", [])
            gaps = [b-a for a, b in zip(times, times[1:])]
            return {"index": index, "ok": reply["tokens"] == expected,
                    "dispatch_wait_ms": dispatch_ms,
                    "client_duration_ms": (time.monotonic()-start)*1000,
                    "max_token_gap_ms": max(gaps, default=0), "reply": reply}
        except Exception as error:
            return {"index": index, "ok": False, "error": str(error),
                    "client_duration_ms": (time.monotonic()-start)*1000}
        finally:
            if runtime.mode == "replicas-2x1t":
                available.put(url)
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        rows = list(pool.map(request, range(requests)))
    elapsed = time.monotonic() - start
    successful = [row for row in rows if row["ok"]]
    return {"whole_run_s": elapsed, "requests": rows, "failures": len(rows)-len(successful),
            "processes_at_start": memory_start, "processes_at_end": runtime.memory_snapshot(),
            "whole_run_tps": sum(len(r["reply"]["tokens"]) for r in successful)/elapsed,
            "median_client_duration_ms": statistics.median(r["client_duration_ms"] for r in rows),
            "median_ttft_ms": statistics.median(r["dispatch_wait_ms"]+r["reply"]["ttft_ms"] for r in successful) if successful else None}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--model", default="Qwen/Qwen3-0.6B")
    ap.add_argument("--repetitions", type=int, default=10)
    ap.add_argument("--concurrency", default="1,2,4,8")
    ap.add_argument("--contexts", default="32")
    ap.add_argument("--tokens", type=int, default=16)
    ap.add_argument("--requests", type=int, default=8)
    ap.add_argument("--seed", type=int, default=20261007)
    ap.add_argument("--base-port", type=int, default=51000)
    ap.add_argument("--modes", default=",".join(MODES))
    ap.add_argument("--resume", action="store_true", help="resume only missing scheduled observations; preserve existing runs")
    args = ap.parse_args()
    modes, contexts, qs = args.modes.split(","), list(map(int, args.contexts.split(","))), list(map(int, args.concurrency.split(",")))
    if min(args.repetitions, args.tokens, args.requests, *contexts, *qs) < 1 or any(m not in MODES for m in modes):
        ap.error("positive sizes and supported modes required")
    cpus = sorted(os.sched_getaffinity(0))
    if len(cpus) < 2:
        ap.error("at least two allowed CPUs required")
    args.out.mkdir(parents=True, exist_ok=True)
    lock = (args.out/"driver.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        ap.error("a driver already owns this output directory")
    manifest_path = args.out / "manifest.json"
    if manifest_path.exists() and not args.resume:
        ap.error("output already contains a run; choose a new directory")
    if args.resume and not manifest_path.exists():
        ap.error("resume requires an existing manifest")
    rng = random.Random(args.seed)
    prompts = {c: [rng.randint(1, 1000) for _ in range(c)] for c in contexts}
    schedule = []
    for repetition in range(args.repetitions):
        order = modes[:]
        rng.shuffle(order)
        for mode in order:
            conditions = [(c, q) for c in contexts for q in qs]
            rng.shuffle(conditions)
            schedule.append({"repetition": repetition, "mode": mode, "conditions": conditions})
    import importlib.metadata
    manifest = {"schema": 1, "evidence_type": "real-model single-host loopback",
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": platform.platform(), "cpu": Path("/proc/cpuinfo").read_text().split("model name\t: ")[-1].splitlines()[0],
        "cpu_quota": Path("/sys/fs/cgroup/cpu.max").read_text().strip(),
        "cpus": cpus, "inference_cpu_budget": cpus[:2], "coordination_cpus": cpus[2:] or cpus,
        "packages": {p: importlib.metadata.version(p) for p in ("torch", "transformers", "grpcio", "numpy", "protobuf")},
        "arguments": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        "pipeline_layout": [[0, 18], [18, 28]], "precision": "FP32", "kv_cache": True,
        "prompts": prompts, "schedule": schedule,
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (Path(__file__), WORKER/"router.py", WORKER/"server.py", WORKER/"backends/qwen3.py", WORKER/"gen/pipeline_pb2.py")}}
    from huggingface_hub import try_to_load_from_cache
    cached_config = try_to_load_from_cache(args.model, "config.json")
    manifest["model_revision"] = Path(cached_config).parent.name if isinstance(cached_config, str) else None
    completed = set()
    epoch = 0
    if args.resume:
        original = json.loads(manifest_path.read_text())
        for key in ("model", "repetitions", "concurrency", "contexts", "tokens", "requests", "seed", "base_port", "modes"):
            if original["arguments"][key] != getattr(args, key):
                ap.error(f"resume argument changed: {key}")
        if original["packages"] != manifest["packages"] or original["cpus"] != cpus or original["cpu"] != manifest["cpu"]:
            ap.error("resume environment differs from the recorded package/CPU configuration")
        for name, digest in original["source_sha256"].items():
            if name == str(Path(__file__).relative_to(ROOT)):
                continue
            if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != digest:
                ap.error(f"serving source changed: {name}")
        # Checkpoint-only edits are allowed, but the measured Runtime and
        # trial bodies must remain byte-for-byte identical to the snapshot.
        snapshot = args.out/"source-snapshot"/"bench/local_publication.py"
        if not snapshot.exists():
            ap.error("resume requires the original driver source snapshot")
        def measured_code(path):
            source = path.read_text()
            return {node.name: ast.get_source_segment(source, node) for node in ast.parse(source).body
                    if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in ("Runtime", "trial", "post")}
        if measured_code(snapshot) != measured_code(Path(__file__)):
            ap.error("resume changed the measured serving/client code")
        prompts = {int(k): v for k, v in original["prompts"].items()}
        schedule = original["schedule"]
        expected = json.loads((args.out/"reference.json").read_text())
        completed = load_checkpoint(args.out/"runs.jsonl", schedule)
        resumes_path = args.out/"resumes.jsonl"
        epoch = len(resumes_path.read_text().splitlines())+1 if resumes_path.exists() else 1
        record = {"execution_epoch": epoch, "resumed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                  "completed_before_resume": len(completed), "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  "measured_code_unchanged": True, "reason": "previous driver not live; workspace restart"}
        with resumes_path.open("a") as f:
            f.write(json.dumps(record)+"\n")
        print(f"Resuming {len(completed)} completed scheduled runs, epoch {epoch}", flush=True)
    else:
        manifest_path.write_text(json.dumps(manifest, indent=2)+"\n")
        for name, digest in manifest["source_sha256"].items():
            destination = args.out/"source-snapshot"/name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((ROOT/name).read_bytes())
        expected = reference(args.model, prompts, args.tokens)
        (args.out/"reference.json").write_text(json.dumps(expected, indent=2)+"\n")
    with (args.out/"runs.jsonl").open("a" if args.resume else "w", buffering=1) as output:
        for block in schedule:
            mode, repetition = block["mode"], block["repetition"]
            missing = [(c, q) for c, q in block["conditions"] if (mode, repetition, c, q) not in completed]
            if not missing:
                continue
            directory = args.out / f"r{repetition:02d}-{mode}-epoch{epoch}"
            with Runtime(mode, args.model, directory, cpus, args.base_port) as runtime:
                for context, q in missing:
                    result = trial(runtime, prompts[context], expected[str(context)], q, max(args.requests, q))
                    result.update(mode=mode, repetition=repetition, context=context, concurrency=q, output_tokens=args.tokens, execution_epoch=epoch)
                    output.write(json.dumps(result)+"\n")
                    output.flush()
                    os.fsync(output.fileno())
                    completed.add((mode, repetition, context, q))
                    write_completion(args.out, len(completed), sum(len(b["conditions"]) for b in schedule))
                    print(f"r={repetition} {mode} C={context} Q={q}: {result['whole_run_tps']:.3f} TPS failures={result['failures']}", flush=True)
    write_completion(args.out, len(completed), sum(len(b["conditions"]) for b in schedule))
    print("Completed; analyze run-level results with bench/publication_analyze.py", flush=True)


def load_checkpoint(path, schedule):
    expected = {(b["mode"], b["repetition"], c, q) for b in schedule for c, q in b["conditions"]}
    completed = set()
    for line in path.read_text().splitlines() if path.exists() else []:
        row = json.loads(line)
        key = (row["mode"], row["repetition"], row["context"], row["concurrency"])
        if key not in expected or key in completed:
            raise ValueError(f"unscheduled or duplicated checkpoint row: {key}")
        completed.add(key)
    return completed


def write_completion(directory, completed, expected):
    pending = directory/"completion-status.pending"
    pending.write_text(json.dumps({"completed_runs": completed, "expected_runs": expected,
        "complete": completed == expected, "updated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, indent=2)+"\n")
    pending.replace(directory/"completion-status.json")


if __name__ == "__main__":
    main()
