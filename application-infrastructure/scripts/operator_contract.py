"""Inspect checksum-pinned operator sources, never compile/run/install them."""
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def inspect_contract(payloads, lock):
    import yaml
    for name, item in lock['files'].items():
        if hashlib.sha256(payloads[name]).hexdigest() != item['sha256']:
            raise ValueError('operator source checksum changed: ' + name)
    for name in ('clickhouseclusters.yaml', 'keeperclusters.yaml'):
        schema = yaml.safe_load(payloads[name])
        versions = [v for v in schema['spec']['versions'] if v['name'] == 'v1alpha1']
        if len(versions) != 1 or schema['spec']['group'] != 'clickhouse.com':
            raise ValueError('operator CR API mismatch')
        image = versions[0]['schema']['openAPIV3Schema']['properties']['spec']['properties']['containerTemplate']['properties']['image']
        fields = image['properties']
        if fields['tag'].get('type') != 'string' or any(k in fields['tag'] for k in ('pattern', 'enum', 'maxLength')):
            raise ValueError('operator tag field rejects reviewed digest syntax')
        if fields['repository'].get('type') != 'string' or fields['hash'].get('type') != 'string':
            raise ValueError('operator image fields changed')
    source = payloads['common.go'].decode()
    if 'return fmt.Sprintf("%s:%s", c.Repository, c.Tag)' not in source:
        raise ValueError('operator image rendering contract changed')
    return {'scope': 'checksum-bound source/schema inspection only',
            'candidateVersion': lock['candidateVersion'], 'commit': lock['commit'],
            'targetOperatorVerified': False, 'operatorExecuted': False}


def main():
    lock = json.loads((ROOT / 'clickhouse-operator.lock.json').read_text())
    payloads = {}
    for name, item in lock['files'].items():
        with urllib.request.urlopen(item['url'], timeout=60) as response:
            payload = response.read(2 * 1024 * 1024 + 1)
        if len(payload) > 2 * 1024 * 1024:
            raise ValueError('operator evidence exceeds bound')
        payloads[name] = payload
    print(json.dumps(inspect_contract(payloads, lock), indent=2))


if __name__ == '__main__':
    main()
