import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "provision" / "lightdm-gtk-greeter.conf"
PROVISION = ROOT / "provision" / "plebian-os-provision.sh"
UPDATE = ROOT / "provision" / "plebian-os-update.sh"
PRESEED = ROOT / "preseed" / "preseed.cfg"
REMASTER = ROOT / "build" / "remaster-iso.sh"
DESTINATION = "/etc/lightdm/lightdm-gtk-greeter.conf.d/50-plebian-os.conf"
WALLPAPER = "/usr/local/share/plebian-os/wallpapers/plebian-os.png"
CONFIG_SHA256 = "985fe09dbbb4ee83949967a83960f71746c054da8d79196a4eac98a32cd76560"


class LightdmGreeterBrandingTests(unittest.TestCase):
    def test_tracked_override_is_exact_and_never_selects_debian_artwork(self):
        data = CONFIG.read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), CONFIG_SHA256)
        self.assertTrue(data.endswith(b"\n"))
        text = data.decode("utf-8")
        active = {
            line.strip() for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        self.assertEqual(
            active,
            {"[greeter]", f"background={WALLPAPER}", "user-background=false"},
        )
        self.assertNotIn("Debian", text)
        self.assertNotIn("desktop-base", text)

    def test_provision_validator_accepts_only_the_pinned_override(self):
        script = r'''
set -euo pipefail
export PLEBIAN_OS_PROVISION_LIB_ONLY=1
source "$PROVISION"
validate_artwork_notice "$CONFIG" "$LIGHTDM_GREETER_CONFIG_SHA256" \
    "LightDM greeter branding" greeter
'''
        good = subprocess.run(
            ["bash", "-c", script], cwd=ROOT,
            env={**os.environ, "PROVISION": str(PROVISION), "CONFIG": str(CONFIG)},
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(good.returncode, 0, good.stderr)
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "greeter.conf"
            bad.write_text(
                f"[greeter]\nbackground={WALLPAPER}\nuser-background=true\n"
            )
            rejected = subprocess.run(
                ["bash", "-c", script], cwd=ROOT,
                env={**os.environ, "PROVISION": str(PROVISION), "CONFIG": str(bad)},
                text=True, capture_output=True, check=False,
            )
            self.assertNotEqual(rejected.returncode, 0)

    def test_iso_installs_override_before_firstboot_can_fail(self):
        remaster = REMASTER.read_text()
        preseed = PRESEED.read_text()
        media_path = "/cdrom/plebian-os/lightdm-gtk-greeter.conf"
        self.assertIn(
            'install -m 0644 "$LIGHTDM_GREETER_CONFIG" '
            '"$EXTRACT/plebian-os/lightdm-gtk-greeter.conf"',
            remaster,
        )
        self.assertIn(media_path, preseed)
        self.assertEqual(preseed.count(f"/target{DESTINATION}"), 3)
        self.assertIn(f"chown root:root /target{DESTINATION}", preseed)
        self.assertIn(f"chmod 0644 /target{DESTINATION}", preseed)
        self.assertLess(preseed.index(media_path), preseed.index("in-target systemctl enable"))
        self.assertEqual(
            remaster.count("manifest_kv PLEBIAN_OS_LIGHTDM_GREETER_CONFIG_SHA256"),
            1,
        )

    def test_provisioning_is_atomic_idempotent_and_rejects_unsafe_paths(self):
        source = PROVISION.read_text()
        section = source[
            source.index("install_lightdm_greeter_branding()"):
            source.index("\nselected_desktop_wallpaper_state_dir()")
        ]
        self.assertIn("/ /etc /etc/lightdm", section)
        self.assertIn('[ ! -L "$config_dir" ]', section)
        self.assertIn('[ ! -L "$LIGHTDM_GREETER_CONFIG_DST" ]', section)
        self.assertIn("install -d -o root -g root -m 0755", section)
        self.assertIn(
            'install_artwork_notice "$source" "$LIGHTDM_GREETER_CONFIG_DST"',
            section,
        )
        generic = source[
            source.index("install_artwork_notice()"):
            source.index("\ninstall_artwork_notices()")
        ]
        # Existing exact files are metadata-reconciled in place; changed files
        # are published with an atomic rename after validation.
        self.assertIn('[ "$source" = "$destination" ]', generic)
        self.assertIn("chown root:root", generic)
        self.assertIn("chmod 0644", generic)
        self.assertIn('mv -fT -- "$tmp" "$destination"', generic)
        call = source.rindex("\ninstall_lightdm_greeter_branding\n")
        self.assertGreater(call, source.rindex("\ninstall_desktop_wallpaper\n"))

    def test_update_transaction_covers_override_and_rollback(self):
        update = UPDATE.read_text()
        self.assertIn('[ "${#expected_hashes[@]}" -eq 11 ]', update)
        self.assertGreaterEqual(update.count("lightdm-gtk-greeter.conf"), 8)
        self.assertGreaterEqual(update.count(DESTINATION), 3)
        self.assertIn("/ /usr /usr/local /usr/local/share /etc /etc/lightdm", update)
        self.assertIn("/etc/lightdm/lightdm-gtk-greeter.conf.d; do", update)
        self.assertIn('python3 - "${new_paths[10]}"', update)
        snapshot = update[update.index("<<'ROOT_SNAPSHOT'"):update.index("\nROOT_SNAPSHOT")]
        restore = update[update.index("<<'ROOT_RESTORE'"):update.index("\nROOT_RESTORE")]
        for text in (snapshot, restore):
            self.assertIn(DESTINATION, text)
            self.assertIn("/etc/lightdm/lightdm-gtk-greeter.conf.d", text)


if __name__ == "__main__":
    unittest.main()
