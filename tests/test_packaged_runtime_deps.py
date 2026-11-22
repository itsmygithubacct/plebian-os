"""Check the checkout and packaged dependency plans without running apt."""
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "provision/install-deps.sh"
PROVISIONER = ROOT / "provision/plebian-os-provision.sh"
APT_INSTALL = "    + apt-get install -y --no-install-recommends"


def run_bash(*args, script=None):
    return subprocess.run(
        ["bash", *args], input=script, capture_output=True, text=True, timeout=20,
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
    )


def install_requests(output):
    return [
        line.removeprefix(APT_INSTALL).split()
        for line in output.splitlines() if line.startswith(APT_INSTALL)
    ]


class PackagedRuntimeDepsTests(unittest.TestCase):
    def test_default_installs_the_checkout_toolchain(self):
        result = run_bash(INSTALLER, "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        packages = {pkg for group in install_requests(result.stdout) for pkg in group}
        self.assertLessEqual({"build-essential", "gcc"}, packages)
        self.assertIn("installing group: build toolchain", result.stdout)

    def test_packaged_runtime_keeps_runtime_packages_and_their_floors(self):
        result = run_bash(INSTALLER, "--dry-run", "--packaged-runtime")
        self.assertEqual(result.returncode, 0, result.stderr)
        excluded = {
            "build-essential", "cmake", "golang-go", "nodejs", "libx11-dev",
            "libssh2-1-dev", "libbrotli-dev", "libpipewire-0.3-dev", "libonnxruntime-dev",
            "libsamplerate0-dev", "gcc", "clang", "autoconf", "autoconf-archive", "automake",
            "bison", "ccache", "device-tree-compiler", "flex", "libconfuse-dev", "libncurses-dev",
            "libtool", "ninja-build", "scons",
        }
        printed = {word.split("=", 1)[0] for word in result.stdout.split()}
        self.assertEqual(excluded & printed, set())
        self.assertNotIn("installing group: build toolchain\n", result.stdout)
        packages = {pkg for group in install_requests(result.stdout) for pkg in group}
        self.assertLessEqual({
            "chromium", "pipewire", "wireplumber", "libfluidsynth3", "libonnxruntime1.21",
            "libsamplerate0", "libssl3t64", "wget", "openssh-client", "file", "e2fsprogs", "parted",
        }, packages)
        for pkg in ("libonnxruntime1.21", "libsamplerate0", "libssl3t64"):
            self.assertIn(f"+ require {pkg} >= ", result.stdout)

    def test_empty_groups_are_skipped_and_optional_runtime_pins_survive(self):
        source = INSTALLER.read_text().replace(
            "DEP_GROUPS=(\n", 'DEP_GROUPS=(\n    "compiler-only base|gcc=1"\n', 1,
        ).replace(
            "QUAL_GROUPS=(\n", 'QUAL_GROUPS=(\n    "compiler-only optional :: clang=1"\n'
            '    "build toolchain extras :: libpipewire-0.3-dev=1 wget=2"\n', 1,
        )
        result = run_bash("-s", "--", "--dry-run", "--packaged-runtime", "--qualification", script=source)
        self.assertEqual(result.returncode, 0, result.stderr)
        requests = install_requests(result.stdout)
        self.assertNotIn([], requests)
        self.assertNotIn("compiler-only", result.stdout)
        self.assertIn(["wget=2"], requests)

    def test_unknown_option_exits_two_and_lists_packaged_runtime(self):
        result = run_bash(INSTALLER, "--not-a-real-option")
        self.assertEqual(result.returncode, 2)
        self.assertRegex(result.stderr, r"^usage: .*\[--packaged-runtime\]")

    def test_first_boot_selects_packaged_runtime_only_when_both_packages_are_installed(self):
        source = PROVISIONER.read_text()
        start = source.index('log "installing runtime dependencies via $DEPS_SCRIPT"')
        end = source.index("\nnormalize_accounts_service_package_directory", start)
        # Use the real package check and dependency step. Record the child script's
        # arguments instead of installing anything on the test machine.
        setup = r'''
PLEBIAN_OS_PROVISION_LIB_ONLY=1 source "$1"
DRY_RUN=$2
pleb_status=$3
kilix_status=$4
dpkg-query() {
    [ "$2" = -f ] && [ "$3" = '${db:Status-Status}' ] || return 1
    case "$4" in
        pleb) printf '%s' "$pleb_status" ;;
        kilix) printf '%s' "$kilix_status" ;;
        *) return 1 ;;
    esac
}
DEPS_SCRIPT=install-deps
UV_VERSION_PIN= UV_INSTALLER_SHA256= UV_INSTALLER_MAX_BYTES=
log() { echo "$*"; }
bash() { printf 'child %s\n' "$*"; }
'''
        cases = (("0", "installed", "installed"), ("0", "config-files", "installed"),
                 ("0", "installed", "unpacked"), ("1", "installed", "installed"))
        for dry, pleb, kilix in cases:
            with self.subTest(dry=dry, pleb=pleb, kilix=kilix):
                result = run_bash("-s", "--", PROVISIONER, dry, pleb, kilix, script=setup + source[start:end])
                self.assertEqual(result.returncode, 0, result.stderr)
                calls = [line.split()[1:] for line in result.stdout.splitlines() if line.startswith("child ")]
                packaged = (dry, pleb, kilix) == ("0", "installed", "installed")
                expected = ["install-deps", "--model-converters"]
                if packaged:
                    expected.append("--packaged-runtime")
                if dry == "1":
                    expected.append("--dry-run")
                self.assertEqual(len(calls), 1)
                self.assertCountEqual(calls[0], expected)
                self.assertEqual(result.stdout.lower().count("skipping the build toolchain"), int(packaged))


if __name__ == "__main__":
    unittest.main()
