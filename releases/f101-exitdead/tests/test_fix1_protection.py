"""Private DAC experiments and protected-path predicates; true guest DAC pending."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fix1_fixture import PACKET, complete, create
from protection import Policy, ROOT
from control_gate import reviewed_tuple


class ProtectedLayout(unittest.TestCase):
    def test_production_root_and_owner_cannot_be_overridden(self):
        self.assertEqual(ROOT, Path('/opt/rc6-f101-age-r5'))
        with self.assertRaises(ValueError): Policy(PACKET)
        with self.assertRaises(ValueError): Policy(owner=os.getuid())
        with self.assertRaises(ValueError): Policy(boundary=PACKET)

    def test_readonly_child_in_writable_parent_can_be_replaced(self):
        base = Path(tempfile.mkdtemp(prefix='fix1-dac-vulnerable-', dir=PACKET / 'runtime'))
        parent = base / 'writable-stage2'; parent.mkdir(mode=0o700)
        binary = parent / 'bin'; binary.mkdir(); binary.chmod(0o555)
        self.assertFalse(os.access(binary, os.W_OK))
        binary.rename(parent / 'bin-original')
        binary.mkdir(); (binary / 'substituted.py').write_text('PRIVATE FIXTURE\n')
        self.assertTrue((binary / 'substituted.py').exists(), 'KILL-PARENT-REPLACEMENT-FACT')

    def test_private_protected_ancestor_rename_and_replacement_denials(self):
        base = Path(tempfile.mkdtemp(prefix='fix1-dac-protected-', dir=PACKET / 'runtime'))
        chain = [base, base / 'opt', base / 'opt/packet', base / 'opt/packet/stage2', base / 'opt/packet/stage2/bin']
        for path in chain[1:]: path.mkdir(mode=0o755)
        leaves = [path / 'probe' for path in chain]
        for leaf in leaves: leaf.write_text('PRIVATE DAC SENTINEL\n'); leaf.chmod(0o444)
        replacement = base.parent / (base.name + '-replacement'); replacement.write_text('PRIVATE REPLACEMENT\n')
        for path in reversed(chain): path.chmod(0o555)
        outcomes = []
        for parent, leaf in zip(chain, leaves):
            self.assertTrue(os.access(leaf, os.R_OK))
            self.assertFalse(os.access(parent, os.W_OK))
            with self.assertRaises(PermissionError): leaf.rename(parent / 'renamed')
            with self.assertRaises(PermissionError): os.replace(replacement, leaf)
            outcomes.append({'path': str(parent), 'read': True, 'write': False, 'rename_refused': True, 'replacement_refused': True})
        for path in chain[1:]:
            with self.assertRaises(PermissionError): path.rename(path.with_name(path.name + '-renamed'))
        evidence = {'fixture_only': True, 'scope': 'actual host UID DAC within private boundary only; not root/rc5model guest proof',
                    'uid': os.getuid(), 'outcomes': outcomes, 'guest_DAC_pending': True}
        (PACKET / 'evidence' / (base.name + '.json')).write_text(json.dumps(evidence, indent=2) + '\n')

    def test_writable_ancestors_code_symlinks_hardlinks_and_owner_mismatch_refuse(self):
        for kind in ('writable_parent', 'writable_file', 'symlink', 'hardlink', 'wrong_owner'):
            with self.subTest(kind=kind):
                root, policy, tools = create()
                file = root / 'candidate/observer.py'
                if kind == 'writable_parent': file.parent.chmod(0o777)
                elif kind == 'writable_file': file.chmod(0o666)
                elif kind == 'symlink':
                    target = root.parent / 'shadow.py'; file.rename(target); file.symlink_to(target)
                elif kind == 'hardlink': os.link(file, root.parent / 'alias.py')
                else: policy = Policy(root, fixture=True, owner=os.getuid() + 1, boundary=root.parent)
                with self.assertRaises((OSError, ValueError)): policy.read(file)

    def test_unlisted_importable_code_refuses_even_with_matching_review_digests(self):
        root, policy, tools = create()
        (root / 'candidate/unlisted.py').write_text('PRIVATE FIXTURE\n')
        with self.assertRaises(ValueError): reviewed_tuple(policy)

    def test_failed_genuine_miniature_execution_never_seals_or_advances_LATEST(self):
        root, policy, tools = create()
        with self.assertRaisesRegex(ValueError, 'genuine controls failed regrade'):
            complete(root, policy, fail_label='C8-counter-protocol')
        self.assertFalse((root / 'results-controls/LATEST').exists())
        self.assertEqual(list((root / 'stage1-seals').glob('controls-*.json')), [])
        out = next((root / 'results-controls').iterdir())
        self.assertFalse(json.loads((out / 'verdict.json').read_text())['accepted'])
        self.assertTrue((out / 'FAILURE.json').exists())
        self.assertEqual(json.loads((out / 'execution.json').read_text())['commands'][0]['returncode'], 1)

    def test_second_control_attempt_cannot_overwrite_evidence(self):
        root, policy, tools = create()
        out = complete(root, policy)
        saved = (root / 'results-controls/LATEST').read_bytes()
        with self.assertRaises(FileExistsError): complete(root, policy)
        self.assertEqual((root / 'results-controls/LATEST').read_bytes(), saved)
        self.assertTrue((out / 'execution.json').exists())

    def test_registered_step_and_grade_parameters_unchanged(self):
        import ast
        import hashlib
        old = PACKET / 'tests/reference/fix4'
        for line in (old / 'SHA256SUMS').read_text().splitlines():
            expected, name = line.split('  ', 1)
            self.assertEqual(hashlib.sha256((old / name).read_bytes()).hexdigest(), expected)
        for name in ('steps.py', 'phase_binding.py', 'compute_bounds.py', 'grade_soak.py',
                     'grade_faults.py', 'selftest_grader.py', 'project_streams.py',
                     'tail.py', 'capture_stall.py', 'sample_cgroup.py'):
            current = (PACKET / 'stage2' / name).read_bytes()
            previous = (old / 'stage2' / name).read_bytes().replace(
                b'/opt/rc6-f101-counter', b'/opt/rc6-f101-age-r5')
            if name in ('grade_soak.py', 'tail.py'):
                # Only these two module docstrings changed to describe the new
                # age gate. Preserve every remaining byte, including comments.
                stripped = []
                for source in (current, previous):
                    tree = ast.parse(source)
                    self.assertIsInstance(tree.body[0], ast.Expr)
                    self.assertIsInstance(tree.body[0].value, ast.Constant)
                    self.assertIsInstance(tree.body[0].value.value, str)
                    doc = tree.body[0]
                    lines = source.splitlines(keepends=True)
                    stripped.append(b''.join(lines[:doc.lineno - 1] + lines[doc.end_lineno:]))
                self.assertEqual(*stripped, name)
            else:
                self.assertEqual(current, previous, name)
        for name in ('portable_pidfd.py', 'lifetime.py'):
            self.assertEqual((PACKET / 'candidate' / name).read_bytes(),
                             (old / 'candidate' / name).read_bytes())
        # EXITDEAD amendment (PREREG-COUNTER-AMENDMENT-ADDENDUM-EXITDEAD.md): owned_tree.py is pinned to
        # the amended bytes. The fix4 reference stays frozen (SHA256SUMS above), and only read_stat,
        # `import time` and the two EXIT_DEAD constants may differ from it.
        current = (PACKET / 'candidate/owned_tree.py').read_bytes()
        self.assertEqual(hashlib.sha256(current).hexdigest(),
                         'b7b4b28cfb15f3b19ff3ac977983605316a7c179ad7b0ed55acbd9c7b2088d6d')
        amended = {'read_stat', 'time', 'EXIT_DEAD_REREADS', 'EXIT_DEAD_PAUSE'}
        def frozen(source, extra):
            names = []
            for node in ast.parse(source).body:
                name = getattr(node, 'name', None) or \
                    ([alias.name for alias in node.names] if isinstance(node, ast.Import) else
                     [target.id for target in node.targets] if isinstance(node, ast.Assign) else [None])[0]
                if name in amended:
                    names.append(name)
                    continue
                extra.append(ast.dump(node))
            return names
        kept_old, kept_new = [], []
        self.assertEqual(frozen((old / 'candidate/owned_tree.py').read_bytes(), kept_old), ['read_stat'])
        self.assertEqual(frozen(current, kept_new), ['time', 'EXIT_DEAD_REREADS', 'EXIT_DEAD_PAUSE', 'read_stat'])
        self.assertEqual(kept_new, kept_old)


if __name__ == '__main__': unittest.main()
