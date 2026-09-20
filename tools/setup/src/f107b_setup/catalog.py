"""The generic optional-component offer and its consent boundary.

F107-B ships **no component-specific control**. The wizard renders whatever
``plebian.setup.optional-component/v1`` records the catalog carries, and
nothing else. If a component's record is absent, nothing is drawn: absence is
indistinguishable from declining, so no dead or inert control ever ships.

The consent boundary is the load-bearing part. Accepting a vendor's terms and
granting that vendor standing root-equivalent package authority are **two acts
and two decisions**. This module cannot express them as one: ``Consent``
carries two independent fields and ``may_invoke_provider`` requires both, plus
an open gate check, before it will say yes.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from jsonschema import Draft202012Validator

from .gates import GateLedger, GateRefusal

#: A population bound. A catalog that exceeds it is refused rather than
#: truncated, because a truncated offer list silently hides a disclosure.
MAX_RECORDS = 64

SCHEMA_ID = "plebian.setup.optional-component/v1"


class CatalogError(ValueError):
    """The catalog cannot be rendered as an offer list."""


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CatalogError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicates)


@dataclass(frozen=True)
class Consent:
    """Two separate acts, recorded separately.

    ``license_accepted`` is a ``kilix.install.license/v1`` decision.
    ``authorization_granted`` is a ``kilix.install.authorization/v2`` decision.
    Neither implies the other, and there is no constructor that sets both from
    one operator action.
    """

    license_accepted: bool = False
    authorization_granted: bool = False

    def accept_license(self) -> "Consent":
        return Consent(True, self.authorization_granted)

    def grant_authorization(self) -> "Consent":
        return Consent(self.license_accepted, True)

    @property
    def complete(self) -> bool:
        return self.license_accepted and self.authorization_granted

    def missing(self) -> tuple[str, ...]:
        absent = []
        if not self.license_accepted:
            absent.append("kilix.install.license/v1 acceptance")
        if not self.authorization_granted:
            absent.append("kilix.install.authorization/v2 grant")
        return tuple(absent)


@dataclass(frozen=True)
class Offer:
    """One rendered offer. Selected is ``False`` on construction, always."""

    record: dict[str, Any]
    selected: bool = False
    consent: Consent = Consent()

    @property
    def offer_id(self) -> str:
        return self.record["id"]

    @property
    def label(self) -> str:
        return self.record["label"]

    @property
    def provider(self) -> str:
        return self.record["provider"]

    def select(self) -> "Offer":
        return Offer(self.record, True, self.consent)

    def deselect(self) -> "Offer":
        """Deselecting drops the consent with it; consent is not sticky."""

        return Offer(self.record, False, Consent())

    def with_consent(self, consent: Consent) -> "Offer":
        return Offer(self.record, self.selected, consent)

    def disclosure_lines(self) -> tuple[str, ...]:
        lines: list[str] = []
        for disclosure in self.record["disclosures"]:
            lines.append(f"[{disclosure['kind']}] {disclosure['subject']}: {disclosure['text']}")
        return tuple(lines)


@dataclass
class OptionalComponentCatalog:
    """A validated, deterministically ordered offer population."""

    offers: tuple[Offer, ...] = ()

    @property
    def population(self) -> int:
        return len(self.offers)

    @property
    def empty(self) -> bool:
        return not self.offers

    def get(self, offer_id: str) -> Offer:
        for offer in self.offers:
            if offer.offer_id == offer_id:
                return offer
        raise KeyError(offer_id)

    def replace(self, offer: Offer) -> "OptionalComponentCatalog":
        offers = tuple(
            offer if existing.offer_id == offer.offer_id else existing for existing in self.offers
        )
        return OptionalComponentCatalog(offers)

    def selected(self) -> tuple[Offer, ...]:
        return tuple(offer for offer in self.offers if offer.selected)

    def render(self) -> tuple[str, ...]:
        """The operator-visible offer list.

        An empty population renders one honest line and no control. It does not
        render a disabled checkbox, a "coming soon" row, or a placeholder.
        """

        if self.empty:
            return ("No optional components are offered on this system.",)
        lines: list[str] = []
        for offer in self.offers:
            box = "[x]" if offer.selected else "[ ]"
            lines.append(f"{box} {offer.label}  ({offer.offer_id})")
            lines.extend(f"      {line}" for line in offer.disclosure_lines())
            lines.append(
                "      Two separate decisions are required: accept the vendor terms, "
                "and separately grant standing package authority."
            )
        return tuple(lines)


def build_catalog(
    records: Sequence[dict[str, Any]], schema_path: Path
) -> OptionalComponentCatalog:
    """Validate, de-duplicate and order a record population.

    Every offer comes back **deselected**. There is no argument that changes
    that, so a catalog cannot ship a pre-ticked box.
    """

    schema = load_json(schema_path)
    if schema.get("$id") != SCHEMA_ID:
        raise CatalogError(f"schema identity is {schema.get('$id')!r}, expected {SCHEMA_ID!r}")
    validator = Draft202012Validator(schema)

    if len(records) > MAX_RECORDS:
        raise CatalogError(f"record population exceeds {MAX_RECORDS}/{MAX_RECORDS}")

    seen: set[str] = set()
    validated: list[dict[str, Any]] = []
    for record in records:
        errors = sorted(validator.iter_errors(record), key=lambda error: list(error.absolute_path))
        if errors:
            raise CatalogError(f"invalid optional-component record: {errors[0].message}")
        if record["id"] in seen:
            raise CatalogError(f"duplicate record id: {record['id']}")
        seen.add(record["id"])
        validated.append(copy.deepcopy(record))

    ordered = sorted(validated, key=lambda record: record["id"])
    return OptionalComponentCatalog(tuple(Offer(record=record) for record in ordered))


def load_catalog(paths: Iterable[Path], schema_path: Path) -> OptionalComponentCatalog:
    return build_catalog([load_json(path) for path in paths], schema_path)


def may_invoke_provider(offer: Offer, ledger: GateLedger) -> GateRefusal | str | None:
    """Decide whether an offer's provider transaction may run.

    Returns ``None`` when it may, a ``str`` naming the missing consent when the
    operator has not given both decisions, and a ``GateRefusal`` when a release
    gate blocks it. The three outcomes are distinct on purpose: "you have not
    consented" and "the release is not ready" are different answers and the
    operator is owed the right one.
    """

    if not offer.selected:
        return "the offer is not selected"
    missing = offer.consent.missing()
    if missing:
        return "missing " + " and ".join(missing)
    return ledger.require("invoke_provider")
