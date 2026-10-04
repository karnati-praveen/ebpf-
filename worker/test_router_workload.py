import unittest
from unittest.mock import patch
import router


class RouterWorkloadTests(unittest.TestCase):
    def test_replay_preserves_remaining_output_budget(self):
        observations = []
        def forward(*args):
            observations.append(router.WORKLOAD.snapshot()["remaining_tokens"])
            if len(observations) == 2:
                raise router.GenerationChanged("test transition")
            return router.pb.ForwardReply(next_token=42, is_last=True)
        with patch.object(router.STATE, "wait_for_pipeline", return_value=([], 1)), patch.object(router, "_forward_chain", side_effect=forward), patch.object(router.time, "sleep"):
            result = router.generate([1, 2], 3)
        self.assertEqual(result["tokens"], [42, 42, 42])
        self.assertEqual(observations, [3, 2, 2, 1])
        self.assertEqual(router.WORKLOAD.snapshot()["active_requests"], 0)

    def test_failure_releases_output_budget(self):
        with patch.object(router.STATE, "wait_for_pipeline", side_effect=RuntimeError("unavailable")):
            with self.assertRaises(RuntimeError):
                router.generate([1], 3)
        self.assertEqual(router.WORKLOAD.snapshot()["remaining_tokens"], 0)


if __name__ == "__main__":
    unittest.main()
