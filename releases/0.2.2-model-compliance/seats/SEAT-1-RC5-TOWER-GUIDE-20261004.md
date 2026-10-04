# Seat 1 — RC5 Tower / guide carrier rebind — 2026-10-04
VERDICT: ship

I independently reviewed the exact candidate below. I did not author these changes. I did not read or coordinate with the other seat, read aborted-seat directories, or use earlier seat records as approval. This verdict covers the model-compliance carrier rebind, subject to the final assembly boundary below. No candidate defect affecting the carried models, model delivery gates, or licence obligations was found. The environment prevented some broader checks; their failures and limits are recorded here.

## Exact reviewed inputs

| Component | Accepted base | Reviewed candidate |
| --- | --- | --- |
| Plebian-OS | `be2cd4fa63f52a3a62aa8099302ef9e988fabbdf` | That exact commit plus `../os-candidate-pins.patch` |
| Kilix host | `e76ea0beb4c7d3340490e6d2dc3bd1a97bd9f3ab` | `2e1638e8392f88160b2a6343a8672c32c98fb188` |
| Kilix 95 | `03da5ffb303c1483a733b4bd2230c13612b4871c` | `14b466a998074d151d2e63dee6b0d8f2763034d0` |
| Content | `1210151be1757d8f62b402b7b3196e1564d976b3` | `ce6c0c63a852b10c6ca2b2f7ed8087934d75f4d0` |
| Licence | `ca8a0f479893ab9c8cd6cadc2716c474aaad2820` | Unchanged |
| Needle | `7de641763c403f8c54873ef4d044277c946d4445` | Unchanged |
| TUI | `8b461045715f176218c57b17ff16ccfd756aace1` | Unchanged |

The host's intervening launcher/content-pin commit is `bd621ec29415e2c125a989370f4c419950d009e0`. The game catalog entry selects `9e4595ee1dee699efeb9668b7d96d6ce6cda40da`; this review does not qualify that game's runtime.

The patch SHA-256 is `906dff6861266845c672e88e71bbb1568836729e6ed7b50c68d26555e590175d`. The provisional input is `../provisional-carrier`; its exact `CARRIER.json` SHA-256 is `3df644bf49055c519976369693c0638308f5588658a9ad2918d83e61debc4e8a`. The comparison carrier is the accepted `releases/0.2.2-model-compliance` from the OS base. Its prior carrier and receipt pins are respectively `96ec0550c5adb5bcd155102cdb0fe3d82fdce65ff82a2001ebfdd2079290de79` and `2e2e2c294fc59bbd5590130e155349eb63106a5b76bcabfb27936ca26f4cede9`; those prior pins remain in the candidate manifests and are not approval of this provisional carrier.

The unchanged generator is `build/generate-model-compliance.py` at the OS base. Additional exact local sources used by its existing checks were Voice `a12be47e289ca03fccd46840276add1833df5760`, Bonsai `630da3cf64d28b35fb65cafd4e7c8a4ad54b8685`, native state `33b88c9ff7cd89c2f768d279eeeacecbcd33f73f`, frame presenter `fa770639eab1f1c1307ecb0a651b8a2a301eec49`, and provider `e255d4af90eb3593c880e10894f2a128aa28eec7`. Their runtime behavior is not release-qualified here.

The six owner inputs under `../determinations` were compared byte for byte with both carriers:

| Relative determination path | SHA-256 |
| --- | --- |
| `lgraph-en-us/OWNER-DETERMINATION-lgraph-en-us.md` | `109fc3ad04b0bd7d76c00e8987a7bdbdc81e7dac389b4c3c46f7eea8b3ecdecf` |
| `small-en-us/OWNER-DETERMINATION-small-en-us.md` | `b6a44eca20a27c550b7fe1cf8e83e384f5ead0c2086130d24dd7684c1a536263` |
| `vibevoice-asr-bitnet/OWNER-DETERMINATION-vibevoice-asr-bitnet.md` | `889658d7317c30f3fc8cdd1780f961feaeb9017573dccdfc552185967228bd33` |
| `vibevoice-asr-bitnet/OWNER-RULING-C2-AMENDMENT-2026-09-29.md` | `8723530b4c230e08627dbd2a7dd94ad8e4b25c25cd9dfa40f265832fb6d4b3d6` |
| `vibevoice-asr-bitnet/OWNER-RULING-J1-J2-2026-09-25.md` | `3618c282d871e8333b53aec18561658fb2a9d94b91dd9861358c901cbff6dcf9` |
| `whisper-small-en/OWNER-DETERMINATION-whisper-small-en.md` | `48c5bd4c2e23f78e538dd1608fbd27c429b3e5c4b785b8284e63ce989472d6ba` |

## Findings and evidence

1. **Consumer selections agree.** Reading the candidate host's Git objects with `--no-replace-objects` establishes that `third_party/kilix-content` is exactly `ce6c0c63a852b10c6ca2b2f7ed8087934d75f4d0`. The host provider's `CONTENT_REF` and carrier's `interface_content_ref` are the same full commit. The host's TUI installer bytes are identical to the accepted host; its default, Content's TUI package selection, and Needle's TUI gitlink all select `8b461045715f176218c57b17ff16ccfd756aace1`. Content's Needle selection remains `7de641763c403f8c54873ef4d044277c946d4445`.

2. **Content changes only the game row and trust digest.** The full Content diff has exactly two paths: `src/kilix_content/catalog/plebian.json` and `src/kilix_content/receipt.py`. Removing the single `pleb-tower` entry from the parsed candidate catalog reproduces the complete base catalog. All 32 asset records compare equal, including ordering and every nested value. The catalog bytes hash to `4a9ad875438f7b82ad6dd185298de858c85510e65f802c4ef7dcddc8d8149b75`, exactly the new trust root. `tools/generate_upstream_records.py --check` passes. The asset/v3 schema is byte-identical, with SHA-256 `07cb268fb8aa0c6131d6c230af3f7ede094270a1214efd3ae5deb407d6a8e870`. The diff introduces no model, weights, or licence determination.

3. **Carrier evidence is preserved.** The provisional directory contains 37 files. Its only changed files shared with the base are `CARRIER.json`, `CARRIER.env`, `BINDINGS.sha256`, and `SHA256SUMS`. The earlier receipt and two earlier seat files are absent by design; no other files are added or removed. All remaining shared files are byte-identical, including model artifacts, licence records, licence texts, all six determinations, NOTICE, and DELIVERY. Parsed carrier JSON differs only in `interface_content_ref` and `bindings_sha256`; `CARRIER.env` differs only in the Content ref. All four model entries and their archive/member/download digests remain identical. The preserved model order is `small-en-us`, `lgraph-en-us`, `vibevoice-asr-bitnet`, `whisper-small-en`; the dictation selection remains `small-en-us`. The licence interface pin is unchanged. The preserved library digest is `25e025093c4399d7278f543568ed8cc5460ac3a4bf48c23673ace1e25d26619f`.

4. **Generation and binding verification pass.** The generator itself compares byte-identically with the OS base object. Running it with the candidate manifests, exact Content and Licence Git objects, and all six unchanged determinations passes `--check` against the entire provisional directory. Both checksum listings verify, their inventories are complete, and the carrier's bindings digest matches the actual `BINDINGS.sha256` bytes.

5. **Release and CI changes are bounded.** Parsing the patched OS manifests shows that only `KILIX_REF`, `KILIX95_REF`, and `PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF` change in `.env`, and only the Content ref changes in `.requirements`; the note table changes consistently. The Kilix 95 diff is solely `.github/workflows/test.yml`'s `KILIX_COMMIT`, replacing the accepted host with the exact candidate host. Its complete runner passes 80/80 test files against the seat-local candidate host after local pinned submodule preparation.

6. **Other changes are reviewed only for carrier impact.** The game entry, game toggle, README text, and guide rewrite do not modify model assets, weight-fetch code, licence authorities, or receipt gates. The shorter guide removes the previous explicit sentence about avoiding model installation or licence acceptance changes for a pane action; it retains authorization boundaries and warns that optional wrappers can install components. No new model-acquisition instruction or gate bypass was found. This is a carrier/delivery/licence review, not a general guide or game qualification.

## Commands, checks, and results

All writes and logs were confined to this seat. Sources were extracted using `git -C REPO archive SHA` or cloned locally using `git clone --shared --no-checkout REPO DEST`, followed by exact detached checkout where tests needed Git metadata. No source repository was modified, no worktree was created there, and no push or external network access was used. Preparation details are in `logs/extraction.log`, `logs/local-clones.log`, `logs/prepare-sources.log`, `logs/prepare-presenter.log`, and `logs/prepare-provider.log`. Full candidate diffs are in `logs/content-diff.log`, `logs/host-diff.log`, and `logs/k95-diff.log`.

Every suite and generator check was launched through `tools/run_logged.py`. It constructs an environment from only ordinary PATH/locale/timezone values, dropping every inherited `KILIX_*`, `GPU_TERMINAL_*`, `KITTY_*`, `PLEB_*`, and XDG variable. HOME, TMPDIR, and all standard XDG roots point inside `seat1/sandbox`. Explicit test overrides select only seat-local sources. Suite-created scratch roots inherit that TMPDIR. Each log records the exact argv, cwd, complete sanitized environment, output, exit code, and elapsed time. No inherited production-store selection was used.

| Command/check | Result and log |
| --- | --- |
| `python3 tools/run_logged.py binding-audit -- python3 tools/verify_bindings.py` | PASS; exact refs, catalog comparison, trust digest, schema, byte inventories, metadata preservation, six determinations, generator identity, and CI-only diff. `logs/binding-audit.log` |
| `python3 tools/run_logged.py manifest-scope -- python3 tools/check_manifest_scope.py` | PASS; manifest value changes, patch hash, unchanged prior assembly pins, determination hashes. `logs/manifest-scope.log` |
| In `snapshots/content`, `PYTHONPATH=src:third_party/kilix-license/src python3 tools/generate_upstream_records.py --check` through the runner | Exit 0. `logs/content-pins.log` |
| `python3 tools/run_logged.py regeneration -- python3 tools/check_regeneration.py` | Exit 0. This invokes the unchanged generator with `--content-repo git-repos/content --license-repo git-repos/license --out ../provisional-carrier --check` and six explicit `--determination MODEL=FILE` arguments. Exact argv in `logs/regeneration.log` |
| In `../provisional-carrier`, `sha256sum --check SHA256SUMS` and `sha256sum --check BINDINGS.sha256` through the runner | Every entry OK, both exit 0. `logs/checksums.log`, `logs/checksum-bindings.log` |
| `python3 tools/run_f100_provisional.py` through the runner with five seat-local repository overrides | 9/9 checks pass. `logs/f100-provisional.log` |
| In `snapshots/content`, `make check` through the runner | 314 tests attempted; failed with 4 failures and 65 errors, detailed below. Exit 2. `logs/content-check.log` |
| Focused Content unittest selection through the runner | 136 tests: 133 pass, 3 blocked by socket creation; exit 1. `logs/content-focused.log` |
| Initial focused host unittest selection, including model setup, through the runner | 194 tests; 3 failing subtests, 1 error, 13 skips; exit 1, detailed below. `logs/host-focused.log` |
| Focused host selection after exact Content metadata preparation, excluding the separately recorded model-setup path limitation | 157 tests, successful with 9 provider fixture skips; exit 0. `logs/host-focused-pinned.log` |
| Provider route suite with exact local provider source | 9 tests; 2 blocked by ancestor ownership checks, remaining cases pass, no skips. Exit 1. `logs/provider-focused.log` |
| In `snapshots/k95`, `python3 tests/run.py` with seat-local `KILIX_HOME`, after pinned state/presenter preparation | 80/80 test files pass, exit 0. `logs/k95-check-complete.log` |
| `python3 tools/run_logged.py failure-summary -- python3 tools/summarize_failures.py` | PASS; independently classifies the broader failures and verifies that the host model-setup test is unchanged from the accepted host. `logs/failure-summary.log` |

The F100 adapter replaces only the module's `CARRIER` path in memory before function defaults bind. It runs the existing AC-1, AC-2, AC-3, AC-5, AC-8, AC-9 tests and the existing served-record test. It also invokes AC-4's artifact/dictation comparison helper on the actual candidate catalog. Its ninth check proves that the actual provisional directory, with its actual carrier hash, is refused specifically because `ACCEPTANCE.json` is absent. No synthetic seats or acceptance receipt were supplied. Receipt-dependent AC-4 forgery execution, AC-6, AC-7, AC-10, AC-11, AC-12, and the positive host-gitlink guard controls require final assembly and are not claimed as passing here.

The focused Content selection covers catalog parsing, contracts, consumer selection, public catalog trust/tamper checks, speech and vision asset records, Needle records, weight absence, vendored receipt compatibility, screen presentability, and packaged conversion records. Exact module selectors are in `logs/content-focused.log`. The successful host selection covers consumer selection, SDK catalog enumeration, content applications, installer/pin delivery, provider authority, speech installers, model wizard and licence prompts, and game dispatch. Exact selectors are in `logs/host-focused-pinned.log`.

## Failures and limits

- The first two suite launch attempts failed before running tests because the seat's logging wrapper parsed its switches as executable names. That wrapper was corrected; the original invocation logs remain as `logs/content-check-harness-invocation-error.log` and `logs/k95-check-harness-invocation-error.log`. An initial binding-audit assertion also assumed a different model order; comparison with the accepted carrier established the actual unchanged order, and the corrected audit passed. Its initial log remains `logs/binding-audit-order-assumption-error.log`.
- The broad Content run's 65 errors consist of 64 `PermissionError: [Errno 1] Operation not permitted` socket-creation errors and one `OSError: AF_UNIX path too long`. The seat's long absolute scratch path caused the latter. Two failures were loopback network-guard controls whose socket connection could not run; two were Git-based packaged-record checks executed against an archive without `.git`. Adding exact candidate Git metadata resolved both Git checks in the focused run. The focused Content run's remaining three errors are the existing first-use loopback fixtures for Whisper, YOLOX, and YAMNet. These are environment limits, not successful download tests. The full Content suite is not reported as passing; the independent upstream-record `--check` was run because `make check` stopped before its pins recipe.
- The initial host error was the real provider authority test's `git rev-parse HEAD` on an extracted Content directory without Git metadata. Exact local metadata preparation resolved it, and the actual authority check passes. Its three failing subtests belong to one supplied-install test that asserts temporary receipts are outside `pwd.getpwuid(...).pw_dir`. The required seat-local TMPDIR is inside that account home, making the assertion fail before the behavior under test. The test file is byte-identical to the accepted host (`dd26069da4031979b1536b390fe96ba1ceca6c8bcfeb203925650fc69f4dded2`). Its behavior was not claimed as newly verified. Four initial skips were loopback-dependent model tests, and nine were missing optional provider-source fixtures.
- Supplying the exact provider source eliminated those provider fixture skips. Two preparation tests then refused the directory chain because this managed sandbox exposes `/` and `/home` as owned by UID 65534, while `private_chain` accepts only root or the current user. The ownership inspection is retained in `logs/provider-ancestor-audit.log`. This is an environment refusal; the guard was not patched or bypassed. Other provider cases, including real Content authority and launcher/tamper cases, passed.
- The first Kilix 95 attempt stopped at missing native state source (`logs/k95-check.log`). After state preparation, a second attempt passed 5/80 files and failed others because the frame-presenter Gitlink was still unpopulated (`logs/k95-check-pinned.log`). Preparing that exact local pinned component produced the successful 80/80 run. No remote submodule fetch was used.

## Acceptance boundary

This seat approves the reviewed carrier rebind inputs. The provisional directory has no seats and no `ACCEPTANCE.json` by design, and the candidate manifests still carry the previous assembly hashes. It is not an accepted assembled carrier yet.

Final assembly must regenerate the carrier with both fresh independent seat files, pin the actual resulting `CARRIER.json` and `ACCEPTANCE.json` SHA-256 values in both `releases/0.2.2.env` and `releases/0.2.2.requirements`, and pass the full carrier acceptance and defect suite. This record makes no runtime VM, ISO, F101/F104, or release qualification claim.
