import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('default_models_installer', ROOT / 'provision/install-default-models.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class DefaultModelDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.payload = b'pinned bundle fixture'
        self.pin = {'bytes': len(self.payload), 'sha256': hashlib.sha256(self.payload).hexdigest(),
                    'url': 'https://example.invalid/bundle.tar.xz'}
        (self.root / 'default-models.json').write_text(json.dumps(self.pin))
        self.archive = self.root / 'bundle.tar.xz'
        self.file_patch = patch.object(installer, '__file__', str(self.root / 'install-default-models.py'))
        self.file_patch.start()
        self.addCleanup(self.file_patch.stop)

    def test_bad_archive_is_refused_before_install(self):
        self.archive.write_bytes(b'bad')
        with self.assertRaises(ValueError):
            installer.verify(self.archive, self.pin)

    def test_offline_media_is_verified_and_never_downloads(self):
        self.archive.write_bytes(self.payload)
        with patch.object(installer.urllib.request, 'urlopen') as fetch, \
                patch.object(installer.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1)) as run:
            installer.main(['--kilix', str(self.root), '--archive', str(self.archive), '--offline'])
            self.assertIn('install', run.call_args.args[0])
            self.assertIn(self.pin['sha256'], run.call_args.args[0])
            fetch.assert_not_called()

    def test_missing_offline_media_never_fetches(self):
        with patch.object(installer.urllib.request, 'urlopen') as fetch, \
                patch.object(installer.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1)) as run:
            with self.assertRaisesRegex(ValueError, 'media'):
                installer.main(['--kilix', str(self.root), '--archive', str(self.archive), '--offline'])
            self.assertEqual(run.call_count, 1)
            fetch.assert_not_called()

    def test_upgrade_download_is_bounded_and_checked(self):
        for payload in (b'wrong', self.payload + b'extra', b'x' * len(self.payload)):
            with self.subTest(payload=payload), \
                    patch.object(installer.urllib.request, 'urlopen', return_value=io.BytesIO(payload)), \
                    patch.object(installer.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1)) as run:
                with self.assertRaises(ValueError):
                    installer.main(['--kilix', str(self.root), '--archive', str(self.archive)])
                self.assertEqual(run.call_count, 1)

    def test_current_assets_need_no_bundle_download(self):
        with patch.object(installer.urllib.request, 'urlopen') as fetch, \
                patch.object(installer.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
            installer.main(['--kilix', str(self.root), '--archive', str(self.archive)])
            fetch.assert_not_called()
            self.assertEqual(run.call_count, 1)


if __name__ == '__main__':
    unittest.main()
