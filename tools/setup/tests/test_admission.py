"""Consumer-side admission, including against a lying producer.

The candidate ships nine invalid-mutation fixtures. Six of them mutate a
document F107-B consumes; those six are replayed here against **F107-B's own**
rules, so a pass means this consumer catches them independently, not that Track
D's validator does.
"""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from typing import Any

import support
from support import CANDIDATE_ROOT, response_data

from f107b_setup.admission import admit

#: The candidate's invalid fixtures that mutate a schema F107-B consumes.
CONSUMED_MUTATIONS = (
    "fit-invents-capacity.json",
    "hardware-forbidden-identifier.json",
    "hardware-ipv6-identifier.json",
    "hardware-noncontiguous-network-index.json",
    "hardware-observation-enables-telemetry.json",
    "hardware-pci-implies-backend.json",
    "plan-ready-without-authority.json",
)

#: Mutations that describe a producer-side or catalog-side concern F107-B does
#: not re-derive. Listed so the split is explicit rather than silent.
NOT_CONSUMER_RULES = (
    "invocation-duplicate-command.json",
    "profile-estimate-qualified.json",
)


def set_pointer(document: Any, pointer: str, value: Any) -> None:
    parts = pointer.lstrip("/").split("/")
    cursor = document
    for part in parts[:-1]:
        key = int(part) if part.isdigit() and isinstance(cursor, list) else part.replace("~1", "/").replace("~0", "~")
        cursor = cursor[key]
    last = parts[-1]
    key = int(last) if last.isdigit() and isinstance(cursor, list) else last.replace("~1", "/").replace("~0", "~")
    cursor[key] = value


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@support.requires_candidate
class HonestFixturesTests(unittest.TestCase):
    """Every unmutated response the wizard consumes is admitted."""

    def test_four_of_four_consumed_response_documents_are_admitted(self) -> None:
        names = (
            "hardware-inventory.json",
            "hardware-gpu.json",
            "sizer-recommend-tts.json",
            "sizer-plan.json",
        )
        admitted = 0
        for name in names:
            with self.subTest(fixture=name):
                result = admit(response_data(name))
                self.assertTrue(result.admitted, result.findings)
                admitted += 1
        self.assertEqual(admitted, 4)

    def test_the_snapshot_and_install_documents_are_admitted(self) -> None:
        for name in ("sizer-snapshot.json", "sizer-install-blocked.json"):
            with self.subTest(fixture=name):
                result = admit(response_data(name))
                self.assertTrue(result.admitted, result.findings)

    def test_the_standalone_fit_and_plan_fixtures_are_admitted(self) -> None:
        for relative in ("fixtures/fit/blocked-no-f100-c0.json", "fixtures/plans/blocked-no-f100-c0.json"):
            with self.subTest(fixture=relative):
                result = admit(load(CANDIDATE_ROOT / relative))
                self.assertTrue(result.admitted, result.findings)


@support.requires_candidate
class CandidateMutationTests(unittest.TestCase):
    """Seven candidate mutations, refused by this consumer's own rules."""

    def test_seven_of_seven_consumed_mutations_are_refused(self) -> None:
        refused = 0
        for name in CONSUMED_MUTATIONS:
            with self.subTest(mutation=name):
                mutation = load(CANDIDATE_ROOT / "fixtures" / "invalid" / name)
                document = copy.deepcopy(load(CANDIDATE_ROOT / mutation["base"]))
                set_pointer(document, mutation["path"], mutation["value"])
                result = admit(document)
                self.assertFalse(
                    result.admitted,
                    f"{name} was admitted; expected refusal for {mutation['expected']!r}",
                )
                refused += 1
        self.assertEqual(refused, len(CONSUMED_MUTATIONS))

    def test_the_two_producer_only_mutations_are_declared_out_of_scope(self) -> None:
        for name in NOT_CONSUMER_RULES:
            self.assertTrue((CANDIDATE_ROOT / "fixtures" / "invalid" / name).is_file())
        self.assertEqual(
            len(CONSUMED_MUTATIONS) + len(NOT_CONSUMER_RULES),
            len(list((CANDIDATE_ROOT / "fixtures" / "invalid").glob("*.json"))),
        )


@support.requires_candidate
class ConsumerSpecificMutationTests(unittest.TestCase):
    """Refusals the candidate's own validator does not have to make."""

    def _mutate(self, name: str, pointer: str, value: Any) -> Any:
        document = copy.deepcopy(response_data(name))
        set_pointer(document, pointer, value)
        return document

    def test_a_recommendation_without_resolved_capacity_is_refused(self) -> None:
        document = self._mutate("sizer-recommend-tts.json", "/overall_verdict", "recommended")
        self.assertFalse(admit(document).admitted)

    def test_qualification_claimed_on_a_synthetic_capture_is_refused(self) -> None:
        document = self._mutate(
            "hardware-inventory.json", "/capture/qualification_eligible", True
        )
        result = admit(document)
        self.assertFalse(result.admitted)
        self.assertTrue(any("qualification" in finding for finding in result.findings))

    def test_a_backend_available_on_pci_identity_alone_is_refused(self) -> None:
        document = copy.deepcopy(response_data("hardware-gpu.json"))
        document["gpus"][1]["backends"][0]["status"] = "available"
        result = admit(document)
        self.assertFalse(result.admitted)
        self.assertTrue(any("availability" in finding for finding in result.findings))

    def test_an_invented_capacity_identity_is_refused(self) -> None:
        document = self._mutate(
            "sizer-recommend-tts.json", "/capacity_contract/identity", "F100-C0"
        )
        self.assertFalse(admit(document).admitted)

    def test_capacity_arithmetic_without_reserves_is_refused(self) -> None:
        document = copy.deepcopy(response_data("sizer-recommend-tts.json"))
        document["resources"][0]["available_bytes"] = 8 * 1024**3
        result = admit(document)
        self.assertFalse(result.admitted)
        self.assertTrue(any("without frozen reserves" in f for f in result.findings))

    def test_populated_totals_without_reserves_are_refused(self) -> None:
        document = self._mutate("sizer-plan.json", "/totals/download_bytes", 0)
        result = admit(document)
        self.assertFalse(result.admitted)
        self.assertTrue(any("totals.download_bytes" in f for f in result.findings))

    def test_synthesized_confirmation_is_refused(self) -> None:
        document = self._mutate("sizer-plan.json", "/confirmation/granted", True)
        result = admit(document)
        self.assertFalse(result.admitted)
        self.assertTrue(any("synthesizes user confirmation" in f for f in result.findings))

    def test_a_waived_confirmation_requirement_is_refused(self) -> None:
        document = self._mutate("sizer-plan.json", "/confirmation/required", False)
        self.assertFalse(admit(document).admitted)

    def test_a_prohibited_identifier_anywhere_is_refused(self) -> None:
        document = copy.deepcopy(response_data("hardware-inventory.json"))
        document["capture"]["hostname"] = "a-host"
        result = admit(document)
        self.assertFalse(result.admitted)
        self.assertTrue(any("prohibited identifier" in f for f in result.findings))

    def test_a_shortened_never_collected_denylist_is_refused(self) -> None:
        document = copy.deepcopy(response_data("hardware-inventory.json"))
        document["never_collected"] = document["never_collected"][:-1]
        self.assertFalse(admit(document).admitted)

    def test_an_unqualified_snapshot_claiming_eligibility_is_refused(self) -> None:
        document = self._mutate("sizer-snapshot.json", "/qualification_eligible", True)
        self.assertFalse(admit(document).admitted)

    def test_an_unknown_schema_has_no_admission_rule_and_is_refused(self) -> None:
        result = admit({"schema": "plebian.models.something/v9"})
        self.assertFalse(result.admitted)
        self.assertIn("no consumer admission rule", result.findings[0])


if __name__ == "__main__":
    unittest.main()
