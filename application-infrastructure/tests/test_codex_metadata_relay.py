"""Synthetic metadata/privacy/durability tests; no live credentials or source data."""
import base64
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('codex_relay', Path(__file__).resolve().parents[1] / 'codex_metadata_relay.py')
relay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(relay)
CANARY = 'UNAPPROVED_PRIVATE_CONTENT_CANARY'


def fixture():
    return {'schemaUrl': CANARY, 'resourceSpans': [{
        'schemaUrl': CANARY, 'resource': {'attributes': [{'key': 'secret', 'value': {'stringValue': CANARY}}]},
        'scopeSpans': [{'schemaUrl': CANARY, 'scope': {'name': CANARY, 'version': CANARY}, 'spans': [{
            'traceId': '1234567890abcdef1234567890abcdef', 'spanId': '1234567890abcdef',
            'name': CANARY, 'startTimeUnixNano': '100', 'endTimeUnixNano': '200',
            'traceState': CANARY, 'status': {'code': 1, 'message': CANARY},
            'attributes': [{'key': 'prompt', 'value': {'stringValue': CANARY}},
                           {'key': 'gen_ai.usage.input_tokens', 'value': {'intValue': '12'}}],
            'events': [{'name': CANARY, 'attributes': [{'key': CANARY, 'value': {'stringValue': CANARY}}]}],
            'links': [{'traceState': CANARY}], 'unknown': CANARY,
        }]}]}]}


class MetadataRelayTests(unittest.TestCase):
    def test_whole_envelope_removes_private_text_and_schema_urls(self):
        result = relay.sanitize(fixture())
        self.assertNotIn(CANARY, json.dumps(result))
        self.assertNotIn('schemaUrl', json.dumps(result))
        self.assertNotIn('traceState', json.dumps(result))
        self.assertNotIn('events', json.dumps(result))

    def test_only_typed_numeric_usage_survives(self):
        item = fixture()
        span = item['resourceSpans'][0]['scopeSpans'][0]['spans'][0]
        span['attributes'] += [{'key': 'gen_ai.usage.output_tokens', 'value': {'intValue': CANARY}}]
        span = relay.sanitize(item)['resourceSpans'][0]['scopeSpans'][0]['spans'][0]
        self.assertIn({'key': 'gen_ai.usage.input_tokens', 'value': {'intValue': '12'}}, span['attributes'])
        self.assertFalse(any(a['key'] == 'gen_ai.usage.output_tokens' for a in span['attributes']))

    def test_logs_and_metrics_are_rejected(self):
        for name in ('resourceLogs', 'resourceMetrics'):
            with self.assertRaises(relay.RelayError):
                relay.sanitize({name: []})

    def test_json_duplicate_keys_and_nonfinite_values_rejected(self):
        for value in (b'{"a":1,"a":2}', b'{"a":NaN}'):
            with self.assertRaises(relay.RelayError):
                relay.decode(value)

    def test_identifier_encodings_and_validation(self):
        raw = bytes.fromhex('1234567890abcdef')
        self.assertEqual(relay.identifier(base64.b64encode(raw).decode(), 8), raw.hex())
        for value in ('0' * 16, CANARY, 4):
            with self.assertRaises(relay.RelayError):
                relay.identifier(value, 8)

    def test_queue_replay_and_restart_preserve_one_sanitized_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'queue.sqlite'
            queue = relay.Queue(path)
            first = queue.accept(fixture())
            self.assertEqual(queue.accept(fixture()), first)
            self.assertNotIn(CANARY.encode(), queue.next()[1])
            del queue
            recovered = relay.Queue(path)
            self.assertEqual(recovered.status()['pending_batches'], 1)
            recovered.attempted(first, False)
            self.assertEqual(recovered.status()['pending_batches'], 1)
            recovered.attempted(first, True)
            self.assertEqual(recovered.status()['delivered_batches'], 1)
            self.assertEqual(recovered.accept(fixture()), first)
            self.assertEqual(recovered.status()['accepted_batches'], 1)
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM batches').fetchone()[0], 1)

    def test_session_identity_is_pseudonymized(self):
        item = fixture()
        span = item['resourceSpans'][0]['scopeSpans'][0]['spans'][0]
        session = '12345678-1234-1234-1234-123456789abc'
        span['attributes'].append({'key': 'conversation.id', 'value': {'stringValue': session}})
        result = relay.sanitize(item)
        self.assertNotIn(session, json.dumps(result))
        self.assertTrue(any(a['key'] == 'session.id' for a in result['resourceSpans'][0]['scopeSpans'][0]['spans'][0]['attributes']))


if __name__ == '__main__':
    unittest.main()
