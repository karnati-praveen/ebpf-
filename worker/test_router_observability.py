import types
import unittest
from unittest.mock import patch

import router
from workload import WorkloadTracker


class RouterObservabilityTests(unittest.TestCase):
    def test_replay_preserves_history_and_distinguishes_transition_scope(self):
        for changed in (True, False):
            with self.subTest(generation_changed=changed):
                generation = 2 if changed else 1
                tracker = WorkloadTracker()
                calls = []
                failed = False
                def forward(stages, gen, request_id, step, ids):
                    nonlocal failed
                    calls.append((gen, step, list(ids), tracker.snapshot()))
                    if step == 1 and not failed:
                        failed = True
                        raise router.GenerationChanged('generation mismatch' if changed else 'kv cache miss')
                    # Accepted history determines the token, including replay.
                    token = 11 if ids == [7, 8] else ids[-1]+1
                    return router.pb.ForwardReply(next_token=token)
                with patch.object(router, 'KV_CACHE', True), patch.object(router, 'WORKLOAD', tracker), \
                     patch.object(router.STATE, 'wait_for_pipeline', side_effect=[([object()],1),([object()],generation)]), \
                     patch.object(router, '_forward_chain', side_effect=forward), patch.object(router.time, 'sleep'):
                    result = router.generate([7,8], 3)
                self.assertEqual(result['tokens'], [11,12,13])
                self.assertEqual([c[2] for c in calls], [[7,8],[11],[7,8,11],[12]])
                event = result['transitions'][0]
                self.assertEqual(event['after_tokens'],1)
                self.assertEqual(event['context_tokens'],3)
                self.assertEqual(event['from_generation'],1)
                self.assertEqual(event['generation'],generation)
                self.assertEqual(event['scope'],'generation' if changed else 'request')
                self.assertIn(':generation:2' if changed else ':request:',event['transition_id'])
                self.assertEqual(len(result['token_times_ms']),3)
                self.assertEqual(result['token_times_ms'],sorted(result['token_times_ms']))
                self.assertEqual(calls[2][3]['replay_context_tokens'],3)
                self.assertEqual(tracker.snapshot()['active_requests'],0)
                self.assertIn(event,router.RECENT_TRANSITIONS)

    def test_residual_and_queue_corrected_transport_use_different_denominators(self):
        stage=types.SimpleNamespace(name='w0',addr='127.0.0.1:1')
        reply=router.pb.ForwardReply(next_token=44,compute_ms=3,queue_ms=4)
        stub=types.SimpleNamespace(Forward=lambda *args,**kwargs:reply)
        for mode,expected in [('residual',9),('queue-corrected',5)]:
            router.RPC_TIMING.stages={}
            with patch.object(router,'KV_CACHE',True), patch.object(router,'APP_LINK_MODE',mode), \
                 patch.object(router.STATE,'stub',return_value=stub), \
                 patch.object(router.time,'monotonic',side_effect=[0,.012,.012]), \
                 patch.object(router,'_record_transport') as record:
                self.assertEqual(router._forward_chain([stage],1,1,1,[7]).next_token,44)
            self.assertAlmostEqual(record.call_args.args[1],expected)
            timing=router.RPC_TIMING.stages['w0']
            self.assertAlmostEqual(timing['residual_ms'],9)
            self.assertAlmostEqual(timing['queue_ms'],4)
            self.assertAlmostEqual(timing['queue_corrected_ms'],5)


if __name__=='__main__':unittest.main()
