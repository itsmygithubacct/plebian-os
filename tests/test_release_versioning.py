import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(*parts):
    return (ROOT.joinpath(*parts)).read_text()


class ReleaseVersioningTests(unittest.TestCase):
    @property
    def version(self):
        return (ROOT / "VERSION").read_text().strip()

    @property
    def manifest(self):
        return _read("releases", f"{self.version}.env")

    def test_version_file_is_semver(self):
        self.assertRegex((ROOT / "VERSION").read_text().strip(), r"^\d+\.\d+\.\d+$")

    def test_release_manifest_pins_refs(self):
        m = self.manifest
        self.assertIn("PLEBIAN_OS_RELEASE_MODE=1", m)
        self.assertIn(f"PLEBIAN_OS_REF=v{self.version}", m)
        for key in ("PLEB_REF", "KILIX_REF", "KILIX95_REF"):
            self.assertRegex(m, rf"(?m)^{key}=[0-9a-f]{{40}}$")

    def test_release_manifest_checksums_are_filled(self):
        m = self.manifest
        # no pin VALUE is still a placeholder (comments may mention REPLACE_ME)
        self.assertFalse(re.search(r"^\w+=REPLACE_ME$", m, re.M))
        self.assertTrue(re.search(r"^KILIX_PREBUILT_VERSION=\d+\.\d+", m, re.M))
        for key in (
            "KILIX_PREBUILT_SHA256", "PLEBIAN_OS_NETINST_SHA256",
            "PLEBIAN_OS_KILIX_GO_SHA256_AMD64",
            "PLEBIAN_OS_KILIX_GO_SHA256_ARM64",
        ):
            self.assertTrue(re.search(rf"^{key}=[0-9a-f]{{64}}$", m, re.M),
                            f"{key} should be a real sha256")
        self.assertRegex(m, r"(?m)^PLEBIAN_OS_NETINST_URL=https://")
        self.assertRegex(m, r"(?m)^PLEBIAN_OS_APT_SNAPSHOT=\d{8}T\d{6}Z$")
        self.assertRegex(m, r"(?m)^PLEBIAN_OS_KILIX_GO_VERSION=go\d+\.\d+\.\d+$")

    def test_remaster_loads_release_manifest(self):
        r = _read("build", "remaster-iso.sh")
        self.assertIn("load_release_manifest", r)
        self.assertIn("PLEBIAN_OS_RELEASE", r)
        self.assertIn("REPLACE_ME", r)

    def test_shell_release_manifest_overrides_ambient_bypass_values(self):
        source = _read("build", "remaster-iso.sh")
        start = source.index("load_release_manifest() {")
        end = source.index('[ -n "${PLEBIAN_OS_RELEASE:-}" ]', start)
        loader = source[start:end]
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / "releases").mkdir()
            (repo / "VERSION").write_text("9.8.7\n")
            (repo / "releases" / "9.8.7.env").write_text(
                "PLEBIAN_OS_VERSION=9.8.7\n"
                "PLEBIAN_OS_RELEASE_MODE=1\n"
                "PLEB_REF=" + "a" * 40 + "\n"
            )
            harness = (
                "set -euo pipefail\n"
                f"HERE={repo!s}\n"
                f"{loader}\n"
                "PLEBIAN_OS_RELEASE_MODE=0\n"
                "PLEB_REF=ambient-bypass\n"
                "load_release_manifest 9.8.7\n"
                "printf '%s\\n%s\\n' \"$PLEBIAN_OS_RELEASE_MODE\" \"$PLEB_REF\"\n"
            )
            result = subprocess.run(
                ["bash", "-c", harness], text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout.splitlines()[-2:], ["1", "a" * 40])

    def test_python_release_manifest_overrides_ambient_bypass_values(self):
        import sys
        from unittest import mock
        sys.path.insert(0, str(ROOT / "build"))
        import build_vm_image as vm

        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / "releases").mkdir()
            (repo / "VERSION").write_text("9.8.7\n")
            (repo / "releases" / "9.8.7.env").write_text(
                "PLEBIAN_OS_VERSION=9.8.7\n"
                "PLEBIAN_OS_RELEASE_MODE=1\n"
                "PLEB_REF=" + "b" * 40 + "\n"
            )
            with mock.patch.object(vm, "REPO", repo), mock.patch.dict(
                    os.environ,
                    {"PLEBIAN_OS_RELEASE_MODE": "0", "PLEB_REF": "ambient-bypass"},
                    clear=False):
                vm.apply_release_manifest("9.8.7")
                self.assertEqual(os.environ["PLEBIAN_OS_RELEASE_MODE"], "1")
                self.assertEqual(os.environ["PLEB_REF"], "b" * 40)

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
        # the password-nag helper is an OS-layer script too — it must redeploy
        self.assertIn("/usr/local/sbin/plebian-os-passwd", u)
        # Exact pins are resolved from the object returned by origin rather
        # than a potentially poisoned local tag, then deployed transactionally.
        self.assertIn(
            'checkout_pinned_ref "$PLEBIAN_OS_DIR" "$PLEBIAN_OS_REF" "plebian-os"',
            u,
        )
        self.assertIn("FETCH_HEAD^{commit}", u)
        self.assertIn("deploy_staged_os_layer", u)
        self.assertIn("systemctl daemon-reload", u)

    def test_python_builders_forward_version_and_release(self):
        vm = _read("build", "build_vm_image.py")
        self.assertIn("apply_release_manifest", vm)
        self.assertIn("PLEBIAN_OS_VERSION", vm)
        # apply_release_manifest populates every coordinated pin (including
        # PLEBIAN_OS_REPO); inheriting os.environ into remaster forwards them
        # without maintaining a second, drift-prone key list here.
        self.assertIn("{**os.environ", vm)
        usb = _read("build", "build_usb_image.py")
        self.assertIn("vm.apply_release_manifest()", usb)

    def test_release_docs_present(self):
        self.assertTrue((ROOT / "RELEASING.md").exists())
        self.assertTrue((ROOT / "CHANGELOG.md").exists())

    def test_acceptance_uses_exact_release_pins_without_release_only_gates(self):
        source = (ROOT / "build" / "acceptance-vm.sh").read_text()
        self.assertIn('PLEBIAN_OS_ACCEPTANCE_RAM:-4096', source)
        self.assertIn('releases/$PLEBIAN_OS_ACCEPTANCE_RELEASE.env', source)
        self.assertIn('PLEBIAN_OS_REF="$(git -C "$ROOT" rev-parse HEAD)"', source)
        self.assertIn('PLEBIAN_OS_RELEASE_MODE=0', source)
        self.assertIn('PLEBIAN_OS_RELEASE=', source)


if __name__ == "__main__":
    unittest.main()
