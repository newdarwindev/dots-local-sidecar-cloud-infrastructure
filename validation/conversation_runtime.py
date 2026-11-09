#!/usr/bin/env python3
"""Real upstream Collector synthetic capture gate, isolated by committed Docker runner."""
import http.client
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('conversation_policy', ROOT / 'application-infrastructure/conversation_policy.py')
POLICY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POLICY)
FRESH = '11111111-1111-4111-8111-111111111111'
RECOVERY = '22222222-2222-4222-8222-222222222222'
UNKNOWN = '33333333-3333-4333-8333-333333333333'
CANARY = 'SYNTHETIC_SECRET_CANARY'
CUTOFF = 2000000000
P = POLICY.PREFIX


def attributes(values):
    return [{'key': key, 'value': {'stringValue': value} if isinstance(value, str)
             else {'arrayValue': {'values': [{'stringValue': CANARY}]}}}
            for key, value in values.items()]


def fixture(session=FRESH, start=CUTOFF, kind='span', **overrides):
    values = {'session.id': session, P + 'type': kind,
              P + 'metadata.codex.thread_id': session, P + 'metadata.codex.turn_id': FRESH,
              P + 'input': 'hello ' + CANARY, P + 'output': 'answer ' + CANARY,
              'user.id': CANARY, 'unknown': CANARY}
    if kind == 'generation':
        values[P + 'input'] = json.dumps([{'role': 'system', 'content': CANARY},
                                         {'role': 'user', 'content': 'HISTORY_PRIVATE'},
                                         {'tools': [{'name': CANARY}]}])
        values[P + 'output'] = json.dumps({'content': 'intermediate ' + CANARY,
                                          'reasoning': CANARY, 'tool_calls': [{'name': CANARY}]})
    values.update(overrides)
    values = {key: value for key, value in values.items() if value is not None}
    span = {'traceId': '1' * 32, 'spanId': '2' * 16, 'name': CANARY,
            'startTimeUnixNano': str(start), 'endTimeUnixNano': str(start + 100),
            'attributes': attributes(values), 'traceState': 'x=' + CANARY,
            'status': {'code': 2, 'message': CANARY},
            'events': [{'name': CANARY, 'attributes': attributes({'secret': CANARY})}]}
    return {'resourceSpans': [{'schemaUrl': 'https://invalid.example/' + CANARY,
                              'resource': {'attributes': attributes({'identity': CANARY})},
                              'scopeSpans': [{'schemaUrl': 'https://invalid.example/' + CANARY,
                                              'scope': {'name': CANARY, 'version': CANARY,
                                                        'attributes': attributes({'identity': CANARY})},
                                              'spans': [span]}]}]}


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class ConversationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Path('/.dockerenv').exists() or set(os.listdir('/sys/class/net')) != {'lo'}:
            raise RuntimeError('Docker --network=none required')
        if '0.163.2' not in subprocess.check_output(['otelcol-contrib', '--version'], text=True):
            raise RuntimeError('Pinned Collector required')

    def collect(self, payload, generations=False, authenticated=True):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            config = POLICY.render({FRESH: CUTOFF, RECOVERY: CUTOFF}, [RECOVERY], generations=generations)
            port = free_port()
            receiver = config['receivers']['otlp/conversation']['protocols']['http']
            receiver['endpoint'] = f'127.0.0.1:{port}'
            # Synthetic SHA password: test / test; not usable outside this ephemeral process.
            config['extensions']['basicauth/conversation']['htpasswd'] = {'inline': 'test:{SHA}qUqP5cyxm6YcTAhz05Hph5gvu9M='}
            config['exporters'] = {'file/sanitized': {'path': str(directory / 'output.jsonl'), 'flush_interval': '100ms'}}
            config['service']['pipelines']['traces/conversation']['exporters'] = ['file/sanitized']
            path = directory / 'collector.json'
            path.write_text(json.dumps(config))
            with (directory / 'log').open('w') as log:
                process = subprocess.Popen(['otelcol-contrib', '--config', str(path)], stdout=log, stderr=log)
                try:
                    for _ in range(100):
                        if process.poll() is not None:
                            self.fail('Collector startup failed: ' + (directory / 'log').read_text())
                        try:
                            with socket.create_connection(('127.0.0.1', port), .1):
                                break
                        except OSError:
                            time.sleep(.05)
                    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
                    headers = {'Content-Type': 'application/json'}
                    if authenticated:
                        headers['Authorization'] = 'Basic dGVzdDp0ZXN0'
                    connection.request('POST', '/api/public/otel/v1/traces', json.dumps(payload), headers)
                    response = connection.getresponse()
                    status = response.status
                    response.read()
                    connection.close()
                    time.sleep(.2)
                finally:
                    process.terminate()
                    process.wait(timeout=5)
            output = directory / 'output.jsonl'
            documents = [json.loads(line) for line in output.read_text().splitlines()] if output.exists() else []
            spans = [span for doc in documents for resource in doc.get('resourceSpans', [])
                     for scope in resource.get('scopeSpans', []) for span in scope.get('spans', [])]
            return status, documents, spans

    def test_fresh_root_sanitized_entire_envelope(self):
        status, documents, spans = self.collect(fixture())
        self.assertEqual(status, 200)
        self.assertEqual(len(spans), 1)
        encoded = json.dumps(documents)
        self.assertNotIn(CANARY, encoded)
        self.assertNotIn('schemaUrl', encoded)
        self.assertNotIn('events', encoded)
        attrs = {item['key']: item['value']['stringValue'] for item in spans[0]['attributes']}
        self.assertEqual(attrs, {'session.id': FRESH, P + 'type': 'span',
                                 P + 'input': 'hello <secret excluded>', P + 'output': 'answer <secret excluded>'})

    def test_session_exclusion_and_original_cutoff(self):
        cases = {'unknown': fixture(UNKNOWN), 'old_session_replay': fixture(UNKNOWN, start=1),
                 'recovery_allow_and_deny': fixture(RECOVERY), 'unknown_fork': fixture(UNKNOWN),
                 'missing_session': fixture(**{'session.id': None}),
                 'missing_turn': fixture(**{P + 'metadata.codex.turn_id': None}),
                 'mismatch': fixture(**{P + 'metadata.codex.thread_id': UNKNOWN}),
                 'old_turn': fixture(start=CUTOFF - 1), 'unknown_type': fixture(kind='unknown'),
                 'typed_media': fixture(**{P + 'input': []}),
                 'serialized_media': fixture(**{P + 'input': '[{"type":"image","url":"private"}]'}),
                 'malformed_root_output': fixture(**{P + 'output': []})}
        for name, payload in cases.items():
            with self.subTest(name=name):
                _, _, spans = self.collect(payload)
                self.assertEqual(spans, [])

    def test_generation_explicit_option(self):
        for session in (UNKNOWN, RECOVERY):
            _, _, spans = self.collect(fixture(session, kind='generation'), generations=True)
            self.assertEqual(spans, [])
        _, _, spans = self.collect(fixture(kind='generation', **{'session.id': None}), generations=True)
        self.assertEqual(spans, [])
        _, _, spans = self.collect(fixture(kind='generation'))
        self.assertEqual(spans, [])
        status, docs, spans = self.collect(fixture(kind='generation'), generations=True)
        self.assertEqual(status, 200)
        self.assertEqual(len(spans), 1)
        encoded = json.dumps(docs)
        for excluded in (CANARY, 'HISTORY_PRIVATE', 'reasoning', 'tool_calls', P + 'input'):
            self.assertNotIn(excluded, encoded)
        self.assertIn('intermediate <secret excluded>', encoded)

    def test_generation_invalid_shapes_and_old_start_fail_closed(self):
        for output in ('not JSON', '[]', '{"content":[{"type":"image"}]}', '{"reasoning":"private"}',
                       '{"content":"[{\\"type\\":\\"image\\"}]"}'):
            with self.subTest(output=output):
                _, _, spans = self.collect(fixture(kind='generation', **{P + 'output': output}), generations=True)
                self.assertEqual(spans, [])
        _, _, spans = self.collect(fixture(kind='generation', start=1), generations=True)
        self.assertEqual(spans, [])

    def test_auth_and_restart_policy(self):
        status, _, spans = self.collect(fixture(), authenticated=False)
        self.assertEqual(status, 401)
        self.assertEqual(spans, [])
        for _ in range(2):
            _, _, spans = self.collect(fixture(RECOVERY), generations=True)
            self.assertEqual(spans, [])
            _, _, spans = self.collect(fixture(UNKNOWN), generations=True)
            self.assertEqual(spans, [])

    def test_links_blocked_and_multiple_secret_patterns(self):
        payload = fixture()
        payload['resourceSpans'][0]['scopeSpans'][0]['spans'][0]['links'] = [
            {'traceId': '3' * 32, 'spanId': '4' * 16, 'traceState': CANARY}]
        _, _, spans = self.collect(payload)
        self.assertEqual(spans, [])
        text = 'Bearer SYNTHETIC_TOKEN hvs.SYNTHETIC_TOKEN sk-SYNTHETIC_SECRET_123456789'
        _, docs, spans = self.collect(fixture(**{P + 'input': text, P + 'output': text}))
        self.assertEqual(len(spans), 1)
        self.assertNotIn('SYNTHETIC', json.dumps(docs))

    def test_invalid_enrollment_and_default_deny(self):
        for enrolled, denied in (({'*': 1}, []), ({FRESH: 0}, []), ({FRESH: True}, []), ({}, ['*'])):
            with self.assertRaises(ValueError):
                POLICY.render(enrolled, denied)
        config = POLICY.render({}, [])
        self.assertIn('not ContainsValue([], span.attributes["session.id"])',
                      config['processors']['filter/enrollment']['traces']['span'])
        self.assertEqual(config, POLICY.render({}, []))


if __name__ == '__main__':
    unittest.main(verbosity=2)
