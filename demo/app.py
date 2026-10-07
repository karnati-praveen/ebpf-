#!/usr/bin/env python3
"""An independent, unprivileged Linux desktop demo using the real control loop."""

import argparse
import fcntl
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
import webbrowser
from http.server import ThreadingHTTPServer

import serve

ROOT = Path(__file__).resolve().parent.parent
NAMES = ("demo-worker-1", "demo-worker-2", "demo-worker-3")


def read_json(url, timeout=3):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)


def available_base(first):
    """Choose an unused block, leaving research deployments on their own ports."""
    for base in range(first, min(first + 1000, 65510), 30):
        sockets = []
        try:
            for offset in (0, 1, 2, 3, 4, 10, 11, 12, 20, 21, 22):
                sock = socket.socket()
                sockets.append(sock)
                sock.bind(("127.0.0.1", base + offset))
            return base
        except OSError:
            continue
        finally:
            for sock in sockets:
                sock.close()
    raise RuntimeError("No free demo ports. Stop another demo and try again.")


class Runtime:
    def __init__(self, state_dir, bin_dir, base):
        self.state_dir = state_dir
        self.bin_dir = bin_dir
        self.base = base
        self.processes = {}
        self.lock = threading.RLock()
        self.token = secrets.token_urlsafe(32)
        self.url = f"http://127.0.0.1:{base + 4}"
        self.stopping = threading.Event()
        self.server = None
        self.started = time.time()
        serve.ROUTER = f"http://127.0.0.1:{base}"
        serve.CTRL = f"http://127.0.0.1:{base + 1}"
        serve.NODE_AGENTS = {
            name: f"http://127.0.0.1:{base + 20 + i}"
            for i, name in enumerate(NAMES)
        }

    def launch(self, name, command, extra=None):
        env = os.environ.copy()
        # Do not inherit research settings into the reproducible desktop demo.
        for key in ("INITIAL_ASSIGNMENT", "STATIC_PIPELINE", "PROFILE_ONCE",
                    "STATIC_MODE", "WORKLOAD_URL", "REMAINING_WORK_AWARE"):
            env.pop(key, None)
        env.update(PYTHONUNBUFFERED="1", KV_CACHE="0", WORKER_DEVICE="cpu",
                   GRPC_HOST="127.0.0.1", HTTP_HOST="127.0.0.1",
                   CONTROLLER_ADDR=f"127.0.0.1:{self.base + 3}")
        env.update(extra or {})
        with (self.state_dir / f"{name}.log").open("ab") as log:
            self.processes[name] = subprocess.Popen(
                command, cwd=ROOT / "worker", env=env,
                stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                start_new_session=True,
            )

    def stop_process(self, name):
        process = self.processes.pop(name, None)
        if process is None:
            return
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=3)

    def worker_on(self, name):
        return all(key in self.processes and self.processes[key].poll() is None
                   for key in (name, name + "-agent"))

    def set_worker(self, name, on):
        with self.lock:
            if name not in NAMES:
                raise ValueError("Unknown demo worker.")
            if not on and self.worker_on(name) and sum(map(self.worker_on, NAMES)) <= 1:
                raise ValueError("Keep at least one worker running for recovery.")
            if on and self.worker_on(name):
                return
            self.stop_process(name + "-agent")
            self.stop_process(name)
            if not on:
                return
            i = NAMES.index(name)
            worker_port, agent_port = self.base + 10 + i, self.base + 20 + i
            self.launch(name, [sys.executable, str(ROOT / "worker/server.py")], {
                "PORT": str(worker_port), "WORKER_NAME": name,
                "NODE_AGENT_ADDR": f"127.0.0.1:{agent_port}",
                "SIM_PER_LAYER_MS": "8", "SIM_HIDDEN_DIM": "128",
            })
            self.launch(name + "-agent", [str(self.bin_dir / "nodeagent")], {
                "NODE_NAME": name, "HTTP_ADDR": f"127.0.0.1:{agent_port}",
                "WORKER_ADDR": f"127.0.0.1:{worker_port}",
                "GPU_MODE": "sim", "EBPF": "off", "SIM_GPU_TAU_S": "5",
                "SIM_GPU_AMBIENT_C": "45", "SIM_GPU_K": "25",
                "SIM_GPU_THROTTLE_C": "80", "SIM_GPU_UNTHROTTLE_C": "75",
                "SIM_GPU_THROTTLE_SPEED": "0.4",
            })

    def start(self):
        config = self.state_dir / "pipeline.json"
        config.write_text(json.dumps({
            "model": "desktop-simulation", "backend": "sim", "totalLayers": 24,
            "perLayerMs": 8, "workers": 3,
            "routerAddr": f"127.0.0.1:{self.base + 2}",
        }))
        self.launch("router", [sys.executable, str(ROOT / "worker/router.py")], {
            "HTTP_PORT": str(self.base), "GRPC_PORT": str(self.base + 2),
        })
        self.launch("controller", [
            str(self.bin_dir / "controller"), "-mode=standalone", f"-config={config}",
            f"-grpc-addr=127.0.0.1:{self.base + 3}",
            f"-http-addr=127.0.0.1:{self.base + 1}",
            "-policy=hysteresis", "-objective=throughput", "-link-source=app",
            "-interval=1s", "-cooldown=5s", "-improvement=0.10",
            "-heartbeat-timeout=3s", "-reassert-interval=3s",
        ])
        for name in NAMES:
            self.set_worker(name, True)
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            self.check_processes()
            try:
                if len(read_json(serve.ROUTER + "/pipeline").get("stages", [])) == 3:
                    return
            except Exception:
                pass
            time.sleep(0.3)
        raise RuntimeError(f"The pipeline did not start. See logs in {self.state_dir}.")

    def check_processes(self):
        with self.lock:
            for name, process in self.processes.items():
                if process.poll() is not None:
                    raise RuntimeError(f"{name} stopped. See {self.state_dir / (name + '.log')}.")

    def status(self):
        with self.lock:
            return {
                "desktop": True, "token": self.token,
                "hostname": socket.gethostname(), "started": self.started,
                "logs": str(self.state_dir), "stopping": self.stopping.is_set(),
                "workers": [{"name": name, "on": self.worker_on(name)} for name in NAMES],
            }

    def request_stop(self):
        self.stopping.set()
        serve.load_on.clear()
        if self.server:
            self.server.shutdown()

    def close(self):
        serve.load_on.clear()
        with self.lock:
            for name in list(self.processes)[::-1]:
                self.stop_process(name)


def make_handler(runtime):
    class AppHandler(serve.Handler):
        def allowed_host(self):
            return self.headers.get("Host") in (
                f"127.0.0.1:{runtime.base + 4}", f"localhost:{runtime.base + 4}",
            )

        def do_GET(self):
            if not self.allowed_host():
                return self._json(403, {"error": "Open the local demo URL."})
            if self.path == "/api/demo":
                return self._json(200, runtime.status())
            return super().do_GET()

        def do_POST(self):
            if (not self.allowed_host() or
                    self.headers.get("X-Demo-Token") != runtime.token):
                return self._json(403, {"error": "Reload the demo before using controls."})
            if self.path == "/api/quit":
                self._json(200, {"ok": True})
                threading.Thread(target=runtime.request_stop, daemon=True).start()
                return
            if self.path == "/api/worker":
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 4096:
                        raise ValueError("Invalid request size.")
                    body = json.loads(self.rfile.read(length))
                    if not isinstance(body, dict) or type(body.get("on")) is not bool:
                        raise ValueError("Choose stop or restore.")
                    if runtime.stopping.is_set():
                        raise ValueError("The demo is closing.")
                    runtime.set_worker(body.get("node"), body["on"])
                    return self._json(200, runtime.status())
                except (ValueError, TypeError) as error:
                    return self._json(400, {"error": str(error)})
            return super().do_POST()

    return AppHandler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--base-port", type=int, default=19000)
    parser.add_argument("--bin-dir", type=Path, default=ROOT / "bin")
    parser.add_argument("--state-dir", type=Path, default=Path(
        os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))
    ) / "kubeedgeinfer-demo")
    args = parser.parse_args()
    if not 1024 <= args.base_port <= 64500:
        parser.error("--base-port must be between 1024 and 64500")
    for name in ("controller", "nodeagent"):
        if not os.access(args.bin_dir / name, os.X_OK):
            parser.error("Missing demo binaries. Run demo/install.sh first.")
    args.state_dir.mkdir(parents=True, exist_ok=True)
    lock = (args.state_dir / "app.lock").open("a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        try:
            url = (args.state_dir / "url").read_text().strip()
            print(f"Demo already running: {url}", flush=True)
            if not args.no_browser:
                webbrowser.open(url)
        except OSError:
            print("Demo is starting. Try again in a few seconds.", flush=True)
        return 0
    runtime = None
    try:
        base = available_base(args.base_port)
        runtime = Runtime(args.state_dir, args.bin_dir.resolve(), base)
        print("Starting three local workers and the adaptive controller…", flush=True)
        runtime.start()
        httpd = ThreadingHTTPServer(("127.0.0.1", base + 4), make_handler(runtime))
        runtime.server = httpd
        (args.state_dir / "url").write_text(runtime.url)

        def stop(_signum, _frame):
            threading.Thread(target=runtime.request_stop, daemon=True).start()

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        for _ in range(serve.LOAD_THREADS):
            threading.Thread(target=serve._load_loop, daemon=True).start()
        print(f"KubeEdgeInfer Demo: {runtime.url}", flush=True)
        print(f"Logs: {args.state_dir}", flush=True)
        if not args.no_browser:
            webbrowser.open(runtime.url)
        httpd.serve_forever(poll_interval=0.3)
        httpd.server_close()
        return 0
    except Exception as error:
        print(f"Demo could not run: {error}", file=sys.stderr, flush=True)
        return 1
    finally:
        if runtime:
            runtime.close()
        (args.state_dir / "url").unlink(missing_ok=True)
        lock.close()


if __name__ == "__main__":
    sys.exit(main())
