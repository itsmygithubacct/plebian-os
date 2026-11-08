"""Offline install: an install made with no network package source.

The 0.2.3 offline persona failed three ways: pkgsel stopped the install because
its package list needs a mirror, nothing configured the network when it was
restored, and the enabled CD-ROM apt entry failed every provisioning attempt.
"""
import os
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "provision" / "plebian-os-offline-install"
PRESEED = ROOT / "preseed" / "preseed.cfg"
REMASTER = ROOT / "build" / "remaster-iso.sh"
PROVISION = ROOT / "provision" / "plebian-os-provision.sh"

HOOK_INSTALL = ("install -m 0755 /cdrom/plebian-os/plebian-os-offline-install "
                "/usr/lib/pre-pkgsel.d/05plebian-os-offline")

# What Debian Installer's apt-setup leaves in the target before pkgsel.
OFFLINE_SOURCES_LIST = textwrap.dedent("""\
    #deb cdrom:[Plebian-OS 0.2.3 amd64 installer]/ trixie main non-free-firmware

    deb cdrom:[Plebian-OS 0.2.3 amd64 installer]/ trixie main non-free-firmware

    # Line commented out by installer because it failed to verify:
    #deb http://security.debian.org/debian-security trixie-security main non-free-firmware
    # Line commented out by installer because it failed to verify:
    #deb-src http://security.debian.org/debian-security trixie-security main non-free-firmware
    """)
MIRROR_SOURCES_LIST = textwrap.dedent("""\
    #deb cdrom:[Plebian-OS 0.2.3 amd64 installer]/ trixie main non-free-firmware

    deb http://deb.debian.org/debian/ trixie main non-free-firmware contrib non-free
    deb-src http://deb.debian.org/debian/ trixie main non-free-firmware contrib non-free

    deb http://security.debian.org/debian-security trixie-security main non-free-firmware contrib non-free
    """)

FAKE_CONFMODULE = textwrap.dedent("""\
    db_set() { printf '%s=[%s]\\n' "$1" "$2" >> "$FAKE_DEBCONF_LOG"; }
    db_get() { RET=""; }
    """)


def mode(path: Path) -> int:
    return stat.S_IMODE(path.lstat().st_mode)


class Fixture:
    def __init__(self, base: Path):
        self.base = base
        self.target = base / "target"
        (self.target / "etc" / "apt" / "sources.list.d").mkdir(parents=True)
        self.debconf_log = base / "debconf.log"
        self.confmodule = base / "confmodule"
        self.confmodule.write_text(FAKE_CONFMODULE)
        self.bin = base / "bin"
        self.bin.mkdir()
        # The helper logs through logger(1); keep test runs out of the host log.
        logger = self.bin / "logger"
        logger.write_text("#!/bin/sh\nexit 0\n")
        logger.chmod(0o755)

    @property
    def marker(self) -> Path:
        return self.target / "etc" / "plebian-os" / "offline-install"

    def sources_list(self, text: str) -> None:
        (self.target / "etc" / "apt" / "sources.list").write_text(text)

    def run(self, *args: str) -> subprocess.CompletedProcess:
        env = {
            **os.environ,
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "TARGET": str(self.target),
            "PLEBIAN_OS_DEBCONF_CONFMODULE": str(self.confmodule),
            "FAKE_DEBCONF_LOG": str(self.debconf_log),
        }
        return subprocess.run(["sh", str(HELPER), *args], env=env,
                              capture_output=True, text=True)

    def debconf_writes(self) -> list[str]:
        if not self.debconf_log.exists():
            return []
        return self.debconf_log.read_text().splitlines()


class PkgselHook(unittest.TestCase):
    def test_no_network_source_defers_the_package_list_and_records_it(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(Path(td))
            fx.sources_list(OFFLINE_SOURCES_LIST)
            result = fx.run()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(fx.debconf_writes(), ["pkgsel/include=[]"])
            self.assertIn("PLEBIAN_OS_OFFLINE_INSTALL=1\n", fx.marker.read_text())
            self.assertEqual(mode(fx.marker), 0o644)
            self.assertFalse(fx.marker.with_name("offline-install.new").exists())

    def test_a_network_mirror_leaves_package_selection_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(Path(td))
            fx.sources_list(MIRROR_SOURCES_LIST)
            result = fx.run()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(fx.debconf_writes(), [])
            self.assertFalse(fx.marker.exists())

    def test_network_entry_forms_that_count(self):
        cases = {
            "https with options": "deb [signed-by=/usr/share/keyrings/x.gpg] https://deb.debian.org/debian trixie main\n",
            "indented ftp": "  deb ftp://ftp.example.org/debian trixie main\n",
            "deb-src only": "deb-src http://deb.debian.org/debian trixie main\n",
        }
        for name, text in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as td:
                fx = Fixture(Path(td))
                fx.sources_list("deb cdrom:[x]/ trixie main\n" + text)
                self.assertEqual(fx.run().returncode, 0)
                self.assertEqual(fx.debconf_writes(), [])
                self.assertFalse(fx.marker.exists())

    def test_list_files_in_sources_list_d_count(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(Path(td))
            fx.sources_list(OFFLINE_SOURCES_LIST)
            (fx.target / "etc/apt/sources.list.d/extra.list").write_text(
                "deb http://deb.debian.org/debian trixie main\n")
            self.assertEqual(fx.run().returncode, 0)
            self.assertFalse(fx.marker.exists())

    def test_deb822_sources_respect_enabled_no(self):
        disabled = textwrap.dedent("""\
            # mirror kept for later
            Types: deb
            URIs: http://deb.debian.org/debian
            Suites: trixie
            Components: main
            Enabled: no
            """)
        enabled = textwrap.dedent("""\
            Types: deb
            URIs: cdrom:[x]/

            Types: deb
            URIs: https://deb.debian.org/debian
            Suites: trixie
            Components: main
            """)
        for name, text, network in (("disabled", disabled, False), ("enabled", enabled, True)):
            with self.subTest(name), tempfile.TemporaryDirectory() as td:
                fx = Fixture(Path(td))
                fx.sources_list(OFFLINE_SOURCES_LIST)
                (fx.target / "etc/apt/sources.list.d/debian.sources").write_text(text)
                self.assertEqual(fx.run().returncode, 0)
                self.assertEqual(fx.marker.exists(), not network)

    def test_missing_sources_list_is_an_offline_install(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(Path(td))
            self.assertEqual(fx.run().returncode, 0)
            self.assertTrue(fx.marker.exists())

    def test_unknown_argument_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(Path(td))
            result = fx.run("pkgsel")
            self.assertEqual(result.returncode, 2)
            self.assertFalse(fx.marker.exists())


class LateCommand(unittest.TestCase):
    UNIT = "etc/systemd/system/plebian-os-offline-network.service"
    WANTS = "etc/systemd/system/multi-user.target.wants/plebian-os-offline-network.service"
    HOLD = "etc/NetworkManager/conf.d/90-plebian-os-offline.conf"

    def test_network_install_writes_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(Path(td))
            fx.sources_list(MIRROR_SOURCES_LIST)
            self.assertEqual(fx.run().returncode, 0)
            result = fx.run("late")
            self.assertEqual(result.returncode, 0, result.stderr)
            for rel in (self.UNIT, self.WANTS, self.HOLD):
                self.assertFalse((fx.target / rel).exists(), rel)

    def test_offline_install_gets_wired_dhcp_and_a_networkmanager_hold(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(Path(td))
            fx.sources_list(OFFLINE_SOURCES_LIST)
            self.assertEqual(fx.run().returncode, 0)
            result = fx.run("late")
            self.assertEqual(result.returncode, 0, result.stderr)
            unit = fx.target / self.UNIT
            text = unit.read_text()
            lines = text.splitlines()
            # Manager mode: keeps running without a lease and follows the link.
            self.assertIn("ExecStart=/usr/sbin/dhcpcd -M -w -t 30 -z en* -z eth*", lines)
            # Debian's dhcpcd.conf sets "persistent": a plain SIGTERM leaves the
            # address, which the restarted NetworkManager then adopts as an
            # external connection and never renews. The stop must release it.
            self.assertIn("ExecStop=/usr/sbin/dhcpcd -k", lines)
            self.assertIn("Type=forking", lines)
            self.assertIn("PIDFile=/run/dhcpcd/pid", lines)
            self.assertIn("ConditionPathExists=/etc/plebian-os/offline-install", lines)
            self.assertIn("ConditionPathExists=!/etc/plebian-os/offline-network-handed-off", lines)
            self.assertIn("Before=network.target network-online.target", lines)
            self.assertIn("WantedBy=multi-user.target", lines)
            self.assertEqual(mode(unit), 0o644)
            wants = fx.target / self.WANTS
            self.assertTrue(wants.is_symlink())
            self.assertEqual(os.readlink(wants), "/etc/systemd/system/plebian-os-offline-network.service")
            hold = fx.target / self.HOLD
            hold_lines = hold.read_text().splitlines()
            self.assertIn("dns=none", hold_lines)
            self.assertIn("unmanaged-devices=interface-name:en*;interface-name:eth*", hold_lines)
            self.assertEqual(mode(hold), 0o644)
            leftovers = [p for p in fx.target.rglob("*.new")]
            self.assertEqual(leftovers, [])

    def test_late_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(Path(td))
            fx.sources_list(OFFLINE_SOURCES_LIST)
            self.assertEqual(fx.run().returncode, 0)
            self.assertEqual(fx.run("late").returncode, 0)
            first = (fx.target / self.UNIT).read_bytes()
            result = fx.run("late")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((fx.target / self.UNIT).read_bytes(), first)
            self.assertTrue((fx.target / self.WANTS).is_symlink())


class MediaWiring(unittest.TestCase):
    def setUp(self):
        self.preseed = PRESEED.read_text()
        self.remaster = REMASTER.read_text()

    def active(self, text: str) -> str:
        return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))

    def test_cdrom_entries_are_disabled_on_every_install(self):
        self.assertIn("d-i apt-setup/disable-cdrom-entries boolean true\n", self.active(self.preseed) + "\n")

    def test_release_preseed_installs_the_pkgsel_hook_early(self):
        early = self.preseed.split("d-i preseed/early_command string", 1)[1].split("\n\n", 1)[0]
        self.assertIn("mkdir -p /usr/lib/pre-pkgsel.d", early)
        self.assertIn(HOOK_INSTALL, early)
        self.assertEqual(self.active(self.preseed).count("d-i preseed/early_command string"), 1)

    def test_the_package_list_is_unchanged_for_network_installs(self):
        include = self.preseed.split("d-i pkgsel/include string", 1)[1].split("d-i pkgsel/upgrade", 1)[0]
        for name in ("network-manager", "lightdm", "curl", "xserver-xorg"):
            self.assertIn(f" {name} ", include.replace("\\\n", " ") + " ")

    def test_late_command_runs_the_helper_before_firstboot_is_enabled(self):
        late = self.preseed.split("d-i preseed/late_command string", 1)[1]
        call = late.index("/bin/sh /cdrom/plebian-os/plebian-os-offline-install late; \\")
        self.assertLess(call, late.index("in-target systemctl enable plebian-os-firstboot.service"))
        self.assertLess(late.index("set -e;"), call)

    def test_media_carries_the_helper_once(self):
        copies = [l for l in self.remaster.splitlines()
                  if l.startswith("cp ") and "plebian-os-offline-install" in l]
        self.assertEqual(copies, ['cp "$HERE/provision/plebian-os-offline-install" "$EXTRACT/plebian-os/"'])
        self.assertTrue(os.access(HELPER, os.X_OK))

    def _transformed_preseed(self, snapshot: str) -> str:
        start = self.remaster.index("apply_installer_snapshot() {")
        end = self.remaster.index("\n}\n", start) + 3
        function = self.remaster[start:end]
        with tempfile.TemporaryDirectory() as td:
            seed = Path(td) / "preseed.cfg"
            seed.write_text(self.preseed)
            carrier = Path(td) / "snapshot"
            script = function + 'apply_installer_snapshot "$1" "$2"\n'
            env = {**os.environ, "PLEBIAN_OS_APT_SNAPSHOT": snapshot}
            result = subprocess.run(["bash", "-c", script, "remaster", str(seed), str(carrier)],
                                    env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return seed.read_text()

    def _effective_early_command(self, seed: str) -> str:
        # debconf keeps the last answer: the last early_command is the one run.
        body = self.active(seed).split("d-i preseed/early_command string")[-1]
        lines = []
        for line in body.splitlines():
            lines.append(line)
            if not line.endswith("\\"):
                break
        return "\n".join(lines)

    def test_live_and_snapshot_images_both_run_the_hook(self):
        for name, snapshot in (("live", ""), ("snapshot", "20261101T000000Z")):
            with self.subTest(name):
                early = self._effective_early_command(self._transformed_preseed(snapshot))
                self.assertIn("mkdir -p /usr/lib/pre-pkgsel.d", early)
                self.assertIn(HOOK_INSTALL, early)
                self.assertLess(early.index("mkdir -p /usr/lib/pre-pkgsel.d"), early.index(HOOK_INSTALL))
                if snapshot:
                    self.assertIn("02plebian-snapshot", early)
                    self.assertIn("93plebian-installer-sources", early)


class ProvisionHandoff(unittest.TestCase):
    """The handover from the offline DHCP service to NetworkManager."""

    def setUp(self):
        source = PROVISION.read_text()
        start = source.index("OFFLINE_INSTALL_MARKER=/etc/plebian-os/offline-install")
        end = source.index("\nhand_offline_network_to_networkmanager\n", start)
        self.block = source[start:end] + "\n"
        self.source = source

    def run_handoff(self, base: Path, *, nm_enabled=True, restart_rc=0, dry_run=False,
                    marker=True, stamp=False, hold=True):
        etc = base / "etc"
        (etc / "plebian-os").mkdir(parents=True, exist_ok=True)
        (etc / "NetworkManager" / "conf.d").mkdir(parents=True, exist_ok=True)
        if marker:
            (etc / "plebian-os" / "offline-install").write_text("PLEBIAN_OS_OFFLINE_INSTALL=1\n")
        if stamp:
            (etc / "plebian-os" / "offline-network-handed-off").write_text("earlier\n")
        if hold:
            (etc / "NetworkManager" / "conf.d" / "90-plebian-os-offline.conf").write_text("[main]\ndns=none\n")
        calls = base / "systemctl.calls"
        bindir = base / "bin"
        bindir.mkdir(exist_ok=True)
        fake = bindir / "systemctl"
        fake.write_text(textwrap.dedent(f"""\
            #!/bin/sh
            printf '%s\\n' "$*" >> {calls}
            case "$*" in
                *is-enabled*) exit {0 if nm_enabled else 1} ;;
                "restart NetworkManager.service") exit {restart_rc} ;;
            esac
            exit 0
            """))
        fake.chmod(0o755)
        block = self.block.replace("=/etc/", f"={etc}/")
        script = (
            "set -euo pipefail\n"
            "log() { printf 'LOG %s\\n' \"$*\"; }\n"
            "warn() { printf 'WARN %s\\n' \"$*\" >&2; }\n"
            f"DRY_RUN={1 if dry_run else 0}\n" + block +
            "hand_offline_network_to_networkmanager\necho RETURNED=$?\n")
        result = subprocess.run(["bash", "-c", script],
                                env={**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}"},
                                capture_output=True, text=True)
        call_list = calls.read_text().splitlines() if calls.exists() else []
        return result, call_list, etc

    def test_hands_over_after_networkmanager_is_installed(self):
        with tempfile.TemporaryDirectory() as td:
            result, calls, etc = self.run_handoff(Path(td))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("RETURNED=0", result.stdout)
            self.assertEqual(calls, [
                "is-enabled --quiet NetworkManager.service",
                "disable --quiet plebian-os-offline-network.service",
                "stop plebian-os-offline-network.service",
                "restart NetworkManager.service",
            ])
            self.assertFalse((etc / "NetworkManager/conf.d/90-plebian-os-offline.conf").exists())
            self.assertRegex((etc / "plebian-os/offline-network-handed-off").read_text(),
                             r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\n$")
            self.assertIn("LOG offline install: NetworkManager now manages wired interfaces", result.stdout)

    def test_network_install_is_untouched(self):
        with tempfile.TemporaryDirectory() as td:
            result, calls, etc = self.run_handoff(Path(td), marker=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(calls, [])
            self.assertTrue((etc / "NetworkManager/conf.d/90-plebian-os-offline.conf").exists())

    def test_keeps_the_offline_service_without_networkmanager(self):
        with tempfile.TemporaryDirectory() as td:
            result, calls, etc = self.run_handoff(Path(td), nm_enabled=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(calls, ["is-enabled --quiet NetworkManager.service"])
            self.assertTrue((etc / "NetworkManager/conf.d/90-plebian-os-offline.conf").exists())
            self.assertFalse((etc / "plebian-os/offline-network-handed-off").exists())
            self.assertIn("keeps managing wired interfaces", result.stderr)

    def test_runs_once(self):
        with tempfile.TemporaryDirectory() as td:
            result, calls, etc = self.run_handoff(Path(td), stamp=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(calls, [])
            self.assertEqual((etc / "plebian-os/offline-network-handed-off").read_text(), "earlier\n")

    def test_a_failed_restart_warns_and_never_fails_provisioning(self):
        with tempfile.TemporaryDirectory() as td:
            result, calls, _ = self.run_handoff(Path(td), restart_rc=1)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("RETURNED=0", result.stdout)
            self.assertEqual(calls[-1], "restart NetworkManager.service")
            self.assertIn("manages wired interfaces from the next boot", result.stderr)

    def test_dry_run_changes_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            result, calls, etc = self.run_handoff(Path(td), dry_run=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(calls, ["is-enabled --quiet NetworkManager.service"])
            self.assertTrue((etc / "NetworkManager/conf.d/90-plebian-os-offline.conf").exists())
            self.assertIn("+ systemctl disable --now plebian-os-offline-network.service", result.stdout)

    def test_runs_only_after_provisioning_has_committed(self):
        call = self.source.index("\nhand_offline_network_to_networkmanager\n")
        for earlier in ("\ncommit_provision_root_transaction\n", "\ncleanup\n",
                        "\ntrap - EXIT INT TERM HUP\n"):
            self.assertLess(self.source.rindex(earlier, 0, call), call)
        self.assertLess(call, self.source.index('log "done. Plebian-OS is provisioned."'))


if __name__ == "__main__":
    unittest.main()
