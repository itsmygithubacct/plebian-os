import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SHELL_LESSON_PREREQ_PACKAGES = {
    "bash",
    "coreutils",
    "diffutils",
    "findutils",
    "gawk",
    "grep",
    "procps",
    "python3",
    "sed",
    "util-linux",
}

VOICE_ARCHIVE_PREREQUISITE_PACKAGES = {
    "coreutils",  # sha256sum
    "curl",
    "unzip",
}

# The model store compiles its CPU inference runtime on the machine that runs
# it, and that build is CMake's. Shipping the toolchain without CMake left the
# store offering a build it could not finish, so this belongs in the image
# rather than in an apt prompt the first time somebody opens a chat.
LOCAL_BUILD_PREREQUISITE_PACKAGES = {
    "build-essential",
    "cmake",
}

# Playalong F122's native terminal surface links SDL2 for output and libsndfile
# for stem decode. The -dev packages are already in the build toolchain group,
# but the runtime libraries are asserted separately on purpose: an image built
# without the toolchain must still be able to start the app, and a loader error
# is a much worse failure than a missing optional feature.
PLAYALONG_RUNTIME_PACKAGES = {"libsdl2-2.0-0", "libsndfile1"}
PLAYALONG_BUILD_PACKAGES = {"libsdl2-dev", "libsndfile1-dev", "pkg-config"}

# The session's TERM is xterm-kitty. Kilix installs the engine's own entry
# into the session user's ~/.terminfo, but root, sudo and every other account
# read the system database, so the packaged entry is what keeps a strict
# ncurses program from meeting an unknown terminal there.
TERMINFO_PACKAGES = {"kitty-terminfo"}

# Catalog-pinned PDF Conversion builds a hash-locked standard venv independently
# of uv. The 0.1.9 release also installs verified uv as system tooling, but both
# package paths retain the converter's complete standard-Python runtime.
PDF_RUNTIME_PREREQUISITE_PACKAGES = {"python3", "python3-venv"}

# Browsers remain useful fallbacks, but the desktop release promises a native
# PDF file handler with printing, forms, and annotation support.
DEFAULT_PDF_VIEWER_PACKAGES = {"evince"}

# Pleb preinstalls the catalog-pinned terminal viewer. These packages let its
# native Poppler/Cairo core build during provisioning; the wrapper retains
# Evince and CPU-rendering fallbacks if GPU presentation is unavailable.
PDF_VIEWER_BUILD_PACKAGES = {
    "build-essential",
    "pkg-config",
    "zlib1g-dev",
    "libcairo2-dev",
    "libglib2.0-dev",
    "libpoppler-glib-dev",
}

# Kilix NVR is catalog-pinned and built on the target. Its database is linked
# through SQLite's C interface, so the release image must ship the development
# header and linker input rather than relying on a host's incidental package.
NVR_BUILD_PACKAGES = {"libsqlite3-dev", "zlib1g-dev"}

COMPRESSION_PREREQUISITE_PACKAGES = {
    "python3",
    "python3-venv",
    "zlib1g",
    "libbz2-1.0",
    "liblzma5",
    "libzstd1",
    "zstd",
    "bzip2",
    "xz-utils",
    "zip",
    "unzip",
    "ca-certificates",
}

HARDWARE_DISCOVERY_PACKAGES = {
    "pciutils",
    "usbutils",
    "dmidecode",
    "lshw",
    "lm-sensors",
    "util-linux",
    "kmod",
    "ethtool",
    "smartmontools",
    "nvme-cli",
}

PERFORMANCE_QUALIFICATION_PACKAGES = {"linux-perf"}

VULKAN_RUNTIME_PACKAGES = {"libvulkan1", "mesa-vulkan-drivers"}
VULKAN_NOUVEAU_PACKAGES = {"firmware-nvidia-graphics"}
VULKAN_QUALIFICATION_PACKAGES = {"vulkan-tools"}

# Kilix IceWM is built on first selection. Plebian-OS 0.2.0 must provide the
# complete, explicit pkg-config closure used by the pinned IceWM configuration
# on both fresh-install paths; transitive dependencies are not this contract.
ICEWM_BUILD_PACKAGES = {
    "build-essential",
    "cmake",
    "pkg-config",
    "libx11-dev",
    "libxext-dev",
    "libxrandr-dev",
    "libxft-dev",
    "libfontconfig-dev",
    "libxrender-dev",
    "libxcomposite-dev",
    "libxcursor-dev",
    "libxdamage-dev",
    "libxfixes-dev",
    "libimlib2-dev",
}


def preseed_packages():
    text = (ROOT / "preseed" / "preseed.cfg").read_text()
    match = re.search(
        r"^d-i pkgsel/include string (?P<body>.*?)^d-i pkgsel/upgrade",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise AssertionError("preseed pkgsel/include block not found")
    body = match.group("body").replace("\\\n", " ")
    return set(body.split())


def additive_packages(array_name):
    """Return packages from one explicitly named additive shell array."""
    text = (ROOT / "provision" / "install-deps.sh").read_text()
    match = re.search(
        rf"^{array_name}=\(\n(?P<body>.*?)^\)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise AssertionError(f"{array_name} not found in install-deps")
    pkgs = set()
    for entry in re.finditer(r'^\s*"[^"]+ :: ([^"]+)"',
                             match.group("body"), flags=re.MULTILINE):
        pkgs.update(entry.group(1).split())
    return pkgs


def qualification_packages():
    """The additive qualification-image groups.

    These are deliberately NOT base-image packages. Vulkan evidence tooling is
    additionally gated on selection of the Vulkan qualification lane.
    """
    return (additive_packages("QUAL_GROUPS")
            | additive_packages("QUAL_VULKAN_GROUPS"))


def install_deps_packages():
    text = (ROOT / "provision" / "install-deps.sh").read_text()
    pkgs = set()
    for match in re.finditer(r'^\s*"[^"|]+\|([^"]+)"', text, flags=re.MULTILINE):
        pkgs.update(match.group(1).split())
    if not pkgs:
        raise AssertionError("install-deps DEP_GROUPS not found")
    return pkgs


class DependencyManifestTests(unittest.TestCase):
    def test_qualification_group_is_not_in_the_base_image(self):
        """OD-12D puts Xephyr on qualification images only.

        If it leaked into the base set it would ship a test-only X server to
        every installed machine, and it would also break the preseed/install-deps
        equality that the next test enforces.
        """
        qual = qualification_packages()
        self.assertTrue(qual, "QUAL_GROUPS not found in install-deps")
        self.assertIn("xserver-xephyr", qual)
        self.assertTrue(qual.isdisjoint(install_deps_packages()))
        self.assertTrue(qual.isdisjoint(preseed_packages()))

    def test_vulkan_runtime_is_conditional_and_provider_specific(self):
        common = additive_packages("VULKAN_GROUPS")
        nouveau = additive_packages("VULKAN_NOUVEAU_GROUPS")
        self.assertEqual(common, VULKAN_RUNTIME_PACKAGES)
        self.assertEqual(nouveau, VULKAN_NOUVEAU_PACKAGES)
        self.assertTrue(common.isdisjoint(install_deps_packages()))
        self.assertTrue(nouveau.isdisjoint(install_deps_packages()))
        self.assertTrue(common.isdisjoint(preseed_packages()))
        self.assertTrue(nouveau.isdisjoint(preseed_packages()))

    def test_vulkan_tools_are_qualification_only(self):
        tools = additive_packages("QUAL_VULKAN_GROUPS")
        self.assertEqual(tools, VULKAN_QUALIFICATION_PACKAGES)
        self.assertTrue(tools.isdisjoint(install_deps_packages()))
        self.assertTrue(tools.isdisjoint(preseed_packages()))

    def test_vulkan_modes_select_the_exact_dry_run_closures(self):
        installer = ROOT / "provision" / "install-deps.sh"

        def output(*args):
            result = subprocess.run(
                ["bash", str(installer), "--dry-run", *args],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout

        base = output()
        vulkan = output("--vulkan")
        nouveau = output("--vulkan-nouveau")
        qualified = output("--qualification", "--vulkan")

        for package in VULKAN_RUNTIME_PACKAGES | VULKAN_NOUVEAU_PACKAGES \
                | VULKAN_QUALIFICATION_PACKAGES:
            self.assertNotIn(package, base)
        for package in VULKAN_RUNTIME_PACKAGES:
            self.assertIn(package, vulkan)
            self.assertIn(package, nouveau)
            self.assertIn(package, qualified)
        self.assertNotIn("firmware-nvidia-graphics", vulkan)
        self.assertIn("firmware-nvidia-graphics", nouveau)
        self.assertNotIn("firmware-nvidia-graphics", qualified)
        self.assertNotIn("vulkan-tools", vulkan)
        self.assertNotIn("vulkan-tools", nouveau)
        self.assertIn("vulkan-tools", qualified)
        self.assertIn("xserver-xephyr", qualified)

    def test_preseed_and_install_deps_package_sets_match(self):
        self.assertEqual(preseed_packages(), install_deps_packages())

    def test_the_engines_terminal_type_is_in_the_system_database(self):
        self.assertLessEqual(TERMINFO_PACKAGES, install_deps_packages())

    def test_local_build_prerequisites_are_installed(self):
        self.assertLessEqual(LOCAL_BUILD_PREREQUISITE_PACKAGES,
                             install_deps_packages())

    def test_pdf_runtime_remains_available_independently_of_uv(self):
        self.assertLessEqual(PDF_RUNTIME_PREREQUISITE_PACKAGES,
                             install_deps_packages())
        self.assertLessEqual(PDF_RUNTIME_PREREQUISITE_PACKAGES,
                             preseed_packages())
        install = (ROOT / "provision" / "install-deps.sh").read_text()
        self.assertIn("python3-venv runtimes remain available", install)

    def test_default_pdf_viewer_is_installed_on_both_paths(self):
        self.assertLessEqual(DEFAULT_PDF_VIEWER_PACKAGES,
                             install_deps_packages())
        self.assertLessEqual(DEFAULT_PDF_VIEWER_PACKAGES,
                             preseed_packages())

    def test_native_pdf_viewer_builds_on_both_paths(self):
        self.assertLessEqual(PDF_VIEWER_BUILD_PACKAGES,
                             install_deps_packages())
        self.assertLessEqual(PDF_VIEWER_BUILD_PACKAGES,
                             preseed_packages())

    def test_nvr_builds_on_both_paths(self):
        self.assertLessEqual(NVR_BUILD_PACKAGES, install_deps_packages())
        self.assertLessEqual(NVR_BUILD_PACKAGES, preseed_packages())

    def test_021_compression_prerequisites_are_on_both_paths(self):
        self.assertLessEqual(COMPRESSION_PREREQUISITE_PACKAGES,
                             install_deps_packages())
        self.assertLessEqual(COMPRESSION_PREREQUISITE_PACKAGES,
                             preseed_packages())

    def test_021_hardware_discovery_is_on_both_paths(self):
        self.assertLessEqual(HARDWARE_DISCOVERY_PACKAGES,
                             install_deps_packages())
        self.assertLessEqual(HARDWARE_DISCOVERY_PACKAGES,
                             preseed_packages())

    def test_021_performance_qualification_tool_is_on_both_paths(self):
        self.assertLessEqual(PERFORMANCE_QUALIFICATION_PACKAGES,
                             install_deps_packages())
        self.assertLessEqual(PERFORMANCE_QUALIFICATION_PACKAGES,
                             preseed_packages())

    def test_kilix_icewm_builds_on_both_paths(self):
        self.assertLessEqual(ICEWM_BUILD_PACKAGES, install_deps_packages())
        self.assertLessEqual(ICEWM_BUILD_PACKAGES, preseed_packages())

    def test_021_playalong_builds_and_runs_on_both_paths(self):
        self.assertLessEqual(PLAYALONG_BUILD_PACKAGES, install_deps_packages())
        self.assertLessEqual(PLAYALONG_BUILD_PACKAGES, preseed_packages())
        self.assertLessEqual(PLAYALONG_RUNTIME_PACKAGES,
                             install_deps_packages())
        self.assertLessEqual(PLAYALONG_RUNTIME_PACKAGES, preseed_packages())

    def test_shell_lesson_prerequisites_are_installed(self):
        self.assertLessEqual(SHELL_LESSON_PREREQ_PACKAGES, install_deps_packages())

    def test_voice_archive_prerequisites_are_installed_on_both_paths(self):
        self.assertLessEqual(
            VOICE_ARCHIVE_PREREQUISITE_PACKAGES,
            install_deps_packages(),
        )
        self.assertLessEqual(
            VOICE_ARCHIVE_PREREQUISITE_PACKAGES,
            preseed_packages(),
        )

    def test_kilix_fork_system_build_dependencies_are_installed(self):
        required = {
            "libpng-dev", "liblcms2-dev", "libcairo2-dev",
            "libharfbuzz-dev", "libssl-dev", "libxxhash-dev",
            "libsimde-dev", "libwayland-dev", "wayland-protocols",
        }
        self.assertLessEqual(required, install_deps_packages())

    def test_recommends_policy_matches_across_paths(self):
        # Both provisioning paths must resolve the same closure: install-deps.sh
        # uses --no-install-recommends, so the preseed must disable recommends too
        # (otherwise the two "in sync" paths install materially different systems).
        install = (ROOT / "provision" / "install-deps.sh").read_text()
        preseed = (ROOT / "preseed" / "preseed.cfg").read_text()
        self.assertIn("--no-install-recommends", install)
        self.assertIn("pkgsel/install-recommends boolean false", preseed)

    def test_recommends_line_not_parsed_as_a_package(self):
        # The recommends directive must sit OUTSIDE the pkgsel/include block, so
        # the drift parser never mistakes it for a package name.
        pkgs = preseed_packages()
        self.assertNotIn("boolean", pkgs)
        self.assertNotIn("pkgsel/install-recommends", pkgs)


if __name__ == "__main__":
    unittest.main()
