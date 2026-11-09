"""Nonsecret rendering regressions; Docker entrypoint only."""
import importlib.util
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('conversation_review', ROOT / 'validation/setup.py')
SETUP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SETUP)
FRESH = '11111111-1111-4111-8111-111111111111'


class ConversationRenderTests(unittest.TestCase):
    def invoke(self, value):
        stdout, stderr = io.StringIO(), io.StringIO()
        result = SETUP.main('conversation-render', io.BytesIO(json.dumps(value).encode()), stdout, stderr)
        return result, stdout.getvalue(), stderr.getvalue()

    def test_exact_policy_output_and_no_ambient_credentials(self):
        value = {'enrolled': {FRESH: 2000000000}, 'denied': [FRESH], 'generations': True}
        with patch.dict(os.environ, {'CONVERSATION_UPSTREAM_AUTHORIZATION': 'PRIVATE_CANARY',
                                    'LANGFUSE_SECRET_KEY': 'PRIVATE_CANARY'}):
            code, stdout, stderr = self.invoke(value)
        self.assertEqual(code, 0)
        self.assertEqual(stderr, '')
        output = json.loads(stdout)
        self.assertEqual(output, SETUP.helper('conversation_setup').POLICY.render(
            value['enrolled'], value['denied'], generations=True))
        self.assertNotIn('PRIVATE_CANARY', stdout)
        self.assertEqual(output['exporters']['otlphttp/rich']['headers']['Authorization'],
                         '${env:CONVERSATION_UPSTREAM_AUTHORIZATION}')

    def test_empty_enrollment_is_default_deny(self):
        code, stdout, _ = self.invoke({'enrolled': {}, 'denied': [], 'generations': False})
        self.assertEqual(code, 0)
        expressions = json.loads(stdout)['processors']['filter/enrollment']['traces']['span']
        self.assertIn('not ContainsValue([], span.attributes["session.id"])', expressions)

    def test_rejects_extra_missing_and_malformed_fields_without_disclosure(self):
        valid = {'enrolled': {FRESH: 2000000000}, 'denied': [], 'generations': False}
        invalid = [[], None, {}, {**valid, 'credentials': 'PRIVATE_CANARY'},
                   {**valid, 'endpoint': 'PRIVATE_CANARY'}, {**valid, 'generations': 'true'},
                   {**valid, 'enrolled': {'*': 1}}, {**valid, 'enrolled': {FRESH: True}},
                   {**valid, 'enrolled': {FRESH: -1}}, {**valid, 'enrolled': {FRESH: 2**63}},
                   {**valid, 'enrolled': {FRESH: 2.5}}, {**valid, 'denied': ['PRIVATE_CANARY']},
                   {**valid, 'denied': {}}, {**valid, 'enrolled': []}]
        invalid += [{key: item for key, item in valid.items() if key != missing} for missing in valid]
        for value in invalid:
            with self.subTest(value=value):
                code, stdout, stderr = self.invoke(value)
                self.assertEqual(code, 2)
                self.assertEqual(stdout, '')
                self.assertEqual(stderr, SETUP.ERROR)

    def test_duplicate_fields_rejected_before_render(self):
        content = b'{"enrolled":{},"denied":[],"generations":false,"generations":true}'
        stdout, stderr = io.StringIO(), io.StringIO()
        self.assertEqual(SETUP.main('conversation-render', io.BytesIO(content), stdout, stderr), 2)
        self.assertEqual(stdout.getvalue(), '')
        self.assertEqual(stderr.getvalue(), SETUP.ERROR)


if __name__ == '__main__':
    unittest.main()
