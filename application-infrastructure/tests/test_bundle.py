import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bundle', ROOT / 'scripts/bundle.py')
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)

class BundleTests(unittest.TestCase):
    def test_storage_selection_covers_every_persistent_component(self):
        value = {'storageClass': 'review-storage'}
        expected = {
            'langfuse': ['postgresql.storage.className', 'redis.dataStorage.className',
                         'clickhouse.cluster.storage.className', 'clickhouse.keeper.storage.className',
                         's3.allInOne.data.storageClass'],
            'homarr': ['persistence.homarrDatabase.storageClassName'],
            'collector': [],
        }
        for component, fields in expected.items():
            with self.subTest(component=component):
                self.assertEqual(bundle.storage_class_args(component, value),
                                 [arg for field in fields for arg in ('--set-string', field + '=review-storage')])

    def test_storage_selection_rejects_placeholders_and_helm_override_syntax(self):
        for value in (None, '', 'REQUIRED_PRIVATE_STORAGE_CLASS', 'a,b=c', 'a/b', 'a.b', '-a', 'a' * 64):
            with self.subTest(value=value), self.assertRaises(bundle.Blocked):
                bundle.storage_class_args('langfuse', {'storageClass': value})

    def test_render_applies_storage_selection_without_activating(self):
        value = bundle.load(ROOT / 'fixtures/target.synthetic.json')
        value['storageClass'] = 'review-storage'
        def rendered(command):
            count = {'langfuse': 5, 'otel-collector': 0, 'homarr-workload': 1}[command[2]]
            return '\n---\n'.join(json.dumps({'apiVersion': 'v1', 'kind': 'PersistentVolumeClaim',
                'metadata': {'name': command[2] + '-' + str(index)},
                'spec': {'storageClassName': value['storageClass']}}) for index in range(count)).encode()
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(bundle, 'prepared_artifact', side_effect=lambda name: Path('/synthetic/' + name + '.tgz')), \
                patch.object(bundle, 'run', side_effect=rendered) as run:
            output = Path(directory) / 'render'
            bundle.render(value, output)
            report = json.loads((output / 'report.json').read_text())
        self.assertEqual(run.call_count, len(bundle.COMPONENTS))
        for component, invocation in zip(bundle.COMPONENTS, run.call_args_list):
            command = invocation.args[0]
            self.assertEqual(command[:2], ['helm', 'template'])
            selected = bundle.storage_class_args(component, value)
            if selected:
                self.assertEqual(command[-len(selected):], selected)
        self.assertIn('actual deployment path disabled pending owner review', report['deploymentBlockers'])
        self.assertIn('synthetic target: no live evidence', report['deploymentBlockers'])

    def test_rendered_storage_scalar_text_is_preserved_without_broad_coercion(self):
        import yaml
        def claim():
            return {'storageClassName': 'SCALAR_SELECTION', 'testBoolean': True}
        # Match the pinned chart shapes: Valkey/SeaweedFS/Homarr standalone
        # claims, PostgreSQL's template, and ClickHouse/Keeper operator claims.
        documents = [{'kind': 'PersistentVolumeClaim', 'spec': claim()} for _ in range(3)]
        documents += [{'kind': 'StatefulSet', 'spec': {'volumeClaimTemplates': [{'spec': claim()}]}}]
        documents += [{'kind': kind, 'spec': {'dataVolumeClaimSpec': claim()}}
                      for kind in ('ClickHouseCluster', 'KeeperCluster')]
        source = yaml.safe_dump_all(documents)
        for storage in ('true', 'null', '0123', '2026-11-03', 'review-storage'):
            payload = source.replace('storageClassName: SCALAR_SELECTION', 'storageClassName: ' + storage)
            result = bundle.preserve_storage_class(list(yaml.safe_load_all(payload)),
                list(yaml.load_all(payload, Loader=yaml.BaseLoader)), storage)
            roundtrip = list(yaml.safe_load_all(yaml.safe_dump_all(result)))
            claims = list(bundle.storage_claim_specs(roundtrip))
            with self.subTest(storage=storage):
                self.assertEqual(len(claims), 6)
                self.assertTrue(all(item['storageClassName'] == storage for item in claims))
                self.assertTrue(all(item['testBoolean'] is True for item in claims))

    def test_rendered_storage_missing_wrong_or_changed_inventory_is_not_repaired(self):
        for count, selected in ((5, 'review-storage'), (7, 'review-storage'), (6, None), (6, 'other-storage')):
            documents = [{'kind': 'PersistentVolumeClaim', 'spec': {'storageClassName': selected}} for _ in range(count)]
            with self.subTest(count=count, selected=selected), self.assertRaises(bundle.Blocked):
                bundle.preserve_storage_class(documents, documents, 'review-storage')

    def test_rendered_namespace_scalar_text_is_preserved_without_broad_coercion(self):
        import yaml
        for namespace in ('true', 'null', '0123', '2026-11-03', 'review-namespace'):
            payload = ('kind: ConfigMap\nmetadata:\n  name: reviewed\n  namespace: ' + namespace +
                       '\ndata:\n  unrelated: true\n---\nkind: Service\nmetadata:\n  name: implicit\n')
            result = bundle.preserve_namespace(list(yaml.safe_load_all(payload)),
                list(yaml.load_all(payload, Loader=yaml.BaseLoader)), namespace)
            roundtrip = list(yaml.safe_load_all(yaml.safe_dump_all(result)))
            with self.subTest(namespace=namespace):
                self.assertEqual(roundtrip[0]['metadata']['namespace'], namespace)
                self.assertIs(roundtrip[0]['data']['unrelated'], True)
                self.assertNotIn('namespace', roundtrip[1]['metadata'])

    def test_namespace_mismatch_is_not_repaired(self):
        docs = [{'kind': 'ConfigMap', 'metadata': {'namespace': 'other'}}]
        with self.assertRaises(bundle.Blocked):
            bundle.preserve_namespace(docs, docs, 'selected')
        with self.assertRaises(bundle.Blocked):
            bundle.preserve_namespace(docs, [], 'selected')

    def test_vendor_media_patch_only_gates_media_environment(self):
        source = (b'EVENT_UPLOAD_UNCHANGED\n- name: LANGFUSE_S3_MEDIA_UPLOAD_BUCKET\n'
                  b'  value: synthetic-bucket\n- name: LANGFUSE_S3_MEDIA_UPLOAD_ACCESS_KEY_ID\n'
                  b'  valueFrom: synthetic-reference\n{{- if hasKey .Values.s3 "concurrency" }}\n'
                  b'CONCURRENCY_UNCHANGED\n{{- end }}\n')
        digest = bundle.hashlib.sha256(source).hexdigest()
        result = bundle.patch_media_template(source, digest)
        expected = source.replace(b'- name: LANGFUSE_S3_MEDIA_UPLOAD_BUCKET\n',
            b'{{- if .Values.s3.mediaUpload.enabled }}\n- name: LANGFUSE_S3_MEDIA_UPLOAD_BUCKET\n')
        expected = expected.replace(b'{{- if hasKey .Values.s3 "concurrency" }}\n',
            b'{{- end }}\n{{- if hasKey .Values.s3 "concurrency" }}\n')
        self.assertEqual(result, expected)
        with self.assertRaises(bundle.Blocked):
            bundle.patch_media_template(source + b'changed', digest)
        for bad in (b'other', source + source,
                    b'{{- if hasKey .Values.s3 "concurrency" }}\n- name: LANGFUSE_S3_MEDIA_UPLOAD_BUCKET\n'):
            with self.assertRaises(bundle.Blocked):
                bundle.patch_media_template(bad, bundle.hashlib.sha256(bad).hexdigest())

    def test_vendor_patch_is_checksum_bound_and_pre_render(self):
        source = b'{{- if or .Values.sftp.enabled .Values.allInOne.enabled }}\nSYNTHETIC\n{{- end }}'
        digest = bundle.hashlib.sha256(source).hexdigest()
        result = bundle.patch_sftp_template(source, digest)
        self.assertIn(b'.Values.allInOne.sftp.enabled', result)
        with self.assertRaises(bundle.Blocked): bundle.patch_sftp_template(source + b'changed', digest)
        with self.assertRaises(bundle.Blocked): bundle.patch_sftp_template(b'other', bundle.hashlib.sha256(b'other').hexdigest())

    def test_locked_bucket_hook_is_hardened(self):
        job = {'kind':'Job','metadata':{'name':'langfuse-bucket-hook'},'spec':{'template':{'spec':{}}}}
        pod = bundle.harden_hooks([job])[0]['spec']['template']['spec']
        self.assertIs(pod['automountServiceAccountToken'], False)
        self.assertEqual(pod['serviceAccountName'], 'langfuse-seaweedfs')
        with self.assertRaises(bundle.Blocked):
            bundle.harden_hooks([{'kind':'Job','metadata':{'name':'unreviewed'}}])

    def test_default_never_executes(self):
        with patch.object(sys, 'argv', ['bundle.py']), patch.object(bundle.subprocess, 'run', side_effect=AssertionError('external execution')):
            bundle.main()

    def test_synthetic_fails_all_production_gates(self):
        value = bundle.load(ROOT / 'fixtures/target.synthetic.json')
        self.assertTrue(set(bundle.GATES).issubset(bundle.blockers(value)))
        with self.assertRaises(bundle.Blocked):
            bundle.target(ROOT / 'fixtures/target.synthetic.json', live=True)

    def test_apply_unconditionally_unavailable(self):
        with patch.object(sys, 'argv', ['bundle.py', 'deploy']), patch.object(bundle.subprocess, 'run', side_effect=AssertionError('external execution')):
            with self.assertRaises(SystemExit) as result:
                bundle.main()
            self.assertEqual(result.exception.code, 2)

    def test_inspection_denies_secrets_cluster_permissions_and_exposure(self):
        docs = [{'kind':'Secret','metadata':{'name':'x'}}, {'kind':'ClusterRole'},
                {'kind':'Service','spec':{'type':'NodePort'}},
                {'kind':'Deployment','spec':{'template':{'spec':{'hostNetwork':True,'containers':[{'image':'test:latest'}]}}}}]
        issues = bundle.inspect_documents(docs, 'staged')
        for issue in ('chart-generated credential material forbidden', 'external service exposure forbidden',
                      'host namespace access forbidden', 'image digest unresolved'):
            self.assertIn(issue, issues)

    def test_namespace_escape_and_duplicate(self):
        doc = {'kind':'ConfigMap','metadata':{'namespace':'other','name':'x'}}
        self.assertIn('resource outside selected namespace', bundle.inspect_documents([doc], 'staged'))
        self.assertIn('duplicate resource identity', bundle.inspect_documents([doc, doc], 'staged'))

    def test_preflight_rejects_wrong_binding_before_broader_reads(self):
        with patch.object(bundle, 'run', return_value=b'wrong') as call:
            with self.assertRaises(bundle.Blocked):
                bundle.preflight({'context':'explicit','namespace':'staged','namespaceUid':'correct'}, '/unused')
            self.assertEqual(call.call_count, 1)
            self.assertEqual(call.call_args.args[0][4:7], ['get','namespace','staged'])

    def test_preflight_uses_minimal_projections(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'preflight.json'
            with patch.object(bundle, 'run', side_effect=[b'correct', b'True\nFalse\n', b'Bound\n', b'Running\nPending\n', b'CustomResourceDefinition\n', b'synthetic']) as call:
                bundle.preflight({'context':'explicit','namespace':'staged','namespaceUid':'correct','storageClass':'synthetic'}, output)
            report = json.loads(output.read_text())
            self.assertEqual(report['observations']['nodes']['notReady'], 1)
            self.assertEqual(report['observations']['pods']['notRunningOrSucceeded'], 1)
            for invocation in call.call_args_list:
                self.assertTrue(invocation.args[0][-1].startswith('jsonpath='))
                self.assertNotIn('env', invocation.args[0][-1])
            pod_projection = call.call_args_list[3].args[0][-1]
            self.assertEqual(pod_projection, 'jsonpath={range .items[*]}{.status.phase}{"\\n"}{end}')

    def test_output_must_be_outside_repository(self):
        for path in (ROOT / 'new-output', ROOT / 'rendered/new', ROOT.parent / 'sibling-output'):
            with self.subTest(path=path), self.assertRaises(bundle.Blocked):
                bundle.private_output(path)

    def test_invalid_identifier_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'target.json'
            value = bundle.load(ROOT / 'fixtures/target.synthetic.json')
            value['context'] = '--malicious-option'
            path.write_text(json.dumps(value))
            with self.assertRaises(bundle.Blocked): bundle.target(path)

    def test_missing_cache_does_not_fetch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'artifacts.lock.json').write_text(json.dumps({'artifacts': {'a': {'sha256':'a'*64,'filename':'a.tgz','url':'https://example.invalid'}}}))
            with patch.object(bundle, 'ROOT', root), patch.object(bundle.urllib.request, 'urlopen', side_effect=AssertionError('network')):
                with self.assertRaises(bundle.Blocked): bundle.artifact('a')

    def test_checksum_corruption_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.runtime/artifacts').mkdir(parents=True)
            (root / '.runtime/artifacts/a.tgz').write_bytes(b'corrupted')
            (root / 'artifacts.lock.json').write_text(json.dumps({'artifacts': {'a': {'sha256':'a'*64,'filename':'a.tgz'}}}))
            with patch.object(bundle, 'ROOT', root):
                with self.assertRaises(bundle.Blocked): bundle.artifact('a')

if __name__ == '__main__': unittest.main()
