"""Deterministic assembly and release preflight for reviewed owner fragments."""

from __future__ import annotations

import copy
import hashlib
import heapq
import os
import stat
from pathlib import Path
from typing import Any, Iterable

from .build_cache import verify_recipe_dependency_surface
from .canonical import (
    MAX_DOCUMENT_BYTES,
    atomic_write_json_new,
    canonical_sha256,
    load_json_bytes,
    require_identifier,
)
from .errors import BuildError, RegistrationError
from .registration import (
    ZERO_COMMIT,
    ComponentRegistration,
    Registration,
    registration_from_document,
)


ASSEMBLY_REPORT_ID = "kilix.f120.registration-assembly-report/v1"
ZERO_SHA256 = "0" * 64
UNRESOLVED_VALUES = {"replace_me", "tbd", "unknown", "unresolved"}


def _captured_fragment(path: Path) -> tuple[dict[str, Any], Registration, str]:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    except OSError as exc:
        raise RegistrationError(
            "owner fragment cannot be opened without following links"
        ) from exc
    with os.fdopen(descriptor, "rb", closefd=True) as handle:
        information = os.fstat(handle.fileno())
        if not stat.S_ISREG(information.st_mode):
            raise RegistrationError("owner fragment must be a regular file")
        payload = handle.read(MAX_DOCUMENT_BYTES + 1)
    value = load_json_bytes(payload)
    if not isinstance(value, dict):
        raise RegistrationError("owner fragment must be a registration object")
    return (
        value,
        registration_from_document(value),
        hashlib.sha256(payload).hexdigest(),
    )


def _component_preflight(component: ComponentRegistration) -> None:
    label = component.instance_id
    if component.expected_commit == ZERO_COMMIT:
        raise RegistrationError(f"release component retains zero commit: {label}")
    if component.ref_kind != "exact-commit":
        raise RegistrationError(f"release component is not exact-commit: {label}")
    if component.requested_ref != component.expected_commit:
        raise RegistrationError(f"release component ref differs from commit: {label}")
    if component.build is None:
        raise RegistrationError(f"release component has no build recipe: {label}")
    if not component.toolchain.executables:
        raise RegistrationError(f"release component has no build executables: {label}")
    if component.architecture.casefold() in UNRESOLVED_VALUES:
        raise RegistrationError(f"release component has unresolved architecture: {label}")
    if component.toolchain.name.casefold() in UNRESOLVED_VALUES:
        raise RegistrationError(
            f"release component has unresolved toolchain name: {label}"
        )
    if component.toolchain.version.casefold() in UNRESOLVED_VALUES:
        raise RegistrationError(
            f"release component has unresolved toolchain version: {label}"
        )
    if any(item.sha256 == ZERO_SHA256 for item in component.toolchain.executables):
        raise RegistrationError(f"release component has zero tool digest: {label}")
    if any(
        item["spdx"] == "NOASSERTION" or item["text_sha256"] == ZERO_SHA256
        for item in component.licenses
    ):
        raise RegistrationError(f"release component has unresolved licence: {label}")
    if any(item["sha256"] == ZERO_SHA256 for item in component.notices):
        raise RegistrationError(f"release component has zero notice digest: {label}")


def _preflight(registration: Registration) -> tuple[int, tuple[str, ...]]:
    components = {item.instance_id: item for item in registration.components}
    staged_dependencies: dict[str, set[str]] = {
        instance: set() for instance in components
    }
    consumers: dict[str, set[str]] = {instance: set() for instance in components}
    edge_keys: set[tuple[str, str, str, str]] = set()
    artifact_ids: set[str] = set()
    artifact_paths: set[str] = set()

    for component in registration.components:
        _component_preflight(component)
        assert component.build is not None
        for artifact in component.build.artifacts:
            if artifact.artifact_id in artifact_ids:
                raise RegistrationError(
                    f"duplicate release artifact id: {artifact.artifact_id}"
                )
            if artifact.path in artifact_paths:
                raise RegistrationError(
                    f"duplicate release artifact path: {artifact.path}"
                )
            artifact_ids.add(artifact.artifact_id)
            artifact_paths.add(artifact.path)

    for edge in registration.dependencies:
        consumer_id = edge["from"]
        provider_id = edge["to"]
        if consumer_id not in components or provider_id not in components:
            raise RegistrationError("release dependency names an unknown endpoint")
        if consumer_id == provider_id:
            raise RegistrationError("release dependency cannot be self-referential")
        key = (
            consumer_id,
            provider_id,
            edge["consumption_mode"],
            edge["runtime_process"],
        )
        if key in edge_keys:
            raise RegistrationError("duplicate logical release dependency edge")
        edge_keys.add(key)
        provider = components[provider_id]
        if edge["required_api_version"] != provider.api_version:
            raise RegistrationError(
                f"dependency API requirement differs from provider: {consumer_id}:{provider_id}"
            )
        if edge["required_abi_version"] != provider.abi_version:
            raise RegistrationError(
                f"dependency ABI requirement differs from provider: {consumer_id}:{provider_id}"
            )
        if edge["consumption_mode"] == "staged-prefix":
            staged_dependencies[consumer_id].add(provider_id)
            consumers[provider_id].add(consumer_id)

    for component in registration.components:
        assert component.build is not None
        try:
            verify_recipe_dependency_surface(
                component.build, staged_dependencies[component.instance_id]
            )
        except BuildError as exc:
            raise RegistrationError(
                f"release recipe dependency mismatch: {component.instance_id}: {exc}"
            ) from exc

    pending = {
        instance: len(providers)
        for instance, providers in staged_dependencies.items()
    }
    ready = [instance for instance, count in pending.items() if count == 0]
    heapq.heapify(ready)
    build_order: list[str] = []
    while ready:
        provider = heapq.heappop(ready)
        build_order.append(provider)
        for consumer in sorted(consumers[provider]):
            pending[consumer] -= 1
            if pending[consumer] == 0:
                heapq.heappush(ready, consumer)
    if len(build_order) != len(components):
        blocked = sorted(instance for instance, count in pending.items() if count)
        raise RegistrationError(f"staged-prefix dependency cycle: {blocked}")
    return len(artifact_ids), tuple(build_order)


def assemble_registration(
    fragments: Iterable[tuple[str, Path]],
    required_owners: Iterable[str],
    *,
    workspace_root: Path,
    output: Path,
    report: Path,
) -> dict[str, Any]:
    """Assemble an exact owner set and publish a fail-closed preflight report."""

    if not workspace_root.is_absolute():
        raise RegistrationError("assembled workspace_root must be absolute")
    required = [require_identifier(item, "required owner") for item in required_owners]
    if not required:
        raise RegistrationError("at least one required owner must be named")
    if len(set(required)) != len(required):
        raise RegistrationError("required owner values must be unique")

    supplied = list(fragments)
    if not supplied:
        raise RegistrationError("at least one owner fragment must be supplied")
    owners = [require_identifier(owner, "fragment owner") for owner, _ in supplied]
    if len(set(owners)) != len(owners):
        raise RegistrationError("fragment owner values must be unique")
    missing = sorted(set(required) - set(owners))
    unexpected = sorted(set(owners) - set(required))
    if missing or unexpected:
        raise RegistrationError(
            "owner fragment set differs from required set; "
            f"missing={missing}, unexpected={unexpected}"
        )

    resolved_paths = [path.resolve() for _, path in supplied]
    if len(set(resolved_paths)) != len(resolved_paths):
        raise RegistrationError("owner fragment paths must be unique")
    if output.resolve() == report.resolve():
        raise RegistrationError("registration output and assembly report must differ")

    component_documents: list[tuple[str, dict[str, Any]]] = []
    dependency_documents: list[dict[str, Any]] = []
    fragment_reports: list[dict[str, Any]] = []
    component_owners: dict[str, str] = {}

    for owner, path in sorted(supplied, key=lambda item: item[0]):
        document, registration, digest = _captured_fragment(path)
        raw_components = document["components"]
        for raw, component in zip(raw_components, registration.components, strict=True):
            if not isinstance(raw, dict) or raw.get("instance_id") != component.instance_id:
                raise RegistrationError(
                    f"owner fragment component lacks explicit instance_id: {owner}"
                )
            previous = component_owners.get(component.instance_id)
            if previous is not None:
                raise RegistrationError(
                    "duplicate component instance across owners: "
                    f"{component.instance_id}:{previous}:{owner}"
                )
            component_owners[component.instance_id] = owner
            component_documents.append((component.instance_id, copy.deepcopy(raw)))
        dependency_documents.extend(copy.deepcopy(document["dependencies"]))
        fragment_reports.append(
            {
                "component_instances": sorted(
                    component.instance_id for component in registration.components
                ),
                "components": len(registration.components),
                "dependencies": len(registration.dependencies),
                "owner": owner,
                "sha256": digest,
            }
        )

    dependency_documents.sort(
        key=lambda item: (
            item["from"],
            item["to"],
            item["consumption_mode"],
            item["runtime_process"],
        )
    )
    assembled_document = {
        "components": [
            item for _, item in sorted(component_documents, key=lambda item: item[0])
        ],
        "dependencies": dependency_documents,
        "schema": "kilix.f120.registration/v2",
        "workspace_root": str(workspace_root.resolve()),
    }
    assembled = registration_from_document(assembled_document)
    artifacts, build_order = _preflight(assembled)
    staged_edges = sum(
        edge["consumption_mode"] == "staged-prefix"
        for edge in assembled.dependencies
    )
    report_document: dict[str, Any] = {
        "artifacts": artifacts,
        "build_order": list(build_order),
        "components": len(assembled.components),
        "dependencies": len(assembled.dependencies),
        "fragments": fragment_reports,
        "registration_sha256": canonical_sha256(assembled_document),
        "required_owners": sorted(required),
        "schema": ASSEMBLY_REPORT_ID,
        "staged_prefix_edges": staged_edges,
        "workspace_root": str(assembled.workspace_root),
    }

    # Publish the receipt first. A process interruption can therefore never
    # expose a registration without its exact digest-bound preflight record.
    atomic_write_json_new(report, report_document)
    report_identity = report.stat()
    try:
        atomic_write_json_new(output, assembled_document)
    except BaseException:
        try:
            current = report.stat()
            if (current.st_dev, current.st_ino) == (
                report_identity.st_dev,
                report_identity.st_ino,
            ):
                report.unlink()
        except OSError:
            pass
        raise
    return report_document
