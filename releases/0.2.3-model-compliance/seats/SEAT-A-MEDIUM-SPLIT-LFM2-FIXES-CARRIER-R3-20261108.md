# Seat A review: Whisper medium, kilix split, LFM2 fixes carrier, round 3 (2026-11-08)

This is the seat A record for the Plebian-OS 0.2.3 RC5 model-compliance carrier, round 3. It reviews the candidate plebian-os 89e0626b606b45c3c1e88f32b3ceea46b719df9b against the last seat-approved state, plebian-os 4034dde27ee1a34d2dbc5ca2e6fd5d9e5a5b0e28.

Candidate CARRIER.json sha256, as this session computed it: 0e544b976dad4a67e0bb0d6d9dbb4407b028782a493bde360a9cfa1ba767ead7.

DEFAULT-MODELS.json field "sha256", as this session read it in both carriers: e00614bf726154d09668820c061cbbcb402239a445bde666b0568d36f01528a6.

## Eligibility

The builder session launched this pane with `kilix @ launch` at 2026-11-08T21:40:26Z and wrote the brief. This session's first command ran at 2026-11-08T21:40:42Z (`date -u`). This session did not author the carrier, its generator, its determinations, the kilix-license records faster-whisper-medium-en or demucs-htdemucs-6s, the kilix-content assets faster-whisper-medium-en or demucs-htdemucs-6s, the Kilix voice patcher, `kilix transcribe`, `kilix split`, the Needle wording change, the Kilix voice-installer default, or the plebian-os test fixture change. Two builder sessions wrote them. This session is eligible.

The review was read-only. Everything was cloned into, and every command ran inside, this seat's `work` directory. Kilix, kilix-content, kilix-license, Needle and plebian-os code ran under `env -i` with HOME, TMPDIR, KILIX_STORAGE_HOME, KILIX_DATA_HOME (inside KILIX_STORAGE_HOME), GPU_TERMINAL_HOME and KILIX_LICENSE_RECEIPTS set to fresh directories inside `work`. This session did not read the other seat's directory, the builders' notes, or any earlier seat record outside the carriers. It committed nothing, pushed nothing and published nothing. It wrote no ACCEPTANCE.json and accepted no licence anywhere. One log file landed outside `work`, in this seat's own directory, after a failed `cd` in a background shell. It held only the line "exit 1", and this session deleted it. Below, `<work>` stands for this seat's work directory.

## Sources and identities

All named commits exist in fresh public clones (`git cat-file -t` printed `commit` for each). The branch tips are plebian-os work/0.2.3-rc5-transcribe-20261107 = 89e0626b; kilix-content same branch = de2764f8; kilix-license same branch = 80aab439; kilix same branch = 4b9f29cf; kilix-needle work/0.2.3-rc5-ask-20261107 = a887e2fa. Each approved commit is an ancestor of its candidate (`git merge-base --is-ancestor`).

- `sha256sum` of the two seat-input CARRIER.json files printed 0e544b976dad4a67e0bb0d6d9dbb4407b028782a493bde360a9cfa1ba767ead7 (candidate) and bf003bf70e6059e3ec7b458ea4e7b26266383486825f361a472e7efc5f1f71ac (approved). Both match the brief.
- `git archive 89e0626b releases/0.2.3-model-compliance` and `git archive 4034dde2 ...` are byte-identical to the candidate and approved seat-input carriers (`diff -r` printed nothing for either).
- DEFAULT-MODELS.json is the same file in both carriers (file sha256 90ee0d64...a0f0). Its "sha256" field reads e00614bf726154d09668820c061cbbcb402239a445bde666b0568d36f01528a6 in both.
- The candidate carrier's SHA256SUMS (69 lines) and BINDINGS.sha256 (64 lines) verify with `sha256sum -c`. Every file outside seats/ is listed in SHA256SUMS. BINDINGS.sha256 hashes to 940814266f3f6364e04058aa375d758c1836be3f5f8d7cc8e037058f877aff56, which is CARRIER.json's bindings_sha256.
- The upstream model repository's API tree for faster-whisper-medium.en at a29b04bd15381511a9af671baec01072039215e3: model.bin size 1527904330, LFS oid 11b220779aea4c6f3ce9d2549c8a95ea869ed84066864b999531ef53e594fe5b. This session downloaded the four other files from the pinned revision and hashed them: config.json 2643 bytes 4a1848eb...7c62; tokenizer.json 2128466 bytes 929c5252...2df; vocabulary.txt 422309 bytes ff775887...15cf; README.md 1337 bytes ab3ddd3b...7675, with line 7 `license: mit`. All equal the brief.
- adefossez/demucs at eeac1d15891af95b1288d2884b95baa3e5baa96c, using `git cat-file -s` and `git show | sha256sum`: LICENSE 1087 bytes cf9b17822d1fcd4ff32ccbe14183386fb3adf6f2ff92dc184130823f7fc28173 (its copyright line names the record's licensor). README.md 59ab8a3595cd5ec8dd853821ca2b377804f397be8467a082920f1c44e0d59d35, line 320 "Demucs is released under the MIT license as found in the [LICENSE](LICENSE) file.". demucs/remote/files.txt 7258eee911e5963e6270983d7072832e90e1ed96b25bb26aadf12f9867109bf9, line 32 `5c90dfd2-34c22ccb.th`. demucs/remote/htdemucs_6s.yaml 21 bytes 207405151270af8fd81c2373c25d27950916682ac91dca7884a11ce13dad6f58, reading `models: ['5c90dfd2']`. Commit 25dada5a68a7ceecd831a113e5712512312e4a3f (2020-04-13, "... + MIT license") exists and is an ancestor of eeac1d15. All equal the brief.
- This session downloaded the weights file at the URL the brief names (path demucs/hybrid_transformer/5c90dfd2-34c22ccb.th) itself. `stat -c %s` printed 54996327 and `sha256sum` printed 34c22ccb381c6f9fdbf324f04e1e2fe21aaaf293f5ded163a162697ff9a02ddd. Both equal the brief.

## Claim 1: kilix-license 0984dd22 to 80aab439

`git diff --name-status 0984dd22 80aab439 -- src/kilix_license/data` lists six added data files and no changed one: demucs-records/demucs-htdemucs-6s.json, determinations-demucs.json and .sha256, determinations-whisper-medium.json and .sha256, and whisper-medium-records/faster-whisper-medium-en.json. The other changes are mechanical consequences: two generator modules (whisper_medium.py, demucs.py), the two new directories added to catalog.py's record search and to pyproject package-data, tools/generate_records.py calling the new generators, the CHANGELOG, and tests. No licence text is added. The Demucs MIT text cf9b1782... was already in data/texts.

- Pins: `sha256sum determinations-whisper-medium.json` printed a5bb89f07a696c1535ec7636cabc67d453aa248b3e8824a802391c26b801534a, which equals its .sha256 file. `sha256sum determinations-demucs.json` printed 994295eecca22640aac82e2f69e24ceb6e8bbf67e987e93b63babbee23e219df, which equals its .sha256 file.
- Regeneration: `generate_whisper_medium_records` and `generate_demucs_records`, run on the pinned data, rendered bytes equal to the committed record files (`render_record_bytes(...) == file` printed True for both). The digests were faster-whisper-medium-en c33e44c18901aa5802f668f733a12f5d39ed63436c5a0eaa96c6eea874e1ae23 and demucs-htdemucs-6s 02f182d709f425adce6d8bb3d69b13aab3e2f976bd8aaf32b3b8eab6c04ae75b, as claimed. `python3 -B tools/generate_records.py --check` printed "records 30 match generator" and "application records 4 match generator".
- No existing digest moves: this session listed every determined record's id, digest and decision class at both commits. `diff` showed exactly two added lines (the two new records) and nothing changed or removed. lfm2-kilix-commands is e4d08e2c53ab514e1e2ca2a812c64895519487d707c441703978bd0f245b5016 at both commits, decision class informational, `expected_decision` "record". `git diff --quiet 0984dd22 80aab439 -- data/lfm2-records lfm2.py data/determinations-lfm2*` returned 0.

## Whisper medium

- The carried whisper-medium-en/LICENCE-RECORD.json is byte-identical to kilix-license 80aab439's whisper-medium-records/faster-whisper-medium-en.json (`cmp` printed nothing). Its sha256 is 0d072d477bf34bce7aac9cf5836eb0bc7ebe46ba39c37a94e4860fe326b2ca7d, which equals licence_record_file_sha256 in CARRIER.json. Its digest, c33e44c1..., is the one the pinned determination generates.
- The carried whisper-medium-en/ARTIFACT.json (sha256 88a6ed22a999cf822433a5cd1b4fe132b2faaac497de722161427d0c02d67fb5) equals the canonical JSON of the faster-whisper-medium-en asset in kilix-content de2764f's catalog: as parsed JSON (True) and as exact bytes (True).
- Upstream identities: the four upstream files in the determination's authority list, and the five in the asset (the four plus README.md), carry exactly the sizes and sha256 values listed above. Every fetch URL is a /resolve/a29b04bd... URL on the upstream host that the provenance names. The determination records card_sha256 ab3ddd3b... and card_licence_line "license: mit". The record is MIT with the record's two licensors, decision affirmative, and the same licence text, copyright statement and model-card advisory that faster-whisper-small-en carries.
- Determination file: carried determinations/whisper-medium-en/OWNER-DETERMINATION-whisper-medium-en.md is 2392 bytes, sha256 6ac0416bdb3f9bb23da7acd57af79055b70ba8b02766891e6abef97eb21b9940. That is exactly the owner_record (path licence-evidence-whisper-medium-en-2026-11-07/..., bytes 2392, sha256 6ac0416b...) that determinations-whisper-medium.json cites. The file says who determined (the owner), when (2026-11-07 at 22:38:59Z), what (MIT, the record's two licensors, first-use download, never shipped) and in which words: verbatim, "New medium record (Recommended)", with the option text shown. This is the owner's decision as the brief states it. The file also says openly that carrying the model-card advisory is the builder's reading of the small.en precedent, not words of the owner. That advisory is shown, not a binding term. It is in the carried record, so it is no term beyond the carried ones.
- Patcher: this session extracted kilix 4b9f29cf's scripts/patch-whisper-medium-model.py and ran it on a `git archive` of kilix-voice 1a4e63b11d0ad9c1664031e2773f5c4f5797913f. It printed "whisper-medium-en added under <work>/kv-patched" and exited 0. It changed only voicelib/licensing.py, models.py and stt.py. A second run was idempotent (exit 0). With the patched tree on PYTHONPATH:
  - `[m.catalog_id for m in models.MODELS]` printed ['small-en-us', 'lgraph-en-us', 'vibevoice-asr-bitnet', 'whisper-small-en', 'whisper-medium-en', 'whistle']. whisper-medium-en sits between whisper-small-en and whistle.
  - Its ModelSpec has engine whisper, size=1530459085 and runtime_supported=True.
  - `licensing.licence_record_id('whisper-medium-en')` and `licensing.content_asset_id('whisper-medium-en')` both printed faster-whisper-medium-en.
  - In the patched kilix-stt, `model_install_argv` printed ['models', 'install', 'faster-whisper-medium-en'] after the launcher, and `runtime_install_argv` printed ['voice', 'whisper']. `install_model` skips its own receipt check only for content-stored models, because `kilix models install` is the licence screen. The install route hands the download to the model catalog and fetches no weights itself, as DELIVERY says.
  - The unpatched 1a4e63b library has no whisper-medium-en (`'whisper-medium-en' in models.MODEL_BY_ID` printed False).
  - The src gitlink moves to terminal-source commit 04c3528c, a descendant of 89db565a whose only change ("Offer whisper-medium-en as a Kilix dictation model.") adds the same id, 1530459085 bytes, the same four files and the faster-whisper-medium-en content directory.
- Provisioner and image: the patched `kilix-stt --models --json` printed the whisper-medium-en row with download_bytes 1530459085, download_size "1.4 GiB" and engine whisper. The provisioner's validate_voice_model_catalog list (provision/plebian-os-provision.sh line 6285) and build/build_vm_image.py (line 1617) both carry ("whisper-medium-en", "whisper", True, 1530459085, "1.4 GiB", ("model.bin", "config.json", "tokenizer.json", "vocabulary.txt")). These are the patched catalog's bytes and its whisper engine's required files. test_whistle_release's test_pinned_voice_catalog_passes_provision_and_vm_acceptance feeds the patched JSON through both consumers, and it passed. The speech-weight census (provisioner voice_dictation_asset_paths and build_vm_image SPEECH_WEIGHT_PATHS) adds voice/models/whisper-medium-en and desktop-apps/assets/faster-whisper-medium-en. The five test_speech_weight_census tests passed.

## Demucs

- The kilix-license demucs-htdemucs-6s record (digest 02f182d7...) is what the pinned determinations-demucs.json generates (bytes equal, above). Its licence text cf9b1782... is byte for byte the upstream LICENSE at eeac1d15. Its licensor is the copyright holder that LICENSE names, licence MIT, decision affirmative, with no advisories, statements, components or binding conditions. The determination's authority records the README sha256 and the README licence line, the files.txt sha256 and line, the bag definition, and the relicensing commit 25dada5a. All equal the upstream values above.
- Owner record: the owner's file at /home/pleb/research/gpu_terminal/licence-evidence-demucs-htdemucs-6s-2026-11-08/OWNER-DETERMINATION-demucs-htdemucs-6s.md is 3506 bytes (`stat`), sha256 c58b90a793b5a0866253d5351de0cc61000f05835daf6736a0ae3a2e2e22def0. That matches the determination's owner_record path (relative to the evidence parent), bytes and sha256. The file says who (the owner), when (2026-11-08 at 12:31:18Z) and what (MIT, the record's licensor, first-use download, never shipped). It gives the words verbatim: "Make it my determination (Recommended)", after the request "route kilix split properly through kilix-license." at 10:29Z. Its "Not established" row states both gaps: no licence is published for the weights apart from the repository's MIT statement, and the training data's terms are not established. The determination's own unproved field states the same two gaps. The file also notes that a different session reported an owner wish to ship Demucs in the ISO, and that this is not part of the determination. This candidate does not ship it (below).
- Refusal: `python3 -B -m unittest -v tests.test_demucs tests.test_whisper_medium` at kilix-license 80aab439 ran 9 tests, OK. This session's own mutations ran on a copy of the data directory, each time re-pinning the .sha256 so that only the owner check stands in the way. Removing owner_record, setting its sha256 to zeros, setting bytes 3505, and changing its path each printed "refused: ValueError Demucs terms lack the owner's determination". Changing owner_record's sha256 without re-pinning printed "refused: Demucs determination pin mismatch". Re-serialising unmodified generated 02f182d7.
- kilix-content asset demucs-htdemucs-6s at de2764f: its files are exactly models/5c90dfd2-34c22ccb.th (54996327 bytes, 34c22ccb...) and notices/LICENSE-mit.txt (1087 bytes, cf9b1782...). Its one fetch URL and its provenance original_url are the same weights URL, so the fetch host equals the provenance host. Its provenance names adefossez/demucs at eeac1d15. Its licence row cites record_digest 02f182d7... with text_sha256 cf9b1782.... The asset's identities equal the upstream ones above.
- The real-bytes test ran. This session placed its downloaded weights at <work>/demucs-supplied/models/5c90dfd2-34c22ccb.th. `DEMUCS_SUPPLIED_DIR=... python3 -B -m unittest -v tests.test_demucs_asset tests.test_whisper_medium_asset` at kilix-content de2764f ran 7 tests, OK. test_real_supplied_bytes_need_a_receipt_and_install_exactly printed "ok", not "skipped".

## kilix split at kilix 4b9f29cf

config/kilix_sdk/split_cli.py at 4b9f29cf:

- No route lets Demucs fetch weights. The earlier `--allow-model-downloads` flag of 37f5d4e is removed in 8e3274d (`git show 8e3274d` shows its add_argument and allow_downloads branch deleted). No download, hub or URL code remains apart from the pinned `git+https` Demucs code URL used by `--install`.
- `command_split` calls `licensed_weights()` before starting Demucs. That function runs `kilix models verify demucs-htdemucs-6s` and refuses unless the exit is 0 and the JSON names "verified": "demucs-htdemucs-6s" with an absolute root containing assets/demucs-htdemucs-6s/models/5c90dfd2-34c22ccb.th. Kilix's content_models.py `_verify` refuses when no stored receipt covers the exact model and manifest, and re-hashes every declared file.
- Demucs then runs as `-m demucs.separate --repo <verified asset>/models --name 5c90dfd2`. Its environment sets HF_HUB_OFFLINE=1 and points http_proxy, https_proxy, HTTP_PROXY, HTTPS_PROXY and ALL_PROXY at http://127.0.0.1:9 with an empty NO_PROXY.
- `kilix split --install` installs the pinned Demucs code with uv and then calls `kilix models install demucs-htdemucs-6s`.
- `printf n | ...` was refused without a terminal: "install requires an interactive terminal ... No acceptance receipt is written without an affirmative answer.". Under a pseudo-terminal, answering "n", the screen showed the record's id, version eeac1d15, source, the weights host, 54996327 bytes, "licence: mit", the record's licensor, "decision: affirmative" and the full MIT text, then "Install this exact model in the shown root? [y/N] n". It exited 1. `find` afterwards listed no file anywhere in that sandbox, so nothing was written. `kilix models verify demucs-htdemucs-6s` in the empty sandbox printed "SetupError: no stored receipt covers this exact model and manifest" and exited 1.
- `python3 -B -m unittest -v tests.test_split_cli` at 4b9f29cf ran 11 tests, OK. These include test_the_model_download_flag_is_gone, test_weights_without_a_covering_receipt_refuse_before_demucs and test_install_hands_the_weights_to_kilix_models_install.
- `kilix transcribe` installs only through `kilix models install` or `kilix stt --install`, and its `--clean` path calls `kilix split`. It gives no other weights route.
- Not shipped: `git grep -i` for demucs, 5c90dfd2, htdemucs and the weights host at 89e0626b matches only CHANGELOG.md, releases/0.2.3-notes.md and a comment in releases/0.2.3.env. No path in provision/, build/ or the carrier ships or fetches the Demucs weights, and the carrier has no Demucs entry. This agrees with the determination's scope: first-use download, never shipped.

## Claim 2: kilix-content d57fa62 to de2764f

The commits are 99122cb (Needle ref only), 3763110 (whisper medium asset), 5c6eb8f (Demucs asset) and de2764f (vendors kilix-license 80aab439). Comparing the parsed catalogs:

- content: only kilix-needle's source ref changes, 5cbff317 to a887e2fa.
- assets: added ['demucs-htdemucs-6s', 'faster-whisper-medium-en'], removed none, changed none. The lfm2-kilix-commands asset is equal.

third_party/kilix-license.pin reads 80aab439d7243936dc69ddcf6a7e90c0753ea7bb. `diff -r` of the vendored tree against a kilix-license 80aab439 archive differs only by the deliberately unvendored files. The vendored lfm2 record, its generator and the texts are unchanged (`git diff --quiet` returned 0). The receipt.py catalog pin equals the catalog's sha256, 59119efeaea214ec81e6afbe64afa256f91e9af397be13ce9e3113ddbeaf35a1. The remaining changes are mechanical: catalog_digests and catalog_source gain the new upstream digests, the upstream-pins files and generator lists gain the two assets, and the tests exempt the two new assets and update the pins and counts. `make pins` (`generate_upstream_records.py --check`) exited 0.

## Claim 3 and known issue (a): Needle 5cbff317 to a887e2fa

The one commit a887e2f changes asset.py, needle_cli.py and two tests. Its vendored third_party/kilix-content is 81f2321b51649effc3275493a351931497c3ba0f at both commits. commands-model.json has the same blob, cb6339162a1d5ffb01c0251478e81c07c25e7674, at both commits.

With an empty receipt store in a fresh sandbox, `python3 -B -c "import commands_runtime; commands_runtime.inspect_bundle()"` printed:
- at a887e2fa: "asset.AssetError: no receipt records that the lfm2-kilix-commands licence terms were shown; install it with: kilix-needle install --commands"
- at 5cbff317: "asset.AssetError: the lfm2-kilix-commands licence has not been accepted; install it with: kilix-needle install --commands"
- with backend='lfm3', at both commits: "the lfm3-kilix-commands licence has not been accepted; install it with: kilix-needle install --commands lfm3"

An affirmative licence keeps "has not been accepted". The command wrote no file in the sandbox.

First use at a terminal: this session called needle_cli._image with may_install=True, a terminal on stdin and stdout, and asset.from_installed raising each wording. "has not been accepted" led into install (install called=True). "no receipt records that ... licence terms were shown" led into install (install called=True). An unrelated error was re-raised (install called=False).

Suite: `make test` ran 1687 tests at 5cbff317 and 1688 at a887e2fa, with the identical set of 11 failures at both (5 FAIL, 6 ERROR, among them "OSError: AF_UNIX path too long" from this sandbox's long path). The new test_an_uncovered_notice_asset_is_not_called_unaccepted passed. The candidate introduces no Needle failure.

## Claim 4 and known issue (b): kilix b0c8939b to 4b9f29cf

The commits are 11869d5 (voice ref default), c6f6497 (content gitlink to 99122cbf), 86fd640 (medium: patcher, installer call, settings, wizard, src gitlink, tests), 37f5d4e (`kilix transcribe`), c7e8410 (settings-file medium choice, doctor), 8e3274d (split through kilix-license) and 4b9f29c (content gitlink to de2764f). The gitlinks are third_party/kilix-content de2764f87c6be98bd5dc18155403006952a4c9ac and src 04c3528c.

- scripts/install-kilix-voice.sh defaults KILIX_VOICE_REF to 1a4e63b11d0ad9c1664031e2773f5c4f5797913f. This equals the carrier's voice_ref and releases/0.2.3.env KILIX_VOICE_REF. It runs patch-whisper-medium-model.py on the staged runtime and dies if the patch fails.
- plebian-os test_the_pinned_kilix_builds_the_vibevoice_runtime passed at 89e0626b and failed at 4034dde2.
- Further kilix tests: test_patch_whisper_medium_model, test_transcribe_cli and test_split_cli passed. test_content_models and test_shared_settings have the identical 15 failures (14 FAIL, 1 ERROR) at b0c8939b and at 4b9f29cf in this sandbox. They are not introduced by the candidate.

## Known issue (c)

test_provision_lifecycle_behavior's test_release_dictation_requires_the_complete_voice_closure passed at 89e0626b and failed at 4034dde2. f53a09a adds only `"KILIX_SECRETS_REF": ref` to that fixture.

## LFM2 notice on every route

- The LFM2 asset and the vendored LFM2 licence record are equal between kilix-content d57fa62 and de2764f. The LFM2 record and generator are unchanged between kilix-license 0984dd22 and 80aab439, with digest e4d08e2c53ab514e1e2ca2a812c64895519487d707c441703978bd0f245b5016, decision class informational and receipt decision `record`.
- The carried lfm2-kilix-commands record and CARRIER.json entry show the same digest and decision informational.
- `git diff --quiet 4034dde2 89e0626b` returned 0 for the image installer (provision/install-image-models.py), provision/command-model.json, provision/command-model-determination.json, the release guard's source (build/remaster-iso.sh, from which validate_voice_release_closure is taken), and the carried LFM2 files. Each path exists at 89e0626b.
- AC-8 test_command_model_records_needle_serves_are_the_carried_ones passed at 89e0626b, where the catalog selects Needle a887e2fa. This session ran the test's own needle_vendor_gaps with the carried files against Needle 3a8e41c52f32f963c4bbeadfbec69b200f13eafe, whose vendored kilix-content is 23cc16c9. It returned three gaps (vendored asset record, licence record, and commands-model.json not the carried ones), so the test's `assertEqual(gaps, [])` fails there. Against a887e2fa and 5cbff317 it returned [].
- This session found no terms waived or hidden on any route it ran: the Demucs, Whisper medium and LFM2 screens or refusals all name their records.

## Claim 5: plebian-os 4034dde2 to 89e0626b

`git log --oneline 4034dde2..89e0626b` printed three commits, not two:

- f53a09a "Supply KILIX_SECRETS_REF in the release dictation fixture" (as claimed)
- 2cd2f7c "Check only voice-run models against the pinned kilix-voice catalog" (not in the claim)
- 89e0626 "Carry whisper-medium-en and pin the medium, split and LFM2-fix sources." (as claimed)

89e0626 touches the provisioner's speech-catalog list and census paths, build_vm_image.py, the generator's LICENCE_RECORD_IDS and CATALOG_INSTALLED_MODELS, the carrier files, releases/0.2.3.env, .requirements and -command-model.json, the notes, the CHANGELOG and tests. The provisioner diff contains only whisper-medium lines. test_whistle_release now reads the current VERSION's env instead of releases/0.2.2.env, and runs the patcher before the consumers. That is a consequence of the release Kilix patching the voice library.

2cd2f7c is a test-only change. It makes test_the_pinned_voice_runs_every_runnable_model skip the Ask command model, which Needle runs, not kilix-voice. That test failed at 4034dde2 (subTest model='lfm2-kilix-commands' FAIL) and passes at 89e0626b. The failure predates this round and is not one of the three known issues the owner chose to fold in, and the claim does not name the commit. Its reasoning is sound, and AC-8 covers the command model. It changes no shipped file, record, pin or gate. It is still a difference outside claims 1 to 6, so this record reports it as a known issue.

## Claim 6: CARRIER.json

Comparing the two CARRIER.json files key by key: the top-level keys are the same. Only bindings_sha256 (2d6d48cd... to 940814266f3f...), interface_content_ref (d57fa62 to de2764f), interface_licence_ref (0984dd22 to 80aab439) and model_order differ. model_order gains whisper-medium-en between whisper-small-en and whistle. models gains whisper-medium-en, and no other model entry changes. No Demucs entry exists (`grep -ril demucs` over the candidate carrier found nothing). CARRIER.env, BINDINGS.sha256 and SHA256SUMS change only by the new model's lines, the two refs and the dependent digests. The new files are whisper-medium-en/{ARTIFACT.json, DELIVERY, LICENCE-RECORD.json, NOTICE} and determinations/whisper-medium-en/OWNER-DETERMINATION-whisper-medium-en.md. ACCEPTANCE.json was ignored as the brief directs.

The whisper-medium-en DELIVERY reads, in part: "The speech install command hands the download to that model catalog and fetches no weights itself (kilix-voice 1a4e63b11d0ad9c1664031e2773f5c4f5797913f)." That is true of the voice library the release installs, which is 1a4e63b as Kilix 4b9f29cf's patcher stages it. The bare 1a4e63b has no whisper-medium-en and so no route for it at all. The statement's claims about behaviour hold: not in the image, not downloaded by provisioning, no download before a receipt, and a catalog hand-off with no weights of its own. This session therefore does not count it as a delivery mismatch. The parenthetical names only the voice commit, not the Kilix patch the route depends on, and this record reports that as a known issue. The text comes from the generator's shared template for catalog-installed models, and AC-8's delivery check requires it.

## Pins

- KILIX_REF 4b9f29cf's third_party/kilix-content gitlink (`git ls-tree`) is de2764f87c6be98bd5dc18155403006952a4c9ac. That equals the carrier interface_content_ref and releases/0.2.3.env PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF.
- KILIX_LICENSE_REF 80aab439d7243936dc69ddcf6a7e90c0753ea7bb equals interface_licence_ref.
- releases/0.2.3.env and releases/0.2.3.requirements agree on PLEBIAN_OS_VOICE_CARRIER_SHA256 (0e544b97..., the candidate CARRIER.json sha256), PLEBIAN_OS_VOICE_CARRIER_RECEIPT_SHA256 (037e29a3..., the sha256 of the candidate ACCEPTANCE.json), KILIX_LICENSE_REF and PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF.
- The kilix-content de2764f catalog's kilix-needle ref is a887e2fae221272aece6b7b9aef143df8bc7ba64.
- releases/0.2.3-command-model.json source_pins name kilix 4b9f29cf, kilix-content de2764f, kilix-license 80aab439 and kilix-needle a887e2fa, with manifest revision de2764f.

## Generator check

This session copied the candidate carrier to a writable <work>/carrier-copy. From the plebian-os clone at 89e0626b, with kilix-content at de2764f and kilix-license at 80aab439, it passed ten --determination arguments, one per file under determinations/ in sorted path order: kilix-diarization-cpu, lfm2-kilix-commands, lgraph-en-us, small-en-us, three for vibevoice-asr-bitnet, whisper-medium-en, whisper-small-en and whistle. It also passed two --seat arguments, one per file under seats/ in sorted order. `python3 -B build/generate-model-compliance.py --content-repo ../kilix-content --license-repo ../kilix-license <those> --out ../carrier-copy --check` printed nothing and exited 0, and the copy still equals the seat input. As a control, appending one line to the copy's whisper-medium-en/DELIVERY made the same command print "carrier differs: whisper-medium-en/DELIVERY" and exit 1.

## Suites

### plebian-os full suite

This session ran the full plebian-os suite at 89e0626b (the clone) and at 4034dde2 (a worktree of it), concurrently, under the same sandbox environment. The command was `python3 -B -m unittest discover -s tests -v`, with PLEBIAN_OS_KILIX_REPO, PLEBIAN_OS_KILIX_CONTENT_REPO, PLEBIAN_OS_KILIX_LICENSE_REPO, PLEBIAN_OS_KILIX_NEEDLE_REPO, PLEBIAN_OS_NEEDLE_REPO and PLEBIAN_OS_KILIX_VOICE_REPO pointing at this session's sibling clones.

- 89e0626b: "Ran 1410 tests", "FAILED (failures=10, skipped=5)".
- 4034dde2: "Ran 1410 tests", "FAILED (failures=12, skipped=5)".

Failing only at the candidate:
- test_model_compliance_carrier test_acceptance_receipt_names_two_independent_seats (AC-7). It printed "AssertionError: '0e544b97...' not found in '# Seat A review: LFM2 notice carrier, round 2 ...'". The receipt still names the round 2 seats. The brief expects this until the receipt names this round's seats.

That is the only failure the candidate introduces.

Failing only at 4034dde2, and fixed by the candidate:
- test_provision_lifecycle_behavior test_release_dictation_requires_the_complete_voice_closure (known issue c)
- test_runnable_models test_the_pinned_kilix_builds_the_vibevoice_runtime (known issue b)
- test_runnable_models test_the_pinned_voice_runs_every_runnable_model, subTest model='lfm2-kilix-commands' (fixed by the undeclared 2cd2f7c)

Failing at both commits, so not introduced by the candidate:
- test_build_vm_image SelectedClosureGateTests: test_rollback_reaches_the_unpublished_selected_closure and test_successful_update_keeps_selected_closure_and_restart.
- test_ollama_carrier_wrappers: test_building_wrapper_dry_runs_show_the_shared_carrier and test_remaster_selects_argument_or_environment_and_canonicalizes.
- test_voice_release_contract test_documents_describe_the_first_use_route_the_code_takes: four subtests on RELEASING.md.
- test_model_compliance_carrier test_delivery_statement_is_true_of_this_image. It printed "no kilix-bonsai checkout holds 630da3cf...; set PLEBIAN_OS_KILIX_BONSAI_REPO", because the brief's list of sibling repositories has no kilix-bonsai. With a kilix-bonsai clone added (PLEBIAN_OS_KILIX_BONSAI_REPO), `python3 -B -m unittest -v test_model_compliance_carrier` ran 17 tests at each commit. At 89e0626b only AC-7 failed, and test_delivery_statement_is_true_of_this_image passed. At 4034dde2 all 17 passed.

Also passing at 89e0626b: AC-1 test_carrier_regenerates_byte_identically, AC-3, AC-4, AC-5, AC-6, AC-9 to AC-12, test_command_model_records_needle_serves_are_the_carried_ones, test_whistle_release and test_speech_weight_census.

### Sibling suites

The candidate introduces no failure in any sibling suite.

- kilix-license, `python3 -B -m unittest discover -s tests -t .` with PYTHONPATH=src:tests/support:
  - 80aab439: 229 tests, "FAILED (failures=1, skipped=2)".
  - 0984dd22: 220 tests, the same single failure, test_receipt_store_root test_a_relative_root_is_refused_rather_than_resolved_somewhere (variable='GPU_TERMINAL_HOME'). This session's sandbox sets KILIX_LICENSE_RECEIPTS.
- kilix-content, `make test` with DEMUCS_SUPPLIED_DIR:
  - de2764f: 403 tests.
  - d57fa62: 396 tests.
  - Both have the same two failures: test_network_guard_coverage test_getent_and_af_unix_are_invisible_too ("OSError: AF_UNIX path too long") and test_content test_timeout_kills_the_whole_build_process_group.
- Needle and Kilix: see the sections above.

## Known issues

1. plebian-os 2cd2f7c is not in the builders' claim. It is a test-only fix of test_the_pinned_voice_runs_every_runnable_model, which failed at 4034dde2 because the Ask command model is looked up in kilix-voice's catalog. It changes no shipped file, record, pin or gate, but the claim says the candidate differs only by f53a09ac and 89e0626b.
2. The carried whisper-medium-en DELIVERY attributes the catalog hand-off to "kilix-voice 1a4e63b11d0ad9c1664031e2773f5c4f5797913f" alone. Bare 1a4e63b has no whisper-medium-en route. The route exists only once Kilix 4b9f29cf's scripts/patch-whisper-medium-model.py has run on the staged library. What the statement says about behaviour is true of the release.
3. The builders' description of kilix 37f5d4e says it adds `kilix transcribe`. It also adds the first config/kilix_sdk/split_cli.py and the `kilix split` dispatch, with an `--allow-model-downloads` flag that let Demucs fetch weights itself. 8e3274d removes that flag and routes the weights through kilix-license, so 4b9f29cf has no such route. The commit-by-commit description is incomplete, but the end state is the one claimed.

None of these touches a required identity, record, determination, pin or receipt gate, and no install route serves terms or records other than the owner's decisions and the carried ones.

VERDICT: ship with known issues
