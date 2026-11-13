"""Fresh install and upgrade install the catalog-pinned Claudex application.

Claudex does not auto-install, and the Zell runtime does not carry it. Both
paths call the Kilix app installer for the catalog id. This does not log in,
answer a trust prompt, or move the Kilix or voice-carrier pins.

Rollback covers the owned checkout only. The entrypoint and git bookkeeping
live inside that checkout; user config, browser state, credentials, and usage
state stay out of the snapshot.
"""
import fcntl
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROVISION = ROOT / 'provision/plebian-os-provision.sh'
UPDATE = ROOT / 'provision/plebian-os-update.sh'
ENV = ROOT / 'releases/0.2.3.env'
PIN_KEYS = ('KILIX_REF', 'KILIX95_REF', 'PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF')
# Deterministic alternate pin file, inlined from the RC9 assembler pins.
# A temporary fixture carries it, including when the release file has the same values.
ALTERNATE_ENV = """\
KILIX_REF=3b953489a436b88d3e464192a5203fc0bbad376e
KILIX95_REF=1e59c1e28d856a7cd0a9e61b431245ab68a2275b
PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF=e78e1cb51c580569680d496ed95bbb6a4c6484ab
"""
ROLLBACK_FUNCTIONS = (
    'kilix_claudex_refuse',
    'kilix_claudex_require_user_dir',
    'kilix_claudex_install_paths_are_safe',
    'snapshot_stack_path',
    'restore_stack_path',
    'kilix_claudex_guard_unlink_created',
    'kilix_claudex_guard_kill',
    'kilix_claudex_guard_finish',
    'kilix_claudex_guard_helper',
    'kilix_claudex_guard_run',
    'kilix_claudex_snapshot_locked',
    'kilix_claudex_restore_locked',
    'snapshot_kilix_claudex_install',
    'restore_kilix_claudex_install',
    'install_kilix_claudex',
)
_HOLDER = r"""
import fcntl
import os
import sys
import time

root, stage_name, ready, release = sys.argv[1:5]
lock = os.path.join(root, ".kilix-claudex.lock")
os.makedirs(root, mode=0o700, exist_ok=True)
fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
os.fchmod(fd, 0o600)
fcntl.flock(fd, fcntl.LOCK_EX)
stage = os.path.join(root, stage_name)
os.mkdir(stage, 0o700)
os.chmod(stage, 0o700)
with open(os.path.join(stage, "payload"), "wb") as handle:
    handle.write(b"live-stage\n")
probe = os.open(lock, os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW)
try:
    fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    blocked = True
else:
    blocked = False
os.close(probe)
if not blocked:
    sys.stderr.write("holder probe acquired\n")
    raise SystemExit(1)
ident = os.fstat(fd)
with open(ready + ".tmp", "w", encoding="ascii") as handle:
    handle.write("%s %s\n" % (ident.st_dev, ident.st_ino))
os.replace(ready + ".tmp", ready)
while not os.path.exists(release):
    time.sleep(0.02)
os.close(fd)
"""


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

    def assert_install_leaves_pins(self, source_bytes, label):
        """Run both installers against one pin file and leave that file unchanged."""
        found = pins(source_bytes.decode())
        self.assertEqual(set(found), set(PIN_KEYS), label)
        for value in found.values():
            self.assertRegex(value, r'^[0-9a-f]{40}$', label)
        update = UPDATE.read_text()
        for origin, script_text in (('provision', PROVISION.read_text()), ('update', update)):
            body = function(script_text, 'install_kilix_claudex')
            for key in PIN_KEYS:
                self.assertNotIn(key, body, origin)
        with tempfile.TemporaryDirectory() as home:
            home = Path(home)
            copy = home / 'pins.env'
            copy.write_bytes(source_bytes)
            kilix, _log = self.fixture(home)
            for origin, script_text in (('provision', PROVISION.read_text()), ('update', update)):
                body = function(script_text, 'install_kilix_claudex')
                if origin == 'provision':
                    prelude = (
                        'log() { :; }\n'
                        'as_user() { "$@"; }\n'
                        'install_env=()\n'
                        'DRY_RUN=0 TARGET_USER=desktop\n')
                else:
                    prelude = 'stack_env=()\n'
                script = (
                    'set -eu\n'
                    'die() { echo "die: $*" >&2; exit 3; }\n'
                    + prelude +
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
                self.assertEqual(result.returncode, 0, f'{label} {origin}: {result.stderr}')
            self.assertEqual(copy.read_bytes(), source_bytes, label)

    def test_install_leaves_release_pins_unchanged(self):
        release = ENV.read_bytes()
        cases = (
            ('release', release),
            ('alternate', ALTERNATE_ENV.encode()),
            ('identical', release),
        )
        for label, source_bytes in cases:
            with self.subTest(label=label):
                self.assert_install_leaves_pins(source_bytes, label)
        self.assertEqual(ENV.read_bytes(), release)

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
        self.assertNotIn('kilix_claudex_guard_run', function(update, 'install_kilix_claudex'))
        self.assertNotIn('kilix-claudex-lock', function(update, 'kilix_claudex_snapshot_locked'))
        self.assertNotIn('kilix-claudex-lock', function(update, 'kilix_claudex_restore_locked'))
        self.assertIn('\n    trap stack_transaction_cleanup EXIT\n', begin)
        self.assertIn("\n    trap 'exit 130' INT\n", begin)
        self.assertIn("\n    trap 'exit 143' TERM\n", begin)
        self.assertIn("\n    trap 'exit 129' HUP\n", begin)
        self.assertIn("\n    trap 'exit 141' PIPE\n", begin)
        guard = function(update, 'kilix_claudex_guard_run')
        self.assertNotIn('stack_transaction_cleanup', guard)
        self.assertIn("trap 'kilix_claudex_guard_finish || true' EXIT", guard)
        self.assertIn('kilix_claudex_guard_helper ', guard)
        self.assertNotIn('import fcntl', guard)
        helper = function(update, 'kilix_claudex_guard_helper')
        self.assertIn('close_inherited_descriptors', helper)
        self.assertIn('trap - EXIT INT TERM HUP PIPE', helper)


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

    def rollback_script(self, script):
        update = UPDATE.read_text()
        body = ''.join(function(update, name) for name in ROLLBACK_FUNCTIONS)
        return (
            'set -euo pipefail\n'
            'die() { printf "die: %s\\n" "$*" >&2; exit 1; }\n'
            'stack_env=("KILIX_DATA_HOME=$KILIX_DATA_HOME")\n'
            '_STACK_TXN_DIR="$TXN"\n'
            'umask 077\n'
            + body + script)

    def rollback_env(self, **extra):
        env = {
            'PATH': '/usr/bin:/bin',
            'HOME': str(self.home),
            'KILIX_DATA_HOME': str(self.data),
            'KILIX_DIR': str(self.kilix),
            'TXN': str(self.txn),
            'CLAUDEX_TEST_LOG': str(self.log),
        }
        env.update(extra)
        return env

    def run_rollback(self, script, timeout=30, **extra):
        return subprocess.run(
            ['bash', '-c', self.rollback_script(script)],
            env=self.rollback_env(**extra),
            capture_output=True, text=True, timeout=timeout)

    def reap_group(self, proc):
        """Stop one private session started with start_new_session.

        Signals only that process group. It does not search by command name.
        """
        if proc is None or proc.pid is None or proc.pid <= 1:
            return
        if proc.poll() is None:
            try:
                os.kill(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        for stream in (proc.stdout, proc.stderr):
            if stream is not None and not stream.closed:
                stream.close()

    def run_contained(self, script, timeout=30, **extra):
        proc = subprocess.Popen(
            ['bash', '-c', self.rollback_script(script)],
            env=self.rollback_env(**extra),
            start_new_session=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True)
        self.addCleanup(self.reap_group, proc)
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.reap_group(proc)
            raise
        return subprocess.CompletedProcess(proc.args, proc.returncode, stdout, stderr)

    def assert_reaped(self, pid):
        self.assertGreater(pid, 1)
        self.assertFalse(Path(f'/proc/{pid}').exists(), f'pid {pid} still present')

    def assert_lock_not_held(self, path):
        if path.is_symlink() or not path.exists():
            return
        fd = os.open(path, os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                self.fail(f'lock still held: {path}')
            else:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

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
                    lock_identity = (lock.stat().st_dev, lock.stat().st_ino)
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
                self.assertEqual(list(self.txn.glob('kilix-claudex-lock*')), [])
                if previous:
                    self.assertEqual(tree(self.checkout()), before)
                    self.assertEqual(stage.read_bytes(), stage_before)
                    self.assertEqual(lock.read_bytes(), lock_before)
                    self.assertEqual((lock.stat().st_dev, lock.stat().st_ino), lock_identity)
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
        self.assertFalse((self.txn / 'kilix-claudex-parent.present').exists())
        self.assertTrue((self.txn / 'kilix-claudex-managed').is_file())

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
        # The interrupted installer left an inactive mutex. It is not payload.
        self.assertEqual((apps / '.kilix-claudex.lock').read_bytes(), b'lock')
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
        lock = self.data / 'desktop-apps/.kilix-claudex.lock'
        lock_before = lock.read_bytes()
        lock_identity = (lock.stat().st_dev, lock.stat().st_ino)
        stage = self.data / 'desktop-apps/.kilix-claudex.install-previous/payload'
        stage_before = stage.read_bytes()
        result = self.run_rollback('restore_kilix_claudex_install\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(tree(self.checkout()), before)
        self.assertEqual(lock.read_bytes(), lock_before)
        self.assertEqual((lock.stat().st_dev, lock.stat().st_ino), lock_identity)
        self.assertEqual(stage.read_bytes(), stage_before)

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

    def test_absent_lock_is_not_snapshot_payload(self):
        lock = self.data / 'desktop-apps/.kilix-claudex.lock'
        needle = self.data / 'desktop-apps/kilix-needle/kilix-needle'
        needle_before = needle.read_bytes()
        self.assertFalse(lock.exists())
        result = self.run_rollback('snapshot_kilix_claudex_install\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(lock.exists())
        self.assertEqual(list(self.txn.glob('kilix-claudex-lock*')), [])
        self.assertTrue((self.txn / 'kilix-claudex-parent.present').is_file())
        self.assertTrue((self.txn / 'kilix-claudex-managed').is_file())
        self.assertEqual(needle.read_bytes(), needle_before)

    def start_holder(self, root, stage_name):
        ready = self.home / ('ready-' + stage_name)
        release = self.home / ('release-' + stage_name)
        proc = subprocess.Popen(
            ['/usr/bin/python3', '-I', '-B', '-c', _HOLDER,
             str(root), stage_name, str(ready), str(release)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.stop_holder, proc, release)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if ready.exists():
                return proc, ready, release
            if proc.poll() is not None:
                raise AssertionError(proc.stderr.read())
            time.sleep(0.02)
        proc.kill()
        raise AssertionError('holder did not lock')

    def stop_holder(self, proc, release):
        if proc.poll() is None:
            release.write_text('go\n')
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        for stream in (proc.stdout, proc.stderr):
            if stream is not None and not stream.closed:
                stream.close()

    def assert_exclusive_lock_blocked(self, path):
        fd = os.open(path, os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW)
        acquired = False
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return
            acquired = True
        finally:
            os.close(fd)
        if acquired:
            self.fail('second exclusive lock acquired')

    def test_snapshot_refuses_a_held_installer_lock(self):
        apps = self.data / 'desktop-apps'
        app = self.checkout()
        app.mkdir(mode=0o700)
        app.chmod(0o700)
        (app / 'claudex').write_bytes(b'live-app\n')
        needle = apps / 'kilix-needle/kilix-needle'
        needle_before = needle.read_bytes()
        proc, ready, release = self.start_holder(apps, '.kilix-claudex.install-active')
        dev, ino = ready.read_text().split()
        lock = apps / '.kilix-claudex.lock'
        stage = apps / '.kilix-claudex.install-active/payload'
        identity = (lock.stat().st_dev, lock.stat().st_ino)
        self.assertEqual(identity, (int(dev), int(ino)))
        started = time.monotonic()
        result = self.run_rollback('snapshot_kilix_claudex_install\n', timeout=12)
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 8, result.stderr)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('Claudex install lock is held', result.stderr)
        self.assertEqual((lock.stat().st_dev, lock.stat().st_ino), identity)
        self.assertEqual(stage.read_bytes(), b'live-stage\n')
        self.assertEqual((app / 'claudex').read_bytes(), b'live-app\n')
        self.assertEqual(needle.read_bytes(), needle_before)
        self.assertFalse((self.txn / 'kilix-claudex-managed').exists())
        self.assert_exclusive_lock_blocked(lock)
        self.stop_holder(proc, release)
        result = self.run_rollback(
            'snapshot_kilix_claudex_install\n'
            'lock="$KILIX_DATA_HOME/desktop-apps/.kilix-claudex.lock"\n'
            '/usr/bin/python3 -I -B - "$lock" <<\'PY\'\n'
            'import fcntl, os, sys\n'
            'path = sys.argv[1]\n'
            'if not os.path.lexists(path):\n'
            '    raise SystemExit(0)\n'
            'fd = os.open(path, os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW)\n'
            'try:\n'
            '    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)\n'
            'except BlockingIOError:\n'
            '    raise SystemExit(2)\n'
            'finally:\n'
            '    os.close(fd)\n'
            'PY\n'
            'install_kilix_claudex\n'
            'false || restore_kilix_claudex_install\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.log.read_text().splitlines()[-2:],
                         ['1', 'app install kilix-claudex'])
        self.assertEqual((app / 'claudex').read_bytes(), b'live-app\n')
        self.assertEqual(stage.read_bytes(), b'live-stage\n')
        self.assertEqual((lock.stat().st_dev, lock.stat().st_ino), identity)
        self.assertEqual(needle.read_bytes(), needle_before)

    def test_restore_refuses_a_held_installer_lock(self):
        apps = self.data / 'desktop-apps'
        needle = apps / 'kilix-needle/kilix-needle'
        needle_before = needle.read_bytes()
        result = self.run_rollback('snapshot_kilix_claudex_install\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        proc, ready, release = self.start_holder(apps, '.kilix-claudex.install-active')
        dev, ino = ready.read_text().split()
        lock = apps / '.kilix-claudex.lock'
        stage = apps / '.kilix-claudex.install-active/payload'
        identity = (lock.stat().st_dev, lock.stat().st_ino)
        self.assertEqual(identity, (int(dev), int(ino)))
        app = self.checkout()
        app.mkdir(mode=0o700)
        app.chmod(0o700)
        (app / 'claudex').write_bytes(b'during-install\n')
        started = time.monotonic()
        result = self.run_rollback('restore_kilix_claudex_install\n', timeout=12)
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 8, result.stderr)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('Claudex install lock is held', result.stderr)
        self.assertEqual((lock.stat().st_dev, lock.stat().st_ino), identity)
        self.assertEqual(stage.read_bytes(), b'live-stage\n')
        self.assertEqual((app / 'claudex').read_bytes(), b'during-install\n')
        self.assertEqual(needle.read_bytes(), needle_before)
        self.assert_exclusive_lock_blocked(lock)
        self.stop_holder(proc, release)
        result = self.run_rollback('restore_kilix_claudex_install\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(stage.parent.exists())
        self.assertFalse(app.exists())
        self.assertEqual(needle.read_bytes(), needle_before)
        self.assertEqual((lock.stat().st_dev, lock.stat().st_ino), identity)

    def test_callback_exit_reaps_the_guardian(self):
        pidfile = self.home / 'guard-pid'
        lock = self.data / 'desktop-apps/.kilix-claudex.lock'
        self.assertFalse(lock.exists())
        started = time.monotonic()
        result = self.run_contained(
            'trap \'printf outer-exit\\n\' EXIT\n'
            'trap \'printf outer-int\\n\' INT\n'
            'trap \'printf outer-pipe\\n\' PIPE\n'
            'before_exit="$(trap -p EXIT)"\n'
            'before_int="$(trap -p INT)"\n'
            'before_pipe="$(trap -p PIPE)"\n'
            'snapshot_stack_path() {\n'
            '  printf "%s\\n" "$_KILIX_CLAUDEX_GUARD_PID" >> "$GUARD_PID"\n'
            '  exit 23\n'
            '}\n'
            'status=0\n'
            'kilix_claudex_guard_run snapshot || status=$?\n'
            '[ "$status" -eq 23 ]\n'
            '[ "$(trap -p EXIT)" = "$before_exit" ]\n'
            '[ "$(trap -p INT)" = "$before_int" ]\n'
            '[ "$(trap -p PIPE)" = "$before_pipe" ]\n'
            'kilix_claudex_restore_locked() {\n'
            '  printf "%s\\n" "$_KILIX_CLAUDEX_GUARD_PID" >> "$GUARD_PID"\n'
            '  exit 23\n'
            '}\n'
            'status=0\n'
            'kilix_claudex_guard_run restore || status=$?\n'
            '[ "$status" -eq 23 ]\n'
            '[ "$(trap -p EXIT)" = "$before_exit" ]\n'
            '[ "$(trap -p INT)" = "$before_int" ]\n'
            '[ "$(trap -p PIPE)" = "$before_pipe" ]\n',
            timeout=12,
            GUARD_PID=str(pidfile))
        self.assertLess(time.monotonic() - started, 8, result.stderr)
        self.assertEqual(result.returncode, 0, result.stderr)
        pids = [int(line) for line in pidfile.read_text().split()]
        self.assertEqual(len(pids), 2, pidfile.read_text())
        for pid in pids:
            self.assert_reaped(pid)
        self.assertFalse(lock.exists())
        self.assert_lock_not_held(lock)

    def test_callback_exit_preserves_an_inactive_lock(self):
        pidfile = self.home / 'guard-pid'
        lock = self.data / 'desktop-apps/.kilix-claudex.lock'
        lock.write_bytes(b'previous lock\n')
        lock.chmod(0o600)
        identity = (lock.stat().st_dev, lock.stat().st_ino)
        result = self.run_contained(
            'snapshot_stack_path() {\n'
            '  printf "%s\\n" "$_KILIX_CLAUDEX_GUARD_PID" > "$GUARD_PID"\n'
            '  exit 23\n'
            '}\n'
            'status=0\n'
            'kilix_claudex_guard_run snapshot || status=$?\n'
            '[ "$status" -eq 23 ]\n',
            timeout=12,
            GUARD_PID=str(pidfile))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_reaped(int(pidfile.read_text().strip()))
        self.assertEqual(lock.read_bytes(), b'previous lock\n')
        self.assertEqual((lock.stat().st_dev, lock.stat().st_ino), identity)
        self.assert_lock_not_held(lock)

    def test_snapshot_failure_reaps_before_the_outer_die(self):
        pidfile = self.home / 'guard-pid'
        lock = self.data / 'desktop-apps/.kilix-claudex.lock'
        result = self.run_contained(
            'snapshot_stack_path() {\n'
            '  printf "%s\\n" "$_KILIX_CLAUDEX_GUARD_PID" > "$GUARD_PID"\n'
            '  exit 23\n'
            '}\n'
            'snapshot_kilix_claudex_install\n',
            timeout=12,
            GUARD_PID=str(pidfile))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('die: could not snapshot the Claudex installation', result.stderr)
        self.assert_reaped(int(pidfile.read_text().strip()))
        self.assertFalse(lock.exists())
        self.assert_lock_not_held(lock)

    def test_parent_kill_reaps_the_guardian(self):
        ready = self.home / 'guard-ready'
        block = self.home / 'guard-block'
        os.mkfifo(block, 0o600)
        lock = self.data / 'desktop-apps/.kilix-claudex.lock'
        script = (
            'exec 7<>"$GUARD_BLOCK"\n'
            'snapshot_stack_path() {\n'
            '  printf "%s %s\\n" "$_KILIX_CLAUDEX_GUARD_PID" "$BASHPID" > "$GUARD_READY"\n'
            '  while true; do\n'
            '    read -r -t 30 _pause <&7 || true\n'
            '  done\n'
            '}\n'
            'kilix_claudex_guard_run snapshot\n')
        proc = subprocess.Popen(
            ['bash', '-c', self.rollback_script(script)],
            env=self.rollback_env(GUARD_READY=str(ready), GUARD_BLOCK=str(block)),
            start_new_session=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True)
        self.addCleanup(self.reap_group, proc)
        deadline = time.monotonic() + 5
        fields = None
        while time.monotonic() < deadline:
            if ready.exists() and ready.stat().st_size > 0:
                parts = ready.read_text().split()
                if len(parts) == 2:
                    fields = parts
                    break
            if proc.poll() is not None:
                err = proc.stderr.read() if proc.stderr is not None else ''
                self.fail(f'guard exited early: {err}')
            time.sleep(0.02)
        self.assertIsNotNone(fields, 'guardian did not become ready')
        guard_pid = int(fields[0])
        shell_pid = int(fields[1])
        self.assertNotEqual(shell_pid, proc.pid)
        self.assertNotEqual(guard_pid, proc.pid)
        self.assertTrue(Path(f'/proc/{guard_pid}').exists())
        os.kill(proc.pid, signal.SIGKILL)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            guard_gone = not Path(f'/proc/{guard_pid}').exists()
            shell_gone = not Path(f'/proc/{shell_pid}').exists()
            if guard_gone and shell_gone:
                break
            time.sleep(0.05)
        self.assert_reaped(guard_pid)
        self.assert_reaped(shell_pid)
        self.assert_lock_not_held(lock)
        self.assertFalse(lock.exists())

    def test_startup_timeout_reaps_the_helper(self):
        pidfile = self.home / 'guard-pid'
        lock = self.data / 'desktop-apps/.kilix-claudex.lock'
        started = time.monotonic()
        result = self.run_contained(
            'kilix_claudex_guard_helper() {\n'
            '  trap - EXIT INT TERM HUP PIPE\n'
            '  printf "%s\\n" "$BASHPID" > "$GUARD_PID"\n'
            '  exec sleep 30\n'
            '}\n'
            'status=0\n'
            'kilix_claudex_guard_run snapshot || status=$?\n'
            '[ "$status" -ne 0 ]\n',
            timeout=12,
            GUARD_PID=str(pidfile))
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 10, result.stderr)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('could not lock the Claudex installation', result.stderr)
        self.assert_reaped(int(pidfile.read_text().strip()))
        self.assert_lock_not_held(lock)

    def test_startup_exit_reaps_the_helper(self):
        pidfile = self.home / 'guard-pid'
        lock = self.data / 'desktop-apps/.kilix-claudex.lock'
        started = time.monotonic()
        result = self.run_contained(
            'kilix_claudex_guard_helper() {\n'
            '  trap - EXIT INT TERM HUP PIPE\n'
            '  printf "%s\\n" "$BASHPID" > "$GUARD_PID"\n'
            '  exit 9\n'
            '}\n'
            'status=0\n'
            'kilix_claudex_guard_run snapshot || status=$?\n'
            '[ "$status" -ne 0 ]\n',
            timeout=12,
            GUARD_PID=str(pidfile))
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 10, result.stderr)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('could not lock the Claudex installation', result.stderr)
        self.assert_reaped(int(pidfile.read_text().strip()))
        self.assert_lock_not_held(lock)


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
