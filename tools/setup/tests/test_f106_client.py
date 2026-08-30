"""The consumer half of the F106 subprocess contract.

Half of these tests run against Track D's replay binaries, which honour the
contract. The other half run against deliberately dishonest doubles, because a
consumer that only ever sees a well-behaved producer has not been tested.
"""

from __future__ import annotations

import os
import stat
import tempfile
import textwrap
import unittest
from pathlib import Path

import support
from support import CANDIDATE_ROOT, REPLAY_BIN

from f107b_setup.f106_client import (
    COMMANDS,
    ContractViolation,
    F106Client,
    Failure,
    JsonResult,
    TextResult,
    parse_document,
)


def write_double(directory: Path, program: str, body: str) -> None:
    path = directory / program
    path.write_text(
        "#!/usr/bin/env python3\nimport sys\n" + textwrap.dedent(body), encoding="utf-8"
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


@support.requires_candidate
class ReplayContractTests(unittest.TestCase):
    """All seven contract commands, against the candidate's own doubles."""

    @classmethod
    def setUpClass(cls) -> None:
        if not REPLAY_BIN.is_dir():
            raise unittest.SkipTest(f"candidate replay binaries absent at {REPLAY_BIN}")
        cls.client = F106Client(bin_dir=REPLAY_BIN)

    def test_seven_of_seven_contract_commands_are_declared(self) -> None:
        self.assertEqual(len(COMMANDS), 7)

    def test_six_json_commands_return_admitted_envelopes(self) -> None:
        json_commands = [
            command for command, (_, schema) in COMMANDS.items() if schema is not None
        ]
        self.assertEqual(len(json_commands), 6)
        checked = 0
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "plan.json"
            plan_path.write_text(
                (CANDIDATE_ROOT / "fixtures" / "plans" / "blocked-no-f100-c0.json").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            for command in json_commands:
                with self.subTest(command=command):
                    kwargs = {"plan_path": plan_path} if command == "sizer.install" else {}
                    result = self.client.call(command, **kwargs)
                    self.assertIsInstance(result, JsonResult)
                    self.assertEqual(result.envelope["command"], command)
                    self.assertEqual(result.data["schema"], COMMANDS[command][1])
                    self.assertIn(result.status, {"ok", "unknown", "blocked"})
                    checked += 1
        self.assertEqual(checked, 6)

    def test_the_one_text_command_is_not_parsed_for_decisions(self) -> None:
        result = self.client.call("hardware.show")
        self.assertIsInstance(result, TextResult)
        self.assertTrue(result.text.endswith("\n"))

    def test_a_usage_error_is_a_contract_shaped_failure(self) -> None:
        # An unknown vocabulary reaches the producer only through the client's
        # own table, so reach past it deliberately.
        raw = self.client._run(["plebian-hardware", "nonsense"])
        self.assertEqual(raw[0], 2)
        self.assertEqual(raw[1], b"")

    def test_an_unsupported_command_id_is_refused_before_execution(self) -> None:
        with self.assertRaises(ContractViolation):
            self.client.call("sizer.recommend.asr")

    def test_a_plan_path_is_refused_on_a_command_that_takes_none(self) -> None:
        with self.assertRaises(ContractViolation):
            self.client.call("sizer.snapshot", plan_path=Path("/dev/null"))

    def test_install_without_a_plan_path_is_refused(self) -> None:
        with self.assertRaises(ContractViolation):
            self.client.call("sizer.install")


class DocumentParsingTests(unittest.TestCase):
    def test_duplicate_keys_are_rejected(self) -> None:
        with self.assertRaises(ContractViolation):
            parse_document(b'{"a": 1, "a": 2}\n')

    def test_trailing_data_is_rejected(self) -> None:
        with self.assertRaises(ContractViolation):
            parse_document(b'{"a": 1} {"b": 2}\n')

    def test_a_second_document_on_a_second_line_is_rejected(self) -> None:
        with self.assertRaises(ContractViolation):
            parse_document(b'{"a": 1}\n{"b": 2}\n')

    def test_non_finite_numbers_are_rejected(self) -> None:
        with self.assertRaises(ContractViolation):
            parse_document(b'{"a": NaN}\n')
        with self.assertRaises(ContractViolation):
            parse_document(b'{"a": [1, Infinity]}\n')

    def test_missing_terminator_is_rejected(self) -> None:
        with self.assertRaises(ContractViolation):
            parse_document(b'{"a": 1}')

    def test_a_non_object_document_is_rejected(self) -> None:
        with self.assertRaises(ContractViolation):
            parse_document(b"[1, 2]\n")

    def test_a_well_formed_document_parses(self) -> None:
        self.assertEqual(parse_document(b'{"a": 1}\n'), {"a": 1})


class DishonestProducerTests(unittest.TestCase):
    """Seven ways a producer can break the contract, all refused."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.bin_dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _client(self) -> F106Client:
        return F106Client(bin_dir=self.bin_dir, timeout_seconds=5)

    def test_exit_zero_with_stderr_is_refused(self) -> None:
        write_double(
            self.bin_dir,
            "plebian-hardware",
            """
            sys.stdout.write('{"schema":"plebian.cli.response/v1","command":"hardware.inventory",'
                             '"status":"ok","warnings":[],"data":{"schema":"plebian.hardware/v1"}}\\n')
            sys.stderr.write("a log line\\n")
            """,
        )
        with self.assertRaisesRegex(ContractViolation, "stderr"):
            self._client().call("hardware.inventory")

    def test_nonzero_exit_with_stdout_is_refused(self) -> None:
        write_double(
            self.bin_dir,
            "plebian-hardware",
            """
            sys.stdout.write("partial output\\n")
            sys.stderr.write("failed\\n")
            raise SystemExit(75)
            """,
        )
        with self.assertRaisesRegex(ContractViolation, "stdout empty"):
            self._client().call("hardware.inventory")

    def test_an_exit_status_outside_the_contract_is_refused(self) -> None:
        write_double(
            self.bin_dir,
            "plebian-hardware",
            """
            sys.stderr.write("odd\\n")
            raise SystemExit(3)
            """,
        )
        with self.assertRaisesRegex(ContractViolation, "exit status 3"):
            self._client().call("hardware.inventory")

    def test_a_multi_line_diagnostic_is_refused(self) -> None:
        write_double(
            self.bin_dir,
            "plebian-hardware",
            """
            sys.stderr.write("line one\\nline two\\n")
            raise SystemExit(69)
            """,
        )
        with self.assertRaisesRegex(ContractViolation, "more than one diagnostic"):
            self._client().call("hardware.inventory")

    def test_a_contract_shaped_failure_is_returned_not_raised(self) -> None:
        write_double(
            self.bin_dir,
            "plebian-hardware",
            """
            sys.stderr.write("required local dependency unavailable\\n")
            raise SystemExit(69)
            """,
        )
        result = self._client().call("hardware.inventory")
        self.assertIsInstance(result, Failure)
        self.assertEqual(result.exit_status, 69)
        self.assertEqual(result.meaning, "required local dependency unavailable")

    def test_a_mismatched_data_schema_is_refused(self) -> None:
        write_double(
            self.bin_dir,
            "plebian-model-sizer",
            """
            sys.stdout.write('{"schema":"plebian.cli.response/v1","command":"sizer.snapshot",'
                             '"status":"ok","warnings":[],'
                             '"data":{"schema":"plebian.models.fit-result/v1"}}\\n')
            """,
        )
        with self.assertRaisesRegex(ContractViolation, "data schema"):
            self._client().call("sizer.snapshot")

    def test_a_mismatched_command_echo_is_refused(self) -> None:
        write_double(
            self.bin_dir,
            "plebian-model-sizer",
            """
            sys.stdout.write('{"schema":"plebian.cli.response/v1","command":"sizer.plan.local-ai-balanced",'
                             '"status":"ok","warnings":[],'
                             '"data":{"schema":"plebian.models.snapshot/v1"}}\\n')
            """,
        )
        with self.assertRaisesRegex(ContractViolation, "envelope command"):
            self._client().call("sizer.snapshot")

    def test_an_overrunning_command_is_refused_at_the_bound(self) -> None:
        write_double(
            self.bin_dir,
            "plebian-hardware",
            """
            import time
            time.sleep(30)
            """,
        )
        client = F106Client(bin_dir=self.bin_dir, timeout_seconds=1)
        with self.assertRaisesRegex(ContractViolation, "read-only bound"):
            client.call("hardware.inventory")

    def test_the_child_environment_is_reduced(self) -> None:
        write_double(
            self.bin_dir,
            "plebian-hardware",
            """
            import json, os
            names = sorted(os.environ)
            body = {"schema": "plebian.cli.response/v1", "command": "hardware.inventory",
                    "status": "ok", "warnings": [],
                    "data": {"schema": "plebian.hardware/v1", "seen": names}}
            sys.stdout.write(json.dumps(body) + "\\n")
            """,
        )
        os.environ["F107B_LEAK_CANARY"] = "must-not-be-inherited"
        self.addCleanup(os.environ.pop, "F107B_LEAK_CANARY", None)
        result = self._client().call("hardware.inventory")
        self.assertIsInstance(result, JsonResult)
        self.assertEqual(sorted(result.data["seen"]), ["LANG", "LC_ALL", "PATH"])


if __name__ == "__main__":
    unittest.main()
