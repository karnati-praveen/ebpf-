#!/usr/bin/env bash
# Inject or clear a fault on THIS VM. Run on a worker VM (VM2/VM3), never on the
# coordinator: faults must degrade a pipeline stage, not the control path.
#
#   fault.sh compute <cpus>       cap the worker at <cpus> CPUs (cgroup v2 cpu.max)
#   fault.sh contention <n>       run <n> CPU-burning processes beside the worker
#   fault.sh network <ms> [jit]   delay this worker's pipeline replies by <ms>
#   fault.sh loss                 stop this VM's worker and node agent (device loss)
#   fault.sh restore <coord-ip>   restart them after a loss
#   fault.sh clear                remove compute/contention/network faults
#   fault.sh status               show what is active, with evidence
#
# Every action prints a UTC timestamp line so the driver can record exact
# fault onset and clearance. Compute and contention are CONTROLLED compute
# degradation -- on VMs they stand in for, but are not, thermal throttling.
set -euo pipefail
source "$(dirname "$0")/common.sh"

CG=/sys/fs/cgroup/keinfer-fault
IFACE="${FAULT_IFACE:-$(primary_iface)}"  # FAULT_IFACE: local testing only
stamp() { echo "FAULT_EVENT $(date -u +%s.%N) $*"; }

worker_pid() {
  [[ -f "$PID_DIR/worker.child" ]] || die "worker not running under start-worker-node.sh"
  cat "$PID_DIR/worker.child"
}

clear_compute() {
  if [[ -d "$CG" ]]; then echo "max 100000" | sudo tee "$CG/cpu.max" >/dev/null; fi
}
clear_contention() {
  if [[ -f "$PID_DIR/contention.pid" ]]; then
    sudo kill "$(cat "$PID_DIR/contention.pid")" 2>/dev/null || true
    rm -f "$PID_DIR/contention.pid"
  fi
  sudo pkill -x stress-ng 2>/dev/null || true
}
clear_network() {
  sudo tc qdisc del dev "$IFACE" root 2>/dev/null || true
}

case "${1:-}" in
  compute)
    cpus="${2:?cpus}"
    pid=$(worker_pid)
    sudo mkdir -p "$CG"
    grep -qw cpu /sys/fs/cgroup/cgroup.subtree_control || echo +cpu | sudo tee /sys/fs/cgroup/cgroup.subtree_control >/dev/null
    quota=$(python3 -c "print(int(float('$cpus') * 100000))")
    echo "$quota 100000" | sudo tee "$CG/cpu.max" >/dev/null
    echo "$pid" | sudo tee "$CG/cgroup.procs" >/dev/null   # moves every thread
    stamp "compute_on cpus=$cpus pid=$pid"
    ;;
  contention)
    n="${2:?n}"
    clear_contention
    sudo nohup stress-ng --cpu "$n" --cpu-method matrixprod >/dev/null 2>&1 &
    echo $! >"$PID_DIR/contention.pid"
    stamp "contention_on n=$n"
    ;;
  network)
    ms="${2:?ms}"; jit="${3:-0}"
    clear_network
    # prio with every priority mapped to band 1:1, so ONLY traffic matched by
    # the filter reaches the netem band. A plain root netem would also delay
    # SSH and the telemetry path, and the default prio priomap sends most
    # traffic to 1:3 -- which would delay it too.
    sudo tc qdisc add dev "$IFACE" root handle 1: prio bands 3 priomap 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
    if [[ "$jit" != 0 ]]; then
      sudo tc qdisc add dev "$IFACE" parent 1:3 handle 30: netem delay "${ms}ms" "${jit}ms"
    else
      sudo tc qdisc add dev "$IFACE" parent 1:3 handle 30: netem delay "${ms}ms"
    fi
    # Match this worker's replies (source port = worker port): the router's
    # round trip to this stage grows by <ms>, nothing else does.
    sudo tc filter add dev "$IFACE" parent 1: protocol ip prio 1 u32 \
      match ip sport "$WORKER_PORT" 0xffff flowid 1:3
    stamp "network_on delay_ms=$ms jitter_ms=$jit iface=$IFACE"
    ;;
  loss)
    stop_one worker
    stop_one nodeagent
    stamp "loss_on"
    ;;
  restore)
    coord="${2:?coordinator ip}"
    "$(dirname "$0")/start-worker-node.sh" "$coord"
    stamp "loss_off"
    ;;
  clear)
    clear_compute; clear_contention; clear_network
    stamp "cleared"
    ;;
  status)
    echo "compute:    $([[ -d $CG ]] && cat $CG/cpu.max || echo none)"
    echo "contention: $([[ -f $PID_DIR/contention.pid ]] && echo "pid $(cat $PID_DIR/contention.pid)" || echo none)"
    echo "network ($IFACE):"
    # Packet counts on class 1:3 are the evidence that netem actually bit. If
    # they stay at 0 while the pipeline runs, traffic is bypassing the qdisc
    # (Azure Accelerated Networking) and the network fault is NOT in effect.
    tc -s class show dev "$IFACE" 2>/dev/null | sed -n '/1:3/,+2p' || true
    tc qdisc show dev "$IFACE"
    ;;
  *) sed -n '2,17p' "$0"; exit 2 ;;
esac
