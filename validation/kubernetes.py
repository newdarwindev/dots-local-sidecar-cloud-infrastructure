#!/usr/bin/env python3
"""Docker-only, checksum-bound Helm and strict Kubernetes schema checks.

No kubeconfig, cluster discovery, installs, dependency updates, or services. CRD
schemas come only from the locked charts/operator. JSON Schema does not execute
Kubernetes CEL rules, admission webhooks, defaulting, or controller behavior.
"""

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import urllib.request

import yaml


ROOT = Path(__file__).resolve().parents[1]
PRIMARY_CHARTS = (
    ('argocd', 'argocd'),
    ('openbao', 'openbao'),
    ('homarr', 'homarr'),
    ('external-secrets', 'homarr'),
)
IGNORED_DIRS = {'.runtime', 'runtime', 'artifacts', 'rendered', '__pycache__'}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path):
    return json.loads(path.read_text())


def documents(text):
    result = [value for value in yaml.safe_load_all(text) if value is not None]
    if any(not isinstance(value, dict) for value in result):
        raise ValueError('Kubernetes manifest documents must be mappings')
    return result


def fetch(url, maximum=64 * 1024 * 1024):
    if not url.startswith('https://'):
        raise ValueError('Artifact/schema downloads require HTTPS')
    with urllib.request.urlopen(url, timeout=90) as response:
        if not response.url.startswith('https://'):
            raise ValueError('Artifact/schema redirect downgraded HTTPS')
        data = response.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError('Artifact/schema download exceeds size limit')
    return data


def locked_bytes(item):
    if not re.fullmatch(r'[a-f0-9]{64}', item.get('sha256', '')):
        raise ValueError('Artifact requires a reviewed SHA256')
    data = fetch(item['url'])
    if hashlib.sha256(data).hexdigest() != item['sha256']:
        raise ValueError('Artifact SHA256 mismatch: ' + item['url'])
    return data


def run(command):
    print('+ ' + ' '.join(str(part) for part in command), flush=True)
    return subprocess.run(command, check=True, text=True, capture_output=False)


def output(command):
    print('+ ' + ' '.join(str(part) for part in command), flush=True)
    return subprocess.check_output(command, text=True)


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d+\.\d+\.\d+', value):
        raise ValueError('Schema validation requires an exact Kubernetes x.y.z version')
    return value


def schema_location(lock):
    revision = lock['revision']
    if not re.fullmatch(r'[a-f0-9]{40}', revision):
        raise ValueError('Kubernetes schema source must be pinned to a full commit')
    expected = (
        'https://raw.githubusercontent.com/yannh/kubernetes-json-schema/'
        + revision
        + '/{{.NormalizedKubernetesVersion}}-standalone{{.StrictSuffix}}/'
        '{{.ResourceKind}}{{.KindSuffix}}.json'
    )
    if lock['urlTemplate'] != expected:
        raise ValueError('Unexpected or unpinned Kubernetes schema location')
    return expected


def metadata_schema(lock, kubernetes_version):
    schema_location(lock)
    url = (
        'https://raw.githubusercontent.com/yannh/kubernetes-json-schema/'
        + lock['revision']
        + '/v' + version(kubernetes_version) + '-standalone-strict/configmap-v1.json'
    )
    schema = json.loads(fetch(url, maximum=8 * 1024 * 1024))
    metadata = schema['properties']['metadata']
    if not isinstance(metadata, dict) or 'properties' not in metadata:
        raise ValueError('Pinned standalone schema must include ObjectMeta properties')
    return metadata


def write_crd_definition_schema(lock, kubernetes_version, directory):
    """Supply the pinned Kubernetes CRD-object schema absent from standalone schemas."""
    schema_location(lock)
    kubernetes_version = version(kubernetes_version)
    revision = lock['revision']
    base = 'https://raw.githubusercontent.com/yannh/kubernetes-json-schema/'
    url = base + revision + '/v' + kubernetes_version + '/customresourcedefinition.json'
    schema = json.loads(fetch(url, maximum=8 * 1024 * 1024))

    # The versioned upstream schema references its companion definitions through
    # master. Rewrite only those known refs to the same immutable locked commit.
    floating_prefix = base + 'master/v' + kubernetes_version + '/_definitions.json#'
    pinned_prefix = base + revision + '/v' + kubernetes_version + '/_definitions.json#'

    def pin_references(value):
        if isinstance(value, dict):
            if '$ref' in value:
                reference = value['$ref']
                if not isinstance(reference, str):
                    raise ValueError('Pinned CRD schema references must be strings')
                if reference.startswith(floating_prefix):
                    value['$ref'] = pinned_prefix + reference[len(floating_prefix):]
                elif reference.startswith(pinned_prefix) or reference.startswith('#'):
                    pass
                else:
                    raise ValueError('CRD schema contains an unapproved reference')
            for child in value.values():
                pin_references(child)
        elif isinstance(value, list):
            for child in value:
                pin_references(child)

    pin_references(schema)
    gvk = schema.get('x-kubernetes-group-version-kind')
    if (schema.get('type') != 'object' or not isinstance(schema.get('properties'), dict)
            or not isinstance(gvk, list)
            or not any(item == {'group': 'apiextensions.k8s.io', 'version': 'v1',
                                'kind': 'CustomResourceDefinition'} for item in gvk)):
        raise ValueError('Pinned Kubernetes schema is not the v1 CustomResourceDefinition schema')
    properties = schema['properties']
    properties['apiVersion'] = {'type': 'string', 'enum': ['apiextensions.k8s.io/v1']}
    properties['kind'] = {'type': 'string', 'enum': ['CustomResourceDefinition']}
    schema['required'] = sorted(set(schema.get('required', [])) |
                               {'apiVersion', 'kind', 'metadata', 'spec'})
    schema['additionalProperties'] = False
    destination = directory / 'apiextensions.k8s.io' / 'customresourcedefinition_v1.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(schema, indent=2) + '\n')
    return destination


def normalize_schema(value, close_properties=True):
    """Convert CRD OpenAPI extensions without relaxing declared constraints.

    Only objects with declared properties are closed, matching kubeconform's
    upstream converter. Explicit dictionaries/additionalProperties and explicit
    preserve-unknown-fields regions retain their CRD-defined openness. Nullable
    extends only the declared type; enums and composition remain authoritative.
    """
    if not isinstance(value, dict):
        return copy.deepcopy(value)
    # Traverse schema positions, not arbitrary dictionaries: a CRD may quite
    # legitimately define properties named "nullable" or "properties".
    result = copy.deepcopy(value)
    for key in ('properties', 'patternProperties', 'definitions', '$defs'):
        if isinstance(result.get(key), dict):
            result[key] = {
                name: normalize_schema(item, close_properties)
                for name, item in result[key].items()
            }
    for key in ('items', 'additionalProperties', 'not', 'contains', 'propertyNames'):
        if isinstance(result.get(key), dict):
            result[key] = normalize_schema(result[key], close_properties)
    for key in ('allOf', 'anyOf', 'oneOf'):
        if isinstance(result.get(key), list):
            result[key] = [normalize_schema(item, close_properties) for item in result[key]]
    nullable = result.pop('nullable', False)
    if not isinstance(nullable, bool):
        raise ValueError('CRD nullable must be boolean')
    if result.get('x-kubernetes-int-or-string') or result.get('format') == 'int-or-string':
        result.pop('format', None)
        result['type'] = ['integer', 'string']
    if nullable and 'type' in result:
        types = result['type'] if isinstance(result['type'], list) else [result['type']]
        if not all(isinstance(item, str) for item in types):
            raise ValueError('CRD type must be a string or string list')
        result['type'] = list(dict.fromkeys([*types, 'null']))
    if result.get('x-kubernetes-preserve-unknown-fields') is True:
        result.setdefault('additionalProperties', True)
    elif close_properties and 'properties' in result:
        result.setdefault('additionalProperties', False)
    return result


def collect_crds(manifests):
    """Keep the full group/version/kind key; conflicting sources fail closed."""
    registry = {}
    for obj in manifests:
        if obj.get('kind') != 'CustomResourceDefinition':
            continue
        if obj.get('apiVersion') != 'apiextensions.k8s.io/v1':
            raise ValueError('Only structural v1 CRD schemas are supported')
        spec = obj['spec']
        for item in spec['versions']:
            if item.get('served') is not True:
                continue
            key = (spec['group'], item['name'], spec['names']['kind'].lower())
            if any(not re.fullmatch(r'[a-z0-9][a-z0-9.-]*', field) for field in key):
                raise ValueError('Unsafe CRD group/version/kind')
            schema = copy.deepcopy(item.get('schema', {}).get('openAPIV3Schema'))
            if not isinstance(schema, dict) or schema.get('type') != 'object':
                raise ValueError('Missing structural schema for CRD ' + '/'.join(key))
            properties = schema.setdefault('properties', {})
            exact_kind = {'type': 'string', 'enum': [spec['names']['kind']]}
            properties['kind'] = (
                {'allOf': [properties['kind'], exact_kind]} if 'kind' in properties else exact_kind
            )
            if key in registry and registry[key] != schema:
                raise ValueError('Conflicting CRD schema for ' + '/'.join(key))
            registry[key] = copy.deepcopy(schema)
    return registry


def write_crd_schemas(registry, directory, metadata):
    for (group, api_version, kind), raw_schema in sorted(registry.items()):
        schema = normalize_schema(raw_schema)
        properties = schema.setdefault('properties', {})
        exact_api = {'type': 'string', 'enum': [group + '/' + api_version]}
        properties['apiVersion'] = (
            {'allOf': [properties['apiVersion'], exact_api]} if 'apiVersion' in properties else exact_api
        )
        # collect_crds preserves the CRD's exact (case-sensitive) Kind enum.
        properties.setdefault('kind', {'type': 'string'})
        declared_metadata = raw_schema.get('properties', {}).get('metadata')
        if declared_metadata is None:
            properties['metadata'] = copy.deepcopy(metadata)
        else:
            if not isinstance(declared_metadata, dict):
                raise ValueError('CRD metadata constraints must be a schema object')
            # Builtin ObjectMeta closes the valid metadata field set. Do not
            # auto-close a CRD's name-only metadata restriction: that would
            # wrongly reject namespace/labels despite the builtin schema.
            properties['metadata'] = {'allOf': [
                copy.deepcopy(metadata),
                normalize_schema(declared_metadata, close_properties=False),
            ]}
        schema['required'] = sorted(set(schema.get('required', [])) | {'apiVersion', 'kind', 'metadata'})
        schema.setdefault('additionalProperties', False)
        destination = directory / group / (kind + '_' + api_version + '.json')
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(schema, indent=2) + '\n')


def validate_files(paths, registry, schemas_lock, kubernetes_version, scratch):
    if not paths:
        raise ValueError('Refusing an empty Kubernetes validation scope')
    version(kubernetes_version)
    source = schema_location(schemas_lock)
    local = scratch / ('schemas-' + kubernetes_version)
    local.mkdir(parents=True, exist_ok=True)
    if registry:
        write_crd_definition_schema(schemas_lock, kubernetes_version, local)
        write_crd_schemas(registry, local, metadata_schema(schemas_lock, kubernetes_version))
    # Missing remote/local schemas, invalid documents, and absent kubeconform are
    # all failures. Never use default/master, -skip or -ignore-missing-schemas.
    run([
        'kubeconform', '-strict', '-summary', '-verbose',
        '-kubernetes-version', kubernetes_version,
        '-schema-location', str(local / '{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'),
        '-schema-location', source,
        *[str(path) for path in paths],
    ])


def static_manifests(bundle):
    paths = []
    for path in sorted(bundle.rglob('*')):
        if path.suffix not in {'.yaml', '.yml'} or any(part in IGNORED_DIRS for part in path.relative_to(bundle).parts):
            continue
        parsed = documents(path.read_text())
        if any('apiVersion' in obj or 'kind' in obj for obj in parsed):
            if any('apiVersion' not in obj or 'kind' not in obj for obj in parsed):
                raise ValueError('Mixed or incomplete Kubernetes resource document: ' + str(path))
            paths.append(path)
    return paths


def write_manifests(path, manifests):
    if not manifests:
        raise ValueError('Rendered no resources: ' + str(path))
    path.write_text(yaml.safe_dump_all(manifests, sort_keys=False))
    return path


def primary(root, scratch, schemas_lock):
    bundle = root / 'primary-infrastructure'
    lock = read_json(bundle / 'artifacts.lock.json')
    kubernetes_version = version(lock['kubernetesVersion'])
    rendered = []
    paths = static_manifests(bundle)
    for name, namespace in PRIMARY_CHARTS:
        item = lock['artifacts'][name]
        chart = scratch / (name + '.tgz')
        chart.write_bytes(locked_bytes(item))
        values = bundle / 'values' / (name + '.yaml')
        run(['helm', 'lint', str(chart), '--kube-version', kubernetes_version, '-f', str(values)])
        payload = output([
            'helm', 'template', name, str(chart), '--namespace', namespace,
            '--kube-version', kubernetes_version, '--include-crds', '--skip-tests', '-f', str(values),
        ])
        manifests = documents(payload)
        rendered.extend(manifests)
        paths.append(write_manifests(scratch / ('primary-' + name + '.yaml'), manifests))
    registry = collect_crds(rendered)
    required = {
        ('argoproj.io', 'v1alpha1', 'application'),
        ('argoproj.io', 'v1alpha1', 'appproject'),
        ('external-secrets.io', 'v1', 'secretstore'),
        ('external-secrets.io', 'v1', 'externalsecret'),
    }
    if not required.issubset(registry):
        raise ValueError('Locked primary charts did not provide every required Argo/ESO CRD schema')
    validate_files(paths, registry, schemas_lock, kubernetes_version, scratch)


def application(root, scratch, schemas_lock):
    bundle_path = root / 'application-infrastructure'
    bundle = load_module('schema_application_bundle', bundle_path / 'scripts/bundle.py')
    target = bundle.target(bundle_path / 'fixtures/target.synthetic.json')
    if target.get('synthetic') is not True:
        raise ValueError('Schema checks accept only the explicit synthetic target')
    kubernetes_version = version(target['kubernetesVersion'])
    for name, (_, values) in bundle.COMPONENTS.items():
        bundle.artifact(name, fetch=True)
        command = [
            'helm', 'lint', str(bundle.prepared_artifact(name)),
            '--kube-version', kubernetes_version, '-f', str(bundle_path / 'values' / (values + '.yaml')),
        ]
        command += bundle.storage_class_args(name, target)
        if name == 'langfuse':
            # helm lint has no --api-versions flag. This upstream-supported,
            # lint-only override never modifies source values or bundle.render.
            command += ['--set', 'clickhouse.crdCheck=false']
        run(command)
    rendered = scratch / 'application-rendered'
    bundle.render(target, rendered)
    manifests = documents((rendered / 'manifests.yaml').read_text())
    operator_lock = read_json(bundle_path / 'clickhouse-operator.lock.json')
    crds = []
    for name in ('clickhouseclusters.yaml', 'keeperclusters.yaml'):
        crds.extend(documents(locked_bytes(operator_lock['files'][name]).decode()))
    registry = collect_crds(manifests + crds)
    required = {
        ('clickhouse.com', 'v1alpha1', 'clickhousecluster'),
        ('clickhouse.com', 'v1alpha1', 'keepercluster'),
    }
    if not required.issubset(registry):
        raise ValueError('Locked operator did not provide both required ClickHouse CRD schemas')
    paths = static_manifests(bundle_path) + [rendered / 'manifests.yaml']
    # Validate the CRD resources themselves as well as CR instances.
    paths.append(write_manifests(scratch / 'clickhouse-crds.yaml', crds))
    validate_files(paths, registry, schemas_lock, kubernetes_version, scratch)
    synthetic_lab(bundle_path, scratch, schemas_lock, registry, target)
    tokscale(root, scratch, schemas_lock)


def synthetic_lab(bundle_path, scratch, schemas_lock, registry, target):
    lab = load_module('schema_synthetic_lab', bundle_path / 'lab/render.py')
    lab_target = dict(target, namespace=lab.NAMESPACE, storageClass=lab.STORAGE)
    lab.bundle.COMPONENTS = {key: value for key, value in lab.bundle.COMPONENTS.items() if key != 'collector'}
    lab.bundle.render(lab_target, scratch / 'lab-baseline')
    lab_manifests = lab.bounded(documents((scratch / 'lab-baseline/manifests.yaml').read_text()))
    lab.validate_images(lab_manifests, read_json(bundle_path / 'images.lock.json'))
    path = write_manifests(scratch / 'synthetic-lab.yaml', lab_manifests)
    validate_files([path], registry, schemas_lock, target['kubernetesVersion'], scratch)


def tokscale(root, scratch, schemas_lock):
    renderer = load_module('schema_tokscale_render', root / 'application-infrastructure/tokscale/render.py')
    config = {
        'namespace': 'synthetic', 'storageClass': 'synthetic-not-storage',
        'appImage': 'example.invalid/synthetic@sha256:' + '0' * 64,
        'postgresImage': 'example.invalid/synthetic@sha256:' + '0' * 64,
        'origin': 'https://synthetic.example.invalid', 'gatewayPodLabel': 'synthetic-gate',
        'databaseSize': '1Gi',
    }
    manifests = renderer.render(config)['items']
    for obj in manifests:
        if obj['kind'] in {'Deployment', 'StatefulSet'} and obj['spec']['replicas'] != 0:
            raise ValueError('Tokscale schema fixture must remain zero-replica')
    path = write_manifests(scratch / 'tokscale-synthetic.yaml', manifests)
    kubernetes_version = read_json(root / 'primary-infrastructure/artifacts.lock.json')['kubernetesVersion']
    validate_files([path], {}, schemas_lock, kubernetes_version, scratch)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', choices=('primary', 'application', 'all'), default='all')
    args = parser.parse_args()
    if not Path('/.dockerenv').exists():
        parser.exit(2, 'Run schema validation only through the committed Docker workflow.\n')
    for tool in ('helm', 'kubeconform'):
        if shutil.which(tool) is None:
            parser.exit(2, 'Missing required tool: ' + tool + '\n')
    schemas_lock = read_json(ROOT / 'validation/tools.lock.json')['kubernetesSchemas']
    with tempfile.TemporaryDirectory(prefix='infrastructure-schemas-') as directory:
        scratch = Path(directory)
        if args.bundle in {'primary', 'all'}:
            primary(ROOT, scratch, schemas_lock)
        if args.bundle in {'application', 'all'}:
            application(ROOT, scratch, schemas_lock)
    print('PASS: selected Helm and strict schema checks; no cluster/runtime readiness established.')


if __name__ == '__main__':
    main()
