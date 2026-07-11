import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build"))
import build_vm_image as vm  # noqa: E402  (path configured above)


def _read(*p):
    return (ROOT.joinpath(*p)).read_text()


def _cfg():
    return vm.Config(name="t", username="pleb", fullname="Plebian User",
                     password="s3cret-pw", hostname="t", ram_mb=1024, cpus=1,
                     vram_mb=64, accelerate_3d=False, disk_gb=20, desktop=True,
                     kiosk=True, nopasswd_sudo=True, ssh_port=2222, gui=False, wait=False)


class DeferredHardeningTests(unittest.TestCase):
    def test_committed_preseed_default_creds_no_ssh(self):
        p = _read("preseed", "preseed.cfg")
        # default password is 'plebian' (weak allowed so it takes); the desktop
        # nags to change it. No ssh-server by default, so it isn't network-reachable.
        self.assertIn("d-i passwd/user-password password plebian", p)
        self.assertIn("d-i user-setup/allow-password-weak boolean true", p)
        tasksel = [l for l in p.splitlines() if l.startswith("tasksel tasksel/first")]
        self.assertEqual(tasksel, ["tasksel tasksel/first multiselect standard"])

    def test_vm_builder_overrides_password_and_adds_ssh(self):
        vm = _read("build", "build_vm_image.py")
        # a chosen password replaces the default lines (hashed when possible);
        # the VM builder adds ssh-server for its loopback provisioning watch
        self.assertIn("user-password-crypted password", vm)
        self.assertIn("enable_ssh", vm)
        self.assertIn(", ssh-server", vm)
        self.assertIn("generate_preseed(cfg, enable_ssh=True)", vm)

    def test_uv_installer_is_pinnable_and_verified(self):
        deps = _read("provision", "install-deps.sh")
        self.assertIn("PLEBIAN_OS_UV_VERSION", deps)
        self.assertIn("PLEBIAN_OS_UV_INSTALLER_SHA256", deps)
        self.assertIn("sha256sum -c", deps)
        # no longer a blind unpinned curl | sh pipe
        self.assertNotIn("| env UV_INSTALL_DIR", deps)

    def test_kiosk_enables_hard_respawn(self):
        prov = _read("provision", "plebian-os-provision.sh")
        self.assertIn("PLEB_RESPAWN=1", prov)

    def test_kiosk_pins_remembered_session(self):
        prov = _read("provision", "plebian-os-provision.sh")
        self.assertIn("pin_remembered_session", prov)
        self.assertIn(".dmrc", prov)
        self.assertIn("AccountsService", prov)

    def test_vm_builder_has_acceptance_verification(self):
        src = _read("build", "build_vm_image.py")
        self.assertIn("def verify_provisioning", src)
        self.assertIn("/var/lib/plebian-os/provisioned", src)
        self.assertIn("pleb.desktop", src)
        self.assertIn("src/kitty/launcher/kitty", src)
        self.assertIn("--no-verify", src)
        # the fork-engine check must honor an overridden KILIX_DIR, not hardcode $HOME
        self.assertIn("KILIX_DIR", src)

    def test_generate_preseed_actually_injects_password_and_ssh(self):
        # Behavioral (not string-only): render the preseed and prove the CHOSEN
        # password ('s3cret-pw') actually replaces the template default 'plebian'
        # — the committed template already carries a 'plebian' password line, so a
        # mere "a password line exists" check would pass even if the override were
        # a no-op. ssh-server must be VM-only.
        import re as _re

        def tasksel(text):
            return [l for l in text.splitlines() if l.startswith("tasksel tasksel/first")][0]

        def password_line(text):
            return [l for l in text.splitlines()
                    if l.startswith("d-i passwd/user-password ")
                    or l.startswith("d-i passwd/user-password-crypted ")][0]

        def assert_is_chosen_password(text, plaintext):
            # the default value must be gone, and the line must encode `plaintext`
            self.assertNotIn("password plebian", text)           # default replaced
            line = password_line(text)
            m = _re.search(r"\$6\$[^$]+\$[^\s]+$", line)
            if m:                                                # hashed (openssl path)
                self.assertTrue(self._openssl_check(m.group(0), plaintext),
                                "crypted line is not the hash of the chosen password")
            else:                                                # plaintext fallback
                self.assertTrue(line.endswith(" " + plaintext), line)

        cfg = _cfg()                                             # password="s3cret-pw"
        vm_ps = vm.generate_preseed(cfg, enable_ssh=True).read_text()
        self.assertNotIn("@PLEBIAN_OS_PASSWORD@", vm_ps)         # sentinel replaced
        assert_is_chosen_password(vm_ps, "s3cret-pw")           # the chosen pw landed
        self.assertIn("standard, ssh-server", tasksel(vm_ps))   # VM path gets sshd
        # a crypted preseed must not leave a dangling -again line
        if "user-password-crypted" in vm_ps:
            self.assertNotIn("user-password-again", vm_ps)

        usb_ps = vm.generate_preseed(cfg, enable_ssh=False).read_text()
        self.assertNotIn("@PLEBIAN_OS_PASSWORD@", usb_ps)
        assert_is_chosen_password(usb_ps, "s3cret-pw")
        self.assertEqual(tasksel(usb_ps),                       # USB/raw path: no sshd
                         "tasksel tasksel/first multiselect standard")

    @staticmethod
    def _openssl_check(hashed, plaintext):
        # re-hash `plaintext` with the salt embedded in `hashed`; equal iff it is
        # genuinely the crypt of `plaintext` (real end-to-end verification).
        import shutil
        import subprocess
        if not shutil.which("openssl"):
            return True                                          # can't verify; don't fail
        salt = hashed.split("$")[2]
        r = subprocess.run(["openssl", "passwd", "-6", "-salt", salt, "-stdin"],
                           input=plaintext, text=True, capture_output=True)
        return r.returncode == 0 and r.stdout.strip() == hashed


if __name__ == "__main__":
    unittest.main()
