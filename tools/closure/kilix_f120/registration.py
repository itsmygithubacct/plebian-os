"""Strict, local implementation registrations that emit frozen v1 documents."""

from __future__ import annotations

import os
import re
from math import isfinite
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .canonical import (
    canonical_sha256,
    file_sha256,
    load_json,
    require_identifier,
    require_relative_path,
    require_sha256,
    stable_instance_id,
)
from .errors import RegistrationError
from .gitops import canonical_https_url


REGISTRATION_ID = "kilix.f120.registration/v2"
ZERO_COMMIT = "0" * 40
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
ENVIRONMENT_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
BUILD_ENVIRONMENT_NAME_RE = re.compile(r"^F120_INPUT_[A-Z0-9_]+$")
RESERVED_ENVIRONMENT = {
    "GIT_ASKPASS",
    "GIT_CONFIG_GLOBAL",
    "GIT_CONFIG_NOSYSTEM",
    "GIT_CONFIG_SYSTEM",
    "GIT_TERMINAL_PROMPT",
    "HOME",
    "LC_ALL",
    "PATH",
    "SOURCE_DATE_EPOCH",
    "TMPDIR",
    "TZ",
    "BASH_ENV",
    "ENV",
    "PERL5LIB",
    "RUBYOPT",
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
EXECUTABLE_KINDS = {"native", "python-interpreter", "python-script", "script"}
VISIBILITIES = {"public", "private", "local-only"}
PUBLICATION = {"publish", "private", "unpublished", "restricted"}
RUNTIME_KINDS = {"native-provider", "process", "python-distribution", "data"}
REF_KINDS = {"exact-commit", "tag", "branch"}
ARTIFACT_KINDS = {
    "command",
    "header",
    "library",
    "python-package",
    "pkg-config",
    "data",
    "notice",
    "manifest",
}
RESERVED_BUILD_OPTION = "f120_recipe_sha256"


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RegistrationError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise RegistrationError(f"{label} must be an array")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise RegistrationError(f"{label} must be a non-empty string")
    return value


def _keys(value: dict[str, Any], allowed: set[str], required: set[str], label: str) -> None:
    missing = sorted(required - set(value))
    extra = sorted(set(value) - allowed)
    if missing:
        raise RegistrationError(f"{label} missing required fields: {missing}")
    if extra:
        raise RegistrationError(f"{label} has unknown fields: {extra}")


def _sorted_identifiers(value: Any, label: str, *, allow_empty: bool) -> tuple[str, ...]:
    entries = _array(value, label)
    identifiers = tuple(require_identifier(entry, label) for entry in entries)
    if not allow_empty and not identifiers:
        raise RegistrationError(f"{label} must not be empty")
    if list(identifiers) != sorted(set(identifiers)):
        raise RegistrationError(f"{label} must be sorted and unique")
    return identifiers


@dataclass(frozen=True)
class ToolExecutable:
    name: str
    path: Path
    sha256: str
    kind: str
    interpreter: str | None

    def verify(self) -> None:
        if not self.path.is_absolute():
            raise RegistrationError(f"tool {self.name} path must be absolute")
        if self.path.is_symlink() or not self.path.is_file() or not os.access(self.path, os.X_OK):
            raise RegistrationError(f"tool {self.name} is not an executable file")
        if file_sha256(self.path) != self.sha256:
            raise RegistrationError(f"tool {self.name} digest mismatch")
        with self.path.open("rb") as handle:
            prefix = handle.read(4096)
        if self.kind in {"native", "python-interpreter"}:
            if not prefix.startswith(b"\x7fELF"):
                raise RegistrationError(f"tool {self.name} is not a classified ELF executable")
            if self.interpreter is not None:
                raise RegistrationError(f"tool {self.name} native kind names an interpreter")
        else:
            if not prefix.startswith(b"#!") or b"\0" in prefix.split(b"\n", 1)[0]:
                raise RegistrationError(f"tool {self.name} is not a classified script")
            if self.interpreter is None:
                raise RegistrationError(f"tool {self.name} script kind lacks an interpreter")


@dataclass(frozen=True)
class Toolchain:
    name: str
    version: str
    executables: tuple[ToolExecutable, ...]

    @property
    def digest(self) -> str:
        return canonical_sha256(
            {
                "executables": [
                    {
                        "interpreter": item.interpreter,
                        "kind": item.kind,
                        "name": item.name,
                        "sha256": item.sha256,
                    }
                    for item in self.executables
                ],
                "name": self.name,
                "version": self.version,
            }
        )

    def contract_value(self) -> dict[str, str]:
        return {"digest": self.digest, "name": self.name, "version": self.version}

    def executable(self, name: str) -> Path:
        matches = [item.path for item in self.executables if item.name == name]
        if len(matches) != 1:
            raise RegistrationError(f"build recipe names unknown tool: {name}")
        return matches[0]

    def executable_record(self, name: str) -> ToolExecutable:
        matches = [item for item in self.executables if item.name == name]
        if len(matches) != 1:
            raise RegistrationError(f"build recipe names unknown tool: {name}")
        return matches[0]

    def verify(self) -> None:
        if not self.executables:
            raise RegistrationError("resolved build toolchain has no executables")
        for executable in self.executables:
            executable.verify()
        by_name = {item.name: item for item in self.executables}
        for executable in self.executables:
            if executable.kind in {"script", "python-script"}:
                interpreter = by_name.get(executable.interpreter or "")
                if interpreter is None:
                    raise RegistrationError(
                        f"tool {executable.name} names an unregistered interpreter"
                    )
                expected = (
                    "python-interpreter" if executable.kind == "python-script" else "native"
                )
                if interpreter.kind != expected:
                    raise RegistrationError(
                        f"tool {executable.name} interpreter has kind {interpreter.kind}, "
                        f"expected {expected}"
                    )


@dataclass(frozen=True)
class CopySpec:
    source: str
    destination: str
    mode: int


@dataclass(frozen=True)
class ArtifactSpec:
    artifact_id: str
    artifact_kind: str
    path: str


@dataclass(frozen=True)
class BuildRecipe:
    commands: tuple[tuple[str, ...], ...]
    environment: tuple[tuple[str, str], ...]
    copies: tuple[CopySpec, ...]
    artifacts: tuple[ArtifactSpec, ...]

    @property
    def digest(self) -> str:
        return canonical_sha256(
            {
                "artifacts": [
                    {
                        "artifact_id": item.artifact_id,
                        "artifact_kind": item.artifact_kind,
                        "path": item.path,
                    }
                    for item in self.artifacts
                ],
                "commands": [list(command) for command in self.commands],
                "copies": [
                    {
                        "destination": item.destination,
                        "mode": item.mode,
                        "source": item.source,
                    }
                    for item in self.copies
                ],
                "environment": dict(self.environment),
            }
        )


@dataclass(frozen=True)
class ComponentRegistration:
    instance_id: str
    component_id: str
    relative_path: str
    canonical_url: str
    visibility: str
    expected_commit: str
    ref_kind: str
    requested_ref: str
    component_version: str
    api_version: str
    abi_version: str
    architecture: str
    runtime_kind: str
    toolchain: Toolchain
    build_options: dict[str, str | int | float | bool]
    features: tuple[str, ...]
    licenses: tuple[dict[str, str], ...]
    notices: tuple[dict[str, str], ...]
    publication_disposition: str
    required_tests: tuple[str, ...]
    build: BuildRecipe | None

    @property
    def effective_build_options(self) -> dict[str, str | int | float | bool]:
        result = dict(self.build_options)
        if self.build is not None:
            result[RESERVED_BUILD_OPTION] = self.build.digest
        return result


@dataclass(frozen=True)
class Registration:
    workspace_root: Path
    components: tuple[ComponentRegistration, ...]
    dependencies: tuple[dict[str, Any], ...]

    def component(self, instance_id: str) -> ComponentRegistration:
        matches = [item for item in self.components if item.instance_id == instance_id]
        if len(matches) != 1:
            raise RegistrationError(f"unknown component instance: {instance_id}")
        return matches[0]


def _parse_toolchain(value: Any, label: str) -> Toolchain:
    document = _object(value, label)
    _keys(document, {"name", "version", "executables"}, {"name", "version", "executables"}, label)
    executables: list[ToolExecutable] = []
    for index, raw in enumerate(_array(document["executables"], f"{label}.executables")):
        item = _object(raw, f"{label}.executables[{index}]")
        _keys(
            item,
            {"interpreter", "kind", "name", "path", "sha256"},
            {"kind", "name", "path", "sha256"},
            f"{label}.executables[{index}]",
        )
        kind = _string(item["kind"], f"{label}.executables[{index}].kind")
        if kind not in EXECUTABLE_KINDS:
            raise RegistrationError(f"{label}.executables[{index}] has invalid kind")
        interpreter = item.get("interpreter")
        if interpreter is not None:
            interpreter = require_identifier(
                interpreter, f"{label}.executables[{index}].interpreter"
            )
        executables.append(
            ToolExecutable(
                name=require_identifier(item["name"], f"{label}.executables[{index}].name"),
                path=Path(_string(item["path"], f"{label}.executables[{index}].path")),
                sha256=require_sha256(item["sha256"], f"{label}.executables[{index}].sha256"),
                kind=kind,
                interpreter=interpreter,
            )
        )
    if [item.name for item in executables] != sorted({item.name for item in executables}):
        raise RegistrationError(f"{label}.executables must be sorted by unique name")
    return Toolchain(
        name=require_identifier(document["name"], f"{label}.name"),
        version=_string(document["version"], f"{label}.version"),
        executables=tuple(executables),
    )


def _parse_build(value: Any, label: str) -> BuildRecipe:
    document = _object(value, label)
    allowed = {"commands", "environment", "copies", "artifacts"}
    _keys(document, allowed, allowed, label)
    commands: list[tuple[str, ...]] = []
    for index, raw in enumerate(_array(document["commands"], f"{label}.commands")):
        command = tuple(_string(item, f"{label}.commands[{index}]") for item in _array(raw, f"{label}.commands[{index}]"))
        if not command:
            raise RegistrationError(f"{label}.commands[{index}] must not be empty")
        commands.append(command)
    if not commands:
        raise RegistrationError(f"{label}.commands must not be empty")

    environment_document = _object(document["environment"], f"{label}.environment")
    environment: list[tuple[str, str]] = []
    for name, raw_value in sorted(environment_document.items()):
        if not ENVIRONMENT_NAME_RE.fullmatch(name):
            raise RegistrationError(f"{label}.environment has invalid name: {name}")
        if (
            name in RESERVED_ENVIRONMENT
            or name.startswith(RESERVED_ENVIRONMENT_PREFIXES)
            or not BUILD_ENVIRONMENT_NAME_RE.fullmatch(name)
        ):
            raise RegistrationError(
                f"{label}.environment uses unsupported or reserved name: {name}"
            )
        environment.append((name, _string(raw_value, f"{label}.environment.{name}")))

    copies: list[CopySpec] = []
    for index, raw in enumerate(_array(document["copies"], f"{label}.copies")):
        item = _object(raw, f"{label}.copies[{index}]")
        _keys(item, {"source", "destination", "mode"}, {"source", "destination", "mode"}, f"{label}.copies[{index}]")
        mode_value = item["mode"]
        if not isinstance(mode_value, int) or isinstance(mode_value, bool) or mode_value < 0 or mode_value > 0o777:
            raise RegistrationError(f"{label}.copies[{index}].mode must be an integer file mode")
        copies.append(
            CopySpec(
                source=require_relative_path(item["source"], f"{label}.copies[{index}].source"),
                destination=require_relative_path(item["destination"], f"{label}.copies[{index}].destination"),
                mode=mode_value,
            )
        )

    artifacts: list[ArtifactSpec] = []
    for index, raw in enumerate(_array(document["artifacts"], f"{label}.artifacts")):
        item = _object(raw, f"{label}.artifacts[{index}]")
        _keys(item, {"artifact_id", "artifact_kind", "path"}, {"artifact_id", "artifact_kind", "path"}, f"{label}.artifacts[{index}]")
        kind = _string(item["artifact_kind"], f"{label}.artifacts[{index}].artifact_kind")
        if kind not in ARTIFACT_KINDS - {"manifest"}:
            raise RegistrationError(f"{label}.artifacts[{index}] has unsupported or reserved artifact kind")
        artifacts.append(
            ArtifactSpec(
                artifact_id=require_identifier(item["artifact_id"], f"{label}.artifacts[{index}].artifact_id"),
                artifact_kind=kind,
                path=require_relative_path(item["path"], f"{label}.artifacts[{index}].path"),
            )
        )
    artifact_ids = [item.artifact_id for item in artifacts]
    artifact_paths = [item.path for item in artifacts]
    if artifact_ids != sorted(set(artifact_ids)):
        raise RegistrationError(f"{label}.artifacts must be sorted by unique artifact_id")
    if len(set(artifact_paths)) != len(artifact_paths):
        raise RegistrationError(f"{label}.artifacts paths must be unique")
    if {item.destination for item in copies} != set(artifact_paths):
        raise RegistrationError(
            f"{label}.copies destinations must exactly match declared artifact paths"
        )
    return BuildRecipe(tuple(commands), tuple(environment), tuple(copies), tuple(artifacts))


def _parse_licenses(value: Any, label: str) -> tuple[dict[str, str], ...]:
    result: list[dict[str, str]] = []
    for index, raw in enumerate(_array(value, label)):
        item = _object(raw, f"{label}[{index}]")
        _keys(item, {"spdx", "text_sha256"}, {"spdx", "text_sha256"}, f"{label}[{index}]")
        result.append(
            {
                "spdx": _string(item["spdx"], f"{label}[{index}].spdx"),
                "text_sha256": require_sha256(item["text_sha256"], f"{label}[{index}].text_sha256"),
            }
        )
    if not result or [item["spdx"] for item in result] != sorted({item["spdx"] for item in result}):
        raise RegistrationError(f"{label} must be non-empty and sorted by unique SPDX identifier")
    return tuple(result)


def _parse_notices(value: Any, label: str) -> tuple[dict[str, str], ...]:
    result: list[dict[str, str]] = []
    for index, raw in enumerate(_array(value, label)):
        item = _object(raw, f"{label}[{index}]")
        _keys(item, {"path", "sha256"}, {"path", "sha256"}, f"{label}[{index}]")
        result.append(
            {
                "path": require_relative_path(item["path"], f"{label}[{index}].path"),
                "sha256": require_sha256(item["sha256"], f"{label}[{index}].sha256"),
            }
        )
    if not result or [item["path"] for item in result] != sorted({item["path"] for item in result}):
        raise RegistrationError(f"{label} must be non-empty and sorted by unique path")
    return tuple(result)


def _parse_component(value: Any, index: int) -> ComponentRegistration:
    label = f"components[{index}]"
    document = _object(value, label)
    required = {
        "component_id",
        "path",
        "canonical_url",
        "visibility",
        "expected_commit",
        "ref_kind",
        "requested_ref",
        "component_version",
        "api_version",
        "abi_version",
        "architecture",
        "runtime_kind",
        "toolchain",
        "build_options",
        "features",
        "licenses",
        "notices",
        "publication_disposition",
        "required_tests",
    }
    allowed = required | {"instance_id", "build"}
    _keys(document, allowed, required, label)
    component_id = require_identifier(document["component_id"], f"{label}.component_id")
    relative_path = require_relative_path(document["path"], f"{label}.path")
    instance_id = document.get("instance_id")
    if instance_id is None:
        instance_id = stable_instance_id(component_id, relative_path)
    else:
        instance_id = require_identifier(instance_id, f"{label}.instance_id")
    expected_commit = _string(document["expected_commit"], f"{label}.expected_commit")
    if not COMMIT_RE.fullmatch(expected_commit):
        raise RegistrationError(f"{label}.expected_commit must be a 40-hex commit or the all-zero unresolved sentinel")
    visibility = _string(document["visibility"], f"{label}.visibility")
    if visibility not in VISIBILITIES:
        raise RegistrationError(f"{label}.visibility is invalid")
    ref_kind = _string(document["ref_kind"], f"{label}.ref_kind")
    if ref_kind not in REF_KINDS:
        raise RegistrationError(f"{label}.ref_kind is invalid")
    runtime_kind = _string(document["runtime_kind"], f"{label}.runtime_kind")
    if runtime_kind not in RUNTIME_KINDS:
        raise RegistrationError(f"{label}.runtime_kind is invalid")
    publication = _string(document["publication_disposition"], f"{label}.publication_disposition")
    if publication not in PUBLICATION:
        raise RegistrationError(f"{label}.publication_disposition is invalid")
    options = _object(document["build_options"], f"{label}.build_options")
    if RESERVED_BUILD_OPTION in options:
        raise RegistrationError(f"{label}.build_options uses reserved field {RESERVED_BUILD_OPTION}")
    for name, option in options.items():
        if not isinstance(name, str) or not isinstance(option, (str, int, float, bool)):
            raise RegistrationError(f"{label}.build_options has an invalid entry")
        if isinstance(option, float) and not isfinite(option):
            raise RegistrationError(f"{label}.build_options has a non-finite number")
    build = _parse_build(document["build"], f"{label}.build") if "build" in document else None
    return ComponentRegistration(
        instance_id=instance_id,
        component_id=component_id,
        relative_path=relative_path,
        canonical_url=canonical_https_url(
            _string(document["canonical_url"], f"{label}.canonical_url")
        ),
        visibility=visibility,
        expected_commit=expected_commit,
        ref_kind=ref_kind,
        requested_ref=_string(document["requested_ref"], f"{label}.requested_ref"),
        component_version=_string(document["component_version"], f"{label}.component_version"),
        api_version=_string(document["api_version"], f"{label}.api_version"),
        abi_version=_string(document["abi_version"], f"{label}.abi_version"),
        architecture=_string(document["architecture"], f"{label}.architecture"),
        runtime_kind=runtime_kind,
        toolchain=_parse_toolchain(document["toolchain"], f"{label}.toolchain"),
        build_options=dict(options),
        features=_sorted_identifiers(document["features"], f"{label}.features", allow_empty=True),
        licenses=_parse_licenses(document["licenses"], f"{label}.licenses"),
        notices=_parse_notices(document["notices"], f"{label}.notices"),
        publication_disposition=publication,
        required_tests=_sorted_identifiers(document["required_tests"], f"{label}.required_tests", allow_empty=False),
        build=build,
    )


def load_registration(path: Path) -> Registration:
    document = _object(load_json(path), "registration")
    _keys(document, {"schema", "workspace_root", "components", "dependencies"}, {"schema", "workspace_root", "components", "dependencies"}, "registration")
    if document["schema"] != REGISTRATION_ID:
        raise RegistrationError(f"unknown registration schema: {document['schema']!r}")
    workspace_root = Path(_string(document["workspace_root"], "workspace_root"))
    if not workspace_root.is_absolute():
        raise RegistrationError("workspace_root must be absolute")
    components = tuple(
        _parse_component(value, index)
        for index, value in enumerate(_array(document["components"], "components"))
    )
    if not components:
        raise RegistrationError("components must not be empty")
    instance_ids = [item.instance_id for item in components]
    if len(set(instance_ids)) != len(instance_ids):
        raise RegistrationError("component instance_id values must be unique")
    dependencies: list[dict[str, Any]] = []
    required_dependency_fields = {
        "from",
        "to",
        "consumption_mode",
        "runtime_process",
        "required_api_version",
        "required_abi_version",
        "required_tests",
    }
    for index, raw in enumerate(_array(document["dependencies"], "dependencies")):
        item = _object(raw, f"dependencies[{index}]")
        _keys(item, required_dependency_fields, required_dependency_fields, f"dependencies[{index}]")
        dependency = {
            "from": require_identifier(item["from"], f"dependencies[{index}].from"),
            "to": require_identifier(item["to"], f"dependencies[{index}].to"),
            "consumption_mode": _string(
                item["consumption_mode"], f"dependencies[{index}].consumption_mode"
            ),
            "runtime_process": require_identifier(
                item["runtime_process"], f"dependencies[{index}].runtime_process"
            ),
            "required_api_version": _string(
                item["required_api_version"],
                f"dependencies[{index}].required_api_version",
            ),
            "required_abi_version": _string(
                item["required_abi_version"],
                f"dependencies[{index}].required_abi_version",
            ),
            "required_tests": list(
                _sorted_identifiers(
                    item["required_tests"],
                    f"dependencies[{index}].required_tests",
                    allow_empty=False,
                )
            ),
        }
        if dependency["consumption_mode"] not in {
            "recursive-git-submodule",
            "nested-source-build",
            "staged-prefix",
            "system-package",
            "runtime-process",
        }:
            raise RegistrationError(
                f"dependencies[{index}].consumption_mode is invalid"
            )
        dependencies.append(dependency)
    if dependencies != sorted(
        dependencies,
        key=lambda item: (
            item["from"],
            item["to"],
            item["consumption_mode"],
            item["runtime_process"],
        ),
    ):
        raise RegistrationError("dependencies must be in canonical edge order")
    return Registration(workspace_root.resolve(), components, tuple(dependencies))
