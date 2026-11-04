"""Private QMP endpoints independent of the VM disk's pathname.

The VM directory keeps a qmp.sock symlink for discovery. Connect to its target,
not the potentially overlong symlink pathname. Successful launches retain the
runtime for the VM's lifetime, including after the builder exits.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile

# Linux sockaddr_un.sun_path has 108 bytes, including the terminating NUL.
MAX_SOCKET_BYTES = 107
PREFIX = "plebian-qmp-"


def check_socket_path(path: Path) -> Path:
    if not path.is_absolute() or len(os.fsencode(path)) > MAX_SOCKET_BYTES:
        raise ValueError(f"QMP requires an absolute pathname of at most {MAX_SOCKET_BYTES} bytes: {path}")
    return path


def _private_directory(path: Path) -> bool:
    try:
        entry = path.lstat()
        return (stat.S_ISDIR(entry.st_mode) and entry.st_uid == os.getuid()
                and stat.S_IMODE(entry.st_mode) == 0o700)
    except OSError:
        return False


def _trusted_ancestors(path: Path) -> bool:
    """Other users must not be able to rename a private runtime's parents."""
    try:
        for parent in path.parents:
            entry = parent.lstat()
            if not stat.S_ISDIR(entry.st_mode) or entry.st_uid not in (0, os.getuid()):
                return False
            if entry.st_mode & 0o022 and not (entry.st_uid == 0 and entry.st_mode & stat.S_ISVTX):
                return False
        return True
    except OSError:
        return False


def _runtime_parents():
    xdg = os.environ.get("XDG_RUNTIME_DIR")
    for path in ([Path(xdg)] if xdg else []) + [Path(f"/run/user/{os.getuid()}")]:
        if path.is_absolute() and _private_directory(path):
            resolved = path.resolve()
            if _trusted_ancestors(resolved):
                yield resolved
    # Ignore TMPDIR: it often lives beside the long build/storage directory.
    # A root-owned sticky /tmp permits exclusive mkdtemp without trusting a
    # pre-existing user-named directory. The child itself is always mode 0700.
    path = Path("/tmp")
    entry = path.lstat()
    if (stat.S_ISDIR(entry.st_mode) and entry.st_uid == 0
            and entry.st_mode & stat.S_ISVTX):
        yield path.resolve()


def prepare_qmp(vm_dir: Path) -> Path:
    """Reserve a fresh endpoint; never overwrite or adopt existing VM state."""
    if not _private_directory(vm_dir):
        raise RuntimeError(f"QEMU requires an owned mode-0700 VM directory: {vm_dir}")
    for name in ("qmp.sock", "qemu.pid", "tab.ready"):
        if os.path.lexists(vm_dir / name):
            raise RuntimeError(f"QEMU requires fresh launch state: {vm_dir / name}")
    errors = []
    for parent in _runtime_parents():
        # Check the resolved path in bytes before making even a temporary dir.
        try:
            check_socket_path(parent / (PREFIX + "x" * 8) / "qmp.sock")
            runtime = Path(tempfile.mkdtemp(prefix=PREFIX, dir=parent))
        except (OSError, ValueError) as error:
            errors.append(str(error))
            continue
        try:
            runtime.chmod(0o700)
            endpoint = check_socket_path(runtime / "qmp.sock")
            (vm_dir / "qmp.sock").symlink_to(endpoint)
            return endpoint
        except BaseException:
            # This newly created directory has not been handed to QEMU yet.
            runtime.rmdir()
            raise
    raise RuntimeError("No safe short QMP runtime directory is available: " + "; ".join(errors))


def qmp_socket_path(vm_dir: Path) -> Path:
    """Discover the new endpoint, or a legacy socket stored with the disk."""
    link = vm_dir / "qmp.sock"
    if not link.is_symlink():
        return check_socket_path(link.absolute())
    endpoint = check_socket_path(link.readlink())
    if (endpoint.name != "qmp.sock" or not endpoint.parent.name.startswith(PREFIX)
            or endpoint.parent != endpoint.parent.resolve()
            or not _private_directory(vm_dir)
            or not _private_directory(endpoint.parent)
            or not _trusted_ancestors(endpoint.parent)):
        raise ValueError(f"Unsafe QMP runtime target: {endpoint}")
    return endpoint


def cleanup_empty_runtime(vm_dir: Path) -> bool:
    """Remove only an empty runtime and its discovery link.

    Call only after launch was refused or the VM has been stopped separately.
    Never unlink a socket, signal a PID, or recursively remove VM state. An
    occupied runtime (including a stale socket) is deliberately left intact.
    """
    link = vm_dir / "qmp.sock"
    if not link.is_symlink():
        return False
    endpoint = qmp_socket_path(vm_dir)
    try:
        endpoint.parent.rmdir()
    except OSError:
        return False
    link.unlink()
    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vm_directory", type=Path)
    parser.add_argument("--cleanup-empty", action="store_true",
                        help="after stopping the VM, remove its empty runtime directory")
    args = parser.parse_args()
    if args.cleanup_empty:
        if not cleanup_empty_runtime(args.vm_directory):
            parser.exit(1, "Runtime retained: it is not an empty managed runtime.\n")
    else:
        print(qmp_socket_path(args.vm_directory))
