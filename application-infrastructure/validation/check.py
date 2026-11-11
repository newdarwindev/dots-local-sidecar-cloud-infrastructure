#!/usr/bin/env python3
"""Container-only synthetic contract and checksum-pinned chart validation."""
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from image_policy import validate_images
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
    target = json.loads((ROOT / 'fixtures/target.synthetic.json').read_text())
    claims = []
    for obj in documents:
        spec = obj.get('spec', {})
        if obj['kind'] == 'PersistentVolumeClaim':
            claims.append(spec)
        if obj['kind'] == 'StatefulSet':
            claims.extend(claim['spec'] for claim in spec.get('volumeClaimTemplates', []))
        if obj['kind'] in {'ClickHouseCluster', 'KeeperCluster'}:
            claims.append(spec['dataVolumeClaimSpec'])
    # Six locked persistence sites: PostgreSQL, Valkey, ClickHouse, Keeper,
    # SeaweedFS and Homarr. Catch missing/defaulted fields, not just CLI flags.
    assert len(claims) == 6, 'Locked bundle persistence inventory changed; review storage wiring'
    assert all(claim.get('storageClassName') == target['storageClass'] for claim in claims), 'Selected StorageClass did not reach every rendered claim'
    langfuse_deployments = [obj for obj in documents if obj['kind'] == 'Deployment'
                           and obj['metadata']['name'] in {'langfuse-web', 'langfuse-worker'}]
    assert len(langfuse_deployments) == 2, 'Expected Langfuse web and worker Deployments'
    for deployment in langfuse_deployments:
        containers = deployment['spec']['template']['spec']['containers']
        environments = [item for container in containers for item in container.get('env', [])]
        assert not any(item['name'].startswith('LANGFUSE_S3_MEDIA_') for item in environments), 'Disabled media configuration was emitted'
        assert any(item['name'] == 'LANGFUSE_S3_EVENT_UPLOAD_BUCKET' and item.get('value') == 'langfuse-events'
                   for item in environments), 'Media correction changed required event ingestion'
        assert any(item['name'] == 'LANGFUSE_S3_BATCH_EXPORT_ENABLED' and item.get('value') == 'false'
                   for item in environments), 'Batch export must remain disabled'
    dockerfile = (ROOT / 'validation/Dockerfile').read_text()
    sources = re.findall(r'^FROM (\S+) AS collector$', dockerfile, re.MULTILINE)
    assert len(sources) == 1, 'Expected one digest-pinned Collector binary source'
    validate_images(documents, json.loads((ROOT / 'images.lock.json').read_text()), sources[0])
    for obj in documents:
        assert obj['kind'] not in {'Ingress', 'CronJob', 'ClusterRole', 'ClusterRoleBinding'}, 'Unexpected exposure, scheduling or cluster permission'
        if obj['kind'] == 'Job':
            assert obj['metadata']['name'] == 'langfuse-bucket-hook'
            pod = obj['spec']['template']['spec']
            assert pod['automountServiceAccountToken'] is False
            assert pod['serviceAccountName'] == 'langfuse-seaweedfs'
        if obj['kind'] == 'Secret':
            assert not obj.get('data') and not obj.get('stringData'), 'Chart rendered credential material'
        if obj['kind'] == 'Service':
            assert obj['spec'].get('type', 'ClusterIP') == 'ClusterIP', 'Non-private Service'
    configs = [obj['data']['relay'] for obj in documents if obj['kind'] == 'ConfigMap' and obj['metadata']['name'] == 'otel-collector']
    assert len(configs) == 1, 'Expected exactly one rendered Collector config'
    collector_config = Path(directory) / 'collector.yaml'
    collector_config.write_text(configs[0])
    environment = dict(os.environ, MY_POD_IP='127.0.0.1',
                       LANGFUSE_DIAGNOSTIC_AUTHORIZATION='Basic SYNTHETIC_NOT_A_CREDENTIAL',
                       LANGFUSE_DIAGNOSTIC_TRACES_ENDPOINT='https://127.0.0.1:4319/api/public/otel/v1/traces')
    version = subprocess.run(['otelcol-contrib', '--version'], check=True, capture_output=True, text=True).stdout
    assert '0.163.2' in version, 'Collector binary/version lock mismatch'
    subprocess.run(['otelcol-contrib', 'validate', '--config', str(collector_config)], check=True, env=environment)
    native = list(yaml.safe_load_all((ROOT / 'native-monitoring/collector.yaml').read_text()))
    native_config = next(obj['data']['collector.yaml'] for obj in native if obj['kind'] == 'ConfigMap')
    collector_config.write_text(native_config)
    environment['LANGFUSE_TRACES_ENDPOINT'] = environment['LANGFUSE_DIAGNOSTIC_TRACES_ENDPOINT']
    subprocess.run(['otelcol-contrib', 'validate', '--config', str(collector_config)], check=True, env=environment)
    assert set(yaml.safe_load(native_config)['service']['pipelines']) == {'traces'}
    tls_documents = list(yaml.safe_load_all((ROOT / 'native-monitoring/langfuse-tls.yaml').read_text()))
    caddy_config = Path(directory) / 'Caddyfile'
    caddy_config.write_text(next(obj['data']['Caddyfile'] for obj in tls_documents if obj['kind'] == 'ConfigMap'))
    subprocess.run(['caddy', 'adapt', '--adapter', 'caddyfile', '--config', str(caddy_config)], check=True, stdout=subprocess.DEVNULL)
    gateway_documents = list(yaml.safe_load_all((ROOT / 'native-monitoring/tokscale-private-gateway.yaml').read_text()))
    gateway_caddy = next(obj['data']['Caddyfile'] for obj in gateway_documents if obj['kind'] == 'ConfigMap')
    assert all(path in gateway_caddy for path in ('/api/submit', '/api/auth/token',
                                                   '/api/auth/github/callback', '/healthz'))
    assert 'handle_path /api/*' not in gateway_caddy
    caddy_config.write_text(gateway_caddy)
    test_hash = subprocess.run(['caddy', 'hash-password', '--plaintext', 'synthetic-gateway-fixture'],
                               check=True, capture_output=True, text=True).stdout.strip()
    subprocess.run(['caddy', 'adapt', '--adapter', 'caddyfile', '--config', str(caddy_config)],
                   check=True, stdout=subprocess.DEVNULL,
                   env=dict(environment, TOKSCALE_GATEWAY_PASSWORD_HASH=test_hash))
    print('PASS: exact digest-pinned Collector 0.163.2 validates rendered configuration; no service started.')
    collector = yaml.safe_load((ROOT / 'values/collector.yaml').read_text())['alternateConfig']
    assert set(collector['service']['pipelines']) == {'traces'}
    assert set(collector['exporters']) == {'otlphttp/diagnostics'}
    assert collector['receivers']['otlp']['protocols']['http']['tls']['client_ca_file']
    assert report['resourceCount'] > 5
    assert report['deploymentBlockers'], 'Synthetic fixture must never be deployment-ready'
    scalar_target = dict(target, namespace='true')
    scalar_input = Path(directory) / 'scalar-target.json'
    scalar_input.write_text(json.dumps(scalar_target))
    scalar_output = Path(directory) / 'scalar-rendered'
    run(sys.executable, 'scripts/bundle.py', 'render', '--target', str(scalar_input), '--output', str(scalar_output))
    scalar_documents = [obj for obj in yaml.safe_load_all((scalar_output / 'manifests.yaml').read_text()) if obj]
    explicit_namespaces = [obj['metadata']['namespace'] for obj in scalar_documents if 'namespace' in obj['metadata']]
    assert explicit_namespaces and all(namespace == 'true' for namespace in explicit_namespaces), 'Rendered namespace scalar text changed'
print('PASS: offline synthetic contracts and pinned chart rendering; deployment remains blocked.')
