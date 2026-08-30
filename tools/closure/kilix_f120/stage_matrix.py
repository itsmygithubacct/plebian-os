"""Cold/warm/independent-clean proof for one exact staged-provider closure."""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
import uuid
from pathlib import Path
from typing import Any, Mapping

from .cache import rename_directory_no_replace
from .canonical import (
    MAX_DOCUMENT_BYTES,
    atomic_write_json_new,
    canonical_bytes,
    canonical_sha256,
    require_sha256,
)
from .errors import BuildError
from .registration import Registration
from .stage import StageReport, stage_workspace


PREFIX_INVENTORY_SCHEMA = "kilix.f120.prefix-inventory/v1"
STAGE_MATRIX_SCHEMA = "kilix.f120.stage-matrix-report/v1"
LEG_NAMES = ("cold", "warm", "independent")


def _stable_identity(information: os.stat_result) -> tuple[int, ...]:
    return (
        information.st_dev,
        information.st_ino,
        information.st_mode,
        information.st_size,
        information.st_mtime_ns,
        information.st_ctime_ns,
    )


def _opened_identity(
    descriptor: int, observed: os.stat_result, label: str
) -> os.stat_result:
    opened = os.fstat(descriptor)
    if _stable_identity(opened) != _stable_identity(observed):
        raise BuildError(f"prefix entry changed while opening: {label}")
    return opened


def _scan_prefix(
    descriptor: int, relative: str, entries: list[dict[str, Any]]
) -> int:
    total = 0
    try:
        names = sorted(os.listdir(descriptor))
    except OSError as exc:
        raise BuildError("cannot enumerate staged prefix") from exc
    for name in names:
        label = f"{relative}/{name}" if relative else name
        try:
            observed = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        except OSError as exc:
            raise BuildError(f"cannot inspect prefix entry: {label}") from exc
        mode = stat.S_IMODE(observed.st_mode)
        if stat.S_ISDIR(observed.st_mode):
            try:
                child = os.open(
                    name,
                    os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=descriptor,
                )
            except OSError as exc:
                raise BuildError(f"cannot open prefix directory: {label}") from exc
            try:
                opened = _opened_identity(child, observed, label)
                entries.append(
                    {
                        "kind": "directory",
                        "mode": mode,
                        "path": label,
                    }
                )
                total += _scan_prefix(child, label, entries)
                if _stable_identity(os.fstat(child)) != _stable_identity(opened):
                    raise BuildError(f"prefix directory changed during audit: {label}")
            finally:
                os.close(child)
            continue
        if stat.S_ISREG(observed.st_mode):
            try:
                child = os.open(
                    name,
                    os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                    dir_fd=descriptor,
                )
            except OSError as exc:
                raise BuildError(f"cannot open prefix file: {label}") from exc
            try:
                opened = _opened_identity(child, observed, label)
                digest = hashlib.sha256()
                size = 0
                while True:
                    payload = os.read(child, 1024 * 1024)
                    if not payload:
                        break
                    digest.update(payload)
                    size += len(payload)
                if _stable_identity(os.fstat(child)) != _stable_identity(opened):
                    raise BuildError(f"prefix file changed during audit: {label}")
                if size != opened.st_size:
                    raise BuildError(f"prefix file length changed during audit: {label}")
                entries.append(
                    {
                        "kind": "regular",
                        "mode": mode,
                        "path": label,
                        "sha256": digest.hexdigest(),
                        "size": size,
                    }
                )
                total += size
            finally:
                os.close(child)
            continue
        raise BuildError(f"prefix contains a symlink or special entry: {label}")
    return total


def prefix_inventory(root: Path) -> dict[str, Any]:
    """Capture a path-free, no-follow inventory of one published prefix."""

    try:
        descriptor = os.open(
            root, os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
        )
    except OSError as exc:
        raise BuildError("staged prefix is not a readable real directory") from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISDIR(opened.st_mode):
            raise BuildError("staged prefix is not a real directory")
        entries: list[dict[str, Any]] = []
        total = _scan_prefix(descriptor, "", entries)
        if _stable_identity(os.fstat(descriptor)) != _stable_identity(opened):
            raise BuildError("staged prefix changed during audit")
    finally:
        os.close(descriptor)
    return {
        "entries": entries,
        "entry_count": len(entries),
        "regular_bytes": total,
        "schema": PREFIX_INVENTORY_SCHEMA,
    }


def _require_once_per_key(report: StageReport, label: str) -> tuple[int, int]:
    source_groups: dict[str, list[dict[str, Any]]] = {}
    for receipt in report.source_receipts:
        source_groups.setdefault(receipt["cache_key_sha256"], []).append(receipt)
    for key, receipts in source_groups.items():
        if sum(not item["cache_hit"] for item in receipts) != 1:
            raise BuildError(f"{label} source key was not missed exactly once: {key}")
        if sum(item["fetches"] for item in receipts) != 1:
            raise BuildError(f"{label} source key was not fetched exactly once: {key}")

    build_groups: dict[str, list[dict[str, Any]]] = {}
    for receipt in report.build_receipts:
        build_groups.setdefault(receipt["build_key_sha256"], []).append(receipt)
    for key, receipts in build_groups.items():
        if sum(not item["cache_hit"] for item in receipts) != 1:
            raise BuildError(f"{label} build key was not missed exactly once: {key}")
        if sum(item["builds"] for item in receipts) != 1:
            raise BuildError(f"{label} build key was not built exactly once: {key}")

    if report.source_cache_misses != len(source_groups):
        raise BuildError(f"{label} source miss total differs from unique source keys")
    if report.fetches != len(source_groups):
        raise BuildError(f"{label} fetch total differs from unique source keys")
    if report.build_cache_misses != len(build_groups):
        raise BuildError(f"{label} build miss total differs from unique build keys")
    if report.builds != len(build_groups):
        raise BuildError(f"{label} build total differs from unique build keys")
    return len(source_groups), len(build_groups)


def _verify_reports(reports: Mapping[str, StageReport]) -> tuple[int, int]:
    cold = reports["cold"]
    warm = reports["warm"]
    independent = reports["independent"]
    if cold.components != warm.components or cold.components != independent.components:
        raise BuildError("stage legs disagree on component count")
    if cold.artifacts != warm.artifacts or cold.artifacts != independent.artifacts:
        raise BuildError("stage legs disagree on artifact count")
    if cold.build_order != warm.build_order or cold.build_order != independent.build_order:
        raise BuildError("stage legs disagree on provider-first build order")
    if cold.evidence_document() != independent.evidence_document():
        raise BuildError("cold and independent stage evidence differ")

    warm_zero_values = (
        warm.source_cache_misses,
        warm.fetches,
        warm.fetch_bytes,
        warm.build_cache_misses,
        warm.builds,
    )
    if warm_zero_values != (0, 0, 0, 0, 0):
        raise BuildError("warm stage performed source or build work")
    if not all(item["cache_hit"] for item in warm.source_receipts):
        raise BuildError("warm stage has a source-cache miss receipt")
    if not all(item["cache_hit"] for item in warm.build_receipts):
        raise BuildError("warm stage has a build-cache miss receipt")

    source_keys, build_keys = _require_once_per_key(cold, "cold")
    independent_source_keys, independent_build_keys = _require_once_per_key(
        independent, "independent"
    )
    if (source_keys, build_keys) != (
        independent_source_keys,
        independent_build_keys,
    ):
        raise BuildError("cold and independent cache-key populations differ")
    return source_keys, build_keys


def _captured_regular(path: Path, label: str) -> bytes:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    except OSError as exc:
        raise BuildError(f"cannot open {label} without following links") from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise BuildError(f"{label} is not a regular file")
        chunks: list[bytes] = []
        total = 0
        while True:
            payload = os.read(descriptor, min(1024 * 1024, MAX_DOCUMENT_BYTES + 1 - total))
            if not payload:
                break
            chunks.append(payload)
            total += len(payload)
            if total > MAX_DOCUMENT_BYTES:
                raise BuildError(f"{label} exceeds the document byte bound")
        if _stable_identity(os.fstat(descriptor)) != _stable_identity(opened):
            raise BuildError(f"{label} changed while being captured")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _retire_candidate(candidate: Path, output: Path) -> None:
    retired_root = output.parent / ".kilix-f120-retired"
    retired_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(
        retired_root, os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    )
    try:
        destination = retired_root / f"{output.name}-{uuid.uuid4().hex}"
        rename_directory_no_replace(candidate, destination)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def run_stage_matrix(
    registration: Registration,
    workspace: dict[str, Any],
    *,
    output: Path,
    release: str,
    registration_sha256: str,
    workspace_manifest_sha256: str,
    local_sources: Mapping[str, Path] | None = None,
) -> dict[str, Any]:
    """Publish one retained cold/warm/independent-clean proof transaction."""

    registration_sha256 = require_sha256(
        registration_sha256, "stage matrix registration digest"
    )
    workspace_manifest_sha256 = require_sha256(
        workspace_manifest_sha256, "stage matrix workspace digest"
    )
    if not output.is_absolute():
        raise BuildError("stage matrix output must be absolute")
    if output.exists() or output.is_symlink():
        raise BuildError("refusing to overwrite an existing stage matrix")
    output = output.parent.resolve() / output.name
    if output.exists() or output.is_symlink():
        raise BuildError("refusing to overwrite an existing stage matrix")
    workspace_root = registration.workspace_root.resolve()
    try:
        output.relative_to(workspace_root)
    except ValueError:
        pass
    else:
        raise BuildError("stage matrix output is inside the workspace")
    output.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    candidate = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.candidate-", dir=output.parent)
    )
    candidate_identity = os.lstat(candidate)
    published = False
    reports: dict[str, StageReport] = {}
    inventories: dict[str, dict[str, Any]] = {}
    try:
        shared_cache = candidate / "cache-shared"
        independent_cache = candidate / "cache-independent"
        for leg in LEG_NAMES:
            cache = independent_cache if leg == "independent" else shared_cache
            prefix = candidate / f"prefix-{leg}"
            lock = candidate / f"lock-{leg}.json"
            report = stage_workspace(
                registration,
                workspace,
                cache=cache,
                destination=prefix,
                release=release,
                release_lock=lock,
                local_sources=local_sources,
            )
            reports[leg] = report
            atomic_write_json_new(candidate / f"report-{leg}.json", report.document())
            atomic_write_json_new(
                candidate / f"evidence-{leg}.json", report.evidence_document()
            )
            inventory = prefix_inventory(prefix)
            inventories[leg] = inventory
            atomic_write_json_new(candidate / f"inventory-{leg}.json", inventory)

        source_keys, build_keys = _verify_reports(reports)
        lock_paths = [candidate / f"lock-{leg}.json" for leg in LEG_NAMES]
        lock_payloads = [
            _captured_regular(path, f"{leg} release lock")
            for leg, path in zip(LEG_NAMES, lock_paths, strict=True)
        ]
        if len(set(lock_payloads)) != 1:
            raise BuildError("cold, warm and independent release locks differ")
        inventory_payloads = [canonical_bytes(inventories[leg]) for leg in LEG_NAMES]
        if len(set(inventory_payloads)) != 1:
            raise BuildError("cold, warm and independent prefix inventories differ")

        lock_sha256 = hashlib.sha256(lock_payloads[0]).hexdigest()
        lock_bytes = len(lock_payloads[0])
        inventory_sha256 = canonical_sha256(inventories["cold"])
        document = {
            "artifacts": reports["cold"].artifacts,
            "build_order": list(reports["cold"].build_order),
            "components": reports["cold"].components,
            "legs": [
                {
                    "evidence_sha256": canonical_sha256(
                        reports[leg].evidence_document()
                    ),
                    "inventory_sha256": canonical_sha256(inventories[leg]),
                    "lock_sha256": hashlib.sha256(lock_payloads[index]).hexdigest(),
                    "name": leg,
                    "report_sha256": canonical_sha256(reports[leg].document()),
                }
                for index, leg in enumerate(LEG_NAMES)
            ],
            "local_source_overrides": sorted((local_sources or {}).keys()),
            "prefix_inventory_sha256": inventory_sha256,
            "release": release,
            "release_lock_bytes": lock_bytes,
            "release_lock_sha256": lock_sha256,
            "registration_sha256": registration_sha256,
            "schema": STAGE_MATRIX_SCHEMA,
            "unique_build_keys": build_keys,
            "unique_source_keys": source_keys,
            "warm_zero_work": True,
            "workspace_manifest_sha256": workspace_manifest_sha256,
        }
        atomic_write_json_new(candidate / "stage-matrix.json", document)
        try:
            rename_directory_no_replace(candidate, output)
        except (FileExistsError, OSError) as exc:
            raise BuildError("refusing to overwrite an existing stage matrix") from exc
        published = True
        descriptor = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return document
    except BaseException:
        retirement_source: Path | None = None
        if published and (output.exists() or output.is_symlink()):
            observed = os.lstat(output)
            if (observed.st_dev, observed.st_ino) != (
                candidate_identity.st_dev,
                candidate_identity.st_ino,
            ):
                raise BuildError("published stage matrix identity changed before retirement")
            retirement_source = output
        elif candidate.exists() or candidate.is_symlink():
            retirement_source = candidate
        if retirement_source is not None:
            try:
                _retire_candidate(retirement_source, output)
            except OSError as exc:
                raise BuildError("failed stage matrix could not be retired") from exc
        raise
