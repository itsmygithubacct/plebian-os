#!/usr/bin/env python3
"""Run the F107-B packet's checks and print every count with its denominator.

Usage, from the packet root:

    uv run --locked --offline python run-checks.py

The runner verifies three things before it will report a pass, and none of the
three is waivable:

1. **Track D's candidate**, because a suite green against different bytes than
   it claims is worse than a red one.
2. **The packet's own control files** — tests, fixtures, schemas, the inventory,
   this runner — against ``SHA256SUMS``.
3. **The test inventory**, so the discovered module set and per-module counts
   must equal a committed expectation.

Control 3 exists because of finding **F107B-01**: this runner used to print
``tests discovered: N/N``, comparing a number to itself. Deleting a test module
made ``N`` smaller and the run stayed green — the loudest possible failure
produced a clean pass. A count is not a check unless it has an independent
denominator.

**Why ``src/f107b_setup/`` is excluded from control 2.** The mutation campaign
rewrites those files on purpose, so a content check over them would either
break the campaign or have to be waivable — and a waivable control is the
defect this packet was just cited for. The division of labour instead:

* ``SHA256SUMS`` and ``TEST-INVENTORY.tsv`` guard **the controls**;
* the controls (the tests) guard **the source**;
* ``mutation-check.py`` proves the tests really do guard the source;
* ``control-check.py`` proves the controls really do guard themselves.

Nothing here is self-authenticating, and it does not pretend to be: an editor
who rewrites a test *and* regenerates ``SHA256SUMS`` defeats control 2. What
they cannot do is change the published commit, which covers every byte
including the manifest. The git SHA is the anchor; these controls catch
everything short of rewriting history.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

#: Track D's candidate is research-side material and lives in no repository,
#: so its location is supplied rather than assumed.
CANDIDATE_ROOT = Path(
    os.environ.get("F107B_CANDIDATE_ROOT", str(ROOT.parent / "track-d-p1-candidate"))
).expanduser()
CANDIDATE_MANIFEST = CANDIDATE_ROOT / "CANDIDATE-SHA256SUMS"
EXPECTED_MANIFEST_SHA256 = "2341c763c4ee7958387335f01a5274155311239e3c82572b1855521dc85d37f4"

SELF_MANIFEST = ROOT / "SHA256SUMS"
TEST_INVENTORY = ROOT / "TEST-INVENTORY.tsv"

#: The one subtree the mutation campaign rewrites. Excluded from the content
#: check, and only from the content check — its *tests* are still inventoried.
MUTABLE_PREFIX = "./src/f107b_setup/"

#: Absent candidate, present-but-wrong candidate, and verified candidate are
#: three different answers and get three different exit statuses.
ABSENT = "absent"
MISMATCH = "mismatch"
VERIFIED = "verified"

#: Exit statuses. A control failure is deliberately distinct from a test
#: failure, so a campaign can assert which control fired rather than settling
#: for "something went wrong".
EXIT_PASS = 0
EXIT_TEST_FAILURE = 1
EXIT_CANDIDATE_MISMATCH = 2
EXIT_PARTIAL = 3
EXIT_CONTROL_FAILURE = 4


def parse_manifest(path: Path) -> dict[str, str]:
    """Parse a ``sha256sum`` manifest into ``{path: digest}``."""

    entries: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, _, name = line.partition("  ")
        if not name:
            raise ValueError(f"malformed manifest line: {line!r}")
        if name in entries:
            raise ValueError(f"duplicate manifest entry: {name}")
        entries[name] = digest
    return entries


def check_candidate() -> tuple[str, list[str]]:
    lines: list[str] = []
    if not CANDIDATE_MANIFEST.is_file():
        return ABSENT, [
            f"Track D R2 candidate not found at {CANDIDATE_ROOT}",
            "set F107B_CANDIDATE_ROOT to the candidate root; every check that "
            "consumes it will skip until you do",
        ]

    digest = hashlib.sha256(CANDIDATE_MANIFEST.read_bytes()).hexdigest()
    manifest_ok = digest == EXPECTED_MANIFEST_SHA256
    lines.append(
        f"candidate manifest digest: {digest} "
        f"({'matches' if manifest_ok else 'DOES NOT MATCH'} the R2 handoff)"
    )

    # F107B-03: the denominator is the number of files the manifest declares,
    # read from the manifest itself. It used to be the number of lines
    # sha256sum printed, which counts warnings as files and can only ever
    # equal the numerator.
    try:
        declared = len(parse_manifest(CANDIDATE_MANIFEST))
    except (OSError, UnicodeError, ValueError) as error:
        return MISMATCH, lines + [f"candidate manifest is unreadable: {error}"]

    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["sha256sum", "-c", "CANDIDATE-SHA256SUMS"],
        cwd=str(CANDIDATE_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=False,
        timeout=120,
    )
    output = completed.stdout.decode("utf-8", "replace").splitlines()
    ok_count = sum(1 for line in output if line.endswith(": OK"))
    lines.append(f"candidate files verified: {ok_count}/{declared} declared")
    verified = manifest_ok and completed.returncode == 0 and ok_count == declared
    return (VERIFIED if verified else MISMATCH), lines


def check_controls() -> tuple[bool, list[str]]:
    """Verify the packet's own control files. Never waivable.

    This is the F107B-01 fix's first half: the runner applies to its own bytes
    the discipline it already applied to Track D's.
    """

    lines: list[str] = []
    if not SELF_MANIFEST.is_file():
        return False, [f"the packet's own SHA256SUMS is missing at {SELF_MANIFEST}"]
    try:
        entries = parse_manifest(SELF_MANIFEST)
    except (OSError, UnicodeError, ValueError) as error:
        return False, [f"the packet's own SHA256SUMS is unreadable: {error}"]

    guarded = {
        name: digest
        for name, digest in entries.items()
        if not name.startswith(MUTABLE_PREFIX)
    }
    mutable = len(entries) - len(guarded)

    verified = 0
    problems: list[str] = []
    for name, expected in sorted(guarded.items()):
        path = ROOT / name
        if not path.is_file():
            problems.append(f"control file missing: {name}")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            problems.append(f"control file altered: {name}")
            continue
        verified += 1

    # A file present on disk but absent from the manifest is also a finding:
    # an unlisted test module is exactly how an inventory gets quietly padded.
    on_disk = {
        f"./{item.relative_to(ROOT).as_posix()}"
        for item in ROOT.rglob("*")
        if item.is_file()
        and item.name != "SHA256SUMS"
        and ".venv" not in item.parts
        and "__pycache__" not in item.parts
    }
    unlisted = sorted(on_disk - set(entries))
    for name in unlisted:
        problems.append(f"file present but unlisted in the manifest: {name}")

    lines.append(
        f"control files verified: {verified}/{len(guarded)} guarded "
        f"({mutable} mutable source file(s) excluded by design, "
        f"{len(unlisted)} unlisted)"
    )
    lines.extend(f"  {problem}" for problem in problems)
    return not problems, lines


def parse_inventory(path: Path) -> dict[str, int]:
    expected: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        module, _, count = stripped.partition("\t")
        if not count:
            raise ValueError(f"malformed inventory line: {line!r}")
        if module in expected:
            raise ValueError(f"duplicate inventory module: {module}")
        expected[module] = int(count)
    return expected


def discovered_inventory(suite: unittest.TestSuite) -> dict[str, int]:
    counts: dict[str, int] = {}

    def walk(item: object) -> None:
        if isinstance(item, unittest.TestSuite):
            for child in item:
                walk(child)
            return
        module = type(item).__module__
        # A module that fails to import becomes a synthetic _FailedTest owned
        # by unittest.loader. Attribute it to the module it failed to be, so
        # the mismatch names the real file rather than the loader.
        if module.startswith("unittest"):
            module = getattr(item, "_testMethodName", "unknown-module")
        counts[module] = counts.get(module, 0) + 1

    walk(suite)
    return counts


def check_inventory(suite: unittest.TestSuite) -> tuple[bool, list[str]]:
    """Compare discovery against a committed expectation.

    This is the F107B-01 fix's second half. ``tests discovered: N/N`` compared
    a number to itself; this compares it to a number an editor has to change on
    purpose, in a file the content check guards.
    """

    if not TEST_INVENTORY.is_file():
        return False, [f"the test inventory is missing at {TEST_INVENTORY}"]
    try:
        expected = parse_inventory(TEST_INVENTORY)
    except (OSError, UnicodeError, ValueError) as error:
        return False, [f"the test inventory is unreadable: {error}"]

    actual = discovered_inventory(suite)
    problems: list[str] = []

    for module in sorted(set(expected) - set(actual)):
        problems.append(f"test module MISSING: {module} (expected {expected[module]} tests)")
    for module in sorted(set(actual) - set(expected)):
        problems.append(f"test module not in the inventory: {module} ({actual[module]} tests)")
    for module in sorted(set(expected) & set(actual)):
        if expected[module] != actual[module]:
            problems.append(
                f"test count changed in {module}: found {actual[module]}, "
                f"inventory expects {expected[module]}"
            )

    expected_total = sum(expected.values())
    actual_total = sum(actual.values())
    lines = [
        f"test modules: {len(actual)}/{len(expected)} expected; "
        f"tests discovered: {actual_total}/{expected_total} expected"
    ]
    lines.extend(f"  {problem}" for problem in problems)
    return not problems, lines


def main() -> int:
    print("F107-B fixture-backed wizard — checks")
    print("=" * 72)

    controls_ok, control_lines = check_controls()
    for line in control_lines:
        print(f"  {line}")

    candidate_state, candidate_lines = check_candidate()
    for line in candidate_lines:
        print(f"  {line}")

    loader = unittest.TestLoader()
    suite = loader.discover(str(ROOT / "tests"), pattern="test_*.py")
    inventory_ok, inventory_lines = check_inventory(suite)
    for line in inventory_lines:
        print(f"  {line}")

    if not controls_ok or not inventory_ok:
        print(
            "REFUSED: the packet's own controls do not verify. A suite whose "
            "test inventory cannot be trusted cannot report a pass."
        )
        return EXIT_CONTROL_FAILURE
    if candidate_state == MISMATCH:
        print("REFUSED: the Track D candidate this packet was built against does not verify.")
        return EXIT_CANDIDATE_MISMATCH

    expected_total = sum(parse_inventory(TEST_INVENTORY).values())
    print("-" * 72)

    runner = unittest.TextTestRunner(verbosity=1, stream=sys.stdout)
    result = runner.run(suite)

    run = result.testsRun
    failed = len(result.failures)
    errored = len(result.errors)
    skipped = len(result.skipped)
    passed = run - failed - errored - skipped
    print("-" * 72)
    print(
        f"RESULT: {passed}/{run} passed, {failed}/{run} failed, "
        f"{errored}/{run} errored, {skipped}/{run} skipped "
        f"(of {expected_total} the inventory expects)"
    )
    print(
        "This is builder evidence against Track D's reviewable R2 candidate. "
        "It is not hardware, backend, model or performance qualification, and "
        "it is not an acceptance."
    )

    if candidate_state == ABSENT:
        print(
            f"PARTIAL: {skipped}/{run} checks did not run because Track D's R2 "
            "candidate was not supplied. This run is NOT a full pass."
        )
        return EXIT_PARTIAL
    if not result.wasSuccessful():
        return EXIT_TEST_FAILURE
    if skipped:
        print(f"PARTIAL: {skipped}/{run} checks were skipped; this is not a full pass.")
        return EXIT_PARTIAL
    return EXIT_PASS


if __name__ == "__main__":
    raise SystemExit(main())
