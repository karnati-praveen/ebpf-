"""EOS stopping is additive and survives the normal generation accounting."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
import router

class EOS(unittest.TestCase):
    def setUp(self):
        self.pipeline=patch.object(router.STATE,'wait_for_pipeline',return_value=(['stage'],1));self.pipeline.start()
    def tearDown(self): self.pipeline.stop()
    def run_generation(self, stop):
        seq=iter((7,9,11,13))
        with patch.object(router,'_forward_chain',side_effect=lambda *args:SimpleNamespace(next_token=next(seq))):
            return router.generate([1],3,stop)['tokens']
    def test_default_keeps_generating(self): self.assertEqual(self.run_generation(None),[7,9,11])
    def test_stop_token_counted_then_halts(self): self.assertEqual(self.run_generation([9]),[7,9])
    def test_empty_stop_list_unchanged(self): self.assertEqual(self.run_generation([]),[7,9,11])
if __name__=='__main__': unittest.main()
