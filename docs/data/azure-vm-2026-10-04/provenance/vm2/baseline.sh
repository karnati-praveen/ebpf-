#!/bin/bash
# Single-device baseline (A13): vm3 stopped, the whole model on vm2, no fault.
cd ~/ebpf-
while pgrep -f "/home/azureuser/[m]ain.sh" >/dev/null; do sleep 10; done
echo "BASELINE START $(date -u +%T)"
ssh vm3 ~/ebpf-/deploy/standalone/stop.sh
sleep 10
python3 -u bench/vmrun.py --workers 1 --scenarios stable:0 --policies static \
  --repeats 3 --seed 20261006 --pre-s 40 --fault-s 120 --post-s 60 --out ~/ebpf-/bench/results/vm-single
echo "BASELINE DONE $(date -u +%T)"
ssh vm3 ~/ebpf-/deploy/standalone/start-worker-node.sh 10.10.1.4 >/dev/null
