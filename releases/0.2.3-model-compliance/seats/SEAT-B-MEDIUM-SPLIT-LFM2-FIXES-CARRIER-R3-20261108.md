# Seat B review: whisper-medium-en, kilix split, LFM2 notice fixes, carrier round 3 (2026-11-08)

This is the seat B record for the Plebian-OS 0.2.3 RC5 model-compliance carrier candidate at plebian-os `89e0626b606b45c3c1e88f32b3ceea46b719df9b`, against the last seat-approved state at plebian-os `4034dde27ee1a34d2dbc5ca2e6fd5d9e5a5b0e28`.

- Candidate `CARRIER.json` sha256, as this session computed it: `0e544b976dad4a67e0bb0d6d9dbb4407b028782a493bde360a9cfa1ba767ead7`.
- Approved `CARRIER.json` sha256, as this session computed it: `bf003bf70e6059e3ec7b458ea4e7b26266383486825f361a472e7efc5f1f71ac`.
- `DEFAULT-MODELS.json` field `sha256`, as this session read it in both carriers: `e00614bf726154d09668820c061cbbcb402239a445bde666b0568d36f01528a6`. The two `DEFAULT-MODELS.json` files are byte-identical.

## Eligibility

The builder session launched this pane with `kilix @ launch` at 2026-11-08T21:40:26Z and wrote the brief. This session's first command ran at 2026-11-08T21:40:53Z (`date -u`). This session did not author the carrier, its generator, its determinations, the kilix-license records faster-whisper-medium-en or demucs-htdemucs-6s, the kilix-content assets faster-whisper-medium-en or demucs-htdemucs-6s, the Kilix voice patcher, `kilix transcribe`, `kilix split`, the Needle wording change, the Kilix voice-installer default, or the plebian-os test fixture change. The builder sessions wrote them. This session only cloned, read, ran and tested them.

The review was read-only. This session did not modify either carrier copy, any source checkout outside its own work directory, or the other seat's directory. It did not read the other seat's directory, the builders' notes, or earlier seat records outside the carriers. It did not commit or push to any public repository, publish anything, write ACCEPTANCE.json, start other agents, or accept a licence in any receipt store outside its work directory. The one licence receipt this session wrote (for demucs-htdemucs-6s, while exercising `kilix split`) is in a sandbox receipt store inside its work directory. Two scratch commits exist only in local throwaway clones inside the work directory. They were used to point the AC-8 test at an older Needle and were never pushed.

In this record, WORK means `/home/pleb/storage/research/plebian-os/023-rc5-transcribe-medium-20261107/r3/seats/b/work`. CAND means the read-only candidate carrier and APPR the read-only approved carrier under `/home/pleb/storage/research/plebian-os/023-rc5-transcribe-medium-20261107/r3/seat-inputs`. Every Kilix, kilix-content, kilix-license, Needle and plebian-os command ran under `env -i`. HOME, TMPDIR, KILIX_STORAGE_HOME, KILIX_DATA_HOME (inside KILIX_STORAGE_HOME), GPU_TERMINAL_HOME and KILIX_LICENSE_RECEIPTS pointed at fresh sandbox directories under WORK, one sandbox per check.

## Sources

All repositories were cloned into WORK from the public repositories named in the brief. Kilix was cloned with `--filter=blob:none`. `git cat-file -t` printed `commit` for every commit the brief names: plebian-os 4034dde2, f53a09ac and 89e0626b; kilix-content d57fa62, 99122cbf and de2764f; kilix-license 0984dd22 and 80aab439; kilix b0c8939b, c6f64973 and 4b9f29cf; kilix-needle 5cbff317 and a887e2fa; kilix-voice 1a4e63b; and upstream Demucs eeac1d15 and 25dada5a. `git branch -r --contains` placed each candidate commit on the branch the brief names.

## Carrier difference (claim 6)

Command: a sorted file list and `cmp` of every file in APPR and CAND, excluding `seats/` and `ACCEPTANCE.json`, then `diff` of the pretty-printed CARRIER.json, CARRIER.env, BINDINGS.sha256 and SHA256SUMS.

Printed: the only added files are `determinations/whisper-medium-en/OWNER-DETERMINATION-whisper-medium-en.md`, `whisper-medium-en/ARTIFACT.json`, `whisper-medium-en/DELIVERY`, `whisper-medium-en/LICENCE-RECORD.json` and `whisper-medium-en/NOTICE`. The only changed files are `BINDINGS.sha256`, `CARRIER.env`, `CARRIER.json` and `SHA256SUMS`.

In CARRIER.json, only these change: `bindings_sha256` (2d6d48cd… to 940814266f3f…), `interface_content_ref` (d57fa62 to de2764f), `interface_licence_ref` (0984dd22 to 80aab439), `model_order` (whisper-medium-en inserted between whisper-small-en and whistle), and `models` (gains a whisper-medium-en entry). `interface_content_schema_sha256`, `voice_ref` (1a4e63b11d0ad9c1664031e2773f5c4f5797913f), the library wheel and every other model entry are unchanged. CARRIER.env changes only `models=`, the two interface refs and eleven new `m_whisper_medium_en_*` lines. BINDINGS.sha256 and SHA256SUMS change only by the new files and the new hashes. No Demucs entry exists. `sha256sum -c SHA256SUMS` and `sha256sum -c BINDINGS.sha256` in CAND printed no failures, and `sha256sum BINDINGS.sha256` printed 940814266f3f6364e04058aa375d758c1836be3f5f8d7cc8e037058f877aff56, which is the bound `bindings_sha256`.

`git archive` of `releases/0.2.3-model-compliance` at 89e0626b and at 4034dde2, compared with `diff -r` against CAND and APPR, printed `89e0626b == candidate-carrier` and `4034dde2 == approved-carrier`.

Claim 6 holds.

## kilix-license 0984dd22 to 80aab439 (claim 1)

Commands: `git log --oneline 0984dd22..80aab439`, `git diff --name-status` and `git diff` of every modified file.

Printed: four commits, 7c70078, 99add45, e05278d and 80aab43. Six data files are added: `demucs-records/demucs-htdemucs-6s.json`, `determinations-demucs.json`, `determinations-demucs.sha256`, `determinations-whisper-medium.json`, `determinations-whisper-medium.sha256` and `whisper-medium-records/faster-whisper-medium-en.json`. No data file is modified or removed. The modified files are CHANGELOG.md, pyproject.toml (two package-data globs), catalog.py (two family directories added to the load and lookup lists), tools/generate_records.py (the two generators called in check and write) and two tests (the expected id sets). There is no other change.

Command: `env PYTHONPATH=src python3 -B tools/generate_records.py --check`. Printed: `records 30 match generator (pin 3038192435db…)` and `application records 4 match generator (pin 80347a2c…)`. The pins are unchanged, so no existing release record digest moved.

Command: load `kilix_license.load_determined_records()` and print id, digest and decision class. Printed:
- `faster-whisper-medium-en c33e44c18901aa5802f668f733a12f5d39ed63436c5a0eaa96c6eea874e1ae23 affirmative`
- `demucs-htdemucs-6s 02f182d709f425adce6d8bb3d69b13aab3e2f976bd8aaf32b3b8eab6c04ae75b affirmative`
- `lfm2-kilix-commands e4d08e2c53ab514e1e2ca2a812c64895519487d707c441703978bd0f245b5016 informational`, with `expected_decision` `record`. The same values print at 0984dd22.

Both new digests equal the digests the brief names.

Command: `env PYTHONPATH=src:tests/support python3 -B -m unittest discover -s tests`, run at 80aab439 and 0984dd22. Printed: 229 tests at 80aab439 and 220 at 0984dd22. Both runs had the same single failure, `test_a_relative_root_is_refused_rather_than_resolved_somewhere (variable='GPU_TERMINAL_HOME')`. Rerunning that file without KILIX_LICENSE_RECEIPTS in the environment printed `Ran 12 tests … OK`, so the failure comes from this session's sandbox variable and not from the candidate. `tests.test_demucs` and `tests.test_whisper_medium` printed `Ran 9 tests … OK`.

Claim 1 holds.

## Whisper medium

Upstream identities. Command: `curl` of the model API tree for faster-whisper-medium.en at a29b04bd, plus a download and `stat`/`sha256sum` of the four small files. Printed:
- `model.bin`: LFS size 1527904330, oid 11b220779aea4c6f3ce9d2549c8a95ea869ed84066864b999531ef53e594fe5b
- `config.json`: 2643 bytes, 4a1848ebabe7938d9797c15a2e8e4ce1d36e6fd4a43d096ae5955257c67c7962
- `tokenizer.json`: 2128466 bytes, 929c5252409436dce1b38a75d1abbcb5e132d170d8e324e4e04ed915fa2d22df
- `vocabulary.txt`: 422309 bytes, ff77588746d3a2595d32ab5b69ffd7b95ce2441ac57533cb66fc3eb575a115cf
- `README.md`: 1337 bytes, ab3ddd3b6af4ea0ef353cb80004f26613ba33217f81652fc13738d3b098c7675; `grep -n license README.md` printed `7:license: mit`

All equal the brief's identities. `determinations-whisper-medium.json` at 80aab439 lists exactly these four files, the card bytes and sha256, `card_licence_line` `license: mit`, and licence text b5d65a59…. The generator `whisper_medium.py` hard-codes and enforces the same values. The kilix-content asset at de2764f lists the same five files plus `notices/LICENSE-mit.txt` (1063 bytes, b5d65a59…). Its `download_bytes` 1530459085 is the sum of the five upstream files.

Record and pin. `cat determinations-whisper-medium.sha256` and `sha256sum determinations-whisper-medium.json` both printed a5bb89f07a696c1535ec7636cabc67d453aa248b3e8824a802391c26b801534a. The generated record carries that `determinations_sha256`. `cmp` of `whisper-medium-records/faster-whisper-medium-en.json` against `CAND/whisper-medium-en/LICENCE-RECORD.json` printed `RECORD-IDENTICAL`. Both hash to 0d072d477bf34bce7aac9cf5836eb0bc7ebe46ba39c37a94e4860fe326b2ca7d, which is the bound `licence_record_file_sha256`.

Artifact. A Python comparison of `CAND/whisper-medium-en/ARTIFACT.json` with the faster-whisper-medium-en object in `plebian.json` at de2764f printed `ARTIFACT.json equals catalog asset object: True`. The record digest in the asset is c33e44c1…. The three licence texts in `CAND/licence-texts` named by the entry hash to their names and are byte-identical to kilix-license's texts.

Determination file. The kilix-license determination's `owner_record` names `licence-evidence-whisper-medium-en-2026-11-07/OWNER-DETERMINATION-whisper-medium-en.md`, 2392 bytes, sha256 6ac0416bdb3f9bb23da7acd57af79055b70ba8b02766891e6abef97eb21b9940. `stat` and `sha256sum` of that file under `/home/pleb/research/gpu_terminal` printed 2392 and 6ac0416b…. `cmp` against the carried determination printed `CARRIED-DET-IDENTICAL`. The file states:
- who determined: the owner, recorded verbatim by a builder who did not make the determination;
- what: MIT, with the record's two licensors, the same terms as whisper-small-en;
- when: 2026-11-07 at 22:38:59Z;
- which words: "New medium record (Recommended)", with the option text shown to the owner and the owner's original request.

This matches the owner's decision in the brief.

Voice patcher. Commands: `git archive` of kilix-voice 1a4e63b into a fresh directory, `git show 4b9f29cf:scripts/patch-whisper-medium-model.py`, then `python3 -I -B patch-whisper-medium-model.py <tree>`. Printed: `whisper-medium-en added under …`, exit 0. `diff -r` against an unpatched copy shows changes only to `voicelib/models.py`, `voicelib/stt.py` and `voicelib/licensing.py`, exactly the replacement pairs in the patcher. Importing the patched voicelib printed:
- `order: ['small-en-us', 'lgraph-en-us', 'vibevoice-asr-bitnet', 'whisper-small-en', 'whisper-medium-en', 'whistle']`
- `size=1530459085`, engine `whisper`
- `licence_record_id: faster-whisper-medium-en`
- `content_asset_id: faster-whisper-medium-en`
- `accept_command: kilix models install faster-whisper-medium-en`

In the patched `kilix-stt`, `model_install_argv` returns `[kilix, "models", "install", "faster-whisper-medium-en"]` for any model in CONTENT_STORED_MODELS. `install_model` only runs that command and then `kilix voice whisper` (the provider runtime). So the install route hands the download to the model catalog and fetches no weights itself, as the carried DELIVERY says. The medium model passes the patched `kilix-stt --models --json` record with `install_and_default_argv` `kilix stt --install whisper-medium-en --default whisper-medium-en`.

Provisioner, image builder and census. Command: the Python body of `validate_voice_model_catalog` was extracted from `provision/plebian-os-provision.sh` at 89e0626b, and the output of `kilix-stt --models --json` from the patched and the unpatched trees was fed to it.
- Patched catalog: bytes 1530459085 and `1.4 GiB` for whisper-medium-en; validate exit 0.
- Unpatched catalog: `unknown speech-model catalog schema`; exit 1.

The `expected` block in `build/build_vm_image.py` is identical to the provisioner's (`expected blocks identical: True`), and medium's required files are model.bin, config.json, tokenizer.json and vocabulary.txt, as the patched catalog and the kitty src commit require. `SPEECH_WEIGHT_PATHS` in build_vm_image.py and `voice_dictation_asset_paths` in the provisioner both add `voice/models/whisper-medium-en` and `desktop-apps/assets/faster-whisper-medium-en`. `tests/test_speech_weight_census.py` adds the same two paths and passes in the full suite.

Kitty src gitlink (kilix 86fd640). Commands: `git log` and `git diff 89db565a 04c3528c`. Printed: one descendant commit changing only `kitty/kilix_voice.py`, which adds whisper-medium-en to the model tuples with the same bytes, required files and content directory, and names the chosen Whisper model in one refusal hint.

## kilix-content d57fa62 to de2764f (claim 2)

Commands: `git log --first-parent`, `git diff --stat`, and a Python comparison of `plebian.json` at both commits. Printed:
- commits 99122cb, 3763110, 5c6eb8f and de2764f;
- `assets 40 -> 42 added ['demucs-htdemucs-6s', 'faster-whisper-medium-en'] removed []`;
- `changed existing assets: []`;
- `content entries changed: ['kilix-needle']`, whose only change is the source ref, 5cbff317 to a887e2fa.

The other changes are mechanical. `receipt.py` re-pins `_CATALOG_SHA256` to 59119efe…, and `sha256sum plebian.json` printed 59119efeaea214ec81e6afbe64afa256f91e9af397be13ce9e3113ddbeaf35a1. The catalog digest lists add the five new file digests. `third_party/kilix-license.pin` is 80aab439, and `diff -rq` of the vendored tree against `git archive` of kilix-license 80aab439 shows only files that are deliberately not vendored. The guard tests change only the asset count (40 to 42), exclusion lists, pins and the Needle ref.

Command: `tools/generate_upstream_records.py --check`. Printed: exit 0.

Command: full suite at de2764f and at d57fa62 (`unittest discover -s tests` with the Makefile's PYTHONPATH). Printed: 403 tests at de2764f and 396 at d57fa62. Both runs had the same three harness failures (`test_getent_and_af_unix_are_invisible_too`, `test_timeout_kills_the_whole_build_process_group` and `test_tests_package_isolation_is_loaded`), and no new failure.

Claim 2 holds.

## Demucs

Upstream identities. Commands: `git cat-file -s` and `git show … | sha256sum` at eeac1d15. Printed:
- `LICENSE`: 1087 bytes, cf9b17822d1fcd4ff32ccbe14183386fb3adf6f2ff92dc184130823f7fc28173
- `README.md`: 59ab8a3595cd5ec8dd853821ca2b377804f397be8467a082920f1c44e0d59d35, with line 320 `Demucs is released under the MIT license as found in the [LICENSE](LICENSE) file.`
- `demucs/remote/files.txt`: 7258eee911e5963e6270983d7072832e90e1ed96b25bb26aadf12f9867109bf9, listing `5c90dfd2-34c22ccb.th` at line 32 under `root: hybrid_transformer/`
- `demucs/remote/htdemucs_6s.yaml`: 21 bytes, 207405151270af8fd81c2373c25d27950916682ac91dca7884a11ce13dad6f58, reading `models: ['5c90dfd2']`

`git log -1 25dada5a` printed 2020-04-13. Its README diff replaces the earlier non-commercial licence line with the MIT line. `git merge-base --is-ancestor 25dada5a eeac1d15` succeeded.

Weights. Command: `curl` of the weights URL the brief names, then `stat -c %s` and `sha256sum`. Printed: `54996327` and `34c22ccb381c6f9fdbf324f04e1e2fe21aaaf293f5ded163a162697ff9a02ddd`. Both equal the brief. The asset's fetch URL is exactly `ROOT_URL + "hybrid_transformer/" + "5c90dfd2-34c22ccb.th"` from `demucs/pretrained.py` at eeac1d15.

Record. The pinned `determinations-demucs.json` hashes to its pin, 994295eecca22640aac82e2f69e24ceb6e8bbf67e987e93b63babbee23e219df. It generates `demucs-htdemucs-6s` with digest 02f182d7…, licence MIT, the record's licensor (the copyright holder in the upstream LICENSE's copyright line), decision `affirmative`, and no advisories, statements, components or binding conditions. `cmp` of upstream `LICENSE` against the record's text file printed `LICENSE-TEXT-IDENTICAL`. The licence text, licensor and decision therefore agree with the upstream LICENSE and README.

Owner record. The determination's `owner_record` names `licence-evidence-demucs-htdemucs-6s-2026-11-08/OWNER-DETERMINATION-demucs-htdemucs-6s.md`, 3506 bytes, c58b90a793b5a0866253d5351de0cc61000f05835daf6736a0ae3a2e2e22def0. `stat` and `sha256sum` of `/home/pleb/research/gpu_terminal/licence-evidence-demucs-htdemucs-6s-2026-11-08/OWNER-DETERMINATION-demucs-htdemucs-6s.md` printed `3506` and c58b90a7…. The file states:
- who: the owner, with the terms proposed by a builder and adopted by the owner;
- what: MIT, with the record's licensor and that text;
- when: 2026-11-08 at 12:31:18Z;
- which words: "Make it my determination (Recommended)", with the option text and the 10:29Z request "route kilix split properly through kilix-license.";
- both gaps, in its "Not established" row: no licence for the pretrained weights apart from the repository's MIT statement, and the training data's terms not established.

The determination's `unproved` field states the same two gaps.

The owner record's distribution row also mentions a separately reported decision to ship these weights in the ISO. It says that change is not part of this determination. The candidate does not implement it (see the image check below), which matches the determination's scope.

Refusal without the owner record. `python3 -B -m unittest tests.test_demucs` passed 5 tests. This session's own mutation script copied the data directory, changed the determination, re-pinned it, and called `generate_demucs_records`. Printed:
- `unmutated: 02f182d7…`
- `remove owner_record -> REFUSED: ValueError Demucs terms lack the owner's determination`
- the same refusal for a changed owner_record sha256, bytes 3505, and a changed path.

Asset. The demucs-htdemucs-6s asset at de2764f lists exactly `models/5c90dfd2-34c22ccb.th` (54996327, 34c22ccb…) and `notices/LICENSE-mit.txt` (1087, cf9b1782…). It has one fetch URL, and the fetch host is the same as the host in `provenance.original_url`. Its provenance is the upstream project at eeac1d15, and its licence row cites record digest 02f182d7…. The asset's identities equal the upstream ones above.

Real-bytes test. The weights were downloaded to `WORK/demucs-supplied/models/5c90dfd2-34c22ccb.th`. Command: `DEMUCS_SUPPLIED_DIR=WORK/demucs-supplied python3 -B -m unittest -v tests.test_demucs_asset tests.test_whisper_medium_asset`. Printed: `test_real_supplied_bytes_need_a_receipt_and_install_exactly … ok` among `Ran 7 tests … OK`. The real-bytes test ran and was not skipped.

Not shipped. Command: `git grep -n -i -e demucs -e 5c90dfd2 -e 34c22ccb -e htdemucs -e 'kilix split' 89e0626b`. Printed: only CHANGELOG.md, `releases/0.2.3-notes.md` (lines saying the weights are a first-use model and never shipped) and a comment in `releases/0.2.3.env`. No path is under `provision/` or `build/`. At 4034dde2 the same grep found zero lines. `provision/install-image-models.py`, the image installer, installs only its two pinned asset ids, the pitch model and lfm2-kilix-commands. `git diff --quiet 4034dde2 89e0626b -- provision/install-image-models.py build/remaster-iso.sh provision/command-model.json provision/basic-pitch-model.json` succeeded. No plebian-os path at 89e0626b ships the demucs-htdemucs-6s weights in the image.

## kilix split at 4b9f29cf

Code read (`config/kilix_sdk/split_cli.py`). The `--allow-model-downloads` flag and its `allow_downloads` environment branch are gone: commit 8e3274d removes them, and `grep` at 4b9f29cf finds neither. `command_split` calls `licensed_weights()` before starting the separator. That function runs `kilix models verify demucs-htdemucs-6s` and refuses with "the htdemucs_6s weights are not installed with a licence receipt. Run: kilix split --install" unless the JSON says `verified: demucs-htdemucs-6s`, has an absolute root, and the weights file exists. The separator then runs as `-m demucs.separate --repo <root>/assets/demucs-htdemucs-6s/models --name 5c90dfd2`, with `HF_HUB_OFFLINE=1` and every proxy variable pointed at an unreachable local port. In the pinned upstream source, `get_model(name, repo)` with a repo goes only to `LocalRepo`/`BagOnlyRepo` and never to the hub or the remote list. `kilix split --install` installs the pinned code and then calls `kilix models install demucs-htdemucs-6s`. `kilix transcribe --clean` reaches separation only through `kilix split`, and `kilix transcribe install` hands off to `kilix models install` or `kilix stt --install`.

Run (sandbox WORK/sb-split, Kilix at 4b9f29cf with third_party/kilix-content at de2764f):
- `content_models.py verify demucs-htdemucs-6s` with an empty store printed `no stored receipt covers this exact model and manifest; run kilix models install demucs-htdemucs-6s in a terminal`, exit 1.
- `content_models.py install demucs-htdemucs-6s` under `script` with the answer `n` printed the plan, the screen (id, version, source, host, 54996327 bytes, `licence: mit`, the record's licensor, `decision: affirmative`, the full MIT text) and `Install this exact model in the shown root? [y/N] n`, then exit 1. A sorted `find` of the sandbox before and after printed no difference (`NOTHING-WRITTEN`).
- The same install with `--from WORK/demucs-supplied` and the answers `y`, `y` printed the acceptance question and `{"installed": "demucs-htdemucs-6s", …}`, exit 0. It wrote one receipt, `02f182d7…-21c12934….json`, in the sandbox store. `verify` then printed `"verified": "demucs-htdemucs-6s", "declared_files_verified": 2`, exit 0.
- `split_cli.main([in.wav, --output, out.wav])` was run with a stand-in separator interpreter that records its argv and environment. In a sandbox with no receipt it printed the refusal above, exit 1, and the stand-in was not started. In the sandbox with the receipt it exited 0. The stand-in recorded `--repo WORK/sb-split/storage/data/desktop-apps/assets/demucs-htdemucs-6s/models --name 5c90dfd2`, the proxies at the unreachable port, `NO_PROXY` empty and `HF_HUB_OFFLINE` `1`.

Command: `python3 -B -m unittest -v tests.test_split_cli`. Printed: `Ran 11 tests … OK`, including `test_the_model_download_flag_is_gone`, `test_weights_without_a_covering_receipt_refuse_before_demucs` and `test_install_hands_the_weights_to_kilix_models_install`.

## Kilix b0c8939b to 4b9f29cf (claim 4)

Command: `git log --first-parent b0c8939b..4b9f29cf`. Printed: 11869d5, c6f6497, 86fd640, 37f5d4e, c7e8410, 8e3274d and 4b9f29c, with the content each claim names (`git show --stat` per commit). The gitlinks move as claimed: src 89db565 to 04c3528, and third_party/kilix-content d57fa62 to 99122cbf (c6f6497) to an intermediate commit (86fd640, 8e3274d) to de2764f (4b9f29c). `settings.py` and `model_wizard.py` add whisper-medium-en, and the `kilix` script adds the doctor path plus the `split` and `transcribe` front ends.

Command: the round's touched test files (`test_split_cli`, `test_patch_whisper_medium_model`, `test_transcribe_cli`, `test_voice_installer`, `test_content_models`, `test_voice_cli`, `test_shared_settings` and `test_voice_chrome`) at 4b9f29cf and at b0c8939b, then `diff` of the sorted failure lists. Printed: `IDENTICAL failure sets (76 each)`. These are socket, signal and atomic-write sandbox failures present at both commits. 277 tests ran at 4b9f29cf and 242 at b0c8939b.

Claim 4 holds.

## Needle 5cbff317 to a887e2fa (claim 3, known issue a)

Command: `git diff 5cbff317 a887e2fa`. Printed: one commit changing `asset.py`, `needle_cli.py` and two tests. `git ls-tree` shows `third_party/kilix-content` at 81f2321b51649effc3275493a351931497c3ba0f at both commits. `git show <ref>:commands-model.json | sha256sum` printed d900708d… at both.

Command (fresh sandbox, receipt store with 0 entries): `python3 -B -c "import commands_runtime; commands_runtime.inspect_bundle()"`.
- At a887e2fa it printed `asset.AssetError: no receipt records that the lfm2-kilix-commands licence terms were shown; install it with: kilix-needle install --commands`.
- At 5cbff317 it printed `asset.AssetError: the lfm2-kilix-commands licence has not been accepted; install it with: kilix-needle install --commands`.
- `asset.installed_asset_dir` for lfm3-kilix-commands at a887e2fa printed `the lfm3-kilix-commands licence has not been accepted; install it with: kilix-needle install --commands lfm3`.

The vendored catalog's licence decisions are only `affirmative` (40) and `informational` (2), so the two-way wording covers every asset.

First use at a terminal: `needle_cli._image(args, may_install=True)` was called with `from_installed` raising each wording, terminals reported as TTYs and `install` stubbed. It printed `install called: True` for both "has not been accepted" and "licence terms were shown".

Command: full suite at a887e2fa and at 5cbff317. Printed: 1688 tests and 1687 tests. Both runs had the same six errors and two failures (seqpacket socket tests, `test_each_launch_keeps_directory_and_omits_task_on_cli_and_mcp` and `test_routing_stays_under_five_milliseconds`), and no new failure.

Claim 3 holds.

## Known issues (b) and (c)

(b) `git diff b0c8939b 4b9f29cf -- scripts/install-kilix-voice.sh` shows `KILIX_VOICE_REF="${KILIX_VOICE_REF:-1a4e63b11d0ad9c1664031e2773f5c4f5797913f}"`. That is the release's KILIX_VOICE_REF and the carrier's `voice_ref`. `test_the_pinned_kilix_builds_the_vibevoice_runtime` printed `ok` at 89e0626b. At 4034dde2 it failed with `'KILIX_VOICE_REF:-1a4e63b…}' not found`.

(c) `test_release_dictation_requires_the_complete_voice_closure` printed `ok` at 89e0626b. At 4034dde2 it failed with `release mode requires KILIX_SECRETS_REF to be a full 40-character lowercase commit SHA`. f53a09ac adds only the two fixture lines.

## LFM2 notice on every route

The lfm2-kilix-commands asset object in `plebian.json` is identical at d57fa62 and de2764f (`lfm2 asset identical: True informational e4d08e2c…`). `git diff 0984dd22 80aab439` of the lfm2 records and generator is 0 lines. The record digest is e4d08e2c53ab514e1e2ca2a812c64895519487d707c441703978bd0f245b5016, class informational, expected decision `record`, at both commits. The carried lfm2-kilix-commands files are unchanged between APPR and CAND.

The image installer `provision/install-image-models.py` is unchanged from 4034dde2, and so are `build/remaster-iso.sh`, which holds the release carrier guard, and `provision/command-model.json`. The provisioner diff is only the medium lines quoted above.

AC-8. `test_command_model_records_needle_serves_are_the_carried_ones` printed `ok` at 89e0626b in the full suite. To point it at Needle 3a8e41c5, this session made a local scratch kilix-content commit on de2764f that changes only the kilix-needle ref to 3a8e41c5. It then made a scratch plebian-os worktree at 89e0626b whose `PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF` names that commit. Run there, the test printed `FAILED (failures=1)`, listing three gaps: the vendored asset record, the vendored licence record and commands-model.json. With the real clones it printed `OK`.

No route waives or hides the LFM2 terms. The Needle change only rewords the refusal; the install still shows the full terms and records a notice receipt.

## Pins

- KILIX_REF 4b9f29cf: `git ls-tree 4b9f29cf third_party/kilix-content` is de2764f87c6be98bd5dc18155403006952a4c9ac, which equals the carrier `interface_content_ref` and `releases/0.2.3.env` `PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF`.
- `KILIX_LICENSE_REF` is 80aab439d7243936dc69ddcf6a7e90c0753ea7bb, which equals `interface_licence_ref` and kilix-content's vendored pin.
- `releases/0.2.3.env` and `releases/0.2.3.requirements` both carry `PLEBIAN_OS_VOICE_CARRIER_SHA256=0e544b97…` (the candidate CARRIER.json sha256 above), `KILIX_LICENSE_REF=80aab439…` and `PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF=de2764f8…`.
- The kilix-content catalog's kilix-needle ref is a887e2fae221272aece6b7b9aef143df8bc7ba64.
- `releases/0.2.3-command-model.json` names kilix 4b9f29cf, kilix-content de2764f, kilix-license 80aab439 and kilix-needle a887e2fa, with manifest revision de2764f.
- `KILIX_VOICE_REF` stays 1a4e63b.

## Generator check

This session made a writable copy of CAND at WORK/carrier-rw. From the plebian-os clone at 89e0626b, with kilix-content checked out at de2764f and kilix-license at 80aab439, it ran:

`python3 -B build/generate-model-compliance.py --content-repo WORK/kilix-content --license-repo WORK/kilix-license --determination kilix-diarization-cpu=… --determination lfm2-kilix-commands=… --determination lgraph-en-us=… --determination small-en-us=… --determination vibevoice-asr-bitnet=… (three files, sorted) --determination whisper-medium-en=… --determination whisper-small-en=… --determination whistle=… --seat …/SEAT-A-LFM2-NOTICE-CARRIER-R2-20261108.md --seat …/SEAT-B-LFM2-NOTICE-CARRIER-R2-20261108.md --out WORK/carrier-rw --check`

There was one argument per file, in sorted path order. It printed nothing and exited 0. As a sanity check, appending one byte to the copy's `whisper-medium-en/NOTICE` made the same command print `carrier differs: whisper-medium-en/NOTICE`, exit 1. The byte was then restored, and `cmp` against CAND confirmed it.

## Full plebian-os suite, 89e0626b against 4034dde2

Command: `python3 -B -m unittest discover -s tests -v` in each tree. The variables PLEBIAN_OS_KILIX_REPO, PLEBIAN_OS_KILIX_CONTENT_REPO, PLEBIAN_OS_KILIX_LICENSE_REPO, PLEBIAN_OS_KILIX_NEEDLE_REPO, PLEBIAN_OS_NEEDLE_REPO and PLEBIAN_OS_KILIX_VOICE_REPO pointed at this session's clones. Printed: 89e0626b `Ran 1410 tests … FAILED (failures=10, skipped=5)`; 4034dde2 `Ran 1410 tests … FAILED (failures=12, skipped=5)`.

- Only at 89e0626b: `test_acceptance_receipt_names_two_independent_seats` (AC-7), with `'0e544b97…' not found in` the round 2 seat A record. This is expected until the receipt names this round's seats. It is the only failure the candidate introduces.
- Only at 4034dde2, fixed by the candidate: `test_release_dictation_requires_the_complete_voice_closure`, `test_the_pinned_kilix_builds_the_vibevoice_runtime`, and `test_the_pinned_voice_runs_every_runnable_model (model='lfm2-kilix-commands')` (`lfm2-kilix-commands is not in the pinned voice catalog`).
- At both, from this session's environment and not from the candidate:
  - `test_delivery_statement_is_true_of_this_image` (`no kilix-bonsai checkout holds 630da3cf…; set PLEBIAN_OS_KILIX_BONSAI_REPO`). With a kilix-bonsai clone supplied it printed `OK` at both 89e0626b and 4034dde2.
  - Two 0.2.2-release wrapper tests and two selected-closure tests, which expect release 0.2.2 in a 0.2.3 tree.
  - Four subtests of `test_documents_describe_the_first_use_route_the_code_takes` on RELEASING.md, which this round does not change.

## plebian-os commits (claim 5)

Command: `git log 4034dde2..89e0626b`. Printed: three commits, f53a09a, 2cd2f7c and 89e0626. f53a09a and 89e0626 match claim 5: the fixture fix, the medium carriage, the provisioner contract, build_vm_image.py, the generator's two medium tables, the census, the tests, the pins, the notes, the CHANGELOG and the command-model file. `test_whistle_release.py` now reads the version's release env instead of the 0.2.2 env, and applies the medium patcher to the voice tree it checks. Since the patcher exists only at this release's KILIX_REF, this session counts that as part of the medium test change in claim 5.

Commit 2cd2f7c ("Check only voice-run models against the pinned kilix-voice catalog") is not in the builders' claim. It is test-only. It changes `tests/test_runnable_models.py` to skip the asset id named in `provision/command-model.json` in `test_the_pinned_voice_runs_every_runnable_model`. That test failed at 4034dde2 for lfm2-kilix-commands, which Needle runs, not kilix-voice, and which AC-8 covers. The change looks correct and touches no record, pin, delivery statement or install route. It is not a mechanical consequence of claims 1 to 6, so it is a defect in the claim.

## Known issues found by this session

1. The builders' difference claim omits plebian-os commit 2cd2f7c, an undeclared test-only change described above. Its content looks correct, but the claim is incomplete.
2. The new comment above `KILIX_REF` in `releases/0.2.3.env` says it advanced from c6f64973. At 4034dde2 this file pinned b0c8939b. c6f64973 is only an intermediate ancestor on the Kilix side, so the comment misstates the previous pin. The value itself is correct.
3. The module docstring of `config/kilix_sdk/split_cli.py` says the separator "runs offline with no proxy". The code does the reverse: it points every proxy variable at an unreachable local port and sets the hub offline flag. The isolation is through environment variables, not a socket-level block, though the `--repo` path makes no network call in the pinned source. The wording is a documentation defect only; the behaviour is the one the brief requires.

No required identity, record, determination, delivery statement, pin or receipt gate failed to match. No install route serves terms or records other than the owner's decisions and the carried ones.

VERDICT: ship with known issues
