"""Installed paths for the updater and the root helpers it deploys.

The expected locations are literals. Nothing here reads them back out of
provision/plebian-os-paths.sh, so a copied block cannot agree with itself
by construction. Worker A covers the installer in tests/test_installed_paths.py.
"""
import re
import stat
import subprocess
import unittest
from pathlib import Path

from test_lid_update import Fixture, as_user, under


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = """\
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
EXPECTED_CONSTANTS = {
    "PLEBIAN_OS_SBINDIR": "/usr/sbin",
    "PLEBIAN_OS_BINDIR": "/usr/bin",
    "PLEBIAN_OS_LIBEXECDIR": "/usr/libexec/plebian-os",
    "PLEBIAN_OS_LIBDIR": "/usr/lib/plebian-os",
    "PLEBIAN_OS_DATADIR": "/usr/share/plebian-os",
    "PLEBIAN_OS_NOTICEDIR": "/usr/share/plebian-os/notices",
    "PLEBIAN_OS_PAYLOADDIR": "/var/lib/plebian-os/payloads",
    "PLEBIAN_OS_UNITDIR": "/usr/lib/systemd/system",
}
OWNED = (
    "provision/plebian-os-update.sh",
    "provision/plebian-os-select-closure.sh",
    "provision/plebian-os-qt-runtime",
    "provision/plebian-os-mpv-runtime",
    "provision/plebian-os-native-runtime",
    "provision/native_package.py",
    "provision/native_process.py",
    "provision/native_runtime.py",
    "provision/native_state.py",
    "provision/plebian-os-install-diarization-converter",
    "provision/plebian-os-install-encodec-converter",
    "provision/plebian-os-install-kilix-ollama-runtime",
    "provision/plebian-os-install-kilix-vulkan-tts",
    "provision/plebian-os-install-ollama-converter",
    "provision/plebian-os-passwd",
    "provision/plebian-os-ssh-server",
    "provision/plebian-os-nvidia-driver",
    "provision/plebian-os-source-carrier",
    "provision/plebian-os-waydroid-setup",
    "provision/NATIVE-RUNTIME.md",
    "build/acceptance-release-hop.sh",
    "build/acceptance-release-hop-host.sh",
)
PYTHON_WITH_CONSTANTS = (
    "provision/plebian-os-qt-runtime",
    "provision/plebian-os-source-carrier",
)
OLD_PATH = re.compile(
    r"/usr/local/sbin/plebian-os-"
    r"|/usr/local/bin/plebian-os-"
    r"|/usr/local/libexec/plebian-os"
    r"|/usr/local/share/plebian-os"
    r"|/usr/local/share/doc/plebian-os"
    r"|/etc/systemd/system/plebian-os-firstboot\.service"
)
SHARED_DIRS = ("/usr/sbin", "/usr/bin", "$PLEBIAN_OS_SBINDIR", "$PLEBIAN_OS_BINDIR")


def blocks(text):
    found = []
    start = 0
    while True:
        at = text.find("# >>> plebian-os-paths\n", start)
        if at < 0:
            return found
        end = text.find("# <<< plebian-os-paths\n", at)
        if end < 0:
            raise AssertionError("path block has no end marker")
        end += len("# <<< plebian-os-paths\n")
        found.append(text[at:end])
        start = end


def heredocs(text):
    found = []
    for match in re.finditer(r"<<'(ROOT_[A-Z_]+)'\n", text):
        name = match.group(1)
        body_at = match.end()
        end = text.find("\n" + name, body_at)
        found.append((name, text[body_at:end]))
    return found


def array_entries(text, name):
    match = re.search(rf"^[ \t]*{name}=\((.*?)\)[ \t]*$", text, re.M | re.S)
    if match is None:
        raise AssertionError(f"missing {name}")
    return re.sub(r"#.*", "", match.group(1)).split()


class InstalledPathUpdateTests(unittest.TestCase):
    def test_shell_blocks_match_the_canonical_literals(self):
        seen = 0
        for relative in OWNED:
            text = (ROOT / relative).read_text()
            copies = blocks(text)
            for copy in copies:
                self.assertEqual(copy, CANONICAL, relative)
            seen += len(copies)
            if "$PLEBIAN_OS_" in text and relative.endswith((".sh", "-runtime")):
                self.assertGreaterEqual(len(copies), 1, relative)
            for name, body in heredocs(text):
                if "$PLEBIAN_OS_" in body:
                    self.assertIn("# >>> plebian-os-paths\n", body, name)
                    self.assertEqual(blocks(body), [CANONICAL], name)
        self.assertGreaterEqual(seen, 10)

    def test_python_constants_are_the_literal_shell_values(self):
        for relative in PYTHON_WITH_CONSTANTS:
            text = (ROOT / relative).read_text()
            assigned = dict(re.findall(r'^(PLEBIAN_OS_[A-Z]+) = "([^"]*)"$', text, re.M))
            self.assertEqual(assigned, EXPECTED_CONSTANTS, relative)

    def test_owned_files_do_not_name_an_old_plebian_os_path(self):
        for relative in OWNED:
            text = (ROOT / relative).read_text()
            self.assertIsNone(OLD_PATH.search(text), relative)

    def test_shared_directories_are_not_snapshot_directories(self):
        update = (ROOT / "provision/plebian-os-update.sh").read_text()
        for name, body in heredocs(update):
            if name not in ("ROOT_SNAPSHOT", "ROOT_RESTORE"):
                continue
            for array_name in ("managed_dirs", "zell_dirs"):
                entries = array_entries(body, array_name)
                for shared in SHARED_DIRS:
                    self.assertNotIn(shared, entries, f"{name} {array_name}")
        for forbidden in (
            "cp -a -- /usr/sbin",
            "cp -a -- /usr/bin",
            'cp -a -- "$PLEBIAN_OS_SBINDIR"',
            'cp -a -- "$PLEBIAN_OS_BINDIR"',
            "cp -a -- $PLEBIAN_OS_SBINDIR\n",
            "cp -a -- $PLEBIAN_OS_BINDIR\n",
        ):
            self.assertNotIn(forbidden, update)

    def test_snapshot_and_restore_leave_foreign_files_in_shared_directories(self):
        fx = Fixture(self)
        foreign_sbin = fx.root / "usr/sbin/not-ours"
        foreign_bin = fx.root / "usr/bin/not-ours"
        ours = fx.root / "usr/sbin/plebian-os-passwd"
        foreign_sbin.write_text("foreign-sbin\n")
        foreign_bin.write_text("foreign-bin\n")
        ours.write_text("ours-before\n")
        for path in (foreign_sbin, foreign_bin, ours):
            path.chmod(0o755)
        text = (ROOT / "provision/plebian-os-update.sh").read_text()
        snap = next(body for name, body in heredocs(text) if name == "ROOT_SNAPSHOT")
        rest = next(body for name, body in heredocs(text) if name == "ROOT_RESTORE")
        env = {"PATH": "/usr/bin:/bin", "HOME": str(fx.tmp)}
        taken = subprocess.run(
            ["bash", "-c", "set -euo pipefail\n" + as_user(under(snap, fx.root))],
            env=env, capture_output=True, text=True)
        self.assertEqual(taken.returncode, 0, taken.stderr)
        txn = Path(taken.stdout.strip().splitlines()[-1])
        copied_names = {path.name for path in txn.rglob("*") if path.is_file()}
        self.assertNotIn("not-ours", copied_names)
        copied_text = [path.read_text(errors="replace") for path in (txn / "items").iterdir() if path.is_file()]
        self.assertIn("ours-before\n", copied_text)
        ours.write_text("ours-after\n")
        foreign_sbin.write_text("foreign-sbin-after\n")
        foreign_bin.write_text("foreign-bin-after\n")
        restored = subprocess.run(
            ["bash", "-s", "--", str(txn)],
            input="systemctl() { :; }\nset -euo pipefail\n" + as_user(under(rest, fx.root)),
            env=env, capture_output=True, text=True)
        self.assertEqual(restored.returncode, 0, restored.stderr)
        self.assertEqual(ours.read_text(), "ours-before\n")
        self.assertEqual(foreign_sbin.read_text(), "foreign-sbin-after\n")
        self.assertEqual(foreign_bin.read_text(), "foreign-bin-after\n")
        self.assertEqual(stat.S_IMODE(foreign_sbin.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE(foreign_bin.stat().st_mode), 0o755)


if __name__ == "__main__":
    unittest.main()
