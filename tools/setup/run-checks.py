#!/usr/bin/env python3
"""Run the F107-B packet's checks and print every count with its denominator.

Usage, from the packet root:

    uv run --project ../f120-contracts --locked --offline python run-checks.py

The runner verifies the Track D candidate it was built against before it runs
anything, because a suite that is green against different bytes than it claims
is worse than a red one.
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

#: Absent candidate, present-but-wrong candidate, and verified candidate are
#: three different answers and get three different exit statuses.
ABSENT = "absent"
MISMATCH = "mismatch"
VERIFIED = "verified"


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
    total = len(output)
    lines.append(f"candidate files verified: {ok_count}/{total}")
    verified = manifest_ok and completed.returncode == 0 and ok_count == total
    return (VERIFIED if verified else MISMATCH), lines


def main() -> int:
    print("F107-B fixture-backed wizard — checks")
    print("=" * 72)
    candidate_state, candidate_lines = check_candidate()
    for line in candidate_lines:
        print(f"  {line}")
    if candidate_state == MISMATCH:
        print("REFUSED: the Track D candidate this packet was built against does not verify.")
        return 2

    loader = unittest.TestLoader()
    suite = loader.discover(str(ROOT / "tests"), pattern="test_*.py")
    total = suite.countTestCases()
    print(f"  tests discovered: {total}/{total}")
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
        f"(of {total} discovered)"
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
        return 3
    if not result.wasSuccessful():
        return 1
    if skipped:
        print(f"PARTIAL: {skipped}/{run} checks were skipped; this is not a full pass.")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
