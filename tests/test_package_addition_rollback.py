"""Rollback removes only apt packages this transaction newly installed.

The fakes stand in for dpkg-query and apt-get. A package that was already
installed, one the operator added between steps, and one apt would not remove
alone are kept. A recorded addition is removed, last one first.
"""
import os
import shlex
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
UPDATE = REPO / "provision/plebian-os-update.sh"

DPKG = r"""#!/bin/bash
db="$PKGDB"
[ "$1" = -W ] || exit 9
last="${@: -1}"
if [ "$3" = -- ] || [ "$4" = -- ]; then
    if grep -Fxq -- "$last" "$db"; then
        printf installed
        exit 0
    fi
    printf not-installed
    exit 1
fi
while IFS= read -r name; do
    [ -n "$name" ] || continue
    printf '%s\tinstalled\n' "$name"
done < "$db"
"""

APT = r"""#!/bin/bash
printf '%s\n' "$*" >>"$APT_LOG"
sim=0
if [ "$1" = -s ]; then
    sim=1
    shift
fi
pkg="${@: -1}"
if [ "$sim" = 1 ]; then
    if [ "$pkg" = "${APT_FAIL_FOR:-}" ]; then
        printf '%s\n' "E: Essential packages were removed and -y was used without --allow-remove-essential." >&2
        exit 100
    fi
    printf 'Remv %s [1]\n' "$pkg"
    case "${APT_EXTRA_FOR:-}" in
        "$pkg:"*) printf 'Remv %s [1]\n' "${APT_EXTRA_FOR#*:}" ;;
    esac
    exit 0
fi
if [ "$pkg" = "${APT_REMOVE_FAIL_FOR:-}" ]; then
    exit 100
fi
grep -Fxv -- "$pkg" "$PKGDB" > "$PKGDB.next" || true
mv -f -- "$PKGDB.next" "$PKGDB"
exit 0
"""


class PackageAdditionRollbackTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.db = self.base / "packages"
        self.log = self.base / "apt.log"
        self.txn = self.base / "txn"
        self.txn.mkdir()
        (self.bin / "dpkg-query").write_text(DPKG)
        (self.bin / "apt-get").write_text(APT)
        (self.bin / "id").write_text("#!/bin/sh\nprintf '0\\n'\n")
        for path in self.bin.iterdir():
            path.chmod(0o755)
        self.env = {
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "HOME": str(self.base / "home"),
            "TMPDIR": str(self.base),
            "LANG": "C",
            "PLEB_STATE_HOME": str(self.base / "state"),
            "PKGDB": str(self.db),
            "APT_LOG": str(self.log),
            "TXN": str(self.txn),
        }

    def tearDown(self):
        self._tmp.cleanup()

    def run_body(self, body: str, **env):
        script = (
            "set -euo pipefail\n"
            "export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1\n"
            f". {shlex.quote(str(UPDATE))}\n"
            "log() { printf 'LOG %s\\n' \"$*\"; }\n"
            "warn() { printf 'WARN %s\\n' \"$*\" >&2; }\n"
            "_STACK_TXN_DIR=\"$TXN\"\n"
            + textwrap.dedent(body)
        )
        merged = dict(self.env)
        merged.update(env)
        return subprocess.run(
            ["/bin/bash", "-c", script], env=merged,
            text=True, capture_output=True, check=False)

    def packages(self) -> list[str]:
        return [line for line in self.db.read_text().splitlines() if line]

    def apt_commands(self) -> list[str]:
        if not self.log.exists():
            return []
        return [line for line in self.log.read_text().splitlines() if line]

    def removes(self) -> list[str]:
        found = []
        for line in self.apt_commands():
            if line.startswith("remove "):
                found.append(line.split()[-1])
        return found

    def test_windows_ignore_what_was_already_there_and_operator_packages(self):
        self.db.write_text("bash\ncoreutils\n")
        result = self.run_body(
            """
            record_transaction_package_baseline
            begin_package_addition_window
            printf '%s\\n' bash coreutils power-profiles-daemon >"$PKGDB"
            end_package_addition_window
            printf '%s\\n' bash coreutils power-profiles-daemon operator-pkg >"$PKGDB"
            begin_package_addition_window
            end_package_addition_window
            remove_transaction_package_additions
            """)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (self.txn / "apt-additions").read_text().splitlines(),
            ["power-profiles-daemon"])
        self.assertEqual(self.packages(), ["bash", "coreutils", "operator-pkg"])
        self.assertEqual(self.removes(), ["power-profiles-daemon"])
        self.assertIn(
            "removed packages this update had installed: power-profiles-daemon",
            result.stdout)

    def test_an_open_window_is_closed_when_the_step_dies(self):
        self.db.write_text("bash\n")
        result = self.run_body(
            """
            record_transaction_package_baseline
            begin_package_addition_window
            printf '%s\\n' bash newpkg >"$PKGDB"
            remove_transaction_package_additions
            """)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.packages(), ["bash"])
        self.assertEqual(self.removes(), ["newpkg"])
        self.assertFalse((self.txn / "apt-window-open").exists())

    def test_a_package_recorded_but_already_present_is_not_removed(self):
        self.db.write_text("bash\nkept\n")
        (self.txn / "apt-installed-before").write_text("bash\nkept\n")
        (self.txn / "apt-additions").write_text("kept\n")
        result = self.run_body("remove_transaction_package_additions\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.packages(), ["bash", "kept"])
        self.assertEqual(self.removes(), [])

    def test_unsafe_names_are_ignored_and_removals_run_in_reverse(self):
        self.db.write_text("aaa\nbbb\n")
        (self.txn / "apt-installed-before").write_text("")
        (self.txn / "apt-additions").write_text("aaa\n../evil\nNotAName\nbbb\n")
        result = self.run_body("remove_transaction_package_additions\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.removes(), ["bbb", "aaa"])
        self.assertEqual(self.packages(), [])
        logged = "\n".join(self.apt_commands())
        self.assertNotIn("../evil", logged)
        self.assertNotIn("NotAName", logged)
        self.assertIn("removed packages this update had installed: bbb aaa", result.stdout)

    def test_a_removal_that_would_take_something_else_is_kept_and_named(self):
        self.db.write_text("power-profiles-daemon\nsudo\n")
        (self.txn / "apt-installed-before").write_text("sudo\n")
        (self.txn / "apt-additions").write_text("power-profiles-daemon\n")
        result = self.run_body(
            "remove_transaction_package_additions\n",
            APT_EXTRA_FOR="power-profiles-daemon:sudo")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("power-profiles-daemon", self.packages())
        self.assertEqual(self.removes(), [])
        self.assertIn(
            "keeping power-profiles-daemon: removing it would also remove sudo, "
            "which this update did not install",
            result.stderr)

    def test_an_unsafe_simulation_keeps_the_package(self):
        self.db.write_text("bash\n")
        (self.txn / "apt-installed-before").write_text("")
        (self.txn / "apt-additions").write_text("bash\n")
        result = self.run_body(
            "remove_transaction_package_additions\n",
            APT_FAIL_FOR="bash")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.packages(), ["bash"])
        self.assertEqual(self.removes(), [])
        self.assertIn(
            "keeping bash: removing it is not safe; it is still installed",
            result.stderr)

    def test_a_failed_remove_is_kept_and_does_not_fail_rollback(self):
        self.db.write_text("stuck\n")
        (self.txn / "apt-installed-before").write_text("")
        (self.txn / "apt-additions").write_text("stuck\n")
        result = self.run_body(
            "remove_transaction_package_additions\n",
            APT_REMOVE_FAIL_FOR="stuck")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.packages(), ["stuck"])
        self.assertIn(
            "keeping stuck: apt remove failed; it is still installed",
            result.stderr)

    def test_missing_dpkg_query_removes_nothing(self):
        hidden = self.base / "no-dpkg"
        hidden.mkdir()
        os.symlink(self.bin / "id", hidden / "id")
        self.db.write_text("bash\n")
        result = self.run_body(
            """
            PATH="$HIDDEN"
            record_transaction_package_baseline
            printf '%s\\n' bash extra >"$PKGDB"
            remove_transaction_package_additions
            """,
            HIDDEN=str(hidden))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.txn / "apt-additions-untracked").is_file())
        self.assertEqual(self.packages(), ["bash", "extra"])
        self.assertIn("package additions were not tracked", result.stderr)


if __name__ == "__main__":
    unittest.main()
