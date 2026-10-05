"""Pair networking and faults, restricted to processes this app owns.

Joining laptops only ever make outbound connections to the host: each keeps a
few idle TCP connections open to the host's tunnel port, and the host splices
one of them to a local connection whenever its router or controller dials that
laptop's worker. A joining laptop therefore needs no open port and no firewall
rule, which is what usually blocks pairing (Windows/WSL, campus Wi-Fi).

Network faults delay only tunnelled worker traffic. Slow faults pause only the
owned worker process. Neither touches shared interfaces or qdiscs.
"""
import collections
import json
import os
import signal
import socket
import threading
import time

GO, PING = b'G', b'P'


def _keepalive(sock):
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    for opt, val in (('TCP_KEEPIDLE', 20), ('TCP_KEEPINTVL', 5), ('TCP_KEEPCNT', 3)):
        if hasattr(socket, opt): sock.setsockopt(socket.IPPROTO_TCP, getattr(socket, opt), val)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)


def _close_listener(sock):
    # shutdown() makes Linux stop accepting at once; close() alone waits for
    # the thread blocked in accept() to notice.
    try: sock.shutdown(socket.SHUT_RDWR)
    except OSError: pass
    sock.close()


def splice(a, b, delay=None, closed=None, track=None):
    """Copy bytes both ways until either side closes. `delay()` (seconds) is
    applied to data flowing b -> a, i.e. from the worker back to the host."""
    def pump(src, dst, delayed):
        try:
            while not (closed and closed.is_set()):
                data = src.recv(65536)
                if not data: break
                d = delay() if delayed and delay else 0
                if d: time.sleep(d)
                dst.sendall(data)
        except OSError: pass
        finally:
            for conn in (src, dst):
                try: conn.shutdown(socket.SHUT_RDWR)
                except OSError: pass
                conn.close()
                if track is not None: track.discard(conn)
    if track is not None: track.update((a, b))
    threading.Thread(target=pump, args=(a, b, False), daemon=True).start()
    threading.Thread(target=pump, args=(b, a, True), daemon=True).start()


class Slowdown:
    """Duty-cycles one owned worker with SIGSTOP/SIGCONT while enabled."""
    def __init__(self, runtime, name):
        self.runtime, self.name = runtime, name
        self.on = threading.Event()
        self.closed = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    def _signal(self, sig):
        proc = self.runtime.processes.get(self.name)
        if proc and proc.poll() is None:
            try: os.killpg(proc.pid, sig)
            except ProcessLookupError: pass

    def _loop(self):
        while not self.closed.wait(.2):
            if self.on.is_set():
                try:
                    self._signal(signal.SIGSTOP)
                    self.closed.wait(.3)
                finally:
                    self._signal(signal.SIGCONT)

    def set(self, on):
        if on: self.on.set()
        else: self.on.clear(); self._signal(signal.SIGCONT)

    def close(self):
        self.on.clear(); self.closed.set(); self._signal(signal.SIGCONT)


class TunnelHub:
    """Host side. Accepts authenticated idle connections from joined laptops
    and exposes each laptop's worker on a private 127.0.0.1 port."""
    def __init__(self, preferred_port, check):
        self.check = check  # check(code, session) -> bool
        self.socket = socket.socket()
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try: self.socket.bind(('0.0.0.0', preferred_port))
        except OSError: self.socket.bind(('0.0.0.0', 0))
        self.socket.listen(64)
        self.socket.settimeout(.5)
        self.port = self.socket.getsockname()[1]
        self.cond = threading.Condition()
        self.idle = collections.defaultdict(collections.deque)  # session -> sockets
        self.listeners = {}  # session -> local listening socket
        self.live = set()
        self.closed = threading.Event()
        threading.Thread(target=self._accept_remote, daemon=True).start()
        threading.Thread(target=self._ping, daemon=True).start()

    def idle_count(self, session):
        with self.cond: return len(self.idle.get(session, ()))

    def register(self, session):
        """Local address the controller and router use for this laptop's worker."""
        with self.cond:
            if session in self.listeners: return self.listeners[session].getsockname()[1]
            local = socket.socket()
            local.bind(('127.0.0.1', 0)); local.listen(16); local.settimeout(.5)
            self.listeners[session] = local
        threading.Thread(target=self._accept_local, args=(session, local), daemon=True).start()
        return local.getsockname()[1]

    def unregister(self, session):
        with self.cond:
            local = self.listeners.pop(session, None)
            conns = self.idle.pop(session, ())
        if local: _close_listener(local)
        for c in conns: c.close()

    def _accept_remote(self):
        while not self.closed.is_set():
            try: conn, _ = self.socket.accept()
            except socket.timeout: continue
            except OSError: break
            threading.Thread(target=self._handshake, args=(conn,), daemon=True).start()

    def _handshake(self, conn):
        try:
            conn.settimeout(5)
            line = b''
            while not line.endswith(b'\n') and len(line) < 512:
                chunk = conn.recv(1)
                if not chunk: raise OSError('closed')
                line += chunk
            hello = json.loads(line)
            session = hello.get('session')
            if not isinstance(session, str) or not self.check(hello.get('code'), session): raise OSError('rejected')
            conn.settimeout(None)
            _keepalive(conn)
        except (OSError, ValueError, AttributeError):
            conn.close(); return
        with self.cond:
            if session not in self.listeners: conn.close(); return
            self.idle[session].append(conn)
            self.cond.notify_all()

    def _take(self, session, timeout=8):
        deadline = time.monotonic() + timeout
        with self.cond:
            while not self.closed.is_set():
                pool = self.idle.get(session)
                while pool:
                    conn = pool.popleft()
                    try:
                        conn.sendall(GO)
                        return conn
                    except OSError:
                        conn.close()
                left = deadline - time.monotonic()
                if left <= 0 or session not in self.listeners: return None
                self.cond.wait(left)
        return None

    def _accept_local(self, session, local):
        while not self.closed.is_set():
            try: client, _ = local.accept()
            except socket.timeout: continue
            except OSError: break
            def bridge(client=client):
                remote = self._take(session)
                if remote is None: client.close(); return
                client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                splice(client, remote, closed=self.closed, track=self.live)
            threading.Thread(target=bridge, daemon=True).start()

    def _ping(self):
        # Idle connections that died silently (sleeping laptop, NAT timeout)
        # are found here instead of when a request needs them.
        while not self.closed.wait(15):
            with self.cond:
                for pool in self.idle.values():
                    for conn in list(pool):
                        try: conn.sendall(PING)
                        except OSError: pool.remove(conn); conn.close()

    def close(self):
        self.closed.set()
        self.socket.close()
        with self.cond:
            for local in self.listeners.values(): _close_listener(local)
            for pool in self.idle.values():
                for c in pool: c.close()
            self.listeners.clear(); self.idle.clear()
            self.cond.notify_all()
        for c in list(self.live):
            try: c.close()
            except OSError: pass


class TunnelClient:
    """Joined-laptop side: keeps `pool` idle outbound connections to the host
    and connects each one to the local worker when the host asks for it."""
    def __init__(self, host, port, session, code, target_port, pool=3):
        self.host, self.port, self.session, self.code = host, port, session, code
        self.target_port = target_port
        self.delay = 0
        self.closed = threading.Event()
        self.live = set()
        self.connected = 0
        self.lock = threading.Lock()
        for _ in range(pool): threading.Thread(target=self._slot, daemon=True).start()

    def _slot(self):
        backoff = .5
        while not self.closed.is_set():
            try:
                conn = socket.create_connection((self.host, self.port), timeout=5)
            except OSError:
                self.closed.wait(backoff); backoff = min(5, backoff * 2); continue
            backoff = .5
            self.live.add(conn)
            try:
                _keepalive(conn)
                conn.sendall(json.dumps({'session': self.session, 'code': self.code}).encode() + b'\n')
                conn.settimeout(45)  # the host pings every 15 s
                with self.lock: self.connected += 1
                try:
                    while True:
                        b = conn.recv(1)
                        if b == PING: continue
                        break
                finally:
                    with self.lock: self.connected -= 1
                if b != GO: raise OSError('closed')
                self.live.discard(conn)
                conn.settimeout(None)
                try: worker = socket.create_connection(('127.0.0.1', self.target_port), timeout=3)
                except OSError: conn.close(); continue
                worker.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                splice(conn, worker, delay=lambda: self.delay, closed=self.closed, track=self.live)
            except OSError:
                self.live.discard(conn); conn.close()
                self.closed.wait(.5)

    def close(self):
        self.closed.set(); self.delay = 0
        for c in list(self.live):
            try: c.close()
            except OSError: pass
