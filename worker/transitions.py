"""Migration-level accounting; request durations are not independent samples."""
import math
import threading
import time


class MigrationTracker:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.records = {}

    def begin(self, body, keys):
        identity = body['transition_id']
        prediction = float(body.get('predicted_ms', 0))
        if not isinstance(identity, str) or not identity or not math.isfinite(prediction) or prediction < 0:
            raise ValueError('invalid transition identity or prediction')
        if body['cause'] not in ('voluntary', 'recovery', 'initial'):
            raise ValueError('invalid transition cause')
        generation = int(body['generation'])
        with self.lock:
            if identity in self.records:
                old = self.records[identity]
                if (old['generation'], old['cause'], old['predicted_ms']) != (generation, body['cause'], prediction):
                    raise ValueError('conflicting transition identity')
                return self._public(old)
            pending = [r for r in self.records.values() if r['status'] == 'pending']
            if pending and body['cause'] == 'voluntary':
                raise ValueError('previous transition still pending')
            for previous in pending:
                previous.update(status='incomplete', error='superseded by recovery or initial assignment', calibration_eligible=False)
            now = self.clock()
            row = dict(transition_id=identity, generation=generation, cause=body['cause'],
                       predicted_ms=prediction, started_at=time.time(), _start=now,
                       affected_requests=list(keys), _pending=set(keys), requests={},
                       status='pending', assignment_complete=False, calibration_eligible=False)
            self.records[identity] = row
            while len(self.records) > 128:
                del self.records[next(iter(self.records))]
            return self._public(row)

    def assignment(self, identity, success, error=''):
        with self.lock:
            row = self.records[identity]
            if row['assignment_complete']:
                return self._public(row)
            row.update(assignment_complete=True, assignment_ms=(self.clock()-row['_start'])*1000,
                       assignment_completed_at=time.time(), assignment_success=bool(success), error=error)
            if not success:
                row.update(status='failed', calibration_eligible=False)
            self._finalize(row)
            return self._public(row)

    def accepted(self, key, generation, replay_ms=0, interruption_ms=0):
        with self.lock:
            for row in self.records.values():
                if row['status'] == 'pending' and key in row['_pending'] and generation == row['generation']:
                    row['_pending'].remove(key)
                    row['requests'][key] = dict(outcome='resumed', resumed_ms=(self.clock()-row['_start'])*1000,
                                                replay_ms=replay_ms, interruption_ms=interruption_ms)
                    self._finalize(row)

    def finished(self, key, success):
        with self.lock:
            for row in self.records.values():
                if row['status'] == 'pending' and key in row['_pending']:
                    row['_pending'].remove(key)
                    row['requests'][key] = dict(outcome='completed' if success else 'failed',
                                                resumed_ms=(self.clock()-row['_start'])*1000,
                                                replay_ms=0, interruption_ms=0)
                    self._finalize(row)

    def _finalize(self, row):
        if row['status'] != 'pending' or not row['assignment_complete'] or row['_pending']:
            return
        requests = list(row['requests'].values())
        duration = max([row['assignment_ms']] + [r['resumed_ms'] for r in requests])
        row.update(status='complete', observed_at=time.time(), duration_ms=duration,
                   replay_ms=sum(r['replay_ms'] for r in requests),
                   maximum_request_interruption_ms=max([0]+[r['interruption_ms'] for r in requests]))
        eligible = (row['cause'] == 'voluntary' and row['predicted_ms'] > 0 and
                    any(r['replay_ms'] > 0 for r in requests) and
                    all(r['outcome'] != 'failed' for r in requests))
        row['calibration_eligible'] = eligible
        if eligible:
            row['observed_to_predicted_ratio'] = duration / row['predicted_ms']

    @staticmethod
    def _public(row):
        return {k: v for k, v in row.items() if not k.startswith('_')}

    def snapshot(self):
        with self.lock:
            for row in self.records.values():
                if row['status'] == 'pending' and self.clock()-row['_start'] > 1800:
                    row.update(status='incomplete', error='transition timeout', calibration_eligible=False)
            # Copy nested structures as well: HTTP serialization runs unlocked.
            import copy
            return copy.deepcopy([self._public(r) for r in self.records.values()])

    def request_identity(self, key, generation):
        with self.lock:
            for row in reversed(list(self.records.values())):
                if key in row['affected_requests'] and generation == row['generation']:
                    return row['transition_id']
        return None
