"""The default-password nag plumbing: the plebian-os-passwd helper's real
check logic (against a shadow fixture), its set-validation, and the provisioner
+ staging that install it with a scoped NOPASSWD sudoers rule."""
import ctypes
import ctypes.util
import importlib.util
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
    def test_provisioner_installs_helper_and_scoped_sudoers(self):
        p = _read("provision", "plebian-os-provision.sh")
        self.assertIn("install_passwd_nag", p)
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

    def test_helper_staged_by_remaster_and_preseed(self):
        self.assertIn("plebian-os-passwd", _read("build", "remaster-iso.sh"))
        preseed_le = _read("preseed", "preseed.cfg")
        self.assertIn("cp /cdrom/plebian-os/plebian-os-passwd "
                      "/target/usr/local/sbin/plebian-os-passwd", preseed_le)

    def test_helper_reads_new_password_from_stdin_not_argv(self):
        # the new password must never appear on the command line (ps-visible)
        h = _read("provision", "plebian-os-passwd")
        self.assertIn("sys.stdin.readline()", h)
        self.assertIn('input=f"{user}:{new}', h)


if __name__ == "__main__":
    unittest.main()
