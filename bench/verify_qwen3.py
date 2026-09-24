#!/usr/bin/env python3
"""Correctness proof for the distributed Qwen3 pipeline.

Two levels:

  --inprocess   Drives the worker backends directly (no gRPC). For several
                shard layouts and both KV_CACHE modes, compares teacher-forced
                last-position logits against single-process HuggingFace at every
                decode step, then compares free-running greedy tokens. Also
                exercises the cache protocol guards. Reports the maximum
                absolute logit difference -- not a pass/fail tolerance alone --
                so any drift is visible.

  (default)     End to end through real worker and router processes, as
                verify_gpt2.py does, in both KV_CACHE modes: distributed greedy
                tokens must equal single-process greedy tokens.

  --relayout    End to end in cached mode, repartitioning 14/14 -> 18/10 in the
                MIDDLE of a request, the way the controller does (workers first,
                then the router). Every stage must rebuild its cache on the new
                layout and the output must still equal the reference. Reports
                the measured transition and reconstruction time.

Usage:
  python3 bench/verify_qwen3.py --inprocess
  python3 bench/verify_qwen3.py [--tokens 24]
  python3 bench/verify_qwen3.py --relayout
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
MODEL = os.environ.get("QWEN_MODEL", "Qwen/Qwen3-0.6B")
PROMPT = "The key idea behind pipeline parallelism is"

# FP32 on CPU: two mathematically identical computations can still differ in
# the last bits when shapes differ (a batched prefill vs one incremental
# position). This bound is for REPORTING context only; the verdict is token
# equality plus logits that stay orders of magnitude below any argmax margin.
LOGIT_REPORT_BOUND = 1e-3

LAYOUTS = {
    "1 stage":     [(0, 28)],
    "14/14":       [(0, 14), (14, 28)],
    "7/21":        [(0, 7), (7, 28)],
    "21/7":        [(0, 21), (21, 28)],
    "9/9/10":      [(0, 9), (9, 18), (18, 28)],
    "7/7/7/7":     [(0, 7), (7, 14), (14, 21), (21, 28)],
}


def reference(tok, n_tokens):
    import torch
    from transformers import AutoModelForCausalLM

    device = "cuda" if os.environ.get("WORKER_DEVICE", "cpu") == "cuda" else "cpu"
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("WORKER_DEVICE=cuda but PyTorch cannot see the GPU")
    dtype = torch.float16 if device == "cuda" else torch.float32
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=dtype,
                                                 attn_implementation="sdpa").to(device)
    model.eval()
    prompt = tok.encode(PROMPT)
    ids = list(prompt)
    with torch.no_grad():
        for _ in range(n_tokens):
            ids.append(int(model(torch.tensor([ids], device=device)).logits[0, -1].argmax()))
        full_logits = model(torch.tensor([ids], device=device)).logits[0]
    gen = ids[len(prompt):]
    # Logits that predict gen[s] sit at position len(prompt) + s - 1.
    step_logits = [full_logits[len(prompt) + s - 1].float().cpu().clone() for s in range(n_tokens)]
    del model
    return prompt, gen, step_logits


# --------------------------------------------------------------------------
# in-process
# --------------------------------------------------------------------------
def _load_chain(layout, cached):
    os.environ["KV_CACHE"] = "1" if cached else "0"
    from backends.qwen3 import Qwen3Backend

    chain = []
    for lo, hi in layout:
        b = Qwen3Backend(MODEL)
        b.load(lo, hi, 28)
        chain.append(b)
    return chain


def _run_chain(chain, request_id, step, ids, pb):
    reply = None
    hidden, shape = b"", []
    for i, b in enumerate(chain):
        req = pb.ForwardRequest(request_id=request_id, step=step)
        if i == 0:
            req.input_ids.extend(ids)
        else:
            req.hidden = hidden
            req.shape.extend(shape)
        reply = b.forward(req)
        if reply.error:
            raise RuntimeError(f"stage {i}: {reply.error}")
        hidden, shape = reply.hidden, list(reply.shape)
    return reply


def inprocess(n_tokens):
    import torch
    from transformers import AutoTokenizer

    sys.path.insert(0, WORKER_DIR)
    sys.path.insert(0, os.path.join(WORKER_DIR, "gen"))
    import pipeline_pb2 as pb

    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(MODEL)
    prompt, ref_gen, ref_logits = reference(tok, n_tokens)
    print(f"prompt tokens={len(prompt)}  reference: {ref_gen}")
    print(f"                           {tok.decode(ref_gen)!r}\n")

    rows, all_ok = [], True
    print(f"{'layout':<9} {'mode':<9} {'max|dlogit|':>12} {'first step >bound':>18} "
          f"{'teacher argmax':>15} {'free-run tokens':>16}")
    for name, layout in LAYOUTS.items():
        for cached in (False, True):
            chain = _load_chain(layout, cached)
            captured = {}
            hook = chain[-1].lm_head.register_forward_hook(
                lambda m, i, o: captured.__setitem__("logits", o[0].detach().clone()))

            # teacher-forced: feed the REFERENCE tokens, compare logits
            max_d, first_bad, argmax_ok = 0.0, None, True
            rid = 1000
            for s in range(n_tokens):
                if cached and s > 0:
                    ids = [ref_gen[s - 1]]
                else:
                    ids = prompt + ref_gen[:s]
                r = _run_chain(chain, rid, s, ids, pb)
                d = float((captured["logits"].float().cpu() - ref_logits[s]).abs().max())
                max_d = max(max_d, d)
                if d > LOGIT_REPORT_BOUND and first_bad is None:
                    first_bad = s
                if r.next_token != ref_gen[s]:
                    argmax_ok = False

            # free-running greedy with our own tokens
            gen = []
            rid = 2000
            for s in range(n_tokens):
                ids = [gen[-1]] if (cached and s > 0) else prompt + gen
                gen.append(_run_chain(chain, rid, s, ids, pb).next_token)
            free_ok = gen == ref_gen

            hook.remove()
            ok = argmax_ok and free_ok
            all_ok &= ok
            mode = "cached" if cached else "stateless"
            print(f"{name:<9} {mode:<9} {max_d:>12.2e} "
                  f"{('-' if first_bad is None else str(first_bad)):>18} "
                  f"{('OK' if argmax_ok else 'MISMATCH'):>15} "
                  f"{('MATCH' if free_ok else 'MISMATCH'):>16}")
            rows.append(dict(layout=name, mode=mode, max_abs_logit_diff=max_d,
                             first_step_over_bound=first_bad,
                             teacher_argmax_ok=argmax_ok, free_run_match=free_ok))
            del chain

    print("\nprotocol guards:")
    guards_ok = _check_guards(prompt, pb)
    all_ok &= guards_ok

    out = os.path.join(os.getcwd(), "qwen3-shard-validation.json")
    with open(out, "w") as f:
        json.dump({"model": MODEL, "prompt": PROMPT, "tokens": n_tokens,
                   "reference": ref_gen, "rows": rows, "guards_ok": guards_ok}, f, indent=2)
    print(f"\nwrote {out}")
    print("ALL CHECKS PASSED" if all_ok else "FAILURES PRESENT")
    return 0 if all_ok else 1


def _check_guards(prompt, pb):
    def expect(label, reply, needle):
        ok = needle in (reply.error or "")
        print(f"  {'ok ' if ok else 'BAD'} {label}: {reply.error or '(no error)'}")
        return ok

    ok = True
    cached = _load_chain([(0, 28)], cached=True)[0]
    ok &= expect("decode step with no session",
                 cached.forward(pb.ForwardRequest(request_id=7, step=3, input_ids=[1])),
                 "kv cache miss")
    cached.forward(pb.ForwardRequest(request_id=8, step=0, input_ids=prompt))
    ok &= expect("out-of-order step",
                 cached.forward(pb.ForwardRequest(request_id=8, step=5, input_ids=[1])),
                 "kv cache step mismatch")
    ok &= expect("multi-position decode (router stateless, worker cached)",
                 cached.forward(pb.ForwardRequest(request_id=8, step=1, input_ids=[1, 2, 3])),
                 "kv cache protocol error")
    cached.forward(pb.ForwardRequest(request_id=9, step=0, input_ids=prompt))
    cached.load(0, 27, 28)  # a relayout must invalidate every cache
    ok &= expect("session after relayout",
                 cached.forward(pb.ForwardRequest(request_id=9, step=1, input_ids=[1])),
                 "kv cache miss")
    del cached

    stateless = _load_chain([(0, 28)], cached=False)[0]
    ok &= expect("single position at step 4 (router cached, worker stateless)",
                 stateless.forward(pb.ForwardRequest(request_id=1, step=4, input_ids=[1])),
                 "stateless worker got")
    return ok


# --------------------------------------------------------------------------
# end to end
# --------------------------------------------------------------------------
def _wait_http(url, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return
        except Exception:
            time.sleep(0.3)
    raise RuntimeError(f"timeout waiting for {url}")


def _wait_port(port, timeout=300):
    import socket
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1).close()
            return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError(f"timeout waiting for port {port}")


def end_to_end(n_tokens, cached, prompt, ref_gen):
    layout = [(0, 14), (14, 28)]
    procs = []
    env_base = {**os.environ, "PYTHONUNBUFFERED": "1", "KV_CACHE": "1" if cached else "0"}
    try:
        for i, (lo, hi) in enumerate(layout):
            env = {**env_base, "PORT": str(50171 + i), "WORKER_NAME": f"q{i}",
                   "INITIAL_ASSIGNMENT": f"{lo}:{hi}:28:qwen3:{MODEL}"}
            procs.append(subprocess.Popen([sys.executable, "server.py"], cwd=WORKER_DIR,
                                          env=env, stdout=subprocess.DEVNULL,
                                          stderr=subprocess.STDOUT))
        stages = ",".join(f"q{i}=127.0.0.1:{50171 + i}={lo}={hi}"
                          for i, (lo, hi) in enumerate(layout))
        procs.append(subprocess.Popen(
            [sys.executable, "router.py"], cwd=WORKER_DIR,
            env={**env_base, "HTTP_PORT": "8190", "GRPC_PORT": "50179",
                 "STATIC_PIPELINE": stages},
            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT))
        _wait_http("http://127.0.0.1:8190/healthz")
        for i in range(len(layout)):
            _wait_port(50171 + i)
        body = json.dumps({"input_ids": prompt, "max_new_tokens": n_tokens}).encode()
        req = urllib.request.Request("http://127.0.0.1:8190/generate", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=1200) as r:
            out = json.load(r)
        return out
    finally:
        for p in procs:
            p.send_signal(signal.SIGTERM)
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()


def relayout(n_tokens, prompt, ref_gen):
    import threading

    import grpc

    sys.path.insert(0, os.path.join(WORKER_DIR, "gen"))
    import pipeline_pb2 as pb
    import pipeline_pb2_grpc as rpc

    before, after = [(0, 14), (14, 28)], [(0, 18), (18, 28)]
    ports = [50271, 50272]
    procs, result = [], {}
    env_base = {**os.environ, "PYTHONUNBUFFERED": "1", "KV_CACHE": "1"}
    try:
        for i, (lo, hi) in enumerate(before):
            env = {**env_base, "PORT": str(ports[i]), "WORKER_NAME": f"r{i}",
                   "INITIAL_ASSIGNMENT": f"{lo}:{hi}:28:qwen3:{MODEL}"}
            procs.append(subprocess.Popen([sys.executable, "server.py"], cwd=WORKER_DIR,
                                          env=env, stdout=subprocess.DEVNULL,
                                          stderr=subprocess.STDOUT))
        stages = ",".join(f"r{i}=127.0.0.1:{ports[i]}={lo}={hi}"
                          for i, (lo, hi) in enumerate(before))
        procs.append(subprocess.Popen(
            [sys.executable, "router.py"], cwd=WORKER_DIR,
            env={**env_base, "HTTP_PORT": "8290", "GRPC_PORT": "50279",
                 "STATIC_PIPELINE": stages},
            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT))
        _wait_http("http://127.0.0.1:8290/healthz")
        for p in ports:
            _wait_port(p)

        def run():
            body = json.dumps({"input_ids": prompt, "max_new_tokens": n_tokens}).encode()
            req = urllib.request.Request("http://127.0.0.1:8290/generate", data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=1200) as r:
                result.update(json.load(r))

        t = threading.Thread(target=run)
        t.start()
        # Wait for real forwards so this still lands mid-request on a fast GPU.
        deadline = time.time() + 30
        while time.time() < deadline and t.is_alive():
            try:
                with urllib.request.urlopen("http://127.0.0.1:8290/stats", timeout=1) as response:
                    stats = json.load(response)
                if sum(stage.get("forwards", 0) for stage in stats["stages"]) >= 8:
                    break
            except Exception:
                pass
            time.sleep(0.01)

        # Repartition exactly as the controller's push() does: workers, then router.
        for i, (lo, hi) in enumerate(after):
            stub = rpc.WorkerStub(grpc.insecure_channel(f"127.0.0.1:{ports[i]}"))
            rep = stub.AssignLayers(pb.AssignLayersRequest(
                start_layer=lo, end_layer=hi, total_layers=28, backend="qwen3",
                model=MODEL, generation=1), timeout=300)
            assert rep.ok, rep.error
        router = rpc.RouterStub(grpc.insecure_channel("127.0.0.1:50279"))
        router.SetPipeline(pb.SetPipelineRequest(generation=1, stages=[
            pb.StageRef(name=f"r{i}", addr=f"127.0.0.1:{ports[i]}", start_layer=lo, end_layer=hi)
            for i, (lo, hi) in enumerate(after)]), timeout=30)
        t.join()
    finally:
        for p in procs:
            p.send_signal(signal.SIGTERM)
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()

    match = result.get("tokens") == ref_gen
    print(f"relayout   : {result.get('tokens')}")
    print(f"             {'MATCH' if match else 'MISMATCH'}  replays={result.get('replays')} "
          f"generation={result.get('generation')} transition_ms={result.get('transition_ms')} "
          f"reconstruct_ms={result.get('reconstruct_ms')}")
    ok = match and result.get("replays", 0) >= 1 and result.get("generation") == 1
    if result.get("replays", 0) < 1:
        print("             NOTE: no replay observed -- the relayout landed outside the request")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inprocess", action="store_true")
    ap.add_argument("--relayout", action="store_true")
    ap.add_argument("--tokens", type=int, default=24)
    args = ap.parse_args()

    if args.inprocess:
        return inprocess(args.tokens)

    if args.relayout:
        from transformers import AutoTokenizer

        tok = AutoTokenizer.from_pretrained(MODEL)
        prompt, ref_gen, _ = reference(tok, args.tokens)
        print("reference  :", ref_gen)
        ok = relayout(args.tokens, prompt, ref_gen)
        print("RELAYOUT OK" if ok else "RELAYOUT FAILED")
        return 0 if ok else 1

    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(MODEL)
    prompt, ref_gen, _ = reference(tok, args.tokens)
    print("reference  :", ref_gen)
    ok = True
    for cached in (False, True):
        out = end_to_end(args.tokens, cached, prompt, ref_gen)
        match = out["tokens"] == ref_gen
        ok &= match
        print(f"{'cached   ' if cached else 'stateless'}  : {out['tokens']}")
        print(f"             {'MATCH' if match else 'MISMATCH'}  "
              f"ttft={out['ttft_ms']}ms tok/s={out['tokens_per_sec']} kv_cache={out['kv_cache']}")
    print("ALL MATCH" if ok else "MISMATCH")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
