"""The installed path table is copied verbatim and the old locations are gone.

Expected values below are literals. This file does not read them out of the
code under test. Worker B's files still name the old locations until that
branch lands, so the absence check covers worker A's files only. Every copy
of the marker block, in either worker's tree, has to match this literal.
"""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CANONICAL_BLOCK = """\
# >>> plebian-os-paths
PLEBIAN_OS_SBINDIR=/usr/sbin
PLEBIAN_OS_BINDIR=/usr/bin
PLEBIAN_OS_LIBEXECDIR=/usr/libexec/plebian-os
PLEBIAN_OS_LIBDIR=/usr/lib/plebian-os
PLEBIAN_OS_DATADIR=/usr/share/plebian-os
PLEBIAN_OS_NOTICEDIR=/usr/share/plebian-os/notices
PLEBIAN_OS_PAYLOADDIR=/var/lib/plebian-os/payloads
PLEBIAN_OS_UNITDIR=/usr/lib/systemd/system
# <<< plebian-os-paths
"""

PYTHON_CONSTANTS = (
    'PLEBIAN_OS_SBINDIR = "/usr/sbin"',
    'PLEBIAN_OS_BINDIR = "/usr/bin"',
    'PLEBIAN_OS_LIBEXECDIR = "/usr/libexec/plebian-os"',
    'PLEBIAN_OS_LIBDIR = "/usr/lib/plebian-os"',
    'PLEBIAN_OS_DATADIR = "/usr/share/plebian-os"',
    'PLEBIAN_OS_NOTICEDIR = "/usr/share/plebian-os/notices"',
    'PLEBIAN_OS_PAYLOADDIR = "/var/lib/plebian-os/payloads"',
    'PLEBIAN_OS_UNITDIR = "/usr/lib/systemd/system"',
)

# Helpers that install or check these paths. Each defines all eight names.
PYTHON_FILES = (
    "provision/install-default-models.py",
    "provision/install-image-models.py",
    "build/build_vm_image.py",
)

# Deployed shell that carries the table. Other copies are checked wherever
# the markers show up under the trees below.
REQUIRED_BLOCK_FILES = (
    "provision/plebian-os-paths.sh",
    "provision/plebian-os-provision.sh",
)

# Worker A's files, plus the greeter drop-in the provisioner pins by hash.
# The absence scan stays inside this list so worker B's unmoved files do
# not fail the suite on this branch.
OWNED_FILES = (
    "provision/plebian-os-paths.sh",
    "provision/plebian-os-provision.sh",
    "provision/install-deps.sh",
    "provision/plebian-os-firstboot.service",
    "provision/plebian-os-firstboot-attempt",
    "provision/plebian-os-offline-install",
    "provision/plebian-os-record-installed-user",
    "provision/install-default-models.py",
    "provision/install-image-models.py",
    "provision/install-neuronte.py",
    "provision/install-zell-runtime.py",
    "provision/stage-command-model.py",
    "provision/lightdm-gtk-greeter.conf",
    "preseed/preseed.cfg",
    "build/remaster-iso.sh",
    "build/build_vm_image.py",
    "build/make-usb.sh",
    "build/build_usb_image.py",
    "build/acceptance-source.py",
    "build/acceptance-vm.sh",
    "build/acceptance-release-iso.sh",
    "bootstrap.sh",
    "README.md",
    "UPGRADING.md",
    "RELEASING.md",
)

BLOCK_ROOTS = ("provision", "preseed", "build")
BLOCK_FILES = ("bootstrap.sh", "README.md", "UPGRADING.md", "RELEASING.md")

# Left column of the path table, plus the installer script that moved with sbin.
OLD_PATHS = (
    "/usr/local/sbin/plebian-os-",
    "/usr/local/bin/plebian-os-update",
    "/usr/local/bin/plebian-os-select-closure",
    "/usr/local/bin/plebian-os-nvidia-driver",
    "/usr/local/libexec/plebian-os",
    "/usr/local/share/plebian-os",
    "/usr/local/share/doc/plebian-os",
    "/etc/systemd/system/plebian-os-firstboot.service",
    "/usr/local/sbin/install-zell-runtime.py",
)

# One historical sentence in UPGRADING.md names the v9 model documents that
# an earlier image left on disk. That sentence stays. Nothing else may.
HISTORICAL_FILE = "UPGRADING.md"
HISTORICAL_PATH = (
    "/usr/local/share/doc/plebian-os/models/lfm2-kilix-commands-20261106-v9/"
)

START = "# >>> plebian-os-paths\n"
END = "# <<< plebian-os-paths\n"
CONSTANT_LINE = re.compile(
    r"^PLEBIAN_OS_(?:SBINDIR|BINDIR|LIBEXECDIR|LIBDIR|DATADIR|NOTICEDIR|PAYLOADDIR|UNITDIR)\s*="
)


def path_blocks(text):
    blocks = []
    rest = text
    while True:
        start = rest.find(START)
        if start < 0:
            break
        end = rest.find(END, start)
        if end < 0:
            raise AssertionError("path block marker is not closed")
        end += len(END)
        blocks.append(rest[start:end])
        rest = rest[end:]
    return blocks


def block_sources():
    found = []
    for relative in BLOCK_ROOTS:
        root = ROOT / relative
        for path in sorted(root.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            if path.suffix == ".pyc":
                continue
            found.append(path)
    for relative in BLOCK_FILES:
        found.append(ROOT / relative)
    return found


class InstalledPathTableTests(unittest.TestCase):
    def test_every_path_block_matches_the_literal_table(self):
        seen = []
        for path in block_sources():
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            blocks = path_blocks(text)
            for block in blocks:
                self.assertEqual(block, CANONICAL_BLOCK, path)
            if blocks:
                seen.append(path.relative_to(ROOT).as_posix())
            uses_table = (
                "$PLEBIAN_OS_SBINDIR" in text or "PLEBIAN_OS_SBINDIR=/" in text
            )
            if uses_table:
                # A file may carry several copies: each script the updater
                # and the selector hand to root is self-contained.
                self.assertTrue(blocks, path)
        for relative in REQUIRED_BLOCK_FILES:
            self.assertIn(relative, seen, relative)

    def test_python_constants_match_the_shell_values(self):
        expected = set(PYTHON_CONSTANTS)
        for relative in OWNED_FILES:
            if not relative.endswith(".py"):
                continue
            lines = [
                line.strip()
                for line in (ROOT / relative).read_text(encoding="utf-8").splitlines()
                if CONSTANT_LINE.match(line.strip())
            ]
            if relative in PYTHON_FILES:
                self.assertEqual(set(lines), expected, relative)
                self.assertEqual(len(lines), len(expected), relative)
            elif lines:
                self.assertEqual(set(lines), expected, relative)

    def test_owned_files_do_not_name_an_old_plebian_os_path(self):
        for relative in OWNED_FILES:
            text = (ROOT / relative).read_text(encoding="utf-8")
            if relative == HISTORICAL_FILE:
                self.assertEqual(text.count(HISTORICAL_PATH), 1, relative)
                text = text.replace(HISTORICAL_PATH, "", 1)
            for old in OLD_PATHS:
                self.assertNotIn(old, text, "%s still names %s" % (relative, old))

    def test_firstboot_unit_lines_are_the_new_paths(self):
        text = (ROOT / "provision/plebian-os-firstboot.service").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "ExecStart=/usr/sbin/plebian-os-firstboot-attempt run "
            "/usr/sbin/plebian-os-provision\n",
            text,
        )
        self.assertIn(
            "ExecCondition=/usr/sbin/plebian-os-firstboot-attempt check\n",
            text,
        )
        self.assertIn(
            "ExecStartPost=/usr/sbin/plebian-os-firstboot-attempt success\n",
            text,
        )


if __name__ == "__main__":
    unittest.main()
