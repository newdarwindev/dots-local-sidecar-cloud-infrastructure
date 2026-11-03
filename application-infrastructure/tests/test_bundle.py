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
