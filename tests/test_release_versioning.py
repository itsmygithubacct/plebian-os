import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(*parts):
    return (ROOT.joinpath(*parts)).read_text()


class ReleaseVersioningTests(unittest.TestCase):
    def test_version_file_is_semver(self):
        self.assertRegex((ROOT / "VERSION").read_text().strip(), r"^\d+\.\d+\.\d+$")

    def test_release_manifest_pins_refs(self):
        m = _read("releases", "0.1.0.env")
        self.assertIn("PLEBIAN_OS_RELEASE_MODE=1", m)
        for ref in ("PLEBIAN_OS_REF=v0.1.0", "PLEB_REF=v0.1.0",
                    "KILIX_REF=v0.1.0", "KILIX95_REF=v0.1.0"):
            self.assertIn(ref, m)

    def test_release_manifest_checksums_are_placeholders(self):
        # Until a real release fills them, the checksum/netinst pins must be
        # explicit REPLACE_ME so a half-filled manifest aborts the build.
        m = _read("releases", "0.1.0.env")
        for key in ("KILIX_PREBUILT_VERSION", "KILIX_PREBUILT_SHA256",
                    "PLEBIAN_OS_NETINST_SHA256"):
            self.assertTrue(re.search(rf"^{key}=REPLACE_ME$", m, re.M),
                            f"{key} should be a REPLACE_ME placeholder")

    def test_remaster_loads_release_manifest(self):
        r = _read("build", "remaster-iso.sh")
        self.assertIn("load_release_manifest", r)
        self.assertIn("PLEBIAN_OS_RELEASE", r)
        self.assertIn("REPLACE_ME", r)

    def test_remaster_records_version_and_runtime_config(self):
        # build-info + firstboot env must carry the version and the previously
        # missing security-relevant runtime knobs (provenance completeness).
        r = _read("build", "remaster-iso.sh")
        for key in ("PLEBIAN_OS_VERSION", "PLEBIAN_OS_KIOSK", "PLEBIAN_OS_USER",
                    "PLEBIAN_OS_NOPASSWD_SUDO", "PLEBIAN_OS_INSTALL_UV",
                    "PLEBIAN_OS_APT_SNAPSHOT", "PLEBIAN_OS_REPO", "PLEBIAN_OS_REF"):
            self.assertIn(key, r)

    def test_release_mode_warns_on_unpinned_apt(self):
        r = _read("build", "remaster-iso.sh")
        self.assertIn("PLEBIAN_OS_APT_SNAPSHOT", r)
        self.assertIn("snapshot.debian.org", r)

    def test_provisioner_persists_self_update_knobs(self):
        p = _read("provision", "plebian-os-provision.sh")
        for key in ("PLEBIAN_OS_VERSION", "PLEBIAN_OS_REPO",
                    "PLEBIAN_OS_REF", "PLEBIAN_OS_APT_SNAPSHOT"):
            self.assertIn(f"write_session_default {key}", p)

    def test_provisioner_has_apt_snapshot_and_manifest(self):
        p = _read("provision", "plebian-os-provision.sh")
        self.assertIn("configure_apt_snapshot", p)
        self.assertIn("write_package_manifest", p)
        self.assertIn("snapshot.debian.org", p)
        self.assertIn("/var/lib/plebian-os/packages.list", p)

    def test_update_helper_self_updates_os_layer(self):
        u = _read("provision", "plebian-os-update.sh")
        self.assertIn("self_update_os_layer", u)
        self.assertIn("update_os_checkout", u)
        self.assertIn("PLEBIAN_OS_SELF_UPDATE", u)
        self.assertIn("install -m 0755", u)
        self.assertIn("/usr/local/sbin/plebian-os-provision", u)
        # keeps honoring an exact pinned ref, like the pleb path
        self.assertIn('checkout --detach "$PLEBIAN_OS_REF"', u)

    def test_python_builders_forward_version_and_release(self):
        vm = _read("build", "build_vm_image.py")
        self.assertIn("apply_release_manifest", vm)
        self.assertIn("PLEBIAN_OS_VERSION", vm)
        self.assertIn("PLEBIAN_OS_REPO", vm)
        usb = _read("build", "build_usb_image.py")
        self.assertIn("vm.apply_release_manifest()", usb)

    def test_release_docs_present(self):
        self.assertTrue((ROOT / "RELEASING.md").exists())
        self.assertTrue((ROOT / "CHANGELOG.md").exists())


if __name__ == "__main__":
    unittest.main()
