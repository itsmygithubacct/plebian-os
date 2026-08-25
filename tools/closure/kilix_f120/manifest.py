"""Emit honest observed-workspace manifests under the frozen F120 v1 contract."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

from .canonical import atomic_write_json
from .contracts import validate_path
from .errors import ContractError, GitError
from .gitops import (
    canonical_https_url,
    committed_blob,
    normalize_remote_for_comparison,
    repository_state,
    resolve_commit,
    source_tree_sha256,
)
from .registration import ZERO_COMMIT, ComponentRegistration, Registration


WORKSPACE_SCHEMA = "kilix.f120.workspace-manifest/v1"


def _component_path(registration: Registration, component: ComponentRegistration) -> Path:
    candidate = (registration.workspace_root / component.relative_path).resolve()
    try:
        candidate.relative_to(registration.workspace_root)
    except ValueError as exc:
        raise ContractError(
            f"component path escapes workspace: {component.instance_id}"
        ) from exc
    return candidate


def _base_component(component: ComponentRegistration) -> dict[str, Any]:
    return {
        "abi_version": component.abi_version,
        "api_version": component.api_version,
        "architecture": component.architecture,
        "build_options": component.effective_build_options,
        "canonical_url": canonical_https_url(component.canonical_url),
        "component_id": component.component_id,
        "component_version": component.component_version,
        "expected_commit": component.expected_commit,
        "features": list(component.features),
        "instance_id": component.instance_id,
        "licenses": [dict(item) for item in component.licenses],
        "notices": [dict(item) for item in component.notices],
        "publication_disposition": component.publication_disposition,
        "ref_kind": component.ref_kind,
        "requested_ref": component.requested_ref,
        "required_tests": list(component.required_tests),
        "runtime_kind": component.runtime_kind,
        "toolchain": component.toolchain.contract_value(),
        "visibility": component.visibility,
    }


def _verify_reference(repository: Path, component: ComponentRegistration) -> None:
    if component.ref_kind == "exact-commit":
        if component.requested_ref != component.expected_commit:
            raise GitError(
                f"exact requested ref differs from expected commit: {component.instance_id}"
            )
        reference = component.requested_ref
    elif component.ref_kind == "tag":
        reference = f"refs/tags/{component.requested_ref}"
    else:
        reference = f"refs/heads/{component.requested_ref}"
    resolved = resolve_commit(repository, reference)
    if resolved != component.expected_commit:
        raise GitError(
            f"requested ref differs from expected commit: {component.instance_id}"
        )


def _verify_notices(
    repository: Path, component: ComponentRegistration, commit: str
) -> None:
    for notice in component.notices:
        actual = hashlib.sha256(
            committed_blob(repository, commit, notice["path"])
        ).hexdigest()
        if actual != notice["sha256"]:
            raise ContractError(
                f"notice digest mismatch: {component.instance_id}:{notice['path']}"
            )


def observe_component(
    registration: Registration,
    component: ComponentRegistration,
    *,
    local_sources: Mapping[str, Path],
) -> dict[str, Any]:
    result = _base_component(component)
    registered_path = _component_path(registration, component)
    explicit = component.instance_id in local_sources
    repository = local_sources.get(component.instance_id, registered_path).resolve()
    if not repository.is_dir():
        result.update({"dirty": True, "resolution_state": "unresolved"})
        return result
    state = repository_state(repository)
    if explicit:
        if repository != registered_path:
            # An override is a deliberate local evidence input, not an observed
            # workspace path.  It never changes the emitted canonical URL.
            pass
    elif normalize_remote_for_comparison(state.origin or "") != component.canonical_url:
        raise GitError(f"observed origin is not canonical: {component.instance_id}")
    if component.expected_commit == ZERO_COMMIT:
        raise ContractError(
            f"resolved component retains unresolved commit sentinel: {component.instance_id}"
        )
    _verify_reference(repository, component)
    component.toolchain.verify()
    _verify_notices(repository, component, state.head)
    result.update(
        {
            "dirty": state.dirty,
            "resolution_state": "resolved",
            "resolved_commit": state.head,
            "source_sha256": source_tree_sha256(repository, state.head),
        }
    )
    return result


def workspace_document(
    registration: Registration,
    *,
    local_sources: Mapping[str, Path] | None = None,
) -> dict[str, Any]:
    overrides = local_sources or {}
    unknown = sorted(set(overrides) - {item.instance_id for item in registration.components})
    if unknown:
        raise ContractError(f"unknown local source override(s): {unknown}")
    components = [
        observe_component(registration, component, local_sources=overrides)
        for component in registration.components
    ]
    components.sort(key=lambda item: item["instance_id"])
    return {
        "components": components,
        "dependencies": [dict(item) for item in registration.dependencies],
        "schema": WORKSPACE_SCHEMA,
        "workspace_root": str(registration.workspace_root),
    }


def emit_workspace_manifest(
    registration: Registration,
    output: Path,
    *,
    local_sources: Mapping[str, Path] | None = None,
    qualify: bool = False,
) -> dict[str, Any]:
    document = workspace_document(registration, local_sources=local_sources)
    atomic_write_json(output, document)
    return validate_path(output, allow_development_state=not qualify)
