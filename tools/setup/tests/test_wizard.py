"""End-to-end wizard runs against the candidate replay binaries."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import support
from support import FIXTURES, OPTIONAL_COMPONENT_SCHEMA, REPLAY_BIN, load_json

from f107b_setup.catalog import Consent, build_catalog
from f107b_setup.f106_client import F106Client
from f107b_setup.gates import GateLedger
from f107b_setup.state import BLOCKED, COMPLETE, SKIPPED, SetupState, load, save
from f107b_setup.wizard import Answers, CoreIncomplete, Wizard

RECORD = load_json(FIXTURES / "catalog" / "generic-vendor-client.json")


def make_wizard(
    state: SetupState | None = None,
    records: list | None = None,
    sudoers_dir: Path | None = None,
) -> Wizard:
    return Wizard(
        state=state or SetupState.fresh(account="operator"),
        ledger=GateLedger(),
        catalog=build_catalog(records if records is not None else [], OPTIONAL_COMPONENT_SCHEMA),
        client=F106Client(bin_dir=REPLAY_BIN),
        sudoers_dir=sudoers_dir,
    )


@support.requires_candidate
class WizardRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not REPLAY_BIN.is_dir():
            raise unittest.SkipTest(f"candidate replay binaries absent at {REPLAY_BIN}")

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_a_default_run_reaches_every_checkpoint(self) -> None:
        wizard = make_wizard(sudoers_dir=self.tmp / "sudoers.d")
        state, transcript = wizard.run(Answers())
        self.assertIsNone(state.resume_at())
        self.assertEqual(sum(state.counts().values()), 8)
        self.assertIn("Setup summary", transcript)

    def test_the_gate_free_checkpoints_complete(self) -> None:
        wizard = make_wizard(sudoers_dir=self.tmp / "sudoers.d")
        state, _ = wizard.run(Answers())
        for checkpoint_id in ("welcome", "account-summary", "sudo-policy", "hardware-report"):
            with self.subTest(checkpoint=checkpoint_id):
                self.assertEqual(state.get(checkpoint_id).status, COMPLETE)

    def test_the_plan_review_is_blocked_and_names_the_reason(self) -> None:
        wizard = make_wizard()
        state, transcript = wizard.run(Answers(confirm_plan=True))
        self.assertEqual(state.get("plan-review").status, BLOCKED)
        self.assertIn("F100_C0_MISSING", transcript)
        self.assertIn("blocked: plan-review", transcript)

    def test_a_goal_produces_a_named_gate_rather_than_a_recommendation(self) -> None:
        wizard = make_wizard()
        state, transcript = wizard.run(Answers(goals=("tts",)))
        self.assertEqual(state.get("goals-and-fit").status, BLOCKED)
        self.assertIn("PROFILE_UNQUALIFIED", transcript)
        self.assertNotIn("Recommended:", transcript)

    def test_no_goals_skips_the_fit_checkpoint(self) -> None:
        state, _ = make_wizard().run(Answers())
        self.assertEqual(state.get("goals-and-fit").status, SKIPPED)

    def test_an_empty_catalog_completes_without_a_dead_control(self) -> None:
        state, transcript = make_wizard().run(Answers())
        checkpoint = state.get("optional-components")
        self.assertEqual(checkpoint.status, COMPLETE)
        self.assertIn("empty catalog", checkpoint.detail)
        self.assertIn("No optional components are offered", transcript)

    def test_a_populated_catalog_defaults_every_offer_off(self) -> None:
        state, transcript = make_wizard(records=[RECORD]).run(Answers())
        self.assertEqual(state.get("optional-components").status, COMPLETE)
        self.assertIn("0/1 offers selected", state.get("optional-components").detail)
        self.assertIn("[ ] Example vendor client", transcript)
        self.assertNotIn("[x]", transcript)

    def test_a_selected_offer_with_both_consents_is_still_gate_blocked(self) -> None:
        consent = Consent().accept_license().grant_authorization()
        answers = Answers(
            selected_components=(RECORD["id"],),
            component_consents={RECORD["id"]: consent},
        )
        state, transcript = make_wizard(records=[RECORD]).run(answers)
        self.assertEqual(state.get("optional-components").status, BLOCKED)
        self.assertIn("F106-P1", transcript)
        self.assertIn("provider invocation is gated", state.get("optional-components").detail)

    def test_a_selected_offer_without_both_consents_names_the_missing_act(self) -> None:
        answers = Answers(
            selected_components=(RECORD["id"],),
            component_consents={RECORD["id"]: Consent().accept_license()},
        )
        _, transcript = make_wizard(records=[RECORD]).run(answers)
        self.assertIn("kilix.install.authorization/v2", transcript)

    def test_a_nonexistent_offer_id_selects_nothing(self) -> None:
        answers = Answers(selected_components=("no-such-component",))
        state, transcript = make_wizard(records=[RECORD]).run(answers)
        self.assertIn("no such record", transcript)
        self.assertEqual(state.get("optional-components").status, COMPLETE)

    def test_declining_the_browser_leaves_chromium_and_writes_nothing(self) -> None:
        state, transcript = make_wizard().run(Answers())
        self.assertEqual(state.get("default-browser").status, SKIPPED)
        self.assertIn("chromium remains the working handler", transcript)
        self.assertNotIn("would write", transcript)

    def test_choosing_a_browser_lists_the_surfaces_it_would_write(self) -> None:
        state, transcript = make_wizard().run(Answers(browser="firefox-esr"))
        self.assertEqual(state.get("default-browser").status, COMPLETE)
        self.assertIn("would write xdg-settings:default-web-browser", transcript)

    def test_the_transcript_never_offers_a_third_party_browser(self) -> None:
        _, transcript = make_wizard().run(Answers())
        for forbidden in ("google-chrome", "dl.google.com", "chawan"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, transcript)

    def test_setup_never_claims_to_have_written_a_receipt(self) -> None:
        _, transcript = make_wizard().run(Answers(confirm_plan=True))
        self.assertIn("write_license_receipt", transcript)
        self.assertIn("BLOCKED", transcript)


@support.requires_candidate
class SkipAndResumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not REPLAY_BIN.is_dir():
            raise unittest.SkipTest(f"candidate replay binaries absent at {REPLAY_BIN}")

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_skipping_at_the_first_screen_leaves_a_complete_machine(self) -> None:
        state, transcript = make_wizard().run(Answers(skip_from="welcome"))
        self.assertTrue(state.setup_complete)
        self.assertEqual(state.counts()[SKIPPED], 8)
        self.assertEqual(state.counts()[BLOCKED], 0)
        self.assertIn("The system is complete and usable", transcript)

    def test_a_run_interrupted_midway_resumes_at_the_next_checkpoint(self) -> None:
        partial = SetupState.fresh(account="operator").complete("welcome")
        partial = partial.complete("account-summary")
        path = self.tmp / "setup.json"
        save(partial, path)

        reloaded = load(path)
        self.assertEqual(reloaded.resume_at(), "sudo-policy")

        wizard = make_wizard(state=reloaded, sudoers_dir=self.tmp / "sudoers.d")
        state, transcript = wizard.run(Answers())
        self.assertNotIn("== Welcome", transcript)
        self.assertIn("== Administrator password policy", transcript)
        self.assertTrue(state.setup_complete)

    def test_a_second_run_of_a_finished_state_changes_nothing(self) -> None:
        first, _ = make_wizard(sudoers_dir=self.tmp / "sudoers.d").run(Answers())
        wizard = make_wizard(state=first, sudoers_dir=self.tmp / "sudoers.d")
        second, transcript = wizard.run(Answers())
        self.assertEqual(first.checkpoints, second.checkpoints)
        self.assertIn("Setup summary", transcript)

    def test_setup_refuses_to_run_before_core_provisioning_finishes(self) -> None:
        state = SetupState.fresh(account="operator", core_complete=False)
        with self.assertRaises(CoreIncomplete):
            make_wizard(state=state).run(Answers())


@support.requires_candidate
class AccountResolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not REPLAY_BIN.is_dir():
            raise unittest.SkipTest(f"candidate replay binaries absent at {REPLAY_BIN}")

    def test_an_unresolved_account_blocks_rather_than_guesses(self) -> None:
        wizard = make_wizard(state=SetupState.fresh(account=None))
        state, transcript = wizard.run(Answers(sudo_passwordless=True))
        self.assertEqual(state.get("account-summary").status, BLOCKED)
        self.assertEqual(state.get("sudo-policy").status, BLOCKED)
        self.assertIn("will not guess an account", transcript)

    def test_the_transcript_never_prints_a_credential(self) -> None:
        _, transcript = make_wizard().run(Answers(sudo_passwordless=True))
        for needle in ("$y$", "$6$", "/etc/shadow"):
            with self.subTest(needle=needle):
                self.assertNotIn(needle, transcript)


if __name__ == "__main__":
    unittest.main()
