#!/usr/bin/env python3
"""Conservative offline rendered-resource budget; never a scheduling/fit approval."""
import argparse
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import json
from pathlib import Path
import re


def quantity(value, cpu=False):
    match = re.fullmatch(r'([0-9]+(?:\.[0-9]+)?)(m|Ki|Mi|Gi|Ti|K|M|G|T)?', str(value))
    if not match:
        raise ValueError('unsupported Kubernetes quantity')
    number, suffix = Decimal(match[1]), match[2] or ''
    if cpu:
        if suffix not in {'', 'm'}:
            raise ValueError('invalid CPU unit')
        result = number if suffix == 'm' else number * 1000
    else:
        units = {'': 1, 'Ki': 2**10, 'Mi': 2**20, 'Gi': 2**30, 'Ti': 2**40,
                 'K': 10**3, 'M': 10**6, 'G': 10**9, 'T': 10**12}
        if suffix not in units:
            raise ValueError('invalid memory/storage unit')
        result = number * units[suffix]
    return int(result.to_integral_value(rounding=ROUND_CEILING))


def flatten(documents):
    for obj in documents:
        if obj is None:
            continue
        if not isinstance(obj, dict):
            raise ValueError('manifest object required')
        if obj.get('kind') == 'List':
            yield from flatten(obj.get('items', []))
        else:
            yield obj


def report(documents, headroom_percent=25):
    if type(headroom_percent) is not int or not 0 <= headroom_percent <= 90:
        raise ValueError('invalid design headroom')
    totals = {'declaredCpuMillicores': 0, 'declaredMemoryBytes': 0, 'requestedStorageBytes': 0}
    blockers = set()
    workloads = zero = jobs = 0
    supported = {'Deployment', 'StatefulSet', 'Job', 'Pod'}
    inert = {'Service', 'ConfigMap', 'Secret', 'ServiceAccount', 'NetworkPolicy', 'Role',
             'RoleBinding', 'PodDisruptionBudget'}
    for obj in flatten(documents):
        kind, spec = obj.get('kind'), obj.get('spec', {})
        if kind == 'PersistentVolumeClaim':
            try:
                totals['requestedStorageBytes'] += quantity(spec['resources']['requests']['storage'])
            except (KeyError, ValueError):
                blockers.add('PVC storage request missing/unsupported')
            continue
        if kind not in supported:
            if kind not in inert:
                blockers.add('unbudgeted resource kind: ' + str(kind))
            continue
        workloads += 1
        if kind == 'Job':
            jobs += 1
            replicas = spec.get('parallelism', 1)
            blockers.add('job overlap/duration must be measured separately')
        else:
            replicas = 1 if kind == 'Pod' else spec.get('replicas', 1)
        if type(replicas) is not int or replicas < 0:
            raise ValueError('invalid workload replicas')
        if replicas == 0:
            zero += 1
            blockers.add('zero-replica workload: activation demand not included')
        if kind == 'Deployment':
            # Replica count alone excludes rolling-update surge; never assert fit.
            blockers.add('deployment rollout surge/old pods not included')
        pod = spec if kind == 'Pod' else spec.get('template', {}).get('spec', {})
        if pod.get('ephemeralContainers'):
            blockers.add('ephemeral container demand not included')
        if pod.get('overhead'):
            blockers.add('runtime pod overhead requires separate reservation')
        containers, init = pod.get('containers', []), pod.get('initContainers', [])
        if not containers:
            blockers.add('workload container list missing')
        if any(c.get('restartPolicy') == 'Always' for c in init):
            blockers.add('restartable init sidecar requires explicit overlap budget')
        for key, total in [('cpu', 'declaredCpuMillicores'), ('memory', 'declaredMemoryBytes')]:
            def request(container):
                try:
                    return quantity(container['resources']['requests'][key], cpu=key == 'cpu')
                except (KeyError, ValueError):
                    blockers.add('container ' + key + ' request missing/unsupported')
                    return 0
            ordinary = sum(request(c) for c in containers)
            initial = [request(c) for c in init]
            # Conservative for init sidecars: add all init requests, not just max.
            # This may overestimate but cannot hide their overlap with app pods.
            totals[total] += replicas * (ordinary + sum(initial))
        for claim in spec.get('volumeClaimTemplates', []):
            try:
                totals['requestedStorageBytes'] += replicas * quantity(claim['spec']['resources']['requests']['storage'])
            except (KeyError, ValueError):
                blockers.add('stateful volume template request missing/unsupported')
    blockers.update({'operator/controller/system reservations not included',
                     'actual placement/fragmentation and existing workloads not measured',
                     'retained PVCs, snapshots, logs and root-disk expansion not included',
                     'limits, burst demand and eviction behavior require separate acceptance',
                     'browser runtime, Temporal, lease store and gateway demand excluded unless supplied as manifests'})
    return {'schemaVersion': 1, 'mode': 'offline-design-estimate', 'fitApproved': False,
            'workloadsCount': workloads, 'zeroReplicaWorkloadsCount': zero, 'jobsCount': jobs,
            **totals, 'designHeadroomPercent': headroom_percent,
            'cpuWithDesignHeadroomMillicores': (totals['declaredCpuMillicores'] * (100 + headroom_percent) + 99) // 100,
            'memoryWithDesignHeadroomBytes': (totals['declaredMemoryBytes'] * (100 + headroom_percent) + 99) // 100,
            'blockers': sorted(blockers)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifests', type=Path)
    parser.add_argument('--headroom-percent', type=int, default=25)
    args = parser.parse_args()
    import yaml  # supplied only by the existing Docker validation environment
    try:
        result = report(list(yaml.safe_load_all(args.manifests.read_text())), args.headroom_percent)
        print(json.dumps(result, indent=2))
    except (ValueError, TypeError, KeyError, AttributeError, OSError, InvalidOperation, yaml.YAMLError):
        parser.exit(2, 'Blocked: invalid or unsupported manifest input; no capacity approval.\n')


if __name__ == '__main__':
    main()
