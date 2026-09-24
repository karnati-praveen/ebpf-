#!/usr/bin/env bash
# Stop everything this VM runs and clear any injected fault.
set -euo pipefail
source "$(dirname "$0")/common.sh"
"$(dirname "$0")/fault.sh" clear >/dev/null 2>&1 || true
for n in controller router worker nodeagent; do stop_one "$n"; done
log "stopped"
