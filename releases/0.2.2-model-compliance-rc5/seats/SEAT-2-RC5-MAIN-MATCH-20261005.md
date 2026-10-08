# Seat 2 independent RC5 main-match carrier review — 2026-10-05
VERDICT: ship

I did not author the reviewed changes, the generator, or the provisional carrier.

This verdict approves the model-compliance carrier rebind for the exact candidate inputs below, subject to the final assembly boundary stated at the end. I independently inspected the selected objects and byte differences and ran checks from copies inside this seat. I did not read or coordinate with the other seat, use earlier seat records as approval, modify the supplied repositories or provisional directory, or use a remote network service.

The reviewed base and candidate objects were:

| Component | Base | Candidate |
| --- | --- | --- |
| Plebian-OS | `bfd82ad25aa3810b03cdaa6a712027b6d659c0b5` | `4588779fbd9f9fbe99ab33ad0727dee2558c47bb` plus the supplied manifest patch |
| Kilix host | `2e1638e8392f88160b2a6343a8672c32c98fb188` | `798db9c92fdb4b372b985c17ce5a28164e4b9448` |
| Kilix 95 | `14b466a998074d151d2e63dee6b0d8f2763034d0` | `13a501cc37a32342b3047c4ce09741827af2d1a6` |
| Pleb | `4c08e6aff6e8a0c216a5d8c4fc3bca1042d66236` | `4cf84b44ee5fb7c43eff0f288a62829bb959cdb4` |
| Content | `ce6c0c63a852b10c6ca2b2f7ed8087934d75f4d0` | `ad620c1429d825230e1c337a20f8a9682ff060d4` |
| Needle | `7de641763c403f8c54873ef4d044277c946d4445` | `53e881ef7bee42964882d40ad51713f2526b7cea` |
| TUI utils | `8b461045715f176218c57b17ff16ccfd756aace1` | Same |
| Licence | `ca8a0f479893ab9c8cd6cadc2716c474aaad2820` | Same |

The OS, host, Kilix 95, Pleb, Content and Needle objects came from the read-only repositories under `/home/pleb/gpu_terminal/worktrees/rc5-main-match-20261005/`; the Licence object came from `/home/pleb/gpu_terminal/kilix-modules/kilix-license`. The base carrier was extracted from OS `bfd82ad`. The provisional input was `../provisional-carrier`, with `CARRIER.json` SHA-256 `276c8bb766b6b7b3ef8f31d6ddba4376d3ec4fb79686142495a133160a6e5caf`. The six supplied files under `../determinations` were also reviewed and compared with the carrier. The SHA-256 of `../os-candidate-pins.patch` was `9c2ffa7ad9be0343a20ff85d41212827b9395b077292b02be54b41133befeff5`; it was applied only to `src/os` inside this seat. Its carrier and receipt hash pins remain at the accepted base, as the brief states.

For the integration history, the following exact objects were resolved and confirmed as ancestors of their stated candidates (`logs/provenance.log`):

- OS desktop merge `c4fbfb5a3ea6bbe4472b401e6773fea530aeabd2` and review fix `c788a3d9709585870ad3cc015b4ef1aad94c47be`, followed by candidate `4588779fbd9f9fbe99ab33ad0727dee2558c47bb`.
- Host main input `44740f4cc1e964ed0530026105b07d5afce9730c`, desktop input `784adf956e4214ddbc5920d0bfe2c4574d26e85c`, multiplexer-pin input `bb436d92d562db2839aafedfb6a006ec9c57527f`, and the accepted host base.
- Content main input `34ef86a57789f5b065f34cf0203bd43001e61396` and the accepted Content base.
- Needle main input `ecf5110d2229f25806b88b386d122ca842eaa2f8` and the accepted Needle base.
- Amp `92f252b3cf64ad85c252b7e0ab00c6325ea8442f` to `e5ce674e40212b3ca410e430d922926fff770094`, a strict descendant with two commits. The complete diff is retained in `logs/amp-diff.patch`.

The unchanged voice selection inspected by the F100 delivery check was `a12be47e289ca03fccd46840276add1833df5760`; its selected Bonsai route was `630da3cf64d28b35fb65cafd4e7c8a4ad54b8685`. Additional provider tests used an extracted copy of their selected provider `e255d4af90eb3593c880e10894f2a128aa28eec7`, without fetching packages or weights.

**Selection and Content findings.** Read-only `git rev-parse <candidate>:third_party/kilix-content` returned `ad620c1429d825230e1c337a20f8a9682ff060d4`, exactly the carrier interface and host `config/kilix_sdk/qwen_provider.py` `CONTENT_REF`. The host TUI installer default, Content's TUI package selection and Needle's TUI gitlink all equal `8b461045715f176218c57b17ff16ccfd756aace1`. Content selects Needle `53e881ef7bee42964882d40ad51713f2526b7cea`. Needle main's older TUI gitlink `75ce46b57ea45262fd56f87766b24ed6100b0449` was replaced by the accepted Help Search selection; the candidate preserves the accepted base's `8b461045` gitlink. The Needle diff from the accepted base adds transcript replay, its pinned replay dependency, documentation and tests; it does not change the TUI gitlink or model authority.

Content's complete base-to-candidate diff contains only four files: `CHANGELOG.md`, `src/kilix_content/catalog/plebian.json`, `src/kilix_content/receipt.py`, and the documentation/literal changes in `tests/test_consumer_selection.py`. The catalog changes exactly the Needle and Amp source refs; their remaining entry fields and every other catalog field are equal. The transcript-replay Needle line is a changelog update inherited from Content main. The TUI ref itself is unchanged from the accepted Content base, despite the supplied release-notes paragraph describing changes to TUI selections.

All 32 asset records are unchanged. Both copies of the asset/v3 schema are byte-identical to base, SHA-256 `07cb268fb8aa0c6131d6c230af3f7ede094270a1214efd3ae5deb407d6a8e870`. The catalog bytes and production trust root agree at SHA-256 `aa7034c9cab85a2c3edf12b0dbd4764138dd4529d068548dfe8cee7d71629dd7`; `tools/generate_upstream_records.py --check` returned 0. There is no new model, weight population, asset identity, licence record or owner determination.

Amp's two commits change `LIVE-FORMAT.md`, `src/encodec_source.c` and `tests/native_live.c`. They select the decoder epoch-start profile from the live header and refuse unsupported or inconsistent markers, with additional C5 coverage. They do not change model acquisition, installed-asset admission, receipt checks, model populations, licence texts or build selection (`make all ENCODEC=1`). Installed admission still precedes model loading. The Amp move does not introduce a model delivery route or new licence obligation. This is a source and record assessment, not a claim that native live-audio tests were executed here.

**Carrier findings.** The provisional directory contains 37 files. Relative to the accepted base, precisely four common files change: `CARRIER.json`, `CARRIER.env`, `BINDINGS.sha256` and `SHA256SUMS`. The provisional directory omits `ACCEPTANCE.json` and the two old seat files by design. I did not use their contents as evidence of approval. All other 33 files are byte-identical, including every model ARTIFACT, LICENCE-RECORD, NOTICE and DELIVERY file, every licence text and all six owner determination files.

Only `interface_content_ref` and the consequential `bindings_sha256` differ in `CARRIER.json`. The complete `models` mapping, advertised order (`small-en-us`, `lgraph-en-us`, `vibevoice-asr-bitnet`, `whisper-small-en`), runnability, dictation selection, download sizes and digests, installed manifest digests, voice ref, licence pin and speech-library URL/digest remain identical. In particular, dictation retains SHA-256 `30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498`, and the speech wheel retains `25e025093c4399d7278f543568ed8cc5460ac3a4bf48c23673ace1e25d26619f`.

The generator is byte-identical to the base generator, SHA-256 `aa79df818f82d97f996202a5ec7bb07256989c8e1a9843195591ec964fa40d27`. Regenerating from the exact Content/Licence pins and unchanged determinations with `--check` returned 0, comparing the entire file mapping and bytes. `sha256sum --strict -c SHA256SUMS` verified all 36 listed files; the corresponding check of `BINDINGS.sha256` verified all 34 listed files. The new bindings digest is `3c2fafbe2b63969b6f46fa61e13e6f386b91d2dadc0edad21538d3d2007ba965`.

**Commands, checks and results.** Exact revision extraction used `git -C <repo> archive <sha> | tar -x -C <seat-copy>`; subsequent checks needing Git metadata used local `git clone --shared --no-checkout <repo> <seat-copy>` followed by detached checkout of the specified object. These commands never created worktrees or modified the source repositories. Extraction, diffs and provenance are retained under `logs/`.

Every suite was launched through `run_sandbox.py`, which removed inherited stack variables and set HOME, TMPDIR and XDG paths inside this seat. Its final form strips the entire `KILIX`, `GPU_TERMINAL`, `KITTY` and `PLEB` families, plus XDG and exported shell functions, before adding explicit test-local overrides. Logs record each command, directory, isolated paths, overrides and exit code. Content's Makefile adds its own scratch environment beneath the seat TMPDIR and loads its network guard. The F100 adapter preserves the isolated paths in the guard's otherwise minimal child environment.

| Check or command | Result and log |
| --- | --- |
| `python3 run_sandbox.py evidence . python3 review_evidence.py` | All selection, asset/schema, byte-comparison and digest assertions pass; `logs/evidence.log` |
| Sandboxed `python3 tools/generate_upstream_records.py --check` in candidate Content | Exit 0; `logs/content-pins.log` |
| `python3 run_sandbox.py regeneration . python3 regenerate_check.py` | Generator `--check`, exact repositories and all six determination arguments: exit 0; `logs/regeneration.log` |
| Sandboxed `sha256sum --strict -c SHA256SUMS` and `-c BINDINGS.sha256` in provisional directory | Both exit 0; `logs/provisional-sha256.log`, `logs/provisional-bindings.log` |
| `python3 run_sandbox.py f100-provisional . python3 check_provisional.py` | 9 tests pass; `logs/f100-provisional.log` |
| `python3 run_sandbox.py content-focused src/content-git python3 ../../focused_content.py` | 91 tests pass, no skips; `logs/content-focused.log` |
| Host `unittest discover -s tests -p test_content_runtime.py -v` | 13 pass |
| Host `test_sdk_content_enumeration.py` | 24 pass |
| Host `test_content_app.py` | 10 pass |
| Host `test_model_wizard.py` | 17 pass |
| Host `test_wizard_licenses.py` | 6 pass |
| Host `test_voice_installer.py` | 45 pass |
| Host `test_tui_provider.py` | 11 pass |
| Host `test_kilix_amp_installer.py` | 6 pass |
| OS `test_voice_acceptance.py` | 6 pass |
| OS `test_dependency_manifest.py` | 43 pass |
| OS `test_portals_config.py`, after supplying the selected Pleb Git checkout | 8 pass, no skips; `logs/os-portals-git.log` |

The host and OS rows use the same sandbox wrapper and unittest-discovery command form; their individual logs are `logs/host-test_<name>.log` and `logs/os-<name>.log`, with complete commands. The 91 focused Content checks explicitly load consumer selection, contracts, Vosk and other model record checks, catalog-wide EnCodec admission and planted-defect checks, packaged/converter record and generator checks, weight hygiene, public catalog validation and vendored receipt compatibility. Their class list is in `focused_content.py` and its log.

The F100 adapter redirects the existing test module's carrier path in memory before definitions/defaults are evaluated. It executes AC-1, AC-2, AC-3, AC-5, AC-8, AC-9 and the served-records check unchanged. It also invokes the existing AC-4 artifact comparison helper against the pinned catalog, and checks the provisional guard's expected refusal. The guard returned 1 with `ACCEPTANCE.json is missing or not a regular file`, followed by the exact F100 release refusal. No accepted receipt or seat evidence was synthesized. Full AC-4's receipt-dependent forgery arm, AC-6, AC-7, AC-10, AC-11, AC-12 and the receipt-dependent host-gitlink attacks require final assembly and are not claimed as passing here.

**Failures and limitations.** These were retained and investigated, not reported as suite passes:

- Full candidate and base Content `make check` each run 314 tests. Archive-only copies initially produced 4 failures and 65 errors apiece. Two failures require a real Git checkout (`git grep HEAD` and its intentional invalid-ref control). Retrying both exact revisions in local shared clones removed those two failures. Each then had exactly 2 failures and 65 errors: 64 socket `PermissionError: [Errno 1] Operation not permitted` errors, one `AF_UNIX path too long` error, and two network-guard coverage assertions whose expected socket logging cannot occur under these restrictions. Failed test identities match exactly between base and candidate. Logs: `content-check.log`, `content-base-check.log`, `content-git-check.log`, `content-base-git-check.log` and `failure-comparison.log`. The Makefile stops before its final pins recipe when the broad suite fails; the pins check was run separately and passed.
- Host `test_content_models.py` runs 37 tests with 3 failing subtests of one test and 4 loopback-related skips. The three subtests assert that scratch receipt paths are outside the account's real home, while this required seat resides under `/home/pleb`. The same three failures and four skips occur at the accepted host/Content base. Logs: `host-model-records.log`, `base-host-model-records.log`.
- Host `test_voice_cli.py` runs 22 tests with 3 errors from Unix socket path length. The exact failed test identities reproduce at base. Logs: `host-test_voice_cli.log`, `base-host-voice-cli.log`.
- Host provider-route tests initially had one error because the archived Content copy lacked Git metadata, plus 9 skipped subtests requiring a provider source. Supplying the exact Content Git checkout made the authority check pass (9 tests, 9 skipped subtests). Supplying the selected provider source then exercised all subtests: 9 tests with 2 errors in preparation-failure checks, reproduced identically at base. The directory safety guard refuses foreign-owned ancestors of this mandated workspace: `/` and `/home` appear with UID 65534 in this sandbox, whereas the guard requires root or the effective user. Directory owner/mode evidence is in `logs/path-constraints.log`. I did not weaken that guard or modify ancestor permissions. Logs: `host-test_qwen_provider_route.log`, `host-provider-git.log`, `host-provider-complete.log`, `base-host-provider-complete.log`.
- The initial OS portal run skipped its selected-Pleb Git comparison. Supplying a local exact Pleb checkout removed the skip; all 8 tests then passed.
- Two review-helper setup errors were corrected: the first catalog assertion used `entries` instead of the actual `content` key, and the first OS ancestry listing accidentally chose `c788a3d` as its endpoint. The corrected assertions and all required ancestry checks pass. Initial diagnostics remain in `logs/evidence-initial-error.log` and `logs/provenance-initial-endpoint-error.log`. Early file discovery also tried absent host `Makefile`/`tests/run.py` and Content `.gitmodules`; the actual runners and vendored source layout were subsequently inspected.

These restrictions prevent a claim that all broader component tests pass in this seat. The unchanged failing tests, identical base/candidate failure inventories and direct byte/record evidence support shipping this carrier rebind. No model-compliance regression was found.

Kilix 95's `.github/workflows/test.yml` `KILIX_COMMIT` equals `798db9c92fdb4b372b985c17ce5a28164e4b9448`. I did not run its optional `tests/run.py` suite. Desktop completion, including capture, portals, clipboard, notifications and capture dependency provisioning, was reviewed only for effects on this carrier, model delivery and licence obligations; its broader implementation has separate code review. The generator, model-free provisioning policy and receipt-gated delivery remain intact. Dependency and portal transaction checks above support that limited assessment.

Local `refs/heads/main` are older ancestors of the supplied candidates where present, and are absent in the supplied Pleb and Kilix 95 repositories. This review establishes exact candidate objects and integration ancestry, not completed main promotion or remote branch state. `logs/main-selection-detail.log` records that distinction. Any main-match publication must promote the intended candidates before claiming branch equality; this seat does not authorize a different SHA by its branch name.

**Acceptance boundary.** Final assembly must regenerate the carrier with both fresh independent seat files, pin the actual `CARRIER.json` and `ACCEPTANCE.json` SHA-256 hashes in both `releases/0.2.2.env` and `releases/0.2.2.requirements`, and pass the full carrier acceptance and defect suite. This provisional review is not that final receipt, and the accepted base hashes currently left in the manifest patch do not complete the rebind. I make no runtime VM, ISO, F101/F104 or release qualification claim.
