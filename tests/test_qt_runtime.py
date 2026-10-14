"""Qt closure and package rollback in a private tree; no host apt operation."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path, PosixPath
import shutil
import subprocess
import tarfile
import tempfile
import types
import unittest
from unittest import mock

import test_native_closure as closure
import test_provision_transaction as transaction

ROOT = Path(__file__).resolve().parents[1]
VALUES = closure.QT_SELECTION


class QtClosureTests(unittest.TestCase):
    def test_installed_entrypoint_parses_its_isolated_python_flags(self):
        result = subprocess.run([str(ROOT / 'provision/plebian-os-qt-runtime'), '--help'],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--install-bundle', result.stdout)

    def boundary(self, values, version='0.2.2', mode='1', valid=True):
        for source in closure.SHELLS:
            script = closure.shell_function(source, 'validate_qt_release_closure')
            result = subprocess.run(['/bin/bash', '-euc', script + '\nvalidate_qt_release_closure "$1" "$2"',
                                     'qt', version, mode],
                env={'PATH': '/usr/bin:/bin', **values}, capture_output=True, timeout=5)
            self.assertEqual(result.returncode == 0, valid, (source, result.stderr))
        with contextlib.redirect_stderr(io.StringIO()):
            if valid:
                closure.vm.validate_qt_release_closure(values, version, mode)
            else:
                with self.assertRaises(SystemExit):
                    closure.vm.validate_qt_release_closure(values, version, mode)

    def test_complete_closure_and_older_empty_selection(self):
        self.boundary(VALUES)
        self.boundary({}, '0.2.1')
        self.boundary({}, '0.2.2', '0')
        self.boundary({}, valid=False)
        self.boundary({**VALUES, 'PLEBIAN_OS_QT_RUNTIME_BYTES': '134217728'})

    def test_partial_and_malformed_closures_refuse(self):
        for key in VALUES:
            self.boundary({k: v for k, v in VALUES.items() if k != key}, valid=False)
        invalid = {
            'PLEBIAN_OS_QT_RUNTIME_URL': ('http://example.invalid/a', 'https://u:p@example.invalid/a',
                'https://example.invalid:65536/a', 'https://example.invalid:0443/a',
                'https://example.invalid/a\nb'),
            'PLEBIAN_OS_QT_RUNTIME_SHA256': ('A' * 64, 'd' * 63, 'd' * 64 + '\n'),
            'PLEBIAN_OS_QT_RUNTIME_BYTES': ('0', '01', '134217729', '9' * 100),
        }
        for key, values in invalid.items():
            for value in values:
                self.boundary({**VALUES, key: value}, valid=False)

    def test_outer_provision_failure_restores_packages_before_helper_files(self):
        fixture = transaction.ProvisionRootTransactionTests()
        for fail in (False, True):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as directory:
                setup, paths = fixture._layout(Path(directory))
                q = fixture._quoted
                code = setup + 'begin_provision_root_transaction\n'
                code += 'mkdir -m 700 "$PROVISION_ROOT_TRANSACTION_DIR/qt-runtime"\n'
                code += 'printf snapshot >"$PROVISION_ROOT_TRANSACTION_DIR/qt-runtime/SNAPSHOT.json"\n'
                code += f'printf changed >{q(paths["existing"])}\n'
                code += 'qt_runtime_command() {\n'
                code += '[ "$1" = --restore ]\n'
                code += f'[ "$(cat {q(paths["existing"])})" = changed ]\n'
                code += 'return ' + ('71' if fail else '0') + '\n}\nexit 55\n'
                result = fixture._run(code)
                self.assertEqual(result.returncode, 70 if fail else 55, result.stderr)
                self.assertEqual(paths['existing'].read_text(), 'changed' if fail else 'before\n')

    def test_update_retains_recovery_when_snapshot_inspection_fails(self):
        function = closure.shell_function('provision/plebian-os-update.sh', 'rollback_qt_runtime_transaction')
        for probe, expected in ((0, 0), (10, 0), (71, 1)):
            command = function + '\n_STACK_ROOT_TXN_DIR=/var/lib/plebian-os/private\n'
            command += 'warn() { :; }\nqt_runtime_snapshot_probe() { return "$PROBE"; }\n'
            command += 'qt_runtime_command() { echo restored; }\nrollback_qt_runtime_transaction\n'
            result = subprocess.run(['/bin/bash', '-euc', command],
                env={'PATH': '/usr/bin:/bin', 'PROBE': str(probe)}, text=True, capture_output=True)
            self.assertEqual(result.returncode, expected, result.stderr)
            self.assertEqual('restored' in result.stdout, probe == 10)


class QtPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='qt-runtime-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        fixture_root = self.root

        class FixturePath(PosixPath):
            def stat(self, **kwargs):
                fields = list(super().stat(**kwargs))
                fields[4] = 0  # Only the fixture's UID is substituted.
                return os.stat_result(fields)

        self.module = types.ModuleType('qt_runtime_fixture')
        source = ROOT / 'provision/plebian-os-qt-runtime'
        exec(compile(source.read_bytes(), str(source), 'exec'), self.module.__dict__)
        def fixture_path(*parts):
            path = Path(*parts)
            if str(path).startswith('/usr/lib/x86_64-linux-gnu/'):
                path = fixture_root / str(path).lstrip('/')
            return FixturePath(path)
        self.module.Path = fixture_path
        self.module.STATE = FixturePath(self.root / 'var/lib/plebian-os/qt-runtime')
        self.module.STATE.parent.mkdir(parents=True)
        self.module.PREFERENCE = FixturePath(self.root / 'etc/apt/preferences.d/qt')
        self.module.HOOK = FixturePath(self.root / 'etc/apt/apt.conf.d/qt')
        for path in (self.module.PREFERENCE, self.module.HOOK):
            path.parent.mkdir(parents=True)
        self.outer = FixturePath(self.root / 'outer')
        self.outer.mkdir(mode=0o700)
        self.versions = {}
        self.archives = {}
        self.events = []
        self.fail_install = False
        self.real_run = subprocess.run
        self.real_output = subprocess.check_output
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(self.module.os, 'geteuid', return_value=0).start()
        mock.patch.object(self.module.subprocess, 'run', side_effect=self.run_command).start()
        mock.patch.object(self.module.subprocess, 'check_output', side_effect=self.output).start()
        # State directory validation uses lstat, whose ownership check stays real.
        self.addCleanup(mock.patch.stopall)
        original_lstat = FixturePath.lstat

        def lstat(path):
            fields = list(original_lstat(path))
            fields[4] = 0
            return os.stat_result(fields)
        mock.patch.object(FixturePath, 'lstat', lstat).start()

    def package_set(self, label, suffix):
        result = []
        lane = self.root / label
        lane.mkdir()
        for name, qt in self.module.PACKAGES.items():
            major = qt.split('.')[0]
            version = qt + '+dfsg-1' + suffix
            source = lane / name
            (source / 'DEBIAN').mkdir(parents=True)
            (source / 'DEBIAN/control').write_text(
                f'Package: {name}\nVersion: {version}\nArchitecture: amd64\n'
                'Maintainer: fixture <fixture@localhost>\nDescription: private test\n')
            paths = [f'usr/lib/x86_64-linux-gnu/libQt{major}Gui.so.{qt}',
                     f'usr/lib/x86_64-linux-gnu/libQt{major}XcbQpa.so.{qt}',
                     f'usr/lib/x86_64-linux-gnu/qt{major}/plugins/platforms/libqxcb.so']
            files = []
            for relative in paths:
                target = source / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                data = (label + ':' + relative).encode()
                target.write_bytes(data)
                files.append({'path': '/' + relative, 'bytes': len(data),
                              'sha256': hashlib.sha256(data).hexdigest()})
            archive = lane / f'{name}_{version}_amd64.deb'
            self.real_run(['dpkg-deb', '--build', '--root-owner-group', str(source), str(archive)],
                          check=True, capture_output=True)
            self.archives[(name, version)] = archive
            result.append({'Package': name, 'Version': version, 'Architecture': 'amd64',
                           'qt': qt, 'path': archive.name, 'bytes': archive.stat().st_size,
                           'sha256': self.module.digest(archive), 'files': files})
        (lane / 'RUNTIME.json').write_text(json.dumps(result))
        return lane, result

    def output(self, argv, **kwargs):
        argv = [Path(argv[0]).name, *argv[1:]]
        if argv[:2] == ['dpkg', '--print-architecture']:
            return 'amd64\n'
        if argv[0] == 'dpkg-query':
            return 'installed\n' + self.versions[argv[-1]]
        return self.real_output(argv, **kwargs)

    def run_command(self, argv, **kwargs):
        argv = [Path(argv[0]).name, *argv[1:]]
        if argv[0] == 'dpkg-query':
            name = argv[-1]
            if name not in self.versions:
                return subprocess.CompletedProcess(argv, 1, '', '')
            value = 'installed' if argv[3] == '-f=${db:Status-Status}' else 'installed\n' + self.versions[name]
            return subprocess.CompletedProcess(argv, 0, value, '')
        if argv[0] == 'apt-get':
            self.events.append(argv)
            if 'download' in argv:
                name, version = argv[-1].split('=', 1)
                shutil.copy2(self.archives[(name, version)], kwargs['cwd'])
            else:
                self.assertFalse(self.module.HOOK.exists(), 'the old hook must be suspended during package replacement')
                for archive in argv[argv.index('install') + 1:]:
                    fields = self.real_output(['dpkg-deb', '-f', archive, 'Package', 'Version'], text=True)
                    meta = dict(line.split(': ', 1) for line in fields.splitlines())
                    self.real_run(['dpkg-deb', '-x', archive, str(self.root)], check=True)
                    self.versions[meta['Package']] = meta['Version']
                    if self.fail_install:
                        self.fail_install = False
                        raise subprocess.CalledProcessError(71, argv)
            return subprocess.CompletedProcess(argv, 0)
        if argv[:2] == ['dpkg', '--remove']:
            for name in argv[2:]:
                self.versions.pop(name, None)
            return subprocess.CompletedProcess(argv, 0)
        return self.real_run(argv, **kwargs)

    def install(self, lane):
        self.module.main(['--install', str(lane / 'RUNTIME.json'), '--package-root', str(lane)])

    def test_selected_packages_verify_bytes_and_only_two_exact_pins(self):
        lane, records = self.package_set('selected', '+plebianrc6.1')
        self.install(lane)
        self.module.main(['--verify'])
        self.assertEqual(self.module.PREFERENCE.read_text().count('Package:'), 2)
        self.assertIn('--verify', self.module.HOOK.read_text())
        changed = self.module.Path(records[0]['files'][0]['path'])
        changed.write_bytes(b'replaced')
        with self.assertRaises(ValueError):
            self.module.main(['--verify'])

    def test_baseline_snapshot_restores_actual_packages_after_later_failure(self):
        baseline, prior = self.package_set('baseline', '')
        for record in prior:
            self.real_run(['dpkg-deb', '-x', str(baseline / record['path']), str(self.root)], check=True)
            self.versions[record['Package']] = record['Version']
        self.module.snapshot(self.outer / 'qt-runtime')
        lane, _ = self.package_set('selected', '+plebianrc6.1')
        self.install(lane)
        self.module.restore(self.outer / 'qt-runtime')
        self.assertEqual(self.versions, {r['Package']: r['Version'] for r in prior})
        self.assertFalse(self.module.HOOK.exists())
        self.assertFalse(self.module.PREFERENCE.exists())
        for record in prior:
            for item in record['files']:
                self.assertEqual(self.module.digest(self.module.Path(item['path'])), item['sha256'])

    def test_selected_upgrade_and_failed_partial_install_restore_cached_version(self):
        old, old_records = self.package_set('old', '+plebianrc6.1')
        new, new_records = self.package_set('new', '+plebianrc6.2')
        self.install(old)
        self.module.snapshot(self.outer / 'qt-runtime')
        self.install(new)
        self.module.restore(self.outer / 'qt-runtime')
        self.module.verify(old_records)
        self.fail_install = True
        with self.assertRaises(subprocess.CalledProcessError):
            self.install(new)
        self.module.verify(old_records)
        self.install(new)
        self.module.verify(new_records)

    def test_replaced_artifact_at_same_version_refuses_before_apt(self):
        old, records = self.package_set('old', '+plebianrc6.1')
        altered, _ = self.package_set('altered', '+plebianrc6.1')
        self.install(old)
        calls = len(self.events)
        with self.assertRaises(ValueError):
            self.install(altered)
        self.assertEqual(len(self.events), calls)
        self.module.verify(records)

    def test_checksum_bound_bundle_installs_and_rejects_links(self):
        lane, records = self.package_set('selected', '+plebianrc6.1')
        bundle = self.root / 'qt.tar.xz'
        with tarfile.open(bundle, 'w:xz') as archive:
            for name in ('RUNTIME.json', *(r['path'] for r in records)):
                archive.add(lane / name, arcname=name)
        self.module.install_bundle(bundle, self.module.digest(bundle), bundle.stat().st_size)
        self.module.verify(records)
        link = self.root / 'linked'
        link.symlink_to(bundle)
        with self.assertRaises(OSError):
            self.module.install_bundle(link, self.module.digest(bundle), bundle.stat().st_size)
        with self.assertRaises(ValueError):
            self.module.install_bundle(bundle, '0' * 64, bundle.stat().st_size)


if __name__ == '__main__':
    unittest.main()
