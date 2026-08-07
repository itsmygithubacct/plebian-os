import re
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

# The session's TERM is xterm-kitty. Kilix installs the engine's own entry
# into the session user's ~/.terminfo, but root, sudo and every other account
# read the system database, so the packaged entry is what keeps a strict
# ncurses program from meeting an unknown terminal there.
TERMINFO_PACKAGES = {"kitty-terminfo"}


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


def install_deps_packages():
    text = (ROOT / "provision" / "install-deps.sh").read_text()
    pkgs = set()
    for match in re.finditer(r'^\s*"[^"|]+\|([^"]+)"', text, flags=re.MULTILINE):
        pkgs.update(match.group(1).split())
    if not pkgs:
        raise AssertionError("install-deps DEP_GROUPS not found")
    return pkgs


class DependencyManifestTests(unittest.TestCase):
    def test_preseed_and_install_deps_package_sets_match(self):
        self.assertEqual(preseed_packages(), install_deps_packages())

    def test_the_engines_terminal_type_is_in_the_system_database(self):
        self.assertLessEqual(TERMINFO_PACKAGES, install_deps_packages())

    def test_local_build_prerequisites_are_installed(self):
        self.assertLessEqual(LOCAL_BUILD_PREREQUISITE_PACKAGES,
                             install_deps_packages())

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
