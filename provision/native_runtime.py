#!/usr/bin/env python3
"""One-package prepare/apply/commit/finish/rollback for the selected OS runtime.

Run only as root, through the fixed deployed helper, with explicit artifact
authority. Never builds a checkout, downloads, loads a model, restores global
dpkg state, forces dependencies, or adopts an unknown existing installation.
commit remains reversible until the enclosing stack transaction calls finish.
Interrupted/incomplete recovery retains a journal; this is not crash atomicity.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import signal
import sys


def sibling(name):
    # -I deliberately excludes the script directory from sys.path. Load only
    # these fixed sibling modules from the deployed root-owned OS layer.
    spec = importlib.util.spec_from_file_location('_plebian_' + name,
        Path(__file__).resolve().with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


artifact = sibling('native_package')
state = sibling('native_state')
processes = sibling('native_process')
PACKAGE = 'libkilix-encodec'
BASE = 'var/lib/plebian-os/native-runtime'
ACTIVE = BASE + '/active.json'
CURRENT = BASE + '/current.json'
TOKEN = re.compile(r'[0-9a-f]{32}\Z')
INFO = ('list', 'md5sums', 'postinst', 'postrm', 'triggers')
FOOTPRINT = tuple(sorted(artifact.FILES | {artifact.RECORD}))
SCRATCH = tuple(name + ending for name in FOOTPRINT for ending in ('.dpkg-new', '.dpkg-tmp', '.dpkg-old'))
need = state.need


def describe_active_owner(active):
    """Report only a validated token, never arbitrary state bytes in a warning."""
    if active is None:
        return 'no active token'
    if (type(active) is dict and set(active) == {'transaction'}
            and type(active['transaction']) is str
            and TOKEN.fullmatch(active['transaction'])):
        return 'active token ' + active['transaction']
    return 'active owner unavailable (invalid record)'


class Dpkg:
    def __init__(self, tree, runner):
        self.tree = tree
        self.runner = runner
        self.guard = lambda: None
        self.mutation = None

    def run(self, argv, *, accepted=(0,)):
        return self.runner.run(argv, guard=self.guard, accepted=accepted)

    def audit(self, *, exclude_native=False):
        """Refuse pending/unhealthy unrelated work instead of processing it.

        Recovery may start with our exact journal-bound partial package. Audit
        every other named package before that mutation, then the entire database
        after success. A pending libc-bin trigger is NOT an excluded package:
        an unresolved trigger failure retains recovery state for an operator.
        """
        names = []
        if exclude_native:
            _, out, err = self.run(['/usr/bin/dpkg-query', '--admindir=/var/lib/dpkg',
                                   '--show', '--showformat=${binary:Package}\n'])
            need(not err and len(out) <= 512 * 1024 and out.endswith(b'\n'),
                 'cannot enumerate package audit population')
            listed = out.decode('ascii').splitlines()
            need(0 < len(listed) <= 10000 and len(listed) == len(set(listed))
                 and all(re.fullmatch(r'[a-z0-9][a-z0-9+.-]{1,127}(?::[a-z0-9][a-z0-9-]{0,29})?',
                                      name) for name in listed),
                 'invalid package audit population')
            need({'dpkg', 'libc-bin'} <= set(listed), 'incomplete package-manager audit population')
            names = sorted(name for name in listed if name.partition(':')[0] != PACKAGE)
        _, out, err = self.run(['/usr/bin/dpkg', '--admindir=/var/lib/dpkg', '--root=/',
                               '--audit', *names])
        need(not out and not err, 'package-manager audit is not clean; retain state for operator recovery')

    def status(self, name=PACKAGE):
        code, out, err = self.run(['/usr/bin/dpkg-query', '--admindir=/var/lib/dpkg',
            '--show', '--showformat=${Status}\n${Version}\n${Architecture}\n', name], accepted=(0, 1))
        if code == 1:
            need(not out and err == f'dpkg-query: no packages found matching {name}\n'.encode(),
                 'unexpected dpkg-query refusal')
            return None
        values = out.decode('ascii').splitlines()
        need(not err and len(values) == 3, 'unexpected package status population')
        status_text, version, architecture = values
        need(re.fullmatch(r'[a-z-]+ [a-z-]+ [a-z-]+', status_text)
             and re.fullmatch(r'[A-Za-z0-9.+:~_-]{1,150}', version)
             and re.fullmatch(r'[a-z0-9-]{1,30}', architecture), 'malformed package identity')
        return {'status': status_text, 'version': version, 'architecture': architecture}

    def snapshot(self):
        with self.tree.directory('var/lib/dpkg/info') as fd:
            names = os.listdir(fd)
        selected = {name for name in names if name.startswith((PACKAGE + '.', PACKAGE + ':'))}
        allowed = {PACKAGE + '.' + name for name in INFO}
        need(selected <= allowed, 'unexpected native package bookkeeping; manual recovery required')
        return {'status': self.status(),
                'files': {name: self.tree.fingerprint(name) for name in (*FOOTPRINT, *SCRATCH)},
                'info': {name: self.tree.fingerprint('var/lib/dpkg/info/' + PACKAGE + '.' + name)
                         for name in INFO}}

    def dependencies(self, metadata):
        for name, version in metadata['dependencies'].items():
            need(self.status(name) == {'status': 'install ok installed', 'version': version,
                                      'architecture': 'amd64'},
                 'native dependency is not the exact installed selection: ' + name)
        for name, expected in metadata['runtime_files'].items():
            self.runner.check()
            self.guard()
            actual = self.tree.fingerprint('usr/lib/x86_64-linux-gnu/' + name, maximum=96 * 1024**2)
            need(actual is not None and actual.get('mode') in (0o644, 0o755)
                 and actual.get('uid') == actual.get('gid') == 0
                 and {key: actual.get(key) for key in ('bytes', 'sha256')} == expected,
                 'native runtime dependency bytes differ: ' + name)
            self.runner.check()
            self.guard()

    def loader_health(self, metadata):
        """Only after exact installed-file verification; never an inert probe."""
        _, output, _ = self.run(['/usr/bin/ldd', '/usr/lib/libkilix-encodec.so.0'])
        actual = set()
        for line in output.decode('ascii').splitlines():
            if re.fullmatch(r'\s*linux-vdso\.so\.[0-9]+ \(0x[0-9a-f]+\)\s*', line):
                continue
            match = re.fullmatch(r'\s*(?:[A-Za-z0-9_+.-]+ => )?(/[^\s]+) \(0x[0-9a-f]+\)\s*', line)
            need(match is not None, 'native loader reports a missing or unrecognized dependency')
            resolved = Path(match.group(1)).resolve(strict=True)
            need(resolved.parent == Path('/usr/lib/x86_64-linux-gnu') and resolved.name not in actual,
                 'native loader selected an unexpected dependency origin')
            actual.add(resolved.name)
        need(actual == set(metadata['runtime_files']), 'native loader closure differs from reviewed package')
        probe = ('import ctypes,json; p=ctypes.CDLL("/usr/lib/libkilix-encodec.so.0"); '
                 'p.kenc_installed_content_commit.restype=ctypes.c_char_p; '
                 'p.kenc_installed_bundle_sha256.restype=ctypes.c_char_p; '
                 'print(json.dumps([p.kenc_installed_content_commit().decode(),'
                 'p.kenc_installed_bundle_sha256().decode()]))')
        _, output, _ = self.run(['/usr/bin/python3', '-I', '-B', '-c', probe])
        need(json.loads(output) == [metadata['content_commit'], metadata['content_bundle_sha256']],
             'installed native Content identity differs at runtime')

    def conflicts(self):
        _, out, err = self.run(['/usr/bin/dpkg-query', '--admindir=/var/lib/dpkg', '--search',
                               *('/' + name for name in FOOTPRINT)], accepted=(0, 1))
        for line in out.decode('utf-8').splitlines():
            owner, separator, name = line.rpartition(': ')
            need(separator and owner == PACKAGE and name.removeprefix('/') in FOOTPRINT,
                 'native path belongs to a different package or diversion')
        expected_errors = {f'dpkg-query: no path found matching pattern /{name}' for name in FOOTPRINT}
        need(set(err.decode('utf-8').splitlines()) <= expected_errors, 'unexpected path ownership error')
        # Diversions or stat overrides can redirect dpkg or change selected file
        # modes despite an otherwise exact archive. Never silently consume them.
        targets = {'/' + name for name in FOOTPRINT}
        for name in FOOTPRINT:
            targets.update('/' + str(parent) for parent in PurePosixPath(name).parents if str(parent) != '.')
        for filename in ('diversions', 'statoverride'):
            raw = self.tree.read('var/lib/dpkg/' + filename, maximum=1024 * 1024, missing=True)
            if raw is None:
                continue
            lines = raw.decode('utf-8').splitlines()
            if filename == 'diversions':
                need(len(lines) % 3 == 0, 'malformed dpkg diversions')
                need(not any(line in targets for index, line in enumerate(lines) if index % 3 != 2),
                     'native path is diverted')
            else:
                for line in lines:
                    values = line.split(' ', 3)
                    need(len(values) == 4 and values[3] not in targets, 'native path has a stat override')

    def verify(self, metadata):
        self.audit()
        observed = self.snapshot()
        if metadata is None:
            need(observed['status'] is None and all(value is None for value in observed['files'].values())
                 and all(value is None for value in observed['info'].values()),
                 'unknown existing native installation; verified rollback archive required')
            self.conflicts()
            return observed
        need(observed['status'] == {'status': 'install ok installed', 'version': metadata['version'],
                                   'architecture': 'amd64'}, 'installed native package identity differs')
        expected_files = {name: row | {'uid': 0, 'gid': 0} for name, row in metadata['files'].items()}
        need(observed['files'] == expected_files | {name: None for name in SCRATCH},
             'installed native files differ from the selected archive')
        self.conflicts()
        self.dependencies(metadata)
        for name, payload in (('postinst', artifact.SCRIPT), ('postrm', artifact.SCRIPT),
                              ('triggers', b'activate-noawait ldconfig\n')):
            need(self.tree.read('var/lib/dpkg/info/' + PACKAGE + '.' + name, maximum=65536,
                                mode=0o644 if name == 'triggers' else 0o755) == payload,
                 'installed maintainer authority differs')
        listed = self.tree.read('var/lib/dpkg/info/' + PACKAGE + '.list', maximum=65536, mode=0o644)
        paths = listed.decode('ascii').splitlines()
        parents = {'/.'}
        for name in FOOTPRINT:
            parents.update('/' + str(parent) for parent in PurePosixPath(name).parents if str(parent) != '.')
        need(len(paths) == len(set(paths)) and set(paths) == parents | {'/' + name for name in FOOTPRINT},
             'installed package file list differs')
        md5sums = self.tree.read('var/lib/dpkg/info/' + PACKAGE + '.md5sums', maximum=65536,
                                 mode=0o644, missing=True)
        if md5sums is not None:
            expected = {hashlib.md5(self.tree.read(name, maximum=artifact.MAX_ARCHIVE)).hexdigest() +
                        '  ' + name for name in FOOTPRINT if name != artifact.LINK}
            actual = md5sums.decode('ascii').splitlines()
            need(len(actual) == len(expected) and set(actual) == expected, 'installed checksum list differs')
        self.loader_health(metadata)
        return observed

    def install(self, path):
        need(self.mutation is not None, 'package mutation requires both database locks')
        self.audit(exclude_native=True)
        with self.mutation():
            self.run(['/usr/bin/dpkg', '--admindir=/var/lib/dpkg', '--root=/', '--triggers', '--install', str(path)])
        self.audit()

    def purge(self):
        need(self.mutation is not None, 'package mutation requires both database locks')
        self.audit(exclude_native=True)
        with self.mutation():
            self.run(['/usr/bin/dpkg', '--admindir=/var/lib/dpkg', '--root=/', '--triggers', '--purge', PACKAGE])
        self.audit()

    def recovery_observer(self):
        # A distinct bounded observation/repair phase, not a renewed install
        # budget or permission for the canceled forward operation to continue.
        old = self.runner
        self.runner = processes.Runner(seconds=15)
        return old.check


class Manager:
    def __init__(self, tree, backend):
        self.tree, self.backend = tree, backend
        self.check = lambda: None

    @contextmanager
    def locked(self):
        for path in (BASE, BASE + '/cache', BASE + '/transactions'):
            self.tree.private_directory(path)
        with self.tree.lock(BASE + '/lock') as own:
            with self.tree.lock('var/lib/dpkg/lock-frontend', frontend=True) as frontend:
                with self.tree.directory('var/lib/dpkg') as dpkg_dir:
                    database = None
                    def acquire_database():
                        lock = self.tree.lock('var/lib/dpkg/lock', frontend=True)
                        check_locked = lock.__enter__()
                        return lock, check_locked
                    database, database_check = acquire_database()
                    info = os.stat('lock', dir_fd=dpkg_dir, follow_symlinks=False)
                    expected = (info.st_dev, info.st_ino, info.st_uid, info.st_mode, info.st_nlink)
                    def check():
                        own()
                        frontend()
                        named = os.stat('lock', dir_fd=dpkg_dir, follow_symlinks=False)
                        need((named.st_dev, named.st_ino, named.st_uid, named.st_mode, named.st_nlink) == expected,
                             'dpkg database lock name changed during handoff')
                        if database is not None:
                            database_check()
                    @contextmanager
                    def mutation():
                        nonlocal database, database_check
                        check()
                        need(database is not None, 'nested package mutation is forbidden')
                        previous, database = database, None
                        previous.__exit__(None, None, None)
                        try:
                            check()
                            yield
                        finally:
                            # dpkg acquires the backend lock itself. Reacquire
                            # only after its complete owned process tree exits.
                            database, database_check = acquire_database()
                            check()
                    self.check = self.backend.guard = check
                    self.backend.mutation = mutation
                    try:
                        yield
                    finally:
                        self.check = self.backend.guard = lambda: None
                        self.backend.mutation = None
                        if database is not None:
                            database.__exit__(None, None, None)

    def read_json(self, name, *, missing=False):
        data = self.tree.read(name, maximum=256 * 1024, mode=0o600, missing=missing)
        return None if data is None else artifact.json_object(data)

    def write_json(self, name, value, *, replace=True):
        self.check()
        self.tree.write(name, state.canonical(value), replace=replace)

    def cache_name(self, metadata):
        need(type(metadata) is dict and type(metadata.get('sha256')) is str
             and artifact.DIGEST.fullmatch(metadata['sha256']), 'invalid cached archive identity')
        return BASE + '/cache/' + metadata['sha256'] + '.deb'

    def metadata(self, value):
        if value is None:
            return None
        raw = self.tree.read(self.cache_name(value), maximum=artifact.MAX_ARCHIVE, mode=0o600)
        inspected = artifact.inspect_package(raw, sha256=value.get('sha256'), byte_count=value.get('bytes'),
            source_commit=value.get('source_commit'), content_commit=value.get('content_commit'))
        need(inspected == value, 'cached package metadata differs from independently selected bytes')
        return inspected

    def journal_name(self, token):
        need(type(token) is str and TOKEN.fullmatch(token), 'invalid native transaction token')
        return BASE + '/transactions/' + token + '/journal.json'

    def read_journal(self, token, *, missing=False):
        name = self.journal_name(token)
        try:
            journal = self.read_json(name, missing=missing)
        except FileNotFoundError:
            # A caller can name its operation before prepare has created the
            # per-token directory. Do not mask missing cached authority below.
            if not missing:
                raise
            return None
        if journal is None:
            return None
        need(journal.get('schema') == 'plebian-os.native-transaction/v1'
             and journal.get('transaction') == token, 'invalid native transaction journal')
        self.metadata(journal.get('old'))
        self.metadata(journal.get('new'))
        need(type(journal.get('new')) is dict and type(journal.get('before')) is dict,
             'incomplete native recovery authority')
        return journal

    def load(self, token):
        active = self.read_json(ACTIVE, missing=True)
        need(active == {'transaction': token},
             'native transaction is not the active owner; ' + describe_active_owner(active))
        return self.read_journal(token)

    def save(self, journal):
        self.write_json(self.journal_name(journal['transaction']), journal)

    def prepare(self, data, *, transaction=None, **selection):
        # The outer transaction may record its fresh token BEFORE invoking us.
        # That handoff survives a failed stdout write or interrupted prepare;
        # it never authorizes guessing another operation's active token.
        token = secrets.token_hex(16) if transaction is None else transaction
        self.journal_name(token)
        new = artifact.inspect_package(data, **selection)
        with self.locked():
            active = self.read_json(ACTIVE, missing=True)
            need(active is None, 'native transaction already active; '
                 + describe_active_owner(active) + '; inspect recovery state')
            old = self.metadata(self.read_json(CURRENT, missing=True))
            before = self.backend.verify(old)
            cache = self.cache_name(new)
            previous = self.tree.read(cache, maximum=artifact.MAX_ARCHIVE, mode=0o600, missing=True)
            if previous is None:
                self.tree.write(cache, data)
            else:
                need(previous == data, 'existing cache population differs')
            self.tree.private_directory(BASE + '/transactions/' + token)
            journal = {'schema': 'plebian-os.native-transaction/v1', 'transaction': token,
                       'phase': 'prepared', 'old': old, 'new': new, 'before': before, 'after': None}
            self.write_json(self.journal_name(token), journal, replace=False)
            self.write_json(ACTIVE, {'transaction': token}, replace=False)
            return token

    def apply(self, token):
        with self.locked():
            journal = self.load(token)
            need(journal['phase'] == 'prepared', 'native transaction is not prepared')
            need(self.read_json(CURRENT, missing=True) == journal['old'], 'committed native selection changed')
            need(self.backend.verify(journal['old']) == journal['before'], 'native state changed after prepare')
            self.backend.dependencies(journal['new'])
            journal['phase'] = 'applying'
            self.save(journal)
            error = None
            try:
                self.backend.install(self.tree.root / self.cache_name(journal['new']))
                self.backend.verify(journal['new'])
            except BaseException as caught:
                error = caught
            original_authority = self.backend.recovery_observer()
            journal['after'] = self.backend.snapshot()
            if error is None:
                try:
                    original_authority()
                except BaseException as caught:
                    error = caught
            journal['phase'] = 'failed' if error else 'applied'
            if error:
                journal['error'] = str(error)[:4096]
            self.save(journal)
            if error:
                raise error

    def commit(self, token):
        with self.locked():
            journal = self.load(token)
            need(journal['phase'] == 'applied', 'native transaction has not applied successfully')
            need(self.backend.verify(journal['new']) == journal['after'], 'native state changed before commit')
            need(self.read_json(CURRENT, missing=True) in (journal['old'], journal['new']),
                 'committed native selection changed')
            self.write_json(CURRENT, journal['new'])
            journal['phase'] = 'committed'
            self.save(journal)

    def finish(self, token):
        """Call only AFTER enclosing stack commit; failure retains safe history."""
        with self.locked():
            journal = self.load(token)
            need(journal['phase'] == 'committed', 'native transaction has not committed')
            need(self.read_json(CURRENT) == journal['new']
                 and self.backend.verify(journal['new']) == journal['after'],
                 'native state changed before finishing')
            self.tree.remove_state(ACTIVE, state.canonical({'transaction': token}))

    def rollback(self, token, *, allow_unpublished=False):
        with self.locked():
            active = self.read_json(ACTIVE, missing=True)
            if allow_unpublished and active is None:
                journal = self.read_journal(token, missing=True)
                if journal is None:
                    # No journal: this exact caller-selected operation never
                    # reached a package mutation. Nothing else is retired.
                    return
                need(journal['phase'] in ('prepared', 'rolled-back'),
                     'inactive native journal is not an unpublished preparation')
            else:
                journal = self.load(token)
            need(self.read_json(CURRENT, missing=True) in (journal['old'], journal['new']),
                 'another committed native selection must not be overwritten')
            phase = journal['phase']
            if phase in ('prepared', 'rolled-back'):
                need(self.read_json(CURRENT, missing=True) == journal['old'],
                     'unapplied committed selection changed')
                need(self.backend.verify(journal['old']) == journal['before'],
                     'unapplied native state changed; refusing unrelated rollback')
            else:
                need(phase in ('applied', 'failed', 'committed', 'recovery-failed')
                     and type(journal.get('after')) is dict
                     and self.backend.snapshot() == journal['after'],
                     'native installation changed or lacks a post-operation observation; retain recovery state')
                # The post-state can legitimately be a partially unpacked or
                # unconfigured package. Exact observed identity prevents an
                # unrelated package-manager change from being overwritten.
                journal['phase'] = 'recovering'
                self.save(journal)
                error = None
                try:
                    if journal['old'] is None:
                        self.backend.purge()
                    else:
                        self.backend.dependencies(journal['old'])
                        self.backend.install(self.tree.root / self.cache_name(journal['old']))
                    need(self.backend.verify(journal['old']) == journal['before'],
                         'native rollback did not restore the exact prior package state')
                except BaseException as caught:
                    error = caught
                original_authority = self.backend.recovery_observer()
                journal['after'] = self.backend.snapshot()
                if error is None:
                    try:
                        need(journal['after'] == journal['before'],
                             'native rollback post-observation differs from the exact prior package state')
                        original_authority()
                    except BaseException as caught:
                        error = caught
                if error:
                    journal['phase'] = 'recovery-failed'
                    journal['recovery_error'] = str(error)[:4096]
                    self.save(journal)
                    raise error
            if journal['old'] is None:
                current = self.tree.read(CURRENT, maximum=256 * 1024, mode=0o600, missing=True)
                if current is not None:
                    self.tree.remove_state(CURRENT, current)
            else:
                self.write_json(CURRENT, journal['old'])
            journal['phase'] = 'rolled-back'
            self.save(journal)
            if active is not None:
                self.tree.remove_state(ACTIVE, state.canonical({'transaction': token}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prepare = sub.add_parser('prepare')
    prepare.add_argument('--artifact', type=Path, required=True)
    prepare.add_argument('--sha256', required=True)
    prepare.add_argument('--bytes', dest='byte_count', type=int, required=True)
    prepare.add_argument('--source-commit', required=True)
    prepare.add_argument('--content-commit', required=True)
    prepare.add_argument('--transaction', help='fresh caller-recorded 32-character lowercase hex token')
    for name in ('apply', 'commit', 'finish'):
        sub.add_parser(name).add_argument('transaction')
    rollback = sub.add_parser('rollback')
    rollback.add_argument('transaction')
    rollback.add_argument('--allow-unpublished', action='store_true',
                          help='also retire only an unstarted/unpublished preparation of this exact token')
    sub.add_parser('status')
    args = parser.parse_args()
    if os.getuid() != 0 or os.geteuid() != 0:
        parser.exit(1, 'native runtime helper requires root\n')
    os.umask(0o077)
    processes.enable_subreaper()
    runner = processes.Runner()
    for number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(number, runner.cancel)
    signal.signal(signal.SIGPIPE, signal.SIG_IGN)
    try:
        with state.Tree() as tree:
            manager = Manager(tree, Dpkg(tree, runner))
            if args.command == 'prepare':
                data = artifact.read_archive(args.artifact)
                token = manager.prepare(data, transaction=args.transaction,
                    sha256=args.sha256, byte_count=args.byte_count,
                    source_commit=args.source_commit, content_commit=args.content_commit)
                print(token, flush=True)
            elif args.command == 'status':
                with manager.locked():
                    print(json.dumps({'active': manager.read_json(ACTIVE, missing=True),
                                      'current': manager.read_json(CURRENT, missing=True)}, sort_keys=True))
            elif args.command == 'rollback':
                manager.rollback(args.transaction, allow_unpublished=args.allow_unpublished)
            else:
                getattr(manager, args.command)(args.transaction)
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, 'native runtime refused: ' + str(error) +
                    '\nRecovery records are retained under /' + BASE + '.\n')


if __name__ == '__main__':
    main()
