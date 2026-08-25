#!/usr/bin/env python3
"""Validate candidate F120 manifests without fetching or mutating a workspace."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parent
SCHEMAS = {
    "kilix.f120.workspace-manifest/v1": ROOT / "schemas" / "kilix.f120.workspace-manifest-v1.schema.json",
    "kilix.f120.release-lock/v1": ROOT / "schemas" / "kilix.f120.release-lock-v1.schema.json",
}
FIXTURES = ROOT / "fixtures"
MAX_DOCUMENT_BYTES = 4 * 1024 * 1024
EXPECTED_INVALID = {
    "release-artifact-binding.json": "source_sha256 does not bind",
    "workspace-cycle.json": "dependency cycle",
    "workspace-dirty-qualification.json": "dirty component is not qualifiable",
    "workspace-empty-components.json": "should be non-empty",
    "workspace-insecure-canonical-url.json": "does not match '^https://'",
    "workspace-mutable-ref.json": "mutable ref is not qualifiable",
    "workspace-native-diamond-conflict.json": "native provider conflict",
}


class ValidationFailure(ValueError):
    pass


def load_json(path: Path) -> Any:
    if path.stat().st_size > MAX_DOCUMENT_BYTES:
        raise ValidationFailure(f"document exceeds {MAX_DOCUMENT_BYTES} bytes")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValidationFailure(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle, object_pairs_hook=reject_duplicates)


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def validators() -> dict[str, Draft202012Validator]:
    result = {}
    for identity, path in SCHEMAS.items():
        schema = load_json(path)
        Draft202012Validator.check_schema(schema)
        result[identity] = Draft202012Validator(
            schema, format_checker=FormatChecker()
        )
    return result


def sorted_unique(values: list[str], label: str, errors: list[str]) -> None:
    if values != sorted(set(values)):
        errors.append(f"{label} must be sorted and unique")


def graph_errors(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    components = document["components"]
    dependencies = document["dependencies"]
    by_instance: dict[str, dict[str, Any]] = {}
    for index, component in enumerate(components):
        instance = component["instance_id"]
        if instance in by_instance:
            errors.append(f"duplicate component instance_id: {instance}")
        by_instance[instance] = component
        sorted_unique(component["features"], f"components[{index}].features", errors)
        sorted_unique(
            component["required_tests"],
            f"components[{index}].required_tests",
            errors,
        )
        spdx = [item["spdx"] for item in component["licenses"]]
        sorted_unique(spdx, f"components[{index}].licenses SPDX identifiers", errors)
        notice_paths = [item["path"] for item in component["notices"]]
        sorted_unique(notice_paths, f"components[{index}].notice paths", errors)
        parsed = urlsplit(component["canonical_url"])
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.hostname != parsed.hostname.lower()
        ):
            errors.append(
                f"components[{index}].canonical_url is not a canonical HTTPS URL"
            )
        if (
            component["publication_disposition"] == "publish"
            and component["visibility"] != "public"
        ):
            errors.append(
                f"components[{index}] publish disposition requires public visibility"
            )

    seen_edges: set[tuple[str, str, str, str]] = set()
    adjacency: dict[str, list[str]] = {instance: [] for instance in by_instance}
    process_instances: dict[str, set[str]] = {}
    for index, edge in enumerate(dependencies):
        source, target = edge["from"], edge["to"]
        if source not in by_instance:
            errors.append(f"dependencies[{index}] unknown from instance: {source}")
        if target not in by_instance:
            errors.append(f"dependencies[{index}] unknown to instance: {target}")
        key = (source, target, edge["consumption_mode"], edge["runtime_process"])
        if key in seen_edges:
            errors.append(f"duplicate dependency edge: {key}")
        seen_edges.add(key)
        sorted_unique(
            edge["required_tests"], f"dependencies[{index}].required_tests", errors
        )
        if source in by_instance and target in by_instance:
            adjacency[source].append(target)
            process_instances.setdefault(edge["runtime_process"], set()).update(
                (source, target)
            )
            target_component = by_instance[target]
            if edge["required_api_version"] != target_component["api_version"]:
                errors.append(
                    f"dependencies[{index}] required_api_version does not match {target}"
                )
            if edge["required_abi_version"] != target_component["abi_version"]:
                errors.append(
                    f"dependencies[{index}] required_abi_version does not match {target}"
                )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(instance: str, trail: list[str]) -> None:
        if instance in visiting:
            start = trail.index(instance)
            errors.append("dependency cycle: " + " -> ".join(trail[start:]))
            return
        if instance in visited:
            return
        visiting.add(instance)
        for target in adjacency.get(instance, []):
            visit(target, trail + [target])
        visiting.remove(instance)
        visited.add(instance)

    for instance in sorted(by_instance):
        visit(instance, [instance])

    for process, instances in sorted(process_instances.items()):
        resolutions: dict[str, set[str]] = {}
        for instance in instances:
            component = by_instance[instance]
            if component["runtime_kind"] != "native-provider":
                continue
            commit = component.get("resolved_commit")
            if commit:
                resolutions.setdefault(component["component_id"], set()).add(commit)
        for component_id, commits in sorted(resolutions.items()):
            if len(commits) > 1:
                errors.append(
                    f"native provider conflict in process {process}: "
                    f"{component_id} resolves to {sorted(commits)}"
                )
    return errors


def semantic_errors(
    document: dict[str, Any], *, allow_development_state: bool
) -> list[str]:
    errors = graph_errors(document)
    identity = document["schema"]
    if identity == "kilix.f120.workspace-manifest/v1":
        if not allow_development_state:
            for component in document["components"]:
                name = component["instance_id"]
                if component["resolution_state"] != "resolved":
                    errors.append(f"unresolved component is not qualifiable: {name}")
                if component["dirty"]:
                    errors.append(f"dirty component is not qualifiable: {name}")
                if component["ref_kind"] != "exact-commit":
                    errors.append(f"mutable ref is not qualifiable: {name}")
                if component["requested_ref"] != component["expected_commit"]:
                    errors.append(f"requested_ref/expected_commit mismatch: {name}")
                if component.get("resolved_commit") != component["expected_commit"]:
                    errors.append(f"expected/resolved commit mismatch: {name}")
        return errors

    components = {item["instance_id"]: item for item in document["components"]}
    artifacts: set[str] = set()
    artifact_components: set[str] = set()
    for index, artifact in enumerate(document["artifacts"]):
        artifact_id = artifact["artifact_id"]
        if artifact_id in artifacts:
            errors.append(f"duplicate artifact_id: {artifact_id}")
        artifacts.add(artifact_id)
        instance = artifact["component_instance"]
        if instance not in components:
            errors.append(f"artifacts[{index}] unknown component_instance: {instance}")
            continue
        artifact_components.add(instance)
        component = components[instance]
        bindings = {
            "source_sha256": component["source_sha256"],
            "architecture": component["architecture"],
            "toolchain_digest": component["toolchain"]["digest"],
            "features": component["features"],
        }
        for field, expected in bindings.items():
            if artifact[field] != expected:
                errors.append(f"artifacts[{index}] {field} does not bind component {instance}")
        expected_licenses = hashlib.sha256(
            canonical_bytes(component["licenses"])
        ).hexdigest()
        if artifact["licenses_sha256"] != expected_licenses:
            errors.append(
                f"artifacts[{index}] licenses_sha256 does not bind component {instance}"
            )
        expected_build_key = hashlib.sha256(
            canonical_bytes(
                {
                    "architecture": component["architecture"],
                    "build_options": component["build_options"],
                    "features": component["features"],
                    "source_sha256": component["source_sha256"],
                    "toolchain_digest": component["toolchain"]["digest"],
                }
            )
        ).hexdigest()
        if artifact["build_key_sha256"] != expected_build_key:
            errors.append(
                f"artifacts[{index}] build_key_sha256 does not bind component {instance}"
            )
        sorted_unique(artifact["features"], f"artifacts[{index}].features", errors)
    missing = sorted(set(components) - artifact_components)
    if missing:
        errors.append(f"components without staged artifacts: {missing}")
    return errors


def validate_document(
    path: Path,
    available: dict[str, Draft202012Validator],
    *,
    allow_development_state: bool = False,
) -> list[str]:
    try:
        document = load_json(path)
    except (OSError, json.JSONDecodeError, ValidationFailure) as exc:
        return [f"cannot load JSON: {exc}"]
    if not isinstance(document, dict):
        return ["document must be an object"]
    identity = document.get("schema")
    if identity not in available:
        return [f"unknown schema identity: {identity!r}"]
    schema_errors = sorted(
        available[identity].iter_errors(document),
        key=lambda error: list(error.absolute_path),
    )
    errors = [
        f"schema at /{'/'.join(map(str, error.absolute_path))}: {error.message}"
        for error in schema_errors
    ]
    if not errors:
        errors.extend(
            semantic_errors(document, allow_development_state=allow_development_state)
        )
    return errors


def verify_canonical_and_hashes() -> list[str]:
    errors: list[str] = []
    json_files = sorted(
        [*SCHEMAS.values(), *FIXTURES.glob("*/*.json")],
        key=lambda path: path.relative_to(ROOT).as_posix(),
    )
    for path in json_files:
        if path.read_bytes() != canonical_bytes(load_json(path)):
            errors.append(f"non-canonical JSON: {path.relative_to(ROOT)}")
    files = sorted(
        [
            ROOT / "CONTRACT-REVIEW.md",
            ROOT / "README.md",
            ROOT / "pyproject.toml",
            ROOT / "uv.lock",
            Path(__file__),
            *json_files,
        ],
        key=lambda path: path.relative_to(ROOT).as_posix(),
    )
    expected = "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(ROOT)}\n"
        for path in files
    )
    actual = (ROOT / "SHA256SUMS").read_text(encoding="ascii")
    if actual != expected:
        errors.append("SHA256SUMS does not match canonical schema/fixture bytes")
    return errors


def self_test(available: dict[str, Draft202012Validator]) -> int:
    failures = verify_canonical_and_hashes()
    valid = sorted((FIXTURES / "valid").glob("*.json"))
    development = sorted((FIXTURES / "valid-development").glob("*.json"))
    invalid = sorted((FIXTURES / "invalid").glob("*.json"))
    if not valid or not development or not invalid:
        failures.append("fixture corpus must contain valid, valid-development and invalid cases")
    for path in valid:
        errors = validate_document(path, available)
        if errors:
            failures.append(f"valid fixture rejected: {path.name}: {errors}")
    for path in development:
        errors = validate_document(path, available, allow_development_state=True)
        if errors:
            failures.append(f"development fixture rejected in development mode: {path.name}: {errors}")
        if not validate_document(path, available, allow_development_state=False):
            failures.append(f"development fixture accepted for qualification: {path.name}")
    for path in invalid:
        errors = validate_document(path, available)
        if not errors:
            failures.append(f"invalid fixture accepted: {path.name}")
        expected = EXPECTED_INVALID.get(path.name)
        if expected is None:
            failures.append(f"invalid fixture lacks expected finding: {path.name}")
        elif not any(expected in error for error in errors):
            failures.append(
                f"invalid fixture {path.name} missed expected finding {expected!r}: {errors}"
            )
    if set(EXPECTED_INVALID) != {path.name for path in invalid}:
        failures.append("invalid fixture/expected-finding inventory differs")

    with tempfile.TemporaryDirectory() as temporary:
        duplicate = Path(temporary) / "duplicate.json"
        duplicate.write_text('{"schema":"a","schema":"b"}\n', encoding="utf-8")
        if not any("duplicate JSON key" in error for error in validate_document(duplicate, available)):
            failures.append("duplicate JSON key was not rejected")
        oversized = Path(temporary) / "oversized.json"
        oversized.write_bytes(b" " * (MAX_DOCUMENT_BYTES + 1))
        if not any("exceeds" in error for error in validate_document(oversized, available)):
            failures.append("oversized JSON document was not rejected")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(
        f"PASS: {len(valid)} valid, {len(development)} development-state, "
        f"{len(invalid)} invalid fixtures; schemas and SHA256SUMS verified"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", type=Path)
    parser.add_argument("--allow-development-state", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    available = validators()
    if args.self_test:
        return self_test(available)
    if args.path is None:
        parser.error("PATH is required unless --self-test is used")
    errors = validate_document(
        args.path,
        available,
        allow_development_state=args.allow_development_state,
    )
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(f"valid: {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
