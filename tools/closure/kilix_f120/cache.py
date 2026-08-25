"""Shared cache locking, atomic directory publication, and quarantine."""

from __future__ import annotations

import ctypes
import errno
import fcntl
import os
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .canonical import require_sha256
from .errors import CacheError


AT_FDCWD = -100
RENAME_NOREPLACE = 1


def rename_directory_no_replace(candidate: Path, destination: Path) -> None:
    """Atomically rename a path while refusing a concurrently created target."""

    try:
        renameat2 = ctypes.CDLL(None, use_errno=True).renameat2
    except AttributeError as exc:
        raise OSError(
            errno.ENOSYS,
            "atomic no-replace publication requires Linux renameat2",
        ) from exc
    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int
    ctypes.set_errno(0)
    result = renameat2(
        AT_FDCWD,
        os.fsencode(candidate),
        AT_FDCWD,
        os.fsencode(destination),
        RENAME_NOREPLACE,
    )
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), os.fspath(destination))


def cache_root(path: Path) -> Path:
    root = path.resolve()
    root.mkdir(mode=0o755, parents=True, exist_ok=True)
    if root.is_symlink() or not root.is_dir():
        raise CacheError("cache root must be a real directory")
    return root


@contextmanager
def cache_lock(root: Path, namespace: str, key: str) -> Iterator[None]:
    lock_directory = root / "locks" / namespace
    lock_directory.mkdir(mode=0o755, parents=True, exist_ok=True)
    lock_path = lock_directory / f"{key}.lock"
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def temporary_directory(root: Path, namespace: str) -> Path:
    directory = root / "tmp" / namespace
    directory.mkdir(mode=0o755, parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="candidate-", dir=directory))


def quarantine(root: Path, namespace: str, entry: Path) -> Path:
    if not entry.exists() and not entry.is_symlink():
        raise CacheError("cannot quarantine a missing cache entry")
    destination_directory = root / "quarantine" / namespace
    destination_directory.mkdir(mode=0o755, parents=True, exist_ok=True)
    destination = destination_directory / f"{entry.name}-{uuid.uuid4().hex}"
    os.replace(entry, destination)
    return destination


def publish_directory(candidate: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise CacheError("refusing to overwrite an existing cache entry")
    destination.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    try:
        rename_directory_no_replace(candidate, destination)
    except FileExistsError as exc:
        raise CacheError("refusing to overwrite an existing cache entry") from exc
    except OSError as exc:
        raise CacheError(f"cannot atomically publish cache entry: {exc}") from exc
    descriptor = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def directory_bytes(path: Path) -> int:
    total = 0
    for candidate in path.rglob("*"):
        if candidate.is_file() and not candidate.is_symlink():
            total += candidate.stat().st_size
    return total


def evict_entry(root_path: Path, namespace: str, key: str) -> Path | None:
    """Recoverably evict one exact content key; never clear a broad cache."""

    if namespace not in {"sources", "builds"}:
        raise CacheError("cache namespace must be sources or builds")
    key = require_sha256(key, "cache eviction key")
    root = cache_root(root_path)
    entry = root / namespace / "sha256" / key
    with cache_lock(root, namespace, key):
        if not entry.exists() and not entry.is_symlink():
            return None
        return quarantine(root, f"evicted-{namespace}", entry)
