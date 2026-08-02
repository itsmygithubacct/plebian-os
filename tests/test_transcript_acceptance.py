import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build"))
import build_vm_image as vm  # noqa: E402


class TranscriptAcceptanceTests(unittest.TestCase):
    def test_fresh_install_keeps_transcripts_within_the_disk_safe_budget(self):
        command = vm._transcript_acceptance_command()
        self.assertIn("GPU_TERMINAL_SETTINGS_FILE", command)
        self.assertIn("KILIX_TRANSCRIPT_MAX_TOTAL=5G", command)
        self.assertIn("KILIX_TRANSCRIPT_ARCHIVE_MAX_TOTAL=1G", command)
        self.assertIn('test ! -L "$f"', command)


if __name__ == "__main__":
    unittest.main()
