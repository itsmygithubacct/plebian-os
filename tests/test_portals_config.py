"""The Pleb desktop declares its portal backends instead of falling back."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVISION = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
CONF = "/etc/xdg-desktop-portal/pleb-portals.conf"


class PortalsConfigTests(unittest.TestCase):
    def test_the_file_is_named_for_the_desktop_the_portal_will_look_up(self):
        # portals.conf(5): the file is <desktop>-portals.conf with the desktop
        # name "in lower-case", and the portal binary carries the literal
        # "%s-portals.conf". pleb-session exports XDG_CURRENT_DESKTOP=Pleb.
        self.assertIn("PORTALS_CONF=" + CONF, PROVISION)
        self.assertTrue(CONF.endswith("/pleb-portals.conf"))

    def test_the_desktop_identity_pleb_session_exports_matches(self):
        # pleb-session lives in the sibling pleb repository, installed by
        # provisioning from the closure's PLEB_REF. A checkout without that
        # sibling cannot run this comparison; say so instead of passing on
        # nothing -- the first version of this test did exactly that.
        session = ROOT.parent / "pleb" / "bin" / "pleb-session"
        if not session.exists():
            self.skipTest(f"no sibling pleb checkout at {session.parent.parent}")
        self.assertIn("XDG_CURRENT_DESKTOP=Pleb", session.read_text())

    def test_gtk_is_named_explicitly_and_nothing_is_left_to_fallback(self):
        block = PROVISION[PROVISION.index("PORTALS_CONF="):PROVISION.index("# ── 5. session mode")]
        self.assertIn("[preferred]", block)
        self.assertIn("default=gtk", block)
        self.assertIn("org.freedesktop.impl.portal.ScreenCast=pleb", block)
        self.assertIn("org.freedesktop.impl.portal.Screenshot=pleb", block)

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

    def test_capture_configuration_and_runtime_are_protected_by_both_transactions(self):
        provision_paths = PROVISION[PROVISION.index("PROVISION_ROOT_TRANSACTION_PATHS=("):]
        provision_paths = provision_paths[:provision_paths.index(")\n")]
        updater = (ROOT / "provision/plebian-os-update.sh").read_text()
        for path in (
            "/usr/local/bin/pleb-lock", "/usr/local/lib/pleb/displays.py",
            "/usr/local/lib/pleb/capture_sources.py", "/usr/local/lib/pleb/capture_worker.py",
            "/usr/local/lib/pleb/capture_portal.py", "/usr/local/lib/pleb/capture_transport.so",
            "/usr/local/share/xdg-desktop-portal/portals/pleb.portal",
            "/usr/local/share/dbus-1/services/org.freedesktop.impl.portal.desktop.pleb.service",
            "/etc/wireplumber/wireplumber.conf.d/50pleb-video-only.conf",
            CONF,
        ):
            with self.subTest(path=path):
                self.assertIn(path, provision_paths)
                self.assertEqual(updater.count("    " + path + "\n"), 2,
                                 "snapshot and restore must protect the same exact artifact")


if __name__ == "__main__":
    unittest.main()
