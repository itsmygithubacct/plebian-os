"""A model the release advertises as runnable really runs at the pinned refs.

Seat 2 (0.2.2 RC3): rolling KILIX_REF back to a Kilix with no VibeASR runtime
left every test green, so "runnable" was a claim nothing tied to the pins.
For each model the speech catalog marks runnable, the pinned kilix-voice must
mark it runtime-supported, and for VibeVoice the pinned Kilix must carry the
pinned runtime installer and the `kilix voice vibeasr` verb that builds it.
"""
import io
import json
import re
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

import test_model_compliance_carrier as carrier
import test_voice_release_contract as voice_contract

ROOT = Path(__file__).resolve().parents[1]


def show(repo: Path, commit: str, path: str) -> str | None:
    result = subprocess.run(["git", "-C", str(repo), "show", f"{commit}:{path}"],
                            capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else None


def patched_catalog(voice: Path, ref: str, patcher: str) -> str:
    """voicelib/models.py at ref after Kilix's medium patcher has run on it."""
    archive = subprocess.run(["git", "-C", str(voice), "archive", "--format=tar", ref, "voicelib"],
                             capture_output=True, check=True).stdout
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(root / "voice", filter="data")
        (root / "patch.py").write_text(patcher)
        subprocess.run([sys.executable, str(root / "patch.py"), str(root / "voice")],
                       capture_output=True, check=True)
        return (root / "voice" / "voicelib" / "models.py").read_text()


class RunnableModelTests(unittest.TestCase):
    def setUp(self):
        self.pins = carrier.manifest(f"{carrier.VERSION}.env")
        provision = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
        self.runnable = [name for name, runnable in carrier.advertised_models(provision)
                         if runnable]
        command = ROOT / "provision" / "command-model.json"
        self.command_model = (json.loads(command.read_bytes())["asset_id"]
                              if command.exists() else None)

    def test_the_pinned_voice_runs_every_runnable_model(self):
        voice = carrier.repo_holding("PLEBIAN_OS_KILIX_VOICE_REPO", "kilix-voice",
                                     self.pins["KILIX_VOICE_REF"])
        self.assertIsNotNone(voice, "no kilix-voice checkout holds KILIX_VOICE_REF; "
                             "set PLEBIAN_OS_KILIX_VOICE_REPO")
        catalog = show(voice, self.pins["KILIX_VOICE_REF"], "voicelib/models.py")
        # KILIX_REF's voice installer adds whisper-medium-en to the staged
        # library, so the catalog the release runs is the patched one.
        kilix = carrier.repo_holding("PLEBIAN_OS_KILIX_REPO", "kilix", self.pins["KILIX_REF"])
        self.assertIsNotNone(kilix, "no kilix checkout holds KILIX_REF; set PLEBIAN_OS_KILIX_REPO")
        patcher = show(kilix, self.pins["KILIX_REF"], "scripts/patch-whisper-medium-model.py")
        if patcher is not None:
            installer = show(kilix, self.pins["KILIX_REF"], "scripts/install-kilix-voice.sh")
            self.assertIn("patch-whisper-medium-model.py", installer)
            catalog = patched_catalog(voice, self.pins["KILIX_VOICE_REF"], patcher)
        for model in self.runnable:
            if model == "kilix-diarization-cpu":
                # Optional generic-catalog asset; the separate Transcribe
                # route below owns it, not the dictation model protocol.
                continue
            if model == self.command_model:
                # Needle runs the Ask command model, not kilix-voice. AC-8
                # (test_command_model_records_needle_serves_are_the_carried_ones)
                # ties it to the Needle the pinned catalog selects.
                continue
            with self.subTest(model=model):
                entry = re.search(rf'ModelSpec\(\s*"{re.escape(model)}",\s*\w+,\s*\d+,\s*(True|False),',
                                  catalog)
                self.assertIsNotNone(entry, f"{model} is not in the pinned voice catalog")
                self.assertEqual(entry.group(1), "True", f"{model} is not runnable at KILIX_VOICE_REF")

    def test_the_pinned_kilix_exposes_the_managed_diarization_route(self):
        self.assertIn("kilix-diarization-cpu", self.runnable)
        kilix = carrier.repo_holding("PLEBIAN_OS_KILIX_REPO", "kilix", self.pins["KILIX_REF"])
        self.assertIsNotNone(kilix, "no kilix checkout holds KILIX_REF")
        provider = show(kilix, self.pins["KILIX_REF"], "config/kilix_sdk/transcribe_provider.py")
        self.assertIsNotNone(provider, "KILIX_REF has no managed Transcribe provider")
        self.assertRegex(provider, r"(?m)^PROVIDER_REF = '[0-9a-f]{40}'$")
        self.assertIn("DIARIZATION_MODEL = 'kilix-diarization-cpu'", provider)
        self.assertIn("prep.add_argument('--diarization'", provider)
        self.assertIn('consumer_schema="kilix.transcribe.diarization-runtime"', provider)
        self.assertIn('DiarizationRuntime(root,model_source=diarization)', provider)

    def test_the_pinned_kilix_builds_the_vibevoice_runtime(self):
        self.assertIn("vibevoice-asr-bitnet", self.runnable)
        kilix = carrier.repo_holding("PLEBIAN_OS_KILIX_REPO", "kilix", self.pins["KILIX_REF"])
        self.assertIsNotNone(kilix, "no kilix checkout holds KILIX_REF; set PLEBIAN_OS_KILIX_REPO")
        installer = show(kilix, self.pins["KILIX_REF"], "scripts/install-kilix-vibeasr.sh")
        self.assertIsNotNone(installer, "KILIX_REF has no VibeASR runtime installer")
        self.assertRegex(installer, r"(?m)^KILIX_VIBEASR_REF=[0-9a-f]{40}$")
        launcher = show(kilix, self.pins["KILIX_REF"], "kilix")
        self.assertRegex(launcher, r"vibeasr\)\s*\n[^\n]*\n\s*exec \"\$KILIX_HOME/scripts/install-kilix-vibeasr.sh\"")
        voice_installer = show(kilix, self.pins["KILIX_REF"], "scripts/install-kilix-voice.sh")
        self.assertIn(f'KILIX_VOICE_REF:-{self.pins["KILIX_VOICE_REF"]}}}', voice_installer,
                      "KILIX_REF must install the same kilix-voice the release pins")


if __name__ == "__main__":
    unittest.main()
