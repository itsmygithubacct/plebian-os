import io
import shlex
import re
import os
from pathlib import Path
import runpy
import tarfile
import tempfile
import unittest
from unittest import mock
import subprocess
import contextlib
import hashlib

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "provision/plebian-os-install-encodec-converter"


class EncodecConverterInstallerTests(unittest.TestCase):
    def setUp(self):
        self.ns = runpy.run_path(str(HELPER))
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.destination = Path(self.temp.name)

    def test_download_allows_a_slow_connection_and_bounds_stalled_transfers(self):
        selected = self.ns["archive_for"]("amd64")
        with mock.patch("shutil.disk_usage") as space, mock.patch("subprocess.run") as run:
            space.return_value.free = selected["compact"]["size"] + selected["installed_bytes"]
            run.side_effect = OSError("test stopped before transfer")
            with self.assertRaisesRegex(OSError, "before transfer"):
                self.ns["stage_download"](self.destination, self.destination, selected, None)
        argv = run.call_args.args[0]
        options = {flag: int(argv[argv.index(flag) + 1]) for flag in
                   ("--connect-timeout", "--max-time", "--speed-limit", "--speed-time", "--max-filesize")}
        self.assertGreaterEqual(options["--max-time"] * 256 * 1024, options["--max-filesize"])
        self.assertLessEqual(options["--max-time"], 3600)
        self.assertEqual(options["--max-filesize"], selected["compact"]["size"])
        self.assertEqual(argv[-1], selected["compact"]["url"])
        self.assertEqual((options["--connect-timeout"], options["--speed-limit"], options["--speed-time"]),
                         (20, 1024, 120))

    def test_supported_dry_run_selects_exact_architecture_without_install_action(self):
        for machine, filename in (
                ('x86_64', 'kilix-encodec-converters_shared_amd64.tar.zst'),
                ('amd64', 'kilix-encodec-converters_shared_amd64.tar.zst'),
                ('aarch64', 'kilix-encodec-converters_shared_arm64.tar.zst'),
                ('arm64', 'kilix-encodec-converters_shared_arm64.tar.zst')):
            output = io.StringIO()
            with self.subTest(machine=machine), \
                    mock.patch('platform.machine', return_value=machine), \
                    mock.patch('sys.argv', [str(HELPER), '--dry-run']), \
                    mock.patch('subprocess.run') as command, \
                    mock.patch('os.geteuid') as privilege, \
                    contextlib.redirect_stdout(output):
                self.ns['main']()
            self.assertIn('releases/download/converters-0.2.4-rc.1/' + filename, output.getvalue())
            command.assert_not_called()
            privilege.assert_not_called()

    def test_explicit_archive_can_still_select_either_pinned_format(self):
        supplied = self.destination / 'offline.tar.zst'
        for machine in ('amd64', 'arm64'):
            selected = self.ns['archive_for'](machine)
            for transfer in (selected, selected['compact']):
                with self.subTest(machine=machine, size=transfer['size']):
                    with supplied.open('wb') as stream:
                        stream.truncate(transfer['size'])
                    self.assertIs(self.ns['transfer_for'](selected, supplied), transfer)

    def test_unsupported_architecture_refuses_before_any_install_action(self):
        with mock.patch('platform.machine', return_value='riscv64'), \
                mock.patch('sys.argv', [str(HELPER), '--dry-run']), \
                mock.patch('subprocess.run') as command:
            with self.assertRaisesRegex(ValueError, 'no source-qualified'):
                self.ns['main']()
        command.assert_not_called()

    def test_copy_verify_and_inventory_use_the_selected_archive(self):
        selections = []
        for architecture, content in [('amd64', b'amd'), ('arm64', b'arm')]:
            selected = dict(size=len(content), sha256=hashlib.sha256(content).hexdigest(),
                            files={'BUILD.json': hashlib.sha256(content).hexdigest()})
            selections.append(selected)
            source = self.destination / (architecture + '-source')
            copied = self.destination / (architecture + '-copied')
            source.write_bytes(content)
            self.ns['copy_archive'](source, copied, selected)
            self.ns['verify_archive'](copied, selected)
            self.assertEqual(copied.read_bytes(), content)
            self.assertEqual(self.ns['expected_inventory'](selected)['BUILD.json'],
                             (0o644, selected['sha256']))
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            self.ns['verify_archive'](self.destination / 'arm64-copied', selections[0])
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            self.ns['verify_archive'](self.destination / 'amd64-copied', selections[1])

    def archive(self, extra=(), *, compact=False):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as archive:
            for name in ("bin/kilix-encodec-convert-24khz", ".converter/runtime.tar", ".converter/receipt.json", "bin/kilix-encodec-convert-48khz", ".converter-48khz/runtime.tar", ".converter-48khz/receipt.json", "BUILD.json", "source.tar.gz"):
                if compact and name == ".converter/runtime.tar":
                    continue
                info = tarfile.TarInfo(name)
                info.size = 4
                info.mode = 0o7777  # Privileged/untrusted modes must not survive.
                archive.addfile(info, io.BytesIO(b"test"))
            for info in extra:
                archive.addfile(info, io.BytesIO(b"x" * info.size))
        stream.seek(0)
        return stream

    def test_extracts_ordinary_files_and_discards_privileged_modes(self):
        self.ns["extract_payload"](self.archive(), self.destination, hashlib.sha256(b"test").hexdigest())
        self.assertFalse((self.destination / ".converter/runtime.tar").exists())
        self.assertEqual((self.destination / "BUILD.json").read_bytes(), b"test")
        self.assertEqual((self.destination / "BUILD.json").stat().st_mode & 0o7777, 0o755)

    def test_private_root_umask_does_not_hide_installed_software(self):
        previous = os.umask(0o077)
        try:
            self.ns["extract_payload"](self.archive(compact=True), self.destination)
        finally:
            os.umask(previous)
        self.assertEqual((self.destination / ".converter").stat().st_mode & 0o777, 0o755)

    def test_rejects_escape_links_devices_and_duplicate_members(self):
        for name, kind in (("../escape", tarfile.REGTYPE), ("/absolute", tarfile.REGTYPE),
                           ("link", tarfile.SYMTYPE), ("hardlink", tarfile.LNKTYPE),
                           ("device", tarfile.CHRTYPE), ("BUILD.json", tarfile.REGTYPE)):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                info = tarfile.TarInfo(name)
                info.type = kind
                info.linkname = "../../escape"
                with self.assertRaises(ValueError):
                    self.ns["extract_payload"](self.archive((info,), compact=True), Path(directory))

    def test_discarded_runtime_is_still_authenticated(self):
        with self.assertRaisesRegex(ValueError, "discarded mono runtime checksum"):
            self.ns["extract_payload"](self.archive(), self.destination, "0" * 64)
        self.assertFalse((self.destination / ".converter/runtime.tar").exists())

    def test_compact_archive_requires_only_the_shared_runtime(self):
        self.ns["extract_payload"](self.archive(compact=True), self.destination)
        self.assertTrue((self.destination / ".converter-48khz/runtime.tar").is_file())
        self.assertFalse((self.destination / ".converter/runtime.tar").exists())

    def test_unpacked_limit_is_enforced_before_copy(self):
        extract = self.ns["extract_payload"]
        extract.__globals__["MAX_UNPACKED_BYTES"] = 3
        with self.assertRaisesRegex(ValueError, "extraction bound"):
            extract(self.archive(), self.destination)

    def test_rejects_modified_archive(self):
        archive = self.destination / "archive"
        archive.write_bytes(b"bad")
        verify = self.ns["verify_archive"]
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            verify(archive, dict(size=3, sha256="0" * 64))

    def test_missing_runtime_dependency_fails_before_filesystem_changes(self):
        main = self.ns["main"]
        for index, package in enumerate(("libgomp1", "libstdc++6", "python3", "bubblewrap", "zstd")):
            responses = [subprocess.CompletedProcess([], 0, "installed", "")] * index
            responses.append(subprocess.CompletedProcess([], 1, "", ""))
            with self.subTest(package=package), \
                    mock.patch("sys.argv", [str(HELPER)]), \
                    mock.patch("os.geteuid", return_value=0), \
                    mock.patch("platform.machine", return_value="x86_64"), \
                    mock.patch("subprocess.run", side_effect=responses), \
                    mock.patch.dict(main.__globals__, {"secure_directory": mock.Mock(side_effect=AssertionError("filesystem mutated"))}):
                with self.assertRaisesRegex(ValueError, re.escape(package)):
                    main()

    def test_fresh_provision_ships_helper_without_invoking_it(self):
        source = (ROOT / "provision/plebian-os-provision.sh").read_text()
        start = source.index('ENCODEC_CONVERTER_INSTALLER_SRC=""')
        end = source.index("\nfi\n", start) + len("\nfi\n")
        block = source[start:end]
        helper = self.destination / HELPER.name
        installed = self.destination / "installed-helper"
        calls = self.destination / "calls"
        # Redirect absolute deployment paths only inside this real shell block.
        block = block.replace("$PLEBIAN_OS_SBINDIR/" + HELPER.name, str(installed))
        helper.write_text("#!/bin/sh\necho invoked >> " + shlex.quote(str(calls)) + "\nexit 0\n")
        helper.chmod(0o755)
        prelude = ('set -eu\nlog() { :; }\ndie() { echo "$*" >&2; exit 1; }\n'
                   + "SELF_DIR=" + shlex.quote(str(self.destination)) + "\n")
        for dry_run in (1, 0):
            result = subprocess.run(["bash", "-c", prelude + f"DRY_RUN={dry_run}\n" + block],
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(calls.exists())
        self.assertEqual(installed.read_bytes(), helper.read_bytes())

    def test_refresh_without_an_explicit_request_has_no_install_side_effects(self):
        marker = self.destination / 'requested'
        with mock.patch.dict(self.ns['main'].__globals__, REQUESTED=marker), \
                mock.patch('sys.argv', [str(HELPER), '--refresh']), \
                mock.patch('subprocess.run', return_value=subprocess.CompletedProcess([], 1, '', '')) as command, \
                mock.patch('platform.machine', side_effect=AssertionError('unexpected installation')):
            self.ns['main']()
        self.assertEqual(command.call_count, 1)
        self.assertFalse(marker.exists())

    def test_size_report_touches_neither_opt_in_nor_network(self):
        for machine in ('amd64', 'arm64'):
            output = io.StringIO()
            with self.subTest(machine=machine), mock.patch('platform.machine', return_value=machine), \
                    mock.patch('sys.argv', [str(HELPER), '--download-bytes']), \
                    mock.patch('subprocess.run') as run, mock.patch('os.open') as create, \
                    contextlib.redirect_stdout(output):
                self.ns['main']()
            self.assertEqual(int(output.getvalue()), self.ns['archive_for'](machine)['compact']['size'])
            run.assert_not_called()
            create.assert_not_called()

    def test_explicit_install_records_success_only_and_refresh_reuses_it(self):
        from types import SimpleNamespace
        import stat
        marker = self.destination / 'requested'
        dest = self.destination / 'payload'
        main = self.ns['main']
        with mock.patch.dict(main.__globals__, REQUESTED=marker, DESTINATION=dest,
                             secure_directory=mock.Mock()), \
                mock.patch('os.geteuid', return_value=0), \
                mock.patch('os.fstat', return_value=SimpleNamespace(st_uid=0, st_mode=stat.S_IFREG | 0o600)), \
                mock.patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0, 'installed', '')), \
                mock.patch('sys.argv', [str(HELPER)]):
            with mock.patch.dict(main.__globals__, install_locked=mock.Mock(side_effect=ValueError('failed'))):
                with self.assertRaisesRegex(ValueError, 'failed'):
                    main()
            self.assertFalse(marker.exists())
            action = mock.Mock()
            with mock.patch.dict(main.__globals__, install_locked=action):
                main()
                self.assertTrue(marker.is_file())
                with mock.patch.object(Path, 'lstat', return_value=SimpleNamespace(
                        st_uid=0, st_mode=stat.S_IFREG | 0o644)), mock.patch('sys.argv', [str(HELPER), '--refresh']):
                    main()
                self.assertEqual(action.call_count, 2)

    def test_configuration_rollback_does_not_acquire_converter(self):
        from test_provision_transaction import ProvisionRootTransactionTests
        fixture = ProvisionRootTransactionTests()
        root = self.destination
        setup, paths = fixture._layout(root)
        helper = root / HELPER.name
        payload = paths['created'] / 'kilix-encodec' / 'runtime'
        helper.write_text('#!/bin/sh\nmkdir -p ' + shlex.quote(str(payload.parent))
                          + "\nprintf 'software only\\n' > " + shlex.quote(str(payload)) + '\n')
        helper.chmod(0o755)
        source = (ROOT / 'provision/plebian-os-provision.sh').read_text()
        start = source.rindex('\nnormalize_accounts_service_package_directory\n')
        end = source.index('# Ship only the small source-closure installer', start)
        # The Ollama install is defined with the library functions and stubbed here.
        sequence = source[start:end].replace(
            '$PLEBIAN_OS_SBINDIR/' + HELPER.name, str(root / 'installed-helper'))
        stubs = ''.join(name + '() { :; }\n' for name in (
            'install_ollama_runtime_from_carrier',
            'normalize_accounts_service_package_directory', 'install_no_beep_defaults',
            'disable_audio_holding_user_units', 'install_quiet_console_defaults',
            'install_lid_defaults', 'install_desktop_wallpaper', 'install_version_marker',
            'install_lightdm_greeter_branding', 'install_artwork_notices',
            'install_native_runtime_helpers', 'apply_selected_qt_runtime',
            'apply_selected_mpv_runtime', 'apply_selected_native_runtime'))
        result = fixture._run(setup + stubs + 'SELF_DIR=' + shlex.quote(str(root))
                              + '\n' + sequence + "\nprintf 'changed\\n' > "
                              + shlex.quote(str(paths['existing'])) + '\nexit 19\n')
        self.assertEqual(result.returncode, 19, result.stderr)
        self.assertEqual(paths['existing'].read_text(), 'before\n')
        self.assertFalse(payload.exists())
        self.assertEqual(list(paths['state'].iterdir()), [])

    def test_update_installer_elevates_and_propagates_failure(self):
        source = (ROOT / "provision/plebian-os-update.sh").read_text()
        function = re.search(r"^run_encodec_converter_installer\(\) \{.*?^\}",
                             source, re.M | re.S).group()
        identity = self.destination / "id"
        sudo = self.destination / "sudo"
        helper = self.destination / "helper"
        calls = self.destination / "calls"
        identity.write_text("#!/bin/sh\necho 1000\n")
        sudo.write_text("#!/bin/sh\necho elevated >> " + shlex.quote(str(calls)) + '\nexec "$@"\n')
        helper.write_text('#!/bin/sh\n[ "$1" = --refresh ] || exit 9\nexit 7\n')
        for path in (identity, sudo, helper):
            path.chmod(0o755)
        function = function.replace("/usr/bin/id", str(identity)).replace("/usr/bin/sudo", str(sudo))
        function = function.replace("$PLEBIAN_OS_SBINDIR/" + HELPER.name, str(helper))
        result = subprocess.run(["bash", "-eu", "-c", function + "\nrun_encodec_converter_installer"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertEqual(calls.read_text(), "elevated\n")
        # The production update executes this required step after dependency refresh.
        main = source[source.index("# Capture the complete old runtime boundary"):]
        self.assertLess(main.index("refresh_os_dependencies"), main.index("run_encodec_converter_installer"))

    def test_helper_is_delivered_in_image_and_upgrade(self):
        for relative in ("build/remaster-iso.sh",
                         "provision/plebian-os-provision.sh", "provision/plebian-os-update.sh"):
            self.assertIn(HELPER.name, (ROOT / relative).read_text(), relative)
        preseed = (ROOT / "preseed/preseed.cfg").read_text()
        self.assertNotIn("cp /cdrom/plebian-os/" + HELPER.name, preseed)
        installed = preseed.split(
            "in-target apt-get install -y --no-install-recommends", 1
        )[1].split(";", 1)[0]
        self.assertIn("plebian-os-tools", installed)


if __name__ == "__main__":
    unittest.main()
