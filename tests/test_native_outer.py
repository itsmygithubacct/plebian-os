"""Real shell sequencing/private root snapshots, with a synthetic helper peer.

No package manager, native ELF, model, network or host-root modification runs.
Downloader tests substitute only the curl executable with an inert writer;
the real kernel file-size bound and timeout command are still exercised.
"""
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

import test_native_closure as closure
import test_provision_transaction as provision_fixture

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ('provision/plebian-os-provision.sh', 'provision/plebian-os-update.sh')
FUNCTIONS = ('native_download_archive', 'apply_selected_native_runtime',
             'rollback_native_runtime_transaction', 'commit_native_runtime_transaction',
             'finish_native_runtime_transaction')
PAYLOAD = b'data'
VALUES = {**closure.VALUES, 'PLEBIAN_OS_NATIVE_DEB_BYTES': str(len(PAYLOAD)),
          'PLEBIAN_OS_NATIVE_DEB_SHA256': hashlib.sha256(PAYLOAD).hexdigest()}


class NativeOuterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='native-outer-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.outer = self.base / 'outer'
        self.outer.mkdir(mode=0o700)
        self.events = self.base / 'events'
        self.archive = self.base / 'input'
        self.archive.write_bytes(PAYLOAD)

    def run_shell(self, source, body, *, values=None, fail=''):
        env = {'PATH': '/usr/bin:/bin', 'HOME': str(self.base), 'LANG': 'C.UTF-8',
               'PLEBIAN_OS_PROVISION_LIB_ONLY': '1',
               'PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY': '1',
               'PLEBIAN_OS_RELEASE': '0.2.2', 'PLEBIAN_OS_VERSION': '0.2.2',
               'PLEBIAN_OS_RELEASE_MODE': '1', 'OUTER': str(self.outer),
               'EVENTS': str(self.events), 'ARCHIVE_INPUT': str(self.archive),
               'NATIVE_FAIL': fail, **(VALUES if values is None else values)}
        prelude = 'set -euo pipefail\nsource ' + shlex.quote(str(ROOT / source)) + '\n'
        prelude += r'''
native_download_archive() { cp -- "$ARCHIVE_INPUT" "$1"; }
native_runtime_command() {
    printf '%s\t' "$@" >>"$EVENTS"
    printf '\n' >>"$EVENTS"
    if [ "$1" = prepare ]; then
        [ "$2" = --transaction ] && [ "$(cat "$OUTER/native-transaction")" = "$3" ] || return 90
        [ "$(stat -c '%a' "$OUTER/native-transaction")" = 600 ] || return 91
    fi
    [ "$NATIVE_FAIL" != "$1" ] || return 71
}
'''
        return subprocess.run(['/bin/bash', '-c', prelude + body], env=env,
                              text=True, capture_output=True, timeout=10)

    def calls(self):
        if not self.events.exists():
            return []
        return [line.rstrip('\t').split('\t') for line in self.events.read_text().splitlines()]

    def test_standalone_transaction_functions_remain_identical(self):
        for name in FUNCTIONS:
            self.assertEqual(closure.shell_function(SCRIPTS[0], name),
                             closure.shell_function(SCRIPTS[1], name), name)

    def test_actual_shell_records_token_before_prepare_and_orders_success(self):
        for index, source in enumerate(SCRIPTS):
            with self.subTest(source=source):
                target = self.base / f'success-{index}'
                target.mkdir(mode=0o700)
                self.outer = target
                self.events.unlink(missing_ok=True)
                result = self.run_shell(source, 'apply_selected_native_runtime "$OUTER" 0\n'
                    'commit_native_runtime_transaction\nfinish_native_runtime_transaction\n'
                    '[ "$NATIVE_TRANSACTION_STARTED" = 0 ]\n')
                self.assertEqual(result.returncode, 0, result.stderr)
                calls = self.calls()
                self.assertEqual([r[0] for r in calls], ['prepare', 'apply', 'commit', 'finish'])
                token = (target / 'native-transaction').read_text().strip()
                self.assertRegex(token, r'^[0-9a-f]{32}$')
                self.assertEqual(calls[0][1:3], ['--transaction', token])
                for command in calls[1:]:
                    self.assertEqual(command[1:], [token])
                args = dict(zip(calls[0][1::2], calls[0][2::2]))
                self.assertEqual(args['--sha256'], VALUES['PLEBIAN_OS_NATIVE_DEB_SHA256'])
                self.assertEqual(args['--bytes'], '4')
                self.assertEqual(args['--source-commit'], VALUES['PLEBIAN_OS_NATIVE_SOURCE_REF'])
                self.assertEqual(args['--content-commit'], VALUES['PLEBIAN_OS_NATIVE_CONTENT_REF'])
                self.assertEqual(Path(args['--artifact']).read_bytes(), PAYLOAD)
                self.assertEqual(Path(args['--artifact']).stat().st_mode & 0o777, 0o600)

    def test_failed_prepare_and_apply_recover_only_the_recorded_token(self):
        for index, (source, failure) in enumerate((s, f) for s in SCRIPTS for f in ('prepare', 'apply')):
            with self.subTest(source=source, failure=failure):
                self.outer = self.base / f'failed-{index}'
                self.outer.mkdir(mode=0o700)
                self.events.unlink(missing_ok=True)
                result = self.run_shell(source,
                    'if apply_selected_native_runtime "$OUTER" 0; then exit 99; fi\n'
                    'rollback_native_runtime_transaction\n[ "$NATIVE_TRANSACTION_STARTED" = 0 ]\n', fail=failure)
                self.assertEqual(result.returncode, 0, result.stderr)
                token = (self.outer / 'native-transaction').read_text().strip()
                expected = ['prepare', 'rollback'] if failure == 'prepare' else ['prepare', 'apply', 'rollback']
                self.assertEqual([row[0] for row in self.calls()], expected)
                self.assertEqual(self.calls()[-1], ['rollback', token, '--allow-unpublished'])

    def test_checksum_size_and_private_directory_refusals_precede_helper(self):
        for index, (source, problem) in enumerate((s, p) for s in SCRIPTS for p in ('checksum', 'size', 'directory')):
            with self.subTest(source=source, problem=problem):
                self.outer = self.base / f'invalid-{index}'
                self.outer.mkdir(mode=0o755 if problem == 'directory' else 0o700)
                self.events.unlink(missing_ok=True)
                values = dict(VALUES)
                if problem == 'checksum':
                    values['PLEBIAN_OS_NATIVE_DEB_SHA256'] = '0' * 64
                if problem == 'size':
                    values['PLEBIAN_OS_NATIVE_DEB_BYTES'] = '5'
                result = self.run_shell(source, 'apply_selected_native_runtime "$OUTER" 0\n', values=values)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.calls(), [])
                self.assertFalse((self.outer / 'native-transaction').exists())

    def test_dry_run_and_old_empty_selection_are_inert(self):
        for source in SCRIPTS:
            for old in (False, True):
                with self.subTest(source=source, old=old):
                    values = {key: '' for key in VALUES} if old else VALUES
                    body = 'PLEBIAN_OS_RELEASE=0.2.1\n' if old else ''
                    body += 'apply_selected_native_runtime "$OUTER" ' + ('0' if old else '1') + '\n'
                    body += 'rollback_native_runtime_transaction\ncommit_native_runtime_transaction\nfinish_native_runtime_transaction\n'
                    result = self.run_shell(source, body, values=values)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(self.calls(), [])
                    self.assertEqual(list(self.outer.iterdir()), [])

    def test_real_provision_snapshot_restores_only_after_native_rollback(self):
        fixture = provision_fixture.ProvisionRootTransactionTests()
        for fail in (False, True):
            with self.subTest(fail=fail):
                root = self.base / ('retained' if fail else 'restored')
                root.mkdir()
                setup, paths = fixture._layout(root)
                existing = shlex.quote(str(paths['existing']))
                callback = 'native_runtime_command() {\n[ "$1" = rollback ]\n'
                callback += f'[ "$(cat {existing})" = changed ]\n'
                callback += 'return ' + ('71' if fail else '0') + '\n}\n'
                result = fixture._run(setup + 'begin_provision_root_transaction\n'
                    + f'printf "changed\\n" >{existing}\n'
                    + 'NATIVE_TRANSACTION_STARTED=1\nNATIVE_TRANSACTION_TOKEN=' + 'a' * 32 + '\n'
                    + callback + 'exit 55\n')
                self.assertEqual(result.returncode, 70 if fail else 55, result.stderr)
                self.assertEqual(paths['existing'].read_text(), 'changed\n' if fail else 'before\n')
                retained = list(paths['state'].glob('provision-rollback.*'))
                self.assertEqual(len(retained), 1 if fail else 0)

    def test_real_provision_commit_and_finish_straddle_outer_commit(self):
        fixture = provision_fixture.ProvisionRootTransactionTests()
        for failure in ('', 'commit', 'finish'):
            with self.subTest(failure=failure):
                root = self.base / ('commit-' + (failure or 'ok'))
                root.mkdir()
                setup, paths = fixture._layout(root)
                existing = shlex.quote(str(paths['existing']))
                callback = r'''
native_runtime_command() {
    case "$1" in
        commit) [ "$PROVISION_ROOT_TRANSACTION_ACTIVE:$PROVISION_ROOT_TRANSACTION_COMMITTED" = 1:0 ] || return 91 ;;
        finish) [ "$PROVISION_ROOT_TRANSACTION_ACTIVE:$PROVISION_ROOT_TRANSACTION_COMMITTED" = 0:1 ] || return 92 ;;
        rollback) [ "$PROVISION_ROOT_TRANSACTION_COMMITTED" = 0 ] || return 93 ;;
        *) return 94 ;;
    esac
'''
                callback += '[ "$1" != ' + shlex.quote(failure) + ' ] || return 71\n}\n'
                result = fixture._run(setup + 'begin_provision_root_transaction\n'
                    + f'printf "changed\\n" >{existing}\n'
                    + 'NATIVE_TRANSACTION_STARTED=1\nNATIVE_TRANSACTION_TOKEN=' + 'b' * 32 + '\n'
                    + callback + 'commit_provision_root_transaction\n')
                self.assertEqual(result.returncode, 1 if failure == 'commit' else 0, result.stderr)
                self.assertEqual(paths['existing'].read_text(), 'before\n' if failure == 'commit' else 'changed\n')
                self.assertEqual(len(list(paths['state'].glob('provision-rollback.*'))), 1 if failure == 'finish' else 0)

    def test_real_updater_rollback_refusal_leaves_every_outer_restore_unentered(self):
        body = r'''
NATIVE_TRANSACTION_STARTED=1
NATIVE_TRANSACTION_TOKEN=cccccccccccccccccccccccccccccccc
deinit_new_kilix_submodules() { printf 'UNEXPECTED\n' >>"$EVENTS"; }
restore_root_stack_snapshot() { printf 'UNEXPECTED\n' >>"$EVENTS"; }
rollback_stack_transaction
'''
        result = self.run_shell(SCRIPTS[1], body, fail='rollback')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [['rollback', 'c' * 32, '--allow-unpublished']])
        self.assertTrue(self.outer.exists())

    def test_recovery_warning_distinguishes_attempted_token_and_retains_owner_diagnostic(self):
        for source in SCRIPTS:
            with self.subTest(source=source):
                body = r'''
NATIVE_TRANSACTION_STARTED=1
NATIVE_TRANSACTION_TOKEN=77777777777777777777777777777777
native_runtime_command() {
    [ "$1" = rollback ] || return 99
    printf '%s\n' 'native transaction is not the active owner; active token 66666666666666666666666666666666' >&2
    return 71
}
if rollback_native_runtime_transaction; then exit 99; fi
[ "$NATIVE_TRANSACTION_STARTED" = 1 ]
'''
                result = self.run_shell(source, body)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('active token ' + '6' * 32, result.stderr)
                self.assertIn('attempted token ' + '7' * 32, result.stderr)
                self.assertIn('this token may have no journal', result.stderr)
                self.assertIn('/usr/local/sbin/plebian-os-native-runtime status as root',
                              result.stderr)
                self.assertNotIn('recovery token ' + '7' * 32, result.stderr)

    def test_updater_helper_dispatch_uses_fixed_identity_and_elevation_tools(self):
        original = closure.shell_function(SCRIPTS[1], 'native_runtime_command')
        fixed = ('/usr/bin/id', '/usr/bin/sudo', '/usr/local/sbin/plebian-os-native-runtime')
        for path in fixed:
            self.assertEqual(original.count(path), 1)
        poison = self.base / 'poison'
        poison.mkdir()
        for name in ('id', 'sudo', 'plebian-os-native-runtime'):
            path = poison / name
            path.write_text('#!/bin/sh\nprintf "UNEXPECTED\\n" >>"$EVENTS"\nexit 99\n')
            path.chmod(0o700)
        for uid in ('0', '1000'):
            with self.subTest(uid=uid):
                identity, elevation, helper = [self.base / (name + uid)
                                               for name in ('identity-', 'elevation-', 'helper-')]
                identity.write_text('#!/bin/sh\nprintf "%s\\n" ' + uid + '\n')
                elevation.write_text('#!/bin/sh\nprintf "elevate\\n" >>"$EVENTS"\nexec "$@"\n')
                helper.write_text('#!/bin/sh\nprintf "%s\\n" "$@" >>"$EVENTS"\n')
                for path in (identity, elevation, helper):
                    path.chmod(0o700)
                program = original
                for selected, stub in zip(fixed, (identity, elevation, helper)):
                    program = program.replace(selected, shlex.quote(str(stub)))
                self.events.unlink(missing_ok=True)
                result = subprocess.run(['/bin/bash', '-euc',
                    program + '\nnative_runtime_command status\n'],
                    env={'PATH': str(poison), 'EVENTS': str(self.events)},
                    text=True, capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.events.read_text().splitlines(),
                                 ['status'] if uid == '0' else ['elevate', 'status'])

    def test_real_updater_commit_orders_native_generation_outer_and_finish(self):
        for index, failure in enumerate(('', 'finish')):
            with self.subTest(failure=failure):
                self.outer = self.base / f'update-{index}'
                self.outer.mkdir(mode=0o700)
                self.events.unlink(missing_ok=True)
                body = r'''
NATIVE_TRANSACTION_STARTED=1
NATIVE_TRANSACTION_TOKEN=dddddddddddddddddddddddddddddddd
_STACK_TXN_DIR="$OUTER"
_STACK_ROOT_TXN_DIR="$OUTER"
_STACK_TXN_ACTIVE=1
_STACK_TXN_COMMITTED=0
native_runtime_command() {
    printf '%s\n' "$1" >>"$EVENTS"
    case "$1" in
        commit) [ "$_STACK_TXN_ACTIVE:$_STACK_TXN_COMMITTED" = 1:0 ] || return 91 ;;
        finish) [ "$_STACK_TXN_ACTIVE:$_STACK_TXN_COMMITTED" = 0:1 ] || return 92 ;;
        *) return 93 ;;
    esac
    [ "$NATIVE_FAIL" != "$1" ] || return 71
}
commit_kilix_engine_generation() { printf 'generation\n' >>"$EVENTS"; }
remove_root_stack_snapshot() { printf 'remove\n' >>"$EVENTS"; }
release_kilix_transaction_lock() { printf 'unlock\n' >>"$EVENTS"; }
commit_stack_transaction
[ "$_STACK_TXN_ACTIVE:$_STACK_TXN_COMMITTED" = 0:1 ]
'''
                result = self.run_shell(SCRIPTS[1], body, fail=failure)
                self.assertEqual(result.returncode, 0, result.stderr)
                expected = ['commit', 'generation', 'finish'] + (['unlock'] if failure else ['remove', 'unlock'])
                self.assertEqual([r[0] for r in self.calls()], expected)
                self.assertEqual(self.outer.exists(), bool(failure))

    def test_fixed_download_argv_and_real_kernel_file_bound(self):
        writer = self.base / 'inert-curl'
        writer.write_text('#!/usr/bin/python3\nimport json,os,resource,sys\n'
            'print(json.dumps({"argv":sys.argv[1:],"fsize":resource.getrlimit(resource.RLIMIT_FSIZE)}),flush=True)\n'
            'with open(sys.argv[sys.argv.index("--output")+1],"wb") as f:\n'
            ' f.write(b"data" + (b"x" if os.environ.get("OVERFLOW")=="1" else b""))\n')
        writer.chmod(0o700)
        original = closure.shell_function(SCRIPTS[0], 'native_download_archive')
        self.assertEqual(original.count('/usr/bin/curl'), 1)
        program = original.replace('/usr/bin/curl', shlex.quote(str(writer)))
        for overflow in ('0', '1'):
            output = self.base / ('download-' + overflow)
            result = subprocess.run(['/bin/bash', '-euc', program + '\nnative_download_archive "$1"\n',
                'download', str(output)], capture_output=True, text=True, timeout=5,
                env={'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1', 'OVERFLOW': overflow, **VALUES})
            self.assertEqual(result.returncode == 0, overflow == '0', result.stderr)
            row = json.loads(result.stdout.splitlines()[0])
            self.assertEqual(row['fsize'], [4, 4])
            self.assertEqual(row['argv'], ['--disable', '--fail', '--silent', '--show-error', '--location',
                '--proto', '=https', '--proto-redir', '=https', '--max-redirs', '5',
                '--connect-timeout', '20', '--max-time', '120', '--max-filesize', '4',
                '--output', str(output), '--url', VALUES['PLEBIAN_OS_NATIVE_DEB_URL']])
            self.assertEqual(output.read_bytes(), PAYLOAD)

    def test_production_call_order_and_all_old_failure_boundaries_remain(self):
        provision = (ROOT / SCRIPTS[0]).read_text()
        update = (ROOT / SCRIPTS[1]).read_text()
        self.assertLess(provision.index('begin_provision_root_transaction\n'),
                        provision.index('install_native_runtime_helpers\n'))
        self.assertLess(provision.index('install_native_runtime_helpers\n'),
                        provision.index('apply_selected_native_runtime "$PROVISION_ROOT_TRANSACTION_DIR"'))
        self.assertLess(update.index('refresh_os_dependencies\n'),
                        update.index('apply_selected_native_runtime "$_STACK_TXN_DIR"'))
        self.assertLess(update.index('apply_selected_native_runtime "$_STACK_TXN_DIR"'),
                        update.index('test_fail_after_boundary pleb-install'))
        for boundary in ('os-layer', 'dependencies', 'native-runtime', 'pleb-checkout',
                         'pleb-install', 'component-update', 'session-env', 'provenance'):
            self.assertTrue('test_fail_after_boundary ' + boundary in update, boundary)


if __name__ == '__main__':
    unittest.main()
