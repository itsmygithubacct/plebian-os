import hashlib
import os
from pathlib import Path, PurePosixPath
import runpy
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "provision" / "plebian-os-install-kilix-vulkan-tts"


class KilixVulkanTtsInstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.namespace = runpy.run_path(str(INSTALLER))
        cls.source = INSTALLER.read_text(encoding="utf-8")

    def test_dry_run_is_non_privileged_exact_and_weight_free(self):
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
        self.assertIn(self.namespace["WORKER_SOURCE_SHA256"], result.stdout)
        self.assertIn("may take several minutes", result.stdout)
        self.assertIn(
            "/usr/lib/plebian-os/ollama/kilix-tts-worker-current",
            result.stdout,
        )
        for package, version in self.namespace["PACKAGE_VERSIONS"].items():
            self.assertIn(f"{package}={version}", result.stdout)

    def test_archive_and_worker_source_are_exactly_pinned(self):
        self.assertEqual(self.namespace["ARCHIVE_SIZE"], 36_889_653)
        self.assertEqual(self.namespace["ARCHIVE_MEMBERS"], 3_791)
        self.assertEqual(
            self.namespace["ARCHIVE_SHA256"],
            "8759ab3d3a92d86ba3ba24fab7e6adde08eaf2f941e6c79118373e4f41e0af8c",
        )
        worker = self.namespace["WORKER_SOURCE"].encode("utf-8")
        self.assertEqual(len(worker), 11_585)
        self.assertEqual(
            hashlib.sha256(worker).hexdigest(),
            self.namespace["WORKER_SOURCE_SHA256"],
        )
        self.assertIn(
            "READY = {'K', 'I', 'L', 'I', 'X', 'T', '1', '\\n'}",
            self.namespace["WORKER_SOURCE"],
        )
        self.assertIn("MAX_TEXT_BYTES = 4096", self.namespace["WORKER_SOURCE"])
        self.assertNotIn("http://", self.namespace["WORKER_SOURCE"])
        self.assertNotIn("https://", self.namespace["WORKER_SOURCE"])

    def test_archive_paths_are_confined_to_the_pinned_root(self):
        select = self.namespace["archive_member_path"]
        root = self.namespace["ARCHIVE_ROOT"]
        self.assertEqual(
            select(f"{root}/tools/mtmd/clip.cpp"),
            PurePosixPath("tools/mtmd/clip.cpp"),
        )
        for unsafe in (
            f"{root}/../../etc/shadow",
            "/etc/shadow",
            "different-root/file",
        ):
            with self.subTest(unsafe=unsafe), self.assertRaises(
                self.namespace["InstallFailure"]
            ):
                select(unsafe)

    def test_build_is_fixed_offline_portable_and_origin_relative(self):
        work = Path("/var/lib/plebian-os/session/fixture")
        configure = self.namespace["cmake_arguments"](work)
        compiler = self.namespace["compiler_arguments"](work)
        joined = "\n".join(configure)
        self.assertIn("-DGGML_VULKAN=ON", configure)
        self.assertIn("-DGGML_BACKEND_DL=ON", configure)
        self.assertIn("-DGGML_NATIVE=OFF", configure)
        self.assertIn("-DGGML_OPENMP=OFF", configure)
        self.assertIn("-DLLAMA_CURL=OFF", configure)
        self.assertIn("-DLLAMA_OPENSSL=OFF", configure)
        self.assertIn("-DFETCHCONTENT_FULLY_DISCONNECTED=ON", configure)
        self.assertIn("-DCMAKE_BUILD_RPATH=$ORIGIN", configure)
        self.assertIn("-DCMAKE_BUILD_WITH_INSTALL_RPATH=ON", configure)
        self.assertIn("/usr/src/kilix-vulkan-tts-r1", joined)
        self.assertIn("-Wl,-rpath,$ORIGIN", compiler)
        self.assertEqual(compiler[0], "/usr/bin/g++")
        self.assertNotIn("-march=native", configure + compiler)

    def test_runtime_output_closure_is_small_and_complete(self):
        outputs = self.namespace["RUNTIME_OUTPUTS"]
        self.assertEqual(
            set(outputs),
            {
                "kilix-tts-worker",
                "libggml-base.so.0",
                "libggml-cpu.so",
                "libggml-vulkan.so",
                "libggml.so.0",
                "libllama-common.so.0",
                "libllama.so.0",
                "libmtmd.so.0",
            },
        )
        self.assertEqual(sum(item[1] for item in outputs.values()), 66_532_472)
        for _name, (_source, size, digest) in outputs.items():
            self.assertGreater(size, 0)
            self.assertRegex(digest, r"^[0-9a-f]{64}$")
        self.assertNotIn("llama-tts", outputs)

    def test_helper_is_present_on_every_os_layer_path(self):
        expected = "plebian-os-install-kilix-vulkan-tts"
        for relative in (
            "build/remaster-iso.sh",
            "preseed/preseed.cfg",
            "provision/plebian-os-provision.sh",
            "provision/plebian-os-update.sh",
        ):
            self.assertIn(expected, (ROOT / relative).read_text(), relative)

    def test_file_verifier_rejects_symlinks_and_wrong_mode(self):
        verify = self.namespace["verified_file_digest"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = b"fixture"
            regular = root / "regular"
            regular.write_bytes(payload)
            regular.chmod(0o600)
            digest = hashlib.sha256(payload).hexdigest()
            verify(
                regular,
                expected_size=len(payload),
                expected_hash=digest,
                expected_owner=os.getuid(),
                expected_mode=0o600,
            )
            with self.assertRaises(self.namespace["InstallFailure"]):
                verify(
                    regular,
                    expected_size=len(payload),
                    expected_hash=digest,
                    expected_owner=os.getuid(),
                    expected_mode=0o644,
                )
            link = root / "link"
            link.symlink_to(regular)
            with self.assertRaises(self.namespace["InstallFailure"]):
                verify(
                    link,
                    expected_size=len(payload),
                    expected_hash=digest,
                    expected_owner=os.getuid(),
                    expected_mode=0o600,
                )

    def test_exclusive_writer_honors_mode_under_private_umask(self):
        write = self.namespace["write_exclusive"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "payload"
            previous = os.umask(0o077)
            try:
                write(path, b"payload", 0o644)
            finally:
                os.umask(previous)
            self.assertEqual(path.stat().st_mode & 0o777, 0o644)

    def test_installer_contains_no_runtime_or_model_payload(self):
        self.assertLess(INSTALLER.stat().st_size, 100_000)
        self.assertNotIn("pocket-tts-english-q8_0.gguf", self.source)
        self.assertNotIn("model.safetensors", self.source)
        self.assertNotIn("generated audio", self.namespace["WORKER_SOURCE"])


if __name__ == "__main__":
    unittest.main()
