import json
import os
import pwd
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
# Permission-safety fixtures use conventional public directory modes even when
# the suite is launched from a Kilix shell with umask 077.
os.umask(0o022)
PROVISION = ROOT / "provision" / "plebian-os-provision.sh"
UPDATE = ROOT / "provision" / "plebian-os-update.sh"
DEPS = ROOT / "provision" / "install-deps.sh"


class ProvisionLifecycleBehaviorTests(unittest.TestCase):
    def _apt_tree(self, base: Path, apt_rc: int = 0):
        etc = base / "etc"
        sources = etc / "apt" / "sources.list.d"
        sources.mkdir(parents=True)
        (etc / "apt" / "apt.conf.d").mkdir()
        bindir = base / "bin"
        bindir.mkdir()
        apt = bindir / "apt-get"
        apt.write_text(f"#!/bin/sh\nexit {apt_rc}\n")
        apt.chmod(0o755)
        env = {
            **os.environ,
            "PATH": f"{bindir}:{os.environ['PATH']}",
            "PLEBIAN_OS_APT_ETC_ROOT": str(etc),
            "PLEBIAN_OS_PROVISION_LIB_ONLY": "1",
        }
        return etc, sources, env

    def _run_library(self, body: str, env: dict[str, str]):
        return subprocess.run(
            ["bash", "-c", f'. "{PROVISION}"\n{body}'],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    @staticmethod
    def _private_storage_layout(data: Path) -> dict[str, Path]:
        pleb = data / "pleb"
        kilix = data / "kilix"
        kilix95 = data / "kilix-95"
        plebian_os = data / "plebian-os"
        return {
            "GPU_TERMINAL_HOME": data,
            "PLEB_STORAGE_HOME": pleb,
            "KILIX_STORAGE_HOME": kilix,
            "KILIX95_STORAGE_HOME": kilix95,
            "PLEBIAN_OS_STORAGE_HOME": plebian_os,
            "PLEB_CONFIG_HOME": pleb / "config",
            "PLEB_STATE_HOME": pleb / "state",
            "PLEB_CACHE_HOME": pleb / "cache",
            "PLEB_SESSION_HOME": pleb / "session",
            "PLEB_DATA_HOME": pleb / "data",
            "KILIX_CONFIG_HOME": kilix / "config",
            "KILIX_STATE_DIRECTORY": kilix / "state",
            "KILIX_CACHE_HOME": kilix / "cache",
            "KILIX_SESSION_HOME": kilix / "session",
            "KILIX_BUILD_DIRECTORY": kilix / "build",
            "KILIX_DATA_HOME": kilix / "data",
            "KILIX_PREBUILT_HOME": kilix / "prebuilt" / "kitty.app",
            "KILIX95_CONFIG_HOME": kilix95 / "config",
            "KILIX95_STATE_HOME": kilix95 / "state",
            "KILIX95_CACHE_HOME": kilix95 / "cache",
            "KILIX95_SESSION_HOME": kilix95 / "session",
            "KILIX95_DATA_HOME": kilix95 / "data",
            "PLEBIAN_OS_SESSION_HOME": plebian_os / "session",
        }

    @staticmethod
    def _private_storage_assignments(layout: dict[str, Path]) -> str:
        return "".join(f"{key}={str(path)!r}\n" for key, path in layout.items())

    def test_snapshot_round_trip_preserves_operator_snapshot_source(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, sources, env = self._apt_tree(base)
            operator = sources / "operator.sources"
            content = "Types: deb\nURIs: https://snapshot.debian.org/operator-owned\n"
            operator.write_text(content)
            result = self._run_library(
                "PLEBIAN_OS_APT_SNAPSHOT=20260712T000000Z\n"
                "configure_apt_snapshot\n"
                "PLEBIAN_OS_APT_SNAPSHOT=\n"
                "configure_apt_snapshot\n",
                env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(operator.read_text(), content)
            self.assertFalse(Path(str(operator) + ".plebian-os-disabled").exists())
            self.assertFalse((etc / "plebian-os" / "apt-snapshot-sources").exists())
            self.assertFalse((sources / "plebian-os-snapshot.sources").exists())

    def test_snapshot_conflict_preflight_does_not_move_earlier_sources(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _etc, sources, env = self._apt_tree(base)
            first = sources / "a.list"
            conflict = sources / "z.sources"
            first.write_text("deb https://deb.example.invalid stable main\n")
            conflict.write_text("Types: deb\nURIs: https://other.invalid\n")
            Path(str(conflict) + ".plebian-os-disabled").write_text("saved\n")
            result = self._run_library(
                "PLEBIAN_OS_APT_SNAPSHOT=20260712T000000Z\nconfigure_apt_snapshot\n",
                env,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(first.exists())
            self.assertFalse(Path(str(first) + ".plebian-os-disabled").exists())
            self.assertTrue(conflict.exists())
            self.assertIn("both", result.stderr)

    def test_failed_snapshot_update_rolls_back_sources_and_inventory(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, sources, env = self._apt_tree(base, apt_rc=1)
            live = sources / "debian.sources"
            content = "Types: deb\nURIs: https://deb.debian.org/debian\n"
            live.write_text(content)
            result = self._run_library(
                "PLEBIAN_OS_APT_SNAPSHOT=20260712T000000Z\nconfigure_apt_snapshot\n",
                env,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(live.read_text(), content)
            self.assertFalse(Path(str(live) + ".plebian-os-disabled").exists())
            self.assertFalse((etc / "plebian-os" / "apt-snapshot-sources").exists())
            self.assertFalse((sources / "plebian-os-snapshot.sources").exists())
            self.assertIn("restored the previous apt configuration", result.stderr)

    def test_snapshot_signal_rolls_back_before_exiting(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, sources, env = self._apt_tree(base)
            apt = base / "bin" / "apt-get"
            apt.write_text('#!/bin/sh\nkill -TERM "$PPID"\nexit 1\n')
            apt.chmod(0o755)
            live = sources / "debian.sources"
            content = "Types: deb\nURIs: https://deb.debian.org/debian\n"
            live.write_text(content)
            result = self._run_library(
                "PLEBIAN_OS_APT_SNAPSHOT=20260712T000000Z\nconfigure_apt_snapshot\n",
                env,
            )
            self.assertEqual(result.returncode, 143, result.stderr)
            self.assertEqual(live.read_text(), content)
            self.assertFalse(Path(str(live) + ".plebian-os-disabled").exists())
            self.assertFalse((etc / "plebian-os" / "apt-snapshot-sources").exists())
            self.assertFalse((sources / "plebian-os-snapshot.sources").exists())

    def test_provision_lock_contends_with_direct_pleb_lock(self):
        user = pwd.getpwuid(os.getuid())
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            state = base / "state"
            env = {
                **os.environ,
                "PLEBIAN_OS_PROVISION_LIB_ONLY": "1",
            }
            body = (
                f"TARGET_USER={user.pw_name!r}\n"
                f"TARGET_UID={user.pw_uid}\nTARGET_GID={user.pw_gid}\n"
                "DRY_RUN=0\n"
                "as_user() { \"$@\"; }\n"
                f"PLEB_STATE_HOME={str(state)!r}\nSUDOERS={str(base / 'sudoers')!r}\n"
                "acquire_provision_lock\n"
                'if flock -n "$PLEB_STATE_HOME/update.lock" -c true; then exit 91; fi\n'
                "cleanup\ntrap - EXIT INT TERM HUP\n"
                'flock -n "$PLEB_STATE_HOME/update.lock" -c true\n'
            )
            result = self._run_library(body, env)
            self.assertEqual(result.returncode, 0, result.stderr)
            lock = state / "update.lock"
            self.assertEqual(lock.stat().st_uid, user.pw_uid)
            self.assertEqual(stat.S_IMODE(lock.stat().st_mode), 0o600)

    def test_provision_lock_contends_with_direct_kilix_lock(self):
        user = pwd.getpwuid(os.getuid())
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            state = base / "state"
            state.mkdir(mode=0o700)
            env = {
                **os.environ,
                "PLEBIAN_OS_PROVISION_LIB_ONLY": "1",
            }
            body = (
                f"TARGET_USER={user.pw_name!r}\n"
                f"TARGET_UID={user.pw_uid}\nTARGET_GID={user.pw_gid}\n"
                "DRY_RUN=0\n"
                "as_user() { \"$@\"; }\n"
                f"KILIX_STATE_DIRECTORY={str(state)!r}\n"
                f"SUDOERS={str(base / 'sudoers')!r}\n"
                "acquire_kilix_provision_lock\n"
                '[ -n "$KILIX_PROVISION_LOCK_FD" ] || exit 92\n'
                f'[ "$KILIX_PROVISION_LOCK_PATH" = {str(state / "build-update.lock")!r} ] '
                "|| exit 93\n"
                'if flock -n "$KILIX_STATE_DIRECTORY/build-update.lock" -c true; '
                "then exit 94; fi\n"
                "cleanup\ntrap - EXIT INT TERM HUP\n"
                'flock -n "$KILIX_STATE_DIRECTORY/build-update.lock" -c true\n'
            )
            result = self._run_library(body, env)
            self.assertEqual(result.returncode, 0, result.stderr)
            lock = state / "build-update.lock"
            self.assertEqual(lock.stat().st_uid, user.pw_uid)
            self.assertEqual(lock.stat().st_nlink, 1)
            self.assertEqual(stat.S_IMODE(lock.stat().st_mode), 0o600)

    def test_private_storage_allocator_repairs_roots_without_replacing_data(self):
        user = pwd.getpwuid(os.getuid())
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            data = home / ".local" / "gpu_terminal"
            layout = self._private_storage_layout(data)
            prebuilt_parent = layout["KILIX_PREBUILT_HOME"].parent
            expected_paths = [*layout.values(), prebuilt_parent]
            for root in expected_paths:
                root.mkdir(parents=True, exist_ok=True)
                root.chmod(0o755)
            prebuilt_sentinel = prebuilt_parent / "keep-parent"
            prebuilt_sentinel.write_text("preserved\n")
            operator_desktop = home / "operator-desktop"
            operator_desktop.mkdir(mode=0o755)
            operator_sentinel = operator_desktop / "keep-me"
            operator_sentinel.write_text("operator-owned\n")
            sentinel = layout["KILIX95_CACHE_HOME"] / "keep-me"
            sentinel.write_text("preserved\n")
            env = {**os.environ, "PLEBIAN_OS_PROVISION_LIB_ONLY": "1"}
            body = (
                f"TARGET_USER={user.pw_name!r}\n"
                f"TARGET_UID={user.pw_uid}\nTARGET_GID={user.pw_gid}\n"
                "DRY_RUN=0\n"
                "as_user() { \"$@\"; }\n"
                f"USER_HOME={str(home)!r}\n"
                f"{self._private_storage_assignments(layout)}"
                f"KILIX_DESKTOP_DIR={str(operator_desktop)!r}\n"
                "allocate_coordinated_private_storage\n"
                "allocate_coordinated_private_storage\n"
            )
            result = self._run_library(body, env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(sentinel.read_text(), "preserved\n")
            self.assertEqual(prebuilt_sentinel.read_text(), "preserved\n")
            self.assertEqual(operator_sentinel.read_text(), "operator-owned\n")
            self.assertEqual(stat.S_IMODE(operator_desktop.stat().st_mode), 0o755)
            for root in expected_paths:
                with self.subTest(root=root):
                    self.assertFalse(root.is_symlink())
                    self.assertEqual(root.stat().st_uid, user.pw_uid)
                    self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)

    def test_private_storage_allocator_rejects_out_of_tree_component(self):
        user = pwd.getpwuid(os.getuid())
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            data = home / ".local" / "gpu_terminal"
            outside = home / "operator-data"
            home.mkdir()
            outside.mkdir(mode=0o755)
            layout = self._private_storage_layout(data)
            layout["PLEB_STORAGE_HOME"] = outside
            env = {**os.environ, "PLEBIAN_OS_PROVISION_LIB_ONLY": "1"}
            body = (
                f"TARGET_USER={user.pw_name!r}\n"
                f"TARGET_UID={user.pw_uid}\nTARGET_GID={user.pw_gid}\n"
                "DRY_RUN=0\n"
                "as_user() { \"$@\"; }\n"
                f"USER_HOME={str(home)!r}\n"
                f"{self._private_storage_assignments(layout)}"
                "allocate_coordinated_private_storage\n"
            )
            result = self._run_library(body, env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("strict descendant", result.stderr)
            self.assertEqual(stat.S_IMODE(outside.stat().st_mode), 0o755)

    def test_private_storage_allocator_rejects_symlink_root(self):
        user = pwd.getpwuid(os.getuid())
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            data = home / ".local" / "gpu_terminal"
            target = home / "operator-data"
            data.mkdir(parents=True)
            target.mkdir(mode=0o755)
            (data / "pleb").symlink_to(target, target_is_directory=True)
            layout = self._private_storage_layout(data)
            env = {**os.environ, "PLEBIAN_OS_PROVISION_LIB_ONLY": "1"}
            body = (
                f"TARGET_USER={user.pw_name!r}\n"
                f"TARGET_UID={user.pw_uid}\nTARGET_GID={user.pw_gid}\n"
                "DRY_RUN=0\n"
                "as_user() { \"$@\"; }\n"
                f"USER_HOME={str(home)!r}\n"
                f"{self._private_storage_assignments(layout)}"
                "allocate_coordinated_private_storage\n"
            )
            result = self._run_library(body, env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("must not contain symlinks", result.stderr)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o755)

    def test_private_storage_allocator_rejects_external_category(self):
        user = pwd.getpwuid(os.getuid())
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            data = home / ".local" / "gpu_terminal"
            outside = home / "operator-cache"
            home.mkdir()
            outside.mkdir(mode=0o755)
            layout = self._private_storage_layout(data)
            layout["KILIX_CACHE_HOME"] = outside
            env = {**os.environ, "PLEBIAN_OS_PROVISION_LIB_ONLY": "1"}
            body = (
                f"TARGET_USER={user.pw_name!r}\n"
                f"TARGET_UID={user.pw_uid}\nTARGET_GID={user.pw_gid}\n"
                "DRY_RUN=0\n"
                "as_user() { \"$@\"; }\n"
                f"USER_HOME={str(home)!r}\n"
                f"{self._private_storage_assignments(layout)}"
                "allocate_coordinated_private_storage\n"
            )
            result = self._run_library(body, env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("KILIX_CACHE_HOME must be a strict descendant", result.stderr)
            self.assertEqual(stat.S_IMODE(outside.stat().st_mode), 0o755)

    def test_private_storage_allocator_rejects_symlink_category(self):
        user = pwd.getpwuid(os.getuid())
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            data = home / ".local" / "gpu_terminal"
            target = home / "operator-cache"
            target.mkdir(parents=True, mode=0o755)
            layout = self._private_storage_layout(data)
            link = layout["KILIX95_CACHE_HOME"]
            link.parent.mkdir(parents=True)
            link.symlink_to(target, target_is_directory=True)
            env = {**os.environ, "PLEBIAN_OS_PROVISION_LIB_ONLY": "1"}
            body = (
                f"TARGET_USER={user.pw_name!r}\n"
                f"TARGET_UID={user.pw_uid}\nTARGET_GID={user.pw_gid}\n"
                "DRY_RUN=0\n"
                "as_user() { \"$@\"; }\n"
                f"USER_HOME={str(home)!r}\n"
                f"{self._private_storage_assignments(layout)}"
                "allocate_coordinated_private_storage\n"
            )
            result = self._run_library(body, env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("KILIX95_CACHE_HOME must not contain symlinks", result.stderr)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o755)

    def test_private_storage_allocator_creates_and_repairs_canonical_desktop(self):
        user = pwd.getpwuid(os.getuid())
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            data = home / ".local" / "gpu_terminal"
            layout = self._private_storage_layout(data)
            desktop = layout["PLEB_DATA_HOME"] / "desktop"
            env = {**os.environ, "PLEBIAN_OS_PROVISION_LIB_ONLY": "1"}
            prefix = (
                f"TARGET_USER={user.pw_name!r}\n"
                f"TARGET_UID={user.pw_uid}\nTARGET_GID={user.pw_gid}\n"
                "DRY_RUN=0\n"
                "as_user() { \"$@\"; }\n"
                f"USER_HOME={str(home)!r}\n"
                f"{self._private_storage_assignments(layout)}"
                f"KILIX_DESKTOP_DIR={str(desktop)!r}\n"
            )
            created = self._run_library(
                prefix + "allocate_coordinated_private_storage\n", env
            )
            self.assertEqual(created.returncode, 0, created.stderr)
            self.assertEqual(stat.S_IMODE(desktop.stat().st_mode), 0o700)

            sentinel = desktop / "keep-me"
            sentinel.write_text("preserved\n")
            desktop.chmod(0o755)
            repaired = self._run_library(
                prefix + "allocate_coordinated_private_storage\n", env
            )
            self.assertEqual(repaired.returncode, 0, repaired.stderr)
            self.assertEqual(stat.S_IMODE(desktop.stat().st_mode), 0o700)
            self.assertEqual(sentinel.read_text(), "preserved\n")

    def test_private_storage_allocator_honors_custom_in_root_prebuilt(self):
        user = pwd.getpwuid(os.getuid())
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            data = home / ".local" / "gpu_terminal"
            layout = self._private_storage_layout(data)
            custom = layout["KILIX_STORAGE_HOME"] / "bundles" / "custom.app"
            layout["KILIX_PREBUILT_HOME"] = custom
            desktop = layout["PLEB_DATA_HOME"] / "desktop"
            custom.parent.mkdir(parents=True)
            custom.parent.chmod(0o755)
            sentinel = custom.parent / "keep-me"
            sentinel.write_text("preserved\n")
            env = {**os.environ, "PLEBIAN_OS_PROVISION_LIB_ONLY": "1"}
            body = (
                f"TARGET_USER={user.pw_name!r}\n"
                f"TARGET_UID={user.pw_uid}\nTARGET_GID={user.pw_gid}\n"
                "DRY_RUN=0\n"
                "as_user() { \"$@\"; }\n"
                f"USER_HOME={str(home)!r}\n"
                f"{self._private_storage_assignments(layout)}"
                f"KILIX_DESKTOP_DIR={str(desktop)!r}\n"
                "allocate_coordinated_private_storage\n"
            )
            result = self._run_library(body, env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(stat.S_IMODE(custom.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(custom.parent.stat().st_mode), 0o700)
            self.assertEqual(sentinel.read_text(), "preserved\n")
            self.assertFalse(
                (layout["KILIX_STORAGE_HOME"] / "prebuilt" / "kitty.app").exists()
            )

    def test_private_storage_allocator_rejects_prebuilt_parent_symlink(self):
        user = pwd.getpwuid(os.getuid())
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            data = home / ".local" / "gpu_terminal"
            layout = self._private_storage_layout(data)
            custom = layout["KILIX_STORAGE_HOME"] / "bundles" / "custom.app"
            layout["KILIX_PREBUILT_HOME"] = custom
            target = home / "operator-bundles"
            target.mkdir(parents=True, mode=0o755)
            layout["KILIX_STORAGE_HOME"].mkdir(parents=True)
            custom.parent.symlink_to(target, target_is_directory=True)
            desktop = layout["PLEB_DATA_HOME"] / "desktop"
            env = {**os.environ, "PLEBIAN_OS_PROVISION_LIB_ONLY": "1"}
            body = (
                f"TARGET_USER={user.pw_name!r}\n"
                f"TARGET_UID={user.pw_uid}\nTARGET_GID={user.pw_gid}\n"
                "DRY_RUN=0\n"
                "as_user() { \"$@\"; }\n"
                f"USER_HOME={str(home)!r}\n"
                f"{self._private_storage_assignments(layout)}"
                f"KILIX_DESKTOP_DIR={str(desktop)!r}\n"
                "allocate_coordinated_private_storage\n"
            )
            result = self._run_library(body, env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("KILIX_PREBUILT_HOME must not contain symlinks", result.stderr)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o755)
            self.assertFalse((target / "custom.app").exists())

    def test_updater_allocates_private_categories_before_first_lock_write(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            data = home / ".local" / "gpu_terminal"
            layout = self._private_storage_layout(data)
            desktop = layout["PLEB_DATA_HOME"] / "desktop"
            custom = layout["KILIX_STORAGE_HOME"] / "bundles" / "custom.app"
            layout["KILIX_PREBUILT_HOME"] = custom
            # Exercise repair as well as fresh child allocation.
            for path in (data, layout["PLEB_STORAGE_HOME"], layout["PLEB_STATE_HOME"]):
                path.mkdir(parents=True, exist_ok=True)
                path.chmod(0o755)
            custom.parent.mkdir(parents=True, exist_ok=True)
            custom.parent.chmod(0o755)
            assignments = self._private_storage_assignments(layout)
            paths = [*layout.values(), custom.parent, desktop]
            quoted_paths = " ".join(repr(str(path)) for path in paths)
            body = (
                "set -euo pipefail\n"
                "export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1\n"
                f"HOME={str(home)!r}\n"
                f"{assignments}"
                f"KILIX_DESKTOP_DIR={str(desktop)!r}\n"
                f"source {str(UPDATE)!r}\n"
                "allocate_coordinated_private_storage\n"
                f"for d in {quoted_paths}; do "
                "[ -d \"$d\" ] && [ ! -L \"$d\" ] && "
                "[ \"$(stat -c '%u:%a' -- \"$d\")\" = \"$(id -u):700\" ]; done\n"
                "[ ! -e \"$PLEB_STATE_HOME/update.lock\" ]\n"
                "acquire_update_lock\n"
                "[ \"$(stat -c '%a' -- \"$PLEB_STATE_HOME/update.lock\")\" = 600 ]\n"
            )
            result = subprocess.run(
                ["bash", "-c", body], text=True, capture_output=True, check=False
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_updater_root_guard_says_to_run_without_sudo(self):
        with tempfile.TemporaryDirectory() as td:
            body = (
                "set -euo pipefail\n"
                "export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1\n"
                f"HOME={td!r}\nPLEB_STATE_HOME={str(Path(td) / 'state')!r}\n"
                f"source {str(UPDATE)!r}\n"
                "require_unprivileged_updater 0\n"
            )
            result = subprocess.run(
                ["bash", "-c", body], text=True, capture_output=True, check=False
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("run plebian-os-update without sudo", result.stderr)

    def test_provision_lock_wraps_the_complete_mutation_window(self):
        source = PROVISION.read_text()
        paths_resolved = source.rindex(
            'PLEBIAN_OS_SESSION_HOME="${PLEBIAN_OS_SESSION_HOME:-'
        )
        allocated = source.rindex("\nallocate_coordinated_private_storage\n")
        acquired = source.rindex("\nacquire_provision_lock\n")
        apt_mutation = source.rindex("\nconfigure_apt_snapshot\n")
        provenance = source.rindex("\nwrite_source_tool_manifest\n")
        transaction = source.rindex("\nbegin_provision_root_transaction\n")
        committed = source.rindex("\ncommit_provision_root_transaction\n")
        released = source.rindex("\ncleanup\ntrap - EXIT INT TERM HUP\n")
        self.assertLess(paths_resolved, allocated)
        self.assertLess(allocated, acquired)
        self.assertLess(acquired, apt_mutation)
        self.assertLess(apt_mutation, transaction)
        self.assertLess(transaction, provenance)
        self.assertLess(apt_mutation, provenance)
        self.assertLess(provenance, committed)
        self.assertLess(committed, released)
        self.assertLess(provenance, released)
        self.assertIn('write_session_default PLEB_STATE_HOME "$PLEB_STATE_HOME"', source)

        update = UPDATE.read_text()
        update_allocated = update.index("\n    allocate_coordinated_private_storage\n")
        update_acquired = update.index("\n    acquire_update_lock\n")
        self.assertLess(update_allocated, update_acquired)
        self.assertLess(
            update.index('require_unprivileged_updater "$EUID"'), update_allocated
        )

    def test_component_versions_are_exact_not_substrings(self):
        env = {**os.environ, "PLEBIAN_OS_PROVISION_LIB_ONLY": "1"}
        exact = self._run_library(
            "PLEBIAN_OS_VERSION=0.1.1\n"
            "validate_component_versions 'pleb 0.1.1' '0.1.1' 'kilix-95 0.1.1'\n",
            env,
        )
        self.assertEqual(exact.returncode, 0, exact.stderr)
        near = self._run_library(
            "PLEBIAN_OS_VERSION=0.1.1\n"
            "validate_component_versions 'pleb 0.1.10' '10.1.1' 'kilix-95 0.1.1-dev'\n",
            env,
        )
        self.assertNotEqual(near.returncode, 0)
        self.assertIn("expected exactly", near.stderr)

    def test_main_session_still_installs_selected_kilix95_provider(self):
        env = {**os.environ, "PLEBIAN_OS_PROVISION_LIB_ONLY": "1"}
        result = self._run_library(
            "DESKTOP=0\n"
            "KILIX_DIR=/missing-kilix-checkout\n"
            "KILIX95_AUTO_INSTALL=1\n"
            "KILIX_DESKTOP_PROVIDER=external\n"
            "kilix95_install_required\n"
            "KILIX_DESKTOP_PROVIDER=cap\n"
            "! kilix95_install_required\n"
            "KILIX_DESKTOP_PROVIDER=external\n"
            "KILIX95_AUTO_INSTALL=0\n"
            "! kilix95_install_required\n",
            env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_explicit_root_target_is_rejected(self):
        result = subprocess.run(
            ["bash", str(PROVISION), "--dry-run", "--user", "root"],
            env={**os.environ, "PLEBIAN_OS_RELEASE_MODE": "0"},
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("regular non-root account", result.stderr)

    def test_release_uv_requires_exact_pins_even_in_dry_run(self):
        invalid = subprocess.run(
            ["bash", str(DEPS), "--dry-run"],
            env={
                **os.environ,
                "PLEBIAN_OS_INSTALL_UV": "1",
                "PLEBIAN_OS_RELEASE_MODE": "1",
                "PLEBIAN_OS_UV_VERSION": "",
                "PLEBIAN_OS_UV_INSTALLER_SHA256": "",
            },
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(invalid.returncode, 0)
        self.assertIn("uv (release-required)", invalid.stderr)

        valid = subprocess.run(
            ["bash", str(DEPS), "--dry-run"],
            env={
                **os.environ,
                "PLEBIAN_OS_INSTALL_UV": "1",
                "PLEBIAN_OS_RELEASE_MODE": "1",
                "PLEBIAN_OS_UV_VERSION": "0.9.0",
                "PLEBIAN_OS_UV_INSTALLER_SHA256": "a" * 64,
            },
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(valid.returncode, 0, valid.stderr)
        self.assertIn("verify staged uv --version reports exactly uv 0.9.0", valid.stdout)

    def test_verified_kilix_build_requires_one_coherent_canonical_identity(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            kilix = base / "kilix"
            src = kilix / "src"
            subprocess.run(["git", "init", "-q", "-b", "main", str(src)], check=True)
            subprocess.run(["git", "-C", str(src), "config", "user.name", "Pleb Test"], check=True)
            subprocess.run(
                ["git", "-C", str(src), "config", "user.email", "pleb@example.invalid"],
                check=True,
            )
            (src / "tracked").write_text("source\n")
            subprocess.run(["git", "-C", str(src), "add", "tracked"], check=True)
            subprocess.run(["git", "-C", str(src), "commit", "-q", "-m", "source"], check=True)
            head = subprocess.check_output(
                ["git", "-C", str(src), "rev-parse", "HEAD"], text=True
            ).strip()

            build = base / "kilix-state" / "build"
            generation = build / "generations/build.Valid"
            (generation / "src/kitty/launcher").mkdir(parents=True)
            (build / "current").symlink_to("generations/build.Valid")
            fork = build / "current/src/kitty/launcher/kitty"
            kitten = build / "current/src/kitty/launcher/kitten"
            for path in (fork, kitten):
                path.write_text("#!/bin/sh\nexit 0\n")
                path.chmod(0o755)
            source_id = build / "current/source-id"
            source_id.write_text(head + "\n")
            state = base / "kilix-state" / "state"
            state.mkdir()
            stamp = state / "fork-built-ref"
            stamp.write_text(f"{kilix.resolve()}\t{head}\n")
            stamp.chmod(0o600)

            launcher = kilix / "kilix"

            def write_launcher(engine: Path = fork, rc: int = 0) -> None:
                launcher.write_text(
                    "#!/bin/sh\n"
                    "[ \"${1:-}\" = --which ] || exit 2\n"
                    f"printf '%s\\n' '{engine}'\n"
                    "printf '%s\\n' 'kilix-test 1.0'\n"
                    f"exit {rc}\n"
                )
                launcher.chmod(0o755)

            write_launcher()
            user = pwd.getpwuid(os.getuid())
            env = {**os.environ, "PLEBIAN_OS_PROVISION_LIB_ONLY": "1"}
            body = (
                f"TARGET_USER={user.pw_name!r}\n"
                f"TARGET_UID={user.pw_uid}\nTARGET_GID={user.pw_gid}\n"
                "DRY_RUN=0\n"
                "as_user() { \"$@\"; }\n"
                "install_env=()\n"
                f"KILIX_DIR={str(kilix)!r}\n"
                f"KILIX_BUILD_DIRECTORY={str(build)!r}\n"
                f"KILIX_STATE_DIRECTORY={str(state)!r}\n"
                "verify_kilix_fork_build\n"
            )

            valid = self._run_library(body, env)
            self.assertEqual(valid.returncode, 0, valid.stderr)

            cases = []
            source_id.write_text("wrong\n")
            cases.append(("source-id", self._run_library(body, env)))
            source_id.write_text(head + "\n\n")
            cases.append(("source-id", self._run_library(body, env)))
            source_id.write_text(head + "\n")

            stamp.write_text("wrong\n")
            cases.append(("stamp", self._run_library(body, env)))
            stamp.write_text(f"{kilix.resolve()}\t{head}\n\n")
            cases.append(("stamp", self._run_library(body, env)))
            stamp.write_text(f"{kilix.resolve()}\t{head}\n")

            kitten.unlink()
            cases.append(("did not produce", self._run_library(body, env)))
            kitten.write_text("#!/bin/sh\nexit 0\n")
            kitten.chmod(0o755)

            kitten.write_text("#!/bin/sh\nexit 74\n")
            cases.append(("kitten failed", self._run_library(body, env)))
            kitten.write_text("#!/bin/sh\nexit 0\n")
            kitten.chmod(0o755)

            (build / "current").unlink()
            (build / "current").symlink_to(generation)
            cases.append(("unsafe current generation", self._run_library(body, env)))
            (build / "current").unlink()
            (build / "current").symlink_to("generations/build.Valid")

            write_launcher(base / "wrong-engine")
            cases.append(("not using the fork engine", self._run_library(body, env)))
            write_launcher(rc=73)
            cases.append(("failed its post-build version probe", self._run_library(body, env)))

            write_launcher()
            alias = state / "fork-built-ref.alias"
            os.link(stamp, alias)
            cases.append(("exactly one hard link", self._run_library(body, env)))
            alias.unlink()

            for message, result in cases:
                with self.subTest(message=message):
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(message, result.stderr)

    def test_exact_go_requires_root_owned_source_stamp(self):
        source = PROVISION.read_text()
        self.assertIn("pinned_go_provenance_ok", source)
        self.assertIn("root=/usr/local/go", source)
        self.assertIn('stamp="$root/.pleb-source"', source)
        self.assertIn("root-owned .pleb-source archive stamp is absent or mismatched", source)
        self.assertLess(source.index("pinned_go_provenance_ok \"$arch\" \"$sha\""),
                        source.index('"GO_VERSION=$KILIX_GO_VERSION"'))

    def test_release_dictation_requires_the_complete_voice_closure(self):
        ref = "a" * 40
        digest = "b" * 64
        env = {
            **os.environ,
            "PLEBIAN_OS_PROVISION_LIB_ONLY": "1",
            "PLEBIAN_OS_RELEASE_MODE": "1",
            "PLEBIAN_OS_REF": ref,
            "PLEB_REF": ref,
            "KILIX_REF": ref,
            "KILIX95_REF": ref,
            "KILIX_PREBUILT_SHA256": digest,
            "PLEBIAN_OS_KILIX_GO_VERSION": "go1.26.5",
            "PLEBIAN_OS_KILIX_GO_SHA256_AMD64": digest,
            "PLEBIAN_OS_KILIX_GO_SHA256_ARM64": digest,
            "PLEBIAN_OS_INSTALL_VOICE_MODEL": "1",
            "KILIX_VOICE_REF": ref,
            "KILIX_VOICE_LIB_VERSION": "0.3.45",
            "KILIX_VOICE_LIB_URL": "https://example.invalid/vosk.whl",
            "KILIX_VOICE_LIB_SHA256": digest,
            "KILIX_VOICE_MODEL_URL": "https://example.invalid/model.zip",
            "KILIX_VOICE_MODEL_SHA256": digest,
        }
        valid = self._run_library("validate_release_inputs\n", env)
        self.assertEqual(valid.returncode, 0, valid.stderr)

        for key in (
            "KILIX_VOICE_REF",
            "KILIX_VOICE_LIB_VERSION",
            "KILIX_VOICE_LIB_URL",
            "KILIX_VOICE_LIB_SHA256",
            "KILIX_VOICE_MODEL_URL",
            "KILIX_VOICE_MODEL_SHA256",
        ):
            with self.subTest(key=key):
                invalid_env = {**env, key: ""}
                refused = self._run_library(
                    "validate_release_inputs\n", invalid_env
                )
                self.assertNotEqual(refused.returncode, 0)
                self.assertIn(key, refused.stderr)

    def test_provision_voice_catalog_rejects_false_release_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            records = []
            for model, engine, supported, size, human_size in (
                ("small-en-us", "vosk", True, 41205931, "39.3 MiB"),
                ("lgraph-en-us", "vosk", True, 130557655, "124.5 MiB"),
                (
                    "vibevoice-asr-bitnet", "vibevoice", False,
                    1705771590, "1.6 GiB",
                ),
            ):
                records.append({
                    "id": model,
                    "engine": engine,
                    "runtime_supported": supported,
                    "download_bytes": size,
                    "download_size": human_size,
                    "installed": False,
                    "selected": model == "small-en-us",
                    "path": str(root / model),
                    "summary": f"{model} fixture summary",
                    "install_and_default_argv": [
                        "kilix", "stt", "--install", model,
                        "--default", model,
                    ],
                })
            document = {
                "schema": "kilix.speech.models/v1",
                "default_model": "small-en-us",
                "models": records,
            }
            environment = {
                **os.environ,
                "PLEBIAN_OS_PROVISION_LIB_ONLY": "1",
            }

            def validate(candidate):
                return subprocess.run(
                    [
                        "bash", "-c",
                        f'. "{PROVISION}"\nvalidate_voice_model_catalog',
                    ],
                    env=environment,
                    input=json.dumps(candidate),
                    text=True,
                    capture_output=True,
                    check=False,
                )

            accepted = validate(document)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)

            invalid_documents = []
            invalid = json.loads(json.dumps(document))
            invalid["models"][1]["download_bytes"] = 1
            invalid_documents.append(("exact bytes", invalid))
            invalid = json.loads(json.dumps(document))
            invalid["models"][1]["runtime_supported"] = 1
            invalid_documents.append(("boolean support", invalid))
            invalid = json.loads(json.dumps(document))
            invalid["models"][1]["installed"] = True
            invalid_documents.append(("filesystem state", invalid))
            for label, invalid in invalid_documents:
                with self.subTest(label=label):
                    refused = validate(invalid)
                    self.assertNotEqual(refused.returncode, 0)

    def test_release_voice_verification_executes_tools_and_checks_attribution(self):
        user = pwd.getpwuid(os.getuid())
        voice_ref = "f05b64a7b2bc25fa9a7e2c3ae1e0b848f04a23f6"
        library_version = "0.3.45"
        library_url = (
            "https://files.pythonhosted.org/packages/fc/ca/83398cfcd557360a3d7b2d732aee1c5f6999f68618d1645f38d53e14c9ff/"
            "vosk-0.3.45-py3-none-manylinux_2_12_x86_64.manylinux2010_x86_64.whl"
        )
        library_sha = (
            "25e025093c4399d7278f543568ed8cc5460ac3a4bf48c23673ace1e25d26619f"
        )
        model_url = (
            "https://alphacephei.com/vosk/models/"
            "vosk-model-small-en-us-0.15.zip"
        )
        model_sha = (
            "30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498"
        )
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            home = base / "home"
            data = base / "data"
            binaries = home / ".local" / "bin"
            binaries.mkdir(parents=True)
            catalog_records = []
            for model, engine, supported, size, human_size in (
                ("small-en-us", "vosk", True, 41205931, "39.3 MiB"),
                ("lgraph-en-us", "vosk", True, 130557655, "124.5 MiB"),
                (
                    "vibevoice-asr-bitnet", "vibevoice", False,
                    1705771590, "1.6 GiB",
                ),
            ):
                catalog_records.append({
                    "id": model,
                    "engine": engine,
                    "runtime_supported": supported,
                    "download_bytes": size,
                    "download_size": human_size,
                    "installed": model == "small-en-us",
                    "selected": model == "small-en-us",
                    "path": str(data / "voice" / "models" / model),
                    "summary": f"{model} release fixture",
                    "install_and_default_argv": [
                        "kilix", "stt", "--install", model,
                        "--default", model,
                    ],
                })
            catalog = json.dumps({
                "schema": "kilix.speech.models/v1",
                "default_model": "small-en-us",
                "models": catalog_records,
            }, separators=(",", ":"))
            for tool in ("kilix-tts", "kilix-stt", "kilix-voiced"):
                executable = binaries / tool
                executable.write_text(
                    "#!/bin/sh\n"
                    "if [ \"${1:-}\" = --version ]; then\n"
                    f"  printf '%s\\n' '{tool} 0.1.3'\n"
                    "elif [ \"${1:-}\" = --print ]; then\n"
                    + (
                        "  printf '%s\\n' 'dictation=ready'\n"
                        if tool == "kilix-stt"
                        else "  printf '%s\\n' 'voice=ready'\n"
                    )
                    + (
                        "elif [ \"${1:-}\" = --models ] "
                        "&& [ \"${2:-}\" = --json ]; then\n"
                        f"  printf '%s\\n' '{catalog}'\n"
                        if tool == "kilix-stt"
                        else ""
                    )
                    + "fi\n"
                )
                executable.chmod(0o755)

            library_parent = data / "voice" / "lib"
            model_parent = data / "voice" / "models"
            library_parent.mkdir(parents=True)
            model_parent.mkdir(parents=True)
            library_generation = (
                library_parent / f"vosk-{library_version}-{library_sha}"
            )
            model_generation = (
                model_parent / f"vosk-model-small-en-us-0.15-{model_sha}"
            )
            library_generation.mkdir()
            model_generation.mkdir()
            (library_parent / "current").symlink_to(library_generation.name)
            (model_parent / "small-en-us").symlink_to(model_generation.name)
            library = library_parent / "current"
            model = model_parent / "small-en-us"
            (library / "libvosk.so").write_bytes(b"fixture\n")
            (model_generation / "conf").mkdir()
            (model_generation / "am").mkdir()
            (model_generation / "conf" / "model.conf").write_text(
                "fixture\n"
            )
            (model_generation / "am" / "final.mdl").write_bytes(
                b"fixture\n"
            )
            license_text = Path(
                "/usr/share/common-licenses/Apache-2.0"
            ).read_bytes()
            for directory in (library, model):
                (directory / "LICENSE.Apache-2.0").write_bytes(license_text)
            (library / "README.kilix-provenance").write_text(
                "Kilix Voice native speech-recognition library\n"
                "Upstream: https://github.com/alphacep/vosk-api\n"
                f"Version: {library_version}\n"
                f"Wheel: {library_url}\n"
                f"Wheel SHA-256: {library_sha}\n"
                "Extracted member: vosk/libvosk.so\n"
                "License: Apache-2.0 (see LICENSE.Apache-2.0)\n"
            )
            model_notice = model / "README.kilix-provenance"
            model_notice.write_text(
                "Vosk small US English acoustic model\n"
                "Upstream catalog: https://alphacephei.com/vosk/models\n"
                f"Archive: {model_url}\n"
                f"Archive SHA-256: {model_sha}\n"
                "Archive directory: vosk-model-small-en-us-0.15\n"
                "License: Apache-2.0 (see LICENSE.Apache-2.0)\n"
            )
            state = base / "state"
            state.mkdir()
            voice_stamp = state / "kilix-voice-install.refs"
            voice_stamp.write_text(
                f"kilix-voice={voice_ref}\n"
                f"libvosk={library_version}+{library_sha}\n"
                f"model-small-en-us={model_sha}\n"
            )
            voice_stamp.chmod(0o600)
            source_home = base / "sources"
            voice_source = (
                source_home
                / ".kilix-voice-sources"
                / f"kilix-voice-{voice_ref}"
            )
            (voice_source / ".git").mkdir(parents=True)
            (voice_source / "VERSION").write_text("0.1.3\n")
            env = {**os.environ, "PLEBIAN_OS_PROVISION_LIB_ONLY": "1"}
            body = (
                f"TARGET_USER={user.pw_name!r}\n"
                f"TARGET_UID={user.pw_uid}\nTARGET_GID={user.pw_gid}\n"
                "DRY_RUN=0\nPLEBIAN_OS_RELEASE_MODE=1\n"
                "INSTALL_VOICE_MODEL=1\ninstall_env=()\n"
                "as_user() {\n"
                "  if [ \"${1:-}\" = git ] && [ \"${4:-}\" = rev-parse ]; then\n"
                f"    printf '%s\\n' {voice_ref!r}; return 0\n"
                "  fi\n"
                "  if [ \"${1:-}\" = git ] && [ \"${4:-}\" = show ]; then\n"
                "    printf '%s\\n' 0.1.3; return 0\n"
                "  fi\n"
                "  \"$@\"\n"
                "}\n"
                "run_voice_functional_smoke() { return 0; }\n"
                f"USER_HOME={str(home)!r}\n"
                f"GPU_TERMINAL_SOURCE_HOME={str(source_home)!r}\n"
                f"KILIX_DATA_HOME={str(data)!r}\n"
                f"KILIX_STATE_DIRECTORY={str(state)!r}\n"
                f"KILIX_VOICE_REF={voice_ref!r}\n"
                f"KILIX_VOICE_LIB_VERSION={library_version!r}\n"
                f"KILIX_VOICE_LIB_URL={library_url!r}\n"
                f"KILIX_VOICE_LIB_SHA256={library_sha!r}\n"
                f"KILIX_VOICE_MODEL_URL={model_url!r}\n"
                f"KILIX_VOICE_MODEL_SHA256={model_sha!r}\n"
                "verify_kilix_voice_install\n"
            )
            valid = self._run_library(body, env)
            self.assertEqual(valid.returncode, 0, valid.stderr)

            model_notice.write_text("opaque model\n")
            refused = self._run_library(body, env)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("model provenance", refused.stderr)


class PersistedPinTests(unittest.TestCase):
    """A re-run of the provisioner must reproduce the installed closure.

    Every pinned install has detached checkouts. The refs that put them there
    live in /etc/pleb/session.env — written by this provisioner, read by
    pleb-session, `pleb` and plebian-os-update. Nothing fed them back into a
    *re-run* of the provisioner: it saw them only through the environment, and
    only plebian-os-firstboot.service ever set that, once. So
    `sudo plebian-os-provision` — the command plebian-os-update recommends for
    OS-layer changes — fell through to `git pull --ff-only` and failed on the
    detached HEAD every pinned install has.
    """

    PINS = (
        "PLEBIAN_OS_REF", "PLEBIAN_OS_BRANCH",
        "PLEB_REF", "PLEB_BRANCH",
        "KILIX_REF", "KILIX_BRANCH",
        "KILIX95_REF", "KILIX95_BRANCH",
        "KILIX_VOICE_REF", "KILIX_CAP_REF",
        "KILIX_TUI_UTILS_REF", "KILIX_LAND_DESKTOP_REF",
    )

    @staticmethod
    def _session_env(path: Path, values: dict[str, str]) -> None:
        # Exactly what write_session_default emits.
        path.write_text("".join(
            'if [ -z "${%s+x}" ]; then %s=%s; fi\n' % (key, key, value)
            for key, value in values.items()
        ))

    @staticmethod
    def _origin_with_two_commits(path: Path) -> tuple[str, str]:
        subprocess.run(["git", "init", "-q", "-b", "main", str(path)],
                       check=True)
        for key, value in (("user.name", "test"),
                           ("user.email", "test@example.invalid")):
            subprocess.run(["git", "-C", str(path), "config", key, value],
                           check=True)
        (path / "tracked").write_text("first\n")
        subprocess.run(["git", "-C", str(path), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", "first"],
                       check=True)
        first = subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
        (path / "tracked").write_text("second\n")
        subprocess.run(["git", "-C", str(path), "commit", "-qam", "second"],
                       check=True)
        second = subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
        return first, second

    def _run(self, session_env: Path, body: str, extra: str = ""):
        # as_user/as_target_readonly exist to drop root privilege; replace them
        # so the checkout logic under test runs as the invoking user, the same
        # way the transactional suites replace their privileged primitives.
        script = (
            "set -euo pipefail\n"
            "export PLEBIAN_OS_PROVISION_LIB_ONLY=1\n"
            f"export PLEBIAN_OS_SESSION_ENV={str(session_env)!r}\n"
            f"{extra}"
            f'. "{PROVISION}"\n'
            "as_user() { \"$@\"; }\n"
            "as_target_readonly() { \"$@\"; }\n"
            "DRY_RUN=0\n"
            f"{body}"
        )
        return subprocess.run(
            ["bash", "-c", script], text=True, capture_output=True, check=False)

    def test_every_component_pin_is_restored_from_the_session_env(self):
        with tempfile.TemporaryDirectory() as td:
            session_env = Path(td) / "session.env"
            values = {key: f"{key.lower()}-value" for key in self.PINS}
            self._session_env(session_env, values)
            result = self._run(
                session_env,
                "restore_installed_closure\n"
                + "".join(f'printf "%s=%s\\n" {key} "${key}"\n'
                          for key in self.PINS),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            for key in self.PINS:
                with self.subTest(pin=key):
                    self.assertIn(f"{key}={values[key]}", result.stdout)

    def test_an_explicit_pin_is_not_overwritten_by_the_session_env(self):
        with tempfile.TemporaryDirectory() as td:
            session_env = Path(td) / "session.env"
            self._session_env(session_env, {"PLEB_REF": "persisted",
                                            "KILIX_REF": "persisted"})
            result = self._run(
                session_env,
                "restore_installed_closure\n"
                'printf "PLEB_REF=%s\\n" "$PLEB_REF"\n'
                'printf "KILIX_REF=%s\\n" "$KILIX_REF"\n',
                extra="export PLEB_REF=explicit\n",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("PLEB_REF=explicit", result.stdout)
            self.assertIn("KILIX_REF=persisted", result.stdout)

    def test_restoring_pins_leaves_unrelated_session_settings_alone(self):
        with tempfile.TemporaryDirectory() as td:
            session_env = Path(td) / "session.env"
            self._session_env(session_env, {
                "PLEB_REF": "persisted",
                # Policy this run already resolved; the file must not reach it.
                "PLEBIAN_OS_KIOSK": "1",
                "PLEB_DIR": "/somewhere/else",
            })
            result = self._run(
                session_env,
                "restore_installed_closure\n"
                'printf "PLEB_REF=%s\\n" "$PLEB_REF"\n'
                'printf "KIOSK=%s\\n" "$KIOSK"\n'
                'printf "PLEB_DIR=%s\\n" "$PLEB_DIR"\n',
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("PLEB_REF=persisted", result.stdout)
            self.assertIn("KIOSK=0", result.stdout)
            self.assertIn("PLEB_DIR=\n", result.stdout)

    def test_install_policy_is_restored_from_the_firstboot_environment(self):
        # A plain re-run reconciles kiosk, sudo and optional components. It saw
        # none of them, so it reconciled to the defaults: a kiosk image lost its
        # autologin and had its passwordless sudo revoked at the very end of an
        # otherwise successful run.
        with tempfile.TemporaryDirectory() as td:
            firstboot = Path(td) / "plebian-os"
            firstboot.write_text(
                '# Generated by build/remaster-iso.sh.\n'
                'PLEBIAN_OS_KIOSK="1"\n'
                'PLEBIAN_OS_NOPASSWD_SUDO="1"\n'
                'PLEBIAN_OS_DESKTOP="0"\n'
                'PLEBIAN_OS_INSTALL_UV="1"\n'
                'PLEBIAN_OS_INSTALL_VOICE_MODEL="1"\n'
                'PLEBIAN_OS_APT_SNAPSHOT="20260727T000000Z"\n'
                'PLEBIAN_OS_USER="pleb"\n'
            )
            report = (
                'printf "KIOSK=%s NOPASSWD_SUDO=%s DESKTOP=%s INSTALL_UV=%s '
                'VOICE=%s APT=%s USER=%s\\n" "$KIOSK" "$NOPASSWD_SUDO" '
                '"$DESKTOP" "$INSTALL_UV" "$INSTALL_VOICE_MODEL" '
                '"$PLEBIAN_OS_APT_SNAPSHOT" "$TARGET_USER"\n'
            )
            result = self._run(
                Path(td) / "missing.env", "restore_persisted_policy\n" + report,
                extra=f"export PLEBIAN_OS_FIRSTBOOT_ENV={str(firstboot)!r}\n")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "KIOSK=1 NOPASSWD_SUDO=1 DESKTOP=0 INSTALL_UV=1 VOICE=1 "
                "APT=20260727T000000Z USER=pleb", result.stdout)

            # An explicit choice still wins — that is how policy is changed.
            explicit = self._run(
                Path(td) / "missing.env", "restore_persisted_policy\n" + report,
                extra=(f"export PLEBIAN_OS_FIRSTBOOT_ENV={str(firstboot)!r}\n"
                       "export PLEBIAN_OS_KIOSK=0\n"
                       "export PLEBIAN_OS_NOPASSWD_SUDO=0\n"))
            self.assertEqual(explicit.returncode, 0, explicit.stderr)
            self.assertIn("KIOSK=0 NOPASSWD_SUDO=0 DESKTOP=0", explicit.stdout)

    def test_unparseable_policy_values_are_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            firstboot = Path(td) / "plebian-os"
            firstboot.write_text(
                'PLEBIAN_OS_KIOSK="$(touch /tmp/pwned)"\n'
                'PLEBIAN_OS_NOPASSWD_SUDO="yes please"\n'
                'PLEBIAN_OS_APT_SNAPSHOT="not-a-timestamp"\n'
            )
            result = self._run(
                Path(td) / "missing.env",
                "restore_persisted_policy\n"
                'printf "KIOSK=%s NOPASSWD_SUDO=%s APT=%s\\n" "$KIOSK" '
                '"$NOPASSWD_SUDO" "$PLEBIAN_OS_APT_SNAPSHOT"\n',
                extra=f"export PLEBIAN_OS_FIRSTBOOT_ENV={str(firstboot)!r}\n")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("KIOSK=0 NOPASSWD_SUDO=0 APT=", result.stdout)
            self.assertFalse(Path("/tmp/pwned").exists())

    def test_a_pinned_detached_checkout_is_updated_from_the_persisted_ref(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            origin = work / "origin"
            first, second = self._origin_with_two_commits(origin)
            checkout = work / "pleb"
            subprocess.run(["git", "clone", "-q", str(origin), str(checkout)],
                           check=True)
            # What a pinned install looks like: no branch, just a commit.
            subprocess.run(
                ["git", "-C", str(checkout), "checkout", "-q", "--detach",
                 first], check=True)
            session_env = work / "session.env"
            self._session_env(session_env, {"PLEB_REF": second})

            common = (
                f"PLEB_DIR={str(checkout)!r}\n"
                f"PLEB_REPO={str(origin)!r}\n"
                "update_pleb_checkout\n"
                'git -C "$PLEB_DIR" rev-parse HEAD\n'
            )
            result = self._run(session_env,
                               "restore_installed_closure\n" + common)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(second, result.stdout)
            self.assertNotIn(
                "not currently on a branch", result.stdout + result.stderr)
            self.assertEqual(
                subprocess.check_output(
                    ["git", "-C", str(checkout), "rev-parse", "HEAD"],
                    text=True).strip(),
                second)

            # Without the pin there is nothing to position the checkout by, and
            # `git pull --ff-only` can only report that in git's own words.
            subprocess.run(
                ["git", "-C", str(checkout), "checkout", "-q", "--detach",
                 first], check=True)
            unpinned = self._run(work / "missing.env", common)
            self.assertNotEqual(unpinned.returncode, 0)
            self.assertIn("is not on a branch and no PLEB_REF/PLEB_BRANCH",
                          unpinned.stderr)
            self.assertEqual(
                subprocess.check_output(
                    ["git", "-C", str(checkout), "rev-parse", "HEAD"],
                    text=True).strip(),
                first)


if __name__ == "__main__":
    unittest.main()
