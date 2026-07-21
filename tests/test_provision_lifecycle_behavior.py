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
        released = source.rindex("\ncleanup; trap - EXIT\n")
        self.assertLess(paths_resolved, allocated)
        self.assertLess(allocated, acquired)
        self.assertLess(acquired, apt_mutation)
        self.assertLess(apt_mutation, provenance)
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


if __name__ == "__main__":
    unittest.main()
