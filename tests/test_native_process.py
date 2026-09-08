"""Actual dedicated child processes, escaped descendants and borrowed owners."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'provision/native_process.py'
DEDICATED = r'''
import importlib.util,json,os,signal,subprocess,sys,threading,time
from pathlib import Path
spec=importlib.util.spec_from_file_location('owned',sys.argv[1])
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.enable_subreaper()
mode=sys.argv[2]; root=Path(sys.argv[3]); log=root/'pids'
unrelated=subprocess.Popen(['/usr/bin/python3','-I','-B','-c','import time;time.sleep(30)'])
borrowed=os.open(root/'sentinel',os.O_RDONLY)
baseline_fds=len(os.listdir('/proc/self/fd'))
timer=None
original_fork_exec=subprocess._fork_exec
try:
    runner=m.Runner(seconds=0.2 if mode=='deadline' else 2)
    if mode=='preexpired':runner.deadline=time.monotonic()-1
    if mode=='precanceled':runner.cancel()
    if mode=='cancel':
        timer=threading.Timer(0.1,runner.cancel);timer.start()
    if mode in ('escape-success','escape-error','deadline','cancel','fork-return','register-memory'):
        code="""
import os,signal,sys,time
from pathlib import Path
log=Path(sys.argv[1]);mode=sys.argv[2]
def record():
    with log.open('a') as f:f.write(str(os.getpid())+chr(10))
record()
pid=os.fork()
if pid==0:
    os.setsid();signal.signal(signal.SIGTERM,signal.SIG_IGN);record()
    time.sleep(30);os._exit(0)
until=time.monotonic()+1
while len(log.read_text().splitlines())<2 and time.monotonic()<until:time.sleep(.002)
if mode in ('deadline','cancel','fork-return','register-memory'):time.sleep(30)
sys.exit(9 if mode=='escape-error' else 0)
"""
        argv=['/usr/bin/python3','-I','-B','-c',code,str(log),mode]
    elif mode=='overflow':
        argv=['/usr/bin/python3','-I','-B','-c','import os;os.write(1,b"x"*1048577)']
    elif mode=='error':
        argv=['/usr/bin/python3','-I','-B','-c','import sys;print("bad",file=sys.stderr);sys.exit(7)']
    elif mode=='guard':
        argv=['/usr/bin/python3','-I','-B','-c','import time;time.sleep(30)']
    elif mode in ('preexpired','precanceled'):
        argv=['/usr/bin/python3','-I','-B','-c','from pathlib import Path;import sys;Path(sys.argv[1]).touch()',str(log)]
    else:
        argv=['/usr/bin/python3','-I','-B','-c','import sys;print("ok");print("note",file=sys.stderr)']
    def wait_for_actual_tree():
        until=time.monotonic()+2
        while not log.exists() or len(log.read_text().splitlines())<2:
            assert time.monotonic()<until, 'actual child tree did not start'
            time.sleep(.002)
    if mode=='fork-return':
        def fail_after_actual_fork(*args,**kwargs):
            pid=original_fork_exec(*args,**kwargs)
            wait_for_actual_tree()
            raise MemoryError('fixture after actual fork before Popen handle return')
        subprocess._fork_exec=fail_after_actual_fork
    if mode=='register-memory':
        poller=m.selectors.DefaultSelector()
        def fail_register(*args,**kwargs):
            wait_for_actual_tree()
            raise MemoryError('fixture registration after Popen handle return')
        poller.register=fail_register
        m.selectors.DefaultSelector=lambda:poller
    calls=0
    def guard():
        global calls
        calls+=1
        if mode=='guard' and calls>2:raise ValueError('fixture held-lock revocation')
    began=time.monotonic(); result=None;error=None
    try:result=runner.run(argv,guard=guard)
    except (m.CommandFailed,ValueError,MemoryError) as caught:error=str(caught)
    if timer:timer.join()
    elapsed=time.monotonic()-began
    pids=[int(v) for v in log.read_text().splitlines()] if log.exists() else []
    assert all(not Path('/proc',str(pid)).exists() for pid in pids)
    assert unrelated.poll() is None and m.children()=={unrelated.pid}
    assert os.read(borrowed,4)==b'keep'
    assert len(os.listdir('/proc/self/fd'))==baseline_fds
    if mode=='success':assert result==(0,b'ok\n',b'note\n') and error is None
    else:assert error is not None and result is None
    if mode in ('deadline','cancel'):assert elapsed<1.5
    if mode in ('escape-success','escape-error','deadline','cancel','fork-return','register-memory'):assert len(pids)==2
    if mode in ('preexpired','precanceled'):assert not log.exists()
    print(json.dumps({'mode':mode,'error':error,'elapsed':elapsed,'pids':pids,
                      'owned_absent':True,'unrelated_alive':True,'fd_delta':0}))
finally:
    subprocess._fork_exec=original_fork_exec
    if timer:timer.join()
    # On a failing parent/candidate observation only, explicitly clean the
    # fixture's owned tree. The assertions above measure product cleanup first.
    until=time.monotonic()+2
    while m.children()-{unrelated.pid}:
        for pid in m.children()-{unrelated.pid}:
            waited,_=os.waitpid(pid,os.WNOHANG)
            if not waited:
                try:os.kill(pid,signal.SIGKILL)
                except ProcessLookupError:pass
        assert time.monotonic()<until, 'fixture observer cleanup incomplete'
        time.sleep(.002)
    os.close(borrowed)
    unrelated.terminate();unrelated.wait(timeout=3)
'''


class ProcessTests(unittest.TestCase):
    def run_case(self, mode):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'sentinel').write_bytes(b'keep')
            result = subprocess.run(['/usr/bin/python3', '-I', '-B', '-c', DEDICATED,
                                     str(MODULE), mode, str(root)], capture_output=True,
                                    timeout=10, env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            observation = json.loads(result.stdout)
            self.assertEqual(observation['fd_delta'], 0)
            self.assertTrue(observation['owned_absent'])
            print(json.dumps(observation, sort_keys=True))
            return observation

    def test_complete_success_retains_unrelated_process_and_fd(self):
        self.assertIsNone(self.run_case('success')['error'])

    def test_nonzero_exit_and_overflow_refuse_after_cleanup(self):
        self.assertIn('exited 7', self.run_case('error')['error'])
        self.assertIn('output exceeds', self.run_case('overflow')['error'])

    def test_success_or_error_with_escaped_descendant_never_returns_early(self):
        for mode in ('escape-success', 'escape-error'):
            with self.subTest(mode=mode):
                self.assertIn('owned descendant', self.run_case(mode)['error'])

    def test_original_deadline_reaps_resistant_escaped_child(self):
        self.assertIn('deadline expired', self.run_case('deadline')['error'])

    def test_cancel_reaps_resistant_escaped_child(self):
        self.assertIn('operation canceled', self.run_case('cancel')['error'])

    def test_held_lock_revocation_refuses_and_reaps(self):
        self.assertIn('held-lock revocation', self.run_case('guard')['error'])

    def test_preexisting_cancel_or_expiry_does_not_spawn(self):
        for mode in ('preexpired', 'precanceled'):
            with self.subTest(mode=mode):
                self.assertEqual(self.run_case(mode)['pids'], [])

    def test_actual_fork_before_handle_return_still_owns_and_reaps_tree(self):
        self.assertIn('after actual fork', self.run_case('fork-return')['error'])

    def test_registration_failure_after_handle_return_still_reaps_tree(self):
        self.assertIn('registration after Popen', self.run_case('register-memory')['error'])


if __name__ == '__main__':
    unittest.main()
