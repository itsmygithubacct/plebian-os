"""Launch the builder's foreground QEMU in one owned Kilix tab.

The caller supplies a fresh private VM directory. The tab owns QEMU through
kilix run; the builder never signals a PID from a file or adopts an existing VM.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import time

from launch_transport import literal_launch
from qemu_runtime import qmp_socket_path


def require_host() -> tuple[list[str], str]:
    kitten = shutil.which(os.environ.get("KILIX_KITTEN") or "kitten")
    kilix = shutil.which("kilix")
    address = os.environ.get("KITTY_LISTEN_ON")
    if not kitten or not kilix or not address:
        raise RuntimeError("QEMU tabs require kilix, kitten and KITTY_LISTEN_ON; "
                           "run inside Kilix or choose --gui --external-window")
    remote = [kitten, "@", "--to", address]
    password = os.environ.get("KILIX_RC_PASSWORD_FILE")
    if password:
        remote += ["--password-file", password]
    # Refuse before disk creation when remote control is unavailable.
    subprocess.run([*remote, "ls"], check=True, capture_output=True,
                   timeout=10)
    return remote, kilix


def _ready(directory: Path, *, deadline: float | None = None) -> bool:
    # A socket timeout per recv would let a slow peer extend this probe forever.
    # Bound the whole greeting, including the remaining launch readiness budget.
    probe_deadline = time.monotonic() + 0.2
    if deadline is not None:
        probe_deadline = min(probe_deadline, deadline)
    # QMP can listen before display capture fails. Require the host's first
    # rendered-content receipt as well as the guest's live greeting.
    try:
        if (directory / "tab.ready").read_bytes() != b"content-ready\n":
            return False
    except OSError:
        return False
    # Only read the greeting, never send a VM lifecycle command. A live QMP
    # listener is stronger evidence than a pidfile written during early init.
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            endpoint = str(qmp_socket_path(directory))
            remaining = probe_deadline - time.monotonic()
            if remaining <= 0:
                return False
            connection.settimeout(remaining)
            connection.connect(endpoint)
            line = bytearray()
            # The 64 KiB limit includes the terminating LF (CRLF is accepted).
            # EOF or reaching the limit without LF is never a complete greeting.
            while len(line) < 65536:
                remaining = probe_deadline - time.monotonic()
                if remaining <= 0:
                    return False
                connection.settimeout(remaining)
                chunk = connection.recv(min(4096, 65536 - len(line)))
                if not chunk:
                    return False
                line.extend(chunk)
                newline = line.find(b"\n")
                if newline >= 0:
                    greeting = json.loads(line[:newline + 1])
                    return (time.monotonic() < probe_deadline
                            and isinstance(greeting, dict)
                            and isinstance(greeting.get("QMP"), dict))
        return False
    except (OSError, ValueError):
        return False


def _marker_absent(payload, marker: str) -> bool:
    """Require a complete window/environment listing before proving absence."""
    name, value = marker.split("=", 1)
    if not isinstance(payload, list):
        return False
    for os_window in payload:
        if not isinstance(os_window, dict) or not isinstance(os_window.get("tabs"), list):
            return False
        for tab in os_window["tabs"]:
            if not isinstance(tab, dict) or not isinstance(tab.get("windows"), list):
                return False
            for window in tab["windows"]:
                if not isinstance(window, dict) or not isinstance(window.get("env"), dict):
                    return False
                environment = window["env"]
                if not all(isinstance(v, str) for v in environment.values()):
                    return False
                if environment.get(name) == value:
                    return False
    return True


def _close_owned(remote: list[str], marker: str) -> None:
    match = "env:" + marker
    try:
        subprocess.run([*remote, "close-window", "--match", match],
                       check=True, capture_output=True, timeout=10)
    except Exception:
        # A short-lived app may already have closed its tab. Prove absence
        # through an authenticated complete listing; never suppress a refusal
        # while a matching tab remains or its state cannot be inspected.
        try:
            result = subprocess.run([*remote, "ls", "--all-env-vars"],
                                    check=True, capture_output=True, text=True, timeout=10)
            if _marker_absent(json.loads(result.stdout), marker):
                return
        except Exception:
            pass
        raise


def launch(argv: list[str], title: str, directory: Path, *, timeout: float = 20) -> None:
    remote, kilix = require_host()
    if any((directory / name).exists() or (directory / name).is_symlink()
           for name in ("qemu.pid", "tab.ready")):
        raise RuntimeError("QEMU tab requires a fresh VM launch directory")
    endpoint = qmp_socket_path(directory)
    if endpoint.exists() or endpoint.is_symlink():
        raise RuntimeError("QEMU tab requires a fresh QMP endpoint")
    if any(flag in argv for flag in ("-daemonize", "--daemonize")):
        raise ValueError("QEMU in a tab must remain in the foreground")
    marker = "KILIX_VM_LAUNCH=" + secrets.token_hex(16)
    target, environment, cwd = literal_launch(
        [kilix, "run", *argv],
        {"KILIX_VM_LAUNCH": marker.split("=", 1)[1], "KILIX_IN_OVERLAY": "1",
         "KILIX_RUN_READY_FILE": str(directory / "tab.ready")}, str(Path.cwd()))
    title = title.encode("utf-8", "replace").decode("utf-8")
    command = [*remote, "launch", "--type=tab", "--keep-focus", "--tab-title", title]
    if cwd is not None:
        command += ["--cwd", cwd]
    for key, value in environment.items():
        command += ["--env", f"{key}={value}"]
    command += ["--", *target]
    try:
        result = subprocess.run(command, check=True, capture_output=True,
                                text=True, timeout=10)
        if not result.stdout.strip().isascii() or not result.stdout.strip().isdigit():
            raise RuntimeError("Kilix did not return a pane ID for the QEMU tab")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if _ready(directory, deadline=deadline) and time.monotonic() < deadline:
                return
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(0.1, remaining))
        raise RuntimeError("QEMU tab did not become ready; check Kilix embedding dependencies")
    except BaseException as error:
        # Match our unguessable launch environment even when launch timed out
        # or returned a malformed ID. Never close by title or signal a PID.
        try:
            _close_owned(remote, marker)
        except Exception as cleanup_error:
            raise RuntimeError(f"QEMU launch failed ({error}); tab cleanup failed "
                               f"({cleanup_error}); inspect {marker}") from error
        raise
