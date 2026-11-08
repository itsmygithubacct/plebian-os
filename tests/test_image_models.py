"""Basic Pitch and Demucs are on the image; they, Whisper medium.en and LFM2 install by default."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
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
                patch.object(installer, 'install_command_model', record('command')), \
                patch.object(installer, 'install_whisper_medium', record('medium')), \
                patch('builtins.print'):
            self.assertEqual(installer.main(['--kilix', '/kilix', *extra]), 0)
        return calls

    def test_image_models_first_and_the_large_download_last(self):
        self.assertEqual(self.run_main(None, '--offline'), [
            ('basic-pitch', None), ('demucs', True), ('command', None), ('medium', True)])
        self.assertEqual(self.run_main(None), [
            ('basic-pitch', None), ('demucs', False), ('command', None), ('medium', False)])

    def test_a_declining_machine_still_gets_the_command_model(self):
        self.assertEqual(self.run_main("the model wizard's Playalong page was answered no"),
                         [('command', None)])
        self.assertEqual(self.run_main('whether this machine declined them cannot be read (x)',
                                       '--offline'), [('command', None)])


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


if __name__ == '__main__':
    unittest.main()
