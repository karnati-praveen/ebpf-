#!/usr/bin/env bash
# Start the controller and router. Run on VM1 only. Idempotent: restarts both
# with the current settings, which is how an experiment switches policy.
#
#   ./deploy/standalone/start-coordinator.sh <expected-worker-count>
#
# Env:
#   POLICY           none | hysteresis | gate | gate-force   (default hysteresis)
#   STATIC_MODE=1    one split, never repartition (the static baseline)
#   PROFILE_ONCE=1   freeze telemetry at the first reading (offline-profile ablation)
#   CONTEXT_LEN      operating context length for the cost model (default 512)
#   GATE_HORIZON_S, GATE_TRANSITION_FIXED_MS, GATE_PREFILL_MS_PER_TOKEN_LAYER,
#   GATE_MARGIN      transition gate parameters (see cmd/controller)
#   COOLDOWN_S, IMPROVEMENT_FRAC   hysteresis parameters
#   LINK_SOURCE      ebpf | app | ebpf+app | none   (default ebpf+app) -- the H3 arms
#   COST_MODEL       full | layer-proportional (default full). layer-proportional
#                    drops the endpoint and context-dependent terms: ablations A9/A10
#   ROUTER=0         restart only the controller, leave the router running
set -euo pipefail
source "$(dirname "$0")/common.sh"
[[ "$WORKER_DEVICE" != cuda || -n "${COST_PROFILE:-}" ]] || die "WORKER_DEVICE=cuda requires COST_PROFILE from bench/profile_qwen3.py"

WORKERS="${1:-}"
[[ "$WORKERS" =~ ^[0-9]+$ ]] || die "usage: $0 <expected-worker-count>"
[[ -x "$BIN/controller" ]] || die "run setup-vm.sh first"
CONTEXT_LEN="${CONTEXT_LEN:-512}"

# Pipeline config: the measured Azure cost model. headMs is lm_head plus the
# final-norm excess (docs/phase4-prelim-findings.md); per-layer costs are the
# decode table the workers' speed probes are normalised against.
CFG="$STATE_DIR/keinfer.json"
COST_MODEL="${COST_MODEL:-full}"
[[ "$COST_MODEL" == full || "$COST_MODEL" == layer-proportional ]] || die "COST_MODEL must be full or layer-proportional"
python3 - "$CFG" "$WORKERS" "$CONTEXT_LEN" "$PER_LAYER_PROFILE" "$ROUTER_GRPC_PORT" "$MODEL" "$COST_MODEL" "${EMBED_MS:-0.09}" "${HEAD_MS:-43.8}" <<'PY'
import json, sys
cfg, workers, ctx, profile, rport, model, cost_model, embed_ms, head_ms = sys.argv[1:]
table = [{"contextLen": int(c), "perLayerMs": float(m)}
         for c, m in (p.split(":") for p in profile.split(",") if p)]
spec = {
    "model": model, "backend": "qwen3", "totalLayers": 28,
    "perLayerMs": table[len(table) // 2]["perLayerMs"], "workers": int(workers),
    "routerAddr": f"127.0.0.1:{rport}", "contextLen": int(ctx),
}
if cost_model == "full":
    # Measured endpoint costs and the context-dependent per-layer table.
    spec.update({"embedMs": float(embed_ms), "headMs": float(head_ms), "perLayerByCtx": table})
# layer-proportional: one scalar per-layer cost, no endpoint terms (A9/A10).
json.dump(spec, open(cfg, "w"), indent=2)
PY

stop_one controller
supervise controller env \
  STATIC_MODE="${STATIC_MODE:-0}" PROFILE_ONCE="${PROFILE_ONCE:-0}" \
  ${COOLDOWN_S:+COOLDOWN_S=$COOLDOWN_S} ${IMPROVEMENT_FRAC:+IMPROVEMENT_FRAC=$IMPROVEMENT_FRAC} \
  ${GATE_HORIZON_S:+GATE_HORIZON_S=$GATE_HORIZON_S} \
  ${GATE_TRANSITION_FIXED_MS:+GATE_TRANSITION_FIXED_MS=$GATE_TRANSITION_FIXED_MS} \
  ${GATE_PREFILL_MS_PER_TOKEN_LAYER:+GATE_PREFILL_MS_PER_TOKEN_LAYER=$GATE_PREFILL_MS_PER_TOKEN_LAYER} \
  ${GATE_MARGIN:+GATE_MARGIN=$GATE_MARGIN} \
  "$BIN/controller" -mode=standalone -config="$CFG" \
  -grpc-addr=":$CONTROLLER_GRPC_PORT" -http-addr=":$CONTROLLER_HTTP_PORT" \
  -policy="${POLICY:-hysteresis}" -link-source="${LINK_SOURCE:-ebpf+app}"

if [[ "${ROUTER:-1}" == 1 ]]; then
  stop_one router
  cd "$REPO/worker"
  # CONTROLLER_ADDR makes the router push application-level link telemetry.
  supervise router env PYTHONUNBUFFERED=1 KV_CACHE="${KV_CACHE:-1}" \
    CONTROLLER_ADDR="127.0.0.1:$CONTROLLER_GRPC_PORT" \
    HTTP_PORT="$ROUTER_HTTP_PORT" GRPC_PORT="$ROUTER_GRPC_PORT" "$VENV/bin/python" router.py
fi

log "coordinator: profile=${COST_PROFILE:-azure-cpu} policy=${POLICY:-hysteresis} link-source=${LINK_SOURCE:-ebpf+app} cost-model=$COST_MODEL static=${STATIC_MODE:-0} profile-once=${PROFILE_ONCE:-0} ctx=$CONTEXT_LEN workers=$WORKERS"
log "  controller state: curl -s localhost:$CONTROLLER_HTTP_PORT/state"
log "  generate:         curl -s -X POST localhost:$ROUTER_HTTP_PORT/generate -d '{\"prompt_len\":64,\"max_new_tokens\":16}'"
