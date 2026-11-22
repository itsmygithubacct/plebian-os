"""The Debian packages install the same files the updater deploys.

debian/install-map is the only list debian/rules installs from. The updater
carries its own list of the same files. These tests hold the two equal, with
the installed locations written here as literals, so neither list can move a
file or change a mode without the other. The packages also install the
archive key, Qt pin, desktop defaults, tasksel descriptor and one-way converter.
"""
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
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
    "plebian-archive-keyring",
}
METAPACKAGES = {"pleb-desktop", "task-pleb-desktop"}
WIREPLUMBER_PROFILE = "/etc/wireplumber/wireplumber.conf.d/50pleb-video-only.conf"
TASKSEL_DESC = "/usr/share/tasksel/descs/pleb-desktop.desc"
DROPINS = {
    "/etc/lightdm/lightdm.conf.d/50-plebian-os.conf":
        "debian/desktop/lightdm-session.conf",
    "/etc/xdg-desktop-portal/pleb-portals.conf":
        "debian/desktop/pleb-portals.conf",
    WIREPLUMBER_PROFILE: "debian/desktop/50pleb-video-only.conf",
    "/etc/xdg/mimeapps.list":
        "debian/desktop/mimeapps.list",
    "/etc/systemd/logind.conf.d/50-plebian-lid.conf":
        "debian/desktop/50-plebian-lid.conf",
    "/etc/systemd/system.conf.d/50-plebian-os-quiet-console.conf":
        "debian/desktop/50-plebian-os-quiet-console.conf",
    "/etc/modprobe.d/plebian-os-no-beep.conf":
        "debian/desktop/plebian-os-no-beep.conf",
}
KEYRING = "plebian-archive-keyring"
KEY_FINGERPRINT = "1730239E771FE87ED7AB9BCFEDC605E76D3B99B0"
QT_PIN = "/etc/apt/preferences.d/plebian-os-qt-runtime"


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
        # Only the tools package deploys the one-way converter.
        converter = "/usr/sbin/plebian-os-convert-0.2.3"
        rows = install_map()
        self.assertEqual([row for row in rows if row[3] == converter], [
            ("plebian-os-tools", "0755", "provision/plebian-os-convert-0.2.3", converter),
        ])
        extra = {QT_PIN, TASKSEL_DESC, converter, *DROPINS}
        core = [row for row in rows
                if row[0] != KEYRING and row[3] not in extra]
        packaged = {(destination, mode) for _, mode, _, destination in core}
        self.assertEqual(packaged, updater_deploy_set())
        self.assertEqual(len(packaged), len(core), "duplicate destination")
        self.assertEqual(len(packaged), 31)
        self.assertEqual(len(rows), 42)

    def test_desktop_base_records_the_qualified_qt_pin(self):
        rows = [row for row in install_map() if row[3] == QT_PIN]
        self.assertEqual(rows, [(
            "plebian-desktop-base", "0644",
            "debian/plebian-os-qt-runtime.pref", QT_PIN,
        )])
        source = (ROOT / "provision" / "plebian-os-qt-runtime").read_text()
        namespace = {}
        exec(compile(source, "plebian-os-qt-runtime", "exec"), namespace)
        records = [
            {"Package": "libqt5gui5t64",
             "Version": "5.15.15+dfsg-6+deb13u1+plebianrc6.2"},
            {"Package": "libqt6gui6",
             "Version": "6.8.2+dfsg-9+deb13u2+plebianrc6.2"},
        ]
        pinned = (ROOT / rows[0][2]).read_text()
        self.assertEqual(pinned, namespace["preferences"](records))

    def test_desktop_base_installs_the_desktop_dropins(self):
        provisioner = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
        rows = {destination: (package, mode, source)
                for package, mode, source, destination in install_map()}
        self.assertEqual(set(DROPINS), set(DROPINS.keys()) & set(rows))
        for destination, source in DROPINS.items():
            package, mode, mapped = rows[destination]
            self.assertEqual((package, mode, mapped),
                             ("plebian-desktop-base", "0644", source))
            text = (ROOT / source).read_text()
            self.assertTrue(text.endswith("\n"))
            if destination == WIREPLUMBER_PROFILE:
                self.assertEqual(
                    text,
                    "# Plebian-OS keeps PulseAudio as its audio server. PipeWire handles video.\n"
                    "context.properties = {\n    wireplumber.profile = video-only\n}\n",
                )
            elif destination == "/etc/xdg/mimeapps.list":
                self.assertEqual(
                    text,
                    "[Default Applications]\n"
                    "application/pdf=org.gnome.Evince.desktop;\n\n",
                )
                self.assertIn("application/pdf", provisioner)
                self.assertIn("org.gnome.Evince.desktop;", provisioner)
            else:
                self.assertIn(text.strip("\n"), provisioner)

    def test_desktop_task_installs_its_tasksel_descriptor(self):
        rows = [row for row in install_map() if row[0] == "task-pleb-desktop"]
        self.assertEqual(rows, [
            ("task-pleb-desktop", "0644", "debian/desktop/pleb-desktop.desc", TASKSEL_DESC),
        ])
        self.assertEqual((ROOT / rows[0][2]).read_text(),
                         "Task: pleb-desktop\nParent: desktop\nRelevance: 2\n"
                         "Key:\n  task-pleb-desktop\nSection: user\n")

    def test_provisioner_preserves_the_packaged_portal_configuration(self):
        provisioner = (ROOT / "provision/plebian-os-provision.sh").read_text()
        destination = "/etc/xdg-desktop-portal/pleb-portals.conf"
        assignment = f"PORTALS_CONF={destination}\n"
        start = provisioner.index(assignment) + len(assignment)
        end = provisioner.index("\n# System defaults", start)
        script = 'PORTALS_CONF=$1 PACKAGED_PLEB=$2 DRY_RUN=$3\nlog() { echo "$*"; }\n' + provisioner[start:end]
        default = (ROOT / DROPINS[destination]).read_text()
        with tempfile.TemporaryDirectory() as tmp:
            portal = Path(tmp) / "pleb-portals.conf"
            for packaged, dry_run in (("1", "0"), ("1", "1"), ("0", "1"), ("0", "0")):
                with self.subTest(packaged=packaged, dry_run=dry_run):
                    portal.write_text("local choice\n")
                    result = subprocess.run(["bash", "-euc", script, "sh", str(portal), packaged, dry_run],
                                            capture_output=True, text=True, check=True)
                    if packaged == "1":
                        self.assertIn("plebian-desktop-base already owns", result.stdout)
                    expected = default if (packaged, dry_run) == ("0", "0") else "local choice\n"
                    self.assertEqual(portal.read_text(), expected)

    def test_the_keyring_package_ships_only_the_public_archive_key(self):
        rows = [row for row in install_map() if row[0] == KEYRING]
        self.assertEqual(rows, [(
            KEYRING, "0644", "debian/keyring/plebian-archive-keyring.gpg",
            "/usr/share/keyrings/plebian-archive-keyring.gpg",
        )])
        data = (ROOT / rows[0][2]).read_bytes()
        tags, bodies, at = [], [], 0
        while at < len(data):                     # OpenPGP packets, RFC 4880 4.2
            head = data[at]
            self.assertTrue(head & 0x80)
            if head & 0x40:
                tag, first = head & 0x3F, data[at + 1]
                if first < 192:
                    size, used = first, 2
                elif first < 224:
                    size, used = ((first - 192) << 8) + data[at + 2] + 192, 3
                else:
                    self.assertEqual(first, 255)
                    size, used = int.from_bytes(data[at + 2:at + 6], "big"), 6
            else:
                tag, kind = (head >> 2) & 0x0F, head & 0x03
                self.assertLess(kind, 3)
                width = (1, 2, 4)[kind]
                size, used = int.from_bytes(data[at + 1:at + 1 + width], "big"), 1 + width
            tags.append(tag)
            bodies.append(data[at + used:at + used + size])
            at += used + size
        self.assertEqual(at, len(data))
        self.assertEqual(tags[0], 6, "first packet is not a public key")
        self.assertEqual(tags.count(6), 1, "more than one primary key")
        self.assertNotIn(5, tags, "secret key packet")
        self.assertNotIn(7, tags, "secret subkey packet")
        self.assertIn(14, tags, "no signing subkey")
        body = bodies[0]
        self.assertEqual(body[0], 4, "not a version 4 key")
        digest = hashlib.sha1(b"\x99" + len(body).to_bytes(2, "big") + body)
        self.assertEqual(digest.hexdigest().upper(), KEY_FINGERPRINT)

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
        self.assertEqual(declared, PACKAGES | METAPACKAGES)
        self.assertEqual({package for package, _, _, _ in install_map()}, PACKAGES | {"task-pleb-desktop"})
        desktop = next(block for block in control.split("\n\n")
                       if block.startswith("Package: pleb-desktop\n"))
        deps = re.search(r"^Depends: (.*(?:\n [^\n]*)*)", desktop, re.MULTILINE)
        self.assertEqual({item.strip() for item in deps[1].split(",")}, {
            "kilix (>= 0.2.3+packaging14)", "kilix-95 (>= 0.2.3+packaging3)",
            "kilix-amp (>= 0.20261029+packaging3)", "kilix-content (>= 0.4.0+packaging3)",
            "kilix-multiplexer", "kilix-needle (>= 0.20261116+packaging6)", "pleb",
            "accountsservice", "lightdm", "lightdm-gtk-greeter", "pulseaudio",
            "pulseaudio-utils", "python3-venv", "xserver-xorg",
            "plebian-desktop-base (= ${binary:Version})", "${misc:Depends}",
        })
        self.assertIn("Depends: pleb-desktop (= ${binary:Version}), ${misc:Depends}",
                      control)

    def test_checker_visits_metapackages_and_rejects_unmapped_members(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            debian, build, output = (root / name for name in ("debian", "build", "output"))
            for directory in (debian, build, output):
                directory.mkdir()
            package = "pleb-desktop"
            (debian / "control").write_text(f"Source: fixture\n\nPackage: {package}\n")
            (debian / "install-map").write_text("")
            checker = build / "check-debs.py"
            shutil.copyfile(ROOT / "build" / checker.name, checker)
            stage = root / "package"
            control = stage / "DEBIAN/control"
            control.parent.mkdir(parents=True)
            control.parent.chmod(0o755)
            control.write_text(
                f"Package: {package}\nVersion: 1\nArchitecture: all\n"
                "Maintainer: Test <test@example.invalid>\nDescription: test fixture\n"
            )
            doc = stage / "usr/share/doc" / package / "copyright"
            doc.parent.mkdir(parents=True)
            doc.write_text("fixture\n")

            for member in (None, "opt", "opt/unlisted"):
                with self.subTest(member=member):
                    if member == "opt":
                        (stage / member).mkdir()
                    elif member:
                        (stage / member).touch()
                    built = subprocess.run(["dpkg-deb", "--root-owner-group", "--build", stage, output],
                                           text=True, capture_output=True)
                    self.assertEqual(built.returncode, 0, built.stderr)
                    result = subprocess.run([sys.executable, checker, output],
                                            text=True, capture_output=True)
                    self.assertEqual(result.returncode, int(member is not None), result.stdout)
                    if member:
                        self.assertIn(f"{package}: unlisted file /{member}", result.stdout)

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
