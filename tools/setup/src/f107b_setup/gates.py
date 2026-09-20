"""F107-B entry and qualification gates.

Every gate here is a *release* gate owned by another stream. This module is the
single place that names them, so no other module may decide on its own that a
gate has closed. A gate is closed only when its recorded evidence is present;
absence is never optimism.

Nothing in this package may be reached by a caller that has not consulted the
ledger first. Gate-dependent operations return a ``GateRefusal`` result rather
than raising, so a refusal is a value the wizard renders, not an error path a
caller can accidentally swallow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class Gate:
    """One release gate F107-B does not own."""

    gate_id: str
    owner: str
    condition: str
    evidence_required: str
    #: Set only when the owning stream has produced the named evidence.
    satisfied: bool = False
    #: What the ledger measured when it last looked, verbatim.
    observed: str = ""


@dataclass(frozen=True)
class GateRefusal:
    """A refusal is a first-class result, never a silent default."""

    capability: str
    gates: tuple[Gate, ...]

    @property
    def refused(self) -> bool:
        return True

    def render(self) -> tuple[str, ...]:
        lines = [f"BLOCKED: {self.capability}"]
        for gate in self.gates:
            lines.append(f"  gate      {gate.gate_id}")
            lines.append(f"  owner     {gate.owner}")
            lines.append(f"  condition {gate.condition}")
            lines.append(f"  evidence  {gate.evidence_required}")
            lines.append(f"  observed  {gate.observed}")
        return tuple(lines)


#: F100 A3. Track A's dispatch: "A3 freezes the F100-C0 capacity contract,
#: which is what unblocks Track D."
F100_A3 = Gate(
    gate_id="F100-A3",
    owner="Track A / F100 owner",
    condition=(
        "F100 freezes the F100-C0 capacity-reserve contract and publishes its "
        "exact identity, path, version and digest"
    ),
    evidence_required=(
        "a capacity-contract artifact whose identity, source_commit and "
        "source_sha256 are all non-null, so plebian.models.* documents can "
        "report capacity_contract status 'resolved'"
    ),
    satisfied=False,
    observed=(
        "F100 is at U1 R16 serial integration; 0 of 17 R16 rows admitted and "
        "U5 not entered. Every F106 fixture reports capacity status 'missing'."
    ),
)

#: F106 P1. F107-B is a named signatory, so it cannot sign a freeze that does
#: not exist, and cannot treat a reviewable candidate as one.
F106_P1 = Gate(
    gate_id="F106-P1",
    owner="Track D / F106 owner (joint signatories include F107-B)",
    condition=(
        "the F106 P1 joint freeze of the plebian-hardware / plebian-model-sizer "
        "schemas and invocation contract, signed identical-byte by every named "
        "signatory"
    ),
    evidence_required=(
        "a successor identical-byte P1 manifest disposing the open Track C "
        "findings, followed by the named joint review and signatures over that "
        "exact manifest"
    ),
    satisfied=False,
    observed=(
        "The current Track D input is the R2 handoff at CANDIDATE-SHA256SUMS "
        "2341c763c4ee7958387335f01a5274155311239e3c82572b1855521dc85d37f4, "
        "which states in its own text that it is NOT the P1 joint freeze."
    ),
)

#: Phase 0 item 0.3. Qualification only; it does not gate construction.
PHASE0_0_3 = Gate(
    gate_id="PHASE0-0.3",
    owner="release owner (Phase 0 item 0.3)",
    condition=(
        "real plebian-hardware and plebian-model-sizer binaries executed on "
        "real hardware from the frozen matrix"
    ),
    evidence_required="live-probe hardware documents with capture.qualification_eligible true",
    satisfied=False,
    observed=(
        "Only synthetic-contract and redacted fixtures exist; every one of them "
        "sets capture.qualification_eligible false."
    ),
)

#: The product surface itself. Measured, not assumed.
SETUP_SURFACE = Gate(
    gate_id="F107-B-SURFACE",
    owner="Track C / F107-B (this stream), gated by F100-A3 and F106-P1",
    condition=(
        "a plebian-os-setup application and a plebian.setup/v1 surface exist in "
        "a product root"
    ),
    evidence_required="a plebian-os-setup package or plebian.setup/v1 schema in a product repository",
    satisfied=False,
    observed="0 of 4 searched product roots carry either surface.",
)


LEDGER: Mapping[str, Gate] = {
    gate.gate_id: gate
    for gate in (F100_A3, F106_P1, PHASE0_0_3, SETUP_SURFACE)
}


#: Which gates each gate-dependent capability needs. A capability absent from
#: this map is gate-free and may run against fixtures.
CAPABILITY_GATES: Mapping[str, tuple[str, ...]] = {
    # Checkpoint 5's fit and plan presentation needs frozen reserves before any
    # number it shows can mean anything.
    "present_positive_fit": ("F100-A3",),
    "present_recommendation": ("F100-A3", "PHASE0-0.3"),
    "execute_plan": ("F100-A3", "F106-P1"),
    # A licence receipt is F100's to write. F107-B presents only.
    "write_license_receipt": ("F100-A3",),
    # Invoking a real provider needs the frozen invocation contract.
    "invoke_provider": ("F100-A3", "F106-P1"),
    # Landing the wizard in a product repository needs both entry gates.
    "land_product_surface": ("F100-A3", "F106-P1"),
    # Signing the freeze F107-B is a signatory to needs the freeze to exist.
    "sign_f106_p1": ("F106-P1",),
    # Any qualification claim about hardware or model performance.
    "claim_qualification": ("F100-A3", "F106-P1", "PHASE0-0.3"),
}


@dataclass
class GateLedger:
    """Resolves capabilities against the recorded gate states."""

    gates: Mapping[str, Gate] = field(default_factory=lambda: dict(LEDGER))
    capabilities: Mapping[str, tuple[str, ...]] = field(
        default_factory=lambda: dict(CAPABILITY_GATES)
    )

    def open_gates(self) -> tuple[Gate, ...]:
        return tuple(gate for gate in self.gates.values() if not gate.satisfied)

    def check(self, capability: str) -> GateRefusal | None:
        """Return a refusal when *capability* is gated, or ``None`` when free.

        An unknown capability is refused on every open gate rather than
        allowed: a capability nobody classified is not a capability anybody
        cleared.
        """

        try:
            required = self.capabilities[capability]
        except KeyError:
            blocking = self.open_gates()
            if not blocking:
                return None
            return GateRefusal(capability=f"{capability} (unclassified)", gates=blocking)

        blocking = tuple(
            self.gates[gate_id] for gate_id in required if not self.gates[gate_id].satisfied
        )
        if not blocking:
            return None
        return GateRefusal(capability=capability, gates=blocking)

    def require(self, capability: str) -> GateRefusal | None:
        return self.check(capability)
