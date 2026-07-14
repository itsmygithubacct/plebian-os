import hashlib
import json
import os
import re
import shutil
import stat
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "assets" / "desktop" / "plebian-os.png"
PROVISION = ROOT / "provision" / "plebian-os-provision.sh"
UPDATE = ROOT / "provision" / "plebian-os-update.sh"


class DesktopWallpaperTests(unittest.TestCase):
    def selected_state_dir(
        self, script_path: Path, provider: str, *, external_installed: bool
    ) -> str:
        script = r'''
set -euo pipefail
if [ "$SCRIPT_KIND" = provision ]; then
    export PLEBIAN_OS_PROVISION_LIB_ONLY=1
else
    export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1
fi
source "$SCRIPT_PATH"
KILIX_DESKTOP_PROVIDER="$PROVIDER"
KILIX_DESKTOP_DIR="$TEST_ROOT/pleb/data/desktop"
KILIX_DATA_HOME="$TEST_ROOT/kilix/data"
KILIX95_DATA_HOME="$TEST_ROOT/kilix-95/data"
KILIX95_DIR="$TEST_ROOT/sources/kilix-95"
selected_desktop_wallpaper_state_dir
'''
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            if external_installed:
                (root / "sources" / "kilix-95").mkdir(parents=True)
                (root / "sources" / "kilix-95" / "main.py").write_text("# installed\n")
            result = subprocess.run(
                ["bash", "-c", script], cwd=ROOT,
                env={
                    **os.environ,
                    "SCRIPT_PATH": str(script_path),
                    "SCRIPT_KIND": "provision" if script_path == PROVISION else "update",
                    "PROVIDER": provider,
                    "TEST_ROOT": str(root),
                    "HOME": str(root / "home"),
                    "PLEB_STATE_HOME": str(root / "state"),
                },
                text=True, capture_output=True, check=True,
            )
            return result.stdout.strip().replace(str(root), "$ROOT")

    def run_seed(self, desktop: Path, *, enabled: bool = True, dry_run: bool = False):
        script = r'''
set -euo pipefail
export PLEBIAN_OS_PROVISION_LIB_ONLY=1
source "$PROVISION"
TARGET_USER="$(id -un)"
TARGET_UID="$(id -u)"
TARGET_GID="$(id -g)"
USER_HOME="$TEST_HOME"
DESKTOP="$DESKTOP_ENABLED"
DRY_RUN="$TEST_DRY_RUN"
as_user() { "$@"; }
seed_desktop_wallpaper_state "$DESKTOP_DIR" "$WALLPAPER"
'''
        env = {
            **os.environ,
            "PROVISION": str(PROVISION),
            "TEST_HOME": str(desktop.parent.parent.parent),
            "DESKTOP_DIR": str(desktop),
            "WALLPAPER": "/usr/local/share/plebian-os/wallpapers/plebian-os.png",
            "DESKTOP_ENABLED": "1" if enabled else "0",
            "TEST_DRY_RUN": "1" if dry_run else "0",
        }
        return subprocess.run(
            ["bash", "-c", script],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )

    def run_install_dry(
        self,
        self_dir: Path,
        *,
        home: Path | None = None,
        os_dir: Path | None = None,
        repo: str = "https://github.com/itsmygithubacct/plebian-os.git",
        os_ref: str = "",
        check: bool = True,
    ):
        script = r'''
set -euo pipefail
export PLEBIAN_OS_PROVISION_LIB_ONLY=1
source "$PROVISION"
SELF_DIR="$TEST_SELF_DIR"
TARGET_USER="$(id -un)"
TARGET_UID="$(id -u)"
TARGET_GID="$(id -g)"
USER_HOME="$TEST_HOME"
PLEBIAN_OS_DIR="$TEST_OS_DIR"
PLEBIAN_OS_REPO="$TEST_OS_REPO"
PLEBIAN_OS_REF="$TEST_OS_REF"
DRY_RUN=1
install_desktop_wallpaper
'''
        return subprocess.run(
            ["bash", "-c", script],
            cwd=ROOT,
            env={
                **os.environ,
                "PROVISION": str(PROVISION),
                "TEST_SELF_DIR": str(self_dir),
                "TEST_HOME": str(home or Path.home()),
                "TEST_OS_DIR": str(os_dir or ""),
                "TEST_OS_REPO": repo,
                "TEST_OS_REF": os_ref,
            },
            text=True,
            capture_output=True,
            check=check,
        )

    def run_update_state_seed(self, desktop: Path):
        script = r'''
set -euo pipefail
export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1
source "$UPDATE"
seed_desktop_wallpaper_state_if_absent "$DESKTOP_DIR" "$WALLPAPER"
'''
        return subprocess.run(
            ["bash", "-c", script],
            cwd=ROOT,
            env={
                **os.environ,
                "UPDATE": str(UPDATE),
                "HOME": str(desktop.parent),
                "PLEB_STATE_HOME": str(desktop.parent / "state"),
                "DESKTOP_DIR": str(desktop),
                "WALLPAPER": "/usr/local/share/plebian-os/wallpapers/plebian-os.png",
            },
            text=True,
            capture_output=True,
            check=True,
        )

    def test_tracked_wallpaper_contract(self):
        data = ASSET.read_bytes()
        self.assertEqual(
            hashlib.sha256(data).hexdigest(),
            "60f63c37f054f7ffd061b47e09a3c22fbf595eec6f161c13e95344ca1a724778",
        )
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(data[12:16], b"IHDR")
        self.assertEqual(
            struct.unpack(">IIBBBBB", data[16:29]),
            (1920, 1080, 8, 2, 0, 0, 0),
        )

    def test_in_repo_dry_run_validates_without_installing(self):
        result = self.run_install_dry(ROOT / "provision")
        self.assertIn("atomic replace", result.stdout)

    def test_wallpaper_source_copy_is_unprivileged_bounded_and_private(self):
        script = r'''
set -euo pipefail
export PLEBIAN_OS_PROVISION_LIB_ONLY=1
source "$PROVISION"
TARGET_USER="$(id -un)"
TARGET_UID="$(id -u)"
TARGET_GID="$(id -g)"
DESKTOP_WALLPAPER_MAX_BYTES=16
small="$TEST_ROOT/small"
large="$TEST_ROOT/large"
small_copy="$TEST_ROOT/small.copy"
large_copy="$TEST_ROOT/large.copy"
printf 'safe-wallpaper' >"$small"
printf '12345678901234567' >"$large"
: >"$small_copy"
: >"$large_copy"
chmod 0600 "$small_copy" "$large_copy"
copy_wallpaper_as_target_bounded "$small" "$small_copy"
cmp "$small" "$small_copy"
if copy_wallpaper_as_target_bounded "$large" "$large_copy"; then
    exit 9
fi
[ "$(stat -c '%s' "$large_copy")" -le "$DESKTOP_WALLPAPER_MAX_BYTES" ]
'''
        with tempfile.TemporaryDirectory() as td:
            result = subprocess.run(
                ["bash", "-c", script],
                cwd=ROOT,
                env={
                    **os.environ,
                    "PROVISION": str(PROVISION),
                    "TEST_ROOT": td,
                },
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

        provision = PROVISION.read_text()
        copy_function = provision[
            provision.index("copy_wallpaper_as_target_bounded()"):
            provision.index("\ninstall_desktop_wallpaper()")
        ]
        self.assertIn("as_target_readonly timeout 30s python3", copy_function)
        self.assertIn("limit + 1 - total", copy_function)
        install = provision[
            provision.index("install_desktop_wallpaper()"):
            provision.index("\nseed_desktop_wallpaper_state()")
        ]
        selection = install[:install.index(
            'log "installing Plebian-OS desktop wallpaper'
        )]
        self.assertNotIn('validate_desktop_wallpaper "$source"', selection)
        real_copy = install.index(
            'copy_wallpaper_as_target_bounded "$source" "$tmp"',
            install.index('if [ "$source" != "$DESKTOP_WALLPAPER_DST" ]'),
        )
        private_mode = install.rfind('chmod 0600 "$tmp"', 0, real_copy)
        private_validation = install.index(
            'validate_desktop_wallpaper "$tmp"', real_copy
        )
        published_mode = install.index('chmod 0644 "$tmp"', private_validation)
        self.assertLess(private_mode, real_copy)
        self.assertLess(real_copy, private_validation)
        self.assertLess(private_validation, published_mode)

    def test_incomplete_checkout_fails_closed_instead_of_reusing_installed_asset(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "provision").mkdir()
            (root / "VERSION").write_text("0.1.1\n")
            result = self.run_install_dry(root / "provision", check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("tracked desktop wallpaper missing or unsafe", result.stderr)

    def test_deployed_provisioner_migrates_only_from_clean_owned_checkout(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            home = root / "home"
            checkout = home / "plebian-os"
            asset = checkout / "assets" / "desktop" / "plebian-os.png"
            deployed = root / "deployed"
            asset.parent.mkdir(parents=True)
            deployed.mkdir()
            shutil.copyfile(ASSET, asset)
            (checkout / "VERSION").write_text("0.1.1\n")
            subprocess.run(["git", "init", "-q", "-b", "main", checkout], check=True)
            subprocess.run(["git", "-C", checkout, "config", "user.name", "test"], check=True)
            subprocess.run(
                ["git", "-C", checkout, "config", "user.email", "test@example.invalid"],
                check=True,
            )
            repo = "https://example.invalid/plebian-os.git"
            subprocess.run(["git", "-C", checkout, "remote", "add", "origin", repo], check=True)
            subprocess.run(["git", "-C", checkout, "add", "VERSION", "assets"], check=True)
            subprocess.run(["git", "-C", checkout, "commit", "-q", "-m", "asset"], check=True)

            result = self.run_install_dry(
                deployed, home=home, os_dir=checkout, repo=repo
            )
            self.assertIn(str(asset), result.stdout)
            self.assertIn("atomic replace", result.stdout)

            # checkout_pinned_ref fetches a release tag into FETCH_HEAD and
            # detaches at its commit without creating a local tag ref.
            pinned = "v0.2.0"
            head = subprocess.check_output(
                ["git", "-C", checkout, "rev-parse", "HEAD"], text=True
            ).strip()
            (checkout / ".git" / "FETCH_HEAD").write_text(
                f"{head}\t\ttag '{pinned}' of {repo}\n"
            )
            tagged = self.run_install_dry(
                deployed, home=home, os_dir=checkout, repo=repo, os_ref=pinned
            )
            self.assertIn("atomic replace", tagged.stdout)

            (checkout / "VERSION").write_text("dirty\n")
            refused = self.run_install_dry(
                deployed, home=home, os_dir=checkout, repo=repo, check=False
            )
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("local changes", refused.stderr)

    def test_new_desktop_gets_user_owned_compatible_state(self):
        with tempfile.TemporaryDirectory() as td:
            desktop = Path(td) / "home" / ".local" / "share" / "kilix" / "desktop"
            self.run_seed(desktop)
            state_path = desktop / ".state.json"
            self.assertEqual(
                json.loads(state_path.read_text()),
                {
                    "wall_image": "/usr/local/share/plebian-os/wallpapers/plebian-os.png",
                    "wall_mode": "stretch",
                    "wall_custom": True,
                },
            )
            self.assertEqual(stat.S_IMODE(state_path.stat().st_mode), 0o600)
            self.assertEqual(state_path.stat().st_uid, os.getuid())

    def test_pleb_session_wallpaper_state_is_provider_independent(self):
        for script in (PROVISION, UPDATE):
            with self.subTest(script=script.name, provider="external"):
                self.assertEqual(
                    self.selected_state_dir(
                        script, "external", external_installed=True),
                    "$ROOT/pleb/data/desktop",
                )
            with self.subTest(script=script.name, provider="builtin"):
                self.assertEqual(
                    self.selected_state_dir(
                        script, "builtin", external_installed=True),
                    "$ROOT/pleb/data/desktop",
                )
            with self.subTest(script=script.name, provider="auto-external"):
                self.assertEqual(
                    self.selected_state_dir(
                        script, "auto", external_installed=True),
                    "$ROOT/pleb/data/desktop",
                )
            with self.subTest(script=script.name, provider="auto-builtin"):
                self.assertEqual(
                    self.selected_state_dir(
                        script, "auto", external_installed=False),
                    "$ROOT/pleb/data/desktop",
                )

    def test_reprovision_preserves_existing_wallpaper_choice_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as td:
            desktop = Path(td) / "desktop"
            desktop.mkdir()
            state_path = desktop / ".state.json"
            original = b'{"wall_image":"/home/me/my-wall.png","wall_mode":"tile"}\n'
            state_path.write_bytes(original)
            state_path.chmod(0o640)
            self.run_seed(desktop)
            self.assertEqual(state_path.read_bytes(), original)
            self.assertEqual(stat.S_IMODE(state_path.stat().st_mode), 0o640)

    def test_symlink_state_is_treated_as_existing_and_never_followed(self):
        with tempfile.TemporaryDirectory() as td:
            desktop = Path(td) / "desktop"
            desktop.mkdir()
            target = Path(td) / "chosen.json"
            target.write_text('{"wall_image":"custom"}\n')
            (desktop / ".state.json").symlink_to(target)
            self.run_seed(desktop)
            self.assertEqual(target.read_text(), '{"wall_image":"custom"}\n')

    def test_no_desktop_and_dry_run_do_not_create_state(self):
        with tempfile.TemporaryDirectory() as td:
            desktop = Path(td) / "desktop"
            self.run_seed(desktop, enabled=False)
            self.assertFalse((desktop / ".state.json").exists())
            result = self.run_seed(desktop, dry_run=True)
            self.assertIn("only if it still does not exist", result.stdout)
            self.assertFalse((desktop / ".state.json").exists())

    def test_new_updater_seeds_only_absent_state_after_migration(self):
        with tempfile.TemporaryDirectory() as td:
            desktop = Path(td) / "desktop"
            self.run_update_state_seed(desktop)
            state = desktop / ".state.json"
            self.assertEqual(
                json.loads(state.read_text()),
                {
                    "wall_image": "/usr/local/share/plebian-os/wallpapers/plebian-os.png",
                    "wall_mode": "stretch",
                    "wall_custom": True,
                },
            )
            self.assertEqual(stat.S_IMODE(state.stat().st_mode), 0o600)
            self.assertEqual(state.stat().st_uid, os.getuid())

    def test_new_updater_preserves_existing_and_symlink_state(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            desktop = root / "desktop"
            desktop.mkdir()
            state = desktop / ".state.json"
            original = b'{"wall_image":"/home/me/custom.png"}\n'
            state.write_bytes(original)
            state.chmod(0o640)
            self.run_update_state_seed(desktop)
            self.assertEqual(state.read_bytes(), original)
            self.assertEqual(stat.S_IMODE(state.stat().st_mode), 0o640)

            state.unlink()
            target = root / "chosen.json"
            target.write_bytes(original)
            state.symlink_to(target)
            self.run_update_state_seed(desktop)
            self.assertEqual(target.read_bytes(), original)

    def test_update_seeds_after_commit_and_tracks_created_directories(self):
        update = UPDATE.read_text()
        provision = PROVISION.read_text()
        commit = update.rindex("\ncommit_stack_transaction\n")
        seed = update.index("seed_desktop_wallpaper_after_commit", commit)
        success = update.rindex('\nlog "Plebian-OS stack updated."')
        self.assertLess(commit, seed)
        self.assertLess(seed, success)
        for marker in (
            'created_dirs+=("$dir")',
            'rmdir -- "${created_dirs[$i]}"',
            'dir.$i.present',
            'rmdir -- "$dir"',
        ):
            self.assertIn(marker, update)
        directory_section = update[
            update.index("# Distribution assets live below"):update.index(
                "# Root-stage every file", update.index("# Distribution assets live below")
            )
        ]
        self.assertIn('elif [ ! -e "$dir" ]', directory_section)
        self.assertNotIn('install -d -o root -g root -m 0755 -- "$dir"\n    owner=', directory_section)
        root_deploy = update[
            update.index("set -euo pipefail", update.index("<<'ROOT_DEPLOY'")):
            update.index("\nROOT_DEPLOY", update.index("<<'ROOT_DEPLOY'"))
        ]
        self.assertNotIn("exit 1", root_deploy)
        self.assertGreaterEqual(
            update.count("for dir in / /usr /usr/local /usr/local/share; do"), 3
        )
        self.assertIn("for path in / /usr /usr/local /usr/local/share; do", provision)
        self.assertIn("(8#$mode & 8#1) != 0", provision)
        self.assertIn("(8#$mode & 8#1) == 0", update)

    def test_privileged_deploy_opens_bounded_sources_and_publishes_after_validation(self):
        update = UPDATE.read_text()
        root_deploy = update[
            update.index("set -euo pipefail", update.index("<<'ROOT_DEPLOY'")):
            update.index("\nROOT_DEPLOY", update.index("<<'ROOT_DEPLOY'"))
        ]
        for marker in (
            'caller_uid="${SUDO_UID:-0}"',
            '[ "$(stat -c \'%u\' "$stage")" = "$caller_uid" ]',
            '[ "$(stat -c \'%a\' "$stage")" = 700 ]',
            "os.O_NOFOLLOW",
            "os.O_NONBLOCK",
            "stat.S_ISREG",
            "source_stat.st_uid != caller_uid",
            "source_stat.st_mode & 0o022",
            "source_stat.st_size > limit",
            "os.fchown(destination_fd, 0, 0)",
            "os.fchmod(destination_fd, 0o600)",
            'max_sizes=(33554432',
            '[ "$(stat -c \'%g\' "${new_paths[$i]}")" = 0 ]',
        ):
            self.assertIn(marker, update)
        self.assertNotIn(
            'install -m "${modes[$i]}" -- "$stage/${names[$i]}"', root_deploy
        )
        copy = root_deploy.index("source_fd = os.open(source, read_flags)")
        private = root_deploy.index("os.fchmod(destination_fd, 0o600)", copy)
        exact_hash = root_deploy.index(
            'actual="$(sha256sum "${new_paths[$i]}"', private
        )
        type_validation = root_deploy.index(
            'python3 - "${new_paths[7]}"', exact_hash
        )
        publish = root_deploy.index(
            'chmod "${modes[$i]}" -- "${new_paths[$i]}"', type_validation
        )
        rename = root_deploy.index(
            'mv -fT -- "${new_paths[$i]}" "${dests[$i]}"', publish
        )
        self.assertLess(copy, private)
        self.assertLess(private, exact_hash)
        self.assertLess(exact_hash, type_validation)
        self.assertLess(type_validation, publish)
        self.assertLess(publish, rename)

    def test_running_updater_uses_newly_deployed_artwork_hash(self):
        script = r'''
set -euo pipefail
export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1
source "$UPDATE"
running_hash="$(printf old | sha256sum | awk '{print $1}')"
deployed_hash="$(sha256sum "$ASSET" | awk '{print $1}')"
DESKTOP_WALLPAPER_SHA256="$running_hash"
_DEPLOYED_DESKTOP_WALLPAPER_SHA256="$deployed_hash"
desktop_wallpaper_matches_expected_hash \
    "$ASSET" "$_DEPLOYED_DESKTOP_WALLPAPER_SHA256"
[ "$DESKTOP_WALLPAPER_SHA256" != "$_DEPLOYED_DESKTOP_WALLPAPER_SHA256" ]
'''
        with tempfile.TemporaryDirectory() as td:
            result = subprocess.run(
                ["bash", "-c", script],
                cwd=ROOT,
                env={
                    **os.environ,
                    "UPDATE": str(UPDATE),
                    "ASSET": str(ASSET),
                    "HOME": td,
                    "PLEB_STATE_HOME": str(Path(td) / "state"),
                },
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
        update = UPDATE.read_text()
        self.assertIn(
            '_DEPLOYED_DESKTOP_WALLPAPER_SHA256="${stage_hashes[7]}"', update
        )

    def test_iso_and_update_paths_carry_the_same_stable_asset(self):
        remaster = (ROOT / "build" / "remaster-iso.sh").read_text()
        preseed = (ROOT / "preseed" / "preseed.cfg").read_text()
        update = (ROOT / "provision" / "plebian-os-update.sh").read_text()
        destination = "/usr/local/share/plebian-os/wallpapers/plebian-os.png"

        self.assertIn('assets/desktop/plebian-os.png', remaster)
        self.assertIn("PLEBIAN_OS_DESKTOP_WALLPAPER_SHA256", remaster)
        self.assertIn("desktop-wallpaper.png", remaster)
        self.assertIn(destination, preseed)
        self.assertIn('assets/desktop/plebian-os.png', update)
        self.assertIn("desktop-wallpaper.png", update)
        self.assertIn('wallpaper_actual" = "$wallpaper_expected', update)
        self.assertIn('wallpaper_actual" = "$wallpaper_update_expected', update)
        self.assertGreaterEqual(update.count(destination), 3)
        self.assertIn('[ "${#expected_hashes[@]}" -eq 10 ]', update)
        for source, installed in (
            (
                "assets/installer/ATTRIBUTION.md",
                "/usr/local/share/doc/plebian-os/installer/ATTRIBUTION.md",
            ),
            (
                "assets/COPYING.GPL-2",
                "/usr/local/share/doc/plebian-os/COPYING.GPL-2",
            ),
        ):
            self.assertIn(source, update)
            self.assertGreaterEqual(update.count(installed), 3)

    def test_notice_deploy_arrays_and_outer_rollback_stay_aligned(self):
        update = UPDATE.read_text()
        root_deploy = update[
            update.index("set -euo pipefail", update.index("<<'ROOT_DEPLOY'")):
            update.index("\nROOT_DEPLOY", update.index("<<'ROOT_DEPLOY'"))
        ]
        for assertion in (
            '[ "${#expected_hashes[@]}" -eq "${#names[@]}" ]',
            '[ "${#dests[@]}" -eq "${#names[@]}" ]',
            '[ "${#modes[@]}" -eq "${#names[@]}" ]',
            '[ "${#max_sizes[@]}" -eq "${#names[@]}" ]',
        ):
            self.assertIn(assertion, root_deploy)
        for marker in (
            "ATTRIBUTION.md",
            "COPYING.GPL-2",
            "modes=(0755 0755 0755 0755 0644 0755 0644 0644 0644 0644)",
            "1048576 1048576)",
            'python3 - "${new_paths[8]}" "${new_paths[9]}"',
        ):
            self.assertIn(marker, root_deploy)

        snapshot = update[
            update.index("<<'ROOT_SNAPSHOT'"):update.index("\nROOT_SNAPSHOT")
        ]
        restore = update[
            update.index("<<'ROOT_RESTORE'"):update.index("\nROOT_RESTORE")
        ]
        for array_name in ("paths", "managed_dirs"):
            pattern = rf"{array_name}=\(\n(.*?)\n\)"
            snapshot_array = re.search(pattern, snapshot, re.S)
            restore_array = re.search(pattern, restore, re.S)
            self.assertIsNotNone(snapshot_array)
            self.assertIsNotNone(restore_array)
            self.assertEqual(snapshot_array.group(1), restore_array.group(1))
        for directory in (
            "/usr/local/share/doc",
            "/usr/local/share/doc/plebian-os",
            "/usr/local/share/doc/plebian-os/installer",
            "/usr/local/share/doc/pleb",
        ):
            self.assertIn(directory, snapshot)
            self.assertIn(directory, restore)

    def test_v011_migration_contract_is_explicit(self):
        readme = (ROOT / "README.md").read_text()
        asset_docs = (ROOT / "assets" / "desktop" / "README.md").read_text()
        for text in (readme, asset_docs):
            normalized = " ".join(text.split())
            self.assertIn("immutable v0.1.1 updater", normalized)
            self.assertIn("seven-file", normalized)
            self.assertIn("second", normalized)
            self.assertIn("ten-file", normalized)
            self.assertIn("bare `sudo plebian-os-provision`", normalized)


if __name__ == "__main__":
    unittest.main()
