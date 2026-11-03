"""Install only hash-verified public binaries into the validation Docker image."""
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parent


def download(item):
    if not item['url'].startswith('https://'):
        raise ValueError('Tool URL must use HTTPS')
    if not re.fullmatch(r'[a-f0-9]{64}', item['sha256']):
        raise ValueError('Missing full tool SHA256')
    with urllib.request.urlopen(item['url'], timeout=90) as response:
        data = response.read(128 * 1024 * 1024 + 1)
    if len(data) > 128 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != item['sha256']:
        raise ValueError('Tool checksum/size mismatch: ' + item['url'])
    return data


def binary_bytes(data, item):
    if item['format'] == 'binary':
        return data
    if item['format'] not in {'tar.gz', 'tar.xz', 'tgz'}:
        raise ValueError('Unsupported tool archive format')
    # Never extract a directory tree, symlink or path supplied by the archive.
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:*') as archive:
        members = [member for member in archive.getmembers() if member.name == item['member']]
        if len(members) != 1 or not members[0].isfile():
            raise ValueError('Tool archive member must be a unique regular file')
        stream = archive.extractfile(members[0])
        if stream is None:
            raise ValueError('Missing tool binary')
        return stream.read()


def main():
    if not Path('/.dockerenv').exists():
        raise SystemExit('Tool installation is Docker-build-only; no host fallback.')
    lock = json.loads((ROOT / 'tools.lock.json').read_text())
    for name, item in lock['binaries'].items():
        if not re.fullmatch(r'[a-z][a-z0-9-]*', name):
            raise ValueError('Unsafe binary name')
        target = Path('/usr/local/bin') / name
        target.write_bytes(binary_bytes(download(item), item))
        target.chmod(0o755)
        print(f'Installed checksum-verified {name} {item["version"]}')


if __name__ == '__main__':
    main()
