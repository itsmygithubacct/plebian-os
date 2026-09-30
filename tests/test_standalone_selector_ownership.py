"""Exercise the elevated transaction with distinct root and user identities."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SELECT = ROOT / "provision/plebian-os-select-closure.sh"
PRIVATE_CASE = r'''
import hashlib,json,os,pathlib,subprocess,sys,tempfile
request=json.load(sys.stdin)
with tempfile.TemporaryDirectory(prefix='selector-owner-private-',dir='/tmp') as temporary:
    root=pathlib.Path(temporary)
    os.chown(root,1000,1000)
    stage=root/'stage';stage.mkdir();os.chown(stage,1000,1000)
    if request['mode']=='image':
        config=root/'etc/pleb'; tools=root/'usr/local/bin';tools.mkdir(parents=True)
        selector=str(tools/'plebian-os-select-closure');updater=str(tools/'plebian-os-update')
        original_owner=0
    else:
        config=root/'user/config';selector=updater='';original_owner=1000
    config.mkdir(parents=True);os.chown(config,original_owner,original_owner)
    if request['mode']=='standalone': os.chown(config.parent,1000,1000)
    session=config/'session.env';closure=config/'closure.env';base=root/'recovery';base.mkdir()
    os.chown(base,original_owner,original_owner)
    session.write_text('old profile\n');session.chmod(0o600)
    os.chown(session,original_owner,original_owner)
    original=(session.read_bytes(),session.stat().st_uid,session.stat().st_gid,session.stat().st_mode & 0o777)
    for name,text,key in [('session.env.new','selected profile\n','session'),
                          ('closure.env','selected pins\n','closure'),
                          ('plebian-os-select-closure','selector\n','selector'),
                          ('plebian-os-update','updater\n','updater')]:
        (stage/name).write_text(text)
        (stage/(key+'.sha256')).write_text(hashlib.sha256(text.encode()).hexdigest()+'\n')
    (stage/'meta').write_text('fixture\n')
    env=os.environ.copy();env.update(SUDO_UID='1000',SUDO_GID='1000')
    done=subprocess.run(['bash','-s','--',str(session),str(closure),selector,updater,
                         str(stage),str(base),request['mode'],request.get('fail_after',''),
                         str(request.get('caller_uid',1000)),'1000'],
                        input=request['body'],text=True,capture_output=True,env=env)
    metadata=lambda p: [p.stat().st_uid,p.stat().st_gid,p.stat().st_mode & 0o777]
    result={'status':done.returncode,'stderr':done.stderr,
            'session_metadata':metadata(session),'closure_present':closure.exists(),
            'old_profile_restored':(session.read_bytes(),*metadata(session))==original,
            'namespace':pathlib.Path('/proc/self/uid_map').read_text()}
    if closure.exists(): result['closure_metadata']=metadata(closure)
    if request['mode']=='standalone' and done.returncode==0:
        read=subprocess.run(['setpriv','--reuid=1000','--regid=1000','--clear-groups',
                             'cat',str(session),str(closure)],capture_output=True,text=True)
        result.update(user_read_status=read.returncode,user_read_output=read.stdout)
    if selector and pathlib.Path(selector).exists():
        result['selector_metadata']=metadata(pathlib.Path(selector))
    print(json.dumps(result))
'''


class ElevatedOwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for command in ("unshare", "newuidmap", "newgidmap", "setpriv"):
            if not shutil.which(command):
                raise unittest.SkipTest("private subordinate-ID namespace tools unavailable")
        cls.command = ["unshare", "--user", "--map-root-user", "--map-auto", sys.executable, "-B", "-c"]
        probe = subprocess.run(cls.command + ["import os; os.setgid(1000); os.setuid(1000)"],
                               capture_output=True, text=True, timeout=10)
        if probe.returncode:
            raise unittest.SkipTest("private subordinate-ID namespace unavailable: " + probe.stderr.strip())

    def transaction(self, mode="standalone", **extra):
        source = SELECT.read_text()
        body = source.split("<<'ROOT_SPLIT_APPLY' || rc=$?\n", 1)[1].split("\nROOT_SPLIT_APPLY\n", 1)[0]
        done = subprocess.run(self.command + [PRIVATE_CASE],
                              input=json.dumps({"body": body, "mode": mode, **extra}),
                              capture_output=True, text=True, timeout=15)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def test_elevated_standalone_files_remain_user_owned_private_and_readable(self):
        result = self.transaction()
        self.assertEqual(result["status"], 0, result)
        self.assertEqual(result["session_metadata"], [1000, 1000, 0o600])
        self.assertEqual(result["closure_metadata"], [1000, 1000, 0o600])
        self.assertEqual(result["user_read_status"], 0, result)
        self.assertEqual(result["user_read_output"], "selected profile\nselected pins\n")

    def test_image_keeps_root_owned_world_readable_configuration_and_tools(self):
        result = self.transaction(mode="image")
        self.assertEqual(result["status"], 0, result)
        self.assertEqual(result["session_metadata"], [0, 0, 0o644])
        self.assertEqual(result["closure_metadata"], [0, 0, 0o644])
        self.assertEqual(result["selector_metadata"], [0, 0, 0o755])

    def test_failed_commit_restores_original_user_metadata_and_absent_closure(self):
        result = self.transaction(fail_after="session")
        self.assertEqual(result["status"], 9, result)
        self.assertTrue(result["old_profile_restored"], result)
        self.assertFalse(result["closure_present"], result)

    def test_caller_identity_mismatch_refuses_before_user_files_change(self):
        result = self.transaction(caller_uid=0)
        self.assertNotEqual(result["status"], 0, result)
        self.assertTrue(result["old_profile_restored"], result)
        self.assertFalse(result["closure_present"], result)


if __name__ == "__main__":
    unittest.main()
