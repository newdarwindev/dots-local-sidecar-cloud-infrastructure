"""Synthetic local admission projection including Collector diagnostic canaries."""
import json
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest import mock
import conversation_runtime as harness
from conversation_runtime import ConversationTests, CANARY
from native_event_runtime import fixture, attrs
SPEC = importlib.util.spec_from_file_location('admission_policy', Path(__file__).resolve().parents[1] / 'application-infrastructure/native_admission_diagnostic_policy.py')
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)


class AdmissionTests(ConversationTests):
    forbidden_canaries = (CANARY,)

    def collect(self, payload):
        config = {'extensions': {'basicauth/conversation': {}},
                  'receivers': {'otlp/conversation': {'protocols': {'http': {'endpoint': '127.0.0.1:17448', 'traces_url_path': '/api/public/otel/v1/traces', 'auth': {'authenticator': 'basicauth/conversation'}}}}},
                  'processors': policy.processors(), 'exporters': {},
                  'service': {'extensions': ['basicauth/conversation'], 'telemetry': {'logs': {'level': 'info'}, 'metrics': {'level': 'none'}},
                              'pipelines': {'traces/conversation': {'receivers': ['otlp/conversation'], 'processors': list(policy.processors()), 'exporters': []}}}}
        with mock.patch.object(harness.POLICY, 'render', return_value=config):
            return super().collect(payload)

    def test_fixed_classifications_and_entire_envelope(self):
        for service, scope, version, match in [('codex_cli_rs', 'codex_cli_rs', '0.167.0', True),
                                              ('codex-app-server', 'codex-app-server', '0.167.0', True),
                                              ('codex_exec', 'codex_exec', '0.167.0', False),
                                              ('codex_cli_rs', CANARY, '0.167.0', False),
                                              (CANARY, CANARY, CANARY, False),
                                              ('codex_cli_rs', 'codex_cli_rs', CANARY, False)]:
            payload = fixture([{'event.name': CANARY, 'prompt': CANARY}])
            resource = payload['resourceSpans'][0]
            resource['resource']['attributes'] = attrs({'service.name': service, 'service.version': version, 'private': CANARY})
            group = resource['scopeSpans'][0]
            group['scope'].update(name=scope, version=CANARY)
            _, docs, spans = self.collect(payload)
            self.assertEqual(len(spans), 1)
            self.assertNotIn(CANARY, json.dumps(docs))
            span = spans[0]
            self.assertEqual(span['traceId'], '1' * 32)
            self.assertEqual(span['spanId'], '2' * 16)
            self.assertNotIn('events', span)
            self.assertNotIn('links', span)
            values = {a['key']: a['value'] for a in span['attributes']}
            self.assertEqual(values['diagnostic.source_match'], {'boolValue': match})
            self.assertEqual(values['diagnostic.event_count'], {'intValue': '1'})
            self.assertEqual(values['diagnostic.link_count'], {'intValue': '0'})
            self.assertEqual(set(values), {'diagnostic.source_match', 'diagnostic.version_match', 'diagnostic.service', 'diagnostic.scope', 'diagnostic.event_count', 'diagnostic.link_count'})

    def test_linked_blind_spot_and_malformed(self):
        payload = fixture([])
        payload['resourceSpans'][0]['scopeSpans'][0]['spans'][0]['links'] = [{'traceId': '4' * 32, 'spanId': '5' * 16, 'traceState': CANARY, 'attributes': attrs({'private': CANARY})}]
        self.assertEqual(self.collect(payload)[2], [])
        self.assertEqual(self.collect('{"' + CANARY + '":')[2], [])


if __name__ == '__main__':
    suite = unittest.TestSuite(AdmissionTests(n) for n in AdmissionTests.__dict__ if n.startswith('test_'))
    passed = unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()
    if passed:
        # Nonsecret template receipt, rendered only inside the committed runner.
        print('QUALIFIED_ADMISSION_PROCESSORS=' + json.dumps(policy.processors(), sort_keys=True))
    sys.exit(not passed)
