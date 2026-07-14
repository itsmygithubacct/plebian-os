import hashlib
import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ATTRIBUTION = ROOT / "assets" / "installer" / "ATTRIBUTION.md"
LICENSE = ROOT / "assets" / "COPYING.GPL-2"
PROVISION = ROOT / "provision" / "plebian-os-provision.sh"
UPDATE = ROOT / "provision" / "plebian-os-update.sh"


class ArtworkNoticeTests(unittest.TestCase):
    def test_tracked_notice_bytes_and_relative_license_link(self):
        contracts = (
            (
                ATTRIBUTION,
                "5216b6ee1ef154dab56cc5d0a026d28f67ed50feec4129d4fedd6ae2fc2b2fb6",
            ),
            (
                LICENSE,
                "8177f97513213526df2cf6184d8ff986c675afb514d4e68a404010521b880643",
            ),
        )
        for path, expected in contracts:
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            data = path.read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), expected)
            self.assertNotIn(b"\x00", data)
            self.assertTrue(data.endswith(b"\n"))
            data.decode("utf-8")

        self.assertIn("../COPYING.GPL-2", ATTRIBUTION.read_text())
        self.assertIn("GPL-2.0-or-later", ATTRIBUTION.read_text())
        self.assertIn("GNU GENERAL PUBLIC LICENSE", LICENSE.read_text())
        self.assertIn("Version 2, June 1991", LICENSE.read_text())

    def test_provisioner_validates_private_copies_before_publication(self):
        source = PROVISION.read_text()
        section = source[
            source.index("install_artwork_notice()"):
            source.index("\ninstall_artwork_notices()")
        ]
        private = section.index('chmod 0600 "$tmp"')
        copy = section.index(
            '"$source" "$tmp" "$ARTWORK_NOTICE_MAX_BYTES"', private
        )
        validate = section.index('validate_artwork_notice "$tmp"', copy)
        publish = section.index('chmod 0644 "$tmp"', validate)
        rename = section.index('mv -fT -- "$tmp" "$destination"', publish)
        self.assertLess(private, copy)
        self.assertLess(copy, validate)
        self.assertLess(validate, publish)
        self.assertLess(publish, rename)
        self.assertIn("as_target_readonly timeout 30s python3", source)
        self.assertIn("ARTWORK_NOTICE_MAX_BYTES=$((1024 * 1024))", source)
        self.assertLess(
            source.index('install_artwork_notice "$license_source"'),
            source.index('install_artwork_notice "$attribution_source"'),
        )

    def test_provision_notice_validator_accepts_only_the_pinned_assets(self):
        script = r'''
set -euo pipefail
export PLEBIAN_OS_PROVISION_LIB_ONLY=1
source "$PROVISION"
validate_artwork_notice "$ATTRIBUTION" "$INSTALLER_ATTRIBUTION_SHA256" \
    "installer artwork attribution" attribution
validate_artwork_notice "$LICENSE" "$GPL2_LICENSE_SHA256" \
    "GPL version 2 license" license
'''
        result = subprocess.run(
            ["bash", "-c", script],
            cwd=ROOT,
            env={
                **os.environ,
                "PROVISION": str(PROVISION),
                "ATTRIBUTION": str(ATTRIBUTION),
                "LICENSE": str(LICENSE),
            },
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_updater_keeps_wallpaper_index_and_appends_both_notices(self):
        source = UPDATE.read_text()
        stage_names = source[
            source.index("stage_names=("):
            source.index("\n    )", source.index("stage_names=("))
        ]
        expected = (
            "plebian-os-provision",
            "plebian-os-install-deps",
            "plebian-os-passwd",
            "plebian-os-update",
            "plebian-os-firstboot.service",
            "plebian-os-firstboot-attempt",
            "VERSION",
            "desktop-wallpaper.png",
            "ATTRIBUTION.md",
            "COPYING.GPL-2",
        )
        positions = [stage_names.index(name) for name in expected]
        self.assertEqual(positions, sorted(positions))
        self.assertIn(
            '_DEPLOYED_DESKTOP_WALLPAPER_SHA256="${stage_hashes[7]}"', source
        )
        self.assertIn('python3 - "${new_paths[8]}" "${new_paths[9]}"', source)


if __name__ == "__main__":
    unittest.main()
