import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(*parts):
    return (ROOT.joinpath(*parts)).read_text()


class DiskSafetyTests(unittest.TestCase):
    def test_make_usb_strips_btrfs_subvol(self):
        # findmnt SOURCE on btrfs is /dev/xxx[/subvol]; the subvol suffix must be
        # stripped so the running root disk still resolves and stays protected.
        self.assertIn('src="${src%%[*}"', _read("build", "make-usb.sh"))

    def test_build_usb_py_strips_btrfs_subvol(self):
        self.assertIn('src.split("[", 1)[0]', _read("build", "build_usb_image.py"))

    def test_make_usb_forces_confirmation_on_fixed_disk(self):
        # A forced (non-removable) target must require the typed confirmation even
        # with --yes; only a genuinely removable stick may be flashed unattended.
        s = _read("build", "make-usb.sh")
        self.assertIn('[ "$removable" != 1 ]', s)

    def test_build_usb_py_forces_confirmation_on_fixed_disk(self):
        s = _read("build", "build_usb_image.py")
        self.assertIn("args.yes and removable", s)
        self.assertIn('return size, model, removable == "1"', s)

    def test_partman_strip_is_namespace_wide(self):
        remaster = _read("build", "remaster-iso.sh")
        usb = _read("build", "build_usb_image.py")
        # robust single-namespace strip present …
        self.assertIn("d-i[[:space:]]+partman", remaster)
        self.assertIn(r"^d-i\s+partman.*\n", usb)
        # … and the old, fragile enumerated patterns are gone
        self.assertNotIn("partman/choose_partition ", remaster)
        self.assertNotIn("partman-partitioning/.*", usb)

    def test_test_credential_gate_independent_of_ssh(self):
        # The weak-password grep must end the gate condition (";  then"), i.e. it
        # is no longer ANDed with an ssh-server grep that could be dropped to evade.
        r = _read("build", "remaster-iso.sh")
        self.assertIn('password plebian$\' "$PRESEED"; then', r)

    def test_temp_sudoers_cleaned_on_signals_and_before_retry(self):
        p = _read("provision", "plebian-os-provision.sh")
        self.assertIn("trap cleanup EXIT", p)
        self.assertIn("INT TERM HUP", p)
        svc = _read("provision", "plebian-os-firstboot.service")
        self.assertIn(
            "ExecStartPre=-/bin/rm -f /etc/sudoers.d/plebian-os-provision", svc)

    def test_preseed_header_warns_against_raw_use(self):
        p = _read("preseed", "preseed.cfg")
        self.assertIn("Do NOT feed this file straight to debian-installer", p)


if __name__ == "__main__":
    unittest.main()
