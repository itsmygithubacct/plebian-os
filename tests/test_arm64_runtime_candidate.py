"""An unselected ARM input cannot become an accepted or foreign carrier."""

import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "arm64_runtime_candidate", ROOT / "build/verify-arm64-runtime-candidate.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ArmRuntimeCandidateTests(unittest.TestCase):
    def setUp(self):
        self.candidate = json.loads(
            (ROOT / "releases/0.2.2-arm64-runtime-candidate.json").read_text())

    def test_unselected_complete_metadata(self):
        module.validate_metadata(self.candidate)

    def test_missing_or_foreign_runtime_fields_refuse(self):
        mutations = (
            lambda c: c["voice"].pop("library_sha256"),
            lambda c: c["voice"].update(elf_machine=62),
            lambda c: c["voice"].update(url=c["voice"]["url"].replace("aarch64", "x86_64")),
            lambda c: c["upstream_kitty_fallback"].update(elf_machine=62),
            lambda c: c["upstream_kitty_fallback"].update(url="https://example.org/kitty-0.48.2-x86_64.txz"),
            lambda c: c.update(selection="selected"),
            lambda c: c["model_runtime_review"][0].update(arm64_runnable=True),
            lambda c: c["model_runtime_review"].pop(),
        )
        for mutate in mutations:
            candidate = copy.deepcopy(self.candidate)
            mutate(candidate)
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                module.validate_metadata(candidate)

    def test_amd64_selection_and_early_arm_refusal_unchanged(self):
        env = (ROOT / "releases/0.2.2.env").read_text()
        requirements = (ROOT / "releases/0.2.2.requirements").read_text()
        self.assertIn("KILIX_VOICE_LIB_URL=https://files.pythonhosted.org/", env)
        self.assertIn("manylinux2010_x86_64.whl", env)
        self.assertIn("KILIX_PREBUILT_SHA256=967a1958e7fc67b495d279c0963bcd1a0482097151817ce6506fabc822689af7", env)
        self.assertIn("PLEBIAN_OS_VOICE_CARRIER_DIR=releases/0.2.2-model-compliance", requirements)
        self.assertIn("PLEBIAN_OS_INSTALL_WAYDROID=1", requirements)
        for name, function in (("plebian-os-provision.sh", "refuse_amd64_only_inputs"),
                               ("plebian-os-update.sh", "refuse_amd64_only_stack_inputs")):
            source = (ROOT / "provision" / name).read_text()
            self.assertIn(f"{function}()", source)
            self.assertIn(f"\n{function}\n", source)
            self.assertIn("0.2.2 has no source-qualified ARM64 closure", source)


if __name__ == "__main__":
    unittest.main()
