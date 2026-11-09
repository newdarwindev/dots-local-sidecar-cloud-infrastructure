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


class NativeEventRenderTests(unittest.TestCase):
    def test_fixed_nonsecret_processors(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        self.assertEqual(SETUP.main('native-event-render', io.BytesIO(b'{}'), stdout, stderr), 0)
        config = json.loads(stdout.getvalue())
        self.assertEqual(set(config), {'edge_processors', 'central_processors'})
        self.assertIn('transform/events', config['edge_processors'])
        self.assertIn('transform/native-event-central', config['central_processors'])
        self.assertEqual(stderr.getvalue(), '')
        for value in ([], {'secret': 'PRIVATE_CANARY'}):
            stdout, stderr = io.StringIO(), io.StringIO()
            self.assertEqual(SETUP.main('native-event-render', io.BytesIO(json.dumps(value).encode()), stdout, stderr), 2)
            self.assertEqual(stdout.getvalue(), '')
            self.assertEqual(stderr.getvalue(), SETUP.ERROR)


class NativeLogDiagnosticRenderTests(unittest.TestCase):
    def test_generic_components_only(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        self.assertEqual(SETUP.main('native-log-diagnostic-render', io.BytesIO(b'{}'), stdout, stderr), 0)
        config = json.loads(stdout.getvalue())
        self.assertIn('filter/content_parser_guard', config['processors'])
        self.assertEqual(set(config['pipelines']), {'logs/native_diagnostic', 'traces/native_diagnostic'})
        self.assertNotIn('receivers', config)
        self.assertNotIn('exporters', config)
        self.assertNotIn('extensions', config)
        self.assertNotIn('enrolled', stdout.getvalue())
        self.assertEqual(stderr.getvalue(), '')
        for value in ([], {'secret': 'PRIVATE_CANARY'}, {'enrolled': {}, 'denied': []}):
            stdout, stderr = io.StringIO(), io.StringIO()
            self.assertEqual(SETUP.main('native-log-diagnostic-render', io.BytesIO(json.dumps(value).encode()), stdout, stderr), 2)
            self.assertEqual(stdout.getvalue(), '')
            self.assertEqual(stderr.getvalue(), SETUP.ERROR)
