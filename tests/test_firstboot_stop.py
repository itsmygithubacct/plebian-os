"""The service's main process must remain alive while its child rolls back."""
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest

RUNNER = Path(__file__).resolve().parents[1] / 'provision/plebian-os-firstboot-attempt'


class FirstbootStopTests(unittest.TestCase):
    def test_stop_waits_for_rollback_without_starting_another_attempt(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            command = root / 'provision'
            command.write_text('''#!/bin/bash
set -eu
finish() {
    trap - EXIT
    trap ':' TERM HUP INT
    touch "$1/restoring"
    sleep 0.7
    touch "$1/restored"
}
trap 'finish "$1"' EXIT
trap 'exit 143' TERM
printf '%s\\n' "$$" > "$1/child"
touch "$1/running" "$1/sudoers"
while :; do sleep 0.02; done
''')
            command.chmod(0o755)
            env = {**os.environ, 'PLEBIAN_OS_STATE_DIR': str(root / 'state'),
                   'PLEBIAN_OS_FIRSTBOOT_MAX_ATTEMPTS': '3',
                   'PLEBIAN_OS_FIRSTBOOT_ATTEMPT_TIMEOUT': '8',
                   'PLEBIAN_OS_FIRSTBOOT_RETRY_DELAY': '0',
                   'PLEBIAN_OS_TEMP_SUDOERS': str(root / 'sudoers')}
            with (root / 'output').open('w') as out:
                p = subprocess.Popen(['sh', str(RUNNER), 'run', str(command), td],
                                     env=env, stdout=out, stderr=out, start_new_session=True)
                try:
                    end = time.monotonic() + 4
                    while not (root / 'running').exists():
                        self.assertIsNone(p.poll())
                        self.assertLess(time.monotonic(), end)
                        time.sleep(0.02)
                    p.send_signal(signal.SIGTERM)
                    time.sleep(0.15)
                    self.assertIsNone(p.poll(), 'service main exited before child rollback')
                    self.assertTrue((root / 'restoring').exists())
                    p.send_signal(signal.SIGTERM)
                    self.assertEqual(p.wait(timeout=4), 143)
                    self.assertTrue((root / 'restored').exists())
                    self.assertFalse((root / 'sudoers').exists())
                    self.assertEqual((root / 'state/firstboot-attempts').read_text(), '1\n')
                    self.assertFalse(Path('/proc', (root / 'child').read_text().strip()).exists())
                finally:
                    if p.poll() is None:
                        p.kill()
                    p.wait(timeout=3)
                    # The baseline intentionally exits before its timeout child.
                    if (root / 'child').exists():
                        try:
                            child = int((root / 'child').read_text())
                            group = os.getpgid(child)
                            if group != os.getpgrp(): os.killpg(group, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                        time.sleep(0.8)


if __name__ == '__main__':
    unittest.main()
