#!/usr/bin/env bash
# One-command demo: clone the repo, run this, open the dashboard.
#
#   ./run-demo.sh
#
# Checks prerequisites, builds the images (first run only; REBUILD=1 forces),
# brings up the 4-node kind cluster, deploys KubeEdgeInfer, port-forwards the
# router and controller, and serves a live dashboard at http://localhost:8000
# with a built-in load generator and thermal fault-injection buttons — so the
# WATCH→DECIDE→ACT→HEAL loop is visible end to end.
#
# Ctrl-C stops the port-forwards/dashboard; the cluster keeps running
# (`make cluster-down` removes it).

set -euo pipefail
cd "$(dirname "$0")"

ROUTER_PORT="${ROUTER_PORT:-18080}"
CTRL_PORT="${CTRL_PORT:-18081}"
DASH_PORT="${DASH_PORT:-8000}"
NS=kubeedgeinfer

log() { echo "[demo] $*"; }
die() { echo "[demo] ERROR: $*" >&2; exit 1; }

# ---- prerequisites --------------------------------------------------------
for tool in docker kind kubectl python3; do
  command -v "$tool" >/dev/null || die "'$tool' is required but not installed.
  docker:  https://docs.docker.com/engine/install/
  kind:    https://kind.sigs.k8s.io/docs/user/quick-start/#installation
  kubectl: https://kubernetes.io/docs/tasks/tools/"
done
docker info >/dev/null 2>&1 || die "docker daemon not running (or no permission — try adding yourself to the docker group)"

# ---- images (skip if already built) ---------------------------------------
have_images() {
  for img in kubeedgeinfer/worker:dev kubeedgeinfer/nodeagent:dev kubeedgeinfer/controller:dev; do
    docker image inspect "$img" >/dev/null 2>&1 || return 1
  done
}
if [[ "${REBUILD:-0}" == "1" ]] || ! have_images; then
  log "building images (first run takes a few minutes)"
  make images
else
  log "images already built (REBUILD=1 to force)"
fi

# ---- cluster + deploy -----------------------------------------------------
log "ensuring kind cluster is up"
make cluster-up
log "deploying"
make deploy

log "waiting for pods to become Ready (up to 5 min on first run)"
kubectl -n "$NS" wait --for=condition=Ready pod --all --timeout=300s
kubectl -n "$NS" get pods -o wide

# ---- port-forwards + dashboard --------------------------------------------
PIDS=()
cleanup() {
  log "stopping dashboard and port-forwards (cluster stays up; 'make cluster-down' removes it)"
  for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

forward() { # keep the port-forward alive if it drops
  while true; do
    kubectl -n "$NS" port-forward "$1" "$2:$3" >/dev/null 2>&1 || true
    sleep 1
  done
}
forward svc/router "$ROUTER_PORT" 8080 & PIDS+=($!)
forward svc/controller "$CTRL_PORT" 8081 & PIDS+=($!)

log "waiting for the router port-forward"
for _ in $(seq 1 30); do
  curl -sf "http://127.0.0.1:${ROUTER_PORT}/healthz" >/dev/null 2>&1 && break
  sleep 1
done
curl -sf "http://127.0.0.1:${ROUTER_PORT}/healthz" >/dev/null || die "router not reachable through port-forward"

log "first pipeline assignment (controller applies it within ~2s):"
kubectl -n "$NS" get ipl demo || true

ROUTER_PORT="$ROUTER_PORT" CTRL_PORT="$CTRL_PORT" DASH_PORT="$DASH_PORT" \
  python3 demo/serve.py & PIDS+=($!)
sleep 1

log ""
log "  dashboard:  http://localhost:${DASH_PORT}"
log "  router API: http://localhost:${ROUTER_PORT}  (/generate /stats /pipeline /metrics)"
log "  controller: http://localhost:${CTRL_PORT}/state"
log ""
log "Try the 'Inject heat' button: within ~35s the controller migrates layers"
log "off the hot node (watch Generation tick up and the layer bar shift),"
log "then 'Clear fault' and watch it move back after the 30s cooldown."
log ""
log "Ctrl-C to stop."
wait
