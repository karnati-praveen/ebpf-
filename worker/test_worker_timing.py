from concurrent.futures import ThreadPoolExecutor
import threading
import unittest

import server


class WorkerTimingTests(unittest.TestCase):
    def test_queue_wait_is_measured_separately_from_execution(self):
        worker = server.WorkerServicer()
        worker.generation = 1
        entered = threading.Event()
        release = threading.Event()
        class Backend:
            def forward(self, request):
                if request.request_id == 1:
                    entered.set()
                    release.wait(timeout=2)
                return server.pb.ForwardReply(next_token=42, is_last=True)
        worker.backend = Backend()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(worker.Forward, server.pb.ForwardRequest(request_id=1, generation=1), None)
            self.assertTrue(entered.wait(timeout=2))
            queued = threading.Event()
            def second():
                queued.set()
                return worker.Forward(server.pb.ForwardRequest(request_id=2, generation=1), None)
            later = pool.submit(second)
            self.assertTrue(queued.wait(timeout=2))
            # The measured interval starts before the lock acquisition. The
            # main thread can release immediately; no arbitrary test sleep.
            release.set()
            first_reply, second_reply = first.result(), later.result()
        self.assertGreaterEqual(second_reply.queue_ms, 0)
        self.assertGreater(first_reply.compute_ms, second_reply.compute_ms)
        self.assertEqual(second_reply.next_token, 42)


if __name__ == "__main__":
    unittest.main()
