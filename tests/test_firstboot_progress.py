"""Firstboot attempts are bounded by lack of progress, not by wall-clock time.

Also: every attempt starts from a consistent package database, and the unit's
timeouts stay consistent with the runner's ceiling and stop sequence.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import time
import unittest

from test_firstboot_stop import RUNNER, make_fixture, runner_env

ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / 'provision/plebian-os-firstboot.service'


def run(root, command_text, timeout=30, **extra):
    command = root / 'provision'
    command.write_text(command_text)
    command.chmod(0o755)
    started = time.monotonic()
    result = subprocess.run(['sh', str(RUNNER), 'run', str(command), str(root)],
                            env=runner_env(root, **extra), capture_output=True,
                            text=True, timeout=timeout)
    return result, time.monotonic() - started


class ProgressTests(unittest.TestCase):
    def test_slow_but_talking_attempt_outlives_the_stall_limit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_fixture(root)
            result, elapsed = run(root, '''#!/bin/sh
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do echo "Get:$i slow mirror"; sleep 0.4; done
''', PLEBIAN_OS_FIRSTBOOT_STALL_TIMEOUT='2')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertGreater(elapsed, 4)
            self.assertEqual((root / 'state/firstboot-attempts').read_text(), '1\n')

    def test_silent_io_counts_as_progress(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_fixture(root)
            # No output at all: a download or link step writing its file.
            result, elapsed = run(root, '''#!/usr/bin/python3
import sys, time
with open(sys.argv[1] + '/download.part', 'wb', buffering=0) as f:
    for _ in range(12):
        f.write(b'x' * 65536)
        time.sleep(0.4)
''', PLEBIAN_OS_FIRSTBOOT_STALL_TIMEOUT='2')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertGreater(elapsed, 4)
            self.assertEqual(result.stdout, '')

    def test_stalled_attempt_is_stopped_and_retried(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_fixture(root)
            result, elapsed = run(root, '''#!/bin/sh
n=$(cat "$1/counter" 2>/dev/null || echo 0)
echo $((n + 1)) >"$1/counter"
echo "fetching from a dead connection"
sleep 60
''', PLEBIAN_OS_FIRSTBOOT_STALL_TIMEOUT='2', PLEBIAN_OS_FIRSTBOOT_MAX_ATTEMPTS='2')
            self.assertEqual(result.returncode, 124, result.stderr)
            self.assertEqual((root / 'counter').read_text().strip(), '2')
            self.assertIn('stopped after no progress for 2s', result.stderr)
            self.assertIn('exhausted 2/2', result.stderr)
            self.assertLess(elapsed, 20)

    def test_overall_ceiling_bounds_a_progressing_job(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_fixture(root)
            result, elapsed = run(root, '''#!/bin/sh
while :; do echo still building; sleep 0.2; done
''', PLEBIAN_OS_FIRSTBOOT_STALL_TIMEOUT='2', PLEBIAN_OS_FIRSTBOOT_CEILING='3')
            self.assertEqual(result.returncode, 124, result.stderr)
            self.assertIn('reached the overall 3s ceiling', result.stderr)
            self.assertIn('the next boot retries', result.stderr)
            # The ceiling covers the whole job: no second attempt starts.
            self.assertEqual((root / 'state/firstboot-attempts').read_text(), '1\n')
            self.assertLess(elapsed, 15)

    def test_successful_command_returns_promptly(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_fixture(root)
            result, elapsed = run(root, '#!/bin/sh\nexit 0\n',
                                  PLEBIAN_OS_FIRSTBOOT_POLL_INTERVAL='15')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertLess(elapsed, 18)

    def test_invalid_limits_are_refused(self):
        for name, value in [('PLEBIAN_OS_FIRSTBOOT_STALL_TIMEOUT', '0'),
                            ('PLEBIAN_OS_FIRSTBOOT_CEILING', 'x'),
                            ('PLEBIAN_OS_FIRSTBOOT_POLL_INTERVAL', '0'),
                            ('PLEBIAN_OS_FIRSTBOOT_POLL_INTERVAL', '1.2.3')]:
            with self.subTest(name=name, value=value), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                make_fixture(root)
                result, _ = run(root, '#!/bin/sh\nexit 0\n', **{name: value})
                self.assertEqual(result.returncode, 2, result.stderr)


# dpkg and apt-get stand-ins for recovery: dpkg reports a pending journal as a
# fault the way a real interrupted database does, and --configure -a replays it.
RECOVERY_DPKG = '''#!/bin/sh
admin=/nonexistent
case "${1:-}" in --admindir=*) admin="${1#--admindir=}"; shift ;; esac
echo "dpkg $*" >>"$MARKS/calls"
case " $* " in
  *" --audit "*) cat "$MARKS/audit" 2>/dev/null; exit 0 ;;
  *" --configure -a "*)
    [ -e "$MARKS/configure-fails" ] && exit 2
    rm -f "$admin"/updates/0000 "$admin"/updates/tmp.i; exit 0 ;;
esac
'''
RECOVERY_APT = '''#!/bin/sh
echo "apt-get $*" >>"$MARKS/calls"
rm -f "$MARKS/audit"
'''
PROVISIONER = '''#!/bin/sh
echo provision >>"$1/calls"
ls "$1/dpkg/updates" >"$1/updates-seen-by-provisioner"
'''


class RecoveryTests(unittest.TestCase):
    def fixture(self, root):
        make_fixture(root)
        for name, text in [('dpkg', RECOVERY_DPKG), ('apt-get', RECOVERY_APT)]:
            (root / 'bin' / name).write_text(text)
            (root / 'bin' / name).chmod(0o755)
        # The journal an interrupted `dpkg --remove kilix-mpv` left in RC9.
        (root / 'dpkg/updates/0000').write_text('Package: kilix-mpv\nStatus: deinstall ok installed\n')
        (root / 'dpkg/updates/tmp.i').write_text('#padding\n')

    def test_interrupted_dpkg_is_recovered_before_provisioning(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.fixture(root)
            (root / 'audit').write_text('The following packages are only half configured\n')
            result, _ = run(root, PROVISIONER)
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = (root / 'calls').read_text().splitlines()
            configure = next(i for i, c in enumerate(calls) if '--configure -a' in c)
            fix = next(i for i, c in enumerate(calls) if c.startswith('apt-get'))
            self.assertLess(configure, fix)
            self.assertLess(fix, calls.index('provision'))
            self.assertIn('--force-confold', calls[configure])
            self.assertIn('-f install', calls[fix])
            self.assertIn('DPkg::Lock::Timeout=300', calls[fix])
            self.assertEqual((root / 'updates-seen-by-provisioner').read_text(), '')
            self.assertIn('package database was left interrupted', result.stderr)
            self.assertIn('dpkg journal pending', result.stderr)
            self.assertIn('package database is consistent again', result.stderr)

    def test_consistent_database_is_left_alone(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.fixture(root)
            for f in (root / 'dpkg/updates').iterdir():
                f.unlink()
            result, _ = run(root, PROVISIONER)
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = (root / 'calls').read_text().splitlines()
            self.assertFalse([c for c in calls if '--configure' in c or c.startswith('apt-get')])

    def test_failed_recovery_fails_clearly_without_provisioning(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.fixture(root)
            (root / 'configure-fails').touch()
            result, _ = run(root, PROVISIONER, PLEBIAN_OS_FIRSTBOOT_MAX_ATTEMPTS='2')
            self.assertEqual(result.returncode, 75, result.stderr)
            self.assertNotIn('provision', (root / 'calls').read_text().splitlines())
            self.assertIn('still inconsistent after recovery; not provisioning', result.stderr)
            self.assertIn('exhausted 2/2 attempts (last exit 75)', result.stderr)


def seconds(value):
    total = 0
    for number, unit in re.findall(r'(\d+)(h|min|s)?', value):
        total += int(number) * {'h': 3600, 'min': 60, 's': 1, '': 1}[unit]
    return total


class UnitConsistencyTests(unittest.TestCase):
    def test_unit_timeouts_cover_the_ceiling_and_the_stop_sequence(self):
        runner = RUNNER.read_text()
        unit = UNIT.read_text()

        def default(name):
            return int(re.search(r'PLEBIAN_OS_FIRSTBOOT_%s:-(\d+)' % name, runner).group(1))
        ceiling, stall = default('CEILING'), default('STALL_TIMEOUT')
        dpkg_grace, stop_grace = default('DPKG_GRACE'), default('STOP_GRACE')
        stop_sequence = dpkg_grace + stop_grace + dpkg_grace
        start = seconds(re.search(r'^TimeoutStartSec=(\S+)$', unit, re.M).group(1))
        stop = seconds(re.search(r'^TimeoutStopSec=(\S+)$', unit, re.M).group(1))
        self.assertGreater(start, ceiling + stop_sequence)
        self.assertGreater(stop, stop_sequence)
        # Twice the longest silent stretch seen on RC9's slow link (598 s).
        self.assertGreaterEqual(stall, 2 * 598)
        self.assertLess(stall, ceiling)
        self.assertIn('KillMode=mixed', unit)
        self.assertNotIn('timeout --signal', runner)
        self.assertNotIn('ATTEMPT_TIMEOUT', runner)


if __name__ == '__main__':
    unittest.main()
