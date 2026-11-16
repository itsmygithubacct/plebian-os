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
lookup() {
    local name="$1" line
    if [ -n "${PKGSTATUS:-}" ] && [ -f "$PKGSTATUS" ]; then
        line="$(awk -F '\t' -v n="$name" '$1 == n { print $2; exit }' "$PKGSTATUS")"
        if [ -n "$line" ]; then
            printf '%s' "$line"
            return 0
        fi
    fi
    if grep -Fxq -- "$name" "$db"; then
        printf installed
        return 0
    fi
    printf not-installed
    return 1
}
if [ "$3" = -- ] || [ "$4" = -- ]; then
    lookup "$last"
    exit $?
fi
while IFS= read -r name; do
    [ -n "$name" ] || continue
    printf '%s\tinstalled\n' "$name"
done < "$db"
"""

# release_apt_get puts -o Dir::... before the apt arguments, and prepare asks
# `apt-get update --print-uris`. -s may appear anywhere. The last argument of
# a remove is the package. APT_KILL_PID is the updater bash pid. SIGTERM goes
# to that pid, not the process group, while setsid is in the foreground.
# SIGINT is discarded when that child then exits 0, so it would not prove
# the removal trap is what kept the shell alive.
APT = r"""#!/bin/bash
printf '%s\n' "$*" >>"$APT_LOG"
for arg in "$@"; do
    if [ "$arg" = update ]; then
        printf "'https://deb.debian.org/debian/dists/%s/main/binary-amd64/Packages' %s/main amd64 Packages\n" \
            "${APT_CODENAME:-trixie}" "${APT_CODENAME:-trixie}"
        exit 0
    fi
done
sim=0
for arg in "$@"; do
    if [ "$arg" = -s ]; then
        sim=1
    fi
done
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
if [ -n "${APT_KILL_PID:-}" ]; then
    kill -TERM "$APT_KILL_PID" 2>/dev/null || true
    sleep 0.2
fi
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
        (self.bin / "sudo").write_text("#!/bin/sh\nexec \"$@\"\n")
        for path in self.bin.iterdir():
            path.chmod(0o755)
        codename = "trixie"
        for line in Path("/etc/os-release").read_text().splitlines():
            if line.startswith("VERSION_CODENAME="):
                codename = line.split("=", 1)[1].strip().strip('"')
        apt_root = self.base / "apt"
        apt_root.mkdir()
        (apt_root / "sources.list").write_text(
            f"deb https://deb.debian.org/debian {codename} main\n")
        self.env = {
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "HOME": str(self.base / "home"),
            "TMPDIR": str(self.base),
            "LANG": "C",
            "PLEB_STATE_HOME": str(self.base / "state"),
            "PKGDB": str(self.db),
            "APT_LOG": str(self.log),
            "TXN": str(self.txn),
            "APT_CODENAME": codename,
            "PLEBIAN_OS_APT_SOURCES_ROOT": str(apt_root),
        }

    def tearDown(self):
        self._tmp.cleanup()

    def patched_update(self) -> Path:
        # Behavioral tests must not call the real /usr/bin/id or /usr/bin/sudo.
        # The static pin test reads UPDATE, the unpatched file.
        text = UPDATE.read_text()
        text = text.replace("/usr/bin/id", str(self.bin / "id"))
        text = text.replace("/usr/bin/sudo", str(self.bin / "sudo"))
        path = self.base / "updater.sh"
        path.write_text(text)
        return path

    def run_body(self, body: str, **env):
        script = (
            "set -euo pipefail\n"
            "export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1\n"
            f". {shlex.quote(str(self.patched_update()))}\n"
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
            words = line.split()
            if "-s" in words or "remove" not in words:
                continue
            found.append(words[-1])
        return found

    def assert_private_source_list(self):
        removal = [
            line for line in self.apt_commands()
            if "remove" in line.split() and "-s" not in line.split()
        ]
        self.assertTrue(removal, self.apt_commands())
        self.assertTrue(
            any("Dir::Etc::SourceList=" in line and "/etc/apt" not in line
                for line in removal),
            removal)

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
        self.assert_private_source_list()
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

    def test_a_window_left_by_another_process_removes_nothing(self):
        self.db.write_text("bash\n")
        first = self.run_body(
            """
            record_transaction_package_baseline
            begin_package_addition_window
            printf '%s\\n' bash stepdep operator-tool >"$PKGDB"
            """)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertTrue((self.txn / "apt-window-open").is_file())
        second = self.run_body("remove_transaction_package_additions\n")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(
            self.packages(), ["bash", "stepdep", "operator-tool"])
        self.assertEqual(self.removes(), [])
        self.assertIn("another process", second.stderr)
        self.assertIn("package additions were not tracked", second.stderr)
        self.assertTrue((self.txn / "apt-additions-untracked").is_file())

    def test_a_removed_baseline_package_keeps_new_packages(self):
        self.db.write_text("foo-ng\n")
        (self.txn / "apt-installed-before").write_text("foo\n")
        (self.txn / "apt-additions").write_text("foo-ng\n")
        result = self.run_body("remove_transaction_package_additions\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.packages(), ["foo-ng"])
        self.assertEqual(self.removes(), [])
        self.assertIn("the update also removed foo", result.stderr)
        self.assertIn("rollback does not reinstall removed packages", result.stderr)

    def test_a_config_files_leftover_is_not_passed_to_apt(self):
        self.db.write_text("leftover\n")
        status = self.base / "status"
        status.write_text("leftover\tconfig-files\n")
        (self.txn / "apt-installed-before").write_text("")
        (self.txn / "apt-additions").write_text("leftover\n")
        result = self.run_body(
            "remove_transaction_package_additions\n", PKGSTATUS=str(status))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.packages(), ["leftover"])
        self.assertEqual(self.removes(), [])
        self.assertNotIn("leftover", "\n".join(self.apt_commands()))

    def test_unsafe_names_installed_in_the_database_are_not_removed(self):
        self.db.write_text("aaa\n../evil\nNotAName\n")
        (self.txn / "apt-installed-before").write_text("")
        (self.txn / "apt-additions").write_text("aaa\n../evil\nNotAName\n")
        result = self.run_body("remove_transaction_package_additions\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.removes(), ["aaa"])
        self.assertEqual(self.packages(), ["../evil", "NotAName"])
        logged = "\n".join(self.apt_commands())
        self.assertNotIn("../evil", logged)
        self.assertNotIn("NotAName", logged)

    def test_a_signal_to_the_updater_during_removal_still_removes(self):
        self.db.write_text("newpkg\n")
        (self.txn / "apt-installed-before").write_text("")
        (self.txn / "apt-additions").write_text("newpkg\n")
        result = self.run_body(
            """
            export APT_KILL_PID=$$
            remove_transaction_package_additions
            echo survived
            """)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("survived", result.stdout)
        self.assertEqual(self.packages(), [])
        self.assertEqual(self.removes(), ["newpkg"])

    def test_rollback_itself_removes_the_recorded_package(self):
        self.db.write_text("newpkg\n")
        (self.txn / "apt-installed-before").write_text("")
        (self.txn / "apt-additions").write_text("newpkg\n")
        result = self.run_body(
            """
            package_database_faults() { :; }
            rollback_mpv_runtime_transaction() { return 0; }
            rollback_qt_runtime_transaction() { return 0; }
            rollback_native_runtime_transaction() { return 0; }
            deinit_new_kilix_submodules() { return 0; }
            restore_stack_checkout() { return 0; }
            restore_recorded_kilix_submodules() { return 0; }
            restore_stack_path() { return 0; }
            restore_kilix_engine_generation() { return 0; }
            restore_kilix_claudex_install() { return 0; }
            restore_root_stack_snapshot() { return 0; }
            report_selection_against_installation() { return 0; }
            rollback_stack_transaction || true
            echo survived
            """)
        self.assertIn("survived", result.stdout, result.stderr)
        self.assertEqual(self.removes(), ["newpkg"], result.stderr)
        self.assertEqual(self.packages(), [])

    def test_the_dependency_step_keeps_its_package_window(self):
        source = UPDATE.read_text()
        needle = (
            "begin_package_addition_window\n"
            "refresh_os_dependencies\n"
            "end_package_addition_window\n")
        self.assertEqual(source.count(needle), 1)

    def test_the_baseline_is_recorded_with_the_owner(self):
        source = UPDATE.read_text()
        needle = (
            "    record_transaction_package_baseline\n"
            "    record_stack_transaction_owner")
        self.assertEqual(source.count(needle), 1)

    def test_package_removal_pins_id_sudo_and_release_apt(self):
        text = UPDATE.read_text()
        start = text.index("remove_transaction_package_additions() {")
        body = text[start:text.index("\n}\n", start)]
        self.assertIn("/usr/bin/id -u", body)
        self.assertIn("/usr/bin/sudo", body)
        run = text.index("_run_release_apt() {")
        runner = text[run:text.index("\n}\n", run)]
        self.assertIn("plebian-os-removal", runner)
        self.assertIn('release_apt_get "$@"', runner)
        self.assertNotIn("plebian-os-package-step", runner)


if __name__ == "__main__":
    unittest.main()
