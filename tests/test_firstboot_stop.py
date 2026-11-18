"""A firstboot stop must never cut a running dpkg, and must let rollback finish.

RC9 lost a first boot this way: the attempt timeout signalled the whole process
group, the provisioner's log tee died with it, and the rollback's dpkg then died
of SIGPIPE writing to the dead pipe, leaving dpkg interrupted for every retry.
These fixtures drive the real runner with stand-ins for the provisioner and for
dpkg (a script named dpkg, which is what the runner looks for).
"""
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / 'provision/plebian-os-firstboot-attempt'
PROVISION = ROOT / 'provision/plebian-os-provision.sh'

# A dpkg stand-in: records that it started and finished, and whether any
# signal reached it. Default dispositions, like dpkg's, so a signal kills it.
FAKE_DPKG = '''#!/bin/sh
case "${1:-}" in --admindir=*) shift ;; esac
case "${1:-}" in --audit) exit 0 ;; esac
for s in TERM INT HUP; do trap "echo $s >>'$MARKS/dpkg-signalled'; exit 1" $s; done
echo "$$" >"$MARKS/dpkg-pid"
touch "$MARKS/dpkg-started"
sleep "${FAKE_DPKG_SECONDS:-1.5}"
touch "$MARKS/dpkg-finished"
'''


def runner_env(root, **extra):
    env = {k: v for k, v in os.environ.items() if k != 'INVOCATION_ID'}
    env.update({
        'PLEBIAN_OS_STATE_DIR': str(root / 'state'),
        'PLEBIAN_OS_FIRSTBOOT_MAX_ATTEMPTS': '3',
        'PLEBIAN_OS_FIRSTBOOT_STALL_TIMEOUT': '30',
        'PLEBIAN_OS_FIRSTBOOT_CEILING': '60',
        'PLEBIAN_OS_FIRSTBOOT_DPKG_GRACE': '20',
        'PLEBIAN_OS_FIRSTBOOT_STOP_GRACE': '20',
        'PLEBIAN_OS_FIRSTBOOT_POLL_INTERVAL': '0.2',
        'PLEBIAN_OS_FIRSTBOOT_RETRY_DELAY': '0',
        'PLEBIAN_OS_TEMP_SUDOERS': str(root / 'sudoers'),
        'PLEBIAN_OS_PROVISION_LOG': str(root / 'provision.log'),
        'PLEBIAN_OS_DPKG_ADMINDIR': str(root / 'dpkg'),
        # Hermetic: only this fixture's dpkg counts as a package process.
        'PLEBIAN_OS_FIRSTBOOT_PACKAGE_COMMS': 'dpkg',
        'MARKS': str(root),
        'PATH': f"{root / 'bin'}:{os.environ['PATH']}",
    })
    env.update(extra)
    return env


def make_fixture(root):
    (root / 'dpkg/updates').mkdir(parents=True)
    (root / 'bin').mkdir()
    dpkg = root / 'bin/dpkg'
    dpkg.write_text(FAKE_DPKG)
    dpkg.chmod(0o755)


def wait_for(path, proc, seconds=8):
    end = time.monotonic() + seconds
    while not path.exists():
        if proc.poll() is not None:
            raise AssertionError(f'runner exited ({proc.returncode}) before {path.name}')
        if time.monotonic() > end:
            raise AssertionError(f'timed out waiting for {path.name}')
        time.sleep(0.02)


def kill_leftovers(root):
    for name in ('child', 'dpkg-pid'):
        f = root / name
        if f.exists():
            try:
                os.killpg(os.getpgid(int(f.read_text())), signal.SIGKILL)
            except (ProcessLookupError, ValueError, PermissionError):
                pass


class FirstbootStopTests(unittest.TestCase):
    def start(self, root, command_text, **extra):
        command = root / 'provision'
        command.write_text(command_text)
        command.chmod(0o755)
        out = (root / 'output').open('w')
        self.addCleanup(out.close)
        p = subprocess.Popen(['sh', str(RUNNER), 'run', str(command), str(root)],
                             env=runner_env(root, **extra), stdout=out, stderr=out,
                             start_new_session=True)

        def cleanup():
            if p.poll() is None:
                p.kill()
            p.wait(timeout=5)
            kill_leftovers(root)
        self.addCleanup(cleanup)
        return p

    def test_stop_waits_for_rollback_without_starting_another_attempt(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_fixture(root)
            p = self.start(root, '''#!/bin/bash
set -eu
finish() {
    trap - EXIT
    trap ':' TERM HUP INT
    touch "$1/restoring"
    sleep 0.7
    touch "$1/restored"
}
trap 'finish "$1"' EXIT
trap 'exit 143' TERM
printf '%s\\n' "$$" > "$1/child"
touch "$1/running" "$1/sudoers"
while :; do sleep 0.02; done
''')
            wait_for(root / 'running', p)
            p.send_signal(signal.SIGTERM)
            wait_for(root / 'restoring', p)
            self.assertIsNone(p.poll(), 'service main exited before child rollback')
            p.send_signal(signal.SIGTERM)
            self.assertEqual(p.wait(timeout=8), 143)
            self.assertTrue((root / 'restored').exists())
            self.assertFalse((root / 'sudoers').exists())
            self.assertEqual((root / 'state/firstboot-attempts').read_text(), '1\n')
            self.assertFalse(Path('/proc', (root / 'child').read_text().strip()).exists())

    def test_stop_lets_an_in_flight_dpkg_finish_before_signalling(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_fixture(root)
            p = self.start(root, '''#!/bin/bash
trap 'touch "$1/provisioner-signalled"; exit 143' TERM
printf '%s\\n' "$$" > "$1/child"
dpkg --unpack something.deb
while :; do sleep 0.02; done
''')
            wait_for(root / 'dpkg-started', p)
            p.send_signal(signal.SIGTERM)
            self.assertEqual(p.wait(timeout=10), 143)
            self.assertTrue((root / 'dpkg-finished').exists(), 'dpkg was cut mid-operation')
            self.assertFalse((root / 'dpkg-signalled').exists())
            output = (root / 'output').read_text()
            self.assertIn('waiting for dpkg', output)
            # The provisioner was signalled only after dpkg had finished.
            self.assertGreaterEqual(
                (root / 'provisioner-signalled').stat().st_mtime_ns,
                (root / 'dpkg-finished').stat().st_mtime_ns)

    def test_rollback_dpkg_survives_the_stop_grace_and_its_kill(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_fixture(root)
            # The rollback starts a package step and then hangs: the runner's
            # stop grace expires while dpkg runs, but KILL waits for dpkg.
            p = self.start(root, '''#!/bin/bash
rollback() {
    trap ':' TERM INT HUP
    dpkg --remove kilix-mpv
    touch "$1/rollback-dpkg-returned"
    while :; do sleep 0.02; done
}
trap 'rollback "$1"' TERM
printf '%s\\n' "$$" > "$1/child"
touch "$1/running"
while :; do sleep 0.02; done
''', PLEBIAN_OS_FIRSTBOOT_STOP_GRACE='1', FAKE_DPKG_SECONDS='2.5')
            wait_for(root / 'running', p)
            p.send_signal(signal.SIGTERM)
            self.assertEqual(p.wait(timeout=15), 143)
            self.assertTrue((root / 'dpkg-finished').exists(), 'rollback dpkg was killed')
            self.assertFalse((root / 'dpkg-signalled').exists())
            output = (root / 'output').read_text()
            self.assertIn('did not finish its rollback within 1s', output)
            self.assertIn('waiting for dpkg', output)
            self.assertFalse(Path('/proc', (root / 'child').read_text().strip()).exists())

    def test_dpkg_grace_is_bounded(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_fixture(root)
            p = self.start(root, '''#!/bin/bash
trap 'exit 143' TERM
printf '%s\\n' "$$" > "$1/child"
dpkg --configure -a
''', PLEBIAN_OS_FIRSTBOOT_DPKG_GRACE='1', FAKE_DPKG_SECONDS='30')
            wait_for(root / 'dpkg-started', p)
            started = time.monotonic()
            p.send_signal(signal.SIGTERM)
            self.assertEqual(p.wait(timeout=10), 143)
            self.assertLess(time.monotonic() - started, 8)
            self.assertIn('still running after 1s; stopping anyway',
                          (root / 'output').read_text())


class ProvisionLogTeeTests(unittest.TestCase):
    def test_log_tee_survives_a_group_stop_so_rollback_output_has_a_reader(self):
        source = PROVISION.read_text()
        match = re.search(r'^    (exec > >\(.*tee -a -- "\$PROVISION_LOG"\) 2>&1)$',
                          source, re.M)
        self.assertIsNotNone(match)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            log = root / 'provision.log'
            script = f'''PROVISION_LOG={log}
{match.group(1)}
trap 'echo rollback-start; sleep 0.3; echo rollback-done; exit 143' TERM
echo running
touch {root}/running
while :; do sleep 0.02; done
'''
            p = subprocess.Popen(['bash', '-c', script], stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
            try:
                end = time.monotonic() + 5
                while not (root / 'running').exists():
                    self.assertLess(time.monotonic(), end)
                    time.sleep(0.02)
                os.killpg(p.pid, signal.SIGTERM)
                self.assertEqual(p.wait(timeout=5), 143)
                end = time.monotonic() + 3
                while 'rollback-done' not in log.read_text():
                    self.assertLess(time.monotonic(), end, log.read_text())
                    time.sleep(0.02)
            finally:
                if p.poll() is None:
                    os.killpg(p.pid, signal.SIGKILL)
                    p.wait()


if __name__ == '__main__':
    unittest.main()
