#!/usr/bin/env python3
"""Safe staging CLI: no deployment, credentials, enrollment or deletion commands."""
import argparse
import datetime as dt
import hashlib
import gzip
import io
import tarfile
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
GATES = ('capacityVerified storageBackingVerified encryptedSecretsVerified '
         'offClusterRestoreVerified privateAccessVerified dependencyArchitectureVerified '
         'operatorPrerequisitesVerified tokscaleContractVerified resourceBudgetVerified '
         'secretReferencesVerified imageDigestsVerified rootStorageHeadroomVerified '
         'ramHeadroomVerified').split()
COMPONENTS = {'langfuse': ('langfuse', 'langfuse'),
              'collector': ('otel-collector', 'collector'),
              'homarr': ('homarr-workload', 'homarr-workload')}
STORAGE_CLASS_VALUES = {
    'langfuse': ('postgresql.storage.className', 'redis.dataStorage.className',
                 'clickhouse.cluster.storage.className', 'clickhouse.keeper.storage.className',
                 's3.allInOne.data.storageClass'),
    'collector': (),
    'homarr': ('persistence.homarrDatabase.storageClassName',),
}

class Blocked(ValueError):
    pass

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()

def revision():
    digest = hashlib.sha256()
    for path in sorted(ROOT.rglob('*')):
        rel = path.relative_to(ROOT)
        if path.is_file() and not any(x in {'.runtime', 'rendered', '__pycache__'} for x in rel.parts) and path.suffix != '.pyc':
            digest.update(str(rel).encode() + b'\0' + path.read_bytes())
    return digest.hexdigest()

def load(path):
    value = json.loads(Path(path).read_text())
    if not isinstance(value, dict):
        raise Blocked('Expected a JSON object')
    return value

def target(path, live=False):
    value = load(path)
    for field in ('context', 'namespace', 'namespaceUid', 'storageClass', 'kubernetesVersion'):
        if not isinstance(value.get(field), str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,252}', value[field]):
            raise Blocked('Supply valid explicit target field: ' + field)
    if live and value.get('synthetic') is not False:
        raise Blocked('Synthetic target cannot be used for live preflight')
    return value

def blockers(value):
    result = [field for field in GATES if value.get(field) is not True]
    if value.get('synthetic') is not False:
        result.append('synthetic target: no live evidence')
    try:
        observed = dt.datetime.fromisoformat(value.get('observedAt', '').replace('Z', '+00:00'))
        age = dt.datetime.now(dt.timezone.utc) - observed
        if age.total_seconds() < 0 or age > dt.timedelta(hours=24):
            result.append('live evidence must be refreshed within 24 hours')
    except (AttributeError, TypeError, ValueError):
        result.append('live evidence timestamp missing or invalid')
    return result

def artifact(name, fetch=False):
    item = load(ROOT / 'artifacts.lock.json')['artifacts'][name]
    if not re.fullmatch('[a-f0-9]{64}', item.get('sha256', '')):
        raise Blocked('Unverified artifact digest: ' + name)
    filename = item.get('filename', '')
    if Path(filename).name != filename or not filename:
        raise Blocked('Unsafe artifact filename')
    dest = ROOT / '.runtime' / 'artifacts' / filename
    if not dest.exists():
        if not fetch:
            raise Blocked('Artifact not cached; run explicit fetch first: ' + name)
        url = item['url']
        if not url.startswith('https://'):
            raise Blocked('Artifact transport must use HTTPS')
        with urllib.request.urlopen(url, timeout=90) as response:
            data = response.read(64 * 1024 * 1024 + 1)
        if len(data) > 64 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != item['sha256']:
            raise Blocked('Downloaded artifact checksum/size mismatch: ' + name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    if hashlib.sha256(dest.read_bytes()).hexdigest() != item['sha256']:
        raise Blocked('Cached artifact checksum mismatch: ' + name)
    return dest

def patch_sftp_template(data, expected_sha):
    if hashlib.sha256(data).hexdigest() != expected_sha:
        raise Blocked('Vendor SFTP template changed; stop for independent review')
    old = b'{{- if or .Values.sftp.enabled .Values.allInOne.enabled }}'
    new = b'{{- if or .Values.sftp.enabled .Values.allInOne.sftp.enabled }}'
    if not data.startswith(old) or data.count(old) != 1:
        raise Blocked('Vendor SFTP patch precondition mismatch')
    return data.replace(old, new, 1)

def patch_media_template(data, expected_sha):
    if hashlib.sha256(data).hexdigest() != expected_sha:
        raise Blocked('Vendor media template changed; stop for independent review')
    start = b'- name: LANGFUSE_S3_MEDIA_UPLOAD_BUCKET\n'
    end = b'{{- if hasKey .Values.s3 "concurrency" }}\n'
    if data.count(start) != 1 or data.count(end) != 1 or data.index(start) >= data.index(end):
        raise Blocked('Vendor media patch precondition mismatch')
    # Chart 2.2.1 otherwise emits media bucket/credentials even with enabled=false.
    # Gate only that block; event upload and batch export keep their own semantics.
    return data.replace(start, b'{{- if .Values.s3.mediaUpload.enabled }}\n' + start, 1).replace(
        end, b'{{- end }}\n' + end, 1)

def prepared_artifact(name):
    original = artifact(name)
    if name != 'langfuse':
        return original
    patches = load(ROOT / 'artifacts.lock.json')['vendorPatches']
    sftp = patches['seaweedfs-unused-sftp']
    media = patches['langfuse-disabled-media']
    # Rewrite only the two checksum-reviewed templates BEFORE Helm execution. No
    # extraction, installation, source history or generated credentials involved.
    output = io.BytesIO()
    patched = {'sftp': 0, 'media': 0}
    with tarfile.open(original, 'r:gz') as source, gzip.GzipFile(fileobj=output, mode='wb', mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w') as dest:
            for member in source:
                if member.name.startswith('/') or '..' in Path(member.name).parts or not (member.isfile() or member.isdir()):
                    raise Blocked('Unsafe vendor archive member')
                data = source.extractfile(member).read() if member.isfile() else None
                if member.name == sftp['member']:
                    data = patch_sftp_template(data, sftp['originalSha256'])
                    member.size = len(data)
                    patched['sftp'] += 1
                elif member.name == media['member']:
                    data = patch_media_template(data, media['originalSha256'])
                    member.size = len(data)
                    patched['media'] += 1
                dest.addfile(member, io.BytesIO(data) if data is not None else None)
    if patched != {'sftp': 1, 'media': 1}:
        raise Blocked('Expected exactly one of each reviewed vendor template')
    destination = ROOT / '.runtime' / 'artifacts' / 'langfuse-reviewed-patch.tgz'
    destination.write_bytes(output.getvalue())
    return destination

def run(args):
    # Never echo raw stderr: cluster/auth plugins can put private data there.
    result = subprocess.run(args, capture_output=True, timeout=120)
    if result.returncode:
        raise Blocked('External command failed (output withheld): ' + args[0])
    return result.stdout

def inspect_documents(documents, namespace):
    """Reject dangerous rendering; no Secrets/cluster resources/adoption by default."""
    import importlib.util
    policy_spec = importlib.util.spec_from_file_location('image_policy', ROOT / 'scripts/image_policy.py')
    policy = importlib.util.module_from_spec(policy_spec)
    policy_spec.loader.exec_module(policy)
    validate_images = policy.validate_images
    problems = []
    try:
        validate_images(documents, load(ROOT / 'images.lock.json'))
    except ValueError as error:
        problems.append(str(error))
    seen = set()
    for obj in documents:
        if not obj:
            continue
        kind = obj.get('kind', '')
        meta = obj.get('metadata', {})
        identity = (kind, meta.get('namespace', namespace), meta.get('name'))
        if identity in seen:
            problems.append('duplicate resource identity')
        seen.add(identity)
        if kind not in {'Deployment', 'StatefulSet', 'Service', 'ConfigMap', 'ServiceAccount', 'PersistentVolumeClaim', 'NetworkPolicy', 'PodDisruptionBudget', 'Job', 'Role', 'RoleBinding'}:
            problems.append('unsupported or cluster-scoped resource: ' + kind)
        if kind == 'Secret':
            problems.append('chart-generated credential material forbidden')
        if meta.get('namespace', namespace) != namespace:
            problems.append('resource outside selected namespace')
        if meta.get('annotations', {}).get('helm.sh/hook'):
            problems.append('chart hook requires explicit review')
        spec = obj.get('spec', {})
        if kind == 'Service' and (spec.get('type', 'ClusterIP') != 'ClusterIP' or spec.get('externalIPs') or spec.get('externalName')):
            problems.append('external service exposure forbidden')
        pod = spec.get('template', {}).get('spec', {})
        if any(pod.get(key) for key in ('hostNetwork', 'hostPID', 'hostIPC')):
            problems.append('host namespace access forbidden')
        if any('hostPath' in vol for vol in pod.get('volumes', [])):
            problems.append('hostPath forbidden')
        for container in pod.get('containers', []) + pod.get('initContainers', []):
            if container.get('securityContext', {}).get('privileged'):
                problems.append('privileged container forbidden')
            if any(port.get('hostPort') for port in container.get('ports', [])):
                problems.append('hostPort forbidden')
            if '@sha256:' not in container.get('image', ''):
                problems.append('image digest unresolved')
    return sorted(set(problems))

def harden_hooks(documents):
    """Explicit deterministic patch for the locked SeaweedFS bucket hook only."""
    for obj in documents:
        if not obj or obj.get('kind') != 'Job':
            continue
        if obj.get('metadata', {}).get('name') != 'langfuse-bucket-hook':
            raise Blocked('Unreviewed chart Job; refusing render')
        pod = obj['spec']['template']['spec']
        pod['serviceAccountName'] = 'langfuse-seaweedfs'
        pod['automountServiceAccountToken'] = False
    return documents

def private_output(path):
    output = Path(path).resolve()
    if output == ROOT or ROOT in output.parents:
        raise Blocked('Output must be outside the bundle source tree')
    # The public repository also contains sibling source files.
    repo = ROOT.parent
    if output == repo or repo in output.parents:
        raise Blocked('Output must be outside the repository')
    return output

def storage_class_args(component, value):
    """Use the same explicit storage selection for Helm lint and review rendering."""
    storage = value.get('storageClass')
    # Match the narrow packet/Tokscale contract, and exclude Helm value syntax.
    if not isinstance(storage, str) or not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', storage):
        raise Blocked('Supply an explicit StorageClass DNS label for review rendering')
    return [argument for field in STORAGE_CLASS_VALUES[component]
            for argument in ('--set-string', field + '=' + storage)]

def storage_claim_specs(documents):
    """The locked bundle's PVCs, StatefulSet templates and operator claims only."""
    for obj in documents:
        if not obj:
            continue
        if not isinstance(obj, dict):
            raise Blocked('Rendered manifest must be an object')
        spec = obj.get('spec', {})
        if obj.get('kind') == 'PersistentVolumeClaim':
            yield spec
        if obj.get('kind') == 'StatefulSet':
            yield from (claim['spec'] for claim in spec.get('volumeClaimTemplates', []))
        if obj.get('kind') in {'ClickHouseCluster', 'KeeperCluster'}:
            yield spec.get('dataVolumeClaimSpec', {})

def preserve_storage_class(documents, string_documents, storage):
    # Some locked templates emit an unquoted value: --set-string alone cannot
    # stop YAML interpreting e.g. true, null, 0123 or a date as a typed scalar.
    # Require the exact selected source text at all six known claim sites before
    # preserving those fields as strings. Never repair a missing/defaulted class.
    claims = list(storage_claim_specs(documents))
    string_claims = list(storage_claim_specs(string_documents))
    if len(claims) != 6 or len(string_claims) != 6:
        raise Blocked('Locked persistence inventory changed; review storage wiring')
    if any(claim.get('storageClassName') != storage for claim in string_claims):
        raise Blocked('Selected StorageClass did not reach every rendered claim')
    for claim in claims:
        claim['storageClassName'] = storage
    return documents

def preserve_namespace(documents, string_documents, namespace):
    # A valid DNS namespace may also be a YAML scalar (true, null, 0123, a date).
    # Preserve only explicit top-level metadata.namespace with matching raw text.
    if len(documents) != len(string_documents):
        raise Blocked('Rendered document inventory changed during namespace review')
    for obj, raw in zip(documents, string_documents):
        if not obj:
            continue
        metadata = raw.get('metadata', {})
        if 'namespace' not in metadata:
            continue
        if metadata['namespace'] != namespace:
            raise Blocked('Rendered namespace differs from selected namespace')
        obj['metadata']['namespace'] = namespace
    return documents

def render(value, output):
    import yaml
    output = private_output(output)
    # Rendering is deliberately offline: no Helm repo/dependency update or cluster lookup.
    if output.exists():
        raise Blocked('Output already exists; preserve it and choose a fresh directory')
    rendered = []
    for key, (release, values) in COMPONENTS.items():
        cmd = ['helm', 'template', release, str(prepared_artifact(key)), '--namespace', value['namespace'],
               '--kube-version', value['kubernetesVersion'], '--include-crds', '--skip-tests',
               '-f', str(ROOT / 'values' / (values + '.yaml'))]
        if key == 'langfuse':
            cmd += ['--api-versions', 'clickhouse.com/v1alpha1/ClickHouseCluster',
                    '--api-versions', 'clickhouse.com/v1alpha1/KeeperCluster']
        cmd += storage_class_args(key, value)
        rendered.append(run(cmd).decode())
    payload = '\n---\n'.join(rendered)
    string_docs = list(yaml.load_all(payload, Loader=yaml.BaseLoader))
    docs = preserve_storage_class(list(yaml.safe_load_all(payload)), string_docs, value['storageClass'])
    docs = preserve_namespace(docs, string_docs, value['namespace'])
    docs = harden_hooks(docs)
    payload = yaml.safe_dump_all(docs, sort_keys=False)
    issues = inspect_documents(docs, value['namespace'])
    output.mkdir(parents=True, mode=0o700)
    os.chmod(output, 0o700)
    (output / 'manifests.yaml').write_text(payload)
    report = {'schemaVersion': 1, 'mode': 'staging-only', 'revision': revision(),
              'targetSha256': hashlib.sha256(canonical(value)).hexdigest(),
              'manifestSha256': hashlib.sha256(payload.encode()).hexdigest(),
              'resourceCount': len([x for x in docs if x]),
              'deploymentBlockers': sorted(set(blockers(value) + issues +
                  ['Tokscale source/build/access contract must be independently completed',
                   'actual deployment path disabled pending owner review']))}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))

def preflight(value, output):
    """Bounded reads only, no Secret reads, exec, shell, apply, patch or access creation."""
    # Supplying a context is not consent; caller must already have authorized this connection.
    base = ['kubectl', '--context', value['context'], '--request-timeout=20s']
    dest = private_output(output)
    ns_uid = run(base + ['get', 'namespace', value['namespace'], '-o', 'jsonpath={.metadata.uid}']).decode()
    if ns_uid != value['namespaceUid']:
        raise Blocked('Namespace UID mismatch: wrong/recreated cluster binding')
    results = {}
    # Project at kubectl: never return pod environment, annotations or full resource
    # documents to this process. Each item yields exactly one newline, even absent status.
    projections = {
        'nodes': (['get', 'nodes'], '.status.conditions[?(@.type=="Ready")].status'),
        'pvc': (['-n', value['namespace'], 'get', 'pvc'], '.status.phase'),
        'pods': (['get', 'pods', '--all-namespaces'], '.status.phase'),
        'crds': (['get', 'crds'], '.kind'),
    }
    for key, (query, expression) in projections.items():
        projection = '{range .items[*]}{' + expression + '}{"\\n"}{end}'
        rows = run(base + query + ['-o', 'jsonpath=' + projection]).decode().splitlines()
        results[key] = {'count': len(rows)}
        if key == 'nodes':
            results[key]['notReady'] = sum(row != 'True' for row in rows)
        if key == 'pods':
            results[key]['notRunningOrSucceeded'] = sum(row not in {'Running', 'Succeeded'} for row in rows)
    # Query only the explicitly selected class, not full parameters/provisioner secrets.
    selected = run(base + ['get', 'storageclass', value['storageClass'], '-o', 'jsonpath={.metadata.name}']).decode()
    results['storageclasses'] = {'selectedPresent': selected == value['storageClass']}
    report = {'schemaVersion': 1, 'observedAt': dt.datetime.now(dt.timezone.utc).isoformat(),
              'scope': 'read-only aggregate inspection; NOT capacity approval', 'observations': results,
              'remaining': ['physical backing/encryption', 'root and RAM headroom', 'combined workload reservation',
                            'off-cluster encrypted restore', 'dependency images/architecture', 'access denial tests']}
    with dest.open('x') as handle:
        os.chmod(dest, 0o600)
        handle.write(json.dumps(report, indent=2) + '\n')
    print('Read-only aggregate preflight recorded; readiness remains unproven.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', nargs='?', default='plan', choices=['plan', 'revision', 'fetch', 'render', 'preflight', 'deploy'])
    parser.add_argument('--target')
    parser.add_argument('--output')
    args = parser.parse_args()
    try:
        if args.action == 'deploy':
            raise Blocked('Deployment is disabled. Exact initial owner approval, resolved production gates, reviewed manifest digest and a separately reviewed CI enablement change are required. No apply command ran.')
        if args.action == 'revision':
            print(revision()); return
        if args.action == 'fetch':
            for name in COMPONENTS:
                artifact(name, fetch=True)
            print('Checksum-verified public chart archives cached; nothing installed.'); return
        if args.action == 'plan':
            value = target(args.target) if args.target else load(ROOT / 'fixtures/target.synthetic.json')
            print(json.dumps({'mode': 'plan-only', 'revision': revision(), 'deploymentEnabled': False,
                              'components': list(COMPONENTS) + ['tokscale-with-dedicated-postgresql'],
                              'blockers': blockers(value)}, indent=2)); return
        if not args.target or not args.output:
            raise Blocked('Explicit --target and fresh --output are essential')
        value = target(args.target, live=args.action == 'preflight')
        if args.action == 'render': render(value, args.output)
        elif args.action == 'preflight': preflight(value, args.output)
    except (Blocked, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        # Only local safe errors are surfaced; never include external stdout or credential data.
        message = str(exc) if isinstance(exc, Blocked) else 'Invalid input or unavailable prerequisite; inspect locally.'
        print('BLOCKED: ' + message, file=sys.stderr)
        sys.exit(2)

if __name__ == '__main__':
    main()
