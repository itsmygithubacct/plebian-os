import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('command_model_stager', ROOT / 'provision/stage-command-model.py')
stager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stager)


class CommandModelDeliveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.document = b'Full model licence fixture\n'
        payload = io.BytesIO()
        with tarfile.open(fileobj=payload, mode='w:gz') as archive:
            for name, data in [('notices/LICENSE.txt', self.document), ('model.gguf', b'weights')]:
                member = tarfile.TarInfo('fixture-v1/' + name)
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
        self.payload = payload.getvalue()
        self.pin = dict(version='fixture-v1', weight_version='fixture.1', root='fixture-v1',
                        bytes=len(self.payload), sha256=hashlib.sha256(self.payload).hexdigest(),
                        url='https://example.invalid/model.tar.gz', documents={
                            'notices/LICENSE.txt': dict(bytes=len(self.document),
                                sha256=hashlib.sha256(self.document).hexdigest())})
        self.pin_path = self.root / 'command-model.json'
        self.pin_path.write_text(json.dumps(self.pin))
        mocked_file = patch.object(stager, '__file__', str(self.root / 'stage-command-model.py'))
        mocked_file.start()
        self.addCleanup(mocked_file.stop)
        self.cache = self.root / 'cache'
        self.docs = self.root / 'docs'
        self.args = ['--cache-dir', str(self.cache), '--documents-dir', str(self.docs)]
        self.archive = self.root / 'model.tar.gz'
        self.archive.write_bytes(self.payload)

    def test_offline_iso_cache_exposes_licences_without_network(self):
        self.cache.mkdir()
        cached = self.cache / self.pin['sha256']
        cached.write_bytes(self.payload)
        with patch.object(stager.urllib.request, 'urlopen') as fetch:
            stager.main(self.args + ['--offline'])
            stager.main(self.args + ['--offline'])
            fetch.assert_not_called()
        self.assertEqual((self.docs / 'fixture-v1/notices/LICENSE.txt').read_bytes(), self.document)
        self.assertEqual(cached.read_bytes(), self.payload)

    def test_upgrade_download_is_checked_and_keeps_prior_archive(self):
        self.cache.mkdir()
        prior = self.cache / ('a' * 64)
        prior.write_bytes(b'previous version')
        with patch.object(stager.urllib.request, 'urlopen', return_value=io.BytesIO(self.payload)) as fetch:
            stager.main(self.args)
            fetch.assert_called_once_with(self.pin['url'], timeout=120)
        self.assertEqual((self.cache / self.pin['sha256']).read_bytes(), self.payload)
        self.assertEqual(prior.read_bytes(), b'previous version')

    def test_bad_download_never_publishes_partial_archive(self):
        for data in (b'short', b'x' * len(self.payload), self.payload + b'extra'):
            with self.subTest(data_size=len(data)), \
                    patch.object(stager.urllib.request, 'urlopen', return_value=io.BytesIO(data)):
                with self.assertRaises(ValueError):
                    stager.main(self.args)
                self.assertFalse((self.cache / self.pin['sha256']).exists())
                self.assertFalse(self.docs.exists())

    def test_missing_media_is_fatal_offline(self):
        with patch.object(stager.urllib.request, 'urlopen') as fetch:
            with self.assertRaisesRegex(ValueError, 'media'):
                stager.main(self.args + ['--offline'])
            fetch.assert_not_called()

    def test_corrupt_or_symlinked_cache_is_refused_without_fetch(self):
        self.cache.mkdir()
        cached = self.cache / self.pin['sha256']
        for symlink in (False, True):
            if symlink:
                cached.symlink_to(self.archive)
            else:
                cached.write_bytes(b'corrupt')
            with patch.object(stager.urllib.request, 'urlopen') as fetch:
                with self.assertRaises((ValueError, OSError)):
                    stager.main(self.args)
                fetch.assert_not_called()
                self.assertFalse(self.docs.exists())
            cached.unlink()

    def test_document_pin_checked_before_archive_is_published(self):
        self.pin['documents']['notices/LICENSE.txt']['sha256'] = '0' * 64
        self.pin_path.write_text(json.dumps(self.pin))
        with self.assertRaisesRegex(ValueError, 'document checksum'):
            stager.main(self.args + ['--archive', str(self.archive), '--offline'])
        self.assertFalse((self.cache / self.pin['sha256']).exists())

    def test_verify_only_checks_real_documents_without_writes(self):
        stager.main(self.args + ['--archive', str(self.archive), '--verify-only'])
        self.assertFalse(self.cache.exists())
        self.assertFalse(self.docs.exists())

    def test_private_admin_umask_does_not_hide_shared_bytes(self):
        old = os.umask(0o077)
        try:
            stager.main(self.args + ['--archive', str(self.archive), '--offline'])
        finally:
            os.umask(old)
        for path in (self.cache, self.docs, self.docs / 'fixture-v1', self.docs / 'fixture-v1/notices'):
            self.assertEqual(path.stat().st_mode & 0o777, 0o755)
        self.assertEqual((self.cache / self.pin['sha256']).stat().st_mode & 0o777, 0o644)


if __name__ == '__main__':
    unittest.main()
