"""The no-weights checks see every carrier model, by executing them.

Seat 1 (0.2.2 RC3): the provisioning census and the guest check knew only the
Vosk small model, so a planted VibeVoice directory passed both, and AC-8 only
searched the source. These run the real census function and the real guest
check against planted trees.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build"))

import build_vm_image  # noqa: E402
PROVISION = ROOT / "provision" / "plebian-os-provision.sh"

PLANTED = (
    "voice/models/small-en-us",
    "voice/models/vosk-model-small-en-us-0.15-abc",
    "voice/models/lgraph-en-us",
    "voice/models/vibevoice-asr-bitnet",
    "voice/models/whisper-small-en",
    "desktop-apps/assets/vosk-model-small-en-us-0.15",
    "desktop-apps/assets/vosk-model-en-us-0.22-lgraph",
    "desktop-apps/assets/vibevoice-asr-bitnet",
    "desktop-apps/assets/faster-whisper-small-en",
    "voice/lib/current",
)


def census_function() -> str:
    source = PROVISION.read_text()
    start = source.index("voice_dictation_asset_paths() {")
    return source[start:source.index("\n}\n", start) + 3]


class CensusTests(unittest.TestCase):
    def census(self, data: Path) -> list[str]:
        result = subprocess.run(
            ["bash", "-c", census_function() + "voice_dictation_asset_paths"],
            env={"PATH": "/usr/bin:/bin", "KILIX_DATA_HOME": str(data)},
            capture_output=True, text=True, check=True)
        return result.stdout.split()

    def test_a_clean_machine_has_no_assets(self):
        with tempfile.TemporaryDirectory() as data:
            (Path(data) / "voice" / "models").mkdir(parents=True)
            self.assertEqual(self.census(Path(data)), [])

    def test_every_carrier_model_is_counted_wherever_it_lands(self):
        for relative in PLANTED:
            with self.subTest(path=relative), tempfile.TemporaryDirectory() as data:
                (Path(data) / relative).mkdir(parents=True)
                self.assertEqual(self.census(Path(data)), [str(Path(data) / relative)])


class GuestCheckTests(unittest.TestCase):
    def run_check(self, data: Path) -> int:
        record = data / "voice-install.record"
        record.write_text("libvosk=skipped\nmodel-small-en-us=skipped\n")
        env = {"PATH": "/usr/bin:/bin", "d": str(data),
               "m": str(data / "voice/models/small-en-us"),
               "l": str(data / "voice/lib/current"), "r": str(record)}
        script = 'd="$d"; m="$m"; l="$l"; r="$r"; ' + build_vm_image._no_speech_weights_check()
        return subprocess.run(["bash", "-c", script], env=env).returncode

    def test_a_clean_image_passes(self):
        with tempfile.TemporaryDirectory() as data:
            (Path(data) / "voice" / "models").mkdir(parents=True)
            self.assertEqual(self.run_check(Path(data)), 0)

    def test_every_carrier_model_fails_the_image(self):
        for relative in PLANTED:
            with self.subTest(path=relative), tempfile.TemporaryDirectory() as data:
                (Path(data) / "voice" / "models").mkdir(parents=True, exist_ok=True)
                (Path(data) / relative).mkdir(parents=True, exist_ok=True)
                self.assertNotEqual(self.run_check(Path(data)), 0)


if __name__ == "__main__":
    unittest.main()
