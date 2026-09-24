#!/usr/bin/env bash
# Start this VM's shard worker and node agent. Run on EVERY VM, including the
# coordinator. Idempotent: restarts whatever is already running.
#
#   ./deploy/standalone/start-worker-node.sh <coordinator-private-ip>
#
# Env: NODE_NAME (default: hostname), TORCH_THREADS (default: torch's own,
# which is what the cost profile was measured with), KV_CACHE (default 1; must
# match the router), EBPF (default on; off for the application-only H3 arm).
set -euo pipefail
source "$(dirname "$0")/common.sh"
[[ "$WORKER_DEVICE" != cuda || -n "${COST_PROFILE:-}" ]] || die "WORKER_DEVICE=cuda requires COST_PROFILE from bench/profile_qwen3.py"

COORD="${1:-}"
[[ -n "$COORD" ]] || die "usage: $0 <coordinator-private-ip>"
[[ -x "$BIN/nodeagent" && -x "$VENV/bin/python" ]] || die "run setup-vm.sh first"
NODE_NAME="${NODE_NAME:-$(hostname)}"
IP="$(private_ip)"
[[ -n "$IP" ]] || die "could not determine this VM's private IP"
KV_CACHE="${KV_CACHE:-1}"

stop_one worker
stop_one nodeagent

cd "$REPO/worker"
supervise worker env \
  PYTHONUNBUFFERED=1 PORT="$WORKER_PORT" WORKER_NAME="$NODE_NAME" KV_CACHE="$KV_CACHE" WORKER_DEVICE="$WORKER_DEVICE" \
  NODE_AGENT_ADDR="127.0.0.1:$AGENT_HTTP_PORT" PER_LAYER_PROFILE="$PER_LAYER_PROFILE" \
  ${TORCH_THREADS:+TORCH_THREADS=$TORCH_THREADS} HF_HOME="$HF_HOME" HF_HUB_OFFLINE=1 \
  "$VENV/bin/python" server.py

# The node agent loads eBPF programs, which needs root. It advertises this
# VM's worker to the controller (WORKER_ADDR) only while that worker serves
# gRPC, and reports speed measured from the worker's own decode timing.
supervise nodeagent sudo env \
  NODE_NAME="$NODE_NAME" HTTP_ADDR=":$AGENT_HTTP_PORT" \
  CONTROLLER_ADDR="$COORD:$CONTROLLER_GRPC_PORT" WORKER_ADDR="$IP:$WORKER_PORT" \
  PORT_MIN="$WORKER_PORT" PORT_MAX="$WORKER_PORT" GPU_MODE=measured EBPF="${EBPF:-on}" \
  "$BIN/nodeagent"

log "node $NODE_NAME: worker $IP:$WORKER_PORT, reporting to $COORD:$CONTROLLER_GRPC_PORT, KV_CACHE=$KV_CACHE device=$WORKER_DEVICE profile=${COST_PROFILE:-azure-cpu}"
