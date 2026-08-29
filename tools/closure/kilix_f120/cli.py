"""Command-line interface for the owned F120 closure path."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .assembly import assemble_registration
from .cache import evict_entry
from .canonical import (
    atomic_write_json,
    atomic_write_json_new,
    canonical_bytes,
    file_sha256,
    require_identifier,
)
from .contracts import frozen_validator, validate_path, verify_contract_package
from .errors import ClosureError
from .graph import reverse_dependencies
from .landing import consumer_landing_templates, verify_consumer_landings
from .manifest import emit_workspace_manifest
from .registration import load_registration
from .stage import retire_stage, stage_workspace
from .stage_matrix import run_stage_matrix


def _local_sources(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        instance, separator, path_value = value.partition("=")
        if not separator:
            raise ClosureError("local source must use INSTANCE=/absolute/path")
        instance = require_identifier(instance, "local source instance")
        path = Path(path_value)
        if not path.is_absolute():
            raise ClosureError("local source path must be absolute")
        if instance in result:
            raise ClosureError(f"duplicate local source instance: {instance}")
        result[instance] = path
    return result


def _owner_fragments(values: list[str]) -> list[tuple[str, Path]]:
    result: list[tuple[str, Path]] = []
    owners: set[str] = set()
    for value in values:
        owner, separator, path_value = value.partition("=")
        if not separator:
            raise ClosureError("owner fragment must use OWNER=/absolute/path")
        owner = require_identifier(owner, "fragment owner")
        path = Path(path_value)
        if not path.is_absolute():
            raise ClosureError("owner fragment path must be absolute")
        if owner in owners:
            raise ClosureError(f"duplicate fragment owner: {owner}")
        owners.add(owner)
        result.append((owner, path))
    return result


def _named_paths(values: list[str], label: str) -> list[tuple[str, Path]]:
    result: list[tuple[str, Path]] = []
    names: set[str] = set()
    for value in values:
        name, separator, path_value = value.partition("=")
        if not separator:
            raise ClosureError(f"{label} must use ID=/absolute/path")
        name = require_identifier(name, f"{label} ID")
        path = Path(path_value)
        if not path.is_absolute():
            raise ClosureError(f"{label} path must be absolute")
        if name in names:
            raise ClosureError(f"duplicate {label} ID: {name}")
        names.add(name)
        result.append((name, path))
    return result


def _print_json(document: object) -> None:
    sys.stdout.buffer.write(canonical_bytes(document))


def _contracts(_: argparse.Namespace) -> int:
    verify_contract_package()
    return frozen_validator().self_test(frozen_validator().validators())


def _assemble(arguments: argparse.Namespace) -> int:
    document = assemble_registration(
        _owner_fragments(arguments.fragment),
        arguments.required_owner,
        workspace_root=arguments.workspace_root,
        output=arguments.output,
        report=arguments.report,
    )
    _print_json(document)
    return 0


def _resolve(arguments: argparse.Namespace) -> int:
    registration = load_registration(arguments.registration)
    document = emit_workspace_manifest(
        registration,
        arguments.output,
        local_sources=_local_sources(arguments.local_source),
        qualify=arguments.qualify,
    )
    _print_json(
        {
            "components": len(document["components"]),
            "qualified": arguments.qualify,
            "schema": "kilix.f120.resolve-report/v1",
        }
    )
    return 0


def _landings(arguments: argparse.Namespace) -> int:
    document = verify_consumer_landings(
        arguments.registration,
        arguments.assembly_report,
        _named_paths(arguments.receipt, "consumer landing receipt"),
        arguments.required_owner,
        _named_paths(arguments.evidence, "consumer landing evidence"),
        output=arguments.output,
    )
    _print_json(document)
    return 0


def _landing_template(arguments: argparse.Namespace) -> int:
    document = consumer_landing_templates(
        arguments.registration,
        arguments.assembly_report,
        arguments.required_owner,
        output=arguments.output,
    )
    _print_json(document)
    return 0


def _validate(arguments: argparse.Namespace) -> int:
    document = validate_path(
        arguments.document,
        allow_development_state=arguments.allow_development_state,
    )
    _print_json(
        {
            "document_schema": document["schema"],
            "schema": "kilix.f120.validation-report/v1",
            "valid": True,
        }
    )
    return 0


def _stage(arguments: argparse.Namespace) -> int:
    registration = load_registration(arguments.registration)
    prefix = arguments.prefix.resolve()
    release_lock = arguments.release_lock.resolve()
    cache = arguments.cache.resolve()
    workspace_root = registration.workspace_root.resolve()
    protected_inputs = {
        arguments.registration.resolve(),
        arguments.workspace_manifest.resolve(),
    }
    reports = [
        item
        for item in (arguments.report, arguments.evidence_report)
        if item is not None
    ]
    if len({item.resolve() for item in reports}) != len(reports):
        raise ClosureError("stage report paths must be distinct")
    for item in reports:
        resolved = item.resolve()
        if resolved == release_lock or resolved in protected_inputs:
            raise ClosureError("stage report path collides with an input or release lock")
        for container, label in (
            (prefix, "staged prefix"),
            (cache, "cache"),
            (workspace_root, "workspace"),
        ):
            try:
                resolved.relative_to(container)
            except ValueError:
                continue
            raise ClosureError(f"stage report path must be outside the {label}")
    if arguments.evidence_report is not None and (
        arguments.evidence_report.exists() or arguments.evidence_report.is_symlink()
    ):
        raise ClosureError("refusing to overwrite an existing stage evidence report")
    workspace = validate_path(arguments.workspace_manifest)
    report = stage_workspace(
        registration,
        workspace,
        cache=arguments.cache,
        destination=arguments.prefix,
        release=arguments.release,
        release_lock=arguments.release_lock,
        local_sources=_local_sources(arguments.local_source),
    )
    document = report.document()
    if arguments.evidence_report is not None:
        try:
            atomic_write_json_new(
                arguments.evidence_report, report.evidence_document()
            )
        except BaseException:
            retire_stage(arguments.prefix, arguments.release_lock)
            raise
    if arguments.report is not None:
        atomic_write_json(arguments.report, document)
    _print_json(document)
    return 0


def _stage_matrix(arguments: argparse.Namespace) -> int:
    for path, label in (
        (arguments.registration, "registration"),
        (arguments.workspace_manifest, "workspace manifest"),
    ):
        if path.is_symlink() or not path.is_file():
            raise ClosureError(f"stage matrix {label} must be a regular non-symlink file")
    registration_before = file_sha256(arguments.registration)
    workspace_before = file_sha256(arguments.workspace_manifest)
    registration = load_registration(arguments.registration)
    workspace = validate_path(arguments.workspace_manifest)
    registration_after = file_sha256(arguments.registration)
    workspace_after = file_sha256(arguments.workspace_manifest)
    if registration_before != registration_after:
        raise ClosureError("stage matrix registration changed while being captured")
    if workspace_before != workspace_after:
        raise ClosureError("stage matrix workspace manifest changed while being captured")
    document = run_stage_matrix(
        registration,
        workspace,
        output=arguments.output,
        release=arguments.release,
        registration_sha256=registration_before,
        workspace_manifest_sha256=workspace_before,
        local_sources=_local_sources(arguments.local_source),
    )
    _print_json(document)
    return 0


def _reverse_dependencies(arguments: argparse.Namespace) -> int:
    document = validate_path(
        arguments.document,
        allow_development_state=arguments.allow_development_state,
    )
    selected = reverse_dependencies(
        document, set(arguments.target), transitive=not arguments.direct
    )
    _print_json(
        {
            "direct_only": arguments.direct,
            "reverse_dependencies": selected,
            "schema": "kilix.f120.reverse-dependencies/v1",
            "targets": sorted(set(arguments.target)),
        }
    )
    return 0


def _evict(arguments: argparse.Namespace) -> int:
    destination = evict_entry(arguments.cache, arguments.namespace, arguments.key)
    _print_json(
        {
            "evicted": destination is not None,
            "key": arguments.key,
            "namespace": arguments.namespace,
            "schema": "kilix.f120.eviction-report/v1",
        }
    )
    return 0


def _retire(arguments: argparse.Namespace) -> int:
    retire_stage(arguments.prefix, arguments.release_lock)
    _print_json(
        {
            "retired": True,
            "schema": "kilix.f120.retire-report/v1",
        }
    )
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="python -m kilix_f120",
        description="Exact F120 workspace closure, cache, and staging",
    )
    commands = result.add_subparsers(dest="command", required=True)

    contracts = commands.add_parser("contracts", help="verify the frozen v1 package")
    contracts.set_defaults(handler=_contracts)

    assemble = commands.add_parser(
        "assemble", help="assemble and preflight exact reviewed owner fragments"
    )
    assemble.add_argument("output", type=Path)
    assemble.add_argument("--workspace-root", required=True, type=Path)
    assemble.add_argument("--report", required=True, type=Path)
    assemble.add_argument(
        "--fragment", required=True, action="append", metavar="OWNER=/ABSOLUTE/PATH"
    )
    assemble.add_argument(
        "--required-owner", required=True, action="append", metavar="OWNER"
    )
    assemble.set_defaults(handler=_assemble)

    landings = commands.add_parser(
        "landings",
        help="bind every staged consumer edge to exact owner landing evidence",
    )
    landings.add_argument("registration", type=Path)
    landings.add_argument("assembly_report", type=Path)
    landings.add_argument("--output", required=True, type=Path)
    landings.add_argument(
        "--required-owner", required=True, action="append", metavar="OWNER"
    )
    landings.add_argument(
        "--receipt", required=True, action="append", metavar="OWNER=/ABSOLUTE/PATH"
    )
    landings.add_argument(
        "--evidence", action="append", default=[], metavar="ID=/ABSOLUTE/PATH"
    )
    landings.set_defaults(handler=_landings)

    landing_template = commands.add_parser(
        "landing-template",
        help="project exact owner receipt populations without claiming evidence",
    )
    landing_template.add_argument("registration", type=Path)
    landing_template.add_argument("assembly_report", type=Path)
    landing_template.add_argument("--output", required=True, type=Path)
    landing_template.add_argument(
        "--required-owner", required=True, action="append", metavar="OWNER"
    )
    landing_template.set_defaults(handler=_landing_template)

    resolve = commands.add_parser("resolve", help="emit an observed workspace manifest")
    resolve.add_argument("registration", type=Path)
    resolve.add_argument("output", type=Path)
    resolve.add_argument("--local-source", action="append", default=[], metavar="INSTANCE=PATH")
    resolve.add_argument("--qualify", action="store_true")
    resolve.set_defaults(handler=_resolve)

    validate = commands.add_parser("validate", help="validate a frozen v1 document")
    validate.add_argument("document", type=Path)
    validate.add_argument("--allow-development-state", action="store_true")
    validate.set_defaults(handler=_validate)

    stage = commands.add_parser("stage", help="fetch, build, and stage a qualified closure")
    stage.add_argument("registration", type=Path)
    stage.add_argument("workspace_manifest", type=Path)
    stage.add_argument("--cache", required=True, type=Path)
    stage.add_argument("--prefix", required=True, type=Path)
    stage.add_argument("--release", required=True)
    stage.add_argument("--release-lock", required=True, type=Path)
    stage.add_argument("--report", type=Path)
    stage.add_argument("--evidence-report", type=Path)
    stage.add_argument("--local-source", action="append", default=[], metavar="INSTANCE=PATH")
    stage.set_defaults(handler=_stage)

    matrix = commands.add_parser(
        "stage-matrix",
        help="prove cold, warm and independent-clean staging as one transaction",
    )
    matrix.add_argument("registration", type=Path)
    matrix.add_argument("workspace_manifest", type=Path)
    matrix.add_argument("--output", required=True, type=Path)
    matrix.add_argument("--release", required=True)
    matrix.add_argument(
        "--local-source", action="append", default=[], metavar="INSTANCE=PATH"
    )
    matrix.set_defaults(handler=_stage_matrix)

    reverse = commands.add_parser(
        "reverse-deps", help="select deterministic reverse dependencies"
    )
    reverse.add_argument("document", type=Path)
    reverse.add_argument("target", nargs="+")
    reverse.add_argument("--direct", action="store_true")
    reverse.add_argument("--allow-development-state", action="store_true")
    reverse.set_defaults(handler=_reverse_dependencies)

    evict = commands.add_parser("evict", help="recoverably evict one exact cache key")
    evict.add_argument("--cache", required=True, type=Path)
    evict.add_argument("--namespace", required=True, choices=("sources", "builds"))
    evict.add_argument("--key", required=True)
    evict.set_defaults(handler=_evict)

    retire = commands.add_parser("retire", help="recoverably retire one staged prefix")
    retire.add_argument("--prefix", required=True, type=Path)
    retire.add_argument("--release-lock", type=Path)
    retire.set_defaults(handler=_retire)
    return result


def main() -> int:
    arguments = parser().parse_args()
    try:
        return int(arguments.handler(arguments))
    except ClosureError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        detail = exc.strerror or "operating system error"
        print(f"error: operation failed: {detail}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("error: interrupted", file=sys.stderr)
        return 130
