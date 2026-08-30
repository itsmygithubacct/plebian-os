"""System Center entries, generated from catalog data rather than committed.

The master is explicit: F107-B's System Center entries are **generated from
`plebian.setup.optional-component/v1` catalog data, not committed as code**, and
F107-B **ships no component-specific control**. The same catalog record that
produces the offer in the wizard produces the "install it later" entry here, so
there is exactly one place a component can be named — the data — and it is not
this file.

That constraint is testable and is tested: no component identifier appears in
this module's source, and an empty catalog yields **zero** optional-component
entries. Absence must be indistinguishable from declining, which means no
placeholder row, no greyed-out entry and no "coming soon".

Two entries are fixed, because they are F107-B's own surfaces rather than any
component's: **Setup**, which resumes the wizard, and **Hardware and model
ability**, which shows what F106 measured. Both are structural and neither
names a component.

An entry is an index row. It carries no authority: acting on an "install it
later" row re-enters the same two-act consent boundary and the same release
gates as the wizard, which is why :func:`entry_action` returns a refusal rather
than a callable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .catalog import Offer, OptionalComponentCatalog, may_invoke_provider
from .gates import GateLedger, GateRefusal
from .state import BLOCKED, COMPLETE, PENDING, SKIPPED, SetupState

#: Where these entries live in the System Center tree, matching the existing
#: `FOCUSED_APPS` breadcrumb shape in `kilix-tui-utils`.
BREADCRUMB = ("Machine",)

SETUP_ENTRY_ID = "setup"
ABILITY_ENTRY_ID = "ability"

#: Prefix for generated component rows. The suffix comes from the record's id,
#: so this module never spells a component's name.
COMPONENT_ENTRY_PREFIX = "optional-"


class RegistrationError(ValueError):
    """The entry set cannot be generated unambiguously."""


@dataclass(frozen=True)
class Entry:
    """One System Center row."""

    entry_id: str
    label: str
    #: Sub-sections, in the `{section_id: label}` shape the TUI already uses.
    sections: Mapping[str, str]
    #: Present only on rows generated from a catalog record.
    offer_id: str | None = None

    @property
    def generated(self) -> bool:
        return self.offer_id is not None


def _setup_summary(state: SetupState) -> str:
    """A one-line status the operator can act on, never a bare percentage."""

    counts = state.counts()
    if state.setup_complete:
        if counts[BLOCKED]:
            return f"Finished; {counts[BLOCKED]} step(s) could not run"
        if counts[SKIPPED]:
            return f"Finished; {counts[SKIPPED]} step(s) skipped"
        return "Finished"
    resume = state.resume_at()
    return f"Resume at: {state.get(resume).title}" if resume else "Finished"


def setup_entry(state: SetupState) -> Entry:
    """The Setup row. Always present — setup is always resumable."""

    counts = state.counts()
    return Entry(
        entry_id=SETUP_ENTRY_ID,
        label="Setup",
        sections={
            "overview": _setup_summary(state),
            "checkpoints": (
                f"{counts[COMPLETE]} done, {counts[SKIPPED]} skipped, "
                f"{counts[BLOCKED]} blocked, {counts[PENDING]} to go"
            ),
            "resume": "Continue setup",
        },
    )


def ability_entry(ledger: GateLedger) -> Entry:
    """The hardware and model ability row.

    It reports what is measurable now. While the capacity contract is unfrozen
    there is no fit or recommendation to show, and the row says so with the
    gate's owner rather than showing an empty panel.
    """

    refusal = ledger.require("present_positive_fit")
    if refusal is None:
        overview = "Measured fit available"
    else:
        owners = "; ".join(f"{gate.gate_id} ({gate.owner})" for gate in refusal.gates)
        overview = f"Fit unavailable — blocked on {owners}"
    return Entry(
        entry_id=ABILITY_ENTRY_ID,
        label="Hardware and model ability",
        sections={
            "overview": overview,
            "hardware": "What this machine has",
            "unknowns": "What could not be determined",
            "models": "What models would fit",
        },
    )


def component_entries(catalog: OptionalComponentCatalog) -> tuple[Entry, ...]:
    """One row per catalog record, and none at all for an empty catalog.

    Every string on a generated row comes from the record. This function has no
    branch on which component it is looking at, and there is no table here to
    add a component to.
    """

    seen: set[str] = set()
    entries: list[Entry] = []
    for offer in catalog.offers:
        entry_id = f"{COMPONENT_ENTRY_PREFIX}{offer.offer_id}"
        if entry_id in seen:
            raise RegistrationError(f"duplicate System Center entry id: {entry_id}")
        seen.add(entry_id)
        entries.append(
            Entry(
                entry_id=entry_id,
                label=offer.label,
                sections={
                    "overview": "Not installed",
                    "disclosures": (
                        f"{len(offer.record['disclosures'])} thing(s) this changes "
                        "on your system"
                    ),
                    "install": "Install it now",
                },
                offer_id=offer.offer_id,
            )
        )
    return tuple(entries)


def register(state: SetupState, catalog: OptionalComponentCatalog, ledger: GateLedger) -> tuple[Entry, ...]:
    """The complete F107-B contribution to System Center."""

    return (setup_entry(state), ability_entry(ledger)) + component_entries(catalog)


def focused_app(entries: Sequence[Entry]) -> tuple[str, tuple[str, ...], dict[str, str]]:
    """Render the entry set in the shape `kilix-tui-utils` already consumes."""

    sections: dict[str, str] = {"overview": ""}
    for entry in entries:
        sections[entry.entry_id] = entry.label
    return ("Setup and ability", BREADCRUMB, sections)


def entry_action(entry: Entry, catalog: OptionalComponentCatalog, ledger: GateLedger) -> GateRefusal | str | None:
    """What happens when the operator activates a generated row.

    A row is an index, not an authority. Activating one re-enters the wizard's
    consent boundary and its gates, so this returns exactly what
    :func:`~f107b_setup.catalog.may_invoke_provider` returns and never a
    shortcut around it.
    """

    if not entry.generated:
        raise RegistrationError(f"{entry.entry_id} is not a component row")
    offer: Offer = catalog.get(entry.offer_id)
    return may_invoke_provider(offer, ledger)
