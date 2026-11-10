# Seat A review: Plebian-OS 0.2.3 RC7 model-compliance carrier and the qwen-0.8b-no-loop-02 licence delivery

Seat: A. Date: 2026-11-09. Reviewer: this session, an independent model-compliance reviewer.

Candidate CARRIER.json sha256, as this session computed it: `42b6956b1669a1351f09e13e16cb00f827448f1c68d64c981d14e6dc56a2dfb3`.

DEFAULT-MODELS.json field "sha256", as this session read it: `e00614bf726154d09668820c061cbbcb402239a445bde666b0568d36f01528a6`.

## Eligibility

The builder session launched this pane in kilix on 2026-11-09 and wrote the brief this review follows. This session did not author the carrier, its generator, its determinations, the kilix-license qwen-0.8b-no-loop-02 record, the kilix-content catalog entry, the Kilix wizard or installer changes, the plebian-os provisioning change, the model release or its card. This session began by reading the brief and had no earlier work in this project. It made no commits. Seat A is eligible.

The review was read-only. This session cloned every repository fresh into its own work directory and changed nothing outside it. It did not read the other seat's directory, the builder's notes in the parent folder, or earlier seat records. Two checks touched the carrier's seats/ files without reading them: `sha256sum -c SHA256SUMS` hashed them, and the generator check received their paths as `--seat` arguments as the brief requires. AC-7's failure message printed the opening words of an earlier seat record's title. Nothing from it was used. This session did not commit, push, publish, write ACCEPTANCE.json, or start other agents.

Paths below are relative to the review folder `/home/pleb/storage/research/plebian-os/023-rc7-no-loop-20261109`. `work/` is `seats/a/work` inside it. A host-name-free placeholder, `$RELEASE`, stands for the download base of release tag `qwen-0.8b-no-loop-02` in the kilix-llm repository. `$EDIT_SRC` stands for the edit source repository named in the determination, at commit `4d09ba6d6a7e891dd8063974dfe81b3d78e3494f`.

## Commits and parents

Command, in each clone: `git rev-parse --verify <commit>^{commit}; git log -1 --format='%P' <commit>; git rev-parse origin/<branch>`.

- plebian-os `2a742d0e44ad26bcc008f2c9cd9464c80dfab88f`: parent `2283b1ae5470819e50129a7b3c229a7fbbedd82b`, tip of `work/0.2.3-rc7-no-loop`. Tag `v0.2.3-rc6` resolves to `2283b1ae`.
- kilix-content `b0c6f650aa6878381758905afb97087519bc0692`: parent `c8f0b0f51966925c5872c70c246434cce6784982`, branch tip.
- kilix-license `2737f321c49371c08d2b624190fda7719a13a52a`: parent `f8486ed3df562bd512b0d948494c76b7e7ae0349`, branch tip.
- kilix `58c36b2e33df8e20a3cfe3c6d99e95d20c748ca7`: parent `beb39587b42cdf89ea0c62258c9ba044d05baa1b`, branch tip.
- kilix-llm `b26cadcdf988547bb5678ec3f0ad2932a5613b1f`: parent `4267e55277de7ab3d3380a561a1f5f0d58261f18`, tip of `work/0.2.3-rc6-no-loop`. Tag `qwen-0.8b-no-loop-02` resolves to `4267e552`.
- kilix-needle `a887e2fae221272aece6b7b9aef143df8bc7ba64` and kilix-voice `1a4e63b11d0ad9c1664031e2773f5c4f5797913f` exist. kilix-bonsai `630da3cf64d28b35fb65cafd4e7c8a4ad54b8685`, which Kilix 58c36b2e's unchanged `scripts/install-kilix-bonsai.sh` installs, exists.
- The candidate also moves KILIX95_REF. That repository was not in the brief's list, so this session cloned it as well. kilix-95 `24130253f29070883713d677469c7ce1161d02c9` has parent `44525e240f9d8fa7d1b4cc0538992be46cd14952`, the RC6 pin.
- Kilix 58c36b2e moves the kilix-avatar pin from `bedd1b8977ccebdf8ef60b43bf091a33b171b6c9` to `a383f65aba6352b232e57482e48f415d2d8dffdc`. Cloning that repository failed (`fatal: could not read Username`), and its public API returns 404 for the repository and for the commit. The builder's follow-ups also say that repository is private. This session could not review that commit (known issue 2).

## Claim 1: kilix-license 2737f321

Command: `git diff --name-status f8486ed3 2737f321`. It added `src/kilix_license/noloop02.py`, `data/determinations-noloop02.json` and `.sha256`, `data/noloop02-records/qwen-0.8b-no-loop-02.json` and three texts (`2569309d…`, `395f7feb…`, `a4e74ed6…`). It modified `catalog.py` and `pyproject.toml` (they register the new record directory), `standard_policy.py`, `tools/generate_records.py` (generates and checks the new family), `CHANGELOG.md`, two existing tests and one new test. No existing record or text was modified or removed, so every earlier record is byte-identical to f8486ed3.

- `sha256sum` of the determination is `0a5c215b89593756ba049ca8dc8fd84824cedcd8ce2c44c2ece7a003457bb1e3`, equal to `determinations-noloop02.sha256`.
- Loading through `kilix_license.catalog.load_determined_records()` at 2737f321 printed: digest `f5a93c984528e50574f42f04d8d9403a217bec2c49f88b5f94980e385f7abcc0`, licence_ids `('Apache-2.0', 'CC-BY-4.0')`, `standard_policy_eligible` True, `requires_typed_agreement` False. `generate_noloop02_records()` regenerated a record with the same digest that compared equal to the committed one.
- Record fields: text_sha256 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`. One component, `weight-edit-from-lm-understand-logs`, with exception text `9ba9550ad48438d0836ddab3da480b3b69ffa0aac7b7878b5a0039e7ab429411`. Statements `modified-model` `2569309df198a85501c07065c837ecf18d48a0387208cfdb755702f3be2d9b44`, `weight-edit-attribution` `a4e74ed6c5f68677ebe95445696de6d9e2f789b5f63184d95a7a70a5f8cd962f` and `weight-edit-source-licence` `395f7febedfda6b5498ca36cfe3344d3986659ce4385dd8b03d2d75604250a8e`. No binding conditions or advisories. Decision class affirmative. Every text file hashes to its name (`sha256sum`). The Apache and CC BY texts were already present at f8486ed3.
- The owner_determination block is dated 2026-11-09 and sets `components` to `{"apache-2.0": "approved", "cc-by-4.0": "approved"}`. Its approved sentence records the Apache-2.0 record as proposed and the CC BY component under the standard policy with no typed answer, and it says itsmygithubacct is the modifier only.
- `standard_policy.py` gains exactly one ordinary-notice tuple: (`qwen-0.8b-no-loop-02`, `weight-edit-from-lm-understand-logs`, `9ba9550a…`). Every record's digest and `standard_policy_eligible` result was computed at f8486ed3 (a worktree) and at 2737f321. The output was `records 44 -> 45 added ['qwen-0.8b-no-loop-02'] removed []` and `changed digest or eligibility []`.
- `python3 -I tools/generate_records.py --check` printed `records 30 match generator (pin 3038192435db…)` and `application records 4 match generator (pin 80347a2c…)`, exit 0.
- `PYTHONPATH=src python3 -m unittest discover -s tests -t .` printed `Ran 240 tests` and `OK (skipped=2)`.

Claim 1 holds.

## Claim 2: kilix-content b0c6f650

Command: `git diff c8f0b0f5 b0c6f650 -- src/kilix_content/catalog/plebian.json`. The diff is one inserted asset object and nothing else. A JSON comparison of the two catalogs printed `assets 43 -> 44 added ['qwen-0.8b-no-loop-02'] removed []`, `changed []` and `order preserved True`. The top-level keys are equal.

- The new asset has provider `kilix-llm`, consumer schema `kilix.llm.models/v1`, mode `upstream-files`, version `qwen-0.8b-no-loop-02`, and provenance revision `4267e552…`. It fetches one file, the GGUF from `$RELEASE`, listed at 833592416 bytes with sha256 `e4d6e93eb644da62e0c5ac0b7b188b4c2cbf31f07a7dcfd42764b6236f96d8a0`. Its five notices are `LICENSE-apache-2.0.txt` (11358 bytes, cfc7749b…), `LICENSE-cc-by-4.0.txt` (18657, 9ba9550a…), `LICENSE-lm_understand-logs.txt` (1819, 395f7feb…), `modified-model.txt` (1607, 2569309d…) and `weight-edit-attribution.txt` (1229, a4e74ed6…). Those sizes and digests are the kilix-license 2737f321 text files' own. installed_bytes 833627086 equals the six file sizes summed.
- Two licence rows: `apache-2.0` (text cfc7749b…) and `cc-by-4.0` (text 9ba9550a…). Both are affirmative and both carry record_digest `f5a93c98…`. Each row names one licensor, equal to the corresponding part of the record's licensor string. Neither row names itsmygithubacct.
- `git show b0c6f650:src/kilix_content/catalog/plebian.json | sha256sum` printed `ba9f1ffaa01b32d1c31a82643a1b4c103a606aee4a8344f1b055eed6499d3426`. That is the new `_CATALOG_SHA256` in `receipt.py`. The old constant `aa5c9a01…` is c8f0b0f5's catalog digest. `tests/data/catalog_digests.txt` and `catalog_source.json` add exactly the GGUF digest (count 288 to 289).
- `src/kilix_content/model.py` gains one clause, which admits exactly this release URL for this asset id, provider, schema, mode, licence, provenance and version, in the same way as the existing kilix-female-02 clause. This mechanically follows from claim 2, because the validator otherwise refuses project-hosted files. The test edits update asset counts and exclusion lists and add the new asset to the owned-file helper.
- `tools/generate_upstream_records.py` and `tools/upstream-pins/qwen-0.8b-no-loop-02.json` add the pin and its notice paths. One comment in that file is stale (known issue 3).
- `python3 -I tools/vendored_kilix_license.py --check --repo ../kilix-license` printed `211 vendored files equal git archive 2737f321… (archive has 265 files; 54 under excluded top-level entries)`, exit 0. A separate byte comparison of every vendored file with `git show 2737f321:<path>` printed `vendored files compared 211 mismatches 0`. `third_party/kilix-license.pin` is 2737f321.
- `make pins PYTHON=python3` (that is, `generate_upstream_records.py --check`) exited 0. `tools/regenerate_catalog_digests.py --check` exited 0.
- `make test PYTHON=python3` printed `Ran 411 tests` and `FAILED (errors=1, skipped=3)`. All five `test_noloop02_asset` tests passed. The one error is `test_network_guard_coverage…test_getent_and_af_unix_are_invisible_too`, with `OSError: AF_UNIX path too long`. The socket path is built under the scratch directory, and this session's work directory is deep enough that the path passes the AF_UNIX length limit. The test file and its support are unchanged since c8f0b0f5. The same single test at c8f0b0f5, run from the same directory, failed with the same error. This comes from the environment, not from the candidate.
- The catalog's kilix-needle app source ref is still `a887e2fae221272aece6b7b9aef143df8bc7ba64` (`git grep a887e2fa b0c6f650 -- src`, catalog line 1758). The lfm2-kilix-commands asset is unchanged, with archive sha256 `ea03c42c…`, 1362204317 bytes and record digest `e4d08e2c…`.

Claim 2 holds.

## Claim 3: kilix 58c36b2e

Command: `git diff beb39587 58c36b2e`. The changed files are `third_party/kilix-content` (gitlink `c8f0b0f5` to `b0c6f650`), `config/model_wizard.py` (provider `kilix-llm` maps to `chat`, and the chat page title names the new runtime), `scripts/install-kilix-llm.sh` (new, `KILIX_LLM_REF` default `b26cadcdf988547bb5678ec3f0ad2932a5613b1f`), `scripts/install-kilix-avatar.sh` (`KILIX_AVATAR_REF` default `bedd1b89…` to `a383f65a…`), `README.md`, the CI shellcheck list, and tests. No other gitlink moved. `config/content_models.py` and `config/wizard_licenses.py` are unchanged.

- `install-kilix-llm.sh` clones the pinned commit, verifies it, initialises its vendored runtime source, checks it against the pin file, and runs that commit's `install.sh`. That `install.sh` only writes a launcher. The script compiles nothing and downloads no weights.
- With `third_party/kilix-content` at b0c6f650 (initialised from this session's clone), this session ran
  `python3 -m unittest tests.test_wizard_licenses tests.test_model_wizard tests.test_content_models tests.test_kilix_llm_installer -v`.
  It printed `Ran 112 tests` and `FAILED (failures=3, errors=2)`. It passed `test_selected_catalog_installs_the_no_loop_gguf_under_standard_policy`, the test that the GGUF is acquired through the content installer and not the system-LLM route, `test_kilix_llm_gguf_is_offered_and_installed_from_the_chat_page` and all eleven `test_kilix_llm_installer` tests. The two errors were `ModuleNotFoundError: No module named 'kilix_state'` in two speech-page wizard tests, because the Kilix state submodule was not yet initialised. After it was initialised, `tests.test_model_wizard` passed in full (`OK`). Three subtests of `test_content_models…test_from_real_install_reads_the_directory_and_fetches_nothing` failed. They assert that the temporary receipt root is not under the account's home directory, and this session's work directory is under it. The same test at beb39587 with kilix-content c8f0b0f5 failed the same three subtests in the same directory. This comes from the environment.
- The kilix-avatar pin move could not be reviewed (known issue 2).

Claim 3 holds as far as this session could test it. The kilix-avatar commit is the exception.

## Claim 4: plebian-os 2a742d0e

Command: `git diff --stat 2283b1ae 2a742d0e` lists 14 files: CHANGELOG, both provisioning scripts, `releases/0.2.3-command-model.json`, follow-ups, notes, `releases/0.2.3.env`, `releases/0.2.3.requirements`, five carrier files and `tests/test_kilix_llm_install.py`.

- A key-by-key comparison of `releases/0.2.3.env` printed changes only to PLEBIAN_OS_REF (`v0.2.3-rc6` to `v0.2.3-rc7`), KILIX_REF (to `58c36b2e…`), KILIX95_REF (to `24130253…`), KILIX_LICENSE_REF (to `2737f321…`), PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF (to `b0c6f650…`), PLEBIAN_OS_VOICE_CARRIER_SHA256 (to `42b6956b…`) and PLEBIAN_OS_VOICE_CARRIER_RECEIPT_SHA256 (to `baa01ea7c52420f3b95f95993f292b67a7c0356eb34189b4d7ab93582d8011ad`). `releases/0.2.3.requirements` has the same values for the carrier sha256, the receipt pin, KILIX_LICENSE_REF and PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF. KILIX_VOICE_REF is `1a4e63b11d0ad9c1664031e2773f5c4f5797913f` in both commits. The receipt pin equals `sha256sum` of the candidate ACCEPTANCE.json. Tag `v0.2.3-rc7` is not yet on the remote, which matches the env comment that it names the local candidate tag.
- KILIX_REF's gitlink, from `git ls-tree 58c36b2e third_party/kilix-content`, is `b0c6f650aa6878381758905afb97087519bc0692`. That equals the carrier's interface_content_ref and PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF.
- `provision/plebian-os-provision.sh` and `provision/plebian-os-update.sh` each add `install_kilix_llm`. It refuses a missing, non-executable or linked installer, runs the pinned Kilix's `scripts/install-kilix-llm.sh` as the desktop user, then runs `kilix-llm build --backend cpu`. It is called after `install_kilix_needle`. No model is fetched.
- `releases/0.2.3-command-model.json` changes only `source_pins` kilix, kilix-content and kilix-license, and the manifest revision. Its model and archive pins, including `ea03c42c…` and 1362204317, are present in both commits.
- `build/remaster-iso.sh` is unchanged: its blob is `da4dc759fa8c398baeecf85322e0987330684831` at both commits.
- kilix-95 24130253 changes `applications.py`, `README.md`, the CI Kilix pin and one test. With the new asset installed and kilix-llm on PATH, it adds two desktop entries. Both launch kilix-llm or kilix-avatar on the wizard-installed file (`--model <content asset path>/qwen-0.8b-no-loop-02.gguf` or `--model-file`). Neither fetches anything. `KILIX_HOME=work/kilix python3 tests/run.py test_installed_applications` printed `PASS test_installed_applications.py` and `1/1 passed`.
- `python3 -m unittest tests.test_kilix_llm_install -v` printed `Ran 5 tests` and `OK`.
- The carrier's model list is unchanged (claim 5), so the new model is not carried.

Claim 4 holds.

## Claim 5 and the carried records

- `sha256sum` printed `42b6956b1669a1351f09e13e16cb00f827448f1c68d64c981d14e6dc56a2dfb3` for `seat-inputs/candidate-carrier/CARRIER.json` and `4fdbffce1f96882bbdc16724b3472895e10296ec603d1441249ff3a2e7470ebc` for `seat-inputs/reviewed-carrier/CARRIER.json`.
- Both seat-input copies were compared file by file with `git show <commit>:releases/0.2.3-model-compliance/<file>`, leaving out seats/ and ACCEPTANCE.json. Each copy has 69 files, all byte-identical to 2a742d0e and to 2283b1ae respectively.
- `diff -rq candidate-carrier reviewed-carrier -x seats -x ACCEPTANCE.json` lists only BINDINGS.sha256, CARRIER.env, CARRIER.json and SHA256SUMS. A flattened JSON comparison of the two CARRIER.json files printed only `bindings_sha256` (`3520a382…` to `21de7caf4a588b5184d930942485183d9a6f6b93ac0a8f2eee8193fd860b23a9`), `interface_content_ref` (c8f0b0f5 to b0c6f650) and `interface_licence_ref` (f8486ed3 to 2737f321), with equal key sets. CARRIER.env differs in the same two ref lines. BINDINGS.sha256 differs only in the CARRIER.env line (`ad47a60d…`). SHA256SUMS differs only in the four lines for ACCEPTANCE.json, BINDINGS.sha256, CARRIER.env and CARRIER.json. `sha256sum -c SHA256SUMS` in the candidate printed OK for every entry.
- `sha256sum PLAYALONG-MODELS.json` printed `8b7f149630fa55d606e2ff01cbcd7c168b41c7febcc4eb8d6603c66d809a9c28` in both carriers. DEFAULT-MODELS.json's "sha256" field reads `e00614bf726154d09668820c061cbbcb402239a445bde666b0568d36f01528a6` in both. COMMAND-MODEL.json is `c3defd9d…` in both.
- Each carried `LICENCE-RECORD.json` was loaded with kilix-license 2737f321's `LicenseRecord.from_bytes`, and its digest was compared with CARRIER.env, with the 2737f321 record index, and with the bytes of the same record file at f8486ed3. Every model printed match=True, lib_digest_match=True, carrier_bytes==lib_bytes=True, lib_bytes==f8486ed3=True and dir_identical_to_reviewed=True: small-en-us `651e3930…`, lgraph-en-us `3de52a5b…`, vibevoice-asr-bitnet `cc29b19c…`, whisper-small-en `3e64fa1b…`, whisper-medium-en `c33e44c1…`, whistle `9fc99f4c…`, kilix-diarization-cpu `e1feb5ca…`, and lfm2-kilix-commands `e4d08e2c53ab514e1e2ca2a812c64895519487d707c441703978bd0f245b5016`. Every model directory (ARTIFACT.json, DELIVERY, LICENCE-RECORD.json, NOTICE), licence-texts/ and determinations/ is byte-identical to the seat-approved carrier.
- The command-archive pins in CARRIER.env are unchanged, at `ea03c42ce0f36d12bca1844c558c0fcaeb442887e55e1e7b76ccb3ed632c3a85` and 1362204317 bytes. This session did not download that archive again.

Claim 5 holds.

## Generator check

The command ran from `work/plebian-os` at 2a742d0e, against `work/kilix-content` at b0c6f650 and `work/kilix-license` at 2737f321, on a writable copy `work/carrier-copy` of the candidate carrier:

`python3 -I build/generate-model-compliance.py --content-repo work/kilix-content --license-repo work/kilix-license --determination kilix-diarization-cpu=…/0.2.1-F104-CAMPP-WEIGHT-LICENCE.md --determination lfm2-kilix-commands=…/command-model-determination.json --determination lgraph-en-us=…/OWNER-DETERMINATION-lgraph-en-us.md --determination small-en-us=…/OWNER-DETERMINATION-small-en-us-BUNDLED-20261105.md --determination vibevoice-asr-bitnet=…/OWNER-DETERMINATION-vibevoice-asr-bitnet.md --determination vibevoice-asr-bitnet=…/OWNER-RULING-C2-AMENDMENT-2026-09-29.md --determination vibevoice-asr-bitnet=…/OWNER-RULING-J1-J2-2026-09-25.md --determination whisper-medium-en=…/OWNER-DETERMINATION-whisper-medium-en.md --determination whisper-medium-en=…/OWNER-DISTRIBUTION-whisper-medium-en-2026-11-08.md --determination whisper-small-en=…/OWNER-DETERMINATION-whisper-small-en.md --determination whistle=…/OWNER-RC6-WHISTLE-BUNDLED-20261105.md --seat …/seats/SEAT-A-PLAYALONG-DEFAULTS-CARRIER-R5-20261109.md --seat …/seats/SEAT-B-PLAYALONG-DEFAULTS-CARRIER-R5-20261109.md --out work/carrier-copy --check`

Each `…` is `work/carrier-copy/determinations/<model>` or `work/carrier-copy`, and the arguments are in sorted path order. The command printed nothing and exited 0. As a negative control, a second copy with interface_licence_ref set back to f8486ed3 printed `carrier differs: CARRIER.env` and exited 1. After the run, `work/carrier-copy` still equalled the input (`diff -r`).

## Carrier acceptance tests

From `work/plebian-os` at 2a742d0e, PLEBIAN_OS_KILIX_REPO, PLEBIAN_OS_KILIX_CONTENT_REPO, PLEBIAN_OS_KILIX_LICENSE_REPO, PLEBIAN_OS_KILIX_VOICE_REPO, PLEBIAN_OS_KILIX_NEEDLE_REPO, PLEBIAN_OS_NEEDLE_REPO and PLEBIAN_OS_KILIX_BONSAI_REPO pointed at this session's clones, at 58c36b2e, b0c6f650, 2737f321, 1a4e63b1, a887e2fa, a887e2fa and 630da3cf. The command was `python3 -m unittest tests.test_model_compliance_carrier -v`. It printed `Ran 17 tests` and `FAILED (failures=1)`. These passed: AC-1 `test_carrier_regenerates_byte_identically`, AC-2 `test_carrier_env_is_a_faithful_projection_of_carrier_json`, AC-3 `test_carrier_licence_records_match_kilix_license`, AC-4 `test_carrier_artifact_records_match_kilix_content`, `test_carried_records_are_the_ones_the_image_serves`, `test_command_model_records_needle_serves_are_the_carried_ones`, AC-5 `test_carrier_covers_every_advertised_model`, AC-6 `test_acceptance_receipt_names_the_real_determinations`, `test_whistle_authorization_requires_the_real_request_and_upstream_evidence`, AC-8 `test_delivery_statement_is_true_of_this_image`, AC-9 `test_guard_refuses_without_a_carrier`, AC-10 `test_guard_accepts_the_verified_carrier`, AC-11 `test_guard_refuses_every_planted_carrier_defect`, both content-gitlink guard tests, and AC-12 `test_release_requirements_pin_the_carrier`. The only failure was AC-7 `test_acceptance_receipt_names_two_independent_seats`, with `AssertionError: '42b6956b…' not found in` the attached RC6 seat record. The brief expects that failure until the receipt names this review.

## The release

`curl` against the release API listed six assets: `edit-record.json`, `LICENSE`, `LICENSE-lm_understand-logs.txt`, `qwen-0.8b-no-loop-02.gguf` (833592416), `README.md` and `SHA256SUMS`. The release targets `4267e552…` and is not a draft. This session downloaded all six into `work/release` with `curl -sSfL -o <name> $RELEASE/<name>`. `sha256sum -c SHA256SUMS` printed `qwen-0.8b-no-loop-02.gguf: OK`, `README.md: OK`, `LICENSE: OK`, `LICENSE-lm_understand-logs.txt: OK` and `edit-record.json: OK`, exit 0. `stat -c %s` printed `833592416`, and `sha256sum qwen-0.8b-no-loop-02.gguf` printed `e4d6e93eb644da62e0c5ac0b7b188b4c2cbf31f07a7dcfd42764b6236f96d8a0`. The release LICENSE hashes to `bbedc3fd…`, the determination's upstream_licence_file_sha256, and `cmp` shows it is identical to the upstream base model's LICENSE at revision `2fc06364…`, which this session fetched separately.

A short header reader (`work/scripts/gguf_meta.py`) printed `general.license = apache-2.0`, a licence link, and a `general.description` naming the modification, the edit's authors and CC BY 4.0. The modified-model notice quotes that description exactly.

## kilix-llm b26cadcd

`models.MODELS['qwen-0.8b-no-loop-02']` was compared with the content asset. It printed `url == content url True`, size 833592416 in both, and sha256 `e4d6e93e…` in both. `KILIX_LLM_REF` in Kilix 58c36b2e's `scripts/install-kilix-llm.sh` is `b26cadcdf988547bb5678ec3f0ad2932a5613b1f`. `PYTHONPATH=src python3 -m unittest discover -s tests` printed `Ran 67 tests` and `FAILED (failures=2, skipped=4)`. Both failures report that the vendored runtime source is missing, because this session did not initialise that submodule. Neither concerns the model entry.

## Licence delivery against the owner's decisions

- Licensors. The record's licensor string has two parts joined by "; " (sha256 of the string `2d6d534845bcc75ee4741f065bbb38039b7ec92a22b534579e60718afc1f2f6f`). The first part is the upstream licensor named in the owner's licence decision, with its model family. The second is the edit source's authors as they name themselves in its LICENSE copyright line. The string does not contain itsmygithubacct. itsmygithubacct appears only as `authority.modifier` in the determination, as "Modified by" in the modified-model notice, as the hosting project in the asset's provenance, and as the publisher in kilix-llm. It is never a licensor. This matches "Approve as proposed" and "list itsmygithubacct only as the modifier".
- Standard policy. `standard_policy_eligible` is True and `requires_typed_agreement` is False, through kilix-license 2737f321 and through the copy Kilix 58c36b2e vendors via kilix-content b0c6f650. This matches "Approve, no extra prompt".
- Wizard. The Kilix test named in the brief passed (claim 3), and so did this session's own run (next section).
- Notices. The five catalog notice digests and sizes are those of the record's text, component and statements, and kilix-content's `test_notices_are_the_record_texts` passed. This session's own install also found the installed bytes identical (next section).

## This session's own wizard run

The script is `work/scripts/own_run.py`. It imports Kilix 58c36b2e's `config/content_models.py` and `config/wizard_licenses.py`, whose kilix_content and vendored kilix_license come from `third_party/kilix-content` at b0c6f650. It calls `wizard_licenses.consent_and_install(['qwen-0.8b-no-loop-02'], input_fn=no_question)`, where `no_question` records any prompt and aborts the run. The catalog, licence authority, receipt store, installer and download are real. Only the receipt store, the wizard state root and the apps root are redirected into `work/tmp/own-run`, and HOME and the XDG directories point there too. The installer downloaded the GGUF from `$RELEASE` itself. The command was `python3 work/scripts/own_run.py work/kilix work/tmp/own-run work/kilix-license`, and it printed:

- `result ({'qwen-0.8b-no-loop-02'}, set()) questions []`. The model was installed, and no question was asked.
- `receipts 1`. The receipt has record_digest `f5a93c984528e50574f42f04d8d9403a217bec2c49f88b5f94980e385f7abcc0`, decision `accept`, licence text digest `cfc7749b…` and no binding-condition digests. Its manifest digest `ff79e3ed71a7ca13b10d374648e528d4ac119704f5ee02a92f2a2eff757aaaa2` equals the catalog asset's. Its context records the component exception `9ba9550a…`, catalogue digest `ba9f1ffa…`, and statement digests `modified-model`, `weight-edit-attribution`, `weight-edit-source-licence` and `standard-license-policy-v1`. The policy digest is `354bb6c1d0691fb66b606edc28b72145b00687a9300b883737df189d76ff6681`, equal to `standard_policy.POLICY_SHA256`. The acceptance capture mode is `no-tty`, and no typed answer is recorded.
- The licence-documents index lists `licence:apache-2.0`, `licence:cc-by-4.0`, the component and the three statements.
- Installed files: the GGUF at 833592416 bytes with sha256 `e4d6e93eb644da62e0c5ac0b7b188b4c2cbf31f07a7dcfd42764b6236f96d8a0`, and five notices. Each notice is byte-identical to the kilix-license 2737f321 text of the same digest: `LICENSE-apache-2.0.txt` 11358, `LICENSE-cc-by-4.0.txt` 18657, `LICENSE-lm_understand-logs.txt` 1819, `modified-model.txt` 1607 and `weight-edit-attribution.txt` 1229.

So the wizard's consent batch installs the model under the standard policy with no typed question, and it delivers exactly the record's five texts.

## Licence conditions

Apache-2.0 section 4.

- (a) A copy of the licence. `LICENSE-apache-2.0.txt` is byte-identical to the canonical Apache-2.0 text from its steward (sha256 `cfc7749b…`, fetched separately). The upstream LICENSE is the same text with its appendix boilerplate filled in as the upstream copyright line: a word-level diff shows that is the only difference. The release also publishes the upstream LICENSE itself. Met.
- (b) Prominent notice of modification. `modified-model.txt` says this is a modified version, who modified it, which two tensors changed and what stayed byte-identical. The GGUF's own `general.description` says it is modified and how. Met.
- (c) Retained notices. The upstream copyright line is kept word for word in `modified-model.txt`, which quotes the model card's statement that the base model is copyright of its licensor under Apache-2.0. The upstream repository at `2fc06364…` holds no NOTICE file (its file list has LICENSE, README.md and model and tokenizer files only), so (d) does not apply. Met.

CC BY 4.0 section 3(a).

- (1)(A)(i) Creator identification. `weight-edit-attribution.txt` names the authors of the paper and the work, as the edit source's own LICENSE names them. The source README makes no other attribution request. Met.
- (1)(A)(ii) Copyright notice. The edit source's LICENSE file, with its copyright line, ships unchanged (395f7feb…, identical to `$EDIT_SRC/LICENSE`). Met.
- (1)(A)(iii) and (iv) Notice referring to the licence and to its disclaimer, and (1)(C) licence text or link. The attribution names CC BY 4.0 with a link, and the full legal code ships as `LICENSE-cc-by-4.0.txt`. That file is byte-identical to the steward's canonical plain-text legal code (sha256 `9ba9550a…`, fetched separately) and includes the disclaimer. Met.
- (1)(A)(v) Link to the material. The attribution gives the repository, the path `exp8_math/runs/p50c/edit` and commit `4d09ba6d…`. That path holds `edit.npz` and `manifest.json`, data that the source LICENSE places under CC BY 4.0, not under its MIT script terms. So the CC BY classification is right. Met.
- (1)(B) Indication of changes. It lists three changes: scaled to one third (alpha 2 of 6), applied to the Q8_0 conversion and quantized, and packaged with new metadata. Met.
- No implied endorsement (section 2(a)(6)). It says "The authors have not reviewed or endorsed this model." Met.

The attribution and modification paragraphs the notices quote are verbatim in the release README (a whitespace-normalised containment check printed True for both).

The delivered notices meet both licences' conditions.

## Defects found (known issues)

1. kilix-llm's `pull` route installs the model without its notices or a receipt. kilix-llm b26cadcd catalogues `qwen-0.8b-no-loop-02`, and its README documents `kilix-llm pull --model-id qwen-0.8b-no-loop-02`. `cmd_pull` fetches only the GGUF into kilix-llm's own model path. It installs none of the five notices and writes no licence receipt. Plebian-OS 2a742d0e now puts that launcher on every installation's PATH. The bytes are the same release file, the release publishes the upstream LICENSE, the card and the edit source's LICENSE beside it, and the GGUF metadata names Apache-2.0 and the CC BY edit. So the terms this route points to are the owner's, and this session does not judge it a licence breach. It is still a second acquisition route that skips the wizard's notice delivery. The kilix-95 entries only open the wizard-installed file, so a pulled copy does not create them.
2. The kilix-avatar commit was not reviewed. Kilix 58c36b2e moves `KILIX_AVATAR_REF` to `a383f65aba6352b232e57482e48f415d2d8dffdc`, and the notes and CHANGELOG list it as part of this change. Its repository is not public, so this session could not read the commit. The pin is as claimed, and the kilix-95 avatar entry passes it the wizard-installed file. But this session cannot say what kilix-avatar does at that commit, including whether it fetches anything. This verdict does not cover that commit.
3. A stale comment in kilix-content b0c6f650. `tools/generate_upstream_records.py` line 168 says "The owner has not yet signed off this component". The determination it cites records the owner's approval of 2026-11-09. Only the comment is wrong. The generated rows are affirmative, and `--check` passes.

Observation, not counted as a defect: the RC7 section of `releases/0.2.3-followups.md` asks for the kilix-content, kilix-license, Kilix and Kilix 95 commits to be published. All four were public when this session cloned them.

No required identity, record, determination, delivery statement, pin or receipt gate mismatched. AC-7 fails only as the brief expects. The wizard route serves exactly the owner-approved record, and the carried records are unchanged. The delivered notices meet Apache-2.0 section 4 and CC BY 4.0 section 3(a).

VERDICT: ship with known issues
