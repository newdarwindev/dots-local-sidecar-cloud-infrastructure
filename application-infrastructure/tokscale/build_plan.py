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
    from prepare_source import tree_digest
    lock = json.loads(Path(__file__).with_name('source.lock.json').read_text())
    images = json.loads(Path(__file__).with_name('images.lock.json').read_text())['images']
    if args.bun_image != 'oven/bun@' + images['bun']['digest']:
        parser.error('Bun digest does not match the reviewed image lock')
    if tree_digest(source) != lock['preparedTreeSha256']:
        parser.error('complete prepared source tree differs from reviewed archive/privacy patch')
    print(json.dumps({'status': 'build-plan-only-not-executed',
                      'sourceRevision': lock['commit'],
                      'fullSourceTreeVerified': True,
                      'preparedTreeSha256': lock['preparedTreeSha256'],
                      'command': ['docker', 'build', '--platform', args.platform,
                                  '--build-arg', 'BUN_IMAGE=' + args.bun_image,
                                  '-f', str(Path(__file__).with_name('Dockerfile').resolve()),
                                  str(source)]}, indent=2))


if __name__ == '__main__':
    main()
