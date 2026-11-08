"""Real remote argv construction with disposable executable stand-ins."""
from contextlib import contextmanager, ExitStack
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import socket
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'build'))
import qemu_tab
import qemu_runtime


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
if 'ls' in sys.argv:
    print(os.environ.get('LS_REPLY', ''))
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

    @contextmanager
    def qmp_peer(self, replies):
        """Serve disposable greetings; never connect to an existing VM."""
        path = self.vm / 'qmp.sock'
        (self.vm / 'tab.ready').write_bytes(b'content-ready\n')
        server = socket.socket(socket.AF_UNIX)
        server.settimeout(0.1)
        server.bind(str(path))
        server.listen(2)
        stop = threading.Event()

        def serve():
            for payload, delay in replies:
                while not stop.is_set():
                    try:
                        connection, _ = server.accept()
                        break
                    except socket.timeout:
                        continue
                else:
                    return
                with connection:
                    chunks = (bytes([byte]) for byte in payload) if delay else [payload]
                    try:
                        for chunk in chunks:
                            connection.sendall(chunk)
                            if stop.wait(delay):
                                return
                    except (BrokenPipeError, ConnectionResetError):
                        pass  # The client deliberately rejects malformed/slow peers.

        worker = threading.Thread(target=serve, daemon=True)
        worker.start()
        try:
            yield
        finally:
            stop.set()
            worker.join(timeout=2)
            server.close()
            path.unlink()
            (self.vm / 'tab.ready').unlink()
            self.assertFalse(worker.is_alive())

    def test_argv_bytes_focus_foreground_and_single_tab(self):
        arguments = ['qemu-system-x86_64', '-name', 'space\nquote\'";$()',
                     '-display', 'gtk', '-drive', 'file=guest name.qcow2',
                     'byte-\udcff', '']
        with patch.object(qemu_tab, '_ready', return_value=True):
            qemu_tab.launch(arguments, 'VM title', self.vm)
        calls = self.calls()
        self.assertEqual(len(calls), 2)
        launch = calls[1]
        target = launch[launch.index('--') + 1:]
        self.assertEqual(target[:2], ['python3', '-c'])
        decoded, environment, cwd = json.loads(target[3])
        self.assertEqual(decoded, [str(self.root / 'kilix'), 'run', *arguments])
        self.assertEqual(environment['KILIX_RUN_READY_FILE'], str(self.vm / 'tab.ready'))
        self.assertEqual(cwd, str(Path.cwd()))
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

    def test_already_exited_tab_requires_authenticated_empty_match(self):
        for reply, accepted in (("[]", True), ('[{"tabs": []}]', True),
                                ('[{"tabs": [{"windows": [{}]}]}]', False),
                                (json.dumps([{'tabs':[{'windows':[{'env':{'KILIX_VM_LAUNCH':'a'*32}}]}]}]), False),
                                (json.dumps([{'tabs':[{'windows':[{'env':{'KILIX_VM_LAUNCH':'b'*32}}]}]}]), True),
                                ('{"error": "denied"}', False), ("invalid", False)):
            with self.subTest(reply=reply), patch.dict(os.environ, {"CLOSE_RC": "1", "LS_REPLY": reply}):
                if accepted:
                    qemu_tab._close_owned([str(self.root / "kitten")], "KILIX_VM_LAUNCH=" + "a" * 32)
                else:
                    with self.assertRaises(subprocess.CalledProcessError):
                        qemu_tab._close_owned([str(self.root / "kitten")], "KILIX_VM_LAUNCH=" + "a" * 32)
                close, inspect = self.calls()[-2:]
                self.assertEqual(inspect, ["ls", "--all-env-vars"])
                self.assertEqual(inspect[0], "ls")
        with patch.dict(os.environ, {"CLOSE_RC": "1", "LS_REPLY": "[]", "LS_RC": "1"}):
            with self.assertRaises(subprocess.CalledProcessError):
                qemu_tab._close_owned([str(self.root / "kitten")], "KILIX_VM_LAUNCH=" + "a" * 32)

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

    def test_long_vm_path_reconnects_through_recorded_private_endpoint(self):
        import socket
        import threading
        directory = self.root / ("é" * 60) / "vm"
        directory.mkdir(mode=0o700, parents=True)
        endpoint = qemu_runtime.prepare_qmp(directory)
        self.addCleanup(qemu_runtime.cleanup_empty_runtime, directory)
        (directory / "tab.ready").write_bytes(b"content-ready\n")
        with socket.socket(socket.AF_UNIX) as server:
            server.settimeout(2)
            server.bind(str(endpoint))
            server.listen(2)
            def serve():
                for _ in range(2):
                    with server.accept()[0] as connection:
                        connection.sendall(b'{"QMP": {}}\r\n')
            worker = threading.Thread(target=serve)
            worker.start()
            try:
                self.assertTrue(qemu_tab._ready(directory))
                self.assertTrue(qemu_tab._ready(directory))
            finally:
                worker.join(timeout=3)
                endpoint.unlink()
        self.assertFalse(worker.is_alive())
        self.assertFalse(qemu_tab._ready(directory))

    def test_prepared_discovery_link_is_allowed_but_occupied_endpoint_refuses(self):
        endpoint = qemu_runtime.prepare_qmp(self.vm)
        self.addCleanup(qemu_runtime.cleanup_empty_runtime, self.vm)
        with patch.object(qemu_tab, "_ready", return_value=True):
            qemu_tab.launch(["qemu-system-x86_64"], "VM", self.vm)
        for symlink in (False, True):
            with self.subTest(symlink=symlink):
                if symlink:
                    endpoint.symlink_to(self.root / "missing")
                else:
                    endpoint.write_bytes(b"keep")
                previous_launches = sum("launch" in call for call in self.calls())
                try:
                    with self.assertRaisesRegex(RuntimeError, "fresh QMP"):
                        qemu_tab.launch(["qemu-system-x86_64"], "VM", self.vm)
                    self.assertEqual(sum("launch" in call for call in self.calls()),
                                     previous_launches)
                    self.assertTrue(os.path.lexists(endpoint))
                finally:
                    endpoint.unlink()

    def test_qmp_greeting_is_required(self):
        import socket
        import threading
        (self.vm / 'tab.ready').write_bytes(b'content-ready\n')
        for greeting, expected in ((b'{"QMP": {}}\r\n', True),
                                   (b'{"error": {}}\n', False), (b'garbage\n', False),
                                   (b'{"QMP": {}}', False), (b'{"QMP":', False),
                                   (b'', False),
                                   (b'{"QMP": {}}' + b' ' * (65536 - 12) + b'\n', True),
                                   (b'{"QMP": {}}' + b' ' * (65536 - 11) + b'\n', False)):
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

    def test_slow_drip_cannot_extend_the_whole_greeting_budget(self):
        with self.qmp_peer([(b'{"QMP": {}}\n', 0.09)]):
            started = time.monotonic()
            self.assertFalse(qemu_tab._ready(self.vm))
            self.assertLess(time.monotonic() - started, 0.8)

    def test_launch_passes_its_shorter_deadline_to_a_slow_greeting(self):
        with ExitStack() as stack:
            def launch_peer(*args, **kwargs):
                stack.enter_context(self.qmp_peer([(b'{"QMP": {}}\n', 0.09)]))
                return SimpleNamespace(stdout='42\n')
            stack.enter_context(patch.object(qemu_tab, 'require_host', return_value=(['fixture'], '/fixture/kilix')))
            stack.enter_context(patch.object(qemu_tab.subprocess, 'run', side_effect=launch_peer))
            close = stack.enter_context(patch.object(qemu_tab, '_close_owned'))
            started = time.monotonic()
            with self.assertRaisesRegex(RuntimeError, 'did not become ready'):
                qemu_tab.launch(['qemu-fixture'], 'VM', self.vm, timeout=0.05)
            self.assertLess(time.monotonic() - started, 0.18)
            close.assert_called_once()
            self.assertRegex(close.call_args.args[1], r'^KILIX_VM_LAUNCH=[0-9a-f]{32}$')

    def test_complete_greeting_received_after_deadline_is_refused(self):
        (self.vm / 'tab.ready').write_bytes(b'content-ready\n')
        now = [10.0]
        with patch.object(qemu_tab.socket, 'socket') as constructor, \
                patch.object(qemu_tab.time, 'monotonic', side_effect=lambda: now[0]):
            connection = constructor.return_value.__enter__.return_value
            def late_receive(size):
                now[0] = 10.05
                return b'{"QMP": {}}\n'
            connection.recv.side_effect = late_receive
            self.assertFalse(qemu_tab._ready(self.vm, deadline=10.05))

    def test_launch_rechecks_deadline_after_successful_probe(self):
        now = [10.0]
        def late_ready(directory, *, deadline):
            now[0] = deadline
            return True
        with patch.object(qemu_tab, '_ready', side_effect=late_ready), \
                patch.object(qemu_tab.time, 'monotonic', side_effect=lambda: now[0]):
            with self.assertRaisesRegex(RuntimeError, 'did not become ready'):
                qemu_tab.launch(['qemu-fixture'], 'VM', self.vm, timeout=0.05)
        self.assertIn('close-window', self.calls()[-1])

    def test_unterminated_greeting_does_not_prevent_valid_reconnect(self):
        with self.qmp_peer([(b'{"QMP": {}}', 0), (b'{"QMP": {}}\r\n', 0)]):
            self.assertFalse(qemu_tab._ready(self.vm))
            self.assertTrue(qemu_tab._ready(self.vm))


if __name__ == '__main__':
    unittest.main()
