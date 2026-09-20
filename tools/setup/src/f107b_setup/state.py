"""``plebian.setup/v1`` — the first-login setup state record.

The state exists so that setup can be skipped, interrupted, logged out of or
rebooted through without either losing the operator's decisions or blocking
core provisioning. Three properties drive the design:

* **Core never waits on setup.** The record carries ``core_complete`` as an
  input it reads and never writes. A wizard that could clear it could hang a
  boot.
* **Stale state is refused, not guessed.** An unknown schema or a newer state
  version is a refusal with a named reason. Silent migration is how a decision
  made under one contract gets re-interpreted under another.
* **The record is decisions, never secrets.** No password, hash, licence text,
  receipt or model payload is ever written here.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA = "plebian.setup/v1"
STATE_VERSION = 1

PENDING = "pending"
COMPLETE = "complete"
SKIPPED = "skipped"
BLOCKED = "blocked"

TERMINAL_STATUSES = frozenset({COMPLETE, SKIPPED, BLOCKED})
ALL_STATUSES = frozenset({PENDING, COMPLETE, SKIPPED, BLOCKED})

#: Checkpoint order is part of the contract: the account summary is shown
#: before any policy question, and the plan review is last so it can quote
#: every decision above it.
CHECKPOINT_ORDER: tuple[tuple[str, str], ...] = (
    ("welcome", "Welcome"),
    ("account-summary", "Your account"),
    ("sudo-policy", "Administrator password policy"),
    ("hardware-report", "What this machine can do"),
    ("goals-and-fit", "What you want to use it for"),
    ("optional-components", "Optional components"),
    ("default-browser", "Default browser"),
    ("plan-review", "Review and confirm"),
)

CHECKPOINT_IDS = tuple(identifier for identifier, _ in CHECKPOINT_ORDER)

#: Keys that must never appear in a persisted state record.
FORBIDDEN_STATE_KEYS = frozenset(
    {"password", "password_hash", "shadow", "crypt", "token", "secret", "license_text"}
)


class StaleState(ValueError):
    """The on-disk record cannot be interpreted under this contract."""


@dataclass(frozen=True)
class Checkpoint:
    checkpoint_id: str
    title: str
    status: str = PENDING
    #: Operator-visible reason, e.g. why a checkpoint is blocked.
    detail: str = ""

    def with_status(self, status: str, detail: str = "") -> "Checkpoint":
        if status not in ALL_STATUSES:
            raise ValueError(f"unknown checkpoint status: {status}")
        return replace(self, status=status, detail=detail)


@dataclass(frozen=True)
class SetupState:
    """One operator's setup progress."""

    account: str | None = None
    core_complete: bool = True
    checkpoints: tuple[Checkpoint, ...] = ()
    state_version: int = STATE_VERSION

    @classmethod
    def fresh(cls, account: str | None = None, core_complete: bool = True) -> "SetupState":
        return cls(
            account=account,
            core_complete=core_complete,
            checkpoints=tuple(
                Checkpoint(checkpoint_id=identifier, title=title)
                for identifier, title in CHECKPOINT_ORDER
            ),
        )

    # -- navigation ---------------------------------------------------------

    def index_of(self, checkpoint_id: str) -> int:
        for index, checkpoint in enumerate(self.checkpoints):
            if checkpoint.checkpoint_id == checkpoint_id:
                return index
        raise KeyError(checkpoint_id)

    def get(self, checkpoint_id: str) -> Checkpoint:
        return self.checkpoints[self.index_of(checkpoint_id)]

    def resume_at(self) -> str | None:
        """The first checkpoint that still needs the operator.

        A blocked checkpoint is terminal for this run: it is not a place to
        resume, because nothing the operator can do at the keyboard closes a
        release gate owned by another stream.
        """

        for checkpoint in self.checkpoints:
            if checkpoint.status not in TERMINAL_STATUSES:
                return checkpoint.checkpoint_id
        return None

    @property
    def setup_complete(self) -> bool:
        return self.resume_at() is None

    def counts(self) -> Mapping[str, int]:
        tally = {status: 0 for status in sorted(ALL_STATUSES)}
        for checkpoint in self.checkpoints:
            tally[checkpoint.status] += 1
        return tally

    # -- transitions --------------------------------------------------------

    def _replace_checkpoint(self, checkpoint: Checkpoint) -> "SetupState":
        index = self.index_of(checkpoint.checkpoint_id)
        checkpoints = list(self.checkpoints)
        checkpoints[index] = checkpoint
        return replace(self, checkpoints=tuple(checkpoints))

    def mark(self, checkpoint_id: str, status: str, detail: str = "") -> "SetupState":
        return self._replace_checkpoint(self.get(checkpoint_id).with_status(status, detail))

    def complete(self, checkpoint_id: str, detail: str = "") -> "SetupState":
        return self.mark(checkpoint_id, COMPLETE, detail)

    def skip(self, checkpoint_id: str, detail: str = "") -> "SetupState":
        return self.mark(checkpoint_id, SKIPPED, detail)

    def block(self, checkpoint_id: str, detail: str) -> "SetupState":
        if not detail:
            raise ValueError("a blocked checkpoint must name its reason")
        return self.mark(checkpoint_id, BLOCKED, detail)

    def skip_all_remaining(self, detail: str = "skipped by the operator") -> "SetupState":
        state = self
        for checkpoint in self.checkpoints:
            if checkpoint.status == PENDING:
                state = state.skip(checkpoint.checkpoint_id, detail)
        return state

    # -- persistence --------------------------------------------------------

    def to_document(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "state_version": self.state_version,
            "account": self.account,
            "core_complete": self.core_complete,
            "checkpoints": [
                {
                    "id": checkpoint.checkpoint_id,
                    "title": checkpoint.title,
                    "status": checkpoint.status,
                    "detail": checkpoint.detail,
                }
                for checkpoint in self.checkpoints
            ],
        }

    @classmethod
    def from_document(cls, document: Any) -> "SetupState":
        if not isinstance(document, dict):
            raise StaleState("setup state is not a JSON object")
        if document.get("schema") != SCHEMA:
            raise StaleState(
                f"setup state schema is {document.get('schema')!r}, expected {SCHEMA!r}"
            )
        version = document.get("state_version")
        if not isinstance(version, int) or isinstance(version, bool):
            raise StaleState("setup state version is not an integer")
        if version > STATE_VERSION:
            raise StaleState(
                f"setup state version {version} is newer than this build's {STATE_VERSION}"
            )
        if version < STATE_VERSION:
            raise StaleState(
                f"setup state version {version} predates this build's {STATE_VERSION}; "
                "a migration must be reviewed, not inferred"
            )

        for key in document:
            if key in FORBIDDEN_STATE_KEYS:
                raise StaleState(f"setup state carries forbidden member {key!r}")

        raw_checkpoints = document.get("checkpoints")
        if not isinstance(raw_checkpoints, list):
            raise StaleState("setup state carries no checkpoint list")

        seen = [entry.get("id") for entry in raw_checkpoints if isinstance(entry, dict)]
        if seen != list(CHECKPOINT_IDS):
            raise StaleState(
                "setup state checkpoints do not match this build's checkpoint order"
            )

        checkpoints: list[Checkpoint] = []
        titles = dict(CHECKPOINT_ORDER)
        for entry in raw_checkpoints:
            status = entry.get("status")
            if status not in ALL_STATUSES:
                raise StaleState(f"unknown checkpoint status {status!r}")
            detail = entry.get("detail", "")
            if not isinstance(detail, str):
                raise StaleState("checkpoint detail is not a string")
            checkpoints.append(
                Checkpoint(
                    checkpoint_id=entry["id"],
                    title=titles[entry["id"]],
                    status=status,
                    detail=detail,
                )
            )

        account = document.get("account")
        if account is not None and not isinstance(account, str):
            raise StaleState("setup state account is neither a string nor null")
        core_complete = document.get("core_complete")
        if not isinstance(core_complete, bool):
            raise StaleState("setup state core_complete is not a boolean")

        return cls(
            account=account,
            core_complete=core_complete,
            checkpoints=tuple(checkpoints),
            state_version=version,
        )


def save(state: SetupState, path: Path) -> None:
    """Persist atomically at mode 0600, or leave the previous record intact."""

    payload = json.dumps(state.to_document(), indent=2, sort_keys=True).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=".setup-state-")
    try:
        os.fchmod(handle, 0o600)
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    directory = os.open(str(path.parent), os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def load(path: Path) -> SetupState:
    def reject_duplicates(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise StaleState(f"duplicate key in setup state: {key}")
            result[key] = value
        return result

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise StaleState(f"setup state is unreadable: {error}") from error
    try:
        document = json.loads(text, object_pairs_hook=reject_duplicates)
    except json.JSONDecodeError as error:
        raise StaleState(f"setup state is not valid JSON: {error}") from error
    return SetupState.from_document(document)
