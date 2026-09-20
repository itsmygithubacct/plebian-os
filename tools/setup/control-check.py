#!/usr/bin/env python3
"""Anti-vacuity for the *controls*, not the source.

``mutation-check.py`` proves the tests catch a broken behaviour. This proves the
runner catches a broken **suite** — the thing finding **F107B-01** said it could
not do:

> "the runner protects Track D's bytes but not its own; a deleted test module is
> a green full pass."

Each control below breaks the suite's integrity in a specific way and requires
``run-checks.py`` to exit with the **specific** status that names the control
that should have fired. Requiring "nonzero" would not be enough: a run that went
red for an unrelated reason would look like proof and would not be.

Four of the eleven controls regenerate ``SHA256SUMS`` after tampering, so the
content check passes and **only the inventory can catch them**. That is the attack worth
testing — an editor who deletes a test and tidies up after themselves — and it
is the one the old runner lost to.

    uv run --locked --offline python control-check.py
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent

EXIT_PASS = 0
EXIT_TEST_FAILURE = 1
EXIT_CANDIDATE_MISMATCH = 2
EXIT_PARTIAL = 3
EXIT_CONTROL_FAILURE = 4

STATUS_NAMES = {
    EXIT_PASS: "pass",
    EXIT_TEST_FAILURE: "test failure",
    EXIT_CANDIDATE_MISMATCH: "candidate mismatch",
    EXIT_PARTIAL: "partial",
    EXIT_CONTROL_FAILURE: "control failure",
}


def regenerate_manifest(root: Path) -> None:
    """Rewrite ``SHA256SUMS`` over the tree, the way a tidy editor would."""

    entries = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name == "SHA256SUMS" or ".venv" in path.parts or "__pycache__" in path.parts:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        entries.append(f"{digest}  ./{path.relative_to(root).as_posix()}")
    (root / "SHA256SUMS").write_text("\n".join(entries) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class Control:
    label: str
    #: Applied to a throwaway copy of the packet.
    apply: Callable[[Path], None]
    expected_exit: int
    claim: str


def _delete_module(root: Path) -> None:
    (root / "tests" / "test_syscenter.py").unlink()


def _delete_module_and_tidy(root: Path) -> None:
    (root / "tests" / "test_syscenter.py").unlink()
    regenerate_manifest(root)


def _empty_module_and_tidy(root: Path) -> None:
    (root / "tests" / "test_syscenter.py").write_text(
        '"""Emptied of its tests."""\n', encoding="utf-8"
    )
    regenerate_manifest(root)


def _rename_module_and_tidy(root: Path) -> None:
    tests = root / "tests"
    (tests / "test_syscenter.py").rename(tests / "test_syscenter_renamed.py")
    regenerate_manifest(root)


def _add_unlisted_module(root: Path) -> None:
    (root / "tests" / "test_smuggled.py").write_text(
        "import unittest\n\n\nclass T(unittest.TestCase):\n"
        "    def test_always_passes(self):\n        self.assertTrue(True)\n",
        encoding="utf-8",
    )


def _tamper_test_content(root: Path) -> None:
    path = root / "tests" / "test_gates.py"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "self.assertEqual(len(LEDGER), 4)", "self.assertEqual(len(LEDGER), 4)  # tampered"
        ),
        encoding="utf-8",
    )


def _tamper_fixture(root: Path) -> None:
    path = root / "fixtures" / "catalog" / "generic-vendor-client.json"
    path.write_text(
        path.read_text(encoding="utf-8").replace("Example vendor client", "Tampered label"),
        encoding="utf-8",
    )


def _tamper_inventory(root: Path) -> None:
    path = root / "TEST-INVENTORY.tsv"
    path.write_text(
        path.read_text(encoding="utf-8").replace("test_syscenter\t23", "test_syscenter\t1"),
        encoding="utf-8",
    )


def _tamper_inventory_and_tidy(root: Path) -> None:
    _tamper_inventory(root)
    regenerate_manifest(root)


def _delete_schema(root: Path) -> None:
    (root / "schemas" / "plebian.setup-v1.schema.json").unlink()


def _mutate_source(root: Path) -> None:
    """Break a behaviour in the one subtree the content check excludes."""

    path = root / "src" / "f107b_setup" / "plan.py"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "    if value is None:\n        return UNKNOWN",
            '    if value is None:\n        return "0 B"',
        ),
        encoding="utf-8",
    )


CONTROLS: tuple[Control, ...] = (
    Control(
        label="delete-a-test-module",
        apply=_delete_module,
        expected_exit=EXIT_CONTROL_FAILURE,
        claim="a deleted test module is caught by the content check",
    ),
    Control(
        label="delete-a-test-module-and-tidy-the-manifest",
        apply=_delete_module_and_tidy,
        expected_exit=EXIT_CONTROL_FAILURE,
        claim="a deleted module is caught by the INVENTORY even when the manifest is regenerated",
    ),
    Control(
        label="empty-a-module-and-tidy-the-manifest",
        apply=_empty_module_and_tidy,
        expected_exit=EXIT_CONTROL_FAILURE,
        claim="a module emptied of its tests is caught by the inventory count",
    ),
    Control(
        label="rename-a-module-and-tidy-the-manifest",
        apply=_rename_module_and_tidy,
        expected_exit=EXIT_CONTROL_FAILURE,
        claim="a renamed module is caught as one missing and one unexpected",
    ),
    Control(
        label="add-an-unlisted-module",
        apply=_add_unlisted_module,
        expected_exit=EXIT_CONTROL_FAILURE,
        claim="a test module nobody declared cannot pad the count",
    ),
    Control(
        label="tamper-a-test-file",
        apply=_tamper_test_content,
        expected_exit=EXIT_CONTROL_FAILURE,
        claim="an edited test file is caught by the content check",
    ),
    Control(
        label="tamper-a-fixture",
        apply=_tamper_fixture,
        expected_exit=EXIT_CONTROL_FAILURE,
        claim="an edited fixture is caught by the content check",
    ),
    Control(
        label="tamper-the-inventory",
        apply=_tamper_inventory,
        expected_exit=EXIT_CONTROL_FAILURE,
        claim="an edited inventory is caught by the content check",
    ),
    Control(
        label="tamper-the-inventory-and-tidy-the-manifest",
        apply=_tamper_inventory_and_tidy,
        expected_exit=EXIT_CONTROL_FAILURE,
        claim="a tidied-up inventory edit is still caught, by the count it now contradicts",
    ),
    Control(
        label="delete-a-schema",
        apply=_delete_schema,
        expected_exit=EXIT_CONTROL_FAILURE,
        claim="a deleted schema is caught before any test consumes it",
    ),
    # The inverse claim, and it matters as much as the others. The content
    # check deliberately excludes src/f107b_setup/ so the mutation campaign can
    # rewrite it. If that exclusion did not hold, every mutation would trip the
    # control check and be scored "caught" without a single test having noticed
    # anything — a vacuous campaign wearing a green badge. This requires a
    # source mutation to surface as a TEST failure, exit 1, not a control one.
    Control(
        label="mutate-source-must-be-caught-by-a-test-not-a-control",
        apply=_mutate_source,
        expected_exit=EXIT_TEST_FAILURE,
        claim="a broken behaviour is caught by the tests, proving the mutation campaign is not vacuous",
    ),
)


def run_suite(root: Path) -> tuple[int, str]:
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(root / "run-checks.py")],
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=False,
        timeout=600,
    )
    return completed.returncode, completed.stdout.decode("utf-8", "replace")


def copy_packet(destination: Path) -> Path:
    root = destination / "setup"
    shutil.copytree(
        ROOT,
        root,
        ignore=shutil.ignore_patterns(".venv", "__pycache__", "*.pyc"),
    )
    return root


def main() -> int:
    print("F107-B control-integrity campaign (finding F107B-01)")
    print("=" * 72)

    with tempfile.TemporaryDirectory(prefix="f107b-control-") as tmp:
        baseline_root = copy_packet(Path(tmp) / "baseline")
        status, output = run_suite(baseline_root)
        summary = next(
            (line for line in output.splitlines() if line.startswith("RESULT:")), "?"
        )
        print(f"  baseline: exit {status} ({STATUS_NAMES.get(status, 'unknown')}) — {summary}")
        if status != EXIT_PASS:
            print(
                "REFUSED: an untampered copy does not pass, so nothing below "
                "would mean anything."
            )
            return 2

    caught = 0
    escaped: list[str] = []
    for index, control in enumerate(CONTROLS, start=1):
        with tempfile.TemporaryDirectory(prefix="f107b-control-") as tmp:
            root = copy_packet(Path(tmp) / "case")
            control.apply(root)
            status, _ = run_suite(root)

        want = control.expected_exit
        if status == want:
            print(
                f"  {index:2d}/{len(CONTROLS)} {control.label}: caught "
                f"(exit {status}, {STATUS_NAMES[status]}) — {control.claim}"
            )
            caught += 1
        else:
            print(
                f"  {index:2d}/{len(CONTROLS)} {control.label}: ESCAPED "
                f"(exit {status}, wanted {want}) — {control.claim}"
            )
            escaped.append(control.label)

    print("-" * 72)
    print(
        f"RESULT: {caught}/{len(CONTROLS)} control breaches caught, "
        f"{len(escaped)}/{len(CONTROLS)} escaped"
    )
    for label in escaped:
        print(f"  escaped: {label}")
    print(
        "Every case ran against a throwaway copy; this packet was not modified. "
        "Each 'caught' required the exact exit status naming the control that "
        "should fire, not merely a nonzero one."
    )
    return 0 if not escaped else 1


if __name__ == "__main__":
    raise SystemExit(main())
