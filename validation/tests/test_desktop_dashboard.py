"""Desktop geometry and fail-closed local connection contracts; no live cluster."""
import importlib.util
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    'desktop_dashboard', Path(__file__).resolve().parents[2] / 'desktop-dashboard/dashboard.py')
dashboard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dashboard)


def configured():
    return {'cluster': {'context': 'example', 'system_namespace_uid': 'system-fixture',
                        'namespace_uids': {'example-lab': 'lab-fixture'}},
            'forwards': [{'id': 'homarr', 'namespace': 'example-lab', 'service': 'homarr',
                          'local_port': 17575, 'remote_port': 7575}],
            'links': [{'id': 'homarr', 'name': 'Homarr', 'forward': 'homarr'}]}


class DesktopContracts(unittest.TestCase):
    def test_window_observation_handles_byte_titles_as_json(self):
        import json
        window = object.__new__(dashboard.DesktopWindow)
        window.window = types.SimpleNamespace(
            get_geometry=lambda: types.SimpleNamespace(width=632, height=1120),
            get_full_property=lambda *a: types.SimpleNamespace(value=[3]),
            get_wm_name=lambda: b'Homarr')
        window.root = types.SimpleNamespace(translate_coords=lambda *a: types.SimpleNamespace(x=112, y=56))
        window.atom = lambda name: name
        window.Xatom = types.SimpleNamespace(CARDINAL=6)
        result = json.loads(json.dumps(window.observed_state()))
        self.assertEqual(result['title'], 'Homarr')
        self.assertEqual(result['actual_workspace'], 3)
        self.assertEqual(result['actual_geometry'], [112, 56, 632, 1120])

    def test_workspace_and_three_columns(self):
        config = configured()
        config['workspace'] = 3
        self.assertEqual(dashboard.validate_config(config)['workspace'], 3)
        for invalid in (-1, 32, True, '4'):
            config['workspace'] = invalid
            with self.assertRaises(ValueError):
                dashboard.validate_config(config)
        boxes = dashboard.pane_geometries((112, 56, 1296, 1120), [50, 22, 28])
        self.assertEqual(len(boxes), 3)
        for a, b in zip(boxes, boxes[1:]):
            self.assertEqual(a[0] + a[2] + 16, b[0])
        self.assertEqual(boxes[-1][0] + boxes[-1][2], 1408)

    def test_https_forward_uses_localhost_and_scoped_health_path(self):
        config = configured()
        config['forwards'][0].update({'scheme': 'https', 'health_path': '/healthz'})
        dashboard.validate_config(config)
        with tempfile.TemporaryDirectory() as directory:
            forward = dashboard.Forward(config['forwards'][0], config['cluster'], Path(directory))
            try:
                self.assertEqual(forward.origin, 'https://localhost:17575')
                self.assertEqual(forward.health_url, 'https://localhost:17575/healthz')
            finally:
                forward.close()

    def test_invalid_forward_scheme_and_health_path_are_rejected(self):
        for key, value in [('scheme', 'file'), ('scheme', ['https']), ('health_path', '//outside'),
                           ('health_path', '/healthz?token=x')]:
            config = configured()
            config['forwards'][0][key] = value
            with self.assertRaises(ValueError):
                dashboard.validate_config(config)

    def test_orphan_cleanup_excludes_active_or_unrelated_browsers(self):
        profile = Path('/home/example/.surf/desktop-dashboard')
        args = ['surf', '-c', str(profile / 'cookies.txt')]
        self.assertTrue(dashboard.orphaned_pane(args, 1, '/usr/bin/surf', profile))
        self.assertFalse(dashboard.orphaned_pane(args, 200, '/usr/bin/surf', profile))
        self.assertFalse(dashboard.orphaned_pane(args, 1, '/usr/bin/firefox', profile))
        self.assertFalse(dashboard.orphaned_pane(['surf', '-c', '/home/example/cookies.txt'],
                                               1, '/usr/bin/surf', profile))

    def test_conky_gap_and_second_monitor_coordinates(self):
        self.assertEqual(dashboard.geometry((0, 0, 1920, 1200), (1450, 17, 470, 1013)),
                         (112, 56, 1296, 1120))
        self.assertEqual(dashboard.geometry((1920, 0, 1920, 1200), (3370, 17, 470, 923)),
                         (2032, 56, 1296, 1120))

    def test_small_screen_never_overlaps_conky(self):
        left, _top, width, _height = dashboard.geometry((0, 0, 1024, 768), (620, 0, 404, 700))
        self.assertLessEqual(left + width, 620 - 42)
        with self.assertRaises(ValueError):
            dashboard.geometry((0, 0, 400, 600), (160, 0, 240, 500))

    def test_side_by_side_panes_reserve_gap_and_conky_space(self):
        boxes = dashboard.pane_geometries((112, 56, 1296, 1120), [70, 30])
        self.assertEqual(boxes, [(112, 56, 896, 1120), (1024, 56, 384, 1120)])
        self.assertEqual(boxes[-1][0] + boxes[-1][2], 1408)
        self.assertEqual(dashboard.pane_geometries((112, 56, 1296, 1120), [1]), [(112, 56, 1296, 1120)])

    def test_small_displays_stack_panes_without_overlap(self):
        boxes = dashboard.pane_geometries((24, 56, 300, 700), [70, 30])
        self.assertEqual(boxes[0][0], boxes[1][0])
        self.assertEqual(boxes[0][2], 300)
        self.assertLessEqual(boxes[0][1] + boxes[0][3] + 16, boxes[1][1])
        self.assertLessEqual(boxes[-1][1] + boxes[-1][3], 756)

    def test_unknown_duplicate_and_nonfinite_panes_are_rejected(self):
        for panes in [[], [{'link': 'missing'}], [{'link': 'homarr'}, {'link': 'homarr'}],
                      [{'link': 'homarr', 'weight': float('nan')}], [{'link': 'homarr', 'zoom': 0}]]:
            config = configured()
            config['panes'] = panes
            with self.assertRaises(ValueError):
                dashboard.validate_config(config)

    def test_langfuse_preferences_are_scoped_and_use_native_intervals(self):
        script = dashboard.langfuse_preferences('http://127.0.0.1:13000/project/fixture/traces', 30000)
        self.assertIn('location.origin !== preference.origin', script)
        self.assertIn('tableRefreshInterval-events-', script)
        self.assertIn('"project": "fixture"', script)
        self.assertIn('"interval": 30000', script)
        self.assertIn("sessionStorage.getItem(marker)", script)
        for url in ['file:///private/test', 'http://127.0.0.1:13000/']:
            with self.assertRaises(ValueError):
                dashboard.langfuse_preferences(url, 30000)

    def test_refresh_rejects_unsupported_fast_interval(self):
        config = configured()
        config['panes'] = [{'link': 'homarr', 'langfuse_refresh_ms': 1000}]
        with self.assertRaises(ValueError):
            dashboard.validate_config(config)

    def test_all_history_requires_boolean_and_refresh_interval(self):
        for pane in [{'link': 'homarr', 'langfuse_all_history': True},
                     {'link': 'homarr', 'langfuse_refresh_ms': 30000,
                      'langfuse_all_history': 'true'}]:
            config = configured()
            config['panes'] = [pane]
            with self.assertRaises(ValueError):
                dashboard.validate_config(config)
        config['panes'] = [{'link': 'homarr', 'langfuse_all_history': True,
                            'langfuse_refresh_ms': 30000}]
        dashboard.validate_config(config)

    def test_no_forwards_without_cluster_pins(self):
        config = configured()
        del config['cluster']['system_namespace_uid']
        with self.assertRaises(ValueError):
            dashboard.validate_config(config)

    def test_duplicate_ports_and_unpinned_namespaces_fail(self):
        config = configured()
        config['forwards'].append(dict(config['forwards'][0], id='other'))
        with self.assertRaises(ValueError):
            dashboard.validate_config(config)
        config = configured()
        config['forwards'][0]['namespace'] = 'other-lab'
        with self.assertRaises(ValueError):
            dashboard.validate_config(config)

    def test_links_cannot_select_unowned_origins(self):
        for link in [{'id': 'app', 'url': 'http://example.invalid'},
                     {'id': 'app', 'url': 'https://user:secret@example.invalid'},
                     {'id': 'app', 'forward': 'missing'},
                     {'id': 'app', 'forward': 'homarr', 'path': '//example.invalid'}]:
            config = configured()
            config['links'] = [link]
            with self.assertRaises(ValueError):
                dashboard.validate_config(config)

    def test_changed_cluster_and_namespace_identities_fail_closed(self):
        config = configured()
        with patch.object(dashboard.subprocess, 'run', return_value=types.SimpleNamespace(returncode=0, stdout='wrong')) as run:
            self.assertFalse(dashboard.cluster_matches(config['cluster'], 'example-lab'))
            self.assertEqual(run.call_count, 1)
        with patch.object(dashboard.subprocess, 'run', side_effect=[
                types.SimpleNamespace(returncode=0, stdout='system-fixture'),
                types.SimpleNamespace(returncode=0, stdout='wrong')]):
            self.assertFalse(dashboard.cluster_matches(config['cluster'], 'example-lab'))

    def test_navigation_reuses_matching_pane_and_rejects_arbitrary_urls(self):
        specs = [{'link': 'langfuse'}, {'link': 'homarr'}]
        records = [{'id': 'langfuse', 'url': 'http://127.0.0.1:13000/'},
                   {'id': 'overview', 'url': 'http://127.0.0.1:17600/'},
                   {'id': 'homarr', 'url': None}]
        self.assertEqual(dashboard.navigation_targets('open:langfuse', specs, records, 'file:///hub'),
                         [(0, 'http://127.0.0.1:13000/')])
        self.assertEqual(dashboard.navigation_targets('open:overview', specs, records, 'file:///hub'),
                         [(1, 'http://127.0.0.1:17600/')])
        self.assertEqual(dashboard.navigation_targets('restore', specs, records, 'file:///hub'),
                         [(0, 'http://127.0.0.1:13000/'), (1, 'file:///hub')])
        self.assertEqual(dashboard.navigation_targets('open:https://evil.invalid', specs, records, 'hub'), [])

    def test_overview_link_requires_owned_child_and_stays_inactive_when_stopped(self):
        config = configured()
        config['overview'] = {'port': 17600}
        forward = types.SimpleNamespace(ready=True, origin='http://127.0.0.1:17575')
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            for owned, running, expected in [(False, True, None), (True, False, None),
                                             (True, True, 'http://127.0.0.1:17600/')]:
                records = dashboard.write_hub(state, config, {'homarr': forward},
                                              running=running, overview_ready=owned)
                self.assertEqual(next(x for x in records if x['id'] == 'overview')['url'], expected)

    def test_overview_requires_recent_successful_status_response(self):
        import io
        config = {'overview': {'port': 17600}}
        for stamp, expected in [('1970-01-01T00:00:00+00:00', False),
                                (dashboard.datetime.now(dashboard.timezone.utc).isoformat(), True)]:
            body = io.BytesIO(('{"observed_at":"' + stamp + '"}').encode())
            opener = types.SimpleNamespace(open=lambda *a, **k: body)
            with patch.object(dashboard, 'build_opener', return_value=opener):
                self.assertEqual(dashboard.overview_healthy(config), expected)

    def test_pane_recovers_destination_after_initial_forward_failure(self):
        calls = []
        pane = dashboard.BrowserPane({'link': 'homarr'}, 0, [1], Path('/tmp'), 'hub', None)
        pane.child = types.SimpleNamespace(poll=lambda: None)
        pane.window = types.SimpleNamespace(placement=lambda: None, home_pressed=lambda: False,
                                            navigate=calls.append)
        pane.waiting_for_link = True
        pane.update([{'id': 'homarr', 'url': None}])
        self.assertEqual(calls, [])
        pane.update([{'id': 'homarr', 'url': 'http://127.0.0.1:17575/'}])
        pane.update([{'id': 'homarr', 'url': 'http://127.0.0.1:17575/'}])
        self.assertEqual(calls, ['http://127.0.0.1:17575/'])

    def test_hub_disables_unowned_forward_and_escapes_labels(self):
        config = configured()
        config['links'][0]['name'] = '<script>bad</script>'
        forward = types.SimpleNamespace(ready=False, origin='http://127.0.0.1:17575')
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            records = dashboard.write_hub(state, config, {'homarr': forward})
            page = (state / 'home.html').read_text()
            self.assertIsNone(records[0]['url'])
            self.assertNotIn('<a href=', page)
            self.assertIn('&lt;script&gt;', page)
            forward.ready = True
            records = dashboard.write_hub(state, config, {'homarr': forward})
            self.assertEqual(records[0]['url'], 'http://127.0.0.1:17575/')


if __name__ == '__main__':
    unittest.main()
