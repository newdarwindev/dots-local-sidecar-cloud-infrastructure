"""Runner command contracts; execute only through the committed Docker runner."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
IMAGE = 'infrastructure-validation:local'


class RunnerTests(unittest.TestCase):
    def setUp(self):
        directory = os.environ.get('VALIDATION_EXEC_TMPDIR')
        if not directory:
            raise RuntimeError('Runner mock tests require the dedicated executable tmpfs')
        self.directory = tempfile.TemporaryDirectory(dir=directory)
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.log = root / 'calls.jsonl'
        self.env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ['PATH'],
                        RUNNER_TEST_LOG=str(self.log))
        mock = root / 'docker'
        mock.write_text('#!' + sys.executable + '\n' + '''import json, os, sys
args = sys.argv[1:]
with open(os.environ['RUNNER_TEST_LOG'], 'a') as stream:
    stream.write(json.dumps(args) + '\\n')
if os.environ.get('RUNNER_TEST_FAIL') in args:
    raise SystemExit(7)
''')
        mock.chmod(0o700)

    def run_scope(self, *args):
        self.log.unlink(missing_ok=True)
        result = subprocess.run(['sh', str(ROOT / 'validation/run.sh'), *args],
                                env=self.env, capture_output=True, text=True, timeout=10)
        calls = [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
        return result, calls

    def test_scope_commands_and_isolation(self):
        common = ['run', '--rm', '--read-only', '--user', '65532:65532',
                  '--cpus=2', '--memory=2g', '--pids-limit=256', '--cap-drop=ALL',
                  '--security-opt=no-new-privileges']
        lint = common + ['--network=none', '--tmpfs', '/tmp:rw,nosuid,nodev,noexec,size=512m',
                         '--tmpfs', '/runner-exec:rw,nosuid,nodev,exec,size=64m',
                         '-e', 'VALIDATION_EXEC_TMPDIR=/runner-exec', IMAGE, 'lint']
        collector = common + ['--network=none', '--tmpfs', '/tmp:rw,nosuid,nodev,noexec,size=128m',
                              IMAGE, 'collector-runtime']
        for args, scope in [((), 'all'), (('all',), 'all'), (('primary',), 'primary'),
                            (('application',), 'application'), (('lint',), 'lint')]:
            with self.subTest(scope=args):
                result, calls = self.run_scope(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
                expected = [['info'], ['build', '--platform', 'linux/amd64', '-f',
                                      'validation/Dockerfile', '-t', IMAGE, '.'], lint]
                if scope in ('all', 'application'):
                    expected.append(collector)
                if scope != 'lint':
                    expected.append(common + ['--tmpfs', '/tmp:rw,nosuid,nodev,size=1g',
                                              IMAGE, 'contracts', '--bundle', scope])
                self.assertEqual(calls, expected)

    def test_failures_stop_later_stages(self):
        for failure in ('info', 'build', 'lint', 'collector-runtime', 'contracts'):
            with self.subTest(failure=failure):
                self.env['RUNNER_TEST_FAIL'] = failure
                result, calls = self.run_scope()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(failure, calls[-1])

    def test_invalid_arguments_never_contact_docker(self):
        for args in [('deploy',), ('all', 'extra')]:
            result, calls = self.run_scope(*args)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
