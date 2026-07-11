import os
import shlex
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build"))

import build_vm_image as vm


def envfile_quote(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


class VmBuilderEnvTests(unittest.TestCase):
    def test_generate_preseed_injects_ref_and_desktop_provider_knobs(self):
        cfg = vm.Config(
            name="test",
            username="pleb",
            fullname="Plebian User",
            password="plebian",
            hostname="plebian",
            ram_mb=1024,
            cpus=1,
            vram_mb=128,
            accelerate_3d=False,
            disk_gb=8,
            desktop=True,
            kiosk=True,
            nopasswd_sudo=True,
            ssh_port=2222,
            gui=False,
            wait=False,
        )
        env = {
            "PLEB_REF": "pleb-v1",
            "KILIX_REF": "kilix-v1",
            "KILIX_PREBUILT_VERSION": "0.47.0",
            "KILIX_PREBUILT_SHA256": "abc123",
            "PLEBIAN_OS_INSTALL_UV": "1",
            "PLEBIAN_OS_BUILD_KILIX_FORK": "1",
            "PLEBIAN_OS_KILIX_GO_MIN_VERSION": "1.26",
            "KILIX_DESKTOP_PROVIDER": "command",
            "KILIX_DESKTOP_COMMAND": "printf 'custom desktop'",
            "KILIX_DESKTOP_NAME": "custom desk",
            "KILIX_DESKTOP_FLAVOR": "xp",
            "KILIX95_AUTO_INSTALL": "0",
        }
        with mock.patch.dict(os.environ, env, clear=False), \
                mock.patch.object(vm, "crypt_password", return_value=("$6$hash", True)):
            preseed = vm.generate_preseed(cfg)
            text = preseed.read_text()

        for key in env:
            self.assertIn(f"{key}=%s", text)
        self.assertIn(shlex.quote(envfile_quote(env["KILIX_DESKTOP_COMMAND"])), text)
        self.assertIn(shlex.quote(envfile_quote(env["KILIX_DESKTOP_NAME"])), text)

    def test_yes_mode_defaults_to_plebian_password(self):
        args = mock.Mock(
            yes=True,
            name=None,
            username=None,
            fullname=None,
            password=None,
            hostname=None,
            ram=None,
            cpus=None,
            vram=None,
            accelerate_3d=False,
            disk=None,
            session=None,
            kiosk=None,
            nopasswd_sudo=None,
            port=None,
            gui=False,
            no_wait=True,
        )
        cfg = vm.gather_config(args)
        self.assertEqual(cfg.password, "plebian")   # default; desktop nags to change

    def test_yes_mode_honors_explicit_password(self):
        args = mock.Mock(
            yes=True,
            name=None,
            username=None,
            fullname=None,
            password="explicit",
            hostname=None,
            ram=None,
            cpus=None,
            vram=None,
            accelerate_3d=False,
            disk=None,
            session=None,
            kiosk=None,
            nopasswd_sudo=None,
            port=None,
            gui=False,
            no_wait=True,
        )
        with mock.patch.object(vm, "generated_password", return_value="random-pass"):
            cfg = vm.gather_config(args)
        self.assertEqual(cfg.password, "explicit")

    def test_vram_is_capped_to_virtualbox_limit(self):
        args = mock.Mock(
            yes=True,
            name=None,
            username=None,
            fullname=None,
            password="explicit",
            hostname=None,
            ram=None,
            cpus=None,
            vram=512,
            accelerate_3d=True,
            disk=None,
            session=None,
            kiosk=None,
            nopasswd_sudo=None,
            port=None,
            gui=False,
            no_wait=True,
        )
        cfg = vm.gather_config(args)
        self.assertEqual(cfg.vram_mb, 256)
        self.assertTrue(cfg.accelerate_3d)


if __name__ == "__main__":
    unittest.main()
