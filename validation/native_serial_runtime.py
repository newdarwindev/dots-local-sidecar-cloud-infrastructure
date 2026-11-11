"""Three real Collectors, synthetic auth/TLS/queues, Docker network-none only.

Qualifies a bounded candidate topology, not production configs or Langfuse storage.
"""
import copy
import hashlib
import http.client
import json
from pathlib import Path
import queue
import ssl
import subprocess
import tempfile
import time
import unittest

from collector_runtime import RuntimeTests, port, AUTH
from native_message_runtime import fixture, POLICY as LOCAL
from conversation_runtime import FRESH, RECOVERY, UNKNOWN, CANARY
import native_log_diagnostic_policy as DIAGNOSTIC
import central_native_message_policy as CENTRAL

CUTOFF = 1794235254000000000
STAMP = CUTOFF + 1000000000
CAP = 1048576


def tool(**changes):
    values = {'arguments': '\x00' * 65536, 'output': '\x00' * 65600,
              'call_id': 'call_synthetic', 'tool_name': 'read', 'tool_namespace': 'functions',
              'agent_name': 'main', 'mcp_server': '', 'mcp_server_origin': '',
              'success': 'true', 'duration_ms': '12'}
    values.update(changes)
    payload = fixture(event='codex.tool_result', timestamp=STAMP, **values)
    payload['resourceLogs'][0]['scopeLogs'][0]['logRecords'][0]['attributes'] += [
        {'key': 'tool_result_seq', 'value': {'intValue': '7'}},
        {'key': 'output_truncated', 'value': {'boolValue': True}}]
    return payload


def content_id(payload):
    record = payload['resourceLogs'][0]['scopeLogs'][0]['logRecords'][0]
    attrs = {a['key']: next(iter(a['value'].values())) for a in record['attributes']}
    item = (attrs['call_id'] + ':' + str(attrs['tool_result_seq']) if attrs['event.name'] == 'codex.tool_result'
            else attrs['item.id'] if attrs['event.name'] == 'codex.agent_response' else '')
    digest = hashlib.sha256(':'.join([attrs['conversation.id'], attrs['event.name'], attrs['event.timestamp'],
                                     record['observedTimeUnixNano'], item]).encode()).hexdigest()
    return digest[:32], digest[32:48]


class SerialTests(RuntimeTests):
    def setUp(self):
        super().setUp()
        self.work = tempfile.TemporaryDirectory(prefix='serial-', dir=self.directory)
        self.root = Path(self.work.name)
        self.children = []
        self.delivered = []
        self.graph_number = 0

    def tearDown(self):
        for process, handle, path in reversed(self.children):
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=5)
            handle.close()
            self.assertNotIn(CANARY, path.read_text())
        super().tearDown()
        self.work.cleanup()

    def tls(self, receiver=False):
        result = {'cert_file': str(self.directory / 'trusted.crt'),
                  'key_file': str(self.directory / 'trusted.key'), 'min_version': '1.3'}
        result['client_ca_file' if receiver else 'ca_file'] = str(self.directory / 'trusted.crt')
        return result

    def exporter(self, target, path='/v1/traces', encoding='json', durable=True):
        result = {'traces_endpoint': f'https://127.0.0.1:{target}{path}', 'tls': self.tls(),
                  'encoding': encoding, 'compression': 'none', 'timeout': '1s',
                  'retry_on_failure': {'enabled': False}, 'sending_queue': {'enabled': False}}
        if durable:
            result['retry_on_failure'] = {'enabled': True, 'initial_interval': '100ms',
                                          'max_interval': '200ms', 'max_elapsed_time': '0s'}
            result['sending_queue'] = {'enabled': True, 'sizer': 'bytes', 'queue_size': 8388608,
                                      'storage': 'file_storage/queues', 'num_consumers': 1,
                                      'batch': {'sizer': 'items', 'min_size': 1, 'max_size': 1, 'flush_timeout': '100ms'}}
        return result

    def launch(self, name, config, durable=False):
        name += '-' + str(self.graph_number)
        config = copy.deepcopy(config)
        health = port()
        config.setdefault('extensions', {})['health_check'] = {'endpoint': f'127.0.0.1:{health}'}
        config['service'].setdefault('extensions', []).append('health_check')
        if durable:
            config['extensions']['file_storage/queues'] = {
                'directory': str(self.root / (name + '-queue')), 'create_directory': True, 'fsync': True,
                'max_size': 25165824, 'recreate': False,
                'compaction': {'on_start': False, 'on_rebound': False, 'cleanup_on_start': False}}
            config['service']['extensions'].append('file_storage/queues')
        config['service']['telemetry'] = {'logs': {'level': 'error'}, 'metrics': {'level': 'none'}}
        path = self.root / (name + '.json'); path.write_text(json.dumps(config))
        log_path = self.root / (name + '.log'); handle = log_path.open('w')
        process = subprocess.Popen(['otelcol-contrib', '--config', str(path)], stdout=handle, stderr=handle)
        self.children.append((process, handle, log_path))
        for _ in range(100):
            self.assertIsNone(process.poll(), name + ' startup: ' + log_path.read_text())
            try:
                conn = http.client.HTTPConnection('127.0.0.1', health, timeout=.2)
                conn.request('GET', '/'); ready = conn.getresponse().status == 200; conn.close()
                if ready: return
            except OSError:
                pass
            time.sleep(.05)
        self.fail(name + ' readiness timeout')

    def graph(self, outer_cap=CAP, inner_cap=CAP, encoding='json'):
        self.graph_number += 1
        self.outer_port, self.inner_port, self.local_port = port(), port(), port()
        def receiver(p, cap):
            return {'protocols': {'http': {'endpoint': f'127.0.0.1:{p}', 'tls': self.tls(True),
                                            'max_request_body_size': cap}}}
        policy = {'enrolled': {FRESH: CUTOFF}, 'denied': [RECOVERY], 'tool_results': True}
        # Use the source's native route. Other content producers have no synthetic
        # admission here; diagnostics use a fixed-name projection with no text.
        row = copy.deepcopy(CENTRAL.ROW)
        row['condition'] = row['condition'][:-1] + ' or span.name == "codex.native.tool_result")'
        inner = {'receivers': {'otlp': receiver(self.inner_port, inner_cap)},
                 'connectors': {CENTRAL.ROUTER: {'error_mode': 'propagate',
                                               'default_pipelines': ['traces/diagnostics'], 'table': [row]}},
                 'processors': CENTRAL.build_processors(**policy), 'exporters': {},
                 'service': {'pipelines': {
                     'traces/ingress': {'receivers': ['otlp'], 'exporters': [CENTRAL.ROUTER]},
                     CENTRAL.PIPELINE: {'receivers': [CENTRAL.ROUTER], 'processors': [CENTRAL.FILTER, CENTRAL.TRANSFORM],
                                        'exporters': ['otlphttp/content']},
                     'traces/diagnostics': {'receivers': [CENTRAL.ROUTER], 'processors': ['transform/diagnostic'],
                                           'exporters': ['otlphttp/diagnostic']}}}}
        inner['processors']['transform/diagnostic'] = {'trace_statements': [{'context': 'span', 'statements': [
            'set(span.name, "codex.operation")', 'keep_keys(span.attributes, [])',
            'keep_keys(resource.attributes, [])', 'keep_keys(instrumentation_scope.attributes, [])']}]}
        for name in ('content', 'diagnostic'):
            inner['exporters']['otlphttp/' + name] = self.exporter(self.server.server_port, '/' + name)
            inner['exporters']['otlphttp/' + name]['headers'] = {'Authorization': AUTH}
        self.launch('inner', inner, durable=True)
        outer = {'receivers': {'otlp': receiver(self.outer_port, outer_cap)},
                 'exporters': {'otlphttp/inner': self.exporter(self.inner_port, encoding=encoding, durable=False)},
                 'service': {'pipelines': {'traces': {'receivers': ['otlp'], 'exporters': ['otlphttp/inner']}}}}
        self.launch('outer', outer)
        local = DIAGNOSTIC.merge(LOCAL.render(**policy), **policy)
        local['extensions']['basicauth/native_messages'] = {'htpasswd': {'inline': 'test:{SHA}qUqP5cyxm6YcTAhz05Hph5gvu9M='}}
        http = local['receivers']['otlp/native_messages']['protocols']['http']
        http.update(endpoint=f'127.0.0.1:{self.local_port}', max_request_body_size=CAP)
        local['exporters']['otlphttp/rich'] = self.exporter(self.outer_port, encoding=encoding)
        self.launch('local', local, durable=True)

    def post(self, payload, authenticated=True):
        body = json.dumps(payload).encode()
        self.assertLessEqual(len(body), CAP)
        conn = http.client.HTTPConnection('127.0.0.1', self.local_port, timeout=5)
        headers = {'Content-Type': 'application/json'}
        if authenticated: headers['Authorization'] = 'Basic dGVzdDp0ZXN0'
        conn.request('POST', '/v1/logs', body, headers)
        response = conn.getresponse(); status = response.status; response.read(); conn.close()
        return status

    def collect_until(self, expected, seconds=5):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                self.delivered.append(self.received.get(timeout=.1))
            except queue.Empty:
                pass
            if len(self.spans('/content')) >= expected:
                break
        # Bound the observation window for extra/misrouted records.
        end = time.monotonic() + .5
        while time.monotonic() < end:
            try: self.delivered.append(self.received.get(timeout=.1))
            except queue.Empty: pass
        for _, headers, body in self.delivered:
            self.assertEqual(headers['Authorization'], AUTH)
            self.assertNotIn(CANARY, json.dumps(body))
            self.assertLessEqual(len(json.dumps(body).encode()), CAP)

    def spans(self, path):
        return [span for route, _, body in self.delivered if route == path
                for resource in body['resourceSpans'] for scope in resource['scopeSpans'] for span in scope['spans']]

    def test_serial_maximum_content_and_denials_json(self):
        self.serial_maximum('json')

    def test_serial_maximum_content_protobuf_hops_json_backend(self):
        self.serial_maximum('proto')

    def serial_maximum(self, encoding):
        self.graph(encoding=encoding)
        positive = [fixture(timestamp=STAMP, prompt='\x00' * 65536),
                    fixture('codex.agent_response', timestamp=STAMP, response='\x00' * 65536), tool()]
        for payload in positive:
            self.assertEqual(self.post(payload), 200)
        for payload in (fixture(session=RECOVERY, timestamp=STAMP), fixture(session=UNKNOWN, timestamp=STAMP),
                        fixture(timestamp=CUTOFF-1000000), fixture(timestamp=STAMP, **{'parent.conversation.id': UNKNOWN}),
                        fixture(timestamp=STAMP, **{'app.version': '0.168.0'})):
            self.assertEqual(self.post(payload), 200)
        self.collect_until(3)
        actual = [(s['traceId'], s['spanId']) for s in self.spans('/content')]
        self.assertCountEqual(actual, [content_id(p) for p in positive])
        self.assertTrue(self.spans('/diagnostic'), 'Independent diagnostic fan-out must survive')
        large = next(s for s in self.spans('/content') if s['name'] == 'codex.native.tool_result')
        attrs = {a['key']: a['value']['stringValue'] for a in large['attributes']}
        self.assertEqual(attrs['langfuse.observation.input'], '\x00' * 65536)
        self.assertEqual(attrs['langfuse.observation.output'], '\x00' * 65600)

    def test_each_64k_hop_blocks_large_content_despite_local_ack(self):
        for outer, inner in ((65536, CAP), (CAP, 65536)):
            with self.subTest(outer_cap=outer, inner_cap=inner):
                # Each subcase owns its three ephemeral processes and queues.
                self.graph(outer_cap=outer, inner_cap=inner)
                small = fixture(timestamp=STAMP)
                sentinel = fixture(timestamp=STAMP+1000000000)
                self.assertEqual(self.post(small), 200)
                self.assertEqual(self.post(tool()), 200)
                self.assertEqual(self.post(sentinel), 200)
                self.collect_until(3, seconds=3)
                self.assertCountEqual([(s['traceId'], s['spanId']) for s in self.spans('/content')],
                                      [content_id(small), content_id(sentinel)])
                sender = 'local' if outer == 65536 else 'outer'
                sending_log = (self.root / (sender + '-' + str(self.graph_number) + '.log')).read_text()
                self.assertRegex(sending_log, r'HTTP Status Code (400|413)')
                self.assertTrue(all(p.poll() is None for p, _, _ in self.children))
                for process, handle, log_path in reversed(self.children):
                    process.terminate()
                    try: process.wait(timeout=3)
                    except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=3)
                    handle.close()
                    self.assertNotIn(CANARY, log_path.read_text())
                self.children = []
                self.delivered = []
                while not self.received.empty(): self.received.get_nowait()

    def test_serial_authentication_boundaries(self):
        self.graph()
        self.assertEqual(self.post(fixture(timestamp=STAMP), authenticated=False), 401)
        for target in (self.outer_port, self.inner_port):
            context = ssl.create_default_context(cafile=str(self.directory / 'trusted.crt'))
            conn = http.client.HTTPSConnection('127.0.0.1', target, context=context, timeout=3)
            with self.assertRaises((ssl.SSLError, ConnectionError, http.client.RemoteDisconnected)):
                conn.request('POST', '/v1/traces', b'{}', {'Content-Type': 'application/json'})
                conn.getresponse().read()
            conn.close()
        self.assertEqual(self.post(fixture(timestamp=STAMP)), 200)
        self.collect_until(1)
        self.assertEqual(len(self.spans('/content')), 1)


if __name__ == '__main__':
    suite = unittest.TestSuite(SerialTests(name) for name in SerialTests.__dict__ if name.startswith('test_'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
