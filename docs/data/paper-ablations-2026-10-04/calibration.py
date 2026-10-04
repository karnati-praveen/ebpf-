"""Exploratory calibration of instrumentation overhead; no real-model result."""
import argparse
import concurrent.futures as cf
import json
import os
from pathlib import Path
import random
import statistics
import subprocess
import sys
import time
from queue_ablation import ROOT, free_port, grpc, pb, rpc


def original_worker(port, service):
    os.environ['SIM_PER_LAYER_MS']=str(service)
    os.environ['NODE_AGENT_ADDR']=''
    from server import WorkerServicer
    server=grpc.server(cf.ThreadPoolExecutor(max_workers=16))
    rpc.add_WorkerServicer_to_server(WorkerServicer(),server)
    assert server.add_insecure_port(f'127.0.0.1:{port}')
    server.start();server.wait_for_termination()


def window(stub,q,duration):
    began=time.monotonic();deadline=began+duration
    def client(index):
        rows=[];step=0
        while time.monotonic()<deadline:
            before=time.monotonic_ns()
            try:
                reply,call=stub.Forward.with_call(pb.ForwardRequest(input_ids=[1],step=1,generation=1,request_id=index*100000000+step+1),timeout=10)
                elapsed=(time.monotonic_ns()-before)/1e6
                if reply.error:raise RuntimeError(reply.error)
                rows.append(dict(ok=True,rpc_ms=elapsed,compute_ms=reply.compute_ms,residual_ms=elapsed-reply.compute_ms))
            except Exception as exc:rows.append(dict(ok=False,error=str(exc)))
            step+=1
        return rows
    records=[]
    with cf.ThreadPoolExecutor(max_workers=q) as pool:
        for future in [pool.submit(client,i) for i in range(q)]:records.extend(future.result())
    elapsed=time.monotonic()-began;good=[r for r in records if r['ok']]
    result=dict(observation_s=elapsed,requests=len(records),failures=len(records)-len(good),completed_rpcs_per_s=len(good)/elapsed)
    for field in ['rpc_ms','compute_ms','residual_ms']:
        result['mean_'+field]=statistics.mean(r[field] for r in good)
    return records,result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--worker',action='store_true');p.add_argument('--port',type=int);p.add_argument('--service',type=float);p.add_argument('--out',type=Path);p.add_argument('--window',type=float,default=8);args=p.parse_args()
    if args.worker:original_worker(args.port,args.service);return
    if args.out is None or args.out.exists() or args.window<=0:p.error('fresh --out and positive window required')
    out=args.out.resolve();out.mkdir(parents=True)
    schedule=[];rng=random.Random(20261005)
    for repeat in [1,2,3]:
        cases=[dict(service_ms=s,concurrency=q,instrumented=i,repeat=repeat) for s in [5,50] for q in [1,4] for i in [False,True]]
        rng.shuffle(cases);schedule.extend(cases)
    meta=dict(scope='Short instrumentation calibration, original versus wrapped worker; simulated loopback compute',window_s=args.window,schedule=schedule,started_utc=time.strftime('%Y-%m-%d %H:%M:%S',time.gmtime()))
    (out/'metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
    processes=[];channels=[];rows=[]
    try:
        stubs={}
        for service in [5,50]:
            for instrumented in [False,True]:
                port=free_port();log=(out/f'worker-{service}-{instrumented}.log').open('w')
                script=Path(__file__).with_name('queue_ablation.py') if instrumented else Path(__file__)
                flag='--service-ms' if instrumented else '--service'
                process=subprocess.Popen([sys.executable,str(script.resolve()),'--worker','--port',str(port),flag,str(service)],stdout=log,stderr=log)
                processes.append((process,log));ch=grpc.insecure_channel(f'127.0.0.1:{port}');channels.append(ch)
                grpc.channel_ready_future(ch).result(timeout=15);stub=rpc.WorkerStub(ch)
                reply=stub.AssignLayers(pb.AssignLayersRequest(start_layer=0,end_layer=1,total_layers=1,backend='sim',generation=1),timeout=10)
                assert reply.ok,reply.error;stubs[(service,instrumented)]=stub
        for case in schedule:
            stub=stubs[(case['service_ms'],case['instrumented'])]
            for _ in range(3):stub.Forward(pb.ForwardRequest(input_ids=[1],step=1,generation=1),timeout=10)
            records,result=window(stub,case['concurrency'],args.window);result.update(case);rows.append(result)
            (out/'windows.json').write_text(json.dumps(rows,indent=2)+'\n')
            with (out/'requests.jsonl').open('a') as f:
                for record in records:f.write(json.dumps(dict(record,**case))+'\n')
            print(json.dumps(result),flush=True)
        meta['completed_utc']=time.strftime('%Y-%m-%d %H:%M:%S',time.gmtime());(out/'metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
    finally:
        for channel in channels:channel.close()
        for process,log in processes:process.terminate()
        for process,log in processes:
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait()
            log.close()


if __name__=='__main__':main()
