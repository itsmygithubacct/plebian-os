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
            "KILIX_DESKTOP_PROVIDER": "command",
            "KILIX_DESKTOP_COMMAND": "printf 'custom desktop'",
            "KILIX_DESKTOP_NAME": "custom desk",
        }
        with mock.patch.dict(os.environ, env, clear=False), \
                mock.patch.object(vm, "crypt_password", return_value=("$6$hash", True)):
            preseed = vm.generate_preseed(cfg)
            text = preseed.read_text()

        for key in env:
            self.assertIn(f"{key}=%s", text)
        self.assertIn(shlex.quote(envfile_quote(env["KILIX_DESKTOP_COMMAND"])), text)
        self.assertIn(shlex.quote(envfile_quote(env["KILIX_DESKTOP_NAME"])), text)


if __name__ == "__main__":
    unittest.main()
