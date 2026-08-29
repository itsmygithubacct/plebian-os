#!/usr/bin/env python3
"""Review-only validator for the ratified F120 v3/v2/v2 candidate line.

The executable is deliberately not wired into the resolver.  A release
qualification call fails closed until F100 supplies the accepted validator/API
identity required by the ratified amendment.  ``--contract-preflight`` checks
only the F120-owned schema and cross-record joins and is never a release pass.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import re
import sys
import tempfile
from collections import Counter, defaultdict
from contextlib import redirect_stderr
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parent
SCHEMAS = {
    "kilix.f120.workspace-manifest/v2": ROOT
    / "schemas"
    / "kilix.f120.workspace-manifest-v2.schema.json",
    "kilix.f120.release-lock/v2": ROOT
    / "schemas"
    / "kilix.f120.release-lock-v2.schema.json",
}
FIXTURES = ROOT / "fixtures"
MAX_DOCUMENT_BYTES = 4 * 1024 * 1024
MAX_COMPONENTS = 4096
MAX_ARTIFACTS = 16384
MAX_UNITS = 4096
MAX_PAYLOAD_IDS = 16384
MAX_LICENCE_ENTRIES = 256
MAX_NOTICE_ENTRIES = 4096
MAX_OTHER_NOTICE_IDS = 4096
RATIFIED_AMENDMENT_SHA256 = (
    "0e1d8ca1fd330bd47a836ad4f221b1df4e04b670c7af259296d2e90238be039e"
)

IDENTIFIER_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")

REGISTRATION_ID = "kilix.f120.registration/v3"
WORKSPACE_ID = "kilix.f120.workspace-manifest/v2"
RELEASE_ID = "kilix.f120.release-lock/v2"
RESERVED_BUILD_OPTIONS = {
    "f120_recipe_sha256",
    "f120_compliance_declaration_sha256",
}
ARTIFACT_ROLES = {
    "payload",
    "artifact-descriptor",
    "compliance-manifest",
    "license-text",
    "conveyance-notice",
    "upstream-notice",
    "other-notice",
    "modifications",
    "upstream-notice-inventory",
    "internal-sha256sums",
    "carrier-archive",
    "carrier-manifest",
    "pair-record",
    "pair-digest",
    "internal-stage-manifest",
}
MANDATORY_UNIT_ROLES = {
    "artifact_descriptor": "artifact-descriptor",
    "carrier_archive": "carrier-archive",
    "carrier_manifest": "carrier-manifest",
    "compliance_manifest": "compliance-manifest",
    "internal_sha256sums": "internal-sha256sums",
    "modifications": "modifications",
    "pair": "pair-record",
    "pair_digest": "pair-digest",
    "upstream_notice_inventory": "upstream-notice-inventory",
}
EXCLUSIVE_ROLES = {
    "pair-record",
    "pair-digest",
    "carrier-archive",
    "carrier-manifest",
    "artifact-descriptor",
    "compliance-manifest",
    "modifications",
    "upstream-notice-inventory",
    "internal-sha256sums",
}
COMPLIANCE_ROLES = ARTIFACT_ROLES - {"payload", "internal-stage-manifest"}
PAYLOAD_KINDS = {"command", "header", "library", "python-package", "pkg-config", "data"}
FORBIDDEN_COMPLIANCE_KINDS = {
    "command",
    "header",
    "library",
    "python-package",
    "pkg-config",
}
ARTIFACT_KINDS = PAYLOAD_KINDS | {"notice", "manifest"}
VISIBILITIES = {"public", "private", "local-only"}
PUBLICATION_DISPOSITIONS = {"publish", "private", "unpublished", "restricted"}
RUNTIME_KINDS = {"native-provider", "process", "python-distribution", "data"}
REF_KINDS = {"exact-commit", "tag", "branch"}
EXECUTABLE_KINDS = {"native", "python-interpreter", "python-script", "script"}
CONSUMPTION_MODES = {
    "recursive-git-submodule",
    "nested-source-build",
    "staged-prefix",
    "system-package",
    "runtime-process",
}
ENVIRONMENT_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
BUILD_ENVIRONMENT_NAME_RE = re.compile(r"^F120_INPUT_[A-Z0-9_]+$")
RESERVED_ENVIRONMENT = {
    "BASH_ENV",
    "ENV",
    "GIT_ASKPASS",
    "GIT_CONFIG_GLOBAL",
    "GIT_CONFIG_NOSYSTEM",
    "GIT_CONFIG_SYSTEM",
    "GIT_TERMINAL_PROMPT",
    "HOME",
    "LC_ALL",
    "PATH",
    "PERL5LIB",
    "RUBYOPT",
    "SOURCE_DATE_EPOCH",
    "TMPDIR",
    "TZ",
    "VIRTUAL_ENV",
}
RESERVED_ENVIRONMENT_PREFIXES = (
    "CONDA_",
    "DYLD_",
    "LD_",
    "NODE_",
    "NPM_",
    "PIP_",
    "PYTHON",
    "UV_",
)

REGISTRATION_COMPONENT_REQUIRED = {
    "abi_version",
    "api_version",
    "architecture",
    "build_options",
    "canonical_url",
    "component_id",
    "component_version",
    "expected_commit",
    "features",
    "licenses",
    "notices",
    "path",
    "publication_disposition",
    "ref_kind",
    "requested_ref",
    "required_tests",
    "runtime_kind",
    "toolchain",
    "visibility",
}
REGISTRATION_COMPONENT_ALLOWED = REGISTRATION_COMPONENT_REQUIRED | {
    "build",
    "instance_id",
}
UNIT_DECLARATION_KEYS = {
    "artifact_binding_sha256",
    "artifact_descriptor_artifact_id",
    "carrier_archive_artifact_id",
    "carrier_manifest_artifact_id",
    "compliance_manifest_artifact_id",
    "internal_sha256sums_artifact_id",
    "license_texts",
    "modifications_artifact_id",
    "notices",
    "other_notice_artifact_ids",
    "pair_artifact_id",
    "pair_digest_artifact_id",
    "pair_sha256",
    "payload_artifact_ids",
    "unit_id",
    "upstream_notice_inventory_artifact_id",
}
EXPANDED_UNIT_KEYS = {
    "artifact_binding_sha256",
    "artifact_descriptor",
    "carrier_archive",
    "carrier_manifest",
    "compliance_binding_sha256",
    "compliance_manifest",
    "component_instance",
    "internal_sha256sums",
    "license_texts",
    "modifications",
    "notices",
    "other_notices",
    "pair",
    "pair_digest",
    "pair_sha256",
    "payloads",
    "unit_id",
    "upstream_notice_inventory",
}

EXPECTED_INVALID = {
    "registration/invalid/older-schema-identity.json": "F120-V3-SCHEMA-IDENTITY",
    "registration/invalid/declared-internal-manifest.json": "F120-V3-DECLARED-INTERNAL-MANIFEST",
    "registration/invalid/reserved-compliance-option.json": "F120-V3-RESERVED-BUILD-OPTION",
    "workspace/invalid/older-schema-identity.json": "F120-V2-SCHEMA-IDENTITY",
    "workspace/invalid/payload-without-unit.json": "F120-V2-PAYLOAD-WITHOUT-UNIT",
    "release/invalid/artifact-binding-mismatch.json": "F120-V2-ARTIFACT-BINDING-MISMATCH",
    "release/invalid/borrowed-same-spdx.json": "F120-V2-LICENCE-TUPLE-MISMATCH",
    "release/invalid/cross-component.json": "F120-V2-CROSS-COMPONENT-REFERENCE",
    "release/invalid/duplicate-artifact-path.json": "F120-V2-DUPLICATE-ARTIFACT-PATH",
    "release/invalid/exclusive-artifact-shared.json": "F120-V2-EXCLUSIVE-COMPLIANCE-ARTIFACT",
    "release/invalid/licence-union-mismatch.json": "F120-V2-LICENCE-UNION-MISMATCH",
    "release/invalid/missing-conveyance.json": "F120-V2-CONVEYANCE-NOTICE-COUNT",
    "release/invalid/notice-tuple-mismatch.json": "F120-V2-NOTICE-TUPLE-MISMATCH",
    "release/invalid/notice-union-mismatch.json": "F120-V2-NOTICE-UNION-MISMATCH",
    "release/invalid/orphan-compliance-artifact.json": "F120-V2-ORPHAN-COMPLIANCE-ARTIFACT",
    "release/invalid/payload-without-unit.json": "F120-V2-PAYLOAD-WITHOUT-UNIT",
    "release/invalid/role-mismatch.json": "F120-V2-ROLE-MISMATCH",
    "release/invalid/staged-artifact-mismatch.json": "F120-V2-STAGED-ARTIFACT-MISMATCH",
    "release/invalid/unknown-artifact.json": "F120-V2-UNKNOWN-ARTIFACT",
    "release/invalid/wrong-pair.json": "F120-V2-PAIR-DIGEST-MISMATCH",
    "release/invalid/wrong-unit-binding.json": "F120-V2-COMPLIANCE-BINDING-MISMATCH",
    "release/invalid/zero-notice-counterexample.json": "F120-V2-ZERO-NOTICE-CARRIER",
}

EXPECTED_REFUSAL_FAMILIES = {
    "F120-V3-SCHEMA-IDENTITY",
    "F120-V2-SCHEMA-IDENTITY",
    "F120-V3-RESERVED-BUILD-OPTION",
    "F120-V3-DECLARED-INTERNAL-MANIFEST",
    "F120-V2-ZERO-NOTICE-CARRIER",
    "F120-V2-PAYLOAD-WITHOUT-UNIT",
    "F120-V2-UNKNOWN-ARTIFACT",
    "F120-V2-CROSS-COMPONENT-REFERENCE",
    "F120-V2-ROLE-MISMATCH",
    "F120-V2-LICENCE-TUPLE-MISMATCH",
    "F120-V2-NOTICE-TUPLE-MISMATCH",
    "F120-V2-LICENCE-UNION-MISMATCH",
    "F120-V2-NOTICE-UNION-MISMATCH",
    "F120-V2-ORPHAN-COMPLIANCE-ARTIFACT",
    "F120-V2-EXCLUSIVE-COMPLIANCE-ARTIFACT",
    "F120-V2-ARTIFACT-BINDING-MISMATCH",
    "F120-V2-PAIR-DIGEST-MISMATCH",
    "F120-V2-STAGED-ARTIFACT-MISMATCH",
    "F120-V2-COMPLIANCE-BINDING-MISMATCH",
    "F120-V2-F100-VALIDATOR-UNAVAILABLE",
}


class CandidateFailure(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    try:
        encoded = json.dumps(value, indent=2, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise CandidateFailure(f"value is not canonical JSON: {exc}") from exc
    return (encoded + "\n").encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def load_json(path: Path) -> Any:
    if path.is_symlink() or not path.is_file():
        raise CandidateFailure("input is not a regular no-follow file")
    if path.stat().st_size > MAX_DOCUMENT_BYTES:
        raise CandidateFailure(f"document exceeds {MAX_DOCUMENT_BYTES} bytes")

    def reject_constant(value: str) -> None:
        raise CandidateFailure(f"non-finite JSON number: {value}")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise CandidateFailure(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    payload = path.read_bytes()
    text = payload.decode("utf-8")
    value = json.loads(
        text,
        object_pairs_hook=reject_duplicates,
        parse_constant=reject_constant,
    )
    if payload != canonical_bytes(value):
        raise CandidateFailure("non-canonical JSON bytes")
    return value


def schema_validators() -> dict[str, Draft202012Validator]:
    result: dict[str, Draft202012Validator] = {}
    for identity, path in SCHEMAS.items():
        schema = load_json(path)
        Draft202012Validator.check_schema(schema)
        result[identity] = Draft202012Validator(
            schema, format_checker=FormatChecker()
        )
    return result


def issue(code: str, detail: str) -> str:
    return f"{code}: {detail}"


def exact_keys(
    value: Any, required: set[str], label: str, errors: list[str]
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        errors.append(issue("F120-V2-OBJECT-SHAPE", f"{label} must be an object"))
        return None
    missing = sorted(required - set(value))
    extra = sorted(set(value) - required)
    if missing:
        errors.append(
            issue("F120-V2-OBJECT-SHAPE", f"{label} missing fields {missing}")
        )
    if extra:
        errors.append(
            issue("F120-V2-OBJECT-SHAPE", f"{label} has unknown fields {extra}")
        )
    return value


def require_array(value: Any, label: str, errors: list[str]) -> list[Any]:
    if not isinstance(value, list):
        errors.append(issue("F120-V2-ARRAY-SHAPE", f"{label} must be an array"))
        return []
    return value


def sorted_unique(
    values: Iterable[Any], label: str, errors: list[str], *, code: str = "F120-V2-NONCANONICAL-ORDER"
) -> None:
    material = list(values)
    try:
        expected = sorted(set(material))
    except TypeError:
        errors.append(issue(code, f"{label} contains non-comparable or unhashable values"))
        return
    if material != expected:
        errors.append(issue(code, f"{label} must be sorted and unique"))


def valid_id(value: Any) -> bool:
    return isinstance(value, str) and len(value) <= 128 and IDENTIFIER_RE.fullmatch(value) is not None


def valid_sha(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value != "0" * 64
        and SHA256_RE.fullmatch(value) is not None
    )


def valid_artifact_id(value: Any) -> bool:
    return valid_id(value) and set(value) != {"0"}


def valid_relative_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or len(value) > 4096 or "\0" in value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts


def canonical_url_error(value: Any) -> bool:
    if not isinstance(value, str):
        return True
    parsed = urlsplit(value)
    return bool(
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.hostname != parsed.hostname.lower()
    )


def kind_role_errors(kind: Any, role: Any, label: str) -> list[str]:
    errors: list[str] = []
    if kind not in ARTIFACT_KINDS:
        errors.append(issue("F120-V2-ROLE-MISMATCH", f"{label} has unknown kind {kind!r}"))
    if role not in ARTIFACT_ROLES:
        errors.append(issue("F120-V2-ROLE-MISMATCH", f"{label} has unknown role {role!r}"))
        return errors
    if role == "payload" and kind not in PAYLOAD_KINDS:
        errors.append(issue("F120-V2-ROLE-MISMATCH", f"{label} payload has incompatible kind {kind!r}"))
    if role in COMPLIANCE_ROLES and kind in FORBIDDEN_COMPLIANCE_KINDS:
        errors.append(issue("F120-V2-ROLE-MISMATCH", f"{label} compliance role has payload kind {kind!r}"))
    if role == "internal-stage-manifest" and kind != "manifest":
        errors.append(issue("F120-V2-ROLE-MISMATCH", f"{label} internal stage manifest is not kind manifest"))
    return errors


def declaration_errors(
    declarations: Any,
    units: Any,
    licences: Any,
    notices: Any,
    *,
    label: str,
    allow_empty: bool,
) -> list[str]:
    errors: list[str] = []
    artifact_list = require_array(declarations, f"{label}.artifact_declarations", errors)
    unit_list = require_array(units, f"{label}.compliance_units", errors)
    licence_list = require_array(licences, f"{label}.licenses", errors)
    notice_list = require_array(notices, f"{label}.notices", errors)
    if len(artifact_list) > MAX_ARTIFACTS or len(unit_list) > MAX_UNITS:
        errors.append(issue("F120-V2-BOUND", f"{label} exceeds artifact/unit bound"))
    if not licence_list:
        errors.append(
            issue(
                "F120-V2-BOUND",
                f"{label}.licenses must not be empty",
            )
        )
    if not notice_list:
        errors.append(
            issue(
                "F120-V2-BOUND",
                f"{label}.notices must not be empty",
            )
        )
    by_id: dict[str, dict[str, Any]] = {}
    paths: set[str] = set()
    for index, raw in enumerate(artifact_list):
        item_label = f"{label}.artifact_declarations[{index}]"
        if not isinstance(raw, dict):
            errors.append(issue("F120-V2-OBJECT-SHAPE", f"{item_label} must be object"))
            continue
        required = {"artifact_id", "artifact_kind", "artifact_role", "path"}
        allowed = required | {"expected_sha256"}
        if set(raw) - allowed or required - set(raw):
            errors.append(issue("F120-V2-OBJECT-SHAPE", f"{item_label} is not closed"))
        artifact_id = raw.get("artifact_id")
        path = raw.get("path")
        role = raw.get("artifact_role")
        if not valid_artifact_id(artifact_id):
            errors.append(issue("F120-V2-IDENTIFIER", f"{item_label}.artifact_id is invalid"))
        elif artifact_id in by_id:
            errors.append(issue("F120-V2-DUPLICATE-ARTIFACT-ID", str(artifact_id)))
        else:
            by_id[artifact_id] = raw
        if not valid_relative_path(path):
            errors.append(issue("F120-V2-PATH", f"{item_label}.path is invalid"))
        elif path in paths:
            errors.append(issue("F120-V2-DUPLICATE-ARTIFACT-PATH", str(path)))
        else:
            paths.add(path)
        errors.extend(kind_role_errors(raw.get("artifact_kind"), role, item_label))
        if role == "internal-stage-manifest":
            errors.append(issue("F120-V3-DECLARED-INTERNAL-MANIFEST", item_label))
        if role not in {"payload", "internal-stage-manifest"} and not valid_sha(
            raw.get("expected_sha256")
        ):
            errors.append(issue("F120-V2-MISSING-EXPECTED-DIGEST", item_label))
        if "expected_sha256" in raw and not valid_sha(raw["expected_sha256"]):
            errors.append(issue("F120-V2-DIGEST", f"{item_label}.expected_sha256 is invalid"))
    ids = [item.get("artifact_id") for item in artifact_list if isinstance(item, dict)]
    sorted_unique(ids, f"{label}.artifact_declarations", errors)

    licence_union = {
        (item.get("spdx"), item.get("text_sha256"))
        for item in licence_list
        if isinstance(item, dict)
    }
    notice_union = {
        (item.get("path"), item.get("sha256"))
        for item in notice_list
        if isinstance(item, dict)
    }
    payload_counts: Counter[str] = Counter()
    compliance_counts: Counter[str] = Counter()
    observed_licences: set[tuple[Any, Any]] = set()
    observed_notices: set[tuple[Any, Any]] = set()
    unit_ids: list[Any] = []
    for index, raw in enumerate(unit_list):
        unit_label = f"{label}.compliance_units[{index}]"
        unit = exact_keys(raw, UNIT_DECLARATION_KEYS, unit_label, errors)
        if unit is None:
            continue
        unit_id = unit.get("unit_id")
        unit_ids.append(unit_id)
        if not valid_id(unit_id):
            errors.append(issue("F120-V2-IDENTIFIER", f"{unit_label}.unit_id is invalid"))
        if not valid_sha(unit.get("artifact_binding_sha256")):
            errors.append(issue("F120-V2-DIGEST", f"{unit_label}.artifact_binding_sha256"))
        if not valid_sha(unit.get("pair_sha256")):
            errors.append(issue("F120-V2-DIGEST", f"{unit_label}.pair_sha256"))
        payload_ids = require_array(unit.get("payload_artifact_ids"), f"{unit_label}.payload_artifact_ids", errors)
        if not payload_ids:
            errors.append(issue("F120-V2-PAYLOAD-WITHOUT-UNIT", f"{unit_label} has no payload"))
        if len(payload_ids) > MAX_PAYLOAD_IDS:
            errors.append(issue("F120-V2-BOUND", f"{unit_label}.payload_artifact_ids"))
        sorted_unique(payload_ids, f"{unit_label}.payload_artifact_ids", errors)
        for artifact_id in payload_ids:
            if not valid_artifact_id(artifact_id):
                errors.append(issue("F120-V2-IDENTIFIER", f"{unit_label}:{artifact_id!r}"))
            payload_counts[artifact_id] += 1
            artifact = by_id.get(artifact_id)
            if artifact is None:
                errors.append(issue("F120-V2-UNKNOWN-ARTIFACT", f"{unit_label}:{artifact_id}"))
            elif artifact.get("artifact_role") != "payload":
                errors.append(issue("F120-V2-ROLE-MISMATCH", f"{unit_label}:{artifact_id} is not payload"))

        mandatory = {
            field: unit.get(f"{field}_artifact_id")
            for field in MANDATORY_UNIT_ROLES
        }
        for field, artifact_id in mandatory.items():
            if not valid_artifact_id(artifact_id):
                errors.append(issue("F120-V2-IDENTIFIER", f"{unit_label}:{field}"))
            compliance_counts[artifact_id] += 1
            artifact = by_id.get(artifact_id)
            expected_role = MANDATORY_UNIT_ROLES[field]
            if artifact is None:
                errors.append(issue("F120-V2-UNKNOWN-ARTIFACT", f"{unit_label}:{artifact_id}"))
            elif artifact.get("artifact_role") != expected_role:
                errors.append(issue("F120-V2-ROLE-MISMATCH", f"{unit_label}:{artifact_id} expected {expected_role}"))
        descriptor = by_id.get(unit.get("artifact_descriptor_artifact_id"))
        if descriptor is not None and descriptor.get("expected_sha256") != unit.get(
            "artifact_binding_sha256"
        ):
            errors.append(issue("F120-V2-ARTIFACT-BINDING-MISMATCH", unit_label))
        pair = by_id.get(unit.get("pair_artifact_id"))
        if pair is not None and pair.get("expected_sha256") != unit.get("pair_sha256"):
            errors.append(issue("F120-V2-PAIR-DIGEST-MISMATCH", unit_label))

        licence_refs = require_array(unit.get("license_texts"), f"{unit_label}.license_texts", errors)
        if not licence_refs or len(licence_refs) > MAX_LICENCE_ENTRIES:
            errors.append(
                issue(
                    "F120-V2-BOUND",
                    f"{unit_label}.license_texts must contain 1..{MAX_LICENCE_ENTRIES} entries",
                )
            )
        licence_order: list[tuple[Any, Any, Any]] = []
        for ref in licence_refs:
            if not isinstance(ref, dict):
                errors.append(issue("F120-V2-OBJECT-SHAPE", f"{unit_label}.license_texts entry"))
                continue
            if set(ref) != {"artifact_id", "spdx", "text_sha256"}:
                errors.append(issue("F120-V2-OBJECT-SHAPE", f"{unit_label}.license_texts entry"))
            tuple_value = (ref.get("spdx"), ref.get("text_sha256"))
            observed_licences.add(tuple_value)
            licence_order.append((ref.get("spdx"), ref.get("text_sha256"), ref.get("artifact_id")))
            if tuple_value not in licence_union:
                errors.append(issue("F120-V2-LICENCE-TUPLE-MISMATCH", f"{unit_label}:{tuple_value}"))
            artifact_id = ref.get("artifact_id")
            if not valid_artifact_id(artifact_id) or not valid_sha(ref.get("text_sha256")):
                errors.append(issue("F120-V2-DIGEST", f"{unit_label}.license_texts entry"))
            compliance_counts[artifact_id] += 1
            artifact = by_id.get(artifact_id)
            if artifact is None:
                errors.append(issue("F120-V2-UNKNOWN-ARTIFACT", f"{unit_label}:{artifact_id}"))
            elif artifact.get("artifact_role") != "license-text":
                errors.append(issue("F120-V2-ROLE-MISMATCH", f"{unit_label}:{artifact_id} expected license-text"))
            elif artifact.get("expected_sha256") != ref.get("text_sha256"):
                errors.append(issue("F120-V2-LICENCE-TUPLE-MISMATCH", f"{unit_label}:{artifact_id} digest"))
        if licence_order != sorted(set(licence_order)):
            errors.append(issue("F120-V2-NONCANONICAL-ORDER", f"{unit_label}.license_texts"))

        notice_refs = require_array(unit.get("notices"), f"{unit_label}.notices", errors)
        if not notice_refs or len(notice_refs) > MAX_NOTICE_ENTRIES:
            errors.append(
                issue(
                    "F120-V2-BOUND",
                    f"{unit_label}.notices must contain 1..{MAX_NOTICE_ENTRIES} entries",
                )
            )
        notice_order: list[tuple[Any, Any, Any, Any]] = []
        conveyance = 0
        for ref in notice_refs:
            if not isinstance(ref, dict):
                errors.append(issue("F120-V2-OBJECT-SHAPE", f"{unit_label}.notices entry"))
                continue
            if set(ref) != {"artifact_id", "kind", "path", "sha256"}:
                errors.append(issue("F120-V2-OBJECT-SHAPE", f"{unit_label}.notices entry"))
            tuple_value = (ref.get("path"), ref.get("sha256"))
            observed_notices.add(tuple_value)
            notice_order.append((ref.get("path"), ref.get("sha256"), ref.get("kind"), ref.get("artifact_id")))
            if ref.get("kind") == "conveyance":
                conveyance += 1
            if tuple_value not in notice_union:
                errors.append(issue("F120-V2-NOTICE-TUPLE-MISMATCH", f"{unit_label}:{tuple_value}"))
            expected_role = {
                "conveyance": "conveyance-notice",
                "upstream": "upstream-notice",
                "attribution": "other-notice",
                "other": "other-notice",
            }.get(ref.get("kind"))
            artifact_id = ref.get("artifact_id")
            if (
                not valid_artifact_id(artifact_id)
                or not valid_relative_path(ref.get("path"))
                or not valid_sha(ref.get("sha256"))
            ):
                errors.append(issue("F120-V2-DIGEST", f"{unit_label}.notices entry"))
            compliance_counts[artifact_id] += 1
            artifact = by_id.get(artifact_id)
            if artifact is None:
                errors.append(issue("F120-V2-UNKNOWN-ARTIFACT", f"{unit_label}:{artifact_id}"))
            elif artifact.get("artifact_role") != expected_role:
                errors.append(issue("F120-V2-ROLE-MISMATCH", f"{unit_label}:{artifact_id} expected {expected_role}"))
            elif artifact.get("expected_sha256") != ref.get("sha256"):
                errors.append(issue("F120-V2-NOTICE-TUPLE-MISMATCH", f"{unit_label}:{artifact_id} digest"))
        if conveyance != 1:
            errors.append(issue("F120-V2-CONVEYANCE-NOTICE-COUNT", f"{unit_label} has {conveyance}"))
        if notice_order != sorted(set(notice_order)):
            errors.append(issue("F120-V2-NONCANONICAL-ORDER", f"{unit_label}.notices"))

        other_ids = require_array(unit.get("other_notice_artifact_ids"), f"{unit_label}.other_notice_artifact_ids", errors)
        if len(other_ids) > MAX_OTHER_NOTICE_IDS:
            errors.append(issue("F120-V2-BOUND", f"{unit_label}.other_notice_artifact_ids"))
        sorted_unique(other_ids, f"{unit_label}.other_notice_artifact_ids", errors)
        for artifact_id in other_ids:
            if not valid_artifact_id(artifact_id):
                errors.append(issue("F120-V2-IDENTIFIER", f"{unit_label}:{artifact_id!r}"))
            compliance_counts[artifact_id] += 1
            artifact = by_id.get(artifact_id)
            if artifact is None:
                errors.append(issue("F120-V2-UNKNOWN-ARTIFACT", f"{unit_label}:{artifact_id}"))
            elif artifact.get("artifact_role") != "other-notice":
                errors.append(issue("F120-V2-ROLE-MISMATCH", f"{unit_label}:{artifact_id} expected other-notice"))

    if unit_ids != sorted(set(unit_ids)):
        errors.append(issue("F120-V2-NONCANONICAL-ORDER", f"{label}.compliance_units"))
    declared_payloads = {
        artifact_id
        for artifact_id, item in by_id.items()
        if item.get("artifact_role") == "payload"
    }
    if declared_payloads and not unit_list and not allow_empty:
        errors.append(issue("F120-V2-PAYLOAD-WITHOUT-UNIT", f"{label} has payload declarations and no units"))
    for artifact_id in sorted(declared_payloads):
        count = payload_counts[artifact_id]
        if count != 1:
            errors.append(issue("F120-V2-PAYLOAD-WITHOUT-UNIT", f"{label}:{artifact_id} occurs in {count} units"))
    for artifact_id, artifact in sorted(by_id.items()):
        role = artifact.get("artifact_role")
        if role in COMPLIANCE_ROLES:
            count = compliance_counts[artifact_id]
            if count == 0:
                errors.append(issue("F120-V2-ORPHAN-COMPLIANCE-ARTIFACT", f"{label}:{artifact_id}"))
            if role in EXCLUSIVE_ROLES and count != 1:
                errors.append(issue("F120-V2-EXCLUSIVE-COMPLIANCE-ARTIFACT", f"{label}:{artifact_id} occurs {count} times"))
    if observed_licences != licence_union and declared_payloads:
        errors.append(issue("F120-V2-LICENCE-UNION-MISMATCH", label))
    if observed_notices != notice_union and declared_payloads:
        errors.append(issue("F120-V2-NOTICE-UNION-MISMATCH", label))
    return errors


def registration_errors(document: Any) -> list[str]:
    errors: list[str] = []
    top = exact_keys(document, {"components", "dependencies", "schema", "workspace_root"}, "registration", errors)
    if top is None:
        return errors
    if top.get("schema") != REGISTRATION_ID:
        errors.append(issue("F120-V3-SCHEMA-IDENTITY", repr(top.get("schema"))))
    if not isinstance(top.get("workspace_root"), str) or not Path(top["workspace_root"]).is_absolute():
        errors.append(issue("F120-V3-WORKSPACE-ROOT", "workspace_root must be absolute"))
    components = require_array(top.get("components"), "components", errors)
    if not components or len(components) > MAX_COMPONENTS:
        errors.append(issue("F120-V3-COMPONENT-COUNT", str(len(components))))
    instance_ids: list[Any] = []
    component_by_instance: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(components):
        label = f"components[{index}]"
        if not isinstance(raw, dict):
            errors.append(issue("F120-V2-OBJECT-SHAPE", f"{label} must be object"))
            continue
        missing = sorted(REGISTRATION_COMPONENT_REQUIRED - set(raw))
        extra = sorted(set(raw) - REGISTRATION_COMPONENT_ALLOWED)
        if missing or extra:
            errors.append(issue("F120-V2-OBJECT-SHAPE", f"{label} missing={missing} extra={extra}"))
        component_id = raw.get("component_id")
        component_path = raw.get("path")
        if not valid_id(component_id):
            errors.append(issue("F120-V2-IDENTIFIER", f"{label}.component_id"))
        if not valid_relative_path(component_path):
            errors.append(issue("F120-V2-PATH", f"{label}.path"))
        instance = raw.get("instance_id")
        if instance is None and valid_id(component_id) and valid_relative_path(component_path):
            instance = f"{component_id}-{hashlib.sha256(component_path.encode('utf-8')).hexdigest()[:12]}"
        instance_ids.append(instance)
        if not valid_id(instance):
            errors.append(issue("F120-V2-IDENTIFIER", f"{label}.instance_id"))
        else:
            component_by_instance[instance] = raw
        if canonical_url_error(raw.get("canonical_url")):
            errors.append(issue("F120-V2-CANONICAL-URL", label))
        if not isinstance(raw.get("expected_commit"), str) or COMMIT_RE.fullmatch(raw["expected_commit"]) is None:
            errors.append(issue("F120-V2-COMMIT", f"{label}.expected_commit"))
        for field in ("component_version", "api_version", "abi_version", "architecture", "requested_ref"):
            value = raw.get(field)
            if not isinstance(value, str) or not value or len(value) > 512:
                errors.append(issue("F120-V2-STRING", f"{label}.{field}"))
        for field, allowed in (
            ("visibility", VISIBILITIES),
            ("publication_disposition", PUBLICATION_DISPOSITIONS),
            ("runtime_kind", RUNTIME_KINDS),
            ("ref_kind", REF_KINDS),
        ):
            if raw.get(field) not in allowed:
                errors.append(issue("F120-V2-ENUM", f"{label}.{field}"))
        options = raw.get("build_options")
        if not isinstance(options, dict):
            errors.append(issue("F120-V2-OBJECT-SHAPE", f"{label}.build_options"))
        else:
            if len(options) > 256:
                errors.append(issue("F120-V2-BOUND", f"{label}.build_options"))
            for name, value in options.items():
                if name in RESERVED_BUILD_OPTIONS:
                    errors.append(issue("F120-V3-RESERVED-BUILD-OPTION", f"{label}:{name}"))
                if not isinstance(name, str) or not isinstance(value, (str, int, bool)):
                    errors.append(issue("F120-V2-BUILD-OPTION", f"{label}:{name}"))
        features = require_array(raw.get("features"), f"{label}.features", errors)
        required_tests = require_array(raw.get("required_tests"), f"{label}.required_tests", errors)
        sorted_unique(features, f"{label}.features", errors)
        sorted_unique(required_tests, f"{label}.required_tests", errors)
        if not required_tests or any(not valid_id(value) for value in required_tests):
            errors.append(issue("F120-V2-IDENTIFIER", f"{label}.required_tests"))
        if any(not valid_id(value) for value in features):
            errors.append(issue("F120-V2-IDENTIFIER", f"{label}.features"))
        licences = require_array(raw.get("licenses"), f"{label}.licenses", errors)
        if not licences:
            errors.append(issue("F120-V2-BOUND", f"{label}.licenses must not be empty"))
        licence_order = []
        for item in licences:
            if not isinstance(item, dict) or set(item) != {"spdx", "text_path", "text_sha256"}:
                errors.append(issue("F120-V2-OBJECT-SHAPE", f"{label}.licenses entry"))
                continue
            licence_order.append(item.get("spdx"))
            if not valid_relative_path(item.get("text_path")) or not valid_sha(item.get("text_sha256")):
                errors.append(issue("F120-V2-LICENCE-TUPLE-MISMATCH", f"{label}.licenses entry"))
        sorted_unique(licence_order, f"{label}.licenses", errors)
        notices = require_array(raw.get("notices"), f"{label}.notices", errors)
        if not notices:
            errors.append(issue("F120-V2-BOUND", f"{label}.notices must not be empty"))
        notice_order = []
        for item in notices:
            if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
                errors.append(issue("F120-V2-OBJECT-SHAPE", f"{label}.notices entry"))
                continue
            notice_order.append(item.get("path"))
            if not valid_relative_path(item.get("path")) or not valid_sha(item.get("sha256")):
                errors.append(issue("F120-V2-NOTICE-TUPLE-MISMATCH", f"{label}.notices entry"))
        sorted_unique(notice_order, f"{label}.notices", errors)
        toolchain = exact_keys(
            raw.get("toolchain"),
            {"executables", "name", "version"},
            f"{label}.toolchain",
            errors,
        )
        if toolchain is not None:
            if not valid_id(toolchain.get("name")):
                errors.append(issue("F120-V2-IDENTIFIER", f"{label}.toolchain.name"))
            if not isinstance(toolchain.get("version"), str) or not toolchain.get("version"):
                errors.append(issue("F120-V2-STRING", f"{label}.toolchain.version"))
            executables = require_array(
                toolchain.get("executables"), f"{label}.toolchain.executables", errors
            )
            executable_names: list[Any] = []
            for executable_index, value in enumerate(executables):
                executable_label = f"{label}.toolchain.executables[{executable_index}]"
                if not isinstance(value, dict):
                    errors.append(issue("F120-V2-OBJECT-SHAPE", executable_label))
                    continue
                required_executable = {"kind", "name", "path", "sha256"}
                if set(value) - (required_executable | {"interpreter"}) or required_executable - set(value):
                    errors.append(issue("F120-V2-OBJECT-SHAPE", executable_label))
                executable_names.append(value.get("name"))
                if value.get("kind") not in EXECUTABLE_KINDS:
                    errors.append(issue("F120-V2-ENUM", f"{executable_label}.kind"))
                if not valid_id(value.get("name")):
                    errors.append(issue("F120-V2-IDENTIFIER", f"{executable_label}.name"))
                if not isinstance(value.get("path"), str) or not Path(value["path"]).is_absolute():
                    errors.append(issue("F120-V2-PATH", f"{executable_label}.path"))
                if not valid_sha(value.get("sha256")):
                    errors.append(issue("F120-V2-DIGEST", f"{executable_label}.sha256"))
                if "interpreter" in value and not valid_id(value.get("interpreter")):
                    errors.append(issue("F120-V2-IDENTIFIER", f"{executable_label}.interpreter"))
            sorted_unique(executable_names, f"{label}.toolchain.executables", errors)
        build = raw.get("build")
        if build is None:
            if raw.get("expected_commit") != "0" * 40:
                errors.append(issue("F120-V3-RESOLVED-COMPONENT-NO-BUILD", label))
            continue
        if raw.get("expected_commit") == "0" * 40:
            errors.append(issue("F120-V3-UNRESOLVED-COMPONENT-HAS-BUILD", label))
        build_object = exact_keys(
            build,
            {"artifacts", "commands", "compliance_units", "copies", "environment"},
            f"{label}.build",
            errors,
        )
        if build_object is None:
            continue
        commands = require_array(build_object.get("commands"), f"{label}.build.commands", errors)
        if not commands or any(not isinstance(command, list) or not command or not all(isinstance(arg, str) and arg for arg in command) for command in commands):
            errors.append(issue("F120-V3-BUILD-COMMAND", label))
        environment = build_object.get("environment")
        if not isinstance(environment, dict):
            errors.append(issue("F120-V3-BUILD-ENVIRONMENT", label))
        else:
            for name, value in environment.items():
                if (
                    not isinstance(name, str)
                    or ENVIRONMENT_NAME_RE.fullmatch(name) is None
                    or name in RESERVED_ENVIRONMENT
                    or name.startswith(RESERVED_ENVIRONMENT_PREFIXES)
                    or BUILD_ENVIRONMENT_NAME_RE.fullmatch(name) is None
                    or not isinstance(value, str)
                    or not value
                ):
                    errors.append(issue("F120-V3-BUILD-ENVIRONMENT", f"{label}:{name}"))
        artifacts = require_array(build_object.get("artifacts"), f"{label}.build.artifacts", errors)
        copies = require_array(build_object.get("copies"), f"{label}.build.copies", errors)
        destinations = []
        for copy_item in copies:
            if not isinstance(copy_item, dict) or set(copy_item) != {"source", "destination", "mode"}:
                errors.append(issue("F120-V2-OBJECT-SHAPE", f"{label}.build.copies entry"))
                continue
            if (
                not valid_relative_path(copy_item.get("source"))
                or not valid_relative_path(copy_item.get("destination"))
                or not isinstance(copy_item.get("mode"), int)
                or isinstance(copy_item.get("mode"), bool)
                or not 0 <= copy_item["mode"] <= 0o777
            ):
                errors.append(issue("F120-V2-COPY", f"{label}.build.copies entry"))
            destinations.append(copy_item.get("destination"))
        artifact_paths = [item.get("path") for item in artifacts if isinstance(item, dict)]
        if set(destinations) != set(artifact_paths) or len(destinations) != len(artifact_paths):
            errors.append(issue("F120-V3-COPY-ARTIFACT-CLOSURE", label))
        errors.extend(
            declaration_errors(
                artifacts,
                build_object.get("compliance_units"),
                licences,
                notices,
                label=label,
                allow_empty=False,
            )
        )
    comparable_instances = [value for value in instance_ids if isinstance(value, str)]
    if len(comparable_instances) != len(set(comparable_instances)):
        errors.append(issue("F120-V2-DUPLICATE-COMPONENT", "registration instance_id"))
    dependencies = require_array(top.get("dependencies"), "dependencies", errors)
    dependency_order: list[tuple[Any, Any, Any, Any]] = []
    for index, raw in enumerate(dependencies):
        label = f"dependencies[{index}]"
        required = {
            "consumption_mode",
            "from",
            "required_abi_version",
            "required_api_version",
            "required_tests",
            "runtime_process",
            "to",
        }
        dependency = exact_keys(raw, required, label, errors)
        if dependency is None:
            continue
        source = dependency.get("from")
        target = dependency.get("to")
        dependency_order.append(
            (source, target, dependency.get("consumption_mode"), dependency.get("runtime_process"))
        )
        for field in ("from", "to", "runtime_process"):
            if not valid_id(dependency.get(field)):
                errors.append(issue("F120-V2-IDENTIFIER", f"{label}.{field}"))
        if dependency.get("consumption_mode") not in CONSUMPTION_MODES:
            errors.append(issue("F120-V2-ENUM", f"{label}.consumption_mode"))
        tests = require_array(dependency.get("required_tests"), f"{label}.required_tests", errors)
        sorted_unique(tests, f"{label}.required_tests", errors)
        if not tests or any(not valid_id(value) for value in tests):
            errors.append(issue("F120-V2-IDENTIFIER", f"{label}.required_tests"))
        target_component = component_by_instance.get(target)
        if source not in component_by_instance or target_component is None:
            errors.append(issue("F120-V2-UNKNOWN-DEPENDENCY-COMPONENT", label))
        elif (
            dependency.get("required_api_version") != target_component.get("api_version")
            or dependency.get("required_abi_version") != target_component.get("abi_version")
        ):
            errors.append(issue("F120-V2-DEPENDENCY-VERSION", label))
    if dependency_order != sorted(dependency_order):
        errors.append(issue("F120-V2-NONCANONICAL-ORDER", "dependencies"))
    return errors


def graph_errors(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    components = document.get("components", [])
    dependencies = document.get("dependencies", [])
    if not isinstance(components, list) or not isinstance(dependencies, list):
        return [issue("F120-V2-GRAPH-SHAPE", "components/dependencies must be arrays")]
    by_instance: dict[str, dict[str, Any]] = {}
    for index, component in enumerate(components):
        if not isinstance(component, dict):
            continue
        instance = component.get("instance_id")
        if not isinstance(instance, str):
            continue
        if instance in by_instance:
            errors.append(issue("F120-V2-DUPLICATE-COMPONENT", instance))
        by_instance[instance] = component
        sorted_unique(component.get("features", []), f"components[{index}].features", errors)
        sorted_unique(
            component.get("required_tests", []),
            f"components[{index}].required_tests",
            errors,
        )
        sorted_unique(
            [
                item.get("spdx")
                for item in component.get("licenses", [])
                if isinstance(item, dict)
            ],
            f"components[{index}].licenses SPDX identifiers",
            errors,
        )
        sorted_unique(
            [
                item.get("path")
                for item in component.get("notices", [])
                if isinstance(item, dict)
            ],
            f"components[{index}].notice paths",
            errors,
        )
        if canonical_url_error(component.get("canonical_url")):
            errors.append(issue("F120-V2-CANONICAL-URL", f"components[{index}]"))
        if component.get("publication_disposition") == "publish" and component.get("visibility") != "public":
            errors.append(issue("F120-V2-PUBLICATION-VISIBILITY", instance))
    seen_edges: set[tuple[Any, ...]] = set()
    adjacency: dict[str, list[str]] = {key: [] for key in by_instance}
    process_instances: dict[str, set[str]] = {}
    for index, edge in enumerate(dependencies):
        if not isinstance(edge, dict):
            continue
        source, target = edge.get("from"), edge.get("to")
        key = (source, target, edge.get("consumption_mode"), edge.get("runtime_process"))
        if key in seen_edges:
            errors.append(issue("F120-V2-DUPLICATE-DEPENDENCY", repr(key)))
        seen_edges.add(key)
        if source not in by_instance or target not in by_instance:
            errors.append(issue("F120-V2-UNKNOWN-DEPENDENCY-COMPONENT", f"dependencies[{index}]"))
            continue
        adjacency[source].append(target)
        process_instances.setdefault(edge.get("runtime_process"), set()).update(
            (source, target)
        )
        sorted_unique(
            edge.get("required_tests", []),
            f"dependencies[{index}].required_tests",
            errors,
        )
        if edge.get("required_api_version") != by_instance[target].get("api_version"):
            errors.append(issue("F120-V2-API-MISMATCH", f"dependencies[{index}]"))
        if edge.get("required_abi_version") != by_instance[target].get("abi_version"):
            errors.append(issue("F120-V2-ABI-MISMATCH", f"dependencies[{index}]"))
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            errors.append(issue("F120-V2-DEPENDENCY-CYCLE", node))
            return
        if node in visited:
            return
        visiting.add(node)
        for target in adjacency.get(node, []):
            visit(target)
        visiting.remove(node)
        visited.add(node)

    for node in sorted(by_instance):
        visit(node)
    for process, instances in sorted(
        process_instances.items(), key=lambda item: repr(item[0])
    ):
        resolutions: dict[str, set[str]] = {}
        for instance in instances:
            component = by_instance[instance]
            if component.get("runtime_kind") != "native-provider":
                continue
            commit = component.get("resolved_commit")
            if commit:
                resolutions.setdefault(component.get("component_id"), set()).add(commit)
        for component_id, commits in sorted(
            resolutions.items(), key=lambda item: repr(item[0])
        ):
            if len(commits) > 1:
                errors.append(
                    issue(
                        "F120-V2-NATIVE-PROVIDER-CONFLICT",
                        f"process {process}: {component_id} resolves to {sorted(commits)}",
                    )
                )
    return errors


def workspace_semantic_errors(document: dict[str, Any], *, allow_development_state: bool) -> list[str]:
    errors = graph_errors(document)
    for index, component in enumerate(document.get("components", [])):
        if not isinstance(component, dict):
            continue
        label = f"components[{index}]"
        resolved = component.get("resolution_state") == "resolved"
        errors.extend(
            declaration_errors(
                component.get("artifact_declarations"),
                component.get("compliance_units"),
                component.get("licenses"),
                component.get("notices"),
                label=label,
                allow_empty=not resolved and allow_development_state,
            )
        )
        expected_declaration_digest = canonical_sha256(
            {
                "artifact_declarations": component.get("artifact_declarations"),
                "compliance_units": component.get("compliance_units"),
            }
        )
        actual_declaration_digest = component.get("build_options", {}).get(
            "f120_compliance_declaration_sha256"
        )
        if resolved and actual_declaration_digest != expected_declaration_digest:
            errors.append(issue("F120-V2-COMPLIANCE-DECLARATION-DIGEST", label))
        if not allow_development_state:
            name = component.get("instance_id", label)
            if not resolved:
                errors.append(issue("F120-V2-UNRESOLVED", str(name)))
            if component.get("dirty"):
                errors.append(issue("F120-V2-DIRTY", str(name)))
            if component.get("ref_kind") != "exact-commit":
                errors.append(issue("F120-V2-MUTABLE-REF", str(name)))
            if component.get("requested_ref") != component.get("expected_commit"):
                errors.append(issue("F120-V2-REQUESTED-COMMIT-MISMATCH", str(name)))
            if component.get("resolved_commit") != component.get("expected_commit"):
                errors.append(issue("F120-V2-RESOLVED-COMMIT-MISMATCH", str(name)))
    return errors


def unit_reference(
    value: Any,
    *,
    expected_role: str,
    unit_label: str,
    artifacts: dict[str, dict[str, Any]],
    component_instance: str,
    counts: Counter[str],
    errors: list[str],
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        errors.append(issue("F120-V2-OBJECT-SHAPE", f"{unit_label} reference"))
        return None
    artifact_id = value.get("artifact_id")
    if not valid_artifact_id(artifact_id):
        errors.append(issue("F120-V2-IDENTIFIER", f"{unit_label}:{artifact_id!r}"))
    artifact = artifacts.get(artifact_id)
    counts[artifact_id] += 1
    if artifact is None:
        errors.append(issue("F120-V2-UNKNOWN-ARTIFACT", f"{unit_label}:{artifact_id}"))
        return None
    if artifact.get("component_instance") != component_instance:
        errors.append(issue("F120-V2-CROSS-COMPONENT-REFERENCE", f"{unit_label}:{artifact_id}"))
    if artifact.get("artifact_role") != expected_role:
        errors.append(issue("F120-V2-ROLE-MISMATCH", f"{unit_label}:{artifact_id} expected {expected_role}"))
    if value.get("staged_path") != artifact.get("path") or value.get("artifact_sha256") != artifact.get("artifact_sha256"):
        errors.append(issue("F120-V2-STAGED-ARTIFACT-MISMATCH", f"{unit_label}:{artifact_id}"))
    return artifact


def release_semantic_errors(document: dict[str, Any], *, require_f100: bool) -> list[str]:
    errors = graph_errors(document)
    components = {
        item.get("instance_id"): item
        for item in document.get("components", [])
        if isinstance(item, dict)
    }
    artifacts: dict[str, dict[str, Any]] = {}
    paths: set[str] = set()
    component_artifacts: set[str] = set()
    payload_ids: set[str] = set()
    for index, artifact in enumerate(document.get("artifacts", [])):
        if not isinstance(artifact, dict):
            continue
        label = f"artifacts[{index}]"
        artifact_id = artifact.get("artifact_id")
        path = artifact.get("path")
        if not valid_artifact_id(artifact_id):
            errors.append(issue("F120-V2-IDENTIFIER", f"{label}.artifact_id"))
        if not valid_sha(artifact.get("artifact_sha256")):
            errors.append(issue("F120-V2-DIGEST", f"{label}.artifact_sha256"))
        if artifact_id in artifacts:
            errors.append(issue("F120-V2-DUPLICATE-ARTIFACT-ID", str(artifact_id)))
        else:
            artifacts[artifact_id] = artifact
        if path in paths:
            errors.append(issue("F120-V2-DUPLICATE-ARTIFACT-PATH", str(path)))
        paths.add(path)
        instance = artifact.get("component_instance")
        component = components.get(instance)
        if component is None:
            errors.append(issue("F120-V2-UNKNOWN-COMPONENT", f"{label}:{instance}"))
            continue
        component_artifacts.add(instance)
        errors.extend(kind_role_errors(artifact.get("artifact_kind"), artifact.get("artifact_role"), label))
        sorted_unique(artifact.get("features", []), f"{label}.features", errors)
        for field, expected in {
            "source_sha256": component.get("source_sha256"),
            "architecture": component.get("architecture"),
            "toolchain_digest": component.get("toolchain", {}).get("digest"),
            "features": component.get("features"),
        }.items():
            if artifact.get(field) != expected:
                errors.append(issue("F120-V2-ARTIFACT-COMPONENT-BINDING", f"{label}:{field}"))
        if artifact.get("licenses_sha256") != canonical_sha256(component.get("licenses")):
            errors.append(issue("F120-V2-LICENCES-BINDING", label))
        expected_build_key = canonical_sha256(
            {
                "architecture": component.get("architecture"),
                "build_options": component.get("build_options"),
                "features": component.get("features"),
                "source_sha256": component.get("source_sha256"),
                "toolchain_digest": component.get("toolchain", {}).get("digest"),
            }
        )
        if artifact.get("build_key_sha256") != expected_build_key:
            errors.append(issue("F120-V2-BUILD-KEY-BINDING", label))
        if artifact.get("artifact_role") == "payload":
            payload_ids.add(artifact_id)
    missing_components = sorted(set(components) - component_artifacts)
    if missing_components:
        errors.append(issue("F120-V2-COMPONENT-WITHOUT-ARTIFACT", repr(missing_components)))

    units = document.get("compliance_units", [])
    if payload_ids and not units:
        errors.append(
            issue(
                "F120-V2-ZERO-NOTICE-CARRIER",
                "payload artifacts exist but the release has zero compliance units",
            )
        )
    unit_order: list[tuple[Any, Any]] = []
    counts: Counter[str] = Counter()
    payload_counts: Counter[str] = Counter()
    component_licence_union: dict[str, set[tuple[Any, Any]]] = {
        instance: {
            (item.get("spdx"), item.get("text_sha256"))
            for item in component.get("licenses", [])
            if isinstance(item, dict)
        }
        for instance, component in components.items()
    }
    component_notice_union: dict[str, set[tuple[Any, Any]]] = {
        instance: {
            (item.get("path"), item.get("sha256"))
            for item in component.get("notices", [])
            if isinstance(item, dict)
        }
        for instance, component in components.items()
    }
    observed_licences: dict[str, set[tuple[Any, Any]]] = defaultdict(set)
    observed_notices: dict[str, set[tuple[Any, Any]]] = defaultdict(set)
    for index, unit in enumerate(units if isinstance(units, list) else []):
        unit_label = f"compliance_units[{index}]"
        if not isinstance(unit, dict):
            continue
        if set(unit) != EXPANDED_UNIT_KEYS:
            errors.append(issue("F120-V2-OBJECT-SHAPE", f"{unit_label} is not closed"))
        instance = unit.get("component_instance")
        unit_id = unit.get("unit_id")
        unit_order.append((instance, unit_id))
        if instance not in components:
            errors.append(issue("F120-V2-CROSS-COMPONENT-REFERENCE", f"{unit_label}:{instance}"))
            continue
        for field, role in MANDATORY_UNIT_ROLES.items():
            unit_reference(
                unit.get(field),
                expected_role=role,
                unit_label=unit_label,
                artifacts=artifacts,
                component_instance=instance,
                counts=counts,
                errors=errors,
            )
        descriptor = unit.get("artifact_descriptor")
        if isinstance(descriptor, dict) and unit.get("artifact_binding_sha256") != descriptor.get("artifact_sha256"):
            errors.append(issue("F120-V2-ARTIFACT-BINDING-MISMATCH", unit_label))
        pair = unit.get("pair")
        if isinstance(pair, dict) and unit.get("pair_sha256") != pair.get("artifact_sha256"):
            errors.append(issue("F120-V2-PAIR-DIGEST-MISMATCH", unit_label))

        payloads = unit.get("payloads", [])
        if not payloads:
            errors.append(issue("F120-V2-PAYLOAD-WITHOUT-UNIT", f"{unit_label} has zero payloads"))
        payload_order = []
        for value in payloads if isinstance(payloads, list) else []:
            artifact = unit_reference(
                value,
                expected_role="payload",
                unit_label=unit_label,
                artifacts=artifacts,
                component_instance=instance,
                counts=counts,
                errors=errors,
            )
            artifact_id = value.get("artifact_id") if isinstance(value, dict) else None
            payload_order.append(artifact_id)
            payload_counts[artifact_id] += 1
            if artifact is not None:
                if artifact.get("distribution_unit_id") != unit_id:
                    errors.append(issue("F120-V2-DISTRIBUTION-UNIT-MISMATCH", f"{unit_label}:{artifact_id}"))
                if artifact.get("compliance_binding_sha256") != unit.get("compliance_binding_sha256"):
                    errors.append(issue("F120-V2-COMPLIANCE-BINDING-MISMATCH", f"{unit_label}:{artifact_id}"))
        sorted_unique(payload_order, f"{unit_label}.payloads", errors)

        licence_order = []
        for value in unit.get("license_texts", []) if isinstance(unit.get("license_texts"), list) else []:
            artifact = unit_reference(
                value,
                expected_role="license-text",
                unit_label=unit_label,
                artifacts=artifacts,
                component_instance=instance,
                counts=counts,
                errors=errors,
            )
            if not isinstance(value, dict):
                continue
            tuple_value = (value.get("spdx"), value.get("text_sha256"))
            observed_licences[instance].add(tuple_value)
            licence_order.append((value.get("spdx"), value.get("text_sha256"), value.get("artifact_id")))
            if tuple_value not in component_licence_union[instance]:
                errors.append(issue("F120-V2-LICENCE-TUPLE-MISMATCH", f"{unit_label}:{tuple_value}"))
            if artifact is not None and (
                value.get("artifact_sha256") != value.get("text_sha256")
                or artifact.get("artifact_sha256") != value.get("text_sha256")
            ):
                errors.append(issue("F120-V2-LICENCE-TUPLE-MISMATCH", f"{unit_label}:{value.get('artifact_id')} digest"))
        if licence_order != sorted(set(licence_order)):
            errors.append(issue("F120-V2-NONCANONICAL-ORDER", f"{unit_label}.license_texts"))

        conveyance = 0
        notice_order = []
        for value in unit.get("notices", []) if isinstance(unit.get("notices"), list) else []:
            if not isinstance(value, dict):
                continue
            kind = value.get("kind")
            expected_role = {
                "conveyance": "conveyance-notice",
                "upstream": "upstream-notice",
                "attribution": "other-notice",
                "other": "other-notice",
            }.get(kind, "other-notice")
            artifact = unit_reference(
                value,
                expected_role=expected_role,
                unit_label=unit_label,
                artifacts=artifacts,
                component_instance=instance,
                counts=counts,
                errors=errors,
            )
            if kind == "conveyance":
                conveyance += 1
            tuple_value = (value.get("path"), value.get("sha256"))
            observed_notices[instance].add(tuple_value)
            notice_order.append((value.get("path"), value.get("sha256"), kind, value.get("artifact_id")))
            if tuple_value not in component_notice_union[instance]:
                errors.append(issue("F120-V2-NOTICE-TUPLE-MISMATCH", f"{unit_label}:{tuple_value}"))
            if artifact is not None and (
                value.get("artifact_sha256") != value.get("sha256")
                or artifact.get("artifact_sha256") != value.get("sha256")
            ):
                errors.append(issue("F120-V2-NOTICE-TUPLE-MISMATCH", f"{unit_label}:{value.get('artifact_id')} digest"))
        if conveyance != 1:
            errors.append(issue("F120-V2-CONVEYANCE-NOTICE-COUNT", f"{unit_label} has {conveyance}"))
        if notice_order != sorted(set(notice_order)):
            errors.append(issue("F120-V2-NONCANONICAL-ORDER", f"{unit_label}.notices"))

        other_order = []
        for value in unit.get("other_notices", []) if isinstance(unit.get("other_notices"), list) else []:
            unit_reference(
                value,
                expected_role="other-notice",
                unit_label=unit_label,
                artifacts=artifacts,
                component_instance=instance,
                counts=counts,
                errors=errors,
            )
            if isinstance(value, dict):
                other_order.append(value.get("artifact_id"))
        sorted_unique(other_order, f"{unit_label}.other_notices", errors)

        binding_input = copy.deepcopy(unit)
        binding_input.pop("compliance_binding_sha256", None)
        expected_binding = hashlib.sha256(
            b"kilix.f120.compliance-unit/v1\0" + canonical_bytes(binding_input)
        ).hexdigest()
        if unit.get("compliance_binding_sha256") != expected_binding:
            errors.append(issue("F120-V2-COMPLIANCE-BINDING-MISMATCH", unit_label))
    if unit_order != sorted(set(unit_order)):
        errors.append(issue("F120-V2-NONCANONICAL-ORDER", "compliance_units"))
    for artifact_id in sorted(payload_ids):
        if payload_counts[artifact_id] != 1:
            errors.append(issue("F120-V2-PAYLOAD-WITHOUT-UNIT", f"{artifact_id} occurs in {payload_counts[artifact_id]} units"))
    for artifact_id, artifact in sorted(artifacts.items()):
        role = artifact.get("artifact_role")
        if role in COMPLIANCE_ROLES:
            if counts[artifact_id] == 0:
                errors.append(issue("F120-V2-ORPHAN-COMPLIANCE-ARTIFACT", artifact_id))
            if role in EXCLUSIVE_ROLES and counts[artifact_id] != 1:
                errors.append(issue("F120-V2-EXCLUSIVE-COMPLIANCE-ARTIFACT", f"{artifact_id} occurs {counts[artifact_id]} times"))
    for instance in components:
        if observed_licences[instance] != component_licence_union[instance]:
            errors.append(issue("F120-V2-LICENCE-UNION-MISMATCH", instance))
        if observed_notices[instance] != component_notice_union[instance]:
            errors.append(issue("F120-V2-NOTICE-UNION-MISMATCH", instance))
    if require_f100:
        errors.append(
            issue(
                "F120-V2-F100-VALIDATOR-UNAVAILABLE",
                "no accepted F100 validator/API identity is bound; release qualification refuses",
            )
        )
    return errors


def schema_errors(document: dict[str, Any], available: dict[str, Draft202012Validator]) -> list[str]:
    identity = document.get("schema")
    validator = available.get(identity)
    if validator is None:
        return [issue("F120-V2-SCHEMA-IDENTITY", repr(identity))]
    return [
        issue(
            "F120-V2-SCHEMA",
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}",
        )
        for error in sorted(
            validator.iter_errors(document), key=lambda item: list(item.absolute_path)
        )
    ]


def validate_document(
    path: Path,
    available: dict[str, Draft202012Validator],
    *,
    allow_development_state: bool = False,
    contract_preflight: bool = False,
    release_qualification: bool = False,
) -> list[str]:
    try:
        document = load_json(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CandidateFailure) as exc:
        return [issue("F120-V2-LOAD", str(exc))]
    if not isinstance(document, dict):
        return [issue("F120-V2-OBJECT-SHAPE", "document must be an object")]
    identity = document.get("schema")
    if release_qualification and identity != RELEASE_ID:
        return [
            issue(
                "F120-V2-QUALIFICATION-INPUT-IDENTITY",
                f"release qualification requires exact {RELEASE_ID}, got {identity!r}",
            )
        ]
    if isinstance(identity, str) and identity.startswith("kilix.f120.registration/"):
        return registration_errors(document)
    errors = schema_errors(document, available)
    if identity == WORKSPACE_ID:
        errors.extend(
            workspace_semantic_errors(
                document, allow_development_state=allow_development_state
            )
        )
    elif identity == RELEASE_ID:
        errors.extend(
            release_semantic_errors(document, require_f100=release_qualification)
        )
    return errors


def package_files() -> list[Path]:
    fixed = [
        ROOT / "README.md",
        ROOT / "PROFILE.md",
        ROOT / "RATIFIED-AMENDMENT.md",
        ROOT / "REVIEW-REQUEST.md",
        ROOT / "build_candidate.py",
        ROOT / "pyproject.toml",
        ROOT / "uv.lock",
        Path(__file__),
    ]
    valid = [
        FIXTURES / "registration" / "valid" / "two-obligation-units.json",
        FIXTURES / "workspace" / "valid" / "two-obligation-units.json",
        FIXTURES / "release" / "valid" / "two-obligation-units.json",
    ]
    invalid = [FIXTURES / relative for relative in EXPECTED_INVALID]
    return sorted(
        [*fixed, *SCHEMAS.values(), *valid, *invalid],
        key=lambda path: path.relative_to(ROOT).as_posix(),
    )


def observed_package_files() -> tuple[set[Path], list[str]]:
    """Enumerate the complete candidate byte surface, not just known globs.

    A top-level ``.venv`` is review-run state created by ``uv`` and is outside
    the candidate package.  Every other directory member is examined.  The
    manifest excludes itself to avoid a self-referential digest.
    """

    observed: set[Path] = set()
    errors: list[str] = []
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if relative.parts[0] == ".venv":
            continue
        if relative == Path("SHA256SUMS"):
            continue
        if path.is_symlink():
            errors.append(
                issue("F120-V2-PACKAGE-INVENTORY", f"symlink is forbidden: {relative.as_posix()}")
            )
        elif path.is_file():
            observed.add(path)
        elif not path.is_dir():
            errors.append(
                issue("F120-V2-PACKAGE-INVENTORY", f"special member is forbidden: {relative.as_posix()}")
            )
    return observed, errors


def expected_hash_manifest() -> str:
    return "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(ROOT).as_posix()}\n"
        for path in package_files()
    )


def package_errors() -> list[str]:
    errors: list[str] = []
    expected = set(package_files())
    observed, inventory_errors = observed_package_files()
    errors.extend(inventory_errors)
    missing = sorted(
        path.relative_to(ROOT).as_posix() for path in expected - observed
    )
    unexpected = sorted(
        path.relative_to(ROOT).as_posix() for path in observed - expected
    )
    if missing or unexpected:
        errors.append(
            issue(
                "F120-V2-PACKAGE-INVENTORY",
                f"missing={missing} unexpected={unexpected}",
            )
        )
    ratified = ROOT / "RATIFIED-AMENDMENT.md"
    if (
        not ratified.is_file()
        or hashlib.sha256(ratified.read_bytes()).hexdigest()
        != RATIFIED_AMENDMENT_SHA256
    ):
        errors.append(
            issue(
                "F120-V2-RATIFICATION-DIGEST",
                "RATIFIED-AMENDMENT.md does not match Owner Decision 14 bytes",
            )
        )
    for path in [*SCHEMAS.values(), *(FIXTURES / relative for relative in EXPECTED_INVALID), *(
        FIXTURES / family / "valid" / "two-obligation-units.json"
        for family in ("registration", "workspace", "release")
    )]:
        try:
            if path.read_bytes() != canonical_bytes(load_json(path)):
                errors.append(issue("F120-V2-NONCANONICAL-BYTES", str(path.relative_to(ROOT))))
        except (OSError, CandidateFailure, json.JSONDecodeError) as exc:
            errors.append(issue("F120-V2-LOAD", f"{path.relative_to(ROOT)}: {exc}"))
    manifest = ROOT / "SHA256SUMS"
    if not manifest.is_file():
        errors.append(issue("F120-V2-HASH-MANIFEST", "SHA256SUMS is absent"))
    elif manifest.read_text(encoding="ascii") != expected_hash_manifest():
        errors.append(issue("F120-V2-HASH-MANIFEST", "SHA256SUMS does not bind candidate bytes"))
    return errors


def adjudication_regression_errors(
    available: dict[str, Draft202012Validator],
) -> list[str]:
    """Replay the eight R2 adjudication findings against the R3 boundary."""

    failures: list[str] = []
    registration = load_json(
        FIXTURES / "registration" / "valid" / "two-obligation-units.json"
    )
    workspace = load_json(
        FIXTURES / "workspace" / "valid" / "two-obligation-units.json"
    )
    release = load_json(FIXTURES / "release" / "valid" / "two-obligation-units.json")

    def require_code(errors: list[str], code: str, label: str) -> None:
        if not any(code in error for error in errors):
            failures.append(f"R3 regression {label} missed {code}: {errors[:8]}")

    # M-01: qualification is an input-bound action, not a formatting flag.
    for label, document in (("registration qualification", registration), ("workspace qualification", workspace)):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.json"
            path.write_bytes(canonical_bytes(document))
            require_code(
                validate_document(path, available, release_qualification=True),
                "F120-V2-QUALIFICATION-INPUT-IDENTITY",
                label,
            )
    parser = argument_parser()
    for arguments, label in (
        (["--release-qualification", "--self-test"], "qualification plus self-test"),
        (["--release-qualification", "--write-hashes"], "qualification plus write-hashes"),
    ):
        try:
            with redirect_stderr(io.StringIO()):
                parser.parse_args(arguments)
        except SystemExit as exc:
            if exc.code == 0:
                failures.append(f"R3 regression {label} exited zero")
        else:
            failures.append(f"R3 regression {label} was not parser-refused")

    # M-02: the registration successor retains v2 closure, enums and environment rules.
    unknown_dependency = copy.deepcopy(registration)
    unknown_dependency["dependencies"] = [{"surprise": "not-closed"}]
    require_code(registration_errors(unknown_dependency), "F120-V2-OBJECT-SHAPE", "closed dependency")
    invalid_visibility = copy.deepcopy(registration)
    invalid_visibility["components"][0]["visibility"] = "not-a-visibility"
    require_code(registration_errors(invalid_visibility), "F120-V2-ENUM", "visibility enum")
    reserved_environment = copy.deepcopy(registration)
    reserved_environment["components"][0]["build"]["environment"] = {"PATH": "/injected"}
    require_code(
        registration_errors(reserved_environment),
        "F120-V3-BUILD-ENVIRONMENT",
        "reserved build environment",
    )

    # M-03: alternate encodings never reach schema or semantic joins.
    with tempfile.TemporaryDirectory() as temporary:
        compact = Path(temporary) / "compact.json"
        compact.write_bytes(json.dumps(release, sort_keys=True).encode("utf-8"))
        require_code(
            validate_document(compact, available, contract_preflight=True),
            "F120-V2-LOAD",
            "non-canonical bytes",
        )

    # M-04: all frozen graph invariants remain active on both successor documents.
    for field in ("features", "required_tests"):
        mutation = copy.deepcopy(workspace)
        mutation["components"][0][field] = ["z-review", "a-review"]
        require_code(graph_errors(mutation), "F120-V2-NONCANONICAL-ORDER", f"component {field} order")
    for field, values in (
        ("licenses", list(reversed(workspace["components"][0]["licenses"]))),
        ("notices", list(reversed(workspace["components"][0]["notices"]))),
    ):
        mutation = copy.deepcopy(workspace)
        mutation["components"][0][field] = values
        require_code(graph_errors(mutation), "F120-V2-NONCANONICAL-ORDER", f"component {field} order")
    dependency_tests = copy.deepcopy(workspace)
    component = dependency_tests["components"][0]
    dependency_tests["dependencies"] = [
        {
            "consumption_mode": "runtime-process",
            "from": component["instance_id"],
            "required_abi_version": component["abi_version"],
            "required_api_version": component["api_version"],
            "required_tests": ["z-review", "a-review"],
            "runtime_process": "review-process",
            "to": component["instance_id"],
        }
    ]
    require_code(
        graph_errors(dependency_tests),
        "F120-V2-NONCANONICAL-ORDER",
        "dependency tests order",
    )
    for base, label in ((workspace, "workspace native conflict"), (release, "release native conflict")):
        conflict = copy.deepcopy(base)
        first = conflict["components"][0]
        second = copy.deepcopy(first)
        second["instance_id"] = "f120-v2-demo-second"
        second["resolved_commit"] = "2" * 40
        second["source_sha256"] = hashlib.sha256(b"second-source").hexdigest()
        conflict["components"].append(second)
        conflict["dependencies"] = [
            {
                "consumption_mode": "runtime-process",
                "from": first["instance_id"],
                "required_abi_version": second["abi_version"],
                "required_api_version": second["api_version"],
                "required_tests": ["carrier-conformance"],
                "runtime_process": "review-process",
                "to": second["instance_id"],
            }
        ]
        require_code(
            graph_errors(conflict),
            "F120-V2-NATIVE-PROVIDER-CONFLICT",
            label,
        )

    # L-01/L-02/L-03: placeholders, missing/bounded arrays and fractional options refuse.
    zero_carrier = copy.deepcopy(registration)
    build = zero_carrier["components"][0]["build"]
    for artifact in build["artifacts"]:
        if artifact["artifact_id"] == "alpha-carrier-archive":
            artifact["artifact_id"] = "0" * 64
            artifact["expected_sha256"] = "0" * 64
    build["compliance_units"][0]["carrier_archive_artifact_id"] = "0" * 64
    require_code(registration_errors(zero_carrier), "F120-V2-IDENTIFIER", "zero carrier identity")
    require_code(registration_errors(zero_carrier), "F120-V2-DIGEST", "zero carrier digest")

    empty_licences = copy.deepcopy(registration)
    empty_licences["components"][0]["licenses"] = []
    require_code(registration_errors(empty_licences), "F120-V2-BOUND", "empty licences")

    overflow = copy.deepcopy(registration)
    overflow["components"][0]["build"]["compliance_units"][0][
        "other_notice_artifact_ids"
    ] = [f"other-notice-{index:04d}" for index in range(MAX_OTHER_NOTICE_IDS + 1)]
    require_code(registration_errors(overflow), "F120-V2-BOUND", "other-notice overflow")

    fractional = copy.deepcopy(registration)
    fractional["components"][0]["build_options"]["review_fraction"] = 0.5
    require_code(registration_errors(fractional), "F120-V2-BUILD-OPTION", "fractional build option")

    # L-04: locally decidable role and conveyance restrictions live in the schemas.
    workspace_validator = available[WORKSPACE_ID]
    internal = copy.deepcopy(workspace)
    internal["components"][0]["artifact_declarations"][0][
        "artifact_role"
    ] = "internal-stage-manifest"
    if not list(workspace_validator.iter_errors(internal)):
        failures.append("R3 regression workspace internal-stage-manifest remained schema-valid")
    incompatible = copy.deepcopy(workspace)
    payload = next(
        item
        for item in incompatible["components"][0]["artifact_declarations"]
        if item["artifact_role"] == "payload"
    )
    payload["artifact_kind"] = "notice"
    if not list(workspace_validator.iter_errors(incompatible)):
        failures.append("R3 regression incompatible kind/role remained schema-valid")
    double_conveyance = copy.deepcopy(workspace)
    second_notice = copy.deepcopy(
        double_conveyance["components"][0]["compliance_units"][0]["notices"][0]
    )
    second_notice["artifact_id"] = "second-conveyance"
    double_conveyance["components"][0]["compliance_units"][0]["notices"].append(second_notice)
    if not list(workspace_validator.iter_errors(double_conveyance)):
        failures.append("R3 regression two conveyance notices remained schema-valid")
    fractional_workspace = copy.deepcopy(workspace)
    fractional_workspace["components"][0]["build_options"]["review_fraction"] = 0.5
    if not list(workspace_validator.iter_errors(fractional_workspace)):
        failures.append("R3 regression fractional workspace build option remained schema-valid")
    return failures


def self_test(available: dict[str, Draft202012Validator]) -> int:
    failures = package_errors()
    failures.extend(adjudication_regression_errors(available))
    valid_paths = sorted(FIXTURES.glob("*/valid/*.json"))
    invalid_paths = sorted(FIXTURES.glob("*/invalid/*.json"))
    if len(valid_paths) != 3:
        failures.append(issue("F120-V2-FIXTURE-INVENTORY", f"expected 3 valid fixtures, found {len(valid_paths)}"))
    observed_refusal_families: set[str] = set()
    for path in valid_paths:
        errors = validate_document(path, available, contract_preflight=True)
        if errors:
            failures.append(f"valid fixture rejected: {path.relative_to(FIXTURES)}: {errors}")
        if path.parts[-3] == "release":
            qualifying = validate_document(
                path,
                available,
                release_qualification=True,
            )
            if any("F120-V2-F100-VALIDATOR-UNAVAILABLE" in error for error in qualifying):
                observed_refusal_families.add("F120-V2-F100-VALIDATOR-UNAVAILABLE")
            else:
                failures.append("release fixture did not fail closed on absent accepted F100 validator")
    observed_invalid = {
        path.relative_to(FIXTURES).as_posix() for path in invalid_paths
    }
    if observed_invalid != set(EXPECTED_INVALID):
        failures.append(
            issue(
                "F120-V2-FIXTURE-INVENTORY",
                f"invalid expected/actual differ: expected={sorted(EXPECTED_INVALID)} actual={sorted(observed_invalid)}",
            )
        )
    for path in invalid_paths:
        errors = validate_document(path, available, contract_preflight=True)
        relative = path.relative_to(FIXTURES).as_posix()
        expected = EXPECTED_INVALID.get(relative)
        if not errors:
            failures.append(f"invalid fixture accepted: {relative}")
        elif expected is not None and not any(expected in error for error in errors):
            failures.append(f"invalid fixture {relative} missed {expected}: {errors}")
        elif expected is not None:
            observed_refusal_families.add(expected)

    missing_families = sorted(EXPECTED_REFUSAL_FAMILIES - observed_refusal_families)
    if missing_families:
        failures.append(
            issue(
                "F120-V2-REFUSAL-COVERAGE",
                f"profile-mandated families without a focused fixture: {missing_families}",
            )
        )

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        duplicate = root / "duplicate.json"
        duplicate.write_text('{"schema":"x","schema":"y"}\n', encoding="utf-8")
        if not any("duplicate JSON key" in item for item in validate_document(duplicate, available)):
            failures.append("duplicate-key control was accepted")
        nonfinite = root / "nonfinite.json"
        nonfinite.write_text('{"schema":NaN}\n', encoding="utf-8")
        if not any("non-finite" in item for item in validate_document(nonfinite, available)):
            failures.append("non-finite-number control was accepted")
        oversized = root / "oversized.json"
        oversized.write_bytes(b" " * (MAX_DOCUMENT_BYTES + 1))
        if not any("exceeds" in item for item in validate_document(oversized, available)):
            failures.append("oversized-document control was accepted")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(
        "PASS: review-only v3/v2/v2 schemas, 3 valid and "
        f"{len(invalid_paths)} named-invalid fixtures; 20/20 profile refusal "
        "families and 8/8 R2 adjudication findings covered; qualification "
        "remains fail-closed on absent accepted F100 validators"
    )
    return 0


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", type=Path)
    parser.add_argument("--allow-development-state", action="store_true")
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--contract-preflight",
        action="store_true",
        help="non-qualifying F120-owned join review; does not call F100",
    )
    action.add_argument(
        "--release-qualification",
        action="store_true",
        help="release qualification; fails closed until accepted F100 validators are bound",
    )
    action.add_argument("--self-test", action="store_true")
    action.add_argument(
        "--write-hashes",
        action="store_true",
        help="write deterministic SHA256SUMS for the current review candidate",
    )
    return parser


def main() -> int:
    parser = argument_parser()
    args = parser.parse_args()
    if args.release_qualification and args.allow_development_state:
        parser.error("--release-qualification forbids --allow-development-state")
    if args.allow_development_state and not args.contract_preflight:
        parser.error("--allow-development-state requires --contract-preflight")
    if (args.self_test or args.write_hashes) and args.path is not None:
        parser.error("PATH cannot be combined with --self-test or --write-hashes")
    if args.write_hashes:
        (ROOT / "SHA256SUMS").write_text(expected_hash_manifest(), encoding="ascii")
        print(f"wrote SHA256SUMS for {len(package_files())} candidate files")
        return 0
    available = schema_validators()
    if args.self_test:
        return self_test(available)
    if args.path is None:
        parser.error("PATH is required unless --self-test is used")
    if not args.contract_preflight and not args.release_qualification:
        parser.error(
            "choose exactly one explicit mode: --contract-preflight or --release-qualification"
        )
    errors = validate_document(
        args.path,
        available,
        allow_development_state=args.allow_development_state,
        contract_preflight=args.contract_preflight,
        release_qualification=args.release_qualification,
    )
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    if args.contract_preflight:
        print(f"valid contract preflight only (not release qualification): {args.path}")
    else:
        print(f"valid: {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
