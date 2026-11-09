"""Static overlay/provenance contracts; execute only in authorized Docker tests."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent


class TlsOverlayTests(unittest.TestCase):
    def test_overlay_hashes_and_three_source_paths(self):
        lock = json.loads((ROOT / 'source.lock.json').read_text())
        self.assertEqual({p['path'] for p in lock['tlsPatches']}, {
            'packages/frontend/src/lib/db/index.ts',
            'packages/frontend/scripts/migrate-core.ts',
            'packages/frontend/drizzle.config.ts',
        })
        for overlay in lock['overlayFiles']:
            self.assertEqual(hashlib.sha256((ROOT / overlay['source']).read_bytes()).hexdigest(), overlay['sha256'])
        helper = (ROOT / 'overlays/tls.ts').read_text()
        for required in ('rejectUnauthorized: true', 'checkServerIdentity', 'DATABASE_CA_FILE', 'url.search', 'isIP(url.hostname)'):
            self.assertIn(required, helper)

    def test_public_fixture_provenance(self):
        directory = ROOT / 'fixtures/tls-public'
        lock = json.loads((directory / 'provenance.json').read_text())
        self.assertEqual(lock['source'], 'https://github.com/nodejs/node/tree/v24.11.0/test/fixtures/keys')
        for name, sha in lock['files'].items():
            self.assertEqual(hashlib.sha256((directory / name).read_bytes()).hexdigest(), sha)
        self.assertIn('public', lock['purpose'].lower())


if __name__ == '__main__':
    unittest.main()
