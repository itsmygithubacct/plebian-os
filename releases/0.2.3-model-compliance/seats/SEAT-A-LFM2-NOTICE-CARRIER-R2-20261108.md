# Seat A review: LFM2 notice carrier, round 2 (2026-11-08)

This is the seat A record for the Plebian-OS 0.2.3 RC5 model-compliance carrier candidate at plebian-os `71aceb850bf5f08f2ef779a35ebf16b4b3c2f8a8`.

Candidate `CARRIER.json` sha256, as this session computed it: `bf003bf70e6059e3ec7b458ea4e7b26266383486825f361a472e7efc5f1f71ac`.

`DEFAULT-MODELS.json` field `sha256`, as this session read it: `e00614bf726154d09668820c061cbbcb402239a445bde666b0568d36f01528a6`.

## Eligibility

The builder session launched this pane with `kilix @ launch` at 2026-11-08T11:05Z and wrote the brief this session followed. This session started fresh in that pane. It did not author the carrier, its generator, its determinations, the kilix-license LFM2 determination, the kilix-content catalog selection, the Needle install code or its vendored content, the Kilix install screens, the plebian-os image installer, or the delivery archive. This session is eligible.

The review was read-only. This session did not modify the carriers, any source checkout outside its own `work` directory, or the other seat's directory. It did not read the other seat's directory or the builder's notes. It did not commit, push, publish, write `ACCEPTANCE.json`, or start other agents. One disclosure: when the carrier's receipt test failed (check 9), the failure message printed the text of an earlier seat record held under the carrier's `seats/` directory. This session did not use that text as evidence for anything in this record.

Paths in this record are relative to this seat's directory (`seats/a2`), except paths that start with `seat-inputs-r2/`, which are relative to the review folder. Live installs ran in sandbox directories under `work/` with a cleared environment (`env -i` with only `PATH`, `HOME` and `KILIX_DATA_HOME` set). This session's shell inherited `GPU_TERMINAL_HOME` and `KILIX_DATA_HOME` from the desktop session, and some unit-test runs inherited them too. Afterwards `find` on the real receipt store and the real data home listed 0 files modified since this session started, so this session wrote nothing there.

## 1. Sources fetched

Command: `git clone` of plebian-os, kilix-content, kilix-license, kilix-needle and kilix-voice, plus kilix with `--filter=blob:none`, into `work/`. Then `git fetch origin '+refs/heads/*:refs/remotes/origin/*'`, `git checkout <commit>` and `git branch -r --contains <commit>` in each. Output:

- plebian-os `71aceb850bf5f08f2ef779a35ebf16b4b3c2f8a8`, on `origin/work/0.2.3-rc5-image-models`
- kilix-content `d57fa62f2393363284a29a6d4024e6f9dfa66ac4`, on `origin/work/0.2.3-rc5-ask-20261107`
- kilix-license `0984dd222bcb7f97859222b0dc2303b9225191fe`, on `origin/work/0.2.3-rc5-ask-20261107`
- kilix `b0c8939b05b7c2b6ffad9d90f10f0a31ec194a9a`, on `origin/work/0.2.3-rc5-ask-20261107`
- kilix-needle `5cbff3172224d5277adee5a3c826ee4b0698917a`, on `origin/work/0.2.3-rc5-ask-20261107`
- kilix-voice `1a4e63b11d0ad9c1664031e2773f5c4f5797913f`

kilix-bonsai was cloned later because the AC-8 delivery test needs a checkout holding `630da3cf64d28b35fb65cafd4e7c8a4ad54b8685`. `git cat-file -t` printed `commit`.

`git log --format='%H %P' -1` showed that each candidate is one commit on top of its rejected parent: plebian-os `71aceb8` on `458d48d`, kilix-content `d57fa62` on `81f2321`, kilix `b0c8939` on `52ba3cd`, and kilix-needle `5cbff31` on `3a8e41c5`.

## 2. Carrier identities and the claim 5 diff

Command: `sha256sum seat-inputs-r2/{candidate,reviewed,rejected}-carrier/CARRIER.json`. Output:

- candidate `bf003bf70e6059e3ec7b458ea4e7b26266383486825f361a472e7efc5f1f71ac`
- last seat-approved `c578757b715a87b8f366fabd0db268c0122d153cef1d26a8ba1f849b4a819726`
- rejected `ace6258566e764a0504efd78a843622814e674b5a1e5e8b7fbb22ea1ea90b913`

All three match the brief.

Command: `diff -r -x seats -x ACCEPTANCE.json seat-inputs-r2/rejected-carrier seat-inputs-r2/candidate-carrier`, followed by a key-by-key JSON comparison of the two `CARRIER.json` documents. Output: only `BINDINGS.sha256`, `CARRIER.env`, `CARRIER.json` and `SHA256SUMS` differ. In `CARRIER.env` the only changed line is `interface_content_ref`, from `81f2321b51649effc3275493a351931497c3ba0f` to `d57fa62f2393363284a29a6d4024e6f9dfa66ac4`. In `CARRIER.json` the only differing keys are `interface_content_ref` (same change) and `bindings_sha256` (from `c5ce191c…` to `2d6d48cd2be8feb19f1306b0455c1820c597a6c18df328147439b348a3ed47d2`). `BINDINGS.sha256` changes only on the `CARRIER.env` line. `SHA256SUMS` changes only on the lines for `ACCEPTANCE.json`, `BINDINGS.sha256`, `CARRIER.env` and `CARRIER.json`. Claim 5 holds.

Command: `sha256sum -c SHA256SUMS` and `sha256sum -c BINDINGS.sha256` in the candidate carrier, printing only lines that were not OK. Output: none. All 64 SHA256SUMS lines and every BINDINGS line verify. `sha256sum BINDINGS.sha256` printed `2d6d48cd2be8feb19f1306b0455c1820c597a6c18df328147439b348a3ed47d2`, which equals `bindings_sha256`.

Command: `diff -r -x seats -x ACCEPTANCE.json work/plebian-os/releases/0.2.3-model-compliance seat-inputs-r2/candidate-carrier`. Output: no differences. The carrier committed at `71aceb8` is the one exported for review.

For context, `diff -rq` against the last seat-approved carrier showed that only the LFM2 files, the LFM2 determination, `COMMAND-MODEL.json`, one licence text (the v9 modified-model notice `65e4cd26…` replacing `e03643ad…`), the three speech DELIVERY lines naming kilix-voice `1a4e63b` instead of `1faf9fb`, and the derived pin files differ. A JSON comparison found every non-LFM2 model entry equal. These differences were already present in the rejected carrier and are unchanged in the candidate.

## 3. The LFM2 records, determination and archive

Command: `cmp` of `work/kilix-license/src/kilix_license/data/lfm2-records/lfm2-kilix-commands.json` with the carrier's `lfm2-kilix-commands/LICENCE-RECORD.json`. Output: equal. `sha256sum` of the kilix-license `determinations-lfm2.json` and of the carrier's `determinations/lfm2-kilix-commands/command-model-determination.json` printed `24843edf602901aa18427e8215a8d3927c863b2fb9cc7029be5a1d5f265bf4e7` for both, and `cmp` found them equal. That value is the kilix-license pin file and the record's `determinations_sha256`. The determination records the owner's verbatim answer choosing option 1, dated 2026-11-07. Its effect text says the commercial-use limitation is delivered as a notice, the full text is shown and shipped, no typed agreement is taken or recorded, the terms are not waived, and coverage is a record receipt that claims no agreement. That matches the owner's decision. The record has `decision_class` `informational` and one binding condition, `commercial-use-limitation`, with `agreement_required` false. The terms are still present, not removed.

Command: in `work/kilix-license`, load the determined records and compute the LFM2 record digest. Output: `lfm2 digest e4d08e2c53ab514e1e2ca2a812c64895519487d707c441703978bd0f245b5016 expected record`. This matches the brief and the carrier's `licence_record_digest`.

Command: `curl -sSL -o lfm2-kilix-commands-20261106-v9.tar.gz <the published release URL from the brief>`, then `stat -c %s` and `sha256sum`. Output: `1362204317` and `ea03c42ce0f36d12bca1844c558c0fcaeb442887e55e1e7b76ccb3ed632c3a85`. Both match the brief and the carrier. `cmp` against the local delivery file named in the brief found it byte-identical to this download.

Command: `tar -xzf` of the download, then `stat -c '%s'` and `sha256sum` on the members. Output: `model.gguf` is 1388859040 bytes with sha256 `3fa22c105b1f80823088de21a45fd2f3dc30a4cfdc63d21037c9344585fae4dd`. `notices/NOTICE.txt` has sha256 `65e4cd26f6f63d2ad45c64df2a6876bc33b17c4af5272c90bd44dd072b0e6601`. `notices/LICENSE-LFM.txt` has `4d28ca14…` and `notices/LICENSE-runtime.txt` has `571c0295…`. All match the brief and the carrier's `licence_text_sha256s`. A script compared every extracted member against the carrier's `ARTIFACT.json`: `artifact files 44 archive members 44 mismatches 0`. The NOTICE.txt text names delivery v9 and weight `lfm2-kilix-v5e1-wse-20261106.9`, and says it does not replace or waive any upstream licence term.

## 4. kilix-license 0984dd22: typed answers refused for LFM2, LFM3 still requires agreement

Command: in `work/kilix-license`, call `capture_agreement` on the LFM2 record with each answer. Output:

- `'yes'`, `'y'`, the record's typed agreement line and `'I agree'`: each refused with `AgreementRequired`
- no answer: `record None`, meaning decision `record` with no typed text

Command: the same for `lfm3-kilix-commands`. Output: `lfm3 4759e37d… accept [True]`. No answer is refused. `'yes'` and `'y'` are accepted, and the exact line is accepted with decision `accept`. kilix-license documents itself as "explicit yes/no consent with legacy exact-line support", so a typed yes is its form of agreement. LFM3 still requires agreement there. The exact-line requirement for LFM3 is Needle's, and check 6 tests it.

Command: `git diff --quiet 062266365abb… 0984dd2 -- …determinations-lfm3.json …lfm3-records …agreement.py …receipts.py …coverage.py`. Output: no differences. The LFM3 record, agreement capture, receipts and coverage are unchanged since the approved kilix-license. Commit `0984dd2` touches only the LFM2 determination and its pin, the LFM2 record, the changelog and tests.

## 5. kilix-content d57fa62 and Needle's vendored kilix-content 81f2321b serve the same LFM2 records

Command: `git diff --stat 81f2321b d57fa62` in kilix-content. Output: `CHANGELOG.md`, `src/kilix_content/catalog/plebian.json`, `src/kilix_content/receipt.py`, `tests/test_detector_pins.py` and `tests/test_pdf_pin.py`. The catalog change is one line, the kilix-needle app ref from `3a8e41c52f32f963c4bbeadfbec69b200f13eafe` to `5cbff3172224d5277adee5a3c826ee4b0698917a`. `receipt.py` re-pins `_CATALOG_SHA256` to `4ad9e66586d6f35088fe70d037b56b69153a53f6cd9842d2f208901b8c7ea419`, and `sha256sum` of the new catalog printed that value. The two tests move the Needle ref pin. `git diff --quiet 81f2321b d57fa62 -- third_party tools` printed `third_party-tools-unchanged`, so no asset or licence record changed. Claim 2 holds.

Command: parse the catalog at d57fa62 for the `kilix-needle` content entry. Output: `needle ref 5cbff3172224d5277adee5a3c826ee4b0698917a`.

Command: in kilix-needle `5cbff317`, `git ls-tree HEAD third_party/` and `git submodule update --init third_party/kilix-content`. Output: the gitlink is `81f2321b51649effc3275493a351931497c3ba0f`, and that commit was checked out.

Command: for both `work/kilix-content` (d57fa62) and `work/kilix-needle/third_party/kilix-content` (81f2321b), take the `lfm2-kilix-commands` asset from the catalog, serialize it canonically, and compare it with the carrier's `ARTIFACT.json` bytes. Output: one entry in each, canonical sha256 `148cbccadb46846ec55c3e7a4245611d23f37010b40b9b99fe8beb3122135ff1` for both, and byte-equal to the carrier for both. The asset is version `lfm2-kilix-commands-20261106-v9` with licence decision `informational` and record digest `e4d08e2c…`.

Command: `cmp` of each vendored LFM2 licence record with the carrier's `LICENCE-RECORD.json`, plus `diff -rq` of the two vendored kilix-license trees and of the d57fa62 vendored tree against `work/kilix-license/src/kilix_license`. Output: both records equal the carrier's, and the vendored trees are identical to each other and to kilix-license `0984dd22`. `third_party/kilix-license.pin` in d57fa62 reads `0984dd222bcb7f97859222b0dc2303b9225191fe`.

Command: `diff` of the two catalogs, 81f2321b against d57fa62. Output: one line, the Needle ref. The vendored catalog inside Needle names the parent Needle `3a8e41c5` as its own app ref. That is unavoidable, because a commit cannot vendor a catalog that names its own hash, and Needle does not install itself from that entry.

## 6. Needle 5cbff317: diff, tests, and a live `install --commands`

Command: `git diff --stat 3a8e41c5 5cbff317`. Output: `README.md`, `asset.py`, `commands-model.json`, `tests/test_apps.py`, `tests/test_asset_vendored_notice.py` (new), `tests/test_commands_runtime.py` and `third_party/kilix-content` (from `23cc16c9` to `81f2321b`). The full diff showed the following:

- `asset.py` changes only the non-terminal message, from "its licence can only be accepted at a terminal" to "its licence terms can only be shown at a terminal".
- `commands-model.json` now has version `lfm2-kilix-commands-20261106-v9`, weight `lfm2-kilix-v5e1-wse-20261106.9`, the v9 model and NOTICE hashes, and weight-edit parent `lfm2-kilix-v5e1-wse-20261106.8` with rows 568 and 8110. That matches the archive's NOTICE.txt. A script compared its `files` map with the carrier's `ARTIFACT.json`: `True 44`.
- `tests/test_apps.py` adds `NOT_YET_LAUNCHABLE = {"kilix-find", "kilix-power-controls", "playalong"}`. A comparison of the content ids in the catalogs at `23cc16c9` and `81f2321b` printed `added ['kilix-find', 'kilix-power-controls', 'playalong'] removed []`, so the three are exactly the apps the vendored move added.
- `README.md` describes delivery v9 and weight `20261106.9`. `tests/test_commands_runtime.py` changes the pinned model hash to `3fa22c10…`.

The README and runtime-test changes are not named in claim 1, but both restate the new delivery that `commands-model.json` describes, so they follow mechanically from claim 1.

Command: in the parent's vendored content `23cc16c9`, read the LFM2 licence record and asset. Output: `affirmative True`, and asset `lfm2-kilix-commands-20261104-v8 affirmative 9db4f674…`. This confirms the defect the previous round found.

Command: `python3 -B -m unittest discover -s tests -p test_asset_vendored_notice.py -v`, then the same for `test_apps.py` and `test_commands_runtime.py`. Output: 3 tests OK, 101 tests OK and 7 tests OK.

Command: `python3 -B -m unittest discover -s tests` at 5cbff317, and in a separate clone at 3a8e41c5 with its vendored content `23cc16c9`. Output: candidate `Ran 1644 tests … FAILED (failures=8, errors=27, skipped=6)`, parent `Ran 1641 tests … FAILED (failures=8, errors=27, skipped=6)`. `diff` of the sorted failing test names printed `same failing set`. Every failure is in `test_jobs` or the `test_logs_*` modules, and the errors read "no kilix-ml tuning library … run `git submodule update --init third_party/kilix-ml`" and "pinned kilix_rollout.records is unavailable". The failures come from submodules this session did not initialize, and the candidate introduces none. It adds 3 passing tests.

Live install. A driver script ran `python3 -B needle_cli.py install --commands --from <the extracted v9 archive>` under a real pseudo-terminal in fresh sandboxes, answered one line at the prompt, and kept the transcript. (A first version of the driver answered early, when a chunk of licence text happened to end in `>`, which echoed the answer into the middle of the screen. The driver was corrected to answer only at the real prompt, and the runs reported here use the corrected driver.) Results:

- Answer `y`: `exit 0`. The screen contains the `LFM Open License v1.0` text, `Commercial Use Limitation`, `decision: informational`, `version: lfm2-kilix-commands-20261106-v9`, then "These terms are a notice and take no agreement." and "Install this exact model? [y/N]". "To accept, type exactly" does not appear. The full texts of `4d28ca14…` (10574 bytes), `571c0295…` (12682 bytes), `65e4cd26…` (1545 bytes) and the commercial-use condition `17f031ac…` (560 bytes) each appear on the screen byte for byte. The install wrote one receipt, `e4d08e2c…-ef701ec2….json`, with `decision record`, record `e4d08e2c53ab514e1e2ca2a812c64895519487d707c441703978bd0f245b5016`, manifest `ef701ec2…`, no `typed_text` field, and capture mode `interactive-tty`.
- Answer `n`: `exit 1`, "kilix-needle: not installed; nothing was written or downloaded", and 0 files in the sandbox.
- Answer equal to LFM2's typed agreement line: `exit 1`, the same refusal, and 0 files. The notice route takes no typed agreement, so the line cannot be used to record one.
- No terminal (`</dev/null`): "kilix-needle: lfm2-kilix-commands is not installed, and its licence terms can only be shown at a terminal: run `kilix-needle install --commands`", `exit=1`.
- `install --commands lfm3` with answer `yes`, and again with `y`: the screen ends "To accept, type exactly:" followed by the exact line, then "kilix-needle: not accepted; nothing was written or downloaded", `exit 1`, and 0 files in the sandbox. With the exact line, the gate passes and the install proceeds to read supplied files, then stops at "could not open supplied file: …/model.gguf" because the supplied directory was deliberately empty. LFM3 still requires the exact line.

## 7. The image installer at 71aceb8, and a receipt written as the image writes it

Command: `git diff --quiet 458d48d 71aceb8 -- provision build`. Output: `provision-build-unchanged-vs-458d48d`. Reading `provision/install-image-models.py` `install_command_model` showed that it verifies the staged archive against the pin and refuses a catalog that differs from the pin. It refuses a record eligible for the standard policy ("must keep its published custom terms"). When no receipt covers the asset, it raises "command model terms need a typed agreement; the image never answers one" for any record whose `expected_decision` is not `record`. Otherwise it calls `lic.capture_agreement(record)` with no answer and writes that receipt. `grep` for `'yes'` and `"yes"` in the file found nothing. The AC-8 tests in check 9 plant `if False:` over that guard and the guard is refused.

Live image install. A driver script loaded `provision/install-image-models.py` from `work/plebian-os` and called its own `validate_command_pin` and `install_command_model`. The arguments were Kilix `b0c8939b` (its `third_party/kilix-content` initialized at d57fa62, clean) and a cache directory holding a hard link to the downloaded archive under its sha256 name. The environment was cleared except for a sandbox `HOME` and `KILIX_DATA_HOME`. Output:

```
Command model: recording the published notice terms for lfm2-kilix-commands
verifying cached lfm2-kilix-commands …
Command model installed: lfm2-kilix-v5e1-wse-20261106.9
```

The modules loaded from Kilix's `third_party/kilix-content` and its vendored kilix-license. The receipt written was `e4d08e2c…-ef701ec2….json`, with `"decision": "record"`, record digest `e4d08e2c53ab514e1e2ca2a812c64895519487d707c441703978bd0f245b5016`, manifest `ef701ec2c8fb6a46bbe733d51a6be498e325bb60d3b45ec8938f0ed0ba1aef50`, no `typed_text` field, capture mode `no-tty`, and `catalogue_digest` `4ad9e665…`, which is the d57fa62 catalog.

Command: against that same sandbox, from `work/kilix-needle`, load Needle's own content and call `first_use.needs_agreement` and `asset._installed_spec`, then run `python3 -B needle_cli.py install --commands </dev/null`. Output: `needle spec lfm2-kilix-commands-20261106-v9 ef701ec2… ['e4d08e2c…']`, `needs_agreement with image receipt: False`, and `already installed: …/desktop-apps/assets/lfm2-kilix-commands--ef701ec2…`, `exit=0`. The receipt the image writes covers the asset Needle serves, although Needle's own catalog digest is `3bc0dac2…`. kilix-license coverage binds the manifest and record digests, not the catalogue digest.

The same check from the parent Needle clone (3a8e41c5) against the same sandbox printed `parent needle spec lfm2-kilix-commands-20261104-v8 ['9db4f674…']` and `needs_agreement with image receipt: True`. That reproduces the defect the previous round found.

## 8. Kilix b0c8939b and its install route

Command: `git diff --stat 52ba3cd1 b0c8939b`. Output: `README.md`, `config/content_models.py`, `tests/test_content_models.py` and `third_party/kilix-content`. The diff changes the module docstring, the `--from` plan note, the `--from` install screen, `_FROM_HELP` and the README paragraph. For a notice licence, each now says the receipt records that the terms were shown and claims no agreement, instead of an acceptance. It adds one test, and moves the gitlink from `81f2321b` to `d57fa62f`. Claim 3 holds. In `_install`, the agreement question is asked only when `record.expected_decision == "accept"`. Otherwise `typed` stays `None` before `install_with_agreement`.

Command: `python3 -B -m unittest tests.test_content_models -v`. Output: `Ran 40 tests … OK`, including `test_from_a_notice_licence_says_its_receipt_claims_no_agreement … ok`.

Live: a pseudo-terminal driver ran `python3 -B config/content_models.py install lfm2-kilix-commands --from <the extracted v9 archive>` in a fresh cleared sandbox and answered `y`. Output: `exit 0`. The screen showed the full texts `4d28ca14…`, `571c0295…`, `65e4cd26…` and `17f031ac…` byte for byte, `decision: informational`, and "The receipt records that the licence terms were shown; it claims no agreement, exactly as for a download." The only question was "Install this exact model in the shown root? [y/N]". The plan note read "The receipt records that the licence terms were shown, claiming no agreement, not that the files were supplied." The receipt has `decision record`, record `e4d08e2c…` and no `typed_text` field.

Command: `git grep` in kilix, kilix-needle and plebian-os (outside vendored, test and data files) for lines that mention LFM2, the command model or the LFM licence together with accept, agree, waive or consent. Output: no Kilix line. Needle printed only a benchmark document heading. plebian-os printed only the image installer's refusal line. A wider search in Needle for licence-acceptance wording found the message reported under Known issues.

## 9. AC-8 at 71aceb8, both ways

Command: `git diff 458d48d 71aceb8 -- tests/test_model_compliance_carrier.py`. Output: the new `needle_vendor_gaps` function and `test_command_model_records_needle_serves_are_the_carried_ones`. The test reads the Needle ref from the catalog at `PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF`, reads that Needle's vendored kilix-content gitlink, and compares that content's LFM2 asset and licence record, and Needle's `commands-model.json`, with the carried ones. It then plants three defects (the v8 version on the asset, `affirmative` in the record, the v8 version in `commands-model.json`) and requires exactly one gap for each. The same commit adds a step to the repository's CI test workflow that fetches the kilix-content commit Needle vendors. That change is not named in claim 4, but it exists only so the new AC-8 test can read Needle's vendored content in CI, so it follows mechanically from claim 4.

Command: `python3 -B -m unittest tests.test_model_compliance_carrier -v` in `work/plebian-os`, with sibling checkouts `kilix`, `kilix-content`, `kilix-license`, `kilix-needle` and `kilix-bonsai`. Output: `Ran 17 tests`, 16 ok and 1 failure. The new `test_command_model_records_needle_serves_are_the_carried_ones … ok`. These also pass: `test_carrier_regenerates_byte_identically`, `test_carried_records_are_the_ones_the_image_serves`, `test_delivery_statement_is_true_of_this_image`, `test_guard_refuses_every_planted_carrier_defect` and `test_release_requirements_pin_the_carrier`. The one failure is `test_acceptance_receipt_names_two_independent_seats`. The committed `ACCEPTANCE.json` names seat records that do not contain the new carrier hash. The brief says the receipt is regenerated after this review, so this session expects that failure and does not count it against the candidate.

Negative run, by pin. Command: `git worktree add --detach ../neg-plebian-os 71aceb8`, then `sed` to set `PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF=81f2321b51649effc3275493a351931497c3ba0f` in `releases/0.2.3.env` (the catalog at 81f2321b selects Needle `3a8e41c52f32f963c4bbeadfbec69b200f13eafe`), then the single AC-8 test. Output: `FAILED (failures=1)`, with the gap list:

```
lfm2-kilix-commands: Needle's vendored asset record is not the carried one
lfm2-kilix-commands: Needle's vendored licence record is not the carried one
lfm2-kilix-commands: Needle's commands-model.json does not describe the carried asset
```

Negative run, direct. Command: import `needle_vendor_gaps` from the test module and call it with each Needle's vendored catalog, licence record and `commands-model.json`. Output: `3a8e41c5 vendors 23cc16c9 gaps:` followed by the same three gaps, and `5cbff317 vendors 81f2321b gaps: []`. The test passes at the candidate and fails on Needle 3a8e41c5's vendored content and `commands-model.json`.

## 10. The release guard in build/remaster-iso.sh

Reading `build/remaster-iso.sh` at 71aceb8 lines 427 to 431: `case "${cv[${prefix}decision]}" in affirmative|informational) ;; *) carrier_refuse "$model licence decision is not affirmative or informational"`.

Command: a script that reuses the test module's `run_guard`, `release_env`, `edit_env` and `rebind`. It runs the guard on the unchanged candidate, then on copies where only `m_lfm2_kilix_commands_decision` is set to each value, with every digest and pin re-derived. Output:

- unchanged candidate carrier: exit 0
- `'informational'`: exit 0
- `'affirmative'`: exit 0
- `'record'`, `'accept'`, `'negative'`, `'pending'`, `'Informational'` and `'informational '`: each exit 1 with "carrier: lfm2-kilix-commands licence decision is not affirmative or informational"
- `''`: exit 1 with "CARRIER.env m_lfm2_kilix_commands_decision is empty or a placeholder"

The guard accepts only the affirmative and informational decisions and refuses everything else.

## 11. Pins

Command: `grep` for each key in `releases/0.2.3.env` and `releases/0.2.3.requirements`, `git ls-tree b0c8939b third_party/kilix-content` in kilix, and a read of the carrier fields. Output:

- `KILIX_REF`: env `b0c8939b05b7c2b6ffad9d90f10f0a31ec194a9a`
- `KILIX_LICENSE_REF`: env and requirements both `0984dd222bcb7f97859222b0dc2303b9225191fe`
- `KILIX_VOICE_REF`: env `1a4e63b11d0ad9c1664031e2773f5c4f5797913f`. Requirements has no such line (count 0), and neither did the approved `c1e3612` (count 0).
- `PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF`: env and requirements both `d57fa62f2393363284a29a6d4024e6f9dfa66ac4`
- `PLEBIAN_OS_VOICE_CARRIER_SHA256`: env and requirements both `bf003bf70e6059e3ec7b458ea4e7b26266383486825f361a472e7efc5f1f71ac`, the candidate carrier hash
- KILIX_REF gitlink: `160000 commit d57fa62f2393363284a29a6d4024e6f9dfa66ac4 third_party/kilix-content`
- carrier `interface_content_ref` `d57fa62f…`, `interface_licence_ref` `0984dd22…`, `voice_ref` `1a4e63b11d0ad9c1664031e2773f5c4f5797913f`

The gitlink, the carrier interface content ref and the env content ref are all equal, and the carrier binds the voice ref. The catalog's kilix-needle ref is `5cbff317` (check 5). `releases/0.2.3-command-model.json`, `CHANGELOG.md` and `releases/0.2.3-notes.md` now name `b0c8939b`, `d57fa62f` and `5cbff317`. The carrier's `COMMAND-MODEL.json` is generated from `provision/command-model.json`, which is unchanged, so its bytes are unchanged too. Claim 4 holds.

kilix-voice gate. `git grep` at `1a4e63b` found `CHECK_FLAG = "--check-licence"` in `voicelib/licensing.py`, and found the `--check-licence` argument and `_check_licence`, which calls `licensing.require_covering_receipt`, in `kilix-stt`. The only change since the approved `1faf9fb` in that file adds a second voice to `CHECK_TOOL_BY_MODEL`. Command: `PYTHONPATH=../kilix-license/src python3 -B -m unittest tests.test_weight_licence`. Output: `Ran 63 tests … OK`. The gate the speech DELIVERY sentences describe still exists.

## 12. Generator check

Command, from `work/plebian-os` at 71aceb8, against a writable copy `work/carrier-copy` of the candidate carrier, with `work/kilix-content` at d57fa62 and `work/kilix-license` at 0984dd22:

```
python3 -B build/generate-model-compliance.py --content-repo work/kilix-content --license-repo work/kilix-license \
  --determination kilix-diarization-cpu=work/carrier-copy/determinations/kilix-diarization-cpu/0.2.1-F104-CAMPP-WEIGHT-LICENCE.md \
  --determination lfm2-kilix-commands=work/carrier-copy/determinations/lfm2-kilix-commands/command-model-determination.json \
  --determination lgraph-en-us=work/carrier-copy/determinations/lgraph-en-us/OWNER-DETERMINATION-lgraph-en-us.md \
  --determination small-en-us=work/carrier-copy/determinations/small-en-us/OWNER-DETERMINATION-small-en-us-BUNDLED-20261105.md \
  --determination vibevoice-asr-bitnet=work/carrier-copy/determinations/vibevoice-asr-bitnet/OWNER-DETERMINATION-vibevoice-asr-bitnet.md \
  --determination vibevoice-asr-bitnet=work/carrier-copy/determinations/vibevoice-asr-bitnet/OWNER-RULING-C2-AMENDMENT-2026-09-29.md \
  --determination vibevoice-asr-bitnet=work/carrier-copy/determinations/vibevoice-asr-bitnet/OWNER-RULING-J1-J2-2026-09-25.md \
  --determination whisper-small-en=work/carrier-copy/determinations/whisper-small-en/OWNER-DETERMINATION-whisper-small-en.md \
  --determination whistle=work/carrier-copy/determinations/whistle/OWNER-RC6-WHISTLE-BUNDLED-20261105.md \
  --seat work/carrier-copy/seats/SEAT-A-KILIX-FIND-CONTENT-20261105.md \
  --seat work/carrier-copy/seats/SEAT-B-KILIX-FIND-CONTENT-20261105.md \
  --out work/carrier-copy --check
```

Output: nothing printed, `exit=0`. A later `diff -r` of the copy against the read-only candidate printed `copy-unchanged-by-check`. As a control, the same command on a second copy with `"informational"` replaced by `"affirmative"` in `lfm2-kilix-commands/LICENCE-RECORD.json` printed `carrier differs: lfm2-kilix-commands/LICENCE-RECORD.json` and exited 1.

## Known issues

1. Needle `5cbff317` `asset.py` line 180, in `_installed_spec`, still says the LFM2 licence "has not been accepted" when no receipt covers it. The Ask command-model runtime reaches that function through `commands_runtime.inspect_bundle`. Command: in a fresh cleared sandbox, `python3 -B -c "import commands_runtime; commands_runtime.inspect_bundle()"`. Output: `AssetError: the lfm2-kilix-commands licence has not been accepted; install it with: kilix-needle install --commands`. By the owner's decision LFM2's terms take no acceptance. The message describes the notice as something to accept, which is the kind of wording claim 1 says was removed from the non-terminal message. The line is unchanged from the approved Needle `8408183f` and the rejected `3a8e41c5`. The terms and records Needle serves are correct, and the command the message names leads to the correct notice screen (check 6). The defect is wording only and does not affect a record, receipt, pin or gate. A fix would phrase the message by the record's expected decision, as `content_models.py` now does in Kilix.

This session found no other defect. Every difference between the candidate and the rejected commits is one of claims 1 to 5 or a mechanical consequence of them, as noted in checks 6 and 9.

VERDICT: ship with known issues
