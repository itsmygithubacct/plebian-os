import os
import pwd
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROVISION = ROOT / "provision" / "plebian-os-provision.sh"
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

    def test_provision_lock_wraps_the_complete_mutation_window(self):
        source = PROVISION.read_text()
        acquired = source.rindex("\nacquire_provision_lock\n")
        apt_mutation = source.rindex("\nconfigure_apt_snapshot\n")
        provenance = source.rindex("\nwrite_source_tool_manifest\n")
        released = source.rindex("\ncleanup; trap - EXIT\n")
        self.assertLess(acquired, apt_mutation)
        self.assertLess(apt_mutation, provenance)
        self.assertLess(provenance, released)
        self.assertIn('write_session_default PLEB_STATE_HOME "$PLEB_STATE_HOME"', source)

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
