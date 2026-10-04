"""Runtime probe only: synthetic sleeping compute, real existing worker/router RPCs.
This is neither a real-model benchmark nor a physical multi-machine experiment.
"""
import argparse
import threading
import concurrent.futures as cf
import csv
import json
import os
from pathlib import Path
import socket
import statistics
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
OUT = None
sys.path.insert(0, str(ROOT / 'worker/gen'))
import grpc
import pipeline_pb2 as pb
import pipeline_pb2_grpc as rpc


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def spawn(module, extra, processes):
    env = dict(os.environ, **extra, PYTHONUNBUFFERED='1')
    log = open(OUT / f'{module}-{extra.get("PORT", extra.get("HTTP_PORT"))}.log', 'w')
    process = subprocess.Popen([sys.executable, str(ROOT / 'worker' / f'{module}.py')], env=env, stdout=log, stderr=log)
    processes.append((process, log))
    return process


def post(url):
    req = urllib.request.Request(url + '/generate', data=b'{"prompt_len":16,"max_new_tokens":16}', headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=45) as response:
        return json.load(response)


def percentile(values, fraction):
    return sorted(values)[min(len(values)-1, int((len(values)-1)*fraction))] if values else None


def run_case(urls, concurrency, window=30, policy="cyclic"):
    pending = [0] * len(urls)
    waiting = []
    routing_lock = threading.Condition()
    records = []
    start = time.monotonic()
    deadline = start + window
    def client(index):
        local = []
        j = 0
        while time.monotonic() < deadline:
            admitted = time.monotonic()
            with routing_lock:
                if policy == 'available':
                    while all(pending):
                        routing_lock.wait()
                if policy == 'available-fifo':
                    ticket = object()
                    waiting.append(ticket)
                    while waiting[0] is not ticket or all(pending):
                        routing_lock.wait()
                    waiting.pop(0)
                target = min(range(len(urls)), key=lambda i: pending[i]) if policy == 'least-pending' else (index+j) % len(urls)
                if policy in ('available', 'available-fifo'):
                    target = next(i for i in range(len(urls)) if pending[i] == 0)
                pending[target] += 1
                routing_lock.notify_all()
            routed = time.monotonic()
            try:
                response = post(urls[target])
                finished = time.monotonic()
                local.append({'admitted_s': admitted-start, 'completed_s': finished-start,
                              'routing_wait_ms': (routed-admitted)*1000,
                              'client_completion_ms': (finished-admitted)*1000,
                              'ok':True, **response})
            except Exception as exc:
                local.append({'admitted_s': admitted-start, 'completed_s': time.monotonic()-start, 'ok':False, 'error':str(exc)})
            finally:
                with routing_lock:
                    pending[target] -= 1
                    routing_lock.notify_all()
            j += 1
        return local
    with cf.ThreadPoolExecutor(max_workers=concurrency) as pool:
        for future in [pool.submit(client, i) for i in range(concurrency)]:
            records.extend(future.result())
    elapsed = time.monotonic()-start
    success = [r for r in records if r['ok']]
    closed = [r for r in success if r['completed_s'] <= window]
    return records, {
        'admission_window_s':window, 'observation_s':elapsed,
        'requests':len(records), 'successes':len(success), 'failures':len(records)-len(success),
        'completed_tokens_per_s_full_observation':sum(len(r['tokens']) for r in success)/elapsed,
        'completed_tokens_per_s_admission_window':sum(len(r['tokens']) for r in closed)/window,
        'median_ttft_ms':statistics.median(r['ttft_ms'] for r in success) if success else None,
        'p95_ttft_ms':percentile([r['ttft_ms'] for r in success], .95),
        'median_completion_ms':statistics.median(r['duration_ms'] for r in success) if success else None,
        'median_client_completion_ms':statistics.median(r['client_completion_ms'] for r in success) if success else None,
        'median_routing_wait_ms':statistics.median(r['routing_wait_ms'] for r in success) if success else None,
    }


def main():
    global OUT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True, help='New output directory; existing directories are refused')
    parser.add_argument('--window',type=float,default=30)
    parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--modes',default='pipeline,replicas')
    parser.add_argument('--workers',default='1,2,3')
    parser.add_argument('--concurrency',default='1,2,4')
    parser.add_argument('--replica-policy',choices=['cyclic','least-pending','available','available-fifo'],default='cyclic')
    args=parser.parse_args()
    if args.window <= 0 or args.repeats <= 0:
        parser.error('window and repeats must be positive')
    counts=[int(x) for x in args.workers.split(',')]
    concurrency=[int(x) for x in args.concurrency.split(',')]
    modes=args.modes.split(',')
    if not counts or any(n<1 or n>3 for n in counts) or any(q<1 for q in concurrency) or any(m not in ('pipeline','replicas') for m in modes):
        parser.error('workers must be 1..3, concurrency positive, and modes pipeline or replicas')
    OUT=args.out.resolve()
    if OUT.exists():
        parser.error('output directory already exists; choose a fresh path')
    OUT.mkdir(parents=True)
    metadata={**vars(args),'out':str(OUT),'scope':'synthetic loopback worker/router probe; not real-model inference','python':sys.version,'total_layers':28,'sim_per_layer_ms':5,'sim_hidden_dim':1024,'prompt_len':16,'max_new_tokens':16}
    (OUT/'runtime-probe-meta.json').write_text(json.dumps(metadata,indent=2)+'\n')
    processes=[]
    channels=[]
    rows=[]
    all_requests=[]
    try:
        # Reuse isolated scratch workers. Controller and node-agent are not involved.
        workers=[]
        for i in range(3):
            p=port()
            spawn('server', {'PORT':str(p), 'SIM_PER_LAYER_MS':'5', 'SIM_HIDDEN_DIM':'1024','NODE_AGENT_ADDR':''}, processes)
            ch=grpc.insecure_channel(f'127.0.0.1:{p}')
            channels.append(ch)
            grpc.channel_ready_future(ch).result(timeout=15)
            workers.append((f'127.0.0.1:{p}', rpc.WorkerStub(ch)))
        routers=[]
        urls=[]
        for i in range(3):
            gp, hp=port(), port()
            spawn('router', {'GRPC_PORT':str(gp), 'HTTP_PORT':str(hp), 'KV_CACHE':'1','CONTROLLER_ADDR':''}, processes)
            ch=grpc.insecure_channel(f'127.0.0.1:{gp}')
            channels.append(ch)
            grpc.channel_ready_future(ch).result(timeout=15)
            routers.append(rpc.RouterStub(ch))
            urls.append(f'http://127.0.0.1:{hp}')
        generation=0
        # Counterbalance mode and resource count by repeat; rotate concurrency order.
        for repeat in range(1,args.repeats+1):
            cases=[(mode,n) for n in counts for mode in modes]
            if repeat==2:
                cases.reverse()
            if repeat==3:
                cases=cases[2:]+cases[:2]
            for mode,n in cases:
                generation+=1
                for i in range(n):
                    lo,hi=(28*i//n,28*(i+1)//n) if mode=='pipeline' else (0,28)
                    result=workers[i][1].AssignLayers(pb.AssignLayersRequest(start_layer=lo,end_layer=hi,total_layers=28,backend='sim',generation=generation),timeout=10)
                    assert result.ok,result.error
                if mode=='pipeline':
                    stages=[pb.StageRef(name=f'w{i}',addr=workers[i][0],start_layer=28*i//n,end_layer=28*(i+1)//n) for i in range(n)]
                    routers[0].SetPipeline(pb.SetPipelineRequest(stages=stages,generation=generation),timeout=10)
                    active_urls=urls[:1]
                else:
                    for i in range(n):
                        stages=[pb.StageRef(name=f'w{i}',addr=workers[i][0],start_layer=0,end_layer=28)]
                        routers[i].SetPipeline(pb.SetPipelineRequest(stages=stages,generation=generation),timeout=10)
                    active_urls=urls[:n]
                for url in active_urls:
                    post(url)
                conc=list(concurrency)
                rotation=(repeat-1)%len(conc)
                conc=conc[rotation:]+conc[:rotation]
                for q in conc:
                    records,result=run_case(active_urls,q,args.window,args.replica_policy if mode == 'replicas' else 'cyclic')
                    result.update(mode=mode,workers=n,concurrency=q,repeat=repeat,replica_policy=args.replica_policy)
                    rows.append(result)
                    for record in records:
                        all_requests.append(dict(record, mode=mode,workers=n,concurrency=q,repeat=repeat))
                    # Write after each window so an interrupted session retains evidence.
                    (OUT/'runtime-probe-summary.json').write_text(json.dumps(rows,indent=2))
                    with open(OUT/'runtime-probe-requests.jsonl','a') as f:
                        for record in records:
                            f.write(json.dumps(dict(record,mode=mode,workers=n,concurrency=q,repeat=repeat))+'\n')
                    print(json.dumps(result),flush=True)
        with open(OUT/'runtime-probe-summary.csv','w') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    finally:
        for channel in channels:
            channel.close()
        for process, log in reversed(processes):
            process.terminate()
        for process, log in reversed(processes):
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            log.close()

if __name__=='__main__':
    main()
