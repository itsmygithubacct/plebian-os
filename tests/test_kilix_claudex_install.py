"""Fresh install and upgrade install the catalog-pinned Claudex application.

Claudex does not auto-install, and the Zell runtime does not carry it. Both
paths call the Kilix app installer for the catalog id. This does not log in,
answer a trust prompt, or move the Kilix or voice-carrier pins.
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
LAUNCHER_KILIX_REF = 'abf4c136b95d26b79acc10733ba8a3a192223c1f'
LAUNCHER_KILIX95_REF = '3469b0f27cbbce4725952808d03ba7892edcd85d'
LAUNCHER_VOICE_CONTENT = 'db463a7b32acac83d28b9ab8a1dce183e14931b2'


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

    def test_launcher_kilix_and_voice_pins_stay(self):
        found = pins(ENV.read_text())
        self.assertEqual(found['KILIX_REF'], LAUNCHER_KILIX_REF)
        self.assertEqual(found['KILIX95_REF'], LAUNCHER_KILIX95_REF)
        self.assertEqual(found['PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF'], LAUNCHER_VOICE_CONTENT)


if __name__ == '__main__':
    unittest.main()
