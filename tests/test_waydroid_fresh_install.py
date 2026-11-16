"""Fresh amd64 installs stage the Waydroid first-use helper.

0.2.3 leaves PLEBIAN_OS_INSTALL_WAYDROID=0, so provisioning must publish the
same root-owned helper the updater publishes, without installing the
application or Android. arm64 stays unstaged. The helper is inside the
provisioning root transaction, so a failed first boot rolls it back.

Behavioral cases run in a user namespace where the caller is uid 0. They write
only under a temporary directory.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROVISION = ROOT / "provision" / "plebian-os-provision.sh"
UPDATE = ROOT / "provision" / "plebian-os-update.sh"
HELPERS = (
    "plebian-os-waydroid-setup",
    "waydroid-closure.env",
    "waydroid-closure.sha256",
)
CLOSURE_SHA256 = hashlib.sha256(
    (ROOT / "provision" / "waydroid-closure.env").read_bytes()
).hexdigest()


def shell_function(source: str, name: str) -> str:
    start = source.index(f"\n{name}() {{\n") + 1
    return source[start:source.index("\n}\n", start) + 3]


PRELUDE = r"""
set -euo pipefail
export PLEBIAN_OS_PROVISION_LIB_ONLY=1
source "$PROVISION"
INSTALL_WAYDROID="$WANT_INSTALL_WAYDROID"
DRY_RUN="$WANT_DRY_RUN"
WAYDROID_CLOSURE_SHA256="$WANT_CLOSURE_SHA"
PLEBIAN_OS_DIR="$CHECKOUT"
if [ -n "${DEST:-}" ]; then
    PLEBIAN_OS_WAYDROID_HELPER_DEST="$DEST"
fi
if [ -n "${UNAME_MACHINE:-}" ]; then
    mkdir -p "$WORK/bin"
    cat > "$WORK/bin/uname" <<EOF
#!/bin/sh
if [ "\$1" = -m ]; then printf '%s\n' "$UNAME_MACHINE"; exit 0; fi
exec /usr/bin/uname "\$@"
EOF
    chmod 755 "$WORK/bin/uname"
    export PATH="$WORK/bin:$PATH"
fi
"""


class WaydroidFreshInstallTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.unshare = shutil.which("unshare")
        cls.unshare_ok = False
        if cls.unshare is None:
            return
        probe = subprocess.run(
            [cls.unshare, "-r", "true"],
            capture_output=True, check=False,
        )
        cls.unshare_ok = probe.returncode == 0

    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory(
            prefix="waydroid-fresh-")))
        self.parent = self.tmp / "parent"
        self.parent.mkdir()
        self.parent.chmod(0o755)
        self.dest = self.parent / "waydroid"
        self.checkout = ROOT

    def run_root(self, body: str, *, checkout: Path | None = None,
                 dest: Path | None = None, install: str = "0",
                 dry_run: str = "0", closure_sha: str = "",
                 uname_machine: str = "",
                 production_path: bool = False) -> subprocess.CompletedProcess[str]:
        if not self.unshare_ok:
            self.skipTest("unprivileged user namespaces are unavailable")
        if production_path:
            dest_value = ""
        elif dest is None:
            dest_value = str(self.dest)
        else:
            dest_value = str(dest)
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(self.tmp),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PROVISION": str(PROVISION),
            "UPDATE": str(UPDATE),
            "CHECKOUT": str(checkout or self.checkout),
            "WORK": str(self.tmp),
            "PARENT": str(self.parent),
            "DEST": dest_value,
            "WANT_INSTALL_WAYDROID": install,
            "WANT_DRY_RUN": dry_run,
            "WANT_CLOSURE_SHA": closure_sha,
            "UNAME_MACHINE": uname_machine,
        }
        return subprocess.run(
            [self.unshare, "-r", "bash", "-c", PRELUDE + body],
            text=True, capture_output=True, check=False, env=env, timeout=180,
        )

    def assert_published(self, result: subprocess.CompletedProcess[str]):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            sorted(path.name for path in self.dest.iterdir()),
            sorted(HELPERS),
        )
        for name in HELPERS:
            installed = self.dest / name
            source = self.checkout / "provision" / name
            self.assertFalse(installed.is_symlink(), name)
            self.assertEqual(installed.read_bytes(), source.read_bytes(), name)
            mode = stat.S_IMODE(installed.stat().st_mode)
            expect = 0o755 if name == HELPERS[0] else 0o644
            self.assertEqual(mode, expect, name)
            self.assertEqual(mode & 0o022, 0, name)
        directory_mode = stat.S_IMODE(self.dest.stat().st_mode)
        self.assertEqual(directory_mode, 0o755)
        self.assertEqual(directory_mode & 0o022, 0)
        self.assertIn("0:0:755:1", result.stdout)
        self.assertIn("0:0:644:1", result.stdout)

    def test_release_flag_still_means_the_application_stays_uninstalled(self):
        env = (ROOT / "releases" / "0.2.3.env").read_text(encoding="utf-8")
        self.assertIn("\nPLEBIAN_OS_INSTALL_WAYDROID=0\n", env)
        self.assertIn("\nPLEBIAN_OS_WAYDROID_CLOSURE_SHA256=\n", env)
        source = PROVISION.read_text(encoding="utf-8")
        application = shell_function(source, "install_waydroid_application")
        staging = shell_function(source, "stage_waydroid_first_use_helper")
        self.assertIn('[ "$INSTALL_WAYDROID" = 1 ] || return 0\n', application)
        self.assertNotIn("install_waydroid_application", staging)
        self.assertNotIn("apt-get", staging)
        self.assertNotIn("curl", staging)
        self.assertEqual(staging.count('"$setup" --dry-run'), 1)
        begun = source.index("\nbegin_provision_root_transaction\n")
        called = source.index("\nstage_waydroid_first_use_helper\n")
        committed = source.index("\ncommit_provision_root_transaction\n")
        defined = source.index("\nstage_waydroid_first_use_helper() {\n")
        library = source.index(
            'if [ "${PLEBIAN_OS_PROVISION_LIB_ONLY:-0}" = 1 ]; then\n'
            "    # shellcheck disable=SC2317  # exit is the direct-execution fallback\n"
            "    return 0 2>/dev/null || exit 0\n"
        )
        self.assertLess(defined, library)
        self.assertLess(library, begun)
        self.assertLess(begun, called)
        self.assertLess(called, committed)
        self.assertNotIn("\ninstall_waydroid_application\n", source[begun:])

    def test_fresh_amd64_install_stages_the_helper_when_the_flag_is_off(self):
        result = self.run_root(r"""
stage_waydroid_first_use_helper
printf 'setup %s\n' "$(stat -c '%u:%g:%a:%h' -- "$DEST/plebian-os-waydroid-setup")"
printf 'closure %s\n' "$(stat -c '%u:%g:%a:%h' -- "$DEST/waydroid-closure.env")"
printf 'pin %s\n' "$(stat -c '%u:%g:%a:%h' -- "$DEST/waydroid-closure.sha256")"
printf 'dir %s\n' "$(stat -c '%u:%g:%a' -- "$DEST")"
[ "$(stat -c '%u:%g:%a:%h' -- "$DEST/plebian-os-waydroid-setup")" = 0:0:755:1 ]
[ "$(stat -c '%u:%g:%a:%h' -- "$DEST/waydroid-closure.env")" = 0:0:644:1 ]
[ "$(stat -c '%u:%g:%a:%h' -- "$DEST/waydroid-closure.sha256")" = 0:0:644:1 ]
[ "$(stat -c '%u:%g:%a' -- "$DEST")" = 0:0:755 ]
""")
        self.assert_published(result)
        self.assertNotIn("download and verify", result.stdout)
        self.assertNotIn("kilix-waydroid", result.stdout)

    def test_second_stage_repairs_a_tampered_helper_and_changes_nothing_else(self):
        result = self.run_root(r"""
stage_waydroid_first_use_helper
printf 'tampered\n' > "$DEST/waydroid-closure.env"
chmod 0666 "$DEST/waydroid-closure.env"
stage_waydroid_first_use_helper
printf 'setup %s\n' "$(stat -c '%u:%g:%a:%h' -- "$DEST/plebian-os-waydroid-setup")"
printf 'closure %s\n' "$(stat -c '%u:%g:%a:%h' -- "$DEST/waydroid-closure.env")"
printf 'pin %s\n' "$(stat -c '%u:%g:%a:%h' -- "$DEST/waydroid-closure.sha256")"
[ "$(stat -c '%u:%g:%a:%h' -- "$DEST/waydroid-closure.env")" = 0:0:644:1 ]
""")
        self.assert_published(result)
        self.assertNotIn(b"tampered", (self.dest / "waydroid-closure.env").read_bytes())

    def test_published_bytes_and_modes_match_the_update_stage(self):
        result = self.run_root(r"""
stage_waydroid_first_use_helper
[ ! -e "$DEST/source.tar" ]
[ ! -e "$DEST/kilix-waydroid" ]
printf 'setup %s\n' "$(stat -c '%u:%g:%a:%h' -- "$DEST/plebian-os-waydroid-setup")"
printf 'closure %s\n' "$(stat -c '%u:%g:%a:%h' -- "$DEST/waydroid-closure.env")"
printf 'pin %s\n' "$(stat -c '%u:%g:%a:%h' -- "$DEST/waydroid-closure.sha256")"
""")
        self.assert_published(result)
        # The updater refuses the host session file when the caller is
        # namespace root. Staging runs as the invoking user, which is how
        # the native deployment tests call the same function.
        stage = self.tmp / "update-stage"
        stage.mkdir(mode=0o700)
        script = r"""
set -euo pipefail
export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1
source "$UPDATE"
PLEBIAN_OS_DIR="$CHECKOUT"
PLEBIAN_OS_VERSION="$(cat "$CHECKOUT/VERSION")"
PLEBIAN_OS_WAYDROID_CLOSURE_SHA256=
systemd-analyze() {
    [ "$#" = 2 ] && [ "$1" = verify ] && [ "$2" = "$STAGE/plebian-os-firstboot.service" ]
}
stage_and_validate_os_layer "$STAGE"
"""
        update = subprocess.run(
            ["/bin/bash", "-c", script],
            text=True, capture_output=True, check=False, timeout=60,
            env={
                "PATH": "/usr/bin:/bin",
                "HOME": str(self.tmp),
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "UPDATE": str(UPDATE),
                "CHECKOUT": str(self.checkout),
                "STAGE": str(stage),
            },
        )
        self.assertEqual(update.returncode, 0, update.stdout + update.stderr)
        for name in HELPERS:
            self.assertEqual((self.dest / name).read_bytes(), (stage / name).read_bytes(), name)
            self.assertEqual(
                stat.S_IMODE((self.dest / name).stat().st_mode),
                stat.S_IMODE((stage / name).stat().st_mode),
                name,
            )
        self.assertFalse((stage / "source.tar").exists())
        self.assertFalse((stage / "kilix-waydroid").exists())

    def test_dry_run_with_the_flag_off_does_not_write_or_preview_android(self):
        result = self.run_root(r"""
stage_waydroid_first_use_helper
[ ! -e "$DEST" ]
""", dry_run="1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("install root-owned first-use helper", result.stdout)
        self.assertNotIn("download and verify", result.stdout)
        self.assertFalse(self.dest.exists())

    def test_dry_run_with_the_flag_on_previews_android_without_writing(self):
        result = self.run_root(r"""
stage_waydroid_first_use_helper
[ ! -e "$DEST" ]
""", install="1", dry_run="1", closure_sha=CLOSURE_SHA256)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("download and verify", result.stdout)
        self.assertFalse(self.dest.exists())

    def test_other_architectures_stage_nothing(self):
        for machine in ("aarch64", "armv7l", "i686"):
            with self.subTest(machine=machine):
                result = self.run_root(r"""
stage_waydroid_first_use_helper
[ ! -e "$DEST" ]
printf 'unstaged\n'
""", uname_machine=machine)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("unstaged", result.stdout)
                self.assertFalse(self.dest.exists())

    def test_enabling_the_flag_on_another_architecture_is_still_refused(self):
        result = self.run_root(r"""
stage_waydroid_first_use_helper
printf 'staged\n'
""", install="1", uname_machine="aarch64")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("staged", result.stdout)
        self.assertIn("amd64-only Waydroid closure", result.stderr)
        self.assertIn("PLEBIAN_OS_INSTALL_WAYDROID=0", result.stderr)
        self.assertFalse(self.dest.exists())

    def test_a_mismatched_or_linked_closure_writes_nothing(self):
        checkout = self.tmp / "checkout"
        provision = checkout / "provision"
        provision.mkdir(parents=True)
        for name in HELPERS:
            shutil.copy2(ROOT / "provision" / name, provision / name)
        (provision / "waydroid-closure.env").write_text(
            (provision / "waydroid-closure.env").read_text(encoding="utf-8")
            + "# changed\n",
            encoding="utf-8",
        )
        result = self.run_root("stage_waydroid_first_use_helper\n", checkout=checkout)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("mismatched Waydroid closure", result.stderr)
        self.assertFalse(self.dest.exists())

        (provision / "waydroid-closure.env").write_bytes(
            (ROOT / "provision" / "waydroid-closure.env").read_bytes()
        )
        (provision / "waydroid-closure.sha256").write_text(CLOSURE_SHA256 + "\nextra\n")
        result = self.run_root("stage_waydroid_first_use_helper\n", checkout=checkout)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("trailing data", result.stderr)
        self.assertFalse(self.dest.exists())

        (provision / "waydroid-closure.sha256").write_bytes(
            (ROOT / "provision" / "waydroid-closure.sha256").read_bytes()
        )
        (provision / "waydroid-closure.env").unlink()
        (provision / "waydroid-closure.env").symlink_to(
            ROOT / "provision" / "waydroid-closure.env"
        )
        result = self.run_root("stage_waydroid_first_use_helper\n", checkout=checkout)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no Waydroid setup closure", result.stderr)
        self.assertFalse(self.dest.exists())

    def test_a_bad_release_hash_and_a_broken_helper_write_nothing(self):
        result = self.run_root(
            "stage_waydroid_first_use_helper\n",
            closure_sha="0" * 64,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("differs from the pinned checkout", result.stderr)
        self.assertFalse(self.dest.exists())

        checkout = self.tmp / "checkout"
        provision = checkout / "provision"
        provision.mkdir(parents=True)
        for name in HELPERS:
            shutil.copy2(ROOT / "provision" / name, provision / name)
        setup = provision / "plebian-os-waydroid-setup"
        setup.write_text(setup.read_text(encoding="utf-8") + "\nif\n", encoding="utf-8")
        setup.chmod(0o755)
        result = self.run_root("stage_waydroid_first_use_helper\n", checkout=checkout)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid Waydroid first-use helper", result.stderr)
        self.assertFalse(self.dest.exists())

    def test_unsafe_destination_is_not_followed_or_replaced(self):
        self.dest.mkdir()
        self.dest.chmod(0o777)
        (self.dest / "marker").write_text("keep\n")
        result = self.run_root("stage_waydroid_first_use_helper\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsafe Waydroid first-use directory", result.stderr)
        self.assertEqual((self.dest / "marker").read_text(), "keep\n")
        self.assertFalse((self.dest / HELPERS[0]).exists())

        shutil.rmtree(self.dest)
        real = self.parent / "real"
        real.mkdir()
        real.chmod(0o755)
        (real / "marker").write_text("keep\n")
        self.dest.symlink_to("real")
        result = self.run_root("stage_waydroid_first_use_helper\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("directory is a symlink", result.stderr)
        self.assertEqual((real / "marker").read_text(), "keep\n")
        self.assertFalse((real / HELPERS[0]).exists())

        self.dest.unlink()
        self.dest.mkdir()
        self.dest.chmod(0o755)
        marker = self.parent / "marker"
        marker.write_text("keep\n")
        (self.dest / "waydroid-closure.env").symlink_to(marker)
        result = self.run_root("stage_waydroid_first_use_helper\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("file is a symlink", result.stderr)
        self.assertEqual(marker.read_text(), "keep\n")
        self.assertFalse((self.dest / HELPERS[0]).exists())

    def test_namespace_root_does_not_publish_through_the_host_path(self):
        host = Path("/usr/lib/plebian-os/waydroid")
        before = host.stat().st_mtime_ns if host.exists() else None
        names_before = sorted(path.name for path in host.iterdir()) if host.is_dir() else None
        result = self.run_root("stage_waydroid_first_use_helper\n", production_path=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsafe Waydroid first-use ancestor", result.stderr)
        if before is None:
            self.assertFalse(host.exists())
        else:
            self.assertEqual(host.stat().st_mtime_ns, before)
            self.assertEqual(sorted(path.name for path in host.iterdir()), names_before)

    def _transaction(self, body: str) -> subprocess.CompletedProcess[str]:
        state = self.tmp / "state"
        state.mkdir(exist_ok=True)
        state.chmod(0o700)
        script = r"""
SUDOERS="$WORK/sudoers-absent"
TARGET_USER=
PROVISION_ROOT_TRANSACTION_BASE="$WORK/state"
PROVISION_ROOT_TRANSACTION_TRUSTED_DIRS=("$WORK")
PROVISION_ROOT_TRANSACTION_MANAGED_DIRS=("$PARENT" "$DEST")
PROVISION_ROOT_TRANSACTION_PATHS=(
    "$DEST/plebian-os-waydroid-setup"
    "$DEST/waydroid-closure.env"
    "$DEST/waydroid-closure.sha256"
)
begin_provision_root_transaction
""" + body
        env_dest = self.dest
        return self.run_root(script, dest=env_dest)

    def test_a_failed_first_boot_removes_a_new_helper_and_restores_an_old_one(self):
        fresh = self._transaction(r"""
stage_waydroid_first_use_helper
[ -f "$DEST/plebian-os-waydroid-setup" ]
exit 1
""")
        self.assertEqual(fresh.returncode, 1, fresh.stdout + fresh.stderr)
        self.assertFalse(self.dest.exists())
        self.assertEqual(list((self.tmp / "state").glob("provision-rollback.*")), [])

        self.dest.mkdir()
        self.dest.chmod(0o755)
        for name in HELPERS:
            path = self.dest / name
            path.write_text("previous " + name + "\n")
            path.chmod(0o640)
        restored = self._transaction(r"""
stage_waydroid_first_use_helper
[ "$(cat "$DEST/waydroid-closure.env")" != "previous waydroid-closure.env" ]
exit 1
""")
        self.assertEqual(restored.returncode, 1, restored.stdout + restored.stderr)
        for name in HELPERS:
            path = self.dest / name
            self.assertEqual(path.read_text(), "previous " + name + "\n")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)
        self.assertEqual(list((self.tmp / "state").glob("provision-rollback.*")), [])

    def test_a_committed_first_boot_keeps_the_helper(self):
        result = self._transaction(r"""
stage_waydroid_first_use_helper
commit_provision_root_transaction
printf 'setup %s\n' "$(stat -c '%u:%g:%a:%h' -- "$DEST/plebian-os-waydroid-setup")"
printf 'closure %s\n' "$(stat -c '%u:%g:%a:%h' -- "$DEST/waydroid-closure.env")"
printf 'pin %s\n' "$(stat -c '%u:%g:%a:%h' -- "$DEST/waydroid-closure.sha256")"
exit 0
""")
        self.assert_published(result)
        self.assertEqual(list((self.tmp / "state").glob("provision-rollback.*")), [])


if __name__ == "__main__":
    unittest.main()
