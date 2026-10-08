import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from local_publication import model_revision


class ModelRevisionTests(unittest.TestCase):
    def test_local_snapshot_does_not_use_hub_id_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / 'snapshots' / 'verified-revision'
            directory.mkdir(parents=True)
            (directory / 'config.json').write_text('{}')
            lookup = Mock(side_effect=AssertionError('local path sent to Hub'))
            with patch.dict('sys.modules', huggingface_hub=SimpleNamespace(try_to_load_from_cache=lookup)):
                self.assertEqual(model_revision(str(directory)), 'verified-revision')
                lookup.assert_not_called()

    def test_arbitrary_local_directory_does_not_invent_revision(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / 'config.json').write_text('{}')
            self.assertIsNone(model_revision(temp))

    def test_hub_id_uses_cached_snapshot_and_handles_cache_miss(self):
        lookup = Mock(return_value='/cache/snapshots/revision/config.json')
        with patch.dict('sys.modules', huggingface_hub=SimpleNamespace(try_to_load_from_cache=lookup)):
            self.assertEqual(model_revision('Qwen/Qwen3-0.6B'), 'revision')
            lookup.assert_called_once_with('Qwen/Qwen3-0.6B', 'config.json')
            lookup.return_value = None
            self.assertIsNone(model_revision('Qwen/Qwen3-0.6B'))


if __name__ == '__main__':
    unittest.main()
