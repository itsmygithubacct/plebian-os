"""Basic Pitch is on the image, and both it and LFM2 install by default."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'image_models_installer', ROOT / 'provision/install-image-models.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)

ONNX = '2c3c1d144bfa61ad236e92e169c13535c880469a12a047d4e73451f2c059a0ec'
LICENCE = '929c910bae2152fa87199a5d0660e09263419b7eee6d4b301d05ee2aaf211c37'
NOTICE = 'b810e55c0e3b520fabb45fc2ccc74880187bf84e309971968541cc812dcde905'
MANIFEST = '231f6d8ed0fdfcc4f230f0c220ac2d5f260b3e7bc1edb889a0115f6751bf6d5b'


def _archive(members):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w:xz') as archive:
        for name, data, kind in members:
            info = tarfile.TarInfo(name)
            info.type = kind
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return stream.getvalue()


class VendoredBasicPitchTests(unittest.TestCase):
    def test_pin_matches_the_catalogued_files_and_archive(self):
        pin = json.loads((ROOT / 'provision/basic-pitch-model.json').read_text())
        archive = ROOT / 'provision/bundles/basic-pitch-icassp-2022-onnx.tar.xz'
        self.assertEqual(pin['files']['models/nmp.onnx']['sha256'], ONNX)
        self.assertEqual(pin['files']['notices/LICENSE-apache-2.0.txt']['sha256'], LICENCE)
        self.assertEqual(pin['files']['notices/NOTICE-basic-pitch.txt']['sha256'], NOTICE)
        self.assertEqual(pin['manifest_digest'], MANIFEST)
        installer.verify_archive(archive, pin)
        self.assertEqual(installer.main(['--verify-only', '--basic-pitch', str(archive)]), 0)

    def test_nine_model_bundle_does_not_absorb_either_model(self):
        bundle = json.loads((ROOT / 'provision/default-models.json').read_text())
        self.assertEqual(len(bundle['assets']), 9)
        self.assertNotIn('basic-pitch-icassp-2022-onnx', bundle['assets'])
        self.assertNotIn('lfm2-kilix-commands', bundle['assets'])
        self.assertEqual(bundle['sha256'],
                         'e00614bf726154d09668820c061cbbcb402239a445bde666b0568d36f01528a6')

    def test_bad_members_are_refused(self):
        payload = b'weights'
        pin = json.loads((ROOT / 'provision/basic-pitch-model.json').read_text())
        cases = [
            ('escape', [('../escape', payload, tarfile.REGTYPE)]),
            ('link', [('models/nmp.onnx', b'', tarfile.SYMTYPE)]),
            ('extra', [('models/nmp.onnx', payload, tarfile.REGTYPE),
                       ('models/extra.bin', payload, tarfile.REGTYPE)]),
        ]
        with tempfile.TemporaryDirectory() as directory:
            for name, members in cases:
                raw = _archive(members)
                path = Path(directory) / (name + '.tar.xz')
                path.write_bytes(raw)
                forged = {**pin, 'bytes': len(raw),
                          'sha256': hashlib.sha256(raw).hexdigest()}
                with self.subTest(name=name), self.assertRaises(ValueError):
                    installer.verify_archive(path, forged)


class InstallPolicyTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.receipts = []
        self.eligible = False
        self.covered = False
        record = SimpleNamespace(id='lfm2-kilix-commands', digest='e' * 64)
        self.record = record
        spec = SimpleNamespace(
            asset_id='lfm2-kilix-commands', archive_sha256='a' * 64, archive_bytes=4,
            manifest_digest='b' * 64, version='lfm2-kilix-commands-20261104-v8',
            root='lfm2-kilix-commands-20261104-v8',
            source_url='https://example.invalid/lfm2.tar.gz',
            licenses=[SimpleNamespace(record_digest=record.digest)])
        self.spec = spec
        cache = tempfile.TemporaryDirectory()
        self.addCleanup(cache.cleanup)
        self.cache = Path(cache.name)
        payload = b'gguf'
        (self.cache / ('a' * 64)).write_bytes(payload)
        self.pin = {
            'asset_id': spec.asset_id, 'sha256': 'a' * 64, 'bytes': 4,
            'manifest_digest': spec.manifest_digest, 'version': spec.version,
            'root': spec.root, 'url': spec.source_url, 'weight_version': 'fixture.8'}
        # The cache file must actually hash to the pin. Rebuild both together.
        digest = hashlib.sha256(payload).hexdigest()
        (self.cache / digest).write_bytes(payload)
        (self.cache / ('a' * 64)).unlink()
        self.pin['sha256'] = self.spec.archive_sha256 = digest

        class Store:
            def write(inner, receipt):
                self.receipts.append(receipt)

        class Licence:
            CoverageRefused = type('CoverageRefused', (Exception,), {})
            AssetRef = staticmethod(lambda *args: args)

            def standard_policy_eligible(inner, record):
                return self.eligible

            def require(inner, *args, **kwargs):
                if not self.covered:
                    raise inner.CoverageRefused()

            def capture_agreement(inner, record, typed):
                self.calls.append(('capture', typed, record.id))
                return 'agreement'

            def capture_standard_policy(inner, record):
                raise AssertionError('standard policy used for the command model')

            def receipt_from_agreement(inner, record, agreement, **kwargs):
                return {'agreement': agreement, 'typed_through': agreement, **kwargs}

            def load_determined_texts(inner, path):
                return 'texts'

            def load_determined_records(inner):
                return 'records'

            class ReceiptStore:
                @staticmethod
                def shared():
                    return Store()

        class Installer:
            def __init__(inner, root):
                inner.root = root

            def ensure_upstream_asset(inner, spec, **kwargs):
                self.calls.append(('upstream', spec.asset_id, kwargs.get('supplied', None)))

            def ensure_supplied_asset(inner, spec, **kwargs):
                self.calls.append(('supplied', spec.asset_id, str(kwargs['supplied'])))

        api = SimpleNamespace(Installer=Installer)
        lic = Licence()
        catalog = SimpleNamespace(require_asset=lambda name: spec)
        setup = type('SetupError', (Exception,), {})
        cm = SimpleNamespace(
            _api=lambda: api, _license=lambda: lic,
            _verified_catalog=lambda api: catalog,
            _record=lambda records, digest: record,
            _verify=lambda *args, **kwargs: (_ for _ in ()).throw(setup('missing')),
            SetupError=setup)
        defaults = SimpleNamespace(authorize=lambda *args: self.calls.append(('authorize', args[1].asset_id)))
        self.cm = cm
        self.load = patch.object(installer, '_load', return_value=(cm, defaults))
        self.root = patch.object(installer, '_apps_root', return_value='/apps')
        self.digests = patch.object(installer, '_receipt_digests', return_value=('c' * 64, 'd' * 64))
        self.load.start()
        self.root.start()
        self.digests.start()
        self.addCleanup(self.load.stop)
        self.addCleanup(self.root.stop)
        self.addCleanup(self.digests.stop)
        previous_cache = os.environ.get('KILIX_CONTENT_ARCHIVE_CACHE')

        def restore_cache():
            if previous_cache is None:
                os.environ.pop('KILIX_CONTENT_ARCHIVE_CACHE', None)
            else:
                os.environ['KILIX_CONTENT_ARCHIVE_CACHE'] = previous_cache

        self.addCleanup(restore_cache)

    def test_command_model_records_custom_terms_and_reads_the_cache(self):
        installer.install_command_model(Path('/kilix'), self.pin, self.cache)
        self.assertEqual(self.calls[0], ('capture', 'yes', 'lfm2-kilix-commands'))
        self.assertEqual(self.calls[1][0], 'upstream')
        self.assertNotIn('supplied', [kind for kind, *_rest in self.calls])
        self.assertEqual(self.receipts[0]['catalogue_digest'], 'c' * 64)
        self.assertEqual(os.environ['KILIX_CONTENT_ARCHIVE_CACHE'], str(self.cache))

    def test_standard_policy_cannot_cover_the_command_model(self):
        self.eligible = True
        with self.assertRaisesRegex(ValueError, 'custom terms'):
            installer.install_command_model(Path('/kilix'), self.pin, self.cache)
        self.assertEqual(self.receipts, [])
        self.assertNotIn('upstream', [kind for kind, *_rest in self.calls])

    def test_verified_command_model_does_not_need_the_archive(self):
        self.cm._verify = lambda *args, **kwargs: 0
        installer.install_command_model(Path('/kilix'), self.pin, Path('/missing-cache'))
        self.assertEqual(self.calls, [])

    def test_basic_pitch_uses_the_standard_policy_and_supplied_bytes(self):
        self.eligible = True
        self.spec.asset_id = 'basic-pitch-icassp-2022-onnx'
        self.spec.manifest_digest = MANIFEST
        pin = json.loads((ROOT / 'provision/basic-pitch-model.json').read_text())
        archive = ROOT / 'provision/bundles/basic-pitch-icassp-2022-onnx.tar.xz'
        installer.install_basic_pitch(Path('/kilix'), archive, pin)
        self.assertEqual(self.calls[0][0], 'authorize')
        self.assertEqual(self.calls[1][0], 'supplied')
        self.assertFalse(any(kind == 'capture' for kind, *_rest in self.calls))

    def test_basic_pitch_refuses_custom_terms(self):
        self.eligible = False
        self.spec.asset_id = 'basic-pitch-icassp-2022-onnx'
        self.spec.manifest_digest = MANIFEST
        pin = json.loads((ROOT / 'provision/basic-pitch-model.json').read_text())
        archive = ROOT / 'provision/bundles/basic-pitch-icassp-2022-onnx.tar.xz'
        with self.assertRaisesRegex(ValueError, 'standard distribution policy'):
            installer.install_basic_pitch(Path('/kilix'), archive, pin)
        self.assertEqual(self.calls, [])


class ImageWiringTests(unittest.TestCase):
    def test_install_and_upgrade_install_after_staging(self):
        provision = (ROOT / 'provision/plebian-os-provision.sh').read_text()
        update = (ROOT / 'provision/plebian-os-update.sh').read_text()
        preseed = (ROOT / 'preseed/preseed.cfg').read_text()
        remaster = (ROOT / 'build/remaster-iso.sh').read_text()
        self.assertLess(provision.index('stage-command-model.py'),
                        provision.index('install-image-models.py'))
        self.assertLess(provision.index('install-default-models.py'),
                        provision.index('install-image-models.py'))
        self.assertIn(
            'as_user env "${install_env[@]}" /usr/bin/python3 \\\n'
            '    "$PLEBIAN_OS_DIR/provision/install-image-models.py" '
            '--kilix "$KILIX_DIR" --offline', provision)
        self.assertLess(update.index('stage-command-model.py'),
                        update.index('install-image-models.py'))
        self.assertLess(update.index('install-default-models.py'),
                        update.index('install-image-models.py'))
        self.assertIn(
            '"$PLEBIAN_OS_DIR/provision/install-image-models.py" --kilix "$KILIX_DIR"',
            update)
        self.assertIn('test_fail_after_boundary image-models', update)
        self.assertIn(
            'cp /cdrom/plebian-os/basic-pitch-icassp-2022-onnx.tar.xz '
            '/target/usr/local/share/plebian-os/basic-pitch-icassp-2022-onnx.tar.xz',
            preseed)
        self.assertIn(
            'install -m 0644 "$HERE/provision/bundles/basic-pitch-icassp-2022-onnx.tar.xz"',
            remaster)
        self.assertLess(
            remaster.index('install-image-models.py" --verify-only'),
            remaster.index('"$EXTRACT/plebian-os/basic-pitch-icassp-2022-onnx.tar.xz"'))


if __name__ == '__main__':
    unittest.main()
