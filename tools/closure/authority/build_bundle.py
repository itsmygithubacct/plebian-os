#!/usr/bin/env python3
"""Construct an external, digest-pinned F120 authority bundle.

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


MANIFEST_HEADER = b"KILIX-F120-CLOSURE-MANIFEST-v1\n"
RESERVED_NAMES = {"sitecustomize.py", "usercustomize.py"}
PINNED_PYTHON_SHA256 = (
    "0dc3a692fa85fcdb7f1a5877d2adf179809ac417a07ffde2373c832863800a15"
)


class BundleError(ValueError):
    """A fail-closed bundle construction error."""


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
    interpreter = _safe_path(arguments.interpreter, "interpreter", directory=False)
    if _sha256(interpreter) != PINNED_PYTHON_SHA256:
        raise BundleError("interpreter does not match the release-pinned Python bytes")
    dependency_source = _safe_path(
        arguments.dependency_root, "dependency root", directory=True
    )
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

        # Normalize external authority material before freezing its metadata.
        _make_read_only(runtime_root)
        _make_read_only(dependency_root)
        (output / "bootstrap.py").chmod(0o444)

        manifests = {
            "subject.manifest": manifest_bytes(subject, reject_reserved=True),
            "runtime.manifest": manifest_bytes(runtime_root, reject_reserved=False),
            "dependency.manifest": manifest_bytes(dependency_root, reject_reserved=False),
        }
        for name, content in manifests.items():
            (output / name).write_bytes(content)

        values = {
            "F120_BOOTSTRAP_SHA256": _sha256(output / "bootstrap.py"),
            "F120_DEPENDENCY_MANIFEST_SHA256": hashlib.sha256(
                manifests["dependency.manifest"]
            ).hexdigest(),
            "F120_PYTHON_BASENAME": copied_interpreter.name,
            "F120_PYTHON_SHA256": _sha256(copied_interpreter),
            "F120_RUNTIME_MANIFEST_SHA256": hashlib.sha256(
                manifests["runtime.manifest"]
            ).hexdigest(),
            "F120_SUBJECT_MANIFEST_SHA256": hashlib.sha256(
                manifests["subject.manifest"]
            ).hexdigest(),
        }
        profile = output / "profile.h"
        profile.write_text(
            "#ifndef KILIX_F120_PROFILE_H\n#define KILIX_F120_PROFILE_H\n"
            + "".join(
                f'#define {name} "{value}"\n' for name, value in sorted(values.items())
            )
            + "#endif\n",
            encoding="utf-8",
        )
        shutil.copy2(launcher_source, output / "launcher.c", follow_symlinks=False)
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
            str(output / "f120-authority"),
            str(output / "launcher.c"),
        ]
        environment = {
            "LC_ALL": "C.UTF-8",
            "PATH": "/usr/bin:/bin",
            "SOURCE_DATE_EPOCH": "0",
            "TZ": "UTC",
        }
        subprocess.run(command, check=True, cwd=output, env=environment)
        (output / "f120-authority").chmod(0o555)

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
                "bootstrap_sha256": values["F120_BOOTSTRAP_SHA256"],
                "compiler": {
                    "path": str(compiler),
                    "sha256": _sha256(compiler),
                    "version": compiler_version,
                },
                "interpreter": {
                    "sha256": values["F120_PYTHON_SHA256"],
                    "version": subprocess.run(
                        [str(interpreter), "-I", "-S", "-B", "-VV"],
                        check=True,
                        capture_output=True,
                        text=True,
                        env=environment,
                        cwd=output_parent,
                    ).stdout.strip(),
                },
                "launcher_sha256": _sha256(output / "f120-authority"),
                "manifests": {
                    name: hashlib.sha256(content).hexdigest()
                    for name, content in sorted(manifests.items())
                },
                "schema": "kilix.f120.authority-bundle-build/v1",
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
