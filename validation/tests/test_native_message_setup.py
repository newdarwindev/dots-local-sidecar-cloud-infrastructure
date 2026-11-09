"""Bounded native render action, executed only by the committed Docker workflow."""
from test_conversation_setup import SETUP, FRESH
import io
import json
import unittest


class NativeRenderTests(unittest.TestCase):
    def invoke(self, value):
        stdout, stderr = io.StringIO(), io.StringIO()
        code = SETUP.main('native-message-render', io.BytesIO(json.dumps(value).encode()), stdout, stderr)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_strict_adapter_and_placeholders(self):
        value = {'enrolled': {FRESH: 2000000000}, 'denied': []}
        code, output, error = self.invoke(value)
        self.assertEqual((code, error), (0, ''))
        config = json.loads(output)
        self.assertEqual(config['receivers']['otlp/native_messages']['protocols']['http']['endpoint'], '127.0.0.1:17449')
        self.assertEqual(config['exporters']['otlphttp/rich']['tls']['min_version'], '1.3')
        self.assertNotIn('headers', config['exporters']['otlphttp/rich'])
        self.assertEqual(config['exporters']['otlphttp/rich']['sending_queue'], {'enabled': False})
        self.assertEqual(config['exporters']['otlphttp/rich']['retry_on_failure'], {'enabled': False})
        self.assertIn('${env:CONVERSATION_HTPASSWD_FILE}', output)
        for invalid in ({}, [], {**value, 'endpoint': 'PRIVATE_CANARY'}, {'enrolled': {'*': 1}, 'denied': []},
                        {'enrolled': {FRESH: True}, 'denied': []}, {'enrolled': {}, 'denied': ['PRIVATE_CANARY']}):
            self.assertEqual(self.invoke(invalid), (2, '', SETUP.ERROR))

    def test_default_deny(self):
        code, output, _ = self.invoke({'enrolled': {}, 'denied': []})
        self.assertEqual(code, 0)
        self.assertIn('not ContainsValue([], log.attributes[\\"conversation.id\\"])', output)
