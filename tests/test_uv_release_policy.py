import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "releases" / "0.1.9.requirements"
EXPECTED = {
    "PLEBIAN_OS_INSTALL_UV": "1",
    "PLEBIAN_OS_UV_VERSION": "0.12.3",
    "PLEBIAN_OS_UV_INSTALLER_SHA256": (
        "a7e3924ea1cd06bf1518c577d635c624ae2e2db030e0fc8ff8cf426224384e17"
    ),
}


def parse_values(path: Path) -> dict[str, str]:
    values = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def shell_loader() -> str:
    source = (ROOT / "build" / "remaster-iso.sh").read_text(encoding="utf-8")
    start = source.index("load_release_manifest() {")
    end = source.index('[ -n "${PLEBIAN_OS_RELEASE:-}" ]', start)
    return source[start:end]


class UvReleasePolicyTests(unittest.TestCase):
    def test_0_1_9_requires_the_verified_uv_pin(self):
        self.assertEqual(parse_values(POLICY), EXPECTED)

    def test_final_manifest_must_repeat_the_policy_when_created(self):
        manifest = ROOT / "releases" / "0.1.9.env"
        if not manifest.exists():
            self.assertNotEqual(
                (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
                "0.1.9",
                "VERSION must not advance until the complete 0.1.9 manifest exists",
            )
            return
        values = parse_values(manifest)
        for key, expected in EXPECTED.items():
            self.assertEqual(values.get(key), expected, key)

    def test_release_loader_accepts_only_the_required_values(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            releases = repo / "releases"
            releases.mkdir()
            (repo / "VERSION").write_text("0.1.9\n", encoding="utf-8")
            (releases / "0.1.9.requirements").write_text(
                POLICY.read_text(encoding="utf-8"), encoding="utf-8"
            )
            manifest = releases / "0.1.9.env"
            base = (
                "PLEBIAN_OS_VERSION=0.1.9\n"
                "PLEBIAN_OS_RELEASE_MODE=1\n"
            )
            harness = (
                "set -euo pipefail\n"
                f"HERE={shlex.quote(str(repo))}\n"
                f"{shell_loader()}\n"
                "load_release_manifest 0.1.9\n"
            )

            manifest.write_text(
                base
                + "\n".join(f"{key}={value}" for key, value in EXPECTED.items())
                + "\n",
                encoding="utf-8",
            )
            (releases / "0.1.9.requirements").unlink()
            missing = subprocess.run(
                ["bash", "-c", harness], text=True, capture_output=True
            )
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("missing releases/0.1.9.requirements", missing.stderr)
            (releases / "0.1.9.requirements").write_text(
                POLICY.read_text(encoding="utf-8"), encoding="utf-8"
            )

            manifest.write_text(
                base
                + "PLEBIAN_OS_INSTALL_UV=0\n"
                + "PLEBIAN_OS_UV_VERSION=0.12.3\n"
                + "PLEBIAN_OS_UV_INSTALLER_SHA256="
                + EXPECTED["PLEBIAN_OS_UV_INSTALLER_SHA256"]
                + "\n",
                encoding="utf-8",
            )
            refused = subprocess.run(
                ["bash", "-c", harness], text=True, capture_output=True
            )
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn(
                "requires PLEBIAN_OS_INSTALL_UV=1", refused.stderr
            )

            manifest.write_text(
                base
                + "\n".join(f"{key}={value}" for key, value in EXPECTED.items())
                + "\n",
                encoding="utf-8",
            )
            accepted = subprocess.run(
                ["bash", "-c", harness], text=True, capture_output=True
            )
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertIn(
                "validated releases/0.1.9.requirements", accepted.stdout
            )

    def test_release_mode_installs_uv_system_wide_and_verifies_it(self):
        installer = (ROOT / "provision" / "install-deps.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('install -m 0755 "$uv_stage/uv" /usr/local/bin/uv', installer)
        self.assertIn('install -m 0755 "$uv_stage/uvx" /usr/local/bin/uvx', installer)
        self.assertIn('uv_actual="$(/usr/local/bin/uv --version', installer)
        self.assertIn('failed+=("uv (release-required)")', installer)


if __name__ == "__main__":
    unittest.main()
