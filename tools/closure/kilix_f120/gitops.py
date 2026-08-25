"""Read-only Git facts and deterministic committed-source identity."""

from __future__ import annotations

import hashlib
import os
import re
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence
from urllib.parse import urlsplit, urlunsplit

from .canonical import require_relative_path
from .errors import GitError


COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
GIT_TIMEOUT_SECONDS = 300
MAX_NOTICE_BYTES = 16 * 1024 * 1024
MAX_SOURCE_BLOB_BYTES = 256 * 1024 * 1024
MAX_SOURCE_TREE_BYTES = 2 * 1024 * 1024 * 1024


def git_environment(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    environment = {
        "GIT_ASKPASS": "/bin/false",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/bin:/bin",
    }
    if extra:
        environment.update(extra)
    return environment


def run_git(
    repository: Path,
    arguments: Sequence[str],
    *,
    text: bool = True,
    extra_environment: Mapping[str, str] | None = None,
    allow_file_protocol: bool = False,
) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]:
    command = ["git", "-c", "credential.helper="]
    if allow_file_protocol:
        command.extend(["-c", "protocol.file.allow=always"])
    command.extend(["-C", str(repository), *arguments])
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=text,
        env=git_environment(extra_environment),
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=GIT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        operation = arguments[0] if arguments else "operation"
        raise GitError(f"git {operation} exceeded the fixed timeout") from exc
    except BaseException:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        raise
    result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    if result.returncode:
        operation = arguments[0] if arguments else "operation"
        raise GitError(f"git {operation} failed with exit {result.returncode}")
    return result


def canonical_https_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.hostname != parsed.hostname.lower()
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise GitError("canonical_url must be canonical HTTPS without credentials")
    path = parsed.path.rstrip("/")
    if not path:
        raise GitError("canonical_url must name a repository path")
    return urlunsplit(("https", parsed.netloc, path, "", ""))


def normalize_remote_for_comparison(value: str) -> str | None:
    try:
        return canonical_https_url(value)
    except GitError:
        return None


@dataclass(frozen=True)
class RepositoryState:
    head: str
    dirty: bool
    origin: str | None


def repository_state(repository: Path) -> RepositoryState:
    head = run_git(repository, ["rev-parse", "HEAD"]).stdout.strip()
    if not isinstance(head, str) or not COMMIT_RE.fullmatch(head):
        raise GitError("repository HEAD is not an exact commit")
    status = run_git(
        repository,
        ["status", "--porcelain=v1", "--untracked-files=all"],
    ).stdout
    try:
        origin_result = subprocess.run(
            [
                "git",
                "-c",
                "credential.helper=",
                "-C",
                str(repository),
                "remote",
                "get-url",
                "origin",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=git_environment(),
            timeout=30,
            start_new_session=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitError("git remote exceeded the fixed timeout") from exc
    origin = origin_result.stdout.strip() if origin_result.returncode == 0 else None
    return RepositoryState(head=head, dirty=bool(status), origin=origin or None)


def resolve_commit(repository: Path, reference: str) -> str:
    result = run_git(repository, ["rev-parse", "--verify", f"{reference}^{{commit}}"]).stdout
    commit = result.strip()
    if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
        raise GitError("reference did not resolve to an exact commit")
    return commit


def commit_timestamp(repository: Path, commit: str) -> int:
    if not COMMIT_RE.fullmatch(commit):
        raise GitError("commit timestamp requested for a non-commit identifier")
    value = run_git(repository, ["show", "-s", "--format=%ct", commit]).stdout.strip()
    try:
        timestamp = int(value)
    except (TypeError, ValueError) as exc:
        raise GitError("commit timestamp is not an integer") from exc
    if timestamp < 0:
        raise GitError("commit timestamp is negative")
    return timestamp


def committed_blob(repository: Path, commit: str, relative_path: str) -> bytes:
    path = require_relative_path(relative_path, "committed blob path")
    size_value = run_git(repository, ["cat-file", "-s", f"{commit}:{path}"]).stdout
    try:
        size = int(size_value.strip())
    except (TypeError, ValueError) as exc:
        raise GitError("committed blob size is invalid") from exc
    if size < 0 or size > MAX_NOTICE_BYTES:
        raise GitError("committed notice blob exceeds the fixed size limit")
    result = run_git(repository, ["show", f"{commit}:{path}"], text=False)
    output = result.stdout
    assert isinstance(output, bytes)
    if len(output) != size:
        raise GitError("committed notice blob size changed during read")
    return output


def _hash_field(digest: "hashlib._Hash", value: bytes) -> None:
    digest.update(len(value).to_bytes(8, byteorder="big", signed=False))
    digest.update(value)


def source_tree_sha256(repository: Path, commit: str) -> str:
    """Hash the exact committed tree, including gitlinks but not their contents."""

    if not COMMIT_RE.fullmatch(commit):
        raise GitError("source digest requested for a non-commit identifier")
    listing_result = run_git(
        repository,
        ["ls-tree", "-r", "-z", "--full-tree", commit],
        text=False,
    )
    listing = listing_result.stdout
    assert isinstance(listing, bytes)
    digest = hashlib.sha256(b"kilix.f120.source-tree/v1\0")
    count = 0
    total_bytes = 0
    for record in listing.split(b"\0"):
        if not record:
            continue
        try:
            header, path = record.split(b"\t", 1)
            mode, kind, object_id = header.split(b" ", 2)
        except ValueError as exc:
            raise GitError("git ls-tree returned an unparseable record") from exc
        if kind not in {b"blob", b"commit"}:
            raise GitError("source tree contains an unsupported Git object kind")
        for field in (mode, kind, object_id, path):
            _hash_field(digest, field)
        if kind == b"blob":
            size_value = run_git(
                repository, ["cat-file", "-s", object_id.decode("ascii")]
            ).stdout
            try:
                size = int(size_value.strip())
            except (TypeError, ValueError) as exc:
                raise GitError("source blob size is invalid") from exc
            total_bytes += size
            if size < 0 or size > MAX_SOURCE_BLOB_BYTES:
                raise GitError("source blob exceeds the fixed size limit")
            if total_bytes > MAX_SOURCE_TREE_BYTES:
                raise GitError("source tree exceeds the fixed size limit")
            blob_result = run_git(repository, ["cat-file", "blob", object_id.decode("ascii")], text=False)
            blob = blob_result.stdout
            assert isinstance(blob, bytes)
            if len(blob) != size:
                raise GitError("source blob size changed during read")
            _hash_field(digest, blob)
        else:
            _hash_field(digest, b"")
        count += 1
    digest.update(count.to_bytes(8, byteorder="big", signed=False))
    return digest.hexdigest()
