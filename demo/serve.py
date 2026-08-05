#!/usr/bin/env python3
"""Demo dashboard server.

Serves demo/dashboard.html and same-origin JSON proxies for the router and
controller (neither sets CORS headers, so the browser can't call them
directly), plus:

  POST /api/fault  {"node": "kubeedgeinfer-worker2", "temp_c": 92}
                   {"node": "...", "clear": true}
      -> forwards a GPU override to that kind node's node agent (port 9101);
         resolves the node's container IP via `docker inspect`.
  POST /api/load   {"on": true|false}
      -> toggles the built-in load generator (2 concurrent /generate loops
         through the router) so the dashboard has live traffic to show.

Expects the router on 127.0.0.1:18080 and the controller on 127.0.0.1:18081
(run-demo.sh sets up the port-forwards).
"""

import json
import os
import subprocess
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROUTER = "http://127.0.0.1:" + os.environ.get("ROUTER_PORT", "18080")
CTRL = "http://127.0.0.1:" + os.environ.get("CTRL_PORT", "18081")
DASH_PORT = int(os.environ.get("DASH_PORT", "8000"))
HERE = os.path.dirname(os.path.abspath(__file__))

LOAD_THREADS = 2
load_on = threading.Event()
load_on.set()  # traffic by default: an empty dashboard shows nothing


def _load_loop():
    while True:
        if not load_on.is_set():
            time.sleep(0.5)
            continue
        try:
            req = urllib.request.Request(
                ROUTER + "/generate",
                data=json.dumps({"prompt_len": 16, "max_new_tokens": 8}).encode(),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=120).read()
        except Exception:
            time.sleep(2)  # router not up yet / mid-repartition


def node_agent_addr(node):
    ip = subprocess.run(
        ["docker", "inspect", "-f",
         "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", node],
        capture_output=True, text=True, timeout=10,
    ).stdout.strip()
    if not ip:
        raise RuntimeError(f"could not resolve container IP for {node!r}")
    return f"http://{ip}:9101"


class Handler(BaseHTTPRequestHandler):
    def _json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _proxy(self, base, path):
        try:
            with urllib.request.urlopen(base + path, timeout=5) as r:
                body = r.read()
        except Exception as e:
            return self._json(502, {"error": str(e)})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path == "/dashboard.html":
            with open(os.path.join(HERE, "dashboard.html"), "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith("/api/router/"):
            self._proxy(ROUTER, "/" + self.path[len("/api/router/"):])
        elif self.path == "/api/ctrl/state":
            self._proxy(CTRL, "/state")
        elif self.path == "/api/load":
            self._json(200, {"on": load_on.is_set()})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json(400, {"error": "bad json"})
        if self.path == "/api/load":
            (load_on.set if body.get("on") else load_on.clear)()
            return self._json(200, {"on": load_on.is_set()})
        if self.path == "/api/fault":
            node = body.get("node", "")
            if not node.replace("-", "").replace("_", "").isalnum():
                return self._json(400, {"error": "bad node name"})
            payload = {"clear": True} if body.get("clear") else {"temp_c": body.get("temp_c", 92)}
            try:
                req = urllib.request.Request(
                    node_agent_addr(node) + "/gpu/override",
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=5) as r:
                    return self._json(200, json.load(r))
            except Exception as e:
                return self._json(502, {"error": str(e)})
        return self._json(404, {"error": "not found"})

    def handle_one_request(self):
        # A polling dashboard drops connections routinely (tab closed, page
        # reloaded mid-request); that is not an error worth a traceback.
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def log_message(self, fmt, *args):
        pass


def main():
    threading.Thread(target=_load_loop, daemon=True).start()
    for _ in range(LOAD_THREADS - 1):
        threading.Thread(target=_load_loop, daemon=True).start()
    httpd = ThreadingHTTPServer(("127.0.0.1", DASH_PORT), Handler)
    print(f"dashboard: http://localhost:{DASH_PORT}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
