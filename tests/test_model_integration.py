"""Offline closure checks, including refusal with preserved previous state."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

TOOL = Path(__file__).resolve().parents[1] / 'build/verify-model-integration.py'
spec = importlib.util.spec_from_file_location('integration', TOOL)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class IntegrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'source'
        self.repo.mkdir()
        def git(*args):
            return subprocess.check_output(['git', '-C', str(self.repo), *args], text=True).strip()
        self.git = git
        git('init', '-q')
        git('config', 'user.name', 'itsmygithubacct')
        git('config', 'user.email', 'itsmygithubacct@users.noreply.github.com')
        (self.repo / 'code').write_text('fixture\n')
        git('add', '.')
        git('commit', '-qm', 'Fixture')
        (self.root / 'runtime').write_bytes(b'fixture')
        (self.root / 'previous-selection').write_text('keep this exact selection\n')
        self.manifest = dict(schema='plebian-os.model-integration/v1', selection='unselected',
            release_accepted=False,
            files=[dict(id='runtime', path='runtime', bytes=7,
                        sha256=hashlib.sha256(b'fixture').hexdigest())],
            sources=[dict(id='consumer', path='source', head=git('rev-parse', 'HEAD'),
                          tree=git('rev-parse', 'HEAD^{tree}'), gitlinks={})],
            profiles=[dict(id='profile', sources=['consumer'], files=['runtime'],
                           abi='fixture-only', cpu='fixture-only', install='staged',
                           relocation='rebind', rollback='retain previous',
                           review={'state':'pending'}, license='missing', license_evidence=[],
                           packaging='pending', quality='no-go', admission='pending')])

    def verify(self):
        return module.verify(self.manifest, self.root)

    def test_identity_is_not_acceptance(self):
        result = self.verify()
        self.assertEqual(result['identity'], 'verified')
        self.assertFalse(result['release_accepted'])
        self.assertEqual(len(result['gaps']), 5)

    def test_missing_corrupt_and_relocated_artifacts(self):
        for content in (b'changed', b''):
            with self.subTest(content=content):
                (self.root/'runtime').write_bytes(content)
                with self.assertRaisesRegex(module.Invalid, 'identity mismatch'): self.verify()
        (self.root/'runtime').unlink()
        with self.assertRaisesRegex(module.Invalid, 'missing regular'): self.verify()

    def test_paths_cannot_escape_root(self):
        for path in ('../runtime', '/runtime', 'a/../../runtime'):
            with self.subTest(path=path):
                self.manifest['files'][0]['path'] = path
                with self.assertRaises(module.Invalid): self.verify()

    def test_symlink_escape(self):
        (self.root/'outside').symlink_to('/etc/hosts')
        self.manifest['files'][0]['path'] = 'outside'
        with self.assertRaisesRegex(module.Invalid, 'symlink escapes'): self.verify()

    def test_stale_source_and_dirty_source(self):
        self.manifest['sources'][0]['head'] = '1'*40
        with self.assertRaisesRegex(module.Invalid, 'HEAD mismatch'): self.verify()
        self.manifest['sources'][0]['head'] = self.git('rev-parse','HEAD')
        (self.repo/'code').write_text('changed')
        with self.assertRaisesRegex(module.Invalid, 'dirty source'): self.verify()

    def test_alternates_refused(self):
        (self.repo/'.git/objects/info/alternates').write_text('/missing\n')
        with self.assertRaisesRegex(module.Invalid, 'alternates'): self.verify()

    def test_git_directory_symlink_refused(self):
        moved = self.root / 'shared.git'
        (self.repo/'.git').rename(moved)
        (self.repo/'.git').symlink_to(moved, target_is_directory=True)
        with self.assertRaisesRegex(module.Invalid, 'own its Git directory'): self.verify()

    def test_duplicate_source_directory_refused(self):
        entry = copy.deepcopy(self.manifest['sources'][0])
        entry['id'] = 'alias'
        self.manifest['sources'].append(entry)
        with self.assertRaisesRegex(module.Invalid, 'duplicate source directory'): self.verify()

    def test_index_flags_cannot_hide_modified_source(self):
        for flag in ("--assume-unchanged", "--skip-worktree"):
            with self.subTest(flag=flag):
                self.git("update-index", flag, "code")
                (self.repo / "code").write_text("changed source")
                with self.assertRaisesRegex(module.Invalid, "index entries"):
                    self.verify()
                self.git("update-index", "--no-assume-unchanged", "code")
                self.git("update-index", "--no-skip-worktree", "code")
                (self.repo / "code").write_text("fixture\n")

    def test_redirected_worktree_is_not_the_declared_source(self):
        other = self.root / "redirected"
        other.mkdir()
        (other / "code").write_text("fixture\n")
        self.git("config", "core.worktree", str(other))
        (self.repo / "code").write_text("changed source")
        with self.assertRaisesRegex(module.Invalid, "not the Git worktree"):
            self.verify()

    def test_readonly_validation_does_not_refresh_index(self):
        import os
        path = self.repo / "code"
        info = path.stat()
        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 2_000_000_000))
        index = self.repo / ".git/index"
        before = index.read_bytes()
        self.verify()
        self.assertEqual(index.read_bytes(), before)

    def test_nonobject_manifest_is_clean_cli_refusal(self):
        import sys
        path = self.root / "bad.json"
        path.write_text("[]")
        result = subprocess.run([sys.executable, str(TOOL), "--root", str(self.root),
                                 "--manifest", str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("model integration refused:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_incomplete_gitlink_inventory(self):
        self.manifest['sources'][0]['gitlinks'] = {'child':'1'*40}
        with self.assertRaisesRegex(module.Invalid, 'gitlink inventory'): self.verify()

    def test_unresolved_profile_reference(self):
        self.manifest['profiles'][0]['files'] = ['other']
        with self.assertRaisesRegex(module.Invalid, 'unresolved files'): self.verify()

    def test_duplicate_json_keys(self):
        with self.assertRaisesRegex(module.Invalid, 'duplicate JSON key'):
            json.loads('{"selection":"unselected","selection":"selected"}',
                       object_pairs_hook=module.unique_object)

    def test_claims_need_bound_evidence(self):
        self.manifest['profiles'][0]['license'] = 'existing-binding'
        with self.assertRaisesRegex(module.Invalid, 'license needs evidence'): self.verify()
        self.manifest['profiles'][0]['license'] = 'missing'
        self.manifest['profiles'][0]['review'] = {'state':'complete', 'file':'absent'}
        with self.assertRaisesRegex(module.Invalid, 'missing review binding'): self.verify()

    def test_preserve_failed_review_and_require_repair_review(self):
        receipt = dict(complete=True, source_heads={'consumer':self.git('rev-parse','HEAD')},
                       original_verdict='fail')
        def bind():
            raw=json.dumps(receipt).encode(); (self.root/'review.json').write_bytes(raw)
            self.manifest['files'] = [self.manifest['files'][0],dict(id='review',path='review.json',
                bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())]
        bind()
        self.manifest['profiles'][0]['review'] = {'state':'complete','file':'review'}
        with self.assertRaisesRegex(module.Invalid, 'independent repair review'): self.verify()
        receipt['repair_independent_review']='pass'; bind(); self.verify()
        receipt['source_heads']['consumer']='1'*40; bind()
        with self.assertRaisesRegex(module.Invalid, 'stale review'): self.verify()

    def test_complete_mode_refuses_without_mutation(self):
        import sys
        (self.root/'manifest.json').write_text(json.dumps(self.manifest))
        before={p.relative_to(self.root):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result=subprocess.run([sys.executable,str(TOOL),'--root',str(self.root),
            '--manifest',str(self.root/'manifest.json'),'--require-complete'],capture_output=True)
        self.assertEqual(result.returncode,2,result.stderr)
        after={p.relative_to(self.root):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before,after)


if __name__ == '__main__': unittest.main()
