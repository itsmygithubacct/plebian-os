from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


AUTHORITY = Path(__file__).resolve().parents[1] / "authority"
SPECIFICATION = importlib.util.spec_from_file_location(
    "authority_build_bundle", AUTHORITY / "build_bundle.py"
)
assert SPECIFICATION is not None and SPECIFICATION.loader is not None
BUILDER = importlib.util.module_from_spec(SPECIFICATION)
SPECIFICATION.loader.exec_module(BUILDER)


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

    def test_td_p1_encodes_three_children_and_nine_exact_replays(self) -> None:
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
        self.assertEqual(len(replay_cases), 9)
        self.assertEqual(
            [case["argv"] for case in replay_cases],
            [
                ["show"],
                ["inventory", "--json"],
                ["gpu", "--json"],
                ["recommend", "tts", "--json"],
                ["plan", "local-ai-balanced", "--json"],
                [
                    "install",
                    {
                        "path": (
                            "contracts/p1-candidate/fixtures/plans/"
                            "blocked-no-f100-c0.json"
                        ),
                        "root": "subject",
                    },
                    "--expected-plan-sha256",
                    "bdf8e8d9afb0fac85b252a5d63f78507bc03b2ef9ed25cac9926ef7641d7a317",
                    "--json",
                ],
                ["install-status", "TRANSACTION_ID", "--json"],
                ["cancel", "TRANSACTION_ID", "--json"],
                ["snapshot", "--json"],
            ],
        )
        self.assertEqual(
            [case["stdout"]["path"] for case in replay_cases],
            [
                "contracts/p1-candidate/fixtures/responses/hardware-show.txt",
                "contracts/p1-candidate/fixtures/responses/hardware-inventory.json",
                "contracts/p1-candidate/fixtures/responses/hardware-gpu.json",
                "contracts/p1-candidate/fixtures/responses/sizer-recommend-tts.json",
                "contracts/p1-candidate/fixtures/responses/sizer-plan.json",
                "contracts/p1-candidate/fixtures/responses/sizer-install-blocked.json",
                (
                    "contracts/p1-candidate/fixtures/responses/"
                    "sizer-install-status-blocked.json"
                ),
                (
                    "contracts/p1-candidate/fixtures/responses/"
                    "sizer-install-cancel-blocked.json"
                ),
                "contracts/p1-candidate/fixtures/responses/sizer-snapshot.json",
            ],
        )
        validator_argv = children[0]["cases"][0]["argv"]
        self.assertEqual(
            validator_argv[
                validator_argv.index("--expected-candidate-manifest-sha256") + 1
            ],
            "a21897870cdbc980dff0f611033848f489ac8cc3dec568560a275640188eb6ab",
        )
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


if __name__ == "__main__":
    unittest.main()
