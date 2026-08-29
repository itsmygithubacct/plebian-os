"""Deterministic build-once cache for exact F120 provider artifacts."""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Collection, Mapping

from .cache import (
    cache_lock,
    cache_root,
    directory_bytes,
    publish_directory,
    quarantine,
    temporary_directory,
)
from .canonical import (
    atomic_write_json,
    canonical_sha256,
    file_sha256,
    load_json,
    require_relative_path,
)
from .errors import BuildError, CacheError, ContractError
from .execution import prepare_launch, run_with_execution_closure
from .gitops import git_environment
from .keys import build_key_sha256
from .registration import (
    RESERVED_STAGED_DEPENDENCIES_OPTION,
    BuildRecipe,
    ComponentRegistration,
)
from .source_cache import CACHED_SOURCE_REF


BUILD_METADATA_SCHEMA = "kilix.f120.build-cache/v1"
TOOL_TOKEN_RE = re.compile(r"^\{tool:([a-z0-9]+(?:[._-][a-z0-9]+)*)\}$")
DEPENDENCY_TOKEN_RE = re.compile(
    r"\{dependency:([a-z0-9]+(?:[._-][a-z0-9]+)*)\}"
)
PLACEHOLDER_RE = re.compile(
    r"\{(?:source|build|prefix|tool:[a-z0-9._-]+|dependency:[a-z0-9._-]+)\}"
)
MAX_ARCHIVE_MEMBERS = 100_000
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024
BUILD_TIMEOUT_SECONDS = 900
REPRODUCIBLE_SOURCE_EPOCH = "0"


@dataclass(frozen=True)
class BuildCacheResult:
    entry: Path
    prefix: Path
    metadata: dict[str, Any]
    hit: bool
    builds: int
    cache_bytes: int


def _binding(component: dict[str, Any], registration: ComponentRegistration) -> dict[str, Any]:
    return {
        "architecture": component["architecture"],
        "build_key_sha256": build_key_sha256(component),
        "build_options": component["build_options"],
        "features": component["features"],
        "schema": BUILD_METADATA_SCHEMA,
        "source_sha256": component["source_sha256"],
        "toolchain_digest": component["toolchain"]["digest"],
    }


def _verify_registration_binding(
    component: dict[str, Any],
    registration: ComponentRegistration,
    dependencies: Mapping[str, BuildCacheResult],
) -> None:
    options = registration.effective_build_options
    dependency_digest = staged_dependencies_sha256(dependencies)
    if dependency_digest is not None:
        options[RESERVED_STAGED_DEPENDENCIES_OPTION] = dependency_digest
    checks = {
        "architecture": registration.architecture,
        "build_options": options,
        "features": list(registration.features),
        "toolchain": registration.toolchain.contract_value(),
    }
    for field, expected in checks.items():
        if component.get(field) != expected:
            raise BuildError(f"workspace component does not bind registration {field}")
    if registration.build is None:
        raise BuildError(f"component has no staged build recipe: {registration.instance_id}")
    registration.toolchain.verify()


def _archive(repository: Path, commit: str, output: Path) -> None:
    with output.open("wb") as handle:
        process = subprocess.Popen(
            [
                "git",
                "-c",
                "credential.helper=",
                "-C",
                str(repository),
                "archive",
                "--format=tar",
                commit,
            ],
            stdout=handle,
            stderr=subprocess.DEVNULL,
            env=git_environment(),
            start_new_session=True,
        )
        try:
            process.wait(timeout=BUILD_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as exc:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise BuildError("git archive exceeded the fixed timeout") from exc
        except BaseException:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise
    if process.returncode:
        raise BuildError(f"git archive failed with exit {process.returncode}")


def _extract_archive(archive: Path, destination: Path) -> None:
    destination.mkdir(mode=0o755)
    seen: set[str] = set()
    total = 0
    with tarfile.open(archive, mode="r:") as bundle:
        members = bundle.getmembers()
        if len(members) > MAX_ARCHIVE_MEMBERS:
            raise BuildError("source archive contains too many members")
        for member in members:
            name = member.name.rstrip("/")
            if not name:
                continue
            normalized = require_relative_path(name, "source archive member")
            if normalized in seen:
                raise BuildError("source archive contains duplicate paths")
            seen.add(normalized)
            pure = PurePosixPath(normalized)
            target = destination.joinpath(*pure.parts)
            if member.isdir():
                target.mkdir(mode=member.mode & 0o777, parents=True, exist_ok=True)
                continue
            if not member.isreg():
                raise BuildError("source archive contains a non-regular member")
            total += member.size
            if total > MAX_ARCHIVE_BYTES:
                raise BuildError("source archive exceeds extraction limit")
            target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            source = bundle.extractfile(member)
            if source is None:
                raise BuildError("source archive member could not be read")
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(member.mode & 0o777)


def _render(
    value: str,
    *,
    source: Path,
    build: Path,
    prefix: Path,
    registration: ComponentRegistration,
    dependencies: Mapping[str, Path],
) -> str:
    fixed = {
        "{source}": str(source),
        "{build}": str(build),
        "{prefix}": str(prefix),
    }

    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        if token in fixed:
            return fixed[token]
        dependency = DEPENDENCY_TOKEN_RE.fullmatch(token)
        if dependency is not None:
            name = dependency.group(1)
            if name not in dependencies:
                raise BuildError(f"build recipe names undeclared dependency: {name}")
            return str(dependencies[name])
        name = token[len("{tool:") : -1]
        return str(registration.toolchain.executable(name))

    rendered = PLACEHOLDER_RE.sub(replace, value)
    if "{" in rendered or "}" in rendered:
        raise BuildError("build recipe contains an unknown placeholder")
    return rendered


def _recipe_values(recipe: BuildRecipe) -> list[str]:
    return [
        *(value for command in recipe.commands for value in command),
        *(value for _, value in recipe.environment),
    ]


def verify_recipe_dependency_surface(
    recipe: BuildRecipe, dependency_instances: Collection[str]
) -> None:
    expected = set(dependency_instances)
    values = _recipe_values(recipe)
    referenced = {
        match.group(1)
        for value in values
        for match in DEPENDENCY_TOKEN_RE.finditer(value)
    }
    if referenced != expected:
        missing = sorted(expected - referenced)
        undeclared = sorted(referenced - expected)
        raise BuildError(
            "build recipe dependency surface differs from staged-prefix edges; "
            f"missing={missing}, undeclared={undeclared}"
        )
    for value in values:
        tokens = list(PLACEHOLDER_RE.finditer(value))
        if "/" in value and not tokens:
            raise BuildError("build recipe contains an unbound path")
        rendered_shape = PLACEHOLDER_RE.sub("BOUND", value)
        if any(part == ".." for part in rendered_shape.split("/")):
            raise BuildError("build recipe contains a parent path segment")
        if re.search(r"(?:^|[=,:]|-[A-Za-z0-9]+)/", rendered_shape):
            raise BuildError("build recipe contains an absolute host path")


def _run_commands(
    recipe: BuildRecipe,
    registration: ComponentRegistration,
    *,
    source: Path,
    build: Path,
    prefix: Path,
    dependencies: Mapping[str, Path],
) -> None:
    verify_recipe_dependency_surface(recipe, set(dependencies))
    tool_directory = build / "toolchain-bin"
    tool_directory.mkdir(mode=0o700)
    for executable in registration.toolchain.executables:
        (tool_directory / executable.name).symlink_to(executable.path)
    environment = {
        "GIT_ASKPASS": "/bin/false",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C.UTF-8",
        "PATH": str(tool_directory),
        "SOURCE_DATE_EPOCH": REPRODUCIBLE_SOURCE_EPOCH,
        "TMPDIR": str(build / "tmp"),
        "TZ": "UTC",
    }
    (build / "tmp").mkdir(mode=0o700, parents=True)
    for name, value in recipe.environment:
        environment[name] = _render(
            value,
            source=source,
            build=build,
            prefix=prefix,
            registration=registration,
            dependencies=dependencies,
        )
    for command in recipe.commands:
        match = TOOL_TOKEN_RE.fullmatch(command[0])
        if match is None:
            raise BuildError("each build command must start with an exact {tool:name}")
        executable = registration.toolchain.executable_record(match.group(1))
        arguments = [
            _render(
                argument,
                source=source,
                build=build,
                prefix=prefix,
                registration=registration,
                dependencies=dependencies,
            )
            for argument in command
        ]
        launch = prepare_launch(
            executable,
            arguments,
            registration.toolchain,
            environment,
            source,
            build / "tmp",
        )
        run_with_execution_closure(
            launch,
            environment=environment,
            cwd=source,
            toolchain=registration.toolchain,
            timeout=BUILD_TIMEOUT_SECONDS,
        )


def _contains_private_path(path: Path, needles: list[bytes]) -> bool:
    overlap = max((len(item) for item in needles), default=1) - 1
    tail = b""
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            data = tail + chunk
            if any(needle and needle in data for needle in needles):
                return True
            tail = data[-overlap:] if overlap else b""
    return False


def _copy_artifacts(recipe: BuildRecipe, source: Path, prefix: Path) -> None:
    prefix.mkdir(mode=0o755)
    source_root = source.resolve()
    for copy in recipe.copies:
        origin = (source / copy.source).resolve()
        try:
            origin.relative_to(source_root)
        except ValueError as exc:
            raise BuildError("artifact source escapes the committed source tree") from exc
        if origin.is_symlink() or not origin.is_file():
            raise BuildError(f"artifact source is not a regular file: {copy.source}")
        destination = prefix.joinpath(*PurePosixPath(copy.destination).parts)
        destination.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        with origin.open("rb") as input_handle, destination.open("xb") as output_handle:
            shutil.copyfileobj(input_handle, output_handle)
        destination.chmod(copy.mode)


def _audit_prefix(
    prefix: Path,
    registration: ComponentRegistration,
    private_paths: list[Path],
) -> list[dict[str, str]]:
    assert registration.build is not None
    declared = {item.path: item for item in registration.build.artifacts}
    observed: dict[str, Path] = {}
    for candidate in prefix.rglob("*"):
        if candidate.is_symlink():
            raise BuildError("staged prefix contains a symbolic link")
        if candidate.is_dir():
            continue
        if not candidate.is_file():
            raise BuildError("staged prefix contains a non-regular file")
        relative = candidate.relative_to(prefix).as_posix()
        observed[relative] = candidate
    if set(observed) != set(declared):
        missing = sorted(set(declared) - set(observed))
        extra = sorted(set(observed) - set(declared))
        raise BuildError(f"staged files differ from declaration; missing={missing}, extra={extra}")
    needles = sorted(
        {str(path.resolve()).encode("utf-8") for path in private_paths if path.is_absolute()},
        key=len,
        reverse=True,
    )
    artifacts: list[dict[str, str]] = []
    for relative, path in sorted(observed.items()):
        if _contains_private_path(path, needles):
            raise BuildError(f"artifact embeds a private build path: {relative}")
        specification = declared[relative]
        artifacts.append(
            {
                "artifact_id": specification.artifact_id,
                "artifact_kind": specification.artifact_kind,
                "artifact_sha256": file_sha256(path),
                "path": relative,
            }
        )
    return artifacts


def _validate_entry(
    entry: Path,
    expected_binding: Mapping[str, Any],
) -> dict[str, Any]:
    if entry.is_symlink() or not entry.is_dir():
        raise CacheError("build cache entry is not a real directory")
    if {item.name for item in entry.iterdir()} != {"metadata.json", "prefix"}:
        raise CacheError("build cache entry contains unexpected files")
    metadata = load_json(entry / "metadata.json")
    if not isinstance(metadata, dict) or set(metadata) != {*expected_binding, "artifacts"}:
        raise CacheError("build cache metadata shape is invalid")
    for field, expected in expected_binding.items():
        if metadata[field] != expected:
            raise CacheError(f"build cache metadata does not bind {field}")
    artifacts = metadata["artifacts"]
    if not isinstance(artifacts, list) or not artifacts:
        raise CacheError("build cache artifacts are missing")
    declared: dict[str, str] = {}
    for artifact in artifacts:
        if not isinstance(artifact, dict) or set(artifact) != {
            "artifact_id",
            "artifact_kind",
            "artifact_sha256",
            "path",
        }:
            raise CacheError("build cache artifact metadata is invalid")
        path = require_relative_path(artifact["path"], "cached artifact path")
        if path in declared:
            raise CacheError("build cache artifact paths are duplicated")
        declared[path] = artifact["artifact_sha256"]
    prefix = entry / "prefix"
    observed: dict[str, str] = {}
    for candidate in prefix.rglob("*"):
        if candidate.is_symlink():
            raise CacheError("build cache prefix contains a symbolic link")
        if candidate.is_dir():
            continue
        if not candidate.is_file():
            raise CacheError("build cache prefix contains a non-regular file")
        observed[candidate.relative_to(prefix).as_posix()] = file_sha256(candidate)
    if observed != declared:
        raise CacheError("build cache artifact bytes failed verification")
    return metadata


def _validated_dependency_metadata(result: BuildCacheResult) -> dict[str, Any]:
    expected_binding = {
        key: value for key, value in result.metadata.items() if key != "artifacts"
    }
    try:
        metadata = _validate_entry(result.entry, expected_binding)
    except (CacheError, ContractError, OSError) as exc:
        raise BuildError("staged dependency cache entry failed verification") from exc
    if metadata != result.metadata:
        raise BuildError("staged dependency metadata changed after selection")
    return metadata


def staged_dependency_records(
    dependencies: Mapping[str, BuildCacheResult],
) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for instance_id, result in sorted(dependencies.items()):
        metadata = _validated_dependency_metadata(result)
        for artifact in metadata["artifacts"]:
            records.append(
                {
                    "artifact_id": artifact["artifact_id"],
                    "artifact_sha256": artifact["artifact_sha256"],
                    "build_key_sha256": metadata["build_key_sha256"],
                    "component_instance": instance_id,
                    "path": artifact["path"],
                }
            )
    return sorted(
        records,
        key=lambda item: (
            item["component_instance"],
            item["build_key_sha256"],
            item["artifact_id"],
            item["path"],
            item["artifact_sha256"],
        ),
    )


def staged_dependencies_sha256(
    dependencies: Mapping[str, BuildCacheResult],
) -> str | None:
    if not dependencies:
        return None
    return canonical_sha256(
        {
            "dependencies": staged_dependency_records(dependencies),
            "schema": "kilix.f120.staged-dependencies/v1",
        }
    )


def _audit_dependency_view(
    view: Path, metadata: Mapping[str, Any]
) -> None:
    expected = {
        artifact["path"]: artifact["artifact_sha256"]
        for artifact in metadata["artifacts"]
    }
    observed: dict[str, str] = {}
    for candidate in view.rglob("*"):
        if candidate.is_symlink():
            raise BuildError("staged dependency view contains a symbolic link")
        if candidate.is_dir():
            if candidate.stat().st_mode & 0o222:
                raise BuildError("staged dependency directory is writable")
            continue
        if not candidate.is_file():
            raise BuildError("staged dependency view contains a non-regular file")
        if candidate.stat().st_mode & 0o222:
            raise BuildError("staged dependency artifact is writable")
        observed[candidate.relative_to(view).as_posix()] = file_sha256(candidate)
    if view.stat().st_mode & 0o222:
        raise BuildError("staged dependency root is writable")
    if observed != expected:
        raise BuildError("staged dependency view differs from its cache metadata")


def _dependency_views(
    work: Path, dependencies: Mapping[str, BuildCacheResult]
) -> dict[str, Path]:
    if not dependencies:
        return {}
    root = work / "dependencies"
    root.mkdir(mode=0o700)
    views: dict[str, Path] = {}
    for instance_id, result in sorted(dependencies.items()):
        metadata = _validated_dependency_metadata(result)
        destination = root / instance_id
        if destination.exists() or destination.is_symlink():
            raise BuildError("staged dependency view path collision")
        shutil.copytree(result.prefix, destination, copy_function=shutil.copy2)
        for candidate in sorted(destination.rglob("*"), reverse=True):
            if candidate.is_symlink():
                raise BuildError("staged dependency cache contains a symbolic link")
            candidate.chmod(candidate.stat().st_mode & 0o555)
        destination.chmod(destination.stat().st_mode & 0o555)
        _audit_dependency_view(destination, metadata)
        views[instance_id] = destination
    return views


def _make_directories_writable(root: Path) -> None:
    if not root.exists():
        return
    for candidate in [root, *root.rglob("*")]:
        if candidate.is_dir() and not candidate.is_symlink():
            candidate.chmod(candidate.stat().st_mode | 0o700)


def _build_entry(
    root: Path,
    component: dict[str, Any],
    registration: ComponentRegistration,
    repository: Path,
    workspace_root: Path,
    expected_binding: dict[str, Any],
    dependencies: Mapping[str, BuildCacheResult],
) -> Path:
    candidate = temporary_directory(root, "builds")
    work = temporary_directory(root, "build-work")
    try:
        archive = work / "source.tar"
        source = work / "source"
        build = work / "build"
        prefix = candidate / "prefix"
        build.mkdir(mode=0o755)
        dependency_views = _dependency_views(work, dependencies)
        _archive(repository, CACHED_SOURCE_REF, archive)
        _extract_archive(archive, source)
        assert registration.build is not None
        _run_commands(
            registration.build,
            registration,
            source=source,
            build=build,
            prefix=prefix,
            dependencies=dependency_views,
        )
        for instance_id, dependency in dependencies.items():
            _audit_dependency_view(
                dependency_views[instance_id],
                _validated_dependency_metadata(dependency),
            )
        registration.toolchain.verify()
        _copy_artifacts(registration.build, source, prefix)
        artifacts = _audit_prefix(
            prefix,
            registration,
            [
                root,
                candidate,
                work,
                source,
                build,
                prefix,
                *dependency_views.values(),
                workspace_root,
                Path.home(),
            ],
        )
        atomic_write_json(
            candidate / "metadata.json", {**expected_binding, "artifacts": artifacts}
        )
        return candidate
    except BaseException:
        shutil.rmtree(candidate, ignore_errors=True)
        raise
    finally:
        _make_directories_writable(work / "dependencies")
        shutil.rmtree(work, ignore_errors=True)


def ensure_build(
    cache: Path,
    component: dict[str, Any],
    registration: ComponentRegistration,
    repository: Path,
    *,
    workspace_root: Path,
    dependencies: Mapping[str, BuildCacheResult] | None = None,
) -> BuildCacheResult:
    staged_dependencies = dependencies or {}
    _verify_registration_binding(component, registration, staged_dependencies)
    assert registration.build is not None
    verify_recipe_dependency_surface(registration.build, set(staged_dependencies))
    root = cache_root(cache)
    binding = _binding(component, registration)
    key = binding["build_key_sha256"]
    entry = root / "builds" / "sha256" / key
    with cache_lock(root, "builds", key):
        if entry.exists() or entry.is_symlink():
            try:
                metadata = _validate_entry(entry, binding)
            except (CacheError, ContractError, OSError):
                quarantine(root, "builds", entry)
            else:
                return BuildCacheResult(
                    entry=entry,
                    prefix=entry / "prefix",
                    metadata=metadata,
                    hit=True,
                    builds=0,
                    cache_bytes=directory_bytes(entry),
                )
        candidate = _build_entry(
            root,
            component,
            registration,
            repository,
            workspace_root,
            binding,
            staged_dependencies,
        )
        try:
            publish_directory(candidate, entry)
        except BaseException:
            shutil.rmtree(candidate, ignore_errors=True)
            raise
        metadata = _validate_entry(entry, binding)
        return BuildCacheResult(
            entry=entry,
            prefix=entry / "prefix",
            metadata=metadata,
            hit=False,
            builds=1,
            cache_bytes=directory_bytes(entry),
        )
