"""No live producers: numeric native logs, including Collector stderr canaries."""
import json
import copy
import gzip
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import sys
import unittest
from unittest import mock
from native_message_runtime import fixture as original_fixture, NativeMessageTests
from conversation_runtime import CANARY
import native_message_runtime as base
import native_log_diagnostic_policy as policy


def fixture(*args, **kwargs):
    return original_fixture(*args, timestamp=1794235254471000000, **kwargs)


class DiagnosticTests(NativeMessageTests):
    forbidden_canaries = (CANARY, 'FAKE_RECOVERY_SHARE_violet_otter', 'PRIVATE_CONTROLPLANE_CANARY')

    def collect(self, payload, **kwargs):
        with mock.patch.object(base.POLICY, 'render', side_effect=lambda *args, **kw: policy.render()):
            return super().collect(payload, **kwargs)

    def wire(self, payload, mode=200, merged=False, response_text="synthetic upstream failure", response_type="application/json", tool_results=False):
        captured = []
        class Backend(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                if self.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                captured.append(body)
                encoded = json.dumps({"code": 13, "message": response_text}).encode() if mode != 200 else b"{}"
                if response_type == "text/plain":
                    encoded = response_text.encode()
                self.send_response(mode)
                self.send_header("Content-Type", response_type)
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Backend)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        from conversation_runtime import FRESH, RECOVERY, CUTOFF, free_port
        config = policy.merge(policy.BASE_RENDER({FRESH: CUTOFF, RECOVERY: CUTOFF}, [RECOVERY], tool_results=tool_results), {FRESH: CUTOFF, RECOVERY: CUTOFF}, [RECOVERY], tool_results=tool_results) if merged else policy.render()
        port = free_port()
        config["receivers"]["otlp/native_messages"]["protocols"]["http"]["endpoint"] = f"127.0.0.1:{port}"
        config["extensions"]["basicauth/native_messages"]["htpasswd"] = {"inline": "test:{SHA}qUqP5cyxm6YcTAhz05Hph5gvu9M="}
        target = free_port() if mode == 0 else server.server_port
        config["exporters"]["otlphttp/rich"] = {"traces_endpoint": f"http://127.0.0.1:{target}/v1/traces", "encoding": "json", "timeout": "1s", "retry_on_failure": {"enabled": False}, "sending_queue": {"enabled": False}}
        config["service"]["telemetry"]["logs"]["level"] = "info"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "config.json").write_text(json.dumps(config))
            with (path / "collector.log").open("w") as log:
                process = subprocess.Popen(["otelcol-contrib", "--config", str(path / "config.json")], stdout=log, stderr=log)
                try:
                    for _ in range(100):
                        if process.poll() is not None:
                            self.fail((path / "collector.log").read_text())
                        try:
                            with socket.create_connection(("127.0.0.1", port), .1):
                                break
                        except OSError:
                            time.sleep(.05)
                    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                    connection.request("POST", "/v1/logs", json.dumps(payload), {"Content-Type": "application/json", "Authorization": "Basic dGVzdDp0ZXN0"})
                    response = connection.getresponse()
                    response.read()
                    connection.close()
                    time.sleep(.4)
                finally:
                    process.terminate()
                    process.wait(timeout=5)
            logs = (path / "collector.log").read_text()
            print("Synthetic wire Collector diagnostics:", logs, flush=True)
            for canary in self.forbidden_canaries:
                self.assertNotIn(canary, logs)
                self.assertTrue(all(canary.encode() not in item for item in captured))
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        return captured, logs

    def test_export_failure_diagnostics(self):
        for status in (0, 400, 401, 429, 500, 503):
            captured, logs = self.wire(fixture("codex.tool_result", arguments=CANARY), mode=status)
            self.assertIn("Exporting failed", logs)
            self.assertEqual(bool(captured), status != 0)

    def test_expanded_content_preserves_diagnostic_fanout_and_redacts_errors(self):
        payload = fixture('codex.tool_result', arguments=CANARY, output=CANARY,
                          call_id='call_synthetic', tool_name='read', tool_namespace='functions',
                          agent_name='main', mcp_server='', mcp_server_origin='', success='true', duration_ms='1')
        attrs = payload['resourceLogs'][0]['scopeLogs'][0]['logRecords'][0]['attributes']
        attrs += [{'key': 'tool_result_seq', 'value': {'intValue': '1'}},
                  {'key': 'output_truncated', 'value': {'boolValue': False}}]
        captured, _ = self.wire(payload, merged=True, tool_results=True)
        docs = [json.loads(body) for body in captured]
        names = [span['name'] for doc in docs for resource in doc.get('resourceSpans', [])
                 for scope in resource.get('scopeSpans', []) for span in scope.get('spans', [])]
        self.assertEqual(sorted(names), ['codex.native.tool_result', 'codex.operation'])
        self.wire(payload, mode=503, merged=True, tool_results=True)

    def test_content_parser_guard_blocks_raw_error_text(self):
        marker = "SYNTHETIC_BAD_CLOCK_PRIVATE_TEXT"
        captured, logs = self.wire(fixture(**{"event.timestamp": marker}), merged=True)
        self.assertTrue(all(marker.encode() not in body for body in captured))
        self.assertNotIn(marker, logs)
        self.assertEqual(captured, [])
        for clock in (None, [], "2026-99-99T99:99:99.000Z"):
            self.wire(fixture(**{"event.timestamp": clock, "arguments": CANARY, "error": self.forbidden_canaries[2]}), merged=True)
        self.wire(fixture("codex.agent_response", **{"item.id": []}), merged=True)

    def test_backend_error_text_handling(self):
        marker = "SYNTHETIC_BACKEND_ONLY_ERROR_TEXT"
        for response_type in ("application/json", "text/plain"):
            _, logs = self.wire(fixture(), mode=400, response_text=marker, response_type=response_type)
            self.assertNotIn(marker, logs)

    def test_merge_immutability_fanout_and_batch_budget(self):
        from conversation_runtime import FRESH, RECOVERY, UNKNOWN, CUTOFF
        original = policy.BASE_RENDER({FRESH: CUTOFF, RECOVERY: CUTOFF}, [RECOVERY])
        snapshot = copy.deepcopy(original)
        merged = policy.merge(original, {FRESH: CUTOFF, RECOVERY: CUTOFF}, [RECOVERY])
        self.assertEqual(original, snapshot)
        for key in ("receivers", "exporters", "extensions"):
            self.assertEqual(merged[key], original[key])
        for group in ("processors", "connectors"):
            for name, value in original[group].items():
                self.assertEqual(merged[group][name], value)
        for name, value in original["service"]["pipelines"].items():
            expected = copy.deepcopy(value)
            if name == "logs/native_messages":
                expected["processors"].insert(0, "filter/content_parser_guard")
            self.assertEqual(merged["service"]["pipelines"][name], expected)
        changed = copy.deepcopy(original)
        changed["processors"]["filter/native_messages"]["logs"]["log_record"] = []
        with self.assertRaises(ValueError):
            policy.merge(changed, {FRESH: CUTOFF, RECOVERY: CUTOFF}, [RECOVERY])
        changed = copy.deepcopy(original)
        changed["receivers"]["otlp/native_messages"]["protocols"]["http"]["auth"] = {}
        with self.assertRaises(ValueError):
            policy.merge(changed, {FRESH: CUTOFF, RECOVERY: CUTOFF}, [RECOVERY])
        changed = copy.deepcopy(original)
        changed["exporters"]["otlphttp/rich"]["sending_queue"]["enabled"] = True
        with self.assertRaises(ValueError):
            policy.merge(changed, {FRESH: CUTOFF, RECOVERY: CUTOFF}, [RECOVERY])
        payload = fixture(prompt="Bounded public synthetic greeting")
        records = payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"]
        for session in (RECOVERY, UNKNOWN):
            records.extend(fixture(session=session, prompt=CANARY)["resourceLogs"][0]["scopeLogs"][0]["logRecords"])
        captured, _ = self.wire(payload, merged=True)
        spans = [span for body in captured for resource in json.loads(body)["resourceSpans"] for scope in resource["scopeSpans"] for span in scope["spans"]]
        content = [span for span in spans if span["name"] == "codex.native.user_message"]
        diagnostics = [span for span in spans if span["name"] == "codex.operation"]
        self.assertEqual(len(content), 1)
        self.assertEqual(len(diagnostics), 3)
        self.assertIn("Bounded public synthetic greeting", json.dumps(content))
        self.assertNotIn("Bounded public synthetic greeting", json.dumps(diagnostics))
        wide = fixture("codex.sse_event", **{"event.kind": "response.completed", **{k: "999999999" for k in policy.events.FIELDS}})
        records = wide["resourceLogs"][0]["scopeLogs"][0]["logRecords"]
        records[:] = [copy.deepcopy(records[0]) for _ in range(25)]
        captured, _ = self.wire(wide)
        self.assertTrue(all(len(body) <= 65536 for body in captured))
        sizes = [sum(len(scope["spans"]) for resource in json.loads(body)["resourceSpans"] for scope in resource["scopeSpans"]) for body in captured]
        self.assertEqual(sum(sizes), 25)
        self.assertTrue(all(size <= 4 for size in sizes))

    def test_catalog_and_canaries(self):
        for event in policy.events.EVENTS:
            payload = fixture(event, **{'arguments': self.forbidden_canaries[1], 'error': self.forbidden_canaries[2], 'duration_ms': '12'})
            _, _, spans = self.collect(payload)
            self.assertEqual(len(spans), 1)
            attrs = {a['key']: a['value'] for a in spans[0]['attributes']}
            timeline = json.loads(attrs[policy.events.PREFIX + 'timeline_json']['stringValue'])
            self.assertEqual(timeline[0]['name'], event)
            self.assertNotIn('langfuse.observation.input', json.dumps(attrs))

    def test_invalid_shapes_and_auth(self):
        for key, value in [('event.timestamp', CANARY), ('event.timestamp', '2026-99-99T99:99:99.000Z'), ('event.timestamp', None), ('event.timestamp', []), ('event.name', []), ('conversation.id', CANARY), ('app.version', CANARY)]:
            self.assertEqual(self.collect(fixture(**{key: value}))[2], [])
        self.assertEqual(self.collect(fixture(), authenticated=False)[2], [])
        self.assertEqual(self.collect('{"' + CANARY + '":')[2], [])

    def test_producer_and_numeric_semantics(self):
        for field, value in (("service.name", CANARY), ("service.version", "0.168.0")):
            payload = fixture()
            attrs = payload["resourceLogs"][0]["resource"]["attributes"]
            next(a for a in attrs if a["key"] == field)["value"]["stringValue"] = value
            self.assertEqual(self.collect(payload)[2], [])
        payload = fixture()
        payload["resourceLogs"][0]["scopeLogs"][0]["scope"]["name"] = CANARY
        self.assertEqual(self.collect(payload)[2], [])
        for kind, expected in (("response.completed", True), (CANARY, False)):
            _, _, spans = self.collect(fixture("codex.sse_event", **{"event.kind": kind, "input_token_count": "17", "tool_token_count": "21"}))
            timeline = next(a["value"]["stringValue"] for a in spans[0]["attributes"] if a["key"].endswith("timeline_json"))
            self.assertEqual("input_token_count" in timeline, expected)
            self.assertEqual("reported_total_token_count" in timeline, expected)
            self.assertNotIn("tool_token_count", timeline)

    def test_missing_and_confused_source_envelopes(self):
        for key in ("service.name", "service.version"):
            for value in (None, {"arrayValue": {"values": [{"stringValue": CANARY}]}}):
                payload = fixture()
                attrs = payload["resourceLogs"][0]["resource"]["attributes"]
                attrs[:] = [a for a in attrs if a["key"] != key]
                if value is not None:
                    attrs.append({"key": key, "value": value})
                self.assertEqual(self.collect(payload)[2], [])
        for value in (None, []):
            self.assertEqual(self.collect(fixture(**{"app.version": value}))[2], [])
        payload = fixture()
        resource = payload["resourceLogs"][0]
        resource["schemaUrl"] = CANARY
        scope = resource["scopeLogs"][0]
        scope["schemaUrl"] = CANARY
        scope["scope"]["version"] = CANARY
        record = scope["logRecords"][0]
        record.update(severityText=CANARY, eventName=CANARY, traceId="a" * 32, spanId="b" * 16)
        record["body"] = {"kvlistValue": {"values": [{"key": CANARY, "value": {"stringValue": CANARY}}]}}
        _, docs, spans = self.collect(payload)
        self.assertEqual(len(spans), 1)
        self.assertNotIn("a" * 32, json.dumps(docs))
        self.assertNotIn("b" * 16, json.dumps(docs))

    def test_unknown_named_events_are_fixed_unclassified(self):
        _, docs, spans = self.collect(fixture(event=CANARY, **{"duration_ms": "123", "input_token_count": "456", "event.kind": "response.completed"}))
        self.assertEqual(len(spans), 1)
        timeline = json.loads(next(a["value"]["stringValue"] for a in spans[0]["attributes"] if a["key"].endswith("timeline_json")))
        self.assertEqual(set(timeline[0]), {"name", "time_unix_nano"})
        self.assertEqual(timeline[0]["name"], "codex.event.unclassified")
        self.assertNotIn(CANARY, json.dumps(docs))
        for value in (None, [], "", "x" * 257):
            self.assertEqual(self.collect(fixture(event=value))[2], [])

    def test_numeric_abuse_and_size(self):
        for value in (CANARY, '-1', '10000000000', [], '1.1', '1e2'):
            _, _, spans = self.collect(fixture('codex.tool_result', **{'arguments_length': value, 'arguments': CANARY * 10000}))
            self.assertEqual(len(spans), 1)
            self.assertNotIn('arguments_length', json.dumps(spans))
            self.assertLess(len(json.dumps(spans)), 2048)


if __name__ == '__main__':
    suite = unittest.TestSuite(DiagnosticTests(n) for n in DiagnosticTests.__dict__ if n.startswith('test_'))
    sys.exit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
