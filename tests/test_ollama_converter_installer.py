import hashlib
import runpy
import subprocess
import unittest
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "provision" / "plebian-os-install-ollama-converter"


class OllamaConverterInstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.namespace = runpy.run_path(str(INSTALLER))
        cls.source = INSTALLER.read_text()

    def test_dry_run_is_non_privileged_and_exact(self):
        result = subprocess.run(
            ["python3", str(INSTALLER), "--dry-run"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("optional; no model weights", result.stdout)
        self.assertIn(str(self.namespace["ARCHIVE_SIZE"]), result.stdout)
        self.assertIn(self.namespace["ARCHIVE_SHA256"], result.stdout)
        self.assertIn(
            "/usr/lib/plebian-os/ollama/pocket-tts-convert-hf-to-gguf",
            result.stdout,
        )
        for package, version in self.namespace["PACKAGE_VERSIONS"].items():
            self.assertIn(f"{package}={version}", result.stdout)

    def test_source_archive_and_selected_tree_are_pinned(self):
        self.assertEqual(self.namespace["ARCHIVE_SIZE"], 36_889_653)
        self.assertEqual(
            self.namespace["ARCHIVE_SHA256"],
            "8759ab3d3a92d86ba3ba24fab7e6adde08eaf2f941e6c79118373e4f41e0af8c",
        )
        self.assertEqual(self.namespace["CONVERTER_TREE_FILES"], 116)
        self.assertEqual(
            self.namespace["CONVERTER_TREE_SHA256"],
            "fb562f74847e9ecde49e1b16b190c6f4f9a40cd22a4e612361f5f3b36ba8a0ba",
        )
        self.assertEqual(
            hashlib.sha256(self.namespace["STUB_SOURCE"].encode()).hexdigest(),
            "9d0e1fa1ae5de6285e58a2298aade8178341b11637e895701a6add0be47bb0db",
        )

    def test_archive_selector_has_a_narrow_allowlist(self):
        select = self.namespace["selected_member_path"]
        root = self.namespace["ARCHIVE_ROOT"]
        self.assertEqual(
            select(f"{root}/convert_hf_to_gguf.py"),
            PurePosixPath("convert_hf_to_gguf.py"),
        )
        self.assertEqual(
            select(f"{root}/conversion/pockettts.py"),
            PurePosixPath("conversion/pockettts.py"),
        )
        self.assertEqual(
            select(f"{root}/gguf-py/gguf/__init__.py"),
            PurePosixPath("gguf-py/gguf/__init__.py"),
        )
        self.assertIsNone(select(f"{root}/examples/server/server.cpp"))
        with self.assertRaises(self.namespace["InstallFailure"]):
            select(f"{root}/conversion/../../etc/shadow")

    def test_runner_is_offline_and_admits_only_the_two_pocket_outputs(self):
        runner = self.namespace["RUNNER_SOURCE"]
        compile(runner, "runner.py", "exec")
        self.assertIn('"HF_HUB_OFFLINE": "1"', runner)
        self.assertIn('"TRANSFORMERS_OFFLINE": "1"', runner)
        self.assertIn("expected SOURCE --outtype q8_0 --outfile OUTPUT [--mmproj]", runner)
        self.assertIn("pocket-tts-english-q8_0.gguf", runner)
        self.assertIn("mmproj-pocket-tts-english-q8_0.gguf", runner)
        self.assertIn("validate_packages()", runner)
        self.assertIn("validate_tree()", runner)

    def test_installer_contains_source_code_url_but_no_model_url(self):
        self.assertIn("github.com/ggml-org/llama.cpp/archive/", self.source)
        self.assertNotIn("huggingface.co", self.source.lower())
        self.assertNotIn("hf.co/", self.source.lower())
        self.assertIn("No model weights", self.namespace["NOTICE_SOURCE"])

    def test_helper_is_present_on_every_os_layer_path(self):
        expected = "plebian-os-install-ollama-converter"
        for relative in (
            "build/remaster-iso.sh",
            "preseed/preseed.cfg",
            "provision/plebian-os-provision.sh",
            "provision/plebian-os-update.sh",
        ):
            self.assertIn(expected, (ROOT / relative).read_text(), relative)

    def test_repository_carries_no_model_artifact(self):
        forbidden = {".gguf", ".safetensors", ".pt", ".pth", ".ckpt", ".onnx"}
        offenders = [
            path.relative_to(ROOT)
            for path in ROOT.rglob("*")
            if path.is_file() and path.suffix.lower() in forbidden
        ]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
