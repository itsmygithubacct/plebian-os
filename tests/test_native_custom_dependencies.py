"""Synthetic download/dpkg controls; actual archive installation is separate."""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_native_transaction import runtime


def records():
    result = {}
    for name in ('libonnxruntime1.21', 'libonnxruntime-dev'):
        data = (name + ' synthetic archive\n').encode()
        version = '1.21.0+dfsg-1+kilix1'
        filename = name + '_' + version + '_amd64.deb'
        result[name] = {'version': version, 'filename': filename, 'archive': 'kilix',
            'provision': 'ort', 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
            'url': 'https://github.com/itsmygithubacct/kilix-encodec/releases/download/ort-deb-rc5/' + filename}
    return result


class ArchiveAuthorityTests(unittest.TestCase):
    def test_legacy_lock_has_no_custom_downloads(self):
        self.assertEqual(runtime.artifact.validate_custom_dependencies({'libc6': {'archive': 'debian'}}), {})

    def test_valid_paired_selection(self):
        self.assertEqual(runtime.artifact.validate_custom_dependencies(records()), records())

    def test_reject_incomplete_or_unexpected_population(self):
        for packages in ({'libonnxruntime1.21': records()['libonnxruntime1.21']},
                         {**records(), 'unrelated': {'archive': 'kilix'}}):
            with self.subTest(packages=list(packages)), self.assertRaises(ValueError):
                runtime.artifact.validate_custom_dependencies(packages)

    def test_reject_unbound_archive_fields(self):
        for field, value in (('url', 'http://example.invalid/package.deb'),
                             ('url', 'https://example.invalid/package.deb'),
                             ('filename', '../runtime.deb'), ('sha256', 'not-a-digest'),
                             ('bytes', True), ('bytes', runtime.artifact.MAX_ARCHIVE + 1),
                             ('provision', 'system'), ('version', '1.21.0+dfsg-1')):
            row = records()
            row['libonnxruntime1.21'][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                runtime.artifact.validate_custom_dependencies(row)

    def test_complete_offer_is_checked_before_extracting_dependencies(self):
        with self.assertRaises(ValueError):
            runtime.artifact.custom_dependency_records(b'invalid archive', sha256='0' * 64,
                byte_count=15, source_commit='a' * 40, content_commit='b' * 40)


class SyntheticBackend:
    def __init__(self):
        self.guard = lambda: None
        self.events = []
        self.packages = {}
        self.bad_hash = self.bad_identity = None

    def verify(self, current):
        self.events.append(('verify', current))

    def status(self, name):
        return self.packages.get(name)

    def version_at_least(self, candidate, old):
        return candidate == old

    def audit(self):
        self.events.append(('audit',))

    def run(self, argv):
        self.guard()
        if argv[0] == '/usr/bin/curl':
            path = Path(argv[argv.index('--output') + 1])
            name = path.name.split('_')[0]
            data = (name + ' synthetic archive\n').encode()
            path.write_bytes(b'changed archive' if self.bad_hash == name else data)
            self.events.append(('download', name))
            return 0, b'', b''
        assert argv[0] == '/usr/bin/dpkg-deb', argv
        name = Path(argv[-1]).name.split('_')[0]
        identity = 'wrong-package' if self.bad_identity == name else name
        return 0, f'{identity}\n{records()[name]["version"]}\namd64\n'.encode(), b''

    def install_dependencies(self, paths):
        self.guard()
        self.events.append(('install', tuple(path.name for path in paths)))
        for name, row in records().items():
            self.packages[name + ':amd64'] = {
                'status': 'install ok installed', 'version': row['version'], 'architecture': 'amd64'}


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tree = runtime.state.Tree(Path(self.tmp.name), uid=os.getuid())
        self.addCleanup(self.tree.close)
        self.tree.private_directory('var/lib/dpkg')
        self.backend = SyntheticBackend()
        self.manager = runtime.Manager(self.tree, self.backend)
        self.current = None
        self.addCleanup(patch.stopall)
        patch.object(runtime.artifact, 'custom_dependency_records', return_value=records()).start()
        patch.object(self.manager, 'metadata', side_effect=lambda value: self.current).start()

    def install(self):
        self.manager.install_dependencies(b'synthetic selection')

    def test_both_archives_validated_before_one_mutation(self):
        self.install()
        events = [event[0] for event in self.backend.events]
        self.assertEqual(events.count('install'), 1)
        self.assertLess(max(i for i, event in enumerate(events) if event == 'download'), events.index('install'))
        self.assertEqual(list((self.tree.root / runtime.BASE / 'cache').iterdir()), [])

    def test_same_version_is_reinstalled_and_repeat_is_verified(self):
        self.install()
        self.backend.events.clear()
        self.install()
        self.assertEqual(sum(event[0] == 'install' for event in self.backend.events), 1)
        self.assertEqual(sum(event[0] == 'verify' for event in self.backend.events), 2)

    def test_legacy_current_refuses_before_download_or_mutation(self):
        self.current = {'runtime_files': {}}
        with self.assertRaisesRegex(ValueError, 'legacy byte-pinned'):
            self.install()
        self.assertEqual(self.backend.events, [])

    def test_unknown_active_transaction_refuses_before_download(self):
        with self.manager.locked():
            self.manager.write_json(runtime.ACTIVE, {'transaction': 'a' * 32})
        with self.assertRaisesRegex(ValueError, 'active native transaction'):
            self.install()
        self.assertEqual(self.backend.events, [])

    def test_changed_archive_or_identity_never_mutates(self):
        for failure in ('bad_hash', 'bad_identity'):
            for name in records():
                self.backend.events.clear()
                setattr(self.backend, failure, name)
                with self.subTest(failure=failure, name=name), self.assertRaises(ValueError):
                    self.install()
                self.assertFalse(any(event[0] == 'install' for event in self.backend.events))
                setattr(self.backend, failure, None)

    def test_unhealthy_or_newer_package_refuses_before_download(self):
        for status, version in (('install ok installed', 'newer'), ('install ok unpacked', records()['libonnxruntime1.21']['version'])):
            self.backend.packages['libonnxruntime1.21:amd64'] = {
                'status': status, 'version': version, 'architecture': 'amd64'}
            with self.subTest(status=status, version=version), self.assertRaises(ValueError):
                self.install()
        self.assertFalse(any(event[0] in ('download', 'install') for event in self.backend.events))


if __name__ == '__main__':
    unittest.main()
