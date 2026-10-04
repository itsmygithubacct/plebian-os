# Seat 2: independent RC5 Tower and guide carrier review
VERDICT: ship

I did not author any of the candidate source changes, the carrier generator, or the provisional carrier.

This verdict accepts the candidate carrier rebind within the assembly boundary below. I independently reviewed the supplied inputs, without consulting the other seat or aborted-seat directories. All extracted trees, local shared clones, scripts, test state, and logs are inside this seat. The original repositories were used only for object reads; no network, pushes, commits, or original-repository worktrees were used.

## Exact reviewed inputs

| Component | Accepted base | Candidate |
| --- | --- | --- |
| Plebian-OS | `be2cd4fa63f52a3a62aa8099302ef9e988fabbdf` | Same base plus `../os-candidate-pins.patch` |
| Kilix host | `e76ea0beb4c7d3340490e6d2dc3bd1a97bd9f3ab` | `2e1638e8392f88160b2a6343a8672c32c98fb188` |
| Kilix 95 | `03da5ffb303c1483a733b4bd2230c13612b4871c` | `14b466a998074d151d2e63dee6b0d8f2763034d0` |
| Content | `1210151be1757d8f62b402b7b3196e1564d976b3` | `ce6c0c63a852b10c6ca2b2f7ed8087934d75f4d0` |
| Licence | `ca8a0f479893ab9c8cd6cadc2716c474aaad2820` | Unchanged |
| Needle | `7de641763c403f8c54873ef4d044277c946d4445` | Unchanged |
| TUI | `8b461045715f176218c57b17ff16ccfd756aace1` | Unchanged |

The host intermediate commit is `bd621ec29415e2c125a989370f4c419950d009e0`, followed by the exact candidate host commit above. The patch SHA-256 is `906dff6861266845c672e88e71bbb1568836729e6ed7b50c68d26555e590175d`.

The reviewed provisional directory is `../provisional-carrier`; its `CARRIER.json` SHA-256 is `3df644bf49055c519976369693c0638308f5588658a9ad2918d83e61debc4e8a`. The accepted base carrier was extracted from `releases/0.2.2-model-compliance` at the OS base above. Its carrier and receipt SHA-256 values are respectively `96ec0550c5adb5bcd155102cdb0fe3d82fdce65ff82a2001ebfdd2079290de79` and `2e2e2c294fc59bbd5590130e155349eb63106a5b76bcabfb27936ca26f4cede9`.

All six files in `../determinations` were checked against both carriers. Supporting test inputs were the unchanged voice selection `a12be47e289ca03fccd46840276add1833df5760`, provider source `e255d4af90eb3593c880e10894f2a128aa28eec7`, host-selected native state source `33b88c9ff7cd89c2f768d279eeeacecbcd33f73f`, and frame presenter `fa770639eab1f1c1307ecb0a651b8a2a301eec49`.

## Evidence and findings

1. The candidate host's Content gitlink and provider `CONTENT_REF` both equal the full candidate Content SHA. The host TUI installer is byte-identical to the base and defaults to the full TUI SHA above. Content's TUI package and Needle entry are unchanged; Needle's TUI gitlink agrees. These were checked from exact Git objects, not repository working trees.

2. Content changes exactly two paths: the catalog gains one `pleb-tower` game entry, and the receipt authority re-pins its catalog digest. Removing that single entry restores the entire prior catalog mapping. All 32 asset records, packages, existing content entries, licence material, upstream pins, and schemas are unchanged. The catalog bytes hash to `4a9ad875438f7b82ad6dd185298de858c85510e65f802c4ef7dcddc8d8149b75`, exactly the new trust digest; `tools/generate_upstream_records.py --check` passes. The unchanged asset/v3 schema SHA-256 is `07cb268fb8aa0c6131d6c230af3f7ede094270a1214efd3ae5deb407d6a8e870`. No model, weights, or licence determination is introduced.

3. Against the accepted base, only `CARRIER.env`, `CARRIER.json`, `BINDINGS.sha256`, and `SHA256SUMS` change among shared paths. The old receipt and two old seat files are absent, as the brief requires; no paths are added. The JSON changes only `interface_content_ref` and its resulting `bindings_sha256`; the environment projection changes only `interface_content_ref`. All 33 model artifact/licence records, licence texts, owner determinations, NOTICE, and DELIVERY files are byte-identical. The four-model set and order, licence pin, and all archive/library digests remain identical. In particular, the dictation download digest remains `30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498`, and the library digest remains `25e025093c4399d7278f543568ed8cc5460ac3a4bf48c23673ace1e25d26619f`.

4. The generator is byte-identical to the accepted OS base. Running it with the candidate manifests, exact Content and Licence objects, and all six unchanged determination files reproduces the entire provisional directory with `--check`. Both checksum manifests pass `sha256sum -c`; an independent check also confirms their complete expected membership and the binding digest in `CARRIER.json`.

5. Kilix 95 changes only `.github/workflows/test.yml`'s `KILIX_COMMIT`, from the base host to the exact candidate host. Its full local runner passes 80/80 suites against that host with the selected native submodules initialized from local objects.

6. The host diff contains only README, the game settings entry, the provider Content constant, the Content gitlink, and `docs/AGENTS.md`. The game entry and guide rewrite are in scope here only for possible effects on carrier integrity, model delivery, and licence obligations. They introduce no change to the generator, model acquisition implementations, licence receipt enforcement, or carried records. This review does not qualify the game or guide's wider behavior.

## Commands, checks, and limitations

`review.py` and the suite runners retain exact argv, working directories, explicit overrides, outputs, and exit codes under `logs/`. Every suite uses a sanitized environment: inherited `KILIX_*`, `GPU_TERMINAL_*`, `KITTY_*`, and `PLEB_*` variables are removed; HOME, TMPDIR, and all XDG paths point inside this seat. Final runs additionally remove the broader `KILIX` and `PLEB` families, including desktop-specific variables. Required overrides select only seat-local sources/state or read-only object repositories. Original sources are never modified.

| Command/check | Result and log |
| --- | --- |
| `python3 review.py`; exact `git diff`, `rev-parse`, `ls-tree`, and byte comparisons | Pass; `logs/review.log`, `logs/evidence.log`, component diff logs |
| Generator with `--content-repo`, `--license-repo`, six `--determination` arguments, `--out ../provisional-carrier --check` | Exit 0; `logs/carrier-generator-check.log` contains the complete command |
| `sha256sum -c SHA256SUMS` and `sha256sum -c BINDINGS.sha256` in the provisional directory | Both exit 0; `logs/verify-*.log` |
| `tools/generate_upstream_records.py --check` on extracted Content | Exit 0; `logs/content-upstream-check.log` |
| `python3 run_suites.py`, then `python3 run_followups.py` | Initial Content run: 49 passes and one socket error; offline follow-up: 49/49 pass. Logs preserve both results |
| `python3 run_final_checks.py` | Eight focused host suites: 101/101 pass; `logs/final-host-*.log` |
| `python3 run_host_records.py` via sanitized runner | 10/10 pass, including packaged model licence texts, verified catalog selection, tamper refusal, read-only listing, and supplied-directory refusal; `logs/host-model-records.log` |
| Existing provider route suite with exact supporting source | Seven of nine test methods pass; two preparation methods encounter the ownership limitation below; `logs/host-provider-complete.log` |
| `python3 run_f100.py` via sanitized runner | Nine checks pass; `logs/final-f100-provisional.log` |
| Kilix 95 `python3 tests/run.py` with seat-local `KILIX_HOME` | 80/80 pass; `logs/k95-full.log` |
| Final extracted-file comparison to exact no-replacement Git archives | Pass; `logs/snapshot-verification.log` |

The F100 run redirects the carrier path in memory before loading the existing test module; it preserves assertions and supplies private HOME/TMPDIR/XDG paths to guard subprocesses. Existing AC-1, AC-2, AC-3, AC-5, AC-8, AC-9, and the image-served-record comparison pass. AC-4's existing pinned-artifact helper also passes. A separate control verifies that the provisional release guard refuses with `ACCEPTANCE.json is missing or not a regular file`. Full AC-4's receipt-rebinding subcase, AC-6, AC-7, AC-10, AC-11, AC-12, and positive-control gitlink guard regressions require the assembled receipt and remain for final assembly.

Failures and explanations are retained:

- One Content first-use receipt test fails with `PermissionError: [Errno 1] Operation not permitted` while creating its loopback TLS socket. Its assertion path could not run in this sandbox. The follow-up excludes precisely that test, retaining all other 49 tests and their assertions; this is a limitation, not a claim that the complete initial suite passed.
- The initial provider run skipped two preparation methods and seven launcher subcases because its supporting source was absent. Supplying the exact pinned source exercises the launcher and all seven tamper/control subcases successfully, but the two preparation methods stop before transaction checks at `managed directory chain is unsafe`. The sandbox presents `/` and `/home` as UID 65534 while the process is UID 1000. `logs/provider-environment-control.log` proves the identical guard from both exact base and candidate commits makes the same refusal. The guard was not relaxed, and preparation behavior beyond it was not verified here.
- Early seat-local evidence harness attempts assumed a different trust-constant layout and licence field spelling. Those harness exceptions are preserved in `logs/review-harness-*-failure.log`. Correcting the harness to parse the actual constant and field yields the passing comparisons; these were not candidate test failures.

## Acceptance boundary

Final assembly must regenerate the carrier with both fresh seat files, pin the actual `CARRIER.json` and `ACCEPTANCE.json` hashes in both `releases/0.2.2.env` and `releases/0.2.2.requirements`, and pass the full carrier acceptance and defect suite. The current patch intentionally retains the prior carrier and receipt pins, and the provisional directory intentionally has no acceptance receipt. This seat record does not substitute for that final assembly or its checks.

No runtime VM, ISO, F101/F104, or release qualification claim is made.
