"""Linux execution-closure monitor for registered provider build commands."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import signal
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .canonical import file_sha256
from .errors import BuildError
from .registration import ToolExecutable, Toolchain


AUTHORITY_BOOTSTRAP_SHA256 = (
    "ae92add2325bc9203d59232b710f678fe7b50d7fef83280d26486a1232d1c913"
)
AUTHORITY_PYTHON_SHA256 = (
    "0dc3a692fa85fcdb7f1a5877d2adf179809ac417a07ffde2373c832863800a15"
)
AUTHORITY_ENVIRONMENT = {
    "bootstrap_fd": "KILIX_TRUSTED_LAUNCH_BOOTSTRAP_FD",
    "python_fd": "KILIX_TRUSTED_LAUNCH_PYTHON_FD",
}
PTRACE_TRACEME = 0
PTRACE_CONT = 7
PTRACE_SETOPTIONS = 0x4200
PTRACE_GETEVENTMSG = 0x4201
PTRACE_O_TRACEFORK = 0x00000002
PTRACE_O_TRACEVFORK = 0x00000004
PTRACE_O_TRACECLONE = 0x00000008
PTRACE_O_TRACEEXEC = 0x00000010
PTRACE_O_EXITKILL = 0x00100000
PTRACE_EVENT_FORK = 1
PTRACE_EVENT_VFORK = 2
PTRACE_EVENT_CLONE = 3
PTRACE_EVENT_EXEC = 4
WAIT_ALL = 0x40000000
MAX_CMDLINE_BYTES = 1024 * 1024


@dataclass(frozen=True)
class AuthorityContext:
    bootstrap_fd: int
    python_fd: int


@dataclass(frozen=True)
class Launch:
    arguments: tuple[str, ...]
    environment: Mapping[str, str] | None
    pass_fds: tuple[int, ...]
    temporary_cwd: Path | None


def _fd_sha256(descriptor: int) -> str:
    digest = hashlib.sha256()
    offset = 0
    while True:
        block = os.pread(descriptor, 1024 * 1024, offset)
        if not block:
            return digest.hexdigest()
        digest.update(block)
        offset += len(block)


def _authority_context() -> AuthorityContext:
    values: dict[str, int] = {}
    for field, name in AUTHORITY_ENVIRONMENT.items():
        raw = os.environ.get(name)
        if raw is None or not raw.isascii() or not raw.isdecimal():
            raise BuildError("Python build requires the external F120 authority launcher")
        values[field] = int(raw)
    context = AuthorityContext(**values)
    try:
        bootstrap = os.fstat(context.bootstrap_fd)
        python = os.fstat(context.python_fd)
    except OSError as exc:
        raise BuildError("external F120 authority descriptors are unavailable") from exc
    if not stat.S_ISREG(bootstrap.st_mode) or not stat.S_ISREG(python.st_mode):
        raise BuildError("external F120 authority descriptors are not regular files")
    if _fd_sha256(context.bootstrap_fd) != AUTHORITY_BOOTSTRAP_SHA256:
        raise BuildError("external F120 authority bootstrap identity mismatch")
    if _fd_sha256(context.python_fd) != AUTHORITY_PYTHON_SHA256:
        raise BuildError("external F120 authority interpreter identity mismatch")
    return context


def _environment_sha256(environment: Mapping[str, str]) -> str:
    encoded = json.dumps(
        dict(environment), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _open_verified(path: Path, expected_sha256: str, *, directory: bool) -> int:
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    if directory:
        flags |= os.O_DIRECTORY
    try:
        descriptor = os.open(path, flags)
        information = os.fstat(descriptor)
    except OSError as exc:
        raise BuildError("registered execution input could not be retained") from exc
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected_type(information.st_mode):
        os.close(descriptor)
        raise BuildError("registered execution input has the wrong file type")
    if not directory and _fd_sha256(descriptor) != expected_sha256:
        os.close(descriptor)
        raise BuildError("registered execution input digest mismatch")
    os.set_inheritable(descriptor, True)
    return descriptor


def _provider_launch(
    executable: ToolExecutable,
    rendered: Sequence[str],
    toolchain: Toolchain,
    environment: Mapping[str, str],
    source: Path,
    temporary_root: Path,
) -> Launch:
    if executable.interpreter is None:
        raise BuildError("Python script lacks a registered interpreter")
    interpreter = toolchain.executable_record(executable.interpreter)
    context = _authority_context()
    if interpreter.sha256 != AUTHORITY_PYTHON_SHA256:
        raise BuildError("registered Python differs from the F120 authority interpreter")
    script_fd = _open_verified(executable.path, executable.sha256, directory=False)
    source_fd = _open_verified(source, "", directory=True)
    bootstrap_fd = os.dup(context.bootstrap_fd)
    python_fd = os.dup(context.python_fd)
    for descriptor in (bootstrap_fd, python_fd):
        os.set_inheritable(descriptor, True)
    cwd = temporary_root / f"python-{os.getpid()}-{time.monotonic_ns()}"
    cwd.mkdir(mode=0o700)
    provider_environment = dict(environment)
    provider_environment["TMPDIR"] = str(cwd)
    bootstrap_path = f"/proc/self/fd/{bootstrap_fd}"
    python_path = f"/proc/self/fd/{python_fd}"
    arguments = (
        python_path,
        "-I",
        "-S",
        "-B",
        bootstrap_path,
        "--mode",
        "provider",
        "--bootstrap-fd",
        str(bootstrap_fd),
        "--bootstrap-sha256",
        AUTHORITY_BOOTSTRAP_SHA256,
        "--python-fd",
        str(python_fd),
        "--python-sha256",
        AUTHORITY_PYTHON_SHA256,
        "--source-fd",
        str(source_fd),
        "--source-path",
        str(source),
        "--script-fd",
        str(script_fd),
        "--script-path",
        str(executable.path),
        "--script-sha256",
        executable.sha256,
        "--environment-sha256",
        _environment_sha256(provider_environment),
        "--tmpdir",
        str(cwd),
        "--",
        *rendered[1:],
    )
    return Launch(
        arguments=arguments,
        environment=provider_environment,
        pass_fds=(bootstrap_fd, python_fd, source_fd, script_fd),
        temporary_cwd=cwd,
    )


def prepare_launch(
    executable: ToolExecutable,
    rendered: Sequence[str],
    toolchain: Toolchain,
    environment: Mapping[str, str],
    source: Path,
    temporary_root: Path,
) -> Launch:
    if executable.kind == "native":
        return Launch(tuple(rendered), None, (), None)
    if executable.kind == "python-interpreter":
        raise BuildError("direct Python commands are forbidden; register a python-script")
    if executable.kind == "python-script":
        return _provider_launch(
            executable, rendered, toolchain, environment, source, temporary_root
        )
    if executable.kind == "script":
        if executable.interpreter is None:
            raise BuildError("script lacks a registered interpreter")
        interpreter = toolchain.executable_record(executable.interpreter)
        script_fd = _open_verified(executable.path, executable.sha256, directory=False)
        return Launch(
            (
                str(interpreter.path),
                f"/proc/self/fd/{script_fd}",
                *rendered[1:],
            ),
            None,
            (script_fd,),
            None,
        )
    raise BuildError("unclassified registered executable")


def _ptrace(request: int, process: int, address: int = 0, data: int = 0) -> int:
    library = ctypes.CDLL(None, use_errno=True)
    result = library.ptrace(
        ctypes.c_ulong(request),
        ctypes.c_ulong(process),
        ctypes.c_void_p(address),
        ctypes.c_void_p(data),
    )
    if result == -1:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    return int(result)


def _process_arguments(process: int) -> tuple[str, ...]:
    try:
        raw = Path(f"/proc/{process}/cmdline").read_bytes()
    except OSError as exc:
        raise BuildError("cannot inspect registered executable argv") from exc
    if len(raw) > MAX_CMDLINE_BYTES or not raw.endswith(b"\0"):
        raise BuildError("registered executable argv is absent or oversized")
    try:
        return tuple(item.decode("utf-8") for item in raw[:-1].split(b"\0"))
    except UnicodeDecodeError as exc:
        raise BuildError("registered executable argv is not UTF-8") from exc


def _process_executable(process: int) -> tuple[os.stat_result, str]:
    try:
        descriptor = os.open(f"/proc/{process}/exe", os.O_RDONLY | os.O_CLOEXEC)
        information = os.fstat(descriptor)
        digest = _fd_sha256(descriptor)
    except OSError as exc:
        raise BuildError("cannot inspect registered executable identity") from exc
    finally:
        if "descriptor" in locals():
            os.close(descriptor)
    return information, digest


def _registered_identities(toolchain: Toolchain) -> dict[tuple[int, int, str], ToolExecutable]:
    result: dict[tuple[int, int, str], ToolExecutable] = {}
    for executable in toolchain.executables:
        information = executable.path.stat(follow_symlinks=False)
        result[(information.st_dev, information.st_ino, executable.sha256)] = executable
    return result


def _verify_exec_event(
    process: int,
    toolchain: Toolchain,
    authority_python_sha256: str,
) -> None:
    information, digest = _process_executable(process)
    executable = _registered_identities(toolchain).get(
        (information.st_dev, information.st_ino, digest)
    )
    arguments = _process_arguments(process)
    if executable is not None:
        if executable.kind != "python-interpreter":
            return
        if digest != authority_python_sha256:
            raise BuildError("registered Python differs from the authority interpreter")
    if digest != authority_python_sha256 or len(arguments) < 7:
        raise BuildError("provider build attempted an undeclared executable")
    if arguments[1:4] != ("-I", "-S", "-B"):
        raise BuildError("provider Python lacks exact ordered -I -S -B")
    if not arguments[4].startswith("/proc/self/fd/"):
        raise BuildError("provider Python did not load the trusted bootstrap descriptor")
    try:
        bootstrap_number = int(arguments[4].removeprefix("/proc/self/fd/"))
        bootstrap_descriptor = os.open(
            f"/proc/{process}/fd/{bootstrap_number}", os.O_RDONLY | os.O_CLOEXEC
        )
        bootstrap_digest = _fd_sha256(bootstrap_descriptor)
        os.close(bootstrap_descriptor)
    except (OSError, ValueError) as exc:
        raise BuildError("provider Python bootstrap descriptor is unavailable") from exc
    if bootstrap_digest != AUTHORITY_BOOTSTRAP_SHA256:
        raise BuildError("provider Python bootstrap identity mismatch")
    try:
        mode_index = arguments.index("--mode")
    except ValueError as exc:
        raise BuildError("provider Python launch lacks an authority mode") from exc
    if mode_index + 1 >= len(arguments) or arguments[mode_index + 1] != "provider":
        raise BuildError("provider Python launch uses the wrong authority mode")


def _kill_group(process: int) -> None:
    try:
        os.killpg(process, signal.SIGKILL)
    except ProcessLookupError:
        pass


def run_with_execution_closure(
    launch: Launch,
    *,
    environment: Mapping[str, str],
    cwd: Path,
    toolchain: Toolchain,
    timeout: float,
) -> None:
    child = os.fork()
    if child == 0:
        try:
            os.setsid()
            os.chdir(launch.temporary_cwd or cwd)
            null = os.open("/dev/null", os.O_RDWR | os.O_CLOEXEC)
            os.dup2(null, 0)
            os.dup2(null, 1)
            os.dup2(null, 2)
            if null > 2:
                os.close(null)
            _ptrace(PTRACE_TRACEME, 0)
            os.kill(os.getpid(), signal.SIGSTOP)
            os.execve(
                launch.arguments[0],
                launch.arguments,
                dict(launch.environment or environment),
            )
        except BaseException:
            os._exit(127)
    started = time.monotonic()
    root_status: int | None = None
    traced = {child}
    try:
        waited, status = os.waitpid(child, WAIT_ALL)
        if waited != child or not os.WIFSTOPPED(status):
            raise BuildError("provider execution monitor did not reach its initial stop")
        options = (
            PTRACE_O_TRACEFORK
            | PTRACE_O_TRACEVFORK
            | PTRACE_O_TRACECLONE
            | PTRACE_O_TRACEEXEC
            | PTRACE_O_EXITKILL
        )
        _ptrace(PTRACE_SETOPTIONS, child, 0, options)
        _ptrace(PTRACE_CONT, child)
        while traced:
            if time.monotonic() - started > timeout:
                raise BuildError("provider build exceeded the fixed timeout")
            try:
                process, status = os.waitpid(-1, WAIT_ALL | os.WNOHANG)
            except ChildProcessError:
                break
            if process == 0:
                time.sleep(0.01)
                continue
            if os.WIFEXITED(status) or os.WIFSIGNALED(status):
                traced.discard(process)
                if process == child:
                    root_status = status
                continue
            if not os.WIFSTOPPED(status):
                continue
            traced.add(process)
            event = status >> 16
            stop_signal = os.WSTOPSIG(status)
            if event == PTRACE_EVENT_EXEC:
                _verify_exec_event(process, toolchain, AUTHORITY_PYTHON_SHA256)
            elif event in {PTRACE_EVENT_FORK, PTRACE_EVENT_VFORK, PTRACE_EVENT_CLONE}:
                message = ctypes.c_ulong()
                _ptrace(PTRACE_GETEVENTMSG, process, 0, ctypes.addressof(message))
                traced.add(int(message.value))
            delivered = 0 if stop_signal in {signal.SIGSTOP, signal.SIGTRAP} else stop_signal
            _ptrace(PTRACE_CONT, process, 0, delivered)
    except (BuildError, OSError):
        _kill_group(child)
        while True:
            try:
                process, _ = os.waitpid(-1, WAIT_ALL)
                if process <= 0:
                    break
            except ChildProcessError:
                break
        raise BuildError("provider build execution closure refused the command")
    finally:
        for descriptor in launch.pass_fds:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if launch.temporary_cwd is not None:
            try:
                launch.temporary_cwd.rmdir()
            except OSError:
                pass
    if root_status is None or not os.WIFEXITED(root_status) or os.WEXITSTATUS(root_status):
        code = os.WEXITSTATUS(root_status) if root_status is not None and os.WIFEXITED(root_status) else 128
        raise BuildError(f"provider build failed with exit {code}")
