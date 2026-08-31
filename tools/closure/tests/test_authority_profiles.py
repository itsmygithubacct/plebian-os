from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import types
import unittest
from pathlib import Path


AUTHORITY = Path(__file__).resolve().parents[1] / "authority"
SPECIFICATION = importlib.util.spec_from_file_location(
    "authority_build_bundle", AUTHORITY / "build_bundle.py"
)
assert SPECIFICATION is not None and SPECIFICATION.loader is not None
BUILDER = importlib.util.module_from_spec(SPECIFICATION)
SPECIFICATION.loader.exec_module(BUILDER)
BOOTSTRAP_SPECIFICATION = importlib.util.spec_from_file_location(
    "authority_bootstrap", AUTHORITY / "bootstrap.py"
)
assert (
    BOOTSTRAP_SPECIFICATION is not None
    and BOOTSTRAP_SPECIFICATION.loader is not None
)
BOOTSTRAP = importlib.util.module_from_spec(BOOTSTRAP_SPECIFICATION)
BOOTSTRAP_SPECIFICATION.loader.exec_module(BOOTSTRAP)


class TrustedLauncherProfileTest(unittest.TestCase):
    def load(self, name: str) -> dict[str, object]:
        value, raw = BUILDER.load_profile((AUTHORITY / "profiles" / name).resolve())
        self.assertEqual(
            raw,
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
            + b"\n",
        )
        return value

    def write_mutant(self, value: object) -> Path:
        temporary = tempfile.TemporaryDirectory(prefix="trusted-profile-test-")
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "profile.json"
        path.write_bytes(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
            + b"\n"
        )
        return path.resolve()

    def test_f120_profile_preserves_both_public_commands(self) -> None:
        profile = self.load("f120-reference-v1.json")
        commands = {command["name"]: command for command in profile["commands"]}
        self.assertEqual(set(commands), {"check", "cli"})
        self.assertEqual(
            [child["id"] for child in commands["check"]["children"]],
            ["contracts", "candidate-contracts", "tests"],
        )
        self.assertEqual(commands["check"]["argument_mode"], "forbidden")
        self.assertEqual(commands["cli"]["argument_mode"], "required")
        self.assertTrue(
            commands["cli"]["children"][0]["cases"][0]["forward_arguments"]
        )

    def test_td_p1_encodes_three_children_and_seven_exact_replays(self) -> None:
        profile = self.load("track-d-td-p1-v1.json")
        command = profile["commands"][0]
        children = command["children"]
        self.assertEqual(profile["profile_id"], "track-d.td-p1/v1")
        self.assertEqual(command["name"], "qualify")
        self.assertEqual(
            [child["id"] for child in children],
            [
                "candidate-validator",
                "plebian-hardware-replay",
                "plebian-model-sizer-replay",
            ],
        )
        replay_cases = [
            case for child in children[1:] for case in child["cases"]
        ]
        self.assertEqual(len(replay_cases), 7)
        for case in replay_cases:
            self.assertEqual(case["expected_exit"], 0)
            self.assertEqual(case["stdout"]["mode"], "file")
            self.assertEqual(case["stderr"], {"mode": "empty"})
            self.assertFalse(case["forward_arguments"])

    def test_td_hw_staged_children_cannot_import_subject_source(self) -> None:
        profile = self.load("track-d-td-hw-v1.json")
        children = profile["commands"][0]["children"]
        self.assertEqual(profile["profile_id"], "track-d.td-hw/v1")
        self.assertEqual(len(children), 5)
        self.assertEqual(children[0]["kind"], "python-unittest")
        for child in children[1:]:
            self.assertEqual(child["script"]["root"], "dependency")
            self.assertEqual(child["script"]["path"], "bin/plebian-hardware")
            self.assertEqual(
                {entry["root"] for entry in child["python_paths"]},
                {"dependency"},
            )
        invalid = children[-1]["cases"][0]
        self.assertEqual(invalid["expected_exit"], 2)
        self.assertEqual(invalid["stdout"], {"mode": "empty"})
        self.assertEqual(invalid["stderr"]["mode"], "literal-utf8")

    def test_profile_contract_refuses_semantic_ambiguity(self) -> None:
        original = self.load("f120-reference-v1.json")
        mutations: list[dict[str, object]] = []

        extra = copy.deepcopy(original)
        extra["unbound"] = True
        mutations.append(extra)

        traversal = copy.deepcopy(original)
        traversal["commands"][0]["children"][0]["script"]["path"] = "../escape.py"
        mutations.append(traversal)

        duplicate_child = copy.deepcopy(original)
        duplicate_child["commands"][0]["children"][1]["id"] = "contracts"
        mutations.append(duplicate_child)

        forwarding = copy.deepcopy(original)
        forwarding["commands"][0]["children"][0]["cases"][0][
            "forward_arguments"
        ] = True
        mutations.append(forwarding)

        unsupported = copy.deepcopy(original)
        unsupported["commands"][0]["children"][0]["kind"] = "shell"
        mutations.append(unsupported)

        boolean_exit = copy.deepcopy(original)
        boolean_exit["commands"][0]["children"][0]["cases"][0][
            "expected_exit"
        ] = True
        mutations.append(boolean_exit)

        for mutation in mutations:
            with self.subTest(mutation=mutations.index(mutation)):
                with self.assertRaises(BUILDER.BundleError):
                    BUILDER.load_profile(self.write_mutant(mutation))

    def test_profile_contract_refuses_noncanonical_and_duplicate_json(self) -> None:
        profile = self.load("f120-reference-v1.json")
        temporary = tempfile.TemporaryDirectory(prefix="trusted-profile-json-")
        self.addCleanup(temporary.cleanup)
        noncanonical = Path(temporary.name) / "pretty.json"
        noncanonical.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
        duplicate = Path(temporary.name) / "duplicate.json"
        duplicate.write_text(
            '{"commands":[],"commands":[],"launcher_name":"x",'
            '"profile_id":"x/v1","schema":"kilix.trusted-launcher.profile/v1",'
            '"subject_hash_manifests":[]}\n',
            encoding="utf-8",
        )
        nonfinite = Path(temporary.name) / "nonfinite.json"
        nonfinite.write_bytes(
            json.dumps(profile, sort_keys=True, separators=(",", ":"))
            .replace('"expected_exit":0', '"expected_exit":NaN', 1)
            .encode("utf-8")
            + b"\n"
        )
        for path in (noncanonical, duplicate, nonfinite):
            with self.assertRaises(BUILDER.BundleError):
                BUILDER.load_profile(path.resolve())

    def test_outer_result_writer_cannot_be_reopened_by_descendant(self) -> None:
        program = textwrap.dedent(
            """
            import importlib.util
            import os
            import sys

            specification = importlib.util.spec_from_file_location(
                "authority_bootstrap", sys.argv[1]
            )
            assert specification is not None and specification.loader is not None
            bootstrap = importlib.util.module_from_spec(specification)
            specification.loader.exec_module(bootstrap)

            result_read, result_write = os.pipe()
            status_read, status_write = os.pipe()
            bootstrap._seal_result_owner()
            owner = os.getpid()
            child = os.fork()
            if child == 0:
                os.close(result_read)
                os.close(result_write)
                os.close(status_read)
                try:
                    reopened = os.open(
                        f"/proc/{owner}/fd/{result_write}", os.O_WRONLY
                    )
                except PermissionError:
                    outcome = b"DENIED"
                except OSError as exc:
                    outcome = f"OSERROR:{exc.errno}".encode("ascii")
                else:
                    os.close(reopened)
                    outcome = b"REOPENED"
                os.write(status_write, outcome)
                os._exit(0)

            os.close(status_write)
            outcome = os.read(status_read, 64)
            waited, status = os.waitpid(child, 0)
            if waited != child or not os.WIFEXITED(status):
                raise SystemExit("descendant did not terminate normally")
            sys.stdout.buffer.write(outcome + b"\\n")
            """
        )
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-S",
                "-B",
                "-c",
                program,
                str(AUTHORITY / "bootstrap.py"),
            ],
            check=False,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8"))
        self.assertEqual(result.stdout, b"DENIED\n")

    def test_typed_refusal_code_catalogue_is_closed(self) -> None:
        refusal = BOOTSTRAP.Refusal(
            "cannot bind live interpreter identity",
            refusal_code=BOOTSTRAP.INTERPRETER_IDENTITY_UNAVAILABLE,
        )
        self.assertEqual(
            refusal.refusal_code,
            "TL-INTERPRETER-IDENTITY/live-executable-unavailable",
        )
        with self.assertRaisesRegex(ValueError, "outside the closed catalogue"):
            BOOTSTRAP.Refusal("unknown", refusal_code="TL-UNKNOWN/detail")

    def test_typed_refusal_result_is_canonical_and_run_bound(self) -> None:
        result_read, result_write = os.pipe()
        arguments = types.SimpleNamespace(
            bootstrap_sha256="a" * 64,
            case_id="ID-04:test",
            first_process_json=(
                '{"argv_sha256":"b","cwd_sha256":"c",'
                '"environment_sha256":"d","executable_device":1,'
                '"executable_inode":2,"executable_sha256":"e","pid":3,'
                '"start_time_ticks":4}'
            ),
            python_sha256="f" * 64,
            launcher_sha256="1" * 64,
            profile_id="f120-reference/v1",
            run_id="2" * 32,
            subject_manifest_sha256="3" * 64,
            result_fd=result_write,
        )
        try:
            BOOTSTRAP._write_refusal(
                arguments, BOOTSTRAP.INTERPRETER_IDENTITY_UNAVAILABLE
            )
        finally:
            os.close(result_write)
        try:
            record = os.read(result_read, BOOTSTRAP.MAX_RESULT_BYTES + 1)
        finally:
            os.close(result_read)
        expected = {
            "bootstrap_sha256": arguments.bootstrap_sha256,
            "case_id": arguments.case_id,
            "first_process_identity": json.loads(arguments.first_process_json),
            "interpreter_sha256": arguments.python_sha256,
            "launcher_sha256": arguments.launcher_sha256,
            "outcome": "refused",
            "profile_id": arguments.profile_id,
            "refusal_code": BOOTSTRAP.INTERPRETER_IDENTITY_UNAVAILABLE,
            "run_id": arguments.run_id,
            "schema": BOOTSTRAP.RESULT_SCHEMA,
            "subject_manifest_sha256": arguments.subject_manifest_sha256,
            "validator_started": False,
        }
        self.assertEqual(
            record,
            json.dumps(expected, sort_keys=True, separators=(",", ":")).encode()
            + b"\n",
        )
        self.assertLessEqual(len(record), BOOTSTRAP.MAX_RESULT_BYTES)


if __name__ == "__main__":
    unittest.main()
