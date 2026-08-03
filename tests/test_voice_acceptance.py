import subprocess
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
        for tool in ("kilix-tts", "kilix-stt", "kilix-voiced"):
            self.assertIn(tool, command)
        self.assertIn('--version', command)
        self.assertIn('kilix-tts" --print', command)
        self.assertIn('kilix-stt" --print', command)
        self.assertIn("libvosk=skipped", command)
        self.assertIn("model-small-en-us=skipped", command)
        self.assertNotIn("lib/current/libvosk.so", command)

    def test_dictation_policy_requires_verified_runtime_artifacts(self):
        command = vm._voice_acceptance_command("1")
        self.assertIn('l="$d/voice/lib/current"', command)
        self.assertIn('m="$d/voice/models/small-en-us"', command)
        self.assertIn('$l/libvosk.so', command)
        self.assertIn('readlink -- "$l"', command)
        self.assertIn(
            'vosk-$KILIX_VOICE_LIB_VERSION-$KILIX_VOICE_LIB_SHA256', command
        )
        self.assertIn('readlink -- "$m"', command)
        self.assertIn(
            'vosk-model-small-en-us-0.15-$KILIX_VOICE_MODEL_SHA256', command
        )
        self.assertIn('KILIX_VOICE_LIB_URL', command)
        self.assertIn('KILIX_VOICE_MODEL_URL', command)
        self.assertIn('kilix-voice=$KILIX_VOICE_REF', command)
        self.assertIn(
            'libvosk=$KILIX_VOICE_LIB_VERSION+$KILIX_VOICE_LIB_SHA256',
            command,
        )
        self.assertIn(
            'model-small-en-us=$KILIX_VOICE_MODEL_SHA256', command
        )
        self.assertIn("README.kilix-provenance", command)
        self.assertIn("LICENSE.Apache-2.0", command)
        self.assertIn("/usr/share/common-licenses/Apache-2.0", command)
        self.assertIn("Upstream: https://github.com/alphacep/vosk-api", command)
        self.assertIn(
            "Upstream catalog: https://alphacephei.com/vosk/models", command
        )
        self.assertIn("Extracted member: vosk/libvosk.so", command)
        self.assertIn("Archive directory: vosk-model-small-en-us-0.15", command)
        self.assertIn("/etc/plebian-os/build-info.env", command)
        self.assertIn("dictation=ready", command)
        self.assertIn("EspeakTts", command)
        self.assertIn("VoskStt", command)
        self.assertIn("lib_path=library_path", command)
        self.assertIn("model_path=model_path", command)
        self.assertIn('os.environ["KILIX_DATA_HOME"]', command)
        self.assertIn("recognizer.lib_path", command)
        self.assertIn("recognizer.model_path", command)
        self.assertIn("kilix voice is working", command)
        self.assertIn("start_utterance", command)
        self.assertIn("end_utterance", command)
        self.assertIn("recognized", command)
        self.assertIn('KILIX_DATA_HOME="$d" PYTHONPATH=', command)
        self.assertNotIn("libvosk=skipped", command)

    def test_unknown_voice_policy_is_rejected(self):
        with self.assertRaises(ValueError):
            vm._voice_acceptance_command("yes")

    def test_dictation_acceptance_is_one_valid_fail_closed_shell_chain(self):
        command = vm._voice_acceptance_command("1")
        self.assertEqual(command.count("dictation=ready"), 1)
        self.assertIn("= 1 && for tool", command)
        self.assertIn("done && timeout", command)
        self.assertIn(
            "dictation=ready' && KILIX_DATA_HOME=\"$d\" PYTHONPATH=",
            command,
        )
        syntax = subprocess.run(
            ["bash", "-n", "-c", command],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr)


if __name__ == "__main__":
    unittest.main()
