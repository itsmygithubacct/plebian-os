"""Real remote argv construction with disposable executable stand-ins."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'build'))
import qemu_tab


class QemuTabTests(unittest.TestCase):
    def setUp(self):
        # UNIX socket paths are bounded; a caller's long TMPDIR must not
        # turn this transport fixture into an unrelated AF_UNIX failure.
        self.tmp = tempfile.TemporaryDirectory(prefix="qemu-tab-", dir="/tmp")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.log = self.root / 'calls'
        self.vm = self.root / 'vm'
        self.vm.mkdir(mode=0o700)
        kitten = self.root / 'kitten'
        kitten.write_text(f'''#!{sys.executable}
import json, os, sys
with open(os.environ['CALLS'], 'a') as log:
    log.write(json.dumps(sys.argv[1:]) + '\\n')
if 'close-window' in sys.argv:
    sys.exit(int(os.environ.get('CLOSE_RC', '0')))
if 'launch' in sys.argv:
    print(os.environ.get('PANE_ID', '42'))
    sys.exit(int(os.environ.get('LAUNCH_RC', '0')))
sys.exit(int(os.environ.get('LS_RC', '0')))
''')
        kitten.chmod(0o755)
        (self.root / 'kilix').write_text('#!/bin/sh\nexit 99\n')
        (self.root / 'kilix').chmod(0o755)
        self.environment = patch.dict(os.environ, {
            'PATH': str(self.root), 'KITTY_LISTEN_ON': 'unix:fixture',
            'KILIX_RC_PASSWORD_FILE': str(self.root / 'password with space'),
            'CALLS': str(self.log),
        }, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_argv_bytes_focus_foreground_and_single_tab(self):
        arguments = ['qemu-system-x86_64', '-name', 'space\nquote\'";$()',
                     '-display', 'gtk', '-drive', 'file=guest name.qcow2',
                     'byte-\udcff', '']
        with patch.object(qemu_tab, '_ready', return_value=True):
            qemu_tab.launch(arguments, 'VM title', self.vm)
        calls = self.calls()
        self.assertEqual(len(calls), 2)
        launch = calls[1]
        self.assertEqual(launch[launch.index('--') + 1:],
                         [str(self.root / 'kilix'), 'run', *arguments])
        self.assertIn('--keep-focus', launch)
        self.assertIn('--type=tab', launch)
        self.assertIn('KILIX_IN_OVERLAY=1', launch)
        self.assertIn(f'KILIX_RUN_READY_FILE={self.vm / "tab.ready"}', launch)
        self.assertNotIn('-daemonize', launch)
        self.assertEqual(launch[launch.index('--password-file') + 1],
                         str(self.root / 'password with space'))

    def test_no_capability_or_remote_refusal_never_launches(self):
        for changes, exception in (({'KITTY_LISTEN_ON': ''}, RuntimeError),
                                   ({'KILIX_KITTEN': '/missing'}, RuntimeError),
                                   ({'LS_RC': '1'}, subprocess.CalledProcessError)):
            with self.subTest(changes=changes), patch.dict(os.environ, changes):
                with self.assertRaises(exception):
                    qemu_tab.launch(['qemu-system-x86_64'], 'VM', self.vm)
        self.assertFalse(any('launch' in c for c in self.calls()))

    def test_every_failed_launch_closes_only_its_marker(self):
        for changes in ({'LAUNCH_RC': '1'}, {'PANE_ID': 'not an ID'}, {}):
            with self.subTest(changes=changes), patch.dict(os.environ, changes):
                with self.assertRaises((RuntimeError, subprocess.CalledProcessError)):
                    qemu_tab.launch(['qemu-system-x86_64'], 'VM', self.vm, timeout=0)
                launch, close = self.calls()[-2:]
                marker = next(x for x in launch if x.startswith('KILIX_VM_LAUNCH='))
                self.assertEqual(close[-3:], ['close-window', '--match', 'env:' + marker])

    def test_close_failure_is_visible(self):
        with patch.dict(os.environ, {'CLOSE_RC': '1'}):
            with self.assertRaisesRegex(RuntimeError, 'tab cleanup failed'):
                qemu_tab.launch(['qemu-system-x86_64'], 'VM', self.vm, timeout=0)

    def test_existing_vm_state_and_detach_are_refused(self):
        (self.vm / 'qemu.pid').write_text('123')
        with self.assertRaisesRegex(RuntimeError, 'fresh'):
            qemu_tab.launch(['qemu-system-x86_64'], 'VM', self.vm)
        (self.vm / 'qemu.pid').unlink()
        for flag in ('-daemonize', '--daemonize'):
            with self.subTest(flag=flag), self.assertRaisesRegex(ValueError, 'foreground'):
                qemu_tab.launch(['qemu-system-x86_64', flag], 'VM', self.vm)
        self.assertFalse(any('launch' in c for c in self.calls()))

    def test_interrupt_closes_owned_tab(self):
        with patch.object(qemu_tab, '_ready', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                qemu_tab.launch(['qemu-system-x86_64'], 'VM', self.vm)
        self.assertIn('close-window', self.calls()[-1])

    def test_content_readiness_is_required_even_with_qmp_available(self):
        with patch.object(qemu_tab.socket, 'socket') as connection:
            self.assertFalse(qemu_tab._ready(self.vm))
            (self.vm / 'tab.ready').write_bytes(b'partial')
            self.assertFalse(qemu_tab._ready(self.vm))
            connection.assert_not_called()

    def test_qmp_greeting_is_required(self):
        import socket
        import threading
        (self.vm / 'tab.ready').write_bytes(b'content-ready\n')
        for greeting, expected in ((b'{"QMP": {}}\r\n', True),
                                   (b'{"error": {}}\n', False), (b'garbage\n', False)):
            with self.subTest(greeting=greeting):
                server = socket.socket(socket.AF_UNIX)
                path = self.vm / 'qmp.sock'
                server.bind(str(path))
                server.listen(1)
                def serve():
                    with server.accept()[0] as connection:
                        connection.sendall(greeting)
                worker = threading.Thread(target=serve)
                worker.start()
                try:
                    self.assertEqual(qemu_tab._ready(self.vm), expected)
                finally:
                    worker.join(timeout=2)
                    server.close()
                    path.unlink()
        self.assertFalse(qemu_tab._ready(self.vm))


if __name__ == '__main__':
    unittest.main()
