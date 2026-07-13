"""KubeEdgeInfer shard worker.

Serves a contiguous range of model layers. The controller re-assigns the
range at runtime via AssignLayers (hot, no restart); the router drives
inference through Forward. A single lock serializes compute, mimicking one
GPU, so busy-time stats are meaningful for bubble-time measurement.
"""

import logging
import os
import sys
import threading
import time
from concurrent import futures

import grpc

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "gen"))

import pipeline_pb2 as pb  # noqa: E402
import pipeline_pb2_grpc as rpc  # noqa: E402

from backends import make_backend  # noqa: E402

log = logging.getLogger("worker")


class WorkerServicer(rpc.WorkerServicer):
    def __init__(self):
        self.compute_lock = threading.Lock()
        self.state_lock = threading.Lock()
        self.backends = {}  # (backend_name, model) -> backend instance
        self.backend = None
        self.generation = -1
        self.start_layer = 0
        self.end_layer = 0
        self.total_layers = 0
        self.window_busy_ms = 0.0
        self.window_start = time.monotonic()
        self.forwards = 0

    def _apply_assignment(self, req):
        key = (req.backend, req.model)
        backend = self.backends.get(key)
        if backend is None:
            backend = make_backend(req.backend, req.model)
            self.backends[key] = backend
        backend.load(req.start_layer, req.end_layer, req.total_layers)
        self.backend = backend
        self.start_layer = req.start_layer
        self.end_layer = req.end_layer
        self.total_layers = req.total_layers
        self.generation = req.generation

    def AssignLayers(self, req, ctx):
        with self.state_lock:
            if req.generation < self.generation:
                # Accept anyway: a restarted controller resets its counter.
                log.warning(
                    "generation went backwards: %d -> %d (controller restart?)",
                    self.generation, req.generation,
                )
            try:
                self._apply_assignment(req)
            except Exception as e:  # surface load errors to the controller
                log.exception("AssignLayers failed")
                return pb.AssignLayersReply(ok=False, error=str(e))
        log.info(
            "assigned layers [%d, %d) of %d backend=%s gen=%d",
            req.start_layer, req.end_layer, req.total_layers,
            req.backend, req.generation,
        )
        return pb.AssignLayersReply(ok=True)

    def Forward(self, req, ctx):
        with self.state_lock:
            gen, backend = self.generation, self.backend
        if backend is None:
            return pb.ForwardReply(error="no layers assigned")
        if req.generation != gen:
            return pb.ForwardReply(
                error=f"generation mismatch: worker={gen} request={req.generation}"
            )
        with self.compute_lock:
            t0 = time.monotonic()
            try:
                reply = backend.forward(req)
            except Exception as e:
                log.exception("forward failed")
                return pb.ForwardReply(error=str(e))
            busy_ms = (time.monotonic() - t0) * 1000.0
        reply.compute_ms = busy_ms
        with self.state_lock:
            self.window_busy_ms += busy_ms
            self.forwards += 1
        return reply

    def Stats(self, req, ctx):
        now = time.monotonic()
        with self.state_lock:
            reply = pb.StatsReply(
                start_layer=self.start_layer,
                end_layer=self.end_layer,
                window_busy_ms=self.window_busy_ms,
                window_wall_ms=(now - self.window_start) * 1000.0,
                forwards=self.forwards,
                generation=self.generation,
            )
            self.window_busy_ms = 0.0
            self.window_start = now
        return reply


def bootstrap_from_env(servicer):
    """Optional self-assignment for running without a controller.

    INITIAL_ASSIGNMENT=<start>:<end>:<total>:<backend>[:<model>]
    """
    spec = os.environ.get("INITIAL_ASSIGNMENT", "")
    if not spec:
        return
    parts = spec.split(":")
    req = pb.AssignLayersRequest(
        start_layer=int(parts[0]),
        end_layer=int(parts[1]),
        total_layers=int(parts[2]),
        backend=parts[3],
        model=parts[4] if len(parts) > 4 else "gpt2",
        generation=0,
    )
    with servicer.state_lock:
        servicer._apply_assignment(req)
    log.info("bootstrapped from INITIAL_ASSIGNMENT=%s", spec)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    port = int(os.environ.get("PORT", "50051"))
    servicer = WorkerServicer()
    bootstrap_from_env(servicer)
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=16),
        options=[
            ("grpc.max_send_message_length", 64 * 1024 * 1024),
            ("grpc.max_receive_message_length", 64 * 1024 * 1024),
        ],
    )
    rpc.add_WorkerServicer_to_server(servicer, server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    log.info("worker %s listening on :%d", os.environ.get("WORKER_NAME", "?"), port)
    server.wait_for_termination()


if __name__ == "__main__":
    main()
