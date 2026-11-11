#!/usr/bin/env python3
"""Loopback mTLS OTLP metadata boundary and durable, noncanonical delivery queue.

Only reconstructed metadata reaches SQLite or Langfuse. Raw request bodies and
subprocess errors are never logged. Credentials are supplied outside the source
tree. The fixed Kubernetes exec transport uses the existing authenticated TLS
connection; its HTTP hop is confined to the target web container's loopback.
"""
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import ssl
import subprocess
import threading
import time

MAX_BODY = 4 * 1024 * 1024
MAX_SPANS = 4096
MAX_PENDING = 4096
MAX_DATABASE = 1024 * 1024 * 1024
SAFE_ROLE = 'diagnostic-noncanonical'
USAGE_KEYS = {
    'gen_ai.usage.input_tokens', 'gen_ai.usage.output_tokens',
    'gen_ai.usage.cache_read.input_tokens', 'gen_ai.usage.reasoning.output_tokens',
    'input_token_count', 'output_token_count', 'cached_input_token_count',
}
SESSION_KEYS = {'conversation.id', 'conversation_id', 'session.id', 'thread.id',
                'codex.conversation_id', 'session_id'}


class RelayError(ValueError):
    """Fixed messages only; never include input data or command diagnostics."""


def identifier(value, width):
    if type(value) is not str:
        raise RelayError('invalid identifier')
    if re.fullmatch(r'[a-fA-F0-9]{%d}' % (width * 2), value):
        data = bytes.fromhex(value)
    else:
        try:
            data = base64.b64decode(value, validate=True)
        except ValueError:
            raise RelayError('invalid identifier') from None
    if len(data) != width or not any(data):
        raise RelayError('invalid identifier')
    return data.hex()


def timestamp(value):
    if type(value) is int:
        number = value
    elif type(value) is str and re.fullmatch(r'[0-9]{1,20}', value):
        number = int(value)
    else:
        raise RelayError('invalid timestamp')
    if not 0 < number < 2**64:
        raise RelayError('invalid timestamp')
    return str(number)


def bounded_list(value, limit=MAX_SPANS):
    if type(value) is not list or len(value) > limit:
        raise RelayError('invalid list')
    return value


def sanitize(document):
    if type(document) is not dict or 'resourceLogs' in document or 'resourceMetrics' in document:
        raise RelayError('trace request required')
    output = {}
    count = 0
    for resource in bounded_list(document.get('resourceSpans'), 128):
        for scope in bounded_list(resource.get('scopeSpans'), 512):
            for raw in bounded_list(scope.get('spans')):
                count += 1
                if count > MAX_SPANS:
                    raise RelayError('span limit exceeded')
                trace = identifier(raw.get('traceId'), 16)
                span = identifier(raw.get('spanId'), 8)
                parent = identifier(raw['parentSpanId'], 8) if raw.get('parentSpanId') else ''
                start, end = timestamp(raw.get('startTimeUnixNano')), timestamp(raw.get('endTimeUnixNano'))
                if int(end) < int(start) or parent == span:
                    raise RelayError('invalid interval or lineage')
                attributes = [
                    {'key': 'dots.accounting.role', 'value': {'stringValue': SAFE_ROLE}},
                    {'key': 'langfuse.trace.name', 'value': {'stringValue': 'Codex CLI metadata'}},
                ]
                sessions = set()
                numeric = {}
                for attribute in bounded_list(raw.get('attributes', [])):
                    key, value = attribute.get('key'), attribute.get('value', {})
                    if key in SESSION_KEYS:
                        session = value.get('stringValue')
                        if type(session) is str and re.fullmatch(r'[a-fA-F0-9-]{32,36}', session):
                            sessions.add(session.lower().replace('-', ''))
                    if key in USAGE_KEYS:
                        number = value.get('intValue')
                        if type(number) is str and re.fullmatch(r'[0-9]{1,16}', number):
                            number = int(number)
                        if type(number) is int and 0 <= number <= 2**53 - 1:
                            numeric[key] = number
                if len(sessions) == 1:
                    pseudonym = hashlib.sha256(('codex-session:' + next(iter(sessions))).encode()).hexdigest()[:32]
                    attributes.append({'key': 'session.id', 'value': {'stringValue': pseudonym}})
                attributes.extend({'key': key, 'value': {'intValue': str(value)}} for key, value in sorted(numeric.items()))
                code = raw.get('status', {}).get('code', 0)
                if isinstance(code, str):
                    code = {'STATUS_CODE_UNSET': 0, 'STATUS_CODE_OK': 1, 'STATUS_CODE_ERROR': 2}.get(code, -1)
                if type(code) is not int or code not in (0, 1, 2):
                    raise RelayError('invalid status code')
                result = {'traceId': trace, 'spanId': span, 'parentSpanId': parent,
                          'name': 'codex.operation', 'kind': 1,
                          'startTimeUnixNano': start, 'endTimeUnixNano': end,
                          'status': {'code': code}, 'attributes': attributes}
                identity = (trace, span)
                if identity in output and output[identity] != result:
                    raise RelayError('conflicting replay')
                output[identity] = result
    ordered = [output[key] for key in sorted(output)]
    return {'resourceSpans': [{'resource': {'attributes': [
        {'key': 'service.name', 'value': {'stringValue': 'codex-cli'}},
    ]}, 'scopeSpans': [{'scope': {'name': 'codex.metadata.boundary', 'version': '1'},
                       'spans': ordered}]}]} if ordered else {'resourceSpans': []}


def decode(raw):
    if len(raw) > MAX_BODY:
        raise RelayError('request too large')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise RelayError('duplicate field')
            result[key] = value
        return result
    def constant(_value):
        raise RelayError('invalid number')
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError):
        raise RelayError('invalid JSON') from None


class Queue:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS batches (id TEXT PRIMARY KEY, payload BLOB NOT NULL, created REAL NOT NULL, sent REAL, attempts INTEGER NOT NULL DEFAULT 0)')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute('PRAGMA synchronous=FULL')
        return db

    def accept(self, document):
        # Never accept a caller's already-sanitized assertion; sanitize here too.
        payload = json.dumps(sanitize(document), sort_keys=True, separators=(',', ':')).encode()
        identity = hashlib.sha256(payload).hexdigest()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT id FROM batches WHERE id=?', (identity,)).fetchone()
            if existing:
                return identity
            size = sum(path.stat().st_size for path in (Path(self.path), Path(self.path + '-wal')) if path.exists())
            if size > MAX_DATABASE or db.execute('SELECT COUNT(*) FROM batches WHERE sent IS NULL').fetchone()[0] >= MAX_PENDING:
                raise RelayError('queue full')
            db.execute('INSERT INTO batches(id,payload,created) VALUES (?,?,?)', (identity, payload, time.time()))
        return identity

    def next(self):
        with self.connect() as db:
            return db.execute('SELECT id,payload FROM batches WHERE sent IS NULL ORDER BY created LIMIT 1').fetchone()

    def attempted(self, identity, success):
        with self.connect() as db:
            db.execute('UPDATE batches SET attempts=attempts+1, sent=CASE WHEN ? THEN ? ELSE sent END WHERE id=?', (success, time.time(), identity))

    def status(self):
        with self.connect() as db:
            total, sent, attempts = db.execute('SELECT COUNT(*),COALESCE(SUM(sent IS NOT NULL),0),COALESCE(SUM(attempts),0) FROM batches').fetchone()
        return {'accepted_batches': total, 'delivered_batches': sent, 'pending_batches': total - sent, 'delivery_attempts': attempts}


NODE_TRANSPORT = r'''
let text=''; for await (const part of process.stdin) text+=part;
const request=JSON.parse(text);
const url=new URL(request.path,'http://127.0.0.1:3000');
if(url.origin!=='http://127.0.0.1:3000') process.exit(2);
const response=await fetch(url,{method:request.method,headers:{
 'Authorization':request.authorization,'Content-Type':'application/json',
 'x-langfuse-ingestion-version':'4'
},body:request.method==='POST'?request.body:undefined,signal:AbortSignal.timeout(20000)});
const body=await response.text();
process.stdout.write(JSON.stringify({status:response.status,body}));
'''


class Transport:
    def __init__(self, config, authorization):
        self.config = config
        self.authorization = authorization
        self.base = ['/usr/bin/kubectl', '--kubeconfig=/etc/rancher/k3s/k3s.yaml',
                     '--server=https://127.0.0.1:6443', '--request-timeout=10s',
                     '--cache-dir=/var/lib/codex-metadata-relay/kube-cache']

    def command(self, args, content=None):
        try:
            result = subprocess.run(self.base + args, input=content, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, timeout=35, check=False)
            if result.returncode:
                raise RelayError('backend unavailable')
            return json.loads(result.stdout)
        except (OSError, subprocess.SubprocessError, ValueError):
            raise RelayError('backend unavailable') from None

    def request(self, path, method='GET', body=None):
        namespace = self.config['namespace']
        for name, expected in [('kube-system', self.config['cluster_uid']), (namespace, self.config['namespace_uid'])]:
            actual = self.command(['get', '--raw=/api/v1/namespaces/' + name])
            if actual['metadata']['uid'] != expected:
                raise RelayError('backend identity changed')
        deployment = self.command(['get', '--raw=/apis/apps/v1/namespaces/' + namespace + '/deployments/langfuse-web'])
        if deployment['metadata']['uid'] != self.config['deployment_uid']:
            raise RelayError('backend identity changed')
        pods = self.command(['get', '--raw=/api/v1/namespaces/' + namespace + '/pods'])
        selected = []
        for pod in pods['items']:
            if pod['metadata'].get('deletionTimestamp'):
                continue
            containers = pod.get('spec', {}).get('containers', [])
            if any(c.get('name') == 'langfuse-web' and c.get('image') == self.config['image'] for c in containers) and any(c.get('type') == 'Ready' and c.get('status') == 'True' for c in pod.get('status', {}).get('conditions', [])):
                selected.append(pod['metadata']['name'])
        if len(selected) != 1:
            raise RelayError('backend unavailable')
        # Fixed node program; all values travel through encrypted stdin, never argv.
        message = {'path': path, 'method': method, 'authorization': self.authorization,
                   'body': body.decode() if body else None}
        return self.command(['-n', namespace, 'exec', '-i', selected[0], '-c', 'langfuse-web',
                             '--', 'node', '--input-type=module', '-e', NODE_TRANSPORT], json.dumps(message).encode())

    def deliver(self, payload):
        response = self.request('/api/public/otel/v1/traces', 'POST', payload)
        if response['status'] != 200:
            return False
        try:
            result = json.loads(response['body'] or '{}')
            partial = result.get('partialSuccess', {})
            return int(partial.get('rejectedSpans', 0)) == 0
        except (ValueError, TypeError):
            return False


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 32
    def handle_error(self, request, client_address):
        pass  # Never log tracebacks containing request or credential data.


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def respond(self, code, value):
        data = json.dumps(value, separators=(',', ':')).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ('/health', '/status'):
            self.respond(200, self.server.queue.status())
        else:
            self.respond(404, {})

    def do_POST(self):
        if self.path != '/v1/traces':
            self.respond(404, {})
            return
        try:
            if self.headers.get('Content-Encoding', 'identity') != 'identity' or self.headers.get('Transfer-Encoding'):
                raise RelayError('unsupported encoding')
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BODY:
                raise RelayError('invalid request length')
            self.server.queue.accept(decode(self.rfile.read(length)))
            self.respond(200, {})
        except RelayError as exc:
            self.respond(503 if str(exc) == 'queue full' else 400, {})
        except (ValueError, TypeError, KeyError, AttributeError, sqlite3.Error):
            self.respond(400, {})


def main():
    os.umask(0o077)
    config = json.loads(Path('/etc/codex/telemetry/relay.json').read_text())
    credentials = Path(os.environ['CREDENTIALS_DIRECTORY'])
    queue = Queue('/var/lib/codex-metadata-relay/events.sqlite')
    transport = Transport(config, (credentials / 'authorization').read_text().strip())
    server = Server(('127.0.0.1', config['port']), Handler)
    server.queue = queue
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.minimum_version = ssl.TLSVersion.TLSv1_3
    tls.load_cert_chain(credentials / 'server-cert', credentials / 'server-key')
    tls.load_verify_locations(credentials / 'client-ca')
    tls.verify_mode = ssl.CERT_REQUIRED
    server.socket = tls.wrap_socket(server.socket, server_side=True)
    stop = threading.Event()
    def worker():
        while not stop.is_set():
            row = queue.next()
            if row:
                try:
                    success = transport.deliver(row[1])
                except Exception:
                    success = False
                queue.attempted(row[0], success)
                stop.wait(0.1 if success else 10)
            else:
                stop.wait(1)
    def shutdown(_signal, _frame):
        stop.set()
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(worker)
        server.serve_forever(poll_interval=0.5)
        server.server_close()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('metadata relay unavailable; diagnostics withheld') from None
