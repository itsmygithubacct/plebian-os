"""SSH server opt-in (0.2.3): the root helper and the provisioner's one-time offer.

The helper is loaded as a module so its apt, systemctl and sshd calls can be
recorded instead of run; nothing here needs root or touches the real system.
The provisioner's offer functions run in bash, extracted from the script, with
the identity-profile, provisioned-marker and dpkg facts supplied per case.
A real trixie exercise of the helper (apt from Debian, systemd) is separate.
"""
import importlib.machinery
import importlib.util
import io
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "provision" / "plebian-os-ssh-server"
PROVISION = ROOT / "provision" / "plebian-os-provision.sh"
UPDATE = ROOT / "provision" / "plebian-os-update.sh"


def load_helper():
    loader = importlib.machinery.SourceFileLoader("plebian_os_ssh_server", str(HELPER))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def shell_function(text, name):
    lines = text.splitlines()
    start = lines.index(f"{name}() {{")
    end = lines.index("}", start)
    return "\n".join(lines[start:end + 1]) + "\n"


class Result:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


class FakeSystem:
    """Answers the helper's commands like a trixie machine would, and records
    every command so a test can say what was and was not run."""

    def __init__(self, installed=False, plan=None, update_rc=0, install_rc=0,
                 enable_rc=0):
        self.installed = installed
        self.enabled = False
        self.active = False
        self.update_rc = update_rc
        self.install_rc = install_rc
        self.enable_rc = enable_rc
        self.plan = plan if plan is not None else (
            "Inst openssh-sftp-server (1:10.0p1-7+deb13u4 Debian:13.7/stable [amd64])\n"
            "Inst openssh-server (1:10.0p1-7+deb13u4 Debian-Security:13/stable-security [amd64])\n"
            "Conf openssh-server (1:10.0p1-7+deb13u4 Debian-Security:13/stable-security [amd64])\n")
        self.calls = []
        self.sources_seen = []

    def run(self, argv, *, check=False):
        argv = list(argv)
        self.calls.append(argv)
        name = argv[0]
        if name == "dpkg-query":
            return Result(0 if self.installed else 1, "ii " if self.installed else "")
        if name == "systemctl":
            verb, unit = argv[1], argv[-1]
            if verb == "is-enabled":
                if not self.installed:
                    return Result(1, "not-found\n")
                return Result(0 if self.enabled else 1,
                              ("enabled" if self.enabled and unit.endswith("service") else "disabled") + "\n")
            if verb == "is-active":
                on = self.active and unit.endswith("service")
                return Result(0 if on else 3, ("active" if on else "inactive") + "\n")
            if verb == "enable":
                if self.enable_rc == 0:
                    self.enabled = self.active = True
                return Result(self.enable_rc, "", "" if self.enable_rc == 0 else "Unit is masked.")
            if verb == "disable":
                self.enabled = self.active = False
                return Result(0)
        if name == "apt-get" and "-s" in argv:
            self._record_sources(argv)
            return Result(0, self.plan)
        if name == "/usr/sbin/sshd":
            return Result(0, "port 22\npermitrootlogin without-password\n")
        if name == "ip":
            return Result(0, '[{"ifname":"enp1s0","addr_info":[{"family":"inet","local":"192.0.2.10"}]},'
                             '{"ifname":"docker0","addr_info":[{"family":"inet","local":"172.17.0.1"}]}]')
        if name == "hostname":
            return Result(0, "plebian\n")
        if name == "ssh-keygen" and "-l" in argv:
            kind = "ED25519" if "ed25519" in argv[-1] else "RSA"
            return Result(0, f"256 SHA256:{kind}fingerprintvalue root@plebian ({kind})\n")
        return Result(0)

    def _record_sources(self, argv):
        for i, word in enumerate(argv):
            if word.startswith("Dir::Etc::SourceParts="):
                parts = Path(word.split("=", 1)[1])
                self.sources_seen.append({p.name: p.read_text() for p in parts.iterdir()})

    def run_shielded(self, argv):
        argv = list(argv)
        self.calls.append(argv)
        self._record_sources(argv)
        if "update" in argv:
            return self.update_rc
        if "install" in argv:
            if self.install_rc == 0:
                self.installed = True
                self.enabled = self.active = True  # Debian's postinst starts ssh
            return self.install_rc
        return 0

    def commands(self, name):
        return [c for c in self.calls if c[0] == name]


class HelperTests(unittest.TestCase):
    def setUp(self):
        self.h = load_helper()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.ssh = base / "etc-ssh"
        (self.ssh / "sshd_config.d").mkdir(parents=True)
        (self.ssh / "sshd_config").write_text("Include /etc/ssh/sshd_config.d/*.conf\n")
        for kind in ("ed25519", "rsa"):
            (self.ssh / f"ssh_host_{kind}_key").write_text("private\n")
            (self.ssh / f"ssh_host_{kind}_key.pub").write_text("public\n")
        keyring = base / "debian-archive-keyring.gpg"
        keyring.write_text("key\n")
        os_release = base / "os-release"
        os_release.write_text('ID=debian\nVERSION_CODENAME=trixie\n')
        self.os_release = os_release
        (base / "var-lib").mkdir()
        self.patches = {
            "SSH_DIR": self.ssh, "KEYRING": str(keyring), "OS_RELEASE": str(os_release),
            "WORK_PARENT": str(base / "var-lib"), "LOCK_PATH": str(base / "lock"),
            "LOG_PATH": str(base / "ssh-server.log"),
        }
        for key, value in self.patches.items():
            patcher = mock.patch.object(self.h, key, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.h._log_stream = None
        env = mock.patch.dict(os.environ, {"SUDO_USER": "alice"})
        env.start()
        self.addCleanup(env.stop)

    def invoke(self, args, system, root=True):
        out, err = io.StringIO(), io.StringIO()
        saved = {n: signal.getsignal(n) for n in (signal.SIGINT, signal.SIGHUP, signal.SIGQUIT)}
        self.addCleanup(lambda: [signal.signal(n, h) for n, h in saved.items()])
        with mock.patch.object(self.h, "run", system.run), \
                mock.patch.object(self.h, "run_shielded", system.run_shielded), \
                mock.patch.object(self.h, "is_root", lambda: root), \
                redirect_stdout(out), redirect_stderr(err):
            rc = self.h.main(list(args))
        if self.h._log_stream is not None:
            self.h._log_stream.close()
            self.h._log_stream = None
        return rc, out.getvalue(), err.getvalue()

    # -- input ----------------------------------------------------------------
    def test_refuses_every_argument_shape_but_one_known_word(self):
        for args in ([], ["bogus"], ["enable", "now"], ["--help"], ["Enable"],
                     ["enable;id"], ["disable", "--force"], [""], ["status", "-v"]):
            system = FakeSystem()
            rc, out, err = self.invoke(args, system)
            self.assertEqual(rc, 2, args)
            self.assertIn("usage:", err)
            self.assertEqual(system.calls, [], f"{args} ran {system.calls}")

    def test_enable_and_disable_need_root_and_do_nothing_without_it(self):
        for action in ("enable", "disable"):
            system = FakeSystem()
            rc, _, err = self.invoke([action], system, root=False)
            self.assertEqual(rc, 2)
            self.assertIn(f"sudo plebian-os-ssh-server {action}", err)
            self.assertEqual(system.calls, [])

    def test_children_never_see_the_callers_environment(self):
        with mock.patch.dict(os.environ, {"APT_CONFIG": "/tmp/evil.conf",
                                          "LD_PRELOAD": "/tmp/evil.so",
                                          "PATH": "/tmp/evil-bin"}):
            result = self.h.run(["env"])
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("APT_CONFIG", result.stdout)
        self.assertNotIn("LD_PRELOAD", result.stdout)
        self.assertIn("PATH=/usr/sbin:/usr/bin:/sbin:/bin\n", result.stdout)

    def test_refuses_a_system_that_is_not_debian(self):
        self.os_release.write_text("ID=ubuntu\nVERSION_CODENAME=noble\n")
        system = FakeSystem(installed=False)
        rc, _, err = self.invoke(["enable"], system)
        self.assertEqual(rc, 2)
        self.assertIn("not a Debian system", err)
        self.assertEqual(system.commands("apt-get"), [])
        self.assertEqual([c for c in system.calls if c[:2] == ["systemctl", "enable"]], [])

    def test_a_second_concurrent_run_is_refused(self):
        import fcntl
        fd = os.open(self.patches["LOCK_PATH"], os.O_RDWR | os.O_CREAT, 0o600)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)
        system = FakeSystem()
        rc, _, err = self.invoke(["enable"], system)
        self.assertEqual(rc, 2)
        self.assertIn("in progress", err)
        self.assertFalse(any(c[0] in ("apt-get", "systemctl") and c[1] in ("update", "enable", "install")
                             for c in system.calls))

    # -- enable ---------------------------------------------------------------
    def test_enable_installs_from_debian_only_then_enables_and_reports(self):
        system = FakeSystem(installed=False)
        rc, out, err = self.invoke(["enable"], system)
        self.assertEqual(rc, 0, err)
        apt = [c for c in system.calls if c[0] == "apt-get"]
        verbs = [next(w for w in ("update", "install") if w in c) for c in apt]
        self.assertEqual(verbs, ["update", "install", "install"])  # update, plan, install
        for command in apt:
            self.assertIn("Dir::Etc::SourceList=/dev/null", command)
            self.assertIn("APT::Get::AllowUnauthenticated=false", command)
            self.assertIn("Acquire::AllowInsecureRepositories=false", command)
            self.assertTrue(any(w.startswith("Dir::State::Lists=") and "/var/lib/plebian-os" not in w
                                or w.startswith("Dir::State::Lists=" + self.patches["WORK_PARENT"])
                                for w in command))
        self.assertIn("--no-remove", apt[-1])
        self.assertEqual(apt[-1][-2:], ["install", "openssh-server"])
        # The only source apt saw is the Debian archive, signed by Debian's key.
        for seen in system.sources_seen:
            self.assertEqual(list(seen), ["debian.sources"])
            text = seen["debian.sources"]
            uris = re.findall(r"^URIs: (\S+)$", text, re.M)
            self.assertEqual(uris, ["https://deb.debian.org/debian",
                                    "https://security.debian.org/debian-security"])
            self.assertEqual(re.findall(r"^Suites: (.+)$", text, re.M),
                             ["trixie trixie-updates", "trixie-security"])
            self.assertEqual(set(re.findall(r"^Signed-By: (\S+)$", text, re.M)),
                             {self.patches["KEYRING"]})
            self.assertNotRegex(text, r"(?i)trusted|allow-")
        # The private apt work area is gone afterwards.
        self.assertEqual(list(Path(self.patches["WORK_PARENT"]).iterdir()), [])
        self.assertIn(["systemctl", "enable", "--now", "ssh.service"], system.calls)
        # What the person is told.
        self.assertIn("SSH server: ON", out)
        self.assertIn("accepts SSH logins from the network with your account\npassword", out)
        self.assertIn("ssh alice@192.0.2.10    (enp1s0)", out)
        self.assertNotIn("172.17.0.1", out)
        self.assertIn("ED25519  SHA256:ED25519fingerprintvalue", out)
        self.assertIn("RSA      SHA256:RSAfingerprintvalue", out)
        self.assertIn("sudo plebian-os-ssh-server disable", out)
        self.assertIn("This helper does not do that for you.", out)
        # Key-only login is a note: the helper never writes sshd configuration.
        self.assertEqual(sorted(p.name for p in (self.ssh / "sshd_config.d").iterdir()), [])
        log = Path(self.patches["LOG_PATH"]).read_text()
        self.assertIn("enable (requested by alice)", log)
        self.assertIn("enabled: ssh.service is enabled and running (requested by alice)", log)

    def test_a_started_change_ignores_the_terminals_interrupt(self):
        system = FakeSystem(installed=True)
        seen = {}

        def enable_and_look(argv, *, check=False):
            if argv[:2] == ["systemctl", "enable"]:
                seen.update({n: signal.getsignal(n) for n in (signal.SIGINT, signal.SIGHUP)})
            return system.__class__.run(system, argv, check=check)
        system.run = enable_and_look
        self.assertEqual(self.invoke(["enable"], system)[0], 0)
        self.assertEqual(seen, {signal.SIGINT: signal.SIG_IGN, signal.SIGHUP: signal.SIG_IGN})

    def test_enable_when_installed_only_enables(self):
        system = FakeSystem(installed=True)
        rc, out, _ = self.invoke(["enable"], system)
        self.assertEqual(rc, 0)
        self.assertEqual(system.commands("apt-get"), [])
        self.assertIn(["systemctl", "enable", "--now", "ssh.service"], system.calls)
        self.assertIn("SSH server: ON", out)

    def test_a_plan_that_removes_anything_is_refused_before_install(self):
        plan = ("Remv kilix-mpv [0.40.0+kilix.9]\n"
                "Inst openssh-server (1:10.0p1-7+deb13u4 Debian:13.7/stable [amd64])\n")
        system = FakeSystem(installed=False, plan=plan)
        rc, _, err = self.invoke(["enable"], system)
        self.assertEqual(rc, 2)
        self.assertIn("would remove kilix-mpv", err)
        self.assertFalse(any("install" in c and "-s" not in c for c in system.commands("apt-get")))
        self.assertFalse(any(c[:2] == ["systemctl", "enable"] for c in system.calls))

    def test_a_plan_from_a_non_debian_origin_is_refused(self):
        plan = "Inst openssh-server (1:99.0-1 Example:1.0/stable [amd64])\n"
        system = FakeSystem(installed=False, plan=plan)
        rc, _, err = self.invoke(["enable"], system)
        self.assertEqual(rc, 2)
        self.assertIn("not Debian", err)
        self.assertFalse(any(c[:2] == ["systemctl", "enable"] for c in system.calls))

    def test_failed_package_list_download_changes_nothing(self):
        system = FakeSystem(installed=False, update_rc=100)
        rc, _, err = self.invoke(["enable"], system)
        self.assertEqual(rc, 1)
        self.assertIn("network", err)
        self.assertEqual(len(system.commands("apt-get")), 1)
        self.assertFalse(any(c[:2] == ["systemctl", "enable"] for c in system.calls))
        self.assertIn("failed:", Path(self.patches["LOG_PATH"]).read_text())

    def test_failed_install_is_reported(self):
        system = FakeSystem(installed=False, install_rc=100)
        rc, out, err = self.invoke(["enable"], system)
        self.assertEqual(rc, 1)
        self.assertIn("exited with status 100", err)
        self.assertNotIn("SSH server: ON", out)

    def test_a_service_that_will_not_start_is_reported(self):
        system = FakeSystem(installed=True, enable_rc=1)
        rc, out, err = self.invoke(["enable"], system)
        self.assertEqual(rc, 1)
        self.assertIn("could not enable ssh.service", err)
        self.assertNotIn("SSH server: ON", out)

    # -- disable / status -----------------------------------------------------
    def test_disable_stops_service_and_socket_and_keeps_the_package(self):
        system = FakeSystem(installed=True)
        system.enabled = system.active = True
        rc, out, _ = self.invoke(["disable"], system)
        self.assertEqual(rc, 0)
        self.assertIn(["systemctl", "disable", "--now", "ssh.socket"], system.calls)
        self.assertIn(["systemctl", "disable", "--now", "ssh.service"], system.calls)
        self.assertEqual(system.commands("apt-get"), [])
        self.assertTrue(system.installed)
        self.assertIn("SSH server: OFF", out)
        self.assertIn("sudo plebian-os-ssh-server enable", out)

    def test_disable_without_the_package_is_a_no_op(self):
        system = FakeSystem(installed=False)
        rc, out, _ = self.invoke(["disable"], system)
        self.assertEqual(rc, 0)
        self.assertIn("not installed", out)
        self.assertFalse(any(c[0] == "systemctl" and c[1] == "disable" for c in system.calls))

    def test_enable_disable_enable_round_trip(self):
        system = FakeSystem(installed=False)
        self.assertEqual(self.invoke(["enable"], system)[0], 0)
        self.assertEqual(self.invoke(["disable"], system)[0], 0)
        self.assertFalse(system.enabled or system.active)
        before = len(system.commands("apt-get"))
        rc, out, _ = self.invoke(["enable"], system)
        self.assertEqual(rc, 0)
        self.assertEqual(len(system.commands("apt-get")), before)  # no reinstall
        self.assertTrue(system.enabled and system.active)

    def test_status_needs_no_root_and_changes_nothing(self):
        system = FakeSystem(installed=False)
        rc, out, _ = self.invoke(["status"], system, root=False)
        self.assertEqual(rc, 0)
        self.assertIn("SSH server: OFF (openssh-server is not installed)", out)
        system = FakeSystem(installed=True)
        system.enabled = system.active = True
        rc, out, _ = self.invoke(["status"], system, root=False)
        self.assertEqual(rc, 0)
        self.assertIn("SSH server: ON", out)
        for command in system.calls:
            self.assertNotIn(command[:2], (["systemctl", "enable"], ["systemctl", "disable"]))
            self.assertNotEqual(command[0], "apt-get")

    # -- package step shield --------------------------------------------------
    def test_package_step_survives_the_terminals_interrupt(self):
        """The real run_shielded: apt runs in its own session, and a SIGINT
        or SIGHUP to the helper while it waits is ignored."""
        script = f"ps -o sid= -p $$; kill -INT {os.getpid()}; kill -HUP {os.getpid()}; echo finished"
        out = io.StringIO()
        with redirect_stdout(out):
            rc = self.h.run_shielded(["sh", "-c", script])
        self.assertEqual(rc, 0)
        lines = out.getvalue().split()
        self.assertNotEqual(int(lines[0]), os.getsid(0))
        self.assertIn("finished", lines)
        self.assertIs(signal.getsignal(signal.SIGINT), signal.default_int_handler)


class ProvisionOfferTests(unittest.TestCase):
    """The provisioner records the question only for a fresh interactive
    installation that has a desktop session and no SSH server."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.text = PROVISION.read_text()
        self.helper = self.base / "plebian-os-ssh-server"
        self.helper.write_text("#!/bin/sh\n")
        self.helper.chmod(0o755)
        self.offer = self.base / "var-lib-plebian-os" / "ssh-server-offer"
        self.offer.parent.mkdir()
        self.marker = self.base / "provisioned"

    def run_offer(self, profile="interactive-v1", provisioned=False, desktop="1",
                  ssh_installed=False, helper=True, user="alice", dry_run="0"):
        if provisioned:
            self.marker.write_text("")
            self.marker.chmod(0o644)
        functions = "".join(shell_function(self.text, name) for name in (
            "machine_already_provisioned", "ssh_server_offer_skip_reason",
            "record_ssh_server_offer"))
        record = "" if profile is None else profile
        script = f"""
set -euo pipefail
log()  {{ printf 'LOG %s\\n' "$*"; }}
die()  {{ printf 'DIE %s\\n' "$*"; exit 1; }}
has_fresh_identity_profile() {{
    [ -n "{record}" ] || return 1
    IDENTITY_PROFILE_NAME="{record}"
}}
dpkg-query() {{ {"printf 'ii '" if ssh_installed else "return 1"}; }}
PROVISION_COMPLETED_MARKER={self.marker}
SSH_SERVER_HELPER={self.helper if helper else self.base / 'missing'}
SSH_SERVER_OFFER={self.offer}
IDENTITY_PROFILE_NAME=""
DESKTOP={desktop}
DRY_RUN={dry_run}
TARGET_USER='{user}'
{functions}
record_ssh_server_offer
"""
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True)

    def test_fresh_interactive_install_records_the_question_once_for_the_owner(self):
        result = self.run_offer()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.offer.read_text(), "ssh-server-offer/v1 alice\n")
        self.assertEqual(self.offer.stat().st_mode & 0o777, 0o644)
        self.assertIn("default: no", result.stdout)
        # A retried first-boot attempt rewrites the same record.
        self.assertEqual(self.run_offer().returncode, 0)
        self.assertEqual(self.offer.read_text(), "ssh-server-offer/v1 alice\n")
        self.assertEqual([p.name for p in self.offer.parent.iterdir()], ["ssh-server-offer"])

    def test_nothing_is_recorded_where_no_person_should_be_asked(self):
        cases = {
            "automated preseed": dict(profile="automated-v1"),
            "legacy machine without an identity record": dict(profile=None),
            "upgrade or re-provision after first boot": dict(provisioned=True),
            "shell-only session": dict(desktop="0"),
            "SSH server already installed": dict(ssh_installed=True),
            "helper missing": dict(helper=False),
        }
        for label, kwargs in cases.items():
            with self.subTest(label):
                result = self.run_offer(**kwargs)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertFalse(self.offer.exists(), label)
                self.assertIn("no first-login question", result.stdout)
                self.marker.unlink(missing_ok=True)

    def test_dry_run_writes_nothing(self):
        result = self.run_offer(dry_run="1")
        self.assertEqual(result.returncode, 0)
        self.assertIn("+ write", result.stdout)
        self.assertFalse(self.offer.exists())

    def test_an_unsafe_account_name_stops_the_run(self):
        result = self.run_offer(user="alice bob")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DIE unsafe target user", result.stdout)
        self.assertFalse(self.offer.exists())

    def test_identity_profile_reader_reports_the_profile_name(self):
        record = self.base / "identity-profile"
        record.write_text("interactive-v1\n")
        script = f"""
set -euo pipefail
die() {{ echo "DIE $*"; exit 1; }}
stat() {{ echo 0:644:1; }}
IDENTITY_PROFILE_RECORD={record}
IDENTITY_PROFILE_NAME=""
{shell_function(self.text, "has_fresh_identity_profile")}
has_fresh_identity_profile
echo "name=$IDENTITY_PROFILE_NAME"
"""
        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
        self.assertEqual(result.stdout.strip(), "name=interactive-v1", result.stderr)


class WiringTests(unittest.TestCase):
    def setUp(self):
        self.provision = PROVISION.read_text()
        self.update = UPDATE.read_text()

    def test_provisioner_installs_the_helper_and_asks_after_the_desktop_request(self):
        main = self.provision[self.provision.index("\nensure_plebian_os_checkout\n"):]
        self.assertTrue(main.startswith("\nensure_plebian_os_checkout\ninstall_ssh_server_helper\n"))
        self.assertLess(main.index("\nrecord_default_desktop\n"),
                        main.index("\nrecord_ssh_server_offer\n"))
        self.assertLess(main.index("\nrecord_ssh_server_offer\n"),
                        main.index("\ncommit_provision_root_transaction\n"))

    def test_both_root_paths_are_inside_the_provisioning_rollback(self):
        start = self.provision.index("PROVISION_ROOT_TRANSACTION_PATHS=(")
        paths = self.provision[start:self.provision.index("\n)\n", start)]
        self.assertIn("/usr/local/sbin/plebian-os-ssh-server\n", paths)
        self.assertIn("/var/lib/plebian-os/ssh-server-offer\n", paths)

    def test_provisioning_never_installs_or_starts_an_ssh_server(self):
        for text, name in ((self.provision, "provisioner"), (self.update, "updater")):
            text = "\n".join(line for line in text.splitlines()
                              if not line.lstrip().startswith("#"))
            self.assertNotRegex(text, r"apt-get[^\n]*install[^\n]*openssh-server", name)
            self.assertNotRegex(text, r"systemctl[^\n]*(enable|start)[^\n]*\bssh(\.service|\.socket)?\b", name)
            self.assertNotRegex(text, r"plebian-os-ssh-server\"?\s+enable", name)

    def test_the_updater_deploys_the_helper_but_never_asks(self):
        self.assertNotIn("ssh-server-offer", self.update)
        self.assertNotIn("record_ssh_server_offer", self.update)
        self.assertIn('install -m 0755 "$prov/plebian-os-ssh-server" "$stage/plebian-os-ssh-server"',
                      self.update)
        # Rollback of a snapshot from before 0.2.3 must not delete the helper's
        # absent-at-snapshot path by mistake: its key is gated by a marker.
        self.assertIn(': >"$txn/ssh-server-helper"', self.update)
        self.assertIn('if [ -f "$txn/ssh-server-helper" ]; then', self.update)

    def test_release_media_still_installs_no_ssh_server(self):
        preseed = (ROOT / "preseed" / "preseed.cfg").read_text()
        self.assertIn("\ntasksel tasksel/first multiselect standard\n", preseed)
        remaster = (ROOT / "build" / "remaster-iso.sh").read_text()
        self.assertIn("release artifacts refuse an effective preseed that installs SSH", remaster)

    def test_helper_is_isolated_python(self):
        first = HELPER.read_text().splitlines()[0]
        self.assertEqual(first, "#!/usr/bin/python3 -I")
        self.assertTrue(os.access(HELPER, os.X_OK))


if __name__ == "__main__":
    unittest.main()
