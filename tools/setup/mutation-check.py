#!/usr/bin/env python3
"""Anti-vacuity: break each invariant on purpose and require the suite to notice.

A suite that passes on the first run has proved nothing until it has been shown
to fail. Each mutation below removes exactly one of the behaviours this packet
claims. Every one must turn the suite red, and the run is only credible if the
count of caught mutations equals the count applied.

Each mutation is applied to a working copy of one source file, the suite is run,
and the file is restored whatever happens.

    uv run --project ../f120-contracts --locked --offline python mutation-check.py
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src" / "f107b_setup"


@dataclass(frozen=True)
class Mutation:
    label: str
    path: Path
    old: str
    new: str
    claim: str


MUTATIONS: tuple[Mutation, ...] = (
    Mutation(
        label="unknown-becomes-zero",
        path=SRC / "plan.py",
        old='    if value is None:\n        return UNKNOWN',
        new='    if value is None:\n        return "0 B"',
        claim="an unmeasured size is rendered as unknown, never as zero",
    ),
    Mutation(
        label="offer-defaults-on",
        path=SRC / "catalog.py",
        old="    record: dict[str, Any]\n    selected: bool = False",
        new="    record: dict[str, Any]\n    selected: bool = True",
        claim="every optional-component offer defaults off",
    ),
    Mutation(
        label="one-act-consent",
        path=SRC / "catalog.py",
        old="    def missing(self) -> tuple[str, ...]:\n        absent = []",
        new="    def missing(self) -> tuple[str, ...]:\n        return ()\n        absent = []",
        claim="licence acceptance and package authority are two separate acts",
    ),
    Mutation(
        label="positive-fit-without-reserves",
        path=SRC / "admission.py",
        old='        if verdict in POSITIVE_VERDICTS:\n            findings.append(f"verdict {verdict!r} asserted without a resolved capacity contract")',
        new='        if False:\n            findings.append(f"verdict {verdict!r} asserted without a resolved capacity contract")',
        claim="no positive fit verdict survives a missing capacity contract",
    ),
    Mutation(
        label="pci-implies-backend",
        path=SRC / "admission.py",
        old="            if status == \"available\" and evidence not in SUCCESSFUL_PROBE_EVIDENCE:",
        new="            if False and evidence not in SUCCESSFUL_PROBE_EVIDENCE:",
        claim="a backend is available only on a successful runtime probe",
    ),
    Mutation(
        label="gate-declared-closed",
        path=SRC / "gates.py",
        old='    satisfied=False,\n    observed=(\n        "F100 is at U1 R16 serial integration;',
        new='    satisfied=True,\n    observed=(\n        "F100 is at U1 R16 serial integration;',
        claim="F100-A3 is recorded as open",
    ),
    Mutation(
        label="unclassified-capability-allowed",
        path=SRC / "gates.py",
        old="        except KeyError:\n            blocking = self.open_gates()",
        new="        except KeyError:\n            return None\n            blocking = self.open_gates()",
        claim="a capability nobody classified is refused, not allowed",
    ),
    Mutation(
        label="silent-state-migration",
        path=SRC / "state.py",
        old='        if version < STATE_VERSION:\n            raise StaleState(',
        new='        if False:\n            raise StaleState(',
        claim="an older state version is refused rather than migrated silently",
    ),
    Mutation(
        label="stderr-on-success-tolerated",
        path=SRC / "f106_client.py",
        old='        if stderr:\n            raise ContractViolation("exit 0 did not leave stderr empty")',
        new='        if False:\n            raise ContractViolation("exit 0 did not leave stderr empty")',
        claim="exit 0 with a dirty stderr is a contract violation",
    ),
    Mutation(
        label="ambient-environment-inherited",
        path=SRC / "f106_client.py",
        old='    return {"LC_ALL": "C.UTF-8", "LANG": "C.UTF-8", "PATH": path}',
        new='    return {**os.environ, "LC_ALL": "C.UTF-8", "LANG": "C.UTF-8", "PATH": path}',
        claim="the child environment is reduced, not inherited",
    ),
    Mutation(
        label="notice-grows-a-checkbox",
        path=SRC / "licenses.py",
        old="    def requires_decision(self) -> bool:\n        return self.decision_class in REQUIRES_DECISION",
        new="    def requires_decision(self) -> bool:\n        return True",
        claim="an informational notice never grows a checkbox",
    ),
    Mutation(
        label="unknown-disposition-permitted",
        path=SRC / "licenses.py",
        old="        decision_class = declared if declared in KNOWN_CLASSES else RESTRICTED",
        new="        decision_class = declared if declared in KNOWN_CLASSES else INFORMATIONAL",
        claim="an unknown licence disposition fails closed as use-restricted",
    ),
    Mutation(
        label="group-wide-nopasswd",
        path=SRC / "sudoers.py",
        old='    if account.startswith(FORBIDDEN_PREFIXES):\n        raise SudoersRefusal(',
        new='    if False:\n        raise SudoersRefusal(',
        claim="NOPASSWD is granted to one account, never a group",
    ),
    Mutation(
        label="third-party-browser-offered",
        path=SRC / "browsers.py",
        old='        if candidate.component != "main":',
        new='        if False:',
        claim="every offered browser comes from Debian main",
    ),
    Mutation(
        label="empty-catalog-grows-a-row",
        path=SRC / "syscenter.py",
        old="    seen: set[str] = set()\n    entries: list[Entry] = []",
        new=(
            "    seen: set[str] = set()\n"
            "    entries: list[Entry] = [Entry('optional-steam', 'Steam (coming soon)',"
            " {'overview': 'coming soon'}, None)]"
        ),
        claim="an empty catalog generates no System Center row and no placeholder",
    ),
    Mutation(
        label="entry-row-carries-authority",
        path=SRC / "syscenter.py",
        old="    offer: Offer = catalog.get(entry.offer_id)\n    return may_invoke_provider(offer, ledger)",
        new="    offer: Offer = catalog.get(entry.offer_id)\n    return None",
        claim="a System Center row is an index and re-enters the consent boundary",
    ),
    Mutation(
        label="ability-row-hides-its-gate",
        path=SRC / "syscenter.py",
        old='        owners = "; ".join(f"{gate.gate_id} ({gate.owner})" for gate in refusal.gates)\n        overview = f"Fit unavailable — blocked on {owners}"',
        new='        overview = "Fit unavailable"',
        claim="the ability row names the blocking gate and its owner",
    ),
    Mutation(
        label="plan-path-is-consent",
        path=SRC / "plan.py",
        old='        if not confirmed:\n            return "the operator has not confirmed this plan"',
        new='        if False:\n            return "the operator has not confirmed this plan"',
        claim="holding a plan path is not the operator's confirmation",
    ),
)


def run_suite() -> tuple[bool, str]:
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(ROOT / "run-checks.py")],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=False,
        timeout=600,
    )
    return completed.returncode == 0, completed.stdout.decode("utf-8", "replace")


def main() -> int:
    print("F107-B anti-vacuity mutation campaign")
    print("=" * 72)

    baseline_green, baseline_output = run_suite()
    summary = [line for line in baseline_output.splitlines() if line.startswith("RESULT:")]
    print(f"  baseline: {'green' if baseline_green else 'RED'} — {summary[0] if summary else '?'}")
    if not baseline_green:
        print("REFUSED: the unmutated suite is not green; a mutation campaign would mean nothing.")
        return 2

    caught = 0
    escaped: list[str] = []
    for index, mutation in enumerate(MUTATIONS, start=1):
        original = mutation.path.read_text(encoding="utf-8")
        if original.count(mutation.old) != 1:
            print(
                f"  {index:2d}/{len(MUTATIONS)} {mutation.label}: "
                f"ANCHOR MATCHED {original.count(mutation.old)} TIMES — not applied"
            )
            escaped.append(f"{mutation.label} (anchor)")
            continue
        try:
            mutation.path.write_text(original.replace(mutation.old, mutation.new), encoding="utf-8")
            green, _ = run_suite()
        finally:
            mutation.path.write_text(original, encoding="utf-8")

        if green:
            print(f"  {index:2d}/{len(MUTATIONS)} {mutation.label}: ESCAPED — {mutation.claim}")
            escaped.append(mutation.label)
        else:
            print(f"  {index:2d}/{len(MUTATIONS)} {mutation.label}: caught — {mutation.claim}")
            caught += 1

    print("-" * 72)
    print(f"RESULT: {caught}/{len(MUTATIONS)} mutations caught, {len(escaped)}/{len(MUTATIONS)} escaped")
    for label in escaped:
        print(f"  escaped: {label}")
    final_green, final_output = run_suite()
    final_summary = [line for line in final_output.splitlines() if line.startswith("RESULT:")]
    print(f"  restored tree: {'green' if final_green else 'RED'} — {final_summary[0] if final_summary else '?'}")
    return 0 if caught == len(MUTATIONS) and final_green else 1


if __name__ == "__main__":
    raise SystemExit(main())
