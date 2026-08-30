"""The model-aware plan: unknown stays unknown, and blocked is an outcome."""

from __future__ import annotations

import copy
import unittest

import support
from support import response_data

from f107b_setup.gates import GateLedger, GateRefusal
from f107b_setup.plan import (
    UNKNOWN,
    fit_view,
    format_bytes,
    hardware_report,
    plan_review,
    sum_or_unknown,
)


#: The shape F106 could legitimately emit once F100-C0 is frozen: every
#: consumer admission rule satisfied, and confirmation still ungranted because
#: no document may grant it.
ADMISSIBLE_READY_PLAN = {
    "schema": "plebian.models.install-plan/v1",
    "plan_id": "hypothetical:ready",
    "operation": "plan",
    "preset": "local-ai-balanced",
    "status": "ready",
    "executable": True,
    "capacity_contract_status": "resolved",
    "items": [
        {
            "profile_id": "example-profile",
            "provider": "example-provider",
            "artifact_id": "example-artifact",
            "license_decision_id": "example-terms",
            "reason": "selected by the preset",
        }
    ],
    "totals": {
        "download_bytes": 1073741824,
        "installed_bytes": 2147483648,
        "temporary_bytes": 1073741824,
        "shared_bytes": 0,
    },
    "authorization_receipts": [
        {"decision_id": "example-terms", "present": True, "receipt_sha256": "c" * 64}
    ],
    "confirmation": {"required": True, "granted": False},
    "blockers": [],
}


class UnknownIsNotZeroTests(unittest.TestCase):
    def test_none_renders_as_unknown_not_as_zero(self) -> None:
        self.assertEqual(format_bytes(None), UNKNOWN)
        self.assertNotIn("0", format_bytes(None))

    def test_zero_renders_as_zero(self) -> None:
        self.assertEqual(format_bytes(0), "0 B")

    def test_known_sizes_render_with_units(self) -> None:
        self.assertEqual(format_bytes(2 * 1024**3), "2.0 GiB")
        self.assertEqual(format_bytes(1536), "1.5 KiB")

    def test_a_negative_or_non_integer_count_is_refused(self) -> None:
        for value in (-1, 1.5, True, "8"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    format_bytes(value)

    def test_one_unknown_addend_makes_the_whole_sum_unknown(self) -> None:
        self.assertIsNone(sum_or_unknown([1024, None, 2048]))
        self.assertEqual(sum_or_unknown([1024, 2048]), 3072)

    def test_an_empty_selection_really_is_zero(self) -> None:
        self.assertEqual(sum_or_unknown([]), 0)


@support.requires_candidate
class HardwareReportTests(unittest.TestCase):
    def test_the_report_names_every_unknown_rather_than_hiding_it(self) -> None:
        report = hardware_report(response_data("hardware-inventory.json"))
        self.assertTrue(report.usable)
        rendered = "\n".join(report.render())
        for unknown in response_data("hardware-inventory.json")["unknowns"]:
            with self.subTest(unknown=unknown):
                self.assertIn(unknown, rendered)

    def test_unmeasured_vram_is_shown_as_unknown_not_zero(self) -> None:
        rendered = "\n".join(hardware_report(response_data("hardware-gpu.json")).render())
        self.assertIn(f"VRAM {UNKNOWN}", rendered)
        self.assertNotIn("VRAM 0 B", rendered)

    def test_the_report_states_that_it_is_not_qualification_evidence(self) -> None:
        rendered = "\n".join(hardware_report(response_data("hardware-inventory.json")).render())
        self.assertIn("not qualification evidence", rendered)

    def test_an_inadmissible_report_is_withheld_with_its_findings(self) -> None:
        document = copy.deepcopy(response_data("hardware-inventory.json"))
        document["capture"]["qualification_eligible"] = True
        report = hardware_report(document)
        self.assertFalse(report.usable)
        rendered = "\n".join(report.render())
        self.assertIn("withheld", rendered)
        self.assertIn("finding:", rendered)


@support.requires_candidate
class FitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = GateLedger()

    def test_the_fixture_reports_unknown_and_is_not_a_recommendation(self) -> None:
        view = fit_view(response_data("sizer-recommend-tts.json"))
        self.assertEqual(view.verdict, "unknown")
        outcome = view.presentable_recommendation(self.ledger)
        self.assertIsInstance(outcome, str)
        self.assertIn("not a recommendation", outcome)

    def test_a_forged_recommendation_is_refused_by_admission_first(self) -> None:
        document = copy.deepcopy(response_data("sizer-recommend-tts.json"))
        document["overall_verdict"] = "recommended"
        view = fit_view(document)
        outcome = view.presentable_recommendation(self.ledger)
        self.assertEqual(outcome, "the fit result failed consumer admission")

    def test_every_reason_the_sizer_gave_is_shown(self) -> None:
        document = response_data("sizer-recommend-tts.json")
        rendered = "\n".join(fit_view(document).render())
        for reason in document["reasons"]:
            with self.subTest(code=reason["code"]):
                self.assertIn(reason["code"], rendered)

    def test_unknown_reserves_are_rendered_as_unknown(self) -> None:
        rendered = "\n".join(fit_view(response_data("sizer-recommend-tts.json")).render())
        self.assertIn(f"reserve {UNKNOWN}", rendered)
        self.assertNotIn("reserve 0 B", rendered)


@support.requires_candidate
class PlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = GateLedger()
        self.review = plan_review(response_data("sizer-plan.json"))

    def test_the_fixture_plan_is_blocked_and_not_executable(self) -> None:
        self.assertTrue(self.review.blocked)
        self.assertEqual(self.review.status, "blocked")

    def test_every_blocker_is_rendered(self) -> None:
        rendered = "\n".join(self.review.render())
        self.assertIn("F100_C0_MISSING", rendered)
        self.assertIn("NO_QUALIFIED_SELECTION", rendered)

    def test_unknown_totals_render_as_unknown(self) -> None:
        rendered = "\n".join(self.review.render())
        self.assertIn(f"Download: {UNKNOWN}", rendered)
        self.assertNotIn("Download: 0 B", rendered)

    def test_the_operator_is_told_the_core_system_is_unaffected(self) -> None:
        self.assertIn("core system is complete", "\n".join(self.review.render()).lower())

    def test_a_blocked_plan_refuses_execution_before_any_gate_is_consulted(self) -> None:
        outcome = self.review.may_execute(self.ledger, confirmed=True)
        self.assertIsInstance(outcome, str)
        self.assertIn("not executable", outcome)

    def test_a_forged_ready_plan_fails_admission_before_anything_else(self) -> None:
        document = copy.deepcopy(response_data("sizer-plan.json"))
        document["status"] = "ready"
        document["executable"] = True
        review = plan_review(document)
        self.assertEqual(
            review.may_execute(self.ledger, confirmed=False),
            "the plan failed consumer admission",
        )

    def test_an_admissible_ready_plan_still_needs_the_confirmation_act(self) -> None:
        # A plan that satisfies every consumer rule — the shape F106 would emit
        # once F100-C0 is frozen. Holding it is still not consent, so the
        # confirmation is a parameter and not a member of the document.
        review = plan_review(ADMISSIBLE_READY_PLAN)
        self.assertTrue(review.admission.admitted, review.admission.findings)
        self.assertFalse(review.blocked)
        self.assertEqual(
            review.may_execute(self.ledger, confirmed=False),
            "the operator has not confirmed this plan",
        )

    def test_a_confirmed_admissible_plan_is_still_held_by_the_release_gates(self) -> None:
        outcome = plan_review(ADMISSIBLE_READY_PLAN).may_execute(self.ledger, confirmed=True)
        self.assertIsInstance(outcome, GateRefusal)
        self.assertEqual(sorted(g.gate_id for g in outcome.gates), ["F100-A3", "F106-P1"])

    def test_an_admissible_ready_plan_renders_its_real_sizes(self) -> None:
        rendered = "\n".join(plan_review(ADMISSIBLE_READY_PLAN).render())
        self.assertIn("Download: 1.0 GiB", rendered)
        self.assertIn("1/1 present", rendered)

    def test_the_install_response_is_also_blocked_and_mutates_nothing(self) -> None:
        review = plan_review(response_data("sizer-install-blocked.json"))
        self.assertTrue(review.blocked)
        self.assertEqual(review.document["operation"], "install")
        self.assertEqual(review.document["items"], [])


if __name__ == "__main__":
    unittest.main()
