#!/usr/bin/env bash
# Azure coordinator continuation: never let two controllers drive the workers.
set -euo pipefail
cd "$HOME/shardwise-demand"
matrix_pid=$(cat "$HOME/shardwise-objective/matrix.pid")
echo "Waiting for objective matrix PID $matrix_pid"
while kill -0 "$matrix_pid" 2>/dev/null; do sleep 5; done
python3 - <<'PY'
import json
from pathlib import Path
p=Path.home()/'shardwise-objective'
assert 'MATRIX COMPLETE' in (p/'matrix.log').read_text(), 'objective matrix did not complete cleanly'
assert len(json.loads((p/'results/events.json').read_text()))==20, 'incomplete objective matrix'
PY
set -a
source "$HOME/shardwise/profile.env"
set +a
export KV_CACHE=1 TORCH_THREADS=1
echo "Starting demand matrix at $(date -u +%FT%TZ)"
python3 -u bench/objective_matrix.py --matrix-kind demand \
  --seed 20261014 --out "$HOME/shardwise-demand/results" \
  --controller "$HOME/shardwise-demand/controller"
