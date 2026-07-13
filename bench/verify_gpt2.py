#!/usr/bin/env python3
"""Correctness proof for the distributed GPT-2 pipeline: greedy tokens from
the 3-stage distributed run must be identical to single-process HuggingFace
greedy decoding.

Runs locally (no cluster): spawns 3 workers + router as subprocesses.
Usage: python3 bench/verify_gpt2.py [--prompt "..."] [--tokens 12]
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKER_DIR = os.path.join(REPO, "worker")


def wait_http(url, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return
        except Exception:
            time.sleep(0.3)
    raise RuntimeError(f"timeout waiting for {url}")


def wait_port(port, timeout=180):
    """Workers accept connections only after their model shard is loaded."""
    import socket
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1).close()
            return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError(f"timeout waiting for port {port}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", default="The meaning of life is")
    ap.add_argument("--tokens", type=int, default=12)
    args = ap.parse_args()

    from transformers import GPT2Tokenizer, GPT2LMHeadModel
    import torch

    tok = GPT2Tokenizer.from_pretrained("gpt2")
    input_ids = tok.encode(args.prompt)

    # --- reference: single-process greedy ---
    model = GPT2LMHeadModel.from_pretrained("gpt2")
    model.eval()
    ref = list(input_ids)
    with torch.no_grad():
        for _ in range(args.tokens):
            logits = model(torch.tensor([ref])).logits
            ref.append(int(logits[0, -1].argmax()))
    ref_new = ref[len(input_ids):]
    print("reference :", ref_new, "|", tok.decode(ref_new))
    del model

    # --- distributed: 3 workers + router ---
    procs = []
    env_base = {**os.environ, "PYTHONUNBUFFERED": "1"}
    try:
        for i, (lo, hi) in enumerate([(0, 4), (4, 8), (8, 12)]):
            env = {**env_base,
                   "PORT": str(50071 + i),
                   "WORKER_NAME": f"v{i+1}",
                   "INITIAL_ASSIGNMENT": f"{lo}:{hi}:12:gpt2:gpt2"}
            procs.append(subprocess.Popen(
                [sys.executable, "server.py"], cwd=WORKER_DIR, env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT))
        stages = ",".join(
            f"v{i+1}=127.0.0.1:{50071+i}={lo}={hi}"
            for i, (lo, hi) in enumerate([(0, 4), (4, 8), (8, 12)]))
        env = {**env_base, "HTTP_PORT": "8090", "GRPC_PORT": "50079",
               "STATIC_PIPELINE": stages}
        procs.append(subprocess.Popen(
            [sys.executable, "router.py"], cwd=WORKER_DIR, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT))

        wait_http("http://127.0.0.1:8090/healthz")
        for i in range(3):
            wait_port(50071 + i)

        body = json.dumps({
            "input_ids": input_ids, "max_new_tokens": args.tokens,
        }).encode()
        req = urllib.request.Request(
            "http://127.0.0.1:8090/generate", data=body,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as r:
            out = json.load(r)
        dist_new = out["tokens"]
        print("distributed:", dist_new, "|", tok.decode(dist_new))
        print(f"ttft={out['ttft_ms']}ms tokens/sec={out['tokens_per_sec']}")

        if dist_new == ref_new:
            print("MATCH: distributed pipeline is token-identical to single-process GPT-2")
            return 0
        print("MISMATCH")
        return 1
    finally:
        for p in procs:
            p.send_signal(signal.SIGTERM)
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    sys.exit(main())
