"""Real private filesystem operations; never system package mutation."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'provision/native_state.py'
spec = importlib.util.spec_from_file_location('native_state_tested', MODULE)
state = importlib.util.module_from_spec(spec)
spec.loader.exec_module(state)


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.tree = state.Tree(self.root, uid=os.getuid())
        self.tree.private_directory('managed')
        self.before_fds = len(os.listdir('/proc/self/fd'))

    def tearDown(self):
        self.assertEqual(len(os.listdir('/proc/self/fd')), self.before_fds)
        self.tree.close()
        self.temporary.cleanup()

    def test_exclusive_and_atomic_replacement_are_exact_and_private(self):
        self.tree.write('managed/file', b'old')
        self.assertEqual(self.tree.read('managed/file', maximum=3, mode=0o600), b'old')
        with self.assertRaises(FileExistsError):
            self.tree.write('managed/file', b'bad')
        self.tree.write('managed/file', b'new', replace=True)
        self.assertEqual(self.tree.read('managed/file', maximum=3), b'new')
        self.assertEqual(sorted(p.name for p in (self.root / 'managed').iterdir()), ['file'])

    def test_unsafe_relative_paths_refuse_without_escape(self):
        for name in ('', '/etc/passwd', '../escape', 'managed/../escape', './managed', 'managed//file'):
            with self.subTest(name=name), self.assertRaises(state.UnsafeState):
                self.tree.write(name, b'no')

    def test_directory_links_and_writable_ancestors_refuse(self):
        (self.root / 'alias').symlink_to(self.root / 'managed', target_is_directory=True)
        with self.assertRaises(OSError):
            self.tree.write('alias/file', b'no')
        (self.root / 'managed').chmod(0o777)
        try:
            with self.assertRaises(state.UnsafeState):
                self.tree.write('managed/file', b'no')
        finally:
            (self.root / 'managed').chmod(0o700)

    def test_private_directory_does_not_chmod_existing_operator_directory(self):
        path = self.root / 'public'
        path.mkdir(mode=0o755)
        path.chmod(0o755)  # Fixture must not inherit the test job's private umask.
        self.assertEqual(path.stat().st_mode & 0o777, 0o755)
        with self.assertRaises(state.UnsafeState):
            self.tree.private_directory('public')
        self.assertEqual(path.stat().st_mode & 0o777, 0o755)

    def test_read_and_replace_refuse_links_fifo_hardlinks_and_writable_files(self):
        target = self.root / 'managed/target'
        target.write_bytes(b'untouched')
        target.chmod(0o600)
        path = self.root / 'managed/file'
        builders = (
            lambda: path.symlink_to(target),
            lambda: os.mkfifo(path, 0o600),
            lambda: os.link(target, path),
            lambda: (path.write_bytes(b'writable'), path.chmod(0o666)),
        )
        for build in builders:
            build()
            try:
                for call in (lambda: self.tree.read('managed/file', maximum=100),
                             lambda: self.tree.write('managed/file', b'no', replace=True)):
                    with self.assertRaises(state.UnsafeState):
                        call()
                self.assertEqual(target.read_bytes(), b'untouched')
            finally:
                path.unlink()

    def test_bounded_reads_and_missing_entry(self):
        self.assertIsNone(self.tree.read('managed/none', maximum=1, missing=True))
        self.tree.write('managed/file', b'four')
        with self.assertRaises(state.UnsafeState):
            self.tree.read('managed/file', maximum=3)
        with self.assertRaises(state.UnsafeState):
            self.tree.read('managed/file', maximum=4, mode=0o644)

    def test_read_memory_failure_closes_held_and_read_descriptors(self):
        self.tree.write('managed/file', b'four')
        with patch.object(state.os, 'read', side_effect=MemoryError), self.assertRaises(MemoryError):
            self.tree.read('managed/file', maximum=4)

    def test_changed_input_name_is_not_accepted_from_held_old_inode(self):
        self.tree.write('managed/file', b'four')
        original = state.os.read
        changed = False
        def replace(fd, count):
            nonlocal changed
            result = original(fd, count)
            if not changed:
                changed = True
                (self.root / 'managed/file').rename(self.root / 'managed/old')
                (self.root / 'managed/file').write_bytes(b'new!')
            return result
        with patch.object(state.os, 'read', side_effect=replace), self.assertRaises(state.UnsafeState):
            self.tree.read('managed/file', maximum=4)

    def test_failed_write_preserves_previous_and_retires_only_own_temporary(self):
        self.tree.write('managed/file', b'old')
        sentinel = self.root / 'managed/unrelated'
        sentinel.write_bytes(b'keep')
        with patch.object(state.os, 'fsync', side_effect=OSError('fixture fsync failure')):
            with self.assertRaises(OSError):
                self.tree.write('managed/file', b'new', replace=True)
        self.assertEqual((self.root / 'managed/file').read_bytes(), b'old')
        self.assertEqual(sentinel.read_bytes(), b'keep')
        self.assertEqual(sorted(p.name for p in sentinel.parent.iterdir()), ['file', 'unrelated'])

    def test_state_removal_requires_expected_bytes(self):
        self.tree.write('managed/file', b'old')
        with self.assertRaises(state.UnsafeState):
            self.tree.remove_state('managed/file', b'wrong')
        self.tree.remove_state('managed/file', b'old')
        self.assertFalse((self.root / 'managed/file').exists())

    def test_fingerprints_are_exact_and_do_not_follow_link(self):
        self.tree.write('managed/file', b'four')
        self.assertEqual(self.tree.fingerprint('managed/file'), {
            'bytes': 4, 'mode': 0o600, 'uid': os.getuid(), 'gid': os.getgid(),
            'sha256': state.hashlib.sha256(b'four').hexdigest()})
        (self.root / 'managed/link').symlink_to('/outside/missing')
        self.assertEqual(self.tree.fingerprint('managed/link'), {
            'link': '/outside/missing', 'uid': os.getuid(), 'gid': os.getgid()})
        self.assertIsNone(self.tree.fingerprint('absent/parent/file'))

    def test_named_lock_replacement_refuses(self):
        with self.assertRaises(state.UnsafeState):
            with self.tree.lock('managed/lock') as check:
                (self.root / 'managed/lock').rename(self.root / 'managed/old-lock')
                (self.root / 'managed/lock').write_bytes(b'')
                check()

    def test_locks_refuse_nonregular_nodes_before_io(self):
        for kind in ('fifo', 'link', 'directory'):
            path = self.root / 'managed/lock'
            if kind == 'fifo':
                os.mkfifo(path, 0o600)
            elif kind == 'link':
                path.symlink_to('/dev/null')
            else:
                path.mkdir(mode=0o700)
            try:
                with self.assertRaises(state.UnsafeState):
                    with self.tree.lock('managed/lock'):
                        self.fail('unsafe lock admitted')
            finally:
                path.rmdir() if kind == 'directory' else path.unlink()


if __name__ == '__main__':
    unittest.main()
