"""The Kilix Ask command model (LFM2) is a first-use download from 0.2.3.

The image does not carry it, a fresh install and an upgrade neither download
nor stage it, and provision/stage-command-model.py, which an updater from an
earlier release candidate still runs from the new checkout, changes nothing.
"""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('command_model_stager', ROOT / 'provision/stage-command-model.py')
stager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stager)

PIN = json.loads((ROOT / 'provision/command-model.json').read_text())
RELEASE = json.loads((ROOT / 'releases/0.2.3-command-model.json').read_text())
V9_MANIFEST = 'ef701ec2c8fb6a46bbe733d51a6be498e325bb60d3b45ec8938f0ed0ba1aef50'
V10_MANIFEST = '2600fd7a91d85669d489777c33db8e548abfe25b6c3a8659afcd4c274d26dc2c'


class StagerChangesNothingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.cache = self.root / 'cache'
        self.docs = self.root / 'docs'

    def run_stager(self, *argv):
        output = io.StringIO()
        with patch.object(stager, 'urllib', create=True) as urllib, \
                patch.object(socket, 'socket', side_effect=AssertionError('network opened')), \
                contextlib.redirect_stdout(output):
            self.assertEqual(stager.main(list(argv)), 0)
            urllib.assert_not_called()
        return output.getvalue()

    def test_every_earlier_invocation_succeeds_without_network_or_writes(self):
        archive = self.root / 'model.tar.gz'
        archive.write_bytes(b'not an archive')
        common = ['--cache-dir', str(self.cache), '--documents-dir', str(self.docs)]
        # The RC9 updater passes no arguments; RC9 provisioning passed --offline;
        # an earlier remaster passed --verify-only --archive.
        for argv in ([], ['--offline'], common, common + ['--offline'],
                     common + ['--archive', str(archive), '--offline'],
                     ['--verify-only', '--archive', str(archive)]):
            with self.subTest(argv=argv):
                printed = self.run_stager(*argv)
                self.assertIn('first-use download; nothing was staged', printed)
                self.assertFalse(self.cache.exists())
                self.assertFalse(self.docs.exists())
        self.assertEqual(archive.read_bytes(), b'not an archive')

    def test_a_previously_staged_archive_and_its_documents_are_left_alone(self):
        self.cache.mkdir()
        staged = self.cache / ('a' * 64)
        staged.write_bytes(b'previous archive')
        notices = self.docs / 'lfm2-kilix-commands-20261106-v9' / 'notices'
        notices.mkdir(parents=True)
        (notices / 'NOTICE.txt').write_bytes(b'v9 notice')
        before = sorted((p.relative_to(self.root), p.stat().st_mtime_ns) for p in self.root.rglob('*'))
        self.run_stager('--cache-dir', str(self.cache), '--documents-dir', str(self.docs))
        after = sorted((p.relative_to(self.root), p.stat().st_mtime_ns) for p in self.root.rglob('*'))
        self.assertEqual(before, after)
        self.assertEqual(staged.read_bytes(), b'previous archive')

    def test_a_pin_that_puts_the_model_on_the_media_or_stages_it_is_refused(self):
        for key, value in (('mode', 'bundled-command-model-archive'),
                           ('on_installation_media', True), ('staged_by_upgrade', True)):
            with self.subTest(key=key):
                pin = json.loads(json.dumps(PIN))
                pin['delivery'][key] = value
                with self.assertRaisesRegex(ValueError, 'invalid command model pin'):
                    stager.check_pin(pin)
        pin = dict(PIN, schema='plebian-os.command-model-archive/v1')
        with self.assertRaisesRegex(ValueError, 'invalid command model pin'):
            stager.check_pin(pin)

    def test_the_stager_has_no_download_or_write_path(self):
        source = (ROOT / 'provision/stage-command-model.py').read_text()
        for word in ('urlopen', 'urllib', 'write_bytes', 'os.link', 'mkdir', 'shutil', 'open('):
            self.assertNotIn(word, source.split('"""', 2)[2])


class CommandModelRecordTests(unittest.TestCase):
    """provision/command-model.json and releases/0.2.3-command-model.json describe v10."""

    def test_the_pin_is_delivery_v10_as_a_first_use_download(self):
        self.assertEqual(PIN['schema'], 'plebian-os.command-model-archive/v2')
        self.assertEqual(PIN['version'], 'lfm2-kilix-commands-20261115-v10')
        self.assertEqual(PIN['root'], PIN['version'])
        self.assertEqual(PIN['weight_version'], 'lfm2-kilix-v5e1-wse-20261106.9')
        self.assertEqual(PIN['bytes'], 1346876805)
        self.assertEqual(PIN['sha256'], 'b9bff58b8d296cf557b721407553d15451a9856ecb8fa1bc09c908c6b0760187')
        self.assertEqual(PIN['installed_bytes'], 1432537967)
        self.assertEqual(PIN['manifest_digest'], V10_MANIFEST)
        self.assertEqual(PIN['url'], 'https://github.com/itsmygithubacct/kilix-needle/releases/download/'
                         'lfm2-kilix-commands-20261115-v10/lfm2-kilix-commands-20261115-v10.tar.gz')
        self.assertEqual(PIN['documents']['notices/NOTICE.txt'], {
            'bytes': 2031, 'sha256': 'ad951c9680c6bcb084a38582514b75ae90e0b85fd022495b4a38d2a6c6810a0f'})
        self.assertEqual(PIN['delivery'], {
            'mode': 'first-use-download', 'on_installation_media': False,
            'staged_by_upgrade': False, 'absent_backend': 'grammar',
            'offered_by': ['the first interactive kilix ask that reaches the command route',
                           "the Kilix model wizard's Local Workflows / Kilix Ask page"]})
        self.assertEqual(PIN['local_migration']['from_version'], 'lfm2-kilix-commands-20261106-v9')
        self.assertEqual(PIN['local_migration']['from_manifest_digest'], V9_MANIFEST)
        self.assertIs(PIN['local_migration']['network'], False)
        stager.check_pin(PIN)

    def test_the_release_record_matches_the_pin(self):
        delivery = RELEASE['delivery']
        self.assertEqual(RELEASE['default_backend'], 'grammar')
        self.assertEqual(RELEASE['backend_when_installed'], 'lfm2')
        self.assertEqual(RELEASE['delivery_version'], PIN['version'])
        self.assertEqual(RELEASE['weight_version'], PIN['weight_version'])
        self.assertEqual(RELEASE['model_sha256'],
                         '3fa22c105b1f80823088de21a45fd2f3dc30a4cfdc63d21037c9344585fae4dd')
        self.assertEqual(delivery['mode'], 'first-use-download')
        self.assertEqual(delivery['archive_pin'], 'provision/command-model.json')
        self.assertEqual((delivery['bytes'], delivery['sha256']), (PIN['bytes'], PIN['sha256']))
        self.assertEqual(delivery['manifest_digest'], PIN['manifest_digest'])
        self.assertIs(delivery['on_installation_media'], False)
        self.assertIs(delivery['staged_by_upgrade'], False)
        self.assertIs(delivery['iso_required'], False)
        self.assertNotIn('upgrade_stages_in_admin_context', delivery)
        self.assertNotIn('documents_path', delivery)
        self.assertEqual(delivery['local_migration']['from_manifest_digest'],
                         PIN['local_migration']['from_manifest_digest'])
        self.assertIs(delivery['local_migration']['network'], False)
        self.assertIs(delivery['explicit_user_choices_preserved'], True)
        # The asset is not published yet; publication belongs to the release session.
        self.assertIs(delivery['release_uploaded'], False)

    def test_the_rollback_names_delivery_v9_and_its_retained_directory(self):
        rollback = RELEASE['rollback']
        self.assertEqual(rollback['delivery_version'], 'lfm2-kilix-commands-20261106-v9')
        self.assertEqual(rollback['weight_version'], 'lfm2-kilix-v5e1-wse-20261106.9')
        self.assertEqual(rollback['manifest_digest'], V9_MANIFEST)
        self.assertIn('retained', rollback['mechanism'])

    def test_quality_and_source_pins_still_owed_are_marked_pending(self):
        self.assertIs(RELEASE['quality']['cpu']['pending'], False)
        self.assertEqual(RELEASE['quality']['cpu']['development']['admitted_outcome_correct'], 1345)
        self.assertTrue(RELEASE['quality']['release_seats']['pending'])
        for name, value in RELEASE['source_pins'].items():
            with self.subTest(pin=name):
                self.assertTrue(value == 'PENDING' or len(value) == 40, value)

    def test_nothing_in_the_tree_still_stages_or_copies_the_archive(self):
        provision = (ROOT / 'provision/plebian-os-provision.sh').read_text()
        update = (ROOT / 'provision/plebian-os-update.sh').read_text()
        preseed = (ROOT / 'preseed/preseed.cfg').read_text()
        remaster = (ROOT / 'build/remaster-iso.sh').read_text()
        self.assertNotIn('stage-command-model.py', provision)
        self.assertNotIn('stage-command-model.py', update)
        self.assertNotIn('test_fail_after_boundary command-model', update)
        self.assertNotIn('model-archives', preseed)
        self.assertNotIn('model-archives', remaster)
        self.assertNotIn('PLEBIAN_OS_COMMAND_MODEL_ARCHIVE_SHA256', remaster)
        self.assertNotIn('bundled-command-model-archive', remaster)
        self.assertNotIn('stage-command-model.py', remaster)


if __name__ == '__main__':
    unittest.main()
