"""Consumer-side admission rules for F106 documents.

Track D's candidate ships a producer-side validator. F107-B does not rely on
it. A producer that has broken an invariant is exactly the producer whose
self-check cannot be trusted, so every invariant F107-B's behaviour depends on
is re-derived here, from the document alone.

These rules are deliberately one-directional. They can only *refuse* a claim;
they never upgrade one. A document that passes admission has not been declared
correct — it has only failed to be caught, which is why the wizard still shows
unknowns and blockers rather than hiding them.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Any, Iterable

#: A MAC address in any of the three spellings a probe might emit.
MAC_PATTERN = re.compile(r"\b(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}\b")

#: Backend evidence that can support an ``available`` claim. Anything else —
#: notably a PCI identity — cannot.
SUCCESSFUL_PROBE_EVIDENCE = frozenset(
    {"api-query", "device-open", "executable-probe", "runtime-query"}
)

UNSUCCESSFUL_PROBE_EVIDENCE = frozenset({"command-unavailable", "contradictory", "unknown"})

#: A fit verdict that asserts something positive about capacity.
POSITIVE_VERDICTS = frozenset({"does-not-fit", "fits-tightly", "fits", "recommended"})

#: Identifiers that must never appear in a hardware document, at any depth.
PROHIBITED_KEYS = frozenset(
    {
        "asset_tag",
        "hostname",
        "ip_address",
        "mac_address",
        "machine_id",
        "serial_number",
        "system_uuid",
        "username",
    }
)

FIXTURE_SOURCES = frozenset({"synthetic-contract", "redacted-observation"})


@dataclass(frozen=True)
class Admission:
    """The result of re-deriving a document's fail-closed invariants."""

    identity: str
    findings: tuple[str, ...]

    @property
    def admitted(self) -> bool:
        return not self.findings


def _looks_like_address(text: str) -> str | None:
    """Name the address class a string carries, or ``None``.

    Interface names, CPU-list text, DRM connector names and PCI bus addresses
    are transient facts the contract permits. An IP or MAC address is not one
    of them at any depth, whatever key it hides behind.
    """

    candidate = text.strip()
    if MAC_PATTERN.search(candidate):
        return "MAC address"
    # ``ip_address`` accepts bare integers and other surprises, so require the
    # shape of an address before asking it.
    if ":" in candidate or (candidate.count(".") == 3 and candidate.replace(".", "").isdigit()):
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            return None
        return "IP address"
    return None


def _prohibited_identifier_findings(value: Any, trail: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in PROHIBITED_KEYS and item not in (None, [], {}):
                # ``never_collected`` is the denylist itself, not a carrier.
                if not trail.endswith("never_collected"):
                    findings.append(f"prohibited identifier populated at {trail}.{key}")
            findings.extend(_prohibited_identifier_findings(item, f"{trail}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            findings.extend(_prohibited_identifier_findings(item, f"{trail}[{index}]"))
    elif isinstance(value, str):
        address_class = _looks_like_address(value)
        if address_class is not None:
            findings.append(f"{address_class} carried at {trail}")
    return findings


def _admit_hardware(document: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    capture = document.get("capture", {})
    source = capture.get("source")
    eligible = capture.get("qualification_eligible")

    if source in FIXTURE_SOURCES and eligible:
        findings.append("synthetic or redacted capture claims qualification eligibility")

    expected_never = sorted(PROHIBITED_KEYS)
    if document.get("never_collected") != expected_never:
        findings.append("never_collected is not the frozen sorted denylist")

    findings.extend(
        finding
        for finding in _prohibited_identifier_findings(
            {key: value for key, value in document.items() if key != "never_collected"}
        )
    )

    unknowns = document.get("unknowns", [])
    if list(unknowns) != sorted(set(unknowns)):
        findings.append("hardware unknowns are not sorted and unique")

    gpus = document.get("gpus", [])
    if [gpu.get("index") for gpu in gpus] != list(range(len(gpus))):
        findings.append("GPU indexes are not contiguous from zero")

    for position, gpu in enumerate(gpus):
        backends = gpu.get("backends", [])
        names = [backend.get("name") for backend in backends]
        if names != sorted(set(names)):
            findings.append(f"gpu {position} backends are not sorted and unique")
        for backend in backends:
            status = backend.get("status")
            evidence = backend.get("evidence")
            if status == "available" and evidence not in SUCCESSFUL_PROBE_EVIDENCE:
                findings.append(
                    f"gpu {position} backend {backend.get('name')!r} claims availability "
                    f"on evidence {evidence!r}"
                )
            if evidence in UNSUCCESSFUL_PROBE_EVIDENCE and status != "unknown":
                findings.append(
                    f"gpu {position} backend {backend.get('name')!r} has an unsuccessful "
                    f"probe but status {status!r}"
                )
            if backend.get("version") is not None and status != "available":
                findings.append(
                    f"gpu {position} backend {backend.get('name')!r} reports a version "
                    "without being available"
                )

    interfaces = document.get("network", {}).get("interfaces", [])
    if [interface.get("index") for interface in interfaces] != list(range(len(interfaces))):
        findings.append("network interface indexes are not contiguous from zero")

    batteries = document.get("power", {}).get("batteries", [])
    if [battery.get("index") for battery in batteries] != list(range(len(batteries))):
        findings.append("battery indexes are not contiguous from zero")

    privacy = document.get("privacy")
    if isinstance(privacy, dict):
        if privacy.get("telemetry_eligible") is not False:
            findings.append(
                "a hardware observation declares itself telemetry-eligible; F107-B "
                "consumes local-only inventory and exports none of it"
            )
        if privacy.get("classification") not in {"fingerprinting-grade-local", "local-only"}:
            findings.append(
                f"privacy classification {privacy.get('classification')!r} is not a local-only class"
            )
    elif source in {"live-probe", "redacted-observation"}:
        findings.append("an observed hardware document carries no privacy classification")

    return findings


def _admit_fit_result(document: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    capacity = document.get("capacity_contract", {})
    status = capacity.get("status")
    verdict = document.get("overall_verdict")
    performance = document.get("performance", {})

    if status == "missing":
        if verdict in POSITIVE_VERDICTS:
            findings.append(f"verdict {verdict!r} asserted without a resolved capacity contract")
        for key in ("identity", "source_commit", "source_sha256"):
            if capacity.get(key) is not None:
                findings.append(f"missing capacity contract carries an invented {key}")
        for index, resource in enumerate(document.get("resources", [])):
            if resource.get("verdict") != "unknown":
                findings.append(
                    f"resource {index} ({resource.get('kind')}) has verdict "
                    f"{resource.get('verdict')!r} without frozen reserves"
                )
            for key in ("available_bytes", "reserve_bytes"):
                if resource.get(key) is not None:
                    findings.append(
                        f"resource {index} ({resource.get('kind')}) reports {key} "
                        "without frozen reserves"
                    )

    numbers = [performance.get(name) for name in ("first_result_ms", "realtime_factor", "tokens_per_second")]
    if any(value is not None for value in numbers) and performance.get("comparable") is not True:
        findings.append("performance numbers are not bound to comparable hardware")

    if verdict == "recommended":
        if not (
            document.get("qualification_eligible") is True
            and status == "resolved"
            and performance.get("verdict") == "recommended"
            and performance.get("comparable") is True
        ):
            findings.append("recommendation lacks qualified, comparable, capacity-bound evidence")

    if performance.get("verdict") == "recommended" and performance.get("comparable") is not True:
        findings.append("performance recommendation is not comparable")

    return findings


def _admit_install_plan(document: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    status = document.get("status")
    capacity = document.get("capacity_contract_status")
    executable = document.get("executable")
    totals = document.get("totals", {})
    receipts = document.get("authorization_receipts", [])
    items = document.get("items", [])

    if status == "blocked" and executable:
        findings.append("a blocked plan is marked executable")

    if capacity == "missing":
        if status == "ready" or executable:
            findings.append("a plan without a resolved capacity contract claims readiness")
        for key, value in totals.items():
            if value is not None:
                findings.append(f"totals.{key} is populated without frozen reserves")

    if status == "ready":
        if not items:
            findings.append("a ready plan selects no items")
        if not receipts:
            findings.append("a ready plan carries no authorization receipts")
        for index, receipt in enumerate(receipts):
            if not receipt.get("present") or not receipt.get("receipt_sha256"):
                findings.append(f"ready plan receipt {index} is absent or unhashed")

    if document.get("confirmation", {}).get("granted") is not False:
        findings.append("the plan document synthesizes user confirmation")
    if document.get("confirmation", {}).get("required") is not True:
        findings.append("the plan document waives the confirmation requirement")

    for index, item in enumerate(items):
        if not item.get("license_decision_id"):
            findings.append(f"plan item {index} carries no licence decision")

    return findings


def _admit_snapshot(document: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    capacity = document.get("capacity_contract", {})
    if capacity.get("status") == "missing":
        if document.get("qualification_eligible"):
            findings.append("a snapshot without frozen reserves claims qualification eligibility")
        if capacity.get("identity") is not None:
            findings.append("missing capacity contract carries an invented identity")
    unknowns = document.get("unknowns", [])
    if list(unknowns) != sorted(set(unknowns)):
        findings.append("snapshot unknowns are not sorted and unique")
    telemetry = document.get("telemetry", {})
    if telemetry.get("available") is False and telemetry.get("fresh") not in (None, False):
        findings.append("unavailable telemetry is reported as fresh")
    return findings


_RULES = {
    "plebian.hardware/v1": _admit_hardware,
    "plebian.models.fit-result/v1": _admit_fit_result,
    "plebian.models.install-plan/v1": _admit_install_plan,
    "plebian.models.snapshot/v1": _admit_snapshot,
}


def admit(document: dict[str, Any]) -> Admission:
    """Re-derive the fail-closed invariants of one F106 data document."""

    identity = document.get("schema")
    if not isinstance(identity, str) or identity not in _RULES:
        return Admission(
            identity=str(identity),
            findings=(f"no consumer admission rule exists for schema {identity!r}",),
        )
    return Admission(identity=identity, findings=tuple(_RULES[identity](document)))


def admit_all(documents: Iterable[dict[str, Any]]) -> tuple[Admission, ...]:
    return tuple(admit(document) for document in documents)
