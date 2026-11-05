#!/usr/bin/env python3
"""Ephemeral Docker network-none Collector canaries, never live acceptance."""
import copy
import gzip
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import queue
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'application-infrastructure'
AUTH = 'Basic SYNTHETIC_NOT_A_CREDENTIAL'
CANARY = 'SYNTHETIC_PRIVATE_CANARY'
SPEC = importlib.util.spec_from_file_location('native_boundary', APP / 'native_otlp.py')
BOUNDARY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BOUNDARY)


def fixture():
    attribute = {'key': CANARY, 'value': {'stringValue': CANARY}}
    span = {'traceId': '1' * 32, 'spanId': '2' * 16, 'name': CANARY,
            'startTimeUnixNano': '1000000000', 'endTimeUnixNano': '2000000000',
            'traceState': 'synthetic=' + CANARY, 'status': {'code': 2, 'message': CANARY},
            'attributes': [attribute]}
    return {'resourceSpans': [{'schemaUrl': 'https://resource.invalid/' + CANARY,
                              'resource': {'attributes': [attribute]},
                              'scopeSpans': [{'schemaUrl': 'https://scope.invalid/' + CANARY,
                                              'scope': {'name': CANARY, 'version': CANARY,
                                                        'attributes': [attribute]}, 'spans': [span]}]}]}


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Path('/.dockerenv').exists():
            raise RuntimeError('Docker-only test')
        # Refuse even a Docker bridge; only loopback may exist in this stage.
        if set(os.listdir('/sys/class/net')) != {'lo'}:
            raise RuntimeError('Collector runtime tests require --network=none')
        version = subprocess.check_output(['otelcol-contrib', '--version'], text=True)
        if '0.163.2' not in version:
            raise RuntimeError('Collector version lock mismatch')
        cls.temp = tempfile.TemporaryDirectory(prefix='collector-runtime-')
        cls.directory = Path(cls.temp.name)
        # Keys never leave container tmpfs and never authorize persistent access.
        for name in ('trusted', 'wrong'):
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                            '-keyout', str(cls.directory / (name + '.key')),
                            '-out', str(cls.directory / (name + '.crt')), '-days', '1',
                            '-subj', '/CN=synthetic-test-only',
                            '-addext', 'subjectAltName=IP:127.0.0.1,DNS:localhost',
                            '-addext', 'extendedKeyUsage=serverAuth,clientAuth'],
                           check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.received = queue.Queue()
        records = self.received

        class Capture(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                payload = self.rfile.read(int(self.headers['Content-Length']))
                if self.headers.get('Content-Encoding') == 'gzip':
                    payload = gzip.decompress(payload)
                records.put((self.path, dict(self.headers), json.loads(payload)))
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', '2')
                self.end_headers()
                self.wfile.write(b'{}')

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Capture)
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.minimum_version = ssl.TLSVersion.TLSv1_3
        tls.load_cert_chain(self.directory / 'trusted.crt', self.directory / 'trusted.key')
        self.server.socket = tls.wrap_socket(self.server.socket, server_side=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.process = None
        self.log = None

    def tearDown(self):
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.log:
            self.log.close()
            print('BEGIN synthetic Collector log ' + self._testMethodName, flush=True)
            print(self.log_path.read_text(), end='', flush=True)
            print('END synthetic Collector log ' + self._testMethodName, flush=True)
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def start(self, trust='trusted', hostname='127.0.0.1'):
        config = yaml.safe_load((APP / 'values/collector.yaml').read_text())['alternateConfig']
        self.receiver_port, health = port(), port()
        config['extensions']['health_check']['endpoint'] = f'127.0.0.1:{health}'
        receiver = config['receivers']['otlp']['protocols']['http']
        receiver['endpoint'] = f'127.0.0.1:{self.receiver_port}'
        receiver['tls'].update(cert_file=str(self.directory / 'trusted.crt'),
                               key_file=str(self.directory / 'trusted.key'),
                               client_ca_file=str(self.directory / 'trusted.crt'))
        exporter = config['exporters']['otlphttp/diagnostics']
        exporter['traces_endpoint'] = f'https://127.0.0.1:{self.server.server_port}/v1/traces'
        exporter['headers']['Authorization'] = AUTH
        exporter['tls']['ca_file'] = str(self.directory / (trust + '.crt'))
        exporter['tls']['server_name_override'] = hostname
        # JSON capture and short bounded timers only; privacy processors unchanged.
        exporter['encoding'] = 'json'
        exporter['retry_on_failure']['enabled'] = False
        exporter['timeout'] = '1s'
        config['processors']['batch']['timeout'] = '100ms'
        path = self.directory / 'config.yaml'
        path.write_text(yaml.safe_dump(config))
        self.log_path = self.directory / (self._testMethodName + '.log')
        self.log = self.log_path.open('w')
        self.process = subprocess.Popen(['otelcol-contrib', '--config', str(path)],
                                        stdout=self.log, stderr=subprocess.STDOUT)
        for _ in range(100):
            if self.process.poll() is not None:
                self.fail('Collector failed to start: ' + self.log_path.read_text())
            try:
                connection = http.client.HTTPConnection('127.0.0.1', health, timeout=.2)
                connection.request('GET', '/')
                ready = connection.getresponse().status == 200
                connection.close()
                if ready:
                    return
            except OSError:
                pass
            time.sleep(.05)
        self.fail('Collector readiness timeout')

    def send(self, request, client='trusted', maximum=None):
        context = ssl.create_default_context(cafile=str(self.directory / 'trusted.crt'))
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        if maximum:
            context.maximum_version = maximum
        if client:
            context.load_cert_chain(self.directory / (client + '.crt'),
                                    self.directory / (client + '.key'))
        connection = http.client.HTTPSConnection('127.0.0.1', self.receiver_port,
                                                 context=context, timeout=3)
        try:
            connection.request('POST', '/v1/traces', json.dumps(request),
                               {'Content-Type': 'application/json'})
            response = connection.getresponse()
            response.read()
            self.assertEqual(response.status, 200)
        finally:
            connection.close()

    def capture(self):
        path, headers, request = self.received.get(timeout=5)
        self.assertEqual(path, '/v1/traces')
        self.assertEqual(headers.get('Authorization'), AUTH)
        self.assertEqual(headers.get('X-Langfuse-Ingestion-Version'), '4')
        return request

    def test_direct_schema_urls_remain_a_blocker(self):
        self.start()
        self.send(fixture())
        actual = self.capture()
        resource = actual['resourceSpans'][0]
        scope = resource['scopeSpans'][0]
        self.assertIn(CANARY, resource['schemaUrl'])
        self.assertIn(CANARY, scope['schemaUrl'])
        del resource['schemaUrl']
        del scope['schemaUrl']
        self.assertNotIn(CANARY, json.dumps(actual))
        self.assertEqual(scope['spans'][0]['name'], 'diagnostic.operation')
        print('LIMITATION VERIFIED: direct Collector input preserves resource/scope schema URLs.')

    def test_rebuilt_whole_envelope_has_no_canary(self):
        self.start()
        raw = fixture()
        span = raw['resourceSpans'][0]['scopeSpans'][0]['spans'][0]
        span['events'] = [{'name': CANARY}]
        span['links'] = [{'traceId': '3' * 32, 'spanId': '4' * 16, 'traceState': CANARY}]
        rebuilt = BOUNDARY.run({'schema_version': 1, 'synthetic': True, 'producer': 'native',
                                'signal': 'traces', 'request': raw})['request']
        self.send(rebuilt)
        actual = self.capture()
        self.assertNotIn(CANARY, json.dumps(actual))
        self.assertNotIn('schemaUrl', json.dumps(actual))
        spans = actual['resourceSpans'][0]['scopeSpans'][0]['spans']
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0]['traceId'], '1' * 32)
        self.assertEqual(spans[0]['attributes'], [{'key': 'dots.accounting.role',
                                                 'value': {'stringValue': 'diagnostic-noncanonical'}}])

    def test_events_and_links_are_dropped(self):
        self.start()
        request = fixture()
        spans = request['resourceSpans'][0]['scopeSpans'][0]['spans']
        event, link = copy.deepcopy(spans[0]), copy.deepcopy(spans[0])
        event.update(spanId='3' * 16, events=[{'name': CANARY}])
        link.update(spanId='4' * 16, links=[{'traceId': '5' * 32, 'spanId': '6' * 16}])
        spans.extend([event, link])
        self.send(request)
        actual = self.capture()
        exported = [span for resource in actual['resourceSpans']
                    for scope in resource['scopeSpans'] for span in scope['spans']]
        self.assertEqual([span['spanId'] for span in exported], ['2' * 16])

    def test_mtls_and_tls13_required(self):
        self.start()
        for client, maximum in ((None, None), ('wrong', None), ('trusted', ssl.TLSVersion.TLSv1_2)):
            with self.subTest(client=client, maximum=maximum), self.assertRaises((OSError, http.client.HTTPException)):
                self.send(fixture(), client, maximum)
        self.send(fixture())
        self.capture()
        self.assertTrue(self.received.empty())

    def rejected_export(self, trust, hostname, diagnostic):
        self.start(trust, hostname)
        self.send(fixture())
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and diagnostic not in self.log_path.read_text():
            time.sleep(.05)
        self.assertIn(diagnostic, self.log_path.read_text())
        self.assertTrue(self.received.empty(), 'Rejected exporter delivered HTTP payload')

    def test_exporter_wrong_ca(self):
        self.rejected_export('wrong', '127.0.0.1', 'unknown authority')

    def test_exporter_wrong_hostname(self):
        self.rejected_export('trusted', 'wrong.invalid', 'certificate is valid for')


if __name__ == '__main__':
    unittest.main(verbosity=2)
