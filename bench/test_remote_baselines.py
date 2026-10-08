import copy
import unittest
from remote_baselines import validate_hardware, REVISION


class PhysicalWorkerTests(unittest.TestCase):
    def setUp(self):
        host = dict(machine_id_sha256='machine-a', packages={'torch': 'test'},
                    serving_source_sha256={'worker/router.py': 'test'},
                    model_revision=REVISION, compute_cpus=[0, 1])
        self.hosts = [host, dict(copy.deepcopy(host), machine_id_sha256='machine-b')]

    def test_distinct_compatible_workers_pass(self):
        validate_hardware(self.hosts, 2)

    def test_same_machine_or_missing_identity_cannot_be_physical_evidence(self):
        for identity in ('machine-a', None, ''):
            with self.subTest(identity=identity):
                self.hosts[1]['machine_id_sha256'] = identity
                with self.assertRaisesRegex(ValueError, 'distinct physical'):
                    validate_hardware(self.hosts, 2)

    def test_duplicate_cpus_and_insufficient_unsplit_budget_rejected(self):
        for cpus in ([0, 0], [0], []):
            with self.subTest(cpus=cpus):
                self.hosts[0]['compute_cpus'] = cpus
                with self.assertRaises(ValueError):
                    validate_hardware(self.hosts, 2)

    def test_runtime_and_model_mismatch_rejected(self):
        for key in ('packages', 'serving_source_sha256', 'model_revision'):
            with self.subTest(key=key):
                hosts = copy.deepcopy(self.hosts)
                hosts[1][key] = 'different'
                with self.assertRaisesRegex(ValueError, 'mismatch'):
                    validate_hardware(hosts, 2)


if __name__ == '__main__':
    unittest.main()
