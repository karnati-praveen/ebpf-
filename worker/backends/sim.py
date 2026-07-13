"""Simulation backend: compute time scales with assigned layers and with the
node's (simulated) GPU speed factor, so thermal throttling injected at the
node agent visibly slows this stage and the control loop can react."""

import json
import os
import threading
import time
import urllib.request

import numpy as np
import pipeline_pb2 as pb

HIDDEN_DIM = int(os.environ.get("SIM_HIDDEN_DIM", "768"))
PER_LAYER_MS = float(os.environ.get("SIM_PER_LAYER_MS", "30"))
NODE_AGENT_ADDR = os.environ.get("NODE_AGENT_ADDR", "")  # host:port, optional


class SimBackend:
    def __init__(self):
        self.start = self.end = self.total = 0
        self._sf = 1.0
        self._sf_ts = 0.0
        self._sf_lock = threading.Lock()
        self._busy_s = 0.0  # compute time since the last agent query

    def load(self, start, end, total):
        self.start, self.end, self.total = start, end, total

    def _speed_factor(self):
        """Fetch the GPU speed factor, reporting our busy fraction so the
        agent's thermal model sees real load."""
        if not NODE_AGENT_ADDR:
            return 1.0
        now = time.monotonic()
        with self._sf_lock:
            if now - self._sf_ts < 0.5:
                return self._sf
            window = max(now - self._sf_ts, 1e-6)
            busy_frac = min(self._busy_s / window, 1.0)
            self._busy_s = 0.0
            self._sf_ts = now
        sf = self._sf
        try:
            url = f"http://{NODE_AGENT_ADDR}/gpu?busy_frac={busy_frac:.4f}"
            with urllib.request.urlopen(url, timeout=0.3) as r:
                sf = float(json.load(r).get("speed_factor", 1.0))
        except Exception:
            pass  # agent unreachable: keep last known factor
        with self._sf_lock:
            self._sf = sf
        return sf

    def forward(self, req):
        n_layers = self.end - self.start
        sf = max(self._speed_factor(), 0.05)
        sleep_s = n_layers * PER_LAYER_MS / 1000.0 / sf
        time.sleep(sleep_s)
        with self._sf_lock:
            self._busy_s += sleep_s

        if self.end >= self.total:  # last stage emits a (fake) token
            return pb.ForwardReply(next_token=0, is_last=True)

        # Produce an activation tensor of realistic size for the next stage.
        if req.input_ids:  # first stage
            seq = len(req.input_ids)
        elif len(req.shape) >= 2:
            seq = req.shape[1]
        else:
            seq = 1
        hidden = np.zeros((1, seq, HIDDEN_DIM), dtype=np.float32)
        return pb.ForwardReply(hidden=hidden.tobytes(), shape=list(hidden.shape))
