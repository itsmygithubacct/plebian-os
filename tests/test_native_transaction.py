"""Journal/cache transaction tests with an explicitly synthetic dpkg backend.

These exercise real private filesystem state and inert selected artifacts.
They do not substitute for actual dpkg/package/maintainer-script integration.
"""
import copy
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import test_native_package as fixtures

MODULE = Path(__file__).resolve().parents[1] / 'provision/native_runtime.py'
spec = importlib.util.spec_from_file_location('native_runtime_tested', MODULE)
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class SyntheticDpkg:
    def __init__(self, populations):
        self.populations = populations
        self.installed = None
        self.damage = None
        self.guard = lambda: None
        self.calls = []
        self.fail_install = False
        self.fail_dependencies = False

    def snapshot(self):
        self.guard()
        return copy.deepcopy({'installed': self.installed, 'damage': self.damage})

    def verify(self, metadata):
        runtime.need(self.installed == (metadata['sha256'] if metadata else None) and self.damage is None,
                     'synthetic installed identity differs')
        return self.snapshot()

    def dependencies(self, _metadata):
        self.guard()
        runtime.need(not self.fail_dependencies, 'synthetic dependency failure')

    def install(self, path):
        self.guard()
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        assert digest in self.populations
        self.calls.append(('install', digest))
        self.installed, self.damage = digest, None
        if self.fail_install:
            raise RuntimeError('synthetic maintainer failure after replacement')

    def purge(self):
        self.guard()
        self.calls.append(('purge', self.installed))
        self.installed, self.damage = None, None

    def recovery_observer(self):
        return lambda: None


class TransactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.first = fixtures.fixture()
        cls.second = fixtures.fixture(source_commit='d' * 40, version_base='0.0.2')
        cls.rows = {}
        for data, source in ((cls.first, fixtures.SOURCE), (cls.second, 'd' * 40)):
            row = runtime.artifact.inspect_package(data, sha256=hashlib.sha256(data).hexdigest(),
                byte_count=len(data), source_commit=source, content_commit=fixtures.CONTENT)
            cls.rows[row['sha256']] = row

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.tree = runtime.state.Tree(self.root, uid=os.getuid())
        self.tree.private_directory('var/lib/dpkg')
        self.backend = SyntheticDpkg(self.rows)
        self.manager = runtime.Manager(self.tree, self.backend)
        self.fd_count = len(os.listdir('/proc/self/fd'))
        self.sentinel = self.root / 'unrelated-package-status'
        self.sentinel.write_bytes(b'operator and unrelated package state\n')

    def tearDown(self):
        self.assertEqual(self.sentinel.read_bytes(), b'operator and unrelated package state\n')
        self.assertEqual(len(os.listdir('/proc/self/fd')), self.fd_count)
        self.tree.close()
        self.temporary.cleanup()

    def prepare(self, second=False, transaction=None):
        raw = self.second if second else self.first
        row = self.rows[hashlib.sha256(raw).hexdigest()]
        return self.manager.prepare(raw, transaction=transaction,
            sha256=row['sha256'], byte_count=row['bytes'],
            source_commit=row['source_commit'], content_commit=row['content_commit'])

    def seed(self):
        token = self.prepare()
        self.manager.apply(token)
        self.manager.commit(token)
        self.manager.finish(token)
        self.backend.calls.clear()

    def journal(self, token):
        return self.manager.read_json(self.manager.journal_name(token))

    def test_absent_prepare_is_inert_and_apply_is_not_outer_commit(self):
        token = self.prepare()
        self.assertEqual(self.backend.calls, [])
        self.assertIsNone(self.backend.installed)
        self.manager.apply(token)
        self.assertEqual(self.journal(token)['phase'], 'applied')
        self.assertIsNone(self.manager.read_json(runtime.CURRENT, missing=True))
        self.assertEqual(self.manager.read_json(runtime.ACTIVE), {'transaction': token})

    def test_caller_token_is_exact_and_collision_preserves_history(self):
        token = '1' * 32
        self.assertEqual(self.prepare(transaction=token), token)
        self.manager.rollback(token)
        before = self.journal(token)
        with self.assertRaises(FileExistsError):
            self.prepare(transaction=token)
        self.assertEqual(self.journal(token), before)
        self.assertIsNone(self.manager.read_json(runtime.ACTIVE, missing=True))
        self.assertEqual(self.backend.calls, [])

    def test_invalid_caller_tokens_refuse_without_state_or_inspection(self):
        for token in ('', '../wrong', 'A' * 32, '0' * 31, '0' * 33, 7):
            with self.subTest(token=token), patch.object(runtime.artifact, 'inspect_package') as inspect:
                with self.assertRaises(ValueError):
                    self.manager.prepare(b'not inspected', transaction=token)
                inspect.assert_not_called()
        self.assertFalse((self.root / runtime.BASE).exists())

    def test_unstarted_exact_token_rollback_does_not_touch_current_or_foreign_owner(self):
        token = '2' * 32
        self.seed()
        before = self.manager.read_json(runtime.CURRENT)
        self.manager.rollback(token, allow_unpublished=True)
        self.assertEqual(self.manager.read_json(runtime.CURRENT), before)
        self.assertEqual(self.backend.calls, [])
        other = self.prepare(second=True)
        journal = self.journal(other)
        with self.assertRaisesRegex(ValueError, 'active owner'):
            self.manager.rollback(token, allow_unpublished=True)
        self.assertEqual(self.journal(other), journal)
        self.assertEqual(self.manager.read_json(runtime.ACTIVE), {'transaction': other})
        self.manager.rollback(other)

    def test_foreign_active_diagnostics_name_actual_owner_without_publishing_caller(self):
        owner, caller = '6' * 32, '7' * 32
        self.prepare(transaction=owner)
        self.manager.apply(owner)
        before = self.journal(owner)
        calls = list(self.backend.calls)
        with self.assertRaisesRegex(ValueError, 'already active; active token ' + owner):
            self.prepare(second=True, transaction=caller)
        with self.assertRaisesRegex(ValueError, 'not the active owner; active token ' + owner):
            self.manager.rollback(caller, allow_unpublished=True)
        self.assertEqual(self.manager.read_json(runtime.ACTIVE), {'transaction': owner})
        self.assertEqual(self.journal(owner), before)
        self.assertEqual(self.backend.calls, calls)
        self.assertFalse((self.root / runtime.BASE / 'transactions' / caller).exists())
        self.manager.rollback(owner)

    def test_active_owner_diagnostics_do_not_echo_invalid_state_as_a_token(self):
        self.assertEqual(runtime.describe_active_owner(None), 'no active token')
        for value in ({}, [], 'hostile\nstate', {'transaction': 'bad\ntoken'},
                      {'transaction': 1}, {'transaction': 'A' * 32},
                      {'transaction': 'a' * 32, 'extra': 'untrusted'}):
            self.assertEqual(runtime.describe_active_owner(value),
                             'active owner unavailable (invalid record)')
        with self.assertRaisesRegex(ValueError, 'not the active owner; no active token'):
            self.manager.rollback('8' * 32)
        self.assertEqual(self.backend.calls, [])

    def test_prepare_publication_failure_is_recoverable_only_by_its_recorded_token(self):
        token = '3' * 32
        original = self.manager.write_json

        def fail_active(name, value, **kwargs):
            if name == runtime.ACTIVE:
                raise OSError('fixture active publication failure')
            return original(name, value, **kwargs)

        with patch.object(self.manager, 'write_json', side_effect=fail_active):
            with self.assertRaisesRegex(OSError, 'publication failure'):
                self.prepare(transaction=token)
        self.assertEqual(self.journal(token)['phase'], 'prepared')
        self.assertIsNone(self.manager.read_json(runtime.ACTIVE, missing=True))
        with self.assertRaisesRegex(ValueError, 'active owner'):
            self.manager.rollback(token)
        self.manager.rollback(token, allow_unpublished=True)
        self.assertEqual(self.journal(token)['phase'], 'rolled-back')
        self.manager.rollback(token, allow_unpublished=True)
        self.assertEqual(self.backend.calls, [])

    def test_unpublished_recovery_does_not_waive_changed_state_or_missing_authority(self):
        token = self.prepare(transaction='4' * 32)
        self.tree.remove_state(runtime.ACTIVE, runtime.state.canonical({'transaction': token}))
        before = self.journal(token)
        self.backend.damage = 'unrelated modification'
        with self.assertRaises(ValueError):
            self.manager.rollback(token, allow_unpublished=True)
        self.assertEqual(self.journal(token), before)
        self.backend.damage = None
        cache = self.root / self.manager.cache_name(before['new'])
        cache.unlink()
        with self.assertRaises(FileNotFoundError):
            self.manager.rollback(token, allow_unpublished=True)
        self.assertEqual(self.journal(token), before)
        self.assertEqual(self.backend.calls, [])

    def test_unpublished_option_never_claims_an_applied_or_finished_journal(self):
        token = self.prepare(transaction='5' * 32)
        self.manager.apply(token)
        self.tree.remove_state(runtime.ACTIVE, runtime.state.canonical({'transaction': token}))
        before = self.journal(token)
        calls = list(self.backend.calls)
        with self.assertRaisesRegex(ValueError, 'unpublished preparation'):
            self.manager.rollback(token, allow_unpublished=True)
        self.assertEqual(self.journal(token), before)
        self.assertEqual(self.backend.calls, calls)
        self.tree.write(runtime.ACTIVE, runtime.state.canonical({'transaction': token}))
        self.manager.commit(token)
        self.manager.finish(token)
        current = self.manager.read_json(runtime.CURRENT)
        with self.assertRaisesRegex(ValueError, 'unpublished preparation'):
            self.manager.rollback(token, allow_unpublished=True)
        self.assertEqual(self.manager.read_json(runtime.CURRENT), current)

    def test_success_commit_keeps_rollback_until_explicit_outer_finish(self):
        token = self.prepare()
        self.manager.apply(token)
        self.manager.commit(token)
        self.assertEqual(self.journal(token)['phase'], 'committed')
        self.assertIsNotNone(self.manager.read_json(runtime.ACTIVE))
        self.manager.rollback(token)
        self.assertIsNone(self.backend.installed)
        self.assertIsNone(self.manager.read_json(runtime.CURRENT, missing=True))
        self.assertIsNone(self.manager.read_json(runtime.ACTIVE, missing=True))
        self.assertEqual(self.journal(token)['phase'], 'rolled-back')

    def test_finished_install_and_exact_old_package_upgrade_rollback(self):
        self.seed()
        old = self.manager.read_json(runtime.CURRENT)
        token = self.prepare(second=True)
        self.manager.apply(token)
        self.manager.rollback(token)
        self.assertEqual(self.manager.read_json(runtime.CURRENT), old)
        self.assertEqual(self.backend.installed, old['sha256'])
        self.assertEqual([call[0] for call in self.backend.calls], ['install', 'install'])

    def test_successful_upgrade_changes_current_only_after_commit(self):
        self.seed()
        old = self.manager.read_json(runtime.CURRENT)
        token = self.prepare(second=True)
        self.manager.apply(token)
        self.assertEqual(self.manager.read_json(runtime.CURRENT), old)
        self.manager.commit(token)
        self.assertNotEqual(self.manager.read_json(runtime.CURRENT), old)
        self.manager.finish(token)
        self.assertIsNone(self.manager.read_json(runtime.ACTIVE, missing=True))

    def test_unapplied_rollback_makes_no_package_call(self):
        token = self.prepare()
        self.manager.rollback(token)
        self.assertEqual(self.backend.calls, [])

    def test_failed_partial_apply_retains_exact_post_state_and_recovers(self):
        self.seed()
        old = self.backend.installed
        token = self.prepare(second=True)
        self.backend.fail_install = True
        with self.assertRaises(RuntimeError):
            self.manager.apply(token)
        journal = self.journal(token)
        self.assertEqual(journal['phase'], 'failed')
        self.assertEqual(journal['after'], self.backend.snapshot())
        self.backend.fail_install = False
        self.manager.rollback(token)
        self.assertEqual(self.backend.installed, old)

    def test_failed_fresh_apply_is_purged_only_for_this_package(self):
        token = self.prepare()
        self.backend.fail_install = True
        with self.assertRaises(RuntimeError):
            self.manager.apply(token)
        self.manager.rollback(token)
        self.assertEqual(self.backend.calls[-1][0], 'purge')
        self.assertIsNone(self.backend.installed)

    def test_dependency_failure_precedes_any_install_and_can_rollback_prepared(self):
        token = self.prepare()
        self.backend.fail_dependencies = True
        with self.assertRaises(runtime.state.UnsafeState):
            self.manager.apply(token)
        self.assertEqual(self.backend.calls, [])
        self.assertEqual(self.journal(token)['phase'], 'prepared')
        self.manager.rollback(token)

    def test_unknown_existing_installation_is_never_adopted(self):
        self.backend.installed = 'unowned-package'
        with self.assertRaises(runtime.state.UnsafeState):
            self.prepare()
        self.assertEqual(self.backend.calls, [])
        self.assertFalse((self.root / runtime.ACTIVE).exists())

    def test_corrupted_or_missing_prior_archive_prevents_replacement(self):
        self.seed()
        old = self.manager.read_json(runtime.CURRENT)
        path = self.root / self.manager.cache_name(old)
        raw = path.read_bytes()
        path.write_bytes(b'corrupt')
        with self.assertRaises(runtime.artifact.InvalidPackage):
            self.prepare(second=True)
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            self.prepare(second=True)
        path.write_bytes(raw)
        path.chmod(0o600)
        self.assertEqual(self.backend.calls, [])

    def test_another_active_transaction_blocks_before_package_mutation(self):
        token = self.prepare()
        with self.assertRaises(runtime.state.UnsafeState):
            self.prepare(second=True)
        self.assertEqual(self.backend.calls, [])
        self.assertEqual(self.manager.read_json(runtime.ACTIVE), {'transaction': token})

    def test_external_changes_after_prepare_and_apply_are_not_overwritten(self):
        token = self.prepare()
        self.backend.damage = 'operator change'
        with self.assertRaises(runtime.state.UnsafeState):
            self.manager.apply(token)
        with self.assertRaises(runtime.state.UnsafeState):
            self.manager.rollback(token)
        self.assertEqual(self.backend.calls, [])
        self.backend.damage = None
        self.manager.apply(token)
        self.backend.damage = 'unrelated root changed native files'
        for command in (self.manager.commit, self.manager.rollback):
            with self.assertRaises(runtime.state.UnsafeState):
                command(token)
        self.assertEqual(len(self.backend.calls), 1)

    def test_recovery_failure_retains_retryable_exact_post_state(self):
        self.seed()
        old = self.backend.installed
        token = self.prepare(second=True)
        self.manager.apply(token)
        self.backend.fail_install = True
        with self.assertRaises(RuntimeError):
            self.manager.rollback(token)
        journal = self.journal(token)
        self.assertEqual(journal['phase'], 'recovery-failed')
        self.assertEqual(journal['after'], self.backend.snapshot())
        self.assertIsNotNone(self.manager.read_json(runtime.ACTIVE))
        self.backend.fail_install = False
        self.manager.rollback(token)
        self.assertEqual(self.backend.installed, old)

    def test_missing_post_observation_refuses_unsafe_recovery(self):
        token = self.prepare()
        with self.manager.locked():
            journal = self.manager.load(token)
            journal['phase'] = 'applying'
            self.manager.save(journal)
        with self.assertRaises(runtime.state.UnsafeState):
            self.manager.rollback(token)
        self.assertEqual(self.backend.calls, [])

    def test_invalid_tokens_and_premature_commit_finish_refuse(self):
        for token in ('../escape', 'A' * 32, '', 'a' * 31):
            with self.assertRaises(runtime.state.UnsafeState):
                self.manager.apply(token)
        token = self.prepare()
        for command in (self.manager.commit, self.manager.finish):
            with self.assertRaises(runtime.state.UnsafeState):
                command(token)
        self.assertEqual(self.backend.calls, [])

    def test_commit_journal_write_failure_still_allows_outer_rollback(self):
        token = self.prepare()
        self.manager.apply(token)
        with patch.object(self.manager, 'save', side_effect=OSError('fixture journal fsync failure')):
            with self.assertRaises(OSError):
                self.manager.commit(token)
        self.assertEqual(self.journal(token)['phase'], 'applied')
        self.assertIsNotNone(self.manager.read_json(runtime.CURRENT))
        self.manager.rollback(token)
        self.assertIsNone(self.backend.installed)

    def test_late_cancel_during_post_state_observation_cannot_report_applied(self):
        token = self.prepare()
        def observer():
            def original_authority():
                raise runtime.processes.CommandFailed('fixture original operation canceled')
            return original_authority
        with patch.object(self.backend, 'recovery_observer', side_effect=observer):
            with self.assertRaises(runtime.processes.CommandFailed):
                self.manager.apply(token)
        self.assertEqual(self.journal(token)['phase'], 'failed')
        self.assertEqual(self.journal(token)['after'], self.backend.snapshot())
        self.manager.rollback(token)
        self.assertIsNone(self.backend.installed)

    def test_rollback_post_observation_must_still_match_prior_state(self):
        self.seed()
        token = self.prepare(second=True)
        self.manager.apply(token)
        self.manager.commit(token)
        current = self.manager.read_json(runtime.CURRENT)
        before = self.journal(token)['before']

        def observer():
            self.backend.damage = 'change after rollback verification'
            return lambda: None

        with patch.object(self.backend, 'recovery_observer', side_effect=observer):
            with self.assertRaisesRegex(runtime.state.UnsafeState, 'post-observation differs'):
                self.manager.rollback(token)
        journal = self.journal(token)
        self.assertEqual(journal['phase'], 'recovery-failed')
        self.assertEqual(journal['before'], before)
        self.assertNotEqual(journal['after'], before)
        self.assertEqual(journal['after'], self.backend.snapshot())
        self.assertEqual(self.manager.read_json(runtime.CURRENT), current)
        self.assertEqual(self.manager.read_json(runtime.ACTIVE), {'transaction': token})
        self.manager.rollback(token)
        self.assertEqual(self.backend.snapshot(), before)
        self.assertEqual(self.journal(token)['phase'], 'rolled-back')

    def test_rollback_post_observer_preserves_original_cancel_and_deadline(self):
        for reason in ('canceled', 'deadline expired'):
            with self.subTest(reason=reason):
                token = self.prepare()
                self.manager.apply(token)
                self.manager.commit(token)
                current = self.manager.read_json(runtime.CURRENT)

                def observer():
                    def original_authority():
                        raise runtime.processes.CommandFailed('fixture original operation ' + reason)
                    return original_authority

                with patch.object(self.backend, 'recovery_observer', side_effect=observer):
                    with self.assertRaisesRegex(runtime.processes.CommandFailed, reason):
                        self.manager.rollback(token)
                journal = self.journal(token)
                self.assertEqual(journal['phase'], 'recovery-failed')
                self.assertEqual(journal['after'], journal['before'])
                self.assertEqual(self.backend.snapshot(), journal['before'])
                self.assertEqual(self.manager.read_json(runtime.CURRENT), current)
                self.assertEqual(self.manager.read_json(runtime.ACTIVE), {'transaction': token})
                self.manager.rollback(token)
                self.assertIsNone(self.manager.read_json(runtime.ACTIVE, missing=True))
                self.assertIsNone(self.manager.read_json(runtime.CURRENT, missing=True))

    def test_actual_frontend_and_database_lock_handoff(self):
        def probe():
            code = ('import fcntl,json,sys\nfrom pathlib import Path\nresult={}\n'
                    'for name in ("lock-frontend","lock"):\n'
                    ' with (Path(sys.argv[1])/name).open("r+") as f:\n'
                    '  try: fcntl.lockf(f,fcntl.LOCK_EX|fcntl.LOCK_NB); result[name]=True\n'
                    '  except BlockingIOError: result[name]=False\n'
                    'print(json.dumps(result))\n')
            result = subprocess.run(['/usr/bin/python3', '-I', '-B', '-c', code,
                                     str(self.root / 'var/lib/dpkg')], capture_output=True, timeout=3)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            return runtime.json.loads(result.stdout)
        with self.manager.locked():
            self.assertEqual(probe(), {'lock-frontend': False, 'lock': False})
            with self.backend.mutation():
                self.assertEqual(probe(), {'lock-frontend': False, 'lock': True})
            self.assertEqual(probe(), {'lock-frontend': False, 'lock': False})
        self.assertEqual(probe(), {'lock-frontend': True, 'lock': True})

    def test_database_lock_name_replacement_during_handoff_refuses(self):
        with self.assertRaises(runtime.state.UnsafeState):
            with self.manager.locked():
                with self.backend.mutation():
                    path = self.root / 'var/lib/dpkg/lock'
                    path.rename(path.with_name('prior-lock'))
                    path.write_bytes(b'')
                    self.manager.check()
        self.assertEqual(self.backend.calls, [])

    def test_nested_mutation_is_not_a_second_lock_owner(self):
        with self.manager.locked():
            with self.backend.mutation():
                with self.assertRaises(runtime.state.UnsafeState):
                    with self.backend.mutation():
                        self.fail('nested mutation entered')
            self.manager.check()


if __name__ == '__main__':
    unittest.main()
