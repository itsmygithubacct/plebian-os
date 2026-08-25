"""Legacy 0.2.0 credential containment and the local transition helper."""
import ctypes
import ctypes.util
import contextlib
import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(*p):
    return (ROOT.joinpath(*p)).read_text()


def _load_helper():
    from importlib.machinery import SourceFileLoader
    loader = SourceFileLoader("plebian_os_passwd",
                              str(ROOT / "provision" / "plebian-os-passwd"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def _crypt(word, setting):
    lib = ctypes.CDLL(ctypes.util.find_library("crypt") or "libcrypt.so.1")
    lib.crypt.restype = ctypes.c_char_p
    lib.crypt.argtypes = (ctypes.c_char_p, ctypes.c_char_p)
    lib.crypt_gensalt.restype = ctypes.c_char_p
    lib.crypt_gensalt.argtypes = (ctypes.c_char_p, ctypes.c_ulong,
                                  ctypes.c_char_p, ctypes.c_int)
    if setting is None:                       # generate a fresh yescrypt salt
        setting = lib.crypt_gensalt(b"$y$", 0, os.urandom(16), 16).decode()
    return lib.crypt(word.encode(), setting.encode()).decode()


@contextlib.contextmanager
def _legacy_upgrade_fixture(password, user="operator"):
    """A nonprivileged shadow/SSH fixture plus identity state that must survive."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ssh = root / "ssh"
        ssh.mkdir(mode=0o755)
        sshd_config = ssh / "sshd_config"
        sshd_config.write_text(
            "Include sshd_config.d/*.conf\n"
            "PasswordAuthentication yes\n"
            "KbdInteractiveAuthentication yes\n"
        )
        sshd_config.chmod(0o644)
        shadow = root / "shadow"
        shadow.write_text(
            f"root:*:1::::::\n{user}:{_crypt(password, None)}:20000:0:99999:7:::\n"
        )
        hostname = root / "hostname"
        hostname.write_text("kept-host\n")
        autologin = root / "autologin.conf"
        autologin.write_text(f"autologin-user={user}\n")
        home = root / "home" / user
        home.mkdir(parents=True, mode=0o750)
        sentinel = home / "sentinel"
        sentinel.write_text("keep\n")
        preserved = {
            "shadow": shadow.read_bytes(),
            "hostname": hostname.read_bytes(),
            "autologin": autologin.read_bytes(),
            "home_uid": home.stat().st_uid,
            "home_mode": home.stat().st_mode,
            "sentinel": sentinel.read_bytes(),
        }
        old_shadow = os.environ.get("PLEBIAN_OS_SHADOW")
        old_ssh = os.environ.get("PLEBIAN_OS_SSH_CONFIG_ROOT")
        os.environ["PLEBIAN_OS_SHADOW"] = str(shadow)
        os.environ["PLEBIAN_OS_SSH_CONFIG_ROOT"] = str(ssh)
        try:
            yield _load_helper(), {
                "root": root,
                "ssh": ssh,
                "dropin": ssh / "sshd_config.d" /
                          "50-plebian-os-legacy-default.conf",
                "shadow": shadow,
                "hostname": hostname,
                "autologin": autologin,
                "home": home,
                "sentinel": sentinel,
                "preserved": preserved,
                "user": user,
            }
        finally:
            if old_shadow is None:
                os.environ.pop("PLEBIAN_OS_SHADOW", None)
            else:
                os.environ["PLEBIAN_OS_SHADOW"] = old_shadow
            if old_ssh is None:
                os.environ.pop("PLEBIAN_OS_SSH_CONFIG_ROOT", None)
            else:
                os.environ["PLEBIAN_OS_SSH_CONFIG_ROOT"] = old_ssh


def _assert_identity_preserved(testcase, fixture):
    preserved = fixture["preserved"]
    testcase.assertEqual(fixture["shadow"].read_bytes(), preserved["shadow"])
    testcase.assertEqual(fixture["hostname"].read_bytes(), preserved["hostname"])
    testcase.assertEqual(fixture["autologin"].read_bytes(), preserved["autologin"])
    testcase.assertEqual(fixture["home"].stat().st_uid, preserved["home_uid"])
    testcase.assertEqual(fixture["home"].stat().st_mode, preserved["home_mode"])
    testcase.assertEqual(fixture["sentinel"].read_bytes(), preserved["sentinel"])


class PasswdHelperCheckTests(unittest.TestCase):
    """cmd_check must recognise the default password across hash schemes and
    treat anything else (or a locked account) as not-default."""

    def _run_check(self, stored_hash, user="pleb"):
        fd, path = tempfile.mkstemp(prefix="plebshadow-")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(f"root:*:1::::::\n{user}:{stored_hash}:20000:0:99999:7:::\n")
            os.environ["PLEBIAN_OS_SHADOW"] = path
            return _load_helper().cmd_check(user)
        finally:
            os.environ.pop("PLEBIAN_OS_SHADOW", None)
            os.unlink(path)

    def test_default_yescrypt_is_detected(self):
        self.assertEqual(self._run_check(_crypt("plebian", None)), 0)

    def test_default_sha512_is_detected(self):
        self.assertEqual(self._run_check(_crypt("plebian", "$6$abcdefghijklmnop")), 0)

    def test_changed_password_is_not_default(self):
        self.assertEqual(self._run_check(_crypt("something-else", None)), 1)

    def test_locked_account_is_not_default(self):
        self.assertEqual(self._run_check("!"), 1)
        self.assertEqual(self._run_check("*"), 1)


class PasswdHelperSetValidationTests(unittest.TestCase):
    """cmd_set must refuse an empty or default new password BEFORE calling
    chpasswd (so these paths need no root)."""

    def _set(self, newpw):
        import io
        import sys
        mod = _load_helper()
        old = sys.stdin
        sys.stdin = io.StringIO(newpw + "\n")
        try:
            return mod.cmd_set("pleb")
        finally:
            sys.stdin = old

    def test_empty_refused(self):
        with self.assertRaises(SystemExit) as e:
            self._set("")
        self.assertEqual(e.exception.code, 2)

    def test_default_refused(self):
        with self.assertRaises(SystemExit) as e:
            self._set("plebian")
        self.assertEqual(e.exception.code, 2)


class HardenedPasswordResetRegressionTests(unittest.TestCase):
    """The NOPASSWD helper is only a transition away from the shipped secret.

    Once the shadow hash changes, an unprivileged process must not be able to
    choose another password and then use it to authenticate to ordinary sudo.
    """

    def test_changed_password_cannot_be_reset(self):
        import io
        import sys

        fd, path = tempfile.mkstemp(prefix="plebshadow-hardened-")
        called = False
        old_env = os.environ.get("PLEBIAN_OS_SHADOW")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(f"pleb:{_crypt('owner-secret', None)}:20000:0:99999:7:::\n")
            os.environ["PLEBIAN_OS_SHADOW"] = path
            mod = _load_helper()

            def forbidden_run(*_args, **_kwargs):
                nonlocal called
                called = True
                raise AssertionError("chpasswd must not run for a hardened account")

            old_run, old_stdin = mod.subprocess.run, sys.stdin
            mod.subprocess.run = forbidden_run
            sys.stdin = io.StringIO("attacker-chosen\n")
            try:
                with self.assertRaises(SystemExit) as e:
                    mod.cmd_set("pleb")
                self.assertEqual(e.exception.code, 2)
            finally:
                mod.subprocess.run = old_run
                sys.stdin = old_stdin
        finally:
            if old_env is None:
                os.environ.pop("PLEBIAN_OS_SHADOW", None)
            else:
                os.environ["PLEBIAN_OS_SHADOW"] = old_env
            os.unlink(path)
        self.assertFalse(called)


class TargetUserTests(unittest.TestCase):
    """target_user() is the whole safety property of the NOPASSWD grant: the
    helper only ever acts on $SUDO_USER, never root and never an empty caller."""

    def _target(self, sudo_user):
        mod = _load_helper()
        old = os.environ.get("SUDO_USER")
        if sudo_user is None:
            os.environ.pop("SUDO_USER", None)
        else:
            os.environ["SUDO_USER"] = sudo_user
        try:
            return mod.target_user()
        finally:
            if old is None:
                os.environ.pop("SUDO_USER", None)
            else:
                os.environ["SUDO_USER"] = old

    def test_normal_user_is_returned(self):
        self.assertEqual(self._target("pleb"), "pleb")

    def test_root_is_refused(self):
        with self.assertRaises(SystemExit) as e:
            self._target("root")
        self.assertEqual(e.exception.code, 2)

    def test_unset_is_refused(self):
        with self.assertRaises(SystemExit) as e:
            self._target(None)
        self.assertEqual(e.exception.code, 2)

    def test_empty_is_refused(self):
        with self.assertRaises(SystemExit) as e:
            self._target("")
        self.assertEqual(e.exception.code, 2)

    def test_non_debian_account_names_are_refused(self):
        for user in ("Upper", "_service", "-option", "name;command",
                     "a" * 33, "name\nMatch all"):
            with self.subTest(user=user), self.assertRaises(SystemExit) as e:
                self._target(user)
            self.assertEqual(e.exception.code, 2)


class LegacyRemotePolicyTests(unittest.TestCase):
    def test_default_hash_disables_remote_password_for_only_that_user(self):
        with _legacy_upgrade_fixture("plebian") as (mod, fixture):
            output = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                self.assertEqual(mod.cmd_reconcile_remote(fixture["user"]), 0)
            expected = mod.remote_policy(fixture["user"])
            self.assertEqual(fixture["dropin"].read_bytes(), expected)
            self.assertEqual(fixture["dropin"].stat().st_mode & 0o777, 0o644)
            policy = expected.decode()
            self.assertIn(f"Match User {fixture['user']}\n", policy)
            self.assertIn("PasswordAuthentication no\n", policy)
            self.assertIn("KbdInteractiveAuthentication no\n", policy)
            self.assertTrue(policy.endswith("Match all\n"))
            self.assertNotIn(mod.DEFAULT_PASSWORD, policy)
            # Ignore the helper's own project-name prefix (`plebian-os-*`);
            # the status payload must not disclose the historical password.
            status_payload = output.getvalue().partition(": ")[2]
            self.assertNotIn(mod.DEFAULT_PASSWORD, status_payload)
            _assert_identity_preserved(self, fixture)

    def test_changed_hash_leaves_remote_policy_untouched(self):
        with _legacy_upgrade_fixture("owner-secret") as (mod, fixture):
            before = fixture["ssh"].joinpath("sshd_config").read_bytes()
            self.assertEqual(mod.cmd_reconcile_remote(fixture["user"]), 0)
            self.assertFalse(fixture["dropin"].exists())
            self.assertEqual(
                fixture["ssh"].joinpath("sshd_config").read_bytes(), before)
            _assert_identity_preserved(self, fixture)

    def test_changed_hash_removes_only_the_exact_managed_policy(self):
        with _legacy_upgrade_fixture("owner-secret") as (mod, fixture):
            fixture["dropin"].parent.mkdir(mode=0o755)
            fixture["dropin"].write_bytes(mod.remote_policy(fixture["user"]))
            fixture["dropin"].chmod(0o644)
            self.assertEqual(mod.cmd_reconcile_remote(fixture["user"]), 0)
            self.assertFalse(fixture["dropin"].exists())
            _assert_identity_preserved(self, fixture)

    def test_nonmatching_dropin_is_never_replaced_or_removed(self):
        for password in ("plebian", "owner-secret"):
            with self.subTest(password=password):
                with _legacy_upgrade_fixture(password) as (mod, fixture):
                    fixture["dropin"].parent.mkdir(mode=0o755)
                    foreign = b"# operator policy\nPasswordAuthentication no\n"
                    fixture["dropin"].write_bytes(foreign)
                    fixture["dropin"].chmod(0o644)
                    if password == "plebian":
                        with self.assertRaises(SystemExit) as error:
                            mod.cmd_reconcile_remote(fixture["user"])
                        self.assertEqual(error.exception.code, 2)
                    else:
                        self.assertEqual(
                            mod.cmd_reconcile_remote(fixture["user"]), 0)
                    self.assertEqual(fixture["dropin"].read_bytes(), foreign)
                    _assert_identity_preserved(self, fixture)


class PasswdHelperSetSuccessTests(unittest.TestCase):
    """cmd_set's success path must format exactly '<user>:<newpw>\\n' for chpasswd
    on stdin and exit 0 — chpasswd is stubbed so this needs no root."""

    def test_success_payload_and_exit(self):
        import io
        import sys
        import types
        mod = _load_helper()
        captured = {}

        def fake_run(argv, input=None, text=None, capture_output=None):
            captured["argv"], captured["input"] = argv, input
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")

        old_run, old_stdin = mod.subprocess.run, sys.stdin
        mod.subprocess.run = fake_run
        mod.cmd_check = lambda _user: 0
        sys.stdin = io.StringIO("new-secret\n")
        with tempfile.TemporaryDirectory() as td:
            rule = Path(td) / "plebian-os-passwd"
            rule.write_text("one-time grant\n")
            mod.SUDOERS_RULE = str(rule)
            try:
                rc = mod.cmd_set("pleb")
            finally:
                mod.subprocess.run = old_run
                sys.stdin = old_stdin
            self.assertFalse(rule.exists(), "successful transition must retire sudoers grant")
        self.assertEqual(rc, 0)
        self.assertEqual(captured["input"], "pleb:new-secret\n")
        # invoked as an argv list (no shell), by absolute path when present
        self.assertIsInstance(captured["argv"], list)
        self.assertTrue(captured["argv"][0].endswith("chpasswd"))


class ProvisioningPlumbingTests(unittest.TestCase):
    def test_provisioner_installs_bridge_only_for_legacy_identity(self):
        p = _read("provision", "plebian-os-provision.sh")
        self.assertIn("install_passwd_nag", p)
        self.assertIn("has_fresh_identity_profile", p)
        self.assertIn("fresh identity profile has no legacy password transition", p)
        self.assertIn('rm -f -- "$rule" "$dst"', p)
        self.assertIn("/usr/local/sbin/plebian-os-passwd", p)
        self.assertIn("/etc/sudoers.d/plebian-os-passwd", p)
        # scoped to exactly the one command, not general passwordless sudo
        self.assertIn("NOPASSWD: %s", p)
        self.assertIn("visudo -cf", p)

    def test_reprovision_does_not_recreate_grant_after_password_change(self):
        p = _read("provision", "plebian-os-provision.sh")
        check = 'SUDO_USER="$TARGET_USER" "$dst" check'
        write = "NOPASSWD: %s"
        self.assertIn(check, p)
        self.assertIn('password_state" != default', p)
        self.assertIn('rm -f "$rule"', p)
        self.assertLess(p.index(check), p.index(write),
                        "shadow state must be checked before writing the grant")

    def test_fresh_media_does_not_stage_legacy_helper(self):
        remaster = _read("build", "remaster-iso.sh")
        self.assertNotIn(
            'cp "$HERE/provision/plebian-os-passwd"', remaster)
        preseed_le = _read("preseed", "preseed.cfg")
        self.assertNotIn("cp /cdrom/plebian-os/plebian-os-passwd", preseed_le)
        self.assertIn("plebian-os-passwd", _read(
            "provision", "plebian-os-update.sh"))

    def test_updater_reconciles_remote_policy_inside_outer_transaction(self):
        update = _read("provision", "plebian-os-update.sh")
        production = update[update.rindex(
            "# Capture the complete old runtime boundary"):]
        self.assertLess(
            production.index("self_update_os_layer\n"),
            production.index("reconcile_legacy_remote_login\n"),
        )
        self.assertLess(
            production.index("reconcile_legacy_remote_login\n"),
            production.index("test_fail_after_boundary os-layer\n"),
        )
        path = "/etc/ssh/sshd_config.d/50-plebian-os-legacy-default.conf"
        self.assertEqual(update.count(path), 2)
        self.assertEqual(update.count("    /etc/ssh/sshd_config.d\n"), 2)
        self.assertIn("fresh identity profile has no legacy remote credential", update)
        self.assertIn("systemctl reload ssh.service", update)

    def test_helper_reads_new_password_from_stdin_not_argv(self):
        # the new password must never appear on the command line (ps-visible)
        h = _read("provision", "plebian-os-passwd")
        self.assertIn("sys.stdin.readline()", h)
        self.assertIn('input=f"{user}:{new}', h)


if __name__ == "__main__":
    unittest.main()
