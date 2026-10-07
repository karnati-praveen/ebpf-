import concurrent.futures
import unittest
from workload import WorkloadTracker


class WorkloadTests(unittest.TestCase):
    def test_replay_context_tracks_all_active_histories(self):
        tracker = WorkloadTracker()
        tracker.begin("a", 3, 64)
        tracker.begin("b", 5, 128)
        tracker.produced("a")
        self.assertEqual(tracker.snapshot()["replay_context_tokens"], 193)
        tracker.finish("b")
        self.assertEqual(tracker.snapshot()["replay_context_tokens"], 65)
        tracker.finish("a")
        self.assertEqual(tracker.snapshot()["replay_context_tokens"], 0)

    def test_progress_and_cleanup(self):
        tracker = WorkloadTracker()
        tracker.begin("a", 3)
        tracker.begin("b", 5)
        tracker.produced("a")
        self.assertEqual(tracker.snapshot()["remaining_tokens"], 7)
        tracker.finish("a")
        self.assertEqual(tracker.snapshot()["remaining_tokens"], 5)
        tracker.finish("b")
        self.assertEqual(tracker.snapshot()["active_requests"], 0)

    def test_concurrent_progress(self):
        tracker = WorkloadTracker()
        for i in range(20):
            tracker.begin(i, 10)
        def work(i):
            for _ in range(10):
                tracker.produced(i)
            tracker.finish(i)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(work, range(20)))
        self.assertEqual(tracker.snapshot()["remaining_tokens"], 0)
        self.assertEqual(tracker.snapshot()["active_requests"], 0)


if __name__ == "__main__":
    unittest.main()
