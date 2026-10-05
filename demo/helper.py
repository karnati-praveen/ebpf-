"""Authenticated pair controls restricted to the enrolled host and app processes.

Network faults delay only an app-owned TCP relay. Slow faults pause only
the owned worker. Neither operation changes shared interfaces or qdiscs.
"""
import hmac
import os
import signal
import threading
import time


class Helper:
    def __init__(self, runtime, host_ip, token):
        self.runtime, self.host_ip, self.token = runtime, host_ip, token
        self.slow = threading.Event()
        self.closed = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def authorize(self, ip, token):
        return ip == self.host_ip and hmac.compare_digest(token or '', self.token)

    def _signal(self, sig):
        proc = self.runtime.processes.get('w2')
        if proc and proc.poll() is None:
            try: os.killpg(proc.pid, sig)
            except ProcessLookupError: pass

    def _loop(self):
        while not self.closed.wait(.2):
            if self.slow.is_set():
                try:
                    self._signal(signal.SIGSTOP)
                    self.closed.wait(.3)
                finally:
                    self._signal(signal.SIGCONT)

    def action(self, action):
        if action == 'slow': self.slow.set()
        elif action == 'net': self.runtime.relay.delay = .1
        elif action == 'clear':
            if getattr(self.runtime, 'relay', None): self.runtime.relay.delay = 0
            self.slow.clear()
            self._signal(signal.SIGCONT)
        elif action != 'status': raise ValueError('Only slow, net, clear and status are supported')
        return {'ok': True, 'slow': self.slow.is_set(), 'net': bool(getattr(self.runtime, 'relay', None) and self.runtime.relay.delay)}

    def close(self):
        if getattr(self.runtime, 'relay', None): self.runtime.relay.delay = 0
        self.slow.clear()
        self.closed.set()
        self._signal(signal.SIGCONT)
        self.thread.join(timeout=1)

class DelayedRelay:
    """App-owned worker TCP proxy; delays only worker-to-router traffic."""
    def __init__(self, target_port, preferred_port=0):
        import socket
        self.socket = socket.socket()
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # A fixed port lets users allow Shardwise through a firewall once.
        try: self.socket.bind(('0.0.0.0', preferred_port))
        except OSError: self.socket.bind(('0.0.0.0', 0))
        self.socket.listen()
        self.socket.settimeout(.5)
        self.port = self.socket.getsockname()[1]
        self.target_port = target_port
        self.delay = 0
        self.closed = threading.Event()
        self.connections = set()
        self.lock = threading.Lock()
        threading.Thread(target=self.accept,daemon=True).start()

    def accept(self):
        import socket
        while not self.closed.is_set():
            try: client, _ = self.socket.accept()
            except socket.timeout: continue
            except OSError: break
            try: upstream = socket.create_connection(('127.0.0.1', self.target_port), timeout=3)
            except OSError: client.close(); continue
            upstream.settimeout(None)
            with self.lock: self.connections.update((client,upstream))
            def pump(src, dst, delayed):
                try:
                    while not self.closed.is_set():
                        data=src.recv(65536)
                        if not data: break
                        if delayed and self.delay: self.closed.wait(self.delay)
                        dst.sendall(data)
                except OSError: pass
                finally:
                    for conn in (src,dst):
                        try: conn.shutdown(socket.SHUT_RDWR)
                        except OSError: pass
                        conn.close()
                        with self.lock: self.connections.discard(conn)
            threading.Thread(target=pump,args=(client,upstream,False),daemon=True).start()
            threading.Thread(target=pump,args=(upstream,client,True),daemon=True).start()

    def close(self):
        self.closed.set(); self.socket.close()
        with self.lock:
            for conn in list(self.connections):
                try: conn.shutdown(2)
                except OSError: pass
                conn.close()
