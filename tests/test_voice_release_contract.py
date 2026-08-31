import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _manifest(path):
    values = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def _voice_validator_source():
    source = (ROOT / "build" / "remaster-iso.sh").read_text(
        encoding="utf-8"
    )
    start = source.index("is_hex_len() {")
    end = source.index("validate_waydroid_release_closure() {")
    return source[start:end]


def _full_voice_closure():
    return {
        "PLEBIAN_OS_INSTALL_VOICE_MODEL": "1",
        "KILIX_VOICE_REF": "1" * 40,
        "KILIX_VOICE_LIB_VERSION": "1.0.0",
        "KILIX_VOICE_LIB_URL": "https://example.invalid/lib.tar.gz",
        "KILIX_VOICE_LIB_SHA256": "a" * 64,
        "KILIX_VOICE_MODEL_URL": "https://example.invalid/model.bin",
        "KILIX_VOICE_MODEL_SHA256": "b" * 64,
    }


class VoiceReleaseContractTests(unittest.TestCase):
    def run_voice_validator(self, **settings):
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
        env.update(settings)
        return subprocess.run(
            [
                "bash",
                "-c",
                "set -u\n" + _voice_validator_source()
                + "\nvalidate_voice_release_closure",
            ],
            env=env,
            text=True,
            capture_output=True,
        )

    def test_0_2_1_release_keeps_the_model_free_leg_open(self):
        result = self.run_voice_validator(
            PLEBIAN_OS_RELEASE_MODE="1",
            PLEBIAN_OS_VERSION="0.2.1",
            PLEBIAN_OS_INSTALL_VOICE_MODEL="0",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")

    def test_0_2_1_release_manifest_is_explicitly_model_free(self):
        values = _manifest(ROOT / "releases" / "0.2.1.env")
        self.assertEqual(values["PLEBIAN_OS_INSTALL_VOICE_MODEL"], "0")

    def test_0_2_1_release_refuses_legacy_pins_without_a_carrier(self):
        settings = _full_voice_closure()
        settings.update(
            PLEBIAN_OS_RELEASE_MODE="1",
            PLEBIAN_OS_VERSION="0.2.1",
        )
        result = self.run_voice_validator(**settings)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            result.stderr,
            "Plebian-OS 0.2.1 release mode refuses "
            "PLEBIAN_OS_INSTALL_VOICE_MODEL=1 until an accepted F100 "
            "compliance-carrier interface and receipt are present\n",
        )

    def test_nonrelease_voice_development_retains_legacy_pin_validation(self):
        settings = _full_voice_closure()
        settings.update(
            PLEBIAN_OS_RELEASE_MODE="0",
            PLEBIAN_OS_VERSION="0.2.1",
        )
        result = self.run_voice_validator(**settings)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_future_release_voice_closure_fails_closed_without_a_carrier(self):
        settings = _full_voice_closure()
        settings.update(
            PLEBIAN_OS_RELEASE_MODE="1",
            PLEBIAN_OS_VERSION="0.2.2",
        )
        result = self.run_voice_validator(**settings)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            result.stderr,
            "Plebian-OS 0.2.2 release mode refuses "
            "PLEBIAN_OS_INSTALL_VOICE_MODEL=1 until an accepted F100 "
            "compliance-carrier interface and receipt are present\n",
        )

    def test_historical_release_voice_closure_is_unchanged(self):
        settings = _full_voice_closure()
        settings.update(
            PLEBIAN_OS_RELEASE_MODE="1",
            PLEBIAN_OS_VERSION="0.1.7",
        )
        result = self.run_voice_validator(**settings)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unpinned_install_defaults_to_read_aloud_only(self):
        remaster = (ROOT / "build" / "remaster-iso.sh").read_text()
        provision = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
        update = (ROOT / "provision" / "plebian-os-update.sh").read_text()
        self.assertGreaterEqual(
            remaster.count('${PLEBIAN_OS_INSTALL_VOICE_MODEL:-0}'), 2)
        self.assertNotIn('${PLEBIAN_OS_INSTALL_VOICE_MODEL:-1}', remaster)
        self.assertIn('${PLEBIAN_OS_INSTALL_VOICE_MODEL:-0}', provision)
        self.assertIn('${PLEBIAN_OS_INSTALL_VOICE_MODEL:-0}', update)

    def test_release_manifests_use_the_runtime_checksum_names(self):
        for path in sorted((ROOT / "releases").glob("*.env")):
            text = path.read_text(encoding="utf-8")
            with self.subTest(manifest=path.name):
                self.assertNotRegex(
                    text, r"(?m)^KILIX_VOICE_(?:LIB|MODEL)_SHA=")

    def test_dictation_policy_requires_a_complete_explicit_closure(self):
        for path in sorted((ROOT / "releases").glob("*.env")):
            values = _manifest(path)
            if values.get("PLEBIAN_OS_INSTALL_VOICE_MODEL") != "1":
                continue
            with self.subTest(manifest=path.name):
                self.assertRegex(
                    values.get("KILIX_VOICE_REF", ""), r"^[0-9a-f]{40}$"
                )
                self.assertRegex(
                    values.get("KILIX_VOICE_LIB_VERSION", ""),
                    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$",
                )
                self.assertRegex(
                    values.get("KILIX_VOICE_LIB_URL", ""), r"^https://"
                )
                self.assertRegex(
                    values.get("KILIX_VOICE_LIB_SHA256", ""),
                    r"^[0-9a-f]{64}$",
                )
                self.assertRegex(
                    values.get("KILIX_VOICE_MODEL_URL", ""), r"^https://")
                self.assertRegex(
                    values.get("KILIX_VOICE_MODEL_SHA256", ""),
                    r"^[0-9a-f]{64}$",
                )

    def test_0_1_7_pins_the_published_offline_dictation_closure(self):
        values = _manifest(ROOT / "releases" / "0.1.7.env")
        self.assertEqual(values["PLEBIAN_OS_INSTALL_VOICE_MODEL"], "1")
        self.assertEqual(
            values["KILIX_VOICE_REF"],
            "f05b64a7b2bc25fa9a7e2c3ae1e0b848f04a23f6",
        )
        self.assertEqual(values["KILIX_VOICE_LIB_VERSION"], "0.3.45")
        self.assertEqual(
            values["KILIX_VOICE_LIB_URL"],
            "https://files.pythonhosted.org/packages/fc/ca/83398cfcd557360a3d7b2d732aee1c5f6999f68618d1645f38d53e14c9ff/vosk-0.3.45-py3-none-manylinux_2_12_x86_64.manylinux2010_x86_64.whl",
        )
        self.assertEqual(
            values["KILIX_VOICE_LIB_SHA256"],
            "25e025093c4399d7278f543568ed8cc5460ac3a4bf48c23673ace1e25d26619f",
        )
        self.assertEqual(
            values["KILIX_VOICE_MODEL_URL"],
            "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
        )
        self.assertEqual(
            values["KILIX_VOICE_MODEL_SHA256"],
            "30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498",
        )

    def test_firstboot_runs_a_real_synthesis_recognition_smoke(self):
        provision = (
            ROOT / "provision" / "plebian-os-provision.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("run_voice_functional_smoke", provision)
        self.assertIn('EspeakTts(voice="en-us", rate=135)', provision)
        self.assertIn("lib_path=library_path", provision)
        self.assertIn("model_path=model_path", provision)
        self.assertIn('os.environ["KILIX_DATA_HOME"]', provision)
        self.assertIn("recognizer.lib_path", provision)
        self.assertIn("recognizer.model_path", provision)
        self.assertIn("kilix voice is working", provision)
        self.assertIn("recognizer.start_utterance()", provision)
        self.assertIn("recognizer.end_utterance().strip()", provision)


if __name__ == "__main__":
    unittest.main()
