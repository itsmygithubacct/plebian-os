"""Static and refusal controls for F109's operator-run VM qualification lane."""

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "build" / "acceptance-release-hop.sh"
RELEASING = ROOT / "RELEASING.md"


class F109ReleaseHopAcceptanceRunnerTests(unittest.TestCase):
    def test_runner_exposes_both_required_shapes_and_exact_hop(self):
        source = RUNNER.read_text()
        for token in (
            "--shape image|standalone",
            'case "$shape" in image|standalone)',
            '"$pleb_bin" update --to "$target" --yes --no-restart',
            "PLEBIAN_OS_SELECT_TEST_FAIL_AFTER",
            "home-before.tsv",
            "home-after-failure.tsv",
            "home-after-success.tsv",
            "MANIFEST.sha256",
            'test ! -e /etc/pleb/session.env',
            'test ! -e "$source_home/plebian-os"',
            'test ! -e /usr/local/bin/plebian-os-update',
            '"installed-pleb-entrypoint-is-tested"',
            '"entrypoint-matches-participating-pleb-checkout"',
            '${GPU_TERMINAL_HOME:-$HOME/.local/gpu_terminal}',
            '"successful_hop_command_denominator": 1',
        ):
            self.assertIn(token, source)

    def test_help_is_non_mutating_and_documents_the_guest_boundary(self):
        result = subprocess.run(
            [str(RUNNER), "--help"], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--disposable-vm", result.stdout)
        self.assertIn("outside", result.stdout)

    def test_runner_refuses_before_creating_a_report_without_vm_consent(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report"
            result = subprocess.run(
                [
                    str(RUNNER),
                    "--shape", "standalone",
                    "--target", "0.2.1",
                    "--report", str(report),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("without --disposable-vm", result.stderr)
            self.assertFalse(report.exists())

    def test_release_procedure_invokes_both_runner_shapes(self):
        text = RELEASING.read_text()
        image = "acceptance-release-hop.sh --shape image --target <x.y.z>"
        standalone = (
            "acceptance-release-hop.sh --shape standalone --target <x.y.z>"
        )
        self.assertEqual(text.count(image), 1)
        self.assertEqual(text.count(standalone), 1)
        self.assertIn("Retain all 2/2", text)


if __name__ == "__main__":
    unittest.main()
