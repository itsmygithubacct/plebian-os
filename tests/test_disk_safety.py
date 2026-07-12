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

    def test_offline_template_default_warns_but_does_not_refuse(self):
        # 'plebian' remains a supported offline ISO default. Python builders use
        # generated/operator passwords, and their opt-in SSH path rejects it.
        r = _read("build", "remaster-iso.sh")
        self.assertIn("password plebian$", r)          # still detected
        # the warning block must not abort the build
        gate = r.split("password plebian$", 1)[1].split("\nfi", 1)[0]
        self.assertNotIn("exit 1", gate)
        self.assertIn("default password 'plebian'", r)

    def test_flashers_protect_critical_mounts_swap_and_stacked_parents(self):
        shell = _read("build", "make-usb.sh")
        py = _read("build", "build_usb_image.py")
        for target in ("/boot/efi", "/usr", "/srv"):
            self.assertIn(target, shell)
            self.assertIn(f'"{target}"', py)
        self.assertIn("swapon --noheadings --raw --show=NAME", shell)
        self.assertIn('"swapon", "--noheadings", "--raw", "--show=NAME"', py)
        self.assertIn("/sys/class/block/$cur/slaves/", shell)
        self.assertIn('node / "slaves"', py)

    def test_shell_flash_revalidates_after_unmount_and_immediately_before_dd(self):
        shell = _read("build", "make-usb.sh")
        unmount = shell.rindex('$SUDO umount "$mp"')
        final_identity = shell.index('current_identity="$(lsblk -dnro MAJ:MIN', unmount)
        final_mount = shell.index('was mounted again before writing', final_identity)
        dd = shell.index('$SUDO dd if="$ISO"', final_mount)
        between = shell[final_mount:dd]
        self.assertIn("refusing", between)
        self.assertNotIn("sleep", between)

    def test_temp_sudoers_cleaned_on_signals_and_before_retry(self):
        p = _read("provision", "plebian-os-provision.sh")
        self.assertIn("trap cleanup EXIT", p)
        self.assertIn("INT TERM HUP", p)
        svc = _read("provision", "plebian-os-firstboot.service")
        self.assertIn(
            "ExecStartPre=-/bin/rm -f /etc/sudoers.d/plebian-os-provision", svc)

    def test_preseed_documents_default_credentials(self):
        p = _read("preseed", "preseed.cfg")
        self.assertIn("DEFAULT CREDENTIALS", p)
        # the header explains the safety story (no sshd + desktop nag)
        self.assertIn("ssh-server is installed", p)
        self.assertIn("change it on first run", p)


if __name__ == "__main__":
    unittest.main()
