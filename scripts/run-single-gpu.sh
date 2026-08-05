#!/usr/bin/env bash
# Run the pipeline on ONE machine with NO Kubernetes.
#
# For rented GPU boxes that are unprivileged containers, where k3s cannot run
# at all. You still get the thing a GPU is actually needed for: real GPT-2
# sharded across a real pipeline on the real device, producing real tokens.
#
# What you do NOT get without Kubernetes: the controller, so no telemetry
# loop, no repartitioning, no healing -- the split is fixed at startup. Use
# the kind demo (./run-demo.sh) or a k3s cluster for those claims.
#
#   ./scripts/run-single-gpu.sh              # 3 shards, GPT-2, auto device
#   SHARDS=4 ./scripts/run-single-gpu.sh     # different shard count
#   BACKEND=sim ./scripts/run-single-gpu.sh  # no torch needed, fake tokens
#
# Ctrl-C stops everything.

set -euo pipefail
cd "$(dirname "$0")/.."

SHARDS="${SHARDS:-3}"
BACKEND="${BACKEND:-gpt2}"
MODEL="${MODEL:-gpt2}"
TOTAL_LAYERS="${TOTAL_LAYERS:-12}"   # gpt2 has 12 transformer blocks
BASE_PORT="${BASE_PORT:-50051}"
HTTP_PORT="${HTTP_PORT:-8080}"
GRPC_PORT="${GRPC_PORT:-50060}"      # kept clear of the worker port range

log() { echo "[single-gpu] $*"; }
die() { echo "[single-gpu] ERROR: $*" >&2; exit 1; }

[[ "$SHARDS" -ge 1 ]] || die "SHARDS must be >= 1"
[[ "$TOTAL_LAYERS" -ge "$SHARDS" ]] || die "TOTAL_LAYERS ($TOTAL_LAYERS) < SHARDS ($SHARDS)"

command -v python3 >/dev/null || die "python3 not found"
command -v curl >/dev/null || die "curl not found (apt-get install -y curl)"

# ---- python dependencies --------------------------------------------------
# Modern Debian/Ubuntu mark the system interpreter "externally managed"
# (PEP 668), so `pip install` into it fails. Prefer a local venv; fall back to
# --break-system-packages when python3-venv isn't available.
PY="${PY:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"

MODS="grpc google.protobuf numpy"
PIP_PKGS="grpcio protobuf numpy"
if [[ "$BACKEND" == "gpt2" ]]; then
  MODS="$MODS torch transformers"
  PIP_PKGS="$PIP_PKGS torch transformers"
fi

have_mods() {
  "$1" -c "import importlib.util,sys;
sys.exit(0 if all(importlib.util.find_spec(m) for m in '$MODS'.split()) else 1)" \
    >/dev/null 2>&1
}

log "checking python dependencies ($MODS)"
if have_mods "$PY"; then
  :
elif [[ -x "$VENV_DIR/bin/python" ]] && have_mods "$VENV_DIR/bin/python"; then
  PY="$VENV_DIR/bin/python"
  log "using existing venv $VENV_DIR"
elif [[ "${SKIP_INSTALL:-0}" == "1" ]]; then
  die "dependencies missing and SKIP_INSTALL=1; install manually: pip install $PIP_PKGS"
else
  log "installing: $PIP_PKGS"
  [[ "$BACKEND" == "gpt2" ]] && log "(torch is a large download -- expect several minutes)"
  if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    python3 -m venv "$VENV_DIR" 2>/dev/null || true
  fi
  if [[ -x "$VENV_DIR/bin/python" ]]; then
    "$VENV_DIR/bin/pip" install --quiet --upgrade pip
    # shellcheck disable=SC2086
    "$VENV_DIR/bin/pip" install --quiet $PIP_PKGS || die "pip install failed in $VENV_DIR"
    PY="$VENV_DIR/bin/python"
    log "installed into $VENV_DIR"
  else
    log "python3-venv unavailable -- installing with --break-system-packages"
    # shellcheck disable=SC2086
    python3 -m pip install --quiet --break-system-packages $PIP_PKGS \
      || die "could not install dependencies. Try: apt-get install -y python3-venv, then re-run"
  fi
  have_mods "$PY" || die "dependencies still missing after install"
fi

if [[ "$BACKEND" == "gpt2" ]]; then
  "$PY" - <<'EOF'
import torch
print(f"[single-gpu] torch {torch.__version__}, cuda available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"[single-gpu] device: {torch.cuda.get_device_name(0)}")
else:
    print("[single-gpu] WARNING: no CUDA visible -- this will run on CPU and be slow")
EOF
fi

PIDS=()
cleanup() {
  log "stopping"
  for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Contiguous layer ranges, remainder spread over the first shards.
base=$((TOTAL_LAYERS / SHARDS))
rem=$((TOTAL_LAYERS % SHARDS))
start=0
stages=""
for ((i = 0; i < SHARDS; i++)); do
  n=$base
  (( i < rem )) && n=$((n + 1))
  end=$((start + n))
  port=$((BASE_PORT + i))

  PORT="$port" \
  WORKER_NAME="shard$i" \
  WORKER_DEVICE="${WORKER_DEVICE:-auto}" \
  INITIAL_ASSIGNMENT="${start}:${end}:${TOTAL_LAYERS}:${BACKEND}:${MODEL}" \
    "$PY" worker/server.py &
  PIDS+=($!)
  log "shard$i: layers [${start}, ${end}) on port ${port}"

  [[ -n "$stages" ]] && stages="${stages},"
  stages="${stages}shard${i}=127.0.0.1:${port}=${start}=${end}"
  start=$end
done

log "waiting for shards to load the model (first run downloads weights)"
for ((i = 0; i < SHARDS; i++)); do
  port=$((BASE_PORT + i))
  for _ in $(seq 1 120); do
    (echo > "/dev/tcp/127.0.0.1/${port}") >/dev/null 2>&1 && break
    sleep 1
  done
done

STATIC_PIPELINE="$stages" HTTP_PORT="$HTTP_PORT" GRPC_PORT="$GRPC_PORT" \
  "$PY" worker/router.py &
PIDS+=($!)

for _ in $(seq 1 60); do
  curl -sf "http://127.0.0.1:${HTTP_PORT}/healthz" >/dev/null 2>&1 && break
  sleep 1
done
curl -sf "http://127.0.0.1:${HTTP_PORT}/healthz" >/dev/null || die "router did not come up"

if [[ "$BACKEND" == "sim" ]]; then
  TOKEN_NOTE='# NOTE: backend=sim -- timings are real, token values are always 0.
  #       Use BACKEND=gpt2 for real model output.'
else
  TOKEN_NOTE='# real GPT-2 output ("Hello, my name is" -> 10 more tokens)'
fi

cat <<EOF

[single-gpu] pipeline up: ${SHARDS} shards, backend=${BACKEND}

  ${TOKEN_NOTE}
  curl -s -X POST localhost:${HTTP_PORT}/generate \\
    -d '{"input_ids":[15496,11,616,1438,318],"max_new_tokens":10}'

  curl -s localhost:${HTTP_PORT}/stats      # per-stage busy/idle
  curl -s localhost:${HTTP_PORT}/pipeline   # the layer split

  # dashboard (controller panels stay empty: there is no controller here)
  ROUTER_PORT=${HTTP_PORT} ${PY} demo/serve.py    # http://localhost:8000

  nvidia-smi                                # should show ${SHARDS} python processes

Ctrl-C to stop.
EOF
wait
