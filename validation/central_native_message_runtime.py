"""Pinned upstream Collector central native EVENT gate, synthetic Docker only."""
import importlib.util
import copy
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
    def collect(self, payload, enrolled=None, denied=None, future_after_ns=None, tool_results=False,
                request_cap=None, routed=False):
        processors = POLICY.build_processors({FRESH: CUTOFF, RECOVERY: CUTOFF} if enrolled is None else enrolled,
                                             [RECOVERY] if denied is None else denied,
                                             future_after_ns=future_after_ns, tool_results=tool_results)
        config = {'extensions': {'basicauth/conversation': {}},
                  'receivers': {'otlp/conversation': {'protocols': {'http': {'endpoint': '127.0.0.1:17448',
                      'traces_url_path': '/api/public/otel/v1/traces', 'auth': {'authenticator': 'basicauth/conversation'}}}}},
                  'processors': processors, 'exporters': {},
                  'service': {'extensions': ['basicauth/conversation'], 'telemetry': {'logs': {'level': 'error'}, 'metrics': {'level': 'none'}},
                              'pipelines': {'traces/conversation': {'receivers': ['otlp/conversation'],
                                  'processors': [POLICY.FILTER, POLICY.TRANSFORM], 'exporters': []}}}}
        if request_cap is not None:
            config['receivers']['otlp/conversation']['protocols']['http']['max_request_body_size'] = request_cap
        capture_pipeline = 'traces/conversation'
        if routed:
            # Start from the patcher's supported graph; only synthetic transport
            # and non-native sinks are substituted for this isolated route test.
            base = copy.deepcopy(config)
            base['receivers']['otlp'] = base['receivers'].pop('otlp/conversation')
            base['processors'] = {'memory_limiter': {'check_interval': '100ms', 'limit_mib': 64},
                                  'batch': {'timeout': '50ms'}, 'batch/conversations': {'timeout': '50ms'},
                                  'filter/privacy': {'traces': {'span': ['true']}},
                                  'filter/conversations': {'traces': {'span': ['true']}},
                                  'transform/privacy': {'trace_statements': [{'context': 'span', 'statements': ['keep_keys(span.attributes, [])']}]},
                                  'transform/conversations': {'trace_statements': [{'context': 'span', 'statements': ['keep_keys(span.attributes, [])']}]}}
            base['connectors'] = {POLICY.ROUTER: {'error_mode': 'propagate', 'default_pipelines': ['traces/diagnostics'],
                                               'table': [copy.deepcopy(POLICY.PLUGIN_ROW)]}}
            base['exporters'] = {'otlphttp/langfuse': {}, 'otlphttp/conversations': {}}
            base['service']['pipelines'] = copy.deepcopy(POLICY.BASE_PIPELINES)
            config = POLICY.patch_config(base, {FRESH: CUTOFF, RECOVERY: CUTOFF}, [RECOVERY],
                                         future_after_ns=future_after_ns, tool_results=tool_results)
            config['receivers']['otlp/conversation'] = config['receivers'].pop('otlp')
            config['service']['pipelines']['traces/ingress']['receivers'] = ['otlp/conversation']
            for name, pipeline in config['service']['pipelines'].items():
                if name != 'traces/ingress': pipeline['exporters'] = ['file/sanitized']
            capture_pipeline = POLICY.PIPELINE
        with mock.patch.object(harness.POLICY, 'render', return_value=config):
            return super().collect(payload, capture_pipeline=capture_pipeline)

    def test_tool_metadata_does_not_expand_message_projection(self):
        for assistant in (False, True):
            status, docs, spans = self.collect(fixture(assistant, **{'langfuse.observation.metadata': CANARY}), tool_results=True)
            self.assertEqual(status, 200)
            self.assertEqual(len(spans), 1)
            self.assertNotIn(CANARY, json.dumps(docs))
            self.assertNotIn('langfuse.observation.metadata', json.dumps(spans))

    def test_route_and_request_cap_with_mixed_admission(self):
        tool = fixture(**{'langfuse.observation.input': '\x00' * 65536,
                          'langfuse.observation.output': '\\' * 65600,
                          'langfuse.observation.metadata': '{}'})
        span = tool['resourceSpans'][0]['scopeSpans'][0]['spans'][0]
        span['name'] = 'codex.native.tool_result'
        self.assertGreater(len(json.dumps(tool).encode()), 65536)
        status, _, spans = self.collect(tool, tool_results=True, request_cap=65536, routed=True)
        self.assertIn(status, (400, 413))
        self.assertEqual(spans, [])
        # Explicit 1-MiB cap is a test fixture, never a deployment/default change.
        status, _, spans = self.collect(tool, tool_results=True, request_cap=1048576, routed=True)
        self.assertEqual(status, 200)
        self.assertEqual(len(spans), 1)
        mixed = fixture()
        records = mixed['resourceSpans'][0]['scopeSpans'][0]['spans']
        for bad in (fixture(session=RECOVERY), fixture(start=CUTOFF-1), fixture(session=UNKNOWN)):
            records.append(bad['resourceSpans'][0]['scopeSpans'][0]['spans'][0])
        status, _, spans = self.collect(mixed, tool_results=True, routed=True)
        self.assertEqual(status, 200)
        self.assertEqual(len(spans), 1)

    def test_future_enrollment_matches_local_cutoff_and_denials(self):
        self.assertEqual(len(self.collect(fixture(session=UNKNOWN), future_after_ns=CUTOFF)[2]), 1)
        for payload in (fixture(session=UNKNOWN, start=CUTOFF - 1), fixture(session=RECOVERY),
                        fixture(session='*'), fixture(session=''), fixture(start=CUTOFF - 1)):
            self.assertEqual(self.collect(payload, future_after_ns=CUTOFF)[2], [])

    def test_tool_result_requires_explicit_opt_in_and_complete_bounded_projection(self):
        payload = fixture(**{'langfuse.observation.output': 'Synthetic result',
                             'langfuse.observation.metadata': '{"output_truncated":true}'})
        payload['resourceSpans'][0]['scopeSpans'][0]['spans'][0]['name'] = 'codex.native.tool_result'
        self.assertEqual(self.collect(payload)[2], [])
        _, docs, spans = self.collect(payload, tool_results=True)
        self.assertEqual(len(spans), 1)
        self.assertNotIn(CANARY, json.dumps(docs))
        for field, value in (('langfuse.observation.metadata', None),
                             ('langfuse.observation.input', 'x' * 65537),
                             ('langfuse.observation.output', 'x' * 65601),
                             ('langfuse.observation.metadata', 'x' * 8193),
                             ('session.id', RECOVERY)):
            import copy
            invalid = copy.deepcopy(payload)
            attrs = invalid['resourceSpans'][0]['scopeSpans'][0]['spans'][0]['attributes']
            attrs[:] = [item for item in attrs if item['key'] != field]
            if value is not None:
                attrs.extend(attributes({field: value}))
            self.assertEqual(self.collect(invalid, tool_results=True)[2], [])

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
