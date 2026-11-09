"""Synthetic-only native source gate structural regressions."""
import copy
import unittest

import native_source_policy as policy


class NativeSourcePolicyTests(unittest.TestCase):
    def fixture(self):
        return {'processors': {'filter/source': copy.deepcopy(policy.OLD_GATE),
                               'transform/privacy': {'unchanged': 'SYNTHETIC_CANARY'}},
                'service': {'pipelines': {'traces': {'processors': [
                    'memory_limiter', 'filter/source', 'filter/privacy', 'transform/privacy', 'batch']}}},
                'receivers': {'synthetic': {'endpoint': '127.0.0.1:1'}},
                'exporters': {'synthetic': {'headers': {'Authorization': 'SYNTHETIC_ONLY'}}}}

    def test_only_gate_changes_without_mutating_original(self):
        original = self.fixture()
        before = copy.deepcopy(original)
        result = policy.patch_config(original)
        self.assertEqual(original, before)
        self.assertEqual(result['processors']['filter/source'], policy.source_gate())
        result['processors']['filter/source'] = copy.deepcopy(policy.OLD_GATE)
        self.assertEqual(result, before)

    def test_idempotent(self):
        once = policy.patch_config(self.fixture())
        self.assertEqual(policy.patch_config(once), once)

    def test_unknown_gate_and_signal_fail_closed(self):
        for changed in ({}, {'error_mode': 'ignore'}, policy.source_gate() | {'extra': True}):
            config = self.fixture()
            config['processors']['filter/source'] = changed
            with self.assertRaises(ValueError):
                policy.patch_config(config)
        config = self.fixture()
        config['service']['pipelines']['logs'] = {}
        with self.assertRaises(ValueError):
            policy.patch_config(config)
        with self.assertRaises(ValueError):
            policy.patch_config({})


if __name__ == '__main__':
    unittest.main()
