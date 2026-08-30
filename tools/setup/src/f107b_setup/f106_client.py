"""The F107-B side of the F106 subprocess contract.

This is the consumer half of the argv/stream rules in Track D's
``invocation-contract.json``. It is deliberately paranoid: the contract is a
*candidate*, not a freeze, so this client re-checks every stream invariant
itself instead of assuming the producer honoured them.

Transport rules enforced here:

* direct argv, never a shell, and never a program name containing a separator;
* a reduced environment and ``stdin`` bound to ``/dev/null``;
* one JSON document followed by exactly one LF, or bounded text for
  ``hardware show``;
* exit 0 requires empty stderr; nonzero requires empty stdout and exactly one
  bounded, LF-terminated stderr line;
* duplicate JSON keys, non-finite numbers, trailing data and unexpected schema
  identities are rejected;
* the read-only timeout is enforced by the caller's clock, not by trust.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

#: Mirrors invocation-contract.json ``limits``. Re-declared rather than read
#: from the candidate so a mutated candidate cannot widen our own bounds.
STDOUT_BYTES = 4 * 1024 * 1024
DIAGNOSTIC_BYTES = 4096
READ_ONLY_TIMEOUT_SECONDS = 15

EXIT_STATUSES: Mapping[int, str] = {
    0: "contract-valid result, including unknown or blocked",
    2: "command-line usage error",
    65: "invalid input document",
    69: "required local dependency unavailable",
    70: "internal invariant failure",
    75: "temporary local failure",
}

RESPONSE_SCHEMA = "plebian.cli.response/v1"

#: command_id -> (argv tail, expected data schema or None for text output)
COMMANDS: Mapping[str, tuple[tuple[str, ...], str | None]] = {
    "hardware.show": (("plebian-hardware", "show"), None),
    "hardware.inventory": (
        ("plebian-hardware", "inventory", "--json"),
        "plebian.hardware/v1",
    ),
    "hardware.gpu": (("plebian-hardware", "gpu", "--json"), "plebian.hardware/v1"),
    "sizer.recommend.tts": (
        ("plebian-model-sizer", "recommend", "tts", "--json"),
        "plebian.models.fit-result/v1",
    ),
    "sizer.plan.local-ai-balanced": (
        ("plebian-model-sizer", "plan", "local-ai-balanced", "--json"),
        "plebian.models.install-plan/v1",
    ),
    "sizer.install": (
        ("plebian-model-sizer", "install", "PLAN_PATH", "--json"),
        "plebian.models.install-plan/v1",
    ),
    "sizer.snapshot": (
        ("plebian-model-sizer", "snapshot", "--json"),
        "plebian.models.snapshot/v1",
    ),
}


class ContractViolation(RuntimeError):
    """The producer broke the invocation contract.

    This is never converted into a value the wizard can mistake for an honest
    ``unknown``: a contract violation is a defect, not a fail-closed answer.
    """


@dataclass(frozen=True)
class TextResult:
    command_id: str
    exit_status: int
    text: str


@dataclass(frozen=True)
class JsonResult:
    command_id: str
    exit_status: int
    envelope: dict[str, Any]

    @property
    def status(self) -> str:
        return self.envelope["status"]

    @property
    def data(self) -> dict[str, Any]:
        return self.envelope["data"]

    @property
    def warnings(self) -> tuple[dict[str, str], ...]:
        return tuple(self.envelope["warnings"])


@dataclass(frozen=True)
class Failure:
    """A contract-shaped nonzero exit.

    ``diagnostic`` is the single redacted stderr line, already bounded. It is
    surfaced to the operator verbatim and never parsed for decisions.
    """

    command_id: str
    exit_status: int
    meaning: str
    diagnostic: str


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise ContractViolation(f"duplicate JSON key: {key}")
        seen[key] = value
    return seen


def _reject_non_finite(value: Any, trail: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ContractViolation(f"non-finite number at {trail}")
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_non_finite(item, f"{trail}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_non_finite(item, f"{trail}[{index}]")


def parse_document(payload: bytes) -> dict[str, Any]:
    """Parse exactly one JSON document followed by exactly one LF."""

    if len(payload) > STDOUT_BYTES:
        raise ContractViolation(f"stdout exceeds {STDOUT_BYTES} bytes")
    if not payload.endswith(b"\n"):
        raise ContractViolation("stdout is not LF-terminated")
    body = payload[:-1]
    if body.endswith(b"\n"):
        raise ContractViolation("stdout carries trailing data after the document")
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ContractViolation("stdout is not valid UTF-8") from error
    decoder = json.JSONDecoder(object_pairs_hook=_reject_duplicates)
    try:
        document, index = decoder.raw_decode(text)
    except json.JSONDecodeError as error:
        raise ContractViolation(f"stdout is not one JSON document: {error}") from error
    if text[index:].strip():
        raise ContractViolation("stdout carries trailing data after the document")
    if not isinstance(document, dict):
        raise ContractViolation("stdout document is not a JSON object")
    _reject_non_finite(document)
    return document


def _check_envelope(command_id: str, document: dict[str, Any]) -> None:
    if document.get("schema") != RESPONSE_SCHEMA:
        raise ContractViolation(
            f"envelope schema is {document.get('schema')!r}, expected {RESPONSE_SCHEMA!r}"
        )
    if document.get("command") != command_id:
        raise ContractViolation(
            f"envelope command is {document.get('command')!r}, expected {command_id!r}"
        )
    for key in ("status", "warnings", "data"):
        if key not in document:
            raise ContractViolation(f"envelope lacks required member {key!r}")
    if document["status"] not in {"ok", "unknown", "blocked"}:
        raise ContractViolation(f"envelope status {document['status']!r} is not in the contract")
    if not isinstance(document["warnings"], list):
        raise ContractViolation("envelope warnings is not an array")
    if not isinstance(document["data"], dict):
        raise ContractViolation("envelope data is not an object")

    expected_schema = COMMANDS[command_id][1]
    actual = document["data"].get("schema")
    if actual != expected_schema:
        raise ContractViolation(
            f"data schema is {actual!r}, expected {expected_schema!r} for {command_id}"
        )


def _reduced_environment(extra_path: str | None) -> dict[str, str]:
    path = os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")
    if extra_path:
        path = f"{extra_path}{os.pathsep}{path}"
    return {"LC_ALL": "C.UTF-8", "LANG": "C.UTF-8", "PATH": path}


@dataclass
class F106Client:
    """Invokes the seven contract commands against a resolved program directory.

    ``bin_dir`` is the directory the two programs are resolved from. Pointing it
    at Track D's ``tools/replay-bin`` is how F107-B builds and tests without the
    real binaries; pointing it at a real installation is qualification, which is
    gated on Phase 0 item 0.3.
    """

    bin_dir: Path
    timeout_seconds: int = READ_ONLY_TIMEOUT_SECONDS

    def _run(self, argv: Sequence[str]) -> tuple[int, bytes, bytes]:
        program = argv[0]
        if "/" in program or os.sep in program:
            raise ContractViolation("program name must not carry a path separator")
        resolved = self.bin_dir / program
        with open(os.devnull, "rb") as devnull:
            try:
                completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
                    [str(resolved), *argv[1:]],
                    stdin=devnull,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=_reduced_environment(str(self.bin_dir)),
                    cwd=str(self.bin_dir),
                    shell=False,
                    timeout=self.timeout_seconds,
                )
            except subprocess.TimeoutExpired as error:
                raise ContractViolation(
                    f"command exceeded the {self.timeout_seconds}s read-only bound"
                ) from error
            except OSError as error:
                raise ContractViolation(f"command could not be executed: {error}") from error
        return completed.returncode, completed.stdout, completed.stderr

    def _diagnostic(self, stderr: bytes) -> str:
        if len(stderr) > DIAGNOSTIC_BYTES:
            raise ContractViolation(f"stderr exceeds {DIAGNOSTIC_BYTES} bytes")
        if not stderr.endswith(b"\n"):
            raise ContractViolation("stderr diagnostic is not LF-terminated")
        line = stderr[:-1]
        if b"\n" in line:
            raise ContractViolation("stderr carries more than one diagnostic line")
        try:
            return line.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ContractViolation("stderr diagnostic is not valid UTF-8") from error

    def call(self, command_id: str, plan_path: Path | None = None) -> JsonResult | TextResult | Failure:
        try:
            argv_template, _ = COMMANDS[command_id]
        except KeyError:
            raise ContractViolation(f"{command_id} is not in the invocation contract") from None

        argv = list(argv_template)
        if command_id == "sizer.install":
            if plan_path is None:
                raise ContractViolation("sizer.install requires a plan path")
            argv[argv.index("PLAN_PATH")] = str(plan_path)
        elif plan_path is not None:
            raise ContractViolation(f"{command_id} takes no plan path")

        exit_status, stdout, stderr = self._run(argv)

        if exit_status != 0:
            if stdout:
                raise ContractViolation("nonzero exit did not leave stdout empty")
            meaning = EXIT_STATUSES.get(exit_status)
            if meaning is None:
                raise ContractViolation(f"exit status {exit_status} is not in the contract")
            return Failure(
                command_id=command_id,
                exit_status=exit_status,
                meaning=meaning,
                diagnostic=self._diagnostic(stderr),
            )

        if stderr:
            raise ContractViolation("exit 0 did not leave stderr empty")

        if COMMANDS[command_id][1] is None:
            if len(stdout) > DIAGNOSTIC_BYTES:
                raise ContractViolation("human-text output exceeds its bound")
            if not stdout.endswith(b"\n"):
                raise ContractViolation("human-text output is not LF-terminated")
            try:
                text = stdout.decode("utf-8")
            except UnicodeDecodeError as error:
                raise ContractViolation("human-text output is not valid UTF-8") from error
            return TextResult(command_id=command_id, exit_status=0, text=text)

        document = parse_document(stdout)
        _check_envelope(command_id, document)
        return JsonResult(command_id=command_id, exit_status=0, envelope=document)
