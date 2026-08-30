"""The default-browser question grants no third-party trust, and skipping works."""

from __future__ import annotations

import unittest
from unittest import mock

import support

from f107b_setup import browsers


class OfferTests(unittest.TestCase):
    def test_every_offered_browser_is_from_debian_main(self) -> None:
        candidates = browsers.offer()
        self.assertTrue(candidates)
        for candidate in candidates:
            with self.subTest(browser=candidate.browser_id):
                self.assertEqual(candidate.component, "main")

    def test_a_non_main_candidate_is_refused_rather_than_offered(self) -> None:
        outside = browsers.BrowserChoice("vendor-browser", "Vendor", "contrib", False)
        with mock.patch.object(browsers, "CANDIDATES", browsers.CANDIDATES + (outside,)):
            with self.assertRaisesRegex(browsers.BrowserRefusal, "not Debian main"):
                browsers.offer()

    def test_chawan_is_never_a_default_handler(self) -> None:
        self.assertIn("chawan", browsers.NEVER_DEFAULT)
        self.assertNotIn("chawan", {c.browser_id for c in browsers.offer()})
        with self.assertRaises(browsers.BrowserRefusal):
            browsers.resolve("chawan")


class ResolutionTests(unittest.TestCase):
    def test_skipping_leaves_chromium_working_and_writes_nothing(self) -> None:
        chosen, surfaces = browsers.resolve(None)
        self.assertEqual(chosen, browsers.SHIPPED_DEFAULT)
        self.assertEqual(chosen, "chromium")
        self.assertEqual(surfaces, ())

    def test_choosing_writes_all_six_association_surfaces(self) -> None:
        chosen, surfaces = browsers.resolve("firefox-esr")
        self.assertEqual(chosen, "firefox-esr")
        self.assertEqual(len(surfaces), 6)
        for needle in (
            "alternatives:x-www-browser",
            "alternatives:gnome-www-browser",
            "xdg-settings:default-web-browser",
            "mimeapps:x-scheme-handler/http",
            "mimeapps:x-scheme-handler/https",
            "mimeapps:text/html",
        ):
            with self.subTest(surface=needle):
                self.assertIn(needle, surfaces)

    def test_an_unoffered_browser_is_refused(self) -> None:
        for name in ("google-chrome-stable", "opera", ""):
            with self.subTest(name=name):
                with self.assertRaises(browsers.BrowserRefusal):
                    browsers.resolve(name)


if __name__ == "__main__":
    unittest.main()
