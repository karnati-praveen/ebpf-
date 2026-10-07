import json
from pathlib import Path
import tempfile
import unittest

from local_publication import load_checkpoint, write_completion


class CheckpointTests(unittest.TestCase):
    def test_keeps_completed_conditions_and_rejects_duplicates(self):
        schedule = [{"mode": "pipeline-2x1t", "repetition": 0, "conditions": [[32, 1], [32, 2]]}]
        row = {"mode": "pipeline-2x1t", "repetition": 0, "context": 32, "concurrency": 1}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"runs.jsonl"
            path.write_text(json.dumps(row)+"\n")
            self.assertEqual(load_checkpoint(path, schedule), {("pipeline-2x1t", 0, 32, 1)})
            path.write_text((json.dumps(row)+"\n")*2)
            with self.assertRaises(ValueError):
                load_checkpoint(path, schedule)

    def test_completion_requires_every_scheduled_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            write_completion(directory, 1, 2)
            self.assertFalse(json.loads((directory/"completion-status.json").read_text())["complete"])
            write_completion(directory, 2, 2)
            self.assertTrue(json.loads((directory/"completion-status.json").read_text())["complete"])


if __name__ == "__main__":
    unittest.main()
