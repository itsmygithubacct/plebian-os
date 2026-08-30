"""The generic optional-component offer and its two-act consent boundary."""

from __future__ import annotations

import copy
import unittest

import support
from support import FIXTURES, OPTIONAL_COMPONENT_SCHEMA, load_json

from f107b_setup.catalog import (
    MAX_RECORDS,
    CatalogError,
    Consent,
    build_catalog,
    may_invoke_provider,
)
from f107b_setup.gates import GateLedger, GateRefusal

RECORD = load_json(FIXTURES / "catalog" / "generic-vendor-client.json")


def catalog(records):
    return build_catalog(records, OPTIONAL_COMPONENT_SCHEMA)


class PopulationTests(unittest.TestCase):
    def test_an_empty_population_renders_one_honest_line_and_no_control(self) -> None:
        empty = catalog([])
        self.assertTrue(empty.empty)
        self.assertEqual(empty.population, 0)
        rendered = empty.render()
        self.assertEqual(len(rendered), 1)
        self.assertIn("No optional components", rendered[0])
        for forbidden in ("[ ]", "[x]", "coming soon", "unavailable"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, rendered[0])

    def test_a_valid_record_renders_with_all_three_disclosures(self) -> None:
        built = catalog([RECORD])
        self.assertEqual(built.population, 1)
        rendered = "\n".join(built.render())
        self.assertIn("third-party-repository", rendered)
        self.assertIn("foreign-architecture", rendered)
        self.assertIn("self-update", rendered)

    def test_records_are_ordered_deterministically_by_id(self) -> None:
        second = copy.deepcopy(RECORD)
        second["id"] = "aaa-first"
        built = catalog([RECORD, second])
        self.assertEqual([offer.offer_id for offer in built.offers], ["aaa-first", RECORD["id"]])

    def test_a_duplicate_id_is_refused(self) -> None:
        with self.assertRaisesRegex(CatalogError, "duplicate record id"):
            catalog([RECORD, copy.deepcopy(RECORD)])

    def test_an_oversized_population_is_refused_not_truncated(self) -> None:
        records = []
        for index in range(MAX_RECORDS + 1):
            record = copy.deepcopy(RECORD)
            record["id"] = f"component-{index:03d}"
            records.append(record)
        with self.assertRaisesRegex(CatalogError, "exceeds"):
            catalog(records)

    def test_a_record_missing_a_required_field_is_refused(self) -> None:
        for field in ("disclosures", "authorization_ref", "license_ref", "provider"):
            with self.subTest(field=field):
                record = copy.deepcopy(RECORD)
                del record[field]
                with self.assertRaises(CatalogError):
                    catalog([record])

    def test_a_record_with_no_disclosure_is_refused(self) -> None:
        record = copy.deepcopy(RECORD)
        record["disclosures"] = []
        with self.assertRaises(CatalogError):
            catalog([record])


class ConsentBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = GateLedger()
        self.catalog = catalog([RECORD])
        self.offer = self.catalog.offers[0]

    def test_every_offer_is_deselected_on_construction(self) -> None:
        self.assertEqual(self.catalog.selected(), ())
        self.assertFalse(self.offer.selected)

    def test_an_unselected_offer_invokes_nothing(self) -> None:
        self.assertEqual(may_invoke_provider(self.offer, self.ledger), "the offer is not selected")

    def test_licence_acceptance_alone_does_not_grant_package_authority(self) -> None:
        offer = self.offer.select().with_consent(Consent().accept_license())
        outcome = may_invoke_provider(offer, self.ledger)
        self.assertIsInstance(outcome, str)
        self.assertIn("kilix.install.authorization/v2", outcome)

    def test_package_authority_alone_does_not_accept_the_terms(self) -> None:
        offer = self.offer.select().with_consent(Consent().grant_authorization())
        outcome = may_invoke_provider(offer, self.ledger)
        self.assertIsInstance(outcome, str)
        self.assertIn("kilix.install.license/v1", outcome)

    def test_both_acts_still_leave_the_release_gate_in_the_way(self) -> None:
        consent = Consent().accept_license().grant_authorization()
        self.assertTrue(consent.complete)
        offer = self.offer.select().with_consent(consent)
        outcome = may_invoke_provider(offer, self.ledger)
        self.assertIsInstance(outcome, GateRefusal)
        self.assertEqual(
            sorted(gate.gate_id for gate in outcome.gates), ["F100-A3", "F106-P1"]
        )

    def test_deselecting_drops_the_consent_with_it(self) -> None:
        consent = Consent().accept_license().grant_authorization()
        offer = self.offer.select().with_consent(consent).deselect()
        self.assertFalse(offer.consent.license_accepted)
        self.assertFalse(offer.consent.authorization_granted)

    def test_consent_has_no_single_act_constructor(self) -> None:
        # There is no ``Consent.all()``; both fields are set independently.
        self.assertFalse(hasattr(Consent, "all"))
        self.assertFalse(Consent().complete)
        self.assertFalse(Consent().accept_license().complete)
        self.assertFalse(Consent().grant_authorization().complete)


if __name__ == "__main__":
    unittest.main()
