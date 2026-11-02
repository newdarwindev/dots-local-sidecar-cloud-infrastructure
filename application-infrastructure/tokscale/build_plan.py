#!/usr/bin/env python3
"""Validate mandatory digest inputs and print a build command; never execute it."""
import argparse
import json
from pathlib import Path
import re


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bun-image', required=True)
    parser.add_argument('--source', required=True, type=Path,
                        help='complete independently verified locked upstream source tree')
    parser.add_argument('--platform', required=True, choices=['linux/amd64', 'linux/arm64'])
    args = parser.parse_args()
    if not re.fullmatch(r'oven/bun@sha256:[0-9a-f]{64}', args.bun_image):
        parser.error('verified oven/bun SHA256 digest required; floating tags are refused')
    source = args.source.resolve()
    if not source.is_dir():
        parser.error('verified source tree directory must already exist')
    # Partial file checks catch accidental source mismatch; they are expressly NOT
    # a full source-tree attestation. Full-source provenance remains an activation gate.
    lock = json.loads(Path(__file__).with_name('source.lock.json').read_text())
    import hashlib
    for relative, digest in lock['files'].items():
        path = source / relative
        if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            parser.error('locked inspected-source file mismatch; stop for source review')
    print(json.dumps({'status': 'build-plan-only-not-executed',
                      'sourceRevision': lock['commit'],
                      'fullSourceAttestationRequired': True,
                      'command': ['docker', 'build', '--platform', args.platform,
                                  '--build-arg', 'BUN_IMAGE=' + args.bun_image,
                                  '-f', str(Path(__file__).with_name('Dockerfile').resolve()),
                                  str(source)]}, indent=2))


if __name__ == '__main__':
    main()
