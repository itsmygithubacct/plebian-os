import fcntl
import json
import os
import pwd
import shutil
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
# What `apt-get indextargets` reports for a deb822 source whose first stanza is
# trixie + trixie-updates and whose second is trixie-security. The apt-get stub
# replaces @SOURCE@ with the path it was handed, as apt's SOURCESENTRY does.
LIVE_DEBIAN_TARGETS = (
    "https://deb.debian.org/debian trixie main @SOURCE@:1\n"
    "https://deb.debian.org/debian trixie-updates main @SOURCE@:1\n"
    "https://security.debian.org/debian-security trixie-security main @SOURCE@:2\n"
)
# What Debian Installer leaves on a snapshot image: the apt-setup generator's
# marker plus the snapshot mirror it configured.
INSTALLER_SOURCES_LIST = (
    "# Plebian-OS snapshot validity policy\n"
    "deb https://snapshot.debian.org/archive/debian/20260727T000000Z/ trixie main\n"
)


class ProvisionLifecycleBehaviorTests(unittest.TestCase):
    def _apt_tree(self, base: Path, apt_rc: int = 0):
        etc = base / "etc"
        sources = etc / "apt" / "sources.list.d"
        sources.mkdir(parents=True)
        (etc / "apt" / "apt.conf.d").mkdir()
        bindir = base / "bin"
        bindir.mkdir()
        apt = bindir / "apt-get"
        fixtures = base / "indextargets"
        fixtures.mkdir()
        log = str(base / "apt.log")
        # Record every call. indextargets reports only the source files apt is
        # actually handed through Dir::Etc::SourceParts and SourceList: each
        # one with a fixture (see _index_targets) yields its targets. apt-get
        # update also records whether the security policy was already written.
        apt.write_text(
            "#!/bin/sh\n"
            f"printf '%s\\n' \"$*\" >> {log!r}\n"
            "if [ \"${1:-}\" = indextargets ]; then\n"
            "  parts=; list=\n"
            "  for arg; do\n"
            "    case \"$arg\" in\n"
            "      Dir::Etc::SourceParts=*) parts=\"${arg#*=}\" ;;\n"
            "      Dir::Etc::SourceList=*) list=\"${arg#*=}\" ;;\n"
            "    esac\n"
            "  done\n"
            "  for source in \"$parts\"/* \"$list\"; do\n"
            f"    fixture={str(fixtures)!r}/\"${{source##*/}}\"\n"
            "    [ -e \"$source\" ] && [ -f \"$fixture\" ] || continue\n"
            "    sed \"s|@SOURCE@|$source|g\" \"$fixture\"\n"
            "  done\n"
            "  exit 0\n"
            "fi\n"
            "if [ \"${1:-}\" = update ]; then\n"
            "  policy=\"$PLEBIAN_OS_APT_ETC_ROOT/apt/apt.conf.d/52plebian-os-security-upgrades\"\n"
            "  if [ -f \"$policy\" ]; then state=yes; else state=no; fi\n"
            f"  printf 'policy-at-update=%s\\n' \"$state\" >> {log!r}\n"
            "fi\n"
            f"exit {apt_rc}\n"
        )
        apt.chmod(0o755)
        # The real tools would read this host's own apt and dpkg state. The
        # real apt-config instead answers from an isolated configuration that
        # holds only the FAKE_* keys, so apt itself reads each spelling;
        # FAKE_APT_CONFIG_FAIL_KEY makes apt-config fail for that one key.
        real_config = shutil.which("apt-config") or "/usr/bin/apt-config"
        isolated = base / "apt-config.conf"
        parts = base / "apt-config.d"
        parts.mkdir()
        config = bindir / "apt-config"
        config.write_text(
            "#!/bin/sh\n"
            "for arg; do\n"
            "  [ \"$arg\" != \"${FAKE_APT_CONFIG_FAIL_KEY:-}/b\" ] || exit 100\n"
            "done\n"
            "{\n"
            f"  printf 'Dir::Etc::main \"%s\";\\nDir::Etc::parts \"%s\";\\n' "
            f"{str(isolated) + '.none'!r} {str(parts)!r}\n"
            "  [ -z \"${FAKE_CHECK_VALID_UNTIL:-}\" ] "
            "|| printf 'Acquire::Check-Valid-Until \"%s\";\\n' \"$FAKE_CHECK_VALID_UNTIL\"\n"
            "  [ -z \"${FAKE_CHECK_DATE:-}\" ] "
            "|| printf 'Acquire::Check-Date \"%s\";\\n' \"$FAKE_CHECK_DATE\"\n"
            f"}} > {str(isolated)!r}\n"
            f"APT_CONFIG={str(isolated)!r} exec {real_config!r} \"$@\"\n"
        )
        config.chmod(0o755)
        query = bindir / "dpkg-query"
        query.write_text("#!/bin/sh\nprintf '%s' \"${FAKE_DPKG_STATUS:-}\"\n")
        query.chmod(0o755)
        env = {
            **os.environ,
            "PATH": f"{bindir}:{os.environ['PATH']}",
            "PLEBIAN_OS_APT_ETC_ROOT": str(etc),
            "PLEBIAN_OS_PROVISION_LIB_ONLY": "1",
        }
        return etc, sources, env

    @staticmethod
    def _index_targets(base: Path, source_name: str, targets: str) -> None:
        """What the apt-get stub reports when it is handed this source file."""
        (base / "indextargets" / source_name).write_text(targets)

    @staticmethod
    def _release_body(base: Path, recorded: bool = True) -> str:
        record = base / "versions.env"
        if recorded:
            record.write_text("PLEBIAN_OS_VERSION=0.2.2\n")
        return (
            "PLEBIAN_OS_RELEASE_MODE=1\n"
            f"APT_INSTALL_RECORD={str(record)!r}\n"
            "PLEBIAN_OS_APT_SNAPSHOT=20260727T000000Z\n"
        )

    @staticmethod
    def _installer_snapshot_state(etc: Path) -> dict[Path, bytes]:
        """First boot's snapshot pin over a Debian Installer sources.list, with
        the global overrides the installer generator and 0.2.1 wrote."""
        apt = etc / "apt"
        state = etc / "plebian-os"
        state.mkdir(exist_ok=True)
        files = {
            apt / "apt.conf": 'Acquire::Check-Valid-Until "false";\n',
            apt / "apt.conf.d" / "99plebian-os-snapshot": 'Acquire::Check-Valid-Until "false";\n',
            apt / "sources.list.plebian-os-disabled": INSTALLER_SOURCES_LIST,
            state / "apt-snapshot-sources": f"{apt / 'sources.list'}\n",
            state / "apt-snapshot": "20260727T000000Z\n",
            apt / "sources.list.d" / "plebian-os-snapshot.sources": (
                "Types: deb\n"
                "URIs: https://snapshot.debian.org/archive/debian/20260727T000000Z\n"
            ),
        }
        for file, text in files.items():
            file.write_text(text)
        return {file: file.read_bytes() for file in files}

    def _assert_snapshot_state_restored(self, etc: Path, before: dict[Path, bytes]):
        for file, content in before.items():
            self.assertEqual(file.read_bytes(), content, file)
        apt = etc / "apt"
        self.assertFalse((apt / "sources.list").exists())
        self.assertFalse((apt / "sources.list.d" / "plebian-os-debian.sources").exists())
        self.assertFalse((apt / "sources.list.plebian-os-installer-snapshot").exists())
        self.assertEqual(list((etc / "plebian-os").glob(".apt-restore.*")), [])
        self.assertEqual(list((etc / "plebian-os").glob(".apt-coverage.*")), [])
        self.assertEqual(list((apt / "sources.list.d").glob(".plebian-os-live.*")), [])

    @staticmethod
    def _tree(root: Path) -> dict[str, bytes | None]:
        return {
            str(item.relative_to(root)): item.read_bytes() if item.is_file() else None
            for item in sorted(root.rglob("*"))
        }

    @staticmethod
    def _apt_updates(base: Path) -> int:
        log = base / "apt.log"
        if not log.exists():
            return 0
        return sum(1 for line in log.read_text().splitlines()
                   if line.split()[:1] == ["update"])

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
                '[ ! -e "$APT_ETC_ROOT/apt/apt.conf.d/99plebian-os-snapshot" ] || exit 97\n'
                "PLEBIAN_OS_APT_SNAPSHOT=\n"
                "configure_apt_snapshot\n",
                env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(operator.read_text(), content)
            self.assertFalse(Path(str(operator) + ".plebian-os-disabled").exists())
            self.assertFalse((etc / "plebian-os" / "apt-snapshot-sources").exists())
            self.assertFalse((sources / "plebian-os-snapshot.sources").exists())
            self.assertFalse((etc / "apt" / "apt.conf.d" / "99plebian-os-snapshot").exists())
            # The operator source provides no live Debian, so the managed one does.
            self.assertTrue((sources / "plebian-os-debian.sources").exists())

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
            override = 'Acquire::Check-Valid-Until "false";\n'
            apt_conf = etc / "apt" / "apt.conf"
            apt_conf.write_text(override)
            legacy_cfg = etc / "apt" / "apt.conf.d" / "99plebian-os-snapshot"
            legacy_cfg.write_text(override)
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
            self.assertEqual(apt_conf.read_text(), override)
            self.assertEqual(legacy_cfg.read_text(), override)

    def test_snapshot_signal_rolls_back_before_exiting(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, sources, env = self._apt_tree(base)
            apt = base / "bin" / "apt-get"
            apt.write_text('#!/bin/sh\nkill -TERM "$PPID"\nexit 1\n')
            apt.chmod(0o755)
            apt_conf = etc / "apt" / "apt.conf"
            apt_conf.write_text('Acquire::Check-Valid-Until "false";\n')
            live = sources / "debian.sources"
            content = "Types: deb\nURIs: https://deb.debian.org/debian\n"
            live.write_text(content)
            result = self._run_library(
                "PLEBIAN_OS_APT_SNAPSHOT=20260712T000000Z\nconfigure_apt_snapshot\n",
                env,
            )
            self.assertEqual(result.returncode, 143, result.stderr)
            self.assertEqual(live.read_text(), content)
            self.assertEqual(apt_conf.read_text(), 'Acquire::Check-Valid-Until "false";\n')
            self.assertFalse(Path(str(live) + ".plebian-os-disabled").exists())
            self.assertFalse((etc / "plebian-os" / "apt-snapshot-sources").exists())
            self.assertFalse((sources / "plebian-os-snapshot.sources").exists())

    def test_snapshot_stanzas_disable_validity_only_per_source(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, sources, env = self._apt_tree(base)
            apt_conf = etc / "apt" / "apt.conf"
            apt_conf.write_text('Acquire::Check-Valid-Until "false";\n')
            result = self._run_library(
                self._release_body(base, recorded=False)
                + "configure_apt_snapshot\n"
                'printf "phase=%s\\n" "$APT_PROVENANCE_PHASE"\n',
                env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            snapshot = (sources / "plebian-os-snapshot.sources").read_text()
            self.assertEqual(snapshot.count("\nCheck-Valid-Until: no\n"), 2)
            self.assertFalse((etc / "apt" / "apt.conf.d" / "99plebian-os-snapshot").exists())
            self.assertFalse(apt_conf.exists())
            self.assertIn("phase=install", result.stdout)

    def test_operator_apt_conf_lines_survive_validity_override_removal(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, _sources, env = self._apt_tree(base)
            apt_conf = etc / "apt" / "apt.conf"
            apt_conf.write_text('APT::Foo "1";\nAcquire::Check-Valid-Until "false";\n')
            apt_conf.chmod(0o640)
            result = self._run_library(
                "PLEBIAN_OS_APT_SNAPSHOT=20260712T000000Z\nconfigure_apt_snapshot\n",
                env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(apt_conf.read_text(), 'APT::Foo "1";\n')
            self.assertEqual(stat.S_IMODE(apt_conf.stat().st_mode), 0o640)

    def test_release_reprovision_never_repins_after_install(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, sources, env = self._apt_tree(base)
            live = sources / "debian.sources"
            content = (
                "Types: deb\nURIs: https://deb.debian.org/debian\n"
                "Suites: trixie trixie-updates\nComponents: main\n\n"
                "Types: deb\nURIs: https://security.debian.org/debian-security\n"
                "Suites: trixie-security\nComponents: main\n"
            )
            live.write_text(content)
            self._index_targets(base, live.name, LIVE_DEBIAN_TARGETS)
            result = self._run_library(
                self._release_body(base)
                + "APT_PROVENANCE_PHASE=unset\n"
                "configure_apt_snapshot\n"
                'printf "phase=%s\\n" "$APT_PROVENANCE_PHASE"\n',
                env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((sources / "plebian-os-snapshot.sources").exists())
            self.assertEqual(list(etc.rglob("*.plebian-os-disabled")), [])
            self.assertEqual(live.read_text(), content)
            self.assertFalse((sources / "plebian-os-debian.sources").exists())
            self.assertIn("phase=lifetime", result.stdout)
            self.assertEqual(self._apt_updates(base), 0)

    def test_installer_snapshot_sources_list_is_retired_not_restored(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, sources, env = self._apt_tree(base)
            before = self._installer_snapshot_state(etc)
            result = self._run_library(
                self._release_body(base) + "configure_apt_snapshot\n", env
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            apt = etc / "apt"
            self.assertFalse((apt / "sources.list").exists())
            self.assertFalse((apt / "sources.list.plebian-os-disabled").exists())
            self.assertEqual(
                (apt / "sources.list.plebian-os-installer-snapshot").read_bytes(),
                before[apt / "sources.list.plebian-os-disabled"],
            )
            for gone in (etc / "plebian-os" / "apt-snapshot-sources",
                         etc / "plebian-os" / "apt-snapshot",
                         sources / "plebian-os-snapshot.sources"):
                self.assertFalse(gone.exists(), gone)
            managed = (sources / "plebian-os-debian.sources").read_text()
            for expected in (
                "URIs: https://deb.debian.org/debian\n",
                "Suites: trixie trixie-updates\n",
                "URIs: https://security.debian.org/debian-security\n",
                "Suites: trixie-security\n",
            ):
                self.assertIn(expected, managed)
            self.assertNotIn("Check-Valid-Until", managed)
            self.assertEqual(self._apt_updates(base), 1)

    def test_operator_sources_disabled_by_the_snapshot_are_restored(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, sources, env = self._apt_tree(base)
            self._installer_snapshot_state(etc)
            chrome = sources / "google-chrome.sources"
            chrome_content = (
                "Types: deb\nURIs: https://dl.google.com/linux/chrome/deb/\n"
                "Suites: stable\nComponents: main\n"
            )
            Path(str(chrome) + ".plebian-os-disabled").write_text(chrome_content)
            (etc / "plebian-os" / "apt-snapshot-sources").write_text(
                f"{chrome}\n{etc / 'apt' / 'sources.list'}\n"
            )
            result = self._run_library(
                self._release_body(base) + "configure_apt_snapshot\n", env
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(chrome.read_text(), chrome_content)
            self.assertFalse(Path(str(chrome) + ".plebian-os-disabled").exists())
            self.assertFalse((etc / "apt" / "sources.list").exists())
            self.assertEqual(
                (etc / "apt" / "sources.list.plebian-os-installer-snapshot").read_text(),
                INSTALLER_SOURCES_LIST,
            )
            self.assertTrue((sources / "plebian-os-debian.sources").exists())

    def test_hand_unpinned_release_machine_converges_idempotently(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, sources, env = self._apt_tree(base)
            before = self._installer_snapshot_state(etc)
            # The administrator restored live Debian by hand and moved the
            # snapshot source out of apt's directories; no apt.conf remains.
            (sources / "plebian-os-snapshot.sources").unlink()
            (etc / "apt" / "apt.conf").unlink()
            live = sources / "debian.sources"
            content = (
                "Types: deb\nURIs: https://deb.debian.org/debian\n"
                "Suites: trixie trixie-updates\nComponents: main\n\n"
                "Types: deb\nURIs: https://security.debian.org/debian-security\n"
                "Suites: trixie-security\nComponents: main\n"
            )
            live.write_text(content)
            self._index_targets(base, live.name, LIVE_DEBIAN_TARGETS)
            body = self._release_body(base) + "configure_apt_snapshot\n"

            first = self._run_library(body, env)
            self.assertEqual(first.returncode, 0, first.stderr)
            apt = etc / "apt"
            self.assertEqual(live.read_text(), content)
            self.assertFalse((sources / "plebian-os-debian.sources").exists())
            self.assertEqual(
                (apt / "sources.list.plebian-os-installer-snapshot").read_bytes(),
                before[apt / "sources.list.plebian-os-disabled"],
            )
            self.assertFalse((apt / "sources.list.plebian-os-disabled").exists())
            self.assertFalse((etc / "plebian-os" / "apt-snapshot-sources").exists())
            self.assertEqual(self._apt_updates(base), 1)
            converged = self._tree(etc)

            second = self._run_library(body, env)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(self._tree(etc), converged)
            self.assertEqual(self._apt_updates(base), 1)

    def test_live_switch_refuses_a_remaining_global_validity_override(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, _sources, env = self._apt_tree(base)
            before = self._installer_snapshot_state(etc)
            env["FAKE_CHECK_VALID_UNTIL"] = "false"
            result = self._run_library(
                self._release_body(base) + "configure_apt_snapshot\n", env
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Check-Valid-Until", result.stderr)
            self.assertIn("the previous snapshot configuration was restored", result.stderr)
            self._assert_snapshot_state_restored(etc, before)
            self.assertEqual(self._apt_updates(base), 0)

    def test_live_switch_refuses_apts_other_false_spellings(self):
        for spelling in ("Disable", "0", "without"):
            with self.subTest(spelling=spelling), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                etc, _sources, env = self._apt_tree(base)
                before = self._installer_snapshot_state(etc)
                env["FAKE_CHECK_VALID_UNTIL"] = spelling
                result = self._run_library(
                    self._release_body(base) + "configure_apt_snapshot\n", env
                )
                self.assertNotEqual(result.returncode, 0)
                self._assert_snapshot_state_restored(etc, before)

    def test_live_switch_signal_rolls_back(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, _sources, env = self._apt_tree(base)
            before = self._installer_snapshot_state(etc)
            # The guard runs in a command substitution, whose parent is a
            # subshell; signal the provisioner itself.
            config = base / "bin" / "apt-config"
            config.write_text('#!/bin/sh\nkill -TERM "$PLEBIAN_OS_TEST_SIGNAL_PID"\n')
            result = self._run_library(
                "export PLEBIAN_OS_TEST_SIGNAL_PID=$$\n"
                + self._release_body(base)
                + "configure_apt_snapshot\n",
                env,
            )
            self.assertEqual(result.returncode, 143, result.stderr)
            self._assert_snapshot_state_restored(etc, before)

    def test_live_switch_retirement_conflict_preflights(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, sources, env = self._apt_tree(base)
            before = self._installer_snapshot_state(etc)
            retired = etc / "apt" / "sources.list.plebian-os-installer-snapshot"
            retired.write_text("# a different retired source\n")
            result = self._run_library(
                self._release_body(base) + "configure_apt_snapshot\n", env
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("both", result.stderr)
            for file, content in before.items():
                self.assertEqual(file.read_bytes(), content, file)
            self.assertEqual(retired.read_text(), "# a different retired source\n")
            self.assertFalse((sources / "plebian-os-debian.sources").exists())

    def test_live_switch_update_failure_keeps_live_sources(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, sources, env = self._apt_tree(base, apt_rc=1)
            self._installer_snapshot_state(etc)
            result = self._run_library(
                self._release_body(base) + "configure_apt_snapshot\n", env
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("apt-get update against live Debian failed", result.stderr)
            self.assertTrue((sources / "plebian-os-debian.sources").exists())
            self.assertTrue(
                (etc / "apt" / "sources.list.plebian-os-installer-snapshot").exists()
            )
            self.assertFalse((sources / "plebian-os-snapshot.sources").exists())
            self.assertEqual(self._apt_updates(base), 1)

    def test_dev_snapshot_off_on_iso_machine_no_longer_restores_snapshot_base(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, sources, env = self._apt_tree(base)
            self._installer_snapshot_state(etc)
            override = 'Acquire::Check-Valid-Until "false";\n'
            apt_conf = etc / "apt" / "apt.conf"
            apt_conf.write_text(override)
            legacy_cfg = etc / "apt" / "apt.conf.d" / "99plebian-os-snapshot"
            legacy_cfg.write_text(override)
            result = self._run_library(
                "PLEBIAN_OS_RELEASE_MODE=0\nPLEBIAN_OS_APT_SNAPSHOT=\nconfigure_apt_snapshot\n",
                env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((etc / "apt" / "sources.list").exists())
            self.assertEqual(
                (etc / "apt" / "sources.list.plebian-os-installer-snapshot").read_text(),
                INSTALLER_SOURCES_LIST,
            )
            self.assertTrue((sources / "plebian-os-debian.sources").exists())
            self.assertFalse(apt_conf.exists())
            self.assertFalse(legacy_cfg.exists())

    def test_security_upgrade_policy_is_security_only_without_reboot(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, _sources, env = self._apt_tree(base)
            policy = etc / "apt" / "apt.conf.d" / "52plebian-os-security-upgrades"
            # Written whether or not unattended-upgrades is installed yet: it is
            # inert without the package and pre-empts the package's defaults.
            result = self._run_library("DRY_RUN=0\ninstall_security_upgrade_policy\n", env)
            self.assertEqual(result.returncode, 0, result.stderr)
            text = policy.read_text()
            for expected in (
                "#clear Unattended-Upgrade::Origins-Pattern;",
                '"origin=Debian,codename=${distro_codename}-security,label=Debian-Security";',
                'Unattended-Upgrade::Automatic-Reboot "false";',
                'APT::Periodic::Update-Package-Lists "1";',
                'APT::Periodic::Unattended-Upgrade "1";',
            ):
                self.assertIn(expected, text)
            self.assertNotIn('label=Debian"', text)
            self.assertEqual(stat.S_IMODE(policy.stat().st_mode), 0o644)

            again = self._run_library("DRY_RUN=0\ninstall_security_upgrade_policy\n", env)
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertEqual(policy.read_text(), text)
            self.assertEqual([path.name for path in policy.parent.iterdir()], [policy.name])

    def test_release_apt_moves_live_only_after_the_provision_commit(self):
        source = PROVISION.read_text()
        committed = source.rindex("\ncommit_provision_root_transaction\n")
        finished = source.rindex("\nfinish_release_apt_install\n")
        released = source.rindex("\ncleanup\ntrap - EXIT INT TERM HUP\n")
        self.assertLess(committed, finished)
        self.assertLess(finished, released)
        self.assertIn("--reconcile-apt-sources) RECONCILE_APT_ONLY=1; shift ;;", source)
        handler = source.index('if [ "$RECONCILE_APT_ONLY" = 1 ]; then')
        self.assertLess(source.index('die "must run as root'), handler)
        self.assertLess(handler, source.rindex("\nallocate_coordinated_private_storage\n"))
        self.assertIn(
            'if [ "$RECONCILE_APT_ONLY" = 1 ]; then\n'
            "    reconcile_apt_sources_and_exit\nfi\n",
            source,
        )
        self.assertLess(handler, source.index("# ── resolve the target user"))

    def test_lifetime_phase_writes_the_security_policy_before_live_sources(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, sources, env = self._apt_tree(base)
            self._installer_snapshot_state(etc)
            result = self._run_library(
                self._release_body(base) + "configure_apt_snapshot\n", env
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((sources / "plebian-os-debian.sources").exists())
            policy = etc / "apt" / "apt.conf.d" / "52plebian-os-security-upgrades"
            self.assertIn("label=Debian-Security", policy.read_text())
            # apt-get update runs only after the live sources are in place.
            self.assertIn("policy-at-update=yes", (base / "apt.log").read_text())
            self.assertNotIn("policy-at-update=no", (base / "apt.log").read_text())

    def test_security_policy_remains_when_the_switch_fails_after_activation(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, _sources, env = self._apt_tree(base)
            before = self._installer_snapshot_state(etc)
            # The replay-protection guard runs once the live source is in place.
            env["FAKE_CHECK_VALID_UNTIL"] = "false"
            result = self._run_library(
                self._release_body(base) + "finish_release_apt_install\n", env
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("the previous snapshot configuration was restored", result.stderr)
            self._assert_snapshot_state_restored(etc, before)
            self.assertTrue(
                (etc / "apt" / "apt.conf.d" / "52plebian-os-security-upgrades").is_file()
            )

    def test_finish_release_apt_install_moves_a_committed_release_to_live_debian(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, sources, env = self._apt_tree(base)
            before = self._installer_snapshot_state(etc)
            result = self._run_library(
                self._release_body(base) + "finish_release_apt_install\n", env
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            apt = etc / "apt"
            self.assertFalse((apt / "sources.list").exists())
            self.assertFalse((apt / "sources.list.plebian-os-disabled").exists())
            self.assertEqual(
                (apt / "sources.list.plebian-os-installer-snapshot").read_bytes(),
                before[apt / "sources.list.plebian-os-disabled"],
            )
            self.assertIn(
                "URIs: https://security.debian.org/debian-security\n",
                (sources / "plebian-os-debian.sources").read_text(),
            )
            for gone in (sources / "plebian-os-snapshot.sources",
                         apt / "apt.conf",
                         apt / "apt.conf.d" / "99plebian-os-snapshot",
                         etc / "plebian-os" / "apt-snapshot",
                         etc / "plebian-os" / "apt-snapshot-sources"):
                self.assertFalse(gone.exists(), gone)
            self.assertTrue((apt / "apt.conf.d" / "52plebian-os-security-upgrades").is_file())
            self.assertEqual(self._apt_updates(base), 1)

    def test_finish_release_apt_install_is_a_no_op_outside_release_mode(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, _sources, env = self._apt_tree(base)
            self._installer_snapshot_state(etc)
            tree = self._tree(etc)
            result = self._run_library(
                self._release_body(base)
                + "PLEBIAN_OS_RELEASE_MODE=0\nfinish_release_apt_install\n",
                env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self._tree(etc), tree)
            self.assertFalse((base / "apt.log").exists())

    def test_reconcile_apt_sources_handler_changes_only_apt_and_exits(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, sources, env = self._apt_tree(base)
            self._installer_snapshot_state(etc)
            tree = self._tree(etc)
            handler = "reconcile_apt_sources_and_exit\necho FELL_THROUGH\n"

            unrecorded = self._run_library(
                self._release_body(base, recorded=False) + handler, env
            )
            self.assertNotEqual(unrecorded.returncode, 0)
            self.assertIn(
                "refusing to leave the install snapshot before an install closure is recorded",
                unrecorded.stderr,
            )
            self.assertNotIn("FELL_THROUGH", unrecorded.stdout)
            self.assertEqual(self._tree(etc), tree)

            development = self._run_library(
                self._release_body(base) + "PLEBIAN_OS_RELEASE_MODE=0\n" + handler, env
            )
            self.assertEqual(development.returncode, 0, development.stderr)
            self.assertIn("apt sources are left as configured", development.stdout)
            self.assertNotIn("FELL_THROUGH", development.stdout)
            self.assertEqual(self._tree(etc), tree)

            recorded = self._run_library(self._release_body(base) + handler, env)
            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            self.assertNotIn("FELL_THROUGH", recorded.stdout)
            self.assertTrue((sources / "plebian-os-debian.sources").exists())
            self.assertTrue(
                (etc / "apt" / "sources.list.plebian-os-installer-snapshot").exists()
            )

    def test_manifest_gate_uses_the_phase_configure_apt_snapshot_chose(self):
        source = PROVISION.read_text()
        manifest = source[source.index("\nwrite_source_tool_manifest() {\n"):]
        self.assertIn(
            'require_release_apt_provenance "$sources_tmp" "$versions_tmp"',
            manifest[:manifest.index("\n}\n")],
        )
        for recorded, violation in (
            (False, "release install closure resolved from an index other than "
                    "snapshot 20260727T000000Z"),
            (True, ""),
        ):
            with self.subTest(recorded=recorded), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                _etc, _sources, env = self._apt_tree(base)
                index = base / "apt-sources.list"
                index.write_text("https://deb.debian.org/debian trixie main amd64\n")
                result = self._run_library(
                    self._release_body(base, recorded=recorded)
                    + "configure_apt_snapshot\n"
                    'printf "violation=[%s]\\n" '
                    f'"$(release_apt_provenance_violation {str(index)!r})"\n',
                    env,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"violation=[{violation}]", result.stdout)

    def test_live_switch_refuses_a_global_check_date_override(self):
        # apt reads a signed or space-padded zero as false as well.
        for spelling in ("false", "No", "0x0", "+0", "-0", " 0"):
            with self.subTest(spelling=spelling), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                etc, _sources, env = self._apt_tree(base)
                before = self._installer_snapshot_state(etc)
                env["FAKE_CHECK_DATE"] = spelling
                result = self._run_library(
                    self._release_body(base) + "configure_apt_snapshot\n", env
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("a global Acquire::Check-Date disables replay protection",
                              result.stderr)
                self._assert_snapshot_state_restored(etc, before)
                self.assertEqual(self._apt_updates(base), 0)

    def test_live_switch_refuses_a_restored_deb822_source_that_disables_trust(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, sources, env = self._apt_tree(base)
            before = self._installer_snapshot_state(etc)
            operator = sources / "debian.sources"
            backup = Path(str(operator) + ".plebian-os-disabled")
            backup.write_text(
                "# Debian, maintained by hand\n\n"
                "Types: deb\nURIs: https://deb.debian.org/debian\n"
                "Suites: trixie trixie-updates\nComponents: main\n\n"
                "# security\n"
                "Types: deb\nURIs: https://security.debian.org/debian-security\n"
                "Suites: trixie-security\nComponents: main\nTrusted: yes\n"
            )
            inventory = etc / "plebian-os" / "apt-snapshot-sources"
            inventory.write_text(f"{operator}\n{etc / 'apt' / 'sources.list'}\n")
            before = {path: path.read_bytes() for path in (*before, backup)}
            self._index_targets(base, operator.name, LIVE_DEBIAN_TARGETS)
            result = self._run_library(
                self._release_body(base) + "configure_apt_snapshot\n", env
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(f"{operator} (entry 2) disables signature or replay checks",
                          result.stderr)
            self._assert_snapshot_state_restored(etc, before)
            self.assertFalse(operator.exists())
            self.assertEqual(self._apt_updates(base), 0)

    def test_live_switch_refuses_a_one_line_source_that_disables_replay_checks(self):
        # Each option turns a check off for its own entry; apt reads +1 as yes.
        for entry, options in ((2, "arch=amd64 check-valid-until=no"),
                               (3, "check-date=no"),
                               (1, "trusted=+1"),
                               (1, "allow-insecure=yes")):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                etc, sources, env = self._apt_tree(base)
                before = self._installer_snapshot_state(etc)
                operator = sources / "debian.list"
                lines = [
                    "deb http://deb.debian.org/debian trixie main",
                    "deb http://deb.debian.org/debian trixie-updates main",
                    "deb http://security.debian.org/debian-security trixie-security main",
                ]
                lines[entry - 1] = lines[entry - 1].replace("deb ", f"deb [ {options} ] ", 1)
                content = "".join(f"{line}\n" for line in lines)
                operator.write_text(content)
                self._index_targets(
                    base, operator.name,
                    "http://deb.debian.org/debian trixie main @SOURCE@:1\n"
                    "http://deb.debian.org/debian trixie-updates main @SOURCE@:2\n"
                    "http://security.debian.org/debian-security trixie-security main @SOURCE@:3\n",
                )
                result = self._run_library(
                    self._release_body(base) + "configure_apt_snapshot\n", env
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f"{operator} (entry {entry}) disables signature or replay checks",
                              result.stderr)
                self._assert_snapshot_state_restored(etc, before)
                self.assertEqual(operator.read_text(), content)
                self.assertEqual(self._apt_updates(base), 0)

    def test_sources_that_keep_apt_checks_on_still_count_as_live_coverage(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, sources, env = self._apt_tree(base)
            operator = sources / "debian.list"
            # apt reads a signed zero as false, so allow-weak=+0 keeps checks on.
            operator.write_text(
                "deb [check-valid-until=yes trusted=no] http://deb.debian.org/debian trixie main\n"
                "deb [ allow-weak=+0 ] http://deb.debian.org/debian trixie-updates main\n"
                "deb http://security.debian.org/debian-security trixie-security main\n"
            )
            self._index_targets(
                base, operator.name,
                "http://deb.debian.org/debian trixie main @SOURCE@:1\n"
                "http://deb.debian.org/debian trixie-updates main @SOURCE@:2\n"
                "http://security.debian.org/debian-security trixie-security main @SOURCE@:3\n",
            )
            result = self._run_library(
                self._release_body(base) + "configure_apt_snapshot\n", env
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((sources / "plebian-os-debian.sources").exists())

    def test_operator_sources_without_point_release_updates_get_the_managed_source(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, sources, env = self._apt_tree(base)
            operator = sources / "debian.list"
            content = (
                "deb http://deb.debian.org/debian trixie main\n"
                "deb http://security.debian.org/debian-security trixie-security main\n"
            )
            operator.write_text(content)
            self._index_targets(
                base, operator.name,
                "http://deb.debian.org/debian trixie main @SOURCE@:1\n"
                "http://security.debian.org/debian-security trixie-security main @SOURCE@:2\n",
            )
            result = self._run_library(
                self._release_body(base) + "configure_apt_snapshot\n", env
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(operator.read_text(), content)
            self.assertIn("Suites: trixie trixie-updates\n",
                          (sources / "plebian-os-debian.sources").read_text())

    def test_live_switch_refuses_when_apt_config_is_unavailable(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, _sources, env = self._apt_tree(base)
            before = self._installer_snapshot_state(etc)
            result = self._run_library(
                'command() { [ "$*" != "-v apt-config" ] || return 1; builtin command "$@"; }\n'
                + self._release_body(base)
                + "configure_apt_snapshot\n",
                env,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("apt-config is unavailable", result.stderr)
            self._assert_snapshot_state_restored(etc, before)

    def test_managed_live_source_alone_is_never_operator_coverage(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, sources, env = self._apt_tree(base)
            managed = sources / "plebian-os-debian.sources"
            body = self._release_body(base) + "configure_apt_snapshot\n"
            first = self._run_library(body, env)
            self.assertEqual(first.returncode, 0, first.stderr)
            content = managed.read_bytes()
            self.assertEqual([path.name for path in sources.iterdir()], [managed.name])
            # Handed to apt, the managed file would read as complete coverage.
            self._index_targets(base, managed.name, LIVE_DEBIAN_TARGETS)
            (base / "apt.log").unlink()

            second = self._run_library(body, env)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(managed.read_bytes(), content)
            self.assertEqual(self._apt_updates(base), 0)
            coverage = self._run_library(
                '_live_debian_coverage_complete trixie || exit "$?"\n', env
            )
            self.assertEqual(coverage.returncode, 1, coverage.stderr)

    def test_unmarked_inventoried_sources_list_is_restored_not_retired(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, _sources, env = self._apt_tree(base)
            self._installer_snapshot_state(etc)
            apt = etc / "apt"
            operator = "deb https://deb.debian.org/debian trixie main\n"
            (apt / "sources.list.plebian-os-disabled").write_text(operator)
            result = self._run_library(
                self._release_body(base) + "configure_apt_snapshot\n", env
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((apt / "sources.list").read_text(), operator)
            self.assertFalse((apt / "sources.list.plebian-os-disabled").exists())
            self.assertFalse((apt / "sources.list.plebian-os-installer-snapshot").exists())

    @unittest.skipIf(os.geteuid() == 0, "root ignores directory permissions")
    def test_live_switch_staging_failure_dies_without_leaking_files(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, sources, env = self._apt_tree(base)
            before = self._installer_snapshot_state(etc)
            sources.chmod(0o555)
            try:
                result = self._run_library(
                    self._release_body(base) + "finish_release_apt_install\n", env
                )
            finally:
                sources.chmod(0o755)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("could not stage the live Debian source; apt was not changed",
                          result.stderr)
            self._assert_snapshot_state_restored(etc, before)
            self.assertEqual(self._apt_updates(base), 0)

    @unittest.skipIf(os.geteuid() == 0, "root ignores directory permissions")
    def test_snapshot_staging_failure_dies_without_leaking_files(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, sources, env = self._apt_tree(base)
            live = sources / "debian.sources"
            content = "Types: deb\nURIs: https://deb.debian.org/debian\n"
            live.write_text(content)
            sources.chmod(0o555)
            try:
                result = self._run_library(
                    "PLEBIAN_OS_APT_SNAPSHOT=20260712T000000Z\nconfigure_apt_snapshot\n", env
                )
            finally:
                sources.chmod(0o755)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("could not stage the apt snapshot source; apt was not changed",
                          result.stderr)
            self.assertEqual(live.read_text(), content)
            self.assertEqual(sorted(path.name for path in sources.iterdir()), [live.name])
            self.assertEqual(
                [path.name for path in (etc / "plebian-os").iterdir()],
                [".apt-sources.lock"],
            )

    def test_manifest_gate_dies_on_a_violation_and_removes_both_staged_files(self):
        for recorded, violation in (
            (False, "release install closure resolved from an index other than "
                    "snapshot 20260727T000000Z"),
            (True, None),
        ):
            with self.subTest(recorded=recorded), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                _etc, _sources, env = self._apt_tree(base)
                index = base / ".apt-sources.list.staged"
                index.write_text("https://deb.debian.org/debian trixie main amd64\n")
                versions = base / ".versions.env.staged"
                versions.write_text("# staged provenance\n")
                result = self._run_library(
                    self._release_body(base, recorded=recorded)
                    + "configure_apt_snapshot\n"
                    f"require_release_apt_provenance {str(index)!r} {str(versions)!r}\n"
                    "echo GATE_PASSED\n",
                    env,
                )
                if violation is None:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("GATE_PASSED", result.stdout)
                    self.assertTrue(index.exists())
                    self.assertTrue(versions.exists())
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(violation, result.stderr)
                    self.assertNotIn("GATE_PASSED", result.stdout)
                    self.assertFalse(index.exists())
                    self.assertFalse(versions.exists())

    def test_live_switch_refuses_when_apt_config_fails_for_one_key(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, _sources, env = self._apt_tree(base)
            before = self._installer_snapshot_state(etc)
            env["FAKE_APT_CONFIG_FAIL_KEY"] = "Acquire::Check-Date"
            result = self._run_library(
                self._release_body(base) + "configure_apt_snapshot\n", env
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("apt-config could not read Acquire::Check-Date", result.stderr)
            self.assertIn("the previous snapshot configuration was restored", result.stderr)
            self._assert_snapshot_state_restored(etc, before)
            self.assertEqual(self._apt_updates(base), 0)

    @unittest.skipIf(os.geteuid() == 0, "root reads files regardless of mode")
    def test_live_switch_refuses_an_operator_source_it_cannot_read(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, sources, env = self._apt_tree(base)
            before = self._installer_snapshot_state(etc)
            operator = sources / "debian.list"
            content = (
                "deb http://deb.debian.org/debian trixie main\n"
                "deb http://deb.debian.org/debian trixie-updates main\n"
                "deb http://security.debian.org/debian-security trixie-security main\n"
            )
            operator.write_text(content)
            self._index_targets(
                base, operator.name,
                "http://deb.debian.org/debian trixie main @SOURCE@:1\n"
                "http://deb.debian.org/debian trixie-updates main @SOURCE@:2\n"
                "http://security.debian.org/debian-security trixie-security main @SOURCE@:3\n",
            )
            # apt can list it, but its options cannot be checked: fail closed.
            operator.chmod(0)
            try:
                result = self._run_library(
                    self._release_body(base) + "configure_apt_snapshot\n", env
                )
            finally:
                operator.chmod(0o644)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(f"{operator} (entry 1) disables signature or replay checks",
                          result.stderr)
            self._assert_snapshot_state_restored(etc, before)
            self.assertEqual(operator.read_text(), content)
            self.assertEqual(self._apt_updates(base), 0)

    @unittest.skipIf(os.geteuid() == 0, "root reads files regardless of mode")
    def test_live_switch_backup_failure_dies_without_leaking_files(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, _sources, env = self._apt_tree(base)
            before = self._installer_snapshot_state(etc)
            tree = self._tree(etc)
            cfg = etc / "apt" / "apt.conf.d" / "99plebian-os-snapshot"
            cfg.chmod(0)
            try:
                result = self._run_library(
                    self._release_body(base) + "finish_release_apt_install\n", env
                )
            finally:
                cfg.chmod(0o644)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "could not stage the move to live Debian sources; apt was not changed",
                result.stderr,
            )
            self._assert_snapshot_state_restored(etc, before)
            # Only the inert security policy and the lock file, both written
            # before staging, are new.
            after = self._tree(etc)
            after.pop("apt/apt.conf.d/52plebian-os-security-upgrades")
            after.pop("plebian-os/.apt-sources.lock")
            self.assertEqual(after, tree)
            self.assertEqual(self._apt_updates(base), 0)

    @unittest.skipIf(os.geteuid() == 0, "root reads files regardless of mode")
    def test_snapshot_backup_failure_dies_without_leaking_files(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, sources, env = self._apt_tree(base)
            (sources / "debian.sources").write_text(
                "Types: deb\nURIs: https://deb.debian.org/debian\n")
            aptconf = etc / "apt" / "apt.conf"
            aptconf.write_text('APT::Keep "1";\n')
            tree = self._tree(etc)
            aptconf.chmod(0)
            try:
                result = self._run_library(
                    "PLEBIAN_OS_APT_SNAPSHOT=20260712T000000Z\nconfigure_apt_snapshot\n", env
                )
            finally:
                aptconf.chmod(0o644)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "could not stage the apt snapshot configuration; apt was not changed",
                result.stderr,
            )
            after = self._tree(etc)
            self.assertEqual(after.pop("plebian-os"), None)
            self.assertEqual(after.pop("plebian-os/.apt-sources.lock"), b"")
            self.assertEqual(after, tree)
            self.assertEqual(self._apt_updates(base), 0)

    def test_security_policy_write_failure_stops_before_live_sources(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, _sources, env = self._apt_tree(base)
            before = self._installer_snapshot_state(etc)
            # A directory in the policy's place makes the final rename fail.
            policy = etc / "apt" / "apt.conf.d" / "52plebian-os-security-upgrades"
            policy.mkdir()
            result = self._run_library(
                self._release_body(base) + "finish_release_apt_install\n", env
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(f"could not write {policy}; apt sources were not changed",
                          result.stderr)
            self.assertEqual(list(policy.iterdir()), [])
            self.assertEqual(
                list(policy.parent.glob(".plebian-os-security-upgrades.*")), [])
            self._assert_snapshot_state_restored(etc, before)
            self.assertFalse((base / "apt.log").exists())

    def test_finish_release_apt_install_waits_for_the_apt_sources_lock(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            etc, _sources, env = self._apt_tree(base)
            before = self._installer_snapshot_state(etc)
            lock = etc / "plebian-os" / ".apt-sources.lock"
            # Another apt source change holds the lock for the whole run.
            with lock.open("w") as held:
                fcntl.flock(held, fcntl.LOCK_EX)
                tree = self._tree(etc)
                result = self._run_library(
                    self._release_body(base)
                    + "APT_SOURCES_LOCK_TIMEOUT=1\nfinish_release_apt_install\n",
                    env,
                )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("another Plebian-OS apt source change is in progress", result.stderr)
            self._assert_snapshot_state_restored(etc, before)
            # The inert security policy is written before the lock is taken.
            after = self._tree(etc)
            after.pop("apt/apt.conf.d/52plebian-os-security-upgrades")
            self.assertEqual(after, tree)
            self.assertFalse((base / "apt.log").exists())

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
        self.assertIn(
            "verify staged uv --version reports pinned uv 0.9.0",
            valid.stdout,
        )

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

    def test_0_2_1_release_requires_the_waydroid_first_use_helper(self):
        ref = "a" * 40
        digest = "b" * 64
        env = {
            **os.environ,
            "PLEBIAN_OS_PROVISION_LIB_ONLY": "1",
            "PLEBIAN_OS_RELEASE": "0.2.1",
            "PLEBIAN_OS_RELEASE_MODE": "1",
            "PLEBIAN_OS_REF": ref,
            "PLEB_REF": ref,
            "KILIX_REF": ref,
            "KILIX95_REF": ref,
            "KILIX_SYSTEM_MONITOR_REF": ref,
            "KILIX_DESKTOP_SDK_REF": ref,
            "KILIX_ICEWM_REF": ref,
            "KILIX_MEDIA_SDK_REF": ref,
            "KILIX_WAYDROID_REF": ref,
            "KILIX_PREBUILT_SHA256": digest,
            "PLEBIAN_OS_KILIX_GO_VERSION": "go1.26.5",
            "PLEBIAN_OS_KILIX_GO_SHA256_AMD64": digest,
            "PLEBIAN_OS_KILIX_GO_SHA256_ARM64": digest,
            "PLEBIAN_OS_INSTALL_WAYDROID": "1",
            "PLEBIAN_OS_WAYDROID_CLOSURE_SHA256": digest,
        }
        valid = self._run_library("validate_release_inputs\n", env)
        self.assertEqual(valid.returncode, 0, valid.stderr)

        refused = self._run_library(
            "validate_release_inputs\n",
            {
                **env,
                "PLEBIAN_OS_INSTALL_WAYDROID": "0",
                "PLEBIAN_OS_WAYDROID_CLOSURE_SHA256": "",
            },
        )
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn(
            "0.2.1 release mode requires PLEBIAN_OS_INSTALL_WAYDROID=1",
            refused.stderr,
        )

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
        env = os.environ.copy()
        for key in self.PINS:
            env.pop(key, None)
        return subprocess.run(
            ["bash", "-c", script], text=True, capture_output=True,
            check=False, env=env)

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
