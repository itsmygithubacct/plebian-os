import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLOSURE = ROOT / "provision" / "waydroid-closure.env"
SETUP = ROOT / "provision" / "plebian-os-waydroid-setup"
PIN = ROOT / "provision" / "waydroid-closure.sha256"
REQUIREMENTS_020 = ROOT / "releases" / "0.2.0.requirements"
REQUIREMENTS_021 = ROOT / "releases" / "0.2.1.requirements"


def values(path: Path) -> dict[str, str]:
    result = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        if key in result:
            raise AssertionError(f"duplicate key: {key}")
        result[key] = value
    return result


class WaydroidReleaseTests(unittest.TestCase):
    def test_runtime_closure_is_exact_and_bound_by_release_requirement(self):
        closure = values(CLOSURE)
        requirements = values(REQUIREMENTS_020)
        digest = hashlib.sha256(CLOSURE.read_bytes()).hexdigest()
        self.assertEqual(requirements["PLEBIAN_OS_INSTALL_WAYDROID"], "1")
        self.assertEqual(
            requirements["PLEBIAN_OS_WAYDROID_CLOSURE_SHA256"], digest
        )
        self.assertEqual(
            requirements["PLEBIAN_OS_NETINST_MAX_BYTES"], "791674880"
        )
        self.assertEqual(
            requirements["PLEBIAN_OS_UV_INSTALLER_MAX_BYTES"], "71225"
        )
        self.assertEqual(PIN.read_text(encoding="utf-8"), digest + "\n")
        self.assertEqual(closure["WAYDROID_WESTON_VERSION"], "14.0.2-1")
        self.assertEqual(closure["WAYDROID_PACKAGE_VERSION"], "1.6.2")
        self.assertEqual(closure["WAYDROID_LIBGLIBUTIL_VERSION"], "1.0.80")
        self.assertEqual(closure["WAYDROID_LIBGBINDER_VERSION"], "1.1.43")
        self.assertEqual(closure["WAYDROID_PYTHON_GBINDER_VERSION"], "1.3.1")
        for key, value in closure.items():
            if key.endswith("_URL"):
                self.assertTrue(value.startswith("https://"), key)
            if key.endswith("_SHA256"):
                self.assertRegex(value, r"^[0-9a-f]{64}$", key)

    def test_0_2_1_retains_the_hash_bound_first_use_helper(self):
        requirements = values(REQUIREMENTS_021)
        digest = hashlib.sha256(CLOSURE.read_bytes()).hexdigest()
        self.assertEqual(requirements["PLEBIAN_OS_INSTALL_WAYDROID"], "1")
        self.assertEqual(
            requirements["PLEBIAN_OS_WAYDROID_CLOSURE_SHA256"], digest
        )

    def test_setup_validates_and_reports_the_closure_without_root(self):
        digest = hashlib.sha256(CLOSURE.read_bytes()).hexdigest()
        result = subprocess.run(
            [str(SETUP), "--dry-run"],
            text=True,
            capture_output=True,
            env={
                key: value for key, value in os.environ.items()
                if key != "PLEBIAN_OS_WAYDROID_CLOSURE_SHA256"
            },
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Waydroid 1.6.2 closure", result.stdout)
        self.assertIn("apt-install exact Weston", result.stdout)
        self.assertIn("initialize Waydroid from the preinstalled", result.stdout)
        self.assertNotIn("checksum was not supplied", result.stderr)

    def test_setup_rejects_substitution_and_unknown_closure_keys(self):
        result = subprocess.run(
            [str(SETUP), "--dry-run"],
            text=True,
            capture_output=True,
            env={
                **os.environ,
                "PLEBIAN_OS_WAYDROID_CLOSURE_SHA256": "0" * 64,
            },
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("closure checksum mismatch", result.stderr)

        with tempfile.TemporaryDirectory() as temporary:
            candidate = Path(temporary) / "closure.env"
            candidate.write_text(
                CLOSURE.read_text(encoding="utf-8") + "UNREVIEWED_URL=https://example.test\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [str(SETUP), "--closure", str(candidate), "--dry-run"],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown Waydroid closure key", result.stderr)

    def test_release_and_reprovision_plumbing_carries_the_policy(self):
        provision = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
        selector = (
            ROOT / "provision" / "plebian-os-select-closure.sh"
        ).read_text()
        remaster = (ROOT / "build" / "remaster-iso.sh").read_text()
        for key in (
            "PLEBIAN_OS_INSTALL_WAYDROID",
            "PLEBIAN_OS_WAYDROID_CLOSURE_SHA256",
        ):
            self.assertIn(key, provision)
            self.assertIn(key, selector)
            self.assertIn(key, remaster)
        self.assertIn("plebian-os-waydroid-setup", provision)
        self.assertIn("waydroid-closure.env", provision)
        self.assertIn("waydroid-closure.sha256", provision)
        self.assertIn("/usr/lib/plebian-os/waydroid", provision)
        self.assertNotIn(
            'env "${WAYDROID_ENV[@]}" "$WAYDROID_SETUP"', provision
        )
        self.assertNotIn("curl |", SETUP.read_text(encoding="utf-8"))

    def test_lazy_privilege_boundary_ignores_caller_paths_and_serializes(self):
        setup = SETUP.read_text(encoding="utf-8")
        self.assertIn('[[ "${SUDO_UID:-}" =~ ^[1-9][0-9]*$ ]]', setup)
        self.assertIn('CLOSURE="$SELF_DIR/waydroid-closure.env"', setup)
        self.assertIn("STAGING_ROOT=/var/lib/plebian-os/session", setup)
        self.assertIn("IMAGES_PARENT=/usr/share/waydroid-extra", setup)
        self.assertIn("first-use setup does not accept caller-supplied arguments", setup)
        self.assertIn('flock "$INSTALL_LOCK_FD"', setup)
        self.assertNotRegex(setup, r"(?m)^[ \t]*sudo(?:[ \t]|$)")

    def test_setup_persists_and_verifies_all_binder_devices(self):
        setup = SETUP.read_text(encoding="utf-8")
        self.assertIn(
            "options binder_linux devices=binder,hwbinder,vndbinder",
            setup,
        )
        self.assertIn("/etc/modprobe.d/plebian-os-waydroid.conf", setup)
        self.assertIn("/etc/modules-load.d/plebian-os-waydroid.conf", setup)
        self.assertIn("modprobe binder_linux", setup)
        self.assertIn("for device in binder hwbinder vndbinder", setup)
        self.assertIn('binder_device_present "$device"', setup)
        self.assertLess(
            setup.index("install_binder_support\n"),
            setup.index("apt-get install -y --no-install-recommends"),
        )

    def test_large_images_use_bounded_verified_range_downloads(self):
        setup = SETUP.read_text(encoding="utf-8")
        self.assertIn("DOWNLOAD_PARALLEL=16", setup)
        self.assertIn("DOWNLOAD_RANGE_BYTES=$((2 * 1024 * 1024))", setup)
        self.assertIn("DOWNLOAD_RETRIES=30", setup)
        self.assertIn("DOWNLOAD_RETRY_MAX_TIME=300", setup)
        self.assertIn("DOWNLOAD_PASSES=3", setup)
        self.assertIn(
            "DOWNLOAD_CACHE_ROOT=/var/cache/plebian-os/waydroid", setup
        )
        self.assertIn(
            '--parallel-max "$DOWNLOAD_PARALLEL"', setup
        )
        self.assertIn('--retry "$DOWNLOAD_RETRIES"', setup)
        self.assertIn('--range "$start-$end"', setup)
        self.assertIn('log "downloading missing ranges (pass ', setup)
        self.assertIn('log "reusing verified cached $name"', setup)
        self.assertIn('part.stat().st_size != expected', setup)
        self.assertLess(
            setup.index('assembly.stat().st_size != total'),
            setup.index('actual="$(sha256sum -- "$output"'),
        )


if __name__ == "__main__":
    unittest.main()
