import re
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROVISION = ROOT / "provision" / "plebian-os-provision.sh"
FIRSTBOOT = ROOT / "provision" / "plebian-os-firstboot.service"


class DmrcSymlinkRegressionTests(unittest.TestCase):
    def test_embedded_writer_replaces_symlink_without_touching_target(self):
        """Exercise the exact unprivileged writer embedded in the provisioner."""
        source = PROVISION.read_text()
        match = re.search(
            r"as_user bash -c (?P<literal>'\n.*?\n') "
            r"plebian-os-dmrc-writer \"\$dmrc\"",
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(match, "safe dmrc writer shell literal not found")

        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            victim = home / "victim"
            victim.write_text("must remain untouched\n")
            dmrc = home / ".dmrc"
            dmrc.symlink_to(victim)

            command = (
                f"writer={match.group('literal')}\n"
                'bash -c "$writer" plebian-os-dmrc-writer "$1"'
            )
            subprocess.run(["bash", "-c", command, "dmrc-test", str(dmrc)],
                           check=True)

            self.assertEqual(victim.read_text(), "must remain untouched\n")
            self.assertFalse(dmrc.is_symlink())
            self.assertEqual(dmrc.read_text(), "[Desktop]\nSession=pleb\n")
            self.assertEqual(stat.S_IMODE(dmrc.stat().st_mode), 0o600)

    def test_root_never_redirects_or_chowns_dmrc(self):
        source = PROVISION.read_text()
        body = source.split("pin_remembered_session() {", 1)[1].split("\n}", 1)[0]
        self.assertIn("as_user bash -c", body)
        self.assertIn("mv -fT", body)
        self.assertNotIn('> "$dmrc"', body)
        self.assertNotRegex(body, r"(?m)^\s*chown\b")


class SudoersLifecycleTests(unittest.TestCase):
    def test_firstboot_cleans_temporary_grant_after_stop(self):
        service = FIRSTBOOT.read_text()
        self.assertIn(
            "ExecStopPost=-/bin/rm -f /etc/sudoers.d/plebian-os-provision",
            service,
        )

    def test_permanent_modes_reconcile_off(self):
        source = PROVISION.read_text()
        self.assertIn('"$PLEB_DIR/bin/pleb" autologin off', source)
        self.assertIn('rm -f "$NOPASSWD_FILE"', source)


if __name__ == "__main__":
    unittest.main()
