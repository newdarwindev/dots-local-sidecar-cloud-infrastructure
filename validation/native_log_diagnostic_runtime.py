"""No live producers: numeric native logs, including Collector stderr canaries."""
import json
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
        for key, value in [('event.timestamp', CANARY), ('event.timestamp', '2026-99-99T99:99:99.000Z'), ('event.timestamp', None), ('event.timestamp', []), ('event.name', CANARY), ('conversation.id', CANARY), ('app.version', CANARY)]:
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

    def test_numeric_abuse_and_size(self):
        for value in (CANARY, '-1', '10000000000', [], '1.1', '1e2'):
            _, _, spans = self.collect(fixture('codex.tool_result', **{'arguments_length': value, 'arguments': CANARY * 10000}))
            self.assertEqual(len(spans), 1)
            self.assertNotIn('arguments_length', json.dumps(spans))
            self.assertLess(len(json.dumps(spans)), 2048)


if __name__ == '__main__':
    suite = unittest.TestSuite(DiagnosticTests(n) for n in DiagnosticTests.__dict__ if n.startswith('test_'))
    sys.exit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
