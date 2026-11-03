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


def _ready(directory: Path) -> bool:
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
            connection.settimeout(0.2)
            connection.connect(str(directory / "qmp.sock"))
            with connection.makefile("rb") as stream:
                greeting = json.loads(stream.readline(65536))
        return isinstance(greeting, dict) and isinstance(greeting.get("QMP"), dict)
    except (OSError, ValueError):
        return False


def launch(argv: list[str], title: str, directory: Path, *, timeout: float = 20) -> None:
    remote, kilix = require_host()
    if any((directory / name).exists() or (directory / name).is_symlink()
           for name in ("qemu.pid", "qmp.sock", "tab.ready")):
        raise RuntimeError("QEMU tab requires a fresh VM launch directory")
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
            if _ready(directory):
                return
            time.sleep(0.1)
        raise RuntimeError("QEMU tab did not become ready; check Kilix embedding dependencies")
    except BaseException as error:
        # Match our unguessable launch environment even when launch timed out
        # or returned a malformed ID. Never close by title or signal a PID.
        try:
            subprocess.run([*remote, "close-window", "--match", "env:" + marker],
                           check=True, capture_output=True, timeout=10)
        except Exception as cleanup_error:
            raise RuntimeError(f"QEMU launch failed ({error}); tab cleanup failed "
                               f"({cleanup_error}); inspect {marker}") from error
        raise
