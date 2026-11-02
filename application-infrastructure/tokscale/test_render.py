"""Synthetic-only tests; run inside the bundle validation container."""
import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('tokscale_render', Path(__file__).with_name('render.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RenderTests(unittest.TestCase):
    def config(self):
        return {'namespace': 'synthetic', 'storageClass': 'synthetic',
                'appImage': 'example.invalid/synthetic@sha256:' + '1' * 64,
                'postgresImage': 'example.invalid/synthetic@sha256:' + '2' * 64,
                'origin': 'https://synthetic.example.invalid', 'gatewayPodLabel': 'synthetic-gate',
                'databaseSize': '1Gi'}

    def test_zero_replicas_and_no_secret_material(self):
        items = module.render(self.config())['items']
        self.assertFalse(any(i['kind'] in ('Secret', 'Ingress', 'Job', 'CronJob') for i in items))
        for item in items:
            if item['kind'] in ('Deployment', 'StatefulSet'):
                self.assertEqual(item['spec']['replicas'], 0)
                self.assertFalse(item['spec']['template']['spec']['automountServiceAccountToken'])
            if item['kind'] == 'Service':
                self.assertEqual(item['spec']['type'], 'ClusterIP')
        rendered = json.dumps(items)
        self.assertNotIn('postgresql://', rendered)
        self.assertNotIn('hostPath', rendered)
        self.assertNotIn('LoadBalancer', rendered)

    def test_fail_closed_without_inputs(self):
        for key in self.config():
            config = self.config()
            del config[key]
            with self.assertRaises(KeyError):
                module.render(config)

    def test_floating_images_rejected(self):
        for key in ('appImage', 'postgresImage'):
            config = self.config()
            config[key] = 'postgres:16-alpine'
            with self.assertRaises(ValueError):
                module.render(config)

    def test_origin_injection_rejected(self):
        for value in ('http://example.invalid', 'https://example.invalid/path', 'https://x\nTOKEN=secret'):
            config = self.config()
            config['origin'] = value
            with self.assertRaises(ValueError):
                module.render(config)

    def test_dedicated_database_and_preservation(self):
        items = module.render(self.config())['items']
        pg = next(i for i in items if i['kind'] == 'StatefulSet')
        self.assertEqual(pg['metadata']['name'], 'tokscale-postgres')
        self.assertEqual(pg['spec']['persistentVolumeClaimRetentionPolicy'],
                         {'whenDeleted': 'Retain', 'whenScaled': 'Retain'})
        app = next(i for i in items if i['kind'] == 'Deployment')
        env = app['spec']['template']['spec']['containers'][0]['env']
        database = next(e for e in env if e['name'] == 'DATABASE_URL')
        self.assertEqual(database['valueFrom']['secretKeyRef']['name'], 'tokscale-database')


if __name__ == '__main__':
    unittest.main()
