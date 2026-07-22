import subprocess
import sys
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
            "GPU_TERMINAL_SOURCE_HOME",
            "GPU_TERMINAL_HOME",
            "GPU_TERMINAL_SETTINGS_FILE",
            "PLEBIAN_OS_MANAGED_INSTALL",
            "PLEB_DIR",
            "PLEB_STORAGE_HOME",
            "PLEB_CONFIG_HOME",
            "PLEB_STATE_HOME",
            "PLEB_CACHE_HOME",
            "PLEB_SESSION_HOME",
            "PLEB_DATA_HOME",
            "PLEB_REPO",
            "PLEB_BRANCH",
            "PLEB_REF",
            "KILIX_REPO",
            "KILIX_STORAGE_HOME",
            "KILIX_CONFIG_HOME",
            "KILIX_STATE_DIRECTORY",
            "KILIX_CACHE_HOME",
            "KILIX_SESSION_HOME",
            "KILIX_BUILD_DIRECTORY",
            "KILIX_DATA_HOME",
            "KILIX_DESKTOP_DIR",
            "KILIX_PREBUILT_HOME",
            "KILIX_BRANCH",
            "KILIX_REF",
            "KILIX_PREBUILT_VERSION",
            "KILIX_PREBUILT_SHA256",
            "PLEBIAN_OS_BUILD_KILIX_FORK",
            "PLEBIAN_OS_KILIX_GO_MIN_VERSION",
            "KILIX_DESKTOP_PROVIDER",
            "KILIX_DESKTOP_COMMAND",
            "KILIX_DESKTOP_NAME",
            "KILIX_DESKTOP_FLAVOR",
            "KILIX95_AUTO_INSTALL",
            "KILIX95_DIR",
            "KILIX95_STORAGE_HOME",
            "KILIX95_CONFIG_HOME",
            "KILIX95_STATE_HOME",
            "KILIX95_CACHE_HOME",
            "KILIX95_SESSION_HOME",
            "KILIX95_DATA_HOME",
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

    def test_fresh_install_uses_sibling_source_and_data_roots(self):
        provision = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
        update = (ROOT / "provision" / "plebian-os-update.sh").read_text()
        for source, source_default in (
            (provision, 'GPU_TERMINAL_SOURCE_HOME="${GPU_TERMINAL_SOURCE_HOME:-$USER_HOME/gpu_terminal}"'),
            (update, 'GPU_TERMINAL_SOURCE_HOME="${GPU_TERMINAL_SOURCE_HOME:-$HOME/gpu_terminal}"'),
        ):
            for contract in (
                source_default,
                '$GPU_TERMINAL_SOURCE_HOME/pleb',
                '$GPU_TERMINAL_SOURCE_HOME/kilix',
                '$GPU_TERMINAL_SOURCE_HOME/kilix-95',
                '$GPU_TERMINAL_SOURCE_HOME/plebian-os',
                '$GPU_TERMINAL_HOME/pleb',
                '$GPU_TERMINAL_HOME/kilix',
                '$GPU_TERMINAL_HOME/kilix-95',
                '$GPU_TERMINAL_HOME/plebian-os',
            ):
                self.assertIn(contract, source)
        self.assertNotIn('PLEB_DIR="$USER_HOME/pleb"', provision)
        for source in (provision, update):
            self.assertIn('"PLEBIAN_OS_MANAGED_INSTALL=1"', source)

        sys.path.insert(0, str(ROOT / "build"))
        import build_vm_image as vm
        cfg = vm.Config(
            name="fresh", username="pleb", fullname="Plebian User",
            password="unused", hostname="fresh", ram_mb=4096, cpus=2,
            vram_mb=128, accelerate_3d=False, disk_gb=20, desktop=True,
            kiosk=False, nopasswd_sudo=False, ssh_port=2222, gui=False,
            wait=False,
        )
        env = vm.runtime_build_env(cfg)
        self.assertEqual(
            env["PLEBIAN_OS_TARGET_SOURCE_HOME"],
            "/home/pleb/gpu_terminal",
        )
        self.assertEqual(
            env["PLEBIAN_OS_TARGET_GPU_TERMINAL_HOME"],
            "/home/pleb/.local/gpu_terminal",
        )
        for host_or_guest_key in (
            "GPU_TERMINAL_SOURCE_HOME", "GPU_TERMINAL_HOME",
            "PLEBIAN_OS_DIR", "PLEB_DIR", "KILIX_DIR", "KILIX95_DIR",
            "PLEB_STORAGE_HOME", "KILIX_STORAGE_HOME",
            "KILIX95_STORAGE_HOME", "PLEBIAN_OS_STORAGE_HOME",
        ):
            self.assertNotIn(host_or_guest_key, env)

    def test_source_and_data_layout_reaches_media_and_session_provenance(self):
        remaster = (ROOT / "build" / "remaster-iso.sh").read_text()
        provision = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
        keys = (
            "GPU_TERMINAL_SOURCE_HOME", "GPU_TERMINAL_HOME",
            "GPU_TERMINAL_SETTINGS_FILE",
            "PLEBIAN_OS_DIR", "PLEBIAN_OS_STORAGE_HOME",
            "PLEB_DIR", "PLEB_STORAGE_HOME", "PLEB_CONFIG_HOME",
            "PLEB_STATE_HOME", "PLEB_CACHE_HOME", "PLEB_SESSION_HOME",
            "PLEB_DATA_HOME",
            "KILIX_DIR", "KILIX_STORAGE_HOME", "KILIX_CONFIG_HOME",
            "KILIX_STATE_DIRECTORY", "KILIX_CACHE_HOME",
            "KILIX_SESSION_HOME", "KILIX_BUILD_DIRECTORY",
            "KILIX_DATA_HOME", "KILIX_DESKTOP_DIR", "KILIX_PREBUILT_HOME",
            "KILIX95_DIR", "KILIX95_STORAGE_HOME", "KILIX95_CONFIG_HOME",
            "KILIX95_STATE_HOME", "KILIX95_CACHE_HOME",
            "KILIX95_SESSION_HOME", "KILIX95_DATA_HOME",
        )
        for key in keys:
            with self.subTest(key=key):
                self.assertIn(f"manifest_kv {key}", remaster)
                self.assertIn(f"env_kv {key}", remaster)
                self.assertIn(f"write_session_default {key}", provision)
                self.assertIn(f"provenance_kv {key}", provision)

    def test_shared_chrome_settings_and_widget_tools_ship_with_the_os(self):
        provision = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
        update = (ROOT / "provision" / "plebian-os-update.sh").read_text()
        deps = (ROOT / "provision" / "install-deps.sh").read_text()
        preseed = (ROOT / "preseed" / "preseed.cfg").read_text()

        self.assertIn('$GPU_TERMINAL_HOME/settings.conf', provision)
        self.assertIn('"GPU_TERMINAL_SETTINGS_FILE=$GPU_TERMINAL_SETTINGS_FILE"',
                      provision)
        self.assertIn('shared Kilix settings were not safely initialized',
                      provision)
        self.assertIn('KILIX_SETTINGS_LINK="${KILIX_SETTINGS_LINK:-/usr/local/bin/kilix-settings}"',
                      update)
        self.assertGreaterEqual(
            update.count('/usr/local/bin/kilix-settings'), 3,
            "the settings command must be validated, snapshotted, and restored",
        )
        self.assertIn('network-manager', deps)
        self.assertIn('network-manager', preseed)
        self.assertIn('pulsemixer', deps)
        self.assertIn('pulsemixer', preseed)

    def test_session_env_writer_uses_shell_escaped_defaults(self):
        text = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
        self.assertIn("write_session_default", text)
        self.assertIn("printf 'if [ -z", text)
        self.assertIn(
            "export KILIX_CONFIG_HOME KILIX_STATE_DIRECTORY KILIX_CACHE_HOME "
            "KILIX_SESSION_HOME KILIX_PREBUILT_HOME",
            text,
        )
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

    def test_firstboot_allocates_and_records_plebian_os_checkout(self):
        provision = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
        self.assertIn("ensure_plebian_os_checkout()", provision)
        self.assertIn(
            'remote="$(as_target_readonly git -C "$dir" config --get remote.origin.url',
            provision,
        )
        self.assertIn(
            'as_user git clone "${clone_args[@]}" "$PLEBIAN_OS_REPO" "$PLEBIAN_OS_DIR"',
            provision,
        )
        self.assertLess(
            provision.rindex("\nensure_plebian_os_checkout\n"),
            provision.index(
                'as_user env "${install_env[@]}" "$PLEB_DIR/bin/pleb" install'
            ),
        )
        for key in (
            "PLEBIAN_OS_REPO", "PLEBIAN_OS_BRANCH", "PLEBIAN_OS_REF",
            "PLEBIAN_OS_COMMIT",
        ):
            self.assertIn(f"provenance_kv {key}", provision)

    def test_reset_env_runtime_calls_receive_coordinated_storage(self):
        provision = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
        for invocation in (
            'as_user env "${install_env[@]}" "$KILIX_DIR/kilix" --build',
            'as_user env "${install_env[@]}" "$KILIX_DIR/kilix" --which',
            'as_user env "${install_env[@]}" "$PLEB_DIR/bin/pleb" autologin',
        ):
            self.assertIn(invocation, provision)

    def test_privileged_dependency_staging_never_uses_user_session_state(self):
        deps = (ROOT / "provision" / "install-deps.sh").read_text()
        self.assertNotIn("PLEBIAN_OS_SESSION_HOME", deps)
        self.assertIn("PLEBIAN_OS_ROOT_SESSION_HOME", deps)
        self.assertIn("/var/lib/plebian-os/session", deps)
        self.assertIn("root:root mode 0700", deps)
        self.assertIn('readlink -m -- "$PLEBIAN_OS_ROOT_SESSION_HOME"', deps)

    def test_update_honors_pinned_pleb_ref(self):
        text = (ROOT / "provision" / "plebian-os-update.sh").read_text()
        self.assertIn("PLEB_REF", text)
        self.assertIn('checkout_pinned_ref "$PLEB_DIR" "$PLEB_REF" "pleb"', text)
        self.assertIn("FETCH_HEAD^{commit}", text)
        self.assertIn("require_clean_pinned_checkout", text)
        self.assertIn('[ "$actual" = "$resolved" ]', text)
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
                if path.name == "plebian-os-provision.sh":
                    self.assertIn(
                        'current="$(as_target_readonly git -C "$PLEB_DIR"',
                        text,
                    )

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
        self.assertIn("RestartSec=60s", text)
        self.assertIn("StartLimitIntervalSec=4h", text)
        self.assertIn("StartLimitBurst=3", text)
        self.assertIn("TimeoutStartSec=3600", text)

    def test_firstboot_builds_and_verifies_kilix_fork(self):
        text = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
        self.assertIn("build_kilix_fork", text)
        self.assertIn("verify_kilix_fork_build", text)
        self.assertIn("submodule update --init --recursive", text)
        self.assertIn("scripts/install-go.sh", text)
        self.assertIn('"$KILIX_DIR/kilix" --build', text)
        self.assertIn("src/kitty/launcher/kitty", text)
        self.assertIn("src/kitty/launcher/kitten", text)
        self.assertIn("generations/build", text)
        self.assertIn("current/source-id", text)
        self.assertIn('"$KILIX_STATE_DIRECTORY/fork-built-ref"', text)
        self.assertIn('"$KILIX_DIR/kilix" --which', text)
        self.assertIn('probe_kilix_launcher "$kitten"', text)
        self.assertIn('timeout 15 "$1" --version', text)
        self.assertIn("cmp -s", text)
        self.assertNotIn('"$PLEB_STATE_HOME/kilix-fork-built-ref"', text)

    def test_provision_disables_kernel_speaker_beeps(self):
        text = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
        self.assertIn("plebian-os-no-beep.conf", text)
        self.assertIn("blacklist pcspkr", text)
        self.assertIn("blacklist snd_pcsp", text)
        self.assertIn("modprobe -r snd_pcsp pcspkr", text)

    def test_provision_as_user_does_not_open_logind_sessions(self):
        text = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
        self.assertIn("setpriv --reuid", text)
        self.assertIn("--reset-env", text)
        self.assertNotIn("runuser -u", text)

    def test_console_status_spam_is_disabled(self):
        provision = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
        preseed = (ROOT / "preseed" / "preseed.cfg").read_text()
        firstboot = (ROOT / "provision" / "plebian-os-firstboot.service").read_text()

        self.assertIn("50-plebian-os-quiet-console.conf", provision)
        self.assertIn("ShowStatus=no", provision)
        self.assertIn("50-plebian-os-quiet-console.conf", preseed)
        self.assertIn("ShowStatus=no", preseed)
        self.assertIn("StandardOutput=journal", firstboot)
        self.assertIn("StandardError=journal", firstboot)
        self.assertNotIn("journal+console", firstboot)

    def test_netinst_fetch_retries_with_debian_cd_signing_key(self):
        text = (ROOT / "build" / "lib.sh").read_text()
        self.assertIn("PLEBIAN_OS_DEBIAN_CD_KEY_URL", text)
        self.assertIn("key-DA87E80D6294BE9B.txt", text)
        self.assertIn("debian-cd-signing-key.gpg", text)
        self.assertIn("_fetch_debian_cd_keyring", text)
        self.assertIn("_download_sums_pair refresh", text)

    def test_make_usb_rebuilds_unless_reuse_is_explicit(self):
        text = (ROOT / "build" / "make-usb.sh").read_text()
        self.assertNotIn("iso_is_fresh", text)
        self.assertNotIn("baked_env_overrides_present", text)
        self.assertIn("ISO_EXPLICIT", text)
        self.assertIn("REUSE_ISO", text)
        self.assertIn("--reuse-iso", text)
        self.assertIn("Default to a fresh build", text)


if __name__ == "__main__":
    unittest.main()
