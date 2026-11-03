"""Future authorized Docker validation only; current revision tests are UNRUN."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

contract = module('cluster_contract')
budget = module('resource_report')


class ContractTests(unittest.TestCase):
    def config(self):
        return json.loads((ROOT / 'contracts/future-cluster.example.json').read_text())

    def test_example_is_inert_and_missing_essential_values(self):
        report = contract.assess(self.config())
        self.assertFalse(report['deploymentAllowed'])
        self.assertFalse(report['canPrepareBundleRenderInputs'])
        self.assertEqual(report['missingBundleRenderInputs'], ['target.kubernetesVersion', 'target.storageClass'])

    def test_no_approval_or_extra_secret_fields(self):
        for key, value in [('deploymentApproved', True), ('ciReenableApproved', True), ('secretValue', 'PUBLIC-TEST')]:
            config = self.config()
            config['authorization'][key] = value
            with self.assertRaises(ValueError):
                contract.assess(config)
        config = self.config()
        config['capacity']['rootFreeGiB'] = True
        with self.assertRaises(ValueError):
            contract.assess(config)

    def test_no_credential_origin_or_render_incompatible_fields(self):
        for section, key, value in [('tokscale', 'privateOrigin', 'https://user:password@private.invalid'),
                                    ('target', 'storageClass', 'not.a.label'),
                                    ('target', 'namespace', 'n' * 64),
                                    ('tokscale', 'gatewayPodLabel', 'g' * 64),
                                    ('tokscale', 'appImage', 'UPPER@sha256:' + 'a' * 64)]:
            config = self.config()
            config[section][key] = value
            with self.assertRaises(ValueError):
                contract.assess(config)
        with self.assertRaises(ValueError):
            json.loads('{"mode":"a","mode":"b"}', object_pairs_hook=contract.no_duplicates)

    def test_claims_never_authorize(self):
        config = self.config()
        for value in config['capabilities'].values():
            value.update(status='evidence-supplied', evidenceRef='private-evidence-ref')
        report = contract.assess(config)
        self.assertFalse(report['deploymentAllowed'])
        self.assertGreater(report['evidenceClaimsNotVerified'], 0)

    def test_operator_missing_identity_and_apis_are_explicit(self):
        report = contract.assess(self.config())
        self.assertIn('actual operator version missing', report['blockers'])
        self.assertIn('actual operator/CRD revision missing', report['blockers'])
        self.assertTrue(any(item.startswith('required operator APIs not reported: ') for item in report['blockers']))

    def test_operator_mismatch_distinguished_from_missing_facts(self):
        config = self.config()
        config['operators']['clickhouse'].update(observedVersion='v0.0.7', observedCommit='0' * 40,
            servedApis=['clickhouse.com/v1alpha1/ClickHouseCluster'])
        report = contract.assess(config)
        self.assertIn('actual operator version differs from reviewed candidate', report['blockers'])
        self.assertIn('actual operator/CRD revision differs from reviewed candidate', report['blockers'])
        self.assertIn('required operator APIs not reported: clickhouse.com/v1alpha1/KeeperCluster', report['blockers'])
        self.assertNotIn('actual operator version missing', report['blockers'])
        self.assertNotIn('actual operator/CRD revision missing', report['blockers'])
        self.assertFalse(report['deploymentAllowed'])

    def test_matching_operator_report_is_not_verification_or_approval(self):
        config = self.config()
        operator = config['operators']['clickhouse']
        operator.update(observedVersion=operator['candidateVersion'], observedCommit=operator['candidateCommit'],
                        servedApis=sorted(contract.OPERATOR_APIS))
        report = contract.assess(config)
        self.assertIn('reported operator identity and served APIs require independent verification', report['blockers'])
        self.assertFalse(any('differs from reviewed candidate' in item for item in report['blockers']))
        self.assertFalse(any(item.startswith('required operator APIs not reported: ') for item in report['blockers']))
        self.assertFalse(report['deploymentAllowed'])

    def test_operator_candidate_is_bound_to_authoritative_lock(self):
        locked = json.loads(contract.OPERATOR_LOCK.read_text())
        for key, value in [('candidateVersion', 'v0.0.7'), ('commit', '0' * 40)]:
            changed = dict(locked, **{key: value})
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'operator.lock.json'
                path.write_text(json.dumps(changed))
                with patch.object(contract, 'OPERATOR_LOCK', path), self.assertRaises(ValueError):
                    contract.assess(self.config())

    def test_operator_placeholder_version_is_missing_not_verified(self):
        config = self.config()
        config['operators']['clickhouse']['observedVersion'] = 'REQUIRED'
        report = contract.assess(config)
        self.assertIn('actual operator version missing', report['blockers'])
        self.assertNotIn('REQUIRED', json.dumps(report))

    def test_packet_preserves_render_selection_not_live_readiness(self):
        config = self.config()
        config['target'].update(kubernetesVersion='1.32.0', storageClass='review-storage',
                                contextRef='private-context-ref', namespaceUid='private-namespace-ref')
        documents = contract.packet_documents(config)
        target = documents['render-target.json']
        self.assertEqual(target['storageClass'], 'review-storage')
        self.assertEqual(target['kubernetesVersion'], '1.32.0')
        self.assertTrue(documents['assessment.json']['canPrepareBundleRenderInputs'])
        self.assertFalse(documents['assessment.json']['deploymentAllowed'])
        self.assertFalse(documents['packet-lock.json']['renderExecuted'])
        self.assertIs(target['synthetic'], True)
        self.assertIs(target['storageBackingVerified'], False)
        self.assertEqual(target['context'], 'synthetic-not-a-cluster')
        self.assertNotEqual(target['namespaceUid'], config['target']['namespaceUid'])

    def test_packet_is_synthetic_private_write_once(self):
        config = self.config()
        config['target'].update(kubernetesVersion='1.32.0', storageClass='review-storage')
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'packet'
            contract.packet(config, out)
            target = json.loads((out / 'render-target.json').read_text())
            self.assertIs(target['synthetic'], True)
            self.assertIs(target['capacityVerified'], False)
            self.assertEqual(target['context'], 'synthetic-not-a-cluster')
            self.assertEqual(out.stat().st_mode & 0o777, 0o700)
            self.assertEqual((out / 'render-target.json').stat().st_mode & 0o777, 0o600)
            with self.assertRaises(ValueError):
                contract.packet(config, out)

    def test_packet_missing_inputs_and_repo_destination_blocked(self):
        with self.assertRaises(ValueError):
            contract.packet(self.config(), ROOT / 'bad-packet')
        config = self.config()
        config['target'].update(kubernetesVersion='1.32.0', storageClass='review-storage')
        with self.assertRaises(ValueError):
            contract.packet(config, ROOT / 'bad-packet')


class BudgetTests(unittest.TestCase):
    def workload(self, replicas=2):
        return {'kind': 'Deployment', 'spec': {'replicas': replicas, 'template': {'spec': {
            'containers': [{'resources': {'requests': {'cpu': '250m', 'memory': '128Mi'}}}],
            'initContainers': [{'resources': {'requests': {'cpu': '100m', 'memory': '64Mi'}}}],
        }}}}

    def test_conservative_sum_not_fit_claim(self):
        result = budget.report([None, self.workload()])
        self.assertEqual(result['declaredCpuMillicores'], 700)
        self.assertEqual(result['declaredMemoryBytes'], 384 * 1024**2)
        self.assertFalse(result['fitApproved'])

    def test_zero_replicas_and_custom_resources_stay_blocked(self):
        result = budget.report([self.workload(0), {'kind': 'ClickHouseCluster'}])
        self.assertEqual(result['zeroReplicaWorkloadsCount'], 1)
        self.assertIn('unbudgeted resource kind: ClickHouseCluster', result['blockers'])

    def test_missing_requests_not_silently_approved(self):
        obj = self.workload()
        del obj['spec']['template']['spec']['containers'][0]['resources']
        self.assertIn('container cpu request missing/unsupported', budget.report([obj])['blockers'])

    def test_quantities_and_bad_inputs(self):
        self.assertEqual(budget.quantity('1.5Gi'), 1610612736)
        self.assertEqual(budget.quantity('0.125', cpu=True), 125)
        for value in ('-1Gi', 'abc', True, '1e6'):
            with self.assertRaises(ValueError):
                budget.quantity(value)
