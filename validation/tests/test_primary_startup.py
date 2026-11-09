"""Offline synthetic startup regressions, only through the Docker entrypoint."""
import os
from pathlib import Path
import plistlib
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
STARTUP = ROOT / 'primary-infrastructure/startup'


class PrimaryStartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ['VALIDATION_EXEC_TMPDIR'])
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / 'home with spaces'
        self.base = self.home / 'Library/Application Support/dots-primary-infrastructure'
        self.lock = self.base / 'startup/start.lock'
        self.lock.parent.mkdir(parents=True)
        self.guest = self.home / '.local/share/dots-primary-lima/primary/lima.yaml'
        self.guest.parent.mkdir(parents=True)
        self.guest.write_text('synthetic existing guest\n')
        self.runtime = self.base / 'runtime/bin/limactl'
        self.runtime.parent.mkdir(parents=True)
        self.runtime.write_text('''#!/bin/sh
set -eu
printf '%s|%s\\n' "$LIMA_HOME" "$*" >> "$HOME/calls"
case "$*" in
  "list primary --format {{.Status}}")
    [ "$MODE" != list-failure ] || exit 7
    if [ "$MODE" = blocked ]; then
      touch "$HOME/entered"
      while [ ! -f "$HOME/release" ]; do sleep 0.05; done
    fi
    printf '%s\\n' "$STATUS" ;;
  "start primary") [ "$MODE" != start-failure ] || exit 8 ;;
  *) exit 99 ;;
esac
''')
        self.runtime.chmod(0o700)
        self.env = {'HOME': str(self.home), 'PATH': '/usr/bin:/bin',
                    'MODE': 'normal', 'STATUS': 'Running', 'LIMA_HOME': '/not-the-guest'}

    def run_start(self, **env):
        return subprocess.run(['/bin/sh', str(STARTUP / 'start-primary.sh')],
                              env=self.env | env, capture_output=True, text=True, timeout=10)

    def calls(self):
        path = self.home / 'calls'
        return path.read_text().splitlines() if path.exists() else []

    def test_running_repeated_noops_pin_home_and_exact_guest(self):
        for _ in range(3):
            result = self.run_start()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(self.lock.exists())
        self.assertEqual(self.calls(), [str(self.guest.parents[1]) + '|list primary --format {{.Status}}'] * 3)
        self.assertEqual(self.guest.read_text(), 'synthetic existing guest\n')

    def test_stopped_starts_exact_existing_primary_once(self):
        result = self.run_start(STATUS='Stopped')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([line.split('|')[1] for line in self.calls()],
                         ['list primary --format {{.Status}}', 'start primary'])
        self.assertFalse(self.lock.exists())

    def test_absent_guest_runtime_and_nonexecutable_fail_without_lima(self):
        self.guest.unlink()
        self.assertNotEqual(self.run_start().returncode, 0)
        self.guest.write_text('synthetic')
        self.runtime.chmod(0o600)
        self.assertNotEqual(self.run_start().returncode, 0)
        self.runtime.unlink()
        self.assertNotEqual(self.run_start().returncode, 0)
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.lock.exists())

    def test_unknown_broken_transitional_and_multiline_status_fail_closed(self):
        for status in ('', 'Broken', 'Starting', 'Stopping', 'Running\nStopped', 'primary Running'):
            with self.subTest(status=status):
                self.assertNotEqual(self.run_start(STATUS=status).returncode, 0)
                self.assertFalse(self.lock.exists())
        self.assertTrue(all('|list primary ' in line for line in self.calls()))

    def test_list_and_start_failures_propagate_without_retry_and_release_lock(self):
        self.assertEqual(self.run_start(MODE='list-failure').returncode, 7)
        self.assertFalse(self.lock.exists())
        self.assertEqual(self.run_start(MODE='start-failure', STATUS='Stopped').returncode, 8)
        self.assertFalse(self.lock.exists())
        self.assertEqual(len(self.calls()), 3)

    def test_existing_lock_preserved_without_lima(self):
        self.lock.mkdir()
        marker = self.lock / 'owner-marker'
        marker.write_text('preserve')
        self.assertNotEqual(self.run_start().returncode, 0)
        self.assertEqual(marker.read_text(), 'preserve')
        self.assertEqual(self.calls(), [])

    def test_concurrent_invocation_rejected_and_original_completes(self):
        first = subprocess.Popen(['/bin/sh', str(STARTUP / 'start-primary.sh')],
                                 env=self.env | {'MODE': 'blocked'}, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 5
            while not (self.home / 'entered').exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue((self.home / 'entered').exists())
            self.assertNotEqual(self.run_start().returncode, 0)
            self.assertEqual(len(self.calls()), 1)
        finally:
            (self.home / 'release').touch()
            first.communicate(timeout=5)
        self.assertEqual(first.returncode, 0)
        self.assertFalse(self.lock.exists())

    def test_template_is_login_only_no_timer_watchdog_or_network(self):
        value = plistlib.loads((STARTUP / 'local.dots.primary-start.plist.template').read_bytes())
        prefix = '__HOME__/Library/Application Support/dots-primary-infrastructure/startup/'
        self.assertEqual(value, {
            'Label': 'local.dots.primary-start', 'ProgramArguments': ['/bin/sh', prefix + 'start-primary.sh'],
            'RunAtLoad': True, 'ProcessType': 'Background',
            'EnvironmentVariables': {'HOME': '__HOME__', 'PATH': '/usr/bin:/bin:/usr/sbin:/sbin'},
            'StandardOutPath': prefix + 'launch.stdout.log',
            'StandardErrorPath': prefix + 'launch.stderr.log'})
