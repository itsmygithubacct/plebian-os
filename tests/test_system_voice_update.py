"""Only completed, non-restarting stack updates publish a voice event."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
UPDATE=(ROOT/'provision/plebian-os-update.sh').read_text()


class SystemVoiceUpdateTests(unittest.TestCase):
    def test_atomic_private_notice_is_a_new_token(self):
        begin=UPDATE.index('notify_system_voice_update_complete() {')
        end=UPDATE.index('restart_session_after_commit() {', begin)
        function=UPDATE[begin:end]
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory)/'state'
            script=("set -euo pipefail\nid() { echo 1000; }\n"
                    f'KILIX_STATE_DIRECTORY={shlex.quote(str(state))}\n'+function+
                    '\nnotify_system_voice_update_complete\n')
            subprocess.run(['bash','-c',script],check=True,capture_output=True)
            notice=state/'system-voice-update-complete'
            first=notice.read_text();self.assertRegex(first,r'^[0-9a-f]{32}\n$')
            self.assertEqual(notice.stat().st_mode & 0o777,0o600)
            subprocess.run(['bash','-c',script],check=True,capture_output=True)
            self.assertNotEqual(notice.read_text(),first)
            self.assertEqual(list(state.iterdir()),[notice])

    def test_notice_follows_success_and_is_not_sent_on_failure_or_auto_restart(self):
        tail=UPDATE[UPDATE.index('\ncommit_stack_transaction\napt_reconcile_rc=0\n')+1:]
        for commit_rc, apt_rc, mode, notice_rc in ((0,0,'--no-restart',0),
                (0,0,'--no-restart',1),(0,1,'--no-restart',0),
                (0,0,'--restart',0),(1,0,'--no-restart',0)):
            with self.subTest(commit=commit_rc,apt=apt_rc,mode=mode,notice=notice_rc):
                script=f'''set -euo pipefail
log() {{ :; }}
warn() {{ :; }}
commit_stack_transaction() {{ echo commit; return {commit_rc}; }}
reconcile_release_apt_sources_after_commit() {{ echo reconcile; return {apt_rc}; }}
seed_desktop_wallpaper_after_commit() {{ :; }}
restart_session_after_commit() {{ echo restart-policy; }}
notify_system_voice_update_complete() {{ echo notice; return {notice_rc}; }}
restart_arg={mode}
'''+tail
                result=subprocess.run(['bash','-c',script],text=True,capture_output=True)
                self.assertEqual(result.returncode,commit_rc or apt_rc,result.stderr)
                should_notify=not commit_rc and not apt_rc and mode=='--no-restart'
                self.assertEqual('notice' in result.stdout.splitlines(),should_notify)
                if should_notify:
                    self.assertLess(result.stdout.index('reconcile'),result.stdout.index('notice'))


if __name__ == '__main__':unittest.main()
