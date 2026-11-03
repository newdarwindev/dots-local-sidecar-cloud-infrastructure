"""Pinned tool installer tests; no network or installed binary execution."""
import importlib.util
import io
from pathlib import Path
import tarfile
import unittest

SPEC = importlib.util.spec_from_file_location('install_tools', Path(__file__).parents[1] / 'install_tools.py')
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class ArchiveTests(unittest.TestCase):
    def archive(self, symbolic=False, duplicate=False):
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode='w:gz') as archive:
            for _ in range(2 if duplicate else 1):
                member = tarfile.TarInfo('tool')
                if symbolic:
                    member.type = tarfile.SYMTYPE
                    member.linkname = '/etc/passwd'
                    archive.addfile(member)
                else:
                    member.size = 4
                    archive.addfile(member, io.BytesIO(b'test'))
        return output.getvalue()

    def test_extracts_only_locked_regular_member(self):
        self.assertEqual(installer.binary_bytes(self.archive(), {'format': 'tar.gz', 'member': 'tool'}), b'test')

    def test_rejects_symlink_duplicate_and_missing_member(self):
        for payload, member in ((self.archive(symbolic=True), 'tool'),
                                (self.archive(duplicate=True), 'tool'),
                                (self.archive(), 'absent')):
            with self.assertRaises(ValueError):
                installer.binary_bytes(payload, {'format': 'tar.gz', 'member': member})

    def test_non_https_or_missing_hash_rejected_before_fetch(self):
        for item in ({'url': 'http://example.invalid/tool', 'sha256': 'a' * 64},
                     {'url': 'https://example.invalid/tool', 'sha256': 'bad'}):
            with self.assertRaises(ValueError):
                installer.download(item)


if __name__ == '__main__':
    unittest.main()
