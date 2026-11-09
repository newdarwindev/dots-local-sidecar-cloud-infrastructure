"""Exact native privacy keys; missing or incorrectly typed fields fail readiness."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'application-infrastructure'))
import native_log_diagnostic_policy as policy


class NativeLogReadinessTests(unittest.TestCase):
    def fixture(self):
        return {'log_user_prompt': False, 'log_agent_responses': False,
                'log_guardian_assessments': False, 'log_sse_deltas': False,
                'tool_result': {'max_bytes': 0}}

    def test_explicit_false_options(self):
        value = self.fixture()
        before = copy.deepcopy(value)
        self.assertTrue(policy.source_privacy_ready(value))
        self.assertEqual(value, before)

    def test_each_missing_wrong_or_enabled_flag(self):
        for flag in self.fixture():
            if flag == 'tool_result':
                continue
            for value in (None, True, 0, 'false', []):
                config = self.fixture()
                config[flag] = value
                self.assertFalse(policy.source_privacy_ready(config))
            config = self.fixture()
            del config[flag]
            self.assertFalse(policy.source_privacy_ready(config))
        config = self.fixture()
        del config['log_sse_deltas']
        config['log_sse_events'] = False
        self.assertFalse(policy.source_privacy_ready(config))
        config = self.fixture()
        del config['log_user_prompt']
        config['log_user_prompts'] = False
        self.assertFalse(policy.source_privacy_ready(config))

    def test_tool_limit_and_nonobjects(self):
        for value in (None, [], {}, {'max_bytes': False}, {'max_bytes': '0'}, {'max_bytes': 1}):
            config = self.fixture()
            config['tool_result'] = value
            self.assertFalse(policy.source_privacy_ready(config))
        for value in (None, [], {}, False):
            self.assertFalse(policy.source_privacy_ready(value))
