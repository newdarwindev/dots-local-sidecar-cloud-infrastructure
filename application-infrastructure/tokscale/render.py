#!/usr/bin/env python3
"""Offline, zero-replica Kubernetes review renderer. Never connects or deploys."""
import argparse
import ipaddress
import json
import re
from pathlib import Path


def name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', value):
        raise ValueError('expected a DNS label')
    return value


def image(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9][a-z0-9./_:-]*@sha256:[0-9a-f]{64}', value):
        raise ValueError('verified image digest is essential; no tag fallback')
    return value


def render(config):
    ns = name(config['namespace'])
    storage = name(config['storageClass'])
    app_image = image(config['appImage'])
    pg_image = image(config['postgresImage'])
    origin = config['origin']
    if not isinstance(origin, str) or not re.fullmatch(r'https://[a-z0-9.-]+(?::[0-9]{1,5})?', origin):
        raise ValueError('explicit HTTPS origin required')
    gateway = name(config['gatewayPodLabel'])
    cidrs = config['githubCidrs']
    if not isinstance(cidrs, list) or not cidrs:
        raise ValueError('explicit GitHub IPv4 egress ranges required')
    try:
        cidrs = sorted({str(ipaddress.ip_network(value, strict=True)) for value in cidrs
                        if ipaddress.ip_network(value, strict=True).version == 4})
    except (TypeError, ValueError):
        raise ValueError('GitHub CIDRs must be strict IPv4 networks') from None
    if not cidrs:
        raise ValueError('GitHub IPv4 egress ranges required')
    if '0.0.0.0/0' in cidrs:
        raise ValueError('unrestricted IPv4 egress is forbidden')
    size = config['databaseSize']
    if not isinstance(size, str) or not re.fullmatch(r'[1-9][0-9]*(?:Gi|Ti)', size):
        raise ValueError('explicit database storage budget required')
    def obj(kind, label, spec, api='v1'):
        return {'apiVersion': api, 'kind': kind, 'metadata': {'name': label, 'namespace': ns,
                'labels': {'app.kubernetes.io/part-of': 'tokscale-staged'},
                'annotations': {'dots.dev/state': 'review-only-no-activation'}}, 'spec': spec}
    def selector(label):
        return {'app.kubernetes.io/name': label}
    def secret_env(env, secret, key):
        return {'name': env, 'valueFrom': {'secretKeyRef': {'name': secret, 'key': key}}}
    app = 'tokscale-hub'
    pg = 'tokscale-postgres'
    pod_security = {'runAsNonRoot': True, 'seccompProfile': {'type': 'RuntimeDefault'}}
    container_security = {'allowPrivilegeEscalation': False, 'capabilities': {'drop': ['ALL']}}
    resources = [
      obj('Service', pg, {'type': 'ClusterIP', 'clusterIP': 'None', 'selector': selector(pg),
          'ports': [{'name': 'postgres', 'port': 5432, 'targetPort': 5432}]}),
      obj('StatefulSet', pg, {
          'replicas': 0, 'serviceName': pg,
          'persistentVolumeClaimRetentionPolicy': {'whenDeleted': 'Retain', 'whenScaled': 'Retain'},
          'selector': {'matchLabels': selector(pg)},
          'template': {'metadata': {'labels': selector(pg)}, 'spec': {
             'automountServiceAccountToken': False,
             'securityContext': dict(pod_security, runAsUser=70, runAsGroup=70, fsGroup=70),
             'containers': [{'name': 'postgres', 'image': pg_image,
               'args': ['-c', 'ssl=on', '-c', 'ssl_cert_file=/tls/tls.crt', '-c', 'ssl_key_file=/tls/tls.key'],
               'securityContext': container_security,
               'env': [secret_env('POSTGRES_PASSWORD', 'tokscale-database', 'postgres-password'),
                       {'name': 'POSTGRES_USER', 'value': 'tokscale'},
                       {'name': 'POSTGRES_DB', 'value': 'tokscale'},
                       {'name': 'PGDATA', 'value': '/var/lib/postgresql/data/pgdata'}],
               'ports': [{'containerPort': 5432, 'name': 'postgres'}],
               'readinessProbe': {'exec': {'command': ['pg_isready', '-U', 'tokscale', '-d', 'tokscale']}, 'periodSeconds': 10},
               'resources': {'requests': {'cpu': '100m', 'memory': '256Mi'}, 'limits': {'cpu': '1', 'memory': '1Gi'}},
               'volumeMounts': [{'name': 'data', 'mountPath': '/var/lib/postgresql/data'},
                                {'name': 'tls', 'mountPath': '/tls', 'readOnly': True}]}],
             'volumes': [{'name': 'tls', 'secret': {'secretName': 'tokscale-postgres-tls', 'defaultMode': 288}}]}},
          'volumeClaimTemplates': [{'metadata': {'name': 'data'}, 'spec': {'accessModes': ['ReadWriteOnce'],
              'storageClassName': storage, 'resources': {'requests': {'storage': size}}}}]}, 'apps/v1'),
      obj('Service', app, {'type': 'ClusterIP', 'selector': selector(app),
          'ports': [{'name': 'http', 'port': 3000, 'targetPort': 3000}]}),
      obj('Deployment', app, {'replicas': 0, 'strategy': {'type': 'Recreate'},
          'selector': {'matchLabels': selector(app)},
          'template': {'metadata': {'labels': selector(app)}, 'spec': {
             'automountServiceAccountToken': False, 'securityContext': pod_security,
             'containers': [{'name': 'hub', 'image': app_image,
               'securityContext': container_security,
               'env': [secret_env('DATABASE_URL', 'tokscale-database', 'database-url'),
                       secret_env('AUTH_SECRET', 'tokscale-auth', 'auth-secret'),
                       secret_env('GITHUB_CLIENT_ID', 'tokscale-auth', 'github-client-id'),
                       secret_env('GITHUB_CLIENT_SECRET', 'tokscale-auth', 'github-client-secret'),
                       {'name': 'DATABASE_SSL', 'value': 'verify-full'},
                       {'name': 'DATABASE_CA_FILE', 'value': '/database-ca/ca.crt'},
                       {'name': 'APP_URL', 'value': origin},
                       {'name': 'CSRF_ALLOWED_ORIGINS', 'value': origin},
                       {'name': 'NEXT_TELEMETRY_DISABLED', 'value': '1'}],
               'ports': [{'containerPort': 3000, 'name': 'http'}],
               'readinessProbe': {'tcpSocket': {'port': 3000}, 'periodSeconds': 10},
               'resources': {'requests': {'cpu': '100m', 'memory': '256Mi'}, 'limits': {'cpu': '1', 'memory': '1Gi'}},
               'volumeMounts': [{'name': 'database-ca', 'mountPath': '/database-ca', 'readOnly': True}]}],
             'volumes': [{'name': 'database-ca', 'secret': {'secretName': 'tokscale-database-ca', 'defaultMode': 292}}]}}}, 'apps/v1'),
      obj('NetworkPolicy', 'tokscale-default-deny', {'podSelector': {'matchExpressions': [
          {'key': 'app.kubernetes.io/name', 'operator': 'In', 'values': [app, pg, gateway]}]},
          'policyTypes': ['Ingress', 'Egress']}, 'networking.k8s.io/v1'),
      obj('NetworkPolicy', 'tokscale-gate-to-app', {'podSelector': {'matchLabels': selector(app)},
          'policyTypes': ['Ingress'], 'ingress': [{'from': [{'podSelector': {'matchLabels': selector(gateway)}}],
          'ports': [{'protocol': 'TCP', 'port': 3000}]}]}, 'networking.k8s.io/v1'),
      obj('NetworkPolicy', 'tokscale-app-to-postgres', {'podSelector': {'matchLabels': selector(app)},
          'policyTypes': ['Egress'], 'egress': [
              {'to': [{'podSelector': {'matchLabels': selector(pg)}}],
               'ports': [{'protocol': 'TCP', 'port': 5432}]},
              {'to': [{'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'kube-system'}},
                       'podSelector': {'matchLabels': {'k8s-app': 'kube-dns'}}}],
               'ports': [{'protocol': 'UDP', 'port': 53}, {'protocol': 'TCP', 'port': 53}]},
              {'to': [{'ipBlock': {'cidr': cidr}} for cidr in cidrs],
               'ports': [{'protocol': 'TCP', 'port': 443}]}]}, 'networking.k8s.io/v1'),
      obj('NetworkPolicy', 'tokscale-postgres-from-app', {'podSelector': {'matchLabels': selector(pg)},
          'policyTypes': ['Ingress'], 'ingress': [{'from': [{'podSelector': {'matchLabels': selector(app)}}],
          'ports': [{'protocol': 'TCP', 'port': 5432}]}]}, 'networking.k8s.io/v1'),
      obj('NetworkPolicy', 'tokscale-gateway-ingress', {'podSelector': {'matchLabels': selector(gateway)},
          'policyTypes': ['Ingress'], 'ingress': [{'from': [{'podSelector': {}}],
          'ports': [{'protocol': 'TCP', 'port': 8445}]}]}, 'networking.k8s.io/v1'),
      obj('NetworkPolicy', 'tokscale-gateway-to-app', {'podSelector': {'matchLabels': selector(gateway)},
          'policyTypes': ['Egress'], 'egress': [
              {'to': [{'podSelector': {'matchLabels': selector(app)}}],
               'ports': [{'protocol': 'TCP', 'port': 3000}]},
              {'to': [{'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'kube-system'}},
                       'podSelector': {'matchLabels': {'k8s-app': 'kube-dns'}}}],
               'ports': [{'protocol': 'UDP', 'port': 53}, {'protocol': 'TCP', 'port': 53}]}]}, 'networking.k8s.io/v1')]
    # GitHub routes are restricted to the current web/api ranges returned by
    # api.github.com/meta. The caller records the snapshot date in its input.
    return {'apiVersion': 'v1', 'kind': 'List', 'items': resources}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    args = parser.parse_args()
    try:
        result = render(json.loads(args.config.read_text()))
    except (KeyError, TypeError, ValueError) as error:
        parser.exit(2, f'Blocked: essential deployment input invalid ({type(error).__name__}).\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
