"""Synthetic lint-orchestration regressions; run only via validation/run.sh."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('repository_lint', Path(__file__).parents[1] / 'lint.py')
lint = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lint)


class StructureTests(unittest.TestCase):
    def test_json_rejects_duplicate_and_nonfinite_numbers(self):
        for payload in ('{"a": 1, "a": 2}', '{"a": {"b": 1, "b": 2}}',
                        '[NaN]', '[Infinity]', '[-Infinity]', '[1e999]'):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                lint.strict_json(payload)
        self.assertEqual(lint.strict_json('{"a": 1.25}'), {'a': 1.25})

    def test_yaml_duplicate_keys_and_github_on(self):
        with self.assertRaises(lint.LintError):
            lint.strict_yaml('outer:\n  duplicate: 1\n  duplicate: 2\n')
        self.assertIn('on', lint.strict_yaml('on: workflow_dispatch\n')[0])
        self.assertEqual(len(lint.strict_yaml('kind: Service\n---\nkind: ConfigMap\n')), 2)

    def test_yaml_rejects_unsafe_constructor(self):
        # BaseLoader never invokes object constructors; syntax becomes inert text.
        self.assertEqual(lint.strict_yaml('!!python/object/apply:os.system [echo]'), [['echo']])

    def test_missing_tool_is_failure(self):
        with patch.object(lint.shutil, 'which', return_value=None), self.assertRaisesRegex(lint.LintError, 'Required tools missing'):
            lint.require_tools(('hadolint', 'shellcheck'))

    def test_nested_pin_validation(self):
        for payload in ({'artifact': {'url': 'https://example.invalid/a'}},
                        {'sha256': 'placeholder'}, {'images': [{'digest': 'latest'}]},
                        {'source': {'commit': 'main'}}):
            with self.subTest(payload=payload), self.assertRaises(lint.LintError):
                lint.check_lock_values(payload, 'test')
        lint.check_lock_values({'url': 'https://example.invalid/a', 'sha256': 'a' * 64}, 'test')


class InventoryTests(unittest.TestCase):
    def test_both_bundles_new_files_and_disabled_workflow_are_discovered(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            names = ['primary-infrastructure/validation/Dockerfile',
                     'application-infrastructure/validation/Dockerfile',
                     'application-infrastructure/tokscale/Dockerfile',
                     'application-infrastructure/validation/deploy-workflow.yml.disabled',
                     'application-infrastructure/tokscale/new-test.ts',
                     'primary-infrastructure/scripts/new.py',
                     'validation/run.sh', '.github/workflows/primary.yml']
            for name in names:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('')
            files = lint.inventory(root)
            self.assertEqual(len(files['docker']), 3)
            self.assertEqual(len(files['yaml']), 2)
            commands = list(lint.lint_commands(root, files))
            actionlint = next(command for command in commands if command[0] == 'actionlint')
            self.assertIn(root / names[3], actionlint)
            self.assertEqual({command[0] for command in commands},
                             {'hadolint', 'shellcheck', 'ruff', 'yamllint', 'actionlint', 'biome'})

    def test_unknown_extension_and_symlink_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'unhandled.tf').write_text('')
            with self.assertRaisesRegex(lint.LintError, 'unclassified'):
                lint.inventory(root)
            (root / 'unhandled.tf').unlink()
            (root / 'elsewhere.py').symlink_to('/etc/passwd')
            with self.assertRaisesRegex(lint.LintError, 'symlinks'):
                lint.inventory(root)

    def test_generated_runtime_is_not_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'application-infrastructure/.runtime/random.binary'
            path.parent.mkdir(parents=True)
            path.write_bytes(b'\x00')
            self.assertEqual(lint.inventory(root), {})


class FilePolicyTests(unittest.TestCase):
    def test_docker_pin_rejects_tag_but_accepts_local_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'Dockerfile'
            lock = {'baseImage': {'reference': 'not-used-outside-validation'}}
            path.write_text('FROM python:3.14\n')
            with self.assertRaisesRegex(lint.LintError, 'full digest'):
                lint.check_docker_pins(root, [path], lock)
            path.write_text('FROM example/image@sha256:' + 'a' * 64 + ' AS base\nFROM base\n')
            lint.check_docker_pins(root, [path], lock)
            path.write_text('FROM ${UNREVIEWED_IMAGE}\n')
            with self.assertRaises(lint.LintError):
                lint.check_docker_pins(root, [path], lock)

    def test_actions_need_full_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'workflow.yml'
            path.write_text('steps:\n  - uses: actions/checkout@v5\n')
            with self.assertRaises(lint.LintError):
                lint.check_workflow_pins(path)
            path.write_text('steps:\n  - uses: actions/checkout@' + 'a' * 40 + '\n')
            lint.check_workflow_pins(path)

    def test_actual_collector_binary_source_must_match_image_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'validation').mkdir()
            (root / 'application-infrastructure/validation').mkdir(parents=True)
            lock = {'images': {'collector': {'tagReference': 'registry-1.docker.io/otel/collector:1.0',
                                             'digest': 'sha256:' + 'a' * 64}}}
            (root / 'application-infrastructure/images.lock.json').write_text(json.dumps(lock))
            for name in ('validation/Dockerfile', 'application-infrastructure/validation/Dockerfile'):
                (root / name).write_text('FROM otel/collector@sha256:' + 'a' * 64 + ' AS collector\n')
            lint.check_collector_pin(root)
            (root / 'validation/Dockerfile').write_text('FROM otel/collector@sha256:' + 'b' * 64 + ' AS collector\n')
            with self.assertRaisesRegex(lint.LintError, 'authoritative image lock'):
                lint.check_collector_pin(root)

    def test_requirement_version_hash_must_match_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'requirements.txt'
            lock = {'pythonPackages': {'example': {'version': '1.0', 'sha256': 'a' * 64}}}
            path.write_text('example==1.0 --hash=sha256:' + 'a' * 64 + '\n')
            lint.check_requirements(root, lock)
            path.write_text('example>=1.0\n')
            with self.assertRaises(lint.LintError):
                lint.check_requirements(root, lock)

    def test_public_key_exception_is_exact_and_hash_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            public = root / lint.TLS_DIRECTORY
            public.mkdir(parents=True)
            pins = {}
            for name in lint.TLS_FILES:
                payload = ('synthetic ' + name).encode()
                (public / name).write_bytes(payload)
                pins[name] = lint.hashlib.sha256(payload).hexdigest()
            (public / 'provenance.json').write_text(json.dumps({'files': pins}))
            with self.assertRaisesRegex(lint.LintError, 'provenance changed'):
                lint.check_fixtures(root, list(public.iterdir()))
            digest = lint.hashlib.sha256((public / 'provenance.json').read_bytes()).hexdigest()
            with patch.object(lint, 'TLS_PROVENANCE_SHA256', digest):
                lint.check_fixtures(root, list(public.iterdir()))
                (public / 'agent1-key.pem.fixture').write_text('changed')
                with self.assertRaisesRegex(lint.LintError, 'checksum mismatch'):
                    lint.check_fixtures(root, list(public.iterdir()))
                (public / 'agent1-key.pem.fixture').write_text('synthetic agent1-key.pem.fixture')
                (public / 'another-key.pem.fixture').write_text('not approved')
                with self.assertRaisesRegex(lint.LintError, 'not a blanket'):
                    lint.check_fixtures(root, list(public.iterdir()))

    def test_local_links_and_heading_anchors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            page = root / 'README.md'
            (root / 'other.md').write_text('# Example heading\n# Example heading\n')
            page.write_text('[good](other.md#example-heading-1)\n[remote](https://example.invalid)\n')
            lint.check_markdown(root, page)
            for target in ('missing.md', 'other.md#missing', '../outside.md'):
                page.write_text(f'[bad]({target})\n')
                with self.subTest(target=target), self.assertRaises(lint.LintError):
                    lint.check_markdown(root, page)

    def test_systemd_structure_not_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.service'
            path.write_text('[Unit]\nDescription=Synthetic\n[Service]\nExecStart=/not/executed\n[Install]\nWantedBy=multi-user.target\n')
            lint.check_systemd(path)
            path.write_text('[Unit]\nDescription=One\nDescription=Two\n')
            with self.assertRaises(lint.configparser.Error):
                lint.check_systemd(path)


if __name__ == '__main__':
    unittest.main()
