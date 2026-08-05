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
die() { echo "[join-node] ERROR: $*" >&2; exit 1; }

# Root containers (most rented GPU boxes) have no sudo and don't need it.
if [[ "$(id -u)" -eq 0 ]]; then
  SUDO=""
elif command -v sudo >/dev/null 2>&1; then
  SUDO="sudo"
else
  die "not root and no sudo available -- re-run as root"
fi

# k3s's installer wants a service manager. Rented GPU boxes are usually
# containers with no systemd, where it installs but cannot start anything;
# there we launch k3s directly instead.
HAVE_SYSTEMD=0
[[ -d /run/systemd/system ]] && HAVE_SYSTEMD=1

# ---- preflight ------------------------------------------------------------
[[ "$(uname -s)" == "Linux" ]] || die "this project needs Linux (eBPF + privileged DaemonSets); macOS/Windows can only run the kind demo inside a Linux VM"

# eBPF CO-RE needs BTF. Without it the node agent still runs (it logs a
# warning and drops network telemetry), so this is a warning, not fatal.
if [[ ! -r /sys/kernel/btf/vmlinux ]]; then
  log "WARNING: /sys/kernel/btf/vmlinux not found -- eBPF network telemetry will be"
  log "         disabled on this machine (kernel needs CONFIG_DEBUG_INFO_BTF=y, ~5.8+)."
  log "         The thermal control loop still works."
else
  log "BTF present: eBPF telemetry supported ($(uname -r))"
fi

log "architecture: $(uname -m) -- every machine in the cluster must match, or you must build multi-arch images (docs/laptops.md)"

if [[ "$ROLE" == "agent" ]]; then
  SERVER_IP_PRE="${2:-}"
  [[ -n "$SERVER_IP_PRE" && -n "${3:-}" ]] || die "agent mode needs: $0 agent <server-ip> <node-token>"
  # Fail early and clearly on the single most common two-laptop problem.
  if command -v curl >/dev/null; then
    curl -sk --connect-timeout 5 "https://${SERVER_IP_PRE}:6443" >/dev/null 2>&1 \
      || die "cannot reach ${SERVER_IP_PRE}:6443 from this machine.
  Check: both machines on the same network, and the SERVER's firewall allows
    6443/tcp (API), 8472/udp (flannel VXLAN), 10250/tcp (kubelet), 5000/tcp (registry).
  On the server:  sudo ufw allow 6443/tcp && sudo ufw allow 8472/udp && sudo ufw allow 10250/tcp && sudo ufw allow 5000/tcp"
    log "server ${SERVER_IP_PRE}:6443 reachable"
  fi
fi

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
      | $SUDO gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
    curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
      | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
      | $SUDO tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
    $SUDO apt-get update -qq && $SUDO apt-get install -y nvidia-container-toolkit
  fi
fi

if [[ "$ROLE" == "server" ]]; then
  if [[ "$HAVE_SYSTEMD" == "1" ]]; then
    log "installing k3s as server"
    curl -sfL https://get.k3s.io | $SUDO sh -
  else
    log "no systemd detected (container environment) -- installing k3s and starting it directly"
    curl -sfL https://get.k3s.io | \
      $SUDO env INSTALL_K3S_SKIP_START=true INSTALL_K3S_SKIP_ENABLE=true sh -
    $SUDO sh -c 'nohup k3s server --write-kubeconfig-mode 644 >/var/log/k3s.log 2>&1 &'
    log "k3s starting in the background (log: /var/log/k3s.log)"
  fi
  log "waiting for k3s to be ready (up to 3 minutes)"
  for _ in $(seq 1 90); do
    $SUDO k3s kubectl get nodes >/dev/null 2>&1 && break
    sleep 2
  done
  $SUDO k3s kubectl get nodes >/dev/null 2>&1 || die "k3s did not become ready.
  Check /var/log/k3s.log (or 'journalctl -u k3s' if systemd).
  k3s needs a privileged container; if this box is an unprivileged container,
  Kubernetes cannot run here -- use the no-Kubernetes path instead:
    ./scripts/run-single-gpu.sh     (see docs/single-gpu.md)"
  mkdir -p "$HOME/.kube"
  $SUDO cp /etc/rancher/k3s/k3s.yaml "$HOME/.kube/config"
  $SUDO chown "$(id -u):$(id -g)" "$HOME/.kube/config"
  TOKEN=$(${SUDO} cat /var/lib/rancher/k3s/server/node-token)
  SERVER_IP="${SERVER_IP:-$(hostname -I | awk '{print $1}')}"
  # Open the ports agents need, if a firewall is active.
  if command -v ufw >/dev/null && $SUDO ufw status 2>/dev/null | grep -q "Status: active"; then
    log "ufw is active -- opening cluster ports"
    for p in 6443/tcp 8472/udp 10250/tcp 5000/tcp; do $SUDO ufw allow "$p" >/dev/null || true; done
  fi
  log "server ready. Give this to the other machines:"
  echo
  echo "  ./scripts/join-node.sh agent ${SERVER_IP} ${TOKEN}"
  echo
  log "(if ${SERVER_IP} is the wrong interface -- e.g. a docker/VPN address --"
  log " re-read it from 'ip addr' and use the LAN address the other laptop can ping)"
else
  SERVER_IP="$2"
  TOKEN="$3"
  log "installing k3s as agent, joining ${SERVER_IP}"
  curl -sfL https://get.k3s.io | \
    $SUDO env K3S_URL="https://${SERVER_IP}:6443" K3S_TOKEN="${TOKEN}" sh -
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
