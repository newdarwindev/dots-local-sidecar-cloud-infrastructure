"""Synthetic native event metadata canaries using pinned upstream Collector."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

import conversation_runtime as harness
from conversation_runtime import ConversationTests, CANARY, attributes

SPEC = importlib.util.spec_from_file_location('native_events', Path(__file__).resolve().parents[1] / 'application-infrastructure/native_event_policy.py')
POLICY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POLICY)


def attrs(values):
    return [{'key': k, 'value': {'stringValue': v} if isinstance(v, str) else
             {'intValue': str(v)} if type(v) is int else {'boolValue': v}}
            for k, v in values.items()]


def fixture(events):
    span = {'traceId': '1' * 32, 'spanId': '2' * 16, 'parentSpanId': '3' * 16,
            'name': CANARY, 'startTimeUnixNano': '2000000000', 'endTimeUnixNano': '3000000000',
            'attributes': attributes({'prompt': CANARY}), 'status': {'message': CANARY}, 'traceState': 'x=' + CANARY,
            'events': [{'name': CANARY, 'timeUnixNano': '2500000000', 'attributes': attrs(e)} for e in events]}
    return {'resourceSpans': [{'schemaUrl': 'https://invalid/' + CANARY,
                              'resource': {'attributes': attributes({'service.name': 'codex_cli_rs', 'service.version': '0.167.0', 'user.email': CANARY})},
                              'scopeSpans': [{'schemaUrl': 'https://invalid/' + CANARY, 'scope': {'name': 'codex_cli_rs', 'attributes': attributes({'path': CANARY})}, 'spans': [span]}]}]}


class NativeEventTests(ConversationTests):
    def collect(self, payload, central_only=False):
        config = {'extensions': {'basicauth/conversation': {}},
                  'receivers': {'otlp/conversation': {'protocols': {'http': {'endpoint': '127.0.0.1:17448',
                      'traces_url_path': '/api/public/otel/v1/traces', 'auth': {'authenticator': 'basicauth/conversation'}}}}},
                  'processors': POLICY.processors(), 'exporters': {},
                  'service': {'extensions': ['basicauth/conversation'], 'telemetry': {'logs': {'level': 'error'}, 'metrics': {'level': 'none'}},
                              'pipelines': {'traces/conversation': {'receivers': ['otlp/conversation'],
                                  'processors': ['filter/source', 'filter/event-envelope', 'transform/event-envelope', 'transform/events', 'transform/event-finalize', 'filter/summarized-events'], 'exporters': []}}}}
        config['processors'].update(POLICY.central_processors())
        stages = config['service']['pipelines']['traces/conversation']['processors']
        if central_only:
            stages.clear()
        stages.extend(['filter/native-event-central', 'transform/native-event-central'])
        with mock.patch.object(harness.POLICY, 'render', return_value=config):
            return super().collect(payload)

    def test_numeric_summaries_unknown_events_and_no_content(self):
        events = [{'event.name': 'codex.sse_event', 'event.kind': 'response.completed', 'input_token_count': '12',
                   'output_token_count': 3, 'cached_token_count': 2, 'tool_token_count': '15', 'error.message': CANARY},
                  {'event.name': CANARY, 'input_token_count': 999, 'prompt': CANARY},
                  {'event.name': 'codex.tool_result', 'arguments_length': 42, 'output_length': 9, 'arguments': CANARY, 'output': CANARY}]
        _, docs, spans = self.collect(fixture(events))
        self.assertEqual(len(spans), 1)
        self.assertNotIn(CANARY, json.dumps(docs))
        span = spans[0]
        self.assertEqual(span['parentSpanId'], '3' * 16)
        self.assertNotIn('events', span)
        timeline = json.loads(next(a['value']['stringValue'] for a in span['attributes'] if a['key'] == POLICY.PREFIX + 'timeline_json'))
        self.assertEqual([e['name'] for e in timeline], ['codex.sse_event', 'codex.event.unclassified', 'codex.tool_result'])
        self.assertEqual(timeline[0]['reported_total_token_count'], 15)
        self.assertNotIn('tool_token_count', timeline[0])
        values = {a['key']: a['value'] for a in span['attributes']}
        self.assertEqual(values[POLICY.PREFIX + 'event_count'], {'intValue': '3'})
        self.assertEqual(values[POLICY.PREFIX + 'unclassified_event_count'], {'intValue': '1'})
        self.assertEqual(values[POLICY.PREFIX + 'sum.reported_total_token_count'], {'intValue': '15'})
        self.assertEqual(values[POLICY.PREFIX + 'sum.input_token_count'], {'intValue': '12'})
        self.assertEqual(values[POLICY.PREFIX + 'sum.output_length'], {'intValue': '9'})
        self.assertEqual(values[POLICY.PREFIX + 'count.codex.tool_result'], {'intValue': '1'})
        self.assertEqual(values[POLICY.PREFIX + 'count.codex.sse_event'], {'intValue': '1'})

    def test_numeric_abuse_wrong_kind_and_unvetted_source(self):
        for value in (CANARY, '-1', '99999999999999999999999999', True, -1, 1000000001):
            _, docs, spans = self.collect(fixture([{'event.name': 'codex.sse_event', 'event.kind': 'response.completed', 'input_token_count': value}]))
            self.assertEqual(len(spans), 1)
            self.assertNotIn('events', spans[0])
            values = {a['key']: a['value'] for a in spans[0]['attributes']}
            self.assertEqual(values[POLICY.PREFIX + 'sum.input_token_count'], {'intValue': '0'})
            self.assertNotIn(CANARY, json.dumps(docs))
        _, _, spans = self.collect(fixture([{'event.name': 'codex.sse_event', 'event.kind': 'not-completed', 'input_token_count': '12'}]))
        self.assertNotIn('events', spans[0])
        values = {a['key']: a['value'] for a in spans[0]['attributes']}
        self.assertEqual(values[POLICY.PREFIX + 'sum.input_token_count'], {'intValue': '0'})
        payload = fixture([])
        payload['resourceSpans'][0]['scopeSpans'][0]['scope']['name'] = 'unvetted'
        self.assertEqual(self.collect(payload)[2], [])

    def test_bounded_timeline_with_explicit_omission_count(self):
        _, docs, spans = self.collect(fixture([{'event.name': 'codex.startup_phase', 'duration_ms': '100'}] * 40))
        self.assertEqual(len(spans), 1)
        values = {a['key']: a['value'] for a in spans[0]['attributes']}
        timeline = values[POLICY.PREFIX + 'timeline_json']['stringValue']
        self.assertLessEqual(len(timeline.encode()), 4096)
        self.assertLessEqual(len(json.loads(timeline)), 32)
        self.assertEqual(len(json.loads(timeline)) + int(values[POLICY.PREFIX + 'timeline_omitted_count']['intValue']), 40)
        self.assertEqual(values[POLICY.PREFIX + 'event_count'], {'intValue': '40'})
        self.assertLess(len(json.dumps(docs).encode()), 12000)
        self.assertLess(len(json.dumps(docs).encode()) * 4, 65536)


    def test_central_revalidation_drops_forged_timeline_and_numeric_fields(self):
        for timeline in ('[{"name":"' + CANARY + '"}]', '[{"name":"codex.sse_event","output":"' + CANARY + '"}]', '{"not":"array"}'):
            payload = fixture([])
            scope = payload['resourceSpans'][0]['scopeSpans'][0]
            scope['scope'] = {'name': 'codex.native.diagnostics', 'version': '1'}
            scope['spans'][0]['attributes'] = attrs({POLICY.PREFIX + 'timeline_json': timeline,
                                                    POLICY.PREFIX + 'sum.input_token_count': CANARY, 'unknown': CANARY})
            _, docs, spans = self.collect(payload, central_only=True)
            self.assertEqual(len(spans), 1)
            self.assertNotIn(CANARY, json.dumps(docs))
            self.assertEqual(spans[0]['attributes'], [{'key': 'dots.accounting.role', 'value': {'stringValue': 'diagnostic-noncanonical'}}])


    def test_link_bearing_span_remains_fail_closed(self):
        payload = fixture([])
        payload['resourceSpans'][0]['scopeSpans'][0]['spans'][0]['links'] = [
            {'traceId': '4' * 32, 'spanId': '5' * 16, 'traceState': 'x=' + CANARY, 'attributes': attrs({'output': CANARY})}]
        self.assertEqual(self.collect(payload)[2], [])

    def test_wide_numeric_timeline_four_span_batch_budget(self):
        event = {field: 1000000000 for field in POLICY.FIELDS}
        event.update({'event.name': 'codex.sse_event', 'event.kind': 'response.completed', 'output': CANARY})
        _, docs, spans = self.collect(fixture([event] * 40))
        self.assertEqual(len(spans), 1)
        values = {a['key']: a['value'] for a in spans[0]['attributes']}
        self.assertEqual(values[POLICY.PREFIX + 'event_count'], {'intValue': '40'})
        self.assertGreater(int(values[POLICY.PREFIX + 'timeline_omitted_count']['intValue']), 0)
        self.assertLessEqual(len(values[POLICY.PREFIX + 'timeline_json']['stringValue'].encode()), 4096)
        self.assertLess(len(json.dumps(docs).encode()) * 4, 65536)
        self.assertNotIn(CANARY, json.dumps(docs))



if __name__ == '__main__':
    suite = unittest.TestSuite(NativeEventTests(name) for name in NativeEventTests.__dict__ if name.startswith('test_'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())
