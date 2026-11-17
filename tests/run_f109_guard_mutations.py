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
        '                || die "release tag $release_tag object is $tag_object, not trusted object $trusted"',
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
    Mutation(
        "spent newest record required for the already-rolled-back answer",
        '    if [ -f "$newest/restored" ] && [ ! -L "$newest/restored" ] \\\n            && refuse_unrelated_recovery_record "$newest" 1 "$trusted_tag"; then',
        '    if refuse_unrelated_recovery_record "$newest" 1 "$trusted_tag"; then # mutation',
        (CASE + "test_an_unspent_newest_record_is_restored_even_when_the_closure_looks_saved",),
    ),
    Mutation(
        "own tag required for the already-rolled-back answer",
        '            && refuse_unrelated_recovery_record "$newest" 1 "$trusted_tag"; then',
        '            && true; then # mutation',
        (CASE + "test_a_repeated_hop_rollback_finds_its_own_spent_record_and_succeeds",),
    ),
    Mutation(
        "no walk back to an older record when the closure changed",
        '        exit 16\n    fi\nfi\n[ "${#candidates[@]}" -gt 0 ] || exit 4',
        '        : # mutation\n    fi\nfi\n[ "${#candidates[@]}" -gt 0 ] || exit 4',
        (CASE + "test_a_hop_rollback_never_walks_back_to_an_older_record",),
    ),
    Mutation(
        "ordering of the newest records",
        '    [ "$newest_status" = 0 ] || exit "$newest_status"',
        '    : # mutation',
        (CASE + "test_a_hop_rollback_never_walks_back_to_an_older_record",),
    ),
    Mutation(
        "hop marker: tag object must match",
        '    [ "$(sed -n 3p -- "$active")" = "$tag" ] || return 0',
        '    : # mutation',
        (CASE + "test_the_hop_marker_is_left_alone_unless_it_is_provably_this_hops",),
    ),
    Mutation(
        "hop marker: phase must be selecting or selected",
        '    case " $phases " in *" $(cat -- "$phase") "*) ;; *) return 0 ;; esac',
        '    : # mutation',
        (CASE + "test_the_hop_marker_is_left_alone_unless_it_is_provably_this_hops",),
    ),
    Mutation(
        "hop marker: image mode only",
        '    [ "$SELECTOR_MODE" = image ] || return 0',
        '    : # mutation',
        (CASE + "test_the_hop_marker_is_left_alone_unless_it_is_provably_this_hops",),
    ),
    Mutation(
        "hop marker: a retained failed rollback keeps it",
        '    ! retained_failed_rollback_exists || return 0',
        '    : # mutation',
        (CASE + "test_a_finished_rollback_settles_the_hop_marker_it_belongs_to",),
    ),
    Mutation(
        "hop marker: release-hop must not be a symlink",
        '    [ -d "$dir" ] && [ ! -L "$dir" ] && [ "$(stat -c \'%u\' -- "$dir" 2>/dev/null)" = "$EUID" ] || return 0',
        '    [ -d "$dir" ] && [ "$(stat -c \'%u\' -- "$dir" 2>/dev/null)" = "$EUID" ] || return 0',
        (CASE + "test_the_hop_marker_is_left_alone_unless_it_is_provably_this_hops",),
    ),
    Mutation(
        "hop marker: four or five lines",
        '    { [ "$lines" = 4 ] || [ "$lines" = 5 ]; } || return 0',
        '    : # mutation',
        (CASE + "test_the_hop_marker_is_left_alone_unless_it_is_provably_this_hops",),
    ),
    Mutation(
        "hop marker: release on line 1",
        '    [[ "$(sed -n 1p -- "$active")" =~ ^[0-9]+\\.[0-9]+\\.[0-9]+(\\.[1-9][0-9]*)?$ ]] || return 0',
        '    : # mutation',
        (CASE + "test_the_hop_marker_is_left_alone_unless_it_is_provably_this_hops",),
    ),
    Mutation(
        "hop marker: selector hash on line 4",
        '    [[ "$(sed -n 4p -- "$active")" =~ ^[0-9a-f]{64}$ ]] || return 0',
        '    : # mutation',
        (CASE + "test_the_hop_marker_is_left_alone_unless_it_is_provably_this_hops",),
    ),
    Mutation(
        "hop marker: tag on line 5",
        '        [[ "$(sed -n 5p -- "$active")" =~ ^v[0-9]+\\.[0-9]+\\.[0-9]+(\\.[1-9][0-9]*)?(-rc[1-9][0-9]*)?$ ]] \\\n            || return 0',
        '        : # mutation',
        (CASE + "test_the_hop_marker_is_left_alone_unless_it_is_provably_this_hops",),
    ),
    Mutation(
        "hop marker: only a request bound to the hop's own record settles",
        '        [ "$REQUIRE_OWN_RECORD" != 1 ] || settle_interrupted_hop_marker',
        '        settle_interrupted_hop_marker # mutation',
        (CASE + "test_a_rollback_not_bound_to_the_hops_own_record_leaves_the_marker",),
    ),
    Mutation(
        "hop marker: a selection that replaced nothing settles only selecting",
        '                settle_interrupted_hop_marker selecting\n                exit 0\n                ;;',
        '                settle_interrupted_hop_marker # mutation\n                exit 0\n                ;;',
        (CASE + "test_a_selection_that_replaced_nothing_settles_only_a_selecting_marker",),
    ),
    Mutation(
        "wait for a running update: status 13 settles nothing",
        '            exit 13',
        '            break # mutation',
        (CASE + "test_a_rollback_that_waits_out_a_running_update_does_not_settle_the_marker",),
    ),
    Mutation(
        "operator install-policy validation",
        '        require_manifest_format "$key" \'^[01]$\' \\\n            "0 or 1 (an image default; an installed operator choice is preserved)"',
        "        : # mutation: invalid operator-policy image default accepted",
        (CASE + "test_image_policy_defaults_are_validated_but_never_selected",),
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
