from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from multistage_publication import ThreeRuntime


class StartupTests(unittest.TestCase):
    def test_workers_load_one_at_a_time_and_empty_workers_are_skipped(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = ThreeRuntime('capacity-3x1t', [[0, 12], [12, 12], [12, 28]],
                                   'model', Path(temp), [0, 1, 2, 3], 55000)
            events = []
            with patch.object(runtime, 'spawn', side_effect=lambda name, *args: events.append(('spawn', name))), \
                 patch.object(runtime, 'wait_workers', side_effect=lambda indices: events.append(('ready', list(indices)))), \
                 patch('multistage_publication.post', return_value={}):
                runtime.start()
            self.assertEqual(events[:4], [('spawn', 'worker-0'), ('ready', [0]),
                                          ('spawn', 'worker-2'), ('ready', [2])])
            self.assertNotIn(('spawn', 'worker-1'), events)

    def test_worker_exit_reports_process_and_return_code(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = ThreeRuntime('replicas-3x1t', [[0, 28]] * 3,
                                   'model', Path(temp), [0, 1, 2, 3], 55000)
            class Exited:
                pid = 123
                def poll(self): return -9
            runtime.processes = [Exited()]
            runtime.process_names = ['worker-0']
            with self.assertRaisesRegex(RuntimeError, 'worker-0.*123.*-9'):
                runtime.wait_workers([0])


if __name__ == '__main__':
    unittest.main()
