#!/usr/bin/env python3
"""Docker-only entrypoint: static offline lint, or bounded public-artifact tests."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(root, *args):
    print('+ ' + ' '.join(str(arg) for arg in args), flush=True)
    subprocess.run(args, cwd=root, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('lint', 'contracts'))
    parser.add_argument('--bundle', choices=('all', 'primary', 'application'), default='all')
    args = parser.parse_args()
    if not Path('/.dockerenv').exists():
        parser.exit(2, 'BLOCKED: use sh validation/run.sh; no host validation fallback.\n')
    if args.stage == 'lint':
        run(ROOT, sys.executable, 'validation/lint.py')
        run(ROOT, sys.executable, '-m', 'unittest', 'discover', '-s', 'validation/tests', '-v')
        return
    # Bundle tests cache public archives; writes stay in ephemeral container tmpfs.
    with tempfile.TemporaryDirectory(prefix='infra-contracts-') as directory:
        root = Path(directory) / 'repo'
        shutil.copytree(ROOT, root)
        if args.bundle in ('all', 'primary'):
            run(root, sys.executable, 'primary-infrastructure/validation/check.py')
        if args.bundle in ('all', 'application'):
            run(root, sys.executable, 'application-infrastructure/validation/check.py')
        run(root, sys.executable, 'validation/kubernetes.py', '--bundle', args.bundle)
    print('PASS: requested Docker-only contracts and schemas; not live acceptance.')


if __name__ == '__main__':
    main()
