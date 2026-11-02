#!/usr/bin/env python3
"""Container-only synthetic contract and checksum-pinned chart validation."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import yaml

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
    documents = [obj for obj in yaml.safe_load_all((rendered / 'manifests.yaml').read_text()) if obj]
    for obj in documents:
        assert obj['kind'] not in {'Ingress', 'CronJob', 'ClusterRole', 'ClusterRoleBinding'}, 'Unexpected exposure, scheduling or cluster permission'
        if obj['kind'] == 'Secret':
            assert not obj.get('data') and not obj.get('stringData'), 'Chart rendered credential material'
        if obj['kind'] == 'Service':
            assert obj['spec'].get('type', 'ClusterIP') == 'ClusterIP', 'Non-private Service'
    collector = yaml.safe_load((ROOT / 'values/collector.yaml').read_text())['alternateConfig']
    assert set(collector['service']['pipelines']) == {'traces'}
    assert set(collector['exporters']) == {'otlphttp/diagnostics'}
    assert collector['receivers']['otlp']['protocols']['http']['tls']['client_ca_file']
    assert report['resourceCount'] > 5
    assert report['deploymentBlockers'], 'Synthetic fixture must never be deployment-ready'
print('PASS: offline synthetic contracts and pinned chart rendering; deployment remains blocked.')
