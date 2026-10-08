#!/usr/bin/env python3
"""Read-only remote inventory and identity generation for calibrated campaigns."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

MODEL = 'Qwen/Qwen3-0.6B'
REVISION = 'c1899de289a04d12100db370d81485cdf75e47ca'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def inventory(host, config):
    repo, state = config['remote_repo'], config['state_directory']
    cpus = host['compute_cpus']
    script = '''import hashlib,importlib.metadata,json,os,platform,shutil,socket
from pathlib import Path
repo=Path(%r); state=Path(%r)
os.environ['HF_HOME']=str(state/'hf')
files={str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ('worker','internal','cmd','gen/pipelinepb','deploy/standalone','bench') for p in sorted((repo/folder).rglob('*')) if p.is_file() and p.suffix in ('.py','.go','.sh','.json')}
model=next(x.split(':',1)[1].strip() for x in Path('/proc/cpuinfo').read_text().splitlines() if x.startswith('model name'))
mem=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
packages={p:importlib.metadata.version(p) for p in ('torch','transformers','grpcio','protobuf','numpy')}
from huggingface_hub import snapshot_download
checkpoint=snapshot_download(%r,revision=%r,local_files_only=True)
weights=Path(checkpoint)/'model.safetensors'
print(json.dumps(dict(hostname=socket.gethostname(),machine_id=Path('/etc/machine-id').read_text().strip(),cpu=model,platform=platform.platform(),python=platform.python_version(),allowed_cpus=sorted(os.sched_getaffinity(0)),compute_cpus=%r,mem_total_kb=int(mem['MemTotal'].split()[0]),mem_available_kb=int(mem['MemAvailable'].split()[0]),disk_free=shutil.disk_usage(repo).free,btf=Path('/sys/kernel/btf/vmlinux').exists(),packages=packages,source=files,controller_sha256=hashlib.sha256((state/'bin/controller').read_bytes()).hexdigest(),model_revision=%r,weights_sha256=hashlib.sha256(weights.read_bytes()).hexdigest())))
''' % (repo, state, MODEL, REVISION, cpus, REVISION)
    command = [str(Path(state)/'venv/bin/python'), '-c', script]
    if host['ssh'] != 'local':
        command = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', host['ssh'], shlex.join(command)]
    result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=180)
    row = json.loads(result.stdout)
    if not set(cpus) <= set(row['allowed_cpus']) or len(cpus) != len(set(cpus)):
        raise ValueError('invalid reserved compute CPUs on '+host['ssh'])
    if row['mem_available_kb'] < 6*1024*1024 or row['disk_free'] < 5*1024**3:
        raise ValueError('need at least 6 GiB available RAM and 5 GiB free disk on '+host['ssh'])
    if not row['btf']:
        raise ValueError('missing BTF on '+host['ssh'])
    row['ssh'] = host['ssh']
    return row


def preflight(config):
    hosts = [config['coordinator']]+config['workers']
    if len(config['workers']) not in (2, 3):
        raise ValueError('two or three physical workers required')
    if config['coordinator']['ssh'] != 'local':
        raise ValueError('run the campaign from its coordinator; use coordinator ssh=local')
    rows = [inventory(host, config) for host in hosts]
    if len({r['machine_id'] for r in rows}) != len(rows):
        raise ValueError('coordinator and workers must be distinct machines')
    for row in rows[1:]:
        for key in ('source', 'python', 'packages', 'controller_sha256', 'weights_sha256'):
            if row[key] != rows[0][key]:
                raise ValueError('different '+key+' between deployment hosts')
    identity = dict(model=MODEL, source=digest(rows[0]['source']),
                    hardware=digest([{k:r[k] for k in ('machine_id','cpu','platform','allowed_cpus','compute_cpus','mem_total_kb')} for r in rows]),
                    runtime=digest(dict(packages=rows[0]['packages'], weights=rows[0]['weights_sha256'], binary=rows[0]['controller_sha256'], configuration=config)))
    return {'identity': identity, 'hosts': rows, 'scope': 'preflight inventory; no inference or network performance claim'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args=parser.parse_args()
    result=preflight(json.loads(args.config.read_text()))
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/'preflight.json').write_text(json.dumps(result,indent=2)+'\n')
    (args.out/'identity.json').write_text(json.dumps(result['identity'],indent=2)+'\n')
    print('Remote fingerprints verified; deployment identity saved.')


if __name__=='__main__':main()
