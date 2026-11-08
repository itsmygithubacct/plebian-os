"""Optional Waydroid provenance and first-use helper rollback, without root."""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_lid_update import Fixture, as_user, scripts, under

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = (ROOT / 'provision/plebian-os-provision.sh',
           ROOT / 'provision/plebian-os-update.sh')
ARCHIVE = 'usr/local/share/kilix-waydroid/source.tar'
HELPER_ROOT = 'usr/lib/plebian-os/waydroid'
HELPERS = ('plebian-os-waydroid-setup', 'waydroid-closure.env',
           'waydroid-closure.sha256')


class OptionalProvenance(unittest.TestCase):
    def run_provenance(self, source, root, *, hash_failure=False):
        text = source.read_text()
        start = text.index('        if [ -e /usr/local/share/kilix-waydroid/source.tar ]')
        end = text.index('\n        fi', start) + len('\n        fi')
        fragment = under(text[start:end], root)
        shell = ('set -euo pipefail\n'
                 'die() { echo "$*" >&2; exit 1; }\n'
                 'provenance_kv() { printf "%s=%s\\n" "$1" "$2"; }\n')
        if hash_failure:
            shell += 'sha256sum() { return 74; }\n'
        shell += 'record() {\n' + fragment + '\n}\nrecord\n'
        return subprocess.run(['bash', '-c', shell], text=True, capture_output=True,
                              env={'PATH': '/usr/bin:/bin', 'HOME': str(root)}, timeout=10)

    def test_absent_optional_archive_emits_no_false_provenance_or_warning(self):
        with tempfile.TemporaryDirectory() as temporary:
            for source in SCRIPTS:
                with self.subTest(source=source.name):
                    result = self.run_provenance(source, Path(temporary))
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual((result.stdout, result.stderr), ('', ''))

    def test_existing_archive_is_hashed_and_hash_failures_abort(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / ARCHIVE
            archive.parent.mkdir(parents=True)
            archive.write_bytes(b'retained legacy source archive')
            expected = hashlib.sha256(archive.read_bytes()).hexdigest()
            for source in SCRIPTS:
                with self.subTest(source=source.name):
                    result = self.run_provenance(source, root)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn('KILIX_WAYDROID_SOURCE_SHA256=' + expected, result.stdout)
                    failed = self.run_provenance(source, root, hash_failure=True)
                    self.assertNotEqual(failed.returncode, 0)
                    self.assertNotIn('KILIX_WAYDROID_SOURCE_SHA256=', failed.stdout)

    def test_linked_archive_is_not_followed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / ARCHIVE
            archive.parent.mkdir(parents=True)
            archive.symlink_to(root / 'absent')
            for source in SCRIPTS:
                with self.subTest(source=source.name):
                    result = self.run_provenance(source, root)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('unsafe installed Waydroid source archive', result.stderr)

    def test_fresh_install_does_not_call_the_legacy_app_installer(self):
        source = SCRIPTS[0].read_text()
        main = source[source.index('\nensure_plebian_os_checkout\n'):]
        self.assertNotIn('\ninstall_waydroid_application\n', main)
        self.assertIn('WAYDROID_INSTALL_DIR=/usr/lib/plebian-os/waydroid', main)


class FirstUseRollback(unittest.TestCase):
    def test_outer_rollback_restores_existing_helpers_or_removes_new_ones(self):
        for installed in (False, True):
            with self.subTest(installed=installed):
                fixture = Fixture(self)
                (fixture.root / 'usr/lib').mkdir()
                directory = fixture.root / HELPER_ROOT
                if installed:
                    directory.mkdir(parents=True)
                    directory.parent.chmod(0o755)
                    directory.chmod(0o755)
                    for name in HELPERS:
                        (directory / name).write_text('previous ' + name)
                        (directory / name).chmod(0o640)
                snapshot, restore = scripts()
                env = {'PATH': '/usr/bin:/bin', 'HOME': str(fixture.tmp)}
                taken = subprocess.run(['bash', '-c', 'set -euo pipefail\n' +
                                        as_user(under(snapshot, fixture.root))],
                                       env=env, capture_output=True, text=True, timeout=30)
                self.assertEqual(taken.returncode, 0, taken.stderr)
                txn = taken.stdout.strip().splitlines()[-1]
                # Simulate the exact three destinations published by the OS
                # deployment, then run the real outer rollback program.
                directory.mkdir(parents=True, exist_ok=True)
                directory.parent.chmod(0o755)
                directory.chmod(0o755)
                for name in HELPERS:
                    (directory / name).write_bytes((ROOT / 'provision' / name).read_bytes())
                    (directory / name).chmod(0o755 if name == HELPERS[0] else 0o644)
                restored = subprocess.run(['bash', '-s', '--', txn],
                    input='systemctl() { :; }\nset -euo pipefail\n' +
                          as_user(under(restore, fixture.root)),
                    env=env, capture_output=True, text=True, timeout=30)
                self.assertEqual(restored.returncode, 0, restored.stderr)
                if installed:
                    for name in HELPERS:
                        self.assertEqual((directory / name).read_text(), 'previous ' + name)
                        self.assertEqual((directory / name).stat().st_mode & 0o777, 0o640)
                else:
                    self.assertFalse(directory.exists())


if __name__ == '__main__':
    unittest.main()
