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


class VoiceReleaseContractTests(unittest.TestCase):
    def test_unpinned_install_defaults_to_read_aloud_only(self):
        remaster = (ROOT / "build" / "remaster-iso.sh").read_text()
        provision = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
        update = (ROOT / "provision" / "plebian-os-update.sh").read_text()
        self.assertEqual(
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
                    values.get("KILIX_VOICE_LIB_VERSION", ""),
                    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$",
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


if __name__ == "__main__":
    unittest.main()
