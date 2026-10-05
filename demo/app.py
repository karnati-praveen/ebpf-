#!/usr/bin/env python3
"""Rootless real-inference demo runtime. All children belong to this instance."""
import argparse
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from hwdetect import hardware, select
from helper import Helper, DelayedRelay

ROOT = Path(__file__).resolve().parents[1]
HOME = Path(os.environ.get('KEINFER_DEMO_HOME', '~/.local/share/keinfer-demo')).expanduser()
MODEL = 'Qwen/Qwen3-0.6B'
MODEL_REVISION = 'c1899de289a04d12100db370d81485cdf75e47ca'


def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def request(url, body=None, token=None, timeout=5):
    headers = {'Content-Type': 'application/json'}
    if token: headers['X-Session-Token'] = token
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


class Runtime:
    def __init__(self, args):
        self.args = args
        for d in ('logs', 'profiles', 'state', 'hf'): (HOME / d).mkdir(parents=True, exist_ok=True)
        self.lock = open(HOME / 'state/lock', 'a')
        try: fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError('Demo already running; use keinfer-demo status or stop')
        self.token = secrets.token_urlsafe(32)
        self.pair_token = secrets.token_urlsafe(32)
        self.processes = {}
        self.workers = {}
        self.events = []
        self.chat_lock = threading.Lock()
        self.lifecycle = threading.RLock()
        self.closed = threading.Event()
        self.state, self.message, self.progress = 'loading', 'Starting runtime', None
        self.device = {'requested': args.device, 'selected': 'cpu', 'reason': 'Detecting hardware', 'gpu_name': None}
        self.ports = {k: port() for k in ('app', 'controller', 'controller_http', 'router', 'router_http', 'helper')}
        self.generation = -1
        self.load_on = False
        self.remote = None
        self.helper = None
        self.bin = Path(os.environ.get('KEINFER_BIN', '/opt/keinfer-demo/bin'))
        if not self.bin.exists(): self.bin = ROOT / 'bin'
        self.env = dict(os.environ, HF_HOME=str(HOME/'hf'), KV_CACHE='1', MODEL=MODEL, PYTHONUNBUFFERED='1')
        self.env['TORCH_THREADS'] = str(max(1, (os.cpu_count() or 2)//2))
        self.server = ThreadingHTTPServer(('127.0.0.1', self.ports['app']), handler(self))
        info = {'pid': os.getpid(), 'port': self.ports['app'], 'token': self.token}
        path = HOME/'state/app.json'
        path.write_text(json.dumps(info)); path.chmod(0o600)

    def event(self, kind, text):
        self.events.append({'t': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'kind': kind, 'text': text})
        self.events = self.events[-100:]

    def spawn(self, name, command, env=None):
        log = open(HOME/'logs'/f'{name}.log', 'a')
        try:
            proc = subprocess.Popen(command, cwd=ROOT/'worker', env=dict(self.env, **(env or {})), stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        finally: log.close()
        self.processes[name] = proc
        return proc

    def kill(self, name):
        proc = self.processes.pop(name, None)
        if proc and proc.poll() is None:
            os.killpg(proc.pid, signal.SIGCONT)
            os.killpg(proc.pid, signal.SIGTERM)
            try: proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL); proc.wait()

    def cleanup_pipeline(self):
        if self.helper: self.helper.close(); self.helper = None
        if getattr(self, 'relay', None): self.relay.close(); self.relay = None
        for name in list(self.processes): self.kill(name)

    def prepare(self):
        from huggingface_hub import snapshot_download
        from transformers import AutoTokenizer
        self.state, self.message = 'downloading', 'Downloading or checking cached Qwen3 model'
        snapshot_download(MODEL, revision=MODEL_REVISION, cache_dir=str(HOME/'hf'/'hub'), allow_patterns=['*.json', '*.safetensors', '*.txt', '*.jinja', '*.model'])
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=MODEL_REVISION, cache_dir=str(HOME/'hf'/'hub'), local_files_only=True)
        self.device, count = select(self.args.device)
        self.env['WORKER_DEVICE'] = self.device['selected']
        import torch, transformers
        identity = json.dumps([MODEL, MODEL_REVISION, self.device['selected'], self.device['gpu_name'], hardware()['cpu']['model'], self.env['TORCH_THREADS'], torch.__version__, transformers.__version__])
        profile = HOME/'profiles'/(hashlib.sha256(identity.encode()).hexdigest()[:20]+'.json')
        if not profile.exists():
            self.state, self.message = 'calibrating', 'Measuring this laptop’s execution speed'
            tmp = profile.with_suffix('.pending')
            tmp.unlink(missing_ok=True)
            proc = self.spawn('calibration', [sys.executable, str(ROOT/'bench/profile_qwen3.py'), '--device', self.device['selected'], '--contexts', '128,512', '--warmup', '1', '--samples', '3', '--out', str(tmp)])
            while proc.poll() is None:
                if self.closed.wait(.2): self.kill('calibration'); return 0
            if proc.returncode != 0: raise RuntimeError('Calibration failed; see logs/calibration.log')
            self.processes.pop('calibration', None)
            tmp.replace(profile)
        self.profile = json.loads(profile.read_text())
        return count

    def worker(self, name, address='127.0.0.1', controller='127.0.0.1', controller_port=None):
        entry = self.workers.get(name)
        if not entry:
            entry = {'name': name, 'node': socket.gethostname(), 'local': True, 'status': 'up', 'layers': None, 'speed': None, 'port': port(), 'agent': port()}
            self.workers[name] = entry
        entry['status'] = 'up'
        profile = ','.join(f"{r['context_len']}:{r['ms']}" for r in self.reference['per_layer_by_ctx'])
        self.spawn(name, [sys.executable, str(ROOT/'worker/server.py')], {'PORT': str(entry['port']), 'WORKER_NAME': name, 'NODE_AGENT_ADDR': f"127.0.0.1:{entry['agent']}", 'PER_LAYER_PROFILE': profile, 'HF_HUB_OFFLINE': '1'})
        if self.args.command == 'join' and not getattr(self, 'relay', None):
            self.relay = DelayedRelay(entry['port'])
        self.spawn(name+'-agent', [str(self.bin/'nodeagent')], {'NODE_NAME': name, 'HTTP_ADDR': f"127.0.0.1:{entry['agent']}", 'CONTROLLER_ADDR': f"{controller}:{controller_port or self.ports['controller']}", 'WORKER_ADDR': f"{address}:{self.relay.port if self.args.command == 'join' else entry['port']}", 'GPU_MODE': 'measured', 'EBPF': 'off'})

    def initialize(self):
        try:
            with self.lifecycle:
                count = self.prepare()
                if self.closed.is_set(): return
                self.state, self.message = 'loading', 'Loading workers and pipeline'
                if self.args.command == 'join':
                    data = request(f'http://{self.args.host}:{self.args.pair_port}/enroll', {'helper_port': self.ports['helper']}, self.args.token)
                    self.join_ip, self.join_controller = data['join_ip'], data['controller_port']
                    self.reference = data['profile']
                    self.remote = {'ip': self.args.host, 'port': self.args.pair_port, 'token': self.args.token}
                    self.helper = Helper(self, self.args.host, self.args.token)
                    self.pair_server = ThreadingHTTPServer(('0.0.0.0', self.ports['helper']), handler(self, pair=True))
                    threading.Thread(target=self.pair_server.serve_forever, daemon=True).start()
                    self.worker('w2', data['join_ip'], self.args.host, data['controller_port'])
                    self.state, self.message = 'loading', 'Friend worker connected; chat is on the host laptop'
                    self.monitor_started = True
                    threading.Thread(target=self.monitor,daemon=True).start()
                    return
                self.reference = self.profile
                config = HOME/'state/controller.json'
                config.write_text(json.dumps({'model': MODEL, 'backend': 'qwen3', 'totalLayers': 28, 'workers': 2 if self.args.command == 'host' else count, 'routerAddr': f"127.0.0.1:{self.ports['router']}", 'contextLen': 512, 'perLayerMs': self.profile['per_layer_by_ctx'][0]['ms'], 'embedMs': self.profile['embed_ms'], 'headMs': self.profile['head_ms'], 'perLayerByCtx': [{'contextLen': r['context_len'], 'perLayerMs': r['ms']} for r in self.profile['per_layer_by_ctx']]}))
                bind = '0.0.0.0' if self.args.command == 'host' else '127.0.0.1'
                self.spawn('controller', [str(self.bin/'controller'), '-mode=standalone', f'-config={config}', f"-grpc-addr={bind}:{self.ports['controller']}", f"-http-addr=127.0.0.1:{self.ports['controller_http']}", '-policy=hysteresis', '-objective=throughput', '-link-source=app'], {'COOLDOWN_S': '10'})
                self.spawn('router', [sys.executable, str(ROOT/'worker/router.py')], {'GRPC_PORT': str(self.ports['router']), 'HTTP_PORT': str(self.ports['router_http']), 'HTTP_HOST': '127.0.0.1', 'GRPC_HOST': '127.0.0.1', 'CONTROLLER_ADDR': f"127.0.0.1:{self.ports['controller']}"})
                if self.args.command == 'host':
                    self.pair_server = ThreadingHTTPServer(('0.0.0.0', self.args.pair_port), handler(self, pair=True))
                    threading.Thread(target=self.pair_server.serve_forever, daemon=True).start()
                    self.workers['w2'] = {'name': 'w2', 'node': 'friend', 'local': False, 'status': 'down', 'layers': None, 'speed': None}
                    print(f'Pair join command: keinfer-demo join <this-laptop-ip> {self.pair_token}', flush=True)
                self.worker('w1')
                if self.args.command == 'solo' and count == 2: self.worker('w2')
                if not hasattr(self, 'monitor_started'):
                    self.monitor_started = True
                    threading.Thread(target=self.monitor, daemon=True).start()
        except Exception as e:
            self.cleanup_pipeline()
            if self.args.device == 'auto' and self.device['selected'] == 'cuda' and not self.closed.is_set():
                self.args.device = 'cpu'
                self.event('rejected', f'GPU startup failed; falling back to CPU: {e}')
                self.initialize()
            else: self.state, self.message = 'failed', str(e)

    def monitor(self):
        while not self.closed.wait(1):
            try:
                if self.args.command == 'join':
                    remote_status = request(f'http://{self.args.host}:{self.args.pair_port}/status', {}, self.args.token)
                    for w in remote_status['workers']:
                        if w['name'] == 'w2':
                            self.workers['w2'].update(layers=w['layers'], speed=w['speed'])
                    self.generation = remote_status['generation']
                    self.state = remote_status['app_state']
                    self.message = 'Friend worker connected; use host dashboard for chat'
                    continue
                if self.state == 'failed': continue
                if self.remote:
                    try:
                        friend = request(f"http://{self.remote['ip']}:{self.remote['port']}/status", {}, self.pair_token)
                        if self.workers['w2']['status'] != 'stopped': self.workers['w2']['status'] = 'up' if friend['running'] else 'down'
                    except Exception:
                        if self.workers['w2']['status'] != 'stopped': self.workers['w2']['status'] = 'down'
                pipeline = request(f"http://127.0.0.1:{self.ports['router_http']}/pipeline")
                stages = pipeline.get('stages', [])
                generation = pipeline.get('generation', -1)
                if generation != self.generation:
                    self.event('healed' if self.state == 'recovering' else 'moved', f'Pipeline generation {generation}')
                    self.generation = generation
                for worker in self.workers.values():
                    stage = next((s for s in stages if s['name'] == worker['name']), None)
                    worker['layers'] = [stage['layers'][0], stage['layers'][1]] if stage else None
                state = request(f"http://127.0.0.1:{self.ports['controller_http']}/state")
                for assignment in state.get('assignments', []) or []:
                    if assignment['worker'] in self.workers: self.workers[assignment['worker']]['speed'] = assignment['speed']
                complete = bool(stages) and stages[0]['layers'][0] == 0 and stages[-1]['layers'][1] == 28
                live = all(self.workers[s['name']]['status'] == 'up' and (not self.workers[s['name']]['local'] or s['addr'].endswith(':'+str(self.workers[s['name']]['port']))) for s in stages)
                if complete and live:
                    self.state, self.message = 'ready', 'Ready for real inference'
            except Exception:
                pass
            for name, proc in list(self.processes.items()):
                if proc.poll() is not None and self.state not in ('stopped', 'failed'):
                    self.state, self.message = 'failed', f'{name} exited; inspect logs/{name}.log'
                    if self.device['selected'] == 'cuda' and self.args.device == 'auto':
                        self.event('rejected', 'GPU runtime failed; restarting on CPU')
                        self.args.device = 'cpu'
                        def fallback():
                            with self.lifecycle:
                                self.cleanup_pipeline(); self.workers.clear(); self.initialize()
                        threading.Thread(target=fallback,daemon=True).start()
                    break

    def control_worker(self, name, action, remote_control=False):
        if name not in self.workers or action not in ('stop', 'restore'): raise ValueError('Unknown worker or action')
        worker = self.workers[name]
        if action == 'restore' and worker['status'] == 'up': raise ValueError('Worker is already running')
        if action == 'stop' and worker['status'] != 'up': raise ValueError('Worker is not running')
        if action == 'stop' and not remote_control and sum(w['status'] == 'up' for w in self.workers.values()) <= 1: raise ValueError('Cannot stop the last running worker')
        if not worker['local']:
            if not self.remote: raise ValueError('Friend has not joined')
            request(f"http://{self.remote['ip']}:{self.remote['port']}/worker", {'action': action}, self.pair_token)
        elif action == 'stop': self.kill(name+'-agent'); self.kill(name)
        elif self.args.command == 'join':
            self.worker(name, self.join_ip, self.args.host, self.join_controller)
        else: self.worker(name)
        worker['status'] = 'stopped' if action == 'stop' else 'up'
        self.state, self.message = 'recovering', 'Waiting for layer reassignment'
        self.event('fault' if action == 'stop' else 'restored', f'{name}: {action}')

    def status(self):
        metrics = {}
        if self.args.command != 'join':
            try: metrics = request(f"http://127.0.0.1:{self.ports['router_http']}/metrics")
            except Exception: pass
        available = len(self.workers) >= 2
        return {'app_state': self.state, 'message': self.message, 'progress': self.progress, 'mode': self.args.command, 'device': self.device, 'workers': [{k:v for k,v in w.items() if k not in ('port','agent')} for w in self.workers.values()], 'generation': self.generation, 'policy': 'hysteresis', 'events': self.events, 'metrics': metrics, 'recovery_demo': {'available': available, 'reason': None if available else 'One worker: insufficient free memory for two, or join mode'}, 'faults_available': ['slow', 'net'] if self.args.command == 'host' and self.remote else [], 'load_on': self.load_on}

    def chat(self, body):
        if self.state != 'ready' or self.args.command == 'join': return 503, {'error': 'not ready'}
        if not self.chat_lock.acquire(False): return 409, {'error': 'busy'}
        try:
            messages = body['messages']
            if not isinstance(messages, list) or not messages or len(messages)>64: raise ValueError('messages must be a nonempty list')
            if any(not isinstance(m, dict) or m.get('role') not in ('user','assistant','system') or not isinstance(m.get('content'), str) for m in messages): raise ValueError('Invalid chat messages')
            limit = body.get('max_new_tokens',128)
            if not isinstance(limit, int) or isinstance(limit,bool) or not 1 <= limit <= 128: raise ValueError('max_new_tokens must be 1..128')
            ids = self.tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, enable_thinking=False, return_dict=False)
            if len(ids)+limit>512: raise ValueError('Context and requested output exceed 512 tokens')
            eos = self.tokenizer.eos_token_id
            result = request(f"http://127.0.0.1:{self.ports['router_http']}/generate", {'input_ids': ids, 'max_new_tokens': limit, 'stop_ids': [eos] if isinstance(eos,int) else eos}, timeout=600)
            tokens = result.pop('tokens')
            result.update(text=self.tokenizer.decode(tokens, skip_special_tokens=True), tokens=len(tokens), device=self.device['selected'])
            return 200, result
        finally: self.chat_lock.release()

    def close(self):
        if self.args.command == 'host' and self.remote:
            try: request(f"http://{self.remote['ip']}:{self.remote['port']}/fault", {'action': 'clear'}, self.pair_token, timeout=2)
            except Exception: pass
        self.closed.set()
        self.state = 'stopped'
        self.kill('calibration')
        with self.lifecycle: self.cleanup_pipeline()
        if hasattr(self,'pair_server'): self.pair_server.shutdown()
        self.server.shutdown()
        (HOME/'state/app.json').unlink(missing_ok=True)


def handler(runtime, pair=False):
    class Handler(BaseHTTPRequestHandler):
        def send(self, code, body, html=False):
            data = body.encode() if html else json.dumps(body).encode()
            self.send_response(code); self.send_header('Content-Type', 'text/html; charset=utf-8' if html else 'application/json'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
        def log_message(self,*args): pass
        def do_GET(self):
            if pair: self.send(404,{'error':'not found'}); return
            if self.path == '/': self.send(200, (ROOT/'demo/app.html').read_text().replace('__SESSION_TOKEN__',runtime.token), True)
            elif self.path == '/api/status': self.send(200,runtime.status())
            elif self.path == '/api/hw': self.send(200,hardware())
            else: self.send(404,{'error':'not found'})
        def do_POST(self):
            token = self.headers.get('X-Session-Token','')
            expected = (runtime.args.token if runtime.args.command == 'join' else runtime.pair_token) if pair else runtime.token
            if not hmac.compare_digest(token, expected) or (pair and runtime.args.command == 'join' and self.client_address[0] != runtime.args.host):
                self.send(403,{'error':'forbidden'}); return
            try:
                length = int(self.headers.get('Content-Length','0'))
                if not 0 < length <= 65536: raise ValueError('Body must be 1..65536 bytes')
                body = json.loads(self.rfile.read(length))
                if not isinstance(body,dict): raise ValueError('Expected JSON object')
                if pair:
                    if self.path == '/status':
                        if runtime.args.command == 'host': self.send(200,runtime.status())
                        else: self.send(200,{'running': bool(runtime.processes.get('w2') and runtime.processes['w2'].poll() is None)})
                        return
                    if self.path == '/enroll' and runtime.args.command == 'host':
                        if runtime.remote and runtime.remote['ip'] != self.client_address[0]: raise ValueError('Another friend is already enrolled')
                        hp = body['helper_port']
                        if not isinstance(hp,int) or not 1024 <= hp <= 65535: raise ValueError('Invalid helper port')
                        runtime.remote = {'ip': self.client_address[0], 'port': hp}
                        runtime.workers['w2']['status'] = 'up'
                        self.send(200,{'profile':runtime.profile, 'controller_port':runtime.ports['controller'], 'join_ip':self.client_address[0]}); return
                    if runtime.args.command != 'join': raise ValueError('Unknown pair endpoint')
                    if self.path == '/fault': result = runtime.helper.action(body['action'])
                    elif self.path == '/worker': runtime.control_worker('w2',body['action'], remote_control=True); result={'ok':True}
                    else: raise ValueError('Unknown endpoint')
                elif self.path == '/api/chat':
                    code,result=runtime.chat(body); self.send(code,result); return
                elif self.path == '/api/worker': runtime.control_worker(body['name'],body['action']); result={'ok':True}
                elif self.path == '/api/fault':
                    if runtime.args.command != 'host' or not runtime.remote or body.get('node') not in ('friend','w2'): raise ValueError('No enrolled friend')
                    result=request(f"http://{runtime.remote['ip']}:{runtime.remote['port']}/fault", {'action':body['action']},runtime.pair_token)
                    runtime.event('fault',body['action'])
                elif self.path == '/api/load':
                    if not isinstance(body.get('on'),bool): raise ValueError('on must be boolean')
                    runtime.load_on=body['on']
                    if runtime.load_on and not getattr(runtime,'load_thread',None):
                        def background():
                            try:
                                while runtime.load_on and not runtime.closed.wait(1):
                                    try: runtime.chat({'messages':[{'role':'user','content':'Explain edge inference briefly.'}], 'max_new_tokens':16})
                                    except Exception: pass
                            finally: runtime.load_thread=None
                        runtime.load_thread=threading.Thread(target=background,daemon=True); runtime.load_thread.start()
                    result={'ok':True}
                elif self.path == '/api/mode':
                    if runtime.args.command != 'solo': raise ValueError('Restart host/join explicitly to switch device')
                    if body.get('device') not in ('auto','cpu','cuda'): raise ValueError('Invalid device')
                    runtime.args.device=body['device']; runtime.state='loading'
                    def restart():
                        with runtime.lifecycle:
                            runtime.cleanup_pipeline(); runtime.workers.clear(); runtime.initialize()
                    threading.Thread(target=restart,daemon=True).start(); result={'ok':True}
                elif self.path == '/api/exit': threading.Thread(target=runtime.close,daemon=True).start(); result={'ok':True}
                else: self.send(404,{'error':'not found'}); return
                self.send(200,result)
            except (ValueError, KeyError, TypeError) as e: self.send(400,{'error':str(e)})
            except Exception as e: self.send(503,{'error':str(e)})
    return Handler


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('command',choices=['solo','host','join','stop','status'],nargs='?',default='solo')
    ap.add_argument('host',nargs='?'); ap.add_argument('token',nargs='?')
    ap.add_argument('--device',choices=['auto','cpu','cuda'],default='auto')
    ap.add_argument('--pair-port',type=int,default=8766)
    args=ap.parse_args()
    if args.command in ('stop','status'):
        try:
            info=json.loads((HOME/'state/app.json').read_text())
            url=f"http://127.0.0.1:{info['port']}"
            print(json.dumps(request(url+('/api/exit' if args.command=='stop' else '/api/status'), {} if args.command=='stop' else None, info['token'])))
        except (OSError, ValueError): print('Demo is not running')
        return
    if args.command=='join':
        if not args.host or not args.token: ap.error('join requires <host-ip> <token>')
        try: socket.inet_aton(args.host)
        except OSError: ap.error('host must be an IPv4 address')
    runtime=Runtime(args)
    def stop(*_): threading.Thread(target=runtime.close,daemon=True).start()
    signal.signal(signal.SIGTERM,stop); signal.signal(signal.SIGINT,stop)
    print(f"Dashboard: http://127.0.0.1:{runtime.ports['app']}",flush=True)
    threading.Thread(target=runtime.initialize,daemon=True).start()
    try: runtime.server.serve_forever()
    finally:
        runtime.cleanup_pipeline()
        runtime.server.server_close()

if __name__=='__main__': main()
