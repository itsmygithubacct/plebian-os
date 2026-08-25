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
Ran 13 tests in 7.445s
OK
```

The suite includes independent source-digest agreement,
qualification/development separation, causal build-process-group cancellation,
the fixed
`plebian-os@v0.2.0` exception, build-key dimension separation, corrupt-entry
quarantine/refetch, two concurrent writers (aggregate one fetch and one build),
recoverable exact-key eviction, recoverable stage retirement, cold/warm/clean
byte equality, and all ten future-component scaffolds.

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

| Run | Fetches | Builds | Source hit | Build hit | Wall time | Cache bytes | Stage bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| empty cache, final code | 1 | 1 | 0 | 0 | 2.35 s | 109,067 | 45,139 |
| same cache, final code | 0 | 0 | 1 | 1 | 1.41 s | 109,067 | 45,139 |
| independent empty cache | 1 | 1 | 0 | 0 | 2.57 s | 109,067 | 45,139 |

Cold and clean reports have SHA-256
`7a42ce9729d4677b496616f77fcdf6ff83c5f53ac14f08c5d2af4bd05b35cb47`;
the expected warm-state report is
`f4029b2cd63bcd823c694f66355ae8b2cf0f93831786e3924d1384e41e4b4206`.

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

## Pilot scratch result and decision-rule nulls

An exact Makefile diff was tested against a disposable copy of
`kilix-object-detect` commit
`ba773db8e8b05d283f1efae909ba3b5ac4044269`. It replaces direct compilation of
the nested motion source with the staged public header/static archive and keeps
an explicit nested rollback mode.

| Leg | Result | Wall time | Object files |
| --- | --- | ---: | ---: |
| staged prefix | 9 region + 10 detection + 7 self-tests pass | 9.08 s | 18 |
| nested rollback | same suites pass | 10.96 s | 19 |

The removed object is exactly `vendor/kilix_motion_detect.o`; inspection found
zero private motion-provider API uses. Static linkage matches the prior
compile-in model.

The one-consumer storage result is not an improvement: its nested provider
worktree is 106,280 bytes, while the reusable source cache is 63,820 bytes, the
build cache 45,247 bytes, and the stage 45,139 bytes. Clone bytes were not
measured because the proof used an explicit local immutable source. The gitlink
was not removed, no pin moved, and pin-churn therefore remains unchanged. These
nulls prevent an efficiency-gate claim.

## Reverse-dependency evidence

A current read-only inventory projection produced a frozen-schema-valid but
deliberately dirty/unresolved development manifest. It has four
`kitty-framebuffer` revisions and 41 unique build-referenced consumer edges.
The projection and commit-to-consumer map digests were respectively
`a46f9b69e749dae7865178f26e260d4c6f3b8c72a7caacb8ef1ec2ff9450fc43` and
`d2c43f75e44b9f078b8e48884b02878e7c88c4877b12432330cbf4931e37b905`.
The `reverse-deps` command returned exactly:

- `43277b433913…` (3): `kilix-pdf`, `kilix-techno`,
  `kitty-terminal-session`;
- `74e8bb292237…` (4): `chumrunner`, `kilix-fantasy`,
  `legend-of-kilix`, `pleb-bound`;
- `784d8aaef6b3…` (33): 26 game consumers (`bash-fighter`, `bashed-earth`,
  `c-com-ufo-defense`, `chess-bash`, `joustix`, `kilix-advanced-tactics`,
  `kilix-billiards`, `kilix-brokeout`, `kilix-fishtank`, `kilix-flight`,
  `kilix-game-sdk`, `kilix-jpak`, `kilix-land`, `kilix-lander`, `kilix-lights`,
  `kilix-offroad`, `kilix-pong`, `kilix-punch-club`, `kilix-rancher`,
  `kilix-trigger`, `kilix-warpath`, `pleb-driver`, `pleb-plant-grower`,
  `pleb-tower`, `shellda`, `super-kilix`) plus `kilix-nvr`, `kilix-cap`,
  `kilix-land-desktop`, `kilix-mask`, `kilix-object-detect`, `kilix-rtsp`, and
  `kilix-sound-detect`;
- `7a2b58f00662…` (1): `kilix-playalong`.

The fourth revision and `kilix-techno` edge are current drift from the earlier
three-revision baseline; the resolver reports them rather than hiding them.

## Open gates

- P6 is blocked on the consumer owner landing and qualifying the queued exact
  diff, deciding the gitlink, and walking rollback from the landed state.
- Full P7 is blocked on P6. Clone/CI/pin-churn and landed rollback numbers are
  null, so the repository-consolidation decision rule has not passed.
- P8/S120 is not announced while P6/P7 remain open, although the command
  surface, integration guide and ten development scaffolds are ready.
- P9 is blocked on F118's third-party ledger/package freeze and Track C's final
  0.2.1 environment. No lock in this report is a frozen release lock.
