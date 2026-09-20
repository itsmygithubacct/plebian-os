"""Phase 8 — supervised execution, driven against fake providers.

Every acceptance criterion the scoping plan names for Phase 8 is exercised
here: cancel, resume, corrupt-mirror, low-disk, offline, partial failure,
shared artifacts not redownloaded and not destructively rolled back, a failed
large download leaving a complete machine, and byte accounting within a
recorded tolerance.

Actually invoking a provider is gated on F100-A3 and F106-P1. To exercise the
mechanics behind that gate the tests use an explicitly hypothetical ledger —
the same device already used for the admissible ready plan, and labelled the
same way. A test asserts that the *real* ledger still refuses.
"""

from __future__ import annotations

import dataclasses
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

import support

from f107b_setup.execution import (
    ACQUIRED,
    ALREADY_PRESENT,
    CANCELLED,
    CORRUPT_MIRROR,
    FAILED,
    INSTALLED,
    LOW_DISK,
    OFFLINE,
    PENDING,
    PROVIDER_ERROR,
    Cancelled,
    ExecutionController,
    ExecutionJournal,
    ExecutionRefusal,
    ItemRecord,
    ProviderOutcome,
    load_journal,
    save_journal,
    within_tolerance,
)
from f107b_setup.gates import LEDGER, GateLedger, GateRefusal

GIB = 1024**3

#: The ledger F107-B will have once its two entry gates close. It is a
#: hypothetical and is named one; the real ledger is asserted to refuse.
HYPOTHETICAL_OPEN_LEDGER = GateLedger(
    gates={
        gate_id: dataclasses.replace(gate, satisfied=True)
        for gate_id, gate in LEDGER.items()
    }
)


class FakeProvider:
    """A provider that fails exactly how it is told to."""

    def __init__(self, *, present=(), acquire_fail=None, install_fail=None, bytes_moved=None, raises=None):
        self.present = set(present)
        self.acquire_fail = acquire_fail or {}
        self.install_fail = install_fail or {}
        self.bytes_moved = bytes_moved or {}
        self.raises = raises or {}
        self.acquired: list[str] = []
        self.installed: list[str] = []
        self.removed: list[str] = []

    def already_present(self, artifact_id: str) -> bool:
        return artifact_id in self.present

    def acquire(self, artifact_id: str) -> ProviderOutcome:
        if artifact_id in self.raises:
            raise self.raises[artifact_id]
        self.acquired.append(artifact_id)
        if artifact_id in self.acquire_fail:
            cause, detail = self.acquire_fail[artifact_id]
            return ProviderOutcome(ok=False, cause=cause, detail=detail)
        return ProviderOutcome(ok=True, bytes_moved=self.bytes_moved.get(artifact_id))

    def install(self, artifact_id: str) -> ProviderOutcome:
        self.installed.append(artifact_id)
        if artifact_id in self.install_fail:
            cause, detail = self.install_fail[artifact_id]
            return ProviderOutcome(ok=False, cause=cause, detail=detail)
        return ProviderOutcome(ok=True)

    def remove(self, artifact_id: str) -> ProviderOutcome:
        self.removed.append(artifact_id)
        return ProviderOutcome(ok=True)


def journal(*items: ItemRecord, plan_id: str = "fixture:plan") -> ExecutionJournal:
    return ExecutionJournal(plan_id=plan_id, items=items)


def item(artifact: str, provider: str = "p", predicted: int | None = None, shared: bool = False) -> ItemRecord:
    return ItemRecord(
        artifact_id=artifact,
        provider=provider,
        profile_id=f"profile-{artifact}",
        predicted_bytes=predicted,
        shared=shared,
    )


class GateTests(unittest.TestCase):
    def test_the_real_ledger_refuses_to_invoke_a_provider(self) -> None:
        controller = ExecutionController(
            journal=journal(item("a")), providers={"p": FakeProvider()}, ledger=GateLedger()
        )
        outcome = controller.run()
        self.assertIsInstance(outcome, GateRefusal)
        self.assertEqual(sorted(g.gate_id for g in outcome.gates), ["F100-A3", "F106-P1"])

    def test_a_refused_run_touches_no_provider(self) -> None:
        provider = FakeProvider()
        ExecutionController(
            journal=journal(item("a")), providers={"p": provider}, ledger=GateLedger()
        ).run()
        self.assertEqual(provider.acquired, [])
        self.assertEqual(provider.installed, [])

    def test_rollback_is_gated_too(self) -> None:
        controller = ExecutionController(
            journal=journal(item("a")), providers={"p": FakeProvider()}, ledger=GateLedger()
        )
        self.assertIsInstance(controller.rollback(), GateRefusal)


class HappyPathTests(unittest.TestCase):
    def test_every_item_installs(self) -> None:
        provider = FakeProvider(bytes_moved={"a": 100, "b": 200})
        controller = ExecutionController(
            journal=journal(item("a", predicted=100), item("b", predicted=200)),
            providers={"p": provider},
            ledger=HYPOTHETICAL_OPEN_LEDGER,
        )
        result = controller.run()
        self.assertIsInstance(result, ExecutionJournal)
        self.assertEqual(result.counts()[INSTALLED], 2)
        self.assertTrue(result.complete)
        self.assertEqual(provider.acquired, ["a", "b"])


class PartialFailureTests(unittest.TestCase):
    """A failed item is an outcome. It does not abort the run."""

    def _run(self, **kwargs) -> ExecutionJournal:
        provider = FakeProvider(**kwargs)
        controller = ExecutionController(
            journal=journal(item("a"), item("b"), item("c")),
            providers={"p": provider},
            ledger=HYPOTHETICAL_OPEN_LEDGER,
        )
        self.provider = provider
        return controller.run()

    def test_a_corrupt_mirror_fails_one_item_only(self) -> None:
        result = self._run(acquire_fail={"b": (CORRUPT_MIRROR, "digest mismatch")})
        self.assertEqual(result.get("b").state, FAILED)
        self.assertEqual(result.get("b").cause, CORRUPT_MIRROR)
        self.assertEqual(result.get("a").state, INSTALLED)
        self.assertEqual(result.get("c").state, INSTALLED)

    def test_low_disk_fails_one_item_only(self) -> None:
        result = self._run(acquire_fail={"a": (LOW_DISK, "no space")})
        self.assertEqual(result.get("a").cause, LOW_DISK)
        self.assertEqual(result.counts()[INSTALLED], 2)

    def test_offline_fails_one_item_only(self) -> None:
        result = self._run(acquire_fail={"c": (OFFLINE, "no route")})
        self.assertEqual(result.get("c").cause, OFFLINE)
        self.assertEqual(result.counts()[INSTALLED], 2)

    def test_an_install_failure_after_a_good_download_is_recorded(self) -> None:
        result = self._run(install_fail={"b": (PROVIDER_ERROR, "dpkg returned 1")})
        self.assertEqual(result.get("b").state, FAILED)
        self.assertEqual(result.counts()[INSTALLED], 2)

    def test_a_provider_that_raises_is_contained(self) -> None:
        result = self._run(raises={"b": RuntimeError("boom")})
        self.assertEqual(result.get("b").state, FAILED)
        self.assertEqual(result.get("b").cause, PROVIDER_ERROR)
        self.assertIn("RuntimeError", result.get("b").detail)
        self.assertEqual(result.counts()[INSTALLED], 2)

    def test_a_missing_adapter_fails_only_its_own_item(self) -> None:
        controller = ExecutionController(
            journal=journal(item("a", provider="p"), item("b", provider="absent")),
            providers={"p": FakeProvider()},
            ledger=HYPOTHETICAL_OPEN_LEDGER,
        )
        result = controller.run()
        self.assertEqual(result.get("b").state, FAILED)
        self.assertEqual(result.get("a").state, INSTALLED)

    def test_an_unknown_failure_cause_is_refused_not_guessed(self) -> None:
        with self.assertRaises(ValueError):
            ProviderOutcome(ok=False, cause="something-new")


class CoreIsUntouchableTests(unittest.TestCase):
    """A failed 20 GB download leaves a bootable, setup-complete OS."""

    def test_a_failed_twenty_gigabyte_download_leaves_the_core_alone(self) -> None:
        provider = FakeProvider(acquire_fail={"big": (LOW_DISK, "20 GiB would not fit")})
        controller = ExecutionController(
            journal=journal(item("big", predicted=20 * GIB)),
            providers={"p": provider},
            ledger=HYPOTHETICAL_OPEN_LEDGER,
        )
        result = controller.run()
        self.assertEqual(result.get("big").state, FAILED)
        rendered = "\n".join(controller.render())
        self.assertIn("core system is complete and was not touched", rendered)

    def test_the_controller_holds_no_reference_to_core_state(self) -> None:
        # Structural, not aspirational: there is no field to reach through.
        fields = {f.name for f in dataclasses.fields(ExecutionController)}
        for forbidden in ("state", "setup_state", "core", "core_complete"):
            with self.subTest(field=forbidden):
                self.assertNotIn(forbidden, fields)

    def test_the_module_exposes_no_core_rollback(self) -> None:
        import f107b_setup.execution as module

        names = [n for n in dir(module) if "core" in n.lower()]
        self.assertEqual(names, [])


class SharedArtifactTests(unittest.TestCase):
    def test_a_present_artifact_is_not_redownloaded(self) -> None:
        provider = FakeProvider(present={"shared"})
        controller = ExecutionController(
            journal=journal(item("shared", shared=True), item("own")),
            providers={"p": provider},
            ledger=HYPOTHETICAL_OPEN_LEDGER,
        )
        result = controller.run()
        self.assertEqual(result.get("shared").state, ALREADY_PRESENT)
        self.assertNotIn("shared", provider.acquired)
        self.assertIn("own", provider.acquired)

    def test_rollback_previews_only_what_this_run_installed_and_owns(self) -> None:
        controller = ExecutionController(
            journal=journal(item("shared", shared=True), item("own"), item("failed")),
            providers={"p": FakeProvider(acquire_fail={"failed": (OFFLINE, "no route")})},
            ledger=HYPOTHETICAL_OPEN_LEDGER,
        )
        controller.run()
        preview = controller.preview_removal()
        self.assertEqual([i.artifact_id for i in preview], ["own"])

    def test_rollback_does_not_remove_a_shared_artifact(self) -> None:
        provider = FakeProvider()
        controller = ExecutionController(
            journal=journal(item("shared", shared=True), item("own")),
            providers={"p": provider},
            ledger=HYPOTHETICAL_OPEN_LEDGER,
        )
        controller.run()
        removed = controller.rollback()
        self.assertEqual([i.artifact_id for i in removed], ["own"])
        self.assertEqual(provider.removed, ["own"])
        self.assertNotIn("shared", provider.removed)

    def test_rollback_does_not_remove_a_failed_items_leftovers(self) -> None:
        provider = FakeProvider(install_fail={"b": (PROVIDER_ERROR, "failed")})
        controller = ExecutionController(
            journal=journal(item("a"), item("b")),
            providers={"p": provider},
            ledger=HYPOTHETICAL_OPEN_LEDGER,
        )
        controller.run()
        controller.rollback()
        self.assertEqual(provider.removed, ["a"])


class CancelAndResumeTests(unittest.TestCase):
    def test_cancelling_before_the_run_cancels_every_item(self) -> None:
        controller = ExecutionController(
            journal=journal(item("a"), item("b")),
            providers={"p": FakeProvider()},
            ledger=HYPOTHETICAL_OPEN_LEDGER,
        )
        controller.cancel()
        result = controller.run()
        self.assertEqual(result.counts()[CANCELLED], 2)
        self.assertTrue(result.cancelled)

    def test_a_provider_raising_cancelled_stops_that_item_cleanly(self) -> None:
        controller = ExecutionController(
            journal=journal(item("a"), item("b")),
            providers={"p": FakeProvider(raises={"a": Cancelled()})},
            ledger=HYPOTHETICAL_OPEN_LEDGER,
        )
        result = controller.run()
        self.assertEqual(result.get("a").state, CANCELLED)
        self.assertEqual(result.get("b").state, INSTALLED)

    def test_a_resumed_run_repeats_no_completed_work(self) -> None:
        provider = FakeProvider()
        done = journal(
            item("a").with_state(INSTALLED),
            item("b"),
        )
        controller = ExecutionController(
            journal=done, providers={"p": provider}, ledger=HYPOTHETICAL_OPEN_LEDGER
        )
        controller.run()
        self.assertEqual(provider.acquired, ["b"])
        self.assertNotIn("a", provider.acquired)

    def test_resume_from_lists_only_unfinished_items(self) -> None:
        j = journal(
            item("a").with_state(INSTALLED),
            item("b").with_state(FAILED, OFFLINE),
            item("c"),
        )
        self.assertEqual([i.artifact_id for i in j.resume_from()], ["c"])


class DurabilityTests(unittest.TestCase):
    """Progress must survive tab closure and logout."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "state" / "journal.json"
        self.addCleanup(self._tmp.cleanup)

    def test_the_journal_round_trips(self) -> None:
        j = journal(item("a", predicted=10).with_state(INSTALLED), item("b"))
        save_journal(j, self.path)
        self.assertEqual(load_journal(self.path), j)

    def test_the_journal_is_written_at_mode_0600(self) -> None:
        save_journal(journal(item("a")), self.path)
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)

    def test_progress_is_persisted_after_every_transition_not_at_the_end(self) -> None:
        # A provider that dies mid-run stands in for a closed tab. The journal
        # on disk must already know what happened before the crash.
        class Dies(FakeProvider):
            def install(self, artifact_id):
                if artifact_id == "b":
                    raise KeyboardInterrupt("tab closed")
                return super().install(artifact_id)

        controller = ExecutionController(
            journal=journal(item("a"), item("b"), item("c")),
            providers={"p": Dies()},
            ledger=HYPOTHETICAL_OPEN_LEDGER,
            journal_path=self.path,
        )
        with self.assertRaises(KeyboardInterrupt):
            controller.run()

        recovered = load_journal(self.path)
        self.assertEqual(recovered.get("a").state, INSTALLED)
        self.assertEqual(recovered.get("b").state, "installing")
        self.assertEqual(recovered.get("c").state, PENDING)
        self.assertEqual([i.artifact_id for i in recovered.resume_from()], ["b", "c"])

    def test_a_foreign_schema_is_refused(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"schema": "something/v9"}), encoding="utf-8")
        with self.assertRaisesRegex(ExecutionRefusal, "schema"):
            load_journal(self.path)

    def test_a_newer_journal_version_is_refused_not_migrated(self) -> None:
        document = journal(item("a")).to_document()
        document["journal_version"] = 99
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(ExecutionRefusal, "migration must be reviewed"):
            load_journal(self.path)

    def test_a_duplicate_key_is_refused(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text('{"schema": "a", "schema": "b"}', encoding="utf-8")
        with self.assertRaisesRegex(ExecutionRefusal, "duplicate key"):
            load_journal(self.path)

    def test_the_journal_carries_no_credential_shaped_member(self) -> None:
        save_journal(journal(item("a")), self.path)
        text = self.path.read_text(encoding="utf-8")
        for needle in ("$y$", "$6$", "/etc/shadow", "oauth", "token"):
            with self.subTest(needle=needle):
                self.assertNotIn(needle, text)


class ByteAccountingTests(unittest.TestCase):
    def test_unknown_on_either_side_is_unknown_not_within_tolerance(self) -> None:
        self.assertIsNone(within_tolerance(None, 100))
        self.assertIsNone(within_tolerance(100, None))
        self.assertIsNone(within_tolerance(None, None))

    def test_an_exact_match_is_within_tolerance(self) -> None:
        self.assertIs(within_tolerance(1000, 1000), True)

    def test_the_boundary_is_inclusive(self) -> None:
        self.assertIs(within_tolerance(1000, 1100, 0.10), True)
        self.assertIs(within_tolerance(1000, 1101, 0.10), False)

    def test_zero_predicted_admits_only_zero_actual(self) -> None:
        self.assertIs(within_tolerance(0, 0), True)
        self.assertIs(within_tolerance(0, 1), False)

    def test_a_negative_count_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            within_tolerance(-1, 1)

    def test_one_unmeasured_item_makes_the_run_total_unknown(self) -> None:
        j = journal(
            item("a", predicted=100).with_state(INSTALLED),
            item("b", predicted=None).with_state(INSTALLED),
        )
        self.assertIsNone(j.totals()["predicted_bytes"])

    def test_an_already_present_item_is_excluded_from_both_sides(self) -> None:
        provider = FakeProvider(present={"shared"}, bytes_moved={"own": 100})
        controller = ExecutionController(
            journal=journal(item("shared", predicted=999, shared=True), item("own", predicted=100)),
            providers={"p": provider},
            ledger=HYPOTHETICAL_OPEN_LEDGER,
        )
        controller.run()
        accounting = controller.accounting()
        self.assertEqual(accounting["predicted_bytes"], 100)
        self.assertEqual(accounting["acquired_bytes"], 100)
        self.assertIs(accounting["within_tolerance"], True)

    def test_the_render_says_unknown_rather_than_zero(self) -> None:
        controller = ExecutionController(
            journal=journal(item("a", predicted=None)),
            providers={"p": FakeProvider()},
            ledger=HYPOTHETICAL_OPEN_LEDGER,
        )
        controller.run()
        rendered = "\n".join(controller.render())
        self.assertIn("predicted unknown", rendered)
        self.assertNotIn("predicted 0,", rendered)


class JournalFromPlanTests(unittest.TestCase):
    def test_a_plan_with_no_items_makes_an_empty_journal(self) -> None:
        j = ExecutionJournal.from_plan({"plan_id": "p", "items": []})
        self.assertEqual(j.items, ())
        self.assertTrue(j.complete)

    def test_shared_ids_are_marked_from_the_caller_not_guessed(self) -> None:
        plan = {
            "plan_id": "p",
            "items": [
                {"artifact_id": "a", "provider": "p", "profile_id": "x"},
                {"artifact_id": "b", "provider": "p", "profile_id": "y"},
            ],
        }
        j = ExecutionJournal.from_plan(plan, shared={"b"})
        self.assertFalse(j.get("a").shared)
        self.assertTrue(j.get("b").shared)

    def test_an_unknown_state_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            item("a").with_state("half-done")

    def test_a_failed_item_must_name_a_known_cause(self) -> None:
        with self.assertRaises(ValueError):
            item("a").with_state(FAILED, "made-up-cause")


if __name__ == "__main__":
    unittest.main()
