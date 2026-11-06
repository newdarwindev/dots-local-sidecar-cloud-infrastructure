"""Pinned tool installer tests; no network or installed binary execution."""
import importlib.util
import io
from pathlib import Path
import tarfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location('install_tools', Path(__file__).parents[1] / 'install_tools.py')
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class BuildGuardTests(unittest.TestCase):
    def test_accepts_only_readonly_lockfile_mount(self):
        target = installer.ROOT / 'tools.lock.json'
        valid = f'123 1 0:1 /tools.lock.json {target} ro,relatime - overlay overlay rw\n'
        for mountinfo, expected in ((valid, True),
                                    (valid.replace('ro,relatime', 'rw,relatime'), False),
                                    (valid.replace(str(target), '/other/tools.lock.json'), False),
                                    ('malformed\n', False), ('', False)):
            with self.subTest(mountinfo=mountinfo), \
                 mock.patch.object(Path, 'is_file', return_value=True), \
                 mock.patch.object(Path, 'is_symlink', return_value=False), \
                 mock.patch.object(Path, 'read_text', return_value=mountinfo):
                self.assertEqual(installer.build_lock_mounted(), expected)

    def test_rejects_missing_or_symlink_lockfile(self):
        for regular, symbolic in ((False, False), (True, True)):
            with self.subTest(regular=regular, symbolic=symbolic), \
                 mock.patch.object(Path, 'is_file', return_value=regular), \
                 mock.patch.object(Path, 'is_symlink', return_value=symbolic), \
                 mock.patch.object(Path, 'read_text') as read:
                self.assertFalse(installer.build_lock_mounted())
                read.assert_not_called()

    def test_unavailable_mountinfo_fails_closed(self):
        with mock.patch.object(Path, 'is_file', return_value=True), \
             mock.patch.object(Path, 'is_symlink', return_value=False), \
             mock.patch.object(Path, 'read_text', side_effect=OSError):
            self.assertFalse(installer.build_lock_mounted())

    def test_host_refusal_precedes_download_or_install(self):
        with mock.patch.object(Path, 'exists', return_value=False), \
             mock.patch.object(installer, 'build_lock_mounted', return_value=False), \
             mock.patch.object(installer, 'download') as download, \
             mock.patch.object(Path, 'write_bytes') as write:
            with self.assertRaisesRegex(SystemExit, 'Docker-build-only'):
                installer.main()
            download.assert_not_called()
            write.assert_not_called()


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
