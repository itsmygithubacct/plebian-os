# Seat B review: Playalong default models carrier, round 5 (2026-11-09)

This is the seat B record for the Plebian-OS 0.2.3 RC5 model-compliance carrier, round 5. It replaces seat B's round-4 record. It reviews the candidate plebian-os ee97037e343ac0c474bdbb9bc319d17509f8a5cf and kilix c90d48efab8c79a0011c9737fa9747f22fe98837 against round 4's candidate (plebian-os 8f8af4fccd37070930ca546b6cc830d1808aefa4, kilix 9e58d31473d8de5ea12a6005afb18665fa0b6e2c). It also reviews them against the last seat-approved state, plebian-os 6942536f53743cd9bee35b41aea59de31a96b2ca (carrier 0e544b97).

Candidate CARRIER.json sha256, as this session computed it: 4fdbffce1f96882bbdc16724b3472895e10296ec603d1441249ff3a2e7470ebc.

DEFAULT-MODELS.json field "sha256", as this session read it in the candidate and approved carriers: e00614bf726154d09668820c061cbbcb402239a445bde666b0568d36f01528a6.

## Eligibility

This session is the one that wrote seat B's round-4 record. The builder session launched it with `kilix @ launch` at 2026-11-08T23:27:30Z. It wrote the round-5 brief at 2026-11-09T00:33:45Z. This session read the round-5 brief at 2026-11-09T00:34:01Z (`date -u`).

This session did not author the carrier, its generator, its determinations, the kilix-license record faster-whisper-large-v3, the distribution entries of demucs-htdemucs-6s and faster-whisper-medium-en, the kilix-content asset faster-whisper-large-v3, Kilix's config/playalong_models.py or its model-wizard change, Kilix Playalong's licensed model routes, Plebian-OS's image-model installer, its Demucs image archive, its remaster, preseed or carrier-guard changes, or the round-3 wording fixes. It did not author either round-5 fix (kilix c90d48ef, plebian-os ee97037e). The builder sessions wrote them. This session is eligible.

The round-4 rules still applied. The review was read-only, and every clone, scratch tree and command was inside this seat's `work` directory. Kilix, kilix-content, kilix-license, Kilix Playalong and plebian-os code ran under `env -i` with HOME, TMPDIR, KILIX_STORAGE_HOME, KILIX_DATA_HOME (inside KILIX_STORAGE_HOME), GPU_TERMINAL_HOME, GPU_TERMINAL_SETTINGS_FILE, KILIX95_STATE_HOME and KILIX_LICENSE_RECEIPTS pointed inside it, with a fresh tree per scenario. This session did not read the other seat's directory or records. Nothing was committed, pushed or published, no ACCEPTANCE.json was written, no licence was accepted outside `work`, and no agent was started. The installer's command-model cache was this session's copy of the pinned LFM2 archive, inside `work` (1362204317 bytes, sha256 ea03c42c…, checked against provision/command-model.json).

## What round 4 missed

Seat B's round-4 check (e) ran an online upgrade with no network and saw the failed downloads reported and exit 0. It did not run the next upgrade on that state. This session has now run that next upgrade with 8f8af4f's installer, in steps A2b, B3 and B4 below. It exits 1 with kilix-content's InstallError from `_installed`, exactly as seat A's round-4 record found. Because plebian-os-update.sh calls the installer under `|| die`, every later upgrade on that machine would have failed. The round-4 medium.en DELIVERY sentence "A failed download installs nothing, and the next upgrade tries again." was false of 8f8af4f. Seat B's round-4 verdict should not have been "ship with known issues" on that point.

## The delta

- `git log 9e58d314..c90d48ef` (kilix): one commit, c90d48e "Decline Playalong's defaults on a refused licence, not on large-v3 alone", parent 9e58d314. It is on the origin branch. `git diff --stat` lists README.md, config/model_wizard.py, config/playalong_models.py and tests/test_playalong_models.py, and nothing else. `git diff --quiet 9e58d314 c90d48ef` returned 0 for config/kilix_sdk, config/content_models.py, config/default_models.py, scripts and third_party. The content gitlink is still c8f0b0f51966925c5872c70c246434cce6784982. The voice installer and the medium.en patcher are untouched.
- `git log 8f8af4fc..ee97037e` (plebian-os): one commit, ee97037 "Retry Playalong defaults after a failed download, and pin Kilix c90d48ef", parent 8f8af4fc. It is on the origin branch. `git diff --stat` lists CHANGELOG.md, provision/install-image-models.py, releases/0.2.3-command-model.json, releases/0.2.3-notes.md, releases/0.2.3.env, tests/test_image_models.py and tests/test_model_compliance_carrier.py. `git diff --quiet 8f8af4fc ee97037e` returned 0 for releases/0.2.3-model-compliance, build, preseed, provision/demucs-model.json, provision/playalong-models.json, provision/bundles, provision/plebian-os-update.sh, provision/plebian-os-provision.sh, provision/command-model.json, releases/0.2.3.requirements and tests/test_mixed_model_delivery.py.
- The installer: an AST comparison of 8f8af4f and ee97037e printed `changed functions: ['_install_from_image', 'install_demucs', 'install_whisper_medium'] added: ['_playalong_installed'] removed: []`. In each of the three, the one change is `_installed(` to `_playalong_installed(`. `_playalong_installed` returns `_installed(cm, asset_id)`. On `cm._api().InstallError` it prints "<asset> is not completely installed (…); installing it again." to stderr and returns False. install_command_model still calls `_installed`.
- The pins: releases/0.2.3.env changes KILIX_REF to c90d48ef and its comment. releases/0.2.3-command-model.json changes source_pins.kilix to c90d48ef. The notes' pin table and the CHANGELOG follow. The notes and CHANGELOG also describe the retry and the refused-licence decline. Nothing else changes.
- Tests: test_image_models.py adds three tests. Its one removed line, `api = SimpleNamespace(Installer=Installer)`, becomes the same line with an InstallError class added to the fake. test_model_compliance_carrier.py's AC-8 adds the retry checks and two plants. The two removed lines in that file are a docstring line and the closing of the plant tuple, extended. The kilix test file removes nothing and adds seven tests.
- The carrier: `diff -r` of releases/0.2.3-model-compliance at ee97037e against the round-4 candidate copy printed nothing (rc 0), including seats/ and ACCEPTANCE.json. `sha256sum CARRIER.json` printed 4fdbffce1f96882bbdc16724b3472895e10296ec603d1441249ff3a2e7470ebc. CARRIER.json binds no KILIX_REF.

Every difference is one the claim names (1 and 2) or a mechanical consequence of them.

## Results that the delta leaves unchanged

These are round-4 results. In each case, this session confirmed above that the delta does not touch the files involved.

- Required identities. These were checked in round 4 and live in files the delta does not change (the carrier, kilix-license f8486ed3, kilix-content c8f0b0f5, provision/demucs-model.json).
  - Approved CARRIER.json is 0e544b97…. The exported carriers equal their repositories.
  - The LFM2 notice record is e4d08e2c53ab514e1e2ca2a812c64895519487d707c441703978bd0f245b5016, decision `record`, unchanged between 80aab439 and f8486ed3.
  - Upstream large-v3 at edaa852e: model.bin 3087284237 bytes, LFS oid 69f74147…. This session fetched README.md (2052, 39e96252…, with `license: mit` at line 106), config.json (2394, a9306624…), preprocessor_config.json (340, 7ccc62c6…), tokenizer.json (2480617, 6d8cbd7c…) and vocabulary.json (1068114, c69260f2…). Each equals the record's pin.
  - Demucs weights downloaded by this session: 54996327 bytes, 34c22ccb381c6f9fdbf324f04e1e2fe21aaaf293f5ded163a162697ff9a02ddd.
  - Demucs LICENSE at eeac1d15: 1087 bytes, cf9b17822d1fcd4ff32ccbe14183386fb3adf6f2ff92dc184130823f7fc28173.
- The Demucs image archive: rebuilt this round with ee97037e's `--build-demucs-archive` from this session's download. It printed 55009280 bytes, sha256 904731cf2e086256a4d3fe98f755bb74b07b4624929617607b697627ad365c2b, and `cmp` with the round-4 build printed nothing. build_demucs_archive is not among the changed functions. Round 4 showed two identical builds; members models/5c90dfd2-34c22ccb.th (54996327) and notices/LICENSE-mit.txt (1087, byte-identical to the upstream LICENSE), ustar, mtime 0, owner 0/0. The remaster chain (early check of a supplied archive, else a bounded download from the pinned URL, build, second check, then staging) and preseed's copy to /usr/local/share/plebian-os are unchanged.
- Claim 6, the carrier: it is unchanged from round 4. That review found five CARRIER.json changes against 0e544b97: bindings_sha256, interface_content_ref, interface_licence_ref, whisper-medium-en delivery and licence_record_file_sha256. It found the changed and added files as claimed, and no Demucs, Basic Pitch or large-v3 entry.
- kilix-license f8486ed3: the large-v3 record ee7369d9417178ee39b23d23f5159d602207d37816adba336a039866992cb172 is generated from the pinned determination, with medium.en's terms. The owner record is named by path, 3218 bytes and 8d8c1cf3…, which match the owner's file. The distribution entries name the owners' files: Demucs 2683 bytes 70c4baa8…, medium 2515 bytes 6798bb89…, both matching. No record digest moves: Demucs 02f182d7…, medium c33e44c1…. The kilix-license tests pass. In this session's seven mutations (owner_record removed or altered, revision altered, a file dropped, a distribution entry removed or altered) each generator refused, and the unmodified control generated ee7369d9….
- kilix-content c8f0b0f5: the vendored kilix-license equals f8486ed3. The catalog adds only faster-whisper-large-v3 and moves the Playalong ref. The large-v3 asset's files and six fetch URLs are the pinned revision's. The targeted tests pass.
- Kilix Playalong a11a0219: no code path downloads model weights. Each provider runs `kilix models verify` immediately before its worker and hands it that directory; the workers run offline.
- Large-v3 is in no default route: not in provision/playalong-models.json, Kilix's DEFAULT_MODELS, DEFAULT-MODELS.json or the image. The wizard's Playalong page pre-selects Basic Pitch, as `pages()` printed again this round (`default row: basic-pitch-icassp-2022-onnx`). `kilix models install faster-whisper-large-v3` refuses without a terminal and asks `[y/N]` in one; an answer of n wrote no receipt.
- LFM2: the asset and licence records are unchanged across both ranges. install_command_model and its helpers are unchanged (above). The command model's behaviour is re-run below.

## Seat A's sequence, re-run

These runs used the real Kilix at c90d48ef with its content submodule at c8f0b0f5, and the installer CLI as plebian-os-update.sh runs it (`install-image-models.py --kilix KILIX`). The one addition is `--command-cache` pointing at this session's copy of the pinned archive. "No network" means `unshare -rn`.

Chain A (medium.en):

- A1, fresh offline install (`--offline --demucs <archive>`), no network: Basic Pitch, Demucs and the command model were installed, and it printed "Whisper medium.en is not in the image; the first online upgrade downloads it.", rc=0.
- A2, online, no network: "Whisper medium.en was not installed (offline: …); the next upgrade tries again.", rc=0. The medium.en receipt c33e44c1… was left with no asset directory.
- A2b, 8f8af4f's installer on that state: rc=1, ending with `kilix_content.install.InstallError: could not open supplied file: …/faster-whisper-medium-en/README.md`, raised from `_installed` in install_whisper_medium.
- A2c, ee97037e's installer on the same state, no network: "faster-whisper-medium-en is not completely installed (could not open supplied file: …README.md); installing it again." It then reported the failed download, rc=0.
- A3, ee97037e online with network: it printed the same retry note and "Whisper medium.en installed: faster-whisper-medium-en", rc=0. `content_models.py verify faster-whisper-medium-en` printed `faster-whisper-medium-en`.
- A4, a further run: "already verified" for Basic Pitch, Demucs, the command model and Whisper medium.en, rc=0.

Chain B (Demucs, image archive absent, then supplied):

- B1, fresh offline with no archive: "Demucs: the installation media did not supply its archive; the first online upgrade downloads it.", rc=0.
- B2, online, no network: both downloads were reported as not installed, rc=0.
- B3, 8f8af4f's installer on that state: rc=1, `InstallError: could not open supplied file: …/demucs-htdemucs-6s/models/5c90dfd2-34c22ccb.th`.
- B4, 8f8af4f's installer with `--demucs <archive>` on that state: also rc=1, the same error.
- B5, ee97037e with `--demucs <archive>`, no network: "demucs-htdemucs-6s is not completely installed (…); installing it again." It then installed Demucs from the archive ("reading 1 supplied file(s) for demucs-htdemucs-6s …", "Demucs installed"), reported the medium.en download failure, rc=0.
- B6, a further run: "Demucs already verified", rc=0.

Chain C (Demucs over the network, and offline after a failure):

- C1, fresh offline with no archive: rc=0.
- C2, online with no network: rc=0, both downloads failed.
- C2b, `--offline` on that failed state, traced with strace for connect: the two retry notes, then the two deferral messages, rc=0, and `inet connects in C2b: 0`.
- C3, ee97037e online with network: the two retry notes, "Demucs installed: demucs-htdemucs-6s" and "Whisper medium.en installed: faster-whisper-medium-en", rc=0. The installed weights hash to 34c22ccb…. `content_models.py verify` printed `demucs-htdemucs-6s` and `faster-whisper-medium-en`. The standard-policy receipts were the ones written before C2's download attempts, and C3 wrote no new receipt file.
- C4, a further run: all four already verified, rc=0.

Chain D (command model):

- D1, fresh offline install. Then this session removed notices/NOTICE.txt from the installed LFM2 asset and kept its receipt.
- D2, ee97037e: rc=1, `kilix_content.install.InstallError: could not open supplied file: …lfm2-kilix-commands--…/notice…`.
- D3, 8f8af4f: rc=1, the same.
- D4, 6942536f: rc=1, the same.

The command model still stops on an incomplete install, as at 6942536f. Only the Playalong defaults retry.

From round 4, still valid because their code paths are unchanged: an online run on a fresh machine writes each standard-policy receipt before its download (the trace showed each receipt's rename before the first port-443 connect). A catalog manifest that differs from provision/playalong-models.json is refused (rc=1) before that asset's receipt.

## The wizard and declined()

The scenarios below used the real `pages`, `apply` and `finish` from config/model_wizard.py at c90d48ef, a stubbed licence step (`consent_and_install` returning the refused set), and a fresh state tree each. The "exit" is `python3 config/playalong_models.py declined`'s status (0 declined, 3 not declined, 4 unreadable).

- W1, seat B's round-4 case (only large-v3 chosen on the Playalong page, its licence refused): saved `{'answer': 'no', 'models': [], 'phase': 'complete', 'refused': ['faster-whisper-large-v3']}`, `declined(): None`, exit 3. The installer run offline on this state installed Basic Pitch, Demucs and the command model and deferred medium.en, rc=0. The defaults now install.
- W2, Basic Pitch's licence refused with large-v3 accepted: saved answer `yes`, models `['faster-whisper-large-v3']`, `refused: ['basic-pitch-icassp-2022-onnx']`. It printed `declined(): the model wizard refused the licence of basic-pitch-icassp-2022-onnx`, exit 0. The installer printed "Playalong's default models skipped: the model wizard refused the licence of basic-pitch-icassp-2022-onnx", installed only the command model, rc=0.
- W3, medium.en's licence refused on the dictation page: `refused: ['faster-whisper-medium-en']` on the dictation page, declined, exit 0.
- W7, Demucs's licence refused on the kilix-split page: declined, exit 0.
- W4, the Playalong page answered no: `declined(): the model wizard's Playalong page was answered no`, exit 0.
- W8, large-v3 refused, then the page re-answered no: the explicit no replaces the entry and its refusals, declined, exit 0.
- W5, KILIX_PLAYALONG_MODELS=0 with an untouched wizard: declined, exit 0.
- W6, a malformed refusal list (a string): `declined() raised ValueError Invalid saved wizard answer.`, exit 4. The installer printed "skipped: whether this machine declined them cannot be read (Invalid saved wizard answer.)" and installed only the command model.

`python3 -m unittest -v tests.test_playalong_models tests.test_model_wizard` at c90d48ef ran 59 tests, OK. These include the seven new ones: refusals on the page, on another page and on a page that ends yes, a large-v3-only refusal, a page with no refusal, a page no, and an unreadable refusal.

declined() against the owner's opt-out words, "Skip the install if the wizard says no or if settings.conf sets the key to 0":

- The setting and a user's "no" on the Playalong page decline as before.
- A refused licence of one of the three defaults, on any wizard page, now also declines all three. This session reads that as the wizard saying no to that model's terms. It keeps a default install from writing a standard-policy receipt for terms the user refused.
- A page "no" that the licence step wrote only because the user refused large-v3's licence no longer declines. This matches the owner's "Both" choice, under which large-v3 is optional.
- Every new branch can only decline or raise. None installs more than round 4 did.
- One consequence is broader than the owner's words name: refusing medium.en for dictation alone, or Demucs on the kilix-split page, also skips Demucs and Basic Pitch. That follows the owner's all-or-nothing opt-out. It never installs anything without a yes, so this session does not count it as a defect.

## The medium.en DELIVERY at ee97037e, sentence by sentence

- "mode: playalong-default-upstream-download": the carrier's mode.
- "This model's weights are not present in the image or downloaded by provisioning.": true. The image stages no medium.en, and provisioning passes `--offline`, which made no connect in C2b.
- The default-install sentence (an online upgrade downloads it from the pinned upstream host and verifies it before installation): true by A3 and C3.
- "The upgrade first records a local standard-policy receipt; build-time receipts are never distributed.": true. The receipt precedes the download (round-4 trace, unchanged code), and none is in the image.
- The opt-out sentence ("It is not installed when the model wizard's kilix-playalong page was answered no, or when KILIX_PLAYALONG_MODELS=0 is set in the shared settings file."): true when the user answers the page no (W4, W8) and for the setting (W5). It is no longer the whole list: a refused default licence on any page also declines (W2, W3, W7). And when the user answered the page yes and the licence step recorded "no" only for large-v3 (W1), the saved answer reads "no" while medium.en is installed. This session reads "was answered no" as the user's answer, so the sentence states no false case. It is incomplete, and is listed as a known issue below.
- "A failed download installs nothing, and the next upgrade tries again.": now true. A2 then A3, B2 then B5, and C2 then C3 each show the failed run installing nothing and the next run retrying to a verified install, where 8f8af4f exited 1 (A2b, B3, B4).
- "A user can also install whisper-medium-en directly.": true.
- The receipt-gate, catalog, kilix-voice 1a4e63b and patcher sentences: unchanged and true. The patcher exists at KILIX_REF c90d48ef, and AC-8 asserts it there.

## AC-8

- At ee97037e, called directly, playalong_installer_gaps returned `[]`, command_installer_gaps `[]` and delivery_gaps `[]`.
- On 8f8af4f's installer, playalong_installer_gaps returned four gaps:
  - "_install_from_image does not retry an install a failed download left incomplete"
  - "install_demucs does not retry an install a failed download left incomplete"
  - "install_whisper_medium does not retry an install a failed download left incomplete"
  - "an install a failed download left incomplete stops the next upgrade"
- `python3 -m unittest -v tests.test_model_compliance_carrier`: test_delivery_statement_is_true_of_this_image ok. Its plants, now six Playalong and three command-model ones plus the patcher-stripped DELIVERY, are each asserted caught in the test. All other tests pass except AC-7.
- `python3 -m unittest tests.test_image_models tests.test_mixed_model_delivery`: 46 tests, OK. This includes test_the_upgrade_after_a_failed_download_downloads_again, test_an_incomplete_image_model_is_installed_again_from_the_image and test_the_command_model_still_stops_on_an_incomplete_install.

Defects planted by this session in scratch worktrees, each restored afterwards (`restored True`):

- Kilix, against test_playalong_models and test_model_wizard:
  - K1, a refused default licence does not decline: caught by the three refusal tests.
  - K2, a large-v3-only refusal declines again: caught by test_refusing_only_large_v3s_licence_declines_nothing.
  - K3, a malformed refusal list accepted: caught by test_an_unreadable_refusal_is_never_read_as_install.
  - K4, finish() drops refusals on a page that ends yes: caught by test_refusing_a_default_licence_declines_even_when_the_page_ends_yes.
- plebian-os, against test_image_models, test_mixed_model_delivery and AC-8:
  - P9, install_demucs back on `_installed`: caught by AC-8 and test_the_upgrade_after_a_failed_download_downloads_again.
  - P10, an incomplete install read as installed (returns True): caught by AC-8, test_an_incomplete_image_model_is_installed_again_from_the_image and test_the_upgrade_after_a_failed_download_downloads_again.
  - P11, the image route back on `_installed`: caught by AC-8 and test_an_incomplete_image_model_is_installed_again_from_the_image.
  - P12, the retry catching every exception: caught by AC-8 only.

## Pins

- releases/0.2.3.env: KILIX_REF c90d48efab8c79a0011c9737fa9747f22fe98837. `git ls-tree c90d48ef third_party/kilix-content` printed c8f0b0f51966925c5872c70c246434cce6784982. That equals the carrier interface_content_ref and PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF (c8f0b0f5…, in env and requirements).
- KILIX_LICENSE_REF f8486ed3df562bd512b0d948494c76b7e7ae0349 in both files, equal to interface_licence_ref.
- PLEBIAN_OS_VOICE_CARRIER_SHA256 4fdbffce… in both, equal to the candidate CARRIER.json sha256. PLEBIAN_OS_VOICE_CARRIER_RECEIPT_SHA256 89e5abff… in both, which is regenerated after review.
- KILIX_VOICE_REF 1a4e63b1… is unchanged. releases/0.2.3.requirements carries no KILIX_REF and is unchanged.
- releases/0.2.3-command-model.json source_pins: kilix c90d48ef, kilix-content c8f0b0f5, kilix-license f8486ed3, kilix-needle a887e2fa, kilix-needle-runtime 4f3aeaff; manifest revision c8f0b0f5. The notes' table shows KILIX_REF c90d48ef. The env comment says KILIX_REF advanced from 9e58d314, the previous pin.

## Generator check

From plebian-os ee97037e, against this session's kilix-content (HEAD c8f0b0f51966925c5872c70c246434cce6784982) and kilix-license (HEAD f8486ed3df562bd512b0d948494c76b7e7ae0349), on a fresh writable copy of the candidate carrier, this session ran:

`python3 build/generate-model-compliance.py --content-repo <kilix-content> --license-repo <kilix-license> --out <copy> --check`

It passed eleven `--determination MODEL=PATH` and two `--seat PATH` arguments, in sorted path order (26 arguments). The command printed nothing and returned 0. In round 4 the same check returned 1 on a one-byte change to the copy's medium DELIVERY, and the generator is unchanged.

## Full plebian-os suite

`python3 -m unittest discover -s tests`, with the seven PLEBIAN_OS_*_REPO variables pointing at this session's clones (kilix at c90d48ef):

- ee97037e: `Ran 1434 tests`, `FAILED (failures=9, skipped=5)`.
- 8f8af4f: `Ran 1431 tests`, `FAILED (failures=9, skipped=5)`.

Comparing the two failure lists, no failure is only in ee97037e, and none is only in 8f8af4f. Both have AC-7 (test_acceptance_receipt_names_two_independent_seats, expected until the receipt names this round's seats). Both also have the eight that failed at 6942536f in round 4 too:

- test_ollama_carrier_wrappers (two tests)
- test_voice_release_contract's RELEASING.md subtests (four)
- test_build_vm_image's two selected-closure gate tests

The candidate introduces no new failure.

## Declared items

- Seat B's round-4 issue 2, the Demucs upgrade sentence: still a defect of wording, and it does not block. determinations-demucs.json `distribution.upgrade` in kilix-license f8486ed ("An online upgrade downloads the weights from the pinned URL."), and the owner's distribution record, say the upgrade downloads. The installer takes the image's archive whenever the machine has one (B5 shows it after a failed download too) and downloads only when it does not. Bytes, sha256, licence text and receipt are identical on both routes. The release notes and CHANGELOG state the condition correctly.
- Seat A's known issue 2 (provisioning always runs offline, so an online setup gets medium.en at its first online upgrade): this session does not count it as a defect, and it does not block. The owner's question at 12:27:04Z began "A fresh ISO install provisions offline." The distribution records say the offline provisioning of a fresh install does not download medium.en, and the DELIVERY says provisioning does not. The user-run setup routes (`kilix-playalong models install`, `kilix stt --install whisper-medium-en`) fetch it on demand after their licence screens. If the owner meant "setup" to include an online first provisioning, that is a question for the owner, not a mismatch with the records.
- Seat A's observations: this session did not read seat A's records, as the brief requires. The brief does not restate them, so this session cannot assess them one by one. Every check this session made of the areas named in this brief is above.

## Known issues found by this session

1. The opt-out wording is narrower than the candidate's decline rule. The medium.en DELIVERY's opt-out sentence, the `declined_by` lists of both distribution entries in kilix-license f8486ed, and the owners' distribution records name only "the kilix-playalong page answered no" and "KILIX_PLAYALONG_MODELS=0". From c90d48ef, a refused licence of any of the three defaults on any wizard page also declines all three. A saved Playalong "no" whose refusals are only large-v3's does not decline (W1). No sentence describes a case where something is installed that the user refused, and every difference installs less. AC-8 and the generator pin the DELIVERY text, so a wording change would need a carrier round. It does not block.
2. Seat B's round-4 issue 2, declared above, remains.

Seat B's round-4 issue 1 (a large-v3-only refusal declined all three defaults) is fixed: W1 and the installer run on W1's state. Seat A's "do not ship" finding, the failed next upgrade, is fixed at ee97037e and caught by AC-8 and three new tests: A2b, B3 and B4 against A2c, A3, B5 and C3.

No required identity, record, determination, delivery statement, pin or receipt gate failed to match. No install route this session ran or read serves terms or records other than the owner's decisions and the carried ones.

VERDICT: ship with known issues
