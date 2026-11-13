"""Run Zell's upgrade and root rollback against a scratch filesystem.

The real carrier, installer, snapshot and restore code run here. Only fixed
system paths and root-ownership expectations are mapped to the test user's
scratch tree; no host install or service is changed.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from test_lid_update import Fixture, as_user, under
from test_lifecycle_hardening import update_call_site


ROOT = Path(__file__).resolve().parents[1]
UPDATE = (ROOT / 'provision/plebian-os-update.sh').read_text()
ARCHIVE = 'zell-0.1.1-x86_64.tar.xz'
LEAVES = (
    'usr/local/bin/zell',
    'usr/local/sbin/install-zell-runtime.py',
    'usr/local/share/plebian-os/zell-runtime.json',
    'usr/local/share/plebian-os/' + ARCHIVE,
    'usr/local/lib/systemd/user/kilix-secrets.service',
    'usr/local/lib/systemd/user/kilix-secrets.socket',
)


def function(name):
    start = UPDATE.index(name + '() {\n')
    return UPDATE[start:UPDATE.index('\n}\n', start) + 3]


def heredoc(name):
    start = UPDATE.index("<<'" + name + "'\n") + len(name) + 5
    return UPDATE[start:UPDATE.index('\n' + name, start)]


class ZellUpdateTests(unittest.TestCase):
    def fixture(self):
        fx = Fixture(self)
        fx.source = fx.tmp / 'os/provision'
        (fx.source / 'bundles').mkdir(parents=True)
        for name in ('install-zell-runtime.py', 'zell-runtime.json', 'bundles/' + ARCHIVE):
            shutil.copyfile(ROOT / 'provision' / name, fx.source / name)
        # A representative private vault outside the system runtime must survive.
        (fx.root / 'user-data').mkdir(mode=0o700)
        (fx.root / 'user-data/vault').write_bytes(b'private user state')
        return fx

    def run_root(self, fx, name, *args):
        script = as_user(under(heredoc(name), fx.root))
        return subprocess.run(['bash', '-s', '--', *map(str, args)],
                              input='systemctl() { :; }\n' + script,
                              env={'PATH': '/usr/bin:/bin', 'HOME': str(fx.tmp)},
                              capture_output=True, text=True, timeout=60)

    def snapshot(self, fx):
        result = self.run_root(fx, 'ROOT_SNAPSHOT')
        self.assertEqual(result.returncode, 0, result.stderr)
        return Path(result.stdout.strip())

    def tree(self, fx):
        return {k: v for k, v in fx.tree().items()
                if not k.startswith('var/lib/plebian-os/update-rollback.')}

    def old_install(self, fx):
        for name in LEAVES:
            path = fx.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('previous ' + name + '\n')
            path.chmod(0o640)
        app = fx.root / 'usr/local/share/kilix-zell'
        (app / 'tools').mkdir(parents=True)
        (app / 'tools/old-only').write_bytes(b'previous runtime')
        for directory in (fx.root / 'usr').rglob('*'):
            if directory.is_dir(): directory.chmod(0o755)
        app.chmod(0o750)
        # Leaf symlinks are replaced without overwriting what they pointed at.
        target = fx.root / 'user-data/launcher-target'
        target.write_bytes(b'keep this target')
        launcher = fx.root / LEAVES[0]
        launcher.unlink()
        launcher.symlink_to(target)

    def install(self, fx, txn, *, rollback=False, after='', before=''):
        names = ('install_zell_runtime', 'validate_root_transaction_dir',
                 'stack_transaction_cleanup', 'test_fail_after_boundary')
        functions = '\n'.join(as_user(under(function(n), fx.root)) for n in names)
        restore = fx.tmp / 'restore.sh'
        restore.write_text('systemctl() { :; }\n' + as_user(under(heredoc('ROOT_RESTORE'), fx.root)))
        cleanup = fx.tmp / 'cleanup.sh'
        cleanup.write_text(as_user(under(heredoc('ROOT_CLEAN'), fx.root)))
        outer = fx.tmp / 'outer'; outer.mkdir(exist_ok=True)
        env = {'PATH': '/usr/bin:/bin', 'HOME': str(fx.tmp),
               'PLEBIAN_OS_DIR': str(fx.source.parent), '_STACK_ROOT_TXN_DIR': str(txn),
               '_STACK_TXN_DIR': str(outer), 'RESTORE': str(restore), 'CLEANUP': str(cleanup),
               'PLEBIAN_OS_UPDATE_TEST_FAIL_AFTER': 'zell-runtime'}
        harness = '''set -euo pipefail
log() { :; }
warn() { printf '%s\\n' "$*" >&2; }
die() { warn "$*"; exit 1; }
sudo() { "$@"; }
release_kilix_transaction_lock() { :; }
rollback_stack_transaction() { bash "$RESTORE" "$_STACK_ROOT_TXN_DIR"; }
remove_root_stack_snapshot() { bash "$CLEANUP" "$1"; }
'''
        if rollback:
            harness += '_STACK_TXN_ACTIVE=1\n_STACK_TXN_COMMITTED=0\ntrap stack_transaction_cleanup EXIT\n'
        return subprocess.run(['bash', '-c', functions + '\n' + harness + before
                               + '\numask 077\ninstall_zell_runtime\n' + after], env=env,
                              capture_output=True, text=True, timeout=60)

    def assert_installed(self, fx):
        app = fx.root / 'usr/local/share/kilix-zell'
        manifest = json.loads((app / 'runtime.json').read_text())
        for name, item in manifest['files'].items():
            path = app / name
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item['sha256'], name)
            self.assertEqual(path.stat().st_mode & 0o777, item['mode'], name)
        self.assertEqual((fx.root / LEAVES[0]).read_bytes(), (app / 'bin/zell').read_bytes())
        for name, source in ((LEAVES[1], 'install-zell-runtime.py'),
                             (LEAVES[2], 'zell-runtime.json'), (LEAVES[3], 'bundles/' + ARCHIVE)):
            self.assertEqual((fx.root / name).read_bytes(), (fx.source / source).read_bytes())
        for i, name in enumerate(LEAVES):
            self.assertEqual((fx.root / name).stat().st_mode & 0o777, 0o755 if i < 2 else 0o644)
        self.assertEqual(app.stat().st_mode & 0o777, 0o755)
        self.assertIn(str(app / 'libexec/kilix-secretsd'), (fx.root / LEAVES[4]).read_text())
        self.assertEqual((fx.root / 'user-data/vault').read_bytes(), b'private user state')

    def test_upgrade_installs_complete_runtime_and_repeated_update_is_safe(self):
        fx = self.fixture(); txn = self.snapshot(fx)
        result = self.install(fx, txn)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_installed(fx)
        before = self.tree(fx)
        result = self.install(fx, txn)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.tree(fx), before)

    def test_later_failure_restores_existing_install_or_original_absence(self):
        for previous in (False, True):
            with self.subTest(previous=previous):
                fx = self.fixture()
                if previous: self.old_install(fx)
                before = self.tree(fx); txn = self.snapshot(fx)
                result = self.install(fx, txn, rollback=True, after='test_fail_after_boundary zell-runtime\n')
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn('injected stack update failure after zell-runtime', result.stderr)
                self.assertEqual(self.tree(fx), before)
                self.assertFalse(txn.exists(), result.stderr)

    def test_interrupt_after_install_uses_the_same_outer_rollback(self):
        fx = self.fixture(); self.old_install(fx)
        before = self.tree(fx); txn = self.snapshot(fx)
        result = self.install(fx, txn, rollback=True, after="trap 'exit 143' TERM\nkill -TERM $$\n")
        self.assertEqual(result.returncode, 143, result.stderr)
        self.assertEqual(self.tree(fx), before)
        self.assertFalse(txn.exists())

    def test_failure_halfway_through_publication_restores_the_whole_previous_set(self):
        fx = self.fixture(); self.old_install(fx)
        before = self.tree(fx); txn = self.snapshot(fx)
        fail_once = '''mv() {
    case "${@: -1}" in */sbin/install-zell-runtime.py)
        if [ ! -f "$HOME/failed-once" ]; then
            : >"$HOME/failed-once"
            return 1
        fi ;;
    esac
    command mv "$@"
}
export -f mv
'''
        result = self.install(fx, txn, rollback=True, before=fail_once)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertTrue((fx.tmp / 'failed-once').exists())
        self.assertEqual(self.tree(fx), before)
        self.assertFalse(txn.exists())

    def test_corrupt_carrier_and_missing_inputs_leave_previous_install_untouched(self):
        for broken in ('corrupt', 'install-zell-runtime.py', 'zell-runtime.json', 'bundles/' + ARCHIVE):
            with self.subTest(broken=broken):
                fx = self.fixture(); self.old_install(fx)
                before = self.tree(fx); txn = self.snapshot(fx)
                if broken == 'corrupt':
                    (fx.source / 'bundles' / ARCHIVE).write_bytes(b'bad archive')
                else:
                    (fx.source / broken).unlink()
                result = self.install(fx, txn, rollback=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotEqual(result.returncode, 70, result.stderr)
                self.assertEqual(self.tree(fx), before)
                self.assertFalse(txn.exists())

    def test_changed_source_after_hashing_is_rejected_before_execution(self):
        fx = self.fixture(); before = self.tree(fx); txn = self.snapshot(fx)
        change = '''sha256sum() {
    command sha256sum "$@"
    case "$1" in */bundles/*) printf 'raise SystemExit("unexpected execution")\\n' >"$PLEBIAN_OS_DIR/provision/install-zell-runtime.py" ;; esac
}
'''
        result = self.install(fx, txn, before=change, rollback=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('unexpected execution', result.stderr)
        self.assertEqual(self.tree(fx), before)

    def test_unsafe_parent_is_refused_without_writing_through_it(self):
        fx = self.fixture(); txn = self.snapshot(fx)
        outside = fx.tmp / 'outside'; outside.mkdir()
        (fx.root / 'usr/local/bin').symlink_to(outside)
        result = self.install(fx, txn)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((fx.root / 'usr/local/share/kilix-zell').exists())
        restored = self.run_root(fx, 'ROOT_RESTORE', txn)
        self.assertNotEqual(restored.returncode, 0)
        self.assertEqual(list(outside.iterdir()), [])

    def test_older_snapshot_does_not_claim_unrecorded_zell_files(self):
        fx = self.fixture(); self.old_install(fx); txn = self.snapshot(fx)
        (txn / 'zell-runtime').unlink()  # An older updater has no Zell records.
        result = self.install(fx, txn)
        self.assertNotEqual(result.returncode, 0)  # Also cannot install without its snapshot.
        before = self.tree(fx)
        result = self.run_root(fx, 'ROOT_RESTORE', txn)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.tree(fx), before)

    def test_main_step_is_after_dependencies_and_before_transaction_commit(self):
        self.assertLess(update_call_site('begin_stack_transaction'), update_call_site('install_zell_runtime'))
        self.assertLess(update_call_site('refresh_os_dependencies'), update_call_site('install_zell_runtime'))
        self.assertLess(update_call_site('install_zell_runtime'), update_call_site('commit_stack_transaction'))
        self.assertIn('install_zell_runtime\ntest_fail_after_boundary zell-runtime', UPDATE)
        self.assertIn('restore_root_stack_snapshot "$_STACK_ROOT_TXN_DIR"', function('rollback_stack_transaction'))


if __name__ == '__main__':
    unittest.main()
