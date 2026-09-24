"""Amd64-only release inputs are refused up front on other architectures.

Release closures pin artifacts that only exist for amd64: the Waydroid runtime
and images, the x86_64 Vosk wheel, and the provisioner's fallback kitty bundle
checksum. An ARM64 install used to accept them and fail late, as a checksum or
ELF mismatch deep inside `pleb install`.
"""

import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROVISION = ROOT / "provision" / "plebian-os-provision.sh"
UPDATE = ROOT / "provision" / "plebian-os-update.sh"

X86_64_WHEEL = (
    "https://files.pythonhosted.org/packages/fc/ca/"
    "83398cfcd557360a3d7b2d732aee1c5f6999f68618d1645f38d53e14c9ff/"
    "vosk-0.3.45-py3-none-manylinux_2_12_x86_64.manylinux2010_x86_64.whl"
)
AARCH64_WHEEL = (
    "https://files.pythonhosted.org/packages/a4/23/"
    "3130a69fa0bf4f5566a52e415c18cd854bf561547bb6505666a6eb1bb625/"
    "vosk-0.3.45-py3-none-manylinux2014_aarch64.whl"
)
AMD64_FALLBACK_SHA256 = (
    "bc230142b2bd27f2a4bf1b1b67575f3d397a4ea2cc83f4ac2b912c306a939693"
)
ARM64_BUNDLE_SHA256 = (
    "998216e2662b4d2237f10e21dfec5f4e916063f1b6c17f96edae08212e91d0fa"
)


def clean_env(**overrides: str) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("KILIX_", "KILIX95_", "PLEB_", "PLEBIAN_OS_"))}
    env.update(overrides)
    return env


def assignments(values: dict[str, str]) -> str:
    return "".join(f"{key}={shlex.quote(value)}\n"
                   for key, value in values.items())


def shell_function(script: Path, name: str) -> str:
    lines = script.read_text().splitlines()
    start = lines.index(f"{name}() {{")
    end = lines.index("}", start)
    return "\n".join(lines[start:end + 1]) + "\n"


class Amd64OnlyInputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bin = Path(self.tmp.name) / "bin"
        self.bin.mkdir()

    def path_for(self, machine: str) -> str:
        uname = self.bin / "uname"
        uname.write_text(
            "#!/bin/sh\n"
            f'[ "${{1:-}}" = -m ] && {{ echo {machine}; exit 0; }}\n'
            'exec /usr/bin/uname "$@"\n'
        )
        uname.chmod(0o755)
        return f"{self.bin}{os.pathsep}/usr/bin{os.pathsep}/bin"

    def provision(self, machine: str, **values: str):
        script = (
            "set -euo pipefail\n"
            "export PLEBIAN_OS_PROVISION_LIB_ONLY=1\n"
            f'. "{PROVISION}"\n'
            f"{assignments(values)}"
            "refuse_amd64_only_inputs\n"
            "echo accepted\n"
        )
        return subprocess.run(
            ["bash", "-c", script], env=clean_env(PATH=self.path_for(machine)),
            text=True, capture_output=True, check=False)

    def update(self, machine: str, **values: str):
        script = (
            "set -euo pipefail\n"
            "die() { printf '%s\\n' \"$*\" >&2; exit 1; }\n"
            f"{shell_function(UPDATE, 'refuse_amd64_only_stack_inputs')}"
            f"{assignments(values)}"
            "refuse_amd64_only_stack_inputs\n"
            "echo accepted\n"
        )
        return subprocess.run(
            ["bash", "-c", script], env=clean_env(PATH=self.path_for(machine)),
            text=True, capture_output=True, check=False)

    def assert_accepted(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "accepted")

    def assert_refused(self, result, *fragments: str):
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("accepted", result.stdout)
        for fragment in fragments:
            self.assertIn(fragment, result.stderr)

    def test_amd64_keeps_every_release_input(self):
        self.assert_accepted(self.provision(
            "x86_64", INSTALL_WAYDROID="1", INSTALL_VOICE_MODEL="1",
            KILIX_VOICE_LIB_URL=X86_64_WHEEL,
            KILIX_PREBUILT_SHA256=AMD64_FALLBACK_SHA256))

    def test_arm64_refuses_the_amd64_waydroid_closure(self):
        self.assert_refused(
            self.provision("aarch64", INSTALL_WAYDROID="1",
                           KILIX_PREBUILT_SHA256=ARM64_BUNDLE_SHA256),
            "amd64-only Waydroid closure", "aarch64",
            "PLEBIAN_OS_INSTALL_WAYDROID=0")

    def test_arm64_refuses_the_x86_64_wheel_only_when_dictation_needs_it(self):
        arm64 = {"KILIX_PREBUILT_SHA256": ARM64_BUNDLE_SHA256}
        self.assert_refused(
            self.provision("aarch64", INSTALL_VOICE_MODEL="1",
                           KILIX_VOICE_LIB_URL=X86_64_WHEEL, **arm64),
            "x86_64 Vosk wheel", "KILIX_VOICE_LIB_SHA256")
        # Read-aloud only never downloads the wheel.
        self.assert_accepted(self.provision(
            "aarch64", INSTALL_VOICE_MODEL="0",
            KILIX_VOICE_LIB_URL=X86_64_WHEEL, **arm64))
        self.assert_accepted(self.provision(
            "aarch64", INSTALL_VOICE_MODEL="1",
            KILIX_VOICE_LIB_URL=AARCH64_WHEEL, **arm64))

    def test_arm64_refuses_the_amd64_fallback_bundle_checksum(self):
        # With nothing set, the built-in fallback is the amd64 bundle.
        self.assert_refused(self.provision("aarch64"),
                            "amd64 kitty", "KILIX_PREBUILT_SHA256")
        self.assert_accepted(self.provision(
            "aarch64", KILIX_PREBUILT_SHA256=ARM64_BUNDLE_SHA256))

    def test_update_refuses_the_same_stack_inputs_before_it_moves(self):
        self.assert_accepted(self.update(
            "x86_64", PLEBIAN_OS_INSTALL_VOICE_MODEL="1",
            KILIX_VOICE_LIB_URL=X86_64_WHEEL,
            KILIX_PREBUILT_SHA256=AMD64_FALLBACK_SHA256))
        self.assert_refused(
            self.update("aarch64", PLEBIAN_OS_INSTALL_VOICE_MODEL="1",
                        KILIX_VOICE_LIB_URL=X86_64_WHEEL,
                        KILIX_PREBUILT_SHA256=ARM64_BUNDLE_SHA256),
            "x86_64 Vosk wheel")
        self.assert_refused(
            self.update("aarch64", PLEBIAN_OS_INSTALL_VOICE_MODEL="0",
                        KILIX_VOICE_LIB_URL="",
                        KILIX_PREBUILT_VERSION="0.47.4",
                        KILIX_PREBUILT_SHA256=AMD64_FALLBACK_SHA256),
            "amd64 kitty")
        self.assert_accepted(self.update(
            "aarch64", PLEBIAN_OS_INSTALL_VOICE_MODEL="1",
            KILIX_VOICE_LIB_URL=AARCH64_WHEEL,
            KILIX_PREBUILT_SHA256=ARM64_BUNDLE_SHA256))

        text = UPDATE.read_text()
        self.assertLess(text.index("\nrefuse_amd64_only_stack_inputs\n"),
                        text.index("\nbegin_stack_transaction\n"))

    def test_provision_refuses_before_it_needs_root(self):
        text = PROVISION.read_text()
        self.assertLess(text.index("\nrefuse_amd64_only_inputs\n"),
                        text.index('\n[ "$(id -u)" = 0 ] || [ "$DRY_RUN" = 1 ]'))


if __name__ == "__main__":
    unittest.main()
