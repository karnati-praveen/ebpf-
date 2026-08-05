#!/usr/bin/env bash
# Run once, on the k3s server, after every machine has run
# scripts/join-node.sh and been labeled. Builds images, gets them onto every
# node via a local registry, and deploys KubeEdgeInfer with real telemetry:
# NVML + CUDA on nodes labeled kubeedgeinfer.io/gpu=true, and real CPU
# thermal (/sys/class/thermal) on GPU-less machines such as laptops.
#
# Assumes: this repo checked out on the server, docker installed, kubectl
# pointed at the k3s cluster (scripts/join-node.sh server already set that
# up). See docs/laptops.md for the two-laptop walkthrough.
#
# Env overrides:
#   SERVER_IP=<ip>   registry address to advertise (default: first hostname -I)
#   WITH_GPT2=1      bake the real GPT-2 backend into the worker image; adds a
#                    ~1GB torch download. Off by default because the shipped
#                    pipeline runs the `sim` backend -- switch the CR to
#                    backend: gpt2 only after building with this.

set -euo pipefail
cd "$(dirname "$0")/.."

log() { echo "[deploy-real-hardware] $*"; }
die() { echo "[deploy-real-hardware] ERROR: $*" >&2; exit 1; }

command -v kubectl >/dev/null || die "kubectl not found (run scripts/join-node.sh server first)"
command -v docker  >/dev/null || die "docker not found"
kubectl get nodes >/dev/null 2>&1 || die "kubectl cannot reach the cluster (is k3s running? is ~/.kube/config set up?)"

SERVER_IP="${SERVER_IP:-$(hostname -I | awk '{print $1}')}"
[[ -n "$SERVER_IP" ]] || die "could not determine this machine's IP; set SERVER_IP=<ip> explicitly"
REGISTRY="${SERVER_IP}:5000"
log "using registry ${REGISTRY} (override with SERVER_IP=<ip> if that is the wrong interface)"

# ---- preflight ------------------------------------------------------------
# The router/controller require a node carrying the control-plane role label.
CP_NODES=$(kubectl get nodes -l node-role.kubernetes.io/control-plane --no-headers 2>/dev/null | wc -l)
[[ "$CP_NODES" -gt 0 ]] || die "no node carries node-role.kubernetes.io/control-plane; the router and controller cannot be scheduled"

WORKER_NODES=$(kubectl get nodes -l kubeedgeinfer.io/worker=true --no-headers 2>/dev/null | wc -l)
[[ "$WORKER_NODES" -gt 0 ]] || die "no node is labeled kubeedgeinfer.io/worker=true -- run scripts/join-node.sh on each machine and apply the labels it prints"
log "${WORKER_NODES} worker node(s) labeled"
[[ "$WORKER_NODES" -ge 2 ]] || log "WARNING: only one worker node -- a 'pipeline' of one stage still runs, but there is nothing to repartition across"

GPU_NODES=$(kubectl get nodes -l kubeedgeinfer.io/gpu=true --no-headers 2>/dev/null | wc -l)
log "${GPU_NODES} GPU node(s) labeled"

# Mixed architectures cannot share one image tag.
ARCHES=$(kubectl get nodes -o jsonpath='{range .items[*]}{.status.nodeInfo.architecture}{"\n"}{end}' | sort -u | tr '\n' ' ')
if [[ $(echo "$ARCHES" | wc -w) -gt 1 ]]; then
  die "cluster mixes architectures ($ARCHES). Build multi-arch images with 'docker buildx --platform' and push them; see docs/laptops.md section 3."
fi

# eBPF needs BTF on each worker node; warn (the agent degrades gracefully).
for node in $(kubectl get nodes -l kubeedgeinfer.io/worker=true -o name); do
  n=${node#node/}
  [[ "$n" == "$(hostname)" ]] || continue
  [[ -r /sys/kernel/btf/vmlinux ]] || \
    log "WARNING: /sys/kernel/btf/vmlinux missing on $n -- eBPF network telemetry will be disabled on it (the control loop still runs on thermal signal)"
done

# ---- registry -------------------------------------------------------------
if ! docker ps --format '{{.Names}}' | grep -q '^kubeedgeinfer-registry$'; then
  log "starting local image registry on :5000"
  docker run -d --restart=always -p 5000:5000 --name kubeedgeinfer-registry registry:2
fi

# ---- build ----------------------------------------------------------------
WITH_GPT2="${WITH_GPT2:-0}"
WITH_CUDA=0
[[ "$GPU_NODES" -gt 0 && "$WITH_GPT2" == "1" ]] && WITH_CUDA=1
log "building images (first run takes a few minutes; WITH_GPT2=${WITH_GPT2} WITH_CUDA=${WITH_CUDA})"
docker build -t "${REGISTRY}/kubeedgeinfer/worker:dev" \
  --build-arg WITH_GPT2="${WITH_GPT2}" --build-arg WITH_CUDA="${WITH_CUDA}" \
  -f deploy/docker/worker.Dockerfile .
docker build -t "${REGISTRY}/kubeedgeinfer/controller:dev" -f deploy/docker/controller.Dockerfile .
if [[ "$GPU_NODES" -gt 0 ]]; then
  docker build -t "${REGISTRY}/kubeedgeinfer/nodeagent:dev" \
    --build-arg GO_BUILD_TAGS=gpu -f deploy/docker/nodeagent.Dockerfile .
else
  docker build -t "${REGISTRY}/kubeedgeinfer/nodeagent:dev" -f deploy/docker/nodeagent.Dockerfile .
fi

log "pushing to ${REGISTRY}"
docker push "${REGISTRY}/kubeedgeinfer/worker:dev"
docker push "${REGISTRY}/kubeedgeinfer/controller:dev"
docker push "${REGISTRY}/kubeedgeinfer/nodeagent:dev"

# ---- registry trust (k3s containerd) --------------------------------------
write_registries_yaml() {
  sudo mkdir -p /etc/rancher/k3s
  printf 'mirrors:\n  "%s":\n    endpoint:\n      - "http://%s"\n' "$REGISTRY" "$REGISTRY" \
    | sudo tee /etc/rancher/k3s/registries.yaml >/dev/null
  sudo systemctl restart k3s 2>/dev/null || sudo systemctl restart k3s-agent 2>/dev/null || true
}
log "configuring this node to trust the insecure registry"
write_registries_yaml

if [[ "$WORKER_NODES" -gt 1 ]]; then
  cat <<EOF

*** ACTION NEEDED ON EVERY OTHER MACHINE ***
k3s's containerd must trust the local registry. On each OTHER machine, run:

  sudo mkdir -p /etc/rancher/k3s
  printf 'mirrors:\n  "${REGISTRY}":\n    endpoint:\n      - "http://${REGISTRY}"\n' \\
    | sudo tee /etc/rancher/k3s/registries.yaml
  sudo systemctl restart k3s-agent

Press Enter once every other machine has done this.
EOF
  read -r _
fi

log "waiting for nodes to come back Ready after the restart"
kubectl wait --for=condition=Ready nodes --all --timeout=180s || \
  log "WARNING: not all nodes reported Ready; continuing anyway"

# ---- deploy ---------------------------------------------------------------
log "applying manifests"
kubectl apply -f deploy/manifests/namespace.yaml
kubectl apply -f deploy/manifests/crd.yaml
kubectl apply -f deploy/manifests/rbac.yaml

log "patching image references to ${REGISTRY}"
sed "s#kubeedgeinfer/worker:dev#${REGISTRY}/kubeedgeinfer/worker:dev#;s#kubeedgeinfer/controller:dev#${REGISTRY}/kubeedgeinfer/controller:dev#" \
  deploy/manifests/workers.yaml | kubectl apply -f -
sed "s#kubeedgeinfer/nodeagent:dev#${REGISTRY}/kubeedgeinfer/nodeagent:dev#" \
  deploy/manifests/nodeagent.yaml | kubectl apply -f -
sed "s#kubeedgeinfer/controller:dev#${REGISTRY}/kubeedgeinfer/controller:dev#" \
  deploy/manifests/controller.yaml | kubectl apply -f -
kubectl apply -f deploy/manifests/pipeline.yaml

# The shipped CR expects 3 workers (the kind default); match reality so the
# static-baseline mode doesn't wait forever for a worker that never arrives.
kubectl -n kubeedgeinfer patch inferencepipeline demo --type=merge \
  -p "{\"spec\":{\"workers\":${WORKER_NODES}}}"
log "pipeline expects ${WORKER_NODES} worker(s)"

kubectl -n kubeedgeinfer set env deploy/controller STATIC_MODE=0
if [[ "$GPU_NODES" -gt 0 ]]; then
  kubectl -n kubeedgeinfer set env ds/keinfer-nodeagent GPU_MODE=nvml
  log "real NVML thermal telemetry enabled"
  if [[ "$WITH_GPT2" == "1" ]]; then
    kubectl -n kubeedgeinfer set env ds/keinfer-worker WORKER_DEVICE=cuda
    log "real CUDA inference enabled"
  fi
else
  # No discrete GPU: read the real CPU package temperature instead of the
  # simulated thermal model, so throttling observed here is genuine hardware.
  kubectl -n kubeedgeinfer set env ds/keinfer-nodeagent GPU_MODE=cputherm
  log "real CPU thermal telemetry enabled (GPU_MODE=cputherm)"
fi

log "waiting for pods (first run pulls images over the LAN)"
kubectl -n kubeedgeinfer wait --for=condition=Ready pod --all --timeout=300s || {
  log "not everything became Ready; current state:"
  kubectl -n kubeedgeinfer get pods -o wide
  die "see 'kubectl -n kubeedgeinfer describe pod <name>' for why"
}
kubectl -n kubeedgeinfer get pods -o wide

cat <<EOF

[deploy-real-hardware] up. Next:

  # live dashboard (same one the kind demo uses)
  kubectl -n kubeedgeinfer port-forward svc/router 18080:8080 &
  kubectl -n kubeedgeinfer port-forward svc/controller 18081:8081 &
  python3 demo/serve.py     # then open http://localhost:8000

  kubectl -n kubeedgeinfer get ipl demo    # assignments + bottleneck

To see REAL thermal throttling you must actually heat the machine: run a
sustained load (bench/run.py, or a stress tool) and watch the temp column.
Tune thresholds to your chassis if needed:
  kubectl -n kubeedgeinfer set env ds/keinfer-nodeagent CPU_THROTTLE_C=<C> CPU_UNTHROTTLE_C=<C>
EOF
