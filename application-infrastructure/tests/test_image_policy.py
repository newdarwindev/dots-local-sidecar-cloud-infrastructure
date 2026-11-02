import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('image_policy', ROOT / 'scripts/image_policy.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class ImagePolicyTests(unittest.TestCase):
    def setUp(self):
        self.lock = json.loads((ROOT / 'images.lock.json').read_text())
        self.image = policy.locked_image(self.lock['images']['collector'])

    def workload(self, image, field='containers', kind='Deployment'):
        return {'kind': kind, 'metadata': {'name': 'otel-collector'},
                'spec': {'template': {'spec': {field: [{'image': image}]}}}}

    def test_exact_image_and_binary_source(self):
        self.assertEqual(policy.validate_images([self.workload(self.image)], self.lock, self.image), [self.image])

    def test_unlisted_digest_in_every_container_type_and_hook(self):
        for field in ('containers', 'initContainers', 'ephemeralContainers'):
            for kind in ('Deployment', 'StatefulSet', 'Job'):
                bad = self.image.split('@')[0] + '@sha256:' + '0' * 64
                with self.subTest(field=field, kind=kind), self.assertRaises(ValueError):
                    policy.validate_images([self.workload(bad, field, kind)], self.lock)

    def test_same_digest_wrong_repository_denied(self):
        with self.assertRaises(ValueError):
            policy.validate_images([self.workload('evil.example/copied@' + self.image.split('@')[1])], self.lock)

    def test_other_allowlisted_image_cannot_replace_collector(self):
        wrong = policy.locked_image(self.lock['images']['homarr'])
        with self.assertRaises(ValueError):
            policy.validate_images([self.workload(wrong)], self.lock, self.image)
        with self.assertRaises(ValueError):
            policy.validate_images([self.workload(self.image)], self.lock, wrong)

    def test_missing_floating_or_malformed_digest_denied(self):
        for image in (None, 'otel/image:latest', self.image + 'x'):
            with self.assertRaises(ValueError):
                policy.validate_images([self.workload(image)], self.lock)

    def test_registry_aliases_and_tag_normalization(self):
        digest = '@sha256:' + 'a' * 64
        expected = 'docker.io/library/postgres' + digest
        for prefix in ('postgres:18', 'docker.io/postgres:18', 'registry-1.docker.io/library/postgres:18'):
            self.assertEqual(policy.canonical_image(prefix + digest), expected)
