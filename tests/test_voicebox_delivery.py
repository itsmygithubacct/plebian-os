"""Run the actual optional hooks in copied sandbox roots; never provision a host."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROVISION = (ROOT / 'provision/plebian-os-provision.sh').read_text()
UPDATE = (ROOT / 'provision/plebian-os-update.sh').read_text()


def function(source, name):
    start = source.index('\n' + name + '() {') + 1
    return source[start:source.index('\n}\n', start) + 3]


class VoiceboxDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.package = self.base / 'selected-offline.tar.gz'
        self.package.write_bytes(b'inert fixture, never installed by these hooks')
        self.digest = hashlib.sha256(self.package.read_bytes()).hexdigest()
        self.log = self.base / 'commands'
        self.host = self.base / 'host'
        self.host.mkdir(mode=0o700)
        script = self.host / 'kilix'
        script.write_text('#!/bin/sh\nprintf "%s\\n" "$@" >> "$LOG"\nexit "${FIXTURE_RC:-0}"\n')
        script.chmod(0o700)

    def run_hook(self, hook, package=True, digest=True, code=0, dry=0):
        env = {'PATH': os.environ['PATH'], 'HOME': str(self.base), 'LOG': str(self.log),
            'FIXTURE_RC': str(code), 'KILIX_VOICEBOX_PACKAGE': str(self.package) if package else '',
            'KILIX_VOICEBOX_PACKAGE_SHA256': self.digest if digest else ''}
        body = 'set -euo pipefail\n'
        body += function(PROVISION, 'install_optional_voicebox')
        body += '\ndie() { printf "%s\\n" "$*" >&2; exit 7; }\nlog() { :; }\nas_user() { "$@"; }\n'
        # This unit checks argument/refusal forwarding only. The complete real
        # root transaction, snapshot and lock are covered in the adjacent suite.
        body += 'begin_provision_voicebox_selection() { KILIX_VOICEBOX_TRANSACTION_FD=999; }\n'
        body += 'install_env=()\n'
        body += 'KILIX_DIR=' + repr(str(self.host)) + '\nKILIX_DATA_HOME=' + repr(str(self.base / 'data')) + '\n'
        body += 'DRY_RUN=' + str(dry) + '\ninstall_optional_voicebox\n'
        return subprocess.run(['/bin/bash', '-c', body], env=env, capture_output=True, text=True, timeout=15)

    def test_default_provision_does_not_install_optional_program_or_models(self):
        result = self.run_hook('provision', package=False, digest=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.log.exists())

    def test_explicit_offline_package_calls_the_host_once_with_exact_digest(self):
        result = self.run_hook('provision')
        self.assertEqual(result.returncode, 0, result.stderr)
        args = self.log.read_text().splitlines()
        self.assertEqual(args, ['voicebox', 'prepare', '--root', str(self.base / 'data/voicebox'),
                               '--package', str(self.package), '--sha256', self.digest])

    def test_partial_selection_missing_package_and_refusal_abort_provision(self):
        self.assertEqual(self.run_hook('provision', digest=False).returncode, 7)
        self.assertFalse(self.log.exists())
        self.package.unlink()
        self.assertEqual(self.run_hook('provision').returncode, 7)
        self.assertFalse(self.log.exists())
        self.package.write_bytes(b'restored synthetic fixture')
        self.assertEqual(self.run_hook('provision', code=2).returncode, 7)

    def test_dry_run_does_not_execute_host(self):
        self.assertEqual(self.run_hook('provision', dry=1).returncode, 0)
        self.assertFalse(self.log.exists())

    def test_outer_update_snapshots_and_restores_only_selection(self):
        self.assertIn('snapshot_stack_path "$KILIX_DATA_HOME/voicebox/selection.json" kilix-voicebox-selection', UPDATE)
        self.assertIn('restore_stack_path "$KILIX_DATA_HOME/voicebox/selection.json" kilix-voicebox-selection file', UPDATE)
        self.assertNotIn('snapshot_stack_path "$KILIX_DATA_HOME/voicebox"', UPDATE)
        self.assertLess(UPDATE.rindex('    install_optional_voicebox_update\n'), UPDATE.rindex('    write_final_provenance\n'))
        self.assertIn('KILIX_VOICEBOX_SELECTION_SHA256', PROVISION)
        self.assertIn('KILIX_VOICEBOX_SELECTION_SHA256', UPDATE)

    def test_snapshot_restore_reinstates_absence_and_preserves_data_sentinels(self):
        selection = self.base / 'delivery/selection.json'
        selection.parent.mkdir(mode=0o700)
        state = self.base / 'transaction'
        state.mkdir(mode=0o700)
        data = self.base / 'product-sample.wav'
        data.write_bytes(b'unaffected synthetic sample')
        # Actual updater primitives execute as the unprivileged fixture user.
        body = 'set -euo pipefail\n' + function(UPDATE, 'snapshot_stack_path') + function(UPDATE, 'restore_stack_path')
        body += '\ndie() { exit 7; }\n_STACK_TXN_DIR=' + repr(str(state)) + '\n'
        body += 'snapshot_stack_path ' + repr(str(selection)) + ' vb\n'
        body += 'printf new >' + repr(str(selection)) + '\n'
        body += 'restore_stack_path ' + repr(str(selection)) + ' vb file\n'
        result = subprocess.run(['/bin/bash', '-c', body], env={'PATH': os.environ['PATH'], 'HOME': str(self.base)},
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(selection.exists())
        self.assertEqual(data.read_bytes(), b'unaffected synthetic sample')


if __name__ == '__main__':
    unittest.main()
