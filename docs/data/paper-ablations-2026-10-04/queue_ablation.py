"""Controlled pilot: queue contamination of RPC-minus-compute telemetry.

Uses the existing worker with sleeping simulation compute. Scratch instrumentation
measures lock acquisition and returns it as gRPC trailing metadata. No product
source is changed. This is not a real-model or physical-network benchmark.
"""
import argparse
import concurrent.futures as cf
import csv
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import random
import socket
import statistics
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'worker'))
sys.path.insert(0, str(ROOT / 'worker/gen'))
import grpc
import pipeline_pb2 as pb
import pipeline_pb2_grpc as rpc


def worker(port, service_ms):
    os.environ['SIM_PER_LAYER_MS'] = str(service_ms)
    os.environ['NODE_AGENT_ADDR'] = ''
    from server import WorkerServicer
    local = threading.local()

    class TimedLock:
        def __init__(self):
            self.lock = threading.Lock()
        def __enter__(self):
            before = time.monotonic_ns()
            self.lock.acquire()
            local.queue_ms = (time.monotonic_ns() - before) / 1e6
            return self
        def __exit__(self, *exc):
            self.lock.release()

    class InstrumentedWorker(WorkerServicer):
        def __init__(self):
            super().__init__()
            self.compute_lock = TimedLock()
        def Forward(self, request, context):
            local.queue_ms = 0
            response = super().Forward(request, context)
            context.set_trailing_metadata((('x-probe-lock-wait-ms', str(local.queue_ms)),))
            return response

    server = grpc.server(cf.ThreadPoolExecutor(max_workers=16))
    rpc.add_WorkerServicer_to_server(InstrumentedWorker(), server)
    assert server.add_insecure_port(f'127.0.0.1:{port}')
    server.start()
    server.wait_for_termination()


class FIFOAdmission:
    def __init__(self):
        self.condition = threading.Condition()
        self.waiting = []
        self.active = False
    def __enter__(self):
        ticket = object()
        with self.condition:
            self.waiting.append(ticket)
            while self.active or self.waiting[0] is not ticket:
                self.condition.wait()
            self.waiting.pop(0)
            self.active = True
    def __exit__(self, *exc):
        with self.condition:
            self.active = False
            self.condition.notify_all()


def percentile(values, q):
    values = sorted(values)
    return values[int((len(values)-1)*q)] if values else None


def run_window(stub, mode, concurrency, duration):
    admission = FIFOAdmission()
    start = time.monotonic()
    deadline = start + duration
    def client(index):
        rows = []
        step = 0
        while time.monotonic() < deadline:
            began = time.monotonic_ns()
            if mode == 'admitted':
                admission.__enter__()
            rpc_start = time.monotonic_ns()
            try:
                request = pb.ForwardRequest(request_id=index*100000000+step+1,
                                            step=1, input_ids=[1], generation=1)
                response, call = stub.Forward.with_call(request, timeout=10)
                finished = time.monotonic_ns()
                if response.error:
                    raise RuntimeError(response.error)
                metadata = dict(call.trailing_metadata())
                queue_ms = float(metadata['x-probe-lock-wait-ms'])
                rpc_ms = (finished-rpc_start)/1e6
                residual = rpc_ms-response.compute_ms
                rows.append(dict(ok=True, admitted_s=(began/1e9-start),
                                 completed_s=(finished/1e9-start),
                                 rpc_ms=rpc_ms, compute_ms=response.compute_ms,
                                 server_lock_wait_ms=queue_ms,
                                 residual_ms=residual, clipped_residual_ms=max(0,residual),
                                 queue_corrected_residual_ms=residual-queue_ms,
                                 client_admission_wait_ms=(rpc_start-began)/1e6,
                                 client_completion_ms=(finished-began)/1e6))
            except Exception as exc:
                rows.append(dict(ok=False, error=str(exc)))
            finally:
                if mode == 'admitted':
                    admission.__exit__()
            step += 1
        return rows
    records = []
    with cf.ThreadPoolExecutor(max_workers=concurrency) as pool:
        for future in [pool.submit(client, i) for i in range(concurrency)]:
            records.extend(future.result())
    elapsed = time.monotonic()-start
    success = [r for r in records if r['ok']]
    result = dict(window_s=duration, observation_s=elapsed, requests=len(records),
                  successes=len(success), failures=len(records)-len(success),
                  completed_rpcs_per_s=len(success)/elapsed)
    for field in ['rpc_ms','compute_ms','server_lock_wait_ms','residual_ms',
                  'clipped_residual_ms','queue_corrected_residual_ms',
                  'client_admission_wait_ms','client_completion_ms']:
        values = [r[field] for r in success]
        result['mean_'+field] = statistics.mean(values) if values else None
        result['median_'+field] = statistics.median(values) if values else None
        result['p95_'+field] = percentile(values,.95)
    return records, result


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0))
        return s.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker',action='store_true')
    parser.add_argument('--port',type=int)
    parser.add_argument('--service-ms',type=float)
    parser.add_argument('--out',type=Path)
    parser.add_argument('--window',type=float,default=15)
    parser.add_argument('--repeats',type=int,default=3)
    args = parser.parse_args()
    if args.worker:
        worker(args.port,args.service_ms)
        return
    if args.out is None or args.out.exists() or args.window<=0 or args.repeats<1:
        parser.error('choose a fresh --out directory, positive window and repeats')
    out = args.out.resolve()
    out.mkdir(parents=True)
    services = [5,20,50]
    cases = [(s,q,m) for s in services for q in [1,2,4] for m in ['direct','admitted']]
    schedule = []
    # Exploratory pilot, deterministic random ordering within each repeat block.
    rng = random.Random(20261004)
    for repeat in range(1,args.repeats+1):
        order = list(cases)
        rng.shuffle(order)
        schedule.extend(dict(service_ms=s,concurrency=q,mode=m,repeat=repeat) for s,q,m in order)
    meta = dict(scope='Instrumented synthetic one-layer worker over loopback; no router/controller/eBPF/real model',
                python=sys.version,platform=platform.platform(),cpu_count=os.cpu_count(),
                packages={n:importlib.metadata.version(n) for n in ['grpcio','protobuf','numpy']},
                window_s=args.window,repeats=args.repeats,schedule=schedule,
                git_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ['worker/server.py','worker/backends/sim.py','worker/router.py']},
                instrumentation='Timed compute_lock acquisition, returned in gRPC trailing metadata; existing Forward code and compute timer preserved',
                admission='FIFO cap of one RPC in flight per selected worker; wait moves to client, not removed from end-to-end timing',
                started_utc=time.strftime('%Y-%m-%d %H:%M:%S',time.gmtime()))
    (out/'metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
    processes=[]
    channels=[]
    rows=[]
    try:
        stubs={}
        for service_ms in services:
            port=free_port()
            log=(out/f'worker-{service_ms}ms.log').open('w')
            process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--worker','--port',str(port),'--service-ms',str(service_ms)],stdout=log,stderr=log)
            processes.append((process,log))
            channel=grpc.insecure_channel(f'127.0.0.1:{port}')
            channels.append(channel)
            grpc.channel_ready_future(channel).result(timeout=15)
            stub=rpc.WorkerStub(channel)
            result=stub.AssignLayers(pb.AssignLayersRequest(start_layer=0,end_layer=1,total_layers=1,backend='sim',generation=1),timeout=10)
            assert result.ok,result.error
            stubs[service_ms]=stub
        for case in schedule:
            stub=stubs[case['service_ms']]
            for _ in range(3):
                reply=stub.Forward(pb.ForwardRequest(input_ids=[1],generation=1,step=1),timeout=10)
                assert not reply.error,reply.error
            records,result=run_window(stub,case['mode'],case['concurrency'],args.window)
            result.update(case)
            rows.append(result)
            (out/'windows.json').write_text(json.dumps(rows,indent=2)+'\n')
            with (out/'requests.jsonl').open('a') as f:
                for record in records:
                    f.write(json.dumps(dict(record,**case))+'\n')
            print(json.dumps(result),flush=True)
        with (out/'windows.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        meta['completed_utc']=time.strftime('%Y-%m-%d %H:%M:%S',time.gmtime())
        meta['completed_windows']=len(rows)
        (out/'metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
    finally:
        for channel in channels:channel.close()
        for process,log in processes:process.terminate()
        for process,log in processes:
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait()
            log.close()


if __name__=='__main__':main()
