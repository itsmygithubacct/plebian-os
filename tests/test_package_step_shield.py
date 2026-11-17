"""A terminal Ctrl-C must not reach apt or dpkg during an update.

The updater starts every step that can run them in its own session with the
terminal's signals ignored. These tests press Ctrl-C on a real pseudo-terminal
while a stand-in for the package helper is running, and check that the stand-in
finishes while the updater's own trap still fires.
"""
import os
import pty
import re
import select
import shlex
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

import test_native_closure as closure

REPO = Path(__file__).resolve().parents[1]
UPDATE_NAME = "provision/plebian-os-update.sh"
UPDATE = REPO / UPDATE_NAME
SHIELD = ("/usr/bin/setsid --wait /bin/bash -c \\\n"
          "        'trap \"\" INT HUP QUIT; exec \"$@\"' plebian-os-package-step \\\n")


def press_ctrl_c(script: str, env: dict, started: Path, timeout=20.0):
    """Run script on a pty, press Ctrl-C once `started` exists; return (rc, output)."""
    pid, fd = pty.fork()
    if pid == 0:
        os.execve("/bin/bash", ["/bin/bash", "-c", script], env)
    deadline = time.monotonic() + timeout
    pressed = False
    output = b""
    while time.monotonic() < deadline:
        if not pressed and started.exists():
            os.write(fd, b"\x03")
            pressed = True
        ready, _, _ = select.select([fd], [], [], 0.05)
        if ready:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            output += chunk
    _, status = os.waitpid(pid, 0)
    os.close(fd)
    return os.waitstatus_to_exitcode(status), output.decode(errors="replace")


# Like dpkg under apt, the stand-in takes SIGINT's default action back, so an
# inherited "ignore" alone would not protect it: only leaving the terminal's
# foreground group does.
HELPER = """#!/usr/bin/python3 -I
import os, signal, time
signal.signal(signal.SIGINT, signal.SIG_DFL)
open(os.environ["STARTED"], "w").close()
time.sleep(1.5)
open(os.environ["FINISHED"], "w").write("finished\\n")
"""


class PackageStepShieldTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.helper = self.base / "helper"
        self.helper.write_text(HELPER)
        self.helper.chmod(0o700)
        self.started = self.base / "started"
        self.finished = self.base / "finished"
        self.env = {"PATH": os.environ["PATH"], "STARTED": str(self.started),
                    "FINISHED": str(self.finished), "HELPER": str(self.helper)}

    def tearDown(self):
        self._tmp.cleanup()

    def test_both_package_steps_carry_the_same_shield(self):
        source = UPDATE.read_text()
        self.assertEqual(source.count(SHIELD), 2)
        native = closure.shell_function(UPDATE_NAME, "native_runtime_command")
        deps = closure.shell_function(UPDATE_NAME, "refresh_os_dependencies")
        self.assertIn(SHIELD + "        /usr/local/sbin/plebian-os-native-runtime", native)
        self.assertIn(SHIELD + '        "$helper" --model-converters', deps)

    def test_unshielded_helper_dies_on_ctrl_c(self):
        """The control: without the shield this harness does kill the helper."""
        rc, _ = press_ctrl_c('trap "exit 130" INT\n"$HELPER"\nexit 0\n',
                             self.env, self.started)
        self.assertEqual(rc, 130)
        self.assertFalse(self.finished.exists())

    def _shielded_native(self) -> str:
        helper = closure.shell_function(UPDATE_NAME, "run_package_step_in_its_own_session")
        native = closure.shell_function(UPDATE_NAME, "native_runtime_command")
        native = native.replace("/usr/local/sbin/plebian-os-native-runtime", '"$HELPER"')
        native = native.replace("/usr/bin/sudo", "/usr/bin/env")
        return helper + "\n" + native

    def test_shielded_helper_finishes_and_the_updater_trap_still_fires(self):
        script = (self._shielded_native() + '\ntrap "echo TRAPPED; exit 130" INT\n'
                  'native_runtime_command status\necho RETURNED\nexit 0\n')
        rc, output = press_ctrl_c(script, self.env, self.started)
        self.assertEqual(self.finished.read_text(), "finished\n", output)
        self.assertEqual(rc, 130, output)
        self.assertIn("TRAPPED", output)
        self.assertIn("interrupted; rolling back", output)
        self.assertNotIn("RETURNED", output)

    def test_interrupt_line_is_in_the_updater_log_when_the_terminal_is_gone(self):
        log = self.base / "update.log"
        quoted = str(log).replace("'", "'\\''")
        script = (self._shielded_native() + "\n"
                  f"exec {{_UPDATE_LOG_FD}}>>'{quoted}'\n"
                  'export PLEBIAN_OS_UPDATE_LOG_FD="$_UPDATE_LOG_FD"\n'
                  'exec 2>/dev/null\n'
                  'native_runtime_command status\n')
        rc, _output = press_ctrl_c(script, self.env, self.started)
        self.assertEqual(self.finished.read_text(), "finished\n")
        self.assertEqual(rc, 130)
        self.assertIn("interrupted; rolling back", log.read_text())

    # A step that keeps writing after the terminal is gone, as apt and dpkg do.
    TALKING_HELPER = """#!/usr/bin/python3 -I
import os, signal, sys, time
signal.signal(signal.SIGINT, signal.SIG_DFL)
open(os.environ["STARTED"], "w").close()
for number in range(8):
    print("package output", number, flush=True)
    print("package warning", number, file=sys.stderr, flush=True)
    time.sleep(0.25)
open(os.environ["FINISHED"], "w").write("finished\\n")
"""

    def _hang_up_during_step(self):
        """Run the shielded step under a login-shell stand-in on a pty, close
        the master once the step started, so the shell dies of the hangup and
        its death hangs up the foreground group, and return the updater's
        recorded status. The stand-in step keeps writing for two seconds."""
        self.helper.write_text(self.TALKING_HELPER)
        rc_file = self.base / "updater-rc"
        log = self.base / "update.log"
        quoted = str(log).replace("'", "'\\''")
        script = (self._shielded_native() + "\n"
                  f"exec {{_UPDATE_LOG_FD}}>>'{quoted}'\n"
                  'export PLEBIAN_OS_UPDATE_LOG_FD="$_UPDATE_LOG_FD"\n'
                  f"trap 'echo $? >{shlex.quote(str(rc_file))}' EXIT\n"
                  "trap 'exit 129' HUP\n"
                  "native_runtime_command status\n")
        pid, fd = pty.fork()
        if pid == 0:
            os.execve("/bin/bash", ["/bin/bash", "-c", '"$@"; exit $?', "login-shell",
                                    "/bin/bash", "-c", script], self.env)
        deadline = time.monotonic() + 20
        while not self.started.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(self.started.exists())
        os.close(fd)
        os.waitpid(pid, 0)
        deadline = time.monotonic() + 20
        while not rc_file.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        return rc_file, log

    def test_a_step_finishes_when_the_terminal_vanishes_while_it_writes(self):
        rc_file, log = self._hang_up_during_step()
        deadline = time.monotonic() + 20
        while not self.finished.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(self.finished.read_text(), "finished\n",
                         "the step died with its terminal")
        self.assertEqual(rc_file.read_text().strip(), "129")
        self.assertIn("interrupted; rolling back", log.read_text())

    def test_update_refuses_a_half_installed_package_database(self):
        bin_dir = self.base / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "dpkg"
        fake.write_text('#!/bin/sh\n[ "$1" = --audit ] || exit 9\n'
                        'printf "%s" "$AUDIT"\n')
        fake.chmod(0o700)
        program = "\n".join((
            'warn() { printf "WARN %s\\n" "$*" >&2; }',
            'die() { printf "DIE %s\\n" "$*" >&2; exit 1; }',
            closure.shell_function(UPDATE_NAME, "package_database_faults"),
            closure.shell_function(UPDATE_NAME, "require_consistent_package_database"),
            "require_consistent_package_database", "echo STARTED"))
        for audit, ok in (("", True), ("The following packages are only half configured\n brightnessctl\n", False)):
            with self.subTest(audit=audit):
                result = subprocess.run(
                    ["/bin/bash", "-euc", program], text=True, capture_output=True,
                    env={"PATH": f"{bin_dir}:/usr/bin:/bin", "AUDIT": audit})
                if ok:
                    self.assertEqual((result.returncode, result.stdout), (0, "STARTED\n"), result.stderr)
                else:
                    self.assertEqual(result.returncode, 1)
                    self.assertNotIn("STARTED", result.stdout)
                    self.assertIn("brightnessctl", result.stderr)
                    self.assertIn("dpkg --configure -a", result.stderr)

    def test_the_audit_runs_before_the_transaction_opens(self):
        source = UPDATE.read_text()
        self.assertEqual(source.count("\nrequire_consistent_package_database\n"), 1)
        self.assertIn("\nrequire_consistent_package_database\nbegin_stack_transaction\n", source)

    def test_rollback_names_an_interrupt_as_an_interrupt(self):
        announce = closure.shell_function(UPDATE_NAME, "_announce_stack_rollback")
        body = closure.shell_function(UPDATE_NAME, "rollback_stack_transaction")
        head = body[:body.index("rollback_mpv_runtime_transaction")]
        self.assertLess(
            head.index("_announce_stack_rollback"),
            head.index("remove_transaction_package_additions"))
        program = "\n".join((
            'warn() { printf "%s\\n" "$*"; }', "package_database_faults() { :; }",
            "remove_transaction_package_additions() { :; }",
            "rollback_mpv_runtime_transaction() { return 1; }",
            announce, head + "    return 0\n}", "rollback_stack_transaction"))
        for status, expected in (("130", "interrupted; rolling back"),
                                 ("143", "interrupted; rolling back"),
                                 ("1", "stack update failed")):
            with self.subTest(status=status):
                result = subprocess.run(
                    ["/bin/bash", "-euc", program], text=True, capture_output=True,
                    env={"PATH": "/usr/bin:/bin", "_STACK_TXN_EXIT_STATUS": status})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(result.stdout.startswith(expected), result.stdout)

    def _open_log(self, path: Path, prelude: str = ""):
        script = (
            "set -euo pipefail\n"
            + prelude
            + "export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1\n"
            + f"export PLEBIAN_OS_UPDATE_LOG={shlex.quote(str(path))}\n"
            + f". {shlex.quote(str(UPDATE))}\n"
            + "printf 'fd=%s\\n' \"${PLEBIAN_OS_UPDATE_LOG_FD:-}\"\n"
        )
        return subprocess.run(
            ["/bin/bash", "-c", script], text=True, capture_output=True,
            env={"PATH": "/usr/bin:/bin", "HOME": str(self.base), "LANG": "C"})

    def test_a_new_log_is_mode_0600_even_when_chmod_fails(self):
        path = self.base / "fresh.log"
        result = self._open_log(path, "umask 000\nchmod() { return 1; }\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_an_existing_log_is_tightened_to_0600(self):
        path = self.base / "existing.log"
        path.write_text("keep\n")
        path.chmod(0o644)
        result = self._open_log(path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertIn("keep", path.read_text())

    def test_a_symlink_log_is_left_alone(self):
        victim = self.base / "victim"
        victim.write_text("secret\n")
        victim.chmod(0o644)
        link = self.base / "linked.log"
        link.symlink_to(victim)
        result = self._open_log(link)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("symlink", result.stderr)
        self.assertEqual(victim.read_text(), "secret\n")
        self.assertEqual(victim.stat().st_mode & 0o777, 0o644)
        rotated = self.base / "rotated.log"
        rotated.write_text("plain\n")
        (self.base / "rotated.log.1").symlink_to(victim)
        again = self._open_log(rotated)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(victim.read_text(), "secret\n")
        self.assertEqual(victim.stat().st_mode & 0o777, 0o644)
        self.assertEqual(rotated.read_text(), "plain\n")

    def test_the_log_fd_is_inherited_by_a_child(self):
        path = self.base / "inherited.log"
        script = (
            "set -euo pipefail\n"
            "export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1\n"
            f"export PLEBIAN_OS_UPDATE_LOG={shlex.quote(str(path))}\n"
            f". {shlex.quote(str(UPDATE))}\n"
            'fd="${PLEBIAN_OS_UPDATE_LOG_FD:-}"\n'
            '[ -n "$fd" ] || exit 2\n'
            'seen="$(/bin/bash -c \'if [ -e "/proc/self/fd/$1" ]; then echo VISIBLE; else echo ABSENT; fi\' bash "$fd")"\n'
            'printf "named=%s seen=%s\\n" "$fd" "$seen"\n'
        )
        result = subprocess.run(
            ["/bin/bash", "-c", script], text=True, capture_output=True,
            env={"PATH": "/usr/bin:/bin", "HOME": str(self.base), "LANG": "C"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("seen=VISIBLE", result.stdout)
        self.assertNotIn("seen=ABSENT", result.stdout)

    def test_a_group_sigint_puts_the_helper_line_in_the_log(self):
        log = self.base / "update.log"
        started = self.base / "step-started"
        finished = self.base / "step-finished"
        script = "\n".join((
            "set -euo pipefail",
            "export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1",
            f"export PLEBIAN_OS_UPDATE_LOG={shlex.quote(str(log))}",
            f". {shlex.quote(str(UPDATE))}",
            "rollback() {",
            '    warn "ROLLBACK status=${_STACK_TXN_EXIT_STATUS:-?}"',
            '    [ "${_STACK_TXN_EXIT_STATUS:-1}" = 130 ] && warn "interrupted; rolling back"',
            "}",
            "trap rollback EXIT",
            "trap 'acknowledge_update_interrupt 130' INT",
            "run_package_step_in_its_own_session /usr/bin/setsid --wait /bin/bash -c \\",
            f"    'trap \"\" INT HUP QUIT; : >{shlex.quote(str(started))}; sleep 1.5; echo finished >{shlex.quote(str(finished))}'",
            "echo RETURNED",
        ))
        proc = subprocess.Popen(
            ["/bin/bash", "-c", script], start_new_session=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            env={"PATH": "/usr/bin:/bin", "HOME": str(self.base), "LANG": "C"})
        deadline = time.monotonic() + 10
        while not started.exists() and time.monotonic() < deadline:
            if proc.poll() is not None:
                break
            time.sleep(0.02)
        self.assertTrue(started.exists(), "the shielded step did not start")
        os.killpg(proc.pid, signal.SIGINT)
        try:
            output, _ = proc.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            output, _ = proc.communicate()
            self.fail("updater did not return after the group signal: " + output)
        self.assertEqual(proc.returncode, 130, output)
        self.assertTrue(finished.is_file(), output)
        self.assertNotIn("RETURNED", output)
        self.assertIn("interrupted; rolling back", output)
        lines = [line for line in log.read_text().splitlines() if line]
        interrupts = [line for line in lines if "interrupted; rolling back" in line]
        self.assertEqual(len(lines), 4, lines)
        self.assertEqual(len(interrupts), 3, lines)
        self.assertTrue(any("ROLLBACK status=130" in line for line in lines), lines)

    def test_a_log_over_the_bound_rotates(self):
        path = self.base / "big.log"
        path.write_bytes(b"z" * (1048576 + 1))
        result = self._open_log(path)
        self.assertEqual(result.returncode, 0, result.stderr)
        previous = Path(str(path) + ".1")
        self.assertTrue(previous.is_file())
        self.assertEqual(previous.stat().st_size, 1048576 + 1)
        self.assertLess(path.stat().st_size, 1048576)

    def test_log_writes_through_the_updater_log(self):
        path = self.base / "record.log"
        script = (
            "set -euo pipefail\n"
            "export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1\n"
            f"export PLEBIAN_OS_UPDATE_LOG={shlex.quote(str(path))}\n"
            f". {shlex.quote(str(UPDATE))}\n"
            "log 'phrase-for-the-updater-log'\n"
        )
        result = subprocess.run(
            ["/bin/bash", "-c", script], text=True, capture_output=True,
            env={"PATH": "/usr/bin:/bin", "HOME": str(self.base), "LANG": "C"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("phrase-for-the-updater-log", path.read_text())


if __name__ == "__main__":
    unittest.main()
