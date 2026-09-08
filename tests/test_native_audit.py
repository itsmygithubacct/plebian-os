"""Command-boundary tests, not actual installed dpkg/trigger qualification."""
from contextlib import contextmanager
from pathlib import Path
import unittest
from unittest.mock import patch

from test_native_transaction import runtime


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.backend = runtime.Dpkg(None, None)
        self.events = []
        self.population = b'dpkg\nlibc-bin\nlibkilix-encodec\nunrelated:amd64\n'
        self.pre_output = self.post_output = self.query_error = b''
        self.pre_error = self.post_error = b''
        self.mutated = False
        self.mutation_error = None

        @contextmanager
        def mutation():
            self.events.append('release-backend')
            try:
                yield
            finally:
                self.events.append('reacquire-backend')

        def run(argv, **_kwargs):
            self.events.append(argv)
            if argv[0] == '/usr/bin/dpkg-query':
                return 0, self.population, self.query_error
            if '--audit' in argv:
                if self.mutated:
                    return 0, self.post_output, self.post_error
                return 0, self.pre_output, self.pre_error
            self.mutated = True
            if self.mutation_error:
                raise self.mutation_error
            return 0, b'actual command substituted by unit test\n', b''

        self.backend.mutation = mutation
        self.backend.run = run

    def test_install_has_named_preflight_normal_triggers_and_full_post_audit(self):
        self.backend.install(Path('/selected/cache.deb'))
        self.assertEqual(self.events, [
            ['/usr/bin/dpkg-query', '--admindir=/var/lib/dpkg', '--show', '--showformat=${binary:Package}\n'],
            ['/usr/bin/dpkg', '--admindir=/var/lib/dpkg', '--root=/', '--audit',
             'dpkg', 'libc-bin', 'unrelated:amd64'],
            'release-backend',
            ['/usr/bin/dpkg', '--admindir=/var/lib/dpkg', '--root=/', '--triggers', '--install', '/selected/cache.deb'],
            'reacquire-backend',
            ['/usr/bin/dpkg', '--admindir=/var/lib/dpkg', '--root=/', '--audit'],
        ])

    def test_purge_selects_only_managed_package_and_audits_after_lock_reacquisition(self):
        self.backend.purge()
        self.assertEqual(self.events[3][-3:], ['--triggers', '--purge', 'libkilix-encodec'])
        self.assertEqual(self.events[-2], 'reacquire-backend')
        self.assertEqual(self.events[-1][-1], '--audit')

    def test_zero_exit_with_pending_or_stderr_refuses_before_mutation(self):
        for field in ('pre_output', 'pre_error'):
            with self.subTest(field=field):
                setattr(self, field, b'pending unrelated or libc-bin package\n')
                with self.assertRaisesRegex(runtime.state.UnsafeState, 'audit is not clean'):
                    self.backend.purge()
                self.assertFalse(self.mutated)
                self.assertNotIn('release-backend', self.events)
                setattr(self, field, b'')

    def test_zero_exit_with_dirty_post_audit_cannot_report_success(self):
        for field in ('post_output', 'post_error'):
            with self.subTest(field=field):
                self.mutated = False
                setattr(self, field, b'unfinished trigger\n')
                with self.assertRaisesRegex(runtime.state.UnsafeState, 'audit is not clean'):
                    self.backend.purge()
                self.assertTrue(self.mutated)
                self.assertEqual(self.events[-2], 'reacquire-backend')
                setattr(self, field, b'')

    def test_missing_duplicate_malformed_and_unbounded_population_refuse(self):
        for data in (b'', b'dpkg\n', b'dpkg\nlibc-bin\ndpkg\n',
                     b'dpkg\nlibc-bin\n--pending\n', b'dpkg\nlibc-bin\nname*\n',
                     b'dpkg\nlibc-bin', b'x' * (512 * 1024 + 1),
                     b'dpkg\nlibc-bin\n' + b'package\n' * 10000):
            with self.subTest(bytes=len(data)):
                self.population = data
                with self.assertRaises(runtime.state.UnsafeState):
                    self.backend.purge()
                self.assertFalse(self.mutated)

    def test_enumeration_warning_refuses_before_lock_handoff(self):
        self.query_error = b'query warning\n'
        with self.assertRaises(runtime.state.UnsafeState):
            self.backend.purge()
        self.assertFalse(self.mutated)

    def test_mutation_error_reacquires_lock_without_claiming_clean_post_state(self):
        self.mutation_error = runtime.processes.CommandFailed('fixture maintainer failure')
        with self.assertRaises(runtime.processes.CommandFailed):
            self.backend.purge()
        self.assertEqual(self.events[-1], 'reacquire-backend')

    def test_verify_never_accepts_absence_without_whole_database_audit(self):
        self.pre_output = b'libc-bin has pending work\n'
        with patch.object(self.backend, 'snapshot') as snapshot:
            with self.assertRaises(runtime.state.UnsafeState):
                self.backend.verify(None)
            snapshot.assert_not_called()
        self.assertEqual(self.events[-1][-1], '--audit')

    def test_mutation_without_manager_lock_ownership_is_inert(self):
        self.backend.mutation = None
        for call in (self.backend.purge, lambda: self.backend.install(Path('/selected/cache.deb'))):
            with self.assertRaises(runtime.state.UnsafeState):
                call()
        self.assertEqual(self.events, [])


if __name__ == '__main__':
    unittest.main()
