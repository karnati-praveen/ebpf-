#!/usr/bin/env bash
# Run once, on the k3s server, after every machine has run
# scripts/join-node.sh and been labeled. Builds GPU-enabled images, gets
# them onto every node via a local registry, and deploys KubeEdgeInfer with
# real NVML telemetry + real CUDA inference on whichever nodes are labeled
# kubeedgeinfer.io/gpu=true.
#
# Assumes: this repo checked out on the server, docker installed, kubectl
# pointed at the k3s cluster (scripts/join-node.sh server already set that
# up). If you have a mix of GPU and CPU-only worker nodes, see the "mixed
# fleet" note in docs/gpu-hardware.md -- this script's fast path assumes all
# worker nodes are GPU nodes, which matches the common case of "N GPU
# machines join the cluster."

set -euo pipefail
cd "$(dirname "$0")/.."

log() { echo "[deploy-real-hardware] $*"; }

SERVER_IP=$(hostname -I | awk '{print $1}')
REGISTRY="${SERVER_IP}:5000"

log "checking node labels"
kubectl get nodes -l kubeedgeinfer.io/worker=true --no-headers | wc -l | xargs -I{} log "{} worker node(s) labeled"
GPU_NODES=$(kubectl get nodes -l kubeedgeinfer.io/gpu=true --no-headers 2>/dev/null | wc -l)
log "${GPU_NODES} GPU node(s) labeled"

if ! docker ps --format '{{.Names}}' | grep -q '^kubeedgeinfer-registry$'; then
  log "starting local image registry on :5000"
  docker run -d --restart=always -p 5000:5000 --name kubeedgeinfer-registry registry:2
fi

log "building images (this takes a few minutes the first time)"
WITH_CUDA=0
[[ "$GPU_NODES" -gt 0 ]] && WITH_CUDA=1
docker build -t "${REGISTRY}/kubeedgeinfer/worker:dev" \
  --build-arg WITH_GPT2=1 --build-arg WITH_CUDA="${WITH_CUDA}" \
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

cat <<EOF

*** ACTION NEEDED ON EVERY NODE (including this one) ***
k3s's containerd needs to trust the insecure local registry. On EACH machine
(server and every agent), run:

  sudo mkdir -p /etc/rancher/k3s
  cat <<REG | sudo tee /etc/rancher/k3s/registries.yaml
mirrors:
  "${REGISTRY}":
    endpoint:
      - "http://${REGISTRY}"
REG
  sudo systemctl restart k3s || sudo systemctl restart k3s-agent

Press Enter once every node has done this and k3s has restarted.
EOF
read -r _

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

kubectl -n kubeedgeinfer set env deploy/controller STATIC_MODE=0
if [[ "$GPU_NODES" -gt 0 ]]; then
  kubectl -n kubeedgeinfer set env ds/keinfer-nodeagent GPU_MODE=nvml
  kubectl -n kubeedgeinfer set env ds/keinfer-worker WORKER_DEVICE=cuda
  log "real NVML telemetry + real CUDA inference enabled"
fi

log "set the pipeline to the GPT-2 backend (edit deploy/manifests/pipeline.yaml: backend: gpt2, or):"
echo "  kubectl -n kubeedgeinfer patch inferencepipeline demo --type=merge -p '{\"spec\":{\"backend\":\"gpt2\"}}'"

log "watch it come up:"
echo "  kubectl -n kubeedgeinfer get pods -w"
echo "  kubectl -n kubeedgeinfer get ipl demo"
