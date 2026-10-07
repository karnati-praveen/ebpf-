import json
from pathlib import Path
import tempfile
import unittest

from publication_analyze import analyze, bootstrap


class AnalysisTests(unittest.TestCase):
    def test_failed_request_is_retained_and_run_is_the_unit(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            schedule, runs = [], []
            for repeat in range(3):
                for mode in ("pipeline-2x1t", "replicas-2x1t"):
                    schedule.append({"repetition": repeat, "mode": mode, "conditions": [[32, 2]]})
                    runs.append({"mode": mode, "repetition": repeat, "context": 32, "concurrency": 2,
                        "whole_run_tps": 4 if mode.startswith("pipeline") else 5,
                        "failures": 1, "median_client_duration_ms": 100,
                        "median_ttft_ms": None, "requests": [{"ok": False, "error": "failed"}]})
            (directory/"manifest.json").write_text(json.dumps({"schedule": schedule, "evidence_type": "test fixture"}))
            (directory/"reference.json").write_text("{}")
            (directory/"runs.jsonl").write_text("\n".join(map(json.dumps, runs)))
            report = analyze(directory)
            self.assertEqual(report["failures"], 6)
            self.assertEqual(report["contrasts"][0]["paired_n"], 3)
            self.assertAlmostEqual(report["contrasts"][0]["paired_mean_tps_change_pct"], -20)
            self.assertEqual(report["missing_runs"], [])
            # Retaining a failure must not require successful TTFT samples.
            self.assertIsNone(report["summaries"][0]["median_run_ttft_ms"])

    def test_one_repeat_does_not_produce_interval(self):
        self.assertEqual(bootstrap([1]), [None, None])


if __name__ == "__main__":
    unittest.main()
