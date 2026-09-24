# Shared settings for the standalone deploy scripts. Sourced, not executed.

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STATE_DIR="${KEINFER_STATE:-$HOME/keinfer}"
LOG_DIR="$STATE_DIR/logs"
PID_DIR="$STATE_DIR/pids"
VENV="$STATE_DIR/venv"
BIN="$STATE_DIR/bin"
export HF_HOME="${HF_HOME:-$STATE_DIR/hf}"
mkdir -p "$LOG_DIR" "$PID_DIR"

MODEL="${MODEL:-Qwen/Qwen3-0.6B}"
# CPU is the calibrated default. Select CUDA explicitly after profiling that GPU.
WORKER_DEVICE="${WORKER_DEVICE:-cpu}"
WORKER_PORT="${WORKER_PORT:-50051}"
AGENT_HTTP_PORT="${AGENT_HTTP_PORT:-9101}"
CONTROLLER_GRPC_PORT="${CONTROLLER_GRPC_PORT:-50053}"
CONTROLLER_HTTP_PORT="${CONTROLLER_HTTP_PORT:-8081}"
ROUTER_GRPC_PORT="${ROUTER_GRPC_PORT:-50052}"
ROUTER_HTTP_PORT="${ROUTER_HTTP_PORT:-8080}"

# Measured on an Azure 4-vCPU Xeon 8272CL (docs/data/azure-d4-2026-09/).
# The worker divides this profile's prediction by its observed decode time to
# report measured speed; the controller partitions with the same table.
PER_LAYER_PROFILE="${PER_LAYER_PROFILE:-128:5.55,512:6.25,1024:7.18,2048:9.49}"

log() { echo "[keinfer] $*"; }
die() { echo "[keinfer] ERROR: $*" >&2; exit 1; }

# One reference cost profile is shared by the coordinator and all workers.
# Workers compare their own decode timing with this table to report relative
# speed; the coordinator uses the same table for placement. A CUDA worker must
# never inherit the Azure CPU profile above.
if [[ -n "${COST_PROFILE:-}" ]]; then
  [[ -r "$COST_PROFILE" ]] || die "COST_PROFILE is not readable: $COST_PROFILE"
  profile_values=$(python3 - "$COST_PROFILE" "$MODEL" "$WORKER_DEVICE" <<'PYPROFILE'
import json, math, sys
profile = json.load(open(sys.argv[1]))
if profile.get("model") != sys.argv[2]:
    raise SystemExit(f"profile model {profile.get('model')!r} does not match MODEL {sys.argv[2]!r}")
if profile.get("device") != sys.argv[3]:
    raise SystemExit(f"profile device {profile.get('device')!r} does not match WORKER_DEVICE {sys.argv[3]!r}")
rows = profile.get("per_layer_by_ctx", [])
if not rows or not isinstance(rows, list):
    raise SystemExit("profile needs a nonempty per_layer_by_ctx list")
seen = set()
for row in rows:
    c, ms = row["context_len"], row["ms"]
    if not isinstance(c, int) or c <= 0 or c in seen or not math.isfinite(ms) or ms <= 0:
        raise SystemExit("profile contexts must be unique positive integers; costs must be finite and positive")
    seen.add(c)
for key in ("embed_ms", "head_ms", "prefill_ms_per_token_layer"):
    value = profile[key]
    if not math.isfinite(value) or value < 0:
        raise SystemExit(f"{key} must be finite and nonnegative")
print(",".join(f"{r['context_len']}:{r['ms']:.6f}" for r in sorted(rows, key=lambda r: r["context_len"])))
print(profile["embed_ms"])
print(profile["head_ms"])
print(profile["prefill_ms_per_token_layer"])
PYPROFILE
  ) || die "invalid COST_PROFILE: $COST_PROFILE"
  mapfile -t profile_fields <<<"$profile_values"
  PER_LAYER_PROFILE="${profile_fields[0]}"
  EMBED_MS="${profile_fields[1]}"
  HEAD_MS="${profile_fields[2]}"
  GATE_PREFILL_MS_PER_TOKEN_LAYER="${GATE_PREFILL_MS_PER_TOKEN_LAYER:-${profile_fields[3]}}"
fi


# The address other VMs reach this one on -- the primary interface's IPv4,
# never 127.0.0.1 and never a docker bridge address.
private_ip() {
  ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<NF;i++) if($i=="src"){print $(i+1); exit}}'
}

primary_iface() {
  ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<NF;i++) if($i=="dev"){print $(i+1); exit}}'
}

# supervise NAME CMD... -- run CMD, restart it if it exits, until stopped.
# This is the only job an orchestrator did for us that the controller does
# not: restarting a crashed process. The controller's periodic reassert
# re-pushes the layout to a restarted worker, so no other recovery is needed.
#
# The loop is fully detached from the caller: its stdin, stdout and stderr go
# to /dev/null and the log, and it ignores SIGHUP. Without that it inherits the
# caller's output pipe, so `ssh vm2 start-worker-node.sh ...` never sees end of
# output and hangs -- and a closing SSH session could hang up the loop.
supervise() {
  local name="$1"; shift
  (
    trap '' HUP
    trap 'kill "$child" 2>/dev/null; exit 0' TERM INT
    while true; do
      "$@" >>"$LOG_DIR/$name.log" 2>&1 </dev/null &
      child=$!
      echo "$child" >"$PID_DIR/$name.child"
      wait "$child"
      echo "[supervise] $name exited ($?); restarting in 2s" >>"$LOG_DIR/$name.log"
      sleep 2
    done
  ) </dev/null >>"$LOG_DIR/$name.log" 2>&1 &
  echo $! >"$PID_DIR/$name.supervisor"
  disown 2>/dev/null || true
  log "started $name (logs: $LOG_DIR/$name.log)"
}

stop_one() {
  local name="$1" p
  for f in "$PID_DIR/$name.supervisor" "$PID_DIR/$name.child"; do
    [[ -f "$f" ]] || continue
    p=$(cat "$f")
    kill "$p" 2>/dev/null || sudo kill "$p" 2>/dev/null || true
    rm -f "$f"
  done
}
