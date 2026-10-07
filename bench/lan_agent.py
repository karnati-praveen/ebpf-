#!/usr/bin/env python3
"""Rootless, token-protected fixed-layout worker agent for a trusted two-laptop LAN.

Only starts/stops its own Qwen worker and router; no shell execution API.
"""
import argparse
import hmac
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

ROOT=Path(__file__).resolve().parents[1]
MODEL='Qwen/Qwen3-0.6B';REVISION='c1899de289a04d12100db370d81485cdf75e47ca'


class Agent:
    def __init__(self,args):
        self.args=args;self.children={};self.lock=threading.RLock();self.model=None
        self.token=os.environ.get('SHARDWISE_LAB_TOKEN')
        if not self.token or len(self.token)<16:raise ValueError('set SHARDWISE_LAB_TOKEN to a shared random value of at least 16 characters')
        self.args.state.mkdir(parents=True,exist_ok=True)
        self.allowed=sorted(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else list(range(os.cpu_count() or 1))
        self.compute=self.allowed[:2]
        self.sequence=0

    def status(self):
        cpu=platform.processor()
        if Path('/proc/cpuinfo').exists():
            cpu=next((x.split(':',1)[1].strip() for x in Path('/proc/cpuinfo').read_text().splitlines() if x.startswith('model name')),cpu)
        return {'platform':platform.platform(),'cpu':cpu,'logical_cpus':os.cpu_count(),
            'allowed_cpus':self.allowed,'compute_cpus':self.compute,
            'affinity_control':hasattr(os,'sched_setaffinity'),'model':MODEL,'model_revision':REVISION,
            'packages':{p:importlib.metadata.version(p) for p in ('torch','transformers','grpcio','protobuf','numpy')},
            'serving_source_sha256':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in (
                'worker/server.py','worker/router.py','worker/workload.py','worker/backends/qwen3.py','worker/gen/pipeline_pb2.py')},
            'processes':{k:{'pid':p.pid,'exit_code':p.poll()} for k,p in self.children.items()},
            'worker_addr':f'{self.args.advertise}:{self.args.base_port}',
            'router_url':f'http://{self.args.advertise}:{self.args.base_port+20}',
            'generation':self.sequence,'scope':'one physical laptop; own processes only; fixed layouts'}

    def stop_worker(self):
        self.kill('worker')
        return {'action':'stopped owned worker','observed_at':time.time()}

    def kill(self,name):
        p=self.children.pop(name,None)
        if p and p.poll() is None:
            p.terminate()
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:p.kill();p.wait()

    def stop(self):
        for k in list(self.children):self.kill(k)

    def spawn(self,name,script,env,cpus):
        with (self.args.state/f'{self.sequence:03d}-{name}.log').open('w') as log:
            p=subprocess.Popen([sys.executable,str(ROOT/'worker'/script)],cwd=ROOT/'worker',
                env={**os.environ,'KV_CACHE':'1','WORKER_DEVICE':'cpu','KV_MAX_SESSIONS':'32',
                     'GRPC_HOST':self.args.host,'HTTP_HOST':self.args.host,'HF_HUB_OFFLINE':'1',
                     'OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','PYTHONUNBUFFERED':'1',**env},
                stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
        self.children[name]=p
        if hasattr(os,'sched_setaffinity'):os.sched_setaffinity(p.pid,cpus)

    def start(self,body):
        lo,hi=map(int,body['layers']);threads=int(body.get('threads',1))
        if not 0<=lo<hi<=28 or threads not in (1,2) or len(self.compute)<threads:raise ValueError('invalid layout or CPU budget')
        chain=body.get('chain')
        if not isinstance(chain,list) or not chain or len(chain)>2:raise ValueError('chain must contain one or two stages')
        for row in chain:
            host,port=row['addr'].rsplit(':',1)
            if not host or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-' for c in host) or not 1<=int(port)<=65535:raise ValueError('invalid endpoint')
            a,b=map(int,row['layers'])
            if not 0<=a<b<=28:raise ValueError('invalid chain layers')
        with self.lock:
            self.stop();self.sequence+=1
            if self.model is None:
                from huggingface_hub import snapshot_download
                self.model=snapshot_download(MODEL,revision=REVISION,allow_patterns=['*.json','*.safetensors','*.txt','*.model','*.jinja'])
            self.spawn('worker','server.py',{'PORT':str(self.args.base_port),'TORCH_THREADS':str(threads),
                'INITIAL_ASSIGNMENT':f'{lo}:{hi}:28:qwen3:{self.model}'},self.compute[:threads])
            if body.get('router',True):
                self.spawn('router','router.py',{'GRPC_PORT':str(self.args.base_port+10),
                    'HTTP_PORT':str(self.args.base_port+20),'STATIC_PIPELINE':','.join(
                    f"w{i}={r['addr']}={r['layers'][0]}={r['layers'][1]}" for i,r in enumerate(chain))},
                    self.allowed[2:] or self.allowed)
            deadline=time.monotonic()+600
            while True:
                if any(p.poll() is not None for p in self.children.values()):raise RuntimeError('owned process exited; inspect agent state logs')
                try:
                    with socket.create_connection(('127.0.0.1' if self.args.host=='0.0.0.0' else self.args.host,self.args.base_port),timeout=.2):break
                except OSError:
                    if time.monotonic()>deadline:raise TimeoutError('worker startup timed out')
                    time.sleep(.2)
            return self.status()

    def promote(self):
        # Manual fault orchestration, not automatic heartbeat recovery.
        sys.path.insert(0,str(ROOT/'worker/gen'))
        import grpc,pipeline_pb2 as pb,pipeline_pb2_grpc as rpc
        address=f"127.0.0.1:{self.args.base_port}" if self.args.host=='0.0.0.0' else f'{self.args.host}:{self.args.base_port}'
        worker=rpc.WorkerStub(grpc.insecure_channel(address))
        reply=worker.AssignLayers(pb.AssignLayersRequest(start_layer=0,end_layer=28,total_layers=28,
            model=self.model,backend='qwen3',generation=1),timeout=600)
        if not reply.ok:raise RuntimeError(reply.error)
        router=rpc.RouterStub(grpc.insecure_channel(address.rsplit(':',1)[0]+f':{self.args.base_port+10}'))
        layout=pb.SetPipelineRequest(generation=1)
        layout.stages.add(name='w0',addr=address,start_layer=0,end_layer=28)
        result=router.SetPipeline(layout,timeout=30)
        if not result.ok:raise RuntimeError(result.error)
        return {'action':'manual promotion and layout publication','observed_at':time.time(),'generation':1}


def handler(agent):
    class Handler(BaseHTTPRequestHandler):
        def send(self,code,value):
            payload=json.dumps(value).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
        def authorized(self):return hmac.compare_digest(self.headers.get('X-Lab-Token',''),agent.token)
        def do_GET(self):
            if not self.authorized():return self.send(403,{'error':'invalid lab token'})
            if self.path=='/status':return self.send(200,agent.status())
            self.send(404,{'error':'not found'})
        def do_POST(self):
            if not self.authorized():return self.send(403,{'error':'invalid lab token'})
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<=size<=65536:raise ValueError('invalid body size')
                body=json.loads(self.rfile.read(size) or b'{}')
                if self.path=='/start':value=agent.start(body)
                elif self.path=='/stop':agent.stop();value={'stopped':True}
                elif self.path=='/stop-worker':value=agent.stop_worker()
                elif self.path=='/promote-full':value=agent.promote()
                else:return self.send(404,{'error':'not found'})
                self.send(200,value)
            except Exception as e:self.send(400,{'error':str(e)})
        def log_message(self,*args):pass
    return Handler


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--host',default='0.0.0.0');ap.add_argument('--advertise',required=True,help='LAN IP reachable from the other laptop')
    ap.add_argument('--port',type=int,default=56080);ap.add_argument('--base-port',type=int,default=56100)
    ap.add_argument('--state',type=Path,default=ROOT/'.lan-test-state')
    args=ap.parse_args();agent=Agent(args)
    server=ThreadingHTTPServer((args.host,args.port),handler(agent))
    print(f'Lab agent http://{args.advertise}:{args.port}; worker {args.base_port}, router {args.base_port+20}. Ctrl+C cleans up owned processes.',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:agent.stop();server.server_close()


if __name__=='__main__':main()
