#!/usr/bin/env python3
"""First-Python bootstrap for the external trusted launcher."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import runpy
import re
import stat
import sys
import tempfile
import traceback
from pathlib import Path


MANIFEST_HEADER = b"KILIX-TRUSTED-CLOSURE-MANIFEST-v1\n"
PROFILE_SCHEMA = "kilix.trusted-launcher.profile/v1"
RESULT_SCHEMA = "kilix.trusted-launcher.result/v1"
RESERVED_NAMES = {"sitecustomize.py", "usercustomize.py"}
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_PROFILE_BYTES = 256 * 1024
MAX_CAPTURE_BYTES = 4 * 1024 * 1024
MAX_RESULT_BYTES = 4096
PR_GET_DUMPABLE = 3
PR_SET_DUMPABLE = 4
PROFILE_NAME = re.compile(r"[a-z][a-z0-9-]{0,63}")
MODULE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")
INTERPRETER_IDENTITY_UNAVAILABLE = (
    "TL-INTERPRETER-IDENTITY/live-executable-unavailable"
)
TYPED_REFUSAL_CODES = frozenset({INTERPRETER_IDENTITY_UNAVAILABLE})
FORBIDDEN_PROVIDER_ENVIRONMENT = {
    "BASH_ENV",
    "ENV",
    "PERL5LIB",
    "RUBYOPT",
    "VIRTUAL_ENV",
}
FORBIDDEN_PROVIDER_PREFIXES = (
    "CONDA_",
    "DYLD_",
    "LD_",
    "NODE_",
    "NPM_",
    "PIP_",
    "PYTHON",
    "UV_",
)
FIXED_PROVIDER_ENVIRONMENT = {
    "GIT_ASKPASS",
    "GIT_CONFIG_GLOBAL",
    "GIT_CONFIG_NOSYSTEM",
    "GIT_CONFIG_SYSTEM",
    "GIT_TERMINAL_PROMPT",
    "LC_ALL",
    "PATH",
    "SOURCE_DATE_EPOCH",
    "TMPDIR",
    "TZ",
}


class Refusal(ValueError):
    """A stable fail-closed launch refusal."""

    def __init__(self, message: str, *, refusal_code: str | None = None) -> None:
        if refusal_code is not None and refusal_code not in TYPED_REFUSAL_CODES:
            raise ValueError("refusal code is outside the closed catalogue")
        super().__init__(message)
        self.refusal_code = refusal_code


def _seal_result_owner() -> None:
    """Deny subject descendants procfs access to the outer process's fds."""
    try:
        process_control = ctypes.CDLL(None, use_errno=True).prctl
        process_control.argtypes = [
            ctypes.c_int,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_ulong,
        ]
        process_control.restype = ctypes.c_int
    except (AttributeError, OSError) as exc:
        raise Refusal("result owner procfs isolation is unavailable") from exc
    if process_control(PR_SET_DUMPABLE, 0, 0, 0, 0) != 0:
        raise Refusal("result owner procfs isolation could not be established")
    if process_control(PR_GET_DUMPABLE, 0, 0, 0, 0) != 0:
        raise Refusal("result owner procfs isolation did not remain active")


def _sha256_fd(descriptor: int) -> str:
    digest = hashlib.sha256()
    offset = 0
    while True:
        block = os.pread(descriptor, 1024 * 1024, offset)
        if not block:
            return digest.hexdigest()
        digest.update(block)
        offset += len(block)


def _read_fd(descriptor: int, limit: int) -> bytes:
    result = bytearray()
    offset = 0
    while True:
        block = os.pread(descriptor, min(1024 * 1024, limit + 1 - len(result)), offset)
        if not block:
            return bytes(result)
        result.extend(block)
        offset += len(block)
        if len(result) > limit:
            raise Refusal("manifest exceeds fixed size limit")


def _exact_object(value: object, fields: set[str], label: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        raise Refusal(f"{label} has an unexpected shape")
    return value


def _profile_pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise Refusal("launch profile contains a duplicate JSON member")
        result[key] = value
    return result


def _profile_constant(value: str) -> object:
    raise Refusal(f"launch profile contains forbidden JSON constant {value}")


def _relative_path(value: object, label: str, *, dot: bool = False) -> str:
    if not isinstance(value, str) or not value:
        raise Refusal(f"{label} is not a bounded relative path")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise Refusal(f"{label} is not Unicode scalar text") from exc
    if len(encoded) > 1024:
        raise Refusal(f"{label} is not a bounded relative path")
    parts = value.split("/")
    if value.startswith("/") or any(part in ("", "..") for part in parts):
        raise Refusal(f"{label} is not a normalized relative path")
    if not dot and value == ".":
        raise Refusal(f"{label} does not name a member below its root")
    if any(part == "." for part in parts[1:]):
        raise Refusal(f"{label} contains a dot segment")
    return value


def _profile(arguments: argparse.Namespace) -> tuple[dict[str, object], dict[str, object]]:
    raw = _read_fd(arguments.profile_fd, MAX_PROFILE_BYTES)
    if hashlib.sha256(raw).hexdigest() != arguments.profile_sha256:
        raise Refusal("launch profile digest differs from the native binding")
    try:
        value = json.loads(
            raw, object_pairs_hook=_profile_pairs, parse_constant=_profile_constant
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise Refusal("launch profile is not duplicate-free UTF-8 JSON") from exc
    canonical = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8") + b"\n"
    if raw != canonical:
        raise Refusal("launch profile is not canonical")
    profile = _exact_object(
        value,
        {"commands", "launcher_name", "profile_id", "schema", "subject_hash_manifests"},
        "launch profile",
    )
    if profile["schema"] != PROFILE_SCHEMA or profile["profile_id"] != arguments.profile_id:
        raise Refusal("launch profile identity differs from the native binding")
    commands = profile["commands"]
    if not isinstance(commands, list) or not 1 <= len(commands) <= 16:
        raise Refusal("launch profile command table is empty or oversized")
    selected: dict[str, object] | None = None
    names: set[str] = set()
    for index, raw_command in enumerate(commands):
        command = _exact_object(
            raw_command, {"argument_mode", "children", "name"}, f"command {index}"
        )
        name = command["name"]
        if not isinstance(name, str) or PROFILE_NAME.fullmatch(name) is None or name in names:
            raise Refusal("launch profile command names are invalid or duplicate")
        names.add(name)
        if name == arguments.command:
            selected = command
    if selected is None:
        raise Refusal("native-selected command is absent from the launch profile")
    children = selected["children"]
    if not isinstance(children, list) or not 1 <= len(children) <= 64:
        raise Refusal("selected command child table is empty or oversized")
    terminal_ids: list[str] = []
    for index, child in enumerate(children):
        if not isinstance(child, dict):
            raise Refusal(f"child {index} is not an object")
        child_id = child.get("id")
        if (
            not isinstance(child_id, str)
            or PROFILE_NAME.fullmatch(child_id) is None
            or child_id in terminal_ids
        ):
            raise Refusal("selected command child IDs are invalid or duplicate")
        terminal_ids.append(child_id)
    terminal = hashlib.sha256(
        "".join(f"{child_id}\n" for child_id in terminal_ids).encode("utf-8")
    ).hexdigest()
    if terminal != arguments.terminal_check_set_sha256:
        raise Refusal("selected child table differs from the native terminal binding")
    return profile, selected


def _entry_line(kind: str, mode: int, size: int, digest: str, relative: str) -> bytes:
    if any(character in relative for character in ("\0", "\n", "\r", "\t")):
        raise Refusal("manifest path contains a control separator")
    return f"{kind}\t{mode:04o}\t{size}\t{digest}\t{relative}\n".encode("utf-8")


def _manifest_bytes(root_fd: int, *, reject_reserved: bool) -> bytes:
    root = os.fstat(root_fd)
    if not stat.S_ISDIR(root.st_mode):
        raise Refusal("closure root is not a directory")
    identities: set[tuple[int, int]] = {(root.st_dev, root.st_ino)}
    lines: list[bytes] = []

    def walk(directory_fd: int, prefix: str) -> None:
        try:
            os.lseek(directory_fd, 0, os.SEEK_SET)
            names = sorted(os.listdir(directory_fd))
        except OSError as exc:
            raise Refusal("cannot enumerate closure root") from exc
        for name in names:
            if name in {".", ".."}:
                raise Refusal("closure has an invalid directory member")
            if reject_reserved and (name in RESERVED_NAMES or name.endswith(".pth")):
                raise Refusal(f"reserved Python startup member: {prefix}{name}")
            if any(character in name for character in ("\0", "\n", "\r", "\t", "/")):
                raise Refusal("closure member name is not representable")
            try:
                information = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            except OSError as exc:
                raise Refusal("cannot stat closure member") from exc
            relative = f"{prefix}{name}"
            if information.st_dev != root.st_dev:
                raise Refusal(f"cross-device closure member: {relative}")
            identity = (information.st_dev, information.st_ino)
            if identity in identities:
                raise Refusal(f"aliased closure member: {relative}")
            identities.add(identity)
            mode = stat.S_IMODE(information.st_mode)
            flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
            if stat.S_ISDIR(information.st_mode):
                child = os.open(name, flags | os.O_DIRECTORY, dir_fd=directory_fd)
                try:
                    lines.append(_entry_line("d", mode, 0, "-", relative))
                    walk(child, relative + "/")
                finally:
                    os.close(child)
            elif stat.S_ISREG(information.st_mode):
                child = os.open(name, flags, dir_fd=directory_fd)
                try:
                    current = os.fstat(child)
                    if (current.st_dev, current.st_ino) != identity:
                        raise Refusal(f"closure member changed during open: {relative}")
                    lines.append(
                        _entry_line(
                            "f", mode, information.st_size, _sha256_fd(child), relative
                        )
                    )
                finally:
                    os.close(child)
            else:
                raise Refusal(f"non-regular closure member: {relative}")

    walk(root_fd, "")
    return MANIFEST_HEADER + b"".join(lines)


def _verify_manifest(
    root_fd: int,
    manifest_fd: int,
    expected_sha256: str,
    *,
    label: str,
    reject_reserved: bool,
) -> None:
    expected = _read_fd(manifest_fd, MAX_MANIFEST_BYTES)
    if hashlib.sha256(expected).hexdigest() != expected_sha256:
        raise Refusal(f"{label} authority manifest digest mismatch")
    observed = _manifest_bytes(root_fd, reject_reserved=reject_reserved)
    if observed != expected:
        observed_sha256 = hashlib.sha256(observed).hexdigest()
        expected_lines = expected.splitlines()
        observed_lines = observed.splitlines()
        mismatch = min(len(expected_lines), len(observed_lines))
        for index, (expected_line, observed_line) in enumerate(
            zip(expected_lines, observed_lines)
        ):
            if expected_line != observed_line:
                mismatch = index
                break
        expected_detail = (
            expected_lines[mismatch][:240].decode("utf-8", "replace")
            if mismatch < len(expected_lines)
            else "<missing>"
        )
        observed_detail = (
            observed_lines[mismatch][:240].decode("utf-8", "replace")
            if mismatch < len(observed_lines)
            else "<missing>"
        )
        raise Refusal(
            f"{label} exact closure differs from authority manifest "
            f"(observed {observed_sha256}; line {mismatch + 1}: "
            f"expected {expected_detail!r}, observed {observed_detail!r})"
        )


def _same_file(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _resolved_fd(descriptor: int) -> Path:
    try:
        return Path(os.readlink(f"/proc/self/fd/{descriptor}")).resolve(strict=True)
    except OSError as exc:
        raise Refusal("cannot resolve retained authority descriptor") from exc


def _inside(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _kernel_argv() -> list[str]:
    try:
        raw = Path("/proc/self/cmdline").read_bytes()
    except OSError as exc:
        raise Refusal("cannot read kernel argv") from exc
    if not raw.endswith(b"\0"):
        raise Refusal("kernel argv is malformed")
    try:
        return [item.decode("utf-8") for item in raw[:-1].split(b"\0")]
    except UnicodeDecodeError as exc:
        raise Refusal("kernel argv is not UTF-8") from exc


def _python_startup_guard(
    *,
    python_fd: int,
    python_sha256: str,
    bootstrap_fd: int,
    bootstrap_sha256: str,
) -> tuple[str, ...]:
    flags = sys.flags
    required = {
        "dont_write_bytecode": 1,
        "ignore_environment": 1,
        "isolated": 1,
        "no_site": 1,
        "no_user_site": 1,
        "safe_path": True,
    }
    for name, expected in required.items():
        if getattr(flags, name) != expected:
            raise Refusal(f"required Python flag absent: {name}")
    for name in ("site", "sitecustomize", "usercustomize"):
        if name in sys.modules:
            raise Refusal(f"startup module already loaded: {name}")

    kernel = _kernel_argv()
    expected_script = f"/proc/self/fd/{bootstrap_fd}"
    if len(kernel) < 5 or kernel[1:5] != ["-I", "-S", "-B", expected_script]:
        raise Refusal("kernel argv lacks exact ordered -I -S -B bootstrap launch")

    python_information = os.fstat(python_fd)
    try:
        executable_information = Path("/proc/self/exe").stat()
        sys_executable_information = Path(sys.executable).stat()
    except OSError as exc:
        raise Refusal(
            "cannot bind live interpreter identity",
            refusal_code=INTERPRETER_IDENTITY_UNAVAILABLE,
        ) from exc
    if not stat.S_ISREG(python_information.st_mode):
        raise Refusal("pinned interpreter is not a regular file")
    if not _same_file(python_information, executable_information):
        raise Refusal("live executable differs from pinned interpreter descriptor")
    if not _same_file(python_information, sys_executable_information):
        raise Refusal("sys.executable differs from pinned interpreter descriptor")
    if _sha256_fd(python_fd) != python_sha256:
        raise Refusal("pinned interpreter digest mismatch")
    if _sha256_fd(bootstrap_fd) != bootstrap_sha256:
        raise Refusal("trusted bootstrap digest mismatch")
    return tuple(sys.path)


def _initial_guard(arguments: argparse.Namespace) -> tuple[Path, tuple[str, ...]]:
    initial_sys_path = _python_startup_guard(
        python_fd=arguments.python_fd,
        python_sha256=arguments.python_sha256,
        bootstrap_fd=arguments.bootstrap_fd,
        bootstrap_sha256=arguments.bootstrap_sha256,
    )

    expected_environment = {
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/bin:/bin",
        "TMPDIR": arguments.tmpdir,
        "TZ": "UTC",
    }
    if dict(os.environ) != expected_environment:
        raise Refusal("process environment differs from the exact launch profile")

    cwd = Path.cwd().resolve(strict=True)
    if str(cwd) != arguments.tmpdir:
        raise Refusal("process cwd differs from the launch profile")
    cwd_information = cwd.stat()
    if stat.S_IMODE(cwd_information.st_mode) != 0o700 or any(cwd.iterdir()):
        raise Refusal("authority cwd is not an empty mode-0700 directory")

    subject = _resolved_fd(arguments.subject_fd)
    subject_information = os.fstat(arguments.subject_fd)
    try:
        path_information = Path(arguments.subject_path).stat(follow_symlinks=False)
    except OSError as exc:
        raise Refusal("subject path no longer identifies the retained root") from exc
    if not _same_file(subject_information, path_information):
        raise Refusal("subject path and retained descriptor disagree")
    if subject_information.st_dev != arguments.subject_device:
        raise Refusal("subject device identity mismatch")
    if subject_information.st_ino != arguments.subject_inode:
        raise Refusal("subject inode identity mismatch")

    dependency = _resolved_fd(arguments.dependency_fd)
    runtime = _resolved_fd(arguments.runtime_fd)
    for controlled in (subject, dependency, runtime):
        if _inside(cwd, controlled) or _inside(controlled, cwd):
            raise Refusal("authority cwd overlaps controlled bytes")

    forbidden = {subject, *subject.parents}
    initial_path: list[str] = []
    for entry in initial_sys_path:
        if not entry:
            raise Refusal("initial sys.path contains an empty entry")
        try:
            resolved = Path(entry).resolve(strict=False)
        except OSError as exc:
            raise Refusal("cannot resolve initial sys.path") from exc
        if resolved in forbidden:
            raise Refusal("subject or subject parent appears on initial sys.path")
        initial_path.append(entry)
    return subject, tuple(initial_path)


def _environment_sha256() -> str:
    encoded = json.dumps(
        dict(os.environ), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _provider_main(arguments: argparse.Namespace) -> int:
    initial_path = _python_startup_guard(
        python_fd=arguments.python_fd,
        python_sha256=arguments.python_sha256,
        bootstrap_fd=arguments.bootstrap_fd,
        bootstrap_sha256=arguments.bootstrap_sha256,
    )
    if _environment_sha256() != arguments.environment_sha256:
        raise Refusal("provider environment differs from its exact profile")
    for name in os.environ:
        if name in FORBIDDEN_PROVIDER_ENVIRONMENT or name.startswith(
            FORBIDDEN_PROVIDER_PREFIXES
        ):
            raise Refusal(f"provider environment contains forbidden startup name: {name}")
        if name not in FIXED_PROVIDER_ENVIRONMENT and not name.startswith(
            "F120_INPUT_"
        ):
            raise Refusal(f"provider environment contains an unprofiled name: {name}")
    cwd = Path.cwd().resolve(strict=True)
    if str(cwd) != arguments.tmpdir:
        raise Refusal("provider bootstrap cwd differs from its exact profile")
    information = cwd.stat()
    if stat.S_IMODE(information.st_mode) != 0o700 or any(cwd.iterdir()):
        raise Refusal("provider bootstrap cwd is not empty mode-0700")

    source = _resolved_fd(arguments.source_fd)
    source_information = os.fstat(arguments.source_fd)
    path_information = Path(arguments.source_path).stat(follow_symlinks=False)
    if not _same_file(source_information, path_information):
        raise Refusal("provider source path and retained descriptor disagree")
    if _inside(cwd, source) or _inside(source, cwd):
        raise Refusal("provider bootstrap cwd overlaps source")

    script_information = os.fstat(arguments.script_fd)
    registered_information = Path(arguments.script_path).stat(follow_symlinks=False)
    if not stat.S_ISREG(script_information.st_mode) or not _same_file(
        script_information, registered_information
    ):
        raise Refusal("provider script path and retained descriptor disagree")
    if _sha256_fd(arguments.script_fd) != arguments.script_sha256:
        raise Refusal("provider script digest mismatch")

    forbidden = {source, *source.parents}
    for entry in initial_path:
        if not entry:
            raise Refusal("provider initial sys.path contains an empty entry")
        if Path(entry).resolve(strict=False) in forbidden:
            raise Refusal("provider source appears on initial sys.path")

    forwarded = arguments.forwarded
    if forwarded[:1] == ["--"]:
        forwarded = forwarded[1:]
    os.chdir(source)
    sys.path[:] = [f"/proc/self/fd/{arguments.source_fd}", *initial_path]
    sys.argv = [arguments.script_path, *forwarded]
    try:
        runpy.run_path(f"/proc/self/fd/{arguments.script_fd}", run_name="__main__")
    except SystemExit as exc:
        return int(exc.code or 0) if isinstance(exc.code, (int, type(None))) else 2
    return 0


def _verify_all(arguments: argparse.Namespace) -> None:
    if _sha256_fd(arguments.profile_fd) != arguments.profile_sha256:
        raise Refusal("launch profile changed after native verification")
    _verify_manifest(
        arguments.runtime_fd,
        arguments.runtime_manifest_fd,
        arguments.runtime_manifest_sha256,
        label="runtime",
        reject_reserved=False,
    )
    _verify_manifest(
        arguments.dependency_fd,
        arguments.dependency_manifest_fd,
        arguments.dependency_manifest_sha256,
        label="dependency",
        reject_reserved=False,
    )
    _verify_manifest(
        arguments.subject_fd,
        arguments.subject_manifest_fd,
        arguments.subject_manifest_sha256,
        label="subject",
        reject_reserved=True,
    )


def _verify_subject_hash_manifest(
    subject_fd: int, declaration: object, index: int
) -> None:
    entry = _exact_object(
        declaration, {"members", "path"}, f"subject hash manifest {index}"
    )
    manifest_path = _relative_path(
        entry["path"], f"subject hash manifest {index} path"
    )
    members = entry["members"]
    if not isinstance(members, list) or not members:
        raise Refusal("subject hash manifest member table is empty or malformed")
    expected_names: list[str] = []
    for member_index, member in enumerate(members):
        name = _relative_path(
            member, f"subject hash manifest {index} member {member_index}"
        )
        if name in expected_names:
            raise Refusal("subject hash manifest declares a duplicate member")
        expected_names.append(name)
    try:
        manifest_fd = os.open(
            manifest_path,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
            dir_fd=subject_fd,
        )
        manifest = _read_fd(manifest_fd, 64 * 1024).decode("ascii")
        os.close(manifest_fd)
    except (OSError, UnicodeDecodeError) as exc:
        raise Refusal("cannot read companion-semantics hash manifest") from exc
    lines = manifest.splitlines()
    if len(lines) != len(expected_names):
        raise Refusal("subject hash manifest has the wrong file set")
    observed_names: list[str] = []
    for line in lines:
        digest, separator, name = line.partition("  ")
        if (
            not separator
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise Refusal("subject hash manifest is malformed")
        observed_names.append(name)
        try:
            descriptor = os.open(
                name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=subject_fd
            )
        except OSError as exc:
            raise Refusal("subject hash manifest member is absent or non-regular") from exc
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise Refusal("subject hash manifest member is not a regular file")
            if _sha256_fd(descriptor) != digest:
                raise Refusal("subject hash manifest member digest mismatch")
        finally:
            os.close(descriptor)
    if observed_names != expected_names:
        raise Refusal("subject hash manifest is not canonical")


def _verify_subject_hash_manifests(subject_fd: int, profile: dict[str, object]) -> None:
    declarations = profile["subject_hash_manifests"]
    if not isinstance(declarations, list) or len(declarations) > 16:
        raise Refusal("subject hash manifest table is malformed or oversized")
    observed_paths: set[str] = set()
    for index, declaration in enumerate(declarations):
        if not isinstance(declaration, dict) or not isinstance(declaration.get("path"), str):
            raise Refusal("subject hash manifest declaration is malformed")
        if declaration["path"] in observed_paths:
            raise Refusal("subject hash manifest path is duplicated")
        observed_paths.add(declaration["path"])
        _verify_subject_hash_manifest(subject_fd, declaration, index)


def _root_path(
    declaration: object,
    arguments: argparse.Namespace,
    label: str,
    *,
    directory: bool | None = None,
    allowed_roots: set[str] | None = None,
) -> Path:
    item = _exact_object(declaration, {"path", "root"}, label)
    root_name = item["root"]
    if not isinstance(root_name, str) or (
        allowed_roots is not None and root_name not in allowed_roots
    ):
        raise Refusal(f"{label} names an unsupported retained root")
    relative = _relative_path(item["path"], f"{label} path", dot=True)
    roots = {
        "dependency": _resolved_fd(arguments.dependency_fd),
        "runtime": _resolved_fd(arguments.runtime_fd),
        "subject": Path(arguments.subject_path).resolve(strict=True),
        "temporary": Path(arguments.tmpdir).resolve(strict=True),
    }
    if root_name in ("launcher", "python"):
        if relative != ".":
            raise Refusal(f"{label} may only name the retained executable itself")
        candidate = Path(
            arguments.launcher_path if root_name == "launcher" else arguments.python_path
        ).resolve(strict=True)
    else:
        if root_name not in roots:
            raise Refusal(f"{label} names an unsupported retained root")
        root = roots[root_name]
        candidate = (root / relative).resolve(strict=True)
        if not _inside(candidate, root) and candidate != root:
            raise Refusal(f"{label} escapes its retained root")
    if directory is True and not candidate.is_dir():
        raise Refusal(f"{label} is not a directory")
    if directory is False and not candidate.is_file():
        raise Refusal(f"{label} is not a regular file")
    return candidate


def _python_paths(
    value: object, arguments: argparse.Namespace, initial_path: tuple[str, ...]
) -> list[str]:
    if not isinstance(value, list) or not 1 <= len(value) <= 16:
        raise Refusal("child Python path table is empty or oversized")
    result: list[str] = []
    for index, declaration in enumerate(value):
        path = str(
            _root_path(
                declaration,
                arguments,
                f"child Python path {index}",
                directory=True,
                allowed_roots={"dependency", "subject"},
            )
        )
        if path in result:
            raise Refusal("child Python path table contains a duplicate")
        result.append(path)
    return [*result, *initial_path]


def _argv(
    value: object,
    forwarded: list[str],
    forward_arguments: object,
    arguments: argparse.Namespace,
) -> list[str]:
    if not isinstance(value, list) or len(value) > 64 or not isinstance(forward_arguments, bool):
        raise Refusal("child argv declaration is malformed or oversized")
    result: list[str] = []
    for index, argument in enumerate(value):
        if isinstance(argument, str):
            try:
                encoded = argument.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise Refusal("child argv literal is not Unicode scalar text") from exc
            if not argument or len(encoded) > 256 or any(
                character in argument for character in ("\0", "\n", "\r")
            ):
                raise Refusal("child argv contains an invalid literal")
            result.append(argument)
        else:
            result.append(
                str(
                    _root_path(
                        argument,
                        arguments,
                        f"child argv {index}",
                        allowed_roots={
                            "dependency",
                            "launcher",
                            "python",
                            "runtime",
                            "subject",
                            "temporary",
                        },
                    )
                )
            )
    if forward_arguments:
        result.extend(forwarded)
    return result


def _run_python_target(
    kind: str,
    target: object,
    argv: list[str],
    arguments: argparse.Namespace,
) -> int:
    if kind == "python-script":
        script = _root_path(
            target,
            arguments,
            "child script",
            directory=False,
            allowed_roots={"dependency", "subject"},
        )
        sys.argv = [str(script), *argv]
        try:
            runpy.run_path(str(script), run_name="__main__")
        except SystemExit as exc:
            return int(exc.code or 0) if isinstance(exc.code, (int, type(None))) else 2
        return 0
    if not isinstance(target, str) or MODULE_NAME.fullmatch(target) is None:
        raise Refusal("child module is not a canonical dotted Python name")
    sys.argv = [f"python -m {target}", *argv]
    try:
        runpy.run_module(target, run_name="__main__", alter_sys=False)
    except SystemExit as exc:
        return int(exc.code or 0) if isinstance(exc.code, (int, type(None))) else 2
    return 0


def _expected_stream(
    declaration: object, arguments: argparse.Namespace, label: str
) -> bytes | None:
    if not isinstance(declaration, dict) or "mode" not in declaration:
        raise Refusal(f"{label} expectation is malformed")
    mode = declaration["mode"]
    if mode in ("empty", "passthrough"):
        _exact_object(declaration, {"mode"}, label)
        return b"" if mode == "empty" else None
    if mode == "literal-utf8":
        item = _exact_object(declaration, {"mode", "value"}, label)
        if not isinstance(item["value"], str):
            raise Refusal(f"{label} literal is not text")
        try:
            encoded = item["value"].encode("utf-8")
        except UnicodeEncodeError as exc:
            raise Refusal(f"{label} literal is not Unicode scalar text") from exc
        if len(encoded) > 65536:
            raise Refusal(f"{label} literal is oversized")
        return encoded
    if mode == "file":
        item = _exact_object(declaration, {"mode", "path", "root"}, label)
        path = _root_path(
            {"path": item["path"], "root": item["root"]},
            arguments,
            label,
            directory=False,
            allowed_roots={"dependency", "subject"},
        )
        payload = path.read_bytes()
        if len(payload) > MAX_CAPTURE_BYTES:
            raise Refusal(f"{label} file is oversized")
        return payload
    raise Refusal(f"{label} expectation mode is unsupported")


def _captured_case(
    kind: str,
    target: object,
    case: dict[str, object],
    forwarded: list[str],
    arguments: argparse.Namespace,
) -> int:
    stdout_expected = _expected_stream(case["stdout"], arguments, "child stdout")
    stderr_expected = _expected_stream(case["stderr"], arguments, "child stderr")
    rendered = _argv(
        case["argv"], forwarded, case["forward_arguments"], arguments
    )
    capture = stdout_expected is not None or stderr_expected is not None
    stdout_file = tempfile.TemporaryFile(dir=arguments.tmpdir) if capture else None
    stderr_file = tempfile.TemporaryFile(dir=arguments.tmpdir) if capture else None
    child = os.fork()
    if child < 0:
        raise Refusal("cannot fork isolated profile case")
    if child == 0:
        try:
            if capture:
                assert stdout_file is not None and stderr_file is not None
                sys.stdout.flush()
                sys.stderr.flush()
                os.dup2(stdout_file.fileno(), 1)
                os.dup2(stderr_file.fileno(), 2)
            status = _run_python_target(kind, target, rendered, arguments)
            sys.stdout.flush()
            sys.stderr.flush()
        except BaseException:
            traceback.print_exc(file=sys.stderr)
            status = 255
        os._exit(status)
    while True:
        try:
            waited, wait_status = os.waitpid(child, 0)
            break
        except InterruptedError:
            continue
    if waited != child or not os.WIFEXITED(wait_status):
        raise Refusal("profile case process did not terminate normally")
    status = os.WEXITSTATUS(wait_status)
    if not capture:
        return status
    assert stdout_file is not None and stderr_file is not None
    stdout_fd = stdout_file.fileno()
    stderr_fd = stderr_file.fileno()
    try:
        if os.fstat(stdout_fd).st_size > MAX_CAPTURE_BYTES or os.fstat(stderr_fd).st_size > MAX_CAPTURE_BYTES:
            raise Refusal("child output exceeds the fixed capture limit")
        stdout = _read_fd(stdout_fd, MAX_CAPTURE_BYTES)
        stderr = _read_fd(stderr_fd, MAX_CAPTURE_BYTES)
    finally:
        stdout_file.close()
        stderr_file.close()
    if stdout_expected is not None and stdout != stdout_expected:
        raise Refusal("child stdout differs from its profile expectation")
    if stderr_expected is not None and stderr != stderr_expected:
        raise Refusal("child stderr differs from its profile expectation")
    if stdout_expected is None and stdout:
        os.write(1, stdout)
    if stderr_expected is None and stderr:
        os.write(2, stderr)
    return status


def _child_main(
    child: dict[str, object],
    forwarded: list[str],
    arguments: argparse.Namespace,
    initial_path: tuple[str, ...],
) -> int:
    kind = child.get("kind")
    common = {"id", "kind", "python_paths"}
    if kind == "python-script":
        item = _exact_object(child, common | {"cases", "script"}, "script child")
        target = item["script"]
    elif kind == "python-module":
        item = _exact_object(child, common | {"cases", "module"}, "module child")
        target = item["module"]
    elif kind == "python-unittest":
        item = _exact_object(child, common | {"start", "top"}, "unittest child")
        sys.path[:] = _python_paths(item["python_paths"], arguments, initial_path)
        import unittest

        start = _root_path(
            item["start"], arguments, "unittest start", directory=True, allowed_roots={"subject"}
        )
        top = _root_path(
            item["top"], arguments, "unittest top", directory=True, allowed_roots={"subject"}
        )
        suite = unittest.defaultTestLoader.discover(str(start), top_level_dir=str(top))
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    else:
        raise Refusal("child kind is unsupported")
    sys.path[:] = _python_paths(item["python_paths"], arguments, initial_path)
    cases = item["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= 64:
        raise Refusal("child case table is empty or oversized")
    for index, raw_case in enumerate(cases):
        case = _exact_object(
            raw_case,
            {"argv", "expected_exit", "forward_arguments", "stderr", "stdout"},
            f"child case {index}",
        )
        expected_exit = case["expected_exit"]
        if type(expected_exit) is not int or not 0 <= expected_exit <= 255:
            raise Refusal("child case expected exit is invalid")
        status = _captured_case(kind, target, case, forwarded, arguments)
        if status != expected_exit:
            raise Refusal("child case exit status differs from its profile expectation")
    return 0


def _run_separate_child(
    child_specification: dict[str, object],
    forwarded: list[str],
    arguments: argparse.Namespace,
    initial_path: tuple[str, ...],
) -> None:
    child = os.fork()
    if child == 0:
        try:
            os.close(arguments.result_fd)
            code = _child_main(child_specification, forwarded, arguments, initial_path)
            sys.stdout.flush()
            sys.stderr.flush()
        except BaseException:
            traceback.print_exc(file=sys.stderr)
            code = 2
        os._exit(code)
    while True:
        try:
            waited, status = os.waitpid(child, 0)
            break
        except InterruptedError:
            continue
    if waited != child or not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
        child_id = child_specification.get("id", "unnamed")
        raise Refusal(f"{child_id} child did not complete successfully")
    _verify_all(arguments)


def _write_result_record(arguments: argparse.Namespace, record: dict[str, object]) -> None:
    encoded = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    if len(encoded) > MAX_RESULT_BYTES:
        raise Refusal("canonical result exceeds fixed bound")
    if os.write(arguments.result_fd, encoded) != len(encoded):
        raise Refusal("canonical result channel short write")


def _write_result(arguments: argparse.Namespace) -> None:
    record = {
        "bootstrap_sha256": arguments.bootstrap_sha256,
        "case_id": arguments.case_id,
        "first_process_identity": json.loads(arguments.first_process_json),
        "interpreter_sha256": arguments.python_sha256,
        "launcher_sha256": arguments.launcher_sha256,
        "outcome": "accepted",
        "profile_id": arguments.profile_id,
        "run_id": arguments.run_id,
        "schema": RESULT_SCHEMA,
        "subject_manifest_sha256": arguments.subject_manifest_sha256,
        "terminal_check_set_sha256": arguments.terminal_check_set_sha256,
        "validator_started": True,
    }
    _write_result_record(arguments, record)


def _write_refusal(arguments: argparse.Namespace, refusal_code: str) -> None:
    if refusal_code not in TYPED_REFUSAL_CODES:
        raise Refusal("refusal code is outside the closed catalogue")
    record = {
        "bootstrap_sha256": arguments.bootstrap_sha256,
        "case_id": arguments.case_id,
        "first_process_identity": json.loads(arguments.first_process_json),
        "interpreter_sha256": arguments.python_sha256,
        "launcher_sha256": arguments.launcher_sha256,
        "outcome": "refused",
        "profile_id": arguments.profile_id,
        "refusal_code": refusal_code,
        "run_id": arguments.run_id,
        "schema": RESULT_SCHEMA,
        "subject_manifest_sha256": arguments.subject_manifest_sha256,
        "validator_started": False,
    }
    _write_result_record(arguments, record)


def outer_parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(add_help=False)
    result.add_argument("--mode", choices=("outer",), required=True)
    result.add_argument("--profile-id", required=True)
    result.add_argument("--profile-fd", type=int, required=True)
    result.add_argument("--profile-sha256", required=True)
    result.add_argument("--case-id", required=True)
    result.add_argument("--launcher-sha256", required=True)
    result.add_argument("--first-process-json", required=True)
    result.add_argument("--terminal-check-set-sha256", required=True)
    result.add_argument("--bootstrap-fd", type=int, required=True)
    result.add_argument("--bootstrap-sha256", required=True)
    result.add_argument("--python-fd", type=int, required=True)
    result.add_argument("--python-path", required=True)
    result.add_argument("--python-sha256", required=True)
    result.add_argument("--runtime-fd", type=int, required=True)
    result.add_argument("--runtime-manifest-fd", type=int, required=True)
    result.add_argument("--runtime-manifest-sha256", required=True)
    result.add_argument("--dependency-fd", type=int, required=True)
    result.add_argument("--dependency-manifest-fd", type=int, required=True)
    result.add_argument("--dependency-manifest-sha256", required=True)
    result.add_argument("--subject-fd", type=int, required=True)
    result.add_argument("--subject-path", required=True)
    result.add_argument("--subject-device", type=int, required=True)
    result.add_argument("--subject-inode", type=int, required=True)
    result.add_argument("--subject-manifest-fd", type=int, required=True)
    result.add_argument("--subject-manifest-sha256", required=True)
    result.add_argument("--result-fd", type=int, required=True)
    result.add_argument("--launcher-path", required=True)
    result.add_argument("--run-id", required=True)
    result.add_argument("--tmpdir", required=True)
    result.add_argument("--command", required=True)
    result.add_argument("forwarded", nargs=argparse.REMAINDER)
    return result


def provider_parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(add_help=False)
    result.add_argument("--mode", choices=("provider",), required=True)
    result.add_argument("--bootstrap-fd", type=int, required=True)
    result.add_argument("--bootstrap-sha256", required=True)
    result.add_argument("--python-fd", type=int, required=True)
    result.add_argument("--python-sha256", required=True)
    result.add_argument("--source-fd", type=int, required=True)
    result.add_argument("--source-path", required=True)
    result.add_argument("--script-fd", type=int, required=True)
    result.add_argument("--script-path", required=True)
    result.add_argument("--script-sha256", required=True)
    result.add_argument("--environment-sha256", required=True)
    result.add_argument("--tmpdir", required=True)
    result.add_argument("forwarded", nargs=argparse.REMAINDER)
    return result


def main() -> int:
    arguments: argparse.Namespace | None = None
    try:
        modes = [
            sys.argv[index + 1]
            for index, value in enumerate(sys.argv[:-1])
            if value == "--mode"
        ]
        if modes == ["provider"]:
            return _provider_main(provider_parser().parse_args())
        if modes != ["outer"]:
            raise Refusal("launch mode is absent, duplicated or invalid")
        arguments = outer_parser().parse_args()
        _seal_result_owner()
        forwarded = arguments.forwarded
        if forwarded[:1] == ["--"]:
            forwarded = forwarded[1:]
        subject, initial_path = _initial_guard(arguments)
        if str(subject) != str(Path(arguments.subject_path).resolve(strict=True)):
            raise Refusal("subject descriptor resolves to an unexpected path")
        _verify_all(arguments)
        profile, command = _profile(arguments)
        argument_mode = command["argument_mode"]
        if argument_mode not in ("forbidden", "required"):
            raise Refusal("selected command argument mode is invalid")
        if argument_mode == "forbidden" and forwarded:
            raise Refusal("selected command forbids forwarded arguments")
        if argument_mode == "required" and not forwarded:
            raise Refusal("selected command requires forwarded arguments")
        _verify_subject_hash_manifests(arguments.subject_fd, profile)
        os.set_inheritable(arguments.result_fd, False)
        os.environ["KILIX_TRUSTED_LAUNCH_BOOTSTRAP_FD"] = str(arguments.bootstrap_fd)
        os.environ["KILIX_TRUSTED_LAUNCH_PYTHON_FD"] = str(arguments.python_fd)
        children = command["children"]
        if not isinstance(children, list):
            raise Refusal("selected command child table is malformed")
        for child in children:
            if not isinstance(child, dict):
                raise Refusal("selected command child entry is malformed")
            _run_separate_child(child, forwarded, arguments, initial_path)
        _verify_all(arguments)
        _write_result(arguments)
    except Refusal as exc:
        if arguments is not None and exc.refusal_code is not None:
            try:
                _write_refusal(arguments, exc.refusal_code)
            except BaseException:
                # The native launcher retains fail-closed ownership when the
                # result channel itself is absent, closed or malformed.
                pass
        print(f"TRUSTED_LAUNCH_BOOTSTRAP_REFUSAL: {exc}", file=sys.stderr)
        return 2
    except BaseException:
        print("TRUSTED_LAUNCH_BOOTSTRAP_REFUSAL: bootstrap operation failed", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
