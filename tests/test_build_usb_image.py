import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build"))

import build_usb_image as usb


def args(**overrides):
    values = dict(
        yes=True, name=None, username=None, fullname=None, password="explicit",
        hostname=None, session=None, kiosk=None, nopasswd_sudo=None,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def cfg(**overrides):
    values = dict(name="test", username="pleb", fullname="Plebian User",
                  password="strong-secret", hostname="plebian", desktop=True,
                  kiosk=False, nopasswd_sudo=False)
    values.update(overrides)
    return usb.Config(**values)


class UsbBuilderTests(unittest.TestCase):
    def test_interactive_usb_preseed_removes_unattended_partitioning(self):
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
                out = usb.make_usb_preseed(cfg(), unattended_disk=False)
            text = out.read_text()
        self.assertNotIn("partman-auto", text)
        self.assertNotIn("partman/confirm", text)
        self.assertIn("passwd/username", text)

    def test_unattended_usb_preseed_keeps_partitioning(self):
        with tempfile.TemporaryDirectory() as td:
            preseed = Path(td) / "preseed.cfg"
            preseed.write_text("d-i partman-auto/method string regular\n")
            with mock.patch.object(usb.vm, "generate_preseed", return_value=preseed):
                out = usb.make_usb_preseed(cfg(), unattended_disk=True)
            text = out.read_text()
        self.assertIn("partman-auto/method", text)

    def test_usb_can_explicitly_add_ssh_for_vm_acceptance(self):
        with tempfile.TemporaryDirectory() as td:
            preseed = Path(td) / "preseed.cfg"
            preseed.write_text("tasksel tasksel/first multiselect standard\n")
            with mock.patch.object(usb.vm, "generate_preseed", return_value=preseed) as gen:
                usb.make_usb_preseed(cfg(), unattended_disk=True, enable_ssh=True)
        gen.assert_called_once_with(cfg(), enable_ssh=True)

    def test_ancestor_set_tracks_every_raid_parent(self):
        parents = {
            "dm-0": {"md0"}, "md0": {"sda2", "sdb2"},
            "sda2": {"sda"}, "sdb2": {"sdb"},
        }
        self.assertEqual(
            usb._ancestors("dm-0", parents),
            {"dm-0", "md0", "sda2", "sdb2", "sda", "sdb"},
        )

    def test_yes_mode_generates_password(self):
        with mock.patch.object(usb.vm, "generated_password", return_value="random-pass"):
            built = usb.gather_config(args(password=None))
        self.assertEqual(built.password, "random-pass")

    def test_yes_mode_honors_explicit_password(self):
        with mock.patch.object(usb.vm, "generated_password", return_value="random-pass"):
            built = usb.gather_config(args(password="explicit"))
        self.assertEqual(built.password, "explicit")

    def test_remaster_receives_same_runtime_values_as_vm_builder(self):
        seen = {}
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.iso"
            seed = Path(td) / "preseed.cfg"
            seed.write_text("seed\n")

            def fake_run(_argv, **kwargs):
                seen.update(kwargs["env"])
                out.write_bytes(b"iso")

            with mock.patch.object(usb.vm, "run", side_effect=fake_run):
                usb.build_iso(cfg(), seed, out, False, False, False,
                              ssh_enabled=True)
        for key, value in usb.vm.runtime_build_env(cfg()).items():
            self.assertEqual(seen[key], value)
        self.assertEqual(seen["PLEBIAN_OS_SSH_ENABLED"], "1")

    def test_flash_revalidates_after_unmount_immediately_before_dd(self):
        events = []
        expected = (8, 16)
        with tempfile.TemporaryDirectory() as td:
            iso = Path(td) / "image.iso"
            iso.write_bytes(b"image")

            def fits(*_args):
                events.append("fits")

            def mounted(_device):
                events.append("mounts")
                return ["/media/test"] if events.count("mounts") == 1 else []

            def subprocess_run(argv, **_kwargs):
                events.append("umount" if "umount" in argv else "subprocess")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            def run(argv, **_kwargs):
                events.append("dd" if "dd" in argv else "sync")
                return SimpleNamespace(returncode=0)

            with mock.patch.object(usb.os, "geteuid", return_value=0), \
                    mock.patch.object(usb, "_device_identity", side_effect=lambda _d: (events.append("identity") or expected)), \
                    mock.patch.object(usb, "_block_kname", side_effect=lambda _d: (events.append("base") or "sdz")), \
                    mock.patch.object(usb, "_root_disks", side_effect=lambda: (events.append("protected") or set())), \
                    mock.patch.object(usb, "validate_image_fits", side_effect=fits), \
                    mock.patch.object(usb, "_mounted_targets", side_effect=mounted), \
                    mock.patch.object(usb, "_lsblk", return_value="0"), \
                    mock.patch.object(usb.subprocess, "run", side_effect=subprocess_run), \
                    mock.patch.object(usb.vm, "run", side_effect=run):
                usb.flash("/dev/sdz", iso, expected)

        self.assertEqual(events.count("identity"), 2)
        self.assertEqual(events.count("fits"), 2)
        self.assertEqual(events.count("mounts"), 2)
        final_identity = len(events) - 1 - events[::-1].index("identity")
        final_mounts = len(events) - 1 - events[::-1].index("mounts")
        dd = events.index("dd")
        self.assertLess(final_identity, final_mounts)
        self.assertEqual(final_mounts + 1, dd, events)


if __name__ == "__main__":
    unittest.main()
