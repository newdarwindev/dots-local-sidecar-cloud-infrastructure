#!/usr/bin/env python3
"""Render the bounded synthetic Langfuse/Homarr lab inside the Docker tool image."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import bundle
from image_policy import validate_images

NAMESPACE = 'dots-synthetic-lab'
STORAGE = 'dots-lab-retain'
ALLOWED = {'ServiceAccount', 'Service', 'ConfigMap', 'PodDisruptionBudget',
           'PersistentVolumeClaim', 'Deployment', 'StatefulSet', 'Job',
           'ClickHouseCluster', 'KeeperCluster'}


def budget(request, limit, cpu='250m', maximum='1'):
    return {'requests': {'cpu': cpu, 'memory': request},
            'limits': {'cpu': maximum, 'memory': limit}}


def bounded(documents):
    result = []
    for obj in documents:
        if obj is None:
            continue
        kind, name = obj['kind'], obj['metadata']['name']
        if obj['metadata'].get('namespace') not in (None, NAMESPACE):
            raise ValueError('lab resource escaped its namespace')
        if kind == 'Secret':
            if obj.get('data') or obj.get('stringData'):
                raise ValueError('chart generated credential material')
            continue
        if kind not in ALLOWED:
            raise ValueError('unreviewed lab resource kind')
        obj['metadata']['namespace'] = NAMESPACE
        obj['metadata'].setdefault('labels', {})['dots.example/purpose'] = 'synthetic-lab'
        spec = obj.get('spec', {})
        if kind == 'Service' and (spec.get('type', 'ClusterIP') != 'ClusterIP'
                                  or spec.get('externalIPs')):
            raise ValueError('lab Service exposure is forbidden')
        if kind == 'PersistentVolumeClaim':
            size = {'langfuse-redis': '2Gi', 'langfuse-s3-all-in-one-data': '10Gi',
                    'homarr-database': '1Gi'}[name]
            spec['resources']['requests']['storage'] = size
        if kind in {'Deployment', 'StatefulSet', 'Job'}:
            pod = spec['template']['spec']
            if pod.get('hostNetwork') or pod.get('hostPID') or pod.get('hostIPC'):
                raise ValueError('host namespace use is forbidden')
            if any('hostPath' in volume for volume in pod.get('volumes', [])):
                raise ValueError('host mounts are forbidden')
            pod['automountServiceAccountToken'] = False
            if kind == 'Deployment':
                spec['replicas'] = 1
                spec['strategy'] = {'type': 'Recreate'}
            for container in pod.get('containers', []) + pod.get('initContainers', []):
                if container.get('securityContext', {}).get('privileged'):
                    raise ValueError('privileged lab container is forbidden')
                container['resources'] = budget('256Mi', '512Mi') if kind == 'Job' else budget('512Mi', '1Gi')
                if name in {'homarr-workload', 'langfuse-redis', 'langfuse-s3-all-in-one'}:
                    container['resources'] = budget('256Mi', '512Mi')
                if name in {'langfuse-web', 'langfuse-worker'} and 'livenessProbe' in container:
                    container['startupProbe'] = copy.deepcopy(container['livenessProbe'])
                    container['startupProbe'].update(initialDelaySeconds=0, failureThreshold=60)
                if name == 'langfuse-web':
                    container['resources'] = budget('1Gi', '2Gi')
                    environment = container.setdefault('env', [])
                    if any(item['name'] == 'NODE_OPTIONS' for item in environment):
                        raise ValueError('review changed upstream Node options before overriding')
                    environment.append({'name': 'NODE_OPTIONS', 'value': '--max-old-space-size=1536'})
            for claim in spec.get('volumeClaimTemplates', []):
                claim['spec']['resources']['requests']['storage'] = '8Gi'
            if kind == 'StatefulSet':
                spec['persistentVolumeClaimRetentionPolicy'] = {'whenDeleted': 'Retain', 'whenScaled': 'Retain'}
        if kind in {'ClickHouseCluster', 'KeeperCluster'}:
            clickhouse = kind == 'ClickHouseCluster'
            spec['containerTemplate']['resources'] = budget('1Gi', '2Gi', '500m', '2') if clickhouse else budget('256Mi', '512Mi')
            spec['dataVolumeClaimSpec']['resources']['requests']['storage'] = '20Gi' if clickhouse else '2Gi'
        result.append(obj)
    claims = list(bundle.storage_claim_specs(result))
    if len(claims) != 6 or any(claim.get('storageClassName') != STORAGE for claim in claims):
        raise ValueError('lab persistence inventory differs from reviewed six claims')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--kubernetes-version', required=True)
    args = parser.parse_args()
    if not Path('/.dockerenv').exists():
        parser.error('use the Docker tool image')
    if args.output.exists():
        parser.error('choose a new output directory; existing receipts are preserved')
    with tempfile.TemporaryDirectory() as scratch:
        bundle.ROOT = Path(scratch) / 'repo/application-infrastructure'
        shutil.copytree(ROOT, bundle.ROOT, ignore=shutil.ignore_patterns('.runtime', '__pycache__'))
        bundle.fetch_artifacts()
        bundle.COMPONENTS = {key: value for key, value in bundle.COMPONENTS.items() if key != 'collector'}
        target = json.loads((ROOT / 'fixtures/target.synthetic.json').read_text())
        target.update(namespace=NAMESPACE, storageClass=STORAGE, kubernetesVersion=args.kubernetes_version)
        bundle.render(target, Path(scratch) / 'baseline')
        documents = bounded(list(yaml.safe_load_all((Path(scratch) / 'baseline/manifests.yaml').read_text())))
        validate_images(documents, json.loads((ROOT / 'images.lock.json').read_text()))
        payload = yaml.safe_dump_all(documents, sort_keys=False)
        args.output.mkdir(mode=0o700, parents=True)
        (args.output / 'lab.yaml').write_text(payload)
        receipt = {'dataClassification': 'synthetic-only', 'namespace': NAMESPACE,
                   'kubernetesVersion': args.kubernetes_version,
                   'manifestSha256': hashlib.sha256(payload.encode()).hexdigest(),
                   'sourceRevision': bundle.revision(), 'resourceCount': len(documents),
                   'realDataAllowed': False, 'sourceIngestionAllowed': False}
        (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        print('Rendered bounded synthetic lab; no apply or credentials generated.')


if __name__ == '__main__':
    main()
