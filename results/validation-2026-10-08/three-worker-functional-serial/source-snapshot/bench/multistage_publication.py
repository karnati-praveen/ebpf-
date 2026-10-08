#!/usr/bin/env python3
"""Three-worker real-model follow-up with 256-token context and 32 outputs.

Compare model-capacity and bottleneck placement with three whole-model replicas
and three-thread unsplit execution. Equal three-CPU compute budgets, one other
CPU for coordination. Worker heterogeneity and physical links are not claimed.
Layouts are fixed per concurrency condition, not an adaptive-controller trial.
"""
import argparse
import fcntl
import hashlib
import json
import itertools
import os
from pathlib import Path
import platform
import random
import socket
import subprocess
import sys
import time

from local_publication import ROOT, Runtime, post, reference, trial, load_checkpoint, write_completion

MODES=('unsplit-3t','replicas-3x1t','bottleneck-3x1t','capacity-3x1t')


class ThreeRuntime(Runtime):
    def __init__(self, arm, layouts, *args):
        # Reuse the measured first-available whole-request dispatch, including
        # its wait, without altering the primary campaign's client code.
        mode='replicas-2x1t' if arm=='replicas-3x1t' else arm
        super().__init__(mode, *args)
        self.arm,self.layouts=arm,layouts

    def start(self):
        self.directory.mkdir(parents=True,exist_ok=True)
        active=[(i,tuple(pair)) for i,pair in enumerate(self.layouts) if pair[0]<pair[1]]
        replicas=self.arm=='replicas-3x1t'
        for i,(lo,hi) in active:
            threads=3 if self.arm=='unsplit-3t' else 1
            self.spawn(f'worker-{i}','server.py',{
                'PORT':str(self.base_port+i),'GRPC_HOST':'127.0.0.1','TORCH_THREADS':str(threads),
                'INITIAL_ASSIGNMENT':f'{lo}:{hi}:28:qwen3:{self.model}'},
                self.cpus[:3] if threads==3 else [self.cpus[i]])
            # Each backend initially loads the full checkpoint before keeping
            # its shard. Wait for that peak to pass before loading another.
            self.wait_workers([i])
        router_indices=[i for i,pair in active] if replicas else [0]
        for i in router_indices:
            stages=[(j,pair) for j,pair in active if j==i] if replicas else active
            self.spawn(f'router-{i}','router.py',{
                'GRPC_PORT':str(self.base_port+10+i),'GRPC_HOST':'127.0.0.1',
                'HTTP_HOST':'127.0.0.1','HTTP_PORT':str(self.base_port+20+i),
                'STATIC_PIPELINE':','.join(f'w{j}=127.0.0.1:{self.base_port+j}={lo}={hi}' for j,(lo,hi) in stages)},self.cpus[3:])
            self.urls.append(f'http://127.0.0.1:{self.base_port+20+i}')
        self.wait_workers([i for i,pair in active])
        for url in self.urls:
            for attempt in range(30):
                try:
                    post(url,{'input_ids':[17,29,43],'max_new_tokens':4});break
                except Exception:
                    if attempt==29:raise
                    time.sleep(.1)
        return self

    def wait_workers(self, pending):
        pending=list(pending)
        deadline=time.monotonic()+360
        while pending:
            exited=[(name,p.pid,p.poll()) for name,p in zip(self.process_names,self.processes) if p.poll() is not None]
            if exited:
                raise RuntimeError(f'runtime exited: {exited}; see {self.directory}')
            for i in pending[:]:
                try:
                    with socket.create_connection(('127.0.0.1',self.base_port+i),timeout=.1):
                        pending.remove(i)
                except OSError:pass
            if time.monotonic()>deadline:raise TimeoutError('worker startup timed out')
            time.sleep(.1)


def plan(binary, profile, q, objective, link):
    row=profile['measurements'][0]
    input={'TotalLayers':28,'PerLayerMs':row['decode_ms_per_layer'],
           'EmbedMs':row['decode_embed_ms'],'HeadMs':row['decode_head_ms'],
           'Concurrency':q,'Workers':[{'Name':f'w{i}','Speed':1} for i in range(3)],
           'LinkMs':[link,link]}
    return json.loads(subprocess.check_output([str(binary.resolve()),f'-objective={objective}'],input=json.dumps(input),text=True))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--model',default='Qwen/Qwen3-0.6B')
    ap.add_argument('--profile',type=Path,required=True)
    ap.add_argument('--planner',type=Path,required=True)
    ap.add_argument('--repetitions',type=int,default=10)
    ap.add_argument('--link-ms',type=float,default=1.)
    ap.add_argument('--resume',action='store_true')
    args=ap.parse_args()
    cpus=sorted(os.sched_getaffinity(0))
    if len(cpus)<4:ap.error('three compute CPUs and one coordination CPU required')
    args.out.mkdir(parents=True,exist_ok=True)
    lock=(args.out/'.driver.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:ap.error('driver already live')
    if (args.out/'manifest.json').exists() and not args.resume:ap.error('output exists; use --resume')
    profile=json.loads(args.profile.read_text())
    if profile['measurements'][0]['context_len']!=256:ap.error('profile must measure context 256')
    qvalues=(1,2,4,8)
    plans={f'{objective}:{q}':plan(args.planner,profile,q,objective,args.link_ms) for objective in ('capacity','throughput') for q in qvalues}
    def layout_for(arm,q):
        if arm=='unsplit-3t':return [[0,28]]
        if arm=='replicas-3x1t':return [[0,28]]*3
        return plans[f'{"capacity" if arm.startswith("capacity") else "throughput"}:{q}']['splits']
    rng=random.Random(20261007)
    prompt=[rng.randrange(0,1000) for _ in range(256)]
    schedule=[]
    for r in range(args.repetitions):
        order=list(MODES);rng.shuffle(order)
        for arm in order:
            qs=list(qvalues);rng.shuffle(qs)
            groups={}
            for q in qs:
                key=tuple(map(tuple,layout_for(arm,q)))
                groups.setdefault(key,[]).append(q)
            # One model restart per contiguous layout group. Group order and
            # order within a group derive from the prespecified seeded shuffle.
            schedule.append({'mode':arm,'repetition':r,'conditions':[[256,q] for group in groups.values() for q in group]})
    files=['bench/multistage_publication.py','bench/local_publication.py','bench/profile_qwen3.py',
           'worker/router.py','worker/server.py','worker/backends/qwen3.py','worker/gen/pipeline_pb2.py']
    import importlib.metadata
    manifest={'evidence_type':'real-model three-worker single-host follow-up',
        'cpu':next(x.split(':',1)[1].strip() for x in Path('/proc/cpuinfo').read_text().splitlines() if x.startswith('model name')),
        'cpus':cpus,'inference_cpu_budget':cpus[:3],'coordination_cpus':cpus[3:],
        'model':args.model,'profile':profile,'plans':plans,'link_ms':args.link_ms,
        'link_scope':'configured 1 ms loopback model coefficient; not a WAN measurement',
        'prompts':{'256':prompt},'schedule':schedule,'output_tokens':32,
        'packages':{p:importlib.metadata.version(p) for p in ('torch','transformers','grpcio','protobuf','numpy')},
        'source_sha256':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files},
        'planner_sha256':hashlib.sha256(args.planner.read_bytes()).hexdigest(),
        'contrast_arm':'capacity-3x1t','contrast_baselines':['bottleneck-3x1t','replicas-3x1t','unsplit-3t'],
        'method_description':'Three available compute CPUs, one coordination CPU. FP32 cached Qwen3-0.6B and exact reference outputs; seeded 256-token inputs, 32 output tokens; Q=1/2/4/8; whole-request first-available three replicas; three-thread unsplit; fixed per-Q model-capacity or bottleneck layouts. Component profile measured on the campaign host before runs. Empty model stages do not launch workers, leaving those CPUs unused.',
        'scope':'additional processes on one host, not physical heterogeneity or adaptive controller superiority; conditions sharing a fixed layout share one restart',
        'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
    completed=set();epoch=0
    if args.resume:
        original=json.loads((args.out/'manifest.json').read_text())
        for key in ('cpu','cpus','model','profile','plans','link_ms','prompts','schedule','packages','source_sha256','planner_sha256'):
            if original[key]!=manifest[key]:ap.error(f'resume changed {key}')
        expected=json.loads((args.out/'reference.json').read_text())
        completed=load_checkpoint(args.out/'runs.jsonl',schedule)
        p=args.out/'resumes.jsonl';epoch=len(p.read_text().splitlines())+1 if p.exists() else 1
        with p.open('a') as f:f.write(json.dumps({'execution_epoch':epoch,'completed_before_resume':len(completed),'resumed_utc':manifest['started_utc']})+'\n')
    else:
        (args.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        for f in files:
            p=args.out/'source-snapshot'/f;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/f).read_bytes())
        expected=reference(args.model,{256:prompt},32)
        (args.out/'reference.json').write_text(json.dumps(expected,indent=2)+'\n')
    with (args.out/'runs.jsonl').open('a' if args.resume else 'w',buffering=1) as out:
        for block in schedule:
            arm,r=block['mode'],block['repetition']
            for layout,group in itertools.groupby(block['conditions'],key=lambda condition:tuple(map(tuple,layout_for(arm,condition[1])))):
                missing=[(c,q) for c,q in group if (arm,r,c,q) not in completed]
                if not missing:continue
                layouts=[list(pair) for pair in layout]
                directory=args.out/f'r{r:02d}-{arm}-q{missing[0][1]}-epoch{epoch}'
                with ThreeRuntime(arm,layouts,args.model,directory,cpus,55000) as runtime:
                    for context,q in missing:
                        result=trial(runtime,prompt,expected['256'],q,max(4,q))
                        result.update(mode=arm,repetition=r,context=context,concurrency=q,output_tokens=32,execution_epoch=epoch,layouts=layouts)
                        out.write(json.dumps(result)+'\n');out.flush();os.fsync(out.fileno())
                        completed.add((arm,r,context,q));write_completion(args.out,len(completed),len(schedule)*4)
                        print(f'r={r} {arm} Q={q} layouts={layouts} TPS={result["whole_run_tps"]:.3f} failures={result["failures"]}',flush=True)
    write_completion(args.out,len(completed),len(schedule)*4)


if __name__=='__main__':main()
