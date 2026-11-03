"""Synthetic orchestration regressions; execute only via the Docker runner."""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location('kubernetes_checks', Path(__file__).resolve().parents[1] / 'kubernetes.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def crd(schema=None):
    return {
        'apiVersion': 'apiextensions.k8s.io/v1', 'kind': 'CustomResourceDefinition',
        'spec': {'group': 'example.invalid', 'names': {'kind': 'Widget'}, 'versions': [
            {'name': 'v1', 'served': True, 'schema': {'openAPIV3Schema': schema or {
                'type': 'object', 'properties': {'spec': {'type': 'object', 'properties': {'size': {'type': 'integer'}}}},
            }}},
        ]},
    }


class SchemaTests(unittest.TestCase):
    def schema_lock(self):
        revision = 'a' * 40
        return {'revision': revision, 'urlTemplate': (
            'https://raw.githubusercontent.com/yannh/kubernetes-json-schema/' + revision
            + '/{{.NormalizedKubernetesVersion}}-standalone{{.StrictSuffix}}/'
            '{{.ResourceKind}}{{.KindSuffix}}.json'
        )}

    def test_duplicate_identical_crd_is_allowed_conflict_fails(self):
        definition = crd()
        self.assertEqual(len(MODULE.collect_crds([definition, copy.deepcopy(definition)])), 1)
        changed = copy.deepcopy(definition)
        changed['spec']['versions'][0]['schema']['openAPIV3Schema']['properties']['spec']['properties']['size']['type'] = 'string'
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            MODULE.collect_crds([definition, changed])

    def test_missing_or_unserved_schema_is_not_accepted(self):
        definition = crd()
        del definition['spec']['versions'][0]['schema']
        with self.assertRaisesRegex(ValueError, 'Missing structural schema'):
            MODULE.collect_crds([definition])
        definition = crd()
        definition['spec']['versions'][0]['served'] = False
        self.assertEqual(MODULE.collect_crds([definition]), {})

    def test_nullable_extends_type_without_bypassing_enum(self):
        result = MODULE.normalize_schema({'type': 'string', 'enum': ['a'], 'nullable': True})
        self.assertEqual(result, {'type': ['string', 'null'], 'enum': ['a']})

    def test_nullable_keeps_composition_constraints_and_explicit_null_enum(self):
        schema = {'type': 'string', 'enum': ['a', None], 'nullable': True,
                  'allOf': [{'enum': ['a']}], 'not': {'enum': ['b']}}
        result = MODULE.normalize_schema(schema)
        self.assertEqual(result['type'], ['string', 'null'])
        self.assertEqual(result['enum'], ['a', None])
        self.assertEqual(result['allOf'], [{'enum': ['a']}])
        self.assertEqual(result['not'], {'enum': ['b']})
        self.assertNotIn('anyOf', result)

    def test_nullable_without_type_does_not_invent_a_null_override(self):
        self.assertEqual(MODULE.normalize_schema({'enum': ['a'], 'nullable': True}), {'enum': ['a']})

    def test_int_or_string_keeps_existing_restrictions(self):
        result = MODULE.normalize_schema({'x-kubernetes-int-or-string': True, 'type': 'string', 'minimum': 0})
        self.assertEqual(result['type'], ['integer', 'string'])
        self.assertEqual(result['minimum'], 0)

    def test_nullable_int_or_string_keeps_enum_restriction(self):
        result = MODULE.normalize_schema({'x-kubernetes-int-or-string': True, 'nullable': True, 'enum': [1, 'a']})
        self.assertEqual(result['type'], ['integer', 'string', 'null'])
        self.assertEqual(result['enum'], [1, 'a'])

    def test_schema_keyword_property_names_are_not_reinterpreted(self):
        result = MODULE.normalize_schema({'type': 'object', 'properties': {
            'nullable': {'type': 'boolean'}, 'properties': {'type': 'string'},
        }})
        self.assertEqual(result['properties'], {
            'nullable': {'type': 'boolean'}, 'properties': {'type': 'string'},
        })
        self.assertFalse(result['additionalProperties'])

    def test_strict_properties_preserve_explicit_maps_and_open_subtrees(self):
        result = MODULE.normalize_schema({'type': 'object', 'properties': {
            'closed': {'type': 'object', 'properties': {'a': {'type': 'string'}}},
            'map': {'type': 'object', 'additionalProperties': {'type': 'string'}},
            'open': {'type': 'object', 'x-kubernetes-preserve-unknown-fields': True, 'properties': {'a': {'type': 'string'}}},
        }})
        self.assertFalse(result['additionalProperties'])
        self.assertFalse(result['properties']['closed']['additionalProperties'])
        self.assertEqual(result['properties']['map']['additionalProperties'], {'type': 'string'})
        self.assertTrue(result['properties']['open']['additionalProperties'])

    def test_metadata_uses_pinned_builtin_schema_not_empty_crd_object(self):
        metadata = {'type': 'object', 'properties': {'name': {'type': 'string'}}, 'additionalProperties': False}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            MODULE.write_crd_schemas(MODULE.collect_crds([crd()]), path, metadata)
            result = json.loads((path / 'example.invalid/widget_v1.json').read_text())
        self.assertEqual(result['properties']['metadata'], metadata)
        self.assertEqual(result['properties']['apiVersion']['enum'], ['example.invalid/v1'])
        self.assertEqual(result['properties']['kind']['enum'], ['Widget'])
        self.assertIn('metadata', result['required'])

    def test_declared_metadata_constraints_preserved_without_closing_name_only_schema(self):
        metadata = {'type': 'object', 'properties': {
            'name': {'type': 'string'}, 'namespace': {'type': 'string'},
            'labels': {'type': 'object', 'additionalProperties': {'type': 'string'}},
        }, 'additionalProperties': False}
        declared = {'type': 'object', 'properties': {'name': {'type': 'string', 'pattern': '^reviewed-'}},
                    'required': ['name']}
        definition = crd({'type': 'object', 'properties': {'metadata': declared}})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            MODULE.write_crd_schemas(MODULE.collect_crds([definition]), path, metadata)
            result = json.loads((path / 'example.invalid/widget_v1.json').read_text())
        built_in, restriction = result['properties']['metadata']['allOf']
        self.assertEqual(built_in, metadata)
        self.assertEqual(restriction, declared)
        self.assertNotIn('additionalProperties', restriction)
        self.assertEqual(restriction['properties']['name']['pattern'], '^reviewed-')

    def test_declared_api_and_kind_constraints_are_not_overwritten(self):
        definition = crd({'type': 'object', 'properties': {
            'apiVersion': {'type': 'string', 'pattern': '^example[.]invalid/'},
            'kind': {'type': 'string', 'pattern': '^Widget$'},
        }})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            MODULE.write_crd_schemas(MODULE.collect_crds([definition]), path, {'type': 'object'})
            result = json.loads((path / 'example.invalid/widget_v1.json').read_text())
        self.assertEqual(result['properties']['apiVersion']['allOf'][0]['pattern'], '^example[.]invalid/')
        self.assertEqual(result['properties']['kind']['allOf'][0]['pattern'], '^Widget$')

    def test_mutable_or_unexpected_schema_source_rejected(self):
        lock = self.schema_lock()
        lock['revision'] = 'master'
        with self.assertRaises(ValueError):
            MODULE.schema_location(lock)
        lock = self.schema_lock()
        lock['urlTemplate'] = 'https://example.invalid/schema.json'
        with self.assertRaises(ValueError):
            MODULE.schema_location(lock)

    def test_kubeconform_never_skips_and_keeps_requested_version(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(MODULE, 'run') as run:
            path = Path(directory)
            MODULE.validate_files([path / 'manifest.yaml'], {}, self.schema_lock(), '1.32.0', path)
        command = run.call_args.args[0]
        self.assertIn('-strict', command)
        self.assertEqual(command[command.index('-kubernetes-version') + 1], '1.32.0')
        self.assertNotIn('-ignore-missing-schemas', command)
        self.assertNotIn('-skip', command)
        self.assertNotIn('default', command)

    def test_missing_schema_failure_propagates(self):
        error = subprocess.CalledProcessError(1, ['kubeconform'])
        with tempfile.TemporaryDirectory() as directory, patch.object(MODULE, 'run', side_effect=error):
            path = Path(directory)
            with self.assertRaises(subprocess.CalledProcessError):
                MODULE.validate_files([path / 'unknown.yaml'], {}, self.schema_lock(), '1.37.1', path)

    def test_static_manifest_discovery_covers_new_paths_not_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'new-area').mkdir()
            manifest = root / 'new-area/namespace.yml'
            manifest.write_text('apiVersion: v1\nkind: Namespace\nmetadata: {name: synthetic}\n')
            (root / 'values.yaml').write_text('server: {enabled: false}\n')
            (root / '.runtime').mkdir()
            (root / '.runtime/ignored.yaml').write_text('kind: Incomplete\n')
            self.assertEqual(MODULE.static_manifests(root), [manifest])
            (root / 'incomplete.yaml').write_text('apiVersion: v1\n')
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                MODULE.static_manifests(root)

    def test_all_four_primary_charts_are_explicit(self):
        self.assertEqual({name for name, _ in MODULE.PRIMARY_CHARTS}, {'argocd', 'openbao', 'homarr', 'external-secrets'})

    def test_application_keeps_target_version_and_narrow_lint_override(self):
        target = {'synthetic': True, 'kubernetesVersion': '1.32.0'}

        def render(value, destination):
            self.assertIs(value, target)
            destination.mkdir()
            (destination / 'manifests.yaml').write_text('apiVersion: v1\nkind: Namespace\nmetadata: {name: synthetic}\n')

        def operator_bytes(item):
            value = crd()
            value['spec']['group'] = 'clickhouse.com'
            value['spec']['names']['kind'] = item['kind']
            value['spec']['versions'][0]['name'] = 'v1alpha1'
            return MODULE.yaml.safe_dump(value).encode()

        bundle = SimpleNamespace(
            target=lambda path: target,
            COMPONENTS={'langfuse': ('langfuse', 'langfuse'), 'collector': ('otel-collector', 'collector'),
                        'homarr': ('homarr-workload', 'homarr-workload')},
            artifact=lambda name, fetch: None,
            prepared_artifact=lambda name: Path('/synthetic/' + name + '.tgz'),
            render=render,
        )
        lock = {'files': {'clickhouseclusters.yaml': {'kind': 'ClickHouseCluster'},
                          'keeperclusters.yaml': {'kind': 'KeeperCluster'}}}
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(MODULE, 'load_module', return_value=bundle), \
                patch.object(MODULE, 'read_json', return_value=lock), \
                patch.object(MODULE, 'locked_bytes', side_effect=operator_bytes), \
                patch.object(MODULE, 'run') as run, \
                patch.object(MODULE, 'validate_files') as validate, \
                patch.object(MODULE, 'tokscale') as tokscale:
            root = Path(directory) / 'repo'
            MODULE.application(root, Path(directory), self.schema_lock())
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(len(commands), 3)
        self.assertTrue(all(command[:2] == ['helm', 'lint'] for command in commands))
        self.assertTrue(all(command[command.index('--kube-version') + 1] == '1.32.0' for command in commands))
        self.assertIn('clickhouse.crdCheck=false', commands[0])
        self.assertTrue(all('clickhouse.crdCheck=false' not in command for command in commands[1:]))
        self.assertEqual(validate.call_args.args[3], '1.32.0')
        self.assertEqual(len(validate.call_args.args[1]), 2)
        tokscale.assert_called_once()

    def test_tokscale_synthetic_fixture_zero_replicas_and_version(self):
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory, patch.object(MODULE, 'validate_files') as validate:
            scratch = Path(directory)
            MODULE.tokscale(root, scratch, self.schema_lock())
            manifests = MODULE.documents((scratch / 'tokscale-synthetic.yaml').read_text())
            for obj in manifests:
                if obj['kind'] in {'Deployment', 'StatefulSet'}:
                    self.assertEqual(obj['spec']['replicas'], 0)
                    for container in obj['spec']['template']['spec']['containers']:
                        self.assertTrue(container['image'].startswith('example.invalid/'))
        expected = json.loads((root / 'primary-infrastructure/artifacts.lock.json').read_text())['kubernetesVersion']
        self.assertEqual(validate.call_args.args[3], expected)


if __name__ == '__main__':
    unittest.main()
