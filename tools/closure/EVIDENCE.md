# F120 mechanism and H4 evidence — 2026-08-25

This is mechanism evidence, not release authority. It does not select a
revision, land a consumer conversion, authorize a repository change, announce
S120, or freeze the 0.2.1 release lock.

## Locked implementation gate

The final tree was checked with uv 0.12.5 and the locked environment:

```text
sha256sum -c SHA256SUMS
SEMANTICS.md: OK
python contracts/validate_f120.py --self-test
PASS: 2 valid, 1 development-state, 7 invalid fixtures; schemas and SHA256SUMS verified
python -m unittest discover -s tests -v
Ran 25 tests in 12.161s
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

## Real staged provider

The clean public `kilix-motion-detect` `main` commit
`b09848f0513e7e2f522e26dc87c917340eb59757` was observed read-only. Compilation
occurred from the cached committed archive, never in its checkout.

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

Cold and clean reports have SHA-256
`fd49c584d60e171ba7d3a97ed792128d2ef5033b9de6847ee7ae4042ff05c8cd`;
the expected warm-state report is
`887fdac3f6c5b46e7f5dac9c8d25f60334de031ef23a808ca233bc1a97c65c68`.
All three stages compare equal recursively, and all three release-lock evidence
files compare byte-for-byte.

Every artifact digest matched across cold, warm and independent caches:

| Artifact | SHA-256 |
| --- | --- |
| public header | `d06ea3b1e88c746a541d6986464cb9a75ae6aa8885ceb01173c0444fbc58ebd5` |
| static library | `e2497fb530f599a6047ee6d1b4dc852cae65d3304f356a913d131c9dda741930` |
| shared library | `701b91e70f3777af3dd12fb46c212c5b083fa9bac9f351802786de86344b7a0f` |
| MIT notice | `938e0db7e6acd7e99d205863bcbdeda47f5fbd053802519f411dbefe0799071e` |
| stage manifest | `07d40344db26b93834361f2bd54eff34776ce162a9495b6879b8136ae0f0a6a0` |
| validated release-lock evidence | `484697944434eda24ef670ae628be489fba2ba18de980dbcd5540c60cf1ba656` |

A strict C11 program compiled and ran using only the staged header and static
archive. This proves the public prefix is consumable; it is not the required
real consumer landing.

## Pilot scratch result and decision-rule measurements

The exact conversion was tested against a disposable clone of the 0.2.1
release-selected `kilix-object-detect` commit
`63b6234b7a30936f8afd4958b450babef6fff6db`. It replaces direct compilation of
the nested motion source with the staged public header/static archive and
removes the motion gitlink and declaration. Reversing the exact diff restores
the rollback leg.

| Leg | Result | Wall time | Output files | Output bytes |
| --- | --- | ---: | ---: | ---: |
| staged prefix | 9 region + 13 detection + 3 scaler + 8 self-tests pass | 11.263 s | 44 | 2,304,430 |
| exact nested rollback | same suites pass | 13.883 s | 46 | 2,390,115 |

The removed object is exactly `vendor/kilix_motion_detect.o`; inspection found
zero private motion-provider API uses. Static linkage matches the prior
compile-in model.
The two `test-detect` binaries are byte-identical at
`ca397c1692964f34af0f2c3950d704af28ea7040d9778acc27b49901b45dbf26`.

The pilot also exposed two existing consumer-test defects. The detection test
hard-codes `build/test-detect-child.log`, so a non-default `BUILD_DIR` requires
an unrelated `build/` directory. Its `offering does not wait` case spins for a
fixed iteration count without yielding and fails intermittently in both modes.
Successful complete runs are retained above; failed attempts are not concealed.
The byte-identical test executables isolate these failures from the staged
provider artifact.

| Checkout leg | Wall time | Bytes | Initialized nested checkouts |
| --- | ---: | ---: | ---: |
| local top clone + all real HTTPS submodules | 17.440 s | 4,684,205 | 12 |
| same, omitting only motion checkout | 12.462 s | 4,495,702 | 11 |
| measured reduction | 4.978 s | 188,503 | 1 |

The removed motion worktree is 106,280 bytes and its nested Git object store is
82,096 bytes. The reusable source/build cache plus one stage is 108,937 +
45,139 = 154,076 bytes, a conservative one-consumer reduction of 34,427 bytes
against the measured complete checkout. The comparison clone still retained
the uninitialized gitlink declaration, so this does not overstate removal.
Consumer-local motion pin edits fall from one to zero, but the central F120
registration/lock requires one pin edit: total one-consumer pin churn is
unchanged at one. Distinct motion resolutions remain one, and independently
releasable component count remains two.

The selected consumer commit has no GitHub Actions, GitLab CI, Jenkins, or
Buildkite definition. CI jobs and CI minutes are therefore null; no runtime or
cost reduction is inferred.

## Reverse-dependency evidence

A current read-only inventory projection produced a frozen-schema-valid but
deliberately dirty/unresolved development manifest. It has four
`kitty-framebuffer` revisions and 41 unique build-referenced consumer edges.
The projection and commit-to-consumer map digests were respectively
`a46f9b69e749dae7865178f26e260d4c6f3b8c72a7caacb8ef1ec2ff9450fc43` and
`d2c43f75e44b9f078b8e48884b02878e7c88c4877b12432330cbf4931e37b905`.
The `reverse-deps` command returned exactly, in 2.517 s total:

- `43277b433913…` (3, 0.612 s): `kilix-pdf`, `kilix-techno`,
  `kitty-terminal-session`;
- `74e8bb292237…` (4, 0.594 s): `chumrunner`, `kilix-fantasy`,
  `legend-of-kilix`, `pleb-bound`;
- `784d8aaef6b3…` (33, 0.695 s): 26 game consumers (`bash-fighter`, `bashed-earth`,
  `c-com-ufo-defense`, `chess-bash`, `joustix`, `kilix-advanced-tactics`,
  `kilix-billiards`, `kilix-brokeout`, `kilix-fishtank`, `kilix-flight`,
  `kilix-game-sdk`, `kilix-jpak`, `kilix-land`, `kilix-lander`, `kilix-lights`,
  `kilix-offroad`, `kilix-pong`, `kilix-punch-club`, `kilix-rancher`,
  `kilix-trigger`, `kilix-warpath`, `pleb-driver`, `pleb-plant-grower`,
  `pleb-tower`, `shellda`, `super-kilix`) plus `kilix-nvr`, `kilix-cap`,
  `kilix-land-desktop`, `kilix-mask`, `kilix-object-detect`, `kilix-rtsp`, and
  `kilix-sound-detect`;
- `7a2b58f00662…` (1, 0.616 s): `kilix-playalong`.

The fourth revision and `kilix-techno` edge are current drift from the earlier
three-revision baseline; the resolver reports them rather than hiding them.

## Open gates

- P6 is blocked on the consumer owner landing and qualifying PR-H-003, fixing or
  qualifying the two consumer-test defects, and walking the exact rollback from
  the landed state.
- P7 now has measured clone time/bytes, cache/stage bytes, build outputs,
  pin-churn, nested-checkout count, honest null CI values, and scratch rollback.
  It remains blocked on P6 because the decision table requires a landed pilot
  and rollback walked from that landed state.
- P8/S120 is not announced while P6/P7 remain open, although the command
  surface, integration guide and ten development scaffolds are ready.
- P9 is blocked on F118's third-party ledger/package freeze and Track C's final
  0.2.1 environment. No lock in this report is a frozen release lock.
