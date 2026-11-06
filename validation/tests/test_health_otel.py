"""Allowlist, lineage and fail-closed tests for the optional local-health feed."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location(
    'health_otel', Path(__file__).resolve().parents[2] / 'desktop-dashboard/health_otel.py')
health = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(health)


def sample():
    return {'timing': {'start_ns': 1000000000, 'end_ns': 2000000000},
            'services': [{'name': 'langfuse', 'healthy': True, 'owned': True,
                          'started_ns': 1100000000, 'ended_ns': 1200000000, 'http_status': 200}],
            'private_extra': {'prompt': 'PRIVATE_CONTENT', 'secret': 'PRIVATE_KEY'}}


class HealthTraceContracts(unittest.TestCase):
    def test_only_allowlisted_fields_are_exported_with_real_lineage(self):
        payload = health.make_payload(sample())
        self.assertNotIn('PRIVATE', json.dumps(payload))
        spans = payload['resourceSpans'][0]['scopeSpans'][0]['spans']
        self.assertEqual(len(spans), 2)
        self.assertEqual(spans[0]['traceId'], spans[1]['traceId'])
        self.assertEqual(spans[1]['parentSpanId'], spans[0]['spanId'])
        self.assertEqual(spans[1]['startTimeUnixNano'], '1100000000')
        self.assertEqual(len(spans[0]['traceId']), 32)
        self.assertNotIn('schemaUrl', json.dumps(payload))

    def test_unowned_destination_never_receives_credentials(self):
        source = sample()
        source['services'][0]['owned'] = False
        exporter = health.HealthExporter('/missing/credential', 13000)
        with patch.object(health, 'build_opener', side_effect=AssertionError('Must not connect')):
            result = exporter.publish(source)
        self.assertEqual(result['skipped_batches'], 1)
        self.assertEqual(result['accepted_spans'], 0)

    def test_accepted_batch_uses_v4_and_keeps_credentials_out_of_status(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'credential.json'
            path.write_text(json.dumps({'public_key': 'fixture', 'secret_key': 'PRIVATE_KEY'}))
            response = io.BytesIO(b'{}')
            response.status = 200
            opener = Mock()
            opener.open.return_value = response
            exporter = health.HealthExporter(path, 13000)
            with patch.object(health, 'build_opener', return_value=opener):
                result = exporter.publish(sample())
            request = opener.open.call_args.args[0]
            self.assertEqual(request.full_url, 'http://127.0.0.1:13000/api/public/otel/v1/traces')
            self.assertEqual(request.get_header('X-langfuse-ingestion-version'), '4')
            self.assertEqual(result['accepted_spans'], 2)
            self.assertNotIn('PRIVATE', json.dumps(result))

    def test_rejected_or_uncertain_batch_is_not_reported_as_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'credential.json'
            path.write_text(json.dumps({'public_key': 'fixture', 'secret_key': 'fixture'}))
            opener = Mock()
            opener.open.side_effect = OSError('private error text')
            exporter = health.HealthExporter(path, 13000)
            with patch.object(health, 'build_opener', return_value=opener):
                result = exporter.publish(sample())
            self.assertEqual(result['failed_batches'], 1)
            self.assertEqual(result['accepted_spans'], 0)
            self.assertNotIn('private error', json.dumps(result))


if __name__ == '__main__':
    unittest.main()
