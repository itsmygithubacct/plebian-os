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
import os
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
TARGET_UID=0
if [ -n "${DEST:-}" ]; then
    PLEBIAN_OS_WAYDROID_HELPER_DEST="$DEST"
fi
if [ -n "${FIXED_ROOT:-}" ]; then
    PLEBIAN_OS_WAYDROID_FIXED_ROOT="$FIXED_ROOT"
fi
if [ -n "${STAGE_PARENT:-}" ]; then
    PLEBIAN_OS_WAYDROID_STAGE_PARENT="$STAGE_PARENT"
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

# Lie about the real helper ancestors so a library-disabled run can reach the
# stage-parent and after-stage seams. Dry-run returns before it publishes.
HOST_STAT_LIE = r"""
stat() {
    local format="" path="" take_format=0 arg
    for arg in "$@"; do
        if [ "$take_format" = 1 ]; then
            format="$arg"
            take_format=0
            continue
        fi
        case "$arg" in
            -c) take_format=1 ;;
            --) ;;
            -*) ;;
            *) path="$arg" ;;
        esac
    done
    case "$path" in
        /|/usr|/usr/lib|/usr/lib/plebian-os|/usr/lib/plebian-os/waydroid)
            case "$format" in
                %u) printf '0\n' ;;
                %a) printf '755\n' ;;
                %u:%a) printf '0:755\n' ;;
                *) command stat "$@" ;;
            esac
            ;;
        *) command stat "$@" ;;
    esac
}
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
        self.stage_parent = self.tmp / "stages"
        self.stage_parent.mkdir()
        self.stage_parent.chmod(0o700)
        self.checkout = ROOT

    def run_root(self, body: str, *, checkout: Path | None = None,
                 dest: Path | None = None, install: str = "0",
                 dry_run: str = "0", closure_sha: str = "",
                 uname_machine: str = "",
                 production_path: bool = False,
                 fixed_root: str = "",
                 timeout: int = 180) -> subprocess.CompletedProcess[str]:
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
            "FIXED_ROOT": fixed_root,
            "STAGE_PARENT": str(self.stage_parent),
            "WANT_INSTALL_WAYDROID": install,
            "WANT_DRY_RUN": dry_run,
            "WANT_CLOSURE_SHA": closure_sha,
            "UNAME_MACHINE": uname_machine,
        }
        result = subprocess.run(
            [self.unshare, "-r", "bash", "-c", PRELUDE + body],
            text=True, capture_output=True, check=False, env=env, timeout=timeout,
        )
        leftovers = sorted(path.name for path in self.stage_parent.iterdir())
        self.assertEqual(leftovers, [], result.stdout + result.stderr)
        return result

    def copy_checkout(self) -> Path:
        checkout = self.tmp / "checkout"
        provision = checkout / "provision"
        provision.mkdir(parents=True)
        for name in HELPERS:
            shutil.copy2(ROOT / "provision" / name, provision / name)
        return checkout

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
        self.assertEqual(staging.count("mv -fT --"), 3)
        self.assertNotIn('install -o root -g root -m 0644 -- "$closure"', staging)
        copy = shell_function(source, "waydroid_copy_owned_source")
        self.assertIn("os.O_NOFOLLOW", copy)
        self.assertIn("os.O_NONBLOCK", copy)
        self.assertIn("install_dir=/usr/lib/plebian-os/waydroid", staging)
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

    def test_packaged_first_boot_verifies_installed_helpers_without_a_checkout(self):
        result = self.run_root(r"""
mkdir -m 755 "$DEST"
install -m 755 "$CHECKOUT/provision/plebian-os-waydroid-setup" "$DEST/"
install -m 644 "$CHECKOUT/provision/"waydroid-closure.{env,sha256} "$DEST/"
SSH_SERVER_HELPER="$WORK/plebian-os-ssh-server"
install -m 755 "$CHECKOUT/provision/plebian-os-ssh-server" "$SSH_SERVER_HELPER"
PLEBIAN_OS_DIR="$WORK/absent"
packages_provide_pleb_and_kilix() { return 0; }
before=$(stat -c '%i:%Z' "$SSH_SERVER_HELPER" "$DEST"/*)
install_ssh_server_helper
stage_waydroid_first_use_helper
[ "$before" = "$(stat -c '%i:%Z' "$SSH_SERVER_HELPER" "$DEST"/*)" ]
[ ! -e "$PLEBIAN_OS_DIR" ]
echo changed >> "$DEST/waydroid-closure.env"
if (stage_waydroid_first_use_helper); then exit 1; fi
chmod 777 "$SSH_SERVER_HELPER"
if (install_ssh_server_helper); then exit 1; fi
""")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Waydroid closure checksum mismatch", result.stderr)
        self.assertIn("packaged SSH server helper is missing or unsafe", result.stderr)

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
        self.assertIn("Waydroid closure file is a symlink", result.stderr)
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

    def test_override_is_ignored_unless_the_library_is_sourced(self):
        marker = self.tmp / "hooked"
        result = self.run_root(r"""
ignored_hook() { printf 'hooked\n' > "$WORK/hooked"; }
PLEBIAN_OS_PROVISION_LIB_ONLY=0
PLEBIAN_OS_WAYDROID_FIXED_ROOT="$WORK/fake-root"
PLEBIAN_OS_WAYDROID_TEST_AFTER_STAGE=ignored_hook
stage_waydroid_first_use_helper
printf 'staged\n'
""")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsafe Waydroid first-use ancestor", result.stderr)
        self.assertNotIn("staged", result.stdout)
        self.assertFalse(marker.exists())
        self.assertFalse(self.dest.exists())

    def test_canonical_override_cannot_name_the_real_helper_directory(self):
        host = Path("/usr/lib/plebian-os/waydroid")
        before = host.stat().st_mtime_ns if host.exists() else None
        names_before = sorted(path.name for path in host.iterdir()) if host.is_dir() else None
        spellings = (
            "/usr/lib/plebian-os/waydroid",
            "/usr/lib/plebian-os/waydroid/",
            "/usr//lib/plebian-os/waydroid",
            "/usr/lib/./plebian-os/waydroid",
            "/usr/lib/plebian-os/waydroid/.",
            "/tmp/../usr/lib/plebian-os/waydroid",
        )
        for spelling in spellings:
            with self.subTest(spelling=spelling):
                result = self.run_root(
                    "stage_waydroid_first_use_helper\n",
                    dest=Path(spelling),
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(
                    "cannot replace a fixed system path",
                    result.stderr,
                )
                self.assertFalse(self.dest.exists())
        nested = self.run_root(
            "stage_waydroid_first_use_helper\n",
            dest=Path("/usr/lib/plebian-os/waydroid/extra"),
        )
        self.assertNotEqual(nested.returncode, 0)
        self.assertIn("is under /usr/lib/plebian-os", nested.stderr)
        self.assertFalse((host / "extra").exists())
        if before is None:
            self.assertFalse(host.exists())
        else:
            self.assertEqual(host.stat().st_mtime_ns, before)
            self.assertEqual(sorted(path.name for path in host.iterdir()), names_before)

    def test_directory_that_other_users_cannot_traverse_is_refused(self):
        self.dest.mkdir()
        self.dest.chmod(0o750)
        result = self.run_root("stage_waydroid_first_use_helper\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsafe Waydroid first-use directory", result.stderr)
        self.assertEqual(list(self.dest.iterdir()), [])

    def test_group_writable_fixed_parent_is_refused(self):
        fake = self.tmp / "fake-root"
        parent = fake / "usr" / "lib" / "plebian-os"
        parent.mkdir(parents=True)
        for directory in (fake, fake / "usr", fake / "usr" / "lib"):
            directory.chmod(0o755)
        parent.chmod(0o775)
        result = self.run_root(
            "stage_waydroid_first_use_helper\n",
            production_path=True,
            fixed_root=str(fake),
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("unsafe Waydroid first-use parent", result.stderr)
        self.assertFalse((parent / "waydroid").exists())

        host = Path("/usr/lib/plebian-os/waydroid")
        before = host.stat().st_mtime_ns
        names_before = sorted(path.name for path in host.iterdir())
        lied = self.run_root(r"""
stat() {
    local format="" path="" take_format=0 arg
    for arg in "$@"; do
        if [ "$take_format" = 1 ]; then
            format="$arg"
            take_format=0
            continue
        fi
        case "$arg" in
            -c) take_format=1 ;;
            --) ;;
            -*) ;;
            *) path="$arg" ;;
        esac
    done
    case "$path" in
        /|/usr|/usr/lib)
            case "$format" in
                %u) printf '0\n' ;;
                %a) printf '755\n' ;;
                *) command stat "$@" ;;
            esac
            ;;
        /usr/lib/plebian-os)
            case "$format" in
                %u) printf '0\n' ;;
                %a) printf '775\n' ;;
                *) command stat "$@" ;;
            esac
            ;;
        *) command stat "$@" ;;
    esac
}
stage_waydroid_first_use_helper
printf 'staged\n'
""", production_path=True)
        self.assertNotEqual(lied.returncode, 0, lied.stdout + lied.stderr)
        self.assertIn("unsafe Waydroid first-use parent: /usr/lib/plebian-os", lied.stderr)
        self.assertNotIn("staged", lied.stdout)
        self.assertEqual(host.stat().st_mtime_ns, before)
        self.assertEqual(sorted(path.name for path in host.iterdir()), names_before)

    def test_fixed_root_seam_publishes_under_the_fake_root(self):
        fake = self.tmp / "fake-root"
        parent = fake / "usr" / "lib" / "plebian-os"
        parent.mkdir(parents=True)
        for directory in (fake, fake / "usr", fake / "usr" / "lib", parent):
            directory.chmod(0o755)
        result = self.run_root(r"""
stage_waydroid_first_use_helper
install_dir="$FIXED_ROOT/usr/lib/plebian-os/waydroid"
printf 'setup %s\n' "$(stat -c '%u:%g:%a:%h' -- "$install_dir/plebian-os-waydroid-setup")"
printf 'closure %s\n' "$(stat -c '%u:%g:%a:%h' -- "$install_dir/waydroid-closure.env")"
printf 'pin %s\n' "$(stat -c '%u:%g:%a:%h' -- "$install_dir/waydroid-closure.sha256")"
[ "$(stat -c '%u:%g:%a:%h' -- "$install_dir/plebian-os-waydroid-setup")" = 0:0:755:1 ]
[ "$(stat -c '%u:%g:%a:%h' -- "$install_dir/waydroid-closure.env")" = 0:0:644:1 ]
""", production_path=True, fixed_root=str(fake))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        published = parent / "waydroid"
        self.assertEqual(sorted(path.name for path in published.iterdir()), sorted(HELPERS))
        for name in HELPERS:
            self.assertEqual(
                (published / name).read_bytes(),
                (ROOT / "provision" / name).read_bytes(),
                name,
            )
        self.assertFalse(self.dest.exists())

    def test_override_parent_and_non_directory_destination_are_refused(self):
        self.parent.chmod(0o777)
        result = self.run_root("stage_waydroid_first_use_helper\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsafe Waydroid first-use parent:", result.stderr)
        self.assertFalse(self.dest.exists())

        self.parent.chmod(0o755)
        self.dest.write_text("keep\n")
        result = self.run_root("stage_waydroid_first_use_helper\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not a directory", result.stderr)
        self.assertEqual(self.dest.read_text(), "keep\n")

    def test_non_regular_destination_members_are_refused_without_blocking(self):
        self.dest.mkdir()
        self.dest.chmod(0o755)
        member = self.dest / "plebian-os-waydroid-setup"
        member.mkdir()
        (member / "keep").write_text("keep\n")
        result = self.run_root("stage_waydroid_first_use_helper\n", timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not a regular file", result.stderr)
        self.assertEqual((member / "keep").read_text(), "keep\n")

        shutil.rmtree(self.dest)
        self.dest.mkdir()
        self.dest.chmod(0o755)
        fifo = self.dest / "waydroid-closure.env"
        os.mkfifo(fifo)
        result = self.run_root("stage_waydroid_first_use_helper\n", timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not a regular file", result.stderr)
        self.assertTrue(fifo.is_fifo())

    def test_source_must_be_executable_regular_and_not_group_writable(self):
        checkout = self.copy_checkout()
        setup = checkout / "provision" / "plebian-os-waydroid-setup"
        setup.chmod(0o644)
        result = self.run_root("stage_waydroid_first_use_helper\n", checkout=checkout)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not executable", result.stderr)
        self.assertFalse(self.dest.exists())

        setup.chmod(0o755)
        closure = checkout / "provision" / "waydroid-closure.env"
        closure.chmod(0o666)
        result = self.run_root("stage_waydroid_first_use_helper\n", checkout=checkout)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("group or world writable", result.stderr)
        self.assertFalse(self.dest.exists())

        closure.chmod(0o644)
        closure.unlink()
        os.mkfifo(closure)
        result = self.run_root(
            "stage_waydroid_first_use_helper\n",
            checkout=checkout,
            timeout=20,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Waydroid closure file is not a regular file", result.stderr)
        self.assertFalse(self.dest.exists())

    def test_swap_after_verification_publishes_the_staged_bytes(self):
        checkout = self.copy_checkout()
        original = (ROOT / "provision" / "waydroid-closure.env").read_bytes()
        secret = self.tmp / "secret"
        secret.write_bytes(b"not-the-closure\n")
        secret.chmod(0o600)
        swapped = self.run_root(r"""
swap_closure_for_secret() {
    ln -sfn "$WORK/secret" "$CHECKOUT/provision/waydroid-closure.env"
}
PLEBIAN_OS_WAYDROID_TEST_AFTER_STAGE=swap_closure_for_secret
stage_waydroid_first_use_helper
printf 'setup %s\n' "$(stat -c '%u:%g:%a:%h' -- "$DEST/plebian-os-waydroid-setup")"
printf 'closure %s\n' "$(stat -c '%u:%g:%a:%h' -- "$DEST/waydroid-closure.env")"
printf 'pin %s\n' "$(stat -c '%u:%g:%a:%h' -- "$DEST/waydroid-closure.sha256")"
""", checkout=checkout, timeout=20)
        self.assertEqual(swapped.returncode, 0, swapped.stdout + swapped.stderr)
        self.assertEqual((self.dest / "waydroid-closure.env").read_bytes(), original)
        self.assertNotIn(b"not-the-closure", (self.dest / "waydroid-closure.env").read_bytes())
        self.assertEqual(secret.read_bytes(), b"not-the-closure\n")
        self.assertEqual(sorted(path.name for path in self.dest.iterdir()), sorted(HELPERS))
        self.assertIn("0:0:644:1", swapped.stdout)

        shutil.rmtree(self.dest)
        closure = checkout / "provision" / "waydroid-closure.env"
        closure.unlink()
        shutil.copy2(ROOT / "provision" / "waydroid-closure.env", closure)
        fifo_swap = self.run_root(r"""
swap_closure_for_fifo() {
    rm -f -- "$CHECKOUT/provision/waydroid-closure.env"
    mkfifo -- "$CHECKOUT/provision/waydroid-closure.env"
}
PLEBIAN_OS_WAYDROID_TEST_AFTER_STAGE=swap_closure_for_fifo
stage_waydroid_first_use_helper
printf 'closure %s\n' "$(stat -c '%u:%g:%a:%h' -- "$DEST/waydroid-closure.env")"
""", checkout=checkout, timeout=20)
        self.assertEqual(fifo_swap.returncode, 0, fifo_swap.stdout + fifo_swap.stderr)
        self.assertEqual((self.dest / "waydroid-closure.env").read_bytes(), original)
        self.assertFalse((self.dest / "waydroid-closure.env").is_fifo())
        self.assertIn("0:0:644:1", fifo_swap.stdout)

    def _host_waydroid_snapshot(self):
        host = Path("/usr/lib/plebian-os/waydroid")
        snapshot = {}
        if host.is_dir():
            for path in host.iterdir():
                info = path.lstat()
                snapshot[path.name] = (info.st_mtime_ns, info.st_size, path.read_bytes())
        return snapshot

    def test_early_die_keeps_inherited_stage_and_temp_paths(self):
        victim_dir = self.tmp / "plebian-os-waydroid.abcDEF"
        victim_dir.mkdir()
        (victim_dir / "keep").write_text("stage\n")
        victim_file = self.tmp / "victim-temp"
        victim_extra = self.tmp / "victim-temp-extra"
        victim_file.write_text("temp\n")
        victim_extra.write_text("extra\n")
        result = subprocess.run(
            [
                "env", "-i",
                "PATH=/usr/bin:/bin",
                "KILIX_SOURCE_CARRIER_SESSION=1",
                f"WAYDROID_PRIVATE_STAGE={victim_dir}",
                f"WAYDROID_PUBLISH_TEMPS={victim_file}\n{victim_extra}",
                "bash", str(PROVISION), "--x",
            ],
            text=True, capture_output=True, check=False, timeout=60,
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("[plebian-os]", result.stderr)
        self.assertEqual((victim_dir / "keep").read_text(), "stage\n")
        self.assertEqual(victim_file.read_text(), "temp\n")
        self.assertEqual(victim_extra.read_text(), "extra\n")
        self.assertTrue(victim_dir.is_dir())
        self.assertFalse(victim_dir.is_symlink())

    def test_cleanup_releases_only_a_recorded_stage_and_temp(self):
        result = self.run_root(r"""
stage="$(mktemp -d "$STAGE_PARENT/plebian-os-waydroid.XXXXXX")"
chmod 0700 -- "$stage"
printf 'keep\n' > "$stage/keep"
dest="$WORK/publish"
mkdir -p -- "$dest"
chmod 755 -- "$dest"
temp="$dest/.plebian-os-waydroid-setup.plebian-os-new.$$"
printf 'temp\n' > "$temp"
victim="$WORK/victim-dir"
mkdir -p -- "$victim"
printf 'victim\n' > "$victim/keep"
other="$WORK/victim-temp"
printf 'other\n' > "$other"
WAYDROID_PRIVATE_STAGE="$stage"
WAYDROID_RECORDED_PRIVATE_STAGE="$stage"
WAYDROID_RECORDED_STAGE_PARENT="$STAGE_PARENT"
WAYDROID_PUBLISH_TEMPS="$temp"$'\n'"$other"
WAYDROID_RECORDED_PUBLISH_TEMPS="$temp"
WAYDROID_RECORDED_PUBLISH_DIR="$dest"
SUDOERS="$WORK/sudoers"
: > "$SUDOERS"
cleanup
[ ! -e "$stage" ]
[ ! -e "$temp" ]
[ "$(cat "$victim/keep")" = victim ]
[ "$(cat "$other")" = other ]
printf 'released\n'
""")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("released", result.stdout)
        self.assertEqual((self.tmp / "victim-dir" / "keep").read_text(), "victim\n")
        self.assertEqual((self.tmp / "victim-temp").read_text(), "other\n")

    def test_source_swapped_for_a_symlink_between_precheck_and_copy_is_refused(self):
        checkout = self.copy_checkout()
        original = (checkout / "provision" / "waydroid-closure.env").read_bytes()
        result = self.run_root(r"""
cp -a -- "$CHECKOUT/provision/waydroid-closure.env" "$WORK/closure-bytes"
chmod 644 -- "$WORK/closure-bytes"
mkdir -p "$WORK/bin"
cat > "$WORK/bin/python3" <<'EOF'
#!/bin/bash
if [ "${1-}" = - ] && [ "${2-}" = "$CHECKOUT/provision/waydroid-closure.env" ]; then
    ln -sfn -- "$WORK/closure-bytes" "$2"
fi
exec /usr/bin/python3 "$@"
EOF
chmod 755 "$WORK/bin/python3"
export PATH="$WORK/bin:$PATH"
stage_waydroid_first_use_helper
printf 'staged\n'
""", checkout=checkout, timeout=30)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Waydroid source is a symlink", result.stderr)
        self.assertNotIn("staged", result.stdout)
        self.assertFalse(self.dest.exists())
        self.assertTrue((checkout / "provision" / "waydroid-closure.env").is_symlink())
        self.assertEqual((self.tmp / "closure-bytes").read_bytes(), original)

    def test_source_swapped_for_a_fifo_between_precheck_and_copy_is_refused(self):
        checkout = self.copy_checkout()
        original = (checkout / "provision" / "waydroid-closure.env").read_bytes()
        result = self.run_root(r"""
cp -a -- "$CHECKOUT/provision/waydroid-closure.env" "$WORK/closure-bytes"
chmod 644 -- "$WORK/closure-bytes"
mkdir -p "$WORK/bin"
cat > "$WORK/bin/python3" <<'EOF'
#!/bin/bash
if [ "${1-}" = - ] && [ "${2-}" = "$CHECKOUT/provision/waydroid-closure.env" ]; then
    rm -f -- "$2"
    mkfifo -- "$2"
    cat -- "$WORK/closure-bytes" > "$2" &
fi
exec /usr/bin/python3 "$@"
EOF
chmod 755 "$WORK/bin/python3"
export PATH="$WORK/bin:$PATH"
stage_waydroid_first_use_helper
printf 'staged\n'
""", checkout=checkout, timeout=20)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Waydroid source is not a regular file", result.stderr)
        self.assertNotIn("staged", result.stdout)
        self.assertFalse(self.dest.exists())
        self.assertEqual((self.tmp / "closure-bytes").read_bytes(), original)

    def test_checkout_swapped_after_copy_is_not_what_gets_verified(self):
        checkout = self.copy_checkout()
        closure = (checkout / "provision" / "waydroid-closure.env").read_bytes()
        pin = (checkout / "provision" / "waydroid-closure.sha256").read_bytes()
        result = self.run_root(r"""
mkdir -p "$WORK/bin"
cat > "$WORK/bin/python3" <<'EOF'
#!/bin/bash
if [ "${1-}" = - ] && [ "${2-}" = "$CHECKOUT/provision/waydroid-closure.sha256" ]; then
    /usr/bin/python3 "$@"
    status=$?
    printf '%s\n' 'not-the-pin' > "$CHECKOUT/provision/waydroid-closure.sha256"
    printf '%s\n' 'not-the-closure' > "$CHECKOUT/provision/waydroid-closure.env"
    chmod 600 "$CHECKOUT/provision/waydroid-closure.sha256" \
        "$CHECKOUT/provision/waydroid-closure.env"
    exit "$status"
fi
exec /usr/bin/python3 "$@"
EOF
chmod 755 "$WORK/bin/python3"
export PATH="$WORK/bin:$PATH"
stage_waydroid_first_use_helper
printf 'setup %s\n' "$(stat -c '%u:%g:%a:%h' -- "$DEST/plebian-os-waydroid-setup")"
printf 'closure %s\n' "$(stat -c '%u:%g:%a:%h' -- "$DEST/waydroid-closure.env")"
printf 'pin %s\n' "$(stat -c '%u:%g:%a:%h' -- "$DEST/waydroid-closure.sha256")"
""", checkout=checkout, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.dest / "waydroid-closure.env").read_bytes(), closure)
        self.assertEqual((self.dest / "waydroid-closure.sha256").read_bytes(), pin)
        self.assertNotIn(b"not-the-closure", (self.dest / "waydroid-closure.env").read_bytes())
        self.assertEqual(
            (checkout / "provision" / "waydroid-closure.env").read_text(),
            "not-the-closure\n",
        )
        self.assertIn("0:0:644:1", result.stdout)
        self.assertIn("0:0:755:1", result.stdout)

    def test_copy_refuses_a_source_owned_by_someone_else(self):
        result = self.run_root(r"""
TARGET_UID=1
stage_waydroid_first_use_helper
printf 'staged\n'
""")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("not owned by the target user", result.stderr)
        self.assertNotIn("staged", result.stdout)
        self.assertFalse(self.dest.exists())

    def test_copy_refuses_a_source_over_its_size_limit(self):
        checkout = self.copy_checkout()
        pin = checkout / "provision" / "waydroid-closure.sha256"
        pin.write_bytes(b"a" * 4097)
        pin.chmod(0o644)
        result = self.run_root(
            "stage_waydroid_first_use_helper\nprintf 'staged\\n'\n",
            checkout=checkout,
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("exceeds its copy limit", result.stderr)
        self.assertNotIn("grew beyond its copy limit", result.stderr)
        self.assertNotIn("staged", result.stdout)
        self.assertFalse(self.dest.exists())

    def test_publish_failure_removes_recorded_temps(self):
        checkout = self.copy_checkout()
        self.dest.mkdir()
        self.dest.chmod(0o755)
        (self.dest / "keep").write_text("keep\n")
        result = self.run_root(r"""
cp -a -- "$CHECKOUT/provision/waydroid-closure.env" "$WORK/closure-bytes"
chmod 644 -- "$WORK/closure-bytes"
mkdir -p "$WORK/bin"
cat > "$WORK/bin/python3" <<'EOF'
#!/bin/bash
# Only the private stage is swapped. A publish that reads the checkout must
# not be turned into a symlink of the checkout itself.
if [ "${1-}" = - ] && [[ "${3-}" == *.waydroid-closure.env.plebian-os-new.* ]] \
        && [[ "${2-}" == *"/plebian-os-waydroid."*"/waydroid-closure.env" ]]; then
    ln -sfn -- "$WORK/closure-bytes" "$2"
fi
exec /usr/bin/python3 "$@"
EOF
chmod 755 "$WORK/bin/python3"
export PATH="$WORK/bin:$PATH"
stage_waydroid_first_use_helper
printf 'staged\n'
""", checkout=checkout, timeout=30)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Waydroid source is a symlink", result.stderr)
        self.assertNotIn("staged", result.stdout)
        self.assertEqual((self.dest / "keep").read_text(), "keep\n")
        names = sorted(path.name for path in self.dest.iterdir())
        self.assertEqual(names, ["keep"])

    def test_fixed_root_is_ignored_unless_the_library_is_sourced(self):
        fake = self.tmp / "fake-root"
        parent = fake / "usr" / "lib" / "plebian-os"
        parent.mkdir(parents=True)
        for directory in (fake, fake / "usr", fake / "usr" / "lib", parent):
            directory.chmod(0o755)
        before = self._host_waydroid_snapshot()
        result = self.run_root(r"""
export TMPDIR="$STAGE_PARENT"
PLEBIAN_OS_PROVISION_LIB_ONLY=0
PLEBIAN_OS_WAYDROID_FIXED_ROOT="$WORK/fake-root"
stage_waydroid_first_use_helper
printf 'staged\n'
""", production_path=True)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("unsafe Waydroid first-use ancestor: /", result.stderr)
        self.assertNotIn("staged", result.stdout)
        self.assertFalse((parent / "waydroid").exists())
        self.assertFalse(self.dest.exists())
        self.assertEqual(self._host_waydroid_snapshot(), before)

    def test_stage_parent_is_ignored_unless_the_library_is_sourced(self):
        bad = self.tmp / "bad-stages"
        bad.mkdir()
        bad.chmod(0o777)
        safe = self.tmp / "safe-stages"
        safe.mkdir()
        safe.chmod(0o700)
        before = self._host_waydroid_snapshot()
        result = self.run_root(
            HOST_STAT_LIE + r"""
export TMPDIR="$WORK/safe-stages"
PLEBIAN_OS_PROVISION_LIB_ONLY=0
PLEBIAN_OS_WAYDROID_STAGE_PARENT="$WORK/bad-stages"
stage_waydroid_first_use_helper
printf 'staged\n'
""",
            production_path=True,
            dry_run="1",
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("staged", result.stdout)
        self.assertEqual(list(bad.iterdir()), [])
        self.assertEqual(list(safe.iterdir()), [])
        self.assertFalse(self.dest.exists())
        self.assertEqual(self._host_waydroid_snapshot(), before)

    def test_after_stage_hook_is_ignored_unless_the_library_is_sourced(self):
        safe = self.tmp / "safe-stages"
        safe.mkdir()
        safe.chmod(0o700)
        marker = self.tmp / "hooked"
        before = self._host_waydroid_snapshot()
        result = self.run_root(
            HOST_STAT_LIE + r"""
ignored_hook() { printf 'hooked\n' > "$WORK/hooked"; }
export TMPDIR="$WORK/safe-stages"
PLEBIAN_OS_PROVISION_LIB_ONLY=0
PLEBIAN_OS_WAYDROID_TEST_AFTER_STAGE=ignored_hook
stage_waydroid_first_use_helper
printf 'staged\n'
""",
            production_path=True,
            dry_run="1",
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("staged", result.stdout)
        self.assertFalse(marker.exists())
        self.assertEqual(list(safe.iterdir()), [])
        self.assertFalse(self.dest.exists())
        self.assertEqual(self._host_waydroid_snapshot(), before)


if __name__ == "__main__":
    unittest.main()
