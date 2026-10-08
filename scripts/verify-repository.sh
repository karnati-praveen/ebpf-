#!/usr/bin/env bash
# Fast verification from a clean checkout; model/hardware campaigns are separate.
set -euo pipefail
cd "$(dirname "$0")/.."
VERIFY_PYTHON="${VERIFY_PYTHON:-python3}"
go test ./...
go vet ./...
go build ./...
go test -race ./internal/...
"$VERIFY_PYTHON" -m unittest discover -s worker -p 'test*.py'
"$VERIFY_PYTHON" -m unittest discover -s bench -p 'test*.py'
"$VERIFY_PYTHON" - <<'PY'
import ast
import subprocess
from pathlib import Path
files = subprocess.check_output(['git', 'ls-files', '-z']).decode().split('\0')
counts = {'python': 0, 'shell': 0}
for name in filter(None, files):
    path = Path(name)
    if path.suffix == '.py':
        ast.parse(path.read_text(), filename=name)
        counts['python'] += 1
    elif path.suffix == '.sh':
        subprocess.run(['bash', '-n', str(path)], check=True)
        counts['shell'] += 1
print('Syntax verification:', counts)
PY
git diff --check
