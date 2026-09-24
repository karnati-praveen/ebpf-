#!/usr/bin/env python3
"""Measure a Qwen3 reference cost profile for standalone placement.

Run on one representative worker before starting a CUDA cluster. This profiles
exactly the backend's full-chain cached prefill and one-token decode path. The
result feeds COST_PROFILE in the standalone launchers; other workers report
speed relative to the same reference profile. It is a component profile, not
an end-to-end transition measurement.
"""

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "worker"))
sys.path.insert(0, str(REPO / "worker" / "gen"))


def profile(args):
    import torch
    import transformers
    from transformers import AutoConfig
    import pipeline_pb2 as pb
    from backends.qwen3 import Qwen3Backend

    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable; install the CUDA torch wheel and check nvidia-smi")
    os.environ["WORKER_DEVICE"] = args.device
    os.environ["KV_CACHE"] = "1"
    # Profiling should never feed its own timing samples back into a node agent.
    os.environ.pop("PER_LAYER_PROFILE", None)
    os.environ.pop("NODE_AGENT_ADDR", None)

    contexts = sorted(set(int(c) for c in args.contexts.split(",")))
    if not contexts or min(contexts) < 1 or args.samples < 1 or args.warmup < 0:
        raise ValueError("contexts and samples must be positive; warmup must be nonnegative")
    total = AutoConfig.from_pretrained(args.model).num_hidden_layers
    backend = Qwen3Backend(args.model)
    backend.load(0, total, total)
    sync = torch.cuda.synchronize if args.device == "cuda" else lambda: None

    starts = {}
    elapsed = {}

    def begin(name):
        def hook(*_):
            sync()
            starts[name] = time.perf_counter()
        return hook

    def end(name):
        def hook(*_):
            sync()
            elapsed[name] = (time.perf_counter() - starts[name]) * 1000
        return hook

    hooks = [
        backend.layers[0].register_forward_pre_hook(begin("layers")),
        backend.layers[-1].register_forward_hook(end("layers")),
        backend.embed.register_forward_pre_hook(begin("embed")),
        backend.embed.register_forward_hook(end("embed")),
        backend.norm.register_forward_pre_hook(begin("head")),
        backend.lm_head.register_forward_hook(end("head")),
    ]

    def forward(req):
        starts.clear()
        elapsed.clear()
        reply = backend.forward(req)
        if reply.error:
            raise RuntimeError(reply.error)
        for key in ("layers", "embed", "head"):
            if key not in elapsed:
                raise RuntimeError(f"timing hook for {key} did not run")
        return dict(elapsed)

    rows = []
    try:
        for context in contexts:
            prefill, decode = [], []
            request_id = context * 100000
            # Separate sessions give a prefill distribution; the last one is
            # retained for the decode series at approximately this context.
            for i in range(args.warmup + args.samples):
                sample = forward(pb.ForwardRequest(
                    request_id=request_id + i, step=0,
                    input_ids=[args.token_id] * context))
                if i >= args.warmup:
                    prefill.append(sample)
            rid = request_id + args.warmup + args.samples - 1
            for step in range(1, args.warmup + args.samples + 1):
                sample = forward(pb.ForwardRequest(
                    request_id=rid, step=step, input_ids=[args.token_id]))
                if step > args.warmup:
                    decode.append(sample)
            row = {
                "context_len": context,
                "decode_ms_per_layer": statistics.median(s["layers"] / total for s in decode),
                "decode_head_ms": statistics.median(s["head"] for s in decode),
                "decode_embed_ms": statistics.median(s["embed"] for s in decode),
                "prefill_ms_per_token_layer": statistics.median(
                    s["layers"] / (context * total) for s in prefill),
                "prefill_layer_ms": statistics.median(s["layers"] for s in prefill),
            }
            rows.append(row)
            print(f"ctx={context:5d} decode={row['decode_ms_per_layer']:.4f} ms/layer "
                  f"head={row['decode_head_ms']:.4f} ms "
                  f"prefill={row['prefill_ms_per_token_layer']:.6f} ms/token/layer",
                  flush=True)
    finally:
        for hook in hooks:
            hook.remove()

    result = {
        "model": args.model,
        "device": args.device,
        "device_name": torch.cuda.get_device_name(0) if args.device == "cuda" else "CPU",
        "dtype": str(backend.dtype),
        "torch_version": torch.__version__,
        "transformers_version": transformers.__version__,
        "total_layers": total,
        "samples_per_context": args.samples,
        "warmup_per_context": args.warmup,
        "per_layer_by_ctx": [{"context_len": r["context_len"], "ms": r["decode_ms_per_layer"]}
                             for r in rows],
        "embed_ms": statistics.median(r["decode_embed_ms"] for r in rows),
        "head_ms": statistics.median(r["decode_head_ms"] for r in rows),
        # The gate uses one scalar prefill coefficient. Preserve the individual
        # context measurements as well so its approximation error is visible.
        "prefill_ms_per_token_layer": statistics.median(
            r["prefill_ms_per_token_layer"] for r in rows),
        "measurements": rows,
    }
    if args.device == "cuda":
        result["peak_cuda_allocated_bytes"] = torch.cuda.max_memory_allocated()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x") as f:
        json.dump(result, f, indent=2)
        f.write("\n")
    print(f"wrote {args.out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default=os.environ.get("MODEL", "Qwen/Qwen3-0.6B"))
    ap.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    ap.add_argument("--contexts", default="128,512,1024,2048")
    ap.add_argument("--warmup", type=int, default=2)
    ap.add_argument("--samples", type=int, default=5)
    ap.add_argument("--token-id", type=int, default=1)
    ap.add_argument("--out", type=Path, required=True,
                    help="new JSON profile path; existing files are never overwritten")
    profile(ap.parse_args())


if __name__ == "__main__":
    main()
