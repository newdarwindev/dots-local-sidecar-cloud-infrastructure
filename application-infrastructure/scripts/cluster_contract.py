#!/usr/bin/env python3
"""Offline design assessment/packet only. Never contacts a cluster or executes tools."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / 'contracts/future-cluster.schema.json'
PLACEHOLDER = re.compile(r'(^|[^a-z])(required|replace|placeholder|changeme|todo|example|synthetic)([^a-z]|$)', re.I)


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON object key')
        result[key] = value
    return result


def validate(value, schema, path='$'):
    """Strict implementation of only the keywords used by our bundled schema."""
    supported = {'$schema', '$id', 'title', 'description', 'type', 'properties', 'required',
                 'additionalProperties', 'const', 'enum', 'minLength', 'pattern', 'minimum',
                 'maximum', 'items', 'uniqueItems'}
    if set(schema) - supported:
        raise ValueError('unsupported schema keyword at ' + path)
    if 'const' in schema and (type(value) is not type(schema['const']) or value != schema['const']):
        raise ValueError('invalid constant at ' + path)
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError('invalid choice at ' + path)
    kinds = schema.get('type', [])
    kinds = [kinds] if isinstance(kinds, str) else kinds
    matches = {'null': value is None, 'string': isinstance(value, str),
               'integer': type(value) is int, 'object': isinstance(value, dict), 'array': isinstance(value, list)}
    if kinds and not any(matches.get(kind, False) for kind in kinds):
        raise ValueError('invalid type at ' + path)
    if value is None:
        return
    if isinstance(value, dict):
        properties = schema.get('properties', {})
        if set(schema.get('required', [])) - set(value):
            raise ValueError('missing keys at ' + path)
        if schema.get('additionalProperties') is False and set(value) - set(properties):
            raise ValueError('unknown keys at ' + path)
        for key, item in value.items():
            if key in properties:
                validate(item, properties[key], path + '.' + key)
    if isinstance(value, str):
        if len(value) < schema.get('minLength', 0) or ('pattern' in schema and not re.fullmatch(schema['pattern'], value)):
            raise ValueError('invalid string at ' + path)
    if type(value) is int:
        if value < schema.get('minimum', value) or value > schema.get('maximum', value):
            raise ValueError('number outside bounds at ' + path)
    if isinstance(value, list):
        if schema.get('uniqueItems') and len({json.dumps(x, sort_keys=True) for x in value}) != len(value):
            raise ValueError('duplicate list item at ' + path)
        for index, item in enumerate(value):
            validate(item, schema['items'], path + '[' + str(index) + ']')


def supplied(value):
    return value is not None and not (isinstance(value, str) and PLACEHOLDER.search(value))


def assess(config):
    validate(config, json.loads(SCHEMA.read_text()))
    required = ['target.kubernetesVersion', 'target.storageClass']
    missing = [key for key in required if not supplied(config['target'][key.split('.')[1]])]
    tokscale_missing = [key for key, value in config['tokscale'].items() if not supplied(value)]
    claims = config['capabilities']
    blockers = ['actual deployment path remains disabled', 'CI remains disabled pending fresh owner approval',
                'hypothetical compatibility is not live readiness or verified evidence',
                'latest strict-TLS and operator-image changes have not passed runtime tests']
    for key, item in claims.items():
        if item['status'] != 'evidence-supplied' or not supplied(item['evidenceRef']):
            blockers.append('capability evidence missing: ' + key)
    if any(value is None for key, value in config['capacity'].items() if key != 'designHeadroomPercent'):
        blockers.append('measured capacity and operator reservations missing')
    if config['target']['platform'] != 'linux/amd64':
        blockers.append('ARM64 app build/runtime unqualified')
    if not all(supplied(value) for value in config['recovery'].values()):
        blockers.append('independent recovery destination/custody/retention/restore evidence missing')
    if not config['operators']['clickhouse']['observedCommit']:
        blockers.append('actual operator/CRD revision unverified')
    return {'schemaVersion': 1, 'mode': 'design-only', 'deploymentAllowed': False,
            'canPrepareBundleRenderInputs': not missing, 'missingBundleRenderInputs': missing,
            'canPrepareTokscaleRenderInputs': not missing and not tokscale_missing,
            'missingTokscaleRenderInputs': tokscale_missing,
            'evidenceClaimsNotVerified': sum(x['status'] == 'evidence-supplied' for x in claims.values()),
            'blockers': sorted(set(blockers))}


def packet(config, output):
    report = assess(config)
    if not report['canPrepareBundleRenderInputs']:
        raise ValueError('essential bundle render inputs missing; use assess for their names')
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError('packet destination exists; refusing overwrite')
    # Resolve symlinked parent before enforcing the repository boundary.
    output = output.resolve()
    if output == ROOT.parent or ROOT.parent in output.parents:
        raise ValueError('packet must be outside the repository')
    output.mkdir(mode=0o700, parents=True)
    os.chmod(output, 0o700)
    target = json.loads((ROOT / 'fixtures/target.synthetic.json').read_text())
    target.update(namespace=config['target']['namespace'], storageClass=config['target']['storageClass'],
                  kubernetesVersion=config['target']['kubernetesVersion'])
    # Never copy context/UID/evidence claims into apparent live approval.
    documents = {'render-target.json': target, 'assessment.json': report}
    if report['canPrepareTokscaleRenderInputs']:
        t = config['tokscale']
        documents['tokscale-render-input.json'] = dict(namespace=config['target']['namespace'],
            storageClass=config['target']['storageClass'], appImage=t['appImage'], postgresImage=t['postgresImage'],
            origin=t['privateOrigin'], gatewayPodLabel=t['gatewayPodLabel'], databaseSize=t['databaseSize'])
    for filename, data in documents.items():
        with (output / filename).open('x') as stream:
            json.dump(data, stream, indent=2)
            stream.write('\n')
        (output / filename).chmod(0o600)
    inputs = {'contractSha256': hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
              'schemaSha256': hashlib.sha256(SCHEMA.read_bytes()).hexdigest(),
              'files': {name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in documents},
              'deploymentAllowed': False, 'renderExecuted': False}
    (output / 'packet-lock.json').write_text(json.dumps(inputs, indent=2) + '\n')
    (output / 'packet-lock.json').chmod(0o600)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['assess', 'packet'])
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(), object_pairs_hook=no_duplicates)
        if args.command == 'packet':
            if args.output is None:
                parser.error('--output is required for packet')
            report = packet(config, args.output)
        else:
            report = assess(config)
        print(json.dumps(report, indent=2))
    except (ValueError, OSError):
        # Avoid printing input contents, private references or credential-like strings.
        parser.exit(2, 'Blocked: invalid/incomplete contract or unsafe output; no external action performed.\n')


if __name__ == '__main__':
    main()
