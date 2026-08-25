import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "releases" / "0.1.9.requirements"
NEXT_POLICY = ROOT / "releases" / "0.2.1.requirements"
DEPS = ROOT / "provision" / "install-deps.sh"
PROVISION = ROOT / "provision" / "plebian-os-provision.sh"
EXPECTED = {
    "PLEBIAN_OS_INSTALL_UV": "1",
    "PLEBIAN_OS_UV_VERSION": "0.12.3",
    "PLEBIAN_OS_UV_INSTALLER_SHA256": (
        "a7e3924ea1cd06bf1518c577d635c624ae2e2db030e0fc8ff8cf426224384e17"
    ),
}
NEXT_EXPECTED = {
    "PLEBIAN_OS_NETINST_URL": (
        "https://cdimage.debian.org/cdimage/archive/13.5.0/amd64/iso-cd/"
        "debian-13.5.0-amd64-netinst.iso"
    ),
    "PLEBIAN_OS_NETINST_SHA256": (
        "95838884f5ea6c82421dfe6baaa5a639dbbe6756c1e380f9fe7a7cb0c1949d2a"
    ),
    "PLEBIAN_OS_NETINST_MAX_BYTES": "791674880",
    "PLEBIAN_OS_APT_SNAPSHOT": "20260727T000000Z",
    "PLEBIAN_OS_INSTALL_UV": "1",
    "PLEBIAN_OS_UV_VERSION": "0.12.5",
    "PLEBIAN_OS_UV_INSTALLER_SHA256": (
        "504511fbbbd811aeaba6738abc79408956b6c7da0ca35437b3dcc24a41efc111"
    ),
    "PLEBIAN_OS_UV_INSTALLER_MAX_BYTES": "71225",
    "PLEBIAN_OS_INSTALL_WAYDROID": "1",
    "PLEBIAN_OS_WAYDROID_CLOSURE_SHA256": (
        "4ad7a4d44eef6ce4e90173491d0c6c8da02b3764d0d20d1df67ca7eeaa7e4175"
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


def shell_function(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf-8")
    start = source.index(f"{name}() {{")
    end = source.index("\n}", start) + 2
    return source[start:end]


class UvReleasePolicyTests(unittest.TestCase):
    def test_0_1_9_requires_the_verified_uv_pin(self):
        self.assertEqual(parse_values(POLICY), EXPECTED)

    def test_0_2_1_requires_the_verified_release_inputs(self):
        self.assertEqual(parse_values(NEXT_POLICY), NEXT_EXPECTED)

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
        installer = DEPS.read_text(encoding="utf-8")
        self.assertIn('install -m 0755 "$uv_stage/uv" /usr/local/bin/uv', installer)
        self.assertIn('install -m 0755 "$uv_stage/uvx" /usr/local/bin/uvx', installer)
        self.assertIn('uv_actual="$(/usr/local/bin/uv --version', installer)
        self.assertIn('uv_version_matches_pin "$uv_actual" "$uv_ver"', installer)
        self.assertIn('failed+=("uv (release-required)")', installer)

    def test_uv_version_pin_accepts_the_current_target_triple_shape_only(self):
        accepted = (
            "uv 0.12.3",
            "uv 0.12.3 (x86_64-unknown-linux-gnu)",
            "uv 0.12.3 (aarch64-apple-darwin)",
        )
        rejected = (
            "",
            "uv 0.12.30",
            "uv 0.12.3 ()",
            "uv 0.12.3 (x86_64 unknown linux gnu)",
            "uv 0.12.3 (x86_64-unknown-linux-gnu) extra",
            "uv 0.12.3 arbitrary-suffix",
        )
        self.assertEqual(
            shell_function(DEPS, "uv_version_matches_pin"),
            shell_function(PROVISION, "uv_version_matches_pin"),
            "install-time and provenance-time uv validation must stay identical",
        )
        for path in (DEPS, PROVISION):
            function = shell_function(path, "uv_version_matches_pin")
            harness = (
                "set -uo pipefail\n"
                f"{function}\n"
                'uv_version_matches_pin "$1" "$2"\n'
            )
            for actual in accepted:
                with self.subTest(script=path.name, accepted=actual):
                    result = subprocess.run(
                        ["bash", "-c", harness, "uv-version-test", actual, "0.12.3"],
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
            for actual in rejected:
                with self.subTest(script=path.name, rejected=actual):
                    result = subprocess.run(
                        ["bash", "-c", harness, "uv-version-test", actual, "0.12.3"],
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    self.assertNotEqual(result.returncode, 0, actual)


if __name__ == "__main__":
    unittest.main()
