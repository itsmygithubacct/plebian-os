"""The model-aware plan: hardware report, fit, and the reviewed plan.

Two rules run through every function here.

**Unknown is a value, not a zero.** ``null`` from F106 means "not measured".
Rendering it as ``0 B`` would turn a missing measurement into a confident
claim of nothing, and every arithmetic path below refuses to participate: a
total that includes one unknown addend is unknown, not the sum of the rest.

**A blocked plan is an outcome, not a failure.** Optional model work that
cannot proceed leaves a complete, bootable, setup-complete machine. Nothing in
this module can roll back core setup, and nothing in it can invoke a provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .admission import Admission, admit
from .gates import GateLedger, GateRefusal

UNKNOWN = "unknown"

_UNITS = ("B", "KiB", "MiB", "GiB", "TiB")


def format_bytes(value: int | None) -> str:
    """Render a byte count, or the word ``unknown``. Never ``0`` for ``None``."""

    if value is None:
        return UNKNOWN
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"not a byte count: {value!r}")
    size = float(value)
    for unit in _UNITS:
        if size < 1024 or unit == _UNITS[-1]:
            if unit == "B":
                return f"{value} B"
            return f"{size:.1f} {unit}"
        size /= 1024
    raise AssertionError("unreachable")


def sum_or_unknown(values: Sequence[int | None]) -> int | None:
    """Add byte counts, propagating unknown.

    One unmeasured addend makes the whole sum unmeasured. An empty sequence is
    ``0``, because nothing selected really is nothing.
    """

    total = 0
    for value in values:
        if value is None:
            return None
        total += value
    return total


@dataclass(frozen=True)
class HardwareReport:
    """Checkpoint 4 — what the machine is, including what is not known."""

    document: Mapping[str, Any]
    admission: Admission

    @property
    def usable(self) -> bool:
        return self.admission.admitted

    def render(self) -> tuple[str, ...]:
        if not self.usable:
            return ("Hardware report withheld: the reported inventory failed consumer admission.",) + tuple(
                f"  finding: {finding}" for finding in self.admission.findings
            )
        cpu = self.document.get("cpu", {})
        memory = self.document.get("memory", {})
        storage = self.document.get("storage", {})
        lines = [
            f"CPU: {cpu.get('architecture', UNKNOWN)}, "
            f"{cpu.get('effective_cpus', UNKNOWN)} effective of "
            f"{cpu.get('logical_cpus', UNKNOWN)} logical",
            f"Memory: {format_bytes(memory.get('total_bytes'))} total, "
            f"{format_bytes(memory.get('available_bytes'))} available",
            f"Model store free: {format_bytes(storage.get('free_bytes'))}",
        ]
        for gpu in self.document.get("gpus", []):
            backends = ", ".join(
                f"{backend['name']}={backend['status']}" for backend in gpu.get("backends", [])
            )
            lines.append(
                f"GPU {gpu.get('index')}: {gpu.get('vendor')} {gpu.get('device_class')}, "
                f"VRAM {format_bytes(gpu.get('vram_bytes'))}; {backends or 'no backends probed'}"
            )
        unknowns = self.document.get("unknowns", [])
        if unknowns:
            lines.append(f"Not determined ({len(unknowns)}): " + ", ".join(unknowns))
        capture = self.document.get("capture", {})
        if not capture.get("qualification_eligible"):
            lines.append(
                "This report is not qualification evidence: "
                f"capture source is {capture.get('source', UNKNOWN)}."
            )
        return tuple(lines)


@dataclass(frozen=True)
class FitView:
    """Checkpoint 5 — the sizer's answer for one task."""

    document: Mapping[str, Any]
    admission: Admission

    @property
    def verdict(self) -> str:
        return self.document.get("overall_verdict", UNKNOWN)

    def presentable_recommendation(self, ledger: GateLedger) -> GateRefusal | str | None:
        """May the wizard present this as a recommendation?

        ``None`` means yes. A ``str`` means the result itself does not claim
        one. A ``GateRefusal`` means the release is not in a state where any
        recommendation could be believed.
        """

        if not self.admission.admitted:
            return "the fit result failed consumer admission"
        if self.verdict != "recommended":
            return f"the sizer reported {self.verdict!r}, not a recommendation"
        return ledger.require("present_recommendation")

    def render(self) -> tuple[str, ...]:
        if not self.admission.admitted:
            return ("Fit result withheld: it failed consumer admission.",) + tuple(
                f"  finding: {finding}" for finding in self.admission.findings
            )
        capacity = self.document.get("capacity_contract", {})
        lines = [
            f"Task profile: {self.document.get('profile_id', UNKNOWN)}",
            f"Verdict: {self.verdict}",
            f"Capacity reserves: {capacity.get('status', UNKNOWN)}",
        ]
        for resource in self.document.get("resources", []):
            lines.append(
                f"  {resource.get('kind')}: needs {format_bytes(resource.get('required_bytes'))}, "
                f"available {format_bytes(resource.get('available_bytes'))}, "
                f"reserve {format_bytes(resource.get('reserve_bytes'))} "
                f"-> {resource.get('verdict', UNKNOWN)}"
            )
        performance = self.document.get("performance", {})
        lines.append(
            f"  performance: {performance.get('verdict', UNKNOWN)} "
            f"(comparable: {performance.get('comparable')})"
        )
        for reason in self.document.get("reasons", []):
            lines.append(f"  why: [{reason.get('code')}] {reason.get('message')}")
        return tuple(lines)


@dataclass(frozen=True)
class PlanReview:
    """Checkpoint 8 — the exact plan, its sizes, licences and blockers."""

    document: Mapping[str, Any]
    admission: Admission

    @property
    def status(self) -> str:
        return self.document.get("status", UNKNOWN)

    @property
    def blocked(self) -> bool:
        return self.status != "ready" or not self.document.get("executable")

    def totals(self) -> Mapping[str, int | None]:
        return dict(self.document.get("totals", {}))

    def blockers(self) -> tuple[Mapping[str, str], ...]:
        return tuple(self.document.get("blockers", []))

    def may_execute(self, ledger: GateLedger, confirmed: bool) -> GateRefusal | str | None:
        """Whether the plan may be handed to the sizer's install command.

        ``confirmed`` is the operator's separate confirmation act. Holding a
        plan path is not consent, so it is a parameter rather than something
        read out of the plan document.
        """

        if not self.admission.admitted:
            return "the plan failed consumer admission"
        if self.blocked:
            return f"the plan is {self.status}, not executable"
        if not confirmed:
            return "the operator has not confirmed this plan"
        return ledger.require("execute_plan")

    def render(self) -> tuple[str, ...]:
        if not self.admission.admitted:
            return ("Plan withheld: it failed consumer admission.",) + tuple(
                f"  finding: {finding}" for finding in self.admission.findings
            )
        totals = self.totals()
        lines = [
            f"Plan {self.document.get('plan_id', UNKNOWN)} "
            f"(preset {self.document.get('preset', UNKNOWN)}): {self.status}",
            f"Capacity reserves: {self.document.get('capacity_contract_status', UNKNOWN)}",
            f"Download: {format_bytes(totals.get('download_bytes'))}   "
            f"Installed: {format_bytes(totals.get('installed_bytes'))}",
            f"Temporary: {format_bytes(totals.get('temporary_bytes'))}   "
            f"Shared: {format_bytes(totals.get('shared_bytes'))}",
        ]
        items = self.document.get("items", [])
        if items:
            for item in items:
                lines.append(
                    f"  {item.get('artifact_id')} via {item.get('provider')} "
                    f"(licence {item.get('license_decision_id')}): {item.get('reason')}"
                )
        else:
            lines.append("  No items are selected.")
        receipts = self.document.get("authorization_receipts", [])
        lines.append(
            f"  Authorization receipts: {sum(1 for r in receipts if r.get('present'))}"
            f"/{len(receipts)} present"
        )
        confirmation = self.document.get("confirmation", {})
        lines.append(
            f"  Confirmation: required={confirmation.get('required')}, "
            f"granted={confirmation.get('granted')} (setup never grants this on the operator's behalf)"
        )
        for blocker in self.blockers():
            lines.append(f"  blocked: [{blocker.get('code')}] {blocker.get('message')}")
        if self.blocked:
            lines.append(
                "  Optional model setup will not run. The core system is complete "
                "and unaffected."
            )
        return tuple(lines)


def hardware_report(document: Mapping[str, Any]) -> HardwareReport:
    return HardwareReport(document=document, admission=admit(dict(document)))


def fit_view(document: Mapping[str, Any]) -> FitView:
    return FitView(document=document, admission=admit(dict(document)))


def plan_review(document: Mapping[str, Any]) -> PlanReview:
    return PlanReview(document=document, admission=admit(dict(document)))
