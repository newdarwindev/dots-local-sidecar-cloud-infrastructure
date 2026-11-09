"""Pinned upstream Collector central native EVENT gate, synthetic Docker only."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

import conversation_runtime as harness
from conversation_runtime import ConversationTests, FRESH, RECOVERY, UNKNOWN, CUTOFF, CANARY, attributes

SPEC = importlib.util.spec_from_file_location('central_native_policy', Path(__file__).resolve().parents[1] / 'application-infrastructure/central_native_message_policy.py')
POLICY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POLICY)


def fixture(assistant=False, session=FRESH, start=CUTOFF, **changes):
    values = {'session.id': session, 'langfuse.observation.type': 'event',
              'langfuse.observation.output' if assistant else 'langfuse.observation.input': 'Synthetic visible message',
              'unknown': CANARY}
    values.update(changes)
    values = {key: value for key, value in values.items() if value is not None}
    span = {'traceId': '1' * 32, 'spanId': '2' * 16, 'name': 'codex.native.assistant_message' if assistant else 'codex.native.user_message',
            'startTimeUnixNano': str(start), 'endTimeUnixNano': str(start), 'attributes': attributes(values),
            'traceState': 'x=' + CANARY, 'status': {'message': CANARY},
            'events': [{'name': CANARY}]}
    return {'resourceSpans': [{'resource': {'attributes': attributes({'unknown': CANARY})},
                              'scopeSpans': [{'scope': {'name': 'codex.native.conversation', 'version': '1',
                                                        'attributes': attributes({'unknown': CANARY})}, 'spans': [span]}]}]}


class CentralNativeRuntimeTests(ConversationTests):
    def collect(self, payload, enrolled=None, denied=None):
        processors = POLICY.build_processors({FRESH: CUTOFF, RECOVERY: CUTOFF} if enrolled is None else enrolled,
                                             [RECOVERY] if denied is None else denied)
        config = {'extensions': {'basicauth/conversation': {}},
                  'receivers': {'otlp/conversation': {'protocols': {'http': {'endpoint': '127.0.0.1:17448',
                      'traces_url_path': '/api/public/otel/v1/traces', 'auth': {'authenticator': 'basicauth/conversation'}}}}},
                  'processors': processors, 'exporters': {},
                  'service': {'extensions': ['basicauth/conversation'], 'telemetry': {'logs': {'level': 'error'}, 'metrics': {'level': 'none'}},
                              'pipelines': {'traces/conversation': {'receivers': ['otlp/conversation'],
                                  'processors': [POLICY.FILTER, POLICY.TRANSFORM], 'exporters': []}}}}
        with mock.patch.object(harness.POLICY, 'render', return_value=config):
            return super().collect(payload)

    def test_empty_enrolled_denied_and_old_cutoff(self):
        self.assertEqual(self.collect(fixture(), enrolled={})[2], [])
        self.assertEqual(self.collect(fixture(), denied=[FRESH])[2], [])
        self.assertEqual(self.collect(fixture(session=UNKNOWN))[2], [])
        self.assertEqual(self.collect(fixture(start=CUTOFF - 1))[2], [])
        for assistant in (False, True):
            _, docs, spans = self.collect(fixture(assistant))
            self.assertEqual(len(spans), 1)
            self.assertNotIn(CANARY, json.dumps(docs))
            attrs = {a['key']: a['value']['stringValue'] for a in spans[0]['attributes']}
            field = 'langfuse.observation.output' if assistant else 'langfuse.observation.input'
            self.assertEqual(attrs, {'session.id': FRESH, 'langfuse.observation.type': 'event', field: 'Synthetic visible message'})
            self.assertNotIn('events', spans[0])

    def test_direction_type_scope_name_and_links_rejected(self):
        cases = [fixture(**{'langfuse.observation.output': 'Wrong extra direction'}),
                 fixture(True, **{'langfuse.observation.input': 'Wrong extra direction'}),
                 fixture(**{'langfuse.observation.input': None}),
                 fixture(**{'langfuse.observation.type': 'agent'})]
        for key, value in (('name', 'wrong'), ('links', [{'traceId': '3' * 32, 'spanId': '4' * 16}])):
            payload = fixture()
            payload['resourceSpans'][0]['scopeSpans'][0]['spans'][0][key] = value
            cases.append(payload)
        for key, value in (('name', 'unknown'), ('version', '2')):
            payload = fixture()
            payload['resourceSpans'][0]['scopeSpans'][0]['scope'][key] = value
            cases.append(payload)
        for payload in cases:
            self.assertEqual(self.collect(payload)[2], [])


if __name__ == '__main__':
    suite = unittest.TestSuite(CentralNativeRuntimeTests(name) for name in CentralNativeRuntimeTests.__dict__ if name.startswith('test_'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())
