"""Exercise the one-way converter in a temporary root with inert curl, apt and systemd."""
from contextlib import redirect_stderr
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import hashlib
import io
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "provision/plebian-os-convert-0.2.3"
loader = SourceFileLoader("convert_023", str(SCRIPT))
converter = module_from_spec(spec_from_loader(loader.name, loader))
loader.exec_module(converter)
KEY = (REPO / "debian/keyring/plebian-archive-keyring.gpg").read_bytes()
MARKER = "usr/local/share/plebian-os/VERSION"
UPDATER = "usr/local/bin/plebian-os-update"
SOURCE = "etc/apt/sources.list.d/plebian.sources"


class Convert023Tests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.write(MARKER, b"0.2.3\n")
        self.write(UPDATER, b"old updater")
        self.calls = []
        self.download = KEY
        self.fail = None

    def write(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(0o644)
        return path

    def run_command(self, argv, **kwargs):
        self.assertTrue(kwargs["check"])
        self.calls.append(argv)
        if argv[0] == "/usr/bin/curl":
            self.assertEqual(argv[-1], "https://itsmygithubacct.github.io/plebian-apt/plebian-archive-keyring.gpg")
            return subprocess.CompletedProcess(argv, 0, stdout=self.download)
        if argv[0] == "/usr/bin/apt-get":
            self.assertEqual((self.root / UPDATER).read_bytes(), b"old updater")
            self.assertEqual((self.root / converter.KEY).read_bytes(), KEY)
            source = (self.root / SOURCE).read_text().splitlines()
            self.assertIn("URIs: https://itsmygithubacct.github.io/plebian-apt", source)
            self.assertIn("Suites: trixie", source)
            self.assertIn("Components: main", source)
            self.assertIn("Signed-By: /usr/share/keyrings/plebian-archive-keyring.gpg", source)
            if self.fail in argv:
                raise subprocess.CalledProcessError(100, argv)
        else:
            self.assertEqual(argv, ["/usr/bin/systemctl", "daemon-reload"])
        return subprocess.CompletedProcess(argv, 0)

    def test_cli_requires_explicit_backup_acknowledgement_before_access(self):
        for argv in ([], ["--acknowledge"]):
            with self.subTest(argv=argv), patch.object(converter, "convert") as convert:
                output = io.StringIO()
                with redirect_stderr(output), patch.object(converter.os, "geteuid") as uid:
                    with self.assertRaises(SystemExit) as caught:
                        converter.main(argv)
                self.assertEqual(caught.exception.code, 2)
                uid.assert_not_called()
                convert.assert_not_called()
                if not argv:
                    for text in ("backup or VM snapshot", "no transactional rollback", "--acknowledge-backup"):
                        self.assertIn(text, output.getvalue())

    def test_acknowledged_cli_requires_root(self):
        with redirect_stderr(io.StringIO()), patch.object(converter.os, "geteuid", return_value=1000):
            with patch.object(converter, "convert") as convert, self.assertRaises(SystemExit) as caught:
                converter.main(["--acknowledge-backup"])
            self.assertEqual(caught.exception.code, 1)
            convert.assert_not_called()

    def test_install_then_retire_only_repository_files(self):
        owned = (UPDATER, "usr/local/bin/plebian-os-select-closure", "usr/local/bin/plebian-os-nvidia-driver",
                 "usr/local/sbin/plebian-os-source-carrier", "usr/local/sbin/plebian-os-provision",
                 "usr/local/libexec/plebian-os/native_runtime.py", "usr/local/share/plebian-os/ollama-release.env",
                 "usr/local/share/plebian-os/wallpapers/plebian-os.png",
                 "usr/local/share/doc/plebian-os/installer/ATTRIBUTION.md")
        for name in owned[1:]:
            self.write(name, b"old OS copy")
        preserved = ("home/pleb/.config/pleb/settings", "home/pleb/.local/share/kilix/apps/demo",
                     "home/pleb/.local/gpu_terminal/plebian-os/.git/HEAD",
                     "srv/old-checkout/.git/config", "etc/pleb/session.env",
                     "etc/apt/preferences.d/plebian-os-qt-runtime", "etc/systemd/system/plebian-os-firstboot.service",
                     "usr/local/bin/plebian-os-custom", "usr/local/bin/zell",
                     "usr/local/share/plebian-os/default-models.tar.xz", "usr/local/share/kilix-zell/app",
                     "usr/local/share/doc/plebian-os/installer/operator-note", "usr/local/libexec/plebian-os/custom.py")
        for name in preserved:
            self.write(name, name.encode()).chmod(0o640)
        linked = self.root / "usr/local/sbin/plebian-os-passwd"
        linked.symlink_to(self.root / preserved[0])
        helper = (REPO / "provision/install-zell-runtime.py").read_bytes()
        self.write("usr/local/sbin/install-zell-runtime.py", helper).chmod(0o755)
        self.write("usr/local/share/plebian-os/zell-runtime.json", b"release pin")
        self.write("usr/local/share/doc/plebian-os/espeak-ng/espeakng-loader-0.2.4-LICENSE", b"retain licence")

        converter.convert(self.root, self.run_command)

        self.assertEqual([call[0] for call in self.calls], ["/usr/bin/curl", "/usr/bin/apt-get", "/usr/bin/apt-get"])
        self.assertEqual(self.calls[1][-1], "update")
        for arg in ("install", "--no-remove", "plebian-archive-keyring", "plebian-os-firstboot",
                    "plebian-os-tools", "task-pleb-desktop"):
            self.assertIn(arg, self.calls[2])
        for name in (*owned, MARKER, linked, "usr/local/sbin/install-zell-runtime.py",
                     "usr/local/share/plebian-os/zell-runtime.json",
                     "usr/local/share/doc/plebian-os/espeak-ng/espeakng-loader-0.2.4-LICENSE"):
            self.assertFalse(os.path.lexists(self.root / name), name)
        for name in preserved:
            path = self.root / name
            self.assertEqual(path.read_bytes(), name.encode())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)
        self.assertEqual((self.root / "usr/sbin/install-zell-runtime.py").read_bytes(), helper)
        self.assertEqual(stat.S_IMODE((self.root / "usr/sbin/install-zell-runtime.py").stat().st_mode), 0o755)
        self.assertEqual((self.root / "usr/share/plebian-os/zell-runtime.json").read_bytes(), b"release pin")
        self.assertEqual((self.root / "usr/share/plebian-os/notices/espeak-ng/espeakng-loader-0.2.4-LICENSE").read_bytes(),
                         b"retain licence")
        self.assertEqual(stat.S_IMODE((self.root / "usr/share/plebian-os/notices/espeak-ng").stat().st_mode), 0o755)

    def test_package_failure_preserves_legacy_files_and_acknowledged_retry_works(self):
        for phase in ("update", "install"):
            self.calls.clear()
            self.fail = phase
            with self.subTest(phase=phase), self.assertRaises(subprocess.CalledProcessError):
                converter.convert(self.root, self.run_command)
            self.assertEqual((self.root / UPDATER).read_bytes(), b"old updater")
            self.assertEqual((self.root / MARKER).read_bytes(), b"0.2.3\n")
            if phase == "update":
                self.assertFalse(any("install" in call for call in self.calls))
        self.calls.clear()
        self.fail = None
        converter.convert(self.root, self.run_command)
        self.assertEqual(self.calls[0][0], "/usr/bin/apt-get")
        self.assertFalse((self.root / UPDATER).exists())

    def test_foreign_version_and_wrong_key_are_refused_before_apt(self):
        self.write(MARKER, b"0.2.2\n")
        with self.assertRaisesRegex(ValueError, "0.2.3"):
            converter.convert(self.root, self.run_command)
        self.assertEqual(self.calls, [])
        self.write(MARKER, b"0.2.3\n")
        self.download = b"wrong signing key"
        with self.assertRaisesRegex(ValueError, "pinned release key"):
            converter.convert(self.root, self.run_command)
        self.assertEqual([call[0] for call in self.calls], ["/usr/bin/curl"])
        self.assertFalse((self.root / converter.KEY).exists())
        self.assertFalse((self.root / SOURCE).exists())
        self.assertTrue((self.root / UPDATER).exists())

    def test_existing_apt_source_and_symlink_targets_are_preserved(self):
        outside = self.write("home/pleb/source", b"operator configuration")
        existing = self.write(SOURCE, b"operator configuration")
        for is_link in (False, True):
            if is_link:
                existing.unlink()
                existing.symlink_to(outside)
            with self.subTest(is_link=is_link), self.assertRaises((OSError, ValueError)):
                converter.convert(self.root, self.run_command)
            self.assertEqual(existing.read_bytes(), b"operator configuration")
            self.assertEqual(existing.is_symlink(), is_link)
            self.assertFalse(any(call[0] == "/usr/bin/apt-get" for call in self.calls))
            self.assertTrue((self.root / UPDATER).exists())

    def test_stock_unit_keeps_enablement_and_retries_failed_daemon_reload(self):
        stock = b"[Service]\nExecStart=/usr/local/sbin/plebian-os-firstboot-attempt\n"
        unit = self.write(converter.FIRSTBOOT, stock)
        wants = unit.parent / "multi-user.target.wants" / unit.name
        wants.parent.mkdir()
        wants.symlink_to("../" + unit.name)

        def fail_reload(argv, **kwargs):
            result = self.run_command(argv, **kwargs)
            if argv[0] == "/usr/bin/systemctl":
                raise subprocess.CalledProcessError(1, argv)
            return result

        with patch.object(converter, "STOCK_FIRSTBOOT_SHA256", hashlib.sha256(stock).hexdigest()):
            with self.assertRaises(subprocess.CalledProcessError):
                converter.convert(self.root, fail_reload)
            self.assertEqual(os.readlink(unit), "/usr/lib/systemd/system/plebian-os-firstboot.service")
            self.assertEqual(os.readlink(wants), "../" + unit.name)
            self.assertTrue((self.root / MARKER).is_file())
            self.calls.clear()
            converter.convert(self.root, self.run_command)
        self.assertEqual(self.calls[-1], ["/usr/bin/systemctl", "daemon-reload"])
        self.assertFalse((self.root / MARKER).exists())

    def test_admin_firstboot_mask_is_preserved(self):
        unit = self.root / converter.FIRSTBOOT
        unit.parent.mkdir(parents=True)
        unit.symlink_to("/dev/null")
        converter.convert(self.root, self.run_command)
        self.assertEqual(os.readlink(unit), "/dev/null")
        self.assertFalse(any(call[0] == "/usr/bin/systemctl" for call in self.calls))

    def test_conflicting_iso_destination_keeps_both_copies(self):
        source = self.write("usr/local/share/plebian-os/zell-runtime.json", b"old release pin")
        target = self.write("usr/share/plebian-os/zell-runtime.json", b"operator pin")
        with self.assertRaisesRegex(ValueError, "preserving"):
            converter.convert(self.root, self.run_command)
        self.assertEqual(target.read_bytes(), b"operator pin")
        self.assertEqual(source.read_bytes(), b"old release pin")
        self.assertTrue((self.root / MARKER).exists())

    def test_foreign_tree_inside_a_legacy_path_is_preserved(self):
        leaf = self.write("home/pleb/tree/plebian-os-provision", b"operator copy")
        (self.root / "usr/local/sbin").symlink_to(leaf.parent, target_is_directory=True)
        with self.assertRaises(OSError):
            converter.convert(self.root, self.run_command)
        self.assertEqual(leaf.read_bytes(), b"operator copy")
        self.assertTrue((self.root / MARKER).exists())
        (self.root / "usr/local/sbin").unlink()
        child = self.write("usr/local/sbin/plebian-os-provision/child", b"directory contents")
        with self.assertRaisesRegex(ValueError, "preserving"):
            converter.convert(self.root, self.run_command)
        self.assertEqual(child.read_bytes(), b"directory contents")
        self.assertTrue((self.root / MARKER).exists())

    def test_package_map_installs_the_executable_in_sbin(self):
        rows = [line.split() for line in (REPO / "debian/install-map").read_text().splitlines()
                if line.startswith("plebian-os-tools") and SCRIPT.name in line]
        self.assertEqual(rows, [["plebian-os-tools", "0755", "provision/" + SCRIPT.name, "/usr/sbin/" + SCRIPT.name]])
        self.assertEqual(stat.S_IMODE(SCRIPT.stat().st_mode), 0o755)


if __name__ == "__main__":
    unittest.main()
