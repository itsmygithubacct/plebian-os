import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('zell_runtime', ROOT/'provision/install-zell-runtime.py')
runtime = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(runtime)
ARCHIVE = ROOT/'provision/bundles/zell-0.1.1-x86_64.tar.xz'
PIN = ROOT/'provision/zell-runtime.json'


class ZellRuntimeTests(unittest.TestCase):
    def test_real_carrier_installs_offline_with_complete_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = runtime.install(ARCHIVE, PIN, root/'app', root/'bin', root/'units')
            self.assertEqual(manifest['version'], '0.1.1')
            self.assertTrue((root/'bin/zell').is_file())
            for name in ('zell_os','zell_system','zell_files','zell_schedule','zell_devices','zell_audio'):
                self.assertTrue((root/'app/tools'/(name+'.py')).is_file())
            unit = (root/'units/kilix-secrets.service').read_text()
            self.assertIn(str(root/'app/libexec/kilix-secretsd'), unit)
            self.assertIn('ProtectSystem=strict', unit)
            self.assertFalse((root/'app/state').exists())
            self.assertFalse((root/'app/vault').exists())

    def test_corrupt_bundle_leaves_previous_install_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); app = root/'app'; app.mkdir()
            (app/'existing').write_text('unchanged')
            bad = root/'bad.tar.xz'; bad.write_bytes(b'bad')
            with self.assertRaisesRegex(ValueError, 'size mismatch'):
                runtime.install(bad, PIN, app)
            self.assertEqual((app/'existing').read_text(), 'unchanged')

    def test_pinned_archive_still_refuses_links_and_path_traversal(self):
        for name, kind in [('../outside', tarfile.REGTYPE), ('link', tarfile.SYMTYPE), ('hard', tarfile.LNKTYPE)]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); bundle = root/'bad.tar.xz'
                with tarfile.open(bundle, 'w:xz') as archive:
                    info = tarfile.TarInfo(name); info.type=kind; info.mode=0o644; info.linkname='/tmp/outside'
                    archive.addfile(info, io.BytesIO())
                pin = json.loads(PIN.read_text())
                pin.update(bytes=bundle.stat().st_size, sha256=hashlib.sha256(bundle.read_bytes()).hexdigest())
                path = root/'pin.json'; path.write_text(json.dumps(pin))
                stage=root/'stage'; stage.mkdir()
                with self.assertRaisesRegex(ValueError, 'Unsafe'):
                    runtime.unpack(bundle, path, stage)

    def test_image_and_first_boot_require_same_carrier(self):
        remaster = (ROOT/'build/remaster-iso.sh').read_text()
        preseed = (ROOT/'preseed/preseed.cfg').read_text()
        provision = (ROOT/'provision/plebian-os-provision.sh').read_text()
        for source in (remaster, preseed, provision):
            self.assertIn('zell-0.1.1-x86_64.tar.xz', source)
            self.assertIn('zell-runtime.json', source)
            self.assertIn('install-zell-runtime.py', source)
        self.assertIn('python3-numpy', preseed)
        deps=(ROOT/'provision/install-deps.sh').read_text()
        for package in ('upower','bluez','scrot','brightnessctl','power-profiles-daemon','nftables','wtmpdb'):
            self.assertIn(package,preseed)
            self.assertIn(package,deps)


if __name__ == '__main__':
    unittest.main()
