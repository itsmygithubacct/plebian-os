import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build"))

import build_vm_image as vm


def args(**overrides):
    values = dict(
        yes=True, name=None, username=None, fullname=None, password="explicit",
        hostname=None, ram=None, cpus=None, vram=None, accelerate_3d=False,
        disk=None, session=None, kiosk=None, nopasswd_sudo=None, port=None,
        gui=False, no_wait=True,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def cfg(**overrides):
    values = dict(
        name="test", username="pleb", fullname="Plebian User",
        password="strong-secret", hostname="plebian", ram_mb=1024, cpus=1,
        vram_mb=128, accelerate_3d=False, disk_gb=8, desktop=True,
        kiosk=True, nopasswd_sudo=False, ssh_port=2222, gui=False, wait=False,
    )
    values.update(overrides)
    return vm.Config(**values)


class VmBuilderEnvTests(unittest.TestCase):
    def test_preseed_has_identity_but_no_second_runtime_env_writer(self):
        with mock.patch.object(vm, "crypt_password", return_value=("$6$hash", True)):
            text = vm.generate_preseed(cfg()).read_text()
        self.assertIn("d-i passwd/username string pleb", text)
        self.assertIn("d-i passwd/user-password-crypted password $6$hash", text)
        self.assertNotIn("PLEB_REF=%s", text)
        self.assertNotIn("env_fmt", text)

    def test_build_iso_forwards_authoritative_runtime_config(self):
        seen = {}
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.iso"
            seed = Path(td) / "preseed.cfg"
            seed.write_text("seed\n")

            def fake_run(_argv, **kwargs):
                seen.update(kwargs["env"])
                out.write_bytes(b"iso")

            with mock.patch.object(vm, "run", side_effect=fake_run):
                vm.build_iso(cfg(), seed, out, False)

        expected = vm.runtime_build_env(cfg())
        for key, value in expected.items():
            self.assertEqual(seen[key], value)
        self.assertEqual(seen["PLEBIAN_OS_SSH_ENABLED"], "1")
        self.assertEqual(seen["PLEBIAN_OS_AUTOBOOT"], "1")
        self.assertEqual(seen["PLEBIAN_OS_UNATTENDED_DISK"], "1")

    def test_acceptance_checks_coordinated_source_allocation(self):
        source = (ROOT / "build" / "build_vm_image.py").read_text()
        self.assertIn('"coordinated checkouts"', source)
        self.assertIn('"pleb recovery guide"', source)
        self.assertIn("/usr/local/share/doc/pleb/RECOVERY.md", source)
        self.assertIn("PLEBIAN_OS_COMMIT=[0-9a-f]{40}", source)
        for checkout in ("PLEBIAN_OS_DIR", "PLEB_DIR", "KILIX_DIR"):
            self.assertIn(checkout, source[source.index("def verify_provisioning"):])

    def test_acceptance_checks_private_storage_roots(self):
        source = (ROOT / "build" / "build_vm_image.py").read_text()
        verify = source[source.index("def verify_provisioning"):]
        self.assertIn('"private storage roots"', verify)
        for root in (
            "GPU_TERMINAL_HOME",
            "PLEB_STORAGE_HOME",
            "KILIX_STORAGE_HOME",
            "KILIX95_STORAGE_HOME",
            "PLEBIAN_OS_STORAGE_HOME",
        ):
            self.assertIn(root, verify)
        self.assertIn("stat -c \\'%u\\'", verify)
        self.assertIn("stat -c \\'%a\\'", verify)
        self.assertIn("readlink -m", verify)
        self.assertIn('case "$g" in "$HOME"/*)', verify)
        self.assertIn('= 700 ] || exit 1', verify)

    def test_yes_mode_generates_password(self):
        with mock.patch.object(vm, "generated_password", return_value="random-pass"):
            built = vm.gather_config(args(password=None))
        self.assertEqual(built.password, "random-pass")

    def test_yes_mode_honors_explicit_password(self):
        with mock.patch.object(vm, "generated_password", return_value="random-pass"):
            built = vm.gather_config(args(password="explicit"))
        self.assertEqual(built.password, "explicit")

    def test_vram_is_capped_to_virtualbox_limit(self):
        built = vm.gather_config(args(vram=512, accelerate_3d=True))
        self.assertEqual(built.vram_mb, 256)
        self.assertTrue(built.accelerate_3d)

    def test_default_ram_uses_release_tested_floor(self):
        with mock.patch.object(vm, "host_ram_mb", return_value=8192):
            self.assertEqual(vm.default_ram_mb(), 4096)
        with mock.patch.object(vm, "host_ram_mb", return_value=32768):
            self.assertEqual(vm.default_ram_mb(), 8192)

    def test_explicit_low_ram_is_honored_with_warning(self):
        with mock.patch.object(vm, "warn") as warn:
            built = vm.gather_config(args(ram=2048))
        self.assertEqual(built.ram_mb, 2048)
        self.assertIn("below the 4096 MB release-tested", warn.call_args.args[0])

    def test_identity_values_are_rejected_before_preseed_or_vbox(self):
        bad = (
            dict(name="../escape"),
            dict(username="root;touch-x"),
            dict(username="root"),
            dict(username="_service"),
            dict(fullname="Name:newline"),
            dict(hostname="bad host"),
            dict(password="bad\nsecret"),
        )
        for values in bad:
            with self.subTest(values=values), self.assertRaises(SystemExit):
                vm.validate_identity(**{
                    "name": "test", "username": "pleb", "fullname": "Plebian User",
                    "password": "secret", "hostname": "test", **values,
                })

    def test_existing_vm_needs_explicit_replace(self):
        with mock.patch.object(vm, "vbox_exists", return_value=True), \
                mock.patch.object(vm, "run") as run:
            with self.assertRaises(SystemExit):
                vm.vbox_create(cfg(), Path("image.iso"), assume_yes=True)
        run.assert_not_called()

    def test_replace_and_yes_is_the_explicit_delete_gate(self):
        calls = []
        with mock.patch.object(vm, "vbox_exists", return_value=True), \
                mock.patch.object(vm, "run", side_effect=lambda argv, **_kw: calls.append(argv)), \
                mock.patch.object(vm, "vbox_info", return_value={"CfgFile": "/tmp/test/test.vbox"}), \
                mock.patch.object(vm.subprocess, "run"), \
                mock.patch.object(vm.time, "sleep"):
            vm.vbox_create(cfg(), Path("image.iso"), replace=True, assume_yes=True)
        self.assertIn(["VBoxManage", "unregistervm", "test", "--delete"], calls)

    def test_openssl_failure_never_falls_back_to_plaintext(self):
        result = SimpleNamespace(returncode=1, stdout="", stderr="failed")
        with mock.patch.object(vm, "have", return_value=True), \
                mock.patch.object(vm.subprocess, "run", return_value=result), \
                self.assertRaises(SystemExit):
            vm.crypt_password("secret")


if __name__ == "__main__":
    unittest.main()
