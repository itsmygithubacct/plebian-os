"""Derive a frozen F120 v1 release lock from qualified staged evidence."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from .canonical import atomic_write_json
from .contracts import validate_path
from .errors import ContractError


RELEASE_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$")
WORKSPACE_ONLY_FIELDS = {
    "dirty",
    "expected_commit",
    "ref_kind",
    "requested_ref",
    "resolution_state",
}


def _locked_component(component: dict[str, Any]) -> dict[str, Any]:
    if component["resolution_state"] != "resolved":
        raise ContractError(f"cannot lock unresolved component: {component['instance_id']}")
    return {
        key: value for key, value in component.items() if key not in WORKSPACE_ONLY_FIELDS
    }


def release_document(
    workspace: dict[str, Any],
    release: str,
    artifacts: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    if not RELEASE_RE.fullmatch(release):
        raise ContractError("release must be a SemVer-like release identifier")
    blocked_modes = sorted(
        {
            edge["consumption_mode"]
            for edge in workspace["dependencies"]
            if edge["consumption_mode"]
            in {"recursive-git-submodule", "nested-source-build"}
        }
    )
    if blocked_modes:
        raise ContractError(
            "release lock requires landed staged-prefix conversion; found "
            + ", ".join(blocked_modes)
        )
    return {
        "artifacts": sorted(
            (dict(item) for item in artifacts), key=lambda item: item["artifact_id"]
        ),
        "components": [
            _locked_component(item)
            for item in sorted(workspace["components"], key=lambda item: item["instance_id"])
        ],
        "dependencies": [dict(item) for item in workspace["dependencies"]],
        "release": release,
        "schema": "kilix.f120.release-lock/v1",
    }


def emit_release_lock(
    workspace: dict[str, Any],
    release: str,
    artifacts: Iterable[dict[str, Any]],
    output: Path,
) -> dict[str, Any]:
    document = release_document(workspace, release, artifacts)
    atomic_write_json(output, document)
    return validate_path(output)
