#!/usr/bin/env python3
"""Checkpointed, sequential remote controller campaign. Run on the coordinator."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import time

from remote_preflight import MODEL, REVISION, digest, preflight

ROOT=Path(__file__).resolve().parents[1]
ARMS={
 'hysteresis': {'POLICY':'hysteresis','LIVE_REPLAY_CONTEXT':'0'},
 'gate': {'POLICY':'gate','LIVE_REPLAY_CONTEXT':'0'},
 'gate-calibrated': {'POLICY':'gate-calibrated'},
 'no-calibration': {'POLICY':'gate-calibrated','CALIBRATED_NO_CALIBRATION':'1'},
 'point-only': {'POLICY':'gate-calibrated','CALIBRATED_POINT_ONLY':'1'},
 'profile-context': {'POLICY':'gate-calibrated','CALIBRATED_PROFILE_CONTEXT':'1'},
 'queue-corrected': {'POLICY':'gate-calibrated','APP_LINK_MODE':'queue-corrected','LINK_SOURCE':'app'},
 'app-residual': {'POLICY':'gate-calibrated','APP_LINK_MODE':'residual','LINK_SOURCE':'app'},
 'online': {'POLICY':'gate-calibrated','CALIBRATION_ONLINE':'1'},
 'remaining-work': {'POLICY':'gate-calibrated','REMAINING_WORK_AWARE':'1'},
}


def schedule(config, phase, repeats, seed):
    if phase=='calibration':
        conditions=[dict(context=128,tokens=32,concurrency=2,demand='continuing',scenario=s) for s in ('compute:0.5','network:120')]
        arms=['hysteresis']
    else:
        conditions=config.get('controller_conditions',[dict(context=128,tokens=64,concurrency=q,demand=d,scenario=s)
            for q in (2,4) for d in ('finite','continuing') for s in ('stable:0','compute:0.5','network:120','loss:0')])
        arms=config.get('controller_arms',['hysteresis','gate','gate-calibrated'])
    if any(a not in ARMS for a in arms):raise ValueError('unknown controller arm')
    rng=random.Random(seed);rows=[]
    for repetition in range(repeats):
        entries=[dict(condition,arm=arm,repetition=repetition) for condition in conditions for arm in arms]
        rng.shuffle(entries)
        for entry in entries:entry['id']=digest(entry)[:20]
        rows+=entries
    return rows


def checkpoint(path, expected):
    rows=[] if not path.exists() else [json.loads(line) for line in path.read_text().splitlines()]
    keys=[r['id'] for r in rows]
    if len(keys)!=len(set(keys)) or not set(keys)<=set(expected):raise ValueError('duplicate or unscheduled checkpoint')
    return rows


def completion(directory, count, expected, stopped=False):
    data=dict(completed_runs=count,expected_runs=expected,complete=count==expected,
              state='complete' if count==expected else 'interrupted' if stopped else 'running')
    temp=directory/'completion-status.pending'
    temp.write_text(json.dumps(data,indent=2)+'\n');temp.replace(directory/'completion-status.json')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--config',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--phase',choices=['calibration','evaluation'],default='evaluation')
    ap.add_argument('--calibration',type=Path);ap.add_argument('--repetitions',type=int,default=10)
    ap.add_argument('--seed',type=int,default=20261008);ap.add_argument('--resume',action='store_true')
    ap.add_argument('--dry-run',action='store_true');ap.add_argument('--limit-runs',type=int)
    a=ap.parse_args();config=json.loads(a.config.read_text());planned=schedule(config,a.phase,a.repetitions,a.seed)
    if a.repetitions<1 or (a.limit_runs is not None and a.limit_runs<1):ap.error('positive run counts required')
    if a.dry_run:
        print(json.dumps({'phase':a.phase,'runs':len(planned),'schedule':planned},indent=2));return
    if a.phase=='evaluation' and not a.calibration:ap.error('held-out calibration artifact required')
    a.out.mkdir(parents=True,exist_ok=True)
    with (a.out/'.campaign.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        observed=preflight(config)
        identity=observed['identity']
        artifact=None
        if a.calibration:
            artifact=json.loads(a.calibration.read_text())
            if artifact['identity']!=identity:raise ValueError('calibration deployment mismatch')
        manifest=dict(phase=a.phase,identity=identity,configuration=config,schedule=planned,
                      seed=a.seed,calibration_sha256=digest(artifact) if artifact else None,
                      driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      evidence_type='physical-host CPU controller experiments',
                      interpretation='scenario fractions are empirical; requests are nested within restart blocks')
        saved=a.out/'manifest.json'
        if saved.exists():
            if not a.resume:raise ValueError('use new output or --resume')
            if json.loads(saved.read_text())!=manifest:raise ValueError('resume changed hardware, sources, runtime, calibration or schedule')
        elif a.resume:raise ValueError('resume requires existing manifest')
        else:saved.write_text(json.dumps(manifest,indent=2)+'\n')
        (a.out/'preflight.json').write_text(json.dumps(observed,indent=2)+'\n')
        (a.out/'identity.json').write_text(json.dumps(identity,indent=2)+'\n')
        (a.out/'initial-layout.json').write_text(json.dumps(config['initial_splits'])+'\n')
        rows=checkpoint(a.out/'runs.jsonl',[r['id'] for r in planned]);completed={r['id'] for r in rows}
        completion(a.out,len(completed),len(planned));new_count=0
        # Compute independent greedy references once, before any timed inference.
        from local_publication import reference
        from huggingface_hub import snapshot_download
        model=snapshot_download(MODEL,revision=REVISION,local_files_only=True)
        for context,tokens in sorted({(r['context'],r['tokens']) for r in planned}):
            dest=a.out/f'reference-{context}-{tokens}.json'
            if not dest.exists():
                rng=random.Random(a.seed+context);prompt=[rng.randrange(1,1000) for _ in range(context)]
                expected=reference(model,{context:prompt},tokens)[str(context)]
                dest.write_text(json.dumps({'input_ids':prompt,'tokens':expected})+'\n')
        stopped=True
        try:
            with (a.out/'runs.jsonl').open('a',buffering=1) as output:
                for entry in planned:
                    if entry['id'] in completed:continue
                    if a.limit_runs is not None and new_count>=a.limit_runs:break
                    destination=a.out/'trials'/entry['id'];destination.mkdir(parents=True,exist_ok=True)
                    attempt=destination/f'attempt-{len(list(destination.glob("attempt-*"))):03d}'
                    env=dict(os.environ,PLACEMENT_OBJECTIVE='auto',MODEL_REVISION=REVISION,TORCH_THREADS='1',
                             KEINFER_STATE=config['state_directory'],EVALUATION_HOLD='1',APP_LINK_MODE='residual',LINK_SOURCE='ebpf',
                             LIVE_REPLAY_CONTEXT='0',REMAINING_WORK_AWARE='0',CALIBRATION_ONLINE='0',
                             CALIBRATED_POINT_ONLY='0',CALIBRATED_NO_CALIBRATION='0',CALIBRATED_PROFILE_CONTEXT='0',
                             INITIAL_LAYOUT=str((a.out/'initial-layout.json').resolve()),
                             CALIBRATION_IDENTITY=str((a.out/'identity.json').resolve()))
                    env.update(config.get('runtime_env',{}));env.update(ARMS[entry['arm']])
                    if a.calibration:env['CALIBRATION_FILE']=str(a.calibration.resolve())
                    command=[sys.executable,str(ROOT/'bench/vmrun.py'),'--workers',str(len(config['workers'])),
                             '--hosts',','.join(h['ssh'] for h in config['workers']),'--target',config['workers'][-1]['ssh'],
                             '--remote-repo',config['remote_repo'],'--coordinator-only','--restart-workers',
                             '--policies',env['POLICY'],'--objective','auto','--link-source',env['LINK_SOURCE'],
                             '--scenarios',entry['scenario'],'--repeats','1','--repeat-offset',str(entry['repetition']),
                             '--prompt-len',str(entry['context']),'--context-len',str(entry['context']),
                             '--new-tokens',str(entry['tokens']),'--concurrency',str(entry['concurrency']),
                             '--demand-mode',entry['demand'],'--history-warmup-s','65',
                             '--input-reference',str((a.out/f'reference-{entry["context"]}-{entry["tokens"]}.json').resolve()),
                             '--out',str(attempt)]
                    with (destination/f'{attempt.name}.log').open('w') as log:
                        result=subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT)
                    if result.returncode:
                        raise RuntimeError(f"trial failed: {entry['id']}; raw attempt retained, campaign stopped")
                    metas=list(attempt.glob('*/meta.json'))
                    if len(metas)!=1:raise ValueError('expected one completed vmrun trial')
                    meta=json.loads(metas[0].read_text())
                    row=dict(entry,trial=str(metas[0].parent.relative_to(a.out)),
                             whole_run_tps=meta['whole_run_tps_including_drain'],observed_at=time.time())
                    output.write(json.dumps(row)+'\n');output.flush();os.fsync(output.fileno())
                    completed.add(entry['id']);new_count+=1;completion(a.out,len(completed),len(planned))
                    print(f"{len(completed)}/{len(planned)} {entry['arm']} {entry['scenario']}",flush=True)
            stopped=len(completed)!=len(planned)
        finally:completion(a.out,len(completed),len(planned),stopped=stopped)


if __name__=='__main__':main()
