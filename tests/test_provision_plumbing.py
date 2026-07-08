import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ProvisionPlumbingTests(unittest.TestCase):
    def test_shell_scripts_parse(self):
        scripts = [
            "bootstrap.sh",
            *[str(p.relative_to(ROOT)) for p in sorted((ROOT / "build").glob("*.sh"))],
            *[str(p.relative_to(ROOT)) for p in sorted((ROOT / "provision").glob("*.sh"))],
        ]
        subprocess.run(["bash", "-n", *scripts], cwd=ROOT, check=True)

    def test_provision_and_update_pass_generic_desktop_knobs(self):
        required = [
            "PLEB_REPO",
            "PLEB_BRANCH",
            "PLEB_REF",
            "KILIX_REPO",
            "KILIX_BRANCH",
            "KILIX_REF",
            "KILIX_PREBUILT_VERSION",
            "KILIX_PREBUILT_SHA256",
            "KILIX_DESKTOP_PROVIDER",
            "KILIX_DESKTOP_COMMAND",
            "KILIX_DESKTOP_NAME",
            "KILIX95_AUTO_INSTALL",
            "KILIX95_REF",
        ]
        for path in [
            ROOT / "provision" / "plebian-os-provision.sh",
            ROOT / "provision" / "plebian-os-update.sh",
        ]:
            text = path.read_text()
            with self.subTest(path=path.name):
                for key in required:
                    self.assertIn(key, text)

    def test_session_env_writer_uses_shell_escaped_defaults(self):
        text = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
        self.assertIn("write_session_default", text)
        self.assertIn("printf 'if [ -z", text)
        self.assertNotIn(': "\\${KILIX_DIR:=', text)

    def test_env_forwarding_uses_arrays_not_optional_word_splitting(self):
        for path in [
            ROOT / "provision" / "plebian-os-provision.sh",
            ROOT / "provision" / "plebian-os-update.sh",
        ]:
            text = path.read_text()
            with self.subTest(path=path.name):
                self.assertIn("env \"${", text)
                self.assertNotIn("${KILIX_BRANCH:+", text)
                self.assertNotIn("${KILIX95_BRANCH:+", text)
                self.assertNotIn("${KILIX_REF:+", text)
                self.assertNotIn("${KILIX95_REF:+", text)

    def test_update_honors_pinned_pleb_ref(self):
        text = (ROOT / "provision" / "plebian-os-update.sh").read_text()
        self.assertIn("PLEB_REF", text)
        self.assertIn("checkout --detach \"$PLEB_REF\"", text)
        self.assertIn("validate_checkout_origin \"$PLEB_DIR\" \"$PLEB_REPO\"", text)

    def test_existing_pleb_checkout_honors_explicit_branch(self):
        for path in [
            ROOT / "provision" / "plebian-os-provision.sh",
            ROOT / "provision" / "plebian-os-update.sh",
        ]:
            text = path.read_text()
            with self.subTest(path=path.name):
                self.assertIn('checkout "$PLEB_BRANCH"', text)
                self.assertIn('checkout --track -b "$PLEB_BRANCH"', text)
                self.assertIn('merge --ff-only "origin/$PLEB_BRANCH"', text)

    def test_preseed_copies_build_manifest(self):
        text = (ROOT / "preseed" / "preseed.cfg").read_text()
        self.assertIn("/target/etc/plebian-os", text)
        self.assertIn("build-info.env", text)

    def test_remaster_writes_build_manifest(self):
        text = (ROOT / "build" / "remaster-iso.sh").read_text()
        for key in [
            "PLEBIAN_OS_SOURCE_ISO_SHA256",
            "PLEB_REF",
            "KILIX_REF",
            "KILIX_PREBUILT_SHA256",
            "KILIX95_REF",
        ]:
            self.assertIn(key, text)


if __name__ == "__main__":
    unittest.main()
