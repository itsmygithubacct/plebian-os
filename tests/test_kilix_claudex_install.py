"""Fresh install and upgrade install the catalog-pinned Claudex application.

Claudex does not auto-install, and the Zell runtime does not carry it. Both
paths call the Kilix app installer for the catalog id. This does not log in,
answer a trust prompt, or move the Kilix or voice-carrier pins.

Rollback covers the owned checkout only. The entrypoint and git bookkeeping
live inside that checkout; user config, browser state, credentials, and usage
state stay out of the snapshot.
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROVISION = ROOT / 'provision/plebian-os-provision.sh'
UPDATE = ROOT / 'provision/plebian-os-update.sh'
ENV = ROOT / 'releases/0.2.3.env'
# Present on the RC9 integration host. Absent in other checkouts; those runs
# still exercise a temporary env carrying different pin values.
ASSEMBLER_ENV = Path('/home/pleb/gpu_terminal/worktrees/023rc9-os/releases/0.2.3.env')
PIN_KEYS = ('KILIX_REF', 'KILIX95_REF', 'PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF')
ROLLBACK_FUNCTIONS = (
    'kilix_claudex_refuse',
    'kilix_claudex_require_user_dir',
    'kilix_claudex_install_paths_are_safe',
    'snapshot_stack_path',
    'restore_stack_path',
    'snapshot_kilix_claudex_install',
    'restore_kilix_claudex_install',
    'install_kilix_claudex',
)


def function(script, name):
    match = re.search(r'^%s\(\) \{\n.*?^\}\n' % re.escape(name), script, re.M | re.S)
    if not match:
        raise AssertionError(f'{name} is not defined')
    return match.group(0)


def pins(text):
    found = {}
    for line in text.splitlines():
        for key in ('KILIX_REF', 'KILIX95_REF', 'PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF'):
            if line.startswith(key + '='):
                found[key] = line.split('=', 1)[1]
    return found


class KilixClaudexInstallTests(unittest.TestCase):
    def fixture(self, home):
        kilix = Path(home) / 'kilix'
        kilix.mkdir()
        log = Path(home) / 'calls'
        executable = kilix / 'kilix'
        executable.write_text(
            '#!/bin/sh\n'
            f'printf "%s\\n" "$KILIX_APP_AUTO_INSTALL" >> {log}\n'
            f'printf "%s\\n" "$*" >> {log}\n')
        executable.chmod(0o755)
        return kilix, log

    def run_provision(self, home, kilix):
        body = function(PROVISION.read_text(), 'install_kilix_claudex')
        script = ('set -eu\n'
                  'log() { :; }\n'
                  'die() { echo "die: $*" >&2; exit 3; }\n'
                  'as_user() { "$@"; }\n'
                  'install_env=()\n'
                  f'DRY_RUN=0 KILIX_DIR={kilix} TARGET_USER=desktop\n'
                  + body + 'install_kilix_claudex\n')
        return subprocess.run(['bash', '-c', script], capture_output=True, text=True)

    def run_update(self, home, kilix):
        body = function(UPDATE.read_text(), 'install_kilix_claudex')
        script = ('set -eu\n'
                  'die() { echo "die: $*" >&2; exit 3; }\n'
                  'stack_env=()\n'
                  f'KILIX_DIR={kilix}\n'
                  + body + 'install_kilix_claudex\n')
        return subprocess.run(['bash', '-c', script], capture_output=True, text=True,
                              env=dict(os.environ, HOME=str(home)))

    def test_install_and_upgrade_call_the_catalog_installer(self):
        for run in (self.run_provision, self.run_update):
            with self.subTest(run.__name__), tempfile.TemporaryDirectory() as home:
                kilix, log = self.fixture(home)
                result = run(home, kilix)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(log.read_text().splitlines(),
                                 ['1', 'app install kilix-claudex'])

    def test_a_failed_installer_stops_the_install(self):
        for run in (self.run_provision, self.run_update):
            with self.subTest(run.__name__), tempfile.TemporaryDirectory() as home:
                kilix, log = self.fixture(home)
                (kilix / 'kilix').write_text('#!/bin/sh\nexit 1\n')
                result = run(home, kilix)
                self.assertEqual(result.returncode, 3)
                self.assertIn('Claudex application installation failed', result.stderr)
                self.assertFalse(log.exists())

    def test_provision_dry_run_installs_nothing(self):
        body = function(PROVISION.read_text(), 'install_kilix_claudex')
        result = subprocess.run(
            ['bash', '-c', 'set -eu\nlog() { echo "$*"; }\n'
             'DRY_RUN=1 TARGET_USER=desktop\n' + body + 'install_kilix_claudex\n'],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('would install the catalog-pinned Claudex application', result.stdout)

    def test_it_runs_after_needle_inside_the_upgrade_boundary(self):
        provision, update = PROVISION.read_text(), UPDATE.read_text()
        main = provision[provision.index('"$PLEB_DIR/bin/pleb" install \\\n'):]
        self.assertLess(main.index('install_kilix_needle\n'), main.index('install_kilix_claudex\n'))
        self.assertLess(main.index('install_kilix_claudex\n'), main.index('install_kilix_llm\n'))
        self.assertLess(update.index('begin_stack_transaction\n'), update.index('    install_kilix_claudex\n'))
        self.assertLess(update.index('    install_kilix_needle\n'), update.index('    install_kilix_claudex\n'))
        self.assertLess(update.index('    install_kilix_claudex\n'), update.index('    install_kilix_llm\n'))
        self.assertIn('    install_kilix_claudex\n    test_fail_after_boundary claudex\n', update)

    def test_install_leaves_release_pins_unchanged(self):
        update = UPDATE.read_text()
        for label, script in (('provision', PROVISION.read_text()), ('update', update)):
            body = function(script, 'install_kilix_claudex')
            for key in PIN_KEYS:
                self.assertNotIn(key, body, label)
        sources = [ENV]
        if ASSEMBLER_ENV.is_file():
            sources.append(ASSEMBLER_ENV)
            self.assertNotEqual(ENV.read_bytes(), ASSEMBLER_ENV.read_bytes())
        seen = []
        for source in sources:
            with self.subTest(source=str(source)):
                before = source.read_bytes()
                found = pins(before.decode())
                self.assertEqual(set(found), set(PIN_KEYS))
                for value in found.values():
                    self.assertRegex(value, r'^[0-9a-f]{40}$')
                seen.append(found)
                with tempfile.TemporaryDirectory() as home:
                    home = Path(home)
                    copy = home / 'pins.env'
                    copy.write_bytes(before)
                    kilix, _log = self.fixture(home)
                    body = function(update, 'install_kilix_claudex')
                    script = (
                        'set -eu\n'
                        'die() { echo "die: $*" >&2; exit 3; }\n'
                        'stack_env=()\n'
                        'saved=$(printf "%s\\n" "$KILIX_REF" "$KILIX95_REF" '
                        '"$PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF")\n'
                        f'KILIX_DIR={kilix}\n'
                        + body + 'install_kilix_claudex\n'
                        'now=$(printf "%s\\n" "$KILIX_REF" "$KILIX95_REF" '
                        '"$PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF")\n'
                        '[ "$saved" = "$now" ]\n')
                    result = subprocess.run(
                        ['bash', '-c', script], capture_output=True, text=True,
                        env={**os.environ, 'HOME': str(home), **found})
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(copy.read_bytes(), before)
                    self.assertEqual(source.read_bytes(), before)
        if len(seen) == 2:
            self.assertNotEqual(seen[0], seen[1])

    def test_upgrade_snapshots_only_the_owned_claudex_outputs(self):
        update = UPDATE.read_text()
        begin = function(update, 'begin_stack_transaction')
        rollback = function(update, 'rollback_stack_transaction')
        recover = function(update, 'recover_interrupted_stack_transaction')
        self.assertIn('\n    snapshot_kilix_claudex_install\n', begin)
        self.assertIn('restore_kilix_claudex_install || failed=1', rollback)
        self.assertIn('rollback_stack_transaction', recover)
        self.assertLess(begin.index('snapshot_kilix_claudex_install'),
                        begin.index('begin_root_stack_snapshot'))
        self.assertLess(rollback.index('restore_kilix_claudex_install'),
                        rollback.index('restore_root_stack_snapshot'))
        self.assertNotIn('snapshot_stack_path "$KILIX_DATA_HOME"', update)
        self.assertNotIn('snapshot_stack_path "$KILIX_DATA_HOME/desktop-apps"', update)


class ClaudexRollbackTests(unittest.TestCase):
    """Drive the real snapshot and restore around a fake offline installer."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name) / 'home files'
        self.home.mkdir(mode=0o700)
        self.data = self.home / 'kilix data'
        self.data.mkdir(mode=0o700)
        self.txn = self.home / 'txn'
        self.txn.mkdir(mode=0o700)
        self.kilix = self.home / 'kilix-checkout'
        self.kilix.mkdir(mode=0o700)
        self.log = self.home / 'installer-calls'
        installer = self.kilix / 'kilix'
        installer.write_text(
            '#!/bin/sh\n'
            'set -eu\n'
            'printf "%s\\n" "$KILIX_APP_AUTO_INSTALL" >> "$CLAUDEX_TEST_LOG"\n'
            'printf "%s\\n" "$*" >> "$CLAUDEX_TEST_LOG"\n'
            '[ "$1" = app ] && [ "$2" = install ] && [ "$3" = kilix-claudex ]\n'
            'root="$KILIX_DATA_HOME/desktop-apps"\n'
            'app="$root/kilix-claudex"\n'
            'if [ "${CLAUDEX_TEST_INTERRUPT:-0}" = 1 ]; then\n'
            '  mkdir -p "$root/.kilix-claudex.install-dead"\n'
            '  printf partial > "$root/.kilix-claudex.install-dead/payload"\n'
            '  printf lock > "$root/.kilix-claudex.lock"\n'
            '  mkdir -p "$app/.git"\n'
            '  printf "#!/bin/sh\\n" > "$app/claudex"\n'
            '  printf partial-head > "$app/.git/HEAD"\n'
            '  printf partial-origin > "$app/.git/config"\n'
            '  exit 1\n'
            'fi\n'
            'mkdir -p "$app/.git"\n'
            'printf "#!/bin/sh\\nprintf installed-claudex\\\\n\\n" > "$app/claudex"\n'
            'chmod 755 "$app/claudex"\n'
            'printf "%s\\n" "https://github.com/itsmygithubacct/kilix-claudex" > "$app/.git/config"\n'
            'printf "%s\\n" 8346512bff4d2bf2e3574285a588361124a4a321 > "$app/.git/HEAD"\n'
            'printf "%s\\n" "$app/claudex"\n')
        installer.chmod(0o755)
        self.decoys = {}
        for relative in (
            'user-config/settings.json',
            'browser-profile/Cookies',
            'credentials/token',
            'usage/state.json',
            'desktop-apps/kilix-needle/kilix-needle',
            'desktop-apps/assets/faster-whisper-small-en/model.bin',
        ):
            path = self.data / relative
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            path.write_bytes(b'before ' + relative.encode())
            self.decoys[path] = path.read_bytes()
        outside = self.home / '.config/claudex/config.json'
        outside.parent.mkdir(parents=True, mode=0o700)
        outside.write_bytes(b'outside user config')
        self.decoys[outside] = outside.read_bytes()
        secret = self.home / '.local/share/credentials/secret'
        secret.parent.mkdir(parents=True, mode=0o700)
        secret.write_bytes(b'credential bytes')
        self.decoys[secret] = secret.read_bytes()

    def checkout(self):
        return self.data / 'desktop-apps/kilix-claudex'

    def plant_previous(self):
        app = self.checkout()
        (app / '.git').mkdir(parents=True, mode=0o700)
        entry = app / 'claudex'
        entry.write_bytes(b'#!/bin/sh\nprintf previous-claudex\\n\n')
        entry.chmod(0o755)
        (app / '.git/HEAD').write_bytes(b'previous-head\n')
        (app / '.git/config').write_bytes(b'previous-origin\n')
        (app / 'notes').mkdir(mode=0o700)
        (app / 'notes/readme').write_bytes(b'previous notes\n')
        stage = self.data / 'desktop-apps/.kilix-claudex.install-previous'
        stage.mkdir(mode=0o700)
        (stage / 'payload').write_bytes(b'previous stage\n')
        lock = self.data / 'desktop-apps/.kilix-claudex.lock'
        lock.write_bytes(b'previous lock\n')
        lock.chmod(0o600)

    def run_rollback(self, script, **extra):
        update = UPDATE.read_text()
        body = ''.join(function(update, name) for name in ROLLBACK_FUNCTIONS)
        env = {
            'PATH': '/usr/bin:/bin',
            'HOME': str(self.home),
            'KILIX_DATA_HOME': str(self.data),
            'KILIX_DIR': str(self.kilix),
            'TXN': str(self.txn),
            'CLAUDEX_TEST_LOG': str(self.log),
        }
        env.update(extra)
        harness = (
            'set -euo pipefail\n'
            'die() { printf "die: %s\\n" "$*" >&2; exit 1; }\n'
            'stack_env=("KILIX_DATA_HOME=$KILIX_DATA_HOME")\n'
            '_STACK_TXN_DIR="$TXN"\n'
            'umask 077\n'
            + body + script)
        return subprocess.run(
            ['bash', '-c', harness], env=env, capture_output=True, text=True, timeout=30)

    def test_later_failure_restores_absence_and_previous_bytes(self):
        settings = self.data / 'user-config/settings.json'
        for previous in (False, True):
            with self.subTest(previous=previous):
                self.txn = self.home / f'txn-{previous}'
                self.txn.mkdir(mode=0o700)
                if self.checkout().exists():
                    subprocess.run(['rm', '-rf', '--', str(self.checkout())], check=True)
                if previous:
                    self.plant_previous()
                    before = tree(self.checkout())
                    stage = self.data / 'desktop-apps/.kilix-claudex.install-previous/payload'
                    lock = self.data / 'desktop-apps/.kilix-claudex.lock'
                    stage_before, lock_before = stage.read_bytes(), lock.read_bytes()
                before_decoys = {path: path.read_bytes() for path in self.decoys}
                result = self.run_rollback(
                    'snapshot_kilix_claudex_install\n'
                    'install_kilix_claudex\n'
                    # User state written after the snapshot must survive rollback.
                    'printf " during" >> "$KILIX_DATA_HOME/user-config/settings.json"\n'
                    'false || restore_kilix_claudex_install\n')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.log.read_text().splitlines()[-2:],
                                 ['1', 'app install kilix-claudex'])
                for path, original in before_decoys.items():
                    expected = original + b' during' if path == settings else original
                    self.assertEqual(path.read_bytes(), expected, path)
                if previous:
                    self.assertEqual(tree(self.checkout()), before)
                    self.assertEqual(stage.read_bytes(), stage_before)
                    self.assertEqual(lock.read_bytes(), lock_before)
                    self.assertEqual(self.checkout().joinpath('claudex').stat().st_mode & 0o777, 0o755)
                else:
                    self.assertFalse(self.checkout().exists())
                    self.assertTrue((self.data / 'desktop-apps/kilix-needle/kilix-needle').is_file())
                    self.assertFalse((self.data / 'desktop-apps/.kilix-claudex.lock').exists())

    def test_a_parent_created_by_the_install_is_removed_again(self):
        empty = self.home / 'empty data'
        empty.mkdir(mode=0o700)
        result = self.run_rollback(
            'snapshot_kilix_claudex_install\n'
            'install_kilix_claudex\n'
            'false || restore_kilix_claudex_install\n',
            KILIX_DATA_HOME=str(empty))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((empty / 'desktop-apps').exists())
        self.assertFalse((empty / 'desktop-apps/kilix-claudex').exists())

    def test_interruption_removes_partial_outputs_and_keeps_user_state(self):
        apps = self.data / 'desktop-apps'
        self.assertTrue((apps / 'kilix-needle/kilix-needle').is_file())
        result = self.run_rollback(
            'snapshot_kilix_claudex_install\n'
            'set +e\n'
            '( CLAUDEX_TEST_INTERRUPT=1; export CLAUDEX_TEST_INTERRUPT; install_kilix_claudex )\n'
            'status=$?\n'
            'set -e\n'
            '[ "$status" -ne 0 ]\n'
            'restore_kilix_claudex_install\n',
            CLAUDEX_TEST_INTERRUPT='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.checkout().exists())
        self.assertFalse((apps / '.kilix-claudex.lock').exists())
        self.assertFalse((apps / '.kilix-claudex.install-dead').exists())
        self.assertTrue((apps / 'kilix-needle/kilix-needle').is_file())
        self.assertTrue((apps / 'assets/faster-whisper-small-en/model.bin').is_file())
        for path, original in self.decoys.items():
            self.assertEqual(path.read_bytes(), original, path)

    def test_previous_stage_survives_and_a_new_stage_does_not(self):
        self.plant_previous()
        result = self.run_rollback(
            'snapshot_kilix_claudex_install\n'
            'set +e\n'
            '( CLAUDEX_TEST_INTERRUPT=1; export CLAUDEX_TEST_INTERRUPT; install_kilix_claudex )\n'
            'status=$?\n'
            'set -e\n'
            '[ "$status" -ne 0 ]\n'
            'restore_kilix_claudex_install\n',
            CLAUDEX_TEST_INTERRUPT='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        stage = self.data / 'desktop-apps/.kilix-claudex.install-previous/payload'
        self.assertEqual(stage.read_bytes(), b'previous stage\n')
        self.assertFalse((self.data / 'desktop-apps/.kilix-claudex.install-dead').exists())
        self.assertEqual((self.checkout() / 'claudex').read_bytes(),
                         b'#!/bin/sh\nprintf previous-claudex\\n\n')
        self.assertEqual((self.checkout() / '.git/HEAD').read_bytes(), b'previous-head\n')
        self.assertEqual((self.checkout() / '.git/config').read_bytes(), b'previous-origin\n')

    def test_older_snapshot_does_not_remove_an_unrecorded_checkout(self):
        self.plant_previous()
        before = tree(self.checkout())
        result = self.run_rollback('restore_kilix_claudex_install\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(tree(self.checkout()), before)

    def test_unsafe_paths_are_refused_before_any_copy_or_delete(self):
        outside = self.home / 'outside'
        outside.mkdir(mode=0o700)
        sentinel = outside / 'sentinel'
        sentinel.write_bytes(b'keep this')
        cases = []

        linked_home = self.home / 'linked-data'
        linked_home.symlink_to(self.data)
        cases.append(('data symlink', {'KILIX_DATA_HOME': str(linked_home)}))

        cases.append(('relative data', {'KILIX_DATA_HOME': 'kilix data'}))

        writable = self.home / 'writable-data'
        writable.mkdir(mode=0o700)
        writable.chmod(0o777)
        (writable / 'sentinel').write_bytes(b'keep writable')
        cases.append(('group writable', {'KILIX_DATA_HOME': str(writable)}))

        # The parent itself is the unsafe symlink; keep it off the decoy tree.
        linked_apps_home = self.home / 'apps-link-data'
        linked_apps_home.mkdir(mode=0o700)
        linked_apps = linked_apps_home / 'desktop-apps'
        linked_apps.symlink_to(outside)
        cases.append(('parent symlink', {'KILIX_DATA_HOME': str(linked_apps_home)}))

        checkout = self.checkout()
        if checkout.exists():
            subprocess.run(['rm', '-rf', str(checkout)], check=True)
        checkout.symlink_to(outside, target_is_directory=True)
        cases.append(('checkout symlink', {}))

        for label, extra in cases:
            with self.subTest(label=label):
                result = self.run_rollback('snapshot_kilix_claudex_install\n', **extra)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn('refusing unsafe Claudex installation path', result.stderr)
                self.assertEqual(sentinel.read_bytes(), b'keep this')
                self.assertEqual(list(self.txn.glob('kilix-claudex-checkout*')), [])
        self.assertEqual((writable / 'sentinel').read_bytes(), b'keep writable')
        self.assertEqual(list(outside.iterdir()), [sentinel])

    def test_restore_refuses_a_checkout_replaced_by_a_symlink(self):
        outside = self.home / 'restore-outside'
        outside.mkdir(mode=0o700)
        sentinel = outside / 'sentinel'
        sentinel.write_bytes(b'keep on restore')
        result = self.run_rollback('snapshot_kilix_claudex_install\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        checkout = self.checkout()
        self.assertFalse(checkout.exists())
        checkout.symlink_to(outside, target_is_directory=True)
        result = self.run_rollback('restore_kilix_claudex_install\n')
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(sentinel.read_bytes(), b'keep on restore')
        self.assertTrue(checkout.is_symlink())
        self.assertEqual(list(outside.iterdir()), [sentinel])


def tree(path):
    found = {}
    for item in sorted(path.rglob('*')):
        relative = str(item.relative_to(path))
        if item.is_symlink():
            found[relative] = ('symlink', item.readlink())
        elif item.is_file():
            found[relative] = ('file', item.stat().st_mode & 0o777, item.read_bytes())
        else:
            found[relative] = ('dir', item.stat().st_mode & 0o777)
    return found


if __name__ == '__main__':
    unittest.main()
