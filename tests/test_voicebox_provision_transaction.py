"""Actual optional provision hook and EXIT cleanup, with private file paths."""
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import sys
import tarfile
import tempfile
import unittest

import test_provision_transaction as root_fixture

HOST = Path(os.environ.get('PLEBIAN_OS_KILIX_REPO',
                           Path(__file__).resolve().parents[2] / 'kilix')).resolve()
sys.path.insert(0, str(HOST / 'config'))
from kilix_sdk import voicebox


def package(root, version):
    files = {'launch.py': b'# inert fixture\n', 'lib/kilix_voicebox_backend/server.py': version.encode(),
             'python/bin/python3.12': b'not executed', 'ui/index.html': b'<p>fixture</p>'}
    rows = [{'path': name, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
             'mode': 0o700 if name.startswith('python/') else 0o600} for name, raw in files.items()]
    files['DELIVERY.json'] = json.dumps({'schema': voicebox.SCHEMA, 'files': rows,
                                       'sources': {'fixture': version}}).encode()
    target = root / (version + '.tar.gz')
    with tarfile.open(target, 'w:gz') as archive:
        for name, raw in files.items():
            item = tarfile.TarInfo(name)
            item.size, item.mode = len(raw), 0o700 if name.startswith('python/') else 0o600
            archive.addfile(item, io.BytesIO(raw))
    return target, hashlib.sha256(target.read_bytes()).hexdigest()


class VoiceboxProvisionTransactionTests(unittest.TestCase):
    def exercise(self, prior, ending):
        library = root_fixture.ProvisionRootTransactionTests()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            setup, paths = library._layout(root)
            managed = root / 'gpu/kilix/data/voicebox'
            data = root / 'product-data'
            data.mkdir(mode=0o700)
            sentinel = data / 'whistle-and-lease-history'
            sentinel.write_bytes(b'accepted history remains untouched')
            for version in (() if prior == 'absent' else ('old',) if prior == 'old' else ('old', 'middle')):
                archive, digest = package(root, version)
                voicebox.install(managed, archive, digest)
            old = (managed / 'selection.json').read_bytes() if prior != 'absent' else None
            archive, digest = package(root, 'new')
            q = shlex.quote
            refusal = ('if env -u KILIX_VOICEBOX_TRANSACTION_FD /usr/bin/python3 -I -B '
                       + q(str(HOST / 'config/kilix_sdk/voicebox.py')) + ' status --root '
                       + q(str(managed)) + '; then die "exclusive lock was lost"; fi\n')
            body = setup + ('as_user() { "$@"; }\n'
                + 'install_env=(' + q('GPU_TERMINAL_HOME=' + str(root / 'gpu')) + ' '
                + q('KILIX_DATA_HOME=' + str(root / 'gpu/kilix/data')) + ')\n'
                + 'KILIX_DIR=' + q(str(HOST)) + '\nKILIX_DATA_HOME=' + q(str(root / 'gpu/kilix/data')) + '\n'
                + 'KILIX_VOICEBOX_PACKAGE=' + q(str(archive)) + '\nKILIX_VOICEBOX_PACKAGE_SHA256=' + digest + '\n'
                + 'begin_provision_root_transaction\ninstall_optional_voicebox\n' + refusal
                + 'printf changed > ' + q(str(paths['existing'])) + '\n')
            if ending == 'provenance':
                body += 'write_source_tool_manifest() { ' + refusal + 'return 41; }\nwrite_source_tool_manifest\n'
            elif ending == 'commit':
                body += 'commit_native_runtime_transaction() { ' + refusal + 'return 42; }\ncommit_provision_root_transaction\n'
            else:
                body += 'commit_provision_root_transaction\n' + refusal
            result = library._run(body)
            self.assertEqual(result.returncode, {'provenance': 41, 'commit': 1, 'success': 0}[ending], result.stderr)
            if ending == 'success':
                self.assertEqual(voicebox.selection(managed)['current'], digest)
                self.assertEqual(paths['existing'].read_text(), 'changed')
            else:
                self.assertEqual((managed / 'selection.json').read_bytes() if (managed / 'selection.json').exists() else None, old)
                self.assertEqual(paths['existing'].read_text(), 'before\n')
            voicebox.verify_generation(managed, digest)
            with voicebox.locked(managed, exclusive=False):
                pass
            self.assertEqual(sentinel.read_bytes(), b'accepted history remains untouched')
            self.assertEqual(list(paths['state'].glob('provision-rollback.*')), [])

    def test_late_provenance_failure_restores_old_new_and_absent_selection(self):
        for prior in ('old', 'new', 'absent'):
            with self.subTest(prior=prior):
                self.exercise(prior, 'provenance')

    def test_final_commit_failure_restores_old_new_and_absent_selection(self):
        for prior in ('old', 'new', 'absent'):
            with self.subTest(prior=prior):
                self.exercise(prior, 'commit')

    def test_success_retains_promotion_and_holds_exclusive_lock_through_commit(self):
        for prior in ('old', 'new', 'absent'):
            with self.subTest(prior=prior):
                self.exercise(prior, 'success')
