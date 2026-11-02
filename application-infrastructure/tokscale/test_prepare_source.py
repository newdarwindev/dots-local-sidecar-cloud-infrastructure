"""Synthetic source integrity tests; execute in Docker validation only."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import tarfile
import unittest
from prepare_source import prepare, tree_digest


class SourceTests(unittest.TestCase):
    def source(self, entries=None):
        entries = entries or [('source/layout.tsx', b'keep\nanalytics\n', tarfile.REGTYPE)]
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
            for name, contents, kind in entries:
                info = tarfile.TarInfo(name)
                info.type = kind
                if kind == tarfile.SYMTYPE:
                    info.linkname = '/outside'
                else:
                    info.size = len(contents)
                archive.addfile(info, io.BytesIO(contents))
        data = buffer.getvalue()
        h = hashlib.sha256()
        h.update(b'layout.tsx\0' + hashlib.sha256(b'keep\n').digest())
        lock = {'archive': {'sha256': hashlib.sha256(data).hexdigest(), 'root': 'source'},
                'privacyPatch': {'path': 'layout.tsx', 'removeExactlyOnce': ['analytics\n']},
                'preparedTreeSha256': h.hexdigest()}
        return data, lock

    def test_complete_tree_and_privacy_patch(self):
        data, lock = self.source()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'prepared'
            prepare(data, target, lock)
            self.assertEqual((target / 'layout.tsx').read_text(), 'keep\n')
            self.assertEqual(tree_digest(target), lock['preparedTreeSha256'])
            (target / 'unexpected').write_text('unexpected')
            self.assertNotEqual(tree_digest(target), lock['preparedTreeSha256'])

    def test_archive_hash_mismatch(self):
        data, lock = self.source()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                prepare(data + b'changed', Path(directory) / 'prepared', lock)

    def test_unsafe_paths_and_links(self):
        for name, kind in [('source/../outside', tarfile.REGTYPE), ('/source/file', tarfile.REGTYPE),
                           ('source/link', tarfile.SYMTYPE)]:
            data, lock = self.source([(name, b'x', kind)])
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):
                    prepare(data, Path(directory) / 'prepared', lock)

    def test_existing_tree_never_overwritten(self):
        data, lock = self.source()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                prepare(data, Path(directory), lock)

    def test_duplicate_file_refused(self):
        entry = ('source/layout.tsx', b'keep\nanalytics\n', tarfile.REGTYPE)
        data, lock = self.source([entry, entry])
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                prepare(data, Path(directory) / 'prepared', lock)


if __name__ == '__main__':
    unittest.main()
