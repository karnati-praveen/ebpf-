#!/usr/bin/env python3
"""Sequence costly follow-ups after completion; never overlap inference campaigns."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--main',type=Path,required=True)
ap.add_argument('--engine',type=Path,required=True)
ap.add_argument('--multistage',type=Path,required=True)
a=ap.parse_args()
while not (a.main/'completion-status.json').exists() or not json.loads((a.main/'completion-status.json').read_text())['complete']:
    time.sleep(10)
m=json.loads((a.main/'manifest.json').read_text())
cpu=next(x.split(':',1)[1].strip() for x in Path('/proc/cpuinfo').read_text().splitlines() if x.startswith('model name'))
if m['cpu']!=cpu:raise RuntimeError('completed main campaign belongs to a different CPU model')
def run(*args):subprocess.run(args,cwd=ROOT,check=True)
run(sys.executable,'scripts/run-optimized-baseline.py','--checkout','.publication-tools/llama.cpp','--source',str(a.main),'--out',str(a.engine))
a.multistage.mkdir(parents=True,exist_ok=True)
profile=a.multistage/'component-profile.json'
if not profile.exists():
    env=dict(os.environ,TORCH_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',HF_HUB_OFFLINE='1')
    subprocess.run(['taskset','-c','0',sys.executable,'bench/profile_qwen3.py','--device','cpu','--contexts','256','--warmup','2','--samples','5','--out',str(profile)],cwd=ROOT,env=env,check=True)
run('taskset','-c','2,3','go','build','-o','.publication-tools/partitionplan','./cmd/partitionplan')
run(sys.executable,'bench/multistage_publication.py','--out',str(a.multistage),'--profile',str(profile),'--planner','.publication-tools/partitionplan',*(['--resume'] if (a.multistage/'manifest.json').exists() else []))
run(sys.executable,'bench/publication_analyze.py',str(a.multistage))
print('Follow-up campaigns completed',flush=True)
