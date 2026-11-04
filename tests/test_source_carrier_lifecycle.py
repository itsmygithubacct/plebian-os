"""Real supervisor signals/children; tiny pool fixture isolates Git preparation."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
HELPER=ROOT/'provision/plebian-os-source-carrier'

class SourceCarrierLifecycleTests(unittest.TestCase):
    def exercise(self, number=None, code=0, stubborn=False):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);state=root/'state.json';rollback=root/'rollback';ready=root/'ready'
            # A genuine process and grandchild in the supervised group. The
            # direct child records a rollback marker on TERM/INT before exiting.
            command=root/'child.py'
            command.write_text('''import json,os,subprocess,sys,time,signal
from pathlib import Path
root=Path(sys.argv[1]); stubborn=sys.argv[2]=='1'
def stop(number,frame):
 (root/'rollback').write_text(str(number));raise SystemExit(0)
signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
if stubborn:
 script='import signal,time,sys;signal.signal(signal.SIGTERM,signal.SIG_IGN);signal.signal(signal.SIGINT,signal.SIG_IGN);open(sys.argv[1],\"w\").write(\"ready\");time.sleep(120)'
 grand=subprocess.Popen([sys.executable,'-c',script,str(root/'grand-ready')])
 while not (root/'grand-ready').exists():time.sleep(.01)
else:grand=None
(root/'state.json').write_text(json.dumps({'pid':os.getpid(),'grandchild':grand.pid if grand else None,'config':os.environ['GIT_CONFIG_GLOBAL']}))
(root/'ready').write_text('ready')
if sys.argv[3]!='wait':raise SystemExit(int(sys.argv[3]))
while True:time.sleep(.02)
''')
            driver=root/'driver.py'
            driver.write_text('''import runpy,sys
from pathlib import Path
api=runpy.run_path(sys.argv[1])
class Pool:
 def prepare_git(self,path):
  path.mkdir();config=path/'gitconfig';config.write_text('');return str(config)
raise SystemExit(api['run_owned'](Pool(),Path(sys.argv[2])/'manifest.json','0'*64,sys.argv[3:]))
''')
            proc=subprocess.Popen([sys.executable,str(driver),str(HELPER),str(root),sys.executable,str(command),str(root),'1' if stubborn else '0','wait' if number else str(code)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            data=None
            try:
                deadline=time.monotonic()+10
                while not ready.exists() and proc.poll() is None and time.monotonic()<deadline:time.sleep(.02)
                self.assertTrue(ready.exists(),'child never became ready')
                data=json.loads(state.read_text());pool=Path(data['config']).parents[1]
                if number:
                    self.assertTrue(pool.exists());os.kill(proc.pid,number)
                _out,err=proc.communicate(timeout=12)
                self.assertEqual(proc.returncode,128+number if number else code,err)
                if number:self.assertEqual(rollback.read_text(),str(number))
                self.assertFalse(pool.exists(),err)
                for pid in (data['pid'],data['grandchild']):
                    if pid:self.assertFalse(Path('/proc',str(pid)).exists(),'owned child/descendant not reaped')
            finally:
                if proc.poll() is None:proc.kill();proc.communicate(timeout=5)
                if data:
                    # Failure cleanup only: this group was created by our child.
                    try:os.killpg(data['pid'],signal.SIGKILL)
                    except ProcessLookupError:pass

    def test_normal_and_failing_child_cleanup(self):
        for status in (0,23):
            with self.subTest(status=status):self.exercise(code=status,stubborn=True)

    def test_term_and_int_forward_rollback_and_reap_stubborn_grandchild(self):
        for number in (signal.SIGTERM,signal.SIGINT):
            with self.subTest(signal=number):self.exercise(number=number,stubborn=True)
