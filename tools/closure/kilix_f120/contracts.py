"""Adapter around the byte-frozen F120 v1 validator."""

from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any

from .canonical import file_sha256, load_json, require_relative_path, require_sha256
from .errors import ContractError


PACKAGE_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_ROOT = PACKAGE_ROOT / "contracts"
FROZEN_HASH_MANIFEST_SHA256 = (
    "4c67ee97ef59066e7c0b64cf77c7056bfa7791075cf7a7b88e0873527fd3371b"
)
BASELINE_TAG_EXCEPTION = {
    "component_id": "plebian-os",
    "ref_kind": "tag",
    "requested_ref": "v0.2.0",
}


@lru_cache(maxsize=1)
def frozen_validator() -> ModuleType:
    validator_path = CONTRACT_ROOT / "validate_f120.py"
    specification = importlib.util.spec_from_file_location(
        "kilix_f120_frozen_validator", validator_path
    )
    if specification is None or specification.loader is None:
        raise ContractError("cannot load frozen F120 validator")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _independent_hash_failures() -> list[str]:
    """Verify frozen bytes before importing the frozen executable validator."""

    manifest = CONTRACT_ROOT / "SHA256SUMS"
    try:
        lines = manifest.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return [f"cannot read frozen hash manifest: {exc}"]
    failures: list[str] = []
    seen: set[str] = set()
    for line_number, line in enumerate(lines, start=1):
        digest, separator, raw_path = line.partition("  ")
        if not separator:
            failures.append(f"malformed SHA256SUMS line {line_number}")
            continue
        try:
            expected = require_sha256(digest, "frozen file digest")
            relative = require_relative_path(raw_path, "frozen file path")
        except ContractError as exc:
            failures.append(f"invalid SHA256SUMS line {line_number}: {exc}")
            continue
        if relative in seen:
            failures.append(f"duplicate frozen file entry: {relative}")
            continue
        seen.add(relative)
        candidate = CONTRACT_ROOT.joinpath(*Path(relative).parts)
        if candidate.is_symlink() or not candidate.is_file():
            failures.append(f"missing or non-regular frozen file: {relative}")
            continue
        if file_sha256(candidate) != expected:
            failures.append(f"frozen file digest mismatch: {relative}")
    if not lines:
        failures.append("frozen hash manifest is empty")
    return failures


def verify_contract_package() -> None:
    actual = file_sha256(CONTRACT_ROOT / "SHA256SUMS")
    if actual != FROZEN_HASH_MANIFEST_SHA256:
        raise ContractError("frozen F120 SHA256SUMS identity changed")
    independent_failures = _independent_hash_failures()
    if independent_failures:
        raise ContractError(
            "frozen F120 contract package failed independent verification: "
            + "; ".join(independent_failures)
        )
    failures = frozen_validator().verify_canonical_and_hashes()
    if failures:
        raise ContractError("frozen F120 contract package failed: " + "; ".join(failures))


def _workspace_qualification_errors(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for component in document["components"]:
        name = component["instance_id"]
        if component["resolution_state"] != "resolved":
            errors.append(f"unresolved component is not qualifiable: {name}")
        if component["dirty"]:
            errors.append(f"dirty component is not qualifiable: {name}")
        if component.get("resolved_commit") != component["expected_commit"]:
            errors.append(f"expected/resolved commit mismatch: {name}")
        is_exception = all(
            component.get(field) == expected
            for field, expected in BASELINE_TAG_EXCEPTION.items()
        )
        if is_exception:
            continue
        if component["ref_kind"] != "exact-commit":
            errors.append(f"mutable ref is not qualifiable: {name}")
        if component["requested_ref"] != component["expected_commit"]:
            errors.append(f"requested_ref/expected_commit mismatch: {name}")
    return errors


def validate_path(
    path: Path,
    *,
    allow_development_state: bool = False,
) -> dict[str, Any]:
    """Validate through frozen v1 and the named baseline-tag policy exception."""

    verify_contract_package()
    document = load_json(path)
    if not isinstance(document, dict):
        raise ContractError("F120 document must be an object")
    identity = document.get("schema")
    validator = frozen_validator()
    # The frozen validator rejects every tag for qualification.  Run its full
    # schema/graph surface in development mode, then apply the same strict state
    # checks here with the one owner-named v0.2.0 exception.
    frozen_development = bool(
        identity == "kilix.f120.workspace-manifest/v1"
    )
    errors = validator.validate_document(
        path,
        validator.validators(),
        allow_development_state=(allow_development_state or frozen_development),
    )
    if not errors and frozen_development and not allow_development_state:
        errors.extend(_workspace_qualification_errors(document))
    if errors:
        raise ContractError("; ".join(errors))
    return document
