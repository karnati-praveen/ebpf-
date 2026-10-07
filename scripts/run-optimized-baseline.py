#!/usr/bin/env python3
"""Prepare a pinned external CPU engine after the main matrix completes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("--checkout", type=Path, required=True)
ap.add_argument("--source", type=Path, required=True)
ap.add_argument("--wait-completion", action="store_true")
ap.add_argument("--out", type=Path, required=True)
args = ap.parse_args()
if args.wait_completion:
    print("Waiting for completed main matrix before engine preparation", flush=True)
    status = args.source / "completion-status.json"
    while not status.exists() or not json.loads(status.read_text())["complete"]:
        time.sleep(10)
source = json.loads((args.source/"manifest.json").read_text())
cpu = next(line.split(":", 1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
           if line.startswith("model name"))
if source["cpu"] != cpu:
    raise RuntimeError("source campaign and optimized engine must use the same CPU model")
args.out.mkdir(parents=True, exist_ok=True)
checkout = args.checkout.resolve()
commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=checkout, text=True).strip()
build_command = ["cmake", "-S", str(checkout), "-B", str(checkout/"build"),
    "-DCMAKE_BUILD_TYPE=Release", "-DLLAMA_BUILD_TESTS=OFF", "-DLLAMA_BUILD_EXAMPLES=OFF",
    "-DLLAMA_BUILD_SERVER=ON", "-DLLAMA_CURL=OFF"]
subprocess.run(["taskset", "-c", "2,3", *build_command], check=True)
subprocess.run(["taskset", "-c", "2,3", "cmake", "--build", str(checkout/"build"),
                "--target", "llama-server", "-j2"], check=True)
from huggingface_hub import try_to_load_from_cache
config = try_to_load_from_cache("Qwen/Qwen3-0.6B", "config.json")
if not isinstance(config, str):
    raise RuntimeError("cached benchmark checkpoint unavailable")
model = Path(config).parent
gguf = checkout.parent/"qwen3-f32.gguf"
conversion = [sys.executable, str(checkout/"convert_hf_to_gguf.py"), str(model),
              "--outfile", str(gguf), "--outtype", "f32"]
if not gguf.exists():
    import shutil
    if shutil.disk_usage(checkout.parent).free < 4*1024**3:
        raise RuntimeError("at least 4 GiB free needed for F32 conversion")
    temporary = gguf.with_suffix(".partial.gguf")
    conversion[conversion.index("--outfile")+1] = str(temporary)
    subprocess.run(["taskset", "-c", "2,3", *conversion], check=True)
    temporary.replace(gguf)
(args.out/"preparation.json").write_text(json.dumps({"engine_commit": commit,
    "build_command": build_command, "conversion_command": conversion,
    "model_revision": model.name, "weight_precision": "F32", "kv_precision": "F32",
    "gguf_sha256": hashlib.file_digest(gguf.open("rb"), "sha256").hexdigest()}, indent=2)+"\n")
subprocess.run([sys.executable, str(ROOT/"bench/engine_publication.py"),
    "--source", str(args.source), "--out", str(args.out),
    "--server", str(checkout/"build/bin/llama-server"), "--gguf", str(gguf),
    "--engine-commit", commit, *(["--resume"] if (args.out/"manifest.json").exists() else [])], check=True)
subprocess.run([sys.executable, str(ROOT/"bench/publication_analyze.py"), str(args.out)], check=True)
print("Optimized baseline completed and analyzed", flush=True)
