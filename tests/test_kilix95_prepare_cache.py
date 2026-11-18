"""Install and update prepare Kilix 95's caches for the desktop user.

Kilix 95 keeps its own and the Kilix SDK's bytecode in a private cache, so
without this step the first desktop start after an install or an update
compiles them (and each application its own on first open); the same step
finishes the start-up Neuronte letter caches. Provisioning runs
`main.py --prepare-cache` once, as the desktop user, after the last step that
installs desktop sources (Neuronte included). The updater runs it once, after
the stack transaction has committed. Both pass KILIX_HOME as the kilix launcher computes it (the
directory of the resolved launcher), so the SDK paths in the cache are the
ones the desktop imports. Any failure is only a warning: the desktop compiles
whatever is missing, as it always has.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROVISION = ROOT / 'provision' / 'plebian-os-provision.sh'
UPDATE = ROOT / 'provision' / 'plebian-os-update.sh'
FIRSTBOOT = ROOT / 'provision' / 'plebian-os-firstboot.service'

# A stand-in for Kilix 95's main.py: records its argv and the variables the
# real one resolves its paths from, then exits with STUB_RC (or sleeps).
FAKE_MAIN = '''import json, os, sys, time
keys = ("KILIX_HOME", "GPU_TERMINAL_HOME", "PLEB_MARK", "STUB_RC")
open(%r, "a").write(json.dumps({"argv": sys.argv[1:], "uid": os.geteuid(),
    "env": {k: os.environ.get(k) for k in keys}}) + "\\n")
if os.environ.get("STUB_SLEEP"):
    time.sleep(float(os.environ["STUB_SLEEP"]))
sys.exit(int(os.environ.get("STUB_RC", "0")))
'''


def function_body(text, name):
    start = text.index(name + '() {')
    return text[start:text.index('\n}\n', start)]


@unittest.skipUnless(shutil.which('bash'), 'needs bash')
class PrepareCacheStepTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(os.path.realpath(self._tmp.name))
        self.calls = self.base / 'calls'
        self.k95 = self.base / 'sources' / 'kilix-desktops' / 'kilix-95'
        self.k95.mkdir(parents=True)
        (self.k95 / 'main.py').write_text(FAKE_MAIN % str(self.calls))
        # The installed launcher is reached through a symlinked KILIX_DIR, as a
        # relocated checkout would be; the launcher itself resolves it.
        self.real_kilix = self.base / 'real' / 'kilix'
        self.real_kilix.mkdir(parents=True)
        (self.real_kilix / 'kilix').write_text('#!/bin/sh\n')
        (self.base / 'sources' / 'kilix').symlink_to(self.real_kilix)

    def tearDown(self):
        self._tmp.cleanup()

    def env(self, **extra):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(('PLEBIAN_OS_', 'NEURONTE_', 'KILIX', 'PLEB_',
                                    'GPU_TERMINAL', 'STUB_', 'PYTHON'))}
        env.update(HOME=str(self.base / 'home'), **extra)
        return env

    def common(self):
        return (f'KILIX_DIR={str(self.base / "sources" / "kilix")!r}\n'
                f'KILIX95_DIR={str(self.k95)!r}\n')

    def provision(self, body, **extra):
        script = (f'. "{PROVISION}"\n'
                  'as_user() { echo AS_USER >&2; "$@"; }\n'
                  'install_env=("GPU_TERMINAL_HOME=/srv/gpu" "PLEB_MARK=install")\n'
                  'TARGET_USER=desk\nDRY_RUN=0\nPLEB_INSTALL_KILIX95=1\n'
                  + self.common() + body)
        return subprocess.run(['bash', '-c', script], capture_output=True, text=True,
                              env=self.env(PLEBIAN_OS_PROVISION_LIB_ONLY='1', **extra),
                              timeout=120)

    def update(self, body, **extra):
        script = ('set -euo pipefail\nexport PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1\n'
                  f'PLEB_STATE_HOME={str(self.base / "state")!r}\n'
                  f'source "{UPDATE}"\n'
                  'stack_env=("GPU_TERMINAL_HOME=/srv/gpu" "PLEB_MARK=stack")\n'
                  + self.common() + body)
        return subprocess.run(['bash', '-c', script], capture_output=True, text=True,
                              env=self.env(**extra), timeout=120)

    def recorded(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()] \
            if self.calls.exists() else []

    def run_step(self, which, body='', **extra):
        if which == 'provision':
            return self.provision(body + 'prepare_kilix95_caches\necho done\n', **extra)
        return self.update(body + 'prepare_kilix95_caches_update\necho done\n', **extra)

    def test_runs_main_prepare_cache_as_the_desktop_user_with_the_launchers_kilix_home(self):
        for which, mark in (('provision', 'install'), ('update', 'stack')):
            with self.subTest(which=which):
                self.calls.unlink(missing_ok=True)
                result = self.run_step(which)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('done', result.stdout)
                self.assertIn('preparing Kilix 95 bytecode and font caches', result.stdout)
                call, = self.recorded()
                self.assertEqual(call['argv'], ['--prepare-cache'])
                self.assertEqual(call['env']['KILIX_HOME'], str(self.real_kilix))
                self.assertEqual(call['env']['GPU_TERMINAL_HOME'], '/srv/gpu')
                self.assertEqual(call['env']['PLEB_MARK'], mark)
                self.assertEqual(call['uid'], os.geteuid())
                if which == 'provision':
                    self.assertIn('AS_USER', result.stderr)

    def test_a_failure_or_a_hang_only_warns(self):
        for which in ('provision', 'update'):
            with self.subTest(which=which, case='exit 1'):
                result = self.run_step(which, STUB_RC='1')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('done', result.stdout)
                self.assertIn('Kilix 95 cache preparation did not complete', result.stderr)
            with self.subTest(which=which, case='timeout'):
                result = self.run_step(which, 'KILIX95_PREPARE_CACHE_TIMEOUT=1s\n',
                                       STUB_SLEEP='30')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('done', result.stdout)
                self.assertIn('did not complete', result.stderr)

    def test_a_missing_checkout_or_launcher_skips_without_failing(self):
        (self.k95 / 'main.py').unlink()
        for which in ('provision', 'update'):
            with self.subTest(which=which, case='no main.py'):
                result = self.run_step(which)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('done', result.stdout)
        self.assertIn('main.py is missing', self.run_step('provision').stderr)
        (self.k95 / 'main.py').symlink_to(self.base / 'elsewhere.py')
        (self.base / 'elsewhere.py').write_text(FAKE_MAIN % str(self.calls))
        self.assertIn('main.py is missing', self.run_step('provision').stderr)
        (self.k95 / 'main.py').unlink()
        (self.k95 / 'main.py').write_text(FAKE_MAIN % str(self.calls))
        (self.real_kilix / 'kilix').unlink()
        for which in ('provision', 'update'):
            with self.subTest(which=which, case='no launcher'):
                result = self.run_step(which)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('no kilix launcher', result.stderr)
        self.assertEqual(self.recorded(), [])

    def test_provision_skips_without_kilix_95_and_logs_a_dry_run(self):
        result = self.provision('PLEB_INSTALL_KILIX95=0\nprepare_kilix95_caches\necho done\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('Kilix 95', result.stdout + result.stderr)
        result = self.provision('DRY_RUN=1\nprepare_kilix95_caches\necho done\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('would prepare Kilix 95 bytecode and font caches for desk', result.stdout)
        self.assertEqual(self.recorded(), [])

    def test_the_step_never_fails_an_install_or_an_update(self):
        for path, name in ((PROVISION, 'prepare_kilix95_caches'),
                           (UPDATE, 'prepare_kilix95_caches_update')):
            with self.subTest(name=name):
                body = function_body(path.read_text(), name)
                self.assertNotIn('die ', body)
                self.assertTrue(body.rstrip().endswith('return 0'), body[-200:])


class PrepareCachePlacementTests(unittest.TestCase):

    def test_provision_runs_it_after_the_last_step_that_installs_desktop_sources(self):
        text = PROVISION.read_text()
        self.assertIn('build_kilix_fork\nseed_selected_desktop_wallpaper_state\n'
                      'record_default_desktop\nprepare_kilix95_caches\n', text)
        main = text.index('\nprepare_kilix95_caches\n')
        for step in ('"$PLEB_DIR/bin/pleb" install', '\ninstall_neuronte\n',
                     '\nbuild_kilix_fork\n'):
            self.assertLess(text.index(step), main, step)

    def test_each_runs_it_once(self):
        for path in (PROVISION, UPDATE):
            with self.subTest(path=path.name):
                calls = [line for line in path.read_text().splitlines()
                         if '--prepare-cache' in line and not line.lstrip().startswith('#')]
                self.assertEqual(len(calls), 1, calls)

    def test_update_runs_it_after_the_commit_and_before_a_restart(self):
        text = UPDATE.read_text()
        call = text.index('\nprepare_kilix95_caches_update\n')
        self.assertLess(text.index('\ncommit_stack_transaction\n'), call)
        self.assertLess(call, text.index('\nrestart_session_after_commit\n'))

    def test_first_boot_holds_the_greeter_until_provisioning_is_done(self):
        unit = FIRSTBOOT.read_text()
        self.assertIn('Before=display-manager.service', unit)
        self.assertIn('ExecStart=/usr/local/sbin/plebian-os-firstboot-attempt run '
                      '/usr/local/sbin/plebian-os-provision', unit)


if __name__ == '__main__':
    unittest.main()
