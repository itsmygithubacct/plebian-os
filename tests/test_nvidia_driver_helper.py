"""The optional NVIDIA driver helper.

Plebian-OS ships nouveau and installs this helper without ever running it. The
tests below hold that line — it stays optional, it stays reachable, and it
refuses rather than installing a driver that cannot drive the card it found.
"""
import os
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "provision" / "plebian-os-nvidia-driver"
PROVISION = ROOT / "provision" / "plebian-os-provision.sh"


class HelperShipsAsAnOptionalTool(unittest.TestCase):
    def test_helper_exists_and_is_executable(self):
        self.assertTrue(HELPER.is_file(), f"{HELPER} is missing")
        self.assertTrue(os.access(HELPER, os.X_OK), f"{HELPER} is not executable")

    def test_helper_is_a_bash_script_with_strict_mode(self):
        text = HELPER.read_text()
        self.assertTrue(text.startswith("#!/usr/bin/env bash"))
        self.assertIn("set -euo pipefail", text)

    def test_provisioner_installs_it_onto_path(self):
        text = PROVISION.read_text()
        self.assertIn("/usr/local/bin/plebian-os-nvidia-driver", text)
        self.assertIn('install -m 0755 "$NVIDIA_SRC"', text)

    def test_provisioner_never_runs_it(self):
        """Installed, not invoked. The image must stay on nouveau by default."""
        text = PROVISION.read_text()
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # Any occurrence must be the install/probe plumbing, never a call
            # with one of the acting modes.
            if "plebian-os-nvidia-driver" in stripped:
                self.assertNotIn("--install", stripped)
                self.assertNotIn("--rollback", stripped)

    def test_firstboot_unit_does_not_reference_it(self):
        unit = (ROOT / "provision" / "plebian-os-firstboot.service").read_text()
        self.assertNotIn("nvidia", unit.lower())

    def test_not_listed_as_an_installed_dependency(self):
        """The driver is never pulled in by the image's package groups."""
        deps = (ROOT / "provision" / "install-deps.sh").read_text()
        for token in ("nvidia-driver", "nvidia-detect", "nvidia-legacy"):
            self.assertNotIn(token, deps)


class HelperUsage(unittest.TestCase):
    def test_help_prints_usage_and_exits_zero(self):
        result = subprocess.run(
            ["bash", str(HELPER), "--help"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Usage: plebian-os-nvidia-driver", result.stdout)
        for mode in ("--check", "--status", "--install", "--rollback"):
            self.assertIn(mode, result.stdout)

    def test_unknown_option_is_rejected(self):
        result = subprocess.run(
            ["bash", str(HELPER), "--wat"],
            capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_no_mode_is_rejected(self):
        result = subprocess.run(
            ["bash", str(HELPER)],
            capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(result.returncode, 0)

    @unittest.skipUnless(shutil.which("shellcheck"), "shellcheck not installed")
    def test_shellcheck_clean(self):
        result = subprocess.run(
            ["shellcheck", "-S", "warning", str(HELPER)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)


def _resolve(detect_output, candidates):
    """Drive the helper's resolve_driver_package() with a synthetic card.

    `candidates` maps a package name to the version apt would offer, so a
    retired legacy series is expressed by simply leaving it out.
    """
    policy_cases = "\n".join(
        f'    {name}) echo "  Candidate: {version}" ;;'
        for name, version in candidates.items()
    )
    # apt_candidate() calls `apt-cache policy <pkg>`, so inside the stub the
    # package name is $2 ($1 is the "policy" subcommand).
    script = f"""
set -euo pipefail
apt-cache() {{
  case "$2" in
{policy_cases}
    *) echo "  Candidate: (none)" ;;
  esac
}}
{_helper_functions()}
legacy=$(legacy_series_of "$1")
if pkg=$(resolve_driver_package "$1"); then
  echo "OK:$pkg:$legacy"
else
  echo "REFUSE:$pkg"
fi
"""
    return subprocess.run(
        ["bash", "-c", script, "bash", detect_output],
        capture_output=True, text=True, check=False,
    )


def _helper_functions():
    """Extract the two resolver functions from the helper, verbatim."""
    text = HELPER.read_text()
    start = text.index("# Candidate version apt would install")
    end = text.index("preflight() {")
    return text[start:end]


class HardwareAgeGate(unittest.TestCase):
    """It must refuse when the card is older than any shipped driver supports."""

    SUPPORTED = (
        "Checking card:  NVIDIA Corporation TU106GLM\n"
        "Your card is supported by all driver versions.\n"
        "It is recommended to install the\n"
        "    nvidia-driver\n"
        "package.\n"
    )
    LEGACY_PACKAGED = (
        "Checking card:  NVIDIA Corporation GF119M\n"
        "Your card is only supported by the legacy 390xx drivers series.\n"
        "It is recommended to install the\n"
        "    nvidia-legacy-390xx-driver\n"
        "package.\n"
    )
    LEGACY_RETIRED = (
        "Checking card:  NVIDIA Corporation G96M\n"
        "Your card is only supported by the legacy 340xx drivers series.\n"
        "It is recommended to install the\n"
        "    nvidia-legacy-340xx-driver\n"
        "package.\n"
    )
    UNSUPPORTED = (
        "Checking card:  NVIDIA Corporation NV44\n"
        "Your card is no longer supported by any driver series.\n"
    )
    NOTHING = "Checking card:  NVIDIA Corporation Something\n"

    def test_current_card_resolves_to_the_default_driver(self):
        out = _resolve(self.SUPPORTED, {"nvidia-driver": "550.163.01-2"})
        self.assertTrue(out.stdout.startswith("OK:nvidia-driver:"), out.stdout)

    def test_packaged_legacy_series_is_allowed_but_flagged(self):
        out = _resolve(
            self.LEGACY_PACKAGED, {"nvidia-legacy-390xx-driver": "390.157-1"}
        )
        self.assertIn("OK:nvidia-legacy-390xx-driver:", out.stdout)
        self.assertIn("legacy 390xx", out.stdout.lower())

    def test_retired_legacy_series_is_refused(self):
        """Recommended by nvidia-detect, but no longer in the archive."""
        out = _resolve(self.LEGACY_RETIRED, {"nvidia-driver": "550.163.01-2"})
        self.assertTrue(out.stdout.startswith("REFUSE:"), out.stdout)
        self.assertIn("nvidia-legacy-340xx-driver", out.stdout)

    def test_card_with_no_supported_series_is_refused(self):
        out = _resolve(self.UNSUPPORTED, {"nvidia-driver": "550.163.01-2"})
        self.assertEqual(out.stdout.strip(), "REFUSE:UNSUPPORTED")

    def test_no_recommendation_is_refused_rather_than_guessed(self):
        out = _resolve(self.NOTHING, {"nvidia-driver": "550.163.01-2"})
        self.assertEqual(out.stdout.strip(), "REFUSE:NORECOMMENDATION")


class NeverUsesTheUpstreamRunInstaller(unittest.TestCase):
    def test_no_run_installer_download(self):
        text = HELPER.read_text().lower()
        self.assertNotIn("nvidia-linux-x86_64", text.replace(" ", ""))
        for token in ("wget", "curl -o", "download.nvidia.com"):
            self.assertNotIn(token, text)

    def test_uses_dkms_and_detect(self):
        text = HELPER.read_text()
        self.assertIn("nvidia-detect", text)
        self.assertIn("dkms", text)
        self.assertIn("linux-headers-amd64", text)

    def test_does_not_edit_apt_sources(self):
        """Sources belong to the provisioner; the helper only reads apt."""
        text = HELPER.read_text()
        for token in ("sources.list.d/", "sed -i", "tee /etc/apt"):
            if token in text:
                # Mentioning the path in guidance text is fine; writing is not.
                for line in text.splitlines():
                    if token in line and not line.strip().startswith(("#", "info", "say")):
                        self.fail(f"helper appears to write apt sources: {line}")


if __name__ == "__main__":
    unittest.main()
