"""Decision-scoped licence presentation, and the receipt F107-B cannot write."""

from __future__ import annotations

import unittest

import support

from f107b_setup.gates import GateLedger, GateRefusal
from f107b_setup.licenses import (
    AFFIRMATIVE,
    INFORMATIONAL,
    RESTRICTED,
    USER_SUPPLIED,
    LicenseRef,
    build_presentation,
    request_receipt,
)

DIGEST_A = "a" * 64
DIGEST_B = "b" * 64


def ref(license_id: str, decision_class: str, digest: str = DIGEST_A) -> dict:
    return {
        "schema": "kilix.install.license/v1",
        "license_id": license_id,
        "license_text_sha256": digest,
        "decision_class": decision_class,
    }


def item(artifact: str, license_id: str) -> dict:
    return {
        "profile_id": f"profile-{artifact}",
        "provider": "example-provider",
        "artifact_id": artifact,
        "license_decision_id": license_id,
        "reason": "selected by the preset",
    }


class DispositionTests(unittest.TestCase):
    def test_an_unknown_disposition_fails_closed_as_restricted(self) -> None:
        parsed = LicenseRef.from_record(ref("mystery", "who-knows"))
        self.assertEqual(parsed.decision_class, RESTRICTED)

    def test_an_absent_disposition_fails_closed_as_restricted(self) -> None:
        record = ref("mystery", AFFIRMATIVE)
        del record["decision_class"]
        self.assertEqual(LicenseRef.from_record(record).decision_class, RESTRICTED)

    def test_an_unpinned_licence_text_fails_closed_as_restricted(self) -> None:
        parsed = LicenseRef.from_record(ref("unpinned", AFFIRMATIVE, digest="short"))
        self.assertEqual(parsed.decision_class, RESTRICTED)

    def test_the_decision_key_is_licence_and_version(self) -> None:
        first = LicenseRef.from_record(ref("terms", AFFIRMATIVE, DIGEST_A))
        second = LicenseRef.from_record(ref("terms", AFFIRMATIVE, DIGEST_B))
        self.assertNotEqual(first.decision_key, second.decision_key)

    def test_a_new_text_for_the_same_name_is_a_second_decision(self) -> None:
        presentation = build_presentation(
            [], [ref("terms", AFFIRMATIVE, DIGEST_A), ref("terms", AFFIRMATIVE, DIGEST_B)]
        )
        self.assertEqual(len(presentation.decisions), 2)


class PresentationTests(unittest.TestCase):
    def test_an_informational_notice_gets_no_checkbox(self) -> None:
        presentation = build_presentation([], [ref("notice", INFORMATIONAL)])
        rendered = "\n".join(presentation.render())
        self.assertNotIn("[ ]", rendered)
        self.assertNotIn("[x]", rendered)
        self.assertIn("No acceptance is requested", rendered)

    def test_an_informational_notice_cannot_be_accepted_or_refused(self) -> None:
        presentation = build_presentation([], [ref("notice", INFORMATIONAL)])
        decision = presentation.decisions[0]
        with self.assertRaises(ValueError):
            decision.accept()
        with self.assertRaises(ValueError):
            decision.refuse()

    def test_an_affirmative_decision_starts_unchecked(self) -> None:
        presentation = build_presentation([], [ref("terms", AFFIRMATIVE)])
        decision = presentation.decisions[0]
        self.assertIsNone(decision.accepted)
        self.assertFalse(decision.satisfied)
        self.assertIn("[ ]", "\n".join(decision.render()))

    def test_a_restricted_licence_is_never_satisfied_even_when_accepted(self) -> None:
        presentation = build_presentation([], [ref("restricted", RESTRICTED)])
        decision = presentation.decisions[0].accept()
        self.assertFalse(decision.satisfied)

    def test_a_user_supplied_licence_needs_an_explicit_acceptance(self) -> None:
        presentation = build_presentation([], [ref("supplied", USER_SUPPLIED)])
        decision = presentation.decisions[0]
        self.assertFalse(decision.satisfied)
        self.assertTrue(decision.accept().satisfied)

    def test_every_rendered_decision_states_its_digest(self) -> None:
        presentation = build_presentation([], [ref("terms", AFFIRMATIVE, DIGEST_A)])
        self.assertIn(DIGEST_A, "\n".join(presentation.render()))


class DependencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.presentation = build_presentation(
            [item("alpha", "terms-a"), item("beta", "terms-b"), item("gamma", "terms-a")],
            [ref("terms-a", AFFIRMATIVE, DIGEST_A), ref("terms-b", AFFIRMATIVE, DIGEST_B)],
        )

    def test_no_item_is_eligible_before_any_acceptance(self) -> None:
        self.assertEqual(self.presentation.eligible_items(), ())

    def test_accepting_one_licence_makes_only_its_items_eligible(self) -> None:
        decision = self.presentation.decisions[0].accept()
        updated = self.presentation.replace_decision(decision)
        eligible = {view.artifact_id for view in updated.eligible_items()}
        self.assertEqual(eligible, {"alpha", "gamma"})

    def test_refusing_removes_only_the_dependent_items(self) -> None:
        state = self.presentation
        for index in range(2):
            state = state.replace_decision(state.decisions[index].accept())
        self.assertEqual(len(state.eligible_items()), 3)
        state, removed = state.withdraw("terms-a")
        self.assertEqual([view.artifact_id for view in removed], ["alpha", "gamma"])
        self.assertEqual([view.artifact_id for view in state.eligible_items()], ["beta"])

    def test_an_item_whose_licence_is_absent_is_dropped_not_permitted(self) -> None:
        presentation = build_presentation([item("orphan", "no-such-licence")], [])
        self.assertEqual(presentation.eligible_items(), ())


class ReceiptTests(unittest.TestCase):
    def test_setup_cannot_write_a_receipt_and_names_the_owner_instead(self) -> None:
        refusal = request_receipt("terms-a", GateLedger())
        self.assertIsInstance(refusal, GateRefusal)
        self.assertIn("F100-A3", [gate.gate_id for gate in refusal.gates])

    def test_the_licences_module_exposes_no_receipt_constructor(self) -> None:
        import f107b_setup.licenses as module

        names = [name for name in dir(module) if "receipt" in name.lower()]
        self.assertEqual(names, ["request_receipt"])


if __name__ == "__main__":
    unittest.main()
