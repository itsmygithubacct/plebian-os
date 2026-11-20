"""Run the OS updater against a fake package database and a disposable checkout."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


UPDATER = Path(__file__).resolve().parents[1] / "provision/plebian-os-update.sh"
PACKAGES = ("task-pleb-desktop", "pleb-desktop", "pleb", "kilix")
ROLLBACK = "install the previous release's frozen suite"
STUB = r"""#!/bin/sh
set -eu
name=${0##*/}
case "$name" in
    dpkg-query)
        [ "$#" = 4 ] && [ "$1" = -W ] && [ "$2" = -f ] && [ "$3" = '${db:Status-Status}' ] || exit 90
        case " $INSTALLED " in
            *" $4 "*) printf installed ;;
            *) [ "$4" = "${RESIDUAL:-pleb-desktop}" ] || exit 1; printf config-files ;;
        esac
        exit 0 ;;
    id)
        if [ "$*" = -u ] && [ -n "${TEST_UID:-}" ]; then echo "$TEST_UID"; exit 0; fi
        exec /usr/bin/id "$@" ;;
    systemd-run) echo systemd-run >> "$CALLS"; exit 0 ;;
esac
echo "$name $*" >> "$CALLS"
case "$name" in
    sudo) [ "$1" = apt-get ] || exit 91; exec "$@" ;;
    apt-get) [ "$1" != "${FAIL_APT:-}" ] || exit 42 ;;
    apt-cache)
        [ "$1" = policy ] || exit 92
        [ "${FAIL_APT:-}" != policy ] || exit 42
        shift
        for package do
            printf '%s:\n  Installed: 0.2.4-1\n  Candidate: 0.2.5-1\n' "$package"
        done ;;
    *) exit 93 ;;
esac
"""


def install_stubs(directory):
    for command in ("dpkg-query", "id", "sudo", "apt-get", "apt-cache", "git", "pleb", "systemd-run"):
        path = directory / command
        path.write_text(STUB)
        path.chmod(0o755)


class PackagedAptUpdateTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.stubs = self.root / "bin"
        self.stubs.mkdir()
        install_stubs(self.stubs)
        self.home = self.root / "home"
        self.home.mkdir()
        self.checkout = self.root / "sources/pleb"
        (self.checkout / "bin").mkdir(parents=True)
        # Record any install attempt through the old checkout's absolute launcher.
        (self.checkout / "bin/pleb").symlink_to(self.stubs / "pleb")
        self.data = self.home / ".local/gpu_terminal"
        self.calls = self.root / "calls"
        self.updater = self.root / "plebian-os-update"
        shutil.copyfile(UPDATER, self.updater)
        # A checkout update configured with a source carrier reaches this helper first.
        (self.root / "plebian-os-source-carrier").write_text(
            'raise SystemExit("checkout source carrier reached")\n')

    def update(self, *args, installed=PACKAGES, **extra):
        env = {"PATH": f"{self.stubs}:/usr/bin:/bin", "HOME": str(self.home),
               "TMPDIR": str(self.root), "PYTHONDONTWRITEBYTECODE": "1",
               "CALLS": str(self.calls), "INSTALLED": " ".join(installed),
               "PLEB_DIR": str(self.checkout), "GPU_TERMINAL_HOME": str(self.data),
               "KILIX_SOURCE_CARRIER_MANIFEST": str(self.root / "manifest.json"), **extra}
        return subprocess.run(["bash", str(self.updater), *args], env=env, text=True,
                              capture_output=True, stdin=subprocess.DEVNULL, timeout=10)

    def recorded_calls(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def test_reports_fresh_versions_and_upgrades_installed_members(self):
        for uid, installed in (("1000", PACKAGES), ("0", ("task-pleb-desktop", "pleb"))):
            with self.subTest(uid=uid):
                self.calls.unlink(missing_ok=True)
                result = self.update(installed=installed, TEST_UID=uid)
                self.assertEqual(result.returncode, 0, result.stderr)
                names = " ".join(installed)
                update = "apt-get update"
                policy = f"apt-cache policy {names}"
                upgrade = f"apt-get upgrade --only-upgrade {names}"
                if uid != "0":
                    calls = [f"sudo {update}", update, policy, f"sudo {upgrade}", upgrade]
                else:
                    calls = [update, policy, upgrade]
                self.assertEqual(self.recorded_calls(), calls)
                for package in installed:
                    self.assertIn(f"{package}:\n  Installed: 0.2.4-1\n  Candidate: 0.2.5-1", result.stdout)
                self.assertIn(ROLLBACK, result.stdout)
                self.assertIn("snapshot", result.stdout)
                self.assertFalse(self.data.exists())

    def test_source_check_recovery_and_unknown_flags_leave_snapshot_alone(self):
        snapshot = self.data / "pleb/state/stack-rollback.ABCDEF"
        snapshot.mkdir(parents=True)
        marker = snapshot / "pleb.head"
        marker.write_text("original\n")
        for args, success, message in (
            (("--check-source-checkouts",), True, "apt owns updates"),
            (("--recover-interrupted",), False, ROLLBACK),
            (("--revalidate-current",), False, "checkout installation"),
            (("--typo",), False, "--typo"),
            (("--check-source-checkouts", "--typo"), False, "--typo"),
        ):
            with self.subTest(args=args):
                result = self.update(*args)
                self.assertEqual(result.returncode == 0, success, result.stderr)
                self.assertIn(message, result.stdout if success else result.stderr)
                self.assertEqual(self.recorded_calls(), [])
                self.assertEqual(marker.read_text(), "original\n")
                self.assertEqual(list(snapshot.parent.iterdir()), [snapshot])

    def test_apt_errors_propagate(self):
        for step in ("update", "policy", "upgrade"):
            with self.subTest(step=step):
                self.calls.unlink(missing_ok=True)
                result = self.update("--restart", FAIL_APT=step, TEST_UID="0")
                self.assertEqual(result.returncode, 42, result.stderr)
                self.assertNotIn(ROLLBACK, result.stdout)
                command = "apt-cache" if step == "policy" else "apt-get"
                self.assertEqual(self.recorded_calls()[-1].split()[:2], [command, step])
                if step == "update":
                    self.assertEqual(self.recorded_calls(), ["apt-get update"])

    def test_explicit_restart_follows_the_package_upgrade(self):
        result = self.update("--restart", installed=("task-pleb-desktop",), TEST_UID="0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.recorded_calls(), ["apt-get update", "apt-cache policy task-pleb-desktop",
                                                "apt-get upgrade --only-upgrade task-pleb-desktop", "systemd-run"])

    def test_without_the_task_package_the_checkout_path_remains(self):
        installed = ("pleb-desktop", "pleb", "kilix")
        for residual in ("", "task-pleb-desktop"):
            with self.subTest(residual=residual):
                result = self.update(installed=installed, RESIDUAL=residual)
                self.assertNotEqual(result.returncode, 0)
                if os.geteuid() == 0:
                    self.assertIn("run plebian-os-update without sudo", result.stderr)
                else:
                    self.assertIn("checkout source carrier reached", result.stderr)
        result = self.update("--check-source-checkouts", installed=installed, KILIX_SOURCE_CARRIER_SESSION="1")
        self.assertNotEqual(result.returncode, 0)
        if os.geteuid() != 0:
            self.assertIn("exists but is not a git checkout", result.stderr)
        self.assertEqual(self.recorded_calls(), [])
        self.assertFalse(self.data.exists())

    def test_packaged_dispatch_precedes_the_checkout_move(self):
        source = UPDATER.read_text()
        dispatch = source.index('packaged_os_update "$@"')
        self.assertLess(dispatch, source.index('require_unprivileged_updater "$EUID"'))
        self.assertLess(dispatch, source.index("\nupdate_pleb_checkout\n"))


if __name__ == "__main__":
    unittest.main()
