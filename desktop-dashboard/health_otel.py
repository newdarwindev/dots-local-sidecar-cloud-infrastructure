#!/usr/bin/env python3
"""Explicitly enabled local dashboard health -> Langfuse OTLP/HTTP traces."""
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import time
from urllib.request import ProxyHandler, Request, build_opener


def attribute(key, value):
    kind = 'boolValue' if isinstance(value, bool) else 'intValue' if isinstance(value, int) else 'stringValue'
    return {'key': key, 'value': {kind: str(value) if kind == 'intValue' else value}}


def make_payload(snapshot):
    """Reconstruct an allowlisted envelope; never serialize the source snapshot."""
    trace_id, root_id = secrets.token_hex(16), secrets.token_hex(8)
    timing = snapshot['timing']
    common = [attribute('langfuse.trace.name', 'Desktop dashboard health'),
              attribute('langfuse.environment', 'local-desktop'),
              attribute('langfuse.observation.type', 'span'),
              attribute('langfuse.trace.metadata.source', 'local-dashboard-health'),
              attribute('langfuse.trace.metadata.synthetic', False)]
    root = {'traceId': trace_id, 'spanId': root_id, 'name': 'Desktop dashboard health', 'kind': 1,
            'startTimeUnixNano': str(timing['start_ns']), 'endTimeUnixNano': str(timing['end_ns']),
            'attributes': common,
            'status': {'code': 1 if all(item['healthy'] for item in snapshot['services']) else 2}}
    spans = [root]
    for service in snapshot['services']:
        if not service.get('started_ns') or not service.get('ended_ns'):
            continue
        extra = [attribute('desktop.service', service['name']), attribute('http.request.method', 'GET'),
                 attribute('desktop.healthy', service['healthy'])]
        if service.get('http_status') is not None:
            extra.append(attribute('http.response.status_code', service['http_status']))
        spans.append({'traceId': trace_id, 'spanId': secrets.token_hex(8), 'parentSpanId': root_id,
                      'name': 'HTTP health: ' + service['name'], 'kind': 3,
                      'startTimeUnixNano': str(service['started_ns']), 'endTimeUnixNano': str(service['ended_ns']),
                      'attributes': common + extra, 'status': {'code': 1 if service['healthy'] else 2}})
    return {'resourceSpans': [{'resource': {'attributes': [attribute('service.name', 'desktop-dashboard-health')]},
                               'scopeSpans': [{'scope': {'name': 'desktop-health', 'version': '1.0'}, 'spans': spans}]}]}


class HealthExporter:
    def __init__(self, credential_file, port):
        self.path, self.port = Path(credential_file), port
        self.accepted_batches = self.accepted_spans = self.failed_batches = self.skipped_batches = 0
        self.last_success = None

    def publish(self, snapshot):
        owned = any(item['name'] == 'langfuse' and item['owned'] and item['healthy'] for item in snapshot['services'])
        status = 'waiting for owned Langfuse connection'
        if not owned:
            self.skipped_batches += 1
        else:
            try:
                credential = json.loads(self.path.read_text())
                token = base64.b64encode((credential['public_key'] + ':' + credential['secret_key']).encode()).decode()
                payload = make_payload(snapshot)
                request = Request(f'http://127.0.0.1:{self.port}/api/public/otel/v1/traces',
                                  data=json.dumps(payload).encode(),
                                  headers={'Authorization': 'Basic ' + token, 'Content-Type': 'application/json',
                                           'x-langfuse-ingestion-version': '4'})
                with build_opener(ProxyHandler({})).open(request, timeout=3) as response:
                    body = response.read()
                    result = json.loads(body) if body else {}
                    if response.status != 200 or int(result.get('partialSuccess', {}).get('rejectedSpans', 0)):
                        raise RuntimeError('Health batch was not fully accepted')
                self.accepted_batches += 1
                self.accepted_spans += len(payload['resourceSpans'][0]['scopeSpans'][0]['spans'])
                self.last_success = datetime.now(timezone.utc).isoformat(timespec='seconds')
                status = 'exporting live local health'
            except (OSError, ValueError, KeyError, TypeError, RuntimeError):
                self.failed_batches += 1
                status = 'export unavailable or delivery uncertain'
                print(time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), status, flush=True)
        return {'status': status, 'accepted_batches': self.accepted_batches, 'accepted_spans': self.accepted_spans,
                'failed_batches': self.failed_batches, 'skipped_batches': self.skipped_batches,
                'last_success_at': self.last_success, 'synthetic': False}
