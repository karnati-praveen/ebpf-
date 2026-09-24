#!/usr/bin/env bash
# One-time setup of a VM for the standalone (no Kubernetes) deployment.
# Run on EVERY VM. Needs sudo for apt and for the eBPF checks.
#
#   ./deploy/standalone/setup-vm.sh
set -euo pipefail
source "$(dirname "$0")/common.sh"

GO_VERSION="${GO_VERSION:-1.26.1}"
[[ "$(uname -s)" == Linux ]] || die "Linux only"
[[ "$(uname -m)" == x86_64 ]] || die "these steps assume x86_64 (got $(uname -m))"

log "system packages"
sudo apt-get update -qq
sudo apt-get install -y -qq python3-venv python3-dev git curl iproute2 stress-ng >/dev/null

log "Go $GO_VERSION (go.mod requires >= 1.26.1; Ubuntu's apt Go is too old)"
if [[ ! -x "$STATE_DIR/go/bin/go" ]] || ! "$STATE_DIR/go/bin/go" version | grep -q "go$GO_VERSION"; then
  rm -rf "$STATE_DIR/go"
  curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" | tar -xz -C "$STATE_DIR"
fi
export PATH="$STATE_DIR/go/bin:$PATH"

log "building controller and node agent"
mkdir -p "$BIN"
( cd "$REPO" && CGO_ENABLED=0 go build -o "$BIN/controller" ./cmd/controller \
               && CGO_ENABLED=0 go build -o "$BIN/nodeagent" ./cmd/nodeagent )

log "Python venv with pinned, verified versions (isolated; never --break-system-packages)"
[[ -x "$VENV/bin/python" ]] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
case "$WORKER_DEVICE" in
  cpu)
    "$VENV/bin/pip" install -q --index-url https://download.pytorch.org/whl/cpu torch==2.14.0
    ;;
  cuda)
    command -v nvidia-smi >/dev/null 2>&1 || die "CUDA setup needs a working NVIDIA driver (nvidia-smi missing)"
    nvidia-smi -L >/dev/null || die "NVIDIA driver cannot see a GPU"
    TORCH_CUDA_INDEX="${TORCH_CUDA_INDEX:-https://download.pytorch.org/whl/cu130}"
    "$VENV/bin/pip" install -q --index-url "$TORCH_CUDA_INDEX" torch==2.14.0
    ;;
  *) die "WORKER_DEVICE must be cpu or cuda for standalone setup" ;;
esac
"$VENV/bin/pip" install -q -r "$(dirname "$0")/requirements.txt"
if [[ "$WORKER_DEVICE" == cuda ]]; then
  "$VENV/bin/python" - <<'PYCUDA' || die "installed torch cannot use this GPU; check the CUDA wheel index and NVIDIA driver"
import torch
assert torch.cuda.is_available(), f"torch {torch.__version__} cannot see CUDA"
print(f"torch {torch.__version__}, CUDA {torch.version.cuda}, GPU {torch.cuda.get_device_name(0)}")
PYCUDA
fi

log "pre-downloading $MODEL so the first assignment does not stall on the network"
"$VENV/bin/python" - <<PY
from transformers import AutoModelForCausalLM, AutoTokenizer
AutoTokenizer.from_pretrained("$MODEL")
AutoModelForCausalLM.from_pretrained("$MODEL")
print("model cached")
PY

log "eBPF prerequisites"
if [[ -r /sys/kernel/btf/vmlinux ]]; then
  log "  kernel BTF present -- eBPF network telemetry will attach"
else
  log "  WARNING: no /sys/kernel/btf/vmlinux -- the node agent will run without eBPF"
fi

log "network"
IFACE=$(primary_iface)
log "  private IP $(private_ip) on $IFACE"
if ethtool -i "$IFACE" 2>/dev/null | grep -q hv_netvsc && ls /sys/class/net/"$IFACE"/lower_* >/dev/null 2>&1; then
  log "  WARNING: Accelerated Networking appears to be ON. Traffic can take the SR-IOV"
  log "  VF and bypass a qdisc on $IFACE, so tc netem may silently do nothing."
  log "  Create the VM with Accelerated Networking OFF, or verify netem with fault.sh."
fi

log "done. Next: start-coordinator.sh on VM1, start-worker-node.sh on every VM."
