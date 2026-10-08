#!/usr/bin/env python3
"""Physical two/three-worker baseline matrix through existing rootless agents."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import json
import os
from pathlib import Path
import random
import sys

from lan_publication import control, LANRuntime
from lan_agent import MODEL, REVISION
from local_publication import reference, trial, post, load_checkpoint, write_completion
from remote_preflight import digest



def validate_hardware(hardware, workers):
    identities = [h.get('machine_id_sha256') for h in hardware]
    if any(not identity for identity in identities) or len(set(identities)) != workers:
        raise ValueError('workers must report distinct physical machine identities')
    if any(h['packages'] != hardware[0]['packages'] or
           h['serving_source_sha256'] != hardware[0]['serving_source_sha256'] or
           h['model_revision'] != REVISION for h in hardware):
        raise ValueError('agent source/package/model mismatch')
    for host in hardware:
        cpus = host['compute_cpus']
        if not cpus or len(cpus) != len(set(cpus)):
            raise ValueError('compute CPU reservations must be nonempty and unique')
    if len(hardware[0]['compute_cpus']) < workers:
        raise ValueError('first agent needs CPUs for the resource-matched unsplit arm')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agents',required=True,help='comma-separated physical worker agent URLs')
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--repetitions',type=int,default=10)
    parser.add_argument('--contexts',default='32,128,256');parser.add_argument('--concurrency',default='1,2,4,8')
    parser.add_argument('--tokens',type=int,default=16);parser.add_argument('--splits',default='',help='comma-separated layer boundaries including 0,28')
    parser.add_argument('--resume',action='store_true');parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args();agents=args.agents.split(',');n=len(agents)
    if n not in (2,3) or len(set(agents))!=n:parser.error('two or three distinct agent URLs required')
    contexts=list(map(int,args.contexts.split(',')));qs=list(map(int,args.concurrency.split(',')))
    if min(args.repetitions,args.tokens,*contexts,*qs)<1:parser.error('positive counts required')
    cuts=list(map(int,args.splits.split(','))) if args.splits else [28*i//n for i in range(n+1)]
    if len(cuts)!=n+1 or cuts[0]!=0 or cuts[-1]!=28 or any(a>=b for a,b in zip(cuts,cuts[1:])):parser.error('one nonempty range per worker required')
    modes=['unsplit-1t',f'unsplit-{n}t',f'replicas-{n}x1t',f'pipeline-{n}x1t']
    rng=random.Random(20261008);schedule=[]
    for repetition in range(args.repetitions):
        order=modes[:];rng.shuffle(order)
        for mode in order:
            conditions=[(c,q) for c in contexts for q in qs];rng.shuffle(conditions)
            schedule.append(dict(mode=mode,repetition=repetition,conditions=conditions))
    if args.dry_run:print(json.dumps({'schedule':schedule,'cuts':cuts},indent=2));return
    args.out.mkdir(parents=True,exist_ok=True)
    with (args.out/'.driver.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        hardware=[control(u,'/status') for u in agents]
        validate_hardware(hardware,n)
        manifest=dict(evidence_type='physical-host FP32 CPU baseline matrix',hardware=hardware,
                      identity=digest([{k:h[k] for k in ('machine_id_sha256','cpu','platform','compute_cpus','packages','serving_source_sha256')} for h in hardware]),
                      schedule=schedule,tokens=args.tokens,cuts=cuts,agents=agents,
                      contrast_arm=f'pipeline-{n}x1t',contrast_baselines=[f'replicas-{n}x1t',f'unsplit-{n}t','unsplit-1t'],
                      method_description=f'{n} physical workers; one thread per distributed worker; whole-request first-available replicas; unsplit one/{n} threads on first worker; fixed layer boundaries {cuts}; independent greedy references.',
                      scope='natural hardware/network conditions; fixed serving layouts; no adaptive-controller comparison')
        path=args.out/'manifest.json'
        completed=set()
        if path.exists():
            if not args.resume:raise ValueError('output exists; use --resume')
            previous=json.loads(path.read_text())
            # Live PIDs/generation change between runs; immutable environment must match.
            for key in ('identity','schedule','tokens','cuts','agents'):
                if previous[key]!=manifest[key]:raise ValueError('incompatible baseline resume: '+key)
            completed=load_checkpoint(args.out/'runs.jsonl',schedule)
            expected=json.loads((args.out/'reference.json').read_text());prompts=previous['prompts']
        else:
            if args.resume:raise ValueError('missing baseline checkpoint')
            from huggingface_hub import snapshot_download
            model=snapshot_download(MODEL,revision=REVISION,local_files_only=True)
            prompts={str(c):[rng.randrange(1,1000) for _ in range(c)] for c in contexts}
            expected=reference(model,{int(c):p for c,p in prompts.items()},args.tokens)
            manifest['prompts']=prompts;path.write_text(json.dumps(manifest,indent=2)+'\n')
            (args.out/'reference.json').write_text(json.dumps(expected,indent=2)+'\n')
        addresses=[h['worker_addr'] for h in hardware]
        try:
            with (args.out/'runs.jsonl').open('a',buffering=1) as output:
                for block in schedule:
                    missing=[(c,q) for c,q in block['conditions'] if (block['mode'],block['repetition'],c,q) not in completed]
                    if not missing:continue
                    for u in agents:control(u,'/stop',{})
                    mode=block['mode'];configs=[None]*n
                    if mode.startswith('unsplit-'):
                        threads=n if mode==f'unsplit-{n}t' else 1
                        configs[0]={'layers':[0,28],'threads':threads,'chain':[{'addr':addresses[0],'layers':[0,28]}]}
                    elif mode.startswith('replicas-'):
                        configs=[{'layers':[0,28],'threads':1,'chain':[{'addr':addr,'layers':[0,28]}]} for addr in addresses]
                    else:
                        chain=[{'addr':addr,'layers':[cuts[i],cuts[i+1]]} for i,addr in enumerate(addresses)]
                        configs=[{'layers':[cuts[i],cuts[i+1]],'threads':1,'chain':chain,'router':i==0} for i in range(n)]
                    with ThreadPoolExecutor(max_workers=n) as pool:
                        futures=[pool.submit(control,u,'/start',cfg) for u,cfg in zip(agents,configs) if cfg]
                        for future in futures:future.result()
                    urls=[h['router_url'] for h in hardware] if mode.startswith('replicas-') else [hardware[0]['router_url']]
                    for url in urls:post(url,{'input_ids':[17,29,43],'max_new_tokens':4})
                    runtime=LANRuntime(mode,urls,agents);runtime.mode=mode
                    for c,q in missing:
                        result=trial(runtime,prompts[str(c)],expected[str(c)],q,max(4,q))
                        result.update(mode=mode,repetition=block['repetition'],context=c,concurrency=q,output_tokens=args.tokens)
                        output.write(json.dumps(result)+'\n');output.flush();os.fsync(output.fileno())
                        completed.add((mode,block['repetition'],c,q))
                        write_completion(args.out,len(completed),sum(len(b['conditions']) for b in schedule))
                        print(f'{len(completed)} runs: {mode} C={c} Q={q}',flush=True)
        finally:
            for u in agents:
                try:control(u,'/stop',{})
                except Exception:pass


if __name__=='__main__':main()
