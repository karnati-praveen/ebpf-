import json
from pathlib import Path
import tempfile
import unittest
from calibrated_campaign import schedule, checkpoint, completion
from export_calibration import export


class CampaignTests(unittest.TestCase):
    def test_deterministic_paired_schedule(self):
        config={'controller_conditions':[dict(context=128,tokens=64,concurrency=2,demand='continuing',scenario='network:120')]}
        first=schedule(config,'evaluation',10,42)
        self.assertEqual(first,schedule(config,'evaluation',10,42))
        self.assertEqual(len(first),30)
        self.assertEqual(len({r['id'] for r in first}),30)
        for repetition in range(10):
            self.assertEqual({r['arm'] for r in first if r['repetition']==repetition},{'hysteresis','gate','gate-calibrated'})

    def test_checkpoint_and_interruption(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);path=directory/'runs.jsonl'
            path.write_text('{"id":"a"}\n')
            self.assertEqual(len(checkpoint(path,['a','b'])),1)
            completion(directory,1,2,stopped=True)
            self.assertFalse(json.loads((directory/'completion-status.json').read_text())['complete'])
            path.write_text('{"id":"a"}\n{"id":"a"}\n')
            with self.assertRaises(ValueError):checkpoint(path,['a'])
            path.write_text('{"id":"other"}\n')
            with self.assertRaises(ValueError):checkpoint(path,['a'])

    def test_export_requires_held_out_compatible_unique_successes(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);identity={'model':'m','source':'s','hardware':'h','runtime':'r'}
            manifest={'phase':'calibration','identity':identity}
            (directory/'manifest.json').write_text(json.dumps(manifest))
            rows=[dict(transition_id=str(i),cause='voluntary',status='complete',calibration_eligible=True,observed_to_predicted_ratio=2) for i in range(10)]
            rows+=rows[:1]+[dict(transition_id='loss',cause='recovery',status='complete',calibration_eligible=False)]
            (directory/'migrations.json').write_text(json.dumps(rows))
            self.assertEqual(len(export(identity,[directory])['observations']),10)
            manifest['phase']='evaluation';(directory/'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):export(identity,[directory])
            manifest['phase']='calibration';manifest['identity']['hardware']='other';(directory/'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):export(dict(identity,hardware='h'),[directory])


if __name__=='__main__':unittest.main()
