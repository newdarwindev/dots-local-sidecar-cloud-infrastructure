"""Synthetic-only native logs to traces integration, upstream Collector in Docker."""
import importlib
from datetime import datetime, timezone
import json
import sys
from pathlib import Path
from unittest import mock
import unittest

from conversation_runtime import ConversationTests, FRESH, RECOVERY, UNKNOWN, CUTOFF, CANARY, attributes
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'application-infrastructure'))
POLICY = importlib.import_module('native_message_policy')


def fixture(event='codex.user_prompt', session=FRESH, timestamp=CUTOFF, **changes):
    attrs = {'event.name': event, 'conversation.id': session, 'app.version': '0.167.0',
             'event.timestamp': datetime.fromtimestamp(timestamp / 1e9, timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'),
             'prompt': 'Hello "quote" \\ slash\nUnicode: 雪 ' + CANARY,
             'response': 'Final answer ' + CANARY, 'agent.type': 'main', 'item.id': 'msg_' + 'a' * 48,
             'unknown': CANARY, 'user.email': CANARY}
    attrs.update(changes)
    attrs = {k: v for k, v in attrs.items() if v is not None}
    return {'resourceLogs': [{'resource': {'attributes': attributes({'service.name': 'codex_cli_rs', 'service.version': '0.167.0', 'secret': CANARY})},
                             'scopeLogs': [{'scope': {'name': 'codex_otel.log_only', 'attributes': attributes({'secret': CANARY})},
                                            'logRecords': [{'observedTimeUnixNano': str(timestamp), 'body': {'stringValue': CANARY},
                                                            'attributes': attributes(attrs) + [{'key': 'response_truncated', 'value': {'boolValue': False}}]}]}]}]}


class NativeMessageTests(ConversationTests):
    # Reuse transport harness, not the plugin tests.
    def collect(self, payload, **kwargs):
        import conversation_runtime as harness
        def rendered(*args, **ignored):
            config = POLICY.render({FRESH: CUTOFF, RECOVERY: CUTOFF}, [RECOVERY])
            config['receivers']['otlp/conversation'] = config['receivers'].pop('otlp/native_messages')
            config['extensions'] = {'basicauth/conversation': {}}
            config['service']['extensions'] = ['basicauth/conversation']
            config['receivers']['otlp/conversation']['protocols']['http']['auth'] = {'authenticator': 'basicauth/conversation'}
            config['service']['pipelines']['logs/native_messages']['receivers'] = ['otlp/conversation']
            config['service']['pipelines']['traces/conversation'] = config['service']['pipelines'].pop('traces/native_messages')
            # Harness configures this path then posts there; receiver treats it as logs.
            config['receivers']['otlp/conversation']['protocols']['http']['logs_url_path'] = '/api/public/otel/v1/traces'
            return config
        with mock.patch.object(harness.POLICY, 'render', side_effect=rendered):
            return super().collect(payload, **kwargs)

    def test_conversion_encoding_and_envelope(self):
        for event in ('codex.user_prompt', 'codex.agent_response'):
            _, docs, spans = self.collect(fixture(event))
            self.assertEqual(len(spans), 1)
            self.assertNotIn(CANARY, json.dumps(docs))
            span = spans[0]
            self.assertEqual(span['name'], 'codex.native.user_message' if event.endswith('user_prompt') else 'codex.native.assistant_message')
            self.assertRegex(span['traceId'], r'^[a-f0-9]{32}$')
            self.assertRegex(span['spanId'], r'^[a-f0-9]{16}$')
            self.assertNotIn('parentSpanId', span)
            attrs = {a['key']: a['value']['stringValue'] for a in span['attributes']}
            field = 'input' if event.endswith('user_prompt') else 'output'
            self.assertEqual(set(attrs), {'session.id', 'langfuse.observation.type', 'langfuse.observation.' + field})
            if field == 'input':
                self.assertEqual(attrs['langfuse.observation.input'], 'Hello "quote" \\ slash\nUnicode: 雪 <secret excluded>')
            _, _, replay = self.collect(fixture(event))
            self.assertEqual(span['traceId'], replay[0]['traceId'])
            self.assertEqual(span['spanId'], replay[0]['spanId'])

    def test_exclusions(self):
        for payload in (fixture(session=UNKNOWN), fixture(session=RECOVERY), fixture(timestamp=CUTOFF - 1000000),
                        fixture(event='codex.tool_result'), fixture(event='codex.agent_response', **{'agent.type': 'subagent'}),
                        fixture(prompt=None), fixture(**{'parent.conversation.id': UNKNOWN})):
            self.assertEqual(self.collect(payload)[2], [])

    def test_source_clock_and_source_identity_fail_closed(self):
        for value in (None, 'not-a-time', '2026-99-99T00:00:00.000Z'):
            self.assertEqual(self.collect(fixture(**{'event.timestamp': value}))[2], [])
        for field, value in (('service.name', 'unknown'), ('service.version', '0.168.0')):
            payload = fixture()
            attrs = payload['resourceLogs'][0]['resource']['attributes']
            next(a for a in attrs if a['key'] == field)['value']['stringValue'] = value
            self.assertEqual(self.collect(payload)[2], [])
        payload = fixture()
        payload['resourceLogs'][0]['scopeLogs'][0]['scope']['name'] = 'codex_otel.trace_safe'
        self.assertEqual(self.collect(payload)[2], [])
        self.assertEqual(self.collect(fixture(event='codex.agent_response', **{'item.id': 'malformed'}))[2], [])

    def test_json_injection_stays_literal_text(self):
        text = '\"}]}]}],\"resourceSpans\":[{\"evil\":true}] \\ \n 雪'
        _, docs, spans = self.collect(fixture(prompt=text))
        self.assertEqual(len(spans), 1)
        attrs = {a['key']: a['value']['stringValue'] for a in spans[0]['attributes']}
        self.assertEqual(attrs['langfuse.observation.input'], text)
        self.assertEqual(len(docs), 1)
        self.assertNotIn('evil', docs[0])

    def test_partial_empty_oversize_and_mismatched_app_rejected(self):
        for payload in (fixture(prompt=''), fixture(prompt='x' * 65537),
                        fixture(event='codex.agent_response', response='x' * 65537),
                        fixture(**{'app.version': '0.168.0'})):
            self.assertEqual(self.collect(payload)[2], [])
        payload = fixture(event='codex.agent_response')
        attrs = payload['resourceLogs'][0]['scopeLogs'][0]['logRecords'][0]['attributes']
        next(a for a in attrs if a['key'] == 'response_truncated')['value']['boolValue'] = True
        self.assertEqual(self.collect(payload)[2], [])

    def test_pattern_filter_is_not_general_secret_detection(self):
        text = 'FAKE ONLY recovery share: violet otter paper lantern'
        _, docs, spans = self.collect(fixture(prompt=text))
        self.assertEqual(len(spans), 1)
        self.assertIn(text, json.dumps(docs))


# Avoid inherited plugin cases: only authored native tests belong in this suite.
if __name__ == '__main__':
    suite = unittest.TestSuite(NativeMessageTests(name) for name in NativeMessageTests.__dict__ if name.startswith('test_'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())
