"""KubeEdgeInfer router.

Front door of the pipeline: accepts generation requests over HTTP, drives the
stage chain over gRPC, and streams telemetry-friendly timing back. The
controller re-orders the chain at runtime via the Router.SetPipeline gRPC; a
generation counter keeps in-flight requests consistent — on a mid-request
repartition, the router re-prefills the accumulated context on the new chain.

HTTP API (default :8080):
  POST /generate  {"input_ids": [..]} or {"prompt_len": N}, "max_new_tokens": M
  GET  /stats     per-stage window busy/wall (bubble-time source)
  GET  /pipeline  current stage layout
  GET  /metrics   cumulative counters
"""

import json
import logging
import os
import random
import sys
import threading
import time
from concurrent import futures
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import grpc

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "gen"))

import pipeline_pb2 as pb  # noqa: E402
import pipeline_pb2_grpc as rpc  # noqa: E402

log = logging.getLogger("router")

GRPC_OPTS = [
    ("grpc.max_send_message_length", 64 * 1024 * 1024),
    ("grpc.max_receive_message_length", 64 * 1024 * 1024),
]


class PipelineState:
    def __init__(self):
        self.lock = threading.Lock()
        self.stages = []  # list of pb.StageRef, pipeline order
        self.generation = -1
        self._layout = ""  # last logged layout, to quiet periodic re-pushes
        self.changed = threading.Condition(self.lock)
        self._channels = {}

    def set(self, stages, generation):
        layout = " -> ".join(
            f"{s.name}[{s.start_layer},{s.end_layer})" for s in stages
        )
        with self.lock:
            if generation < self.generation:
                log.warning("generation went backwards: %d -> %d (controller restart?)",
                            self.generation, generation)
            # The controller re-pushes the current layout periodically so a
            # restarted router recovers; only log when something changed.
            changed = generation != self.generation or layout != self._layout
            self.stages = list(stages)
            self.generation = generation
            self._layout = layout
            self.changed.notify_all()
        if changed:
            log.info("pipeline gen=%d: %s", generation, layout)
        return True

    def snapshot(self):
        with self.lock:
            return list(self.stages), self.generation

    def wait_for_pipeline(self, timeout=30.0):
        deadline = time.monotonic() + timeout
        with self.lock:
            while not self.stages:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError("no pipeline configured")
                self.changed.wait(remaining)
            return list(self.stages), self.generation

    def stub(self, addr):
        with self.lock:
            ch = self._channels.get(addr)
            if ch is None:
                ch = grpc.insecure_channel(addr, options=GRPC_OPTS)
                self._channels[addr] = ch
        return rpc.WorkerStub(ch)


STATE = PipelineState()

METRICS = {
    "requests": 0,
    "tokens": 0,
    "ttft_ms_sum": 0.0,
    "duration_ms_sum": 0.0,
    "repartition_replays": 0,
    "errors": 0,
}
METRICS_LOCK = threading.Lock()


class GenerationChanged(Exception):
    pass


def _forward_chain(stages, generation, request_id, step, first_stage_ids):
    """Run one token step through all stages; returns last stage's reply."""
    hidden = b""
    shape = []
    reply = None
    for i, stage in enumerate(stages):
        req = pb.ForwardRequest(
            request_id=request_id, step=step, generation=generation
        )
        if i == 0:
            req.input_ids.extend(first_stage_ids)
        else:
            req.hidden = hidden
            req.shape.extend(shape)
        try:
            reply = STATE.stub(stage.addr).Forward(req, timeout=120)
        except grpc.RpcError as e:
            raise GenerationChanged(f"stage {stage.name} unreachable: {e.code()}")
        if reply.error:
            if "generation mismatch" in reply.error:
                raise GenerationChanged(reply.error)
            raise RuntimeError(f"stage {stage.name}: {reply.error}")
        hidden, shape = reply.hidden, list(reply.shape)
    return reply


def generate(input_ids, max_new_tokens):
    request_id = random.getrandbits(63)
    t_start = time.monotonic()
    ttft_ms = None
    out_tokens = []
    replays = 0

    stages, generation = STATE.wait_for_pipeline()
    step = 0

    while len(out_tokens) < max_new_tokens:
        # Workers are stateless: send the full accumulated context each step.
        # This keeps distributed output token-identical to single-process
        # greedy decoding and makes repartition recovery trivial.
        first_ids = list(input_ids) + out_tokens
        try:
            reply = _forward_chain(stages, generation, request_id, step, first_ids)
        except GenerationChanged as e:
            # The pipeline was repartitioned (or a stage died) mid-request.
            # Refresh the layout and replay the full accumulated context.
            # Healing needs heartbeat timeout + reconcile + apply (~5-7s),
            # so give the controller room before declaring the run dead.
            replays += 1
            if replays > 40:
                raise RuntimeError(f"too many pipeline changes: {e}")
            time.sleep(0.5)
            new_stages, new_generation = STATE.wait_for_pipeline()
            if new_generation == generation and replays > 24:
                raise RuntimeError(f"pipeline stuck: {e}")
            stages, generation = new_stages, new_generation
            step = 0
            request_id = random.getrandbits(63)
            continue
        out_tokens.append(reply.next_token)
        if ttft_ms is None:
            ttft_ms = (time.monotonic() - t_start) * 1000.0
        step += 1

    duration_ms = (time.monotonic() - t_start) * 1000.0
    with METRICS_LOCK:
        METRICS["requests"] += 1
        METRICS["tokens"] += len(out_tokens)
        METRICS["ttft_ms_sum"] += ttft_ms
        METRICS["duration_ms_sum"] += duration_ms
        METRICS["repartition_replays"] += replays
    return {
        "tokens": out_tokens,
        "ttft_ms": round(ttft_ms, 2),
        "duration_ms": round(duration_ms, 2),
        "tokens_per_sec": round(len(out_tokens) / (duration_ms / 1000.0), 3),
        "replays": replays,
        "generation": generation,
    }


def collect_stats():
    stages, generation = STATE.snapshot()
    out = {"generation": generation, "stages": []}
    for s in stages:
        entry = {
            "name": s.name,
            "addr": s.addr,
            "layers": [s.start_layer, s.end_layer],
        }
        try:
            st = STATE.stub(s.addr).Stats(pb.StatsRequest(), timeout=2)
            busy, wall = st.window_busy_ms, st.window_wall_ms
            entry.update(
                window_busy_ms=round(busy, 2),
                window_wall_ms=round(wall, 2),
                idle_fraction=round(1.0 - busy / wall, 4) if wall > 0 else None,
                forwards=st.forwards,
                worker_generation=st.generation,
            )
        except grpc.RpcError as e:
            entry["error"] = str(e.code())
        out["stages"].append(entry)
    return out


class RouterServicer(rpc.RouterServicer):
    def SetPipeline(self, req, ctx):
        if STATE.set(req.stages, req.generation):
            return pb.Ack(ok=True)
        return pb.Ack(ok=False, error="stale generation")


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/stats":
            self._send(200, collect_stats())
        elif self.path == "/pipeline":
            stages, generation = STATE.snapshot()
            self._send(200, {
                "generation": generation,
                "stages": [
                    {"name": s.name, "addr": s.addr,
                     "layers": [s.start_layer, s.end_layer]}
                    for s in stages
                ],
            })
        elif self.path == "/metrics":
            with METRICS_LOCK:
                m = dict(METRICS)
            if m["requests"]:
                m["avg_ttft_ms"] = round(m["ttft_ms_sum"] / m["requests"], 2)
                m["avg_duration_ms"] = round(m["duration_ms_sum"] / m["requests"], 2)
            self._send(200, m)
        elif self.path == "/healthz":
            self._send(200, {"ok": True})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/generate":
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            input_ids = body.get("input_ids")
            if not input_ids:
                prompt_len = int(body.get("prompt_len", 16))
                input_ids = [random.randint(1, 1000) for _ in range(prompt_len)]
            max_new_tokens = int(body.get("max_new_tokens", 16))
            self._send(200, generate(input_ids, max_new_tokens))
        except Exception as e:
            log.exception("generate failed")
            with METRICS_LOCK:
                METRICS["errors"] += 1
            self._send(500, {"error": str(e)})

    def log_message(self, fmt, *args):  # quiet access log
        pass


def bootstrap_from_env():
    """STATIC_PIPELINE=name=addr=start=end,name=addr=start=end,..."""
    spec = os.environ.get("STATIC_PIPELINE", "")
    if not spec:
        return
    stages = []
    for part in spec.split(","):
        name, addr, start, end = part.split("=")
        stages.append(pb.StageRef(
            name=name, addr=addr, start_layer=int(start), end_layer=int(end)
        ))
    STATE.set(stages, 0)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    bootstrap_from_env()

    grpc_port = int(os.environ.get("GRPC_PORT", "50052"))
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    rpc.add_RouterServicer_to_server(RouterServicer(), server)
    server.add_insecure_port(f"[::]:{grpc_port}")
    server.start()

    http_port = int(os.environ.get("HTTP_PORT", "8080"))
    httpd = ThreadingHTTPServer(("", http_port), Handler)
    log.info("router: http :%d grpc :%d", http_port, grpc_port)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
