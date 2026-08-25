"""Command-line interface for the owned F120 closure path."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .cache import evict_entry
from .canonical import atomic_write_json, canonical_bytes, require_identifier
from .contracts import frozen_validator, validate_path, verify_contract_package
from .errors import ClosureError
from .graph import reverse_dependencies
from .manifest import emit_workspace_manifest
from .registration import load_registration
from .stage import retire_stage, stage_workspace


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


def _print_json(document: object) -> None:
    sys.stdout.buffer.write(canonical_bytes(document))


def _contracts(_: argparse.Namespace) -> int:
    verify_contract_package()
    return frozen_validator().self_test(frozen_validator().validators())


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
    if arguments.report is not None:
        atomic_write_json(arguments.report, document)
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
    stage.add_argument("--local-source", action="append", default=[], metavar="INSTANCE=PATH")
    stage.set_defaults(handler=_stage)

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
