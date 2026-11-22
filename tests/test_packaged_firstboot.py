"""Check both first-boot paths using the provisioner's shell and a temporary root."""
from pathlib import Path
import subprocess
import tempfile
import unittest


PROVISION = Path(__file__).resolve().parents[1] / "provision/plebian-os-provision.sh"
SOURCE = PROVISION.read_text()


def section(start, end):
    begin = SOURCE.index("\n" + start) + 1
    return SOURCE[begin:SOURCE.index("\n" + end, begin)] + "\n"


INSTALL = section('PLEB_LAUNCHER="$PLEB_DIR/bin/pleb"', "disable_audio_holding_user_units\n")
CHECKS_AND_ENGINE = section('if [ "$DRY_RUN" != 1 ] && [ "$PACKAGED_PLEB" = 0 ]; then',
                            "seed_selected_desktop_wallpaper_state\n")
AUTOLOGIN = section('if [ "$PACKAGED_PLEB" = 1 ]; then\n    # This command edits', "# Passwordless sudo for the owner.")
SETUP = r'''
source "$1"
PLEBIAN_OS_BINDIR="$2/bin"
PLEBIAN_OS_LIBEXECDIR="$2/libexec"
PLEB_DIR="$2/pleb"
KILIX_DIR="$2/kilix"
PLEBIAN_OS_DIR="$2/os"
KILIX_DATA_HOME="$2/data"
KILIX_STATE_DIRECTORY="$2/state"
USER_HOME="$2/user"
SUDOERS="$2/sudoers"
TARGET_USER=desktop
PLEB_REF=test-pin
DRY_RUN="$TEST_DRY_RUN"
install_env=(TEST_ENV=shared)
dpkg-query() {
    [ "$1" = -W ] && [ "$2" = -f ] && [ "$3" = '${db:Status-Status}' ] || return 1
    case "$4" in
        pleb) printf '%s' "$PLEB_STATUS" ;;
        kilix) printf '%s' "$KILIX_STATUS" ;;
        kilix-needle) printf '%s' "$NEEDLE_STATUS" ;;
        *) return 1 ;;
    esac
}
as_user() { printf 'as_user %s\n' "$*"; }
update_pleb_checkout() { echo update_pleb_checkout; }
checkout_pinned_ref() { echo checkout_pinned_ref; }
visudo() { [ -s "$SUDOERS" ]; }
install_kilix_needle() { echo needle-called; }
install_kilix_claudex() { echo claudex-called; }
install_kilix_llm() { echo llm-called; }
install_neuronte() { echo neuronte-called; }
build_kilix_fork() { echo checkout-build-called; }
pin_remembered_session() { echo pin-session; }
'''


class PackagedFirstbootTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        for name in ("bin/pleb", "bin/kilix"):
            path = self.root / name
            path.parent.mkdir(exist_ok=True)
            path.write_text('#!/bin/sh\ncase "$1" in\n'
                            '    --version) echo "pleb 0.2.3" ;;\n'
                            '    --kilix-version) echo "0.2.3" ;;\n'
                            '    *) printf "package command %s\\n" "$*" ;;\n'
                            'esac\n')
            path.chmod(0o755)
        stage = self.root / "os/provision/install-image-models.py"
        stage.parent.mkdir(parents=True)
        stage.write_text('import sys\nprint("Paradee stage", *sys.argv[1:])\n')
        installed = self.root / "libexec/image-models/install-image-models.py"
        installed.parent.mkdir(parents=True)
        installed.write_text(stage.read_text())

    def shell(self, body, *, pleb="installed", kilix="installed", needle="installed", dry=False):
        return subprocess.run(
            ["/bin/bash", "-c", SETUP + body, "test-packaged-firstboot", str(PROVISION), str(self.root)],
            env={"PATH": "/usr/bin:/bin", "TMPDIR": str(self.root), "PLEBIAN_OS_PROVISION_LIB_ONLY": "1",
                 "PLEB_STATUS": pleb, "KILIX_STATUS": kilix, "NEEDLE_STATUS": needle,
                 "TEST_DRY_RUN": str(int(dry)),
                 "PYTHONDONTWRITEBYTECODE": "1"}, capture_output=True, text=True, timeout=20)

    def test_source_preserves_package_detection_and_checkout_commands(self):
        self.assertIn("record_voice_dictation_census\nif packages_provide_pleb_and_kilix; then", INSTALL)
        self.assertLess(SOURCE.index("\ninstall_env=("), SOURCE.index("\nrecord_voice_dictation_census\n"))
        packaged, checkout = INSTALL.split("\nelse\n", 1)
        self.assertIn("packaged pleb and kilix are installed", packaged)
        self.assertIn("as_user git clone", checkout)
        self.assertIn('checkout_pinned_ref "$PLEB_DIR"', checkout)
        install = 'as_user env "${install_env[@]}" "$PLEB_DIR/bin/pleb" install'
        self.assertIn(install, checkout)
        self.assertLess(INSTALL.index("packaged pleb and kilix are installed"), INSTALL.index(install))
        self.assertIn('as_user env "${install_env[@]}" "$KILIX_DIR/kilix" --build', SOURCE)
        self.assertLess(INSTALL.index('default_models.py" verify'), INSTALL.index("    install_neuronte\n"))
        self.assertLess(SOURCE.index("    build_kilix_fork\n"), SOURCE.index("\nprepare_kilix95_caches\n"))

    def test_dpkg_status_missing_query_and_dry_run(self):
        for pleb, kilix, dry, expected in (("installed", "installed", False, 0), ("config-files", "installed", False, 1),
                                          ("installed", "unpacked", False, 1), ("installed", "installed", True, 1)):
            with self.subTest(pleb=pleb, kilix=kilix, dry=dry):
                result = self.shell("packages_provide_pleb_and_kilix", pleb=pleb, kilix=kilix, dry=dry)
                self.assertEqual(result.returncode, expected, result.stderr)
        missing = self.shell('unset -f dpkg-query\nPATH="$2/bin"\npackages_provide_pleb_and_kilix')
        self.assertNotEqual(missing.returncode, 0)

    def test_packaged_without_checkouts_runs_shared_steps_and_uses_installed_commands(self):
        checkout = self.shell("ensure_plebian_os_checkout")
        self.assertEqual(checkout.returncode, 0, checkout.stderr)
        self.assertIn("packaged install does not clone plebian-os source", checkout.stdout)
        self.assertNotIn("as_user git clone", checkout.stdout)
        result = self.shell(INSTALL + CHECKS_AND_ENGINE + AUTOLOGIN +
                            'echo "census=$PROVISION_VOICE_CENSUS_TAKEN models=$PROVISION_DEFAULT_MODELS_VERIFIED"\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        for message in ("using the packaged Needle runtime", "packaged install has no kilix checkout", "Paradee stage --install-paradee-runtime --offline",
                        "packaged kilix-engine", "package command autologin off", "census=1 models=0"):
            self.assertIn(message, result.stdout)
        for action in ("as_user git clone", "checkout-build-called", "needle-called", "claudex-called",
                       "llm-called", "neuronte-called", "default_models.py verify", "--kilix "):
            self.assertNotIn(action, result.stdout)
        self.assertFalse((self.root / "sudoers").exists())
        self.assertFalse((self.root / "pleb").exists())
        self.assertFalse((self.root / "kilix").exists())

    def test_existing_kilix_checkout_keeps_the_source_only_model_helpers(self):
        launcher = self.root / "kilix/kilix"
        launcher.parent.mkdir()
        launcher.touch(mode=0o755)
        result = self.shell('PLEBIAN_OS_DIR="$2/os-checkout"\nensure_plebian_os_checkout')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("as_user git clone", result.stdout)

    def test_packaged_with_checkouts_runs_checkout_extras_without_updating_pleb_or_building(self):
        (self.root / "pleb/.git").mkdir(parents=True)
        launcher = self.root / "kilix/kilix"
        launcher.parent.mkdir()
        launcher.touch(mode=0o755)
        result = self.shell(INSTALL + CHECKS_AND_ENGINE + 'KIOSK=1\n' + AUTOLOGIN)
        self.assertEqual(result.returncode, 0, result.stderr)
        for action in ("using the packaged Needle runtime", "claudex-called", "llm-called", "neuronte-called",
                       "install-default-models.py --kilix", "install-image-models.py --kilix",
                       "default_models.py verify", "package command autologin on desktop", "pin-session"):
            self.assertIn(action, result.stdout)
        for action in ("needle-called", "update_pleb_checkout", "as_user git clone", "checkout-build-called"):
            self.assertNotIn(action, result.stdout)
        self.assertFalse((self.root / "sudoers").exists())

    def test_older_packaged_install_uses_checkout_needle_when_available(self):
        result = self.shell(INSTALL, needle="config-files")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Install the kilix-needle package", result.stderr)
        self.assertNotIn("using the packaged Needle", result.stdout)
        self.assertNotIn("needle-called", result.stdout)

        launcher = self.root / "kilix/kilix"
        launcher.parent.mkdir()
        launcher.touch(mode=0o755)
        result = self.shell(INSTALL, needle="config-files")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("needle-called", result.stdout)
        self.assertNotIn("using the packaged Needle", result.stdout)

    def test_packaged_missing_or_nonexecutable_command_fails_before_checkout(self):
        for name in ("pleb", "kilix"):
            with self.subTest(name=name):
                path = self.root / "bin" / name
                if name == "pleb":
                    path.unlink()
                else:
                    path.chmod(0o644)
                result = self.shell(INSTALL)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(str(path), result.stderr)
                self.assertNotIn("as_user git clone", result.stdout)
                self.assertFalse((self.root / "sudoers").exists())
                path.touch()
                path.chmod(0o755)

    def test_one_missing_package_clones_or_updates_and_writes_the_temporary_grant(self):
        for existing in (False, True):
            with self.subTest(existing=existing):
                if existing:
                    (self.root / "pleb/.git").mkdir(parents=True)
                result = self.shell(INSTALL, kilix="config-files")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("update_pleb_checkout" if existing else "as_user git clone", result.stdout)
                if not existing:
                    self.assertIn("checkout_pinned_ref", result.stdout)
                self.assertIn(f"as_user env TEST_ENV=shared {self.root}/pleb/bin/pleb install", result.stdout)
                for step in ("needle-called", "claudex-called", "llm-called", "neuronte-called"):
                    self.assertIn(step, result.stdout)
                sudoers = self.root / "sudoers"
                self.assertEqual(sudoers.read_text(), "desktop ALL=(ALL) NOPASSWD:ALL\n")
                self.assertEqual(sudoers.stat().st_mode & 0o777, 0o440)
                sudoers.unlink()

    def test_dry_run_keeps_checkout_build_and_writes_no_grant(self):
        result = self.shell(INSTALL + CHECKS_AND_ENGINE, dry=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("as_user git clone", result.stdout)
        self.assertIn("checkout-build-called", result.stdout)
        self.assertFalse((self.root / "sudoers").exists())

    def test_packaged_census_still_detects_weights_added_after_selection(self):
        result = self.shell(INSTALL + '''
PLEBIAN_OS_RELEASE_MODE=1
mkdir -p "$KILIX_DATA_HOME/voice/models/whistle"
verify_kilix_voice_install
''')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("provisioning installed speech-model dictation assets during this run", result.stderr)

    def test_packaged_release_checks_installed_versions_without_checkout_commits(self):
        commits = section('    if [ "$PACKAGED_PLEB" = 0 ]; then\n        pleb_commit=', '    kilix95_commit=')
        versions = section('    pleb_version="$(as_user env ', '    if [ -f "$KILIX95_DIR/main.py" ]; then')
        gate = section('        if [ "$PACKAGED_PLEB" = 1 ]; then\n            validate_component_versions',
                       '        if [ "$INSTALL_UV" = 1 ]; then')
        for release, success in (("0.2.3", True), ("0.2.4", False)):
            with self.subTest(release=release):
                result = self.shell(INSTALL + '''
as_user() {
    if [ "$1" = git ]; then echo "unexpected Git probe" >&2; return 1; fi
    "$@"
}
''' + f'PLEBIAN_OS_VERSION={release}\n' + commits + versions + gate)
                self.assertEqual(result.returncode == 0, success, result.stderr)
                self.assertNotIn("unexpected Git probe", result.stderr)
                if not success:
                    self.assertIn("expected exactly 'pleb 0.2.4'", result.stderr)

    def test_optional_voicebox_logs_its_missing_checkout(self):
        result = self.shell(INSTALL + 'KILIX_VOICEBOX_PACKAGE="$2/offline-package"\n'
                            + 'KILIX_VOICEBOX_PACKAGE_SHA256=' + "a" * 64 + '\ninstall_optional_voicebox\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Skipping the optional Voicebox checkout installer", result.stdout)


if __name__ == "__main__":
    unittest.main()
