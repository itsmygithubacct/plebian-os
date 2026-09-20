"""The runner's own logic, including regressions for F107B-01 and F107B-03.

The runner grew real logic when it started guarding its own controls. Untested
control logic is how a control stops being able to fail, which is the finding
this module exists because of.
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

import support
from support import PACKET_ROOT


def _load_runner():
    """Import ``run-checks.py``, whose filename is not a legal module name."""

    spec = importlib.util.spec_from_file_location(
        "f107b_run_checks", PACKET_ROOT / "run-checks.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = _load_runner()


class ManifestParsingTests(unittest.TestCase):
    """F107B-03: the denominator is a file count, taken from the manifest."""

    def _manifest(self, text: str) -> Path:
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".sums", delete=False, encoding="utf-8"
        )
        handle.write(text)
        handle.close()
        path = Path(handle.name)
        self.addCleanup(path.unlink)
        return path

    def test_a_manifest_parses_to_one_entry_per_file(self) -> None:
        path = self._manifest(f"{'a' * 64}  ./one\n{'b' * 64}  ./two\n")
        self.assertEqual(len(runner.parse_manifest(path)), 2)

    def test_blank_lines_do_not_inflate_the_file_count(self) -> None:
        # The old denominator counted output lines, so anything sha256sum
        # printed — a warning, a blank — became a "file" and the count could
        # only ever equal itself.
        path = self._manifest(f"\n{'a' * 64}  ./one\n\n{'b' * 64}  ./two\n\n")
        self.assertEqual(len(runner.parse_manifest(path)), 2)

    def test_a_warning_shaped_line_is_refused_not_counted(self) -> None:
        path = self._manifest(
            f"{'a' * 64}  ./one\nsha256sum: WARNING: 1 line is improperly formatted\n"
        )
        with self.assertRaisesRegex(ValueError, "malformed manifest line"):
            runner.parse_manifest(path)

    def test_a_duplicate_entry_is_refused(self) -> None:
        path = self._manifest(f"{'a' * 64}  ./one\n{'b' * 64}  ./one\n")
        with self.assertRaisesRegex(ValueError, "duplicate manifest entry"):
            runner.parse_manifest(path)

    def test_the_packets_own_manifest_parses(self) -> None:
        entries = runner.parse_manifest(runner.SELF_MANIFEST)
        self.assertGreater(len(entries), 30)
        self.assertNotIn("./SHA256SUMS", entries)


class InventoryParsingTests(unittest.TestCase):
    """F107B-01: discovery is compared to a committed expectation."""

    def _inventory(self, text: str) -> Path:
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".tsv", delete=False, encoding="utf-8"
        )
        handle.write(text)
        handle.close()
        path = Path(handle.name)
        self.addCleanup(path.unlink)
        return path

    def test_comments_and_blanks_are_ignored(self) -> None:
        path = self._inventory("# a comment\n\ntest_one\t3\ntest_two\t4\n")
        self.assertEqual(runner.parse_inventory(path), {"test_one": 3, "test_two": 4})

    def test_a_malformed_line_is_refused(self) -> None:
        path = self._inventory("test_one 3\n")
        with self.assertRaisesRegex(ValueError, "malformed inventory line"):
            runner.parse_inventory(path)

    def test_a_duplicate_module_is_refused(self) -> None:
        path = self._inventory("test_one\t3\ntest_one\t4\n")
        with self.assertRaisesRegex(ValueError, "duplicate inventory module"):
            runner.parse_inventory(path)

    def test_the_committed_inventory_parses_and_is_not_empty(self) -> None:
        expected = runner.parse_inventory(runner.TEST_INVENTORY)
        self.assertGreaterEqual(len(expected), 11)
        self.assertGreater(sum(expected.values()), 150)

    def test_this_module_is_itself_in_the_committed_inventory(self) -> None:
        # A test module that inventories others but not itself would be the
        # same blind spot one layer up.
        self.assertIn("test_runner", runner.parse_inventory(runner.TEST_INVENTORY))


class InventoryComparisonTests(unittest.TestCase):
    """The comparison must name a difference in either direction."""

    def _suite(self, cases: dict[str, int]) -> unittest.TestSuite:
        suite = unittest.TestSuite()
        for module, count in cases.items():
            for index in range(count):
                case = unittest.FunctionTestCase(lambda: None)
                case.__class__ = type(
                    "Case", (unittest.FunctionTestCase,), {"__module__": module}
                )
                suite.addTest(case)
        return suite

    def test_discovery_counts_per_module(self) -> None:
        counts = runner.discovered_inventory(self._suite({"test_a": 2, "test_b": 3}))
        self.assertEqual(counts, {"test_a": 2, "test_b": 3})

    def test_an_empty_suite_discovers_nothing(self) -> None:
        self.assertEqual(runner.discovered_inventory(unittest.TestSuite()), {})

    def test_the_live_suite_matches_the_committed_inventory(self) -> None:
        loader = unittest.TestLoader()
        suite = loader.discover(str(PACKET_ROOT / "tests"), pattern="test_*.py")
        ok, lines = runner.check_inventory(suite)
        self.assertTrue(ok, "\n".join(lines))


class ExitStatusTests(unittest.TestCase):
    """A control failure must be distinguishable from a test failure."""

    def test_the_five_statuses_are_distinct(self) -> None:
        statuses = {
            runner.EXIT_PASS,
            runner.EXIT_TEST_FAILURE,
            runner.EXIT_CANDIDATE_MISMATCH,
            runner.EXIT_PARTIAL,
            runner.EXIT_CONTROL_FAILURE,
        }
        self.assertEqual(len(statuses), 5)

    def test_a_control_failure_is_not_a_test_failure(self) -> None:
        self.assertNotEqual(runner.EXIT_CONTROL_FAILURE, runner.EXIT_TEST_FAILURE)
        self.assertNotEqual(runner.EXIT_CONTROL_FAILURE, runner.EXIT_PASS)


class ControlCheckTests(unittest.TestCase):
    def test_the_packets_own_controls_verify_right_now(self) -> None:
        ok, lines = runner.check_controls()
        self.assertTrue(ok, "\n".join(lines))

    def test_the_mutable_subtree_is_excluded_and_named(self) -> None:
        # The exclusion must be a narrow, stated one — not a blanket skip.
        self.assertEqual(runner.MUTABLE_PREFIX, "./src/f107b_setup/")
        entries = runner.parse_manifest(runner.SELF_MANIFEST)
        excluded = [n for n in entries if n.startswith(runner.MUTABLE_PREFIX)]
        guarded = [n for n in entries if not n.startswith(runner.MUTABLE_PREFIX)]
        self.assertGreater(len(guarded), len(excluded))
        # Every test file must be on the guarded side.
        self.assertTrue(all(not n.startswith(runner.MUTABLE_PREFIX) for n in entries if "/tests/" in n))


if __name__ == "__main__":
    unittest.main()
