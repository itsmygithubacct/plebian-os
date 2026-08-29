"""Build and atomically stage a qualified F120 workspace closure."""

from __future__ import annotations

import copy
import hashlib
import heapq
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .build_cache import (
    BuildCacheResult,
    ensure_build,
    staged_dependencies_sha256,
)
from .cache import cache_root, directory_bytes, rename_directory_no_replace
from .canonical import atomic_write_json, file_sha256, load_json, require_identifier
from .contracts import validate_path
from .errors import BuildError, ContractError
from .keys import licenses_sha256
from .registration import (
    RESERVED_STAGED_DEPENDENCIES_OPTION,
    ComponentRegistration,
    Registration,
)
from .release import emit_release_lock
from .source_cache import SourceCacheResult, ensure_source


STAGE_MANIFEST_SCHEMA = "kilix.f120.stage-manifest/v1"


@dataclass(frozen=True)
class StageReport:
    components: int
    source_cache_hits: int
    source_cache_misses: int
    fetches: int
    fetch_bytes: int
    build_cache_hits: int
    build_cache_misses: int
    builds: int
    cache_bytes: int
    staged_bytes: int
    artifacts: int

    def document(self) -> dict[str, int | str]:
        return {
            "artifacts": self.artifacts,
            "build_cache_hits": self.build_cache_hits,
            "build_cache_misses": self.build_cache_misses,
            "builds": self.builds,
            "cache_bytes": self.cache_bytes,
            "components": self.components,
            "fetches": self.fetches,
            "fetch_bytes": self.fetch_bytes,
            "schema": "kilix.f120.stage-report/v1",
            "source_cache_hits": self.source_cache_hits,
            "source_cache_misses": self.source_cache_misses,
            "staged_bytes": self.staged_bytes,
        }


def _verify_component_registration(
    observed: dict[str, Any], registration: ComponentRegistration
) -> None:
    expected = {
        "abi_version": registration.abi_version,
        "api_version": registration.api_version,
        "architecture": registration.architecture,
        "build_options": registration.effective_build_options,
        "canonical_url": registration.canonical_url,
        "component_id": registration.component_id,
        "component_version": registration.component_version,
        "expected_commit": registration.expected_commit,
        "features": list(registration.features),
        "instance_id": registration.instance_id,
        "licenses": [dict(item) for item in registration.licenses],
        "notices": [dict(item) for item in registration.notices],
        "publication_disposition": registration.publication_disposition,
        "ref_kind": registration.ref_kind,
        "requested_ref": registration.requested_ref,
        "required_tests": list(registration.required_tests),
        "runtime_kind": registration.runtime_kind,
        "toolchain": registration.toolchain.contract_value(),
        "visibility": registration.visibility,
    }
    for field, value in expected.items():
        if observed.get(field) != value:
            raise ContractError(
                f"workspace manifest differs from registration: {registration.instance_id}:{field}"
            )


def _artifact_record(
    component: dict[str, Any],
    build_key: str,
    artifact: dict[str, str],
) -> dict[str, Any]:
    return {
        "architecture": component["architecture"],
        "artifact_id": artifact["artifact_id"],
        "artifact_kind": artifact["artifact_kind"],
        "artifact_sha256": artifact["artifact_sha256"],
        "build_key_sha256": build_key,
        "component_instance": component["instance_id"],
        "features": component["features"],
        "licenses_sha256": licenses_sha256(component["licenses"]),
        "path": artifact["path"],
        "source_sha256": component["source_sha256"],
        "toolchain_digest": component["toolchain"]["digest"],
    }


def _copy_cached_artifacts(
    result: BuildCacheResult,
    stage: Path,
    component: dict[str, Any],
    artifact_ids: set[str],
    artifact_paths: set[str],
) -> list[dict[str, Any]]:
    build_key = result.metadata["build_key_sha256"]
    records: list[dict[str, Any]] = []
    for artifact in result.metadata["artifacts"]:
        artifact_id = artifact["artifact_id"]
        if artifact_id in artifact_ids:
            raise BuildError(f"duplicate release artifact_id: {artifact_id}")
        artifact_ids.add(artifact_id)
        if artifact["path"] in artifact_paths:
            raise BuildError(f"duplicate staged artifact path: {artifact['path']}")
        artifact_paths.add(artifact["path"])
        relative = PurePosixPath(artifact["path"])
        source = result.prefix.joinpath(*relative.parts)
        destination = stage.joinpath(*relative.parts)
        destination.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        if destination.exists() or destination.is_symlink():
            if (
                destination.is_symlink()
                or not destination.is_file()
                or file_sha256(destination) != artifact["artifact_sha256"]
            ):
                raise BuildError(f"staged artifact path collision: {artifact['path']}")
        else:
            with source.open("rb") as input_handle, destination.open("xb") as output_handle:
                shutil.copyfileobj(input_handle, output_handle)
            destination.chmod(source.stat().st_mode & 0o777)
        records.append(_artifact_record(component, build_key, artifact))
    return records


def _stage_manifest_id(instance_id: str) -> str:
    suffix = hashlib.sha256(instance_id.encode("utf-8")).hexdigest()[:20]
    return f"stage-manifest-{suffix}"


def _write_stage_manifest(
    stage: Path,
    component: dict[str, Any],
    build_result: BuildCacheResult,
    component_records: list[dict[str, Any]],
    artifact_ids: set[str],
    artifact_paths: set[str],
) -> dict[str, Any]:
    relative = f"share/kilix-f120/{component['instance_id']}.json"
    if relative in artifact_paths:
        raise BuildError(f"stage manifest path collision: {relative}")
    artifact_paths.add(relative)
    document = {
        "architecture": component["architecture"],
        "artifacts": [
            {
                "artifact_id": item["artifact_id"],
                "artifact_kind": item["artifact_kind"],
                "artifact_sha256": item["artifact_sha256"],
                "path": item["path"],
            }
            for item in component_records
        ],
        "build_key_sha256": build_result.metadata["build_key_sha256"],
        "component_instance": component["instance_id"],
        "features": component["features"],
        "licenses_sha256": licenses_sha256(component["licenses"]),
        "schema": STAGE_MANIFEST_SCHEMA,
        "source_sha256": component["source_sha256"],
        "toolchain_digest": component["toolchain"]["digest"],
    }
    output = stage.joinpath(*PurePosixPath(relative).parts)
    atomic_write_json(output, document)
    artifact_id = _stage_manifest_id(component["instance_id"])
    if artifact_id in artifact_ids:
        raise BuildError(f"stage manifest artifact_id collision: {artifact_id}")
    artifact_ids.add(artifact_id)
    return _artifact_record(
        component,
        build_result.metadata["build_key_sha256"],
        {
            "artifact_id": artifact_id,
            "artifact_kind": "manifest",
            "artifact_sha256": file_sha256(output),
            "path": relative,
        },
    )


def _audit_stage(stage: Path, records: list[dict[str, Any]]) -> int:
    declared: dict[str, str] = {}
    for record in records:
        path = record["path"]
        digest = record["artifact_sha256"]
        if path in declared:
            raise BuildError(f"release records duplicate staged path: {path}")
        declared[path] = digest
    observed: dict[str, str] = {}
    total = 0
    for candidate in stage.rglob("*"):
        if candidate.is_symlink():
            raise BuildError("final stage contains a symbolic link")
        if candidate.is_dir():
            continue
        if not candidate.is_file():
            raise BuildError("final stage contains a non-regular file")
        relative = candidate.relative_to(stage).as_posix()
        observed[relative] = file_sha256(candidate)
        total += candidate.stat().st_size
    if observed != declared:
        raise BuildError("final stage does not exactly match release artifacts")
    return total


def _publish_stage(candidate: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise BuildError("refusing to overwrite an existing staged prefix")
    destination.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    try:
        rename_directory_no_replace(candidate, destination)
    except FileExistsError as exc:
        raise BuildError("refusing to overwrite an existing staged prefix") from exc
    except OSError as exc:
        raise BuildError(f"cannot atomically publish staged prefix: {exc}") from exc
    descriptor = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _publish_lock(candidate: Path, destination: Path) -> None:
    """Atomically publish a new lock without ever replacing an existing one."""

    destination.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    linked = False
    try:
        os.link(candidate, destination)
        linked = True
        candidate.unlink()
        descriptor = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except FileExistsError as exc:
        raise BuildError("refusing to overwrite an existing release lock") from exc
    except BaseException:
        if linked:
            destination.unlink(missing_ok=True)
        raise


def _retire_failed_publication(destination: Path) -> None:
    """Remove a prefix from its public name if paired lock publication fails."""

    failed_root = destination.parent / ".kilix-f120-failed"
    failed_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    failed = failed_root / uuid.uuid4().hex
    os.replace(destination, failed)


def _staged_dependency_map(
    registration: Registration,
) -> dict[str, tuple[str, ...]]:
    known = {component.instance_id for component in registration.components}
    dependencies: dict[str, list[str]] = {instance: [] for instance in known}
    for edge in registration.dependencies:
        if edge["consumption_mode"] != "staged-prefix":
            continue
        consumer = edge["from"]
        provider = edge["to"]
        if consumer not in known or provider not in known:
            raise ContractError("staged-prefix edge names an unknown component")
        if consumer == provider:
            raise ContractError("staged-prefix dependency cannot be self-referential")
        if provider in dependencies[consumer]:
            raise ContractError("duplicate staged-prefix dependency edge")
        dependencies[consumer].append(provider)
    return {
        consumer: tuple(sorted(providers))
        for consumer, providers in dependencies.items()
    }


def _staged_build_order(registration: Registration) -> list[ComponentRegistration]:
    dependencies = _staged_dependency_map(registration)
    components = {item.instance_id: item for item in registration.components}
    consumers: dict[str, list[str]] = {instance: [] for instance in components}
    pending = {instance: len(providers) for instance, providers in dependencies.items()}
    for consumer, providers in dependencies.items():
        for provider in providers:
            consumers[provider].append(consumer)
    ready = [instance for instance, count in pending.items() if count == 0]
    heapq.heapify(ready)
    ordered: list[ComponentRegistration] = []
    while ready:
        instance = heapq.heappop(ready)
        ordered.append(components[instance])
        for consumer in sorted(consumers[instance]):
            pending[consumer] -= 1
            if pending[consumer] == 0:
                heapq.heappush(ready, consumer)
    if len(ordered) != len(components):
        blocked = sorted(instance for instance, count in pending.items() if count)
        raise ContractError(f"staged-prefix dependency cycle: {blocked}")
    return ordered


def _build_component(
    component: dict[str, Any], dependencies: Mapping[str, BuildCacheResult]
) -> dict[str, Any]:
    result = copy.deepcopy(component)
    digest = staged_dependencies_sha256(dependencies)
    if digest is not None:
        options = dict(result["build_options"])
        if RESERVED_STAGED_DEPENDENCIES_OPTION in options:
            raise ContractError("workspace uses reserved staged-dependency build option")
        options[RESERVED_STAGED_DEPENDENCIES_OPTION] = digest
        result["build_options"] = options
    return result


def stage_workspace(
    registration: Registration,
    workspace: dict[str, Any],
    *,
    cache: Path,
    destination: Path,
    release: str,
    release_lock: Path,
    local_sources: Mapping[str, Path] | None = None,
) -> StageReport:
    if workspace.get("workspace_root") != str(registration.workspace_root):
        raise ContractError("workspace manifest root differs from registration")
    cache_path = cache.resolve()
    workspace_path = registration.workspace_root.resolve()
    destination_path = destination.resolve()
    for candidate, container, label in (
        (cache_path, workspace_path, "cache root is inside the workspace"),
        (workspace_path, cache_path, "cache root contains the workspace"),
        (destination_path, workspace_path, "staged prefix is inside the workspace"),
        (destination_path, cache_path, "staged prefix is inside the cache"),
        (cache_path, destination_path, "staged prefix contains the cache"),
    ):
        try:
            candidate.relative_to(container)
        except ValueError:
            continue
        raise BuildError(label)
    overrides = local_sources or {}
    known = {item.instance_id for item in registration.components}
    unknown = sorted(set(overrides) - known)
    if unknown:
        raise ContractError(f"unknown local source override(s): {unknown}")
    observed_by_id = {item["instance_id"]: item for item in workspace["components"]}
    if set(observed_by_id) != known:
        raise ContractError("workspace manifest components differ from registration")
    if release_lock.exists() or release_lock.is_symlink():
        raise BuildError("refusing to overwrite an existing release lock")

    destination = destination.resolve()
    destination.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{destination.name}.candidate-", dir=destination.parent))
    lock_candidate = release_lock.parent / f".{release_lock.name}.{uuid.uuid4().hex}.candidate"
    source_results: list[SourceCacheResult] = []
    build_results: list[BuildCacheResult] = []
    build_results_by_id: dict[str, BuildCacheResult] = {}
    locked_components: dict[str, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []
    artifact_ids: set[str] = set()
    artifact_paths: set[str] = set()
    published = False
    try:
        dependencies = _staged_dependency_map(registration)
        for component_registration in registration.components:
            component = observed_by_id[component_registration.instance_id]
            _verify_component_registration(component, component_registration)
        for component_registration in _staged_build_order(registration):
            component = observed_by_id[component_registration.instance_id]
            component_dependencies = {
                instance: build_results_by_id[instance]
                for instance in dependencies[component_registration.instance_id]
            }
            build_component = _build_component(component, component_dependencies)
            source_result = ensure_source(
                cache,
                component,
                local_source=overrides.get(component_registration.instance_id),
            )
            source_results.append(source_result)
            build_result = ensure_build(
                cache,
                build_component,
                component_registration,
                source_result.repository,
                workspace_root=registration.workspace_root,
                dependencies=component_dependencies,
            )
            build_results.append(build_result)
            build_results_by_id[component_registration.instance_id] = build_result
            locked_components[component_registration.instance_id] = build_component
            component_records = _copy_cached_artifacts(
                build_result,
                stage,
                build_component,
                artifact_ids,
                artifact_paths,
            )
            records.extend(component_records)
            records.append(
                _write_stage_manifest(
                    stage,
                    build_component,
                    build_result,
                    component_records,
                    artifact_ids,
                    artifact_paths,
                )
            )
        staged_bytes = _audit_stage(stage, records)
        release_lock.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        release_workspace = copy.deepcopy(workspace)
        release_workspace["components"] = [
            locked_components[item["instance_id"]]
            for item in release_workspace["components"]
        ]
        emit_release_lock(release_workspace, release, records, lock_candidate)
        _publish_stage(stage, destination)
        published = True
        _publish_lock(lock_candidate, release_lock)
    except BaseException:
        if published:
            _retire_failed_publication(destination)
        else:
            shutil.rmtree(stage, ignore_errors=True)
        lock_candidate.unlink(missing_ok=True)
        raise

    root = cache_root(cache)
    return StageReport(
        components=len(registration.components),
        source_cache_hits=sum(item.hit for item in source_results),
        source_cache_misses=sum(not item.hit for item in source_results),
        fetches=sum(item.fetches for item in source_results),
        fetch_bytes=sum(item.fetch_bytes for item in source_results),
        build_cache_hits=sum(item.hit for item in build_results),
        build_cache_misses=sum(not item.hit for item in build_results),
        builds=sum(item.builds for item in build_results),
        cache_bytes=directory_bytes(root / "sources") + directory_bytes(root / "builds"),
        staged_bytes=staged_bytes,
        artifacts=len(records),
    )


def retire_stage(destination: Path, release_lock: Path | None = None) -> Path:
    """Recoverably remove one exact stage from service for rollback."""

    stage = destination.resolve()
    if stage == Path("/") or stage == Path.home().resolve():
        raise BuildError("refusing to retire a broad filesystem path")
    if stage.is_symlink() or not stage.is_dir():
        raise BuildError("staged prefix is not a real directory")
    if (stage / ".git").exists() or (stage / ".gitmodules").exists():
        raise BuildError("refusing to retire a repository as a staged prefix")
    manifest_root = stage / "share" / "kilix-f120"
    if manifest_root.is_symlink() or not manifest_root.is_dir():
        raise BuildError("staged prefix has no F120 stage-manifest directory")
    manifests = sorted(manifest_root.glob("*.json"))
    if not manifests:
        raise BuildError("staged prefix has no F120 stage manifests")
    if {item for item in manifest_root.iterdir()} != set(manifests):
        raise BuildError("F120 stage-manifest directory contains unexpected entries")
    for manifest in manifests:
        if manifest.is_symlink() or not manifest.is_file():
            raise BuildError("F120 stage manifest is not a regular file")
        document = load_json(manifest)
        if not isinstance(document, dict) or document.get("schema") != STAGE_MANIFEST_SCHEMA:
            raise BuildError("F120 stage manifest identity is invalid")
        instance = require_identifier(
            document.get("component_instance"), "stage manifest component instance"
        )
        if manifest.name != f"{instance}.json":
            raise BuildError("F120 stage manifest filename does not bind its component")
    lock: Path | None = None
    if release_lock is not None:
        lock = release_lock.resolve()
        if lock.is_symlink() or not lock.is_file():
            raise BuildError("release lock is not a real file")
        lock_document = validate_path(lock)
        _audit_stage(stage, lock_document["artifacts"])
    retirement_root = stage.parent / ".kilix-f120-retired"
    retirement_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    retirement = retirement_root / uuid.uuid4().hex
    retirement.mkdir(mode=0o700)
    os.replace(stage, retirement / "prefix")
    if lock is not None:
        os.replace(lock, retirement / "release-lock.json")
    return retirement
