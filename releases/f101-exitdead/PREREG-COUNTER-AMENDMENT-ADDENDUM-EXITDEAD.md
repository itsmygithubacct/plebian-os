# F101 counter amendment — addendum EXITDEAD (owned-tree stat reads of exiting tasks)

Status: DRAFT for independent review (worker232, not an author of this addendum or its code). This addendum authorises nothing.
It does not edit `PREREG-COUNTER-AMENDMENT-DRAFT.md` (`815609f7ba01fc3e9ac5fbaf763e6c35e2d4d8976959fcc8b3af9dceec6558c5`),
`PREREG-COUNTER-AMENDMENT-ADDENDUM-FIX4.md` (`32a69dbee9eda373d76429da27ab313fa8dc0f985a89ebb6edbd473f203c52e7`) or
`PREREG-COUNTER-AMENDMENT-ADDENDUM-TAGSET.md` (`6f24b7d18638ca1f51d57107af499db666760d92cba019edbd9d3bda7b850faf`); all three stay
unchanged and are read together with this one. Diagnosis: `audio-d698-b4c-20261028/B4BP-DIAGNOSIS.txt` (7d0a0246). Run record:
`audio-d698-b4c-20261028/b4b-prime/ROOT-B4BP-RUN-RESULT.json` (1fd20cde).

## Why

The one registered attempt of the TAGSET tuple (packet `7b73ebe`, receipt `195e3065`; B4b′ run `4d8c290b74804c67`) was refused by
the staged grader: 20 of 21 rules passed (`C10_29_tagged_mutants_and_nulls` among them), and `execution_and_returncodes` failed
"timeout/incomplete owned cleanup: C7-readiness-r4-1". It stays FAILED, the attempt is consumed, and this addendum does not regrade
it into a pass.

Cause (B4BP-DIAGNOSIS section 1). The record's only cleanup error is "known PID 1345/38803: ValueError: invalid process stat for 1345".
Teardown itself was complete: `cleanup_attempt_completed` true, no survivors in the final observation, exit 0, no signal sent.
`candidate/owned_tree.py` `read_stat` read a FULL stat line of a task in EXIT_DEAD (`X`) after its signal struct was released. The
kernel prints such a row with ppid 0 and pgid/sid -1 (`<pid> (python3) X 0 -1 -1 0 -1 …`) for the microseconds before
`release_task` unhashes the PID. `validate()` rejects pgid -1, `read_stat` raises "invalid process stat", `OwnedTree.observe` latches
the error permanently for the known identity, and `ManagedProcess.status` then refuses `owned_tree_torn_down`. The 20 ms poll of
`scripts/owned_command.py` hit that window once in 3,298 guest identities (B4b and B4b′). B4b ran the same `owned_tree.py`
(`e1b699c3`), `lifetime.py` and `owned_command.py` and was exposed in the same way; it passed this rule by chance. The same read sits
under C5/C10 (`tests/run_mutants.py`, `scripts/mutants_r4.py`) and `lifetime.ProcessControl.send`.

## The change (candidate/owned_tree.py, `read_stat` only)

`read_stat` re-reads the stat line ONLY when a fully parsed row fails `validate()` AND its state is `X`. It re-reads at most
`EXIT_DEAD_REREADS` = 100 times, `EXIT_DEAD_PAUSE` = 1 ms apart, and stops when:
1. `/proc` reports the PID gone (ENOENT/ESRCH) → `None`. This is the module's existing and only absence rule; none is added.
2. a row validates → that row is returned. A later process at the same PID carries a different start time, so `OwnedTree` treats
   the known identity as gone by START-TIME MISMATCH, never by PID number.
3. the row is still an invalid `X` after the bound → `ValueError('invalid process stat for <pid>')`, exactly as before.

Every other parse failure raises exactly as before: an empty or short read, a PID mismatch, a state that is not one character, and a
negative pgid on a row whose state is not `X`. A valid `X` row is returned unchanged. A parse error alone never becomes absence.
The worst-case added delay is about 100 ms per persistently invalid `X` row, after which the read fails closed.
`validate`, `snapshot`, `OwnedTree`, `lifetime.py`, `portable_pidfd.py`, `owned_command.py`, the grader and stage2 are unchanged.

## Frozen reference and its pin (tests/test_fix1_protection.py)

`tests/reference/fix4/` stays frozen: its `SHA256SUMS` still lists `candidate/owned_tree.py` `e1b699c3…`, and the test still checks every
line of it. `test_registered_step_and_grade_parameters_unchanged` asserted that `candidate/owned_tree.py` is byte-equal to that reference.
It now asserts instead that:
* `portable_pidfd.py` and `lifetime.py` are still byte-equal to the reference (unchanged);
* `candidate/owned_tree.py` has sha256 `b7b4b28cfb15f3b19ff3ac977983605316a7c179ad7b0ed55acbd9c7b2088d6d`;
* its module body equals the reference's node for node (`ast.dump`), apart from exactly `read_stat`, `import time`, `EXIT_DEAD_REREADS`
  and `EXIT_DEAD_PAUSE`.

## Additions (tests only)

`tests/test_owned_tree_exit_dead.py` (9 tests). It is outside the registered control plan, as the FIX4 and TAGSET tests are. It is not in
`candidate/`, so C2's registered candidate test count is unchanged. Scripted reads: X then ENOENT → absent; X then ESRCH → absent; X then a
reused PID → a new identity (start mismatch, no error); persistent X → error after more than one read; valid X → returned; R with pgid -1 →
error; truncated, empty, PID-mismatch and two-character-state rows → errors. Real processes: a live owned `sleep` whose stat is made
unreadable is never credited as torn down; continuous real `snapshot()` while short-lived trees exit gives no "invalid process stat".
Under the unfixed module (`OWNED_TREE` = the fix4 reference) the race test and the X tests fail; under a mutant that maps every parse error
to absence the real-survivor and strictness tests fail.

## Bytes

| file | TAGSET (`7b73ebe`) | EXITDEAD |
|---|---|---|
| `candidate/owned_tree.py` | `e1b699c3088e2ab13b6bcccc911d065cf4e68bb043859981282c5a5f678f3ea5` | `b7b4b28cfb15f3b19ff3ac977983605316a7c179ad7b0ed55acbd9c7b2088d6d` |
| `scripts/CANDIDATE-COUNTER-SHA256SUMS` | `8da17305…` | its successor (one line changed) |
| `tests/test_fix1_protection.py` | `2eaedc03…` | listed in the scripts manifest |
| `tests/test_owned_tree_exit_dead.py` | — | listed in the scripts manifest |
| this addendum, `scripts/SCRIPTS-COUNTER-SHA256SUMS` | | listed in the manifest / its successor |

Not changed, in any form: every other `candidate/` file; `tests/reference/fix4/` (including its `owned_tree.py` and `SHA256SUMS`); `stage2/`
and `STAGE2-COUNTER-SHA256SUMS` 01860e25; the KMX binding; `SOURCE.json`; both binaries; `source/`; `scripts/control_plan.py` b4b50b80 (so
the plan's `plan_source_sha256` is unchanged); `scripts/grade_controls_r4.py` 32afb14e; `tests/run_mutants.py` 06185875; `scripts/mutants_r4.py`;
every mutant, killer, registered tag, count, argv, timeout, threshold and input. No mutant targets `owned_tree.py`.

## Route and review binding

The candidate manifest changes, so receipt `195e3065` is void for this tuple (`candidate_manifest_sha256` and `scripts_manifest_sha256`
change). The change is installed as a delta into a fresh child of the unconsumed D1 child `90cdc4ce`. The reviewed in-guest delta helper
refuses every `candidate/` path, so a revision that allows exactly `candidate/owned_tree.py`, as a changed file, must be reviewed first.
`dac-preflight` is not run again. A new ACCEPT receipt from a non-author reviewer is required before the receipt install (B4a″). Then ONE
fresh registered attempt (B4b″) runs, whose acceptance rule is the registration with this addendum, reviewed before it runs. The consumed
B4b and B4b′ attempts stay on record as FAILED.

## Still not authorised by this document

Any remote run, any receipt, any execution of C1–C10, S1–S3, inference, calibration, soak or DAC preflight, any retry on a consumed child,
and the owner's decision whether F101 stays release-blocking.
