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

    def test_shell_lesson_prerequisites_are_installed(self):
        self.assertLessEqual(SHELL_LESSON_PREREQ_PACKAGES, install_deps_packages())

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
