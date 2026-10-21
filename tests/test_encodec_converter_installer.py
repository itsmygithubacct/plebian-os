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

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "provision/plebian-os-install-encodec-converter"


class EncodecConverterInstallerTests(unittest.TestCase):
    def setUp(self):
        self.ns = runpy.run_path(str(HELPER))
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.destination = Path(self.temp.name)

    def archive(self, extra=()):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as archive:
            for name in ("bin/kilix-encodec-convert-24khz", ".converter/runtime.tar", ".converter/receipt.json", "bin/kilix-encodec-convert-48khz", ".converter-48khz/runtime.tar", ".converter-48khz/receipt.json", "BUILD.json", "source.tar.gz"):
                info = tarfile.TarInfo(name)
                info.size = 4
                info.mode = 0o7777  # Privileged/untrusted modes must not survive.
                archive.addfile(info, io.BytesIO(b"test"))
            for info in extra:
                archive.addfile(info, io.BytesIO(b"x" * info.size))
        stream.seek(0)
        return stream

    def test_extracts_ordinary_files_and_discards_privileged_modes(self):
        self.ns["extract_payload"](self.archive(), self.destination)
        self.assertEqual((self.destination / "BUILD.json").read_bytes(), b"test")
        self.assertEqual((self.destination / "BUILD.json").stat().st_mode & 0o7777, 0o755)

    def test_private_root_umask_does_not_hide_installed_software(self):
        previous = os.umask(0o077)
        try:
            self.ns["extract_payload"](self.archive(), self.destination)
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
                    self.ns["extract_payload"](self.archive((info,)), Path(directory))

    def test_unpacked_limit_is_enforced_before_copy(self):
        extract = self.ns["extract_payload"]
        extract.__globals__["MAX_UNPACKED_BYTES"] = 3
        with self.assertRaisesRegex(ValueError, "extraction bound"):
            extract(self.archive(), self.destination)

    def test_rejects_modified_archive(self):
        archive = self.destination / "archive"
        archive.write_bytes(b"bad")
        verify = self.ns["verify_archive"]
        verify.__globals__["ARCHIVE_SIZE"] = 3
        verify.__globals__["ARCHIVE_SHA256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            verify(archive)

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

    def test_fresh_provision_installs_and_runs_required_software(self):
        source = (ROOT / "provision/plebian-os-provision.sh").read_text()
        start = source.index('ENCODEC_CONVERTER_INSTALLER_SRC=""')
        end = source.index("# Ship only the small source-closure installer", start)
        block = source[start:end]
        helper = self.destination / HELPER.name
        installed = self.destination / "installed-helper"
        calls = self.destination / "calls"
        # Redirect absolute deployment paths only inside this real shell block.
        block = block.replace("/usr/local/sbin/" + HELPER.name, str(installed))
        helper.write_text("#!/bin/sh\necho invoked >> " + shlex.quote(str(calls)) + "\nexit 0\n")
        helper.chmod(0o755)
        prelude = ('set -eu\nlog() { :; }\ndie() { echo "$*" >&2; exit 1; }\n'
                   + "SELF_DIR=" + shlex.quote(str(self.destination)) + "\n")
        for dry_run in (1, 0):
            result = subprocess.run(["bash", "-c", prelude + f"DRY_RUN={dry_run}\n" + block],
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(calls.exists(), not dry_run)
        self.assertEqual(calls.read_text(), "invoked\n")
        helper.write_text("#!/bin/sh\nexit 7\n")
        result = subprocess.run(["bash", "-c", prelude + "DRY_RUN=0\n" + block],
                                text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("required EnCodec converter installation failed", result.stderr)

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
        helper.write_text("#!/bin/sh\nexit 7\n")
        for path in (identity, sudo, helper):
            path.chmod(0o755)
        function = function.replace("/usr/bin/id", str(identity)).replace("/usr/bin/sudo", str(sudo))
        function = function.replace("/usr/local/sbin/" + HELPER.name, str(helper))
        result = subprocess.run(["bash", "-eu", "-c", function + "\nrun_encodec_converter_installer"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertEqual(calls.read_text(), "elevated\n")
        # The production update executes this required step after dependency refresh.
        main = source[source.index("# Capture the complete old runtime boundary"):]
        self.assertLess(main.index("refresh_os_dependencies"), main.index("run_encodec_converter_installer"))

    def test_helper_is_delivered_in_image_and_upgrade(self):
        for relative in ("build/remaster-iso.sh", "preseed/preseed.cfg",
                         "provision/plebian-os-provision.sh", "provision/plebian-os-update.sh"):
            self.assertIn(HELPER.name, (ROOT / relative).read_text(), relative)


if __name__ == "__main__":
    unittest.main()
