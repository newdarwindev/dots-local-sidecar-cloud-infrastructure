#!/usr/bin/env python3
"""Container-only synthetic contract and checksum-pinned chart validation."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if not Path('/.dockerenv').exists():
    sys.exit('Validation must run in Docker; do not start a daemon to bypass this guard.')

def run(*args):
    subprocess.run(args, check=True, cwd=ROOT)

run(sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v')
run(sys.executable, '-m', 'unittest', 'discover', '-s', 'tokscale', '-p', 'test_*.py', '-v')
run(sys.executable, 'scripts/bundle.py')
run(sys.executable, 'scripts/bundle.py', 'fetch')
with tempfile.TemporaryDirectory() as directory:
    rendered = Path(directory) / 'rendered'
    run(sys.executable, 'scripts/bundle.py', 'render', '--target', str(ROOT / 'fixtures/target.synthetic.json'), '--output', str(rendered))
    report = json.loads((rendered / 'report.json').read_text())
    assert report['resourceCount'] > 5
    assert report['deploymentBlockers'], 'Synthetic fixture must never be deployment-ready'
print('PASS: offline synthetic contracts and pinned chart rendering; deployment remains blocked.')
