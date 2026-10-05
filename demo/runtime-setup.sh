#!/usr/bin/env bash
set -euo pipefail
flavor=${1:-auto}
case "$flavor" in cpu|cuda|auto) ;; *) echo 'Usage: runtime-setup.sh [cpu|cuda|auto]' >&2; exit 2;; esac
if [[ "$flavor" == auto ]]; then
  if command -v nvidia-smi >/dev/null && nvidia-smi -L >/dev/null 2>&1; then flavor=cuda; else flavor=cpu; fi
fi
app_home=${SHARDWISE_HOME:-${KEINFER_DEMO_HOME:-$HOME/.local/share/shardwise}}
app_bin=${SHARDWISE_BIN:-${KEINFER_BIN:-/opt/shardwise/bin}}
uv_bin="$app_bin/uv"
if [[ ! -x "$uv_bin" ]]; then uv_bin=$(command -v uv || true); fi
[[ -n "$uv_bin" ]] || { echo 'uv is missing. Install the demo package or uv before setup.' >&2; exit 1; }
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
mkdir -p "$app_home"; export UV_PYTHON_INSTALL_DIR="$app_home/python" UV_CACHE_DIR="$app_home/uv-cache"
runtime="$app_home/runtime"
echo "[setup] Preparing Python 3.12 ($flavor); downloads resume using the uv cache."
if [[ ! -x "$runtime/bin/python" ]]; then "$uv_bin" venv --python 3.12 --python-preference only-managed "$runtime"; fi
index=https://download.pytorch.org/whl/cpu
[[ "$flavor" != cuda ]] || index=https://download.pytorch.org/whl/cu130
# Keep torch's trusted index separate from PyPI dependency resolution.
torch_args=()
if [[ ! -f "$runtime/.flavor" ]] || [[ $(cat "$runtime/.flavor") != "$flavor" ]]; then torch_args+=(--reinstall-package torch); fi
"$uv_bin" pip install --python "$runtime/bin/python" --index-url "$index" "${torch_args[@]}" 'torch==2.14.0'
# Exclude torch here so switching CPU/CUDA cannot reuse the wrong PyPI wheel.
requirements=$(mktemp); trap 'rm -f "$requirements"' EXIT
sed '/^torch==/d' "$script_dir/requirements-$flavor.txt" > "$requirements"
echo '[setup] Installing the pinned inference dependencies.'
"$uv_bin" pip install --python "$runtime/bin/python" --index-url https://pypi.org/simple -r "$requirements"
"$runtime/bin/python" -c 'import torch, transformers, grpc; print("[setup] Imports verified. Torch", torch.__version__)'
printf '%s\n' "$flavor" > "$runtime/.flavor"
echo "[setup] Ready: $runtime"
