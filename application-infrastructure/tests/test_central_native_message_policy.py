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
