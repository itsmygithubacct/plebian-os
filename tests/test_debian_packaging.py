"""The Debian packages install the same files the updater deploys.

debian/install-map is the only list debian/rules installs from. The updater
carries its own list of the same files. These tests hold the two equal, with
the installed locations written here as literals, so neither list can move a
file or change a mode without the other.
"""
import re
import unittest
from pathlib import Path

import test_os_layer_deploy_set as deploy_set

ROOT = Path(__file__).resolve().parents[1]
DEBIAN = ROOT / "debian"
LOCATIONS = {
    "$PLEBIAN_OS_SBINDIR": "/usr/sbin",
    "$PLEBIAN_OS_BINDIR": "/usr/bin",
    "$PLEBIAN_OS_LIBEXECDIR": "/usr/libexec/plebian-os",
    "$PLEBIAN_OS_DATADIR": "/usr/share/plebian-os",
    "$PLEBIAN_OS_NOTICEDIR": "/usr/share/plebian-os/notices",
    "$PLEBIAN_OS_UNITDIR": "/usr/lib/systemd/system",
}
PACKAGES = {
    "plebian-os-release",
    "plebian-os-tools",
    "plebian-os-firstboot",
    "plebian-desktop-base",
}


def install_map():
    rows = []
    for line in (DEBIAN / "install-map").read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) != 4:
            raise AssertionError(f"install-map row is not four fields: {line!r}")
        rows.append(tuple(fields))
    if not rows:
        raise AssertionError("install-map has no rows")
    return rows


def updater_deploy_set():
    text = deploy_set.UPDATE.read_text()
    block = deploy_set.root_block(text)
    result = set()
    for destination, mode in zip(deploy_set.array("dests", block),
                                 deploy_set.array("modes", block)):
        for variable, literal in LOCATIONS.items():
            if destination.startswith(variable + "/"):
                destination = literal + destination[len(variable):]
        if "$" in destination:
            raise AssertionError(f"unexpanded destination: {destination}")
        result.add((destination, mode))
    return result


class DebianPackagingTests(unittest.TestCase):
    def test_packages_install_exactly_what_the_updater_deploys(self):
        packaged = {(destination, mode) for _, mode, _, destination in install_map()}
        self.assertEqual(packaged, updater_deploy_set())
        self.assertEqual(len(packaged), len(install_map()), "duplicate destination")
        self.assertEqual(len(packaged), 31)

    def test_nothing_is_installed_under_usr_local(self):
        for _, _, _, destination in install_map():
            self.assertTrue(destination.startswith("/"), destination)
            self.assertFalse(destination.startswith("/usr/local"), destination)

    def test_every_source_is_a_tracked_regular_file(self):
        version = (ROOT / "VERSION").read_text().strip()
        for _, _, source, _ in install_map():
            path = ROOT / source.replace("@VERSION@", version)
            self.assertTrue(path.is_file(), source)
            self.assertFalse(path.is_symlink(), source)

    def test_the_map_and_the_control_file_name_the_same_packages(self):
        control = (DEBIAN / "control").read_text()
        declared = set(re.findall(r"^Package: (\S+)$", control, flags=re.MULTILINE))
        self.assertEqual(declared, PACKAGES)
        self.assertEqual({package for package, _, _, _ in install_map()}, PACKAGES)

    def test_first_boot_files_are_in_the_first_boot_package_only(self):
        owner = {destination: package for package, _, _, destination in install_map()}
        for destination in (
            "/usr/sbin/plebian-os-provision",
            "/usr/sbin/plebian-os-firstboot-attempt",
            "/usr/lib/systemd/system/plebian-os-firstboot.service",
        ):
            self.assertEqual(owner[destination], "plebian-os-firstboot")

    def test_installing_the_package_never_enables_or_starts_first_boot(self):
        rules = (DEBIAN / "rules").read_text()
        self.assertIn("\tdh_installsystemd --no-enable --no-start\n", rules)
        for script in ("postinst", "preinst", "prerm", "postrm"):
            self.assertEqual(list(DEBIAN.glob(f"*{script}")), [], script)

    def test_the_package_version_is_built_on_the_release_version(self):
        version = (ROOT / "VERSION").read_text().strip()
        first = (DEBIAN / "changelog").read_text().splitlines()[0]
        match = re.fullmatch(r"plebian-os \(([^)]+)\) \S+; urgency=\w+", first)
        self.assertIsNotNone(match, first)
        self.assertRegex(match.group(1), "^" + re.escape(version) + r"[+~]")


if __name__ == "__main__":
    unittest.main()
