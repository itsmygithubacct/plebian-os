# F120 P2–P8 acceptance evidence — 2026-08-25

This report binds the implemented resolver, cache, staged-provider path, real
pilot conversion, rollback, measurements and dependent-stream handoff. F120 is
evidence, never release authority: this report does not select a revision or
freeze the final 0.2.1 release lock. The exact published S120 handoff commit is
recorded in the Track H release log after the final clean-tree gate.

## Locked implementation gate

The implementation gate uses uv 0.12.5 and the locked environment:

```text
sha256sum -c SHA256SUMS
SEMANTICS.md: OK
python contracts/validate_f120.py --self-test
PASS: 2 valid, 1 development-state, 7 invalid fixtures; schemas and SHA256SUMS verified
python -m unittest discover -s tests -v
Ran 25 tests
OK
```

The suite includes all eight artifact kinds, independent source-digest
agreement, qualification/development separation, non-finite JSON and uppercase
URL rejection, independent verification of every frozen contract byte before
executing its validator, the fixed `plebian-os@v0.2.0` exception, real cache
separation for architecture/features/toolchain, corrupt-entry
quarantine/refetch, two concurrent writers (aggregate one fetch and one build),
source and build process-group cancellation with no publication, exact-key
eviction, guarded recoverable stage retirement, atomic paired prefix/lock
failure recovery, a competing-destination publication race with no replacement,
cache/prefix workspace separation, cold/warm/clean byte equality, and all ten
future-component scaffolds.

The audit also exercises the otherwise easy-to-miss invariant that two commits
with the same source tree share the source/build cache key. Commit identity is
therefore not embedded in cache metadata or artifact bytes; builds use the
cached source-tree archive and fixed `SOURCE_DATE_EPOCH=0`. A forced rebuild
from two commits with different commit timestamps produced byte-identical
artifacts containing the exact fixed epoch.

## P2/P3 origin and graph acceptance

PR-H-004 is accepted against the owner disposition at SHA-256
`ee0dbc605ecc2b2f694a6411cf4b77e6c9ea4ac725a8ddb0eb0af97629ffc1e7`.
The six initialized rows were synchronized from their committed `.gitmodules`
declarations, the two absent rows and their two newly exposed descendants were
initialized at their indexed commits, and no tracked file or gitlink changed.

The accepted eight-path snapshot is bound as follows:

| # | Indexed commit | Tree | Canonical-source result |
| ---: | --- | --- | --- |
| 1 | `3fc7d8b624385aa070da0acd0720b063becfcc12` | `3a0b62a217c43aa7b03d55d8a89c5773ef51ff43` | exact HTTPS fetch and observed origin match |
| 2 | `35114babdfebe95c347dde1df78ccad8eb1e2747` | `8e558fc74e48f000dab0efa031eb022848e989a5` | exact HTTPS fetch and observed origin match |
| 3 | `35f742d6cf2f7635b43157fcf6f2e0264bf0d761` | `580c7ddac25350403f1a42c169c720be752f49de` | exact HTTPS fetch and observed origin match |
| 4 | `b6b4e1e4b6933d60bfc919a90d8e1f6f86b20e77` | `bf235ebdc29e1185c3df4ee1829317493b03a735` | exact HTTPS fetch and observed origin match |
| 5 | `281ee3bdcdda0725404689cb5b84c6f1cf3ded96` | `1a9f03e7781510e7decf8b8301b5eaf12ac21a74` | annotated tag `f120-pin-281ee3b`; fresh exact fetch succeeds |
| 6 | `2b0c241729dec182a87ebab78edd10b142edf828` | `50b3d030e18540463f1d5c12baa3267c1c86231f` | exact HTTPS fetch and observed origin match |
| 7 | `da9502913c0e07948a0e439c04b6765f2d8857bd` | `e4fb7a03dcaf5c4c94a04afc26d43b3dea02884d` | initialized indexed commit; origin matches declaration |
| 8 | `2b0c241729dec182a87ebab78edd10b142edf828` | `50b3d030e18540463f1d5c12baa3267c1c86231f` | initialized indexed commit; origin matches declaration |

The two descendants exposed by row 7 are also initialized and exact:
`kitty-framebuffer` `784d8aaef6b35acc2306434eb330ab9fe1787359`,
tree `c74c1bc978034f014f16efd9b0be2136d872b05c`, and `kitty-input`
`fca32e2d0f641344eeadb8f242147225d41bff55`, tree
`b4b3a6e0e3ae65338c07a73a4b6d1947f5425617`.

A fresh read-only inventory was generated without invoking the historical
fixed-output writer. Its normalized JSON hashes to
`2031bfb2bf4fc035adb4ff41eb0ae5336469c11f31861f84649031b0e57b3e06`:

| Observation | Count |
| --- | ---: |
| top-level repositories | 81 |
| provider occurrences | 297 |
| initialized/resolved | 297 |
| canonical HTTPS origins | 297 |
| absolute local origins | 0 |
| null origins | 0 |
| other non-HTTPS origins | 0 |
| dirty tracked occurrences | 4 |
| resolved/indexed mismatches | 8 |

The last two rows are intentional development-state facts. P2 accepts them with
`--allow-development-state` and qualification refuses them; it does not hide or
bless them. In particular, the live Kilix Techno development checkout advanced
after the accepted disposition to indexed `pcm-mixer`
`0f391617a1363bc15c347abedfad19a18745240a`, tree
`23b7affc5eadb514ca27891e9c85ff03ab7c3aee`. Its observed origin is canonical,
but a fresh exact-SHA fetch returns `upload-pack: not our ref`. The published
`281ee3b…` tag closes the accepted snapshot only; it is not misapplied to this
later commit. P9 must qualify whichever pin the final release selects.

The regenerated `kitty-framebuffer` development projection validates only with
`--allow-development-state` and refuses strict qualification at rc 2. Its
projection, commit-to-consumer map and strict diagnostic hash respectively to
`9581d0f4a9a8e55bddb909753f21f76cc583382f3831e9575defed7c6986eefb`,
`d2c43f75e44b9f078b8e48884b02878e7c88c4877b12432330cbf4931e37b905`
and `388908314566768405cfe64a7fa2b8cba711be04d68f85df852063a59b03ffa4`.
Four direct reverse-dependency queries completed in 1.400 s and returned:

- `43277b433913…`: 3 consumers;
- `74e8bb292237…`: 4 consumers;
- `784d8aaef6b3…`: 33 consumers; and
- `7a2b58f00662…`: 1 consumer.

The consumer sets byte-match the retained map. The frozen validator self-test
continues to reject all seven invalid-fixture classes, while this real
development projection demonstrates that the same qualification boundary is
observable on current workspace-derived input. P2/P3 are therefore accepted as
mechanism and development-state evidence; no pre-P9 release-lock claim is made.

## Real staged provider

The clean public `kilix-motion-detect` commit
`b09848f0513e7e2f522e26dc87c917340eb59757` was compiled from the cached
committed archive, never in its checkout.

| Binding | Digest |
| --- | --- |
| source tree | `67226af5d27f09ee65c37f0bd16aa464b5745f4a454ca692b28bf32dc2f4c342` |
| toolchain | `719bace1464ae8b7bf7526f869194c3b83733751bfd52340031bb49cd8e2a567` |
| recipe | `3d5e2a53bc098b7149a363e70fe0df4b0103a650692362285ec920c1b72d916f` |
| frozen build key | `078e353c86dbca73f440d16fc3096a4173a94932c92c1febe92a9077ac241a17` |

The toolchain binds exact executable bytes for GNU `ar`, assembler, compiler
driver, `cc1`, `collect2`, linker, make and `mkdir`; architecture is
`x86_64-linux-gnu`, and features are `shared` plus `static`.

| Run | Fetches | Fetch bytes | Builds | Source hit | Build hit | Wall time | Cache bytes | Stage bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| empty network cache | 1 | 37,312 | 1 | 0 | 0 | 2.842 s | 108,937 | 45,139 |
| same network cache | 0 | 0 | 0 | 1 | 1 | 1.075 s | 108,937 | 45,139 |
| independent empty network cache | 1 | 37,312 | 1 | 0 | 0 | 3.563 s | 108,937 | 45,139 |

Cold and independent-clean reports hash to
`fd49c584d60e171ba7d3a97ed792128d2ef5033b9de6847ee7ae4042ff05c8cd`;
the expected warm-state report is
`887fdac3f6c5b46e7f5dac9c8d25f60334de031ef23a808ca233bc1a97c65c68`.
All three stages compare equal recursively, and all three release-lock
mechanism files compare byte-for-byte.

| Artifact | SHA-256 |
| --- | --- |
| public header | `d06ea3b1e88c746a541d6986464cb9a75ae6aa8885ceb01173c0444fbc58ebd5` |
| static library | `e2497fb530f599a6047ee6d1b4dc852cae65d3304f356a913d131c9dda741930` |
| shared library | `701b91e70f3777af3dd12fb46c212c5b083fa9bac9f351802786de86344b7a0f` |
| MIT notice | `938e0db7e6acd7e99d205863bcbdeda47f5fbd053802519f411dbefe0799071e` |
| stage manifest | `07d40344db26b93834361f2bd54eff34776ce162a9495b6879b8136ae0f0a6a0` |
| validated mechanism lock | `484697944434eda24ef670ae628be489fba2ba18de980dbcd5540c60cf1ba656` |

A strict C11 program compiled and ran using only the staged header and static
archive.

## P6 landed pilot and walked rollback

The owner landed the consumer conversion on public `kilix-object-detect` as two
ordered commits:

| Identity | Commit/tree |
| --- | --- |
| selected base | `63b6234b7a30936f8afd4958b450babef6fff6db` |
| test stabilization | `1713b410dc1fbc00bd9011b787ebfdbe1d0e9bf9` |
| staged-prefix conversion | `5b0131dd83ea744271964fb5787deba424e3029b`, tree `881b2e98a29b542cbfef087cc6763ee282200c10` |

The four prepared file hashes match, and the declaration plus mode-160000
gitlink were removed at exact provider object `b09848f…`. Root reran the gate:
25 source tests plus 8 command checks pass, all three missing-prefix/header/
archive controls refuse at rc 2 without creating a build directory, prefix-free
`make clean` works, and the command defines 8 and leaves 0 unresolved `kmd_`
symbols with no provider shared-library dependency.

A real two-component F120 observation was then emitted and qualified. The
registration hashes to
`3bc2cd79d0fb66216275be901eabcfe1a5590ecb2a59db5480e627381a6eb638`;
the workspace manifest hashes to
`967129b3667d088446de19bf07379ed924cceb980f26c9cbceb573e811324ae6`.
It binds consumer source digest
`276af87caea5604103fa1776d1860cd716b9d75ed75ac337a067ba4f88521983`,
records `kilix_motion_detect_linkage=static`, and contains exactly this edge:

```json
{
  "consumption_mode": "staged-prefix",
  "from": "kilix-object-detect",
  "required_abi_version": "0.2",
  "required_api_version": "0.2",
  "required_tests": [
    "command-selftest",
    "detection",
    "installed-consumer",
    "regions",
    "scaler"
  ],
  "runtime_process": "kilix-look",
  "to": "kilix-motion-detect"
}
```

`reverse-deps` returns exactly `kilix-object-detect` for the provider. The
consumer API/ABI 0.1/0.1 and component version 0.1.0 come from its committed
public-header version macros; the edge separately requires the provider's
0.2/0.2 interface.

Track H reran the complete landed-tree surface. Sanitizer passed all 33 checks;
the installed command passed all 8 self-tests and the install contained four
files. All three fail-closed controls returned rc 2 with no build directory.
Linkage again showed 8 defined/0 unresolved provider symbols, 0 provider `.so`
dependencies and 0 private motion-source path hits. The original checkout
remained clean at `5b0131d…`.

The rollback was walked from exact landed Commit B in a disposable checkout.
`git revert --no-commit 5b0131d…` produced index tree
`d8b393576de5bfa46d7c2fb7ad20f82790b57241`, exactly Commit A's tree. It
restored provider `b09848f…`, tree
`56f8236512207139db9a896db834d55e0650e6fa`, from the canonical HTTPS
declaration. The nested command, full 33-check surface, sanitizer and installed
self-test passed without `F120_PREFIX`. The public consumer and original local
checkout remained unchanged at the landed tip. P6 is accepted.

## P7 decision-rule measurements

The complete positive command surface was regenerated from the landed
conversion and the verified Commit-A rollback tree using the same external
build-directory method:

| Leg | Result | Wall time | Output files | Output bytes |
| --- | --- | ---: | ---: | ---: |
| landed staged prefix | 33 checks pass | 10.313 s | 45 | 2,305,962 |
| exact nested rollback | 33 checks pass | 9.760 s | 47 | 2,391,478 |
| staged delta | same behavior | **+0.553 s** | **-2** | **-85,516** |

The warm local staged timing sample is slower and is retained as such; it does
not replace the earlier faster sample. The remaining decision axes are:

| Measure | Nested | Staged | Result |
| --- | ---: | ---: | --- |
| distinct provider resolutions | 1 | 1 | unchanged |
| initialized checkouts in complete clone | 12 | 11 | -1 |
| complete-clone wall time | 17.440 s | 12.462 s | -4.978 s |
| complete-clone bytes | 4,684,205 | 4,495,702 | -188,503 |
| consumer-local provider compilations | 1 | 0 | removed; one shared cached build |
| warm source/build operations | n/a | 0 fetches / 0 builds | both cache hits |
| consumer-local pin edits | 1 | 0 | moved to one central registration edit |
| total one-consumer pin edits | 1 | 1 | unchanged |
| reverse-dependency query | no deterministic command | 4 queries / 1.400 s | exact consumer sets |
| independently releasable components | 2 | 2 | preserved |
| CI jobs/minutes | null | null | repository defines no CI |

The removed worktree plus Git object store measured 188,376 bytes. One reusable
source/build cache plus stage is 154,076 bytes, a conservative 34,300-byte
one-consumer saving under those direct measurements; the separately measured
complete-clone reduction is 188,503 bytes. Rollback changes one exact consumer
commit and restores one exact gitlink; cache retirement remains scoped to the
named source/build keys and is unnecessary while another consumer uses them.

Checkout count, clone time, clone bytes, duplicate compilation and build-output
storage improve; pin churn and independent release boundaries do not regress.
The single regenerated warm timing does not improve, and is not hidden. The
decision rule therefore retains the conversion and the tooling. P7 is accepted.

## P8 dependent-stream handoff

Track C's exact image-manifest tip
`143b24c0a71d2ca7831a5860281a018aa2492737` was integrated into the Track H
line by merge `7902ce1b6954d9f83efcaff0a6f8874abf5b0e82`, tree
`37deaa92848cc26d9205e2bd063f8262e832387d`, with Track H tip `da1a9d0…` and
Track C tip `143b24c…` as its two parents. The two sides changed zero overlapping
paths. Track C's branch was not moved.

The stable interface is the command surface in `README.md`, the registration
and qualification procedure in `INTEGRATION.md`, the four pre-repository
registration fixtures covering F106, F110, F111 and F121, and `make check` as
the consumer-facing conformance gate. The fixtures cover all ten named future
components and emit schema-valid development manifests while refusing
qualification until owners replace their sentinels. A stream can therefore
register before repository creation, resolve honestly, then qualify and consume
only the staged public prefix after landing.

The final clean-tree check, recursive publication hygiene result, exact
publication commit and remote verification are retained in the Track H log.
At that exact ref, P8 is the S120 implementation handoff. P9 remains deliberately
open for F118's ledger/package freeze and Track C's final `releases/0.2.1.env`;
no mechanism lock named in this report is the 0.2.1 release lock.
