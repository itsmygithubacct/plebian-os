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
            "PLEBIAN_OS_BUILD_KILIX_FORK",
            "PLEBIAN_OS_KILIX_GO_MIN_VERSION",
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
        self.assertIn("firstboot.env", text)
        self.assertIn("/target/etc/default/plebian-os", text)

    def test_remaster_writes_build_manifest_and_firstboot_env(self):
        text = (ROOT / "build" / "remaster-iso.sh").read_text()
        for key in [
            "PLEBIAN_OS_SOURCE_ISO_SHA256",
            "PLEBIAN_OS_NETINST_SHA256",
            "PLEBIAN_OS_RELEASE_MODE",
            "PLEB_REF",
            "KILIX_REF",
            "KILIX_PREBUILT_SHA256",
            "PLEBIAN_OS_BUILD_KILIX_FORK",
            "PLEBIAN_OS_KILIX_GO_MIN_VERSION",
            "KILIX95_REF",
        ]:
            self.assertIn(key, text)
        self.assertIn("write_firstboot_env", text)
        self.assertIn("firstboot.env", text)
        self.assertIn("release_mode_check", text)

    def test_release_mode_requires_all_pins(self):
        text = (ROOT / "build" / "remaster-iso.sh").read_text()
        self.assertIn("PLEBIAN_OS_RELEASE_MODE", text)
        self.assertIn("PLEBIAN_OS_NETINST_SHA256", text)
        for key in [
            "PLEB_REF",
            "KILIX_REF",
            "KILIX95_REF",
            "KILIX_PREBUILT_VERSION",
            "KILIX_PREBUILT_SHA256",
        ]:
            self.assertIn(key, text)

    def test_firstboot_retries_transient_failures(self):
        text = (ROOT / "provision" / "plebian-os-firstboot.service").read_text()
        self.assertIn("Restart=on-failure", text)
        self.assertIn("RestartSec=90s", text)
        self.assertIn("StartLimitBurst=5", text)
        self.assertIn("TimeoutStartSec=7200", text)

    def test_firstboot_builds_and_verifies_kilix_fork(self):
        text = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
        self.assertIn("build_kilix_fork", text)
        self.assertIn("submodule update --init --recursive", text)
        self.assertIn("scripts/install-go.sh", text)
        self.assertIn('"$KILIX_DIR/kilix" --build', text)
        self.assertIn("src/kitty/launcher/kitty", text)
        self.assertIn('"$KILIX_DIR/kilix" --which', text)

    def test_provision_disables_kernel_speaker_beeps(self):
        text = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
        self.assertIn("plebian-os-no-beep.conf", text)
        self.assertIn("blacklist pcspkr", text)
        self.assertIn("blacklist snd_pcsp", text)
        self.assertIn("modprobe -r snd_pcsp pcspkr", text)

    def test_netinst_fetch_retries_with_debian_cd_signing_key(self):
        text = (ROOT / "build" / "lib.sh").read_text()
        self.assertIn("PLEBIAN_OS_DEBIAN_CD_KEY_URL", text)
        self.assertIn("key-DA87E80D6294BE9B.txt", text)
        self.assertIn("debian-cd-signing-key.gpg", text)
        self.assertIn("_fetch_debian_cd_keyring", text)
        self.assertIn("_download_sums_pair refresh", text)

    def test_make_usb_rebuilds_stale_iso_when_baked_inputs_change(self):
        text = (ROOT / "build" / "make-usb.sh").read_text()
        self.assertIn("iso_is_fresh", text)
        self.assertIn("baked_env_overrides_present", text)
        self.assertIn("ISO_EXPLICIT", text)
        self.assertIn("PLEBIAN_OS_INSTALL_UV", text)
        self.assertIn("PLEBIAN_OS_BUILD_KILIX_FORK", text)
        self.assertIn("PLEBIAN_OS_KILIX_GO_MIN_VERSION", text)
        self.assertIn("UNATTENDED_DISK", text)
        for path in [
            "remaster-iso.sh",
            "preseed/preseed.cfg",
            "plebian-os-provision.sh",
            "plebian-os-firstboot.service",
            "plebian-os-update.sh",
        ]:
            self.assertIn(path, text)


if __name__ == "__main__":
    unittest.main()
