"""Pure central route patch tests; synthetic objects, Docker workflow only."""
import copy
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location('central_native', Path(__file__).resolve().parents[1] / 'central_native_message_policy.py')
POLICY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POLICY)
FRESH = '11111111-1111-4111-8111-111111111111'


def fixture():
    return {'receivers': {'otlp': {'synthetic': 'unchanged'}}, 'extensions': {'synthetic': {'preserve': True}},
            'connectors': {POLICY.ROUTER: {'error_mode': 'propagate', 'default_pipelines': ['traces/diagnostics'], 'table': [copy.deepcopy(POLICY.PLUGIN_ROW)]}},
            'processors': {name: {'synthetic': 'unchanged'} for name in ('memory_limiter', 'filter/privacy', 'transform/privacy', 'batch', 'filter/conversations', 'transform/conversations', 'batch/conversations')},
            'exporters': {'otlphttp/langfuse': {'synthetic': 'diagnostics'}, 'otlphttp/conversations': {'synthetic': 'conversation'}},
            'service': {'pipelines': copy.deepcopy(POLICY.BASE_PIPELINES)}}


class CentralNativePolicyTests(unittest.TestCase):
    def test_reviewed_update_preserves_durable_graph_and_guards_original_policy(self):
        old = {'enrolled': {FRESH: 2000000000}, 'denied': [], 'future_after_ns': None, 'tool_results': False}
        new = dict(old, future_after_ns=3000000000, tool_results=True)
        original = POLICY.patch_config(fixture(), **old)
        for pipeline in original['service']['pipelines'].values():
            pipeline['processors'] = [p for p in pipeline['processors'] if not p.startswith('batch')]
        original['extensions']['file_storage/queues'] = {'fsync': True, 'synthetic': 'preserve'}
        for exporter in original['exporters'].values():
            exporter['sending_queue'] = {'enabled': True, 'sizer': 'bytes', 'storage': 'file_storage/queues',
                                         'batch': {'sizer': 'items', 'max_size': 32}}
        before = copy.deepcopy(original)
        updated = POLICY.reviewed_update(original, old, new)
        self.assertEqual(original, before)
        self.assertEqual(POLICY.reviewed_update(updated, new, new), updated)
        self.assertEqual(POLICY.reviewed_update(updated, new, old), original)
        restored = copy.deepcopy(updated)
        for name in (POLICY.FILTER, POLICY.TRANSFORM):
            restored['processors'][name] = original['processors'][name]
        restored['connectors'][POLICY.ROUTER] = original['connectors'][POLICY.ROUTER]
        self.assertEqual(restored, original)
        bad = copy.deepcopy(original); bad['processors'][POLICY.FILTER]['traces']['span'][0] = 'false'
        with self.assertRaises(ValueError): POLICY.reviewed_update(bad, old, new)
        bad = copy.deepcopy(original); bad['extensions']['file_storage/queues']['fsync'] = False
        with self.assertRaises(ValueError): POLICY.reviewed_update(bad, old, new)
        bad = copy.deepcopy(original); bad['service']['pipelines'][POLICY.PIPELINE]['processors'].append('batch')
        with self.assertRaises(ValueError): POLICY.reviewed_update(bad, old, new)
        for proposed in (dict(new, enrolled={}), dict(new, enrolled={FRESH: 1999999999}),
                         dict(new, denied=None), {'enrolled': {}, 'denied': []}):
            with self.assertRaises(ValueError): POLICY.reviewed_update(original, old, proposed)
        with self.assertRaises(ValueError):
            POLICY.reviewed_update(original, dict(old, denied=[FRESH]), new)
        with self.assertRaises(ValueError):
            POLICY.reviewed_update(updated, new, dict(new, future_after_ns=2999999999))

    def test_tool_content_route_is_explicit_and_cannot_silently_replace_policy(self):
        result = POLICY.patch_config(fixture(), {FRESH: 2000000000}, [], tool_results=True)
        row = result['connectors'][POLICY.ROUTER]['table'][0]
        self.assertIn('span.name == "codex.native.tool_result"', row['condition'])
        self.assertEqual(POLICY.patch_config(result, {FRESH: 2000000000}, [], tool_results=True), result)
        with self.assertRaises(ValueError):
            POLICY.patch_config(result, {FRESH: 2000000000}, [])
        for value in ('true', 1, None):
            with self.assertRaises(ValueError):
                POLICY.build_processors({}, [], tool_results=value)

    def test_future_enrollment_is_optional_and_no_implicit_live_update(self):
        result = POLICY.patch_config(fixture(), {}, [FRESH], future_after_ns=2000000000)
        rule = result['processors'][POLICY.FILTER]['traces']['span'][0]
        self.assertIn('>= 2000000000', rule)
        self.assertIn('not ContainsValue(["' + FRESH + '"]', rule)
        with self.assertRaises(ValueError):
            POLICY.patch_config(result, {}, [FRESH], future_after_ns=2000000001)
        for cutoff in (True, False, 0, -1, 2**63, 1.5, 'all'):
            with self.assertRaises(ValueError):
                POLICY.build_processors({}, [], future_after_ns=cutoff)

    def test_only_new_components_added_and_original_immutable(self):
        original = fixture()
        before = copy.deepcopy(original)
        result = POLICY.patch_config(original, {FRESH: 2000000000}, [])
        self.assertEqual(original, before)
        self.assertEqual(result['connectors'][POLICY.ROUTER]['table'], [POLICY.ROW, POLICY.PLUGIN_ROW])
        result['connectors'][POLICY.ROUTER]['table'].remove(POLICY.ROW)
        del result['processors'][POLICY.FILTER]
        del result['processors'][POLICY.TRANSFORM]
        del result['service']['pipelines'][POLICY.PIPELINE]
        self.assertEqual(result, original)
        result['extensions']['synthetic']['preserve'] = False
        self.assertTrue(original['extensions']['synthetic']['preserve'])

    def test_exact_idempotence_and_no_implicit_policy_updates(self):
        result = POLICY.patch_config(fixture(), {FRESH: 2000000000}, [])
        self.assertEqual(POLICY.patch_config(result, {FRESH: 2000000000}, []), result)
        with self.assertRaises(ValueError):
            POLICY.patch_config(result, {FRESH: 2000000001}, [])
        with self.assertRaises(ValueError):
            POLICY.patch_config(result, {FRESH: 2000000000}, [FRESH])

    def test_unknown_shape_collision_and_missing_reference_rejected(self):
        cases = [None, [], {}]
        value = fixture(); value['connectors'][POLICY.ROUTER]['table'][0]['condition'] = 'true'; cases.append(value)
        value = fixture(); value['processors'][POLICY.FILTER] = {}; cases.append(value)
        value = fixture(); del value['processors']['memory_limiter']; cases.append(value)
        value = fixture(); value['service']['pipelines']['logs/unknown'] = {}; cases.append(value)
        value = fixture(); value['service']['pipelines']['traces/ingress']['exporters'] = ['otlphttp/langfuse']; cases.append(value)
        value = fixture(); del value['exporters']['otlphttp/conversations']; cases.append(value)
        value = fixture(); value['service']['pipelines'] = []; cases.append(value)
        for value in cases:
            with self.assertRaises(ValueError):
                POLICY.patch_config(value, {}, [])

    def test_default_deny_and_invalid_inputs(self):
        for enrolled, denied in (({}, []), ({FRESH: 1}, [FRESH])):
            self.assertEqual(POLICY.build_processors(enrolled, denied)[POLICY.FILTER]['traces']['span'][0], 'true')
        for enrolled, denied in (({'*': 1}, []), ({FRESH: True}, []), ({FRESH: -1}, []), ({}, ['bad"id']), ({}, {})):
            with self.assertRaises(ValueError):
                POLICY.build_processors(enrolled, denied)
