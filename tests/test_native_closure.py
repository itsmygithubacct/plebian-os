"""Exact native selection across standalone OS metadata boundaries.

These are inert validation/configuration tests. Private selector fixtures use
untagged synthetic commits and perform no download, package or OS operation.
"""
import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build'))
import build_vm_image as vm
import test_closure_selection as closure_fixture
import test_provision_pin_integrity as pin_fixture

SHELLS = ('provision/plebian-os-provision.sh',
          'provision/plebian-os-select-closure.sh', 'build/remaster-iso.sh',
          'provision/plebian-os-update.sh')
VALUES = {
    'PLEBIAN_OS_NATIVE_DEB_URL': 'https://example.invalid/releases/native.deb',
    'PLEBIAN_OS_NATIVE_DEB_SHA256': 'a' * 64,
    'PLEBIAN_OS_NATIVE_DEB_BYTES': '405204',
    'PLEBIAN_OS_NATIVE_SOURCE_REF': 'b' * 40,
    'PLEBIAN_OS_NATIVE_CONTENT_REF': 'c' * 40,
}


def shell_function(source, name):
    text = (ROOT / source).read_text()
    start = text.index(name + '() {\n')
    return text[start:text.index('\n}\n', start) + 3]


class NativeClosureTests(unittest.TestCase):
    def boundary(self, values, version='0.2.2', mode='1', expected=0):
        env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', **values}
        for source in SHELLS:
            with self.subTest(source=source, values=values, version=version, mode=mode):
                command = shell_function(source, 'validate_native_release_closure')
                command += '\nvalidate_native_release_closure "$1" "$2"\n'
                result = subprocess.run(['/bin/bash', '-euc', command, 'boundary', version, mode],
                    env=env, text=True, capture_output=True, timeout=5)
                self.assertEqual(result.returncode, expected, result.stderr)
        with contextlib.redirect_stderr(io.StringIO()):
            if expected:
                with self.assertRaises(SystemExit):
                    vm.validate_native_release_closure(values, version, mode)
            else:
                vm.validate_native_release_closure(values, version, mode)

    def test_standalone_shell_contracts_remain_identical(self):
        bodies = [shell_function(source, 'validate_native_release_closure') for source in SHELLS]
        self.assertEqual(bodies, [bodies[0]] * len(SHELLS))
        self.assertEqual(tuple(VALUES), vm.NATIVE_RELEASE_KEYS)

    def test_complete_exact_selection_and_archive_bounds(self):
        for size in ('1', '405204', '8388608'):
            self.boundary({**VALUES, 'PLEBIAN_OS_NATIVE_DEB_BYTES': size})
        self.boundary(VALUES, '0.2.1')
        self.boundary(VALUES, '0.2.2', '0')

    def test_older_empty_closure_and_development_are_compatible(self):
        self.boundary({}, '0.2.1')
        self.boundary({}, '0.1.8')
        self.boundary({}, '0.2.2', '0')

    def test_strict_022_requires_every_field(self):
        self.boundary({}, expected=1)
        for key in VALUES:
            self.boundary({k: v for k, v in VALUES.items() if k != key}, expected=1)

    def test_partial_selection_refuses_even_outside_release_mode(self):
        for key, value in VALUES.items():
            self.boundary({key: value}, '0.2.1', expected=1)
            self.boundary({key: value}, '0.2.2', '0', expected=1)

    def test_malformed_and_unbounded_values_refuse(self):
        invalid = {
            'PLEBIAN_OS_NATIVE_DEB_URL': ('http://example.invalid/a', 'file:///tmp/a',
                'https://user:secret@example.invalid/a', 'https://example.invalid/a b',
                'https://example.invalid/a\nb', 'https://example.invalid/' + 'x' * 2048),
            'PLEBIAN_OS_NATIVE_DEB_BYTES': ('0', '-1', '+1', '01', '1.0', '1e6',
                '8388609', '9' * 100, '405204\n'),
            'PLEBIAN_OS_NATIVE_DEB_SHA256': ('A' * 64, 'a' * 63, 'a' * 65, 'a' * 64 + '\n'),
            'PLEBIAN_OS_NATIVE_SOURCE_REF': ('main', 'B' * 40, 'b' * 39, 'b' * 41),
            'PLEBIAN_OS_NATIVE_CONTENT_REF': ('v0.2.2', 'C' * 40, 'c' * 39, 'c' * 40 + '\n'),
        }
        for key, values in invalid.items():
            for value in values:
                self.boundary({**VALUES, key: value}, expected=1)

    def test_explicit_ports_accept_canonical_bounds_without_parsing_path_or_query(self):
        for port in ('1', '80', '443', '8443', '65535'):
            for suffix in ('/native.deb', '?artifact=native:abc'):
                self.boundary({**VALUES, 'PLEBIAN_OS_NATIVE_DEB_URL':
                    f'https://example.invalid:{port}{suffix}'})
        for url in ('https://example.invalid/path:abc/native.deb',
                    'https://example.invalid?artifact=native:65536',
                    'https://example.invalid/path?mirror=other:abc'):
            self.boundary({**VALUES, 'PLEBIAN_OS_NATIVE_DEB_URL': url})

    def test_explicit_ports_reject_malformed_out_of_range_and_noncanonical_values(self):
        for port in ('', 'abc', '65536', '99999', '9' * 200, '0', '+443',
                     '-1', '0443', '000443', '443:80', '%34%34%33'):
            self.boundary({**VALUES, 'PLEBIAN_OS_NATIVE_DEB_URL':
                f'https://example.invalid:{port}/native.deb'}, expected=1)

    def test_real_selector_rejects_bad_ports_before_configuration_or_recovery_mutation(self):
        fixture = closure_fixture.ClosureSelectionTests()
        for port in ('abc', '65536'):
            with self.subTest(port=port), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                env = fixture._machine(base)
                before = env.read_bytes()
                values = {**VALUES, 'PLEBIAN_OS_NATIVE_DEB_URL':
                    f'https://example.invalid:{port}/native.deb'}
                manifest = fixture._f120_manifest_text(PLEBIAN_OS_VERSION='0.2.2',
                    PLEBIAN_OS_REF='v0.2.2', **values)
                commit = fixture._source(base, manifest, version='0.2.2',
                    release='0.2.2', tag=None)
                result = fixture._run(base, '0.2.2', '--offline',
                    '--development-commit', commit)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('native HTTPS port', result.stderr)
                self.assertEqual(env.read_bytes(), before)
                self.assertEqual(fixture._recovery_records(base), [])

    def test_all_five_values_have_configuration_and_provenance_transport(self):
        provision = (ROOT / SHELLS[0]).read_text()
        update = (ROOT / 'provision/plebian-os-update.sh').read_text()
        remaster = (ROOT / SHELLS[2]).read_text()
        controlled = pin_fixture.selector_release_keys()
        for key in VALUES:
            self.assertIn(key, controlled)
            self.assertIn(f'write_session_default {key} "${key}"', provision)
            self.assertIn(f'provenance_kv {key} "${key}"', provision)
            self.assertIn(f'provenance_kv {key} "${key}"', update)
            self.assertIn(f'"{key}=${key}"', update)
            self.assertIn(f'manifest_kv {key} "${{{key}:-}}"', remaster)
            self.assertIn(f'env_kv {key} "${{{key}:-}}"', remaster)

    def test_reprovision_restores_all_five_and_explicit_value_wins(self):
        fixture = pin_fixture.ReprovisionPinIntegrityTests()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'session.env'
            path.write_text(pin_fixture.session_env_text(VALUES))
            path.chmod(0o644)
            body = 'restore_installed_closure\n' + fixture._report(VALUES)
            result = fixture._run(path, body)
            self.assertEqual(result.returncode, 0, result.stderr)
            for key, value in VALUES.items():
                self.assertIn(f'{key}={value}\n', result.stdout)
            alternate = 'https://example.invalid/releases/alternate.deb'
            result = fixture._run(path, body, extra=f'export PLEBIAN_OS_NATIVE_DEB_URL={alternate}\n')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f'PLEBIAN_OS_NATIVE_DEB_URL={alternate}\n', result.stdout)
            # Existing provision semantics intentionally classify only a
            # nonempty value as explicit. Do not change every release field's
            # precedence as part of adding this five-field selection.
            result = fixture._run(path, body, extra='export PLEBIAN_OS_NATIVE_DEB_URL=\n')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f'PLEBIAN_OS_NATIVE_DEB_URL={VALUES["PLEBIAN_OS_NATIVE_DEB_URL"]}\n', result.stdout)

    def test_builders_do_not_fill_named_manifest_holes_from_ambient_selection(self):
        for version in ('0.1.8', '0.2.2'):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                (root / 'releases').mkdir()
                (root / 'VERSION').write_text(version + '\n')
                (root / 'releases' / f'{version}.env').write_text(
                    f'PLEBIAN_OS_VERSION={version}\nPLEBIAN_OS_RELEASE_MODE=1\n')
                with mock.patch.object(vm, 'REPO', root), mock.patch.dict(os.environ, VALUES):
                    with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                        if version == '0.2.2':
                            with self.assertRaises(SystemExit):
                                vm.apply_release_manifest(version)
                        else:
                            vm.apply_release_manifest(version)
                            for key in VALUES:
                                self.assertEqual(os.environ[key], '')
                # Execute the actual standalone loader and validator, with only
                # HERE bound to the private fixture; no build/remaster occurs.
                command = shell_function(SHELLS[2], 'load_release_manifest') + '\n'
                command += shell_function(SHELLS[2], 'validate_native_release_closure') + '\n'
                command += 'load_release_manifest "$1"\n'
                command += 'validate_native_release_closure "$1" 1\n'
                command += '\n'.join(f'[ -z "${{{key}}}" ]' for key in VALUES)
                result = subprocess.run(['/bin/bash', '-euc', command, 'loader', version],
                    env={'PATH': '/usr/bin:/bin', 'HERE': str(root), **VALUES},
                    capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 1 if version == '0.2.2' else 0, result.stderr)

    def test_real_private_selector_moves_five_keys_and_rolls_back_exactly(self):
        fixture = closure_fixture.ClosureSelectionTests()
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = fixture._machine(base)
            before = env.read_bytes()
            manifest = fixture._f120_manifest_text(PLEBIAN_OS_VERSION='0.2.2',
                PLEBIAN_OS_REF='v0.2.2', **VALUES)
            commit = fixture._source(base, manifest, version='0.2.2', release='0.2.2', tag=None)
            result = fixture._run(base, '0.2.2', '--offline', '--development-commit', commit)
            self.assertEqual(result.returncode, 0, result.stderr)
            selected = fixture._values(env)
            for key, value in VALUES.items():
                self.assertEqual(selected[key], value)
            for key, value in closure_fixture.OPERATOR_VALUES:
                self.assertEqual(selected[key], value)
            self.assertEqual(subprocess.check_output(['git', '-C', str(base / 'src'), 'tag', '--list']), b'')
            rolled = fixture._run(base, '--rollback')
            self.assertEqual(rolled.returncode, 0, rolled.stderr)
            self.assertEqual(env.read_bytes(), before)

    def test_real_selector_refuses_missing_selection_before_mutation(self):
        fixture = closure_fixture.ClosureSelectionTests()
        for missing in (None, *VALUES):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                env = fixture._machine(base)
                before = env.read_bytes()
                selected = {} if missing is None else {k: v for k, v in VALUES.items() if k != missing}
                manifest = fixture._f120_manifest_text(PLEBIAN_OS_VERSION='0.2.2',
                    PLEBIAN_OS_REF='v0.2.2', **selected)
                commit = fixture._source(base, manifest, version='0.2.2', release='0.2.2', tag=None)
                result = fixture._run(base, '0.2.2', '--offline', '--development-commit', commit)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('native runtime closure', result.stderr)
                self.assertEqual(env.read_bytes(), before)
                self.assertEqual(fixture._recovery_records(base), [])


if __name__ == '__main__':
    unittest.main()
