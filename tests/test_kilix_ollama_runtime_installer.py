import hashlib
import os
from pathlib import Path, PurePosixPath
import runpy
import tarfile
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "provision" / "plebian-os-install-kilix-ollama-runtime"
LISTENER_PATCH = (
    ROOT
    / "provision"
    / "ollama"
    / "patches"
    / "0001-kilix-private-unix-listener.patch"
)


class KilixOllamaRuntimeInstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.namespace = runpy.run_path(str(INSTALLER))
        cls.source = INSTALLER.read_text(encoding="utf-8")

    def test_dry_run_is_small_local_only_and_weight_free(self):
        result = subprocess.run(
            ["python3", str(INSTALLER), "--dry-run"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no model weights", result.stdout)
        self.assertIn("installed-offline-0.2.2", result.stdout)
        self.assertIn("firmware-nvidia-graphics: not required", result.stdout)
        self.assertIn(self.namespace["UNIX_LISTENER_PATCH_SHA256"], result.stdout)
        self.assertIn("119645888", result.stdout)
        self.assertIn(
            "/usr/lib/plebian-os/ollama/ollama-current",
            result.stdout,
        )
        self.assertNotIn("http://", self.source)
        self.assertNotIn("https://", self.source)

    def test_exact_runtime_projection_is_metadata_only(self):
        files = self.namespace["RUNTIME_FILES"]
        self.assertEqual(len(files), 25)
        self.assertEqual(sum(item[0] for item in files.values()), 119_645_888)
        self.assertEqual(
            files[PurePosixPath("usr/bin/ollama")],
            (
                35_336_984,
                "63f9670532c81db5712420defb481732f55bcfdfa5f94b1b45cfb0739626cfbc",
            ),
        )
        self.assertIn(
            PurePosixPath("usr/lib/ollama/vulkan/libggml-vulkan.so"),
            files,
        )
        forbidden = (".gguf", ".safetensors", ".pt", ".pth", ".ckpt", ".onnx")
        self.assertFalse(any(str(path).endswith(forbidden) for path in files))
        self.assertLess(INSTALLER.stat().st_size, 64 * 1024)

    def test_listener_delta_is_exact_and_carries_tests(self):
        payload = LISTENER_PATCH.read_bytes()
        self.assertEqual(
            hashlib.sha256(payload).hexdigest(),
            self.namespace["UNIX_LISTENER_PATCH_SHA256"],
        )
        text = payload.decode("utf-8")
        self.assertIn("OLLAMA_KILIX_SOCKET", text)
        self.assertIn("TestListenKilixUnixRefusesUnsafePaths", text)
        self.assertIn("TestNoCloudServerCreatesNoRegistryIdentity", text)

    def test_runtime_links_are_relative_and_confined(self):
        links = self.namespace["RUNTIME_LINKS"]
        self.assertEqual(len(links), 10)
        for path, target in links.items():
            self.assertEqual(path.parts[:3], ("usr", "lib", "ollama"))
            self.assertNotIn("/", target)
            self.assertNotIn("..", PurePosixPath(target).parts)

    def test_notice_manifest_parser_rejects_traversal(self):
        parse = self.namespace["parse_notice_manifest"]
        lines = [f"{'0' * 64}  ./license-{index}" for index in range(80)]
        records = parse(("\n".join(lines) + "\n").encode("ascii"))
        self.assertEqual(len(records), 80)
        lines[7] = f"{'0' * 64}  ./../../etc/shadow"
        with self.assertRaises(self.namespace["InstallFailure"]):
            parse(("\n".join(lines) + "\n").encode("ascii"))

    def test_carrier_pin_verification_checks_size_and_digest(self):
        self.assertEqual(
            self.namespace["read_carrier_pin"](ROOT / "releases" / "0.2.2.env"),
            (
                20_689_764,
                "47cdb94ae64351242aee2e4391e87de1c7ff7f8cb579006b8dfd56353aaa6914",
            ),
        )
        payload = b"pinned offline carrier"
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "carrier.tar.xz"
            manifest = root / "0.2.2.env"
            archive.write_bytes(payload)
            manifest.write_text(
                "PLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_BYTES="
                f"{len(payload)}\n"
                "PLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_SHA256="
                f"{digest}\n",
                encoding="utf-8",
            )
            self.assertEqual(
                self.namespace["verify_carrier_archive"](archive, manifest),
                (len(payload), digest),
            )
            archive.write_bytes(b"x" * len(payload))
            with self.assertRaises(self.namespace["InstallFailure"]):
                self.namespace["verify_carrier_archive"](archive, manifest)

    def test_carrier_paths_reject_absolute_and_traversing_names(self):
        archive_path = self.namespace["archive_path"]
        directory = tarfile.TarInfo("./usr/")
        directory.type = tarfile.DIRTYPE
        self.assertEqual(archive_path(directory).as_posix(), "usr")
        for name in ("/etc/passwd", "./usr/../etc/passwd", "./usr//passwd"):
            with self.subTest(name=name), self.assertRaises(
                self.namespace["InstallFailure"]
            ):
                archive_path(tarfile.TarInfo(name))

    def test_service_unit_and_path_client_are_pinned(self):
        unit = self.namespace["SYSTEMD_UNIT_SOURCE"]
        for expected in (
            "User=ollama", "Group=ollama", "SupplementaryGroups=render video",
            "OLLAMA_HOST=127.0.0.1:11434",
            "OLLAMA_MODELS=/var/lib/ollama/models", "OLLAMA_NO_CLOUD=1",
            "OLLAMA_VULKAN=1", "NoNewPrivileges=true", "ProtectSystem=strict",
            "ProtectHome=true", "PrivateTmp=true", "ReadWritePaths=/var/lib/ollama",
            "Restart=on-failure",
        ):
            self.assertIn(expected, unit)
        self.assertIn(
            f"exec {self.namespace['GENERATION']}/usr/bin/ollama \"$@\"",
            self.namespace["PUBLIC_COMMAND_SOURCE"],
        )
        self.assertEqual(
            self.namespace["PUBLIC_NOTICE_ROOT"],
            Path("/usr/share/doc/ollama-runtime/notices"),
        )
        self.assertIn("sync_public_notices(repair=True)", self.source)
        self.assertIn("sync_public_notices(repair=False)", self.source)

    def test_carrier_is_verified_staged_and_installed_after_base_packages(self):
        remaster = (ROOT / "build" / "remaster-iso.sh").read_text()
        preseed = (ROOT / "preseed" / "preseed.cfg").read_text()
        provision = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
        vm_builder = (ROOT / "build" / "build_vm_image.py").read_text()
        self.assertIn('OLLAMA_CARRIER="${3:-}"', remaster)
        self.assertIn("--verify-carrier \"$OLLAMA_CARRIER\"", remaster)
        self.assertIn("/plebian-os/ollama-runtime-carrier.tar.xz", remaster)
        self.assertIn('install -m 0644 "$HERE/releases/0.2.2.env"', remaster)
        self.assertIn("/cdrom/plebian-os/0.2.2.env", preseed)
        self.assertIn("local manifest=/usr/local/share/plebian-os/0.2.2.env", provision)
        self.assertIn(
            "cp /cdrom/plebian-os/ollama-runtime-carrier.tar.xz "
            "/target/usr/local/share/plebian-os/ollama-runtime-carrier.tar.xz",
            preseed,
        )
        self.assertIn("--extract-carrier \"$archive\"", provision)
        self.assertIn("--closure \"$work/closure\"", provision)
        self.assertIn("systemctl enable --now plebian-os-ollama.service", provision)
        self.assertLess(
            provision.index('bash "$DEPS_SCRIPT" ||'),
            provision.index("install_ollama_runtime_from_carrier\n\n"),
        )
        self.assertIn('"--ollama-carrier", type=Path', vm_builder)

    def test_install_requires_one_explicit_mode(self):
        result = subprocess.run(
            ["python3", str(INSTALLER)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("choose exactly one", result.stderr)

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

    def test_helper_is_present_on_every_os_layer_path(self):
        expected = "plebian-os-install-kilix-ollama-runtime"
        for relative in (
            "build/remaster-iso.sh",
            "preseed/preseed.cfg",
            "provision/plebian-os-provision.sh",
            "provision/plebian-os-update.sh",
        ):
            self.assertIn(expected, (ROOT / relative).read_text(), relative)


if __name__ == "__main__":
    unittest.main()
