"""System Center entries are generated from data, and name no component."""

from __future__ import annotations

import copy
import re
import unittest
from pathlib import Path

import support
from support import FIXTURES, OPTIONAL_COMPONENT_SCHEMA, load_json

from f107b_setup import syscenter
from f107b_setup.catalog import Consent, build_catalog
from f107b_setup.gates import GateLedger, GateRefusal
from f107b_setup.state import SetupState
from f107b_setup.syscenter import (
    ABILITY_ENTRY_ID,
    SETUP_ENTRY_ID,
    RegistrationError,
    component_entries,
    entry_action,
    focused_app,
    register,
)

RECORD = load_json(FIXTURES / "catalog" / "generic-vendor-client.json")


def catalog(records):
    return build_catalog(records, OPTIONAL_COMPONENT_SCHEMA)


class NoComponentSpecificControlTests(unittest.TestCase):
    """The master's rule, asserted against the source rather than the intent."""

    def test_the_module_source_names_no_component(self) -> None:
        source = Path(syscenter.__file__).read_text(encoding="utf-8")
        # The example record's identifiers must not appear anywhere in the
        # generator: if they did, the entry would be code, not data.
        for needle in (RECORD["id"], RECORD["label"], RECORD["provider"]):
            with self.subTest(needle=needle):
                self.assertNotIn(needle, source)

    def test_the_module_source_names_no_known_third_party_component(self) -> None:
        source = Path(syscenter.__file__).read_text(encoding="utf-8").lower()
        for needle in ("steam", "valve", "i386", "chrome", "ollama", "waydroid"):
            with self.subTest(needle=needle):
                self.assertNotIn(needle, source)

    def test_the_generator_has_no_per_component_table(self) -> None:
        source = Path(syscenter.__file__).read_text(encoding="utf-8")
        # A dict literal keyed by component ids would be exactly the banned
        # shape. The only mappings here are the fixed section labels.
        self.assertEqual(len(re.findall(r'^\s*"[a-z0-9-]+":\s*"', source, re.M)) > 0, True)
        self.assertNotIn("COMPONENTS = {", source)
        self.assertNotIn("KNOWN_COMPONENTS", source)


class EmptyCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = GateLedger()
        self.state = SetupState.fresh(account="operator")

    def test_an_empty_catalog_generates_zero_component_rows(self) -> None:
        self.assertEqual(component_entries(catalog([])), ())

    def test_only_the_two_structural_rows_remain(self) -> None:
        entries = register(self.state, catalog([]), self.ledger)
        self.assertEqual(len(entries), 2)
        self.assertEqual(
            [entry.entry_id for entry in entries], [SETUP_ENTRY_ID, ABILITY_ENTRY_ID]
        )
        self.assertEqual([entry.generated for entry in entries], [False, False])

    def test_an_empty_catalog_ships_no_placeholder_row(self) -> None:
        _, _, sections = focused_app(register(self.state, catalog([]), self.ledger))
        rendered = " ".join(sections.values()).lower()
        for forbidden in ("coming soon", "unavailable", "not yet", "placeholder", "none"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, rendered)


class GenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = GateLedger()
        self.state = SetupState.fresh(account="operator")

    def test_one_record_generates_exactly_one_row(self) -> None:
        entries = component_entries(catalog([RECORD]))
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0].generated)
        self.assertEqual(entries[0].offer_id, RECORD["id"])

    def test_the_row_label_comes_from_the_record(self) -> None:
        self.assertEqual(component_entries(catalog([RECORD]))[0].label, RECORD["label"])

    def test_a_relabelled_record_changes_the_row_with_no_code_change(self) -> None:
        renamed = copy.deepcopy(RECORD)
        renamed["label"] = "Some Other Client"
        self.assertEqual(component_entries(catalog([renamed]))[0].label, "Some Other Client")

    def test_the_disclosure_count_comes_from_the_record(self) -> None:
        entry = component_entries(catalog([RECORD]))[0]
        self.assertIn(str(len(RECORD["disclosures"])), entry.sections["disclosures"])

    def test_rows_follow_the_catalog_ordering(self) -> None:
        second = copy.deepcopy(RECORD)
        second["id"] = "aaa-first"
        entries = component_entries(catalog([RECORD, second]))
        self.assertEqual(
            [entry.offer_id for entry in entries], ["aaa-first", RECORD["id"]]
        )

    def test_a_full_registration_is_two_structural_rows_plus_the_data(self) -> None:
        entries = register(self.state, catalog([RECORD]), self.ledger)
        self.assertEqual(len(entries), 3)
        self.assertEqual(sum(1 for entry in entries if entry.generated), 1)

    def test_the_focused_app_shape_matches_the_existing_tui_convention(self) -> None:
        title, breadcrumb, sections = focused_app(
            register(self.state, catalog([RECORD]), self.ledger)
        )
        self.assertIsInstance(title, str)
        self.assertEqual(breadcrumb, ("Machine",))
        self.assertIn("overview", sections)
        self.assertEqual(sections["overview"], "")
        self.assertEqual(len(sections), 4)


class SetupRowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = GateLedger()

    def test_a_fresh_state_offers_a_resume_point(self) -> None:
        entry = syscenter.setup_entry(SetupState.fresh(account="operator"))
        self.assertIn("Resume at", entry.sections["overview"])
        self.assertIn("Welcome", entry.sections["overview"])

    def test_a_finished_state_says_finished(self) -> None:
        state = SetupState.fresh(account="operator").skip_all_remaining()
        entry = syscenter.setup_entry(state)
        self.assertIn("Finished", entry.sections["overview"])
        self.assertIn("8 step(s) skipped", entry.sections["overview"])

    def test_blocked_steps_are_reported_not_hidden(self) -> None:
        state = SetupState.fresh(account="operator")
        for checkpoint in state.checkpoints:
            state = state.complete(checkpoint.checkpoint_id)
        state = state.block("plan-review", "F100-A3")
        entry = syscenter.setup_entry(state)
        self.assertIn("could not run", entry.sections["overview"])

    def test_the_checkpoint_line_carries_a_denominator_of_eight(self) -> None:
        entry = syscenter.setup_entry(SetupState.fresh(account="operator"))
        line = entry.sections["checkpoints"]
        total = sum(int(part) for part in re.findall(r"\d+", line))
        self.assertEqual(total, 8)


class AbilityRowTests(unittest.TestCase):
    def test_the_row_names_the_blocking_gate_and_its_owner(self) -> None:
        entry = syscenter.ability_entry(GateLedger())
        overview = entry.sections["overview"]
        self.assertIn("F100-A3", overview)
        self.assertIn("Track A", overview)

    def test_the_row_still_offers_what_is_measurable(self) -> None:
        entry = syscenter.ability_entry(GateLedger())
        self.assertIn("hardware", entry.sections)
        self.assertIn("unknowns", entry.sections)


class EntryAuthorityTests(unittest.TestCase):
    """A row is an index. It carries no authority of its own."""

    def setUp(self) -> None:
        self.ledger = GateLedger()
        self.catalog = catalog([RECORD])
        self.entry = component_entries(self.catalog)[0]

    def test_activating_an_unselected_row_invokes_nothing(self) -> None:
        self.assertEqual(
            entry_action(self.entry, self.catalog, self.ledger),
            "the offer is not selected",
        )

    def test_activating_a_row_still_requires_both_consent_acts(self) -> None:
        selected = self.catalog.replace(
            self.catalog.get(RECORD["id"]).select().with_consent(Consent().accept_license())
        )
        outcome = entry_action(self.entry, selected, self.ledger)
        self.assertIsInstance(outcome, str)
        self.assertIn("kilix.install.authorization/v2", outcome)

    def test_a_fully_consented_row_is_still_gate_blocked(self) -> None:
        consent = Consent().accept_license().grant_authorization()
        selected = self.catalog.replace(
            self.catalog.get(RECORD["id"]).select().with_consent(consent)
        )
        outcome = entry_action(self.entry, selected, self.ledger)
        self.assertIsInstance(outcome, GateRefusal)
        self.assertEqual(sorted(g.gate_id for g in outcome.gates), ["F100-A3", "F106-P1"])

    def test_a_structural_row_has_no_component_action(self) -> None:
        entry = syscenter.setup_entry(SetupState.fresh(account="operator"))
        with self.assertRaises(RegistrationError):
            entry_action(entry, self.catalog, self.ledger)


if __name__ == "__main__":
    unittest.main()
