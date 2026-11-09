import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('formation_settings', ROOT / 'application-infrastructure/formation_settings.py')
SETTINGS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SETTINGS)


def fixture():
    return {'processors': {'transform/privacy': {'trace_statements': [
        {'context': 'span', 'statements': [
            'keep_keys(resource.attributes, [])',
            SETTINGS.KEEP_NONE,
            'set(span.attributes["langfuse.environment"], "local-codex")',
            'set(span.status.message, "")']}]}},
        'receivers': {'unchanged': True}, 'exporters': {'unchanged': True}}


class FormationSettingsTests(unittest.TestCase):
    def test_only_two_statements_change_and_input_is_untouched(self):
        original = fixture()
        actual = SETTINGS.attribution_config(original, ['workstation-a', 'workstation-b'])
        self.assertEqual(original, fixture())
        statements = actual['processors']['transform/privacy']['trace_statements'][0]['statements']
        expected = fixture()
        expected['processors']['transform/privacy']['trace_statements'][0]['statements'][1:3] = statements[1:3]
        self.assertEqual(actual, expected)
        self.assertEqual(statements[1], SETTINGS.KEEP_ENVIRONMENT)
        self.assertIn('where not ContainsValue(["workstation-a", "workstation-b"]', statements[2])
        self.assertEqual(SETTINGS.attribution_config(actual, ['workstation-a', 'workstation-b']), actual)

    def test_labels_are_bounded_and_no_code_injection(self):
        for labels in [[], ['x', 'x'], ['local-codex'], ['private/name'], ['x' * 33], [None], ['x"); bad()']]:
            with self.subTest(labels=labels), self.assertRaises(ValueError):
                SETTINGS.attribution_config(fixture(), labels)

    def test_drift_is_rejected(self):
        original = fixture()
        statements = original['processors']['transform/privacy']['trace_statements'][0]['statements']
        statements[1] = 'keep_keys(span.attributes, ["unexpected"])'
        with self.assertRaises(ValueError):
            SETTINGS.attribution_config(original, ['workstation-a'])


class BatchingDotenvTests(unittest.TestCase):
    def test_native_startup_file_contains_only_reviewed_sdk_keys(self):
        actual = SETTINGS.batching_dotenv('')
        self.assertEqual(actual, 'OTEL_BSP_MAX_EXPORT_BATCH_SIZE=1\nOTEL_BSP_SCHEDULE_DELAY=100\n')
        self.assertEqual(SETTINGS.batching_dotenv(actual), actual)

    def test_existing_comments_and_settings_are_preserved(self):
        before = '# Existing comment\nOTEL_BSP_MAX_EXPORT_BATCH_SIZE=1'
        self.assertEqual(SETTINGS.batching_dotenv(before), before + '\nOTEL_BSP_SCHEDULE_DELAY=100\n')

    def test_conflicts_duplicates_and_unknown_values_are_rejected(self):
        for before in ['OTHER_KEY=value', 'OTEL_BSP_SCHEDULE_DELAY=5000',
                       'OTEL_BSP_MAX_EXPORT_BATCH_SIZE=1\nOTEL_BSP_MAX_EXPORT_BATCH_SIZE=1',
                       'export OTEL_BSP_MAX_EXPORT_BATCH_SIZE=1',
                       'OTEL_BSP_MAX_EXPORT_BATCH_SIZE="1"', 'BAD=\x00', None]:
            with self.subTest(before=before), self.assertRaises(ValueError):
                SETTINGS.batching_dotenv(before)
