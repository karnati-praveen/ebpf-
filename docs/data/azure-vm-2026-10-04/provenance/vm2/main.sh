#!/bin/bash
# Confirmatory matrix (pilot data is not reused). Faults on vm3 only.
cd ~/ebpf-
echo "MAIN START $(date -u +%T)"
python3 -u bench/vmrun.py --workers 2 --hosts vm3 --target vm3 \
  --scenarios network:120,compute:0.5 --policies static,hysteresis,gate,gate-force \
  --repeats 3 --seed 20261004 --pre-s 40 --fault-s 120 --post-s 60 --out ~/ebpf-/bench/results/vm
echo "CORE DONE $(date -u +%T)"
python3 -u bench/vmrun.py --workers 2 --hosts vm3 --target vm3 \
  --scenarios loss:0 --policies static,hysteresis,gate \
  --repeats 2 --seed 20261005 --pre-s 40 --fault-s 120 --post-s 60 --out ~/ebpf-/bench/results/vm
echo "MAIN DONE $(date -u +%T)"
