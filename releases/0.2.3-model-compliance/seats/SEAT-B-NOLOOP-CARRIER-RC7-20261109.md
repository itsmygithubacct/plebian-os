# Seat B review: model-compliance carrier for the 0.2.3 RC7 candidate

Seat: B. This session. Date: 2026-11-09. This record reviews the Plebian-OS 0.2.3 RC7 model-compliance carrier and the licence delivery of the optional model qwen-0.8b-no-loop-02.

Candidate CARRIER.json sha256, as this session computed it: `42b6956b1669a1351f09e13e16cb00f827448f1c68d64c981d14e6dc56a2dfb3`.

DEFAULT-MODELS.json field "sha256", as this session read it in the candidate carrier: `e00614bf726154d09668820c061cbbcb402239a445bde666b0568d36f01528a6`.

## Eligibility

The builder session launched this pane in kilix on 2026-11-09 and wrote the brief. This session recorded that before writing.

This session did not author the carrier, its generator, its determinations, the kilix-license qwen-0.8b-no-loop-02 record, the kilix-content catalog entry, the Kilix wizard or installer changes, the plebian-os provisioning change, the model release, or its card. This session confirmed that before writing. The work directory was empty when this session started. This session has made no commit in any of those repositories. It wrote only under its own work directory and this file. The review was read-only toward the carriers and the source commits. This session did not commit, push, publish, write ACCEPTANCE.json, or start other agents.

## Required identities

`sha256sum` of the two CARRIER.json files printed:

```
42b6956b1669a1351f09e13e16cb00f827448f1c68d64c981d14e6dc56a2dfb3  candidate CARRIER.json
4fdbffce1f96882bbdc16724b3472895e10296ec603d1441249ff3a2e7470ebc  seat-approved CARRIER.json
```

Those are the required candidate and last seat-approved identities.

`sha256sum` of both PLAYALONG-MODELS.json files printed `8b7f149630fa55d606e2ff01cbcd7c168b41c7febcc4eb8d6603c66d809a9c28`. The two files are byte-identical.

A JSON read of both DEFAULT-MODELS.json files printed field `sha256` `e00614bf726154d09668820c061cbbcb402239a445bde666b0568d36f01528a6`. The two files have the same file sha256, `90ee0d6448ed95a88a51b359e40567ba805d0b57ef43a7be8bf3fd5c3495a0f0`.

In both CARRIER.json files, lfm2-kilix-commands has licence record digest `e4d08e2c53ab514e1e2ca2a812c64895519487d707c441703978bd0f245b5016`, archive sha256 `ea03c42ce0f36d12bca1844c558c0fcaeb442887e55e1e7b76ccb3ed632c3a85`, and archive size 1362204317. This session did not download that archive. The pins are unchanged.

Loading qwen-0.8b-no-loop-02 through kilix-license 2737f321 printed digest `f5a93c984528e50574f42f04d8d9403a217bec2c49f88b5f94980e385f7abcc0`.

## Claim 5, the carrier

`diff -rq`, excluding `seats` and `ACCEPTANCE.json`, printed differences only in BINDINGS.sha256, CARRIER.env, CARRIER.json, and SHA256SUMS. A byte compare of the other 65 files printed no changes. The model set is the same eight carried models. qwen-0.8b-no-loop-02 is absent from the carrier.

A structural compare of the two CARRIER.json documents printed three value changes:

- `bindings_sha256`, from `3520a3820e63582c90ad0c5834be82a1ee65f4e14752f7fd1d5914a8bdc49a2e` to `21de7caf4a588b5184d930942485183d9a6f6b93ac0a8f2eee8193fd860b23a9`
- `interface_content_ref`, from `c8f0b0f51966925c5872c70c246434cce6784982` to `b0c6f650aa6878381758905afb97087519bc0692`
- `interface_licence_ref`, from `f8486ed3df562bd512b0d948494c76b7e7ae0349` to `2737f321c49371c08d2b624190fda7719a13a52a`

`diff -u` of CARRIER.env printed the same two ref changes and no others. The candidate BINDINGS.sha256 file is the line `21de7caf4a588b5184d930942485183d9a6f6b93ac0a8f2eee8193fd860b23a9`, matching the JSON field.

`diff -u` of SHA256SUMS printed four changed lines: ACCEPTANCE.json, BINDINGS.sha256, CARRIER.env, and CARRIER.json. Every other line is unchanged. `sha256sum` of the candidate ACCEPTANCE.json printed `baa01ea7c52420f3b95f95993f292b67a7c0356eb34189b4d7ab93582d8011ad`, which is the receipt pin in releases/0.2.3.env. This session ignored the seat files and the acceptance receipt body, as the brief requires. The receipt is regenerated after this review.

The carrier inside plebian-os 2a742d0e matches the read-only candidate carrier. `diff -rq`, excluding `seats`, printed nothing. `sha256sum` of that checkout's CARRIER.json printed `42b6956b1669a1351f09e13e16cb00f827448f1c68d64c981d14e6dc56a2dfb3`.

## The commits

Each candidate is one commit on the named parent.

`git rev-parse HEAD` and `git rev-parse HEAD^` printed:

- plebian-os `2a742d0e44ad26bcc008f2c9cd9464c80dfab88f`, parent `2283b1ae5470819e50129a7b3c229a7fbbedd82b`
- kilix-content `b0c6f650aa6878381758905afb97087519bc0692`, parent `c8f0b0f51966925c5872c70c246434cce6784982`
- kilix-license `2737f321c49371c08d2b624190fda7719a13a52a`, parent `f8486ed3df562bd512b0d948494c76b7e7ae0349`
- kilix `58c36b2e33df8e20a3cfe3c6d99e95d20c748ca7`, parent `beb39587b42cdf89ea0c62258c9ba044d05baa1b`

`git rev-list --count PARENT..HEAD` printed 1 for each. `git merge-base --is-ancestor` accepted each parent.

## Claim 1, kilix-license 2737f321

`git diff --name-status f8486ed3df562bd512b0d948494c76b7e7ae0349 2737f321c49371c08d2b624190fda7719a13a52a` printed modifications of CHANGELOG.md, pyproject.toml, src/kilix_license/catalog.py, src/kilix_license/standard_policy.py, tests/test_records.py, tests/test_wheel_records.py, and tools/generate_records.py, plus the new files src/kilix_license/noloop02.py, src/kilix_license/data/determinations-noloop02.json, src/kilix_license/data/determinations-noloop02.sha256, src/kilix_license/data/noloop02-records/qwen-0.8b-no-loop-02.json, tests/test_noloop02.py, and three text files:

- `2569309df198a85501c07065c837ecf18d48a0387208cfdb755702f3be2d9b44`
- `395f7febedfda6b5498ca36cfe3344d3986659ce4385dd8b03d2d75604250a8e`
- `a4e74ed6c5f68677ebe95445696de6d9e2f789b5f63184d95a7a70a5f8cd962f`

A compare of every `src/kilix_license/data/` path present at f8486ed3 printed no changed files and no removed files. Every record file the previous commit carried is byte-identical. The code changes register the new family: catalog.py and pyproject.toml add `noloop02-records` to the load path and the package data, and tools/generate_records.py generates and checks that family. The test edits add this record id to the existing identity tables. Those edits follow from adding the family.

`sha256sum` of the determination file equals the pin file. Both are `0a5c215b89593756ba049ca8dc8fd84824cedcd8ce2c44c2ece7a003457bb1e3`. The determination schema is `kilix.license.noloop02-determination/v1`. Its owner_determination date is 2026-11-09. Its components map is `apache-2.0: approved` and `cc-by-4.0: approved`. Its authority modifier is `itsmygithubacct`. Its licensor string, copied into the record, is `Alibaba Cloud / Qwen; the authors of "LLMs can understand and write neural network weights"`.

From kilix-license, `PYTHONPATH=src python3` loading `load_determined_records().by_id("qwen-0.8b-no-loop-02")` printed:

```
digest f5a93c984528e50574f42f04d8d9403a217bec2c49f88b5f94980e385f7abcc0
eligible True
licensor Alibaba Cloud / Qwen; the authors of "LLMs can understand and write neural network weights"
licence_ids ('Apache-2.0', 'CC-BY-4.0')
text cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30
components [('weight-edit-from-lm-understand-logs', '9ba9550ad48438d0836ddab3da480b3b69ffa0aac7b7878b5a0039e7ab429411')]
statements [('modified-model', '2569309df198a85501c07065c837ecf18d48a0387208cfdb755702f3be2d9b44'), ('weight-edit-attribution', 'a4e74ed6c5f68677ebe95445696de6d9e2f789b5f63184d95a7a70a5f8cd962f'), ('weight-edit-source-licence', '395f7febedfda6b5498ca36cfe3344d3986659ce4385dd8b03d2d75604250a8e')]
decision affirmative accept
```

The same process loaded each carried digest from the candidate CARRIER.json. It printed FOUND and a matching digest for small-en-us, lgraph-en-us, vibevoice-asr-bitnet, faster-whisper-small-en, faster-whisper-medium-en, whistle, kilix-diarization-cpu, and lfm2-kilix-commands.

`git diff` of standard_policy.py adds one ordinary-notice triple: record `qwen-0.8b-no-loop-02`, component `weight-edit-from-lm-understand-logs`, text `9ba9550ad48438d0836ddab3da480b3b69ffa0aac7b7878b5a0039e7ab429411`. The surrounding rule is unchanged: any other component text still makes the record ineligible.

`sha256sum` of the five text files matched their names. The Apache text is 11358 bytes. The CC BY 4.0 legal code is 18657 bytes. The modified-model notice is 1607 bytes. The attribution is 1229 bytes. The edit-source licence file is 1819 bytes.

`PYTHONPATH=src python3 -m unittest tests.test_noloop02 -v` printed four tests, all ok, and `Ran 4 tests in 0.210s` then `OK`.

## Claim 2, kilix-content b0c6f650

`git diff --name-status` against c8f0b0f5 printed the catalog, model.py, receipt.py, the vendored licence tree and its pin, catalog digest fixtures, tests that follow the new asset and the new pin, tools/generate_upstream_records.py, tools/upstream-pins/qwen-0.8b-no-loop-02.json, and a new tests/test_noloop02_asset.py.

A JSON compare of catalog/plebian.json printed one added asset, `qwen-0.8b-no-loop-02`, and no changed or removed asset. `packages` and `content` are equal. Asset count goes from 43 to 44. The catalog file sha256 goes from `aa5c9a01b22068d934132540b1739b19409756517e1436896851e33eb5386c7b` to `ba9f1ffaa01b32d1c31a82643a1b4c103a606aee4a8344f1b055eed6499d3426`. receipt.py changes only that catalog constant. The content gitlink's needle app ref is still `a887e2fae221272aece6b7b9aef143df8bc7ba64`, at `content[51].source.ref`, in both catalogs.

The new asset, read as fields, has provider `kilix-llm`, source mode `upstream-files`, consumer schema `kilix.llm.models/v1`, and schema `kilix.content.asset/v3`. Its one fetch URL is `https://github.com/itsmygithubacct/kilix-llm/releases/download/qwen-0.8b-no-loop-02/qwen-0.8b-no-loop-02.gguf`. The GGUF entry is 833592416 bytes with sha256 `e4d6e93eb644da62e0c5ac0b7b188b4c2cbf31f07a7dcfd42764b6236f96d8a0`. Provenance revision is `4267e55277de7ab3d3380a561a1f5f0d58261f18`. The five notice entries are the five text digests above, with the same byte lengths as the licence texts. This session did not quote the catalog lines that carry product or vendor names. The two licence rows share record digest `f5a93c984528e50574f42f04d8d9403a217bec2c49f88b5f94980e385f7abcc0`. One row is apache-2.0 with licensor `Alibaba Cloud / Qwen` and text `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`. The other is cc-by-4.0 with licensor `the authors of "LLMs can understand and write neural network weights"` and text `9ba9550ad48438d0836ddab3da480b3b69ffa0aac7b7878b5a0039e7ab429411`.

model.py admits that single release URL when the asset id, provider, consumer schema, source mode, version, and provenance revision match. The test diffs add the new id to preservation filters, move the vendored pin from f8486ed3 to 2737f321, and raise the vendored file count from 204 to 211. A byte compare of third_party/kilix-license against kilix-license 2737f321 printed 211 vendored files, no byte mismatches, and no extra vendored files. The paths present only in kilix-license are the tests, tools, and repository files that the vendor has always omitted. The pin file is `2737f321c49371c08d2b624190fda7719a13a52a`.

## Claim 3, Kilix 58c36b2e

`git diff --name-status` against beb39587 printed:

- third_party/kilix-content, a gitlink
- config/model_wizard.py
- scripts/install-kilix-avatar.sh
- scripts/install-kilix-llm.sh, added
- tests for the content count, the installer, the wizard, and the licence batch
- .github/workflows/test.yml
- README.md

`git ls-tree` printed the content gitlink moving from `c8f0b0f51966925c5872c70c246434cce6784982` to `b0c6f650aa6878381758905afb97087519bc0692`. That equals the carrier `interface_content_ref` and `PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF`.

`git diff` of scripts/install-kilix-avatar.sh printed one line: `KILIX_AVATAR_REF` from `bedd1b8977ccebdf8ef60b43bf091a33b171b6c9` to `a383f65aba6352b232e57482e48f415d2d8dffdc`. scripts/install-kilix-llm.sh sets `KILIX_LLM_REF` to `b26cadcdf988547bb5678ec3f0ad2932a5613b1f`. scripts/install-kilix-bonsai.sh is unchanged, and its ref remains `630da3cf64d28b35fb65cafd4e7c8a4ad54b8685`. The workflow diff adds the new installer to the existing shellcheck lists. The README adds a paragraph that the chat page offers this catalog asset and that the installer does not download the weights.

model_wizard.py adds provider `kilix-llm` to the chat group and names Kilix LLM in the chat page title. The new wizard test expects the chat page to select this asset and to call the content consent batch.

`python3 -m unittest tests.test_wizard_licenses.BatchTests.test_selected_catalog_installs_the_no_loop_gguf_under_standard_policy -v`, run in the Kilix checkout after its content gitlink was filled at b0c6f650, printed `ok`, `Ran 1 test in 0.131s`, and `OK`.

This session then ran its own consent, `python3 /home/pleb/storage/research/plebian-os/023-rc7-no-loop-20261109/seats/b/work/own-wizard-run.py`. The script loads the same Kilix and content checkouts, calls `consent_and_install` for qwen-0.8b-no-loop-02, keeps the receipt store under the work directory, and replaces the installer so the run does not download the weights. It printed:

```
provider kilix-llm
source_mode upstream-files
consumer_schema kilix.llm.models/v1
licence_ids ['apache-2.0', 'cc-by-4.0']
record_digest f5a93c984528e50574f42f04d8d9403a217bec2c49f88b5f94980e385f7abcc0
record_licensor Alibaba Cloud / Qwen; the authors of "LLMs can understand and write neural network weights"
eligible True
account_in_licensor False
allowed ['qwen-0.8b-no-loop-02']
declined []
questions []
installer_calls 1
installed_asset qwen-0.8b-no-loop-02
receipt_count 1
receipt_record_digest f5a93c984528e50574f42f04d8d9403a217bec2c49f88b5f94980e385f7abcc0
statement_digests {'modified-model': '2569309df198a85501c07065c837ecf18d48a0387208cfdb755702f3be2d9b44', 'standard-license-policy-v1': '354bb6c1d0691fb66b606edc28b72145b00687a9300b883737df189d76ff6681', 'weight-edit-attribution': 'a4e74ed6c5f68677ebe95445696de6d9e2f789b5f63184d95a7a70a5f8cd962f', 'weight-edit-source-licence': '395f7febedfda6b5498ca36cfe3344d3986659ce4385dd8b03d2d75604250a8e'}
```

The document index names `licence:apache-2.0` at `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`, `licence:cc-by-4.0` and `component:weight-edit-from-lm-understand-logs` at `9ba9550ad48438d0836ddab3da480b3b69ffa0aac7b7878b5a0039e7ab429411`, and the three statement digests above. No typed question was asked. The receipt names the standard-policy statement.

The avatar repository returned HTTP 404 to the public commit API, and `git ls-remote` stopped without a ref. releases/0.2.3-followups.md in this candidate says that repository is private and that `a383f65aba6352b232e57482e48f415d2d8dffdc` is pushed. This session confirmed the pin string in the installer and did not read that commit's tree.

## Claim 4, plebian-os 2a742d0e

`git diff --name-status` against 2283b1ae printed CHANGELOG.md, both provision scripts, releases/0.2.3-command-model.json, releases/0.2.3-followups.md, the five carrier files named above, releases/0.2.3-notes.md, releases/0.2.3.env, releases/0.2.3.requirements, and the new tests/test_kilix_llm_install.py. `git diff --stat` of build/remaster-iso.sh printed nothing.

releases/0.2.3.env sets `PLEBIAN_OS_REF=v0.2.3-rc7`, `KILIX_REF=58c36b2e33df8e20a3cfe3c6d99e95d20c748ca7`, `KILIX95_REF=24130253f29070883713d677469c7ce1161d02c9`, `KILIX_LICENSE_REF=2737f321c49371c08d2b624190fda7719a13a52a`, `PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF=b0c6f650aa6878381758905afb97087519bc0692`, `PLEBIAN_OS_VOICE_CARRIER_SHA256=42b6956b1669a1351f09e13e16cb00f827448f1c68d64c981d14e6dc56a2dfb3`, and `PLEBIAN_OS_VOICE_CARRIER_RECEIPT_SHA256=baa01ea7c52420f3b95f95993f292b67a7c0356eb34189b4d7ab93582d8011ad`. `KILIX_VOICE_REF` is `1a4e63b11d0ad9c1664031e2773f5c4f5797913f` at both 2283b1ae and 2a742d0e.

releases/0.2.3.requirements carries the same four values for the carrier sha256, the receipt pin, `KILIX_LICENSE_REF`, and `PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF`. It does not carry `KILIX_REF` or `KILIX_VOICE_REF`. Its diff is those four assignments.

The provision and update scripts each gain `install_kilix_llm`. The provision function runs the pinned Kilix `scripts/install-kilix-llm.sh` and then `kilix-llm build --backend cpu`. The update function does the same with the update environment. The call sits after the needle install and before command-model staging. The comments say the weights arrive through the wizard.

`python3 -m unittest tests.test_kilix_llm_install -v` from the plebian-os checkout printed five tests, all ok, `Ran 5 tests in 0.034s`, and `OK`. The install-and-upgrade test's recorded lines are `install ` and `kilix-llm build --backend cpu`.

releases/0.2.3-command-model.json changes the kilix, kilix-content, and kilix-license source pins to the candidate commits, and the manifest revision to b0c6f650. The needle pin stays `a887e2fae221272aece6b7b9aef143df8bc7ba64`. The command archive identity in that file is otherwise the same.

Kilix 95 `24130253f29070883713d677469c7ce1161d02c9` is one commit on `44525e240f9d8fa7d1b4cc0538992be46cd14952`, message "Offer LLM Chat and Kilix Avatar entries for qwen-0.8b-no-loop-02". `git diff --name-status` printed applications.py, its test, the README, and the workflow's Kilix commit pin, which moves to `58c36b2e33df8e20a3cfe3c6d99e95d20c748ca7`. The application change adds chat and avatar rows for this asset when the kilix-llm binary is installed, and it leaves a Bonsai chat row in place when another chat asset is selected. The follow-up says the avatar entry appears after `kilix avatar`, as the existing avatar entry does.

## kilix-llm catalogue and the release

kilix-llm checkout `b26cadcdf988547bb5678ec3f0ad2932a5613b1f` is one commit on `4267e55277de7ab3d3380a561a1f5f0d58261f18`. `git rev-parse qwen-0.8b-no-loop-02^{commit}` printed `4267e55277de7ab3d3380a561a1f5f0d58261f18`. The catalogue entry in src/kilix_llm/models.py names file `qwen-0.8b-no-loop-02.gguf`, size 833592416, sha256 `e4d6e93eb644da62e0c5ac0b7b188b4c2cbf31f07a7dcfd42764b6236f96d8a0`, and the same release URL as the content asset.

This session downloaded all six release assets from `https://github.com/itsmygithubacct/kilix-llm/releases/download/qwen-0.8b-no-loop-02/` into its work directory and ran `sha256sum -c SHA256SUMS`. The command printed:

```
qwen-0.8b-no-loop-02.gguf: OK
README.md: OK
LICENSE: OK
LICENSE-lm_understand-logs.txt: OK
edit-record.json: OK
```

`wc -c qwen-0.8b-no-loop-02.gguf` printed 833592416. SHA256SUMS lists sha256 `e4d6e93eb644da62e0c5ac0b7b188b4c2cbf31f07a7dcfd42764b6236f96d8a0` for that file. The release tag's target on the GitHub API is `4267e55277de7ab3d3380a561a1f5f0d58261f18`.

## Licence delivery

The record's licensors are Alibaba Cloud / Qwen and the authors of the edit source. `itsmygithubacct` is the authority modifier and the "Modified by" line of the modified-model notice. The licensor field does not contain that account. `standard_policy_eligible` is true for this record and false if the component text digest is replaced.

The five asset notice digests are the record's Apache text, the CC BY 4.0 component text, and the three statement texts. Each licence text file hashes to its name, and the catalog entries use those digests and byte lengths, so the bytes the installer records are those texts.

This session fetched `Qwen/Qwen3.5-0.8B` LICENSE at revision `2fc06364715b967f1860aea9cf38778875588b17`. Its sha256 is `bbedc3fda3305820b977265f01b8619d87570a6739de3a5582c3464840f1e57a`, the determination's `upstream_licence_file_sha256`, and it is byte-identical to the release LICENSE. After converting newlines, that file and the shipped Apache text `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30` differ by the appendix line `Copyright 2026 Alibaba Cloud` in the upstream file, where the shipped Apache text keeps the appendix placeholder, and by one trailing newline. The terms in the body match. A fetch of NOTICE at that revision returned HTTP 404.

This session fetched `RikiyaT/lm_understand-logs` LICENSE at `4d09ba6d6a7e891dd8063974dfe81b3d78e3494f`. Its sha256 is `395f7febedfda6b5498ca36cfe3344d3986659ce4385dd8b03d2d75604250a8e`. It is byte-identical to the record text and to the release file LICENSE-lm_understand-logs.txt.

This session fetched the CC BY 4.0 legal code from `https://creativecommons.org/licenses/by/4.0/legalcode.txt`. It is byte-identical to text `9ba9550ad48438d0836ddab3da480b3b69ffa0aac7b7878b5a0039e7ab429411`, 18657 bytes.

Apache-2.0 section 4, as this session judges the delivered notices:

- A copy of the licence is delivered. The catalog notice is the Apache 2.0 terms. The release LICENSE is the upstream file, which is those terms with the copyright appendix filled in.
- A prominent modification notice is delivered. The modified-model notice says the file is a modified version, names the modifier, names the two changed tensors, and says the other tensors are unchanged. The release card's last paragraph is the paragraph the notice quotes, and it is present in the release README. The GGUF metadata key `general.description` contains the sentence the notice quotes: `Modified from Qwen/Qwen3.5-0.8B (Q8_0): one third of a published edit (alpha 2 of 6) applied to 64 ffn_down columns in layers 15 and 19, to reduce thinking-mode loops. Edit by the authors of 'LLMs can understand and write neural network weights' (CC BY 4.0). Apache-2.0.`
- The copyright notice from the upstream licence appendix is retained. The release LICENSE keeps `Copyright 2026 Alibaba Cloud`. The modified-model notice and the release card both say `Qwen3.5-0.8B is Copyright 2026 Alibaba Cloud` and name the Apache License 2.0.

CC BY 4.0 section 3(a), as this session judges the delivered notices:

- The creator is identified as the authors of "LLMs can understand and write neural network weights", with the repository, path `exp8_math/runs/p50c/edit`, and commit `4d09ba6d6a7e891dd8063974dfe81b3d78e3494f`. The source licence file keeps its copyright line and is delivered unchanged.
- The attribution notice and the release card give the licence name and the link `https://creativecommons.org/licenses/by/4.0/`. The catalog also delivers the legal code itself.
- The attribution states the three changes: scaled to one third (alpha 2 of 6), applied to the Q8_0 conversion and quantized, and packaged with new GGUF metadata. The release card has the same three lines.
- The attribution and the release card say the authors have not reviewed or endorsed this model.

This session judges that the delivered notices meet those conditions. The carrier's eight models still carry the licence records, artifact records, licence texts, and delivery statements of the seat-approved carrier.

## Generator check

From the work directory, on a writable copy of the candidate carrier, this session ran `python3 plebian-os/build/generate-model-compliance.py --content-repo kilix-content --license-repo kilix-license --out candidate-carrier-copy --check` with one `--determination MODEL=PATH` per file under determinations/, MODEL being the parent directory name, and one `--seat PATH` per file under seats/, both in sorted path order. The eleven determination paths and two seat paths were the files in that copy. The generator printed nothing. The exit status was 0.

## Carrier tests

From the plebian-os checkout at 2a742d0e, with `PLEBIAN_OS_KILIX_REPO`, `PLEBIAN_OS_KILIX_CONTENT_REPO`, `PLEBIAN_OS_KILIX_LICENSE_REPO`, `PLEBIAN_OS_KILIX_VOICE_REPO`, `PLEBIAN_OS_KILIX_NEEDLE_REPO`, `PLEBIAN_OS_NEEDLE_REPO`, and `PLEBIAN_OS_KILIX_BONSAI_REPO` set to the sibling checkouts at the candidate commits, this session ran:

```
python3 -m unittest tests.test_model_compliance_carrier -v
```

It printed ok for AC-1 through AC-6 and AC-8 through AC-12, under the test names in the generator's qualification list, and ok for the other tests in that module. It printed FAIL for `test_acceptance_receipt_names_two_independent_seats`. The assertion requires the candidate carrier sha256 `42b6956b1669a1351f09e13e16cb00f827448f1c68d64c981d14e6dc56a2dfb3` to appear in each attached seat text. Those attached texts are the earlier seat records carried beside this carrier, and they do not contain that sha256. The command printed `Ran 17 tests in 5.378s` and `FAILED (failures=1)`. That is the AC-7 failure the brief expects until a receipt names this review.

## Known issue

In kilix-content tools/generate_upstream_records.py, the comment above the weight-edit component row says the owner has not yet signed off that component and points at the owner_determination in determinations-noloop02.json. That determination records both components approved on 2026-11-09. The row the generator writes is `decision: affirmative`, and the catalog asset and the wizard receipt use that approved record. The comment is false. It does not change the served terms, the record, or the receipt.

## Verdict

The required identities match. The carried records, texts, and delivery statements are unchanged. The new record implements the owner's licence decisions, the wizard installs it with a standard-policy receipt and no typed question, and the delivered notices meet the two licences' conditions named in the brief. The comment above is a defect. It is not one of the mismatches that require a refusal.

VERDICT: ship with known issues
