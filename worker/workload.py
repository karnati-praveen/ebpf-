"""Live admitted output budget, independent of inference and telemetry timers."""
import threading
import time


class WorkloadTracker:
    def __init__(self):
        self._lock = threading.Lock()
        self._requests = {}

    def begin(self, key, tokens, prompt_tokens=0):
        if tokens <= 0:
            raise ValueError("max_new_tokens must be positive")
        if prompt_tokens < 0:
            raise ValueError("prompt_tokens must be nonnegative")
        with self._lock:
            self._requests[key] = [tokens, prompt_tokens]

    def produced(self, key):
        with self._lock:
            request = self._requests[key]
            if request[0] > 0:
                request[0] -= 1
                request[1] += 1

    def finish(self, key, callback=None):
        with self._lock:
            if callback is not None:
                callback()
            self._requests.pop(key, None)

    def with_active_keys(self, callback):
        with self._lock:
            return callback(list(self._requests))

    def active_keys(self):
        with self._lock:
            return list(self._requests)

    def snapshot(self):
        with self._lock:
            return {"active_requests": len(self._requests),
                    "remaining_tokens": sum(r[0] for r in self._requests.values()),
                    "replay_context_tokens": sum(r[1] for r in self._requests.values()),
                    "observed_at": time.time()}


WORKLOAD = WorkloadTracker()
