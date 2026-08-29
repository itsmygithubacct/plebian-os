#!/usr/bin/env python3
"""Construct an external, digest-pinned trusted-launcher bundle.

This program is a construction aid, not an authority entry point.  The output
becomes trusted only after its recorded bytes are reviewed and accepted outside
the subject tree.  The resulting native launcher performs the closure check
before starting Python.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path


MANIFEST_HEADER = b"KILIX-TRUSTED-CLOSURE-MANIFEST-v1\n"
PROFILE_SCHEMA = "kilix.trusted-launcher.profile/v1"
PROFILE_LIMIT = 256 * 1024
PROFILE_ID = re.compile(r"[a-z0-9][a-z0-9._/-]{0,95}")
PROFILE_NAME = re.compile(r"[a-z][a-z0-9-]{0,63}")
MODULE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")
RESERVED_NAMES = {"sitecustomize.py", "usercustomize.py"}
PINNED_PYTHON_SHA256 = (
    "0dc3a692fa85fcdb7f1a5877d2adf179809ac417a07ffde2373c832863800a15"
)


class BundleError(ValueError):
    """A fail-closed bundle construction error."""


def _exact_object(value: object, fields: set[str], label: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        raise BundleError(f"{label} must contain exactly {sorted(fields)}")
    return value


def _bounded_string(value: object, label: str, *, limit: int = 256) -> str:
    if not isinstance(value, str) or not value:
        raise BundleError(f"{label} must be a nonempty string of at most {limit} bytes")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise BundleError(f"{label} is not Unicode scalar text") from exc
    if len(encoded) > limit:
        raise BundleError(f"{label} must be a nonempty string of at most {limit} bytes")
    if any(character in value for character in ("\0", "\n", "\r")):
        raise BundleError(f"{label} contains a control separator")
    return value


def _relative_path(value: object, label: str, *, dot: bool = False) -> str:
    path = _bounded_string(value, label, limit=1024)
    parts = path.split("/")
    if path.startswith("/") or any(part in ("", "..") for part in parts):
        raise BundleError(f"{label} must be a normalized relative path")
    if not dot and path == ".":
        raise BundleError(f"{label} must name a member below its root")
    if any(part == "." for part in parts[1:]):
        raise BundleError(f"{label} must not contain dot segments")
    return path


def _root_path(value: object, label: str, *, roots: set[str], dot: bool = False) -> None:
    item = _exact_object(value, {"path", "root"}, label)
    if item["root"] not in roots:
        raise BundleError(f"{label}.root is not an allowed retained root")
    _relative_path(item["path"], f"{label}.path", dot=dot)


def _argv_item(value: object, label: str) -> None:
    if isinstance(value, str):
        _bounded_string(value, label)
        return
    _root_path(
        value,
        label,
        roots={"dependency", "launcher", "python", "runtime", "subject", "temporary"},
        dot=True,
    )


def _stream_expectation(value: object, label: str) -> None:
    if not isinstance(value, dict) or "mode" not in value:
        raise BundleError(f"{label} must be a stream-expectation object")
    mode = value.get("mode")
    if mode in ("empty", "passthrough"):
        _exact_object(value, {"mode"}, label)
    elif mode == "literal-utf8":
        item = _exact_object(value, {"mode", "value"}, label)
        if not isinstance(item["value"], str):
            raise BundleError(f"{label}.value must be a UTF-8 string of at most 65536 bytes")
        try:
            encoded = item["value"].encode("utf-8")
        except UnicodeEncodeError as exc:
            raise BundleError(f"{label}.value is not Unicode scalar text") from exc
        if len(encoded) > 65536:
            raise BundleError(f"{label}.value must be a UTF-8 string of at most 65536 bytes")
    elif mode == "file":
        item = _exact_object(value, {"mode", "path", "root"}, label)
        _root_path(
            {"root": item["root"], "path": item["path"]},
            label,
            roots={"dependency", "subject"},
        )
    else:
        raise BundleError(f"{label}.mode is unsupported")


def _case(value: object, label: str) -> None:
    item = _exact_object(
        value,
        {"argv", "expected_exit", "forward_arguments", "stderr", "stdout"},
        label,
    )
    argv = item["argv"]
    if not isinstance(argv, list) or len(argv) > 64:
        raise BundleError(f"{label}.argv must be a list of at most 64 items")
    for index, argument in enumerate(argv):
        _argv_item(argument, f"{label}.argv[{index}]")
    if type(item["expected_exit"]) is not int or not 0 <= item["expected_exit"] <= 255:
        raise BundleError(f"{label}.expected_exit must be an exit status from 0 to 255")
    if not isinstance(item["forward_arguments"], bool):
        raise BundleError(f"{label}.forward_arguments must be boolean")
    _stream_expectation(item["stdout"], f"{label}.stdout")
    _stream_expectation(item["stderr"], f"{label}.stderr")


def _python_paths(value: object, label: str) -> None:
    if not isinstance(value, list) or not value or len(value) > 16:
        raise BundleError(f"{label} must contain 1 to 16 retained-root paths")
    encoded: set[str] = set()
    for index, entry in enumerate(value):
        _root_path(
            entry,
            f"{label}[{index}]",
            roots={"dependency", "subject"},
            dot=True,
        )
        key = json.dumps(entry, sort_keys=True, separators=(",", ":"))
        if key in encoded:
            raise BundleError(f"{label} contains a duplicate path")
        encoded.add(key)


def _child(value: object, label: str) -> tuple[str, int]:
    if not isinstance(value, dict):
        raise BundleError(f"{label} must be an object")
    kind = value.get("kind")
    common = {"id", "kind", "python_paths"}
    if kind == "python-script":
        item = _exact_object(value, common | {"cases", "script"}, label)
        _root_path(item["script"], f"{label}.script", roots={"dependency", "subject"})
        cases = item["cases"]
    elif kind == "python-module":
        item = _exact_object(value, common | {"cases", "module"}, label)
        module = _bounded_string(item["module"], f"{label}.module")
        if MODULE_NAME.fullmatch(module) is None:
            raise BundleError(f"{label}.module is not a dotted Python name")
        cases = item["cases"]
    elif kind == "python-unittest":
        item = _exact_object(value, common | {"start", "top"}, label)
        _root_path(item["start"], f"{label}.start", roots={"subject"})
        _root_path(item["top"], f"{label}.top", roots={"subject"}, dot=True)
        cases = []
    else:
        raise BundleError(f"{label}.kind is unsupported")
    child_id = _bounded_string(item["id"], f"{label}.id", limit=64)
    if PROFILE_NAME.fullmatch(child_id) is None:
        raise BundleError(f"{label}.id is not a canonical child name")
    _python_paths(item["python_paths"], f"{label}.python_paths")
    if kind != "python-unittest":
        if not isinstance(cases, list) or not cases or len(cases) > 64:
            raise BundleError(f"{label}.cases must contain 1 to 64 cases")
        for index, case in enumerate(cases):
            _case(case, f"{label}.cases[{index}]")
    return child_id, sum(
        int(case["forward_arguments"])
        for case in cases
        if isinstance(case, dict)
    )


def load_profile(path: Path) -> tuple[dict[str, object], bytes]:
    """Load a duplicate-free, canonical, closed trusted-launcher profile."""

    source = _safe_path(path, "profile", directory=False)
    raw = source.read_bytes()
    if not raw or len(raw) > PROFILE_LIMIT:
        raise BundleError("profile is empty or exceeds the 256 KiB limit")

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise BundleError("profile contains a duplicate JSON member")
            result[key] = value
        return result

    def constant(value: str) -> object:
        raise BundleError(f"profile contains forbidden JSON constant {value}")

    try:
        profile = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise BundleError("profile is not duplicate-free UTF-8 JSON") from exc
    canonical = json.dumps(
        profile, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8") + b"\n"
    if raw != canonical:
        raise BundleError("profile is not canonical JSON plus one LF")
    item = _exact_object(
        profile,
        {"commands", "launcher_name", "profile_id", "schema", "subject_hash_manifests"},
        "profile",
    )
    if item["schema"] != PROFILE_SCHEMA:
        raise BundleError("profile schema is unsupported")
    profile_id = _bounded_string(item["profile_id"], "profile.profile_id", limit=96)
    if PROFILE_ID.fullmatch(profile_id) is None:
        raise BundleError("profile.profile_id is not canonical")
    launcher_name = _bounded_string(item["launcher_name"], "profile.launcher_name", limit=64)
    if PROFILE_NAME.fullmatch(launcher_name) is None:
        raise BundleError("profile.launcher_name is not canonical")
    manifests = item["subject_hash_manifests"]
    if not isinstance(manifests, list) or len(manifests) > 16:
        raise BundleError("profile.subject_hash_manifests must be a list of at most 16 items")
    manifest_paths: set[str] = set()
    for index, manifest in enumerate(manifests):
        entry = _exact_object(manifest, {"members", "path"}, f"profile.subject_hash_manifests[{index}]")
        manifest_path = _relative_path(entry["path"], f"profile.subject_hash_manifests[{index}].path")
        members = entry["members"]
        if manifest_path in manifest_paths or not isinstance(members, list) or not members:
            raise BundleError("profile subject hash manifests must be unique and nonempty")
        manifest_paths.add(manifest_path)
        observed: set[str] = set()
        for member_index, member in enumerate(members):
            name = _relative_path(member, f"profile.subject_hash_manifests[{index}].members[{member_index}]")
            if name in observed:
                raise BundleError("profile subject hash manifest contains duplicate members")
            observed.add(name)
    commands = item["commands"]
    if not isinstance(commands, list) or not commands or len(commands) > 16:
        raise BundleError("profile.commands must contain 1 to 16 commands")
    command_names: set[str] = set()
    for command_index, command in enumerate(commands):
        entry = _exact_object(
            command,
            {"argument_mode", "children", "name"},
            f"profile.commands[{command_index}]",
        )
        name = _bounded_string(entry["name"], f"profile.commands[{command_index}].name", limit=64)
        if PROFILE_NAME.fullmatch(name) is None or name in command_names:
            raise BundleError("profile command names must be canonical and unique")
        command_names.add(name)
        if entry["argument_mode"] not in ("forbidden", "required"):
            raise BundleError("profile command argument_mode must be forbidden or required")
        children = entry["children"]
        if not isinstance(children, list) or not children or len(children) > 64:
            raise BundleError("profile command children must contain 1 to 64 entries")
        child_ids: set[str] = set()
        forward_count = 0
        for child_index, child in enumerate(children):
            child_id, child_forward_count = _child(
                child, f"profile.commands[{command_index}].children[{child_index}]"
            )
            if child_id in child_ids:
                raise BundleError("profile command child IDs must be unique")
            child_ids.add(child_id)
            forward_count += child_forward_count
        required = entry["argument_mode"] == "required"
        if forward_count != int(required):
            raise BundleError("profile command forwarding does not match argument_mode")
    return item, raw


def _declared_input(
    declaration: dict[str, object],
    roots: dict[str, Path],
    label: str,
    *,
    directory: bool | None = None,
) -> None:
    root_name = declaration["root"]
    if root_name not in roots:
        return
    candidate = roots[root_name] / str(declaration["path"])
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise BundleError(f"{label} is absent from its declared closure") from exc
    if not _within(resolved, roots[root_name]) and resolved != roots[root_name]:
        raise BundleError(f"{label} escapes its declared closure")
    if candidate.is_symlink():
        raise BundleError(f"{label} must not be a symlink")
    if directory is True and not resolved.is_dir():
        raise BundleError(f"{label} is not a directory")
    if directory is False and not resolved.is_file():
        raise BundleError(f"{label} is not a regular file")


def validate_profile_inputs(
    profile: dict[str, object], subject: Path, dependency: Path
) -> None:
    """Require every subject/dependency profile path to exist before freezing."""

    roots = {"dependency": dependency, "subject": subject}
    for command in profile["commands"]:
        for child in command["children"]:
            for index, python_path in enumerate(child["python_paths"]):
                _declared_input(python_path, roots, f"child Python path {index}", directory=True)
            if child["kind"] == "python-script":
                _declared_input(child["script"], roots, "child script", directory=False)
            elif child["kind"] == "python-unittest":
                _declared_input(child["start"], roots, "unittest start", directory=True)
                _declared_input(child["top"], roots, "unittest top", directory=True)
            for case in child.get("cases", []):
                for index, argument in enumerate(case["argv"]):
                    if isinstance(argument, dict):
                        _declared_input(argument, roots, f"child argv {index}")
                for stream_name in ("stdout", "stderr"):
                    stream = case[stream_name]
                    if stream["mode"] == "file":
                        _declared_input(stream, roots, f"child {stream_name}", directory=False)
    for declaration in profile["subject_hash_manifests"]:
        _declared_input(
            {"root": "subject", "path": declaration["path"]},
            roots,
            "subject hash manifest",
            directory=False,
        )
        for member in declaration["members"]:
            _declared_input(
                {"root": "subject", "path": member},
                roots,
                "subject hash manifest member",
                directory=False,
            )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _safe_path(path: Path, label: str, *, directory: bool) -> Path:
    if not path.is_absolute():
        raise BundleError(f"{label} must be absolute")
    if path.is_symlink():
        raise BundleError(f"{label} must not be a symlink")
    resolved = path.resolve(strict=True)
    if directory and not resolved.is_dir():
        raise BundleError(f"{label} is not a directory")
    if not directory and not resolved.is_file():
        raise BundleError(f"{label} is not a regular file")
    return resolved


def _entry_line(kind: str, mode: int, size: int, digest: str, relative: str) -> bytes:
    if any(character in relative for character in ("\0", "\n", "\r", "\t")):
        raise BundleError("manifest paths must not contain control separators")
    return f"{kind}\t{mode:04o}\t{size}\t{digest}\t{relative}\n".encode("utf-8")


def manifest_bytes(root: Path, *, reject_reserved: bool) -> bytes:
    """Return the complete canonical regular-file/directory closure."""

    root_stat = root.stat(follow_symlinks=False)
    root_device = root_stat.st_dev
    identities: set[tuple[int, int]] = {(root_stat.st_dev, root_stat.st_ino)}
    lines: list[bytes] = []

    def walk(directory: Path, prefix: str) -> None:
        for name in sorted(os.listdir(directory)):
            if name in {".", ".."}:
                raise BundleError("invalid directory member")
            if reject_reserved and (name in RESERVED_NAMES or name.endswith(".pth")):
                raise BundleError(f"reserved Python startup member: {prefix}{name}")
            candidate = directory / name
            information = candidate.stat(follow_symlinks=False)
            relative = f"{prefix}{name}"
            if information.st_dev != root_device:
                raise BundleError(f"cross-device manifest member: {relative}")
            identity = (information.st_dev, information.st_ino)
            if identity in identities:
                raise BundleError(f"aliased manifest member: {relative}")
            identities.add(identity)
            mode = stat.S_IMODE(information.st_mode)
            if stat.S_ISDIR(information.st_mode):
                lines.append(_entry_line("d", mode, 0, "-", relative))
                walk(candidate, relative + "/")
            elif stat.S_ISREG(information.st_mode):
                lines.append(
                    _entry_line("f", mode, information.st_size, _sha256(candidate), relative)
                )
            else:
                raise BundleError(f"non-regular manifest member: {relative}")

    walk(root, "")
    return MANIFEST_HEADER + b"".join(lines)


def _make_read_only(root: Path) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        information = path.stat(follow_symlinks=False)
        if stat.S_ISDIR(information.st_mode):
            path.chmod(stat.S_IMODE(information.st_mode) & ~0o222)
        elif stat.S_ISREG(information.st_mode):
            path.chmod(stat.S_IMODE(information.st_mode) & ~0o222)
        else:
            raise BundleError(f"bundle contains a non-regular member: {path}")
    root.chmod(stat.S_IMODE(root.stat().st_mode) & ~0o222)


def _copy_runtime(interpreter: Path, destination: Path) -> Path:
    if interpreter.parent.name != "bin":
        raise BundleError("interpreter must live directly beneath a runtime bin directory")
    runtime = interpreter.parent.parent
    match = re.fullmatch(r"python(\d+)\.(\d+)", interpreter.name)
    if match is None:
        raise BundleError("interpreter basename must be pythonMAJOR.MINOR")
    version = f"python{match.group(1)}.{match.group(2)}"
    stdlib = runtime / "lib" / version
    library = runtime / "lib" / f"lib{version}.so.1.0"
    for candidate, label in ((stdlib, "runtime stdlib"), (library, "runtime library")):
        if candidate.is_symlink() or not candidate.exists():
            raise BundleError(f"{label} is absent or symlinked")
    (destination / "bin").mkdir(parents=True, mode=0o700)
    (destination / "lib").mkdir(mode=0o700)
    shutil.copy2(interpreter, destination / "bin" / interpreter.name, follow_symlinks=False)
    shutil.copy2(library, destination / "lib" / library.name, follow_symlinks=False)
    shutil.copytree(stdlib, destination / "lib" / version, symlinks=False)
    return destination / "bin" / interpreter.name


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _bundle_hashes(root: Path) -> bytes:
    lines: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "BUNDLE-SHA256SUMS":
            lines.append(f"{_sha256(path)}  {path.relative_to(root).as_posix()}\n")
    return "".join(lines).encode("utf-8")


def build(arguments: argparse.Namespace) -> None:
    subject = _safe_path(arguments.subject, "subject", directory=True)
    source_root = Path(__file__).resolve().parent
    bootstrap_source = _safe_path(source_root / "bootstrap.py", "bootstrap", directory=False)
    launcher_source = _safe_path(source_root / "launcher.c", "launcher source", directory=False)
    profile_source = _safe_path(arguments.profile, "profile", directory=False)
    profile_value, profile_bytes = load_profile(profile_source)
    interpreter = _safe_path(arguments.interpreter, "interpreter", directory=False)
    if _sha256(interpreter) != PINNED_PYTHON_SHA256:
        raise BundleError("interpreter does not match the release-pinned Python bytes")
    dependency_source = _safe_path(
        arguments.dependency_root, "dependency root", directory=True
    )
    validate_profile_inputs(profile_value, subject, dependency_source)
    compiler = _safe_path(arguments.cc, "C compiler", directory=False)
    output = arguments.output
    if not output.is_absolute():
        raise BundleError("output must be absolute")
    output_parent = output.parent.resolve(strict=True)
    output_resolved = output_parent / output.name
    if output_resolved.exists() or output_resolved.is_symlink():
        raise BundleError("output must not already exist")
    for protected in (subject, source_root, interpreter.parent.parent, dependency_source):
        if _within(output_resolved, protected) or _within(protected, output_resolved):
            raise BundleError("output must be disjoint from subject, runtime and dependencies")

    output.mkdir(mode=0o700)
    try:
        runtime_root = output / "runtime"
        copied_interpreter = _copy_runtime(interpreter, runtime_root)
        dependency_root = output / "dependencies"
        shutil.copytree(dependency_source, dependency_root, symlinks=False)
        shutil.copy2(bootstrap_source, output / "bootstrap.py", follow_symlinks=False)
        (output / "launch-profile.json").write_bytes(profile_bytes)

        # Normalize external authority material before freezing its metadata.
        _make_read_only(runtime_root)
        _make_read_only(dependency_root)
        (output / "bootstrap.py").chmod(0o444)
        (output / "launch-profile.json").chmod(0o444)

        manifests = {
            "subject.manifest": manifest_bytes(subject, reject_reserved=True),
            "runtime.manifest": manifest_bytes(runtime_root, reject_reserved=False),
            "dependency.manifest": manifest_bytes(dependency_root, reject_reserved=False),
        }
        for name, content in manifests.items():
            (output / name).write_bytes(content)

        values = {
            "TL_BOOTSTRAP_SHA256": _sha256(output / "bootstrap.py"),
            "TL_DEPENDENCY_MANIFEST_SHA256": hashlib.sha256(
                manifests["dependency.manifest"]
            ).hexdigest(),
            "TL_PROFILE_ID": profile_value["profile_id"],
            "TL_PROFILE_SHA256": hashlib.sha256(profile_bytes).hexdigest(),
            "TL_PYTHON_BASENAME": copied_interpreter.name,
            "TL_PYTHON_SHA256": _sha256(copied_interpreter),
            "TL_RUNTIME_MANIFEST_SHA256": hashlib.sha256(
                manifests["runtime.manifest"]
            ).hexdigest(),
            "TL_SUBJECT_MANIFEST_SHA256": hashlib.sha256(
                manifests["subject.manifest"]
            ).hexdigest(),
        }
        command_rows = []
        for command_value in profile_value["commands"]:
            terminal_bytes = (
                "".join(f"{child['id']}\n" for child in command_value["children"])
            ).encode("utf-8")
            command_rows.append(
                "    {"
                + json.dumps(command_value["name"])
                + ", "
                + json.dumps(hashlib.sha256(terminal_bytes).hexdigest())
                + ", "
                + ("TL_ARGUMENTS_REQUIRED" if command_value["argument_mode"] == "required" else "TL_ARGUMENTS_FORBIDDEN")
                + "},\n"
            )
        profile = output / "profile.h"
        profile.write_text(
            "#ifndef KILIX_TRUSTED_LAUNCHER_PROFILE_H\n"
            "#define KILIX_TRUSTED_LAUNCHER_PROFILE_H\n"
            + "".join(
                f'#define {name} "{value}"\n' for name, value in sorted(values.items())
            )
            + f"#define TL_COMMAND_COUNT {len(command_rows)}U\n"
            + "static const struct tl_profile_command TL_COMMANDS[TL_COMMAND_COUNT] = {\n"
            + "".join(command_rows)
            + "};\n"
            + "#endif\n",
            encoding="utf-8",
        )
        shutil.copy2(launcher_source, output / "launcher.c", follow_symlinks=False)
        launcher_name = profile_value["launcher_name"]
        command = [
            str(compiler),
            "-std=c11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-fPIE",
            "-pie",
            "-o",
            str(output / launcher_name),
            str(output / "launcher.c"),
        ]
        environment = {
            "LC_ALL": "C.UTF-8",
            "PATH": "/usr/bin:/bin",
            "SOURCE_DATE_EPOCH": "0",
            "TZ": "UTC",
        }
        subprocess.run(command, check=True, cwd=output, env=environment)
        (output / launcher_name).chmod(0o555)

        compiler_version = subprocess.run(
            [str(compiler), "--version"],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        ).stdout.splitlines()[0]
        _write_json(
            output / "BUILD-RECORD.json",
            {
                "bootstrap_sha256": values["TL_BOOTSTRAP_SHA256"],
                "compiler": {
                    "path": str(compiler),
                    "sha256": _sha256(compiler),
                    "version": compiler_version,
                },
                "interpreter": {
                    "sha256": values["TL_PYTHON_SHA256"],
                    "version": subprocess.run(
                        [str(interpreter), "-I", "-S", "-B", "-VV"],
                        check=True,
                        capture_output=True,
                        text=True,
                        env=environment,
                        cwd=output_parent,
                    ).stdout.strip(),
                },
                "launcher_name": launcher_name,
                "launcher_sha256": _sha256(output / launcher_name),
                "manifests": {
                    name: hashlib.sha256(content).hexdigest()
                    for name, content in sorted(manifests.items())
                },
                "profile": {
                    "id": values["TL_PROFILE_ID"],
                    "sha256": values["TL_PROFILE_SHA256"],
                },
                "schema": "kilix.trusted-launcher.bundle-build/v1",
                "source": {
                    "bootstrap_sha256": _sha256(bootstrap_source),
                    "builder_sha256": _sha256(Path(__file__).resolve()),
                    "launcher_sha256": _sha256(launcher_source),
                },
            },
        )
        (output / "BUNDLE-SHA256SUMS").write_bytes(_bundle_hashes(output))
        for path in output.iterdir():
            if path.is_file():
                path.chmod(stat.S_IMODE(path.stat().st_mode) & ~0o222)
        _make_read_only(output)
    except BaseException:
        # The output was required to be new.  A failed construction has no
        # accepted bytes, so remove only that exact newly-created directory.
        shutil.rmtree(output, ignore_errors=True)
        raise


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--subject", required=True, type=Path)
    result.add_argument("--output", required=True, type=Path)
    result.add_argument("--interpreter", required=True, type=Path)
    result.add_argument("--dependency-root", required=True, type=Path)
    result.add_argument("--cc", required=True, type=Path)
    result.add_argument(
        "--profile",
        type=Path,
        default=Path(__file__).resolve().parent / "profiles" / "f120-reference-v1.json",
        help="canonical kilix.trusted-launcher.profile/v1 document",
    )
    return result


def main() -> int:
    try:
        build(parser().parse_args())
    except (BundleError, OSError, subprocess.SubprocessError) as exc:
        print(f"authority bundle refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
