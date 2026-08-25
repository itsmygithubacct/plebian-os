"""Canonical JSON, bounded loading, hashing, and atomic publication."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from .errors import ContractError


MAX_DOCUMENT_BYTES = 4 * 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")


def canonical_bytes(value: Any) -> bytes:
    """Return the exact canonical representation used by frozen F120 v1."""

    try:
        encoded = json.dumps(value, indent=2, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"value is not canonical JSON: {exc}") from exc
    return (encoded + "\n").encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path, *, maximum_bytes: int = MAX_DOCUMENT_BYTES) -> Any:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ContractError(f"cannot stat JSON document: {exc.strerror}") from exc
    if size > maximum_bytes:
        raise ContractError(f"document exceeds {maximum_bytes} bytes")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ContractError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject_nonfinite(value: str) -> None:
        raise ContractError(f"non-finite JSON number is forbidden: {value}")

    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(
                handle,
                object_pairs_hook=reject_duplicates,
                parse_constant=reject_nonfinite,
            )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot load JSON document: {exc}") from exc


def atomic_write(path: Path, payload: bytes, *, mode: int = 0o644) -> None:
    """Publish bytes with a same-directory fsync + replace transaction."""

    path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def atomic_write_json(path: Path, value: Any, *, mode: int = 0o644) -> None:
    atomic_write(path, canonical_bytes(value), mode=mode)


def require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ContractError(f"{label} must be a lowercase SHA-256 digest")
    return value


def require_identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) > 128 or not ID_RE.fullmatch(value):
        raise ContractError(f"{label} is not a valid F120 identifier")
    return value


def require_relative_path(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ContractError(f"{label} must be a non-empty relative path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or value != pure.as_posix():
        raise ContractError(f"{label} must be a normalized relative path")
    return value


def stable_instance_id(component_id: str, relative_path: str) -> str:
    """Mint a path-distinct ID without embedding an operator path."""

    require_identifier(component_id, "component_id")
    relative = require_relative_path(relative_path, "component path")
    suffix = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:12]
    return f"{component_id}-{suffix}"
