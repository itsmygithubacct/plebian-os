"""Basic Pitch, Demucs and page OCR are on the image; they, Whisper medium.en and LFM2 install by default."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import tarfile
import sys
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
DEMUCS_MANIFEST = '21c129345826c583e5327902dde4e7fe610282c2b0594bc058afb003ec8b03ff'
DEMUCS_WEIGHTS = '34c22ccb381c6f9fdbf324f04e1e2fe21aaaf293f5ded163a162697ff9a02ddd'
DEMUCS_LICENCE = 'cf9b17822d1fcd4ff32ccbe14183386fb3adf6f2ff92dc184130823f7fc28173'
MEDIUM_MANIFEST = '133afbde25b1a801f2f68d3a033c006a1979004df4452ea2496d12908006ce4b'
APACHE = 'cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30'
PP_OCR = {
    # asset id: (catalog manifest digest, archive bytes, archive sha256, {file: (bytes, sha256)})
    'pp-ocrv6-small-det': (
        '953752951e3805d83e0da54d24566d75d1e9a52d95101c6d900d45940fbd511e', 9902080,
        'dbd78e6646688f55b167ffc6f27548ae52952f82bb746c2eea77293a715bf21c',
        {'inference.onnx': (9880512, 'd73e0058b7a8086bbd57f3d10b8bcd4ff95363f67e06e2762b5e814fe9c9410e')}),
    'pp-ocrv6-small-rec': (
        '19566d34492f0fc80fa188a24195abd485777d3a211a99ae0fa9b17ef85d7a4e', 21329920,
        'b358b3821a26000da53ebb8bdbd59dafdefe09c7797d7a820d848ad38368cda6',
        {'inference.onnx': (21159378, '5435fd747c9e0efe15a96d0b378d5bd157e9492ed8fd80edf08f30d02fa24634'),
         'inference.yml': (150579, 'ab078671bb49f06228eadccd34f1bb501e157f7a047095ffb943ba81512c77d1')}),
}


def _demucs_pin():
    return json.loads((ROOT / 'provision/demucs-model.json').read_text())


def _archive(members, mode='w:xz'):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode=mode) as archive:
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
        self.assertIn('kilix-female-02', bundle['assets'])
        self.assertNotIn('basic-pitch-icassp-2022-onnx', bundle['assets'])
        self.assertNotIn('lfm2-kilix-commands', bundle['assets'])
        self.assertNotIn('paradee-8m-v1.2', bundle['assets'])
        self.assertNotIn('en-core-web-sm-3.8.0', bundle['assets'])
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


class DemucsArchiveTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        # Stand-in weights; the pin is re-made for them, as the build makes it
        # for Meta's file.
        self.weights = self.root / 'weights.th'
        self.weights.write_bytes(b'demucs-weights' * 100)
        pin = _demucs_pin()
        pin['files'] = {**pin['files'], 'models/5c90dfd2-34c22ccb.th': {
            'bytes': self.weights.stat().st_size,
            'sha256': hashlib.sha256(self.weights.read_bytes()).hexdigest()}}
        self.pin = pin

    def forge(self, raw):
        return {**self.pin, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

    def build(self, name, pin):
        with patch.object(installer, 'verify_demucs_archive'), patch('builtins.print'):
            installer.build_demucs_archive(self.weights, self.root / name, pin)
        return (self.root / name).read_bytes()

    def test_pin_names_meta_s_file_its_mit_text_and_the_catalogued_asset(self):
        pin = _demucs_pin()
        installer.validate_demucs_pin(pin)
        self.assertEqual(pin['manifest_digest'], DEMUCS_MANIFEST)
        self.assertEqual(pin['files']['models/5c90dfd2-34c22ccb.th'],
                         {'bytes': 54996327, 'sha256': DEMUCS_WEIGHTS})
        self.assertEqual(pin['files']['notices/LICENSE-mit.txt'], {'bytes': 1087, 'sha256': DEMUCS_LICENCE})
        self.assertEqual(pin['url'],
                         'https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/5c90dfd2-34c22ccb.th')
        # The MIT text the image carries is the Demucs LICENSE byte for byte.
        self.assertEqual(hashlib.sha256(installer.DEMUCS_LICENCE_SOURCE.read_bytes()).hexdigest(),
                         DEMUCS_LICENCE)
        self.assertNotEqual(pin['sha256'], pin['files']['models/5c90dfd2-34c22ccb.th']['sha256'])
        for field, value in (('url', 'https://example.invalid/weights.th'),
                             ('filename', 'demucs-htdemucs-6s.tar.xz'), ('asset_id', 'demucs')):
            with self.subTest(field=field), self.assertRaises(ValueError):
                installer.validate_demucs_pin({**pin, field: value})

    def test_the_archive_is_reproducible_and_verifies(self):
        raw = self.build('first.tar', self.pin)
        pin = self.forge(raw)
        self.assertEqual(self.build('second.tar', self.pin), raw)
        installer.verify_demucs_archive(self.root / 'first.tar', pin)
        with tarfile.open(self.root / 'first.tar', mode='r:') as archive:
            members = archive.getmembers()
        self.assertEqual([member.name for member in members],
                         ['models/5c90dfd2-34c22ccb.th', 'notices/LICENSE-mit.txt'])
        for member in members:
            self.assertEqual((member.mtime, member.uid, member.gid, member.mode, member.uname),
                             (0, 0, 0, 0o644, ''))
        unpacked = self.root / 'unpacked'
        unpacked.mkdir()
        installer.materialize_demucs(self.root / 'first.tar', pin, unpacked)
        self.assertEqual((unpacked / 'models/5c90dfd2-34c22ccb.th').read_bytes(), self.weights.read_bytes())
        self.assertEqual((unpacked / 'notices/LICENSE-mit.txt').read_bytes(),
                         installer.DEMUCS_LICENCE_SOURCE.read_bytes())

    def test_the_builder_refuses_other_weights_and_leaves_nothing(self):
        self.weights.write_bytes(b'other-weights' * 100)
        with self.assertRaisesRegex(ValueError, 'Demucs input size or checksum mismatch'):
            self.build('bad.tar', self.pin)
        self.assertFalse((self.root / 'bad.tar').exists())

    def test_the_builder_verifies_its_output_and_removes_a_mismatch(self):
        wrong = {**self.pin, 'bytes': 10240, 'sha256': 'f' * 64}
        with patch('builtins.print'), self.assertRaisesRegex(ValueError, 'size or checksum'):
            installer.build_demucs_archive(self.weights, self.root / 'wrong.tar', wrong)
        self.assertFalse((self.root / 'wrong.tar').exists())

    def test_bad_members_are_refused(self):
        payload = b'weights'
        licence = installer.DEMUCS_LICENCE_SOURCE.read_bytes()
        cases = [
            ('escape', [('../escape', payload, tarfile.REGTYPE)]),
            ('link', [('models/5c90dfd2-34c22ccb.th', b'', tarfile.SYMTYPE),
                      ('notices/LICENSE-mit.txt', licence, tarfile.REGTYPE)]),
            ('extra', [('models/5c90dfd2-34c22ccb.th', self.weights.read_bytes(), tarfile.REGTYPE),
                       ('notices/LICENSE-mit.txt', licence, tarfile.REGTYPE),
                       ('models/extra.bin', payload, tarfile.REGTYPE)]),
            ('no-licence', [('models/5c90dfd2-34c22ccb.th', self.weights.read_bytes(), tarfile.REGTYPE)]),
        ]
        for name, members in cases:
            raw = _archive(members, mode='w')
            path = self.root / (name + '.tar')
            path.write_bytes(raw)
            with self.subTest(name=name), self.assertRaises(ValueError):
                installer.verify_demucs_archive(path, self.forge(raw))

    def test_the_image_archive_is_preferred_and_a_symlink_is_not_used(self):
        with patch.object(installer, 'SHARED_BASIC_PITCH', self.root):
            self.assertIsNone(installer.resolve_demucs(None))
            (self.root / 'elsewhere.tar').write_bytes(b'x')
            (self.root / 'demucs-htdemucs-6s.tar').symlink_to(self.root / 'elsewhere.tar')
            self.assertIsNone(installer.resolve_demucs(None))
            (self.root / 'demucs-htdemucs-6s.tar').unlink()
            (self.root / 'demucs-htdemucs-6s.tar').write_bytes(b'x')
            self.assertEqual(installer.resolve_demucs(None), self.root / 'demucs-htdemucs-6s.tar')
            self.assertEqual(installer.resolve_demucs(self.root / 'given.tar'), self.root / 'given.tar')


def _paradee_pin():
    return json.loads((ROOT / 'provision/paradee-model.json').read_text())


def _spacy_pin():
    return json.loads((ROOT / 'provision/en-core-web-sm-model.json').read_text())


class ParadeeArchiveTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.onnx = self.root / 'paradee_int8.onnx'
        self.config = self.root / 'config.json'
        self.onnx.write_bytes(b'paradee-onnx' * 40)
        self.config.write_bytes(b'{"voices":["af_heart"]}')
        pin = _paradee_pin()
        pin['files'] = {**pin['files'],
                        'onnx/paradee_int8.onnx': {
                            'bytes': self.onnx.stat().st_size,
                            'sha256': hashlib.sha256(self.onnx.read_bytes()).hexdigest(),
                            'url': pin['files']['onnx/paradee_int8.onnx']['url']},
                        'config.json': {
                            'bytes': self.config.stat().st_size,
                            'sha256': hashlib.sha256(self.config.read_bytes()).hexdigest(),
                            'url': pin['files']['config.json']['url']}}
        self.pin = pin

    def forge(self, raw):
        return {**self.pin, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

    def build(self, name, pin):
        with patch.object(installer, 'verify_paradee_archive'), patch('builtins.print'):
            installer.build_paradee_archive(self.onnx, self.config, self.root / name, pin)
        return (self.root / name).read_bytes()

    def test_pin_names_the_onnx_config_and_apache_text(self):
        pin = _paradee_pin()
        installer.validate_paradee_pin(pin)
        self.assertEqual(pin['manifest_digest'],
                         '99929f0a7f1811eb7b7cc5821526d9e486e0a46fbccbf178959ade25e3f3f967')
        self.assertEqual(pin['files']['onnx/paradee_int8.onnx'], {
            'bytes': 8462119,
            'sha256': 'a6989796692ac173597e15d405c971989202d5c73cfad65f22e90bd7b6c97da1',
            'url': installer.PARADEE_ONNX_URL})
        self.assertEqual(pin['files']['config.json']['sha256'],
                         '002535cf8dd08a434cdddb13372da8a7b4844152bdf9b5b4e7342e12ec30bcfb')
        self.assertEqual(pin['files']['notices/LICENSE-apache-2.0.txt'],
                         {'bytes': 11358,
                          'sha256': 'cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30'})
        self.assertEqual(hashlib.sha256(installer.PARADEE_LICENCE_SOURCE.read_bytes()).hexdigest(),
                         pin['files']['notices/LICENSE-apache-2.0.txt']['sha256'])
        self.assertEqual(pin['sha256'],
                         '61e95049263a04897b1cc69923aaed0eb33d47d610763d9055de14b4f52b908a')
        for field, value in (('filename', 'paradee-8m-v1.2.tar.xz'), ('asset_id', 'paradee')):
            with self.subTest(field=field), self.assertRaises(ValueError):
                installer.validate_paradee_pin({**pin, field: value})

    def test_the_archive_is_reproducible_and_verifies(self):
        raw = self.build('first.tar', self.pin)
        pin = self.forge(raw)
        self.assertEqual(self.build('second.tar', self.pin), raw)
        installer.verify_paradee_archive(self.root / 'first.tar', pin)
        with tarfile.open(self.root / 'first.tar', mode='r:') as archive:
            members = archive.getmembers()
        self.assertEqual([member.name for member in members],
                         ['onnx/paradee_int8.onnx', 'config.json', 'notices/LICENSE-apache-2.0.txt'])
        for member in members:
            self.assertEqual((member.mtime, member.uid, member.gid, member.mode, member.uname),
                             (0, 0, 0, 0o644, ''))
        unpacked = self.root / 'unpacked'
        unpacked.mkdir()
        installer.materialize_paradee(self.root / 'first.tar', pin, unpacked)
        self.assertEqual((unpacked / 'onnx/paradee_int8.onnx').read_bytes(), self.onnx.read_bytes())
        self.assertEqual((unpacked / 'config.json').read_bytes(), self.config.read_bytes())

    def test_the_builder_refuses_other_weights_and_leaves_nothing(self):
        self.onnx.write_bytes(b'other-onnx' * 40)
        with self.assertRaisesRegex(ValueError, 'Paradee input size or checksum mismatch'):
            self.build('bad.tar', self.pin)
        self.assertFalse((self.root / 'bad.tar').exists())

    def test_the_builder_verifies_its_output_and_removes_a_mismatch(self):
        wrong = {**self.pin, 'bytes': 10240, 'sha256': 'f' * 64}
        with patch('builtins.print'), self.assertRaisesRegex(ValueError, 'size or checksum'):
            installer.build_paradee_archive(self.onnx, self.config, self.root / 'wrong.tar', wrong)
        self.assertFalse((self.root / 'wrong.tar').exists())

    def test_bad_members_are_refused(self):
        payload = b'weights'
        licence = installer.PARADEE_LICENCE_SOURCE.read_bytes()
        cases = [
            ('escape', [('../escape', payload, tarfile.REGTYPE)]),
            ('link', [('onnx/paradee_int8.onnx', b'', tarfile.SYMTYPE)]),
            ('extra', [('onnx/paradee_int8.onnx', self.onnx.read_bytes(), tarfile.REGTYPE),
                       ('config.json', self.config.read_bytes(), tarfile.REGTYPE),
                       ('notices/LICENSE-apache-2.0.txt', licence, tarfile.REGTYPE),
                       ('extra.bin', payload, tarfile.REGTYPE)]),
            ('no-licence', [('onnx/paradee_int8.onnx', self.onnx.read_bytes(), tarfile.REGTYPE),
                            ('config.json', self.config.read_bytes(), tarfile.REGTYPE)]),
        ]
        for name, members in cases:
            raw = _archive(members, mode='w')
            path = self.root / (name + '.tar')
            path.write_bytes(raw)
            with self.subTest(name=name), self.assertRaises(ValueError):
                installer.verify_paradee_archive(path, self.forge(raw))

    def test_a_missing_runtime_file_is_copied_and_a_mismatch_is_left_alone(self):
        raw = self.build('runtime.tar', self.pin)
        pin = self.forge(raw)
        runtime = self.root / 'runtime'
        installer.stage_paradee_runtime(self.root / 'runtime.tar', pin, runtime)
        self.assertEqual((runtime / 'onnx/paradee_int8.onnx').read_bytes(), self.onnx.read_bytes())
        self.assertEqual((runtime / 'notices/LICENSE-apache-2.0.txt').read_bytes(),
                         installer.PARADEE_LICENCE_SOURCE.read_bytes())
        (runtime / 'config.json').write_bytes(b'not-the-config')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            installer.verify_paradee_runtime(pin, runtime)
        before = (runtime / 'config.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            installer.stage_paradee_runtime(self.root / 'runtime.tar', pin, runtime)
        self.assertEqual((runtime / 'config.json').read_bytes(), before)
        self.assertEqual((runtime / 'notices/LICENSE-apache-2.0.txt').read_bytes(),
                         installer.PARADEE_LICENCE_SOURCE.read_bytes())

    def test_the_image_archive_is_preferred_and_a_symlink_is_not_used(self):
        with patch.object(installer, 'SHARED_BASIC_PITCH', self.root):
            self.assertIsNone(installer.resolve_paradee(None))
            (self.root / 'paradee-8m-v1.2.tar').symlink_to(self.onnx)
            self.assertIsNone(installer.resolve_paradee(None))
            (self.root / 'paradee-8m-v1.2.tar').unlink()
            (self.root / 'paradee-8m-v1.2.tar').write_bytes(b'x')
            self.assertEqual(installer.resolve_paradee(None), self.root / 'paradee-8m-v1.2.tar')


class SpacyArchiveTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.wheel = self.root / 'model.whl'
        self.wheel.write_bytes(b'spacy-wheel' * 50)
        pin = _spacy_pin()
        pin['files'] = {**pin['files'], installer.SPACY_WHEEL: {
            'bytes': self.wheel.stat().st_size,
            'sha256': hashlib.sha256(self.wheel.read_bytes()).hexdigest(),
            'url': pin['files'][installer.SPACY_WHEEL]['url']}}
        self.pin = pin

    def forge(self, raw):
        return {**self.pin, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

    def test_pin_names_the_wheel_and_both_texts(self):
        pin = _spacy_pin()
        installer.validate_spacy_pin(pin)
        self.assertEqual(pin['manifest_digest'],
                         'ce7a28de5ef369d1e1c7bd58571e4fe615a6783124721f8142de651755239271')
        self.assertEqual(pin['files'][installer.SPACY_WHEEL]['sha256'],
                         '1932429db727d4bff3deed6b34cfc05df17794f4a52eeb26cf8928f7c1a0fb85')
        self.assertEqual(pin['files'][installer.SPACY_WHEEL]['bytes'], 12806118)
        self.assertEqual(hashlib.sha256(installer.SPACY_LICENCE_SOURCE.read_bytes()).hexdigest(),
                         pin['files'][installer.SPACY_LICENCE]['sha256'])
        self.assertEqual(hashlib.sha256(installer.SPACY_SOURCES_SOURCE.read_bytes()).hexdigest(),
                         pin['files'][installer.SPACY_SOURCES]['sha256'])
        self.assertEqual(pin['sha256'],
                         'eedbef109150c8b8f0534fae3ac6ee1a79d9616f09f638247c35a7a309f180fb')

    def test_the_archive_members_stay_in_pin_order(self):
        with patch.object(installer, 'verify_spacy_archive'), patch('builtins.print'):
            installer.build_spacy_archive(self.wheel, self.root / 'model.tar', self.pin)
        raw = (self.root / 'model.tar').read_bytes()
        installer.verify_spacy_archive(self.root / 'model.tar', self.forge(raw))
        with tarfile.open(self.root / 'model.tar', mode='r:') as archive:
            self.assertEqual([member.name for member in archive.getmembers()], list(installer.SPACY_FILES))

    def test_a_missing_archive_is_an_error_and_an_installed_copy_is_kept(self):
        with patch.object(installer, '_load', return_value=(None, None)), \
                patch.object(installer, '_playalong_installed', return_value=False), \
                patch.object(installer, '_install_from_image', side_effect=AssertionError('download')):
            with self.assertRaisesRegex(ValueError, 'did not supply the en_core_web_sm model'):
                installer.install_spacy('/kilix', None, self.pin, offline=True)
        for offline in (True, False):
            with self.subTest(offline=offline), \
                    patch.object(installer, '_load', return_value=(None, None)), \
                    patch.object(installer, '_playalong_installed', return_value=True), \
                    patch('builtins.print') as printed:
                installer.install_spacy('/kilix', None, self.pin, offline=offline)
            printed.assert_called_with('en_core_web_sm already verified; no bundle install needed.')

    def test_an_upgrade_without_the_archive_skips_and_never_downloads(self):
        with patch.object(installer, '_load', return_value=(None, None)), \
                patch.object(installer, '_playalong_installed', return_value=False), \
                patch.object(installer, '_install_from_image', side_effect=AssertionError('install')), \
                patch.object(installer, 'fetch_default', side_effect=AssertionError('download')), \
                patch('builtins.print') as printed:
            installer.install_spacy('/kilix', None, self.pin, offline=False)
        self.assertIn('the next upgrade tries again', printed.call_args.args[0])


def _pp_ocr_pin(asset_id):
    return json.loads((ROOT / f'provision/{asset_id}-model.json').read_text())


class PageOcrArchiveTests(unittest.TestCase):
    """PDF Conversion's PP-OCRv6 small models ship in the image (owner, 2026-11-10)."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        # Stand-in files; each pin is re-made for them, as the build makes it
        # for PaddlePaddle's files.
        self.sources = {}
        self.pins = {}
        for asset_id, (_manifest, _bytes, _sha, files) in PP_OCR.items():
            source = self.root / asset_id
            source.mkdir()
            pin = _pp_ocr_pin(asset_id)
            for name in files:
                data = (asset_id + name).encode() * 64
                (source / name).write_bytes(data)
                pin['files'][name] = {**pin['files'][name], 'bytes': len(data),
                                      'sha256': hashlib.sha256(data).hexdigest()}
            self.sources[asset_id] = source
            self.pins[asset_id] = pin

    def build(self, asset_id, name):
        with patch.object(installer, 'verify_pp_ocr_archive'), patch('builtins.print'):
            installer.build_pp_ocr_archive(self.sources[asset_id], self.root / name, self.pins[asset_id])
        raw = (self.root / name).read_bytes()
        return raw, {**self.pins[asset_id], 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

    def test_pins_name_paddlepaddle_s_files_the_apache_text_and_the_catalogued_assets(self):
        self.assertEqual(hashlib.sha256(installer.PP_OCR_LICENCE_SOURCE.read_bytes()).hexdigest(), APACHE)
        for asset_id, (manifest, size, digest, files) in PP_OCR.items():
            pin = _pp_ocr_pin(asset_id)
            with self.subTest(asset=asset_id):
                installer.validate_pp_ocr_pin(pin, asset_id)
                self.assertEqual(pin['since_release'], '0.2.3-rc8')
                self.assertEqual((pin['manifest_digest'], pin['bytes'], pin['sha256']), (manifest, size, digest))
                self.assertEqual(pin['filename'], asset_id + '.tar')
                self.assertEqual(list(pin['files']), list(installer.pp_ocr_files(asset_id)))
                for name, (length, sha) in files.items():
                    self.assertEqual((pin['files'][name]['bytes'], pin['files'][name]['sha256']), (length, sha))
                    self.assertTrue(pin['files'][name]['url'].startswith(
                        'https://huggingface.co/PaddlePaddle/PP-OCRv6_small_'))
                    self.assertIn('/resolve/' + pin['files'][name]['url'].split('/resolve/')[1].split('/')[0] + '/',
                                  installer.PP_OCR_MODELS[asset_id][0])
                self.assertEqual(pin['files'][installer.PP_OCR_LICENCE], {'bytes': 11358, 'sha256': APACHE})
                other = 'pp-ocrv6-small-rec' if asset_id.endswith('det') else 'pp-ocrv6-small-det'
                for field, value in (('filename', asset_id + '.tar.xz'), ('asset_id', other),
                                     ('schema', 'plebian-os.demucs-archive/v1')):
                    with self.assertRaises(ValueError):
                        installer.validate_pp_ocr_pin({**pin, field: value}, asset_id)
                moved = json.loads(json.dumps(pin))
                name = next(iter(files))
                moved['files'][name]['url'] = moved['files'][name]['url'].replace('/resolve/', '/resolve/main/x')
                with self.assertRaisesRegex(ValueError, 'URL is not the pinned file'):
                    installer.validate_pp_ocr_pin(moved, asset_id)
        with self.assertRaisesRegex(ValueError, 'not a page OCR model'):
            installer.pp_ocr_files('granite-docling-258m')

    def test_the_archives_are_reproducible_verify_and_unpack(self):
        for asset_id in PP_OCR:
            with self.subTest(asset=asset_id):
                raw, pin = self.build(asset_id, asset_id + '-first.tar')
                self.assertEqual(self.build(asset_id, asset_id + '-second.tar')[0], raw)
                path = self.root / (asset_id + '-first.tar')
                installer.verify_pp_ocr_archive(path, pin)
                with tarfile.open(path, mode='r:') as archive:
                    members = archive.getmembers()
                self.assertEqual([member.name for member in members], list(installer.pp_ocr_files(asset_id)))
                for member in members:
                    self.assertEqual((member.mtime, member.uid, member.gid, member.mode, member.uname),
                                     (0, 0, 0, 0o644, ''))
                unpacked = self.root / (asset_id + '-unpacked')
                unpacked.mkdir()
                installer.materialize_pp_ocr(path, pin, unpacked)
                self.assertEqual((unpacked / installer.PP_OCR_LICENCE).read_bytes(),
                                 installer.PP_OCR_LICENCE_SOURCE.read_bytes())
                for name in PP_OCR[asset_id][3]:
                    self.assertEqual((unpacked / name).read_bytes(), (self.sources[asset_id] / name).read_bytes())

    def test_the_builder_refuses_other_files_and_leaves_nothing(self):
        asset_id = 'pp-ocrv6-small-rec'
        (self.sources[asset_id] / 'inference.yml').write_bytes(b'other characters')
        with self.assertRaisesRegex(ValueError, 'pp-ocrv6-small-rec input size or checksum mismatch'):
            self.build(asset_id, 'bad.tar')
        self.assertFalse((self.root / 'bad.tar').exists())
        wrong = {**self.pins['pp-ocrv6-small-det'], 'bytes': 10240, 'sha256': 'f' * 64}
        with patch('builtins.print'), self.assertRaisesRegex(ValueError, 'size or checksum'):
            installer.build_pp_ocr_archive(self.sources['pp-ocrv6-small-det'], self.root / 'wrong.tar', wrong)
        self.assertFalse((self.root / 'wrong.tar').exists())

    def test_bad_members_are_refused(self):
        asset_id = 'pp-ocrv6-small-det'
        model = (self.sources[asset_id] / 'inference.onnx').read_bytes()
        licence = installer.PP_OCR_LICENCE_SOURCE.read_bytes()
        cases = [
            ('escape', [('../escape', model, tarfile.REGTYPE)]),
            ('link', [('inference.onnx', b'', tarfile.SYMTYPE),
                      (installer.PP_OCR_LICENCE, licence, tarfile.REGTYPE)]),
            ('extra', [('inference.onnx', model, tarfile.REGTYPE),
                       (installer.PP_OCR_LICENCE, licence, tarfile.REGTYPE),
                       ('README.md', b'card', tarfile.REGTYPE)]),
            ('no-licence', [('inference.onnx', model, tarfile.REGTYPE)]),
        ]
        for name, members in cases:
            raw = _archive(members, mode='w')
            path = self.root / (name + '.tar')
            path.write_bytes(raw)
            forged = {**self.pins[asset_id], 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
            with self.subTest(name=name), self.assertRaises(ValueError):
                installer.verify_pp_ocr_archive(path, forged)

    def test_the_image_archive_is_preferred_and_a_symlink_is_not_used(self):
        with patch.object(installer, 'SHARED_BASIC_PITCH', self.root):
            for asset_id in PP_OCR:
                with self.subTest(asset=asset_id):
                    self.assertIsNone(installer.resolve_pp_ocr(None, asset_id))
                    (self.root / (asset_id + '-elsewhere.tar')).write_bytes(b'x')
                    (self.root / (asset_id + '.tar')).symlink_to(self.root / (asset_id + '-elsewhere.tar'))
                    self.assertIsNone(installer.resolve_pp_ocr(None, asset_id))
                    (self.root / (asset_id + '.tar')).unlink()
                    (self.root / (asset_id + '.tar')).write_bytes(b'x')
                    self.assertEqual(installer.resolve_pp_ocr(None, asset_id), self.root / (asset_id + '.tar'))
                    self.assertEqual(installer.resolve_pp_ocr(self.root / 'given.tar', asset_id),
                                     self.root / 'given.tar')

    def test_the_command_line_builds_and_verifies_each_archive(self):
        pins = {}
        for asset_id in PP_OCR:
            raw, pins[asset_id] = self.build(asset_id, asset_id + '-expected.tar')
        real = installer._load_pin
        for asset_id in PP_OCR:
            with self.subTest(asset=asset_id), patch.dict(installer.__dict__), patch('builtins.print'):
                installer._load_pin = lambda name: (pins[name[:-len('-model.json')]]
                                                    if name[:-len('-model.json')] in pins else real(name))
                output = self.root / (asset_id + '-cli.tar')
                self.assertEqual(installer.main(['--build-pp-ocr-archive', asset_id, str(output),
                                                 '--pp-ocr-files', str(self.sources[asset_id])]), 0)
                self.assertEqual(output.read_bytes(), (self.root / (asset_id + '-expected.tar')).read_bytes())
                self.assertEqual(installer.main([
                    '--verify-only', '--basic-pitch',
                    str(ROOT / 'provision/bundles/basic-pitch-icassp-2022-onnx.tar.xz'),
                    '--' + asset_id, str(output)]), 0)
        with patch('sys.stderr', new_callable=io.StringIO), self.assertRaises(SystemExit):
            installer.main(['--build-pp-ocr-archive', 'granite-docling-258m', str(self.root / 'x.tar'),
                            '--pp-ocr-files', str(self.root)])


class ParadeeWheelTests(unittest.TestCase):
    def lock(self, filename='model.whl'):
        return {'schema': 'plebian-os.paradee-wheels/v1', 'python': '3.13', 'wheels': [{
            'name': 'en_core_web_sm', 'version': '3.8.0', 'filename': filename,
            'url': 'https://example.invalid/' + filename, 'bytes': 4, 'sha256': 'ab' * 32}]}

    def test_the_committed_lock_matches_the_bundled_docopt_wheel(self):
        lock = installer.load_wheel_lock()
        self.assertEqual(len(lock['wheels']), 77)
        bundled = [item for item in lock['wheels'] if 'bundle' in item]
        self.assertEqual([item['filename'] for item in bundled],
                         ['docopt-0.6.2-py2.py3-none-any.whl'])
        blob = ROOT / 'provision/bundles' / bundled[0]['filename']
        self.assertEqual(hashlib.sha256(blob.read_bytes()).hexdigest(), bundled[0]['sha256'])
        self.assertEqual(bundled[0]['bytes'], blob.stat().st_size)
        names = {item['name'] for item in lock['wheels']}
        self.assertTrue({'en_core_web_sm', 'misaki', 'numpy', 'onnxruntime', 'click'} <= names)

    def test_the_lock_requires_the_spacy_wheel_and_refuses_a_bad_entry(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / 'lock.json'
        path.write_text(json.dumps(self.lock()))
        self.assertEqual(installer.load_wheel_lock(path)['python'], '3.13')
        planted = self.lock()
        planted['wheels'][0]['name'] = 'numpy'
        path.write_text(json.dumps(planted))
        with self.assertRaisesRegex(ValueError, 'en_core_web_sm'):
            installer.load_wheel_lock(path)
        planted['wheels'][0]['filename'] = '../escape.whl'
        planted['wheels'][0]['name'] = 'en_core_web_sm'
        path.write_text(json.dumps(planted))
        with self.assertRaisesRegex(ValueError, 'wheel lock entry'):
            installer.load_wheel_lock(path)

    def test_an_existing_python_is_left_alone_and_a_symlink_is_refused(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        python = root / 'pd' / 'bin' / 'python'
        python.parent.mkdir(parents=True)
        python.write_bytes(b'#!/bin/sh\n')
        python.chmod(0o755)
        with patch.object(installer.subprocess, 'run', side_effect=AssertionError('rebuilt')), \
                patch('builtins.print'):
            installer.install_paradee_venv(root, self.lock(), python)
        link = root / 'python-link'
        link.symlink_to(python)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            installer.install_paradee_venv(root, self.lock(), link)

    def test_a_missing_wheel_stops_before_the_venv_is_created(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        (root / 'wheels').mkdir()
        python = root / 'pd' / 'bin' / 'python'
        with patch.object(installer.subprocess, 'run', side_effect=AssertionError('venv')):
            with self.assertRaisesRegex(ValueError, 'wheel is missing'):
                installer.install_paradee_venv(root / 'wheels', self.lock(), python)
        self.assertFalse((root / 'pd').exists())

    def test_a_fresh_venv_copies_the_interpreter(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        wheels = root / 'wheels'
        wheels.mkdir()
        blob = b'wheel'
        lock = self.lock()
        lock['wheels'][0]['bytes'] = len(blob)
        lock['wheels'][0]['sha256'] = hashlib.sha256(blob).hexdigest()
        (wheels / lock['wheels'][0]['filename']).write_bytes(blob)
        python = root / 'pd' / 'bin' / 'python'
        real = installer.subprocess.run
        calls = []

        def run(argv, **kwargs):
            calls.append(list(argv))
            if '-m' in argv and argv[argv.index('-m') + 1] == 'venv':
                return real(argv, **kwargs)
            return installer.subprocess.CompletedProcess(argv, 0)

        with patch.object(installer.subprocess, 'run', side_effect=run), patch('builtins.print'):
            installer.install_paradee_venv(wheels, lock, python)
        self.assertEqual(calls[0][3:5], ['venv', '--copies'])
        self.assertFalse(python.is_symlink())
        self.assertTrue(python.is_file())
        self.assertIn('--no-index', calls[1])
        self.assertEqual(calls[1][0], str(python))


class ParadeeUpgradeTests(unittest.TestCase):
    """A machine installed without the Paradee archives gets them on an online upgrade."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.shared = self.root / 'shared'
        self.runtime = self.root / 'runtime'
        self.python = self.root / 'pd' / 'bin' / 'python'
        self.upstream = {}
        pin = _paradee_pin()
        files = dict(pin['files'])
        for name, blob in (('onnx/paradee_int8.onnx', b'paradee-onnx' * 40),
                           ('config.json', b'{"voices":["af_heart"]}')):
            files[name] = {'bytes': len(blob), 'sha256': hashlib.sha256(blob).hexdigest(),
                           'url': pin['files'][name]['url']}
            self.upstream[files[name]['url']] = blob
        self.pin = self.forged({**pin, 'files': files}, 'paradee')
        spin = _spacy_pin()
        wheel = b'spacy-wheel' * 50
        item = {'bytes': len(wheel), 'sha256': hashlib.sha256(wheel).hexdigest(),
                'url': spin['files'][installer.SPACY_WHEEL]['url']}
        self.upstream[item['url']] = wheel
        self.spin = self.forged({**spin, 'files': {**spin['files'], installer.SPACY_WHEEL: item}}, 'spacy')
        blob = b'a-wheel'
        self.lock = {'schema': 'plebian-os.paradee-wheels/v1', 'python': '3.13', 'wheels': [{
            'name': 'en_core_web_sm', 'version': '3.8.0', 'filename': 'en_core_web_sm.whl',
            'url': 'https://example.invalid/en_core_web_sm.whl', 'bytes': len(blob),
            'sha256': hashlib.sha256(blob).hexdigest()}]}
        self.upstream['https://example.invalid/en_core_web_sm.whl'] = blob
        source = b'espeak-ng-source' * 30
        espeak = installer.load_espeak_pin()
        self.espeak = {**espeak, 'bytes': len(source), 'sha256': hashlib.sha256(source).hexdigest()}
        self.upstream[espeak['url']] = source
        self.docs = self.root / 'doc' / 'espeak-ng'
        self.downloads = []

    def forged(self, pin, kind):
        """The pin with the archive bytes and digest that its builder writes for these inputs."""
        with tempfile.TemporaryDirectory() as scratch, patch('builtins.print'):
            scratch = Path(scratch)
            output = scratch / 'archive.tar'
            if kind == 'paradee':
                (scratch / 'onnx').write_bytes(self.upstream[pin['files']['onnx/paradee_int8.onnx']['url']])
                (scratch / 'config').write_bytes(self.upstream[pin['files']['config.json']['url']])
                with patch.object(installer, 'verify_paradee_archive'):
                    installer.build_paradee_archive(scratch / 'onnx', scratch / 'config', output, pin)
            else:
                (scratch / 'wheel').write_bytes(self.upstream[pin['files'][installer.SPACY_WHEEL]['url']])
                with patch.object(installer, 'verify_spacy_archive'):
                    installer.build_spacy_archive(scratch / 'wheel', output, pin)
            raw = output.read_bytes()
        return {**pin, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

    def download(self, url, size, target):
        self.downloads.append(url)
        if isinstance(self.upstream.get(url), Exception):
            raise self.upstream[url]
        Path(target).write_bytes(self.upstream[url])

    def venv(self, wheelhouse, lock, python):
        """install_paradee_venv without pip: an existing interpreter is left alone."""
        if python.is_file():
            return
        installer.verify_paradee_wheels(wheelhouse, lock)
        python.parent.mkdir(parents=True, exist_ok=True)
        python.write_bytes(b'#!/bin/sh\n')

    def run_root(self, *, offline=False):
        with patch.object(installer, 'SHARED_BASIC_PITCH', self.shared), \
                patch.object(installer, 'load_wheel_lock', return_value=self.lock), \
                patch.object(installer, '_download_pinned', side_effect=self.download), \
                patch.object(installer, 'install_paradee_venv', side_effect=self.venv) as venv, \
                patch('builtins.print') as printed:
            result = installer.install_paradee_runtime(
                self.pin, self.spin, runtime=self.runtime, wheelhouse=self.shared / 'paradee-wheels',
                python=self.python, docs=self.docs, espeak_pin=self.espeak, offline=offline)
        return result, venv, printed

    def test_an_upgrade_downloads_checks_and_places_the_image_archives(self):
        result, venv, _printed = self.run_root()
        self.assertTrue(result)
        self.assertEqual(self.downloads, [
            self.pin['files']['onnx/paradee_int8.onnx']['url'], self.pin['files']['config.json']['url'],
            self.spin['files'][installer.SPACY_WHEEL]['url'], 'https://example.invalid/en_core_web_sm.whl',
            self.espeak['url']])
        for pin, verify in ((self.pin, installer.verify_paradee_archive),
                            (self.spin, installer.verify_spacy_archive)):
            placed = self.shared / pin['filename']
            verify(placed, pin)
            self.assertEqual(stat.S_IMODE(placed.stat().st_mode), 0o644)
        self.assertEqual(sorted(path.name for path in self.shared.iterdir()),
                         [self.spin['filename'], self.pin['filename']])
        installer.verify_paradee_runtime(self.pin, self.runtime)
        self.assertEqual((self.runtime / 'notices/LICENSE-apache-2.0.txt').read_bytes(),
                         installer.PARADEE_LICENCE_SOURCE.read_bytes())
        # The wheels were checked against the lock and installed from scratch.
        self.assertEqual(venv.call_args.args[2], self.python)
        self.assertNotEqual(venv.call_args.args[0], self.shared / 'paradee-wheels')
        # The next upgrade finds the archives and the interpreter and downloads nothing.
        self.downloads.clear()
        result, _venv, _printed = self.run_root()
        self.assertTrue(result)
        self.assertEqual(self.downloads, [])

    def test_the_en_core_wheel_is_downloaded_once_for_the_archive_and_the_wheelhouse(self):
        # In the real lock the en_core_web_sm wheel is the spaCy pin's wheel.
        item = self.spin['files'][installer.SPACY_WHEEL]
        self.lock['wheels'][0].update(url=item['url'], bytes=item['bytes'], sha256=item['sha256'])
        result, venv, _printed = self.run_root()
        self.assertTrue(result)
        self.assertEqual(self.downloads, [
            self.pin['files']['onnx/paradee_int8.onnx']['url'], self.pin['files']['config.json']['url'],
            item['url'], self.espeak['url']])
        # The fake venv checked the wheelhouse against the lock before "installing".
        self.assertTrue(self.python.is_file())
        venv.assert_called_once()

    def test_the_wheel_is_downloaded_when_the_spacy_archive_was_on_the_image(self):
        item = self.spin['files'][installer.SPACY_WHEEL]
        self.lock['wheels'][0].update(url=item['url'], bytes=item['bytes'], sha256=item['sha256'])
        self.run_root()
        self.python.unlink()
        self.downloads.clear()
        result, _venv, _printed = self.run_root()
        self.assertTrue(result)
        self.assertEqual(self.downloads, [item['url']])

    def test_a_failed_download_places_nothing_and_does_not_fail_the_upgrade(self):
        self.upstream['https://example.invalid/en_core_web_sm.whl'] = OSError('network is unreachable')
        result, venv, printed = self.run_root()
        self.assertFalse(result)
        venv.assert_not_called()
        self.assertFalse(self.shared.exists() and any(self.shared.iterdir()))
        self.assertFalse(self.runtime.exists())
        self.assertIn('the next upgrade tries again', printed.call_args.args[0])

    def test_other_upstream_bytes_are_refused_and_nothing_is_placed(self):
        url = self.pin['files']['onnx/paradee_int8.onnx']['url']
        self.upstream[url] = b'other-onnx' * 40
        result, venv, printed = self.run_root()
        self.assertFalse(result)
        venv.assert_not_called()
        self.assertFalse(self.shared.exists() and any(self.shared.iterdir()))
        self.assertFalse(self.runtime.exists())
        self.assertIn('input size or checksum mismatch', printed.call_args.args[0])

    def test_a_wheel_with_other_bytes_is_refused_before_anything_is_placed(self):
        self.upstream['https://example.invalid/en_core_web_sm.whl'] = b'b-wheel'
        result, venv, printed = self.run_root()
        self.assertFalse(result)
        venv.assert_not_called()
        self.assertFalse(self.shared.exists() and any(self.shared.iterdir()))
        self.assertIn('wheel size or checksum mismatch', printed.call_args.args[0])

    def test_an_archive_is_checked_again_where_it_is_placed(self):
        built = self.root / 'built.tar'
        built.write_bytes(b'not the archive')
        with patch.object(installer, 'SHARED_BASIC_PITCH', self.shared), \
                self.assertRaisesRegex(ValueError, 'size or checksum'):
            installer._place_shared_archive(built, self.pin, installer.verify_paradee_archive)
        self.assertEqual(list(self.shared.iterdir()), [])

    def test_a_fresh_install_without_the_archive_is_an_error_and_downloads_nothing(self):
        with self.assertRaisesRegex(ValueError, 'did not supply the Paradee model'):
            self.run_root(offline=True)
        self.assertEqual(self.downloads, [])

    def test_with_the_image_archives_present_nothing_is_downloaded(self):
        self.run_root()
        (self.shared / 'paradee-wheels').mkdir()
        self.python.unlink()
        self.downloads.clear()
        with patch.object(installer, 'verify_paradee_wheels'):
            result, venv, _printed = self.run_root()
        self.assertTrue(result)
        self.assertEqual(self.downloads, [])
        self.assertEqual(venv.call_args.args[0], self.shared / 'paradee-wheels')

    def umask(self, mask):
        previous = os.umask(mask)
        self.addCleanup(os.umask, previous)

    def modes(self, top):
        """Every path under top, with its mode, not following symlinks."""
        found = {'.': stat.S_IMODE(top.lstat().st_mode)}
        for current, directories, files in os.walk(top):
            for name in directories + files:
                path = Path(current) / name
                found[str(path.relative_to(top))] = stat.S_IMODE(path.lstat().st_mode)
        return found

    def venv_with_cfg(self, wheelhouse, lock, python):
        """The fake venv, plus the pyvenv.cfg and executable bit a real one has."""
        type(self).venv(self, wheelhouse, lock, python)
        (python.parents[1] / 'pyvenv.cfg').write_text('home = /usr/bin\n')
        python.chmod(0o755)
        (python.parents[1] / 'lib').mkdir(exist_ok=True)
        (python.parents[1] / 'lib' / 'module.py').write_text('x = 1\n')

    def expected_runtime_modes(self):
        expected = {'.': 0o755, 'onnx': 0o755, 'notices': 0o755}
        expected.update({name: 0o644 for name in installer.PARADEE_FILES})
        return expected

    def expected_venv_modes(self):
        return {'.': 0o755, 'bin': 0o755, 'bin/python': 0o755, 'pyvenv.cfg': 0o644,
                'lib': 0o755, 'lib/module.py': 0o644}

    def test_a_0077_umask_still_leaves_a_runtime_the_desktop_user_can_read(self):
        # sudo keeps the caller's umask. Under 0077 the runtime came out root-only.
        self.umask(0o077)
        with patch.object(self, 'venv', self.venv_with_cfg):
            result, _venv, _printed = self.run_root()
        self.assertTrue(result)
        self.assertEqual(self.modes(self.runtime), self.expected_runtime_modes())
        self.assertEqual(self.modes(self.python.parents[1]), self.expected_venv_modes())
        self.assertEqual(stat.S_IMODE(self.shared.stat().st_mode), 0o755)
        self.assertEqual(self.modes(self.docs), self.expected_docs_modes())
        # The caller's umask is put back.
        self.assertEqual(os.umask(0o077), 0o077)

    def test_a_runtime_an_earlier_run_left_root_only_is_repaired(self):
        with patch.object(self, 'venv', self.venv_with_cfg):
            self.run_root()
        # What a run under umask 0077 left: nothing for group or other.
        for top in (self.runtime, self.python.parents[1]):
            for current, _directories, files in os.walk(top):
                os.chmod(current, 0o700)
                for name in files:
                    path = Path(current) / name
                    os.chmod(path, stat.S_IMODE(path.stat().st_mode) & 0o700)
        self.downloads.clear()
        result, _venv, _printed = self.run_root()
        self.assertTrue(result)
        self.assertEqual(self.downloads, [])
        self.assertEqual(self.modes(self.runtime), self.expected_runtime_modes())
        self.assertEqual(self.modes(self.python.parents[1]), self.expected_venv_modes())

    def test_the_parent_of_the_default_runtime_is_made_readable(self):
        kilix = self.root / 'kilix'
        kilix.mkdir(mode=0o700)
        self.runtime = kilix / 'paradee'
        with patch.object(installer, 'PARADEE_RUNTIME', self.runtime):
            result, _venv, _printed = self.run_root()
        self.assertTrue(result)
        self.assertEqual(stat.S_IMODE(kilix.stat().st_mode), 0o755)

    def test_an_interpreter_outside_a_venv_is_not_walked(self):
        # --paradee-python /usr/bin/python3 must not chmod /usr.
        usr = self.root / 'usr'
        (usr / 'bin').mkdir(parents=True)
        self.python = usr / 'bin' / 'python3'
        self.python.write_bytes(b'#!/bin/sh\n')
        self.python.chmod(0o700)
        secret = usr / 'private'
        secret.mkdir(mode=0o700)
        (secret / 'key').write_text('k')
        os.chmod(secret / 'key', 0o600)
        before = self.modes(usr)
        result, _venv, _printed = self.run_root()
        self.assertTrue(result)
        self.assertEqual(self.modes(usr), before)

    def outside_dir(self):
        """A root-only directory outside the runtime, holding a root-only file."""
        outside = self.root / 'outside'
        outside.mkdir(mode=0o700)
        (outside / 'paradee_int8.onnx').write_bytes(b'outside')
        os.chmod(outside / 'paradee_int8.onnx', 0o600)
        return outside

    def test_a_symlinked_runtime_is_refused_before_anything_is_downloaded(self):
        outside = self.outside_dir()
        before = self.modes(outside)
        self.runtime.symlink_to(outside)
        self.umask(0o077)
        with self.assertRaisesRegex(ValueError, 'Paradee runtime path is a symlink'):
            self.run_root()
        self.assertEqual(self.downloads, [])
        self.assertEqual(self.modes(outside), before)
        self.assertEqual(os.umask(0o077), 0o077)

    def test_a_symlink_inside_the_runtime_is_refused(self):
        for name in ('onnx', 'notices', 'config.json', 'onnx/paradee_int8.onnx'):
            with self.subTest(name=name):
                shutil.rmtree(self.root / 'outside', ignore_errors=True)
                shutil.rmtree(self.runtime, ignore_errors=True)
                outside = self.outside_dir()
                (self.runtime / 'onnx').mkdir(parents=True)
                target = outside / 'paradee_int8.onnx' if '.' in name else outside
                link = self.runtime / name
                if link.exists():
                    link.rmdir()
                link.symlink_to(target)
                before = self.modes(outside)
                self.downloads.clear()
                with self.assertRaisesRegex(ValueError, 'Paradee runtime path is a symlink'):
                    self.run_root()
                self.assertEqual(self.downloads, [])
                self.assertEqual(self.modes(outside), before)

    def test_staging_and_publishing_refuse_a_symlink_on_their_own(self):
        self.run_root()
        outside = self.outside_dir()
        shutil.rmtree(self.runtime / 'notices')
        (self.runtime / 'notices').symlink_to(outside)
        before = self.modes(outside)
        with self.assertRaisesRegex(ValueError, 'Paradee runtime path is a symlink'):
            installer.publish_paradee_runtime(self.runtime)
        with self.assertRaisesRegex(ValueError, 'Paradee runtime path is a symlink'):
            installer.stage_paradee_runtime(self.shared / self.pin['filename'], self.pin, self.runtime)
        self.assertEqual(self.modes(outside), before)

    def test_symlinks_in_the_venv_are_not_followed(self):
        outside = self.root / 'outside'
        outside.mkdir(mode=0o700)
        (outside / 'file').write_text('o')
        os.chmod(outside / 'file', 0o600)
        with patch.object(self, 'venv', self.venv_with_cfg):
            self.run_root()
        (self.python.parents[1] / 'lib' / 'link').symlink_to(outside)
        (self.python.parents[1] / 'lib' / 'filelink').symlink_to(outside / 'file')
        installer.publish_paradee_venv(self.python.parents[1])
        self.assertEqual(stat.S_IMODE(outside.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((outside / 'file').stat().st_mode), 0o600)

    def expected_docs_modes(self, *, source=True):
        names = installer.ESPEAK_NOTICES + ((self.espeak['filename'],) if source else ())
        return {'.': 0o755, **{name: 0o644 for name in names}}

    def test_an_upgrade_installs_the_espeak_source_and_loader_texts(self):
        result, _venv, _printed = self.run_root()
        self.assertTrue(result)
        self.assertEqual(self.modes(self.docs), self.expected_docs_modes())
        bundles = ROOT / 'provision' / 'bundles'
        for name in installer.ESPEAK_NOTICES:
            self.assertEqual((self.docs / name).read_bytes(), (bundles / name).read_bytes())
        self.assertEqual((self.docs / self.espeak['filename']).read_bytes(),
                         self.upstream[self.espeak['url']])
        # The same files the image installs.
        preseed = (ROOT / 'preseed' / 'preseed.cfg').read_text()
        for name in installer.ESPEAK_NOTICES + (self.espeak['filename'],):
            self.assertIn('/target' + str(installer.ESPEAK_DOCS / name), preseed)
        self.downloads.clear()
        self.assertTrue(self.run_root()[0])
        self.assertEqual(self.downloads, [])

    def test_a_failed_espeak_download_leaves_only_the_source_out(self):
        self.upstream[self.espeak['url']] = OSError('network is unreachable')
        result, _venv, printed = self.run_root()
        self.assertTrue(result)
        self.assertEqual(self.modes(self.docs), self.expected_docs_modes(source=False))
        messages = [call.args[0] for call in printed.call_args_list]
        self.assertTrue(any('espeak-ng source was not installed' in message
                            and 'the next upgrade tries again' in message for message in messages))
        # The next upgrade tries again.
        self.upstream[self.espeak['url']] = b'espeak-ng-source' * 30
        self.downloads.clear()
        self.assertTrue(self.run_root()[0])
        self.assertEqual(self.downloads, [self.espeak['url']])
        self.assertEqual(self.modes(self.docs), self.expected_docs_modes())

    def test_other_espeak_source_bytes_are_refused(self):
        self.upstream[self.espeak['url']] = b'other-source' * 40
        result, _venv, printed = self.run_root()
        self.assertTrue(result)
        self.assertFalse((self.docs / self.espeak['filename']).exists())
        self.assertEqual(sorted(path.name for path in self.docs.iterdir()),
                         sorted(installer.ESPEAK_NOTICES))
        messages = [call.args[0] for call in printed.call_args_list]
        self.assertTrue(any('espeak-ng source size or checksum mismatch' in message for message in messages))

    def test_a_fresh_install_copies_the_loader_texts_and_downloads_nothing(self):
        self.run_root()
        for path in self.docs.iterdir():
            path.unlink()
        self.downloads.clear()
        result, _venv, printed = self.run_root(offline=True)
        self.assertTrue(result)
        self.assertEqual(self.downloads, [])
        self.assertEqual(self.modes(self.docs), self.expected_docs_modes(source=False))
        messages = [call.args[0] for call in printed.call_args_list]
        self.assertTrue(any('did not supply it' in message for message in messages))

    def test_files_already_there_are_left_alone(self):
        self.docs.mkdir(parents=True)
        for name in installer.ESPEAK_NOTICES + (self.espeak['filename'],):
            (self.docs / name).write_bytes(b'already here')
        self.assertTrue(self.run_root()[0])
        self.assertNotIn(self.espeak['url'], self.downloads)
        for name in installer.ESPEAK_NOTICES + (self.espeak['filename'],):
            self.assertEqual((self.docs / name).read_bytes(), b'already here')

    def test_a_loader_licence_other_than_the_pinned_one_is_refused(self):
        self.espeak['loader_licence_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'espeakng-loader licence size or checksum mismatch'):
            self.run_root()
        self.assertFalse((self.docs / 'espeakng-loader-0.2.4-LICENSE').exists())

    def test_the_espeak_pin_is_checked(self):
        pin = installer.load_espeak_pin()
        self.assertEqual(pin['sha256'], 'bb4338102ff3b49a81423da8a1a158b420124b055b60fa76cfb4b18677130a23')
        for change in ({'url': 'http://example.invalid/x.tar.gz'}, {'filename': '../x'},
                       {'bytes': 0}, {'sha256': 'x'}, {'loader_licence_sha256': None},
                       {'schema': 'other'}):
            path = self.root / 'pin.json'
            path.write_text(json.dumps({**pin, **change}))
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'invalid espeak-ng'):
                installer.load_espeak_pin(path)

    def test_the_download_is_https_and_exactly_the_pinned_size(self):
        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False
        with self.assertRaisesRegex(ValueError, 'not https'):
            installer._download_pinned('http://example.invalid/x', 4, self.root / 'x')
        import urllib.request
        for body, message in ((b'abc', 'incomplete'), (b'abcde', 'exceeds')):
            target = self.root / message
            with self.subTest(body=body), \
                    patch.object(urllib.request, 'urlopen', return_value=Response(body)), \
                    self.assertRaisesRegex(ValueError, message):
                installer._download_pinned('https://example.invalid/x', 4, target)
        with patch.object(urllib.request, 'urlopen', return_value=Response(b'abcd')):
            installer._download_pinned('https://example.invalid/x', 4, self.root / 'exact')
        self.assertEqual((self.root / 'exact').read_bytes(), b'abcd')


class InstallPolicyTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.receipts = []
        self.eligible = False
        self.covered = False
        self.fetch_error = None
        record = SimpleNamespace(id='lfm2-kilix-commands', digest='e' * 64,
                                 expected_decision='record')
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

            def capture_agreement(inner, record, typed=None):
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
                if self.fetch_error is not None:
                    raise self.fetch_error

            def ensure_supplied_asset(inner, spec, **kwargs):
                self.calls.append(('supplied', spec.asset_id, str(kwargs['supplied'])))

        api = SimpleNamespace(Installer=Installer, InstallError=type('InstallError', (RuntimeError,), {}))
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

    def test_command_model_records_its_notice_terms_and_reads_the_cache(self):
        installer.install_command_model(Path('/kilix'), self.pin, self.cache)
        # A notice record: no typed answer is passed, so none is recorded.
        self.assertEqual(self.calls[0], ('capture', None, 'lfm2-kilix-commands'))
        self.assertEqual(self.calls[1][0], 'upstream')
        self.assertNotIn('supplied', [kind for kind, *_rest in self.calls])
        self.assertEqual(self.receipts[0]['catalogue_digest'], 'c' * 64)
        self.assertEqual(os.environ['KILIX_CONTENT_ARCHIVE_CACHE'], str(self.cache))

    def test_terms_that_need_agreement_are_never_answered_by_the_image(self):
        self.record.expected_decision = 'accept'
        with self.assertRaisesRegex(ValueError, 'never answers'):
            installer.install_command_model(Path('/kilix'), self.pin, self.cache)
        self.assertEqual(self.receipts, [])
        self.assertNotIn('capture', [kind for kind, *_rest in self.calls])
        self.assertNotIn('upstream', [kind for kind, *_rest in self.calls])

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


    def kinds(self):
        return [kind for kind, *_rest in self.calls]

    def test_demucs_from_the_image_uses_the_standard_policy_and_supplied_bytes(self):
        self.eligible = True
        self.spec.asset_id = 'demucs-htdemucs-6s'
        self.spec.manifest_digest = DEMUCS_MANIFEST
        case = DemucsArchiveTests('test_the_archive_is_reproducible_and_verifies')
        case.setUp()
        self.addCleanup(case.doCleanups)
        pin = case.forge(case.build('image.tar', case.pin))
        pin['manifest_digest'] = DEMUCS_MANIFEST
        installer.install_demucs(Path('/kilix'), case.root / 'image.tar', pin, offline=True)
        self.assertEqual(self.kinds(), ['authorize', 'supplied'])

    def test_demucs_refuses_custom_terms_before_a_download(self):
        self.spec.asset_id = 'demucs-htdemucs-6s'
        self.spec.manifest_digest = DEMUCS_MANIFEST
        with self.assertRaisesRegex(ValueError, 'standard distribution policy'):
            installer.install_demucs(Path('/kilix'), None, _demucs_pin(), offline=False)
        self.assertEqual(self.calls, [])

    def test_offline_never_downloads_demucs_or_medium(self):
        self.eligible = True
        with patch('builtins.print') as shown:
            installer.install_demucs(Path('/kilix'), None, _demucs_pin(), offline=True)
            installer.install_whisper_medium(Path('/kilix'), MEDIUM_MANIFEST, offline=True)
        self.assertEqual(self.calls, [])
        text = ' '.join(str(call) for call in shown.call_args_list)
        self.assertIn('first online upgrade downloads it', text)

    def test_online_downloads_what_the_image_did_not_supply(self):
        self.eligible = True
        self.spec.asset_id = 'demucs-htdemucs-6s'
        self.spec.manifest_digest = DEMUCS_MANIFEST
        installer.install_demucs(Path('/kilix'), None, _demucs_pin(), offline=False)
        self.spec.asset_id = 'faster-whisper-medium-en'
        self.spec.manifest_digest = MEDIUM_MANIFEST
        installer.install_whisper_medium(Path('/kilix'), MEDIUM_MANIFEST, offline=False)
        self.assertEqual(self.calls, [
            ('authorize', 'demucs-htdemucs-6s'), ('upstream', 'demucs-htdemucs-6s', None),
            ('authorize', 'faster-whisper-medium-en'), ('upstream', 'faster-whisper-medium-en', None)])

    def test_a_failed_download_is_reported_and_does_not_stop_the_run(self):
        self.eligible = True
        self.spec.asset_id = 'faster-whisper-medium-en'
        self.spec.manifest_digest = MEDIUM_MANIFEST
        for error in (RuntimeError('all content downloads failed'), OSError('network is unreachable')):
            self.fetch_error = error
            with self.subTest(error=error), patch('sys.stderr', new_callable=io.StringIO) as stderr:
                self.assertFalse(installer.fetch_default(Path('/kilix'), 'faster-whisper-medium-en',
                                                         'Whisper medium.en', MEDIUM_MANIFEST))
                self.assertIn('the next upgrade tries again', stderr.getvalue())
        # Anything else is a defect, not a download failure.
        self.fetch_error = KeyError('bug')
        with self.assertRaises(KeyError):
            installer.fetch_default(Path('/kilix'), 'faster-whisper-medium-en', 'Whisper medium.en',
                                    MEDIUM_MANIFEST)

    def incomplete(self):
        """Verify as kilix-content does when a receipt exists but its files do not."""
        error = self.cm._api().InstallError

        def verify(*args, **kwargs):
            raise error('could not open supplied file: README.md')
        self.cm._verify = verify

    def test_the_upgrade_after_a_failed_download_downloads_again(self):
        self.eligible = True
        self.spec.asset_id = 'faster-whisper-medium-en'
        self.spec.manifest_digest = MEDIUM_MANIFEST
        # This upgrade records the receipt, then the download fails.
        self.fetch_error = RuntimeError('all content downloads failed')
        with patch('sys.stderr', new_callable=io.StringIO):
            installer.install_whisper_medium(Path('/kilix'), MEDIUM_MANIFEST, offline=False)
        # The next one finds that receipt and no files: it must try again, not stop.
        self.incomplete()
        self.fetch_error = None
        with patch('sys.stderr', new_callable=io.StringIO) as stderr, \
                patch('sys.stdout', new_callable=io.StringIO):
            installer.install_whisper_medium(Path('/kilix'), MEDIUM_MANIFEST, offline=False)
            self.spec.asset_id = 'demucs-htdemucs-6s'
            self.spec.manifest_digest = DEMUCS_MANIFEST
            installer.install_demucs(Path('/kilix'), None, _demucs_pin(), offline=False)
            # Offline, an incomplete install still downloads nothing.
            installer.install_demucs(Path('/kilix'), None, _demucs_pin(), offline=True)
            installer.install_whisper_medium(Path('/kilix'), MEDIUM_MANIFEST, offline=True)
        self.assertEqual(self.calls, [
            ('authorize', 'faster-whisper-medium-en'), ('upstream', 'faster-whisper-medium-en', None),
            ('authorize', 'faster-whisper-medium-en'), ('upstream', 'faster-whisper-medium-en', None),
            ('authorize', 'demucs-htdemucs-6s'), ('upstream', 'demucs-htdemucs-6s', None)])
        self.assertIn('is not completely installed', stderr.getvalue())
        self.assertIn('installing it again', stderr.getvalue())

    def test_an_incomplete_image_model_is_installed_again_from_the_image(self):
        self.eligible = True
        self.incomplete()
        self.spec.asset_id = 'basic-pitch-icassp-2022-onnx'
        self.spec.manifest_digest = MANIFEST
        pin = json.loads((ROOT / 'provision/basic-pitch-model.json').read_text())
        archive = ROOT / 'provision/bundles/basic-pitch-icassp-2022-onnx.tar.xz'
        with patch('sys.stderr', new_callable=io.StringIO):
            installer.install_basic_pitch(Path('/kilix'), archive, pin)
        self.assertEqual(self.kinds(), ['authorize', 'supplied'])

    def test_the_command_model_still_stops_on_an_incomplete_install(self):
        # Unchanged from 0.2.3-rc5's approved installer: only Playalong defaults retry.
        self.incomplete()
        with self.assertRaises(self.cm._api().InstallError):
            installer.install_command_model(Path('/kilix'), self.pin, self.cache)
        self.assertEqual(self.calls, [])

    def test_a_download_runs_only_for_the_pinned_asset(self):
        self.eligible = True
        for asset_id, digest in (('faster-whisper-large-v3', MEDIUM_MANIFEST),
                                 ('faster-whisper-medium-en', 'e' * 64)):
            self.spec.asset_id, self.spec.manifest_digest = asset_id, digest
            with self.subTest(asset_id=asset_id), \
                    self.assertRaisesRegex(ValueError, 'differs from the Playalong inventory'):
                installer.fetch_default(Path('/kilix'), 'faster-whisper-medium-en', 'Whisper medium.en',
                                        MEDIUM_MANIFEST)
        self.assertEqual(self.calls, [])

    def test_verified_playalong_models_are_left_alone(self):
        self.cm._verify = lambda *args, **kwargs: 0
        installer.install_demucs(Path('/kilix'), None, _demucs_pin(), offline=False)
        installer.install_whisper_medium(Path('/kilix'), MEDIUM_MANIFEST, offline=False)
        self.assertEqual(self.calls, [])

    def test_page_ocr_from_the_image_uses_the_standard_policy_and_supplied_bytes(self):
        self.eligible = True
        case = PageOcrArchiveTests('test_the_archives_are_reproducible_verify_and_unpack')
        case.setUp()
        self.addCleanup(case.doCleanups)
        for asset_id, (manifest, *_rest) in PP_OCR.items():
            self.calls.clear()
            self.spec.asset_id, self.spec.manifest_digest = asset_id, manifest
            _raw, pin = case.build(asset_id, asset_id + '-image.tar')
            with self.subTest(asset=asset_id), patch('builtins.print'):
                installer.install_pp_ocr(Path('/kilix'), case.root / (asset_id + '-image.tar'), pin, offline=True)
                self.assertEqual(self.calls, [('authorize', asset_id),
                                              ('supplied', asset_id, self.calls[1][2])])

    def test_page_ocr_downloads_only_online_and_only_its_pinned_asset(self):
        self.eligible = True
        for asset_id, (manifest, *_rest) in PP_OCR.items():
            pin = _pp_ocr_pin(asset_id)
            self.spec.asset_id, self.spec.manifest_digest = asset_id, manifest
            with self.subTest(asset=asset_id):
                self.calls.clear()
                with patch('builtins.print') as shown:
                    installer.install_pp_ocr(Path('/kilix'), None, pin, offline=True)
                self.assertEqual(self.calls, [])
                self.assertIn('the first online upgrade downloads it', str(shown.call_args))
                with patch('builtins.print'):
                    installer.install_pp_ocr(Path('/kilix'), None, pin, offline=False)
                self.assertEqual(self.calls, [('authorize', asset_id), ('upstream', asset_id, None)])
                self.calls.clear()
                self.spec.manifest_digest = 'e' * 64
                with self.assertRaisesRegex(ValueError, asset_id + ' catalog differs from its image pin'):
                    installer.install_pp_ocr(Path('/kilix'), None, pin, offline=False)
                self.assertEqual(self.calls, [])
        self.cm._verify = lambda *args, **kwargs: 0
        with patch('builtins.print'):
            installer.install_pp_ocr(Path('/kilix'), None, _pp_ocr_pin('pp-ocrv6-small-det'), offline=False)
        self.assertEqual(self.calls, [])

    def test_page_ocr_refuses_custom_terms_before_a_download(self):
        self.spec.asset_id, self.spec.manifest_digest = 'pp-ocrv6-small-rec', PP_OCR['pp-ocrv6-small-rec'][0]
        with self.assertRaisesRegex(ValueError, 'standard distribution policy'):
            installer.install_pp_ocr(Path('/kilix'), None, _pp_ocr_pin('pp-ocrv6-small-rec'), offline=False)
        self.assertEqual(self.calls, [])

    def kilix_module(self, *, declined=None, error=None, defaults=None):
        module = SimpleNamespace(DEFAULT_MODELS=defaults or installer.PLAYALONG_DEFAULTS)

        def answer():
            if error is not None:
                raise error
            return declined
        module.declined = answer
        return patch.dict(sys.modules, playalong_models=module)

    def test_the_kilix_answer_decides(self):
        with self.kilix_module():
            self.assertIsNone(installer.playalong_declined(Path('/kilix')))
        with self.kilix_module(declined='KILIX_PLAYALONG_MODELS=0 in settings.conf'):
            self.assertEqual(installer.playalong_declined(Path('/kilix')),
                             'KILIX_PLAYALONG_MODELS=0 in settings.conf')
        with self.kilix_module(error=ValueError('unsupported model wizard state')):
            self.assertIn('cannot be read', installer.playalong_declined(Path('/kilix')))
        with self.kilix_module(defaults=('demucs-htdemucs-6s', 'basic-pitch-icassp-2022-onnx',
                                         'faster-whisper-large-v3')):
            with self.assertRaisesRegex(ValueError, 'other Playalong default models'):
                installer.playalong_declined(Path('/kilix'))
        self.assertNotIn('faster-whisper-large-v3', installer.PLAYALONG_DEFAULTS)


class PlayalongInventoryTests(unittest.TestCase):
    def pins(self):
        load = lambda name: json.loads((ROOT / 'provision' / name).read_text())
        return load('playalong-models.json'), load('basic-pitch-model.json'), load('demucs-model.json')

    def test_the_inventory_matches_both_image_pins_and_the_catalog(self):
        inventory, basic, demucs = self.pins()
        installer.validate_playalong_inventory(inventory, basic, demucs)
        self.assertEqual(inventory['assets']['faster-whisper-medium-en'],
                         {'delivery': 'online', 'manifest_digest': MEDIUM_MANIFEST})
        self.assertEqual(inventory['assets']['demucs-htdemucs-6s']['manifest_digest'], DEMUCS_MANIFEST)
        self.assertEqual(inventory['assets']['basic-pitch-icassp-2022-onnx']['manifest_digest'], MANIFEST)

    def test_a_drifted_inventory_is_refused(self):
        inventory, basic, demucs = self.pins()
        cases = {
            'large-v3 made a default': lambda i: i['assets'].update(
                {'faster-whisper-large-v3': {'delivery': 'online', 'manifest_digest': 'a' * 64}}),
            'medium in the image': lambda i: i['assets']['faster-whisper-medium-en'].update(delivery='image'),
            'demucs online only': lambda i: i['assets']['demucs-htdemucs-6s'].update(delivery='online'),
            'stale demucs manifest': lambda i: i['assets']['demucs-htdemucs-6s'].update(
                manifest_digest='a' * 64),
            'other opt-out': lambda i: i['declined_by'].update(setting='KILIX_SPLIT_MODELS'),
        }
        for name, change in cases.items():
            planted = json.loads(json.dumps(inventory))
            change(planted)
            with self.subTest(name=name), self.assertRaises(ValueError):
                installer.validate_playalong_inventory(planted, basic, demucs)


class PlayalongOrderTests(unittest.TestCase):
    def run_main(self, declined, *extra):
        calls = []

        def record(name):
            return lambda *args, **kwargs: calls.append((name, kwargs.get('offline')))
        with patch.object(installer, 'playalong_declined', return_value=declined), \
                patch.object(installer, 'install_basic_pitch', record('basic-pitch')), \
                patch.object(installer, 'install_demucs', record('demucs')), \
                patch.object(installer, 'install_paradee', record('paradee')), \
                patch.object(installer, 'install_spacy', record('spacy')), \
                patch.object(installer, 'install_command_model', record('command')), \
                patch.object(installer, 'install_pp_ocr',
                             lambda kilix, archive, pin, **kwargs: calls.append(
                                 (pin['asset_id'], kwargs.get('offline')))), \
                patch.object(installer, 'install_whisper_medium', record('medium')), \
                patch('builtins.print'):
            self.assertEqual(installer.main(['--kilix', '/kilix', *extra]), 0)
        return calls

    def test_image_models_first_and_the_large_download_last(self):
        self.assertEqual(self.run_main(None, '--offline'), [
            ('basic-pitch', None), ('demucs', True), ('paradee', True), ('spacy', True),
            ('command', None), ('pp-ocrv6-small-det', True), ('pp-ocrv6-small-rec', True),
            ('medium', True)])
        self.assertEqual(self.run_main(None), [
            ('basic-pitch', None), ('demucs', False), ('paradee', False), ('spacy', False),
            ('command', None), ('pp-ocrv6-small-det', False), ('pp-ocrv6-small-rec', False),
            ('medium', False)])

    def test_a_declining_machine_still_gets_paradee_page_ocr_and_the_command_model(self):
        self.assertEqual(self.run_main("the model wizard's Playalong page was answered no"),
                         [('paradee', False), ('spacy', False), ('command', None),
                          ('pp-ocrv6-small-det', False), ('pp-ocrv6-small-rec', False)])
        self.assertEqual(self.run_main('whether this machine declined them cannot be read (x)',
                                       '--offline'),
                         [('paradee', True), ('spacy', True), ('command', None),
                          ('pp-ocrv6-small-det', True), ('pp-ocrv6-small-rec', True)])


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

    def test_demucs_travels_from_the_build_to_the_installed_system(self):
        preseed = (ROOT / 'preseed/preseed.cfg').read_text()
        remaster = (ROOT / 'build/remaster-iso.sh').read_text()
        self.assertIn(
            'cp /cdrom/plebian-os/demucs-htdemucs-6s.tar '
            '/target/usr/local/share/plebian-os/demucs-htdemucs-6s.tar', preseed)
        self.assertIn('chmod 0644 /target/usr/local/share/plebian-os/demucs-htdemucs-6s.tar', preseed)
        self.assertEqual(installer.SHARED_BASIC_PITCH / _demucs_pin()['filename'],
                         Path('/usr/local/share/plebian-os/demucs-htdemucs-6s.tar'))
        staged = remaster.index('install -m 0644 "$DEMUCS_MODEL_BUNDLE" '
                                '"$EXTRACT/plebian-os/demucs-htdemucs-6s.tar"')
        # A supplied archive is checked early; a built one comes from the pinned
        # URL through the bounded download and is checked again before staging.
        self.assertIn('DEMUCS_MODEL_BUNDLE="${PLEBIAN_OS_DEMUCS_MODEL_BUNDLE:-}"', remaster)
        download = remaster.index('_bounded_download "$demucs_weight_bytes" 1800 "$WORK/demucs-weights.th"')
        built = remaster.index('--build-demucs-archive "$DEMUCS_MODEL_BUNDLE"')
        checked = remaster.rindex('--demucs "$DEMUCS_MODEL_BUNDLE"')
        self.assertLess(download, built)
        self.assertLess(built, checked)
        self.assertLess(checked, staged)
        self.assertLess(remaster.index('WORK="$(mktemp -d'), download)

    def test_page_ocr_travels_from_the_build_to_the_installed_system(self):
        preseed = (ROOT / 'preseed/preseed.cfg').read_text()
        remaster = (ROOT / 'build/remaster-iso.sh').read_text()
        self.assertIn('build_pp_ocr_bundle() {', remaster)
        download = remaster.index('_bounded_download "$bytes" 600 "$files/$name"')
        built = remaster.index('--build-pp-ocr-archive "$asset_id" "$WORK/$asset_id.tar"')
        self.assertLess(remaster.index('WORK="$(mktemp -d'), download)
        self.assertLess(download, built)
        for asset_id, variable in (('pp-ocrv6-small-det', 'PP_OCR_DET_MODEL_BUNDLE'),
                                   ('pp-ocrv6-small-rec', 'PP_OCR_REC_MODEL_BUNDLE')):
            with self.subTest(asset=asset_id):
                self.assertEqual(installer.SHARED_BASIC_PITCH / _pp_ocr_pin(asset_id)['filename'],
                                 Path(f'/usr/local/share/plebian-os/{asset_id}.tar'))
                self.assertIn(
                    f'cp /cdrom/plebian-os/{asset_id}.tar /target/usr/local/share/plebian-os/{asset_id}.tar',
                    preseed)
                self.assertIn(f'chmod 0644 /target/usr/local/share/plebian-os/{asset_id}.tar', preseed)
                # A supplied archive is checked early; a built one is checked
                # again before staging.
                self.assertIn(f'{variable}="${{PLEBIAN_OS_{variable}:-}}"', remaster)
                called = remaster.index(f'    build_pp_ocr_bundle {asset_id}\n')
                checked = remaster.rindex(f'--{asset_id} "${variable}"')
                staged = remaster.index(f'install -m 0644 "${variable}" "$EXTRACT/plebian-os/{asset_id}.tar"')
                self.assertLess(built, called)
                self.assertLess(called, checked)
                self.assertLess(checked, staged)

    def test_paradee_travels_from_the_build_to_the_installed_system(self):
        preseed = (ROOT / 'preseed/preseed.cfg').read_text()
        remaster = (ROOT / 'build/remaster-iso.sh').read_text()
        provision = (ROOT / 'provision/plebian-os-provision.sh').read_text()
        self.assertIn(
            'cp /cdrom/plebian-os/paradee-8m-v1.2.tar '
            '/target/usr/local/share/plebian-os/paradee-8m-v1.2.tar', preseed)
        self.assertIn(
            'tar -x -C /target/usr/lib/kilix/paradee -f /cdrom/plebian-os/paradee-8m-v1.2.tar '
            'onnx/paradee_int8.onnx config.json notices/LICENSE-apache-2.0.txt', preseed)
        self.assertIn(
            'cp /cdrom/plebian-os/en-core-web-sm-3.8.0.tar '
            '/target/usr/local/share/plebian-os/en-core-web-sm-3.8.0.tar', preseed)
        self.assertIn(
            'cp -a /cdrom/plebian-os/paradee-wheels/. '
            '/target/usr/local/share/plebian-os/paradee-wheels/', preseed)
        self.assertIn('--verify-paradee-wheels "$WORK/paradee-wheels"', remaster)
        self.assertIn('"$EXTRACT/plebian-os/paradee-wheels/"', remaster)
        download = remaster.index('_bounded_download "$paradee_onnx_bytes" 1800 "$WORK/paradee_int8.onnx"')
        built = remaster.index('--build-paradee-archive "$PARADEE_MODEL_BUNDLE"')
        checked = remaster.rindex('--paradee "$PARADEE_MODEL_BUNDLE"')
        staged = remaster.index('install -m 0644 "$PARADEE_MODEL_BUNDLE" '
                                '"$EXTRACT/plebian-os/paradee-8m-v1.2.tar"')
        self.assertLess(download, built)
        self.assertLess(built, checked)
        self.assertLess(checked, staged)
        # A fresh install stages the runtime from the image only; an upgrade, as
        # root and before the desktop user's step, downloads what the image did not supply.
        self.assertIn(
            '"$PLEBIAN_OS_DIR/provision/install-image-models.py" \\\n'
            '        --install-paradee-runtime --offline', provision)
        self.assertLess(provision.index('--install-paradee-runtime'),
                        provision.index('install-image-models.py" --kilix "$KILIX_DIR" --offline'))
        update = (ROOT / 'provision/plebian-os-update.sh').read_text()
        root_step = update.index(
            '"${command_model_elevate[@]}" /usr/bin/python3 \\\n'
            '        "$PLEBIAN_OS_DIR/provision/install-image-models.py" --install-paradee-runtime \\\n'
            '        --no-ollama-runtime \\\n'
            '        || die "required Paradee runtime staging failed"')
        self.assertLess(update.index('test_fail_after_boundary default-models'), root_step)
        self.assertLess(root_step, update.index('test_fail_after_boundary paradee-runtime'))
        self.assertLess(update.index('test_fail_after_boundary paradee-runtime'),
                        update.index('install-image-models.py" --kilix "$KILIX_DIR"'))
        source = json.loads((ROOT / 'provision/espeak-ng-source.json').read_text())
        licence = (ROOT / 'provision/bundles/espeakng-loader-0.2.4-LICENSE').read_bytes()
        self.assertEqual(hashlib.sha256(licence).hexdigest(), source['loader_licence_sha256'])
        self.assertEqual(len(licence), 1069)
        self.assertEqual(source['bytes'], 17739803)
        self.assertEqual(source['sha256'],
                         'bb4338102ff3b49a81423da8a1a158b420124b055b60fa76cfb4b18677130a23')
        self.assertIn('espeak-ng source size or checksum mismatch', remaster)
        self.assertIn(
            'cp /cdrom/plebian-os/espeak-ng-1.52.0.tar.gz '
            '/target/usr/local/share/doc/plebian-os/espeak-ng/espeak-ng-1.52.0.tar.gz', preseed)
        self.assertIn('espeakng-loader-0.2.4-LICENSE', preseed)
        self.assertIn('espeakng-loader-0.2.4-build.sh', preseed)


if __name__ == '__main__':
    unittest.main()
