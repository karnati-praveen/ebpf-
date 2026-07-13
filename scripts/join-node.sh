#!/usr/bin/env bash
# Run this on each machine you want to add to the cluster (your desktop +
# your friend's two GPU machines). Auto-detects whether the machine has an
# NVIDIA GPU and whether it should be the k3s server (first machine) or an
# agent joining an existing one, then labels the node so the existing
# manifests' nodeSelectors pick it up unchanged. This is the "any person can
# use it" entry point -- one script, run once per machine, no manual YAML
# editing. See docs/gpu-hardware.md for the full walkthrough and the
# concrete two-GPU example this was built for.
#
# Usage:
#   First machine (becomes the k3s server):
#     ./scripts/join-node.sh server
#   Every other machine (needs the server's LAN IP and node token):
#     ./scripts/join-node.sh agent <server-ip> <node-token>
#
# The node token is printed by this script when run with `server`, and also
# readable afterwards on the server at
# /var/lib/rancher/k3s/server/node-token

set -euo pipefail

ROLE="${1:-}"
if [[ "$ROLE" != "server" && "$ROLE" != "agent" ]]; then
  echo "usage: $0 server | $0 agent <server-ip> <node-token>" >&2
  exit 1
fi

log() { echo "[join-node] $*"; }

has_gpu=0
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
  has_gpu=1
  log "NVIDIA GPU detected: $(nvidia-smi -L | head -1)"
else
  log "no NVIDIA GPU detected (nvidia-smi missing or failed) -- this node will run GPU_MODE=cputherm"
fi

if [[ "$has_gpu" == "1" ]]; then
  if ! dpkg -l | grep -q nvidia-container-toolkit 2>/dev/null; then
    log "installing nvidia-container-toolkit (required for K8s to pass the GPU into containers)"
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
      | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
    curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
      | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
      | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
    sudo apt-get update -qq && sudo apt-get install -y nvidia-container-toolkit
  fi
fi

if [[ "$ROLE" == "server" ]]; then
  log "installing k3s as server"
  curl -sfL https://get.k3s.io | sh -
  log "waiting for k3s to be ready"
  until sudo k3s kubectl get nodes >/dev/null 2>&1; do sleep 2; done
  mkdir -p "$HOME/.kube"
  sudo cp /etc/rancher/k3s/k3s.yaml "$HOME/.kube/config"
  sudo chown "$(id -u):$(id -g)" "$HOME/.kube/config"
  TOKEN=$(sudo cat /var/lib/rancher/k3s/server/node-token)
  SERVER_IP=$(hostname -I | awk '{print $1}')
  log "server ready. Give this to the other machines:"
  echo
  echo "  ./scripts/join-node.sh agent ${SERVER_IP} ${TOKEN}"
  echo
else
  SERVER_IP="$2"
  TOKEN="$3"
  log "installing k3s as agent, joining ${SERVER_IP}"
  curl -sfL https://get.k3s.io | \
    K3S_URL="https://${SERVER_IP}:6443" K3S_TOKEN="${TOKEN}" sh -
fi

NODE_NAME=$(hostname)
if [[ "$ROLE" == "agent" ]]; then
  # Agents don't have a local kubeconfig; label via the server isn't possible
  # from here, so print the exact commands to run on the server.
  log "node will register as '${NODE_NAME}'. On the SERVER machine, run:"
  echo
  echo "  kubectl label node ${NODE_NAME} kubeedgeinfer.io/worker=true"
  if [[ "$has_gpu" == "1" ]]; then
    echo "  kubectl label node ${NODE_NAME} kubeedgeinfer.io/gpu=true"
  fi
  echo
else
  kubectl label node "$NODE_NAME" kubeedgeinfer.io/worker=true --overwrite
  if [[ "$has_gpu" == "1" ]]; then
    kubectl label node "$NODE_NAME" kubeedgeinfer.io/gpu=true --overwrite
  fi
  log "labeled ${NODE_NAME}"
fi

log "done. Once every worker node is joined and labeled, run ./scripts/deploy-real-hardware.sh from the server."
