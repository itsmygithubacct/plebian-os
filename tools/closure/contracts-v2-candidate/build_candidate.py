#!/usr/bin/env python3
"""Deterministically derive the review-only F120 v3/v2/v2 contract corpus.

This generator never edits the frozen v1 package.  It copies the accepted v1
workspace/release vocabulary in memory, applies only the ratified incompatible
delta, and emits canonical candidate schemas and fixtures below this directory.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
V1_ROOT = ROOT.parent / "contracts"
SCHEMAS = ROOT / "schemas"
FIXTURES = ROOT / "fixtures"
FROZEN_V1_SHA256SUMS_SHA256 = (
    "4c67ee97ef59066e7c0b64cf77c7056bfa7791075cf7a7b88e0873527fd3371b"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

SHA256 = {"pattern": "^[0-9a-f]{64}$", "type": "string"}
ID = {
    "maxLength": 128,
    "pattern": "^[a-z0-9]+(?:[._-][a-z0-9]+)*$",
    "type": "string",
}
RELATIVE_PATH = {
    "maxLength": 4096,
    "minLength": 1,
    "pattern": r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$))[^\u0000]+$",
    "type": "string",
}

ARTIFACT_ROLES = [
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
]

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


def load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))


def verify_frozen_v1() -> None:
    manifest = V1_ROOT / "SHA256SUMS"
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != FROZEN_V1_SHA256SUMS_SHA256:
        raise SystemExit("refused: frozen v1 SHA256SUMS identity changed")
    seen: set[str] = set()
    for line_number, line in enumerate(
        manifest.read_text(encoding="ascii").splitlines(), start=1
    ):
        expected, separator, relative = line.partition("  ")
        if not separator or not SHA256_RE.fullmatch(expected):
            raise SystemExit(f"refused: malformed frozen v1 hash line {line_number}")
        if relative in seen:
            raise SystemExit(f"refused: duplicate frozen v1 hash entry {relative}")
        seen.add(relative)
        candidate = V1_ROOT.joinpath(*Path(relative).parts)
        try:
            candidate.relative_to(V1_ROOT)
        except ValueError:
            raise SystemExit(f"refused: escaping frozen v1 hash entry {relative}")
        if candidate.is_symlink() or not candidate.is_file():
            raise SystemExit(f"refused: missing frozen v1 file {relative}")
        if hashlib.sha256(candidate.read_bytes()).hexdigest() != expected:
            raise SystemExit(f"refused: frozen v1 digest mismatch {relative}")


def digest(value: Any) -> str:
    if isinstance(value, bytes):
        payload = value
    elif isinstance(value, str):
        payload = value.encode("utf-8")
    else:
        payload = canonical_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def role_schema() -> dict[str, Any]:
    return {"enum": ARTIFACT_ROLES}


def artifact_declaration_schema() -> dict[str, Any]:
    non_payload = [
        role
        for role in ARTIFACT_ROLES
        if role not in {"payload", "internal-stage-manifest"}
    ]
    return {
        "additionalProperties": False,
        "allOf": [
            {
                "if": {
                    "properties": {"artifact_role": {"enum": non_payload}},
                    "required": ["artifact_role"],
                },
                "then": {"required": ["expected_sha256"]},
            }
        ],
        "properties": {
            "artifact_id": {"$ref": "#/$defs/id"},
            "artifact_kind": {
                "enum": [
                    "command",
                    "header",
                    "library",
                    "python-package",
                    "pkg-config",
                    "data",
                    "notice",
                    "manifest",
                ]
            },
            "artifact_role": {"$ref": "#/$defs/artifactRole"},
            "expected_sha256": {"$ref": "#/$defs/sha256"},
            "path": {"$ref": "#/$defs/relativePath"},
        },
        "required": ["artifact_id", "artifact_kind", "artifact_role", "path"],
        "type": "object",
    }


def licence_reference_schema(*, expanded: bool) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "artifact_id": {"$ref": "#/$defs/id"},
        "spdx": {"maxLength": 128, "minLength": 1, "type": "string"},
        "text_sha256": {"$ref": "#/$defs/sha256"},
    }
    required = ["artifact_id", "spdx", "text_sha256"]
    if expanded:
        properties.update(
            {
                "artifact_sha256": {"$ref": "#/$defs/sha256"},
                "staged_path": {"$ref": "#/$defs/relativePath"},
            }
        )
        required.extend(["staged_path", "artifact_sha256"])
    return {
        "additionalProperties": False,
        "properties": properties,
        "required": required,
        "type": "object",
    }


def notice_reference_schema(*, expanded: bool) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "artifact_id": {"$ref": "#/$defs/id"},
        "kind": {"enum": ["conveyance", "upstream", "attribution", "other"]},
        "path": {"$ref": "#/$defs/relativePath"},
        "sha256": {"$ref": "#/$defs/sha256"},
    }
    required = ["artifact_id", "kind", "path", "sha256"]
    if expanded:
        properties.update(
            {
                "artifact_sha256": {"$ref": "#/$defs/sha256"},
                "staged_path": {"$ref": "#/$defs/relativePath"},
            }
        )
        required.extend(["staged_path", "artifact_sha256"])
    return {
        "additionalProperties": False,
        "properties": properties,
        "required": required,
        "type": "object",
    }


def compliance_unit_declaration_schema() -> dict[str, Any]:
    scalar_ids = [
        "artifact_descriptor_artifact_id",
        "carrier_archive_artifact_id",
        "carrier_manifest_artifact_id",
        "compliance_manifest_artifact_id",
        "internal_sha256sums_artifact_id",
        "modifications_artifact_id",
        "pair_artifact_id",
        "pair_digest_artifact_id",
        "unit_id",
        "upstream_notice_inventory_artifact_id",
    ]
    properties: dict[str, Any] = {
        name: {"$ref": "#/$defs/id"} for name in scalar_ids
    }
    properties.update(
        {
            "artifact_binding_sha256": {"$ref": "#/$defs/sha256"},
            "license_texts": {
                "items": {"$ref": "#/$defs/licenseTextReference"},
                "maxItems": 256,
                "minItems": 1,
                "type": "array",
            },
            "notices": {
                "items": {"$ref": "#/$defs/noticeReference"},
                "maxItems": 4096,
                "minItems": 1,
                "type": "array",
            },
            "other_notice_artifact_ids": {
                "items": {"$ref": "#/$defs/id"},
                "maxItems": 4096,
                "type": "array",
                "uniqueItems": True,
            },
            "pair_sha256": {"$ref": "#/$defs/sha256"},
            "payload_artifact_ids": {
                "items": {"$ref": "#/$defs/id"},
                "maxItems": 16384,
                "minItems": 1,
                "type": "array",
                "uniqueItems": True,
            },
        }
    )
    return {
        "additionalProperties": False,
        "properties": properties,
        "required": sorted(properties),
        "type": "object",
    }


def expanded_artifact_schema() -> dict[str, Any]:
    return {
        "additionalProperties": False,
        "properties": {
            "artifact_id": {"$ref": "#/$defs/id"},
            "artifact_sha256": {"$ref": "#/$defs/sha256"},
            "staged_path": {"$ref": "#/$defs/relativePath"},
        },
        "required": ["artifact_id", "staged_path", "artifact_sha256"],
        "type": "object",
    }


def expanded_unit_schema() -> dict[str, Any]:
    properties: dict[str, Any] = {
        "artifact_binding_sha256": {"$ref": "#/$defs/sha256"},
        "component_instance": {"$ref": "#/$defs/id"},
        "compliance_binding_sha256": {"$ref": "#/$defs/sha256"},
        "license_texts": {
            "items": {"$ref": "#/$defs/expandedLicenseText"},
            "maxItems": 256,
            "minItems": 1,
            "type": "array",
        },
        "notices": {
            "items": {"$ref": "#/$defs/expandedNotice"},
            "maxItems": 4096,
            "minItems": 1,
            "type": "array",
        },
        "other_notices": {
            "items": {"$ref": "#/$defs/expandedArtifact"},
            "maxItems": 4096,
            "type": "array",
        },
        "pair_sha256": {"$ref": "#/$defs/sha256"},
        "payloads": {
            "items": {"$ref": "#/$defs/expandedArtifact"},
            "maxItems": 16384,
            "minItems": 1,
            "type": "array",
        },
        "unit_id": {"$ref": "#/$defs/id"},
    }
    for name in MANDATORY_UNIT_ROLES:
        properties[name] = {"$ref": "#/$defs/expandedArtifact"}
    return {
        "additionalProperties": False,
        "properties": properties,
        "required": sorted(properties),
        "type": "object",
    }


def v2_licence_schema() -> dict[str, Any]:
    return {
        "additionalProperties": False,
        "properties": {
            "spdx": {"maxLength": 128, "minLength": 1, "type": "string"},
            "text_path": {"$ref": "#/$defs/relativePath"},
            "text_sha256": {"$ref": "#/$defs/sha256"},
        },
        "required": ["spdx", "text_path", "text_sha256"],
        "type": "object",
    }


def workspace_schema() -> dict[str, Any]:
    schema = copy.deepcopy(
        load(V1_ROOT / "schemas" / "kilix.f120.workspace-manifest-v1.schema.json")
    )
    schema["$comment"] = (
        "Review candidate for the ratified F120 licence carrier amendment; "
        "not authority until the required independent two-review freeze."
    )
    schema["$id"] = "https://schemas.kilix.dev/kilix.f120.workspace-manifest/v2"
    schema["title"] = "Kilix F120 observed workspace manifest with compliance units"
    schema["properties"]["schema"]["const"] = "kilix.f120.workspace-manifest/v2"
    defs = schema["$defs"]
    defs["license"] = v2_licence_schema()
    defs["artifactRole"] = role_schema()
    defs["artifactDeclaration"] = artifact_declaration_schema()
    defs["licenseTextReference"] = licence_reference_schema(expanded=False)
    defs["noticeReference"] = notice_reference_schema(expanded=False)
    defs["complianceUnitDeclaration"] = compliance_unit_declaration_schema()
    component = defs["component"]
    component["properties"]["artifact_declarations"] = {
        "items": {"$ref": "#/$defs/artifactDeclaration"},
        "maxItems": 16384,
        "type": "array",
    }
    component["properties"]["compliance_units"] = {
        "items": {"$ref": "#/$defs/complianceUnitDeclaration"},
        "maxItems": 4096,
        "type": "array",
    }
    component["required"] = sorted(
        [*component["required"], "artifact_declarations", "compliance_units"]
    )
    return schema


def release_schema() -> dict[str, Any]:
    schema = copy.deepcopy(
        load(V1_ROOT / "schemas" / "kilix.f120.release-lock-v1.schema.json")
    )
    schema["$comment"] = (
        "Review candidate for the ratified F120 licence carrier amendment; "
        "not authority until the required independent two-review freeze."
    )
    schema["$id"] = "https://schemas.kilix.dev/kilix.f120.release-lock/v2"
    schema["title"] = "Kilix F120 exact release lock with distribution-unit carriers"
    schema["properties"]["schema"]["const"] = "kilix.f120.release-lock/v2"
    defs = schema["$defs"]
    defs["license"] = v2_licence_schema()
    defs["artifactRole"] = role_schema()
    defs["expandedArtifact"] = expanded_artifact_schema()
    defs["expandedLicenseText"] = licence_reference_schema(expanded=True)
    defs["expandedNotice"] = notice_reference_schema(expanded=True)
    defs["expandedComplianceUnit"] = expanded_unit_schema()

    artifact = defs["artifact"]
    artifact["properties"].update(
        {
            "artifact_role": {"$ref": "#/$defs/artifactRole"},
            "compliance_binding_sha256": {"$ref": "#/$defs/sha256"},
            "distribution_unit_id": {"$ref": "#/$defs/id"},
        }
    )
    artifact["required"] = sorted([*artifact["required"], "artifact_role"])
    artifact["allOf"] = [
        {
            "if": {
                "properties": {"artifact_role": {"const": "payload"}},
                "required": ["artifact_role"],
            },
            "then": {
                "required": ["distribution_unit_id", "compliance_binding_sha256"]
            },
            "else": {
                "not": {
                    "anyOf": [
                        {"required": ["distribution_unit_id"]},
                        {"required": ["compliance_binding_sha256"]},
                    ]
                }
            },
        }
    ]
    schema["properties"]["compliance_units"] = {
        "items": {"$ref": "#/$defs/expandedComplianceUnit"},
        "maxItems": 16384,
        "minItems": 1,
        "type": "array",
    }
    schema["required"] = sorted([*schema["required"], "compliance_units"])
    return schema


def fixture_hash(label: str) -> str:
    return digest(f"kilix-f120-v2-candidate:{label}")


def artifact_kind(role: str, payload_index: int = 0) -> str:
    if role == "payload":
        return "command" if payload_index == 0 else "data"
    if role in {
        "artifact-descriptor",
        "compliance-manifest",
        "carrier-manifest",
        "pair-record",
    }:
        return "manifest"
    if role == "carrier-archive":
        return "data"
    return "notice"


def declarations_and_units() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    declarations: dict[str, dict[str, Any]] = {}
    units: list[dict[str, Any]] = []
    licence_sources = {
        "Apache-2.0": ("LICENSES/Apache-2.0.txt", fixture_hash("license-apache")),
        "MIT": ("LICENSES/MIT.txt", fixture_hash("license-mit")),
    }
    unit_inputs = [
        ("alpha", ["payload-alpha"], ["Apache-2.0"]),
        ("beta", ["payload-beta"], ["MIT"]),
        ("gamma", ["payload-gamma-data", "payload-gamma-tool"], ["Apache-2.0"]),
    ]
    for unit_id, payload_ids, spdx_values in unit_inputs:
        role_ids = {
            field: f"{unit_id}-{role}"
            for field, role in MANDATORY_UNIT_ROLES.items()
        }
        notice_id = f"{unit_id}-notice"
        notice_source_path = f"compliance/{unit_id}/NOTICE"
        notice_sha = fixture_hash(f"notice-source-{unit_id}")
        licence_refs: list[dict[str, str]] = []
        for spdx in spdx_values:
            slug = "apache" if spdx == "Apache-2.0" else "mit"
            artifact_id = f"license-{slug}"
            source_path, text_sha = licence_sources[spdx]
            licence_refs.append(
                {"artifact_id": artifact_id, "spdx": spdx, "text_sha256": text_sha}
            )
            declarations.setdefault(
                artifact_id,
                {
                    "artifact_id": artifact_id,
                    "artifact_kind": "notice",
                    "artifact_role": "license-text",
                    "expected_sha256": text_sha,
                    "path": f"share/licenses/demo/{Path(source_path).name}",
                },
            )
        for payload_index, artifact_id in enumerate(payload_ids):
            declarations[artifact_id] = {
                "artifact_id": artifact_id,
                "artifact_kind": artifact_kind("payload", payload_index),
                "artifact_role": "payload",
                "path": f"bin/{artifact_id}" if payload_index == 0 else f"share/demo/{artifact_id}",
            }
        for field, role in MANDATORY_UNIT_ROLES.items():
            artifact_id = role_ids[field]
            declarations[artifact_id] = {
                "artifact_id": artifact_id,
                "artifact_kind": artifact_kind(role),
                "artifact_role": role,
                "expected_sha256": fixture_hash(f"artifact-{artifact_id}"),
                "path": f"share/compliance/{unit_id}/{role}",
            }
        declarations[notice_id] = {
            "artifact_id": notice_id,
            "artifact_kind": "notice",
            "artifact_role": "conveyance-notice",
            "expected_sha256": notice_sha,
            "path": f"share/compliance/{unit_id}/NOTICE",
        }
        units.append(
            {
                "artifact_binding_sha256": declarations[
                    role_ids["artifact_descriptor"]
                ]["expected_sha256"],
                "artifact_descriptor_artifact_id": role_ids["artifact_descriptor"],
                "carrier_archive_artifact_id": role_ids["carrier_archive"],
                "carrier_manifest_artifact_id": role_ids["carrier_manifest"],
                "compliance_manifest_artifact_id": role_ids["compliance_manifest"],
                "internal_sha256sums_artifact_id": role_ids["internal_sha256sums"],
                "license_texts": sorted(
                    licence_refs,
                    key=lambda item: (
                        item["spdx"], item["text_sha256"], item["artifact_id"]
                    ),
                ),
                "modifications_artifact_id": role_ids["modifications"],
                "notices": [
                    {
                        "artifact_id": notice_id,
                        "kind": "conveyance",
                        "path": notice_source_path,
                        "sha256": notice_sha,
                    }
                ],
                "other_notice_artifact_ids": [],
                "pair_artifact_id": role_ids["pair"],
                "pair_digest_artifact_id": role_ids["pair_digest"],
                "pair_sha256": declarations[role_ids["pair"]]["expected_sha256"],
                "payload_artifact_ids": sorted(payload_ids),
                "unit_id": unit_id,
                "upstream_notice_inventory_artifact_id": role_ids[
                    "upstream_notice_inventory"
                ],
            }
        )
    return sorted(declarations.values(), key=lambda item: item["artifact_id"]), units


def registration_fixture() -> dict[str, Any]:
    declarations, units = declarations_and_units()
    licences = [
        {
            "spdx": "Apache-2.0",
            "text_path": "LICENSES/Apache-2.0.txt",
            "text_sha256": fixture_hash("license-apache"),
        },
        {
            "spdx": "MIT",
            "text_path": "LICENSES/MIT.txt",
            "text_sha256": fixture_hash("license-mit"),
        },
    ]
    notices = [
        {
            "path": f"compliance/{unit}/NOTICE",
            "sha256": fixture_hash(f"notice-source-{unit}"),
        }
        for unit in ("alpha", "beta", "gamma")
    ]
    copies = [
        {"destination": item["path"], "mode": 0o644, "source": item["path"]}
        for item in declarations
    ]
    return {
        "components": [
            {
                "abi_version": "1",
                "api_version": "1",
                "architecture": "x86_64-linux-gnu",
                "build": {
                    "artifacts": declarations,
                    "commands": [["install", "-D", "fixture", "prefix"]],
                    "compliance_units": units,
                    "copies": copies,
                    "environment": {},
                },
                "build_options": {"fixture": True},
                "canonical_url": "https://github.com/itsmygithubacct/f120-v2-demo.git",
                "component_id": "f120-v2-demo",
                "component_version": "1.0.0",
                "expected_commit": "1" * 40,
                "features": ["carrier-v2"],
                "instance_id": "f120-v2-demo",
                "licenses": licences,
                "notices": notices,
                "path": "components/f120-v2-demo",
                "publication_disposition": "publish",
                "ref_kind": "exact-commit",
                "requested_ref": "1" * 40,
                "required_tests": ["carrier-conformance"],
                "runtime_kind": "native-provider",
                "toolchain": {
                    "executables": [
                        {
                            "kind": "native",
                            "name": "install",
                            "path": "/usr/bin/install",
                            "sha256": fixture_hash("tool-install"),
                        }
                    ],
                    "name": "fixture-toolchain",
                    "version": "1",
                },
                "visibility": "public",
            }
        ],
        "dependencies": [],
        "schema": "kilix.f120.registration/v3",
        "workspace_root": "/workspace",
    }


def workspace_fixture(registration: dict[str, Any]) -> dict[str, Any]:
    source = registration["components"][0]
    declarations = copy.deepcopy(source["build"]["artifacts"])
    units = copy.deepcopy(source["build"]["compliance_units"])
    compliance_digest = digest(
        {"artifact_declarations": declarations, "compliance_units": units}
    )
    recipe_digest = digest(source["build"])
    toolchain_digest = digest(
        {
            "executables": [
                {
                    "interpreter": None,
                    "kind": "native",
                    "name": "install",
                    "sha256": fixture_hash("tool-install"),
                }
            ],
            "name": "fixture-toolchain",
            "version": "1",
        }
    )
    component = {
        "abi_version": source["abi_version"],
        "api_version": source["api_version"],
        "architecture": source["architecture"],
        "artifact_declarations": declarations,
        "build_options": {
            "f120_compliance_declaration_sha256": compliance_digest,
            "f120_recipe_sha256": recipe_digest,
            "fixture": True,
        },
        "canonical_url": source["canonical_url"],
        "component_id": source["component_id"],
        "component_version": source["component_version"],
        "compliance_units": units,
        "dirty": False,
        "expected_commit": source["expected_commit"],
        "features": source["features"],
        "instance_id": source["instance_id"],
        "licenses": source["licenses"],
        "notices": source["notices"],
        "publication_disposition": source["publication_disposition"],
        "ref_kind": source["ref_kind"],
        "requested_ref": source["requested_ref"],
        "required_tests": source["required_tests"],
        "resolution_state": "resolved",
        "resolved_commit": source["expected_commit"],
        "runtime_kind": source["runtime_kind"],
        "source_sha256": fixture_hash("source-tree"),
        "toolchain": {
            "digest": toolchain_digest,
            "name": "fixture-toolchain",
            "version": "1",
        },
        "visibility": source["visibility"],
    }
    return {
        "components": [component],
        "dependencies": [],
        "schema": "kilix.f120.workspace-manifest/v2",
        "workspace_root": "/workspace",
    }


def release_fixture(workspace: dict[str, Any]) -> dict[str, Any]:
    workspace_component = workspace["components"][0]
    declarations = workspace_component["artifact_declarations"]
    declaration_by_id = {item["artifact_id"]: item for item in declarations}
    source_sha = workspace_component["source_sha256"]
    toolchain_digest = workspace_component["toolchain"]["digest"]
    licenses_sha = digest(workspace_component["licenses"])
    build_key = digest(
        {
            "architecture": workspace_component["architecture"],
            "build_options": workspace_component["build_options"],
            "features": workspace_component["features"],
            "source_sha256": source_sha,
            "toolchain_digest": toolchain_digest,
        }
    )

    artifacts: list[dict[str, Any]] = []
    for declaration in declarations:
        actual_sha = declaration.get(
            "expected_sha256", fixture_hash(f"payload-{declaration['artifact_id']}")
        )
        artifacts.append(
            {
                "architecture": workspace_component["architecture"],
                "artifact_id": declaration["artifact_id"],
                "artifact_kind": declaration["artifact_kind"],
                "artifact_role": declaration["artifact_role"],
                "artifact_sha256": actual_sha,
                "build_key_sha256": build_key,
                "component_instance": workspace_component["instance_id"],
                "features": workspace_component["features"],
                "licenses_sha256": licenses_sha,
                "path": declaration["path"],
                "source_sha256": source_sha,
                "toolchain_digest": toolchain_digest,
            }
        )
    by_id = {item["artifact_id"]: item for item in artifacts}

    expanded_units: list[dict[str, Any]] = []
    for declaration in workspace_component["compliance_units"]:
        expanded: dict[str, Any] = {
            "artifact_binding_sha256": declaration["artifact_binding_sha256"],
            "component_instance": workspace_component["instance_id"],
            "license_texts": [],
            "notices": [],
            "other_notices": [],
            "pair_sha256": declaration["pair_sha256"],
            "payloads": [],
            "unit_id": declaration["unit_id"],
        }
        for field, role in MANDATORY_UNIT_ROLES.items():
            source_field = f"{field}_artifact_id"
            artifact = by_id[declaration[source_field]]
            expanded[field] = {
                "artifact_id": artifact["artifact_id"],
                "artifact_sha256": artifact["artifact_sha256"],
                "staged_path": artifact["path"],
            }
        for item in declaration["payload_artifact_ids"]:
            artifact = by_id[item]
            expanded["payloads"].append(
                {
                    "artifact_id": item,
                    "artifact_sha256": artifact["artifact_sha256"],
                    "staged_path": artifact["path"],
                }
            )
        for item in declaration["license_texts"]:
            artifact = by_id[item["artifact_id"]]
            expanded["license_texts"].append(
                {
                    **item,
                    "artifact_sha256": artifact["artifact_sha256"],
                    "staged_path": artifact["path"],
                }
            )
        for item in declaration["notices"]:
            artifact = by_id[item["artifact_id"]]
            expanded["notices"].append(
                {
                    **item,
                    "artifact_sha256": artifact["artifact_sha256"],
                    "staged_path": artifact["path"],
                }
            )
        for item in declaration["other_notice_artifact_ids"]:
            artifact = by_id[item]
            expanded["other_notices"].append(
                {
                    "artifact_id": item,
                    "artifact_sha256": artifact["artifact_sha256"],
                    "staged_path": artifact["path"],
                }
            )
        binding_input = copy.deepcopy(expanded)
        binding = hashlib.sha256(
            b"kilix.f120.compliance-unit/v1\0" + canonical_bytes(binding_input)
        ).hexdigest()
        expanded["compliance_binding_sha256"] = binding
        for payload in expanded["payloads"]:
            by_id[payload["artifact_id"]]["distribution_unit_id"] = declaration[
                "unit_id"
            ]
            by_id[payload["artifact_id"]]["compliance_binding_sha256"] = binding
        expanded_units.append(expanded)

    internal_id = "stage-manifest-f120-v2-demo"
    artifacts.append(
        {
            "architecture": workspace_component["architecture"],
            "artifact_id": internal_id,
            "artifact_kind": "manifest",
            "artifact_role": "internal-stage-manifest",
            "artifact_sha256": fixture_hash("stage-manifest"),
            "build_key_sha256": build_key,
            "component_instance": workspace_component["instance_id"],
            "features": workspace_component["features"],
            "licenses_sha256": licenses_sha,
            "path": "share/kilix-f120/f120-v2-demo.json",
            "source_sha256": source_sha,
            "toolchain_digest": toolchain_digest,
        }
    )
    locked_component = {
        key: copy.deepcopy(value)
        for key, value in workspace_component.items()
        if key
        not in {
            "artifact_declarations",
            "compliance_units",
            "dirty",
            "expected_commit",
            "ref_kind",
            "requested_ref",
            "resolution_state",
        }
    }
    return {
        "artifacts": sorted(artifacts, key=lambda item: item["artifact_id"]),
        "components": [locked_component],
        "compliance_units": sorted(
            expanded_units,
            key=lambda item: (item["component_instance"], item["unit_id"]),
        ),
        "dependencies": [],
        "release": "0.2.1",
        "schema": "kilix.f120.release-lock/v2",
    }


def invalid_fixtures(
    registration: dict[str, Any], workspace: dict[str, Any], release: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    registration_old_identity = copy.deepcopy(registration)
    registration_old_identity["schema"] = "kilix.f120.registration/v2"
    result["registration-older-schema-identity.json"] = registration_old_identity

    workspace_old_identity = copy.deepcopy(workspace)
    workspace_old_identity["schema"] = "kilix.f120.workspace-manifest/v1"
    result["workspace-older-schema-identity.json"] = workspace_old_identity

    zero_notice = copy.deepcopy(release)
    zero_notice["compliance_units"] = []
    zero_notice["artifacts"] = [
        item
        for item in zero_notice["artifacts"]
        if item["artifact_role"] in {"payload", "internal-stage-manifest"}
    ]
    result["release-zero-notice-counterexample.json"] = zero_notice

    wrong_binding = copy.deepcopy(release)
    wrong_binding["compliance_units"][0]["compliance_binding_sha256"] = "0" * 64
    result["release-wrong-unit-binding.json"] = wrong_binding

    wrong_artifact_binding = copy.deepcopy(release)
    wrong_artifact_binding["compliance_units"][0]["artifact_binding_sha256"] = "0" * 64
    result["release-artifact-binding-mismatch.json"] = wrong_artifact_binding

    borrowed = copy.deepcopy(release)
    borrowed["compliance_units"][1]["license_texts"][0]["spdx"] = "Apache-2.0"
    result["release-borrowed-same-spdx.json"] = borrowed

    missing_licence_union = copy.deepcopy(release)
    missing_licence_union["compliance_units"][1]["license_texts"] = []
    result["release-licence-union-mismatch.json"] = missing_licence_union

    missing_payload = copy.deepcopy(release)
    missing_payload["compliance_units"][0]["payloads"] = []
    result["release-payload-without-unit.json"] = missing_payload

    unknown_artifact = copy.deepcopy(release)
    unknown_artifact["compliance_units"][0]["payloads"][0]["artifact_id"] = "missing-payload"
    result["release-unknown-artifact.json"] = unknown_artifact

    staged_mismatch = copy.deepcopy(release)
    staged_mismatch["compliance_units"][0]["payloads"][0]["staged_path"] = "bin/not-the-payload"
    result["release-staged-artifact-mismatch.json"] = staged_mismatch

    role_mismatch = copy.deepcopy(release)
    notice_id = role_mismatch["compliance_units"][0]["notices"][0]["artifact_id"]
    for artifact in role_mismatch["artifacts"]:
        if artifact["artifact_id"] == notice_id:
            artifact["artifact_role"] = "upstream-notice"
    result["release-role-mismatch.json"] = role_mismatch

    wrong_component = copy.deepcopy(release)
    wrong_component["compliance_units"][0]["component_instance"] = "other-component"
    result["release-cross-component.json"] = wrong_component

    duplicate_path = copy.deepcopy(release)
    duplicate_path["artifacts"][1]["path"] = duplicate_path["artifacts"][0]["path"]
    result["release-duplicate-artifact-path.json"] = duplicate_path

    no_conveyance = copy.deepcopy(release)
    no_conveyance["compliance_units"][0]["notices"][0]["kind"] = "upstream"
    result["release-missing-conveyance.json"] = no_conveyance

    notice_tuple = copy.deepcopy(release)
    notice_tuple["compliance_units"][0]["notices"][0]["sha256"] = "0" * 64
    result["release-notice-tuple-mismatch.json"] = notice_tuple

    missing_notice_union = copy.deepcopy(release)
    missing_notice_union["compliance_units"][1]["notices"] = []
    result["release-notice-union-mismatch.json"] = missing_notice_union

    orphan = copy.deepcopy(release)
    orphan_artifact = copy.deepcopy(
        next(
            item
            for item in orphan["artifacts"]
            if item["artifact_role"] == "conveyance-notice"
        )
    )
    orphan_artifact["artifact_id"] = "zz-orphan-compliance-artifact"
    orphan_artifact["path"] = "share/compliance/zz-orphan/NOTICE"
    orphan["artifacts"].append(orphan_artifact)
    orphan["artifacts"].sort(key=lambda item: item["artifact_id"])
    result["release-orphan-compliance-artifact.json"] = orphan

    shared_exclusive = copy.deepcopy(release)
    shared_exclusive["compliance_units"][1]["modifications"] = copy.deepcopy(
        shared_exclusive["compliance_units"][0]["modifications"]
    )
    result["release-exclusive-artifact-shared.json"] = shared_exclusive

    wrong_pair = copy.deepcopy(release)
    wrong_pair["compliance_units"][0]["pair_sha256"] = "f" * 64
    result["release-wrong-pair.json"] = wrong_pair

    workspace_missing_unit = copy.deepcopy(workspace)
    workspace_missing_unit["components"][0]["compliance_units"] = []
    result["workspace-payload-without-unit.json"] = workspace_missing_unit

    registration_reserved = copy.deepcopy(registration)
    registration_reserved["components"][0]["build_options"][
        "f120_compliance_declaration_sha256"
    ] = "0" * 64
    result["registration-reserved-compliance-option.json"] = registration_reserved

    registration_internal = copy.deepcopy(registration)
    registration_internal["components"][0]["build"]["artifacts"][0][
        "artifact_role"
    ] = "internal-stage-manifest"
    result["registration-declared-internal-manifest.json"] = registration_internal
    return result


def expected_outputs() -> dict[Path, bytes]:
    outputs: dict[Path, bytes] = {
        SCHEMAS / "kilix.f120.workspace-manifest-v2.schema.json": canonical_bytes(
            workspace_schema()
        ),
        SCHEMAS / "kilix.f120.release-lock-v2.schema.json": canonical_bytes(
            release_schema()
        ),
    }
    registration = registration_fixture()
    workspace = workspace_fixture(registration)
    release = release_fixture(workspace)
    outputs[
        FIXTURES / "registration" / "valid" / "two-obligation-units.json"
    ] = canonical_bytes(registration)
    outputs[
        FIXTURES / "workspace" / "valid" / "two-obligation-units.json"
    ] = canonical_bytes(workspace)
    outputs[
        FIXTURES / "release" / "valid" / "two-obligation-units.json"
    ] = canonical_bytes(release)
    invalid = invalid_fixtures(registration, workspace, release)
    for name, document in invalid.items():
        family, filename = name.split("-", 1)
        outputs[FIXTURES / family / "invalid" / filename] = canonical_bytes(document)
    return outputs


def emit() -> None:
    for path, payload in expected_outputs().items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    verify_frozen_v1()
    if args.check:
        expected = expected_outputs()
        observed_paths = {
            path
            for root in (SCHEMAS, FIXTURES)
            for path in root.rglob("*")
            if path.is_file() or path.is_symlink()
        }
        changed = sorted(
            path.relative_to(ROOT).as_posix()
            for path in set(expected) | observed_paths
            if not path.is_file() or expected.get(path) != path.read_bytes()
        )
        if changed:
            raise SystemExit("candidate regeneration drift: " + ", ".join(changed))
        print(f"PASS: deterministic candidate regeneration ({len(expected)} JSON files)")
        return 0
    emit()
    print("wrote candidate schemas and fixtures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
