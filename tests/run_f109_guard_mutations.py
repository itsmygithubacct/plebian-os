#!/usr/bin/env python3
"""Kill the F109 selector's release-hop acceptance-guard mutants.

This is intentionally outside unittest discovery: it copies the repository,
deletes one load-bearing check at a time, and requires the corresponding
focused control to fail. A zero exit means every declared mutant was killed.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SELECTOR = Path("provision/plebian-os-select-closure.sh")


@dataclass(frozen=True)
class Mutation:
    name: str
    old: str
    new: str
    tests: tuple[str, ...]
    occurrences: int = 1


CASE = "tests.test_closure_selection.ClosureSelectionTests."
MUTATIONS = (
    Mutation(
        "placeholder refusal",
        '            || closure_reject "$key is still REPLACE_ME — the release was never finished"',
        "            || : # mutation: REPLACE_ME accepted by this guard",
        (CASE + "test_placeholder_pin_is_refused_by_name",),
    ),
    Mutation(
        "branch-pin refusal",
        '            || closure_reject "$key must be empty in a release closure — a release pins exact commits, not branches (got \'${MANIFEST[$key]}\')"',
        "            || : # mutation: branch accepted",
        (CASE + "test_branch_pin_in_a_release_closure_is_refused_by_name",),
    ),
    Mutation(
        "half-pinned optional closure refusal",
        '            || closure_reject "PLEBIAN_OS_INSTALL_VOICE_MODEL=1 needs pinned values for: ${missing[*]}"',
        "            || : # mutation: partial voice closure accepted",
        (CASE + "test_half_pinned_optional_closure_is_refused_by_name",),
    ),
    Mutation(
        "release-version agreement",
        '        || closure_reject "PLEBIAN_OS_VERSION is \'${MANIFEST[PLEBIAN_OS_VERSION]:-unset}\', not $TARGET"',
        "        || : # mutation: disagreeing release version accepted",
        (CASE + "test_manifest_version_disagreeing_with_the_release_is_refused",),
    ),
    Mutation(
        "advertised-ref reachability",
        '        || closure_reject "$label target $ref_key=$target is not reachable from any advertised head or tag"',
        "        || : # mutation: unpublished object accepted",
        (CASE + "test_component_commit_must_be_reachable_from_an_advertised_ref",),
    ),
    Mutation(
        "sideways component direction",
        '        COMPONENT_DIRECTION["$ref_key"]=diverged',
        '        COMPONENT_DIRECTION["$ref_key"]=forward # mutation',
        (CASE + "test_component_sideways_move_is_announced_as_diverged",),
        occurrences=2,
    ),
    Mutation(
        "offline tag-object identity",
        '            || die "release tag v$TARGET object is $tag_object, not trusted object $trusted"',
        "            || : # mutation: wrong tag object accepted",
        (CASE + "test_offline_tag_requires_an_exact_trusted_tag_object",),
    ),
    Mutation(
        "ambiguous split-key refusal",
        '                die "$src line $lineno sets release-controlled key $key in an ambiguous form; use a plain KEY=value assignment or resolve the edit before migration"',
        "                : # mutation: ambiguous release-key edit accepted",
        (CASE + "test_split_migration_refuses_an_ambiguous_release_pin_edit",),
    ),
    Mutation(
        "split apply and rollback compensation",
        "trap cleanup EXIT",
        ": # mutation: transactional compensation disabled",
        (
            CASE + "test_0_2_1_split_transaction_restores_every_write_boundary",
            CASE + "test_0_2_1_split_rollback_retains_selected_pair_at_every_boundary",
        ),
        occurrences=4,
    ),
    Mutation(
        "target-selector byte identity",
        '    cmp -s -- "$self" "$STAGE/plebian-os-select-closure" \\\n        || closure_reject "the running selector does not match provision/plebian-os-select-closure.sh in target commit $OS_COMMIT"',
        "    : # mutation: running selector identity not checked",
        (CASE + "test_selector_must_match_the_exact_target_commit",),
    ),
)


def run_tests(root: Path, tests: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["TMPDIR"] = "/home/pleb/scratch-workers"
    return subprocess.run(
        [sys.executable, "-m", "unittest", *tests],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def main() -> int:
    unique_tests = tuple(dict.fromkeys(test for item in MUTATIONS for test in item.tests))
    baseline = run_tests(ROOT, unique_tests)
    if baseline.returncode != 0:
        sys.stderr.write("baseline controls failed; mutation result is invalid\n")
        sys.stderr.write(baseline.stdout + baseline.stderr)
        return 2

    killed = 0
    scratch = os.environ.get("TMPDIR", "/home/pleb/scratch-workers")
    for index, mutation in enumerate(MUTATIONS, 1):
        with tempfile.TemporaryDirectory(dir=scratch) as td:
            mutant = Path(td) / "plebian-os"
            shutil.copytree(
                ROOT,
                mutant,
                ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
            )
            path = mutant / SELECTOR
            source = path.read_text()
            observed = source.count(mutation.old)
            if observed != mutation.occurrences:
                print(
                    f"[INVALID {index}/{len(MUTATIONS)}] {mutation.name}: "
                    f"expected {mutation.occurrences} mutation sites, found {observed}",
                    file=sys.stderr,
                )
                return 2
            path.write_text(source.replace(mutation.old, mutation.new))
            result = run_tests(mutant, mutation.tests)
            if result.returncode == 0:
                print(
                    f"[SURVIVED {index}/{len(MUTATIONS)}] {mutation.name}",
                    file=sys.stderr,
                )
                return 1
            killed += 1
            print(f"[KILLED {index}/{len(MUTATIONS)}] {mutation.name}")
    print(f"F109 selector mutations killed: {killed}/{len(MUTATIONS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
