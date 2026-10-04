"""Live admitted output budget, independent of inference and telemetry timers."""
import threading
import time


class WorkloadTracker:
    def __init__(self):
        self._lock = threading.Lock()
        self._requests = {}

    def begin(self, key, tokens):
        if tokens <= 0:
            raise ValueError("max_new_tokens must be positive")
        with self._lock:
            self._requests[key] = tokens

    def produced(self, key):
        with self._lock:
            self._requests[key] = max(0, self._requests[key] - 1)

    def finish(self, key):
        with self._lock:
            self._requests.pop(key, None)

    def snapshot(self):
        with self._lock:
            return {"active_requests": len(self._requests), "remaining_tokens": sum(self._requests.values()), "observed_at": time.time()}


WORKLOAD = WorkloadTracker()
