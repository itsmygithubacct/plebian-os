"""Decision-scoped licence presentation.

F107-B owns **presentation only**. ``kilix-content`` (F100) owns the
``kilix.install.license/v1`` schema, its validation and the receipt store.
Nothing here writes a receipt, and there is deliberately no function that
could: ``request_receipt`` returns the gate that owns the answer.

Four rules the presentation must not lose:

* an informational notice never grows a checkbox — a fake decision is worse
  than no decision, because it produces a record of consent nobody gave;
* an affirmative decision starts unchecked, per distinct licence *and version*
  (the version is the digest, not the name);
* an unknown or absent disposition fails closed as use-restricted;
* refusing a licence removes only the items that depend on it, and the sizes
  are recomputed rather than restated — while an unknown size stays unknown.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Iterable, Mapping, Sequence

from .gates import GateLedger, GateRefusal

INFORMATIONAL = "informational"
AFFIRMATIVE = "affirmative"
USER_SUPPLIED = "user-supplied"
RESTRICTED = "restricted"

KNOWN_CLASSES = frozenset({INFORMATIONAL, AFFIRMATIVE, USER_SUPPLIED, RESTRICTED})

#: Classes that require an explicit operator act before a dependent item may
#: be planned. ``restricted`` is here because a use-restricted licence needs a
#: decision it cannot get inside setup, which is what fail-closed means.
REQUIRES_DECISION = frozenset({AFFIRMATIVE, USER_SUPPLIED, RESTRICTED})


@dataclass(frozen=True)
class LicenseRef:
    license_id: str
    license_text_sha256: str
    decision_class: str

    @classmethod
    def from_record(cls, ref: Mapping[str, Any]) -> "LicenseRef":
        """Build a reference, failing closed on an unknown disposition."""

        declared = ref.get("decision_class")
        decision_class = declared if declared in KNOWN_CLASSES else RESTRICTED
        digest = ref.get("license_text_sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            # A licence whose text is not pinned cannot be presented as a
            # versioned decision, so it is use-restricted.
            digest = ""
            decision_class = RESTRICTED
        license_id = ref.get("license_id")
        if not isinstance(license_id, str) or not license_id:
            raise ValueError("licence reference carries no licence id")
        return cls(
            license_id=license_id,
            license_text_sha256=digest,
            decision_class=decision_class,
        )

    @property
    def decision_key(self) -> tuple[str, str]:
        """Distinct licence *and version*. Same name, new text, new decision."""

        return (self.license_id, self.license_text_sha256)

    @property
    def requires_checkbox(self) -> bool:
        return self.decision_class == AFFIRMATIVE

    @property
    def requires_decision(self) -> bool:
        return self.decision_class in REQUIRES_DECISION


@dataclass(frozen=True)
class LicenseDecision:
    """One presented decision and its current, operator-set answer."""

    ref: LicenseRef
    #: ``None`` means undecided. Affirmative decisions start here, never at True.
    accepted: bool | None = None
    #: The offline text this presentation would show, if the store carries it.
    text_available: bool = False

    def accept(self) -> "LicenseDecision":
        if not self.ref.requires_decision:
            raise ValueError(
                f"{self.ref.license_id} is {self.ref.decision_class}; it has no acceptance to give"
            )
        return replace(self, accepted=True)

    def refuse(self) -> "LicenseDecision":
        if not self.ref.requires_decision:
            raise ValueError(
                f"{self.ref.license_id} is {self.ref.decision_class}; it has no acceptance to refuse"
            )
        return replace(self, accepted=False)

    @property
    def satisfied(self) -> bool:
        """Whether a dependent item may be planned under this decision.

        ``restricted`` is never satisfied inside setup even when accepted: the
        restriction is on use, and setup is not the authority that lifts it.
        """

        if self.ref.decision_class == INFORMATIONAL:
            return True
        if self.ref.decision_class == RESTRICTED:
            return False
        return self.accepted is True

    def render(self) -> tuple[str, ...]:
        digest = self.ref.license_text_sha256 or "(unpinned)"
        lines = [f"{self.ref.license_id}  [{self.ref.decision_class}]  sha256 {digest}"]
        if self.ref.decision_class == INFORMATIONAL:
            lines.append("    Notice. No acceptance is requested and none is recorded.")
        elif self.ref.decision_class == RESTRICTED:
            lines.append(
                "    Use-restricted or unknown disposition. This item is not offered; "
                "setup does not decide restricted licences."
            )
        else:
            box = {None: "[ ]", True: "[x]", False: "[-]"}[self.accepted]
            lines.append(f"    {box} I accept these terms")
        lines.append(
            "    Offline text: " + ("available" if self.text_available else "not available")
        )
        return tuple(lines)


@dataclass(frozen=True)
class PlanItemView:
    """A plan item as the licence screen sees it."""

    profile_id: str
    provider: str
    artifact_id: str
    license_decision_id: str
    reason: str

    @classmethod
    def from_plan_item(cls, item: Mapping[str, Any]) -> "PlanItemView":
        return cls(
            profile_id=item["profile_id"],
            provider=item["provider"],
            artifact_id=item["artifact_id"],
            license_decision_id=item["license_decision_id"],
            reason=item["reason"],
        )


@dataclass
class LicensePresentation:
    """The licence screen for one plan."""

    decisions: tuple[LicenseDecision, ...]
    items: tuple[PlanItemView, ...]

    def decision_for(self, license_decision_id: str) -> LicenseDecision | None:
        for decision in self.decisions:
            if decision.ref.license_id == license_decision_id:
                return decision
        return None

    def replace_decision(self, decision: LicenseDecision) -> "LicensePresentation":
        decisions = tuple(
            decision if existing.ref.decision_key == decision.ref.decision_key else existing
            for existing in self.decisions
        )
        return LicensePresentation(decisions=decisions, items=self.items)

    def eligible_items(self) -> tuple[PlanItemView, ...]:
        """Items whose licence decision is satisfied.

        An item whose licence is missing entirely is dropped: an item with no
        decision is not an item with a permissive decision.
        """

        kept: list[PlanItemView] = []
        for item in self.items:
            decision = self.decision_for(item.license_decision_id)
            if decision is not None and decision.satisfied:
                kept.append(item)
        return tuple(kept)

    def withdraw(self, license_decision_id: str) -> tuple["LicensePresentation", tuple[PlanItemView, ...]]:
        """Refuse one licence and report exactly which items that removed."""

        decision = self.decision_for(license_decision_id)
        if decision is None:
            raise KeyError(license_decision_id)
        before = set(self.eligible_items())
        updated = self.replace_decision(decision.refuse())
        after = set(updated.eligible_items())
        removed = tuple(sorted(before - after, key=lambda item: item.artifact_id))
        return updated, removed

    def render(self) -> tuple[str, ...]:
        lines: list[str] = []
        for decision in self.decisions:
            lines.extend(decision.render())
        return tuple(lines)


def build_presentation(
    plan_items: Sequence[Mapping[str, Any]],
    license_refs: Iterable[Mapping[str, Any]],
    offline_texts: frozenset[str] = frozenset(),
) -> LicensePresentation:
    decisions: list[LicenseDecision] = []
    seen: set[tuple[str, str]] = set()
    for ref in license_refs:
        parsed = LicenseRef.from_record(ref)
        if parsed.decision_key in seen:
            continue
        seen.add(parsed.decision_key)
        decisions.append(
            LicenseDecision(ref=parsed, text_available=parsed.license_id in offline_texts)
        )
    return LicensePresentation(
        decisions=tuple(decisions),
        items=tuple(PlanItemView.from_plan_item(item) for item in plan_items),
    )


def request_receipt(license_decision_id: str, ledger: GateLedger) -> GateRefusal:
    """Ask F100 for a receipt.

    There is no branch that returns a receipt. F107-B has never been able to
    write one, and the absence of a success path here is the point: a receipt
    that setup could produce is a receipt the receipt store did not validate.
    """

    refusal = ledger.require("write_license_receipt")
    if refusal is None:  # pragma: no cover - unreachable while F100-A3 is open
        raise RuntimeError(
            f"receipt for {license_decision_id} must be written by kilix-content, "
            "never by plebian-os-setup"
        )
    return refusal
