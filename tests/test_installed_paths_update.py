"""Installed paths for the updater and the root helpers it deploys.

The expected locations are literals. Nothing here reads them back out of
provision/plebian-os-paths.sh, so a copied block cannot agree with itself
by construction. Worker A covers the installer in tests/test_installed_paths.py.
"""
import hashlib
import re
import runpy
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
    r"|/usr/local/sbin/install-zell-runtime\.py"
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
    def run_root_block(self, fx, name, *args):
        update = (ROOT / "provision/plebian-os-update.sh").read_text()
        body = dict(heredocs(update))[name]
        return subprocess.run(
            ["bash", "-s", "--", *map(str, args)],
            input="systemctl() { :; }\nset -euo pipefail\n" + as_user(under(body, fx.root)),
            env={"PATH": "/usr/bin:/bin", "HOME": str(fx.tmp)}, capture_output=True, text=True, timeout=60)

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

    def test_source_carrier_default_and_bootstraps_use_the_installed_payload(self):
        expected = Path("/var/lib/plebian-os/payloads/source-carrier/manifest.json")
        helper = runpy.run_path(str(ROOT / "provision/plebian-os-source-carrier"))
        self.assertEqual(helper["DEFAULT"], expected)
        for script in ("plebian-os-provision.sh", "plebian-os-update.sh"):
            with self.subTest(script=script):
                source = (ROOT / "provision" / script).read_text()
                self.assertIn('[ -e "$PLEBIAN_OS_PAYLOADDIR/source-carrier/manifest.json" ]', source)
                self.assertNotIn("DATADIR/source-carrier", source)

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
        zell_helper = fx.root / "usr/sbin/install-zell-runtime.py"
        zell_helper.write_text("previous Zell helper\n")
        foreign_sbin.write_text("foreign-sbin\n")
        foreign_bin.write_text("foreign-bin\n")
        ours.write_text("ours-before\n")
        for path in (foreign_sbin, foreign_bin, ours, zell_helper):
            path.chmod(0o755)
        taken = self.run_root_block(fx, "ROOT_SNAPSHOT")
        self.assertEqual(taken.returncode, 0, taken.stderr)
        txn = Path(taken.stdout.strip().splitlines()[-1])
        copied_names = {path.name for path in txn.rglob("*") if path.is_file()}
        self.assertNotIn("not-ours", copied_names)
        copied_text = [path.read_text(errors="replace") for path in (txn / "items").iterdir() if path.is_file()]
        self.assertIn("ours-before\n", copied_text)
        ours.write_text("ours-after\n")
        zell_helper.write_text("updated Zell helper\n")
        foreign_sbin.write_text("foreign-sbin-after\n")
        foreign_bin.write_text("foreign-bin-after\n")
        # A pre-move journal has the old helper's bytes under the same numeric key.
        marker = txn / "zell-usr-sbin"
        marker.unlink()
        refused = self.run_root_block(fx, "ROOT_RESTORE", txn)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("predates the helper move", refused.stderr)
        self.assertEqual(zell_helper.read_text(), "updated Zell helper\n")
        self.assertEqual(ours.read_text(), "ours-after\n")
        marker.touch()
        restored = self.run_root_block(fx, "ROOT_RESTORE", txn)
        self.assertEqual(restored.returncode, 0, restored.stderr)
        self.assertEqual(ours.read_text(), "ours-before\n")
        self.assertEqual(zell_helper.read_text(), "previous Zell helper\n")
        self.assertEqual(stat.S_IMODE(zell_helper.stat().st_mode), 0o755)
        self.assertEqual(foreign_sbin.read_text(), "foreign-sbin-after\n")
        self.assertEqual(foreign_bin.read_text(), "foreign-bin-after\n")
        self.assertEqual(stat.S_IMODE(foreign_sbin.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE(foreign_bin.stat().st_mode), 0o755)

    def test_zell_publishes_in_usr_sbin_and_restores_original_absence(self):
        fx = Fixture(self)
        previous = fx.root / "usr/local/sbin/install-zell-runtime.py"
        previous.write_bytes(b"legacy copy")
        helper = fx.root / "usr/sbin/install-zell-runtime.py"
        taken = self.run_root_block(fx, "ROOT_SNAPSHOT")
        self.assertEqual(taken.returncode, 0, taken.stderr)
        txn = Path(taken.stdout.strip())
        provision = ROOT / "provision"
        inputs = ("install-zell-runtime.py", "zell-runtime.json", "bundles/zell-0.1.1-x86_64.tar.xz")
        digests = [hashlib.sha256((provision / name).read_bytes()).hexdigest() for name in inputs]
        for _ in range(2):
            installed = self.run_root_block(fx, "ROOT_ZELL_INSTALL", txn, provision, *digests)
            self.assertEqual(installed.returncode, 0, installed.stderr)
            self.assertEqual(helper.read_bytes(), (provision / inputs[0]).read_bytes())
            self.assertEqual(stat.S_IMODE(helper.stat().st_mode), 0o755)
            self.assertEqual(previous.read_bytes(), b"legacy copy")
        restored = self.run_root_block(fx, "ROOT_RESTORE", txn)
        self.assertEqual(restored.returncode, 0, restored.stderr)
        self.assertFalse(helper.exists())
        self.assertEqual(previous.read_bytes(), b"legacy copy")


if __name__ == "__main__":
    unittest.main()
