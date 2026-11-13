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

    def test_shielded_helper_finishes_and_the_updater_trap_still_fires(self):
        native = closure.shell_function(UPDATE_NAME, "native_runtime_command")
        native = native.replace("/usr/local/sbin/plebian-os-native-runtime", '"$HELPER"')
        native = native.replace("/usr/bin/sudo", "/usr/bin/env")
        script = (native + '\ntrap "echo TRAPPED; exit 130" INT\n'
                  'native_runtime_command status\necho RETURNED\nexit 0\n')
        rc, output = press_ctrl_c(script, self.env, self.started)
        self.assertEqual(self.finished.read_text(), "finished\n", output)
        self.assertEqual(rc, 130, output)
        self.assertIn("TRAPPED", output)
        self.assertNotIn("RETURNED", output)

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
        body = closure.shell_function(UPDATE_NAME, "rollback_stack_transaction")
        head = body[:body.index("rollback_mpv_runtime_transaction")]
        program = "\n".join((
            'warn() { printf "%s\\n" "$*"; }', "package_database_faults() { :; }",
            "rollback_mpv_runtime_transaction() { return 1; }",
            head + "    return 0\n}", "rollback_stack_transaction"))
        for status, expected in (("130", "update interrupted (status 130)"),
                                 ("143", "update interrupted (status 143)"),
                                 ("1", "stack update failed")):
            with self.subTest(status=status):
                result = subprocess.run(
                    ["/bin/bash", "-euc", program], text=True, capture_output=True,
                    env={"PATH": "/usr/bin:/bin", "_STACK_TXN_EXIT_STATUS": status})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(result.stdout.startswith(expected), result.stdout)


if __name__ == "__main__":
    unittest.main()
