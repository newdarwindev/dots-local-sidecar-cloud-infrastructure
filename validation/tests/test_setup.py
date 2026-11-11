"""Synthetic setup boundary regressions; execute only through the Docker runner."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('offline_setup', ROOT / 'validation/setup.py')
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)
APP = ROOT / 'application-infrastructure'


class ReviewTests(unittest.TestCase):
    def config(self):
        value = json.loads((APP / 'contracts/future-cluster.example.json').read_text())
        value['target'].update(kubernetesVersion='1.32.0', storageClass='review-storage')
        return value

    def review(self, action, value):
        return setup.review(action, io.BytesIO(json.dumps(value).encode()))

    def test_cluster_assessment_and_packet_are_inert(self):
        value = self.config()
        value['target'].update(contextRef='private-reference', namespaceUid='private-namespace')
        result = self.review('cluster-packet', value)
        self.assertFalse(result['deploymentAllowed'])
        documents = result['documents']
        target = documents['render-target.json']
        self.assertTrue(target['synthetic'])
        self.assertEqual(target['context'], 'synthetic-not-a-cluster')
        self.assertFalse(target['capacityVerified'])
        self.assertNotIn('private-reference', json.dumps(result))
        self.assertNotIn('private-namespace', json.dumps(result))
        self.assertEqual(documents['assessment.json'], self.review('cluster-assess', value))
        self.assertNotIn('tokscale-render-input.json', documents)

    def test_packet_hashes_match_existing_disk_interface(self):
        contract = setup.helper('cluster_contract')
        value = self.config()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'packet'
            contract.packet(value, output)
            documents = self.review('cluster-packet', value)['documents']
            for name, document in documents.items():
                expected = (json.dumps(document, indent=2) + '\n').encode()
                self.assertEqual((output / name).read_bytes(), expected)
                self.assertEqual((output / name).stat().st_mode & 0o777, 0o600)
                if name != 'packet-lock.json':
                    self.assertEqual(documents['packet-lock.json']['files'][name], hashlib.sha256(expected).hexdigest())
            with self.assertRaises(ValueError):
                contract.packet(value, output)

    def test_plugin_actions_never_enable_or_read_ambient_credentials(self):
        with patch.dict(os.environ, {'TRACE_TO_LANGFUSE': 'true', 'LANGFUSE_SECRET_KEY': 'synthetic-canary'}):
            for action, fixture in [('plugin-render', 'plugin-render.synthetic.json'),
                                    ('plugin-check', 'plugin-check.synthetic.json')]:
                result = self.review(action, json.loads((APP / 'fixtures' / fixture).read_text()))
                self.assertFalse(result.get('effective', result)['enabled'])
                self.assertNotIn('synthetic-canary', json.dumps(result))
                if action == 'plugin-check':
                    self.assertFalse(result['activation_allowed'])
                    self.assertFalse(result['live_configuration_verified'])

    def test_empty_oversize_duplicate_nonfinite_float_encoding_and_deep_inputs(self):
        payloads = [b'', b' ' * (setup.MAX_BYTES + 1), b'{"x":1,"x":2}',
                    b'{"x":NaN}', b'{"x":1e999}', b'{"x":1.0}', b'\xff',
                    b'[' * 2000 + b']' * 2000]
        for content in payloads:
            stdout, stderr = io.StringIO(), io.StringIO()
            self.assertEqual(setup.main('cluster-assess', io.BytesIO(content), stdout, stderr), 2)
            self.assertEqual(stdout.getvalue(), '')
            self.assertEqual(stderr.getvalue(), setup.ERROR)

    def test_reader_never_requests_more_than_limit_plus_one(self):
        stream = unittest.mock.Mock()
        stream.read.return_value = b' ' * (setup.MAX_BYTES + 1)
        with self.assertRaises(ValueError):
            setup.review('cluster-assess', stream)
        stream.read.assert_called_once_with(setup.MAX_BYTES + 1)

    def test_exact_byte_limit_is_accepted_and_stdout_remains_one_document(self):
        payload = json.dumps(self.config()).encode()
        content = payload + b' ' * (setup.MAX_BYTES - len(payload))
        stdout, stderr = io.StringIO(), io.StringIO()
        self.assertEqual(setup.main('cluster-assess', io.BytesIO(content), stdout, stderr), 0)
        self.assertFalse(json.loads(stdout.getvalue())['deploymentAllowed'])
        self.assertEqual(stderr.getvalue(), '')

    def test_arbitrary_commands_extra_keys_credentials_and_activation_rejected(self):
        for action in ('preflight', 'deploy', 'fetch', 'sh', 'plugin-render; echo canary'):
            with self.assertRaises(ValueError):
                self.review(action, {})
        for field in ('auth', 'history', 'secretValue', 'command'):
            value = self.config()
            value[field] = 'private-canary'
            stdout, stderr = io.StringIO(), io.StringIO()
            self.assertEqual(setup.main('cluster-packet', io.BytesIO(json.dumps(value).encode()), stdout, stderr), 2)
            self.assertEqual(stdout.getvalue(), '')
            self.assertNotIn('private-canary', stderr.getvalue())
        for field, item in [('enabled', True), ('secret_key', 'private-canary')]:
            value = json.loads((APP / 'fixtures/plugin-check.synthetic.json').read_text())
            value['layers']['project'][field] = item
            with self.assertRaises(ValueError):
                self.review('plugin-check', value)

    def test_container_entrypoint_redacts_unrecognized_arguments(self):
        result = subprocess.run([sys.executable, str(ROOT / 'validation/check.py'), 'setup',
                                 '--action', 'private-argument-canary'], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, '')
        self.assertEqual(result.stderr, 'BLOCKED: unsupported validation arguments.\n')


class RunnerTests(unittest.TestCase):
    def setUp(self):
        exec_tmpdir = os.environ.get('VALIDATION_EXEC_TMPDIR')
        if not exec_tmpdir:
            raise RuntimeError('Runner mock tests require the dedicated executable tmpfs')
        self.directory = tempfile.TemporaryDirectory(dir=exec_tmpdir)
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.assertEqual(self.root.parent, Path(exec_tmpdir))
        binary = self.root / 'bin'
        binary.mkdir()
        self.log = self.root / 'calls.jsonl'
        self.input = self.root / 'input.json'
        self.input.write_text('{"synthetic":"only"}\n')
        self.env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ['PATH'],
                        DOCKER_HOST='unix:///synthetic-docker.sock', DOCKER_CONTEXT='',
                        FAKE_LOG=str(self.log), FAKE_INPUT=str(self.root / 'received'),
                        FAKE_SOURCE=str(self.input),
                        FAKE_ENDPOINT='unix:///synthetic-docker.sock')
        # A local mock, never a Docker daemon. Tests themselves run inside Docker.
        mock = binary / 'docker'
        mock.write_text('#!' + sys.executable + '\n' + '''import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ['FAKE_LOG'], 'a') as stream:
    stream.write(json.dumps(args) + '\\n')
if os.environ.get('FAKE_FAILURE') in args:
    print('private-error-canary', file=sys.stderr)
    raise SystemExit(2)
if args == ['context', 'show']:
    print('synthetic')
elif args[:2] == ['context', 'inspect']:
    print(os.environ['FAKE_ENDPOINT'])
elif '--config' in args:
    directory = Path(args[args.index('--config') + 1])
    assert list(directory.iterdir()) == []
    assert 'DOCKER_HOST' not in os.environ and 'DOCKER_CONTEXT' not in os.environ
    if 'build' in args:
        mutation = os.environ.get('FAKE_MUTATE')
        if mutation:
            source = Path(os.environ['FAKE_SOURCE'])
            if mutation != 'inplace':
                source.unlink()
            if mutation == 'fifo':
                os.mkfifo(source)
            elif mutation == 'symlink':
                other = source.parent / 'auth.json'
                other.write_text('{"secret":"synthetic-replacement-canary"}')
                source.symlink_to(other)
            else:
                source.write_text('{"secret":"synthetic-replacement-canary"}')
        print('sha256:' + 'a' * 64)
    elif 'run' in args:
        Path(os.environ['FAKE_INPUT']).write_bytes(sys.stdin.buffer.read())
        print('{"synthetic":true}')
else:
    raise SystemExit(2)
''')
        mock.chmod(0o700)

    def run_setup(self, *args):
        return subprocess.run(['sh', str(ROOT / 'validation/run.sh'), 'setup', *map(str, args)],
                              env=self.env, capture_output=True, text=True, check=False, timeout=10)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def assert_blocked(self, *args):
        result = self.run_setup(*args)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, '')
        self.assertNotIn(str(self.input), result.stderr)
        self.assertNotIn('build', [part for call in self.calls() for part in call])

    def test_all_actions_have_only_bounded_offline_runtime_and_stdout(self):
        for action in setup.ACTIONS:
            result = self.run_setup(action, self.input)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {'synthetic': True})
        self.assertEqual((self.root / 'received').read_bytes(), self.input.read_bytes())
        for call in self.calls():
            self.assertNotIn(str(self.input), call)
            if 'run' not in call:
                continue
            for flag in ('--network=none', '--read-only', '--cap-drop=ALL', '--log-driver=none',
                         '--pull=never', '--security-opt=no-new-privileges', '--memory=256m', '--pids-limit=32'):
                self.assertIn(flag, call)
            self.assertEqual(call[call.index('--user') + 1], '65532:65532')
            self.assertEqual(call[-4:-1], ['sha256:' + 'a' * 64, 'setup', '--action'])
            for flag in ('--env', '-e', '--env-file', '--mount', '--volume', '-v', '--privileged'):
                self.assertNotIn(flag, call)
            self.assertFalse(Path(call[call.index('--config') + 1]).parent.exists())

    def test_rejects_unknown_action_extra_args_and_relative_input(self):
        for args in [('sh', self.input), ('plugin-render;echo private-canary', self.input),
                     ('plugin-render', self.input, 'extra'), ('plugin-render', 'input.json')]:
            self.assert_blocked(*args)

    def test_rejects_special_symlink_empty_oversize_repo_and_account_paths(self):
        link = self.root / 'link.json'
        link.symlink_to(self.input)
        fifo = self.root / 'pipe.json'
        os.mkfifo(fifo)
        account = self.root / '.codex'
        account.mkdir()
        auth = account / 'auth.json'
        auth.write_text('{}')
        for path in (link, fifo, self.root, auth, APP / 'fixtures/plugin-render.synthetic.json'):
            self.assert_blocked('plugin-render', path)
        for content in ('', ' ' * (setup.MAX_BYTES + 1)):
            self.input.write_text(content)
            self.assert_blocked('plugin-render', self.input)

    def test_rejects_remote_daemon_and_respects_context_precedence(self):
        self.env['DOCKER_HOST'] = 'tcp://private-canary.invalid:2375'
        self.assert_blocked('plugin-render', self.input)
        self.env.update(DOCKER_HOST='unix:///synthetic-docker.sock', DOCKER_CONTEXT='remote',
                        FAKE_ENDPOINT='ssh://private-canary.invalid')
        self.assert_blocked('plugin-render', self.input)

    def test_build_time_replacement_never_changes_snapshotted_input(self):
        original = self.input.read_bytes()
        for mutation in ('symlink', 'fifo', 'regular', 'inplace'):
            self.env['FAKE_MUTATE'] = mutation
            result = self.run_setup('plugin-render', self.input)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((self.root / 'received').read_bytes(), original)
            self.input.unlink()
            self.input.write_bytes(original)

    def test_darwin_compares_real_descriptor_identity_not_fdescfs_device(self):
        # Exercise the BSD stat command contract inside Docker. Actual macOS
        # acceptance is separately established by the inert setup operation.
        binary = self.root / 'bin'
        uname = binary / 'uname'
        uname.write_text('#!/bin/sh\nprintf "Darwin\\n"\n')
        uname.chmod(0o700)
        stat = binary / 'stat'
        stat.write_text('#!' + sys.executable + '\n' + '''import os, sys
assert sys.argv[1:3] == ['-f', '%d:%i']
assert not any('/dev/fd/' in arg for arg in sys.argv)
value = os.stat(sys.argv[3]) if len(sys.argv) == 4 else os.fstat(0)
inode = value.st_ino
if len(sys.argv) == 3 and os.environ.get('FAKE_FSTAT_MISMATCH'):
    inode += 1
print(f'{value.st_dev}:{inode}')
''')
        stat.chmod(0o700)
        result = self.run_setup('plugin-render', self.input)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'received').read_bytes(), self.input.read_bytes())
        self.log.unlink()
        self.env['FAKE_FSTAT_MISMATCH'] = '1'
        self.assert_blocked('plugin-render', self.input)
        self.assertEqual(self.calls(), [])

    def test_runtime_errors_are_stage_specific_and_do_not_disclose_values(self):
        for stage, message in [('build', 'image build failed'), ('run', 'rejected JSON')]:
            self.env['FAKE_FAILURE'] = stage
            result = self.run_setup('plugin-render', self.input)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, '')
            self.assertIn(message, result.stderr)
            self.assertNotIn('private-error-canary', result.stderr)


if __name__ == '__main__':
    unittest.main()
