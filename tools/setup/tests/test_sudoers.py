"""The passwordless-sudo drop-in: one account, mode 0440, validated or refused."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import support

from f107b_setup import sudoers


class DropinTests(unittest.TestCase):
    def test_the_dropin_names_one_account_and_no_group(self) -> None:
        dropin = sudoers.build_dropin("operator")
        self.assertIn("operator ALL=(ALL:ALL) NOPASSWD: ALL", dropin.content)
        self.assertNotIn("%sudo", dropin.content)
        self.assertNotIn("%admin", dropin.content)
        self.assertFalse(sudoers.contains_group_wide_nopasswd(dropin.content))

    def test_the_dropin_mode_is_0440(self) -> None:
        self.assertEqual(sudoers.build_dropin("operator").mode, 0o440)

    def test_a_group_subject_is_refused_as_a_group_not_as_a_bad_name(self) -> None:
        # The account pattern would also reject these. That is not enough: the
        # refusal must be the *group* refusal, so that widening the name rules
        # later cannot quietly admit a group.
        for subject in ("%sudo", "%admin", "+netgroup", "#1000"):
            with self.subTest(subject=subject):
                with self.assertRaises(sudoers.SudoersRefusal) as caught:
                    sudoers.build_dropin(subject)
                self.assertIn("group or netgroup", str(caught.exception))
                self.assertIn("one account only", str(caught.exception))

    def test_a_group_wide_fragment_is_detected(self) -> None:
        self.assertTrue(
            sudoers.contains_group_wide_nopasswd("%sudo ALL=(ALL:ALL) NOPASSWD: ALL\n")
        )
        self.assertFalse(
            sudoers.contains_group_wide_nopasswd("# %sudo ALL=(ALL) NOPASSWD: ALL\n")
        )

    def test_hostile_account_names_are_refused(self) -> None:
        hostile = (
            "operator ALL=(ALL) NOPASSWD: ALL",
            "operator\nroot",
            "operator ALL",
            "../../etc/passwd",
            "opera tor",
            "Operator",
            "1000",
            "",
            "a" * 33,
            "operator#",
            "operator,root",
            "operator\tALL",
        )
        refused = 0
        for name in hostile:
            with self.subTest(name=name):
                with self.assertRaises(sudoers.SudoersRefusal):
                    sudoers.build_dropin(name)
                refused += 1
        self.assertEqual(refused, len(hostile))

    def test_boundary_names_are_accepted(self) -> None:
        for name in ("a", "_svc", "a" * 32, "op-1_x"):
            with self.subTest(name=name):
                self.assertIn(name, sudoers.build_dropin(name).content)

    def test_validation_reports_unavailable_rather_than_passing(self) -> None:
        dropin = sudoers.build_dropin("operator")
        with tempfile.TemporaryDirectory() as tmp:
            result, detail = sudoers.validate(dropin, Path(tmp))
        self.assertIn(
            result,
            {sudoers.VALIDATION_PASS, sudoers.VALIDATION_UNAVAILABLE},
        )
        if result == sudoers.VALIDATION_UNAVAILABLE:
            self.assertIn("visudo", detail)

    def test_a_group_wide_fragment_fails_validation_without_visudo(self) -> None:
        forged = sudoers.SudoersDropin(
            account="operator",
            filename="90-forged",
            content="%sudo ALL=(ALL:ALL) NOPASSWD: ALL\n",
        )
        with tempfile.TemporaryDirectory() as tmp:
            result, detail = sudoers.validate(forged, Path(tmp))
        self.assertEqual(result, sudoers.VALIDATION_FAIL)
        self.assertIn("group", detail)


if __name__ == "__main__":
    unittest.main()
