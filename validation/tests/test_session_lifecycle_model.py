"""Test-only lifecycle specification, NOT a service or durable-store implementation.

Freshness/ancestry below are trusted admission facts supplied by a hypothetical
owner-reviewed lifecycle source, never assertions accepted from telemetry.
Atomic publication is modeled; real filesystem, locking, fsync and rollback
resistance remain unimplemented and unqualified.
"""
import copy
import unittest


def valid(state):
    if not isinstance(state, dict) or set(state) != {'revision', 'cutoff', 'sessions', 'denied'}:
        return False
    return (type(state['revision']) is int and state['revision'] >= 0
            and type(state['cutoff']) is int and state['cutoff'] > 0
            and isinstance(state['sessions'], dict) and isinstance(state['denied'], set)
            and all(isinstance(key, str) and isinstance(value, dict)
                    and set(value) == {'birth', 'parent'} and type(value['birth']) is int
                    and (value['parent'] is None or isinstance(value['parent'], str))
                    for key, value in state['sessions'].items()))


def allowed(state, session, start):
    if not valid(state) or type(start) is not int:
        return False
    seen = set()
    current = session
    while current is not None:
        if current in seen or current in state['denied'] or current not in state['sessions']:
            return False
        seen.add(current)
        record = state['sessions'][current]
        if record['birth'] < state['cutoff'] or start < record['birth']:
            return False
        current = record['parent']
    return bool(seen)


class AtomicPublicationModel:
    """Ideal CAS primitive only; no claim Python assignment is durable storage."""
    def __init__(self):
        self.state = {'revision': 0, 'cutoff': 100, 'sessions': {}, 'denied': set()}

    def commit(self, expected, candidate):
        if (not valid(self.state) or not valid(candidate)
                or self.state['revision'] != expected or candidate['revision'] != expected + 1
                or candidate['cutoff'] != self.state['cutoff']
                or not self.state['denied'].issubset(candidate['denied'])):
            raise ValueError('fail closed: invalid state, stale writer or lost tombstone')
        for key, record in self.state['sessions'].items():
            if candidate['sessions'].get(key) != record:
                raise ValueError('immutable admission facts changed')
        self.state = copy.deepcopy(candidate)

    def candidate(self):
        result = copy.deepcopy(self.state)
        result['revision'] += 1
        return result


class LifecycleSpecificationTests(unittest.TestCase):
    def setUp(self):
        self.store = AtomicPublicationModel()
        state = self.store.candidate()
        state['sessions']['fresh'] = {'birth': 101, 'parent': None}
        self.store.commit(0, state)

    def test_fresh_after_cutoff_old_unknown_and_backfill_blocked(self):
        self.assertTrue(allowed(self.store.state, 'fresh', 101))
        self.assertFalse(allowed(self.store.state, 'unknown', 200))
        self.assertFalse(allowed(self.store.state, 'fresh', 99))
        state = self.store.candidate()
        state['sessions']['old'] = {'birth': 99, 'parent': None}
        self.store.commit(1, state)
        self.assertFalse(allowed(self.store.state, 'old', 200))

    def test_optout_tombstone_permanent_and_child_inherits(self):
        state = self.store.candidate()
        state['sessions']['child'] = {'birth': 102, 'parent': 'fresh'}
        state['denied'].add('fresh')
        self.store.commit(1, state)
        for session in ('fresh', 'child'):
            self.assertFalse(allowed(self.store.state, session, 300))
        for _ in range(3):
            candidate = self.store.candidate()
            candidate['denied'].clear()
            with self.assertRaises(ValueError):
                self.store.commit(2, candidate)
        self.assertFalse(allowed(self.store.state, 'fresh', 999))

    def test_missing_corrupt_unknown_parent_and_cycle_fail_closed(self):
        for state in (None, {}, {'revision': 0}, 'corrupt', self.store.state | {'revision': True}):
            self.assertFalse(allowed(state, 'fresh', 200))
        for parent in ('missing', 'child'):
            state = self.store.candidate()
            state['sessions']['child'] = {'birth': 102, 'parent': parent}
            self.assertFalse(allowed(state, 'child', 200))

    def test_stale_concurrent_writer_cannot_erase_optout(self):
        stale = self.store.candidate()
        optout = self.store.candidate()
        optout['denied'].add('fresh')
        self.store.commit(1, optout)
        with self.assertRaises(ValueError):
            self.store.commit(1, stale)
        self.assertFalse(allowed(self.store.state, 'fresh', 200))

    def test_crash_before_publication_keeps_old_snapshot(self):
        before = copy.deepcopy(self.store.state)
        candidate = self.store.candidate()
        candidate['sessions']['new'] = {'birth': 102, 'parent': None}
        # Candidate construction interrupted: no successful atomic publication.
        self.assertEqual(self.store.state, before)
        self.assertFalse(allowed(self.store.state, 'new', 200))
        self.store.commit(1, candidate)
        # Restart modeled from complete committed snapshot, not an actual disk.
        restarted = copy.deepcopy(self.store.state)
        self.assertTrue(allowed(restarted, 'new', 200))
        self.assertFalse(allowed({'revision': 2}, 'new', 200))


if __name__ == '__main__':
    unittest.main()
