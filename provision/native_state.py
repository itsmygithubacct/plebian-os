"""Small root-owned filesystem boundary for the native package transaction.

The production anchor is / and owner is uid 0. An explicit library-only anchor
permits private filesystem tests; there is no environment or command-line root
override. No file under the shared dpkg database is written by this module.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import stat


class UnsafeState(ValueError):
    """Refuse an ambiguous, writable or changed managed filesystem entry."""


def need(condition, message):
    if not condition:
        raise UnsafeState(message)


def identity(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


class Tree:
    def __init__(self, root=Path('/'), *, uid=0):
        self.root = Path(root)
        self.uid = uid
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            self.check_dir(self.fd)
        except BaseException:
            os.close(self.fd)
            self.fd = None
            raise

    def close(self):
        if self.fd is not None:
            fd, self.fd = self.fd, None
            os.close(fd)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    @staticmethod
    def parts(relative):
        need(type(relative) is str and relative and not relative.startswith('/')
             and str(PurePosixPath(relative)) == relative
             and all(part not in ('.', '..', '') for part in relative.split('/')),
             'managed path is not a canonical relative name')
        return relative.split('/')

    def check_dir(self, fd):
        info = os.fstat(fd)
        need(stat.S_ISDIR(info.st_mode) and info.st_uid == self.uid
             and not info.st_mode & 0o022, 'managed ancestor is not a trusted directory')

    @contextmanager
    def directory(self, relative='', *, create=False):
        parts = self.parts(relative) if relative else []
        fds = [os.dup(self.fd)]
        try:
            for name in parts:
                self.check_dir(fds[-1])
                if create:
                    try:
                        os.mkdir(name, 0o700, dir_fd=fds[-1])
                    except FileExistsError:
                        pass
                fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                             dir_fd=fds[-1])
                fds.append(fd)
                self.check_dir(fd)
            yield fds[-1]
        finally:
            for fd in reversed(fds):
                os.close(fd)

    @contextmanager
    def parent(self, relative, *, create=False):
        parts = self.parts(relative)
        with self.directory('/'.join(parts[:-1]), create=create) as fd:
            yield fd, parts[-1]

    def private_directory(self, relative):
        with self.directory(relative, create=True) as fd:
            need(stat.S_IMODE(os.fstat(fd).st_mode) == 0o700,
                 'private package state must already have mode 0700')

    def read(self, relative, *, maximum, mode=None, missing=False):
        with self.parent(relative) as (parent, name):
            try:
                held = os.open(name, os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            except FileNotFoundError:
                if missing:
                    return None
                raise
            fd = None
            try:
                before = os.fstat(held)
                need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                     and before.st_uid == self.uid and not before.st_mode & 0o022,
                     'managed input is not a trusted single-link regular file')
                need(mode is None or stat.S_IMODE(before.st_mode) == mode, 'managed file mode differs')
                need(0 <= before.st_size <= maximum, 'managed file exceeds read bound')
                fd = os.open(f'/proc/self/fd/{held}', os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK)
                need(identity(os.fstat(fd)) == identity(before), 'held file identity changed')
                chunks, remaining = [], before.st_size + 1
                while remaining:
                    value = os.read(fd, min(remaining, 1024 * 1024))
                    if not value:
                        break
                    chunks.append(value)
                    remaining -= len(value)
                result = b''.join(chunks)
                need(len(result) == before.st_size and identity(before) == identity(os.fstat(fd)),
                     'managed input changed during read')
                need(identity(before) == identity(os.stat(name, dir_fd=parent, follow_symlinks=False)),
                     'managed input name changed during read')
                return result
            finally:
                try:
                    if fd is not None:
                        os.close(fd)
                finally:
                    os.close(held)

    def write(self, relative, data, *, replace=False):
        need(type(data) is bytes and len(data) <= 8 * 1024**2, 'invalid managed write')
        with self.parent(relative) as (parent, name):
            temporary = '.write-' + secrets.token_hex(16)
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                         0o600, dir_fd=parent)
            published = False
            try:
                view = memoryview(data)
                while view:
                    count = os.write(fd, view)
                    need(count > 0, 'managed write made no progress')
                    view = view[count:]
                os.fchmod(fd, 0o600)
                os.fsync(fd)
                if replace:
                    try:
                        old = os.stat(name, dir_fd=parent, follow_symlinks=False)
                    except FileNotFoundError:
                        old = None
                    if old is not None:
                        need(stat.S_ISREG(old.st_mode) and old.st_uid == self.uid
                             and old.st_nlink == 1 and stat.S_IMODE(old.st_mode) == 0o600,
                             'refusing to replace an unsafe state entry')
                    os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
                else:
                    # link+unlink supplies atomic no-replace publication. The
                    # temporary link is removed before any consumer may read it.
                    os.link(temporary, name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
                    os.unlink(temporary, dir_fd=parent)
                published = True
                os.fsync(parent)
            finally:
                try:
                    os.close(fd)
                finally:
                    if not published:
                        try:
                            os.unlink(temporary, dir_fd=parent)
                        except FileNotFoundError:
                            pass

    def remove_state(self, relative, expected):
        need(self.read(relative, maximum=256 * 1024, mode=0o600) == expected,
             'state entry changed before retirement')
        with self.parent(relative) as (parent, name):
            os.unlink(name, dir_fd=parent)
            os.fsync(parent)

    def fingerprint(self, relative, *, maximum=8 * 1024**2):
        """Bound regular/link/absence only, without following a payload link."""
        try:
            with self.parent(relative) as (parent, name):
                try:
                    info = os.stat(name, dir_fd=parent, follow_symlinks=False)
                except FileNotFoundError:
                    return None
                need(info.st_uid == self.uid, 'installed entry is not root-owned')
                if stat.S_ISLNK(info.st_mode):
                    target = os.readlink(name, dir_fd=parent)
                    need(len(target) <= 1024 and info.st_nlink == 1, 'invalid installed symlink')
                    need(identity(info) == identity(os.stat(name, dir_fd=parent, follow_symlinks=False)),
                         'installed link changed during inspection')
                    return {'link': target, 'uid': info.st_uid, 'gid': info.st_gid}
                data = self.read(relative, maximum=maximum)
                need(identity(info) == identity(os.stat(name, dir_fd=parent, follow_symlinks=False)),
                     'installed entry changed during fingerprinting')
                return {'bytes': len(data), 'mode': stat.S_IMODE(info.st_mode),
                        'uid': info.st_uid, 'gid': info.st_gid,
                        'sha256': hashlib.sha256(data).hexdigest()}
        except FileNotFoundError:
            return None

    @contextmanager
    def lock(self, relative, *, frontend=False):
        """Nonblocking lock with a continuing held/name identity check."""
        with self.parent(relative) as (parent, name):
            try:
                created = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                                  0o600, dir_fd=parent)
            except FileExistsError:
                pass
            else:
                os.close(created)
            held = os.open(name, os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            fd = None
            try:
                info = os.fstat(held)
                need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                     and info.st_uid == self.uid and not info.st_mode & 0o022,
                     'package lock is not a trusted regular file')
                fd = os.open(f'/proc/self/fd/{held}', os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC)
                need(identity(info) == identity(os.fstat(fd)), 'held lock identity changed')
                def check():
                    named = os.stat(name, dir_fd=parent, follow_symlinks=False)
                    need((named.st_dev, named.st_ino, named.st_uid, named.st_mode, named.st_nlink) ==
                         (info.st_dev, info.st_ino, info.st_uid, info.st_mode, info.st_nlink),
                         'package lock entry changed while held')
                    self.check_dir(parent)
                if frontend:
                    fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                else:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                check()
                yield check
                check()
            finally:
                try:
                    if fd is not None:
                        os.close(fd)
                finally:
                    os.close(held)
