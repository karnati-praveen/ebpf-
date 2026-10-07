#!/usr/bin/env python3
"""Record storage availability during long experiments; never deletes files."""
import argparse
import json
from pathlib import Path
import shutil
import time

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("--path", default="/workspaces")
ap.add_argument("--interval", type=float, default=180)
ap.add_argument("--out", type=Path, required=True)
ap.add_argument("--stop-file", type=Path, required=True)
args = ap.parse_args()
if args.interval < 10:
    ap.error("interval must be at least 10 seconds")
args.out.parent.mkdir(parents=True, exist_ok=True)
with args.out.open("a", buffering=1) as output:
    while not args.stop_file.exists():
        disk = shutil.disk_usage(args.path)
        row = {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "total_bytes": disk.total, "used_bytes": disk.used, "free_bytes": disk.free,
               "used_pct": round(100*disk.used/disk.total, 2)}
        output.write(json.dumps(row)+"\n")
        print(f"{row['utc']} disk {row['used_pct']}% used; {disk.free/2**30:.2f} GiB free", flush=True)
        deadline = time.monotonic() + args.interval
        while time.monotonic() < deadline and not args.stop_file.exists():
            time.sleep(min(5, max(0, deadline-time.monotonic())))
