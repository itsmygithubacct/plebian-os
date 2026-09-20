"""The gate ledger refuses, names owners, and never defaults to permissive."""

from __future__ import annotations

import unittest
from dataclasses import replace

import support  # noqa: F401 - installs the src path

from f107b_setup.gates import CAPABILITY_GATES, LEDGER, GateLedger, GateRefusal


class GateLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = GateLedger()

    def test_all_four_recorded_gates_are_open(self) -> None:
        self.assertEqual(len(LEDGER), 4)
        self.assertEqual(len(self.ledger.open_gates()), 4)

    def test_every_gate_names_an_owner_and_a_condition(self) -> None:
        for gate_id, gate in LEDGER.items():
            with self.subTest(gate=gate_id):
                self.assertTrue(gate.owner.strip(), f"{gate_id} has no owner")
                self.assertTrue(gate.condition.strip(), f"{gate_id} has no condition")
                self.assertTrue(gate.evidence_required.strip())
                self.assertTrue(gate.observed.strip())

    def test_every_gated_capability_is_refused_while_gates_are_open(self) -> None:
        refused = 0
        for capability in CAPABILITY_GATES:
            with self.subTest(capability=capability):
                refusal = self.ledger.require(capability)
                self.assertIsInstance(refusal, GateRefusal)
                self.assertTrue(refusal.gates)
                refused += 1
        self.assertEqual(refused, len(CAPABILITY_GATES))

    def test_an_unclassified_capability_is_refused_not_allowed(self) -> None:
        refusal = self.ledger.require("some-capability-nobody-classified")
        self.assertIsInstance(refusal, GateRefusal)
        self.assertIn("unclassified", refusal.capability)

    def test_a_capability_clears_only_when_all_its_gates_close(self) -> None:
        gates = dict(LEDGER)
        gates["F100-A3"] = replace(gates["F100-A3"], satisfied=True)
        partly_open = GateLedger(gates=gates)
        # execute_plan needs F100-A3 and F106-P1; only one has closed.
        refusal = partly_open.require("execute_plan")
        self.assertIsInstance(refusal, GateRefusal)
        self.assertEqual([gate.gate_id for gate in refusal.gates], ["F106-P1"])

        gates["F106-P1"] = replace(gates["F106-P1"], satisfied=True)
        self.assertIsNone(GateLedger(gates=gates).require("execute_plan"))

    def test_refusal_renders_the_owner_and_condition(self) -> None:
        refusal = self.ledger.require("execute_plan")
        rendered = "\n".join(refusal.render())
        self.assertIn("F100-A3", rendered)
        self.assertIn("Track A / F100 owner", rendered)
        self.assertIn("F106-P1", rendered)
        self.assertIn("Track D / F106 owner", rendered)


if __name__ == "__main__":
    unittest.main()
