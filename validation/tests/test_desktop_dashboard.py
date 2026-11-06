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
