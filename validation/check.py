#!/usr/bin/env python3
"""Docker-only entrypoint: static offline lint, or bounded public-artifact tests."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from setup import ACTIONS, main as setup_main

ROOT = Path(__file__).resolve().parents[1]


def run(root, *args):
    print('+ ' + ' '.join(str(arg) for arg in args), flush=True)
    subprocess.run(args, cwd=root, check=True)


class SafeParser(argparse.ArgumentParser):
    def error(self, _message):
        self.exit(2, 'BLOCKED: unsupported validation arguments.\n')


def main():
    parser = SafeParser(description=__doc__)
    parser.add_argument('stage', choices=('lint', 'contracts', 'collector-runtime', 'setup'))
    parser.add_argument('--bundle', choices=('all', 'primary', 'application'), default='all')
    parser.add_argument('--action', choices=ACTIONS)
    args = parser.parse_args()
    if not Path('/.dockerenv').exists():
        parser.exit(2, 'BLOCKED: use sh validation/run.sh; no host validation fallback.\n')
    if args.stage == 'setup':
        if args.action is None or args.bundle != 'all':
            parser.error('setup requires only its action')
        raise SystemExit(setup_main(args.action))
    if args.action is not None:
        parser.error('action only applies to setup')
    if args.stage == 'lint':
        run(ROOT, sys.executable, 'validation/lint.py')
        run(ROOT, sys.executable, '-m', 'unittest', 'discover', '-s', 'validation/tests', '-v')
        return
    if args.stage == 'collector-runtime':
        run(ROOT, sys.executable, 'validation/collector_runtime.py')
        run(ROOT, sys.executable, 'validation/conversation_runtime.py')
        run(ROOT, sys.executable, 'validation/native_message_runtime.py')
        run(ROOT, sys.executable, 'validation/central_native_message_runtime.py')
        run(ROOT, sys.executable, 'validation/native_event_runtime.py')
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
