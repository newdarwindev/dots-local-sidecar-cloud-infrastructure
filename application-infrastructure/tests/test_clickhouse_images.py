"""Synthetic image-contract tests. Docker only; no operator execution."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('image_policy', ROOT / 'scripts/image_policy.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class StructuredImageTests(unittest.TestCase):
    def setUp(self):
        self.lock = json.loads((ROOT / 'images.lock.json').read_text())

    def document(self, kind='ClickHouseCluster', key='clickhouse'):
        selected = self.lock['images'][key]
        repository, tag = selected['tagReference'].rsplit(':', 1)
        return {'apiVersion': 'clickhouse.com/v1alpha1', 'kind': kind,
                'spec': {'containerTemplate': {'image': {
                    'repository': repository, 'tag': tag + '@' + selected['digest']}}}}

    def test_both_structured_images_use_exact_component_locks(self):
        docs = [self.document(), self.document('KeeperCluster', 'keeper')]
        self.assertEqual(len(policy.validate_images(docs, self.lock)), 2)

    def test_tag_only_hash_only_unknown_fields_and_bad_digest_rejected(self):
        for image in ({'repository': 'clickhouse/clickhouse-server', 'tag': 'latest'},
                      {'repository': 'clickhouse/clickhouse-server', 'hash': self.lock['images']['clickhouse']['digest']},
                      {'repository': 'clickhouse/clickhouse-server', 'tag': 'v@sha256:' + '0' * 64},
                      {'repository': 'clickhouse/clickhouse-server', 'tag': 'latest', 'digest': 'unknown'}):
            doc = self.document()
            doc['spec']['containerTemplate']['image'] = image
            with self.assertRaises(ValueError):
                policy.validate_images([doc], self.lock)

    def test_wrong_component_and_api_rejected(self):
        with self.assertRaises(ValueError):
            policy.validate_images([self.document('KeeperCluster', 'clickhouse')], self.lock)
        doc = self.document()
        doc['apiVersion'] = 'clickhouse.com/v1beta1'
        with self.assertRaises(ValueError):
            policy.validate_images([doc], self.lock)
