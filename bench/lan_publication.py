#!/usr/bin/env python3
"""Coordinate real two-laptop fixed-layout comparisons or manual replay checks.

The peers must voluntarily run lan_agent.py. No SSH credentials or shell access
are needed. The lab token is read from the environment and never saved in data.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import time
import urllib.request

from local_publication import reference,trial,post,load_checkpoint,write_completion
from lan_agent import MODEL,REVISION


def control(url,path,body=None):
    req=urllib.request.Request(url.rstrip('/')+path,data=None if body is None else json.dumps(body).encode(),
        headers={'X-Lab-Token':os.environ['SHARDWISE_LAB_TOKEN'],'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=900) as reply:return json.load(reply)


class LANRuntime:
    def __init__(self,mode,urls,agents):
        self.mode='replicas-2x1t' if mode=='replicas-2x1t' else mode
        self.urls=urls;self.agents=agents
    def memory_snapshot(self):return [control(u,'/status') for u in self.agents]


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--local',required=True,help='local laptop agent URL')
    ap.add_argument('--peer',required=True,help='friend laptop agent URL')
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--repetitions',type=int,default=10)
    ap.add_argument('--contexts',default='32,128');ap.add_argument('--concurrency',default='1,2,4,8')
    ap.add_argument('--tokens',type=int,default=16);ap.add_argument('--split',type=int,default=18)
    ap.add_argument('--resume',action='store_true')
    ap.add_argument('--recovery',action='store_true',help='manual loss and promotion after observed output progress')
    ap.add_argument('--position',type=int,default=4)
    a=ap.parse_args()
    if not os.environ.get('SHARDWISE_LAB_TOKEN'):ap.error('set the same SHARDWISE_LAB_TOKEN as the two agents')
    if a.local==a.peer or not 0<a.split<28:ap.error('distinct agents and nonempty pipeline stages required')
    contexts=list(map(int,a.contexts.split(',')));qs=list(map(int,a.concurrency.split(',')))
    if min(a.repetitions,a.tokens,*contexts,*qs)<1:ap.error('positive counts required')
    a.out.mkdir(parents=True,exist_ok=True)
    # Windows has no fcntl; Linux/WSL is the coordinator supported below.
    lock=(a.out/'.driver.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if (a.out/'manifest.json').exists() and not a.resume:ap.error('output exists; use a new directory or --resume')
    agents=[a.local,a.peer];hardware=[control(u,'/status') for u in agents]
    if any(h['model_revision']!=REVISION for h in hardware) or hardware[0]['packages']!=hardware[1]['packages'] or hardware[0]['serving_source_sha256']!=hardware[1]['serving_source_sha256']:
        ap.error('model revisions and package versions must match between laptops')
    rng=random.Random(20261007);prompts={c:[rng.randrange(0,1000) for _ in range(c)] for c in contexts}
    schedule=[]
    modes=['unsplit-1t','unsplit-2t','replicas-2x1t','pipeline-2x1t']
    if a.recovery:modes=['manual-loss-replay'];contexts=contexts[:1];qs=[1]
    for r in range(a.repetitions):
        order=modes[:];rng.shuffle(order)
        for mode in order:
            conditions=[(c,q) for c in contexts for q in qs];rng.shuffle(conditions)
            schedule.append({'mode':mode,'repetition':r,'conditions':conditions})
    manifest={'evidence_type':'real-model two-physical-laptop LAN measurements',
        'model':MODEL,'model_revision':REVISION,'hardware':hardware,'agents':agents,'prompts':prompts,
        'schedule':schedule,'arguments':{k:v for k,v in vars(a).items() if k not in ('resume','out')},
        'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
        'method_description':f'Two physical laptops; one compute thread per distributed worker; unsplit one/two threads on the coordinator laptop; replica whole-request first-available dispatch; pipeline split {a.split}/{28-a.split}; cached FP32 pinned Qwen3-0.6B, fixed seeded token inputs. Peer HTTP request routing and pipeline gRPC transport are both measured by the coordinator client.',
        'scope':'heterogeneous physical hardware allowed and recorded; natural network conditions; fixed layouts; no automatic controller comparison',
        'source_sha256':{f:hashlib.sha256((Path(__file__).parent/f).read_bytes()).hexdigest() for f in ('lan_agent.py','lan_publication.py','local_publication.py')}}
    completed=set();epoch=0
    if a.resume:
        old=json.loads((a.out/'manifest.json').read_text())
        for key in ('arguments','source_sha256'):
            if old[key]!=manifest[key]:ap.error(f'resume changed {key}')
        for before,now in zip(old['hardware'],hardware):
            for key in ('cpu','platform','packages','compute_cpus','affinity_control','serving_source_sha256'):
                if before[key]!=now[key]:ap.error(f'peer hardware/environment changed: {key}')
        prompts={int(k):v for k,v in old['prompts'].items()};schedule=old['schedule']
        expected=json.loads((a.out/'reference.json').read_text());completed=load_checkpoint(a.out/'runs.jsonl',schedule)
        path=a.out/'resumes.jsonl';epoch=len(path.read_text().splitlines())+1 if path.exists() else 1
        with path.open('a') as f:f.write(json.dumps({'epoch':epoch,'observed_at':time.time(),'completed_before':len(completed)})+'\n')
    else:
        (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        from huggingface_hub import snapshot_download
        model=snapshot_download(MODEL,revision=REVISION,allow_patterns=['*.json','*.safetensors','*.txt','*.model','*.jinja'])
        expected=reference(model,prompts,a.tokens)
        (a.out/'reference.json').write_text(json.dumps(expected,indent=2)+'\n')
    aa,bb=[h['worker_addr'] for h in hardware]
    def setup(mode):
        for u in agents:control(u,'/stop',{})
        full_a={'layers':[0,28],'threads':2 if mode=='unsplit-2t' else 1,'chain':[{'addr':aa,'layers':[0,28]}]}
        configurations=[full_a,None]
        if mode=='replicas-2x1t':configurations[1]={'layers':[0,28],'threads':1,'chain':[{'addr':bb,'layers':[0,28]}]}
        elif mode in ('pipeline-2x1t','manual-loss-replay'):
            configurations=[{'layers':[0,a.split],'threads':1,'chain':[{'addr':aa,'layers':[0,a.split]},{'addr':bb,'layers':[a.split,28]}]},
                {'layers':[a.split,28],'threads':1,'chain':[{'addr':bb,'layers':[a.split,28]}],'router':False}]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(control,u,'/start',cfg) for u,cfg in zip(agents,configurations) if cfg]
            for f in futures:f.result()
        urls=[hardware[0]['router_url']]+([hardware[1]['router_url']] if mode=='replicas-2x1t' else [])
        for url in urls:
            for attempt in range(30):
                try:post(url,{'input_ids':[17,29,43],'max_new_tokens':4});break
                except Exception:
                    if attempt==29:raise
                    time.sleep(.2)
        return LANRuntime(mode,urls,agents)
    try:
        with (a.out/'runs.jsonl').open('a' if a.resume else 'w',buffering=1) as output:
            for block in schedule:
                missing=[(c,q) for c,q in block['conditions'] if (block['mode'],block['repetition'],c,q) not in completed]
                if not missing:continue
                runtime=setup(block['mode'])
                for c,q in missing:
                    if not a.recovery:result=trial(runtime,prompts[c],expected[str(c)],q,max(4,q))
                    else:
                        if not 0<a.position<a.tokens:ap.error('position must fall within output')
                        with ThreadPoolExecutor(max_workers=1) as pool:
                            pending=pool.submit(post,runtime.urls[0],{'input_ids':prompts[c],'max_new_tokens':a.tokens})
                            deadline=time.monotonic()+300
                            observed=None
                            reached=False
                            while not pending.done() and time.monotonic()<deadline:
                                with urllib.request.urlopen(runtime.urls[0]+'/workload',timeout=5) as response:observed=json.load(response)
                                if observed['active_requests'] and a.tokens-observed['remaining_tokens']>=a.position:
                                    reached=True;break
                                time.sleep(.02)
                            if pending.done() or not reached:raise RuntimeError('fault trigger not reached while request was active; increase output length or lower position')
                            fault=control(a.peer,'/stop-worker',{})
                            promotion=control(a.local,'/promote-full',{})
                            reply=pending.result(timeout=900)
                        gaps=[b-a for a,b in zip(reply['token_times_ms'],reply['token_times_ms'][1:])]
                        result={'whole_run_s':reply['duration_ms']/1000,'whole_run_tps':reply['tokens_per_sec'],
                            'failures':int(reply['tokens']!=expected[str(c)]),'requests':[{'ok':reply['tokens']==expected[str(c)],'reply':reply}],
                            'median_client_duration_ms':reply['duration_ms'],'median_ttft_ms':reply['ttft_ms'],
                            'fault_observation':observed,'fault':fault,'promotion':promotion,'maximum_internal_token_gap_ms':max(gaps,default=0),
                            'scope':'manual orchestration; observed position can overshoot polling target; final HTTP JSON is not streaming delivery'}
                    result.update(mode=block['mode'],repetition=block['repetition'],context=c,concurrency=q,output_tokens=a.tokens,execution_epoch=epoch,observed_at=time.time())
                    output.write(json.dumps(result)+'\n');output.flush();os.fsync(output.fileno())
                    completed.add((block['mode'],block['repetition'],c,q));write_completion(a.out,len(completed),sum(len(b['conditions']) for b in schedule))
                    print(f'{len(completed)} runs: {block["mode"]} C={c} Q={q}, TPS={result["whole_run_tps"]:.3f}, failures={result["failures"]}',flush=True)
    finally:
        for u in agents:
            try:control(u,'/stop',{})
            except Exception:pass


if __name__=='__main__':main()
