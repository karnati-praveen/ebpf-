import unittest
from transitions import MigrationTracker


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.tracker = MigrationTracker(lambda: self.now)
        self.body = dict(transition_id='epoch:generation:2', generation=2, cause='voluntary', predicted_ms=100)

    def test_overlap_is_one_observation_and_assignment_is_included(self):
        self.tracker.begin(self.body, ['a', 'b'])
        self.now = .1
        self.tracker.assignment(self.body['transition_id'], True)
        self.now = .2
        self.tracker.accepted('a', 2, 20, 50)
        self.assertEqual(self.tracker.snapshot()[0]['status'], 'pending')
        self.now = .3
        self.tracker.accepted('b', 2, 30, 70)
        row = self.tracker.snapshot()[0]
        self.assertTrue(row['calibration_eligible'])
        self.assertEqual(row['duration_ms'], 300)
        self.assertEqual(row['observed_to_predicted_ratio'], 3)
        self.assertEqual(row['replay_ms'], 50)
        self.tracker.accepted('b', 2, 300, 700)
        self.tracker.begin(self.body, ['other'])
        self.assertEqual(len(self.tracker.snapshot()), 1)
        self.assertEqual(self.tracker.snapshot()[0]['duration_ms'], 300)

    def test_recovery_supersedes_pending_and_is_not_calibration(self):
        self.tracker.begin(self.body, ['a'])
        recovery = dict(self.body, transition_id='epoch:generation:3', generation=3, cause='recovery')
        self.tracker.begin(recovery, ['a'])
        self.tracker.assignment(recovery['transition_id'], True)
        self.tracker.accepted('a', 3, 20, 50)
        rows = self.tracker.snapshot()
        self.assertEqual(rows[0]['status'], 'incomplete')
        self.assertFalse(rows[1]['calibration_eligible'])

    def test_failed_assignment_or_request_excluded(self):
        for assignment_success in (True, False):
            tracker = MigrationTracker(lambda: 0)
            tracker.begin(self.body, ['a'])
            tracker.assignment(self.body['transition_id'], assignment_success)
            tracker.finished('a', False)
            self.assertFalse(tracker.snapshot()[0]['calibration_eligible'])

    def test_timeout_no_replay_duplicate_conflict_and_wrong_generation(self):
        self.tracker.begin(self.body, ['a'])
        self.tracker.assignment(self.body['transition_id'], True)
        self.tracker.accepted('a', 1, 20, 50)
        self.assertEqual(self.tracker.snapshot()[0]['status'], 'pending')
        with self.assertRaises(ValueError):
            self.tracker.begin(dict(self.body, predicted_ms=200), ['a'])
        self.now = 1801
        self.assertEqual(self.tracker.snapshot()[0]['status'], 'incomplete')
        tracker = MigrationTracker(lambda: 0)
        tracker.begin(self.body, [])
        tracker.assignment(self.body['transition_id'], True)
        self.assertFalse(tracker.snapshot()[0]['calibration_eligible'])


if __name__ == '__main__':
    unittest.main()
