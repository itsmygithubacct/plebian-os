"""Fetch-once, content-addressed Git source cache."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cache import (
    cache_lock,
    cache_root,
    directory_bytes,
    publish_directory,
    quarantine,
    temporary_directory,
)
from .canonical import atomic_write_json, load_json, require_sha256
from .errors import CacheError, ContractError, GitError
from .gitops import COMMIT_RE, canonical_https_url, resolve_commit, run_git, source_tree_sha256


SOURCE_METADATA_SCHEMA = "kilix.f120.source-cache/v1"
CACHED_SOURCE_REF = "refs/kilix-f120/source"


@dataclass(frozen=True)
class SourceCacheResult:
    repository: Path
    hit: bool
    fetches: int
    fetch_bytes: int
    cache_bytes: int


def _metadata(entry: Path) -> dict[str, Any]:
    document = load_json(entry / "metadata.json")
    if not isinstance(document, dict) or set(document) != {
        "schema",
        "source_sha256",
    }:
        raise CacheError("source cache metadata shape is invalid")
    if document["schema"] != SOURCE_METADATA_SCHEMA:
        raise CacheError("source cache metadata schema is invalid")
    require_sha256(document["source_sha256"], "source cache source_sha256")
    return document


def _validate_entry(entry: Path, source_sha256: str) -> Path:
    if entry.is_symlink() or not entry.is_dir():
        raise CacheError("source cache entry is not a real directory")
    if {item.name for item in entry.iterdir()} != {"metadata.json", "repo.git"}:
        raise CacheError("source cache entry contains unexpected files")
    metadata = _metadata(entry)
    if metadata["source_sha256"] != source_sha256:
        raise CacheError("source cache key does not bind metadata")
    repository = entry / "repo.git"
    if repository.is_symlink() or not repository.is_dir():
        raise CacheError("source cache repository is invalid")
    cached_commit = resolve_commit(repository, CACHED_SOURCE_REF)
    if source_tree_sha256(repository, cached_commit) != source_sha256:
        raise CacheError("source cache repository failed content verification")
    return repository


def _create_entry(
    root: Path,
    source_sha256: str,
    commit: str,
    canonical_url: str,
    local_source: Path | None,
) -> tuple[Path, int, int]:
    candidate = temporary_directory(root, "sources")
    try:
        repository = candidate / "repo.git"
        repository.mkdir(mode=0o755)
        run_git(repository, ["init", "--bare"])
        source = canonical_url
        allow_file = False
        if local_source is not None:
            source = str(local_source.resolve())
            allow_file = True
        run_git(
            repository,
            [
                "-c",
                "fetch.unpackLimit=0",
                "fetch",
                "--no-tags",
                "--force",
                "--depth=1",
                source,
                commit,
            ],
            allow_file_protocol=allow_file,
        )
        pack_bytes = sum(
            item.stat().st_size
            for item in (repository / "objects" / "pack").glob("*.pack")
            if item.is_file() and not item.is_symlink()
        )
        if pack_bytes == 0:
            pack_bytes = sum(
                item.stat().st_size
                for item in (repository / "objects").glob("[0-9a-f][0-9a-f]/*")
                if item.is_file() and not item.is_symlink()
            )
        fetched = resolve_commit(repository, "FETCH_HEAD")
        if fetched != commit:
            raise CacheError("fetch did not return the requested exact commit")
        run_git(repository, ["update-ref", CACHED_SOURCE_REF, commit])
        # FETCH_HEAD records the transport URL, which may be an explicitly
        # supplied local evidence path.  The content ref above is sufficient.
        (repository / "FETCH_HEAD").unlink(missing_ok=True)
        actual_source = source_tree_sha256(repository, commit)
        if actual_source != source_sha256:
            raise CacheError("fetched source tree does not match workspace manifest")
        atomic_write_json(
            candidate / "metadata.json",
            {
                "schema": SOURCE_METADATA_SCHEMA,
                "source_sha256": source_sha256,
            },
        )
        size = directory_bytes(candidate)
        return candidate, size, pack_bytes
    except BaseException:
        shutil.rmtree(candidate, ignore_errors=True)
        raise


def ensure_source(
    cache: Path,
    component: dict[str, Any],
    *,
    local_source: Path | None = None,
) -> SourceCacheResult:
    root = cache_root(cache)
    source_sha256 = require_sha256(
        component.get("source_sha256"), "component source_sha256"
    )
    commit = component.get("resolved_commit")
    if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
        raise ContractError("source cache requires a resolved exact commit")
    canonical_url = canonical_https_url(component.get("canonical_url", ""))
    if local_source is not None:
        local_source = local_source.resolve()
        if not local_source.is_dir():
            raise CacheError("explicit local source override is not a directory")
        if resolve_commit(local_source, commit) != commit:
            raise CacheError("explicit local source lacks the exact resolved commit")
    entry = root / "sources" / "sha256" / source_sha256
    with cache_lock(root, "sources", source_sha256):
        if entry.exists() or entry.is_symlink():
            try:
                repository = _validate_entry(entry, source_sha256)
            except (CacheError, ContractError, GitError, OSError):
                quarantine(root, "sources", entry)
            else:
                return SourceCacheResult(
                    repository=repository,
                    hit=True,
                    fetches=0,
                    fetch_bytes=0,
                    cache_bytes=directory_bytes(entry),
                )
        candidate, size, fetch_bytes = _create_entry(
            root, source_sha256, commit, canonical_url, local_source
        )
        try:
            publish_directory(candidate, entry)
        except BaseException:
            shutil.rmtree(candidate, ignore_errors=True)
            raise
        repository = _validate_entry(entry, source_sha256)
        return SourceCacheResult(
            repository=repository,
            hit=False,
            fetches=1,
            fetch_bytes=fetch_bytes,
            cache_bytes=size,
        )
