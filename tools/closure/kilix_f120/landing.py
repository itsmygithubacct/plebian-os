"""Fail-closed evidence binding for owner-landed staged-prefix consumers."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from typing import Any, Iterable

from .canonical import (
    MAX_DOCUMENT_BYTES,
    atomic_write_json_new,
    load_json_bytes,
    require_identifier,
    require_sha256,
)
from .errors import RegistrationError
from .registration import Registration, registration_from_document


LANDING_RECEIPT_ID = "kilix.f120.consumer-landing/v1"
LANDING_REPORT_ID = "kilix.f120.consumer-landing-report/v1"
ZERO_SHA256 = "0" * 64
LINKAGE_KINDS = {
    "command-exec",
    "data-interface",
    "dynamic-link",
    "runtime-import",
    "static-link",
}
PRIVATE_API_DISPOSITIONS = {"not-used", "removed"}


def _keys(
    document: dict[str, Any],
    expected: set[str],
    label: str,
) -> None:
    actual = set(document)
    if actual != expected:
        raise RegistrationError(
            f"{label} fields differ; missing={sorted(expected - actual)}, "
            f"unexpected={sorted(actual - expected)}"
        )


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RegistrationError(f"{label} must be an object")
    return value


def _array(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise RegistrationError(f"{label} must be an array")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise RegistrationError(f"{label} must be a non-empty string")
    return value


def _commit(value: object, label: str) -> str:
    text = _string(value, label)
    if len(text) != 40 or any(character not in "0123456789abcdef" for character in text):
        raise RegistrationError(f"{label} must be a lowercase 40-hex commit")
    if text == "0" * 40:
        raise RegistrationError(f"{label} must not be the zero commit")
    return text


def _command(value: object, label: str) -> list[str]:
    command = _array(value, label)
    if not command:
        raise RegistrationError(f"{label} must not be empty")
    result: list[str] = []
    for index, argument in enumerate(command):
        result.append(_string(argument, f"{label}[{index}]"))
    return result


def _captured_json(path: Path, label: str) -> tuple[dict[str, Any], str, tuple[int, int]]:
    if not path.is_absolute():
        raise RegistrationError(f"{label} path must be absolute")
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    except OSError as exc:
        raise RegistrationError(f"{label} cannot be opened without following links") from exc
    with os.fdopen(descriptor, "rb", closefd=True) as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise RegistrationError(f"{label} must be a regular file")
        payload = handle.read(MAX_DOCUMENT_BYTES + 1)
        after = os.fstat(handle.fileno())
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        raise RegistrationError(f"{label} changed while being captured")
    document = load_json_bytes(payload)
    if not isinstance(document, dict):
        raise RegistrationError(f"{label} must be a JSON object")
    return document, hashlib.sha256(payload).hexdigest(), (before.st_dev, before.st_ino)


def _captured_evidence(path: Path, label: str) -> tuple[str, int, tuple[int, int]]:
    if not path.is_absolute():
        raise RegistrationError(f"{label} path must be absolute")
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    except OSError as exc:
        raise RegistrationError(f"{label} cannot be opened without following links") from exc
    digest = hashlib.sha256()
    with os.fdopen(descriptor, "rb", closefd=True) as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise RegistrationError(f"{label} must be a regular file")
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
        after = os.fstat(handle.fileno())
    if not before.st_size:
        raise RegistrationError(f"{label} must not be empty")
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        raise RegistrationError(f"{label} changed while being captured")
    return digest.hexdigest(), before.st_size, (before.st_dev, before.st_ino)


def _evidence_reference(value: object, label: str) -> tuple[str, str]:
    document = _object(value, label)
    _keys(document, {"evidence_id", "sha256"}, label)
    evidence_id = require_identifier(document["evidence_id"], f"{label}.evidence_id")
    digest = require_sha256(document["sha256"], f"{label}.sha256")
    if digest == ZERO_SHA256:
        raise RegistrationError(f"{label}.sha256 must not be the zero digest")
    return evidence_id, digest


def _claim(
    value: object,
    label: str,
    *,
    expected_commit: str,
    extra_field: str,
    allowed_values: set[str],
) -> tuple[dict[str, Any], tuple[str, str]]:
    document = _object(value, label)
    _keys(document, {extra_field, "producing_commit", "evidence"}, label)
    selection = _string(document[extra_field], f"{label}.{extra_field}")
    if selection not in allowed_values:
        raise RegistrationError(f"{label}.{extra_field} is invalid")
    producing_commit = _commit(document["producing_commit"], f"{label}.producing_commit")
    if producing_commit != expected_commit:
        raise RegistrationError(f"{label}.producing_commit differs from consumer commit")
    evidence = _evidence_reference(document["evidence"], f"{label}.evidence")
    return (
        {
            extra_field: selection,
            "producing_commit": producing_commit,
            "evidence_id": evidence[0],
        },
        evidence,
    )


def _execution_claim(
    value: object,
    label: str,
    *,
    expected_commit: str,
    test_id: str | None = None,
) -> tuple[dict[str, Any], tuple[str, str]]:
    document = _object(value, label)
    expected_fields = {"command", "exit_status", "producing_commit", "evidence"}
    if test_id is not None:
        expected_fields.add("test_id")
    _keys(document, expected_fields, label)
    if document["exit_status"] != 0 or isinstance(document["exit_status"], bool):
        raise RegistrationError(f"{label}.exit_status must be integer zero")
    producing_commit = _commit(document["producing_commit"], f"{label}.producing_commit")
    if producing_commit != expected_commit:
        raise RegistrationError(f"{label}.producing_commit differs from consumer commit")
    command = _command(document["command"], f"{label}.command")
    evidence = _evidence_reference(document["evidence"], f"{label}.evidence")
    result: dict[str, Any] = {
        "command_arguments": len(command),
        "evidence_id": evidence[0],
        "exit_status": 0,
        "producing_commit": producing_commit,
    }
    if test_id is not None:
        observed = require_identifier(document["test_id"], f"{label}.test_id")
        if observed != test_id:
            raise RegistrationError(f"{label}.test_id is not in canonical order")
        result["test_id"] = observed
    return result, evidence


def _assembly_owners(
    assembly: dict[str, Any],
    registration: Registration,
    registration_sha256: str,
    required_owners: list[str],
) -> dict[str, str]:
    if assembly.get("schema") != "kilix.f120.registration-assembly-report/v1":
        raise RegistrationError("unknown registration assembly report schema")
    if assembly.get("registration_sha256") != registration_sha256:
        raise RegistrationError("assembly report does not bind the captured registration")
    if assembly.get("required_owners") != sorted(required_owners):
        raise RegistrationError("assembly report required-owner set differs")
    if assembly.get("components") != len(registration.components):
        raise RegistrationError("assembly report component count differs")
    if assembly.get("dependencies") != len(registration.dependencies):
        raise RegistrationError("assembly report dependency count differs")
    staged_count = sum(
        edge["consumption_mode"] == "staged-prefix"
        for edge in registration.dependencies
    )
    if assembly.get("staged_prefix_edges") != staged_count:
        raise RegistrationError("assembly report staged-prefix edge count differs")
    fragments = _array(assembly.get("fragments"), "assembly report fragments")
    if len(fragments) != len(required_owners):
        raise RegistrationError("assembly report fragment population differs")
    owners: dict[str, str] = {}
    seen_fragment_owners: set[str] = set()
    for index, value in enumerate(fragments):
        fragment = _object(value, f"assembly report fragments[{index}]")
        owner = require_identifier(
            fragment.get("owner"), f"assembly report fragments[{index}].owner"
        )
        if owner in seen_fragment_owners or owner not in required_owners:
            raise RegistrationError("assembly report fragment owner set differs")
        seen_fragment_owners.add(owner)
        instances = _array(
            fragment.get("component_instances"),
            f"assembly report fragments[{index}].component_instances",
        )
        if instances != sorted(instances):
            raise RegistrationError("assembly report component instances are not sorted")
        for raw_instance in instances:
            instance = require_identifier(raw_instance, "assembly report component instance")
            if instance in owners:
                raise RegistrationError("assembly report repeats a component owner mapping")
            owners[instance] = owner
    expected_instances = {component.instance_id for component in registration.components}
    if set(owners) != expected_instances or seen_fragment_owners != set(required_owners):
        raise RegistrationError("assembly report component-owner coverage differs")
    return owners


def verify_consumer_landings(
    registration_path: Path,
    assembly_report_path: Path,
    receipts: Iterable[tuple[str, Path]],
    required_owners: Iterable[str],
    evidence_paths: Iterable[tuple[str, Path]],
    *,
    output: Path,
) -> dict[str, Any]:
    """Bind every staged consumer edge to exact owner and retained evidence."""

    required = [require_identifier(owner, "required owner") for owner in required_owners]
    if not required or len(set(required)) != len(required):
        raise RegistrationError("required owners must be a non-empty unique set")
    if not output.is_absolute():
        raise RegistrationError("consumer landing output path must be absolute")

    registration_document, registration_sha256, registration_identity = _captured_json(
        registration_path, "consumer landing registration"
    )
    registration = registration_from_document(registration_document)
    assembly, assembly_sha256, assembly_identity = _captured_json(
        assembly_report_path, "consumer landing assembly report"
    )
    if registration_identity == assembly_identity:
        raise RegistrationError("registration and assembly report inputs must differ")
    component_owners = _assembly_owners(
        assembly, registration, registration_sha256, required
    )

    supplied_receipts = list(receipts)
    receipt_owners = [require_identifier(owner, "receipt owner") for owner, _ in supplied_receipts]
    if len(set(receipt_owners)) != len(receipt_owners):
        raise RegistrationError("consumer landing receipt owners must be unique")
    if set(receipt_owners) != set(required):
        raise RegistrationError(
            "consumer landing receipt set differs from required owner set; "
            f"missing={sorted(set(required) - set(receipt_owners))}, "
            f"unexpected={sorted(set(receipt_owners) - set(required))}"
        )

    components = {component.instance_id: component for component in registration.components}
    expected_edges: dict[tuple[str, str, str], dict[str, Any]] = {}
    for edge in registration.dependencies:
        if edge["consumption_mode"] != "staged-prefix":
            continue
        if edge["from"] not in components or edge["to"] not in components:
            raise RegistrationError("registration staged-prefix edge names an unknown endpoint")
        key = (edge["from"], edge["to"], edge["runtime_process"])
        if key in expected_edges:
            raise RegistrationError("registration repeats a staged-prefix landing edge")
        expected_edges[key] = edge

    references: dict[str, str] = {}
    receipt_reports: list[dict[str, Any]] = []
    observed_edges: set[tuple[str, str, str]] = set()
    structured_identities = {registration_identity, assembly_identity}

    def bind_reference(reference: tuple[str, str]) -> None:
        evidence_id, digest = reference
        previous = references.get(evidence_id)
        if previous is not None and previous != digest:
            raise RegistrationError(f"evidence ID has conflicting digests: {evidence_id}")
        references[evidence_id] = digest

    for owner, path in sorted(supplied_receipts, key=lambda item: item[0]):
        document, receipt_sha256, identity = _captured_json(
            path, f"consumer landing receipt {owner}"
        )
        if identity in structured_identities:
            raise RegistrationError("consumer landing structured input files must be distinct")
        structured_identities.add(identity)
        _keys(
            document,
            {"assembly_report_sha256", "landings", "owner", "registration_sha256", "schema"},
            f"consumer landing receipt {owner}",
        )
        if document["schema"] != LANDING_RECEIPT_ID:
            raise RegistrationError(f"unknown consumer landing receipt schema: {owner}")
        if document["owner"] != owner:
            raise RegistrationError(f"consumer landing receipt owner differs: {owner}")
        if document["registration_sha256"] != registration_sha256:
            raise RegistrationError(f"consumer landing registration digest differs: {owner}")
        if document["assembly_report_sha256"] != assembly_sha256:
            raise RegistrationError(f"consumer landing assembly digest differs: {owner}")

        landing_reports: list[dict[str, Any]] = []
        landings = _array(document["landings"], f"consumer landing receipt {owner}.landings")
        keys_in_receipt: list[tuple[str, str, str]] = []
        for index, raw_landing in enumerate(landings):
            label = f"consumer landing receipt {owner}.landings[{index}]"
            landing = _object(raw_landing, label)
            _keys(
                landing,
                {
                    "consumer_commit",
                    "consumer_instance",
                    "installed_surface_tests",
                    "linkage",
                    "private_api",
                    "provider_commit",
                    "provider_instance",
                    "recipe_token",
                    "rollback",
                    "runtime_process",
                },
                label,
            )
            consumer_id = require_identifier(
                landing["consumer_instance"], f"{label}.consumer_instance"
            )
            provider_id = require_identifier(
                landing["provider_instance"], f"{label}.provider_instance"
            )
            runtime_process = require_identifier(
                landing["runtime_process"], f"{label}.runtime_process"
            )
            key = (consumer_id, provider_id, runtime_process)
            edge = expected_edges.get(key)
            if edge is None:
                raise RegistrationError(
                    f"consumer landing names an unknown staged-prefix edge: {key}"
                )
            if key in observed_edges:
                raise RegistrationError(f"consumer landing repeats a staged-prefix edge: {key}")
            if component_owners[consumer_id] != owner:
                raise RegistrationError(
                    f"consumer landing is filed by the wrong owner: {consumer_id}"
                )
            consumer_commit = _commit(landing["consumer_commit"], f"{label}.consumer_commit")
            provider_commit = _commit(landing["provider_commit"], f"{label}.provider_commit")
            if consumer_commit != components[consumer_id].expected_commit:
                raise RegistrationError(f"consumer landing commit differs: {consumer_id}")
            if provider_commit != components[provider_id].expected_commit:
                raise RegistrationError(f"provider landing commit differs: {provider_id}")
            if landing["recipe_token"] != f"{{dependency:{provider_id}}}":
                raise RegistrationError(f"consumer landing recipe token differs: {key}")

            linkage, linkage_evidence = _claim(
                landing["linkage"],
                f"{label}.linkage",
                expected_commit=consumer_commit,
                extra_field="kind",
                allowed_values=LINKAGE_KINDS,
            )
            private_api, private_evidence = _claim(
                landing["private_api"],
                f"{label}.private_api",
                expected_commit=consumer_commit,
                extra_field="disposition",
                allowed_values=PRIVATE_API_DISPOSITIONS,
            )
            rollback, rollback_evidence = _execution_claim(
                landing["rollback"],
                f"{label}.rollback",
                expected_commit=consumer_commit,
            )
            bind_reference(linkage_evidence)
            bind_reference(private_evidence)
            bind_reference(rollback_evidence)

            raw_tests = _array(
                landing["installed_surface_tests"],
                f"{label}.installed_surface_tests",
            )
            expected_tests = list(edge["required_tests"])
            observed_test_ids = [
                require_identifier(
                    _object(
                        value, f"{label}.installed_surface_tests[{test_index}]"
                    ).get("test_id"),
                    f"{label}.installed_surface_tests[{test_index}].test_id",
                )
                for test_index, value in enumerate(raw_tests)
            ]
            if observed_test_ids != expected_tests:
                raise RegistrationError(f"installed-surface test set differs: {key}")
            test_reports: list[dict[str, Any]] = []
            for test_index, (test_id, raw_test) in enumerate(
                zip(expected_tests, raw_tests, strict=True)
            ):
                test_report, test_evidence = _execution_claim(
                    raw_test,
                    f"{label}.installed_surface_tests[{test_index}]",
                    expected_commit=consumer_commit,
                    test_id=test_id,
                )
                bind_reference(test_evidence)
                test_reports.append(test_report)

            observed_edges.add(key)
            keys_in_receipt.append(key)
            landing_reports.append(
                {
                    "consumer_commit": consumer_commit,
                    "consumer_instance": consumer_id,
                    "installed_surface_tests": test_reports,
                    "linkage": linkage,
                    "private_api": private_api,
                    "provider_commit": provider_commit,
                    "provider_instance": provider_id,
                    "recipe_token": landing["recipe_token"],
                    "rollback": rollback,
                    "runtime_process": runtime_process,
                }
            )
        if keys_in_receipt != sorted(keys_in_receipt):
            raise RegistrationError(f"consumer landing edges are not in canonical order: {owner}")
        receipt_reports.append(
            {
                "landings": landing_reports,
                "owner": owner,
                "sha256": receipt_sha256,
            }
        )

    if observed_edges != set(expected_edges):
        raise RegistrationError(
            "consumer landing edge coverage differs; "
            f"missing={sorted(set(expected_edges) - observed_edges)}"
        )

    supplied_evidence = list(evidence_paths)
    supplied_ids = [
        require_identifier(evidence_id, "evidence input ID")
        for evidence_id, _ in supplied_evidence
    ]
    if len(set(supplied_ids)) != len(supplied_ids):
        raise RegistrationError("consumer landing evidence input IDs must be unique")
    if set(supplied_ids) != set(references):
        raise RegistrationError(
            "consumer landing evidence set differs from referenced set; "
            f"missing={sorted(set(references) - set(supplied_ids))}, "
            f"unexpected={sorted(set(supplied_ids) - set(references))}"
        )
    evidence_reports: list[dict[str, Any]] = []
    evidence_identities: set[tuple[int, int]] = set()
    for evidence_id, path in sorted(supplied_evidence, key=lambda item: item[0]):
        digest, size, identity = _captured_evidence(
            path, f"consumer landing evidence {evidence_id}"
        )
        if identity in structured_identities or identity in evidence_identities:
            raise RegistrationError("consumer landing input files must have distinct identities")
        evidence_identities.add(identity)
        if digest != references[evidence_id]:
            raise RegistrationError(f"consumer landing evidence digest differs: {evidence_id}")
        evidence_reports.append({"bytes": size, "evidence_id": evidence_id, "sha256": digest})

    report = {
        "assembly_report_sha256": assembly_sha256,
        "evidence": evidence_reports,
        "evidence_files": len(evidence_reports),
        "installed_surface_tests": sum(
            len(edge["required_tests"]) for edge in expected_edges.values()
        ),
        "landings": receipt_reports,
        "owners": len(required),
        "registration_sha256": registration_sha256,
        "required_owners": sorted(required),
        "schema": LANDING_REPORT_ID,
        "staged_prefix_edges": len(expected_edges),
    }
    atomic_write_json_new(output, report)
    return report
