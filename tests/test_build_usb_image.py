import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build"))

import build_usb_image as usb


class UsbBuilderTests(unittest.TestCase):
    def test_interactive_usb_preseed_removes_unattended_partitioning(self):
        cfg = usb.Config(
            name="test",
            username="pleb",
            fullname="Plebian User",
            password="plebian",
            hostname="plebian",
            desktop=True,
            kiosk=False,
            nopasswd_sudo=False,
        )
        with tempfile.TemporaryDirectory() as td:
            preseed = Path(td) / "preseed.cfg"
            preseed.write_text(
                "d-i partman-auto/method string regular\n"
                "d-i partman-auto/choose_recipe select atomic\n"
                "d-i partman-partitioning/confirm_write_new_label boolean true\n"
                "d-i partman/choose_partition select finish\n"
                "d-i partman/confirm boolean true\n"
                "d-i passwd/username string pleb\n"
            )
            with mock.patch.object(usb.vm, "generate_preseed", return_value=preseed):
                out = usb.make_usb_preseed(cfg, unattended_disk=False)
            text = out.read_text()
        self.assertNotIn("partman-auto", text)
        self.assertNotIn("partman/confirm", text)
        self.assertIn("passwd/username", text)

    def test_unattended_usb_preseed_keeps_partitioning(self):
        cfg = usb.Config("test", "pleb", "Plebian User", "plebian",
                         "plebian", True, False, False)
        with tempfile.TemporaryDirectory() as td:
            preseed = Path(td) / "preseed.cfg"
            preseed.write_text("d-i partman-auto/method string regular\n")
            with mock.patch.object(usb.vm, "generate_preseed", return_value=preseed):
                out = usb.make_usb_preseed(cfg, unattended_disk=True)
            text = out.read_text()
        self.assertIn("partman-auto/method", text)

    def test_ancestor_set_tracks_parents(self):
        parents = {"dm-0": "sda2", "sda2": "sda"}
        self.assertEqual(usb._ancestors("dm-0", parents), {"dm-0", "sda2", "sda"})

    def test_yes_mode_generates_password_when_omitted(self):
        args = mock.Mock(
            yes=True,
            name=None,
            username=None,
            fullname=None,
            password=None,
            hostname=None,
            session=None,
            kiosk=None,
            nopasswd_sudo=None,
        )
        with mock.patch.object(usb.vm, "generated_password", return_value="random-pass"):
            cfg = usb.gather_config(args)
        self.assertEqual(cfg.password, "random-pass")

    def test_yes_mode_honors_explicit_password(self):
        args = mock.Mock(
            yes=True,
            name=None,
            username=None,
            fullname=None,
            password="explicit",
            hostname=None,
            session=None,
            kiosk=None,
            nopasswd_sudo=None,
        )
        with mock.patch.object(usb.vm, "generated_password", return_value="random-pass"):
            cfg = usb.gather_config(args)
        self.assertEqual(cfg.password, "explicit")


if __name__ == "__main__":
    unittest.main()
