"""Exercise pinned Secrets installation and failure recovery in a scratch root."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import unittest

from test_lid_update import Fixture, as_user, under
from test_lifecycle_hardening import update_call_site
import test_zell_update as zell


ROOT = Path(__file__).resolve().parents[1]
UPDATE = (ROOT / 'provision/plebian-os-update.sh').read_text()
FILES = (
    'bin/kilix-secrets', 'bin/kilix-secretsd', 'include/kilix_secrets.h',
    'lib/libkilix-secrets.a', 'lib/libkilix-secrets.so.0',
    'lib/pkgconfig/kilix-secrets.pc', 'lib/systemd/user/kilix-secrets.service',
    'lib/systemd/user/kilix-secrets.socket',
    'share/doc/kilix-secrets/DEPENDENCIES.md',
    'share/doc/kilix-secrets/F113-CUSTODY-INTERFACE.md',
    'share/doc/kilix-secrets/LICENSE', 'share/doc/kilix-secrets/THIRD_PARTY_NOTICES.md',
)


class SecretsUpgradeTests(unittest.TestCase):
    def fixture(self, *, bad_package=''):
        fx = Fixture(self)
        fx.repo = fx.tmp / 'source'
        fx.repo.mkdir()
        for name in FILES:
            path = fx.repo / 'package' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('pinned fixture ' + name + '\n')
            path.chmod(0o755 if name.startswith('bin/') or name.endswith('.so.0') else 0o644)
        (fx.repo / 'package/lib/libkilix-secrets.so').symlink_to('libkilix-secrets.so.0')
        if bad_package == 'extra':
            (fx.repo / 'package/bin/unexpected').write_text('unlisted\n')
        elif bad_package == 'symlink':
            (fx.repo / 'package/include/unexpected').symlink_to('/nonexistent')
        elif bad_package == 'missing':
            (fx.repo / 'package/include/kilix_secrets.h').unlink()
        elif bad_package == 'link':
            path = fx.repo / 'package/lib/libkilix-secrets.so'
            path.unlink(); path.symlink_to('wrong-library')
        (fx.repo / 'Makefile').write_text(
            '.PHONY: all install\nall:\n\t@true\ninstall:\n'
            '\tmkdir -p "$(DESTDIR)$(PREFIX)"\n'
            '\tcp -a package/. "$(DESTDIR)$(PREFIX)/"\n')
        env = {'PATH': '/usr/bin:/bin', 'HOME': str(fx.tmp),
               'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null'}
        for args in (['init', '-q'], ['add', '.'],
                     ['-c', 'user.name=itsmygithubacct', '-c',
                      'user.email=itsmygithubacct@users.noreply.github.com',
                      'commit', '-qm', 'Fixture package']):
            subprocess.run(['git', '-C', str(fx.repo), *args], env=env,
                           check=True, capture_output=True)
        fx.ref = subprocess.check_output(['git', '-C', str(fx.repo), 'rev-parse', 'HEAD'],
                                         env=env, text=True).strip()
        fx.calls = fx.tmp / 'calls'
        fx.shims = fx.tmp / 'bin'; fx.shims.mkdir()
        # Only ownership flags are removed; real install, archive and make run.
        (fx.shims / 'install').write_text('''#!/bin/bash
args=()
while (($#)); do
    case "$1" in -o|-g) shift 2 ;; *) args+=("$1"); shift ;; esac
done
if [ -n "${FIXTURE_FAIL_INSTALL:-}" ] \
        && [ "$FIXTURE_FAIL_INSTALL" = "${args[-1]##*/}" ]; then exit 73; fi
exec /usr/bin/install "${args[@]}"
''')
        (fx.shims / 'install').chmod(0o755)
        fx.env = {**env, 'PATH': f'{fx.shims}:/usr/bin:/bin',
                  'FIXTURE_ROOT': str(fx.root), 'FIXTURE_REPO': str(fx.repo),
                  'FIXTURE_FETCH_REF': fx.ref, 'FIXTURE_CALLS': str(fx.calls),
                  'KILIX_SECRETS_REF': fx.ref, 'KILIX_SECRETS_BRANCH': '',
                  'KILIX_SECRETS_REPO': 'https://github.com/itsmygithubacct/kilix-secrets.git'}
        (fx.root / 'user-data').mkdir(mode=0o700)
        (fx.root / 'user-data/vault').write_bytes(b'untouched encrypted user data')
        return fx

    def mapped(self, fx, code):
        # PREFIX is package metadata, while deployment destinations are remapped.
        return as_user(under(code, fx.root)).replace(
            f'PREFIX={fx.root}/usr/local', 'PREFIX=/usr/local')

    def stubs(self):
        return '''
systemctl() {
    printf 'systemctl %s\\n' "$*" >>"$FIXTURE_CALLS"
    if [ "$*" = '--global enable kilix-secrets.socket' ]; then
        mkdir -p "$FIXTURE_ROOT/etc/systemd/user/sockets.target.wants"
        ln -sfn /usr/local/lib/systemd/user/kilix-secrets.socket \
            "$FIXTURE_ROOT/etc/systemd/user/sockets.target.wants/kilix-secrets.socket"
        [ "${FIXTURE_FAIL_ENABLE:-0}" != 1 ] || return 74
    fi
}
ldconfig() { echo ldconfig >>"$FIXTURE_CALLS"; }
git() {
    if [ "${3:-}" = fetch ]; then
        printf 'fetch %s %s\\n' "${5:-}" "${6:-}" >>"$FIXTURE_CALLS"
        [ "${FIXTURE_FAIL_FETCH:-0}" != 1 ] || return 75
        command git -C "$2" fetch --depth=1 "$FIXTURE_REPO" "$FIXTURE_FETCH_REF"
    else
        command git "$@"
    fi
}
sudo() { "$@"; }
export -f systemctl ldconfig git sudo
'''

    def root(self, fx, name, *args):
        return subprocess.run(['bash', '-s', '--', *map(str, args)], env=fx.env,
                              input=self.stubs() + self.mapped(fx, zell.heredoc(name)),
                              capture_output=True, text=True, timeout=60)

    def snapshot(self, fx):
        result = self.root(fx, 'ROOT_SNAPSHOT')
        self.assertEqual(result.returncode, 0, result.stderr)
        return Path(result.stdout.strip())

    def tree(self, fx):
        return {k: v for k, v in fx.tree().items()
                if not k.startswith('var/lib/plebian-os/update-rollback.')}

    def old_install(self, fx):
        for name in (*FILES, 'share/kilix-secrets/source.tar',
                     'share/kilix-secrets/provenance.env'):
            path = fx.root / 'usr/local' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('previous ' + name + '\n'); path.chmod(0o640)
        (fx.root / 'usr/local/lib/libkilix-secrets.so').symlink_to('libkilix-secrets.so.0')
        wants = fx.root / 'etc/systemd/user/sockets.target.wants'
        wants.mkdir(parents=True)
        (wants / 'kilix-secrets.socket').symlink_to('/previous/socket')
        for prefix in ('usr', 'etc'):
            for path in (fx.root / prefix).rglob('*'):
                if path.is_dir() and not path.is_symlink(): path.chmod(0o755)

    def install(self, fx, txn, *, rollback=False, after=''):
        funcs = '\n'.join(self.mapped(fx, zell.function(n)) for n in (
            'install_kilix_secrets_update', 'validate_root_transaction_dir',
            'stack_transaction_cleanup', 'test_fail_after_boundary'))
        for name in ('ROOT_RESTORE', 'ROOT_CLEAN'):
            (fx.tmp / name).write_text(self.stubs() + self.mapped(fx, zell.heredoc(name)))
        outer = fx.tmp / 'outer'; outer.mkdir(exist_ok=True)
        env = {**fx.env, '_STACK_ROOT_TXN_DIR': str(txn), '_STACK_TXN_DIR': str(outer),
               'PLEBIAN_OS_UPDATE_TEST_FAIL_AFTER': 'kilix-secrets'}
        script = '''set -euo pipefail
log() { :; }
warn() { printf '%s\\n' "$*" >&2; }
die() { warn "$*"; exit 1; }
release_kilix_transaction_lock() { :; }
rollback_stack_transaction() { bash "$HOME/ROOT_RESTORE" "$_STACK_ROOT_TXN_DIR"; }
remove_root_stack_snapshot() { bash "$HOME/ROOT_CLEAN" "$1"; }
'''
        if rollback:
            script += '_STACK_TXN_ACTIVE=1\n_STACK_TXN_COMMITTED=0\ntrap stack_transaction_cleanup EXIT\n'
        return subprocess.run(['bash', '-c', funcs + self.stubs() + script
                               + '\numask 077\ninstall_kilix_secrets_update\n' + after],
                              env=env, capture_output=True, text=True, timeout=60)

    def test_exact_pinned_install_and_repeat_preserve_private_state(self):
        fx = self.fixture(); txn = self.snapshot(fx)
        result = self.install(fx, txn)
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in FILES:
            path = fx.root / 'usr/local' / name
            self.assertEqual(path.read_bytes(), (fx.repo / 'package' / name).read_bytes())
            self.assertEqual(path.stat().st_mode & 0o777,
                             0o755 if name.startswith('bin/') or name.endswith('.so.0') else 0o644)
        self.assertEqual(os.readlink(fx.root / 'usr/local/lib/libkilix-secrets.so'),
                         'libkilix-secrets.so.0')
        source = fx.root / 'usr/local/share/kilix-secrets/source.tar'
        expected = subprocess.check_output(['git', '-C', str(fx.repo), 'archive', fx.ref])
        self.assertEqual(source.read_bytes(), expected)
        provenance = (source.parent / 'provenance.env').read_text()
        self.assertIn(f'KILIX_SECRETS_REF={fx.ref}\n', provenance)
        self.assertIn(hashlib.sha256(expected).hexdigest(), provenance)
        self.assertEqual((fx.root / 'user-data/vault').read_bytes(), b'untouched encrypted user data')
        self.assertIn(f'fetch https://github.com/itsmygithubacct/kilix-secrets.git {fx.ref}',
                      fx.calls.read_text())
        first = self.tree(fx)
        result = self.install(fx, txn)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.tree(fx), first)
        self.assertNotIn('restart', fx.calls.read_text())
        self.assertNotIn(' start ', fx.calls.read_text())

    def test_later_failure_and_interrupt_restore_old_files_or_absence(self):
        for previous in (False, True):
            for after, code in (('test_fail_after_boundary kilix-secrets\n', 1),
                                ("trap 'exit 143' TERM\nkill -TERM $$\n", 143)):
                with self.subTest(previous=previous, code=code):
                    fx = self.fixture()
                    if previous: self.old_install(fx)
                    before = self.tree(fx); txn = self.snapshot(fx)
                    result = self.install(fx, txn, rollback=True, after=after)
                    self.assertEqual(result.returncode, code, result.stderr)
                    self.assertEqual(self.tree(fx), before)
                    self.assertFalse(txn.exists())
                    self.assertEqual(fx.calls.read_text().count('ldconfig\n'), 2)

    def test_partial_install_and_enable_failure_restore_the_complete_snapshot(self):
        for key, value in (('FIXTURE_FAIL_INSTALL', 'libkilix-secrets.a'),
                           ('FIXTURE_FAIL_ENABLE', '1')):
            for previous in (False, True):
                with self.subTest(key=key, previous=previous):
                    fx = self.fixture()
                    if previous: self.old_install(fx)
                    before = self.tree(fx); txn = self.snapshot(fx)
                    fx.env[key] = value
                    result = self.install(fx, txn, rollback=True)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotEqual(result.returncode, 70, result.stderr)
                    self.assertEqual(self.tree(fx), before)
                    self.assertFalse(txn.exists())

    def test_invalid_pins_and_fetch_failures_never_publish(self):
        for key, value in (('KILIX_SECRETS_REF', 'main'),
                           ('KILIX_SECRETS_REF', '1' * 40),
                           ('KILIX_SECRETS_BRANCH', 'main'),
                           ('KILIX_SECRETS_REPO', 'https://example.invalid/source.git'),
                           ('FIXTURE_FAIL_FETCH', '1')):
            with self.subTest(key=key, value=value):
                fx = self.fixture(); self.old_install(fx)
                before = self.tree(fx); txn = self.snapshot(fx)
                fx.env[key] = value
                result = self.install(fx, txn, rollback=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotEqual(result.returncode, 70, result.stderr)
                self.assertEqual(self.tree(fx), before)

    def test_unexpected_package_objects_are_refused_before_publication(self):
        for defect in ('extra', 'symlink', 'missing', 'link'):
            with self.subTest(defect=defect):
                fx = self.fixture(bad_package=defect); self.old_install(fx)
                before = self.tree(fx); txn = self.snapshot(fx)
                result = self.install(fx, txn, rollback=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotEqual(result.returncode, 70, result.stderr)
                self.assertEqual(self.tree(fx), before)

    def test_unsafe_parent_or_leaf_never_writes_through_symlinks(self):
        for relative in ('usr/local/include', 'etc/systemd/user', 'usr/local/bin/kilix-secrets'):
            with self.subTest(relative=relative):
                fx = self.fixture(); txn = self.snapshot(fx)
                outside = fx.tmp / 'outside'
                if relative.endswith('kilix-secrets'): outside.write_bytes(b'keep')
                else: outside.mkdir()
                path = fx.root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.symlink_to(outside)
                result = self.install(fx, txn)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(outside.read_bytes() if outside.is_file() else list(outside.iterdir()),
                                 b'keep' if outside.is_file() else [])

    def test_older_snapshot_does_not_claim_secrets_files(self):
        fx = self.fixture(); self.old_install(fx); txn = self.snapshot(fx)
        (txn / 'kilix-secrets').unlink()
        self.assertNotEqual(self.install(fx, txn).returncode, 0)
        path = fx.root / 'usr/local/bin/kilix-secrets'
        path.write_text('newer installation\n')
        before = self.tree(fx)
        result = self.root(fx, 'ROOT_RESTORE', txn)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.tree(fx), before)

    def test_empty_pin_and_dry_run_write_nothing(self):
        for values in ({'KILIX_SECRETS_REF': ''}, {'DRY_RUN': '1'}):
            fx = self.fixture(); before = self.tree(fx); fx.env.update(values)
            result = self.install(fx, fx.tmp / 'no-snapshot')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.tree(fx), before)
            self.assertFalse(fx.calls.exists())

    def test_install_runs_inside_transaction_after_dependencies_before_zell(self):
        step = update_call_site('install_kilix_secrets_update')
        self.assertLess(update_call_site('begin_stack_transaction'), step)
        self.assertLess(update_call_site('refresh_os_dependencies'), step)
        self.assertLess(step, update_call_site('install_zell_runtime'))
        self.assertLess(step, update_call_site('commit_stack_transaction'))
        self.assertIn('install_kilix_secrets_update\ntest_fail_after_boundary kilix-secrets', UPDATE)


if __name__ == '__main__':
    unittest.main()
