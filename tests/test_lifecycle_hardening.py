import re
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UPDATE_PATH = ROOT / "provision" / "plebian-os-update.sh"
PROVISION = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
UPDATE = UPDATE_PATH.read_text()
FIRSTBOOT = (ROOT / "provision" / "plebian-os-firstboot.service").read_text()
ATTEMPT = ROOT / "provision" / "plebian-os-firstboot-attempt"


class UpdateLifecycleTests(unittest.TestCase):
    def test_update_is_serialized(self):
        self.assertIn("acquire_update_lock", UPDATE)
        self.assertIn('local lock="$PLEB_STATE_HOME/update.lock"', UPDATE)
        self.assertIn("flock -n 9", UPDATE)
        self.assertIn('"PLEB_UPDATE_LOCK_FD=9"', UPDATE)
        self.assertIn('"PLEB_STATE_HOME=$PLEB_STATE_HOME"', UPDATE)
        self.assertNotIn("PLEBIAN_OS_UPDATE_LOCK", UPDATE)
        self.assertLess(UPDATE.index("acquire_update_lock\n"),
                        UPDATE.index("self_update_os_layer\n"))

    def test_root_session_config_is_ownership_and_path_validated(self):
        self.assertIn("root_config_safe_to_source", UPDATE)
        self.assertIn('[ ! -L "$cfg" ]', UPDATE)
        self.assertIn("(8#$mode & 8#22)", UPDATE)
        self.assertIn("refusing to source unsafe /etc/pleb/session.env as root", UPDATE)
        self.assertLess(UPDATE.index("root_config_safe_to_source /etc/pleb/session.env"),
                        UPDATE.index(". /etc/pleb/session.env"))

    def test_restart_is_explicit_opt_in(self):
        self.assertIn("Usage: plebian-os-update [--restart]", UPDATE)
        self.assertIn("restart_arg=--no-restart", UPDATE)
        self.assertIn("--restart) restart_arg=--restart", UPDATE)
        self.assertIn('pleb" update --no-restart', UPDATE)
        self.assertIn("restart_session_after_commit", UPDATE)
        self.assertLess(UPDATE.index("commit_stack_transaction\n"),
                        UPDATE.index("restart_session_after_commit\n"))
        help_result = subprocess.run(
            ["bash", str(UPDATE_PATH), "--help"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("Usage: plebian-os-update [--restart]", help_result.stdout)

    def test_pinned_checkouts_are_clean_and_fetch_resolved(self):
        self.assertIn("status --porcelain --untracked-files=normal", UPDATE)
        self.assertIn("status --porcelain --untracked-files=normal", PROVISION)
        for source in (UPDATE, PROVISION):
            self.assertIn("FETCH_HEAD^{commit}", source)
            self.assertIn('actual" = "$resolved', source)
            self.assertIn("require_clean_pinned_checkout", source)

    def test_os_layer_is_complete_validated_and_transactional(self):
        for name in (
            "plebian-os-provision",
            "plebian-os-install-deps",
            "plebian-os-passwd",
            "plebian-os-update",
            "plebian-os-firstboot.service",
            "plebian-os-firstboot-attempt",
            "VERSION",
        ):
            self.assertIn(name, UPDATE)
        self.assertIn("bash -n", UPDATE)
        self.assertIn("compile(pathlib.Path", UPDATE)
        self.assertIn("staged firstboot unit", UPDATE)
        self.assertIn("systemd-analyze verify", UPDATE)
        self.assertIn("backup_paths", UPDATE)
        self.assertIn("rollback()", UPDATE)
        self.assertIn("mv -fT", UPDATE)
        self.assertIn("systemctl daemon-reload", UPDATE)
        self.assertIn("Re-validate the root-owned copies", UPDATE)
        self.assertIn("rollback was incomplete", UPDATE)
        self.assertNotIn("continuing with the pleb/kilix update only", UPDATE)
        self.assertNotIn("failed to update /usr/local", UPDATE)
        self.assertLess(UPDATE.index('deploy_staged_os_layer "$stage"'),
                        UPDATE.index('log "OS layer refreshed'))

    def test_privileged_stage_is_bound_to_pre_sudo_hashes(self):
        self.assertIn('local -a expected_hashes=("$@")', UPDATE)
        self.assertIn('stage_hashes+=("$(sha256sum "$stage/$file"', UPDATE)
        self.assertIn('[ "$actual" = "${expected_hashes[$i]}" ]', UPDATE)
        self.assertLess(
            UPDATE.index('actual="$(sha256sum "${new_paths[$i]}"'),
            UPDATE.index("# Back up the complete old set"),
        )

    def test_outer_transaction_covers_every_stack_boundary(self):
        for marker in ("os-layer", "pleb-checkout", "pleb-install",
                       "component-update"):
            self.assertIn(f"test_fail_after_boundary {marker}", UPDATE)
        for primitive in (
            "begin_stack_transaction",
            "rollback_stack_transaction",
            "restore_root_stack_snapshot",
            'record_stack_checkout "$PLEB_DIR" pleb pleb',
            'snapshot_stack_path "$KILIX_DIR/kitty.app" kilix-prebuilt',
            "/usr/local/bin/pleb-session",
            "/usr/share/xsessions/pleb.desktop",
            "/usr/local/bin/kilix",
            "/usr/local/bin/pleb",
        ):
            self.assertIn(primitive, UPDATE)
        self.assertLess(UPDATE.index("begin_stack_transaction\n"),
                        UPDATE.index("self_update_os_layer\n"))
        self.assertLess(UPDATE.index("commit_stack_transaction\n"),
                        UPDATE.index('log "Plebian-OS stack updated."'))

    def test_injected_boundary_failures_restore_checkout_and_outputs(self):
        harness = r'''
set -euo pipefail
script="$1"
work="$2"
boundary="$3"
shift 3
export HOME="$work/home"
export PLEB_STATE_HOME="$work/state"
export PLEB_DIR="$work/pleb"
export PLEBIAN_OS_DIR="$work/os"
export KILIX_DIR="$work/kilix"
export KILIX95_DIR="$work/kilix95"
export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1
mkdir -p "$HOME" "$PLEB_STATE_HOME"
init_repo() {
    dir="$1"
    git init -q -b main "$dir"
    git -C "$dir" config user.name test
    git -C "$dir" config user.email test@example.invalid
    printf '%s\n' old >"$dir/tracked"
    printf '%s\n' 'kitty.app/' >>"$dir/.gitignore"
    git -C "$dir" add tracked .gitignore
    git -C "$dir" commit -q -m old
}
init_repo "$PLEB_DIR"
init_repo "$PLEBIAN_OS_DIR"
init_repo "$KILIX_DIR"
init_repo "$KILIX95_DIR"
mkdir -p "$KILIX_DIR/kitty.app/bin"
printf '%s\n' old-engine >"$KILIX_DIR/kitty.app/bin/kitty"
printf '%s\n' old-root >"$work/root-output"
cp "$work/root-output" "$work/root-backup"
git -C "$PLEB_DIR" rev-parse HEAD >"$work/old-head"
. "$script"

# Replace only the privileged snapshot functions: checkout/path rollback is the
# production implementation under test, while the root-managed representative
# stays inside the temporary test directory.
restore_root_stack_snapshot() { cp "$work/root-backup" "$work/root-output"; }
remove_root_stack_snapshot() { :; }

_STACK_TXN_DIR="$(mktemp -d "$PLEB_STATE_HOME/stack-rollback.XXXXXX")"
record_stack_checkout "$PLEB_DIR" pleb pleb
record_stack_checkout "$PLEBIAN_OS_DIR" os plebian-os
record_stack_checkout "$KILIX_DIR" kilix kilix
record_stack_checkout "$KILIX95_DIR" kilix95 "kilix 95"
snapshot_stack_path "$KILIX_DIR/kitty.app" kilix-prebuilt
_STACK_ROOT_TXN_DIR=/var/lib/plebian-os/update-rollback.test
_STACK_TXN_ACTIVE=1
_STACK_TXN_COMMITTED=0
trap stack_transaction_cleanup EXIT

printf '%s\n' new >"$PLEB_DIR/tracked"
git -C "$PLEB_DIR" add tracked
git -C "$PLEB_DIR" commit -q -m new
printf '%s\n' new-engine >"$KILIX_DIR/kitty.app/bin/kitty"
printf '%s\n' new-root >"$work/root-output"
export PLEBIAN_OS_UPDATE_TEST_FAIL_AFTER="$boundary"
test_fail_after_boundary "$boundary"
'''
        for boundary in ("os-layer", "pleb-checkout", "pleb-install",
                         "component-update"):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as td:
                result = subprocess.run(
                    ["bash", "-c", harness, "harness", str(UPDATE_PATH), td,
                     boundary],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("restored the pre-update", result.stdout)
                work = Path(td)
                self.assertEqual(
                    subprocess.check_output(
                        ["git", "-C", str(work / "pleb"), "rev-parse", "HEAD"],
                        text=True,
                    ).strip(),
                    (work / "old-head").read_text().strip(),
                )
                self.assertEqual(
                    (work / "kilix" / "kitty.app" / "bin" / "kitty")
                    .read_text().strip(),
                    "old-engine",
                )
                self.assertEqual((work / "root-output").read_text().strip(),
                                 "old-root")


class FirstbootBoundTests(unittest.TestCase):
    def test_timeout_attempts_fit_inside_start_limit_window(self):
        self.assertIn("StartLimitIntervalSec=4h", FIRSTBOOT)
        self.assertIn("StartLimitBurst=3", FIRSTBOOT)
        self.assertIn("RestartSec=60s", FIRSTBOOT)
        self.assertIn("TimeoutStartSec=3600", FIRSTBOOT)
        # Three maximum-length attempts plus the two intervening delays remain
        # inside the four-hour start-limit window, so a fourth cannot escape it.
        self.assertGreater(4 * 3600, 3 * 3600 + 2 * 60)
        self.assertIn("ExecStopPost=-/bin/rm -f /etc/sudoers.d/plebian-os-provision",
                      FIRSTBOOT)
        self.assertIn("ExecCondition=/usr/local/sbin/plebian-os-firstboot-attempt check",
                      FIRSTBOOT)
        marker = FIRSTBOOT.index(
            "ExecStartPost=/usr/bin/install -Dm644 /dev/null /var/lib/plebian-os/provisioned")
        clear = FIRSTBOOT.index(
            "ExecStartPost=/usr/local/sbin/plebian-os-firstboot-attempt success")
        self.assertLess(marker, clear, "attempt state must not clear before the success marker")

    def test_attempt_bound_persists_until_success(self):
        with tempfile.TemporaryDirectory() as td:
            env = {**os.environ, "PLEBIAN_OS_STATE_DIR": td,
                   "PLEBIAN_OS_FIRSTBOOT_MAX_ATTEMPTS": "3"}
            for _ in range(3):
                subprocess.run(["sh", str(ATTEMPT), "check"], env=env, check=True,
                               capture_output=True, text=True)
                subprocess.run(["sh", str(ATTEMPT), "begin"], env=env, check=True,
                               capture_output=True, text=True)
            exhausted = subprocess.run(["sh", str(ATTEMPT), "check"], env=env,
                                       capture_output=True, text=True)
            self.assertNotEqual(exhausted.returncode, 0)
            self.assertIn("exhausted 3/3", exhausted.stderr)
            subprocess.run(["sh", str(ATTEMPT), "success"], env=env, check=True)
            subprocess.run(["sh", str(ATTEMPT), "check"], env=env, check=True)

    def test_vm_waiter_reports_exhausted_inactive_attempts(self):
        source = (ROOT / "build" / "build_vm_image.py").read_text()
        self.assertIn('[ -s /var/lib/plebian-os/firstboot-attempts ]', source)
        self.assertIn('[ \\"$s\\" = inactive ]', source)


class ProvisioningLifecycleTests(unittest.TestCase):
    def test_snapshot_can_restore_live_sources(self):
        self.assertIn("restore_live_apt_sources", PROVISION)
        self.assertIn(".plebian-os-disabled", PROVISION)
        self.assertIn("https://deb.debian.org/debian", PROVISION)
        self.assertIn("https://security.debian.org/debian-security", PROVISION)
        self.assertIn("snapshot\\.debian\\.org", PROVISION)

    def test_release_snapshot_update_fails_closed(self):
        self.assertIn("PLEBIAN_OS_RELEASE_MODE", PROVISION)
        self.assertIn("release mode requires PLEBIAN_OS_APT_SNAPSHOT", PROVISION)
        self.assertIn("apt-get update against snapshot", PROVISION)
        self.assertIn("refusing an unpinned/stale package closure", PROVISION)

    def test_final_provenance_is_written_after_builds(self):
        package_call = PROVISION.rindex("\nwrite_package_manifest\n")
        source_call = PROVISION.rindex("\nwrite_source_tool_manifest\n")
        build_call = PROVISION.rindex("\nbuild_kilix_fork\n")
        self.assertGreater(package_call, build_call)
        self.assertGreater(source_call, package_call)
        for artifact in ("packages.list", "versions.env", "apt-sources.list"):
            self.assertIn(artifact, PROVISION)
        for key in ("PLEB_COMMIT", "KILIX_COMMIT", "KILIX95_COMMIT",
                    "GO_VERSION", "KILIX_ENGINE_VERSION"):
            self.assertIn(key, PROVISION)

    def test_exact_go_pins_reach_install_update_and_session(self):
        keys = (
            "PLEBIAN_OS_KILIX_GO_VERSION",
            "PLEBIAN_OS_KILIX_GO_SHA256_AMD64",
            "PLEBIAN_OS_KILIX_GO_SHA256_ARM64",
        )
        for key in keys:
            self.assertIn(key, PROVISION)
            self.assertIn(key, UPDATE)
            self.assertIn(f"write_session_default {key}", PROVISION)
        self.assertIn('"GO_VERSION=$KILIX_GO_VERSION"', PROVISION)
        self.assertIn('"GO_SHA256=$sha"', PROVISION)


if __name__ == "__main__":
    unittest.main()
