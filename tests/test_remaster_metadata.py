"""Exercise the real cpio and ISO writers across caller permission masks."""
import gzip
import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "build/remaster-iso.sh").read_text()


def section(start, end):
    offset = SOURCE.index(start)
    return SOURCE[offset:SOURCE.index(end, offset)]


def run(argv, **kwargs):
    return subprocess.run(argv, check=True, capture_output=True, **kwargs)


@unittest.skipUnless(all(shutil.which(x) for x in ("cpio", "gzip", "xorriso")),
                     "real archive tools are required")
class MetadataReproducibilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def initial_initrd(self):
        source = self.root / "debian"
        source.mkdir()
        files = {
            "var/lib/dpkg/info/main-menu.templates": b"Description: Debian installer main menu\n",
            "usr/share/graphics/logo_debian.png": b"original light logo",
            "usr/share/graphics/logo_debian_dark.png": b"original dark logo",
            "usr/share/graphics/logo_installer.png": b"retained installer light logo",
            "usr/share/graphics/logo_installer_dark.png": b"retained installer dark logo",
        }
        for name, data in files.items():
            p = source / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
            p.chmod(0o644)
            os.utime(p, (0, 0))
        raw = run(["cpio", "--null", "--create", "--format=newc", "--owner=0:0",
                   "--reproducible", "--quiet"], cwd=source,
                  input=b"\0".join(n.encode() for n in files) + b"\0").stdout
        return gzip.compress(raw, mtime=0)

    def test_graphical_overlay_bytes_do_not_inherit_caller_umask(self):
        original = self.initial_initrd()
        function = section("brand_graphical_installer() {", "\nconfigure_boot_menu_policy() {")
        results = []
        for mask in ("0022", "0077"):
            root = self.root / mask
            work = root / "work"
            extract = root / "extract"
            work.mkdir(parents=True)
            initrd = extract / "install.amd/gtk/initrd.gz"
            initrd.parent.mkdir(parents=True)
            initrd.write_bytes(original)
            initrd.chmod(0o644)
            env = dict(os.environ, WORK=str(work), EXTRACT=str(extract),
                       INSTALLER_ASSETS=str(ROOT / "assets/installer"),
                       INSTALLER_BRANDER=str(ROOT / "build/brand-installer.py"),
                       PLEBIAN_OS_VERSION="9.8.7")
            run(["bash", "-c", "set -euo pipefail\numask " + mask + "\n" +
                 function + "\nbrand_graphical_installer\n"], env=env)
            generated = initrd.read_bytes()
            self.assertEqual(generated[:len(original)], original)
            overlay = gzip.decompress(generated[len(original):])
            template = run(["cpio", "-i", "--quiet", "--to-stdout",
                            "var/lib/dpkg/info/main-menu.templates"], input=overlay).stdout
            self.assertIn(b"Plebian-OS 9.8.7 installer main menu", template)
            overlay_template = work / "gtk-banner-overlay/var/lib/dpkg/info/main-menu.templates"
            self.assertEqual(stat.S_IMODE(overlay_template.stat().st_mode), 0o644)
            results.append(generated)
        self.assertEqual(results[0], results[1])

    def test_iso_bytes_and_public_metadata_ignore_source_permissions(self):
        command = section('xorriso -as mkisofs -V "$PLEBIAN_OS_ISO_VOLUME_ID"',
                          "\n\n# Refuse to replace a known-good output")
        images = []
        for mask in ("0022", "0077"):
            root = self.root / mask
            root.mkdir()
            extract = root / "tree"
            env = dict(os.environ, EXTRACT=str(extract), OUT_TMP=str(root / "image.iso"),
                       PLEBIAN_OS_ISO_VOLUME_ID="REPRO TEST", SOURCE_DATE_EPOCH="1700000000",
                       ISO_SOURCE_DATE_XORRISO="2023111422132000")
            script = ('set -euo pipefail\numask ' + mask + '\n'
                      'mkdir -p "$EXTRACT/public"\n'
                      'printf config > "$EXTRACT/public/config"\n'
                      'printf executable > "$EXTRACT/public/run"\n'
                      'chmod +x "$EXTRACT/public/run"\n'
                      'mkisofs_argv=()\n' + command + '\n')
            run(["bash", "-c", script], env=env)
            image = root / "image.iso"
            images.append(image.read_bytes())
            listing = run(["xorriso", "-indev", str(image), "-find", "/", "-exec", "lsdl", "--"], text=True).stdout
            rows = {line.split()[-1]: line.split() for line in listing.splitlines()}
            self.assertEqual(rows["'/public/config'"][0], "-r--r--r--")
            self.assertEqual(rows["'/public/run'"][0], "-r-xr-xr-x")
            self.assertEqual(rows["'/public'"][0], "dr-xr-xr-x")
            self.assertTrue(all(row[2:4] == ["0", "0"] for row in rows.values()))
            # Normalization applies to the image, without widening private
            # workspace or output-file permissions on the build machine.
            expected = 0o600 if mask == "0077" else 0o644
            self.assertEqual(stat.S_IMODE((extract / "public/config").stat().st_mode), expected)
            self.assertEqual(stat.S_IMODE(image.stat().st_mode), expected)
        self.assertEqual(hashlib.sha256(images[0]).digest(), hashlib.sha256(images[1]).digest())


if __name__ == "__main__":
    unittest.main()
