import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build"))
import build_vm_image as vm  # noqa: E402


class VoiceAcceptanceTests(unittest.TestCase):
    def test_read_aloud_policy_requires_the_skipped_dictation_stamp(self):
        command = vm._voice_acceptance_command("0")
        self.assertIn('PLEBIAN_OS_INSTALL_VOICE_MODEL:-0', command)
        self.assertIn('test -x "$HOME/.local/bin/kilix-tts"', command)
        self.assertIn("libvosk=skipped", command)
        self.assertIn("model-small-en-us=skipped", command)
        self.assertNotIn("lib/current/libvosk.so", command)

    def test_dictation_policy_requires_verified_runtime_artifacts(self):
        command = vm._voice_acceptance_command("1")
        self.assertIn("voice/lib/current/libvosk.so", command)
        self.assertIn("voice/models/small-en-us", command)
        self.assertIn("[0-9a-f]{64}", command)
        self.assertNotIn("libvosk=skipped", command)

    def test_unknown_voice_policy_is_rejected(self):
        with self.assertRaises(ValueError):
            vm._voice_acceptance_command("yes")


if __name__ == "__main__":
    unittest.main()
