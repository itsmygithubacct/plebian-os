from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
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


if __name__ == "__main__":
    unittest.main()
