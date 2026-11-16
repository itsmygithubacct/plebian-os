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


def crypt_hash(password, salt="$6$plebtest$"):
    import ctypes
    library = ctypes.CDLL("libcrypt.so.1")
    library.crypt.restype = ctypes.c_char_p
    library.crypt.argtypes = (ctypes.c_char_p, ctypes.c_char_p)
    return library.crypt(password.encode(), salt.encode()).decode()


GENERATED = ("sshd-vsock.socket", "sshd-unix-local.socket", "sshd-unix-export.socket")


class FakeSystem:
    """Answers the helper's commands like a trixie machine would, and records
    every command so a test can say what was and was not run.

    `enabled`/`active` are ssh.service; `socket_*` are ssh.socket; `generated`
    maps systemd-ssh-generator sockets to "active"/"inactive" (present only
    once sshd is installed). The fake models Debian's postinst, which enables
    and starts ssh.service during the install even when apt then fails."""

    def __init__(self, installed=False, plan=None, update_rc=0, install_rc=0,
                 enable_rc=0, postinst_ran=True, start_fails=False, stuck=False,
                 disable_rc=0, generated=None, etc=None, stray_sshd=False):
        self.installed = installed
        self.enabled = False
        self.active = False
        self.socket_enabled = False
        self.socket_active = False
        self.update_rc = update_rc
        self.install_rc = install_rc
        self.enable_rc = enable_rc
        self.postinst_ran = postinst_ran
        self.start_fails = start_fails
        self.stuck = stuck
        self.disable_rc = disable_rc
        self.stray_sshd = stray_sshd
        self.generated = dict(generated or {})
        self.masked = set()
        self.etc = etc
        self.plan = plan if plan is not None else (
            "Inst openssh-sftp-server (1:10.0p1-7+deb13u4 Debian:13.7/stable [amd64])\n"
            "Inst openssh-server (1:10.0p1-7+deb13u4 Debian-Security:13/stable-security [amd64])\n"
            "Conf openssh-server (1:10.0p1-7+deb13u4 Debian-Security:13/stable-security [amd64])\n")
        self.calls = []
        self.sources_seen = []
        self.apt_configs = []

    def _is_enabled(self, unit):
        if unit in self.masked:
            return "masked"
        if not self.installed:
            return "not-found"
        if unit == "ssh.service":
            return "enabled" if self.enabled else "disabled"
        if unit == "ssh.socket":
            return "enabled" if self.socket_enabled else "disabled"
        if unit in self.generated:
            return "generated"
        return "not-found"

    def _is_active(self, unit):
        if unit == "ssh.service":
            return self.active
        if unit == "ssh.socket":
            return self.socket_active
        return self.generated.get(unit) == "active" and unit not in self.masked

    def run(self, argv, *, check=False, env=None):
        argv = list(argv)
        self.calls.append(argv)
        name = argv[0]
        if name == "dpkg-query":
            return Result(0 if self.installed else 1, "ii " if self.installed else "")
        if name == "systemctl":
            verb, unit = argv[1], argv[-1]
            if verb == "is-enabled":
                word = self._is_enabled(unit)
                return Result(0 if word in ("enabled", "generated") else 1, word + "\n")
            if verb == "is-active":
                on = self._is_active(unit)
                return Result(0 if on else 3, ("active" if on else "inactive") + "\n")
            if verb == "list-units":
                rows = "".join(f"{u} loaded {'active' if self._is_active(u) else 'inactive'} x\n"
                               for u in self.generated if self.installed)
                return Result(0, rows)
            if verb == "enable":
                if self.enable_rc == 0:
                    self.enabled = True
                    self.active = not self.start_fails
                return Result(self.enable_rc, "", "" if self.enable_rc == 0 else "Unit is masked.")
            if verb == "disable":
                if self.disable_rc:
                    return Result(self.disable_rc, "", "Failed to disable unit: Access denied")
                if unit == "ssh.service":
                    self.enabled = False
                    self.active = self.stuck
                else:
                    self.socket_enabled = self.socket_active = False
                return Result(0)
            if verb == "mask":
                if self.disable_rc:
                    return Result(self.disable_rc, "", "Access denied")
                self.masked.add(unit)
                if self.etc is not None:
                    link = Path(self.etc) / unit
                    if not link.is_symlink():
                        link.symlink_to("/dev/null")
                return Result(0)
            if verb == "unmask":
                self.masked.discard(unit)
                if self.etc is not None:
                    (Path(self.etc) / unit).unlink(missing_ok=True)
                return Result(0)
        if name == "ss":
            rows = ""
            if self.active or self.stray_sshd:
                rows = 'LISTEN 0 128 0.0.0.0:22 0.0.0.0:* users:(("sshd",pid=7,fd=6))\n'
            return Result(0, rows + 'LISTEN 0 4096 127.0.0.1:631 0.0.0.0:* users:(("cupsd",pid=9,fd=7))\n')
        if name == "apt-get" and "-s" in argv:
            self._record_sources(argv, env)
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
            i = argv.index("-E") if "-E" in argv else -1
            digest = argv[i + 1] if i >= 0 else "sha256"
            label = {"sha256": "SHA256", "md5": "MD5"}.get(digest, digest.upper())
            return Result(0, f"256 {label}:{kind}fingerprintvalue root@plebian ({kind})\n")
        return Result(0)

    def _record_sources(self, argv, env=None):
        if argv and argv[0] == "apt-get" and env and env.get("APT_CONFIG"):
            self.apt_configs.append(Path(env["APT_CONFIG"]).read_text())
        for i, word in enumerate(argv):
            if word.startswith("Dir::Etc::SourceParts="):
                parts = Path(word.split("=", 1)[1])
                self.sources_seen.append({p.name: p.read_text() for p in parts.iterdir()})

    def run_shielded(self, argv, *, env=None):
        argv = list(argv)
        self.calls.append(argv)
        self._record_sources(argv, env)
        if "update" in argv:
            return self.update_rc
        if "install" in argv:
            if self.install_rc == 0 or self.postinst_ran:
                # Debian's postinst enables and starts ssh.service; a failing
                # trigger or Post-Invoke hook can still fail apt afterwards.
                self.installed = True
                self.enabled = self.active = True
                self.generated.setdefault("sshd-unix-local.socket", "inactive")
            return self.install_rc
        return 0

    def commands(self, name):
        return [c for c in self.calls if c[0] == name]

    def changes(self):
        return [c for c in self.calls if c[0] == "systemctl" and c[1] in
                ("enable", "disable", "mask", "unmask")]


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
        self.etc = base / "etc-systemd-system"
        self.etc.mkdir()
        self.shadow = base / "shadow"
        self.write_shadow()
        self.patches = {
            "SSH_DIR": self.ssh, "KEYRING": str(keyring), "OS_RELEASE": str(os_release),
            "WORK_PARENT": str(base / "var-lib"), "LOCK_PATH": str(base / "lock"),
            "LOG_PATH": str(base / "ssh-server.log"), "SHADOW_PATH": str(self.shadow),
            "SYSTEMD_ETC": self.etc, "MASK_RECORD": str(base / "var-lib" / "masked-sockets"),
        }
        for key, value in self.patches.items():
            patcher = mock.patch.object(self.h, key, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.h._log_stream = None
        env = mock.patch.dict(os.environ, {"SUDO_USER": "alice"})
        env.start()
        self.addCleanup(env.stop)

    def write_shadow(self, *extra):
        rows = [
            "root:!:19000:0:99999:7:::",
            "daemon:*:19000:0:99999:7:::",
            "alice:" + crypt_hash("Corr3ct-h0rse") + ":19000:0:99999:7:::",
            "bob:" + crypt_hash("bobs own", "$6$bobsalt$") + ":19000:0:99999:7:::",
            "nopass::19000:0:99999:7:::",
            *extra,
        ]
        self.shadow.write_text("\n".join(rows) + "\n")

    def work_dirs(self):
        return [p for p in Path(self.patches["WORK_PARENT"]).iterdir() if p.name != "masked-sockets"]

    def invoke(self, args, system, root=True):
        if getattr(system, "etc", None) is None:
            system.etc = self.etc
        out, err = io.StringIO(), io.StringIO()
        saved = {n: signal.getsignal(n) for n in
                 (signal.SIGINT, signal.SIGHUP, signal.SIGQUIT, signal.SIGTERM)}
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
        self.assertEqual(len(system.apt_configs), len(apt))
        for conf in system.apt_configs:
            self.assertIn('Dir::Etc::Parts "', conf)
            self.assertNotIn("Sources::With", conf)
            self.assertNotIn("AllowUnauthenticated", conf)
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
            stanzas = [block for block in text.split("\n\n") if "URIs:" in block]
            self.assertEqual(len(stanzas), 2)
            for stanza in stanzas:  # every stanza, not just somewhere in the file
                self.assertEqual(re.findall(r"^Signed-By: (\S+)$", stanza, re.M),
                                 [self.patches["KEYRING"]], stanza)
            self.assertNotRegex(text, r"(?i)trusted|allow-")
        # The private apt work area is gone afterwards.
        self.assertEqual(self.work_dirs(), [])
        self.assertIn(["systemctl", "enable", "--now", "ssh.service"], system.calls)
        # What the person is told.
        self.assertIn("SSH server: ON", out)
        self.assertIn("accepts SSH logins from the network for every account on it\n"
                      "that has a password, not only yours.", out)
        self.assertIn("Accounts with a password here: alice, bob\n", out)
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
                seen.update({n: signal.getsignal(n) for n in
                             (signal.SIGINT, signal.SIGHUP, signal.SIGQUIT, signal.SIGTERM)})
            return system.__class__.run(system, argv, check=check)
        system.run = enable_and_look
        self.assertEqual(self.invoke(["enable"], system)[0], 0)
        self.assertEqual(seen, {signal.SIGINT: signal.SIG_IGN, signal.SIGHUP: signal.SIG_IGN,
                                signal.SIGQUIT: signal.SIG_IGN, signal.SIGTERM: signal.SIG_IGN})

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

    def test_failed_install_before_the_postinst_leaves_ssh_off(self):
        system = FakeSystem(installed=False, install_rc=100, postinst_ran=False)
        rc, out, err = self.invoke(["enable"], system)
        self.assertEqual(rc, 1)
        self.assertIn("exited with status 100", err)
        self.assertNotIn("SSH server: ON", out)
        self.assertTrue(out.rstrip().endswith("SSH server: OFF -- nothing accepts SSH logins"), out)

    # -- B2: apt fails after Debian's postinst already started sshd -------------
    def test_install_failing_after_the_postinst_started_sshd_turns_it_off_again(self):
        system = FakeSystem(installed=False, install_rc=100)  # e.g. DPkg::Post-Invoke failed
        rc, out, err = self.invoke(["enable"], system)
        self.assertEqual(rc, 1)
        self.assertIn("exited with status 100", err)
        self.assertFalse(system.enabled or system.active, system.calls)
        self.assertIn(["systemctl", "disable", "--now", "ssh.service"], system.calls)
        self.assertIn(["systemctl", "disable", "--now", "ssh.socket"], system.calls)
        for unit in GENERATED:
            self.assertIn(["systemctl", "mask", "--now", unit], system.calls)
        # The last word is the state read back afterwards.
        self.assertTrue(out.rstrip().endswith("SSH server: OFF -- nothing accepts SSH logins"), out)
        self.assertNotIn("SSH server: ON", out)
        log = Path(self.patches["LOG_PATH"]).read_text()
        self.assertIn("enable failed; turned SSH off again", log)
        self.assertIn("final state: OFF", log)

    def test_install_failure_that_cannot_be_undone_reports_ssh_on_with_the_warning(self):
        system = FakeSystem(installed=False, install_rc=100, disable_rc=1)
        rc, out, err = self.invoke(["enable"], system)
        self.assertEqual(rc, 1)
        self.assertTrue(system.active)
        self.assertIn("SSH server: ON -- this run reported an error (above), and SSH is still on", out)
        self.assertIn("for every account on it\nthat has a password", out)
        self.assertIn("ED25519  SHA256:ED25519fingerprintvalue", out)
        self.assertIn("Turn it off again with:  sudo plebian-os-ssh-server disable", out)
        self.assertIn("sshd listening on 0.0.0.0:22", out)
        self.assertNotIn("SSH server: OFF", out)
        log = Path(self.patches["LOG_PATH"]).read_text()
        self.assertIn("enable failed; could not turn SSH off again: ssh.service:", log)
        self.assertNotIn("turned SSH off again", log)
        self.assertIn("final state: ON", log)

    def test_a_service_that_will_not_start_is_reported_and_left_off(self):
        system = FakeSystem(installed=True, enable_rc=1)
        rc, out, err = self.invoke(["enable"], system)
        self.assertEqual(rc, 1)
        self.assertIn("could not enable ssh.service", err)
        self.assertNotIn("SSH server: ON", out)
        self.assertIn("SSH server: OFF", out)

    def test_enabled_but_not_running_is_a_failure_and_is_turned_off(self):
        system = FakeSystem(installed=True, start_fails=True)
        rc, out, err = self.invoke(["enable"], system)
        self.assertEqual(rc, 1)
        self.assertIn("is not running after it was enabled", err)
        self.assertFalse(system.enabled)
        self.assertNotIn("SSH server: ON", out)

    def test_a_failed_enable_leaves_ssh_that_was_already_on_alone_and_says_so(self):
        system = FakeSystem(installed=True, enable_rc=1)
        system.enabled = system.active = True
        rc, out, err = self.invoke(["enable"], system)
        self.assertEqual(rc, 1)
        self.assertFalse(any(c[1] in ("disable", "mask") for c in system.changes()))
        self.assertIn("SSH server: ON -- this run reported an error", out)

    def test_an_unexpected_os_error_is_a_reported_failure_not_a_traceback(self):
        system = FakeSystem(installed=False)
        with mock.patch.object(self.h.tempfile, "mkdtemp", side_effect=PermissionError(13, "denied")):
            rc, out, err = self.invoke(["enable"], system)
        self.assertEqual(rc, 1)
        self.assertIn("denied", err)
        self.assertNotIn("Traceback", err)
        self.assertIn("SSH server: OFF", out)
        self.assertIn("failed:", Path(self.patches["LOG_PATH"]).read_text())

    # -- B1: the public 0.2.0 starter password ---------------------------------
    def test_enable_refuses_while_any_account_has_the_starter_password(self):
        self.write_shadow("pleb:" + crypt_hash("plebian") + ":19000:0:99999:7:::",
                          "guest:" + crypt_hash("plebian", "$y$j9T$F5Jx5fExrKuPp53xLKQ..1$")
                          + ":19000:0:99999:7:::")
        with mock.patch.dict(os.environ, {"SUDO_USER": "pleb"}):
            system = FakeSystem(installed=False)
            rc, out, err = self.invoke(["enable"], system)
        self.assertEqual(rc, 2)
        self.assertIn("accounts pleb, guest still use the public Plebian-OS starter password", err)
        self.assertIn("SSH was not turned on and nothing was installed", err)
        self.assertIn("  passwd                  (your own account, pleb)", err)
        self.assertIn("sudo passwd guest", err)
        self.assertIn("sudo passwd -l guest", err)
        self.assertEqual(system.commands("apt-get"), [])
        self.assertEqual(system.changes(), [])
        self.assertTrue(out.rstrip().endswith("SSH server: OFF"), out)
        log = Path(self.patches["LOG_PATH"]).read_text()
        self.assertIn("refused: accounts pleb, guest still use the public Plebian-OS starter "
                      "password. | Anyone could log in", log)
        self.assertNotIn("\nAnyone could log in", log)  # one audit entry per line

    def test_starter_password_refusal_also_covers_an_installed_server(self):
        self.write_shadow("pleb:" + crypt_hash("plebian") + ":19000:0:99999:7:::")
        system = FakeSystem(installed=True)
        rc, out, err = self.invoke(["enable"], system)
        self.assertEqual(rc, 2)
        self.assertIn("account pleb still uses the public", err)
        self.assertEqual(system.changes(), [])
        system.enabled = system.active = True  # already on: say so, change nothing
        rc, out, err = self.invoke(["enable"], system)
        self.assertEqual(rc, 2)
        self.assertEqual(system.changes(), [])
        self.assertIn("SSH server: ON", out)

    def test_a_locked_starter_password_does_not_block_and_a_changed_one_passes(self):
        self.write_shadow("pleb:!" + crypt_hash("plebian") + ":19000:0:99999:7:::",
                          "carol:" + crypt_hash("plebian2") + ":19000:0:99999:7:::")
        system = FakeSystem(installed=True)
        rc, out, err = self.invoke(["enable"], system)
        self.assertEqual(rc, 0, err)
        self.assertIn("Accounts with a password here: alice, bob, carol\n", out)

    def test_enable_refuses_when_passwords_cannot_be_checked(self):
        cases = {
            "unreadable": None,
            "unknown hash": "zed:$9$zz$yy:19000:0:99999:7:::",
        }
        for label, extra in cases.items():
            if extra is None:
                self.shadow.unlink()
            else:
                self.write_shadow(extra)
            system = FakeSystem(installed=False)
            rc, out, err = self.invoke(["enable"], system)
            self.assertEqual(rc, 2, label)
            self.assertIn("cannot", err, label)
            self.assertIn("SSH was not turned on", err, label)
            self.assertEqual(system.commands("apt-get"), [], label)
            self.assertEqual(system.changes(), [], label)
            self.write_shadow()

    def test_disable_never_needs_the_password_check(self):
        self.shadow.unlink()
        system = FakeSystem(installed=True)
        system.enabled = system.active = True
        self.assertEqual(self.invoke(["disable"], system)[0], 0)
        self.assertFalse(system.active)

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

    def test_disable_that_leaves_sshd_running_is_a_failure_that_says_on(self):
        system = FakeSystem(installed=True, stuck=True)
        system.enabled = system.active = True
        rc, out, err = self.invoke(["disable"], system)
        self.assertEqual(rc, 1)
        self.assertIn("could not be turned off completely", err)
        self.assertIn("running: ssh.service", err)
        self.assertIn("SSH server: ON -- this run reported an error", out)

    def test_an_sshd_listening_outside_systemd_counts_as_on(self):
        system = FakeSystem(installed=True, stray_sshd=True)
        rc, out, err = self.invoke(["disable"], system)
        self.assertEqual(rc, 1)
        self.assertIn("sshd listening on 0.0.0.0:22", err)
        self.assertNotIn("cupsd", err + out)

    def test_disable_masks_the_generator_sockets_and_enable_restores_only_those(self):
        system = FakeSystem(installed=True, generated={
            "sshd-vsock.socket": "active", "sshd-unix-local.socket": "inactive",
            "sshd-extra-1.socket": "active"})
        system.enabled = system.active = True
        system.masked.add("sshd-unix-export.socket")  # the owner's own mask
        (self.etc / "sshd-unix-export.socket").symlink_to("/dev/null")
        rc, out, err = self.invoke(["disable"], system)
        self.assertEqual(rc, 0, err)
        for unit in ("sshd-vsock.socket", "sshd-unix-local.socket", "sshd-extra-1.socket"):
            self.assertIn(["systemctl", "mask", "--now", unit], system.calls)
        self.assertNotIn(["systemctl", "mask", "--now", "sshd-unix-export.socket"], system.calls)
        self.assertFalse(any(system._is_active(u) for u in system.generated))
        record = Path(self.patches["MASK_RECORD"])
        self.assertEqual(record.read_text().split(),
                         ["sshd-vsock.socket", "sshd-unix-local.socket", "sshd-extra-1.socket"])
        self.assertEqual(oct(record.stat().st_mode & 0o777), "0o644")
        # A second disable keeps the record and adds nothing.
        self.assertEqual(self.invoke(["disable"], system)[0], 0)
        self.assertEqual(len(record.read_text().split()), 3)
        rc, out, err = self.invoke(["enable"], system)
        self.assertEqual(rc, 0, err)
        unmasked = [c[2] for c in system.changes() if c[1] == "unmask"]
        self.assertEqual(unmasked, ["sshd-vsock.socket", "sshd-unix-local.socket", "sshd-extra-1.socket"])
        self.assertIn("sshd-unix-export.socket", system.masked)  # the owner's mask stays
        self.assertFalse(record.exists())

    def test_the_audit_log_never_carries_an_unvalidated_caller_name(self):
        system = FakeSystem(installed=True)
        with mock.patch.dict(os.environ, {"SUDO_USER": "x\nenabled: forged (requested by root)"}):
            self.invoke(["enable"], system)
        log = Path(self.patches["LOG_PATH"]).read_text()
        self.assertIn("enable (requested by unknown)", log)
        self.assertNotIn("forged", log)

    def test_children_get_default_signal_handling_back(self):
        script = ["sh", "-c", "grep '^SigIgn:' /proc/self/status"]
        saved = {n: signal.getsignal(n) for n in self.h.SHIELDED_SIGNALS}
        self.addCleanup(lambda: [signal.signal(n, h) for n, h in saved.items()])
        for number in self.h.SHIELDED_SIGNALS:
            signal.signal(number, signal.SIG_IGN)
        plain = self.h.run(script).stdout
        out = io.StringIO()
        with redirect_stdout(out):
            self.h.run_shielded(script)
        for text in (plain, out.getvalue()):
            mask = int(text.split()[-1], 16)
            for number in self.h.SHIELDED_SIGNALS:
                self.assertFalse(mask & (1 << (number - 1)), f"{number} ignored in child: {text}")

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

    def test_upgrading_says_how_enable_refuses_and_how_to_turn_ssh_off_after_a_rollback(self):
        text = " ".join((ROOT / "UPGRADING.md").read_text().split())
        self.assertIn("refuses, before installing anything, while any account still has the "
                      "0.2.0 starter password", text)
        self.assertIn("rolled back to a release without the helper, SSH stays on", text)
        self.assertIn("sudo systemctl disable --now ssh.service ssh.socket", text)
        self.assertIn("sudo systemctl mask --now sshd-vsock.socket sshd-unix-local.socket", text)

    def test_helper_is_isolated_python(self):
        first = HELPER.read_text().splitlines()[0]
        self.assertEqual(first, "#!/usr/bin/python3 -I")
        self.assertTrue(os.access(HELPER, os.X_OK))


if __name__ == "__main__":
    unittest.main()
