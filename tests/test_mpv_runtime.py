"""Terminal package selection, inert archives and outer rollback boundaries."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest import mock

import test_native_closure as closure
import test_provision_transaction as transaction

ROOT = Path(__file__).resolve().parents[1]
VALUES = {
    'PLEBIAN_OS_MPV_URL': 'https://github.com/itsmygithubacct/kilix-mpv/releases/download/v0.40.0-kilix.4-test.1/kilix-mpv_0.40.0%2Bkilix.4_amd64.deb',
    'PLEBIAN_OS_MPV_SHA256': 'a' * 64,
    'PLEBIAN_OS_MPV_BYTES': '900000',
    'PLEBIAN_OS_MPV_VERSION': '0.40.0+kilix.4',
    'PLEBIAN_OS_MPV_SOURCE_REF': 'b' * 40,
    'PLEBIAN_OS_MPV_LAUNCHER_REF': 'c' * 40,
}


class MpvClosureTests(unittest.TestCase):
    def boundary(self, values, valid=True):
        for source in closure.SHELLS:
            command = closure.shell_function(source, 'validate_mpv_release_closure')
            result = subprocess.run(['/bin/bash', '-euc', command + '\nvalidate_mpv_release_closure'],
                                    env={'PATH': '/usr/bin:/bin', **values}, capture_output=True)
            self.assertEqual(result.returncode == 0, valid, (source, result.stderr))
        with contextlib.redirect_stderr(io.StringIO()):
            if valid:
                closure.vm.validate_mpv_release_closure(values)
            else:
                with self.assertRaises(SystemExit):
                    closure.vm.validate_mpv_release_closure(values)

    def test_complete_selection_and_legacy_empty(self):
        self.boundary(VALUES)
        self.boundary({})

    def test_partial_selection_refused_at_every_boundary(self):
        for key in VALUES:
            self.boundary({k: v for k, v in VALUES.items() if k != key}, False)

    def test_malformed_selection_refused(self):
        for key, value in (
            ('URL', 'http://github.com/a.deb'), ('URL', VALUES['PLEBIAN_OS_MPV_URL'] + '\n'),
            ('URL', 'https://other.invalid/player.deb'), ('SHA256', 'A' * 64),
            ('BYTES', '0'), ('BYTES', '0900000'), ('BYTES', '8388609'),
            ('VERSION', '--help'), ('SOURCE_REF', 'main'), ('LAUNCHER_REF', 'C' * 40),
        ):
            self.boundary({**VALUES, 'PLEBIAN_OS_MPV_' + key: value}, False)

    def test_apply_records_recovery_before_package_mutation(self):
        for source in ('provision/plebian-os-provision.sh', 'provision/plebian-os-update.sh'):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as outer:
                command = '\n'.join(closure.shell_function(source, name) for name in
                    ('validate_mpv_release_closure', 'apply_selected_mpv_runtime',
                     'rollback_mpv_runtime_transaction'))
                command += r'''
MPV_TRANSACTION_STARTED=0
PROVISION_ROOT_TRANSACTION_DIR="$OUTER"
_STACK_ROOT_TXN_DIR="$OUTER"
mpv_download_archive() { printf data >"$1"; }
mpv_runtime_snapshot_probe() { return 10; }
mpv_runtime_command() {
    case "$1" in
        --snapshot) mkdir "$2"; printf snapshot >"$2/SNAPSHOT.json" ;;
        --install-package)
            [ "$MPV_TRANSACTION_STARTED" = 1 ] && [ "$(cat "$OUTER/mpv-runtime-transaction")" = 1 ] || exit 99
            return 71 ;;
        --restore) printf restored ;;
        *) exit 98 ;;
    esac
}
if apply_selected_mpv_runtime "$OUTER" 0; then exit 97; fi
[ "$MPV_TRANSACTION_STARTED" = 1 ]
rollback_mpv_runtime_transaction
[ "$MPV_TRANSACTION_STARTED" = 0 ]
'''
                result = subprocess.run(['/bin/bash', '-euc', command],
                    env={'PATH': '/usr/bin:/bin', 'OUTER': outer, **VALUES}, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, 'restored')

    def test_outer_failure_restores_player_before_helper_files(self):
        fixture = transaction.ProvisionRootTransactionTests()
        for fail in (False, True):
            with tempfile.TemporaryDirectory() as directory:
                setup, paths = fixture._layout(Path(directory))
                q = fixture._quoted
                code = setup + 'begin_provision_root_transaction\n'
                code += 'mkdir -m 700 "$PROVISION_ROOT_TRANSACTION_DIR/mpv-runtime"\n'
                code += 'printf snapshot >"$PROVISION_ROOT_TRANSACTION_DIR/mpv-runtime/SNAPSHOT.json"\n'
                code += 'MPV_TRANSACTION_STARTED=1\n'
                code += f'printf changed >{q(paths["existing"])}\n'
                code += 'mpv_runtime_command() {\n[ "$1" = --restore ]\n'
                code += f'[ "$(cat {q(paths["existing"])})" = changed ]\n'
                code += 'return ' + ('71' if fail else '0') + '\n}\nexit 55\n'
                result = fixture._run(code)
                self.assertEqual(result.returncode, 70 if fail else 55, result.stderr)
                self.assertEqual(paths['existing'].read_text(), 'changed' if fail else 'before\n')


class MpvArchiveTests(unittest.TestCase):
    def setUp(self):
        self.module = types.ModuleType('mpv_runtime_test')
        path = ROOT / 'provision/plebian-os-mpv-runtime'
        exec(compile(path.read_bytes(), str(path), 'exec'), self.module.__dict__)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tree = self.root / 'package'
        control = self.tree / 'DEBIAN'
        control.mkdir(parents=True, mode=0o755)
        (control / 'control').write_text('Package: kilix-mpv\nVersion: 0.40.0+kilix.4\nArchitecture: amd64\nMaintainer: Test <test@example.invalid>\nDescription: inert test fixture\n')
        for name in self.module.FILES:
            target = self.tree / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps({'commit': 'c' * 40}) if name.endswith('/LAUNCHER.json') else 'fixture\n')

    def build(self):
        archive = self.root / 'package.deb'
        subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(self.tree), str(archive)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return archive

    def test_exact_inert_payload_accepted(self):
        record = self.module.archive_info(self.build())
        self.assertEqual(record['version'], '0.40.0+kilix.4')
        self.assertEqual(record['launcher'], 'c' * 40)

    def test_maintainer_script_refused(self):
        (self.tree / 'DEBIAN/postinst').write_text('#!/bin/sh\nexit 0\n')
        (self.tree / 'DEBIAN/postinst').chmod(0o755)
        with self.assertRaisesRegex(ValueError, 'maintainer'):
            self.module.archive_info(self.build())

    def test_payload_link_refused(self):
        target = self.tree / 'usr/bin/kilix-mpv'
        target.unlink()
        target.symlink_to('/usr/bin/mpv')
        with self.assertRaisesRegex(ValueError, 'unsafe'):
            self.module.archive_info(self.build())

    def test_system_player_replacement_refused(self):
        (self.tree / 'usr/bin/mpv').write_text('unexpected\n')
        with self.assertRaisesRegex(ValueError, 'unexpected'):
            self.module.archive_info(self.build())


class Arm64MpvPackageTests(MpvArchiveTests):
    def setUp(self):
        super().setUp()
        patch = mock.patch.object(self.module, 'native_architecture', return_value='arm64')
        patch.start()
        self.addCleanup(patch.stop)
        control = self.tree / 'DEBIAN/control'
        control.write_text(control.read_text().replace('Architecture: amd64', 'Architecture: arm64'))

    def test_arm64_snapshot_and_restore_use_native_cache(self):
        self.module.STATE = self.root / 'state'
        cache = self.module.STATE / 'packages'
        cache.mkdir(parents=True)
        import shutil
        archive = cache / 'kilix-mpv_0.40.0+kilix.4_arm64.deb'
        shutil.copyfile(self.build(), archive)
        snapshot = self.root / 'snapshot'
        real_run = subprocess.run
        calls = []

        def run(argv, **kwargs):
            if argv[0] == '/usr/bin/apt-get':
                calls.append(argv)
                return subprocess.CompletedProcess(argv, 0)
            return real_run(argv, **kwargs)

        with mock.patch.object(self.module, 'private_directory'), \
                mock.patch.object(self.module, 'installed_version', return_value='0.40.0+kilix.4'), \
                mock.patch.object(self.module, 'verify'), \
                mock.patch.object(self.module.subprocess, 'run', side_effect=run):
            self.module.snapshot(snapshot)
            self.module.restore(snapshot)
        self.assertEqual(len(calls), 1)
        self.assertIn('--allow-downgrades', calls[0])
        self.assertEqual((snapshot / 'previous.deb').read_bytes(), archive.read_bytes())

    def test_foreign_archive_refused(self):
        control = self.tree / 'DEBIAN/control'
        control.write_text(control.read_text().replace('Architecture: arm64', 'Architecture: amd64'))
        with self.assertRaisesRegex(ValueError, 'native-architecture'):
            self.module.archive_info(self.build())


if __name__ == '__main__':
    unittest.main()
