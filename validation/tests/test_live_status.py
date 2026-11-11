"""Synthetic status collection tests; no host credentials or cluster queries."""
import importlib.util
import io
import json
import re
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

SPEC = importlib.util.spec_from_file_location(
    'live_status', Path(__file__).resolve().parents[2] / 'desktop-dashboard/live_status.py')
status = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(status)


class LiveStatusContracts(unittest.TestCase):
    def test_dashboard_scripts_parse_and_all_render_targets_exist(self):
        scripts = re.findall(r'<script>(.*?)</script>', status.PAGE, re.S)
        self.assertEqual(len(scripts), 1)
        parsed = subprocess.run(['biome', 'format', '--stdin-file-path=dashboard.js'],
                                input=scripts[0], text=True, capture_output=True, check=False)
        self.assertEqual(parsed.returncode, 0, parsed.stderr)
        ids = re.findall(r'id="([^"]+)"', status.PAGE)
        self.assertEqual(len(ids), len(set(ids)))
        targets = set(re.findall(r"node\('([^']+)'\)", scripts[0]))
        self.assertFalse(targets - set(ids), targets - set(ids))

    def test_stored_activity_excludes_content_and_unrelated_sources(self):
        source = {'name': 'Desktop dashboard health', 'environment': 'local-desktop',
                  'startTime': '2026-11-06T10:00:00Z', 'latency': 0.2, 'level': 'DEFAULT',
                  'input': 'PRIVATE', 'output': 'PRIVATE', 'metadata': {'secret': 'PRIVATE'}}
        rows = status.project_health_activity([source, dict(source, environment='production'),
                                              dict(source, name='private user action'),
                                              dict(source, startTime='bad')])
        self.assertEqual(len(rows), 1)
        self.assertEqual(set(rows[0]), {'name', 'startTime', 'latency', 'level'})
        self.assertNotIn('PRIVATE', json.dumps(rows))
        self.assertIsNone(status.project_health_activity([dict(source, latency={'secret':'PRIVATE'})])[0]['latency'])

    def test_restarting_and_unready_pods_are_not_healthy(self):
        document = {'items': [
            {'metadata': {'name': 'ready'}, 'spec': {'containers': [{}]}, 'status': {
                'phase': 'Running', 'containerStatuses': [{'ready': True, 'restartCount': 3}]}},
            {'metadata': {'name': 'failed'}, 'spec': {'containers': [{}]}, 'status': {
                'phase': 'Running', 'containerStatuses': [{'ready': False, 'restartCount': 9,
                                                          'state': {'waiting': {'reason': 'CrashLoopBackOff'}}}]}},
            {'metadata': {'name': 'job'}, 'status': {'phase': 'Succeeded'}}]}
        rows = {row['name']: row for row in status.pod_rows(document)}
        self.assertTrue(rows['ready']['healthy'])
        self.assertFalse(rows['failed']['healthy'])
        self.assertEqual(rows['failed']['reason'], 'CrashLoopBackOff')
        self.assertEqual(rows['ready']['restarts'], 3)

    def test_identity_change_withholds_workload_data(self):
        config = {'overview': {'namespace': 'fixture-lab'}}
        def forbidden_query(*_args):
            self.fail('Must not query an unverified cluster')
        result = status.collect_snapshot(config, query=forbidden_query, identity_check=lambda _config: False)
        self.assertFalse(result['cluster_verified'])
        self.assertEqual(result['pods'], [])
        self.assertTrue(result['errors'])

    def test_query_failure_is_visible_and_not_a_green_zero(self):
        config = {'overview': {'namespace': 'fixture-lab'}}
        def failed_query(*_args):
            raise RuntimeError('Unavailable')
        result = status.collect_snapshot(config, query=failed_query, identity_check=lambda _config: True)
        self.assertEqual(len(result['errors']), 3)
        self.assertEqual(result['pods'], [])
        self.assertEqual(result['available'], {'pods': False, 'nodes': False, 'pvc': False})

    def test_only_approved_fields_leave_the_collector(self):
        config = {'overview': {'namespace': 'fixture-lab'}}
        def query(_config, kind):
            if kind == 'nodes':
                return {'items': [{'metadata': {'name': 'fixture-node', 'annotations': {'private': 'never-display'}},
                                   'status': {'addresses': [{'address': 'private-address'}],
                                              'conditions': [{'type': 'Ready', 'status': 'True'}],
                                              'nodeInfo': {'kubeletVersion': 'fixture'}}}]}
            return {'items': []}
        result = status.collect_snapshot(config, query=query, identity_check=lambda _config: True)
        encoded = json.dumps(result)
        self.assertNotIn('never-display', encoded)
        self.assertNotIn('private-address', encoded)
        self.assertTrue(result['nodes'][0]['ready'])

    def test_stale_and_invalid_cpu_history_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'history.json'
            path.write_text(json.dumps([{'t': 1000, 'cpu': 5}, {'t': 1100, 'cpu': 999}, {'t': 1200, 'cpu': 12}]))
            result = status.cpu_history(path, 1500)
            self.assertTrue(result['stale'])
            self.assertEqual(len(result['samples']), 2)
            self.assertFalse(status.cpu_history(path, 1250)['stale'])
            path.write_text('not json')
            self.assertTrue(status.cpu_history(path, 1500)['stale'])

    def test_missing_storage_is_unknown_not_zero(self):
        with patch.object(status.os, 'statvfs', side_effect=OSError):
            row = status.storage_rows([{'name': 'fixture', 'path': '/fixture'}])[0]
        self.assertIsNone(row['used_percent'])
        self.assertIsNone(row['available_bytes'])

    def test_downsampling_keeps_latest_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'history.json'
            path.write_text(json.dumps([{'t': 1000+index, 'cpu': index % 100} for index in range(1000)]))
            samples = status.cpu_history(path, 2000)['samples']
            self.assertEqual(samples[-1]['t'], 1999)
            self.assertLessEqual(len(samples), 121)

    def test_unowned_listener_never_receives_diagnostic_credentials(self):
        config = {'overview': {'namespace': 'fixture-lab', 'verification_credentials': '/fixture'},
                  'forwards': [{'id': 'langfuse', 'local_port': 13000}]}
        with patch.object(status, 'verification_summary', side_effect=AssertionError('Must not authenticate')):
            result = status.collect_snapshot(config, query=lambda *_args: {'items': []}, identity_check=lambda _config: True)
        self.assertFalse(result['verification']['available'])

    def test_owned_https_forward_health_check_uses_localhost_path(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'desktop-dashboard'
            state.mkdir()
            (state / 'status.json').write_text(json.dumps({
                'observed_at': status.datetime.now(status.timezone.utc).isoformat(),
                'supervisor_running': True,
                'links': [{'id': 'tokscale', 'status': 'Available locally'}]}))
            config = {'overview': {'namespace': 'fixture-lab', 'storage': []},
                      'forwards': [{'id': 'tokscale', 'local_port': 18445, 'scheme': 'https',
                                    'health_path': '/healthz'}]}
            opener = Mock()
            response = MagicMock()
            response.__enter__.return_value.status = 200
            opener.open.return_value = response
            with patch.dict(status.os.environ, {'XDG_STATE_HOME': directory}), \
                    patch.object(status, 'build_opener', return_value=opener):
                result = status.collect_snapshot(config, query=lambda *_args: {'items': []},
                                                  identity_check=lambda _config: True)
            opener.open.assert_called_once_with('https://localhost:18445/healthz', timeout=2)
        self.assertTrue(result['services'][0]['healthy'])
        self.assertTrue(result['services'][0]['owned'])

    def test_diagnostic_response_never_contains_keys_or_payloads(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic-credentials.json'
            path.write_text(json.dumps({'public_key': 'fixture-public', 'secret_key': 'PRIVATE_KEY', 'project_id': 'fixture-project'}))
            config = {'overview': {'verification_credentials': str(path)},
                      'forwards': [{'id': 'langfuse', 'local_port': 13000}]}
            opener = Mock()
            opener.open.return_value = io.StringIO(json.dumps({'data': [{'traceId': 'one', 'input': 'PRIVATE_PAYLOAD'}, {'traceId': 'one'}]}))
            with patch.object(status, 'build_opener', return_value=opener):
                result = status.verification_summary(config)
        self.assertEqual(result['observations'], 2)
        self.assertEqual(result['traces'], 1)
        self.assertNotIn('PRIVATE', json.dumps(result))


if __name__ == '__main__':
    unittest.main()
