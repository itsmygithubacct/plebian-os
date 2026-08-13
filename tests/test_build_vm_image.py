import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build"))

import build_vm_image as vm


def args(**overrides):
    values = dict(
        yes=True, name=None, username=None, fullname=None, password="explicit",
        hostname=None, ram=None, cpus=None, vram=None, accelerate_3d=False,
        firmware=None,
        disk=None, session=None, kiosk=None, nopasswd_sudo=None, port=None,
        gui=False, no_wait=True, iso=None, no_verify=False,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def cfg(**overrides):
    values = dict(
        name="test", username="pleb", fullname="Plebian User",
        password="strong-secret", hostname="plebian", ram_mb=1024, cpus=1,
        vram_mb=128, accelerate_3d=False, firmware="bios", disk_gb=8, desktop=True,
        kiosk=True, nopasswd_sudo=False, ssh_port=2222, gui=False, wait=False,
    )
    values.update(overrides)
    return vm.Config(**values)


class VmBuilderEnvTests(unittest.TestCase):
    def test_default_wait_budget_covers_install_and_firstboot(self):
        self.assertEqual(vm.DEFAULT_PROVISION_TIMEOUT_MINUTES, 120)
        result = subprocess.run(
            [sys.executable, str(ROOT / "build" / "build_vm_image.py"),
             "--help"],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn(
            "combined minutes to wait for Debian installation",
            result.stdout,
        )
        self.assertIn("firstboot (default: 120)", result.stdout)

    def test_preseed_has_identity_but_no_second_runtime_env_writer(self):
        with mock.patch.object(vm, "crypt_password", return_value=("$6$hash", True)):
            text = vm.generate_preseed(cfg()).read_text()
        self.assertIn("d-i passwd/username string pleb", text)
        self.assertIn("d-i passwd/user-password-crypted password $6$hash", text)
        self.assertNotIn("PLEB_REF=%s", text)
        self.assertNotIn("env_fmt", text)

    def test_build_iso_forwards_authoritative_runtime_config(self):
        seen = {}
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.iso"
            seed = Path(td) / "preseed.cfg"
            seed.write_text("seed\n")

            def fake_run(_argv, **kwargs):
                seen.update(kwargs["env"])
                out.write_bytes(b"iso")

            with mock.patch.object(vm, "run", side_effect=fake_run):
                vm.build_iso(cfg(), seed, out, False)

        expected = vm.runtime_build_env(cfg())
        for key, value in expected.items():
            self.assertEqual(seen[key], value)
        self.assertEqual(seen["PLEBIAN_OS_SSH_ENABLED"], "1")
        self.assertEqual(seen["PLEBIAN_OS_AUTOBOOT"], "1")
        self.assertEqual(seen["PLEBIAN_OS_UNATTENDED_DISK"], "1")

    def test_acceptance_checks_coordinated_source_allocation(self):
        source = (ROOT / "build" / "build_vm_image.py").read_text()
        self.assertIn('"coordinated checkouts"', source)
        self.assertIn('"pleb recovery guide"', source)
        self.assertIn("/usr/local/share/doc/pleb/RECOVERY.md", source)
        for commit in (
            "PLEBIAN_OS_COMMIT", "PLEB_COMMIT", "KILIX_COMMIT",
            "KILIX95_COMMIT",
        ):
            self.assertIn(commit, source[source.index("def verify_provisioning"):])
        self.assertIn('[0-9a-f]{40}', source[source.index("def verify_provisioning"):])
        for ref in ("PLEBIAN_OS_REF", "PLEB_REF", "KILIX_REF", "KILIX95_REF"):
            self.assertIn(ref, source[source.index("def verify_provisioning"):])
        self.assertIn('git -C "${dir_var}" rev-parse HEAD', source)
        self.assertIn('"provision version"', source)
        self.assertIn(
            "/usr/local/sbin/plebian-os-provision --version",
            source[source.index("def verify_provisioning"):],
        )
        self.assertIn('"component versions"', source)
        self.assertIn("/usr/local/bin/pleb --version", source)
        self.assertIn('"$KILIX_DIR/kilix" --kilix-version', source)
        self.assertIn('python3 "$KILIX95_DIR/main.py" --version', source)
        self.assertIn('"session exports"', source)
        self.assertIn('KILIX95_REF=', source[source.index("def verify_provisioning"):])
        for checkout in ("PLEBIAN_OS_DIR", "PLEB_DIR", "KILIX_DIR", "KILIX95_DIR"):
            self.assertIn(checkout, source[source.index("def verify_provisioning"):])

    def test_acceptance_checks_coherent_canonical_kilix_generation(self):
        source = (ROOT / "build" / "build_vm_image.py").read_text()
        verify = source[source.index("def verify_provisioning"):]
        self.assertIn('"kilix fork generation"', verify)
        self.assertIn("KILIX_STATE_DIRECTORY", verify)
        self.assertIn("KILIX_BUILD_DIRECTORY", verify)
        self.assertIn("current/source-id", verify)
        self.assertIn("generations/build", verify)
        self.assertIn("readlink --", verify)
        self.assertIn("fork-built-ref", verify)
        self.assertIn("launcher/kitty", verify)
        self.assertIn("launcher/kitten", verify)
        self.assertIn("rev-parse --verify HEAD", verify)
        self.assertIn("pwd -P", verify)
        self.assertIn("--which", verify)
        self.assertIn('timeout 15 "$t" --version', verify)
        self.assertIn("cmp -s", verify)
        self.assertIn("stat -c \\'%a\\'", verify)
        self.assertIn("stat -c \\'%h\\'", verify)
        self.assertIn('test ! -e "$ps/kilix-fork-built-ref"', verify)
        self.assertIn('test ! -L "$ps/kilix-fork-built-ref"', verify)

    def test_acceptance_checks_private_storage_roots(self):
        source = (ROOT / "build" / "build_vm_image.py").read_text()
        verify = source[source.index("def verify_provisioning"):]
        self.assertIn('"private storage roots"', verify)
        for root in (
            "GPU_TERMINAL_HOME",
            "PLEB_STORAGE_HOME",
            "KILIX_STORAGE_HOME",
            "KILIX95_STORAGE_HOME",
            "PLEBIAN_OS_STORAGE_HOME",
            "PLEB_CONFIG_HOME",
            "PLEB_STATE_HOME",
            "PLEB_CACHE_HOME",
            "PLEB_SESSION_HOME",
            "PLEB_DATA_HOME",
            "KILIX_CONFIG_HOME",
            "KILIX_STATE_DIRECTORY",
            "KILIX_CACHE_HOME",
            "KILIX_SESSION_HOME",
            "KILIX_BUILD_DIRECTORY",
            "KILIX_DATA_HOME",
            "KILIX_PREBUILT_HOME",
            "KILIX95_CONFIG_HOME",
            "KILIX95_STATE_HOME",
            "KILIX95_CACHE_HOME",
            "KILIX95_SESSION_HOME",
            "KILIX95_DATA_HOME",
            "PLEBIAN_OS_SESSION_HOME",
            "KILIX_DESKTOP_DIR",
        ):
            self.assertIn(root, verify)
        self.assertIn("stat -c \\'%u\\'", verify)
        self.assertIn("stat -c \\'%a\\'", verify)
        self.assertIn("readlink -m", verify)
        self.assertIn('case "$d" in "$anchor"/*)', verify)
        self.assertIn('private_dir "$HOME" "$g"', verify)
        self.assertIn('private_dir "$p" "$pc"', verify)
        self.assertIn('private_dir "$k" "$kc"', verify)
        self.assertIn('private_tree "$k" "$kp"', verify)
        self.assertIn('private_dir "$tree_root" "$tree_current"', verify)
        self.assertIn('private_dir "$n" "$nc"', verify)
        self.assertIn('private_dir "$o" "$or"', verify)
        self.assertIn('"$pd"/*) private_dir "$pd" "$w"', verify)
        self.assertIn('= 700 ];', verify)

    def test_acceptance_checks_exact_session_selection(self):
        source = (ROOT / "build" / "build_vm_image.py").read_text()
        verify = source[source.index("def verify_provisioning"):]
        self.assertIn('"session selection"', verify)
        self.assertIn('"session provenance"', verify)
        self.assertIn('"visible kilix chrome"', verify)
        self.assertIn('"first-page Kilix desktop"', verify)
        self.assertIn(
            "KILIX_ARGV=(--start-as=maximized -o "
            "hide_window_decorations=yes)",
            verify,
        )
        self.assertIn("KILIX_ARGV=(--start-as=fullscreen)", verify)
        self.assertIn("DESKTOP_ARGS=(env KILIX_IN_OVERLAY=1", verify)
        self.assertIn('\\"$KILIX\\" desktop)', verify)
        for key in (
            "PLEB_DESKTOP", "PLEB_RESPAWN", "PLEBIAN_OS_DESKTOP",
            "PLEBIAN_OS_KIOSK", "KILIX_DESKTOP_PROVIDER",
            "KILIX_DESKTOP_FLAVOR",
        ):
            self.assertIn(key, verify)

    def test_catalog_acceptance_builds_in_temporary_guest_roots(self):
        result = SimpleNamespace(returncode=0, stdout="", stderr="")
        with mock.patch.object(vm, "ssh", return_value=result) as remote, \
                mock.patch.object(vm, "info"):
            vm.verify_catalog_builds(cfg(), "askpass")
        command = remote.call_args.args[1]
        self.assertIn("TemporaryDirectory", command)
        self.assertIn("default_catalog", command)
        self.assertIn("Installer", command)
        self.assertIn("spec.source_type", command)
        self.assertIn("timeout 1750 python3", command)
        self.assertEqual(remote.call_args.kwargs["timeout"], 1800)

    def test_acceptance_treats_exit_status_as_authoritative(self):
        # A failed guest command that happens to print "OK" must never pass.
        result = SimpleNamespace(returncode=1, stdout="OK\n", stderr="")
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(vm, "ssh", return_value=result) as remote, \
                mock.patch.object(vm, "info"), self.assertRaises(SystemExit):
            vm.verify_provisioning(cfg(), "askpass")
        self.assertGreater(remote.call_count, 1)

    def test_update_rollback_gate_uses_real_installed_updater(self):
        result = SimpleNamespace(returncode=0, stdout="", stderr="")
        with mock.patch.object(vm, "ssh", return_value=result) as remote, \
                mock.patch.object(vm, "info"):
            vm.verify_update_rollback(cfg(), "askpass")
        command = remote.call_args.args[1]
        self.assertIn("PLEBIAN_OS_UPDATE_TEST_FAIL_AFTER=os-layer", command)
        self.assertIn("/usr/local/bin/plebian-os-update", command)
        self.assertIn("snapshot_acceptance_update", command)
        self.assertIn('cmp -s "$before" "$after"', command)
        self.assertIn("/usr/local/bin/plebian-os-select-closure", command)

    def test_successful_update_waits_for_a_new_lightdm_invocation(self):
        before = SimpleNamespace(
            returncode=0,
            stdout="0123456789abcdef0123456789abcdef\n",
            stderr="",
        )
        success = SimpleNamespace(returncode=0, stdout="", stderr="")
        with mock.patch.object(
                vm, "ssh", side_effect=(before, success, success)) as remote, \
                mock.patch.object(vm, "info"):
            vm.verify_successful_update(cfg(), "askpass")

        self.assertEqual(remote.call_count, 3)
        self.assertIn("InvocationID", remote.call_args_list[0].args[1])
        self.assertIn("plebian-os-update --restart", remote.call_args_list[1].args[1])
        health = remote.call_args_list[2].args[1]
        self.assertIn("timeout 45", health)
        self.assertIn("0123456789abcdef0123456789abcdef", health)
        self.assertIn('"$current" != "$1"', health)
        self.assertIn("systemctl is-active --quiet lightdm.service", health)
        self.assertIn("systemctl is-failed --quiet lightdm.service", health)
        self.assertEqual(remote.call_args_list[2].kwargs["timeout"], 60)

    def test_successful_update_refuses_missing_lightdm_identity(self):
        missing = SimpleNamespace(returncode=0, stdout="\n", stderr="")
        with mock.patch.object(vm, "ssh", return_value=missing) as remote, \
                mock.patch.object(vm, "info"), self.assertRaises(SystemExit):
            vm.verify_successful_update(cfg(), "askpass")
        self.assertEqual(remote.call_count, 1)

    def test_catalog_acceptance_program_clean_builds_and_selects_every_pin(self):
        installed = []
        roots = []

        class Installer:
            def __init__(self, root):
                self.root = Path(root)
                roots.append(self.root)

            def executable(self, spec):
                return str(self.root / spec.content_id / spec.binary)

            def ensure(self, spec, report):
                installed.append(spec.content_id)
                report(f"building {spec.content_id}")
                executable = Path(self.executable(spec))
                executable.parent.mkdir(parents=True, exist_ok=True)
                executable.write_text("#!/bin/sh\n")
                executable.chmod(0o755)
                return str(executable)

            def ready(self, spec):
                executable = Path(self.executable(spec))
                return str(executable) if executable.is_file() else None

        specs = (
            SimpleNamespace(
                content_id="game", source_type="git", kind="game",
                binary="game",
            ),
            SimpleNamespace(
                content_id="app", source_type="archive", kind="app",
                binary="bin/app",
            ),
            SimpleNamespace(
                content_id="builtin", source_type="custom", kind="app",
                binary="",
            ),
        )
        module = ModuleType("kilix_content")
        module.Installer = Installer
        module.default_catalog = lambda: specs
        with mock.patch.dict(sys.modules, {"kilix_content": module}), \
                mock.patch("builtins.print"):
            exec(vm._catalog_build_script(), {})

        self.assertEqual(installed, ["game", "app"])
        self.assertTrue(roots)
        self.assertTrue(all(not root.exists() for root in roots))

    def test_yes_mode_generates_password(self):
        with mock.patch.object(vm, "generated_password", return_value="random-pass"):
            built = vm.gather_config(args(password=None))
        self.assertEqual(built.password, "random-pass")

    def test_yes_mode_honors_explicit_password(self):
        with mock.patch.object(vm, "generated_password", return_value="random-pass"):
            built = vm.gather_config(args(password="explicit"))
        self.assertEqual(built.password, "explicit")

    def test_image_config_uses_documented_release_password(self):
        with mock.patch.dict(os.environ, {
            "IMAGE_PASSWORD": "plebian",
            "RANDOM_PASSWORD": "0",
        }, clear=True):
            built = vm.gather_config(args(password=None))
        self.assertEqual(built.password, "plebian")

    def test_random_password_config_overrides_image_password(self):
        with mock.patch.dict(os.environ, {
            "IMAGE_PASSWORD": "plebian",
            "RANDOM_PASSWORD": "1",
        }, clear=True), mock.patch.object(
                vm, "generated_password", return_value="random-pass"):
            built = vm.gather_config(args(password=None))
        self.assertEqual(built.password, "random-pass")

    def test_explicit_password_overrides_image_config(self):
        with mock.patch.dict(os.environ, {
            "IMAGE_PASSWORD": "configured",
            "RANDOM_PASSWORD": "1",
        }, clear=True), mock.patch.object(vm, "generated_password") as generated:
            built = vm.gather_config(args(password="explicit"))
        self.assertEqual(built.password, "explicit")
        generated.assert_not_called()

    def test_defaults_to_desktop_in_first_kilix_page_and_non_kiosk(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            built = vm.gather_config(args())
        self.assertTrue(built.desktop)
        self.assertFalse(built.kiosk)

    def test_environment_session_defaults_are_honored(self):
        with mock.patch.dict(os.environ, {
            "PLEBIAN_OS_DESKTOP": "yes",
            "PLEBIAN_OS_KIOSK": "on",
            "PLEBIAN_OS_NOPASSWD_SUDO": "no",
        }, clear=True):
            built = vm.gather_config(args())
        self.assertTrue(built.desktop)
        self.assertTrue(built.kiosk)
        self.assertFalse(built.nopasswd_sudo)

    def test_explicit_session_flags_override_environment_defaults(self):
        with mock.patch.dict(os.environ, {
            "PLEBIAN_OS_DESKTOP": "1",
            "PLEBIAN_OS_KIOSK": "1",
        }, clear=True):
            built = vm.gather_config(args(session="shell", kiosk=False))
        self.assertFalse(built.desktop)
        self.assertFalse(built.kiosk)

    def test_invalid_environment_boolean_fails_closed(self):
        with mock.patch.dict(os.environ, {"PLEBIAN_OS_DESKTOP": "sometimes"},
                             clear=True), self.assertRaises(SystemExit):
            vm.gather_config(args())

    def test_vram_is_capped_to_virtualbox_limit(self):
        built = vm.gather_config(args(vram=512, accelerate_3d=True))
        self.assertEqual(built.vram_mb, 256)
        self.assertTrue(built.accelerate_3d)

    def test_firmware_defaults_to_bios_and_accepts_efi(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(vm.gather_config(args()).firmware, "bios")
            self.assertEqual(
                vm.gather_config(args(firmware="efi")).firmware,
                "efi",
            )

    def test_default_hostname_sanitizes_versioned_vm_name(self):
        built = vm.gather_config(args(
            name="plebian-acceptance-0.1.9-deadbeef",
            hostname=None,
        ))
        self.assertEqual(
            built.hostname,
            "plebian-acceptance-0-1-9-deadbeef",
        )

    def test_default_ram_uses_release_tested_floor(self):
        with mock.patch.object(vm, "host_ram_mb", return_value=8192):
            self.assertEqual(vm.default_ram_mb(), 4096)
        with mock.patch.object(vm, "host_ram_mb", return_value=32768):
            self.assertEqual(vm.default_ram_mb(), 8192)

    def test_explicit_low_ram_is_honored_with_warning(self):
        with mock.patch.object(vm, "warn") as warn:
            built = vm.gather_config(args(ram=2048))
        self.assertEqual(built.ram_mb, 2048)
        self.assertIn("below the 4096 MB release-tested", warn.call_args.args[0])

    def test_identity_values_are_rejected_before_preseed_or_vbox(self):
        bad = (
            dict(name="../escape"),
            dict(username="root;touch-x"),
            dict(username="root"),
            dict(username="_service"),
            dict(fullname="Name:newline"),
            dict(hostname="bad host"),
            dict(password="bad\nsecret"),
        )
        for values in bad:
            with self.subTest(values=values), self.assertRaises(SystemExit):
                vm.validate_identity(**{
                    "name": "test", "username": "pleb", "fullname": "Plebian User",
                    "password": "secret", "hostname": "test", **values,
                })

    def test_existing_vm_needs_explicit_replace(self):
        with mock.patch.object(vm, "vbox_exists", return_value=True), \
                mock.patch.object(vm, "run") as run:
            with self.assertRaises(SystemExit):
                vm.vbox_create(cfg(), Path("image.iso"), assume_yes=True)
        run.assert_not_called()

    def test_replace_and_yes_is_the_explicit_delete_gate(self):
        calls = []
        with mock.patch.object(vm, "vbox_exists", return_value=True), \
                mock.patch.object(vm, "run", side_effect=lambda argv, **_kw: calls.append(argv)), \
                mock.patch.object(vm, "vbox_info", return_value={"CfgFile": "/tmp/test/test.vbox"}), \
                mock.patch.object(vm.subprocess, "run"), \
                mock.patch.object(vm.time, "sleep"):
            vm.vbox_create(cfg(), Path("image.iso"), replace=True, assume_yes=True)
        self.assertIn(["VBoxManage", "unregistervm", "test", "--delete"], calls)

    def test_virtualbox_exposes_audio_and_hotpluggable_install_media(self):
        calls = []
        with mock.patch.object(vm, "vbox_exists", return_value=False), \
                mock.patch.object(
                    vm, "run", side_effect=lambda argv, **_kw: calls.append(argv)
                ), \
                mock.patch.object(
                    vm, "vbox_info",
                    return_value={"CfgFile": "/tmp/test/test.vbox"},
                ):
            vm.vbox_create(cfg(), Path("image.iso"))

        modify = next(call for call in calls if call[:2] == ["VBoxManage", "modifyvm"])
        self.assertEqual(modify[modify.index("--audio-enabled") + 1], "on")
        self.assertEqual(modify[modify.index("--audio-in") + 1], "on")
        self.assertEqual(modify[modify.index("--audio-out") + 1], "on")
        self.assertEqual(modify[modify.index("--firmware") + 1], "bios")
        dvd = next(call for call in calls if
                   call[:2] == ["VBoxManage", "storageattach"] and
                   "dvddrive" in call)
        self.assertEqual(dvd[dvd.index("--hotpluggable") + 1], "on")

    def test_iso_detach_failure_is_fatal(self):
        failed = SimpleNamespace(returncode=1, stdout="", stderr="busy")
        with mock.patch.object(vm, "vbox_info", return_value={
                "SATA-1-0": "/tmp/installer.iso",
        }), mock.patch.object(vm.subprocess, "run", return_value=failed), \
                self.assertRaises(SystemExit):
            vm.vbox_detach_iso(cfg())

    def test_iso_detach_is_idempotent_after_guest_eject(self):
        with mock.patch.object(vm, "vbox_info", return_value={
                "SATA-1-0": "emptydrive",
                "SATA-IsEjected-1-0": "on",
        }), mock.patch.object(vm.subprocess, "run") as detach:
            vm.vbox_detach_iso(cfg())
        detach.assert_not_called()

    def test_acceptance_report_is_nonsecret_and_checksummed(self):
        git_results = [
            SimpleNamespace(stdout="a" * 40 + "\n"),
            SimpleNamespace(stdout=""),
        ]
        with mock.patch.object(
                vm, "run", return_value=SimpleNamespace(stdout="7.1.0\n")), \
                mock.patch.object(
                    vm.subprocess, "run", side_effect=git_results):
            initial = vm.acceptance_report_initial(cfg(), args())
        serialized = json.dumps(initial)
        self.assertNotIn("strong-secret", serialized)
        self.assertNotIn(str(vm.REPO), serialized)

        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "acceptance.json"
            iso = Path(td) / "candidate.iso"
            iso.write_bytes(b"candidate bytes")
            recorder = vm.AcceptanceRecorder(report, initial)
            recorder.stage("preflight")
            recorder.set_iso(iso)
            recorder.check("guest check", True)
            recorder.complete()
            parsed = json.loads(report.read_text())
            self.assertEqual(parsed["status"], "passed")
            self.assertEqual(parsed["stages"][0]["name"], "preflight")
            self.assertEqual(parsed["iso"]["filename"], "candidate.iso")
            self.assertNotIn(td, json.dumps(parsed))
            checksum = hashlib.sha256(report.read_bytes()).hexdigest()
            self.assertEqual(
                (Path(str(report) + ".sha256")).read_text(),
                f"{checksum}  {report.name}\n",
            )

    def test_openssl_failure_never_falls_back_to_plaintext(self):
        result = SimpleNamespace(returncode=1, stdout="", stderr="failed")
        with mock.patch.object(vm, "have", return_value=True), \
                mock.patch.object(vm.subprocess, "run", return_value=result), \
                self.assertRaises(SystemExit):
            vm.crypt_password("secret")


if __name__ == "__main__":
    unittest.main()
