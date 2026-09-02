"""The Pleb desktop declares its portal backends instead of falling back."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVISION = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
CONF = "/etc/xdg-desktop-portal/pleb-portals.conf"


class PortalsConfigTests(unittest.TestCase):
    def test_the_file_matches_the_desktop_identity_pleb_session_exports(self):
        session = (ROOT.parent / "pleb" / "bin" / "pleb-session")
        if session.exists():
            self.assertIn("XDG_CURRENT_DESKTOP=Pleb", session.read_text())
        # xdg-desktop-portal lowercases the desktop name to find its file
        self.assertIn("PORTALS_CONF=" + CONF, PROVISION)

    def test_gtk_is_named_explicitly_and_nothing_is_left_to_fallback(self):
        block = PROVISION[PROVISION.index("PORTALS_CONF="):PROVISION.index("# ── 5. session mode")]
        self.assertIn("[preferred]", block)
        self.assertIn("default=gtk", block)
        self.assertIn("ScreenCast", block, "the deliberate omission must be stated, not implied")

    def test_it_is_written_inside_the_root_transaction(self):
        # Otherwise a rollback would leave it behind, or a failed provision
        # would have written it outside the atomic transaction.
        paths = PROVISION[PROVISION.index("PROVISION_ROOT_TRANSACTION_PATHS=("):]
        paths = paths[:paths.index(")\n")]
        self.assertIn(CONF, paths)
        dirs = PROVISION[PROVISION.index("PROVISION_ROOT_TRANSACTION_MANAGED_DIRS=("):]
        dirs = dirs[:dirs.index(")\n")]
        self.assertIn("/etc/xdg-desktop-portal", dirs)

    def test_dry_run_announces_it(self):
        self.assertIn("+ write $PORTALS_CONF", PROVISION)


if __name__ == "__main__":
    unittest.main()
