"""Notification service rollback uses named keys and respects older snapshots."""
from pathlib import Path
import subprocess
import unittest

from test_lid_update import Fixture, as_user, scripts, under


class NotificationRollbackTests(unittest.TestCase):
    def run_root(self, fixture, script, *args):
        return subprocess.run(['bash', '-s', '--', *map(str, args)],
                              input='systemctl() { :; }\nldconfig() { :; }\n' +
                              as_user(under(script, fixture.root)),
                              env={'PATH': '/usr/bin:/bin', 'HOME': str(fixture.tmp)},
                              capture_output=True, text=True, timeout=20)

    def prepare_module(self, fixture):
        for name in ("usr/local/lib", "usr/local/lib/pleb"):
            directory = fixture.root / name
            directory.mkdir(exist_ok=True)
            directory.chmod(0o755)

    def test_restore_recovers_previous_bytes_or_removes_new_delivery(self):
        for installed in (False, True):
            with self.subTest(installed=installed):
                fixture = Fixture(self)
                module = fixture.root / 'usr/local/lib/pleb/notification_center.py'
                if installed:
                    self.prepare_module(fixture)
                    module.write_bytes(b'previous module')
                    module.chmod(0o640)
                snapshot, restore = scripts()
                result = self.run_root(fixture, snapshot)
                self.assertEqual(result.returncode, 0, result.stderr)
                transaction = Path(result.stdout.strip())
                self.assertTrue((transaction / 'pleb-notifications').is_file())
                self.prepare_module(fixture)
                module.write_bytes(b'new module')
                staged = module.with_name('.notification_center.py.new')
                staged.write_bytes(b'interrupted stage')
                result = self.run_root(fixture, restore, transaction)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(staged.exists())
                if installed:
                    self.assertEqual(module.read_bytes(), b'previous module')
                    self.assertEqual(module.stat().st_mode & 0o777, 0o640)
                else:
                    self.assertFalse(module.exists())

    def test_snapshot_without_notification_marker_keeps_later_module(self):
        fixture = Fixture(self)
        module = fixture.root / 'usr/local/lib/pleb/notification_center.py'
        self.prepare_module(fixture)
        snapshot, restore = scripts()
        result = self.run_root(fixture, snapshot)
        self.assertEqual(result.returncode, 0, result.stderr)
        transaction = Path(result.stdout.strip())
        (transaction / 'pleb-notifications').unlink()
        module.write_bytes(b'later notification service')
        result = self.run_root(fixture, restore, transaction)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(module.read_bytes(), b'later notification service')


if __name__ == '__main__':
    unittest.main()
