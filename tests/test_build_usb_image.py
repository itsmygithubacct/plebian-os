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
    def test_flash_candidate_accepts_each_kernel_signal_independently(self):
        cases = (
            ("1", "sata", "0", True),
            ("0", "usb", "0", True),
            ("0", "USB", "0", True),
            ("0", "sata", "1", True),
            ("0", "sata", "0", False),
            ("0", "?", "?", False),
        )
        for removable, transport, hotplug, accepted in cases:
            with self.subTest(
                    removable=removable, transport=transport, hotplug=hotplug):
                self.assertEqual(
                    usb._device_is_flash_candidate(removable, transport, hotplug),
                    accepted,
                )

    def test_validate_device_accepts_rm_zero_usb_transport(self):
        with mock.patch.object(usb.Path, "is_block_device", return_value=True), \
                mock.patch.object(usb, "_block_kname", return_value="sdz"), \
                mock.patch.object(usb, "_root_disks", return_value=set()), \
                mock.patch.object(usb, "_lsblk", side_effect=["disk", "0"]), \
                mock.patch.object(
                    usb, "_device_characteristics",
                    return_value=("0", "usb", "1", "7.5G", "Cruzer Fit"),
                ), \
                mock.patch.object(usb, "_device_identity", return_value=(8, 16)):
            validated = usb.validate_device("/dev/sdz", force=False)
        self.assertEqual(validated, ("7.5G", "Cruzer Fit", True, (8, 16)))

    def test_validate_device_refusal_names_observed_evidence(self):
        with mock.patch.object(usb.Path, "is_block_device", return_value=True), \
                mock.patch.object(usb, "_block_kname", return_value="sdz"), \
                mock.patch.object(usb, "_root_disks", return_value=set()), \
                mock.patch.object(usb, "_lsblk", side_effect=["disk", "0"]), \
                mock.patch.object(
                    usb, "_device_characteristics",
                    return_value=("0", "sata", "0", "931.5G", "Fixed Disk"),
                ), \
                mock.patch.object(usb, "die", side_effect=RuntimeError) as die:
            with self.assertRaises(RuntimeError):
                usb.validate_device("/dev/sdz", force=False)
        die.assert_called_once_with(
            "/dev/sdz is not marked removable (RM=0, TRAN=sata, HOTPLUG=0, "
            "MODEL=Fixed Disk, SIZE=931.5G) — pass --force if this is the "
            "device you intend to erase"
        )

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

    def test_root_disks_decodes_every_proc_swaps_escape_once(self):
        encoded = r"/swap\040space\011tab\012line\134backslash"
        decoded = "/swap space\ttab\nline\\backslash"
        literal_encoded_escape = r"/swap\134040literal"
        literal_decoded_escape = r"/swap\040literal"
        swaps = (
            "Filename Type Size Used Priority\n"
            f"{encoded} file 1024 0 -2\n"
            f"{literal_encoded_escape} file 1024 0 -3\n"
        )
        swap_backings = {
            decoded: "/dev/sdz1",
            literal_decoded_escape: "/dev/sdy1",
        }
        seen_targets = []

        def run(argv, **_kwargs):
            target = argv[-1]
            if target in swap_backings:
                seen_targets.append(target)
                return SimpleNamespace(
                    returncode=0, stdout=swap_backings[target] + "\n", stderr="")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with mock.patch.object(usb.Path, "read_text", return_value=swaps), \
                mock.patch.object(usb, "_parent_map", return_value={}), \
                mock.patch.object(
                    usb, "_block_kname", side_effect=lambda path: Path(path).name
                ), \
                mock.patch.object(
                    usb, "_ancestors", side_effect=lambda name, _parents: {name}
                ), \
                mock.patch.object(usb.subprocess, "run", side_effect=run):
            protected = usb._root_disks()

        self.assertEqual(seen_targets, [decoded, literal_decoded_escape])
        self.assertEqual(protected, {"sdz1", "sdy1"})

    def test_yes_mode_generates_password(self):
        with mock.patch.object(usb.vm, "generated_password", return_value="random-pass"):
            built = usb.gather_config(args(password=None))
        self.assertEqual(built.password, "random-pass")

    def test_yes_mode_honors_explicit_password(self):
        with mock.patch.object(usb.vm, "generated_password", return_value="random-pass"):
            built = usb.gather_config(args(password="explicit"))
        self.assertEqual(built.password, "explicit")

    def test_release_image_config_defaults_to_plebian(self):
        with mock.patch.dict(usb.os.environ, {
            "IMAGE_PASSWORD": "plebian",
            "RANDOM_PASSWORD": "0",
        }, clear=True):
            built = usb.gather_config(args(password=None))
        self.assertEqual(built.password, "plebian")

    def test_release_image_config_can_request_random_password(self):
        with mock.patch.dict(usb.os.environ, {
            "IMAGE_PASSWORD": "plebian",
            "RANDOM_PASSWORD": "yes",
        }, clear=True), mock.patch.object(
                usb.vm, "generated_password", return_value="random-pass"):
            built = usb.gather_config(args(password=None))
        self.assertEqual(built.password, "random-pass")

    def test_defaults_to_desktop_in_first_kilix_page_and_non_kiosk(self):
        with mock.patch.dict(usb.os.environ, {}, clear=True):
            built = usb.gather_config(args())
        self.assertTrue(built.desktop)
        self.assertFalse(built.kiosk)

    def test_release_environment_session_defaults_are_honored(self):
        with mock.patch.dict(usb.os.environ, {
            "PLEBIAN_OS_DESKTOP": "1",
            "PLEBIAN_OS_KIOSK": "true",
        }, clear=True):
            built = usb.gather_config(args())
        self.assertTrue(built.desktop)
        self.assertTrue(built.kiosk)

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
