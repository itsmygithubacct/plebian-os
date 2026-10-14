import io
import os
from pathlib import Path
import runpy
import tarfile
import tempfile
import unittest
from unittest import mock
import subprocess

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "provision/plebian-os-install-diarization-converter"


class DiarizationConverterInstallerTests(unittest.TestCase):
    def setUp(self):
        self.ns = runpy.run_path(str(HELPER))
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.destination = Path(self.temp.name)

    def archive(self, extra=()):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as archive:
            for name in ("bin/kilix-diarization-convert", "python/bin/python3.12", "tool.json"):
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
        self.assertEqual((self.destination / "tool.json").read_bytes(), b"test")
        self.assertEqual((self.destination / "tool.json").stat().st_mode & 0o7777, 0o755)

    def test_private_root_umask_does_not_hide_installed_software(self):
        previous = os.umask(0o077)
        try:
            self.ns["extract_payload"](self.archive(), self.destination)
        finally:
            os.umask(previous)
        self.assertEqual((self.destination / "python/bin").stat().st_mode & 0o777, 0o755)

    def test_rejects_escape_links_devices_and_duplicate_members(self):
        for name, kind in (("../escape", tarfile.REGTYPE), ("/absolute", tarfile.REGTYPE),
                           ("link", tarfile.SYMTYPE), ("hardlink", tarfile.LNKTYPE),
                           ("device", tarfile.CHRTYPE), ("tool.json", tarfile.REGTYPE)):
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

    def test_missing_openmp_dependency_fails_before_filesystem_changes(self):
        main = self.ns["main"]
        with mock.patch("sys.argv", [str(HELPER)]), \
                mock.patch("os.geteuid", return_value=0), \
                mock.patch("platform.machine", return_value="x86_64"), \
                mock.patch("subprocess.run", return_value=subprocess.CompletedProcess([], 1, "", "")), \
                mock.patch.dict(main.__globals__, {"secure_directory": mock.Mock(side_effect=AssertionError("filesystem mutated"))}):
            with self.assertRaisesRegex(ValueError, "libgomp1"):
                main()

    def test_helper_is_delivered_in_image_and_upgrade(self):
        for relative in ("build/remaster-iso.sh", "preseed/preseed.cfg",
                         "provision/plebian-os-provision.sh", "provision/plebian-os-update.sh"):
            self.assertIn(HELPER.name, (ROOT / relative).read_text(), relative)


if __name__ == "__main__":
    unittest.main()
