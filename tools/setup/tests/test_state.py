"""Setup state: skip, resume, stale refusal, atomic persistence, no secrets."""

from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

import support
from support import SCHEMAS, load_json

from jsonschema import Draft202012Validator

from f107b_setup.state import (
    BLOCKED,
    CHECKPOINT_IDS,
    FORBIDDEN_STATE_KEYS,
    COMPLETE,
    PENDING,
    SKIPPED,
    STATE_VERSION,
    SetupState,
    StaleState,
    load,
    save,
)

SCHEMA = load_json(SCHEMAS / "plebian.setup-v1.schema.json")
VALIDATOR = Draft202012Validator(SCHEMA)


class ShapeTests(unittest.TestCase):
    def test_a_fresh_state_has_eight_pending_checkpoints(self) -> None:
        state = SetupState.fresh(account="operator")
        self.assertEqual(len(state.checkpoints), 8)
        self.assertEqual(state.counts()[PENDING], 8)
        self.assertEqual([c.checkpoint_id for c in state.checkpoints], list(CHECKPOINT_IDS))

    def test_a_fresh_state_validates_against_the_published_schema(self) -> None:
        errors = list(VALIDATOR.iter_errors(SetupState.fresh(account="operator").to_document()))
        self.assertEqual(errors, [], errors)

    def test_a_fully_walked_state_validates(self) -> None:
        state = SetupState.fresh(account="operator")
        state = state.complete("welcome").skip("account-summary").block("sudo-policy", "why")
        errors = list(VALIDATOR.iter_errors(state.to_document()))
        self.assertEqual(errors, [], errors)


class NavigationTests(unittest.TestCase):
    def test_resume_returns_the_first_non_terminal_checkpoint(self) -> None:
        state = SetupState.fresh(account="operator")
        self.assertEqual(state.resume_at(), "welcome")
        state = state.complete("welcome")
        self.assertEqual(state.resume_at(), "account-summary")

    def test_a_blocked_checkpoint_is_terminal_and_is_stepped_past(self) -> None:
        state = SetupState.fresh(account="operator").complete("welcome")
        state = state.block("account-summary", "no resolved account")
        self.assertEqual(state.resume_at(), "sudo-policy")

    def test_skipping_the_rest_completes_setup_without_completing_checkpoints(self) -> None:
        state = SetupState.fresh(account="operator").complete("welcome")
        state = state.skip_all_remaining()
        self.assertIsNone(state.resume_at())
        self.assertTrue(state.setup_complete)
        self.assertEqual(state.counts()[COMPLETE], 1)
        self.assertEqual(state.counts()[SKIPPED], 7)

    def test_a_blocked_checkpoint_must_name_a_reason(self) -> None:
        with self.assertRaises(ValueError):
            SetupState.fresh().block("welcome", "")

    def test_an_unknown_status_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            SetupState.fresh().mark("welcome", "almost")

    def test_counts_sum_to_the_checkpoint_population(self) -> None:
        state = SetupState.fresh().complete("welcome").skip("account-summary")
        state = state.block("sudo-policy", "gated")
        self.assertEqual(sum(state.counts().values()), 8)


class PersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "state" / "setup.json"
        self.addCleanup(self._tmp.cleanup)

    def test_a_round_trip_preserves_every_checkpoint(self) -> None:
        state = SetupState.fresh(account="operator").complete("welcome")
        state = state.block("plan-review", "F100-A3")
        save(state, self.path)
        self.assertEqual(load(self.path), state)

    def test_the_record_is_written_at_mode_0600(self) -> None:
        save(SetupState.fresh(account="operator"), self.path)
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)

    def test_no_temporary_file_is_left_behind(self) -> None:
        save(SetupState.fresh(account="operator"), self.path)
        leftovers = [p.name for p in self.path.parent.iterdir() if p.name.startswith(".setup-state-")]
        self.assertEqual(leftovers, [])

    def test_a_newer_state_version_is_refused_not_downgraded(self) -> None:
        document = SetupState.fresh(account="operator").to_document()
        document["state_version"] = STATE_VERSION + 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(StaleState, "newer"):
            load(self.path)

    def test_an_older_state_version_is_refused_not_migrated(self) -> None:
        document = SetupState.fresh(account="operator").to_document()
        document["state_version"] = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(StaleState, "migration must be reviewed"):
            load(self.path)

    def test_an_unknown_schema_is_refused(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"schema": "plebian.setup/v2"}), encoding="utf-8")
        with self.assertRaisesRegex(StaleState, "schema"):
            load(self.path)

    def test_a_reordered_checkpoint_list_is_refused(self) -> None:
        document = SetupState.fresh(account="operator").to_document()
        document["checkpoints"].reverse()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(StaleState, "checkpoint order"):
            load(self.path)

    def test_a_state_carrying_a_secret_is_refused(self) -> None:
        document = SetupState.fresh(account="operator").to_document()
        document["password_hash"] = "$y$j9T$notreal"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(StaleState, "forbidden member"):
            load(self.path)

    def test_a_duplicate_key_is_refused(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text('{"schema": "plebian.setup/v1", "schema": "x"}', encoding="utf-8")
        with self.assertRaisesRegex(StaleState, "duplicate key"):
            load(self.path)

    def test_no_persisted_record_carries_a_credential_value(self) -> None:
        # The English word "password" appears in policy prose and is fine; a
        # credential *value* or a member named for one is not.
        state = SetupState.fresh(account="operator").complete("sudo-policy", "passwordless sudo")
        save(state, self.path)
        document = json.loads(self.path.read_text(encoding="utf-8"))
        for key in FORBIDDEN_STATE_KEYS:
            with self.subTest(key=key):
                self.assertNotIn(key, document)
        text = self.path.read_text(encoding="utf-8")
        for needle in ("$y$", "$6$", "$1$", "/etc/shadow"):
            with self.subTest(needle=needle):
                self.assertNotIn(needle, text)


if __name__ == "__main__":
    unittest.main()
