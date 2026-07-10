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
    def test_committed_preseed_has_no_password_or_ssh(self):
        p = _read("preseed", "preseed.cfg")
        # no committed account password (builders inject a hashed one)
        self.assertNotIn("user-password password ", p)
        self.assertIn("@PLEBIAN_OS_PASSWORD@", p)       # sentinel the builders replace
        # tasksel ships STANDARD only — no ssh-server by default
        tasksel = [l for l in p.splitlines() if l.startswith("tasksel tasksel/first")]
        self.assertEqual(tasksel, ["tasksel tasksel/first multiselect standard"])

    def test_vm_builder_injects_password_and_ssh(self):
        vm = _read("build", "build_vm_image.py")
        self.assertIn("@PLEBIAN_OS_PASSWORD@", vm)       # replaces the sentinel
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
        # Behavioral (not string-only): render the preseed and prove the sentinel
        # is replaced by a real password line, and ssh-server is VM-only.
        def tasksel(text):
            return [l for l in text.splitlines() if l.startswith("tasksel tasksel/first")][0]

        def has_password(text):
            return any(l.startswith("d-i passwd/user-password") for l in text.splitlines())

        cfg = _cfg()
        vm_ps = vm.generate_preseed(cfg, enable_ssh=True).read_text()
        self.assertNotIn("@PLEBIAN_OS_PASSWORD@", vm_ps)          # sentinel replaced
        self.assertTrue(has_password(vm_ps))                     # real password line landed
        self.assertIn("standard, ssh-server", tasksel(vm_ps))    # VM path gets sshd

        usb_ps = vm.generate_preseed(cfg, enable_ssh=False).read_text()
        self.assertNotIn("@PLEBIAN_OS_PASSWORD@", usb_ps)
        self.assertTrue(has_password(usb_ps))
        self.assertEqual(tasksel(usb_ps),                        # USB/raw path: no sshd
                         "tasksel tasksel/first multiselect standard")


if __name__ == "__main__":
    unittest.main()
