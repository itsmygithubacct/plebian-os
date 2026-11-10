"""Install and upgrade place the Kilix-pinned kilix-llm and compile nothing.

The qwen-0.8b-no-loop-02 LLM Chat and Kilix Avatar rows run kilix-llm, so the
image installs it after Kilix (which pins its revision): the launcher and the
pinned llama.cpp source. kilix-llm builds its CPU runtime on first use, so a
machine that never uses the model does not pay about 1.5 GB and ten minutes for
it. The model itself is not installed here; it arrives only through the model
wizard.
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


def function(script, name):
    match = re.search(r'^%s\(\) \{\n.*?^\}\n' % re.escape(name), script, re.M | re.S)
    if not match:
        raise AssertionError(f'{name} is not defined')
    return match.group(0)


class KilixLlmInstallTests(unittest.TestCase):
    def fixture(self, home):
        """A Kilix checkout whose installer writes a recording kilix-llm."""
        kilix = Path(home) / 'kilix'
        (kilix / 'scripts').mkdir(parents=True)
        log = Path(home) / 'calls'
        installer = kilix / 'scripts/install-kilix-llm.sh'
        installer.write_text(
            '#!/bin/sh\n'
            f'echo "install $*" >> {log}\n'
            f'mkdir -p {home}/.local/bin\n'
            f'printf \'#!/bin/sh\\necho "kilix-llm $*" >> {log}\\n\' > {home}/.local/bin/kilix-llm\n'
            f'chmod +x {home}/.local/bin/kilix-llm\n')
        installer.chmod(0o755)
        return kilix, log

    def run_provision(self, home, kilix):
        body = function(PROVISION.read_text(), 'install_kilix_llm')
        script = ('set -eu\n'
                  'log() { :; }\n'
                  'die() { echo "die: $*" >&2; exit 3; }\n'
                  'as_user() { "$@"; }\n'
                  'install_env=()\n'
                  f'DRY_RUN=0 KILIX_DIR={kilix} USER_HOME={home} TARGET_USER=desktop\n'
                  + body + 'install_kilix_llm\n')
        return subprocess.run(['bash', '-c', script], capture_output=True, text=True)

    def run_update(self, home, kilix):
        body = function(UPDATE.read_text(), 'install_kilix_llm')
        script = ('set -eu\n'
                  'die() { echo "die: $*" >&2; exit 3; }\n'
                  'stack_env=()\n'
                  f'KILIX_DIR={kilix}\n'
                  + body + 'install_kilix_llm\n')
        return subprocess.run(['bash', '-c', script], capture_output=True, text=True,
                              env=dict(os.environ, HOME=str(home)))

    def test_install_and_upgrade_install_without_building(self):
        for run in (self.run_provision, self.run_update):
            with self.subTest(run.__name__), tempfile.TemporaryDirectory() as home:
                kilix, log = self.fixture(home)
                result = run(home, kilix)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(log.read_text().splitlines(), ['install '])
        for script in (PROVISION, UPDATE):
            with self.subTest(script.name):
                self.assertNotIn('kilix-llm" build', function(script.read_text(), 'install_kilix_llm'))

    def test_a_missing_or_linked_installer_stops_the_install(self):
        for run in (self.run_provision, self.run_update):
            with self.subTest(run.__name__), tempfile.TemporaryDirectory() as home:
                kilix, log = self.fixture(home)
                real = kilix / 'scripts/real-installer.sh'
                (kilix / 'scripts/install-kilix-llm.sh').rename(real)
                os.symlink(real, kilix / 'scripts/install-kilix-llm.sh')
                result = run(home, kilix)
                self.assertEqual(result.returncode, 3)
                self.assertIn('missing or unsafe', result.stderr)
                self.assertFalse(log.exists())

    def test_a_failed_installer_stops_the_install(self):
        for run in (self.run_provision, self.run_update):
            with self.subTest(run.__name__), tempfile.TemporaryDirectory() as home:
                kilix, log = self.fixture(home)
                installer = kilix / 'scripts/install-kilix-llm.sh'
                installer.write_text(installer.read_text() + 'exit 1\n')
                result = run(home, kilix)
                self.assertEqual(result.returncode, 3)
                self.assertIn('kilix-llm installation failed', result.stderr)

    def test_dry_run_installs_nothing(self):
        body = function(PROVISION.read_text(), 'install_kilix_llm')
        result = subprocess.run(['bash', '-c', 'set -eu\nlog() { echo "$*"; }\n'
                                 'DRY_RUN=1 TARGET_USER=desktop\n' + body + 'install_kilix_llm\n'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('would install the Kilix-pinned kilix-llm (source only', result.stdout)

    def test_it_runs_after_kilix_and_needle_and_before_the_models(self):
        provision, update = PROVISION.read_text(), UPDATE.read_text()
        main = provision[provision.index('"$PLEB_DIR/bin/pleb" install \\\n'):]
        self.assertLess(main.index('install_kilix_needle\n'), main.index('install_kilix_llm\n'))
        self.assertLess(main.index('install_kilix_llm\n'), main.index('stage-command-model.py'))
        self.assertLess(update.index('    install_kilix_needle\n'), update.index('    install_kilix_llm\n'))
        self.assertLess(update.index('    install_kilix_llm\n'), update.index('stage-command-model.py'))
        self.assertIn('    install_kilix_llm\n    test_fail_after_boundary kilix-llm\n', update)


if __name__ == '__main__':
    unittest.main()
