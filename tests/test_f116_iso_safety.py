import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build"))

import build_vm_image as vm
from test_build_vm_image import cfg


class F116IsoSafetyTests(unittest.TestCase):
    def test_vm_default_is_isolated_under_acceptance_artifacts(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(
            os.environ, {"PLEBIAN_OS_ARTIFACTS": td}, clear=False
        ):
            self.assertEqual(vm.acceptance_artifacts_dir(), Path(td) / "acceptance")

    def test_unattended_build_writes_directory_and_exact_sibling_warnings(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "plebian-os-ci.iso"
            seed = Path(td) / "preseed.cfg"
            seed.write_text("seed\n")

            def fake_run(_argv, **_kwargs):
                out.write_bytes(b"iso")

            with mock.patch.object(vm, "run", side_effect=fake_run):
                vm.build_iso(cfg(), seed, out, False)

            directory_warning, sibling_warning = vm.unattended_warning_paths(out)
            self.assertTrue(directory_warning.is_file())
            self.assertTrue(sibling_warning.is_file())
            self.assertIn(vm.UNATTENDED_WARNING, directory_warning.read_text())
            self.assertIn(out.name, sibling_warning.read_text())
            self.assertIn(vm.UNATTENDED_VOLUME_ID, sibling_warning.read_text())

    def test_warning_writer_refuses_a_symlink_substitution(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "candidate.iso"
            victim = Path(td) / "victim"
            victim.write_text("preserve me\n")
            _directory_warning, sibling_warning = vm.unattended_warning_paths(out)
            sibling_warning.symlink_to(victim)
            with self.assertRaises(SystemExit):
                vm.write_unattended_media_warnings(out)
            self.assertEqual(victim.read_text(), "preserve me\n")

    def test_automated_summary_warns_and_interactive_summary_does_not(self):
        automated = io.StringIO()
        with contextlib.redirect_stdout(automated):
            vm.final_summary(cfg(interactive_installer=False), Path("test.iso"))
        self.assertIn(vm.UNATTENDED_WARNING, automated.getvalue())

        interactive = io.StringIO()
        with contextlib.redirect_stdout(interactive):
            vm.final_summary(cfg(interactive_installer=True), Path("release.iso"))
        self.assertNotIn(vm.UNATTENDED_WARNING, interactive.getvalue())

    def test_remaster_assigns_distinct_release_and_unattended_volume_ids(self):
        source = (ROOT / "build" / "remaster-iso.sh").read_text()
        self.assertIn('[ "${PLEBIAN_OS_UNATTENDED_DISK:-0}" = 1 ]', source)
        self.assertIn('PLEBIAN_OS_ISO_VOLUME_ID="PLEBIAN-TEST-ERASES-DISK"', source)
        self.assertIn(
            'PLEBIAN_OS_ISO_VOLUME_ID="PLEBIAN-OS $PLEBIAN_OS_VERSION AMD64"',
            source,
        )

    def test_documentation_names_both_media_classes_and_the_durable_warning(self):
        vm_guide = (ROOT / "build" / "build_vm_image.md").read_text()
        readme = (ROOT / "README.md").read_text()
        releasing = (ROOT / "RELEASING.md").read_text()
        for text in (vm_guide, readme, releasing):
            self.assertIn("PLEBIAN-TEST-ERASES-DISK", text)
            self.assertIn("real hardware", text)
        self.assertIn("Which ISO do you want?", vm_guide)
        self.assertIn("artifacts/acceptance/", readme)


if __name__ == "__main__":
    unittest.main()
