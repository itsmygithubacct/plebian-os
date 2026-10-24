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
                code += 'QT_RUNTIME_TRANSACTION_STARTED=1\n'
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
        for probe, expected in ((0, 1), (10, 0), (71, 1)):
            command = function + '\n_STACK_ROOT_TXN_DIR=/var/lib/plebian-os/private\n'
            command += 'QT_RUNTIME_TRANSACTION_STARTED=1\n'
            command += 'warn() { :; }\nqt_runtime_snapshot_probe() { return "$PROBE"; }\n'
            command += 'qt_runtime_command() { echo restored; }\nrollback_qt_runtime_transaction\n'
            result = subprocess.run(['/bin/bash', '-euc', command],
                env={'PATH': '/usr/bin:/bin', 'PROBE': str(probe)}, text=True, capture_output=True)
            self.assertEqual(result.returncode, expected, result.stderr)
            self.assertEqual('restored' in result.stdout, probe == 10)

    def test_unused_qt_transaction_never_elevates_during_rollback(self):
        function = closure.shell_function('provision/plebian-os-update.sh', 'rollback_qt_runtime_transaction')
        command = function + '\n_STACK_ROOT_TXN_DIR=/var/lib/plebian-os/private\n'
        command += 'QT_RUNTIME_TRANSACTION_STARTED=0\n'
        command += 'qt_runtime_snapshot_probe() { exit 99; }\nrollback_qt_runtime_transaction\n'
        result = subprocess.run(['/bin/bash', '-euc', command], capture_output=True)
        self.assertEqual(result.returncode, 0)

    def test_apply_records_interrupted_recovery_before_package_mutation(self):
        for source in ('provision/plebian-os-provision.sh', 'provision/plebian-os-update.sh'):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as outer:
                command = '\n'.join(closure.shell_function(source, name) for name in
                    ('validate_qt_release_closure', 'apply_selected_qt_runtime', 'rollback_qt_runtime_transaction'))
                command += r'''
QT_RUNTIME_TRANSACTION_STARTED=0
PROVISION_ROOT_TRANSACTION_DIR="$OUTER"
_STACK_ROOT_TXN_DIR="$OUTER"
qt_download_archive() { printf data >"$1"; }
qt_runtime_snapshot_probe() { return 10; }
qt_runtime_command() {
    case "$1" in
        --snapshot) mkdir "$2"; printf snapshot >"$2/SNAPSHOT.json" ;;
        --install-bundle)
            [ "$QT_RUNTIME_TRANSACTION_STARTED" = 1 ] && [ "$(cat "$OUTER/qt-runtime-transaction")" = 1 ] || exit 99
            return 71 ;;
        --restore) printf restored ;;
        *) exit 98 ;;
    esac
}
if apply_selected_qt_runtime "$OUTER" 0; then exit 97; fi
[ "$QT_RUNTIME_TRANSACTION_STARTED" = 1 ]
rollback_qt_runtime_transaction
[ "$QT_RUNTIME_TRANSACTION_STARTED" = 0 ]
'''
                result = subprocess.run(['/bin/bash', '-euc', command],
                    env={'PATH': '/usr/bin:/bin', 'OUTER': outer, 'PLEBIAN_OS_RELEASE': '0.2.2',
                         'PLEBIAN_OS_RELEASE_MODE': '1', **VALUES}, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, 'restored')


class QtPackageTests(unittest.TestCase):
    architecture = "amd64"
    triplet = "x86_64-linux-gnu"

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
            if (str(path).startswith(f'/usr/lib/{self.triplet}/')
                    or str(path).startswith(f'/usr/include/{self.triplet}/')):
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
        self.package_statuses = {}
        self.archives = {}
        self.events = []
        self.fail_install = False
        self.partial_on_failure = False
        self.inject_dependency_on_install = False
        self.simulated_existing_change = ''
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
                f'Package: {name}\nVersion: {version}\nArchitecture: {self.architecture}\n'
                'Maintainer: fixture <fixture@localhost>\nDescription: private test\n')
            paths = [f'usr/lib/{self.triplet}/libQt{major}Gui.so.{qt}',
                     f'usr/lib/{self.triplet}/libQt{major}XcbQpa.so.{qt}',
                     f'usr/lib/{self.triplet}/qt{major}/plugins/platforms/libqxcb.so']
            files = []
            for relative in paths:
                target = source / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                data = (label + ':' + relative).encode()
                target.write_bytes(data)
                files.append({'path': '/' + relative, 'bytes': len(data),
                              'sha256': hashlib.sha256(data).hexdigest()})
            archive = lane / f'{name}_{version}_{self.architecture}.deb'
            self.real_run(['dpkg-deb', '--build', '--root-owner-group', str(source), str(archive)],
                          check=True, capture_output=True)
            self.archives[(name, version)] = archive
            result.append({'Package': name, 'Version': version, 'Architecture': self.architecture,
                           'qt': qt, 'path': archive.name, 'bytes': archive.stat().st_size,
                           'sha256': self.module.digest(archive), 'files': files})
        (lane / 'RUNTIME.json').write_text(json.dumps(result))
        return lane, result

    def output(self, argv, **kwargs):
        argv = [Path(argv[0]).name, *argv[1:]]
        if argv[:2] == ['dpkg', '--print-architecture']:
            return self.architecture + '\n'
        if argv[0] == 'dpkg-query':
            if argv[-1] == '-f=${Package}\t${Architecture}\t${db:Status-Status}\n':
                return ''.join(f'{name}\t{self.architecture}\t'
                               f'{self.package_statuses.get(name, "installed")}\n'
                               for name in sorted(set(self.versions) | set(self.package_statuses)))
            name = argv[-1]
            return self.package_statuses.get(name, 'installed') + '\n' + self.versions[name]
        return self.real_output(argv, **kwargs)

    def run_command(self, argv, **kwargs):
        argv = [Path(argv[0]).name, *argv[1:]]
        if argv[0] == 'dpkg-query':
            name = argv[-1]
            if name not in self.versions:
                return subprocess.CompletedProcess(argv, 1, '', '')
            status = self.package_statuses.get(name, 'installed')
            value = status if argv[3] == '-f=${db:Status-Status}' else status + '\n' + self.versions[name]
            return subprocess.CompletedProcess(argv, 0, value, '')
        if argv[0] == 'apt-get':
            self.events.append(argv)
            if '--simulate' in argv and 'install' in argv:
                planned = ''
                if self.inject_dependency_on_install:
                    planned = ('Inst libqt5gui5t64 (fixture [arm64])\n'
                               'Inst libqt6gui6 (fixture [arm64])\n'
                               'Inst qt6-base-dev (fixture [arm64])\n'
                               'Inst libxcb-res0 (fixture [arm64])\n')
                planned += self.simulated_existing_change
                return subprocess.CompletedProcess(argv, 0, planned, '')
            if 'purge' in argv:
                packages = argv[argv.index('purge') + 1:]
                if '--simulate' in argv:
                    return subprocess.CompletedProcess(argv, 0,
                        ''.join('Purg ' + name.split(':')[0] + ' (fixture)\n' for name in packages), '')
                for name in packages:
                    self.versions.pop(name.split(':')[0], None)
                    self.package_statuses.pop(name.split(':')[0], None)
                return subprocess.CompletedProcess(argv, 0)
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
                        if self.partial_on_failure:
                            self.package_statuses[meta['Package']] = 'unpacked'
                            self.versions['libxcb-res0'] = '1.17.0-2+b1'
                            self.package_statuses['libxcb-res0'] = 'half-configured'
                        raise subprocess.CalledProcessError(71, argv)
                if self.inject_dependency_on_install:
                    self.versions['libxcb-res0'] = '1.17.0-2+b1'
            return subprocess.CompletedProcess(argv, 0)
        if argv[:2] == ['dpkg', '--remove']:
            for name in argv[2:]:
                self.versions.pop(name, None)
            return subprocess.CompletedProcess(argv, 0)
        return self.real_run(argv, **kwargs)

    def install(self, lane, snapshot=None):
        command = ['--install', str(lane / 'RUNTIME.json'), '--package-root', str(lane)]
        if snapshot is not None:
            command += ['--snapshot-path', str(snapshot)]
        self.module.main(command)

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

    def test_checksum_bound_bundle_accepts_nested_package_paths(self):
        lane, records = self.package_set('selected', '+plebianrc6.1')
        for record in records:
            old = lane / record['path']
            prefix = 'qtbase-opensource-src' if record['qt'].startswith('5.') else 'qt6-base'
            record['path'] = prefix + '/' + old.name
            selected = lane / record['path']
            selected.parent.mkdir(exist_ok=True)
            old.rename(selected)
            self.archives[(record['Package'], record['Version'])] = selected
        (lane / 'RUNTIME.json').write_text(json.dumps(records))
        bundle = self.root / 'qt-nested.tar.xz'
        with tarfile.open(bundle, 'w:xz') as archive:
            for name in ('RUNTIME.json', *(r['path'] for r in records)):
                archive.add(lane / name, arcname=name)
        self.module.install_bundle(bundle, self.module.digest(bundle), bundle.stat().st_size)
        self.module.verify(records)

    def test_checksum_bound_bundle_rejects_an_unlisted_file_before_install(self):
        lane, records = self.package_set('selected', '+plebianrc6.1')
        (lane / 'unlisted').write_text('must not install')
        bundle = self.root / 'qt-extra.tar.xz'
        with tarfile.open(bundle, 'w:xz') as archive:
            for name in ('RUNTIME.json', *(r['path'] for r in records), 'unlisted'):
                archive.add(lane / name, arcname=name)
        with self.assertRaises(ValueError):
            self.module.install_bundle(bundle, self.module.digest(bundle), bundle.stat().st_size)
        self.assertEqual(self.events, [])


class Arm64QtPackageTests(QtPackageTests):
    architecture = "arm64"
    triplet = "aarch64-linux-gnu"

    def test_selected_residual_config_refused_before_snapshot_work(self):
        for name in (*self.module.PACKAGES, self.module.ARM_DEV_PACKAGE):
            with self.subTest(name=name):
                self.versions[name] = '6.8.2+dfsg-1'
                self.package_statuses[name] = 'config-files'
                target = self.outer / ('snapshot-' + name)
                with self.assertRaisesRegex(ValueError, 'incomplete Qt package'):
                    self.module.snapshot(target)
                self.assertFalse(target.exists())
                self.assertEqual(self.events, [])
                del self.versions[name]
                del self.package_statuses[name]

    def test_partial_new_packages_are_purged_after_failed_install(self):
        snapshot = self.outer / 'qt-runtime'
        self.module.snapshot(snapshot)
        selected, _ = self.package_set('selected', '+plebianrc6.1')
        self.inject_dependency_on_install = True
        self.partial_on_failure = True
        self.fail_install = True
        with self.assertRaises(subprocess.CalledProcessError):
            self.install(selected, snapshot=snapshot)
        self.assertEqual(self.package_statuses['libqt5gui5t64'], 'unpacked')
        self.assertEqual(self.package_statuses['libxcb-res0'], 'half-configured')
        self.module.restore(snapshot)
        self.assertEqual(self.versions, {})
        self.assertEqual(self.package_statuses, {})

    def test_existing_dependency_change_refused_before_apt_mutation(self):
        self.versions['libxcb-res0'] = '1.17.0-2'
        snapshot = self.outer / 'qt-runtime'
        self.module.snapshot(snapshot)
        selected, _ = self.package_set('selected', '+plebianrc6.1')
        self.inject_dependency_on_install = True
        for change in ('Inst libxcb-res0 [1.17.0-2] (1.17.0-2+b1 Debian:13 [arm64])\n',
                       'Inst libxcb-res0 (1.17.0-2+b1 Debian:13 [arm64])\n'):
            self.simulated_existing_change = change
            before = len([event for event in self.events if 'install' in event and '--simulate' not in event])
            with self.assertRaisesRegex(ValueError, 'preexisting non-Qt package'):
                self.install(selected, snapshot=snapshot)
            after = len([event for event in self.events if 'install' in event and '--simulate' not in event])
            self.assertEqual(before, after)
            self.assertEqual(self.versions['libxcb-res0'], '1.17.0-2')
            self.assertFalse(self.module.PREFERENCE.exists())


    def test_matching_dev_companion_and_new_dependency_restore(self):
        baseline, prior = self.package_set('baseline', '')
        for record in prior:
            self.real_run(['dpkg-deb', '-x', str(baseline / record['path']), str(self.root)], check=True)
            self.versions[record['Package']] = record['Version']
        self.versions['unrelated-residual-config'] = '1.0'
        self.package_statuses['unrelated-residual-config'] = 'config-files'
        self.module.snapshot(self.outer / 'qt-runtime')
        selected, records = self.package_set('selected', '+plebianrc6.1')
        name = self.module.ARM_DEV_PACKAGE
        version = '6.8.2+dfsg-1+plebianrc6.1'
        source = selected / name
        (source / 'DEBIAN').mkdir(parents=True)
        (source / 'DEBIAN/control').write_text(
            f'Package: {name}\nVersion: {version}\nArchitecture: arm64\n'
            f'Depends: libqt6gui6 (= {version})\n'
            'Maintainer: fixture <fixture@localhost>\nDescription: private test\n')
        files = []
        for absolute in sorted(self.module.runtime_files(name)):
            path = source / absolute.lstrip('/')
            path.parent.mkdir(parents=True, exist_ok=True)
            data = absolute.encode()
            path.write_bytes(data)
            files.append({'path': absolute, 'bytes': len(data),
                          'sha256': hashlib.sha256(data).hexdigest()})
        archive = selected / f'{name}_{version}_arm64.deb'
        self.real_run(['dpkg-deb', '--build', '--root-owner-group', str(source), str(archive)],
                      check=True, capture_output=True)
        records.append({'Package': name, 'Version': version, 'Architecture': 'arm64',
                        'qt': '6.8.2', 'path': archive.name, 'bytes': archive.stat().st_size,
                        'sha256': self.module.digest(archive), 'files': files})
        (selected / 'RUNTIME.json').write_text(json.dumps(records))
        self.inject_dependency_on_install = True
        self.install(selected, snapshot=self.outer / 'qt-runtime')
        self.assertIn(name, self.versions)
        self.assertIn('libxcb-res0', self.versions)
        self.versions['unrelated-later-package'] = '1.0'
        self.inject_dependency_on_install = False
        self.module.restore(self.outer / 'qt-runtime')
        self.assertEqual(self.versions,
                         {**{r['Package']: r['Version'] for r in prior},
                          'unrelated-residual-config': '1.0',
                          'unrelated-later-package': '1.0'})
        self.assertEqual(self.package_statuses['unrelated-residual-config'], 'config-files')
        self.assertFalse(self.module.HOOK.exists())
        self.assertFalse(self.module.PREFERENCE.exists())

    def test_foreign_manifest_refused_before_package_mutation(self):
        lane, records = self.package_set('foreign', '+plebianrc6.1')
        for record in records:
            record['Architecture'] = 'amd64'
        (lane / 'RUNTIME.json').write_text(json.dumps(records))
        with self.assertRaisesRegex(ValueError, 'architecture'):
            self.install(lane)
        self.assertEqual(self.events, [])
        self.assertFalse(self.module.PREFERENCE.exists())


if __name__ == '__main__':
    unittest.main()
