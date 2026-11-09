#!/usr/bin/env python3
"""Fetch checksum-locked public source, apply exact privacy patch; Docker CI only."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parent


def tree_digest(root):
    digest = hashlib.sha256()
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('symlink in prepared source tree')
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            digest.update(relative.encode() + b'\0' + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def prepare(archive_bytes, destination, lock):
    if destination.exists():
        raise ValueError('destination already exists; refusing overwrite')
    if hashlib.sha256(archive_bytes).hexdigest() != lock['archive']['sha256']:
        raise ValueError('source archive checksum mismatch')
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode='r:gz') as archive:
        entries = []
        seen = set()
        for member in archive:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != lock['archive']['root']:
                raise ValueError('unsafe source archive path')
            if not (member.isfile() or member.isdir()):
                raise ValueError('non-file source archive entry')
            relative = PurePosixPath(*path.parts[1:])
            if member.isfile():
                if str(relative) in seen:
                    raise ValueError('duplicate source file')
                seen.add(str(relative))
                entries.append((relative, archive.extractfile(member).read(), member.mode))
    destination.mkdir(parents=True)
    for relative, contents, mode in entries:
        target = destination / str(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(contents)
        target.chmod(0o755 if mode & 0o111 else 0o644)
    patch = lock['privacyPatch']
    target = destination / patch['path']
    contents = target.read_text()
    for text in patch['removeExactlyOnce']:
        if contents.count(text) != 1:
            raise ValueError('privacy patch source mismatch')
        contents = contents.replace(text, '')
    target.write_text(contents)
    for patch in lock.get('tlsPatches', []):
        target = destination / patch['path']
        if hashlib.sha256(target.read_bytes()).hexdigest() != patch['originalSha256']:
            raise ValueError('TLS patch source checksum mismatch')
        contents = target.read_text()
        for replacement in patch['replacements']:
            if contents.count(replacement['old']) != 1:
                raise ValueError('TLS patch source mismatch')
            contents = contents.replace(replacement['old'], replacement['new'])
        target.write_text(contents)
    for overlay in lock.get('overlayFiles', []):
        contents = (ROOT / overlay['source']).read_bytes()
        if hashlib.sha256(contents).hexdigest() != overlay['sha256']:
            raise ValueError('TLS overlay checksum mismatch')
        target = destination / overlay['path']
        if target.exists():
            raise ValueError('TLS overlay must not replace an existing file')
        target.write_bytes(contents)
    if tree_digest(destination) != lock['preparedTreeSha256']:
        raise ValueError('complete prepared source tree mismatch')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--archive', type=Path, help='optional already-downloaded public source archive')
    args = parser.parse_args()
    lock = json.loads((ROOT / 'source.lock.json').read_text())
    if args.archive:
        payload = args.archive.read_bytes()
    else:
        with urllib.request.urlopen(lock['archive']['url'], timeout=120) as response:
            payload = response.read(64 * 1024 * 1024 + 1)
        if len(payload) > 64 * 1024 * 1024:
            parser.error('source archive exceeds bound')
    try:
        prepare(payload, args.output, lock)
    except ValueError as error:
        parser.exit(2, 'Blocked: ' + str(error) + '; do not build.\n')
    except (OSError, tarfile.TarError):
        parser.exit(2, 'Blocked: source preparation failed; retain output for inspection, do not build.\n')
    print(json.dumps({'status': 'prepared-not-built', 'commit': lock['commit'],
                      'sourceArchiveSha256': lock['archive']['sha256'],
                      'preparedTreeSha256': lock['preparedTreeSha256'],
                      'privacyPatch': 'removed Vercel Analytics import and component'}, indent=2))


if __name__ == '__main__':
    main()
