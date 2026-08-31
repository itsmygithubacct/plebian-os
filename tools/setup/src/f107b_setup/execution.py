"""Phase 8 — supervised, provider-owned execution.

The wizard never installs anything itself. It drives providers, watches them,
and records what happened. That distinction is the whole design: **F107-B owns
the supervision, providers own the work**, and the controller has no code path
that writes a model artifact, a package, or a receipt.

The governing requirement is the one that reads like a slogan and is actually a
structural constraint:

    a failed 20 GB download leaves a bootable, setup-complete OS

So this module cannot touch core state. It holds no reference to it, exposes no
function that could roll it back, and the tests assert both. Optional model work
failing is an *outcome*, not an error — the same stance the plan review takes.

Durability is the other half. Progress must survive tab closure and logout,
which means the journal is written atomically after **every** state transition,
not at the end. A controller that only persists on success loses exactly the
runs you most needed a record of.

Actually invoking a provider remains gated on F100-A3 and F106-P1. The
mechanics below are gate-free and are what this module is for; ``run`` consults
the ledger and refuses before it reaches a provider.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Iterable, Mapping, Protocol, Sequence

from .gates import GateLedger, GateRefusal

SCHEMA = "plebian.setup.execution-journal/v1"
JOURNAL_VERSION = 1

# -- item states ------------------------------------------------------------

PENDING = "pending"
ACQUIRING = "acquiring"
ACQUIRED = "acquired"
INSTALLING = "installing"
INSTALLED = "installed"
FAILED = "failed"
CANCELLED = "cancelled"
#: The artifact was already present and shared with something else. Not an
#: error and not work: it is the correct outcome and must not be redownloaded.
ALREADY_PRESENT = "already-present"

TERMINAL = frozenset({INSTALLED, FAILED, CANCELLED, ALREADY_PRESENT})
ALL_STATES = frozenset(
    {PENDING, ACQUIRING, ACQUIRED, INSTALLING, INSTALLED, FAILED, CANCELLED, ALREADY_PRESENT}
)

#: Recoverable, named failure classes. A provider that fails in a way not on
#: this list is still recorded, but as ``unknown`` rather than being mapped to
#: the nearest familiar cause.
CORRUPT_MIRROR = "corrupt-mirror"
LOW_DISK = "low-disk"
OFFLINE = "offline"
PROVIDER_ERROR = "provider-error"
VERIFICATION_FAILED = "verification-failed"
UNKNOWN_CAUSE = "unknown"

FAILURE_CAUSES = frozenset(
    {CORRUPT_MIRROR, LOW_DISK, OFFLINE, PROVIDER_ERROR, VERIFICATION_FAILED, UNKNOWN_CAUSE}
)

#: Default tolerance for predicted-versus-actual byte accounting.
DEFAULT_TOLERANCE = 0.10


class ExecutionRefusal(RuntimeError):
    """The controller will not do what was asked."""


class Cancelled(Exception):
    """Cooperative cancellation. Raised by a provider callback, never by force."""


# -- byte accounting --------------------------------------------------------


def within_tolerance(
    predicted: int | None, actual: int | None, fraction: float = DEFAULT_TOLERANCE
) -> bool | None:
    """Is *actual* within *fraction* of *predicted*?

    ``None`` when either side is unmeasured — never ``True``. An unknown that
    reports as "within tolerance" is how an unmeasured prediction becomes an
    accepted one.
    """

    if predicted is None or actual is None:
        return None
    if predicted < 0 or actual < 0:
        raise ValueError("byte counts cannot be negative")
    if predicted == 0:
        return actual == 0
    return abs(actual - predicted) <= predicted * fraction


# -- the provider seam ------------------------------------------------------


@dataclass(frozen=True)
class ProviderOutcome:
    """What a provider reports. It never reports a receipt."""

    ok: bool
    bytes_moved: int | None = None
    cause: str = UNKNOWN_CAUSE
    detail: str = ""

    def __post_init__(self) -> None:
        if not self.ok and self.cause not in FAILURE_CAUSES:
            raise ValueError(f"unknown failure cause: {self.cause!r}")


class Provider(Protocol):
    """The seam F107-B drives. Implementations live in the provider repos."""

    def already_present(self, artifact_id: str) -> bool:
        ...

    def acquire(self, artifact_id: str) -> ProviderOutcome:
        ...

    def install(self, artifact_id: str) -> ProviderOutcome:
        ...

    def remove(self, artifact_id: str) -> ProviderOutcome:
        ...


# -- the journal ------------------------------------------------------------


@dataclass(frozen=True)
class ItemRecord:
    artifact_id: str
    provider: str
    profile_id: str
    #: Bytes the plan predicted for this item; ``None`` when unmeasured.
    predicted_bytes: int | None = None
    #: Whether other items or an existing installation share this artifact.
    shared: bool = False
    state: str = PENDING
    cause: str = ""
    detail: str = ""
    acquired_bytes: int | None = None

    def with_state(self, state: str, cause: str = "", detail: str = "") -> "ItemRecord":
        if state not in ALL_STATES:
            raise ValueError(f"unknown item state: {state}")
        if state == FAILED and cause not in FAILURE_CAUSES:
            raise ValueError(f"a failed item must name a known cause, not {cause!r}")
        return replace(self, state=state, cause=cause, detail=detail[:512])

    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL

    @property
    def installed_by_this_run(self) -> bool:
        """Only what this run installed is this run's to remove."""

        return self.state == INSTALLED


@dataclass(frozen=True)
class ExecutionJournal:
    """The durable record. Written after every transition, not at the end."""

    plan_id: str
    items: tuple[ItemRecord, ...]
    cancelled: bool = False
    journal_version: int = JOURNAL_VERSION

    def index_of(self, artifact_id: str) -> int:
        for index, item in enumerate(self.items):
            if item.artifact_id == artifact_id:
                return index
        raise KeyError(artifact_id)

    def get(self, artifact_id: str) -> ItemRecord:
        return self.items[self.index_of(artifact_id)]

    def replace_item(self, item: ItemRecord) -> "ExecutionJournal":
        items = list(self.items)
        items[self.index_of(item.artifact_id)] = item
        return replace(self, items=tuple(items))

    def counts(self) -> Mapping[str, int]:
        tally = {state: 0 for state in sorted(ALL_STATES)}
        for item in self.items:
            tally[item.state] += 1
        return tally

    def resume_from(self) -> tuple[ItemRecord, ...]:
        """Items still to do. A resumed run repeats no completed work."""

        return tuple(item for item in self.items if not item.terminal)

    @property
    def complete(self) -> bool:
        return all(item.terminal for item in self.items)

    def totals(self) -> Mapping[str, int | None]:
        predicted: list[int | None] = []
        actual: list[int | None] = []
        for item in self.items:
            if item.state == ALREADY_PRESENT:
                # A shared artifact that was already there moved zero bytes,
                # and predicting bytes for it would inflate both sides.
                continue
            predicted.append(item.predicted_bytes)
            actual.append(item.acquired_bytes)

        def total(values: Sequence[int | None]) -> int | None:
            running = 0
            for value in values:
                if value is None:
                    return None
                running += value
            return running

        return {"predicted_bytes": total(predicted), "acquired_bytes": total(actual)}

    def to_document(self) -> dict[str, object]:
        return {
            "schema": SCHEMA,
            "journal_version": self.journal_version,
            "plan_id": self.plan_id,
            "cancelled": self.cancelled,
            "items": [
                {
                    "artifact_id": item.artifact_id,
                    "provider": item.provider,
                    "profile_id": item.profile_id,
                    "predicted_bytes": item.predicted_bytes,
                    "acquired_bytes": item.acquired_bytes,
                    "shared": item.shared,
                    "state": item.state,
                    "cause": item.cause,
                    "detail": item.detail,
                }
                for item in self.items
            ],
        }

    @classmethod
    def from_document(cls, document: object) -> "ExecutionJournal":
        if not isinstance(document, dict):
            raise ExecutionRefusal("execution journal is not a JSON object")
        if document.get("schema") != SCHEMA:
            raise ExecutionRefusal(
                f"journal schema is {document.get('schema')!r}, expected {SCHEMA!r}"
            )
        version = document.get("journal_version")
        if version != JOURNAL_VERSION:
            raise ExecutionRefusal(
                f"journal version {version!r} is not {JOURNAL_VERSION}; "
                "a migration must be reviewed, not inferred"
            )
        raw_items = document.get("items")
        if not isinstance(raw_items, list):
            raise ExecutionRefusal("journal carries no item list")
        items = []
        for entry in raw_items:
            state = entry.get("state")
            if state not in ALL_STATES:
                raise ExecutionRefusal(f"unknown item state {state!r}")
            items.append(
                ItemRecord(
                    artifact_id=entry["artifact_id"],
                    provider=entry["provider"],
                    profile_id=entry["profile_id"],
                    predicted_bytes=entry.get("predicted_bytes"),
                    acquired_bytes=entry.get("acquired_bytes"),
                    shared=bool(entry.get("shared")),
                    state=state,
                    cause=entry.get("cause", ""),
                    detail=entry.get("detail", ""),
                )
            )
        return cls(
            plan_id=document["plan_id"],
            items=tuple(items),
            cancelled=bool(document.get("cancelled")),
        )

    @classmethod
    def from_plan(cls, plan: Mapping[str, object], shared: Iterable[str] = ()) -> "ExecutionJournal":
        shared_ids = set(shared)
        items = tuple(
            ItemRecord(
                artifact_id=str(item["artifact_id"]),
                provider=str(item["provider"]),
                profile_id=str(item["profile_id"]),
                predicted_bytes=item.get("predicted_bytes"),
                shared=str(item["artifact_id"]) in shared_ids,
            )
            for item in plan.get("items", [])  # type: ignore[union-attr]
        )
        return cls(plan_id=str(plan.get("plan_id", "unknown")), items=items)


def save_journal(journal: ExecutionJournal, path: Path) -> None:
    """Atomic, 0600, fsynced. Called after every transition."""

    payload = json.dumps(journal.to_document(), indent=2, sort_keys=True).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=".journal-")
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


def load_journal(path: Path) -> ExecutionJournal:
    def reject_duplicates(pairs: Iterable[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ExecutionRefusal(f"duplicate key in journal: {key}")
            result[key] = value
        return result

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ExecutionRefusal(f"journal is unreadable: {error}") from error
    try:
        document = json.loads(text, object_pairs_hook=reject_duplicates)
    except json.JSONDecodeError as error:
        raise ExecutionRefusal(f"journal is not valid JSON: {error}") from error
    return ExecutionJournal.from_document(document)


# -- the controller ---------------------------------------------------------


@dataclass
class ExecutionController:
    """Drives a plan's items through their providers, and records everything.

    It deliberately holds **no** reference to the setup state or to anything
    describing the core system. There is no field to reach through and no
    method that could roll core setup back, which is how the "a failed 20 GB
    download leaves a bootable machine" requirement is met structurally rather
    than by remembering not to.
    """

    journal: ExecutionJournal
    providers: Mapping[str, Provider]
    ledger: GateLedger
    journal_path: Path | None = None
    #: Set by :meth:`cancel`; checked between items and between phases.
    _cancel_requested: bool = field(default=False, repr=False)

    def cancel(self) -> None:
        """Request cancellation. Cooperative: never kills a provider mid-write."""

        self._cancel_requested = True

    def _persist(self) -> None:
        if self.journal_path is not None:
            save_journal(self.journal, self.journal_path)

    def _transition(self, item: ItemRecord, state: str, cause: str = "", detail: str = "") -> ItemRecord:
        updated = item.with_state(state, cause, detail)
        self.journal = self.journal.replace_item(updated)
        self._persist()
        return updated

    def may_run(self) -> GateRefusal | None:
        return self.ledger.require("invoke_provider")

    def run(self) -> GateRefusal | ExecutionJournal:
        """Execute the plan, or return the gate refusing to let it start.

        A per-item failure never aborts the run: the item is recorded and the
        next one is attempted. Optional model work is optional item by item, not
        only as a whole.
        """

        refusal = self.may_run()
        if refusal is not None:
            return refusal

        for item in self.journal.items:
            if item.terminal:
                continue
            if self._cancel_requested:
                self._transition(item, CANCELLED, detail="cancelled before this item started")
                continue
            self._run_one(item)

        if self._cancel_requested:
            self.journal = replace(self.journal, cancelled=True)
            self._persist()
        return self.journal

    def _run_one(self, item: ItemRecord) -> None:
        provider = self.providers.get(item.provider)
        if provider is None:
            self._transition(
                item, FAILED, PROVIDER_ERROR, f"no adapter registered for {item.provider}"
            )
            return

        try:
            if provider.already_present(item.artifact_id):
                # Not work, not an error, and above all not a redownload.
                self._transition(item, ALREADY_PRESENT, detail="artifact already present")
                return

            current = self._transition(item, ACQUIRING)
            outcome = provider.acquire(item.artifact_id)
            if not outcome.ok:
                self._transition(current, FAILED, outcome.cause, outcome.detail)
                return
            current = replace(current, acquired_bytes=outcome.bytes_moved)
            self.journal = self.journal.replace_item(current)
            current = self._transition(current, ACQUIRED)

            if self._cancel_requested:
                self._transition(current, CANCELLED, detail="cancelled after acquisition")
                return

            current = self._transition(current, INSTALLING)
            outcome = provider.install(item.artifact_id)
            if not outcome.ok:
                self._transition(current, FAILED, outcome.cause, outcome.detail)
                return
            self._transition(current, INSTALLED)
        except Cancelled:
            self._transition(self.journal.get(item.artifact_id), CANCELLED, detail="cancelled by provider")
        except Exception as error:  # noqa: BLE001 - a provider may raise anything
            self._transition(
                self.journal.get(item.artifact_id),
                FAILED,
                PROVIDER_ERROR,
                f"{type(error).__name__}: {error}",
            )

    # -- removal ------------------------------------------------------------

    def preview_removal(self) -> tuple[ItemRecord, ...]:
        """What a rollback would remove — and nothing else.

        Shared artifacts are excluded even when this run installed them:
        something else depends on them, and a rollback that takes them is
        destructive beyond its own scope.
        """

        return tuple(
            item
            for item in self.journal.items
            if item.installed_by_this_run and not item.shared
        )

    def rollback(self) -> GateRefusal | tuple[ItemRecord, ...]:
        """Remove exactly what :meth:`preview_removal` said, no more."""

        refusal = self.may_run()
        if refusal is not None:
            return refusal

        removed: list[ItemRecord] = []
        for item in self.preview_removal():
            provider = self.providers.get(item.provider)
            if provider is None:
                continue
            outcome = provider.remove(item.artifact_id)
            if outcome.ok:
                removed.append(self._transition(item, PENDING, detail="removed by rollback"))
        return tuple(removed)

    # -- reporting ----------------------------------------------------------

    def accounting(self, fraction: float = DEFAULT_TOLERANCE) -> Mapping[str, object]:
        totals = self.journal.totals()
        return {
            "predicted_bytes": totals["predicted_bytes"],
            "acquired_bytes": totals["acquired_bytes"],
            "within_tolerance": within_tolerance(
                totals["predicted_bytes"], totals["acquired_bytes"], fraction
            ),
            "tolerance": fraction,
        }

    def render(self) -> tuple[str, ...]:
        counts = self.journal.counts()
        total = len(self.journal.items)
        lines = [
            f"Plan {self.journal.plan_id}: {counts[INSTALLED]}/{total} installed, "
            f"{counts[ALREADY_PRESENT]}/{total} already present, "
            f"{counts[FAILED]}/{total} failed, {counts[CANCELLED]}/{total} cancelled, "
            f"{counts[PENDING]}/{total} not started"
        ]
        for item in self.journal.items:
            if item.state == FAILED:
                lines.append(f"  failed: {item.artifact_id} [{item.cause}] {item.detail}")
        accounting = self.accounting()
        verdict = accounting["within_tolerance"]
        lines.append(
            "Bytes: predicted "
            f"{accounting['predicted_bytes'] if accounting['predicted_bytes'] is not None else 'unknown'}, "
            f"acquired {accounting['acquired_bytes'] if accounting['acquired_bytes'] is not None else 'unknown'}, "
            f"within tolerance: {'unknown' if verdict is None else verdict}"
        )
        lines.append(
            "The core system is complete and was not touched by any of the above."
        )
        return tuple(lines)
