#!/usr/bin/env python3
"""Shardwise development-only mock: all inference and hardware values are simulated. Never packaged."""
import argparse, json, secrets, threading, time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

class Mock:
    def __init__(self, gpu=False, single=False, mode='solo'):
        self.token=secrets.token_urlsafe(32); self.started=time.monotonic(); self.lock=threading.RLock(); self.busy=False
        self.gpu=gpu; self.gpu_capable=gpu; self.requested="auto"; self.single=single or mode=="join"; self.mode=mode; self.recover_until=0; self.generation=1; self.events=[]; self.requests=0; self.tokens=0; self.load=False; self.stopped=False
        self.workers=[dict(name='w1',node='this-laptop',local=True,status='up',layers=[0,28] if single else [0,14],speed=1.0)]
        if mode=='join':self.workers=[dict(name='w2',node='this-laptop',local=True,status='up',layers=[14,28],speed=0.95)]
        elif not single:self.workers.append(dict(name='w2',node='friend' if mode=='host' else 'this-laptop',local=mode!='host',status='up',layers=[14,28],speed=0.95))
    def event(self,kind,text):self.events.append(dict(t=datetime.now(timezone.utc).isoformat(),kind=kind,text=text))
    def status(self):
        elapsed=time.monotonic()-self.started
        state='stopped' if self.stopped else 'recovering' if time.monotonic()<self.recover_until else 'downloading' if elapsed<2 else 'calibrating' if elapsed<4 else 'loading' if elapsed<6 else 'ready'
        if self.recover_until and state=='ready':
            self.recover_until=0; live=[w for w in self.workers if w['status']=='up']
            for w in self.workers:w['layers']=([0,28] if len(live)==1 else [0,14] if w['name']=='w1' else [14,28]) if w['status']=='up' else None
            self.generation+=1; self.event('healed' if len(live)==1 else 'restored','Layer assignments recovered.')
        return dict(app_state=state,message='Shardwise development mock — simulated inference and hardware',progress=min(elapsed/6,1) if state in ('downloading','calibrating','loading') else None,mode=self.mode,device=dict(requested=self.requested,selected='cuda' if self.gpu else 'cpu',reason='Mock device for UI testing',gpu_name='RTX 4060' if self.gpu else None),workers=self.workers,generation=self.generation,policy='hysteresis',events=self.events,metrics=dict(requests=self.requests,tokens=self.tokens,avg_ttft_ms=420,avg_duration_ms=2000,repartition_replays=0),recovery_demo=dict(available=not self.single,reason='Use the host dashboard to control Pair recovery.' if self.mode=='join' else 'Only one worker fits in available memory.' if self.single else None),faults_available=['slow','net'] if self.mode=='host' else [],load_on=self.load)
    def hw(self):return dict(cpu=dict(model='Mock Intel CPU',cores=8,util_pct=37.5),ram=dict(total_mb=16000,used_mb=9100),gpu=dict(name='RTX 4060',util_pct=62,temp_c=58,vram_used_mb=3200,vram_total_mb=8192) if self.gpu else None)

class Handler(BaseHTTPRequestHandler):
    def reply(self,code,value):
        raw=json.dumps(value).encode(); self.send_response(code); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        with self.server.mock.lock:
            if self.path=='/':
                raw=Path(__file__).with_name('app.html').read_text().replace('__SESSION_TOKEN__',self.server.mock.token).encode(); self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers();self.wfile.write(raw)
            elif self.path=='/api/status':self.reply(200,self.server.mock.status())
            elif self.path=='/api/hw':self.reply(200,self.server.mock.hw())
            else:self.reply(404,dict(error='not found'))
    def do_POST(self):
        m=self.server.mock
        if self.headers.get('X-Session-Token')!=m.token:return self.reply(403,dict(error='invalid session token'))
        try:
            length=int(self.headers.get('Content-Length',0))
            if length>65536:raise ValueError('request too large')
            d=json.loads(self.rfile.read(length)); assert isinstance(d,dict)
        except (ValueError,AssertionError):return self.reply(400,dict(error='invalid JSON'))
        if self.path=='/api/chat':
            with m.lock:
                if m.busy:return self.reply(409,dict(error='busy'))
                if m.status()['app_state']!='ready':return self.reply(503,dict(error='not ready'))
                if not isinstance(d.get('messages'),list) or not d['messages']:return self.reply(400,dict(error='messages required'))
                m.busy=True
            try:
                time.sleep(2)
                with m.lock:m.requests+=1;m.tokens+=57
                self.reply(200,dict(text='This is simulated text for UI testing. The real app runs Qwen3 across the assigned workers and recovers when a worker stops.',tokens=57,ttft_ms=420,duration_ms=2000,tokens_per_sec=28.5,device='cuda' if m.gpu else 'cpu',replays=0,transition_ms=0))
            finally:m.busy=False
            return
        with m.lock:
            try:
                if self.path=='/api/worker':
                    w=next((w for w in m.workers if w['name']==d.get('name')),None)
                    if not w or d.get('action') not in ('stop','restore'):raise ValueError('invalid worker/action')
                    if d['action']=='stop' and sum(x['status']=='up' for x in m.workers)<=1:raise ValueError('cannot stop last worker')
                    w['status']='stopped' if d['action']=='stop' else 'up';m.recover_until=time.monotonic()+6;m.event('fault' if d['action']=='stop' else 'restored',f"{w['name']} {d['action']}")
                elif self.path=='/api/fault':
                    if m.mode!='host' or d.get('action') not in ('slow','net','clear'):raise ValueError('fault unavailable')
                    m.event('fault','Mock fault '+d['action'])
                elif self.path=='/api/mode':
                    if d.get('device') not in ('auto','cpu','cuda'):raise ValueError('invalid device')
                    m.requested=d['device'];m.gpu=d['device']=='cuda' or d['device']=='auto' and m.gpu_capable;m.started=time.monotonic()
                elif self.path=='/api/load':
                    if not isinstance(d.get('on'),bool):raise ValueError('on must be boolean')
                    m.load=d['on']
                elif self.path=='/api/exit':m.stopped=True
                else:return self.reply(404,dict(error='not found'))
                self.reply(200,dict(ok=True))
            except ValueError as e:self.reply(400,dict(error=str(e)))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--gpu',action='store_true');p.add_argument('--single-worker',action='store_true');p.add_argument('--mode',choices=['solo','host','join'],default='solo');p.add_argument('--port',type=int,default=8080);a=p.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',a.port),Handler);server.mock=Mock(a.gpu,a.single_worker,a.mode);print(f'MOCK: http://127.0.0.1:{server.server_port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
