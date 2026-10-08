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
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from hwdetect import hardware, select
from helper import Slowdown, TunnelHub, TunnelClient

ROOT = Path(__file__).resolve().parents[1]
HOME = Path(os.environ.get('SHARDWISE_HOME', os.environ.get('KEINFER_DEMO_HOME', '~/.local/share/shardwise'))).expanduser()
# Small enough to download quickly (~1 GB) and run on any laptop CPU.
MODEL = 'Qwen/Qwen2.5-0.5B-Instruct'
MODEL_REVISION = '7ae557604adf67be50417f59c2c2f167def9a775'
LAYERS = 24
MAX_FRIENDS = 15


def port(preferred=0, host='127.0.0.1'):
    """A free port; `preferred` first, so Pair ports stay fixed (8766-8768 on the inviting laptop)
    and can be allowed through a firewall once."""
    for candidate in ((preferred, 0) if preferred else (0,)):
        with socket.socket() as s:
            # Like Go's listeners: a port in TIME_WAIT after a restart is free.
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try: s.bind((host, candidate))
            except OSError: continue
            return s.getsockname()[1]
    raise RuntimeError('no free port')


def lan_ip():
    """This laptop's address on the local network (no packet is sent)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(('192.0.2.1', 9))
            return s.getsockname()[0]
        except OSError:
            return None


def wsl():
    """'nat' or 'mirrored' under Windows WSL2, None on a normal Linux laptop."""
    try:
        if 'microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower(): return None
    except OSError:
        return None
    ip = lan_ip() or ''
    # WSL's default NAT gives the VM a private 172.16.0.0/12 address other
    # laptops cannot reach; mirrored mode shares the Windows LAN address.
    a = ip.split('.')
    return 'nat' if len(a) == 4 and a[0] == '172' and 16 <= int(a[1]) <= 31 else 'mirrored'


def open_browser(url):
    """Best effort only: never crash and never take over the terminal."""
    try:
        if wsl():
            subprocess.Popen(['explorer.exe', url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'):
            subprocess.Popen(['xdg-open', url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        pass


def pair_code():
    # Eight digits: easy to read aloud and type, nothing to confuse (O/0,
    # l/1). The pair server locks out after repeated wrong codes.
    raw = ''.join(secrets.choice('0123456789') for _ in range(8))
    return raw[:4] + '-' + raw[4:]


def norm_code(code):
    """Digits only, so '4821-0937', '4821 0937', '48210937' and a pasted
    en-dash all match."""
    return ''.join(c for c in str(code or '') if c in '0123456789')


def now_iso():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


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
        except BlockingIOError: raise RuntimeError('Demo already running; use shardwise status or stop')
        self.token = secrets.token_urlsafe(32)
        self.pair_token = pair_code()
        self.pair_failures = 0
        self.processes = {}
        self.workers = {}
        self.events = []
        self.chat_lock = threading.Lock()
        # Real measurements for the dashboard: per-request samples, measured
        # recoveries, and the latest controller/router readings.
        self.user_waiting = threading.Event()
        self.history, self.recoveries = [], []
        self.recovery_started = None
        self.unplaced = set()
        self.ctrl_state, self.stage_stats = {}, []
        self.lifecycle = threading.RLock()
        self.closed = threading.Event()
        self.state, self.message, self.progress = 'loading', 'Starting runtime', None
        self.device = {'requested': args.device, 'selected': 'cpu', 'reason': 'Detecting hardware', 'gpu_name': None}
        self.ports = {k: port() for k in ('app', 'controller_http', 'router', 'router_http')}
        self.ports['controller'] = port(args.pair_port + 1, '0.0.0.0')
        self.generation = -1
        self.load_on = False
        # Host: joined laptops by session. Join: our name and the host's view.
        self.friends = {}
        self.hub = None
        self.tunnel = None
        self.slowdown = None
        self.my_name = None
        self.session = None
        self.host_view = None
        self.host_contact = None
        self.bin = Path(os.environ.get('SHARDWISE_BIN',os.environ.get('KEINFER_BIN', '/opt/shardwise/bin')))
        if not self.bin.exists(): self.bin = ROOT / 'bin'
        self.env = dict(os.environ, HF_HOME=str(HOME/'hf'), MODEL_REVISION=MODEL_REVISION, KV_CACHE='1', MODEL=MODEL, PYTHONUNBUFFERED='1')
        self.env['TORCH_THREADS'] = str(max(1, (os.cpu_count() or 2)//2))
        self.server = ThreadingHTTPServer(('127.0.0.1', self.ports['app']), handler(self))
        info = {'pid': os.getpid(), 'port': self.ports['app'], 'token': self.token}
        path = HOME/'state/app.json'
        path.write_text(json.dumps(info)); path.chmod(0o600)

    def event(self, kind, text):
        self.events.append({'t': now_iso(), 'kind': kind, 'text': text})
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

    def switch_pairing(self, command, host=None, code=None):
        """Change between solo, host and join from the dashboard: tear the
        pipeline down and start it again in the new role."""
        if command not in ('solo', 'host', 'join'): raise ValueError('Unknown pairing mode')
        if command == 'join':
            host = (host or '').strip() if isinstance(host, str) else ''
            try: socket.inet_aton(host); valid = host.count('.') == 3
            except OSError: valid = False
            if not valid: raise ValueError('Enter the inviting laptop’s address exactly as it shows it, e.g. 192.168.1.20')
            code = norm_code(code)
            if len(code) != 8: raise ValueError('The pairing code has 8 digits, e.g. 4821-0937')
            if host == lan_ip() or host.startswith('127.'): raise ValueError('That is this laptop’s own address — enter the address shown on the other laptop')
        def restart():
            if self.args.command == 'join' and self.session:
                try: request(f'http://{self.args.host}:{self.args.pair_port}/leave', {'session': self.session}, self.args.token, timeout=2)
                except Exception: pass
            with self.lifecycle:
                self.cleanup_pipeline()
                if getattr(self, 'pair_server', None):
                    self.pair_server.shutdown(); self.pair_server.server_close(); del self.pair_server
                self.workers.clear(); self.friends.clear(); self.generation = -1; self.recovery_started = None
                self.session = self.my_name = self.host_view = None
                self.args.command, self.args.host, self.args.token = command, host, code
                if command == 'host': self.pair_token, self.pair_failures = pair_code(), 0
                self.state, self.message = 'loading', {'solo': 'Returning to Solo mode', 'host': 'Opening this laptop for pairing', 'join': f'Connecting to {host}'}[command]
                self.event('moved', self.message)
            self.initialize()
        threading.Thread(target=restart, daemon=True).start()

    def pairing(self):
        host = self.args.command == 'host'
        friends = [{'name': f['name'], 'node': f['node'], 'ip': f['ip'], 'status': self.workers.get(f['name'], {}).get('status', 'down')}
                   for f in self.friends.values()] if host else []
        return {'mode': self.args.command, 'lan_ip': lan_ip(), 'pair_port': self.args.pair_port,
                'code': self.pair_token if host else None,
                'friends': friends, 'max_friends': MAX_FRIENDS,
                'friend': ', '.join(f['node'] for f in friends if f['status'] == 'up') or None,
                'host': self.args.host if self.args.command == 'join' else None,
                'name': self.my_name,
                'ports': sorted({self.args.pair_port, self.ports['controller'], self.hub.port if self.hub else self.args.pair_port + 2}),
                'warning': 'This Windows WSL setup uses NAT networking: it can join other laptops, but other laptops cannot reach it to join. To invite from this laptop, turn on mirrored networking (see WINDOWS.md) and restart Shardwise.' if wsl() == 'nat' else None}

    def cleanup_pipeline(self):
        if self.slowdown: self.slowdown.close(); self.slowdown = None
        if self.tunnel: self.tunnel.close(); self.tunnel = None
        if self.hub: self.hub.close(); self.hub = None
        for name in list(self.processes): self.kill(name)

    def prepare(self):
        from huggingface_hub import snapshot_download
        from transformers import AutoTokenizer
        self.state, self.message = 'downloading', f'Downloading or checking the cached model ({MODEL.split("/")[-1]}, ~1 GB once)'
        snapshot_download(MODEL, revision=MODEL_REVISION, cache_dir=str(HOME/'hf'/'hub'), allow_patterns=['*.json', '*.safetensors', '*.txt', '*.jinja', '*.model'])
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=MODEL_REVISION, cache_dir=str(HOME/'hf'/'hub'), local_files_only=True)
        from transformers import AutoConfig
        layers = AutoConfig.from_pretrained(MODEL, revision=MODEL_REVISION, cache_dir=str(HOME/'hf'/'hub'), local_files_only=True).num_hidden_layers
        if layers != LAYERS: raise RuntimeError(f'{MODEL} has {layers} layers, expected {LAYERS}')
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

    def worker(self, name, advertise=None, controller=None):
        entry = self.workers.get(name)
        if not entry:
            entry = {'name': name, 'node': socket.gethostname(), 'local': True, 'status': 'up', 'layers': None, 'speed': None, 'port': port(), 'agent': port()}
            self.workers[name] = entry
        entry['status'] = 'up'
        profile = ','.join(f"{r['context_len']}:{r['ms']}" for r in self.reference['per_layer_by_ctx'])
        self.spawn(name, [sys.executable, str(ROOT/'worker/server.py')], {'PORT': str(entry['port']), 'WORKER_NAME': name, 'NODE_AGENT_ADDR': f"127.0.0.1:{entry['agent']}", 'PER_LAYER_PROFILE': profile, 'HF_HUB_OFFLINE': '1', 'GRPC_HOST': '127.0.0.1'})
        # A joined laptop advertises the host-side end of its tunnel: the
        # controller and router dial that, on the host's own loopback.
        self.spawn(name+'-agent', [str(self.bin/'nodeagent')], {'NODE_NAME': name, 'HTTP_ADDR': f"127.0.0.1:{entry['agent']}", 'CONTROLLER_ADDR': controller or f"127.0.0.1:{self.ports['controller']}", 'WORKER_ADDR': advertise or f"127.0.0.1:{entry['port']}", 'WORKER_PROBE_ADDR': f"127.0.0.1:{entry['port']}", 'GPU_MODE': 'measured', 'EBPF': 'off'})
        return entry

    def initialize(self):
        try:
            with self.lifecycle:
                if self.args.command == 'join':
                    self.state, self.message = 'loading', f'Checking {self.args.host} and the pairing code'
                    self.check_invite()
                count = self.prepare()
                if self.closed.is_set(): return
                self.state, self.message = 'loading', 'Loading workers and pipeline'
                if self.args.command == 'join':
                    self.join_host()
                    if not hasattr(self, 'monitor_started'):
                        self.monitor_started = True
                        threading.Thread(target=self.monitor, daemon=True).start()
                    return
                self.reference = self.profile
                config = HOME/'state/controller.json'
                config.write_text(json.dumps({'model': MODEL, 'backend': 'qwen3', 'totalLayers': LAYERS, 'workers': 1 if self.args.command == 'host' else count, 'routerAddr': f"127.0.0.1:{self.ports['router']}", 'contextLen': 512, 'perLayerMs': self.profile['per_layer_by_ctx'][0]['ms'], 'embedMs': self.profile['embed_ms'], 'headMs': self.profile['head_ms'], 'perLayerByCtx': [{'contextLen': r['context_len'], 'perLayerMs': r['ms']} for r in self.profile['per_layer_by_ctx']]}))
                bind = '0.0.0.0' if self.args.command == 'host' else '127.0.0.1'
                self.spawn('controller', [str(self.bin/'controller'), '-mode=standalone', f'-config={config}', f"-grpc-addr={bind}:{self.ports['controller']}", f"-http-addr=127.0.0.1:{self.ports['controller_http']}", '-policy=hysteresis', '-objective=throughput', '-link-source=app'], {'COOLDOWN_S': '10'})
                self.spawn('router', [sys.executable, str(ROOT/'worker/router.py')], {'GRPC_PORT': str(self.ports['router']), 'HTTP_PORT': str(self.ports['router_http']), 'HTTP_HOST': '127.0.0.1', 'GRPC_HOST': '127.0.0.1', 'CONTROLLER_ADDR': f"127.0.0.1:{self.ports['controller']}"})
                if self.args.command == 'host':
                    self.hub = TunnelHub(self.args.pair_port + 2, lambda code, session: hmac.compare_digest(norm_code(code), norm_code(self.pair_token)) and session in self.friends)
                    self.pair_server = ThreadingHTTPServer(('0.0.0.0', self.args.pair_port), handler(self, pair=True))
                    threading.Thread(target=self.pair_server.serve_forever, daemon=True).start()
                    print(f'Invite open. On other laptops: shardwise join {lan_ip()} {self.pair_token}', flush=True)
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

    def reach(self, port, what):
        """Fail with a message that says what to fix, not just 'cannot connect'."""
        host = self.args.host
        try: socket.create_connection((host, port), timeout=4).close()
        except ConnectionRefusedError:
            raise RuntimeError(f'{host} answered but refused port {port} ({what}). Is that laptop showing an invite ("Invite laptops")? Is {host} the address it shows?') from None
        except OSError:
            raise RuntimeError(f'No answer from {host} on port {port} ({what}). Check: (1) both laptops on the same Wi-Fi — campus/guest Wi-Fi often blocks laptop-to-laptop traffic, a phone hotspot works; '
                               f'(2) the inviting laptop allows TCP ports {self.args.pair_port}-{self.args.pair_port + 2} through its firewall (Windows: see WINDOWS.md).') from None

    def check_invite(self):
        """Seconds, not minutes: verify address and code before downloading."""
        self.reach(self.args.pair_port, 'pairing')
        try: request(f'http://{self.args.host}:{self.args.pair_port}/check', {}, self.args.token)
        except urllib.error.HTTPError as e: raise self.pair_error(e) from None

    @staticmethod
    def pair_error(e):
        try: detail = json.load(e).get('error', '')
        except Exception: detail = ''
        return RuntimeError({403: 'Wrong pairing code. Type the 8 digits shown on the inviting laptop (pressing Invite again makes a new code).',
                             410: 'That laptop is not inviting right now. Press "Invite laptops" on it first.',
                             429: 'The inviting laptop received too many wrong codes. Press Stop sharing and Invite again there for a new code.'}.get(e.code, f'Pairing refused: {detail or e.code}'))

    def join_host(self):
        """Join mode: enroll with the host, then run one worker that the host
        reaches through an outbound tunnel (no inbound port on this laptop)."""
        host, code, pp = self.args.host, self.args.token, self.args.pair_port
        self.reach(pp, 'pairing')
        try:
            data = request(f'http://{host}:{pp}/enroll', {'node': socket.gethostname(), 'session': self.session}, code)
        except urllib.error.HTTPError as e:
            raise self.pair_error(e) from None
        if (data.get('model'), data.get('revision')) != (MODEL, MODEL_REVISION):
            raise RuntimeError(f"The inviting laptop runs {data.get('model') or 'an older Shardwise'}, this one runs {MODEL}. Install the same Shardwise version on every laptop.")
        self.reach(data['controller_port'], 'controller')
        self.reach(data['tunnel_port'], 'worker tunnel')
        self.session, self.my_name, self.reference = data['session'], data['name'], data['profile']
        self.host_contact = time.monotonic()
        entry = self.worker(self.my_name, advertise=f"127.0.0.1:{data['worker_port']}", controller=f"{host}:{data['controller_port']}")
        self.join_info = data
        self.tunnel = TunnelClient(host, data['tunnel_port'], self.session, code, entry['port'])
        self.slowdown = Slowdown(self, self.my_name)
        self.state, self.message = 'loading', f'Joined {host} as {self.my_name}; waiting for layers'
        self.event('restored', f'Joined {host} as {self.my_name}')

    def run_command(self, cmd):
        """Join mode: a control the host's dashboard queued for this laptop."""
        name, action = self.my_name, cmd.get('action')
        if cmd.get('type') == 'worker':
            if action == 'stop': self.kill(name+'-agent'); self.kill(name)
            elif action == 'restore' and not (self.processes.get(name) and self.processes[name].poll() is None):
                d = self.join_info
                self.worker(name, advertise=f"127.0.0.1:{d['worker_port']}", controller=f"{self.args.host}:{d['controller_port']}")
            self.workers[name]['status'] = 'stopped' if action == 'stop' else 'up'
        elif action == 'slow': self.slowdown.set(True)
        elif action == 'net': self.tunnel.delay = .1
        elif action == 'clear': self.slowdown.set(False); self.tunnel.delay = 0
        self.event('fault' if action in ('stop', 'slow', 'net') else 'restored', f'Host: {action} {name}')

    def enroll(self, body, ip):
        """Host mode: admit one more laptop (or re-admit a known session)."""
        session = body.get('session')
        node = body.get('node', 'laptop')
        if not isinstance(node, str) or not 1 <= len(node) <= 64: raise ValueError('Invalid node name')
        friend = self.friends.get(session) if isinstance(session, str) else None
        if not friend:
            # The same laptop coming back (crash, sleep, restart) keeps its slot.
            friend = next((f for f in self.friends.values() if f['node'] == node and f.get('ip') == ip
                           and self.workers.get(f['name'], {}).get('status') != 'up'), None)
            if friend:
                session = friend['session']; friend['commands'] = []
                self.event('restored', f"{node} ({ip}) came back as {friend['name']}")
        if not friend:
            if len(self.friends) >= MAX_FRIENDS: raise ValueError(f'This invite is full ({MAX_FRIENDS} laptops)')
            k = 2
            while f'w{k}' in self.workers: k += 1
            session = secrets.token_hex(16)
            friend = self.friends[session] = {'session': session, 'name': f'w{k}', 'node': node, 'commands': [], 'running': False}
            self.workers[friend['name']] = {'name': friend['name'], 'node': node, 'local': False, 'status': 'down', 'layers': None, 'speed': None}
            self.event('restored', f"{node} ({ip}) joined as {friend['name']}")
        friend.update(ip=ip, last_seen=time.monotonic())
        friend['worker_port'] = self.hub.register(session)
        return {'session': session, 'name': friend['name'], 'profile': self.profile, 'model': MODEL, 'revision': MODEL_REVISION, 'controller_port': self.ports['controller'],
                'tunnel_port': self.hub.port, 'worker_port': friend['worker_port']}

    def drop_friend(self, session, why):
        friend = self.friends.pop(session, None)
        if not friend: return
        if self.hub: self.hub.unregister(session)
        was_up = self.workers.pop(friend['name'], {}).get('status') == 'up'
        if was_up and self.recovery_started is None:
            self.recovery_started = (f"{friend['name']} ({friend['node']}) loss recovery", time.monotonic())
        self.event('fault', f"{friend['node']} ({friend['name']}) {why}")

    def friend_named(self, name):
        return next((f for f in self.friends.values() if name in (f['name'], f['node'])), None)

    def poll_host(self):
        """Join mode, every second: report this worker, fetch queued controls
        and the host's pipeline view. Only outbound requests."""
        proc = self.processes.get(self.my_name)
        report = {'session': self.session, 'running': bool(proc and proc.poll() is None),
                  'slow': bool(self.slowdown and self.slowdown.on.is_set()), 'net': bool(self.tunnel and self.tunnel.delay),
                  'tunnel': self.tunnel.connected if self.tunnel else 0}
        try:
            reply = request(f'http://{self.args.host}:{self.args.pair_port}/poll', report, self.args.token, timeout=4)
        except urllib.error.HTTPError as e:
            if e.code == 410:  # host restarted or dropped us: enroll again
                self.event('moved', 'The inviting laptop no longer knew this laptop; joining again')
                self.session = None
                def again():
                    with self.lifecycle:
                        self.cleanup_pipeline(); self.workers.clear(); self.host_view = None
                    self.initialize()
                threading.Thread(target=again, daemon=True).start()
            else:
                self.cleanup_pipeline()
                self.state, self.message = 'failed', 'The inviting laptop stopped sharing or made a new code. Press Back to Solo, then Join with the new code.'
            return
        except OSError:
            gone = time.monotonic() - (self.host_contact or 0)
            self.state = 'recovering'
            self.message = f'Lost contact with {self.args.host} for {gone:.0f} s — retrying' + ('. It may have stopped sharing or left the Wi-Fi.' if gone > 15 else '')
            return
        self.host_contact = time.monotonic()
        for cmd in reply.pop('commands', []): self.run_command(cmd)
        self.host_view = reply
        self.generation = reply.get('generation', -1)
        self.state = reply.get('app_state', 'loading')
        self.message = f"Part of {self.args.host}'s pipeline as {self.my_name}. Chat runs on that laptop."

    def monitor(self):
        while not self.closed.wait(1):
            try:
                if self.args.command == 'join':
                    if not self.session or self.state == 'failed': continue
                    self.poll_host()
                    continue
                if self.state == 'failed': continue
                if not self.lifecycle.acquire(False): continue
                try: processes = list(self.processes.items())
                finally: self.lifecycle.release()
                crashed = next(((name,proc) for name,proc in processes if proc.poll() is not None),None)
                if crashed and self.processes.get(crashed[0]) is crashed[1]:
                    name,proc=crashed
                    if name in self.workers: self.workers[name]['status']='down'
                    self.state,self.message='failed',f'{name} exited; inspect logs/{name}.log'
                    if self.device['selected']=='cuda' and self.args.device=='auto':
                        self.event('rejected','GPU runtime failed; restarting on CPU')
                        self.args.device='cpu'
                        def fallback():
                            with self.lifecycle:
                                self.cleanup_pipeline(); self.workers.clear(); self.initialize()
                        threading.Thread(target=fallback,daemon=True).start()
                    continue
                now = time.monotonic()
                for session, friend in list(self.friends.items()):
                    w = self.workers.get(friend['name'])
                    # A queued or just-delivered stop/restore decides, not a stale report.
                    if not w or friend['commands'] or now < friend.get('grace_until', 0): continue
                    fresh = now - friend['last_seen'] < 5
                    if not fresh and now - friend['last_seen'] > 120:
                        self.drop_friend(session, 'left (no contact for 2 minutes)'); continue
                    if w['status'] != 'stopped':
                        new = 'up' if fresh and friend['running'] else 'down'
                        # A laptop joining or leaving is timed like the Stop
                        # and Restore buttons: until the pipeline is whole.
                        if new != w['status']:
                            if self.recovery_started is None:
                                # A lost laptop is timed from its last contact.
                                self.recovery_started = (f"{w['name']} ({w['node']}) {'join' if new == 'up' else 'loss recovery'}", now if new == 'up' else friend['last_seen'], w['name'] if new == 'up' else None)
                            self.event('restored' if new == 'up' else 'fault', f"{w['node']} ({w['name']}) {'connected' if new == 'up' else 'unreachable'}")
                        w['status'] = new
                state = request(f"http://127.0.0.1:{self.ports['controller_http']}/state")
                pipeline = request(f"http://127.0.0.1:{self.ports['router_http']}/pipeline")
                stages = pipeline.get('stages', [])
                generation = pipeline.get('generation', -1)
                if generation != self.generation:
                    split = ' · '.join(f"{s['name']} L{s['layers'][0]}–{s['layers'][1]-1}" for s in stages) or 'no stages'
                    self.event('healed' if self.state == 'recovering' else 'moved', f'Generation {generation}: {split}')
                    self.generation = generation
                for worker in list(self.workers.values()):
                    stage = next((s for s in stages if s['name'] == worker['name']), None)
                    worker['layers'] = [stage['layers'][0], stage['layers'][1]] if stage else None
                self.ctrl_state = state
                try: self.stage_stats = request(f"http://127.0.0.1:{self.ports['router_http']}/stats").get('stages', [])
                except Exception: self.stage_stats = []
                for assignment in state.get('assignments', []) or []:
                    if assignment['worker'] in self.workers: self.workers[assignment['worker']]['speed'] = assignment['speed']
                complete = bool(stages) and stages[0]['layers'][0] == 0 and stages[-1]['layers'][1] == LAYERS
                def alive(stage):
                    w = self.workers.get(stage['name'])
                    if not w or w['status'] != 'up': return False
                    if not w['local']: return True
                    proc = self.processes.get(w['name'])
                    return stage['addr'].endswith(':'+str(w['port'])) and proc is not None and proc.poll() is None
                live = all(alive(st) for st in stages)
                assigned = {s['name'] for s in stages}
                # Only workers whose node agent reaches the controller can be
                # placed; one that never does must not block everyone's chat.
                heard = set(((state.get('telemetry') or {}).get('nodes') or {}).keys())
                expected = {w['name'] for w in self.workers.values() if w['status']=='up' and (w['local'] or w['name'] in heard)}
                contiguous = all(a['layers'][1]==b['layers'][0] for a,b in zip(stages,stages[1:]))
                # A worker the controller does not place within 2 minutes (e.g.
                # judged too slow to help) stops blocking readiness.
                self.unplaced -= assigned
                expected -= self.unplaced
                # A join/rejoin is complete only once that worker holds layers.
                want = {self.recovery_started[2]} - {None} if self.recovery_started and len(self.recovery_started) > 2 else set()
                if self.recovery_started and time.monotonic() - self.recovery_started[1] > 120 and not (expected | want).issubset(assigned):
                    self.unplaced |= (expected | want) - assigned
                    self.event('rejected', f'{self.recovery_started[0]}: not placed within 120 s; the controller kept the current layout')
                    self.recovery_started = None
                    expected -= self.unplaced
                if complete and live and contiguous and expected.issubset(assigned):
                    if self.recovery_started is not None and want.issubset(assigned):
                        kind, t0 = self.recovery_started[:2]
                        secs = round(time.monotonic() - t0, 1)
                        self.recoveries = (self.recoveries + [{'kind': kind, 'seconds': secs, 't': now_iso()}])[-10:]
                        self.event('healed', f'{kind} completed in {secs} s (measured)')
                        self.recovery_started = None
                    self.state, self.message = 'ready', 'Ready for real inference'
                elif self.state == 'ready':
                    self.state,self.message='recovering','Waiting for a complete live pipeline'
            except Exception:
                if self.state == 'ready':
                    self.state,self.message='recovering','Coordinator temporarily unreachable'

    def control_worker(self, name, action):
        if name not in self.workers or action not in ('stop', 'restore'): raise ValueError('Unknown worker or action')
        worker = self.workers[name]
        if action == 'restore' and worker['status'] == 'up': raise ValueError('Worker is already running')
        if action == 'stop' and worker['status'] != 'up': raise ValueError('Worker is not running')
        if action == 'stop' and sum(w['status'] == 'up' for w in self.workers.values()) <= 1: raise ValueError('Cannot stop the last running worker')
        if not worker['local']:
            friend = self.friend_named(name)
            if not friend: raise ValueError('That laptop is not connected')
            friend['commands'].append({'type': 'worker', 'action': action})
        elif action == 'stop': self.kill(name+'-agent'); self.kill(name)
        else: self.worker(name)
        worker['status'] = 'stopped' if action == 'stop' else 'up'
        self.unplaced.discard(name)
        self.recovery_started = (f'{name} {"loss recovery" if action == "stop" else "rejoin"}', time.monotonic(), name if action == 'restore' else None)
        self.state, self.message = 'recovering', 'Waiting for layer reassignment'
        self.event('fault' if action == 'stop' else 'restored', f'{name}: {action}')

    def status(self):
        metrics = {}
        workload = None
        transitions = []
        if self.args.command != 'join':
            try: metrics = request(f"http://127.0.0.1:{self.ports['router_http']}/metrics")
            except Exception: pass
            try: workload = request(f"http://127.0.0.1:{self.ports['router_http']}/workload", timeout=.7)
            except Exception: pass
            try: transitions = request(f"http://127.0.0.1:{self.ports['router_http']}/transitions", timeout=.7).get('events', [])
            except Exception: pass
        workers = [{k:v for k,v in w.items() if k not in ('port','agent')} for w in self.workers.values()]
        telemetry = self.telemetry()
        if self.args.command == 'join' and self.host_view:
            # Show the whole pipeline as the host sees it; "local" = this laptop.
            workers = [dict(w, local=w['name'] == self.my_name) for w in self.host_view.get('workers', [])]
            metrics, telemetry = self.host_view.get('metrics') or {}, self.host_view.get('telemetry') or telemetry
        available = len(self.workers) >= 2 and self.args.command != 'join'
        reason = 'Controls are on the inviting laptop.' if self.args.command == 'join' else 'One worker: not enough free memory for two on this laptop. Invite another laptop to demonstrate recovery.'
        return {'app_state': self.state, 'message': self.message, 'progress': self.progress, 'mode': self.args.command, 'device': self.device, 'workers': workers, 'generation': self.generation, 'policy': 'hysteresis', 'events': self.events, 'metrics': metrics, 'recovery_demo': {'available': available, 'reason': None if available else reason}, 'faults_available': ['slow', 'net'] if self.args.command == 'host' and self.friends else [], 'load_on': self.load_on,
                'total_layers': LAYERS, 'model': MODEL, 'telemetry': telemetry, 'pairing': self.pairing(),
                'workload': workload, 'transitions': transitions}

    def telemetry(self):
        """Measured values only: controller predictions from measured speeds,
        router-observed stage busy time, link RTTs, decisions, recoveries."""
        st = self.ctrl_state or {}
        tel = st.get('telemetry') or {}
        decisions = [{'t': d.get('time'), 'reason': d.get('reason'), 'executed': d.get('executed'), 'gate_accepts': d.get('gate_accepts'),
                      'improvement_pct': round(100 * (d.get('improvement_frac') or 0), 1), 'from': d.get('from_splits'), 'to': d.get('to_splits'),
                      'predicted_ms': round(d['optimal_objective_ms'], 1) if d.get('optimal_objective_ms') else None,
                      'transition_forecast_ms': d.get('transition_ms'), 'active_requests': d.get('concurrency')}
                     for d in (st.get('decisions') or [])[-8:]][::-1]
        names = {w['port']: w['name'] for w in self.workers.values() if w.get('port')}
        names.update({f['worker_port']: f['name'] for f in self.friends.values() if f.get('worker_port')})
        stages = [{'name': s.get('name'), 'busy_pct': round(100 * (1 - s['idle_fraction']), 1) if s.get('idle_fraction') is not None else None,
                   'forwards': s.get('forwards')} for s in self.stage_stats]
        return {'predicted_token_ms': round(st['pipeline_ms'], 1) if st.get('pipeline_ms') else None,
                'predicted_bottleneck_ms': round(st['bottleneck_ms'], 1) if st.get('bottleneck_ms') else None,
                'nodes': {k: {'speed': v.get('speed_factor'), 'age_s': round(v.get('age_s') or 0, 1),
                              'temp_c': v['temp_c'] if (v.get('temp_c') or -1) >= 0 else None} for k, v in (tel.get('nodes') or {}).items()},
                'links': [{'dst': names.get(f.get('port')) or f"{f.get('dst')}:{f.get('port')}", 'rtt_ms': round(f['srtt_ms'], 2) if f.get('srtt_ms') else None} for f in tel.get('flows') or []],
                'stages': stages, 'decisions': decisions, 'history': self.history, 'recoveries': self.recoveries,
                'recovering_for_s': round(time.monotonic() - self.recovery_started[1], 1) if self.recovery_started else None}

    def chat(self, body, background=False):
        if self.args.command == 'join': return 503, {'error': 'Chat runs on the host laptop'}
        if background:
            if self.user_waiting.is_set() or self.state != 'ready' or not self.chat_lock.acquire(False):
                return 409, {'error': 'busy'}
        else:
            # A person asking waits through a recovery or a background request
            # instead of being turned away; background load yields meanwhile.
            self.user_waiting.set()
            try:
                deadline = time.monotonic() + 90
                while self.state != 'ready' and time.monotonic() < deadline and not self.closed.is_set():
                    time.sleep(0.25)
                if self.state != 'ready': return 503, {'error': f'Pipeline not ready ({self.state}): {self.message}'}
                if not self.chat_lock.acquire(timeout=max(1, deadline - time.monotonic())):
                    return 409, {'error': 'Another request is still running; try again'}
            finally: self.user_waiting.clear()
        try:
            if self.state != 'ready': return 503, {'error':'not ready'}
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
            self.history = (self.history + [{'t': now_iso(), 'tokens_per_sec': result.get('tokens_per_sec'), 'ttft_ms': result.get('ttft_ms'),
                                             'ms_per_token': round(result['duration_ms'] / max(1, len(tokens)), 1), 'replays': result.get('replays', 0),
                                             'generation': result.get('generation'), 'source': 'load' if background else 'chat'}])[-60:]
            return 200, result
        finally: self.chat_lock.release()

    def close(self):
        if self.args.command == 'join' and self.session:
            try: request(f'http://{self.args.host}:{self.args.pair_port}/leave', {'session': self.session}, self.args.token, timeout=2)
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
            elif self.path == '/illustration': self.send(200,(ROOT/'demo/cpu-gpu-illustration.html').read_text(),True)
            elif self.path == '/api/status': self.send(200,runtime.status())
            elif self.path == '/api/hw': self.send(200,hardware())
            else: self.send(404,{'error':'not found'})
        def do_POST(self):
            token = self.headers.get('X-Session-Token','')
            if not token.isascii(): token = ''
            if pair:
                if runtime.args.command != 'host': self.send(410,{'error':'not inviting'}); return
                if runtime.pair_failures >= 20:
                    self.send(429,{'error':'too many wrong pairing codes; start a new invite'}); return
                ok = hmac.compare_digest(norm_code(token), norm_code(runtime.pair_token))
            else: ok = hmac.compare_digest(token, runtime.token)
            if not ok:
                if pair: runtime.pair_failures += 1
                self.send(403,{'error':'wrong pairing code' if pair else 'forbidden'}); return
            try:
                length = int(self.headers.get('Content-Length','0'))
                if not 0 < length <= 65536: raise ValueError('Body must be 1..65536 bytes')
                body = json.loads(self.rfile.read(length))
                if not isinstance(body,dict): raise ValueError('Expected JSON object')
                if pair:
                    ip = self.client_address[0]
                    if self.path == '/check': result = {'ok': True}
                    elif self.path == '/enroll':
                        if not runtime.hub: self.send(503,{'error':'invite is still starting'}); return
                        with runtime.lifecycle: result = runtime.enroll(body, ip)
                    elif self.path in ('/poll', '/leave'):
                        friend = runtime.friends.get(body.get('session'))
                        if not friend: self.send(410,{'error':'unknown session'}); return
                        if self.path == '/leave':
                            runtime.drop_friend(friend['session'], 'left'); result = {'ok': True}
                        else:
                            friend.update(ip=ip, last_seen=time.monotonic(), running=bool(body.get('running')), slow=bool(body.get('slow')), net=bool(body.get('net')), tunnel=body.get('tunnel'))
                            commands, friend['commands'] = friend['commands'], []
                            if commands: friend['grace_until'] = time.monotonic() + 3
                            view = runtime.status(); view.pop('pairing', None); view.pop('events', None)
                            result = dict(view, commands=commands)
                    else: self.send(404,{'error':'not found'}); return
                elif self.path == '/api/pair':
                    action = body.get('action')
                    target = {'invite': 'host', 'join': 'join', 'leave': 'solo'}.get(action)
                    if not target: raise ValueError('action must be invite, join or leave')
                    if target == runtime.args.command and target != 'join': result = {'ok': True}
                    else:
                        runtime.switch_pairing(target, body.get('host'), body.get('code'))
                        result = {'ok': True}
                elif self.path == '/api/chat':
                    code,result=runtime.chat(body); self.send(code,result); return
                elif self.path == '/api/worker':
                    if runtime.state not in ('ready','recovering'):
                        self.send(409,{'error':'Pipeline is initializing or unavailable'}); return
                    with runtime.lifecycle: runtime.control_worker(body['name'],body['action'])
                    result={'ok':True}
                elif self.path == '/api/fault':
                    friend = runtime.friend_named(body.get('node')) if runtime.args.command == 'host' else None
                    if not friend: raise ValueError('That laptop is not connected')
                    if body.get('action') not in ('slow','net','clear'): raise ValueError('action must be slow, net or clear')
                    friend['commands'].append({'type': 'fault', 'action': body['action']})
                    runtime.event('fault' if body['action'] != 'clear' else 'restored', f"{body['action']} on {friend['name']} ({friend['node']})")
                    result={'ok':True}
                elif self.path == '/api/load':
                    if not isinstance(body.get('on'),bool): raise ValueError('on must be boolean')
                    runtime.load_on=body['on']
                    if runtime.load_on and not getattr(runtime,'load_thread',None):
                        def background():
                            try:
                                while runtime.load_on and not runtime.closed.wait(1):
                                    try: runtime.chat({'messages':[{'role':'user','content':'Explain edge inference briefly.'}], 'max_new_tokens':16}, background=True)
                                    except Exception: pass
                            finally: runtime.load_thread=None
                        runtime.load_thread=threading.Thread(target=background,daemon=True); runtime.load_thread.start()
                    result={'ok':True}
                elif self.path == '/api/mode':
                    if runtime.chat_lock.locked() or runtime.state != 'ready':
                        self.send(409,{'error':'busy'}); return
                    if runtime.args.command != 'solo': raise ValueError('Restart host/join explicitly to switch device')
                    if body.get('device') not in ('auto','cpu','cuda'): raise ValueError('Invalid device')
                    if body['device'] != 'cpu':
                        import torch
                        gpu = hardware()['gpu']
                        if body['device'] == 'cuda' and not gpu:
                            raise ValueError('Forced GPU unavailable: NVIDIA GPU/driver not detected. Select CPU or Auto.')
                        if torch.version.cuda is None and gpu:
                            raise ValueError('This runtime has CPU-only PyTorch. Exit and launch shardwise again to install the detected GPU runtime; then switch devices.')
                    if not runtime.chat_lock.acquire(False):
                        self.send(409,{'error':'busy'}); return
                    try:
                        runtime.args.device=body['device']; runtime.state='loading'
                    finally: runtime.chat_lock.release()
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
    ap.add_argument('--no-browser',action='store_true')
    ap.add_argument('--pair-port',type=int,default=8766)
    args=ap.parse_args()
    if args.command in ('stop','status'):
        try:
            info=json.loads((HOME/'state/app.json').read_text())
            url=f"http://127.0.0.1:{info['port']}"
            response = request(url+('/api/exit' if args.command=='stop' else '/api/status'), {} if args.command=='stop' else None, info['token'])
            if args.command == 'stop':
                deadline = time.monotonic()+30
                while time.monotonic() < deadline:
                    try:
                        with open(HOME/'state/lock','a') as lock:
                            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                        break
                    except BlockingIOError: time.sleep(.1)
                else: raise RuntimeError('Demo shutdown still pending; inspect logs before restarting')
            print(json.dumps(response))
        except (OSError, ValueError): print('Demo is not running')
        return
    if args.command=='join':
        if not args.host or not args.token: ap.error('join requires <host-ip> <pairing-code>')
        try: socket.inet_aton(args.host)
        except OSError: ap.error('host must be an IPv4 address')
        args.token = norm_code(args.token)
        if len(args.token) != 8: ap.error('the pairing code has 8 digits, e.g. 4821-0937')
    try: runtime=Runtime(args)
    except RuntimeError as e:
        print(str(e),file=sys.stderr); return 1
    def stop(*_): threading.Thread(target=runtime.close,daemon=True).start()
    signal.signal(signal.SIGTERM,stop); signal.signal(signal.SIGINT,stop)
    url = f"http://127.0.0.1:{runtime.ports['app']}"
    print(f'Dashboard: {url}',flush=True)
    if not args.no_browser:
        threading.Thread(target=open_browser,args=(url,),daemon=True).start()
    threading.Thread(target=runtime.initialize,daemon=True).start()
    try: runtime.server.serve_forever()
    finally:
        runtime.cleanup_pipeline()
        runtime.server.server_close()

if __name__=='__main__': sys.exit(main())
