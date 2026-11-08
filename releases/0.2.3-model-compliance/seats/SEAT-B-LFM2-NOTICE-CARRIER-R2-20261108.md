# Seat B review: LFM2 notice carrier, round 2 (plebian-os 71aceb8)

This is the seat B record for the Plebian-OS 0.2.3 RC5 model-compliance carrier at plebian-os 71aceb850bf5f08f2ef779a35ebf16b4b3c2f8a8. It was written on 2026-11-08.

## Eligibility

The builder session launched this pane with `kilix @ launch` at 2026-11-08T11:05Z and wrote the brief this session followed. This session did not author the carrier, its generator, its determinations, the kilix-license LFM2 determination, the kilix-content catalog selection, the Needle install code or its vendored content, the Kilix install screens, the plebian-os image installer, or the delivery archive. This session began with an empty work directory, read the brief, and only read, cloned, ran and hashed. It is eligible.

This session did not read the other seat's directory, the builder's notes in the parent folder, or earlier seat records outside the carriers. It did not modify the carriers or any source outside its own work directory. It did not commit, push, publish, write ACCEPTANCE.json, or start other agents. One test failure message (AC-7, below) printed the text of an older seat record that is committed inside the carrier's `seats/` directory. This session did not use that text as evidence.

Every repository was cloned from the public remote named in the brief into `/home/pleb/storage/research/plebian-os/023-rc5-ask-parser-debian-20261107/seats/b2/work`, with kilix as a blob-filtered clone. Kilix-bonsai was also cloned, at the ref KILIX_REF installs, because the AC-8 tests read it. `git cat-file -t` printed `commit` for all 21 commits the brief names. Each candidate is the head of its named branch: `git rev-parse origin/work/0.2.3-rc5-image-models` printed 71aceb850bf5f08f2ef779a35ebf16b4b3c2f8a8 in plebian-os, and `origin/work/0.2.3-rc5-ask-20261107` printed d57fa62f…, 0984dd22…, b0c8939b… and 5cbff317… in kilix-content, kilix-license, kilix and kilix-needle. In kilix-license, `git log --oneline 65e5ae07..0984dd22` printed only `0984dd2 Deliver the LFM2 terms as a notice, Debian style.`, so 0984dd22 is the same commit the last rejected candidate used.

## Required identities

`sha256sum` on the three CARRIER.json files printed:

- candidate: `bf003bf70e6059e3ec7b458ea4e7b26266383486825f361a472e7efc5f1f71ac`. This matches the brief.
- rejected 458d48d: `ace6258566e764a0504efd78a843622814e674b5a1e5e8b7fbb22ea1ea90b913`. This matches the brief.
- last seat-approved c1e3612: `c578757b715a87b8f366fabd0db268c0122d153cef1d26a8ba1f849b4a819726`. This matches the brief.

The `sha256` field of the candidate DEFAULT-MODELS.json, read with a JSON parser, is `e00614bf726154d09668820c061cbbcb402239a445bde666b0568d36f01528a6`. This matches the brief.

The LFM2 entry in the candidate CARRIER.json has `licence_record_digest` `e4d08e2c53ab514e1e2ca2a812c64895519487d707c441703978bd0f245b5016`, `decision` `informational`, version `lfm2-kilix-commands-20261106-v9`, `archive_sha256` `ea03c42ce0f36d12bca1844c558c0fcaeb442887e55e1e7b76ccb3ed632c3a85` and `archive_bytes` 1362204317. Loading the record through kilix-license 0984dd22 (`load_determined_records().by_id('lfm2-kilix-commands')`) printed digest `e4d08e2c53ab514e1e2ca2a812c64895519487d707c441703978bd0f245b5016`, decision class `informational`, expected decision `record`, and `agreement_required` `[False]`. This matches the brief.

This session downloaded the archive from the published release URL in the brief with `curl -sSL -o lfm2-kilix-commands-20261106-v9.tar.gz <published URL>`. `stat -c %s` printed `1362204317`, and `sha256sum` printed `ea03c42ce0f36d12bca1844c558c0fcaeb442887e55e1e7b76ccb3ed632c3a85`. Both match the brief. `sha256sum` on the local file `/home/pleb/research/lfm2-ask-weights-20261106/delivery/lfm2-kilix-commands-20261106-v9.tar.gz` printed the same digest and size.

This session extracted the downloaded archive and hashed every member against the carrier's `lfm2-kilix-commands/ARTIFACT.json`. The script printed `members archive 44 artifact 44 equal True`. It printed `model.gguf ('3fa22c105b1f80823088de21a45fd2f3dc30a4cfdc63d21037c9344585fae4dd', 1388859040)` and `NOTICE.txt ('65e4cd26f6f63d2ad45c64df2a6876bc33b17c4af5272c90bd44dd072b0e6601', 1545)`. Both match the brief. `cmp` of the archive's `notices/LICENSE-LFM.txt`, `notices/LICENSE-runtime.txt` and `notices/NOTICE.txt` against the carrier's `licence-texts/4d28ca14….txt`, `571c0295….txt` and `65e4cd26….txt` found all three identical.

## Claim 5: the candidate carrier against the rejected 458d48d carrier

`diff -r -q -x seats -x ACCEPTANCE.json rejected-carrier candidate-carrier` listed only four files: BINDINGS.sha256, CARRIER.env, CARRIER.json and SHA256SUMS. A diff of the sorted JSON showed exactly two changed keys: `bindings_sha256` `c5ce191c…` to `2d6d48cd2be8feb19f1306b0455c1820c597a6c18df328147439b348a3ed47d2`, and `interface_content_ref` 81f2321b… to `d57fa62f2393363284a29a6d4024e6f9dfa66ac4`. The raw `diff` of the two CARRIER.json files is a single line. The rest follows from those two changes:

- CARRIER.env changed only `interface_content_ref`.
- BINDINGS.sha256 changed only the CARRIER.env line.
- SHA256SUMS changed only the ACCEPTANCE.json, BINDINGS.sha256, CARRIER.env and CARRIER.json lines.

`sha256sum BINDINGS.sha256` printed `2d6d48cd…`, which equals `bindings_sha256`. `sha256sum -c --quiet SHA256SUMS` and `sha256sum -c --quiet BINDINGS.sha256` both printed no failures. `diff -r -q -x seats -x ACCEPTANCE.json` between the plebian-os checkout's `releases/0.2.3-model-compliance` at 71aceb8 and the seat-input candidate copy printed nothing, so the copy is the committed carrier.

For context, this session also compared the candidate with the last seat-approved carrier (c1e3612). Every difference is one of three things:

- the v9 delivery: the archive digest and size, manifest, record and artifact digests, a new NOTICE text 65e4cd26 replacing e03643ad, and the COMMAND-MODEL.json, ARTIFACT.json, NOTICE and DELIVERY files;
- the notice decision: `affirmative` to `informational`, with `agreement_required` true to false in the determination, and the owner's words "1: debian-style." recorded verbatim with the date 2026-11-07;
- the licence, content and voice refs: `interface_licence_ref` to 0984dd22, `interface_content_ref` to d57fa62, and `voice_ref` to 1a4e63b. The three speech DELIVERY files changed only their kilix-voice ref.

That is the same content the earlier seats found correct in the 458d48d carrier.

## Claim 4: plebian-os 458d48d to 71aceb8

`git log --oneline 458d48d..71aceb8` printed one commit, `71aceb8 Check that the Needle the catalog selects serves the carried LFM2 terms`. `git diff --stat` listed 12 files:

- **The CI workflow file (`test.yml`)**: one added fetch of Needle's vendored kilix-content commit for AC-8.
- **CHANGELOG.md, releases/0.2.3-notes.md and releases/0.2.3-command-model.json**: Kilix 52ba3cd1 becomes b0c8939b, content 81f2321b becomes d57fa62f, Needle 3a8e41c5 becomes 5cbff317, and the manifest note now says Needle 5cbff317's commands-model.json describes this delivery.
- **releases/0.2.3.env and releases/0.2.3.requirements**: the KILIX_REF, carrier sha256, receipt sha256 and content ref pins.
- **The carrier files**: as above.
- **tests/test_model_compliance_carrier.py**: the new test and its helper `needle_vendor_gaps`.

`git diff --quiet 458d48d 71aceb8 -- provision build` exited 0, so the image installer and the release guard did not change from the rejected candidate. No other difference exists.

## Claims 1 to 3: the other commits

**kilix-needle 3a8e41c5 to 5cbff317** is one commit (`5cbff31 Vendor the kilix-content that carries LFM2's notice record`), touching seven files:

- `third_party/kilix-content` gitlink moves from 23cc16c9 to 81f2321b.
- `commands-model.json` now names version `lfm2-kilix-commands-20261106-v9`, weight `lfm2-kilix-v5e1-wse-20261106.9`, model sha256 3fa22c10…, NOTICE.txt 65e4cd26… at 1545 bytes, and parent `lfm2-kilix-v5e1-wse-20261106.8`.
- `asset.py` changes one message from "its licence can only be accepted at a terminal" to "its licence terms can only be shown at a terminal".
- `tests/test_asset_vendored_notice.py` is new.
- `tests/test_apps.py` adds `NOT_YET_LAUNCHABLE = {"kilix-find", "kilix-power-controls", "playalong"}`.
- Two changes the builder did not list:
  - The README paragraph that names the pinned delivery now names v9 and says the vendored content supplies the same asset and licence record the image installs.
  - In `tests/test_commands_runtime.py`, the expected model sha256 changes to 3fa22c10….

  Both are mechanical consequences of claim 1, because they describe the delivery the new vendored catalog selects. This session does not count them as defects.

Moving the vendored content from 23cc16c9 to 81f2321b also brings in these catalog changes:

- assets: `paradee-8m-v1.2` added; `kilix-diarization-cpu` and `lfm2-kilix-commands` changed;
- content entries: `kilix-find`, `kilix-power-controls` and `playalong` added; `kilix-help-llm` and `kilix-needle` changed.

These are the 81f2321b content that the earlier carrier was built against and that the earlier seats reviewed. They are not new content.

**kilix-content 81f2321b to d57fa62** is one commit (`d57fa62 Select the Needle that vendors LFM2's notice record`) touching five files:

- The only catalog line that changed is the kilix-needle `ref` (3a8e41c5… to 5cbff317…).
- `receipt.py` re-pins `_CATALOG_SHA256` to `4ad9e665…`, and `git show d57fa62:src/kilix_content/catalog/plebian.json | sha256sum` printed `4ad9e66586d6f35088fe70d037b56b69153a53f6cd9842d2f208901b8c7ea419`.
- The two pin tests and the CHANGELOG follow.

No asset or licence record changed.

**kilix 52ba3cd1 to b0c8939b** is one commit (`b0c8939 Say a notice licence's --from receipt claims no agreement; content d57fa62.`) touching four files:

- The gitlink moves to d57fa62.
- In `config/content_models.py`:
  - the module docstring, the `--from` plan note, the `--from` screen line and `_FROM_HELP` now say that for a notice licence the receipt records that the terms were shown and claims no agreement;
  - the plan note keys on the catalog decision `affirmative`, and the screen line keys on the record's expected decision `accept`.
- The README paragraph for `--from` says the same.
- One test is added.

## Every route that installs LFM2

### Image installer (provision/install-image-models.py at 71aceb8)

This session read `install_command_model`. It does the following:

1. It checks the staged archive's size and sha256 against the image pin.
2. It requires the catalog asset to equal the pin field by field.
3. It refuses any record that is standard-policy eligible.
4. For an uncovered record it raises `command model terms need a typed agreement; the image never answers one` unless `record.expected_decision` is `record`.
5. Only then does it call `lic.capture_agreement(record)` and write `receipt_from_agreement` with Kilix's catalog digest and release digest.

An AST scan printed `capture_agreement calls: [(253, 1, [])]` (one call, one argument, no keywords) and `string constants 'yes'/'y': []`. `grep -rn "capture_agreement\|typed_text\|capture_standard_policy" provision build` found only that line. The script is called from `provision/plebian-os-provision.sh` (fresh install, `--offline`), `provision/plebian-os-update.sh` (upgrade) and `build/remaster-iso.sh` (`--verify-only`). `provision/command-model.json` names version v9, weight 20261106.9, sha256 ea03c42c…, 1362204317 bytes and manifest ef701ec2…. The DELIVERY and release-notes sentences say the notice receipt claims no agreement, the terms are shipped and not waived, and typed-agreement terms are never answered by the image. Those sentences match this code.

### kilix-license 0984dd22

A probe of `capture_agreement` printed:

- For `lfm2-kilix-commands`: answer `None` gave decision `record` with typed `None`. The answers `'yes'`, `'y'`, `'no'` and the exact typed line each raised `AgreementRequired`.
- For `lfm3-kilix-commands` (digest 4759e37d…, decision class `affirmative`, expected `accept`, `agreement_required [True]`): `None` and `'no'` raised `AgreementRequired`, while `'yes'`, `'y'` and the exact line gave `accept`.

So the LFM2 record refuses every typed answer, and LFM3 still requires agreement. `cmp` of kilix-license's `src/kilix_license/data/lfm2-records/lfm2-kilix-commands.json` with the carrier's `LICENCE-RECORD.json` found them byte-identical (sha256 e65b49ba…). `standard_policy_eligible` is false for the LFM2 record, as the package's own test asserts.

`make sync` and then `make test` (TMPDIR under the work directory) ran 220 tests: 219 passed, 2 were skipped, and 1 failed. The failure, `test_all_record_families_and_notice_bytes_survive_wheel_install`, raised `ModuleNotFoundError: No module named 'setuptools'`. setuptools is a build-system requirement that the lock does not install. Rerun with setuptools supplied (`uv run --frozen --no-sync --with 'setuptools>=77' … python -m unittest tests.test_wheel_records`), the test printed `Ran 1 test … OK`. This is a property of this machine, not of the commit.

### Kilix b0c8939b's content (d57fa62) and Needle 5cbff317's vendored content (81f2321b)

`git rev-parse b0c8939b:third_party/kilix-content` printed d57fa62f2393363284a29a6d4024e6f9dfa66ac4. `git rev-parse 5cbff317:third_party/kilix-content` printed 81f2321b51649effc3275493a351931497c3ba0f.

For each content commit, this session read the catalog's `lfm2-kilix-commands` asset and the vendored kilix-license LFM2 record:

- **d57fa62**: the record hashed to `e65b49ba4428f227c0765f2aa6ce6816c2fa756ff7d4432b8466a0d481239d28`. The asset printed `equals carried ARTIFACT.json True version lfm2-kilix-commands-20261106-v9 decision informational digest e4d08e2c`.
- **81f2321b**: the same two lines.
- **23cc16c9**, the copy 3a8e41c5 vendored: the record hashed to `ed4225d1…`, and the asset printed `equals carried ARTIFACT.json False version lfm2-kilix-commands-20261104-v8 decision affirmative digest 9db4f674`.

The carrier's LICENCE-RECORD.json hashes to e65b49ba…. d57fa62 and 81f2321b carry the same vendored kilix-license tree (3797b74e…). Its pin file reads 0984dd222bcb7f97859222b0dc2303b9225191fe. Comparing every one of its 192 files with kilix-license 0984dd22 printed `vendored files 192 differ 0 only-vendored 0`. Both routes therefore serve delivery v9 with the carried asset and licence record, byte for byte.

### `kilix-needle install --commands` in a clone of Needle 5cbff317

This session ran `git submodule update --init` and `git submodule status` printed `81f2321b… third_party/kilix-content`. With HOME, GPU_TERMINAL_HOME and KILIX_DATA_HOME inside the work directory, it ran each command under a pseudo-terminal, using `printf '<answer>\n' | script -qefc "./kilix-needle install --commands[ lfm3] --from <extracted archive root>" <log>`:

- **LFM2, answer `n`**: exit 1. The log ends `These terms are a notice and take no agreement.` / `Install this exact model? [y/N] kilix-needle: not installed; nothing was written or downloaded`. No file was written under the test home or data root.
- **LFM3, answer `y`**: exit 1. The log ends `To accept, type exactly:` followed by the exact agreement line, then `kilix-needle: not accepted; nothing was written or downloaded`. Nothing was written.
- **LFM2, answer `y`**: exit 0. The log ends `Install this exact model? [y/N]   reading 40 supplied file(s) for lfm2-kilix-commands …` and `installed: …/desktop-apps/assets/lfm2-kilix-commands--ef701ec2c8fb6a46bbe733d51a6be498e325bb60d3b45ec8938f0ed0ba1aef50`.

The LFM2 screen shows `version: lfm2-kilix-commands-20261106-v9` and `decision: informational`, and the sections `licence`, `component:native-runtime`, `binding:commercial-use-limitation` and `statement:modified-model`. A script that searched the captured screen printed `full text on screen: True` for the licence text 4d28ca14 (10574 bytes), the runtime notice 571c0295 (12682 bytes) and the modified-model notice 65e4cd26 (1545 bytes). It printed `commercial-use condition text 17f031ac on screen: True` (560 bytes), and found no "To accept", "type exactly" or "I agree" on the LFM2 screen. The install asked only to confirm the install, and the code path passed `typed=None`.

The receipt it wrote is named `e4d08e2c…-ef701ec2….json`. It has `"decision": "record"`, `"binding_condition_text_digests": {}`, `"record_digest": "e4d08e2c…"`, `"manifest_digest": "ef701ec2…"`, `capture_mode` `interactive-tty`, and no typed text.

`kilix-needle install` (with or without `--from`), the first-use path in `needle_cli.py` and `workflows.py` all reach the same `asset.install`. Kilix's model wizard hands Ask models to `kilix app run kilix-needle -- workflows`, and `config/model_wizard.py` is unchanged from 52ba3cd1 to b0c8939b. Kilix's own `kilix models install` path (`config/content_models._install`) shows the authority's screen, asks `Install this exact model in the shown root? [y/N]`, and passes `typed = None` unless `record.expected_decision == "accept"`, in which case it asks a separate yes or no agreement. Kilix's default-model bundle (`config/default_models.authorize`) refuses any record that is not standard-policy eligible, which excludes LFM2.

### A receipt written the way the image writes it covers the asset Needle serves

This session wrote an LFM2 receipt into an empty store using the image installer's calls (`capture_agreement(record)`, then `receipt_from_agreement` with `catalog_sha256()` and `release_digest()`), importing kilix-content d57fa62 and its vendored kilix-license. The script printed `image-style receipt written: content catalog 4ad9e665 record e4d08e2c decision record typed None manifest ef701ec2`. A second process that imported Needle's own `asset._content()` then asked `first_use.needs_agreement` against that store:

- At Needle 5cbff317 it printed `Needle serves lfm2-kilix-commands-20261106-v9 manifest ef701ec2 record e4d08e2c -> needs_agreement with image receipt: False`.
- At Needle 3a8e41c5 (a separate worktree with its submodule at 23cc16c9) it printed `Needle serves lfm2-kilix-commands-20261104-v8 manifest db2674e0 record 9db4f674 -> needs_agreement with image receipt: True`. That reproduces the previous defect.

kilix-license `covers()` compares the manifest, licence id, licensor, licence text digest, binding digests, decision and record digest. It does not compare `catalogue_digest`. So the difference between the image receipt's catalog digest (4ad9e665) and the one Needle writes (3bc0dac2) does not affect coverage.

In Needle 5cbff317, `python3 -B -m unittest discover -s tests -p 'test_asset*.py' -v` printed `Ran 23 tests … OK (skipped=1)`, including the three tests in `test_asset_vendored_notice.py`. `test_apps.py` printed `Ran 101 tests … OK`, and `test_commands_runtime.py` printed `Ran 7 tests … OK`. The full `discover` printed `Ran 1687 tests … FAILED (errors=6, skipped=6)`. All six errors are in `test_app_controls` and are `OSError: AF_UNIX path too long`, because the socket paths are built under this deep work directory. The same six fail identically at 3a8e41c5, and neither commit changes `test_app_controls.py` or the app-controls code. They are environmental.

In Kilix b0c8939b with its kilix-content submodule initialized, the new `test_from_a_notice_licence_says_its_receipt_claims_no_agreement` and the `SuppliedDirectoryOptionTests` class printed `Ran 5 tests … OK`. The whole `tests.test_content_models` module printed `Ran 40 tests … FAILED (failures=3)`. The three failures are subtests of the unchanged `test_from_real_install_reads_the_directory_and_fetches_nothing`, which asserts the receipt store is not under the account's passwd home. That cannot hold when the work directory itself is under that home, so this is environmental. In kilix-content d57fa62, `tests.test_detector_pins` and `tests.test_pdf_pin` printed `Ran 2 tests … OK`.

## The previous defect cannot silently return: the new AC-8 test both ways

With the sibling checkouts at the candidate commits, `python3 -m unittest tests.test_model_compliance_carrier -v` at 71aceb8 printed `Ran 17 tests … FAILED (failures=1)`. `test_command_model_records_needle_serves_are_the_carried_ones … ok`, and AC-1 to AC-6 and AC-8 to AC-12 passed. The one failure is AC-7, `test_acceptance_receipt_names_two_independent_seats`. It fails because the committed receipt's seat records predate this candidate and do not name bf003bf7…. The brief says the receipt is regenerated after this review, so this is expected and is not a defect of the candidate.

To point the test at Needle 3a8e41c5, this session ran a script that imports the test module, patches only its `manifest()` so `PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF` reads 81f2321b, and runs the test method. 81f2321b's catalog selects Needle 3a8e41c5, and `git show 81f2321b:…plebian.json` confirmed the ref `3a8e41c52f32f963c4bbeadfbec69b200f13eafe`. The run printed `FAIL: test_command_model_records_needle_serves_are_the_carried_ones` and listed three gaps:

- `lfm2-kilix-commands: Needle's vendored asset record is not the carried one`
- `lfm2-kilix-commands: Needle's vendored licence record is not the carried one`
- `lfm2-kilix-commands: Needle's commands-model.json does not describe the carried asset`

It ended `pointed at 3a8e41c5: failures 1 errors 0`. Calling `needle_vendor_gaps` directly printed `[]` for Needle 5cbff317 (vendored 81f2321b) and the same three gaps for Needle 3a8e41c5 (vendored 23cc16c9). The test's own planted defects (the old delivery version, an affirmative record, and an old commands-model version) each yield exactly one gap, as asserted.

## The release guard (build/remaster-iso.sh at 71aceb8)

The guard's per-model decision check is `case "${cv[${prefix}decision]}" in affirmative|informational) ;; *) carrier_refuse "$model licence decision is not affirmative or informational"`. This session wrote a probe that reuses the test module's `run_guard`, `release_env`, `edit_env` and `rebind`, so every digest and both pins are re-derived and the decision branch itself is reached. It printed:

- `control (unmodified candidate carrier): 0`
- `lfm2 decision='informational': rc=0`
- `lfm2 decision='affirmative': rc=0`
- `rc=1 decision refusal` for each of `'record'`, `'accept'`, `'pending'`, `'negative'`, `'waived'` and `'Informational'`

AC-9, AC-10 and AC-11 also passed in the run above. The guard accepts only the affirmative and informational decisions and refuses anything else.

## Pins

The pins read as follows:

- **releases/0.2.3.env**:
  - `KILIX_REF=b0c8939b05b7c2b6ffad9d90f10f0a31ec194a9a`
  - `KILIX_LICENSE_REF=0984dd222bcb7f97859222b0dc2303b9225191fe`
  - `KILIX_VOICE_REF=1a4e63b11d0ad9c1664031e2773f5c4f5797913f`
  - `PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF=d57fa62f2393363284a29a6d4024e6f9dfa66ac4`
  - `PLEBIAN_OS_VOICE_CARRIER_SHA256=bf003bf70e6059e3ec7b458ea4e7b26266383486825f361a472e7efc5f1f71ac`
  - `PLEBIAN_OS_VOICE_CARRIER_RECEIPT_SHA256=5bc3b72aebbac912db5c6f03c252d604994e5942bf51c964635d486816e9388c`
- **releases/0.2.3.requirements**: the same values for `PLEBIAN_OS_VOICE_CARRIER_SHA256`, `PLEBIAN_OS_VOICE_CARRIER_RECEIPT_SHA256`, `KILIX_LICENSE_REF` and `PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF`. It carries no `KILIX_VOICE_REF`; `git show c1e36124:releases/0.2.3.requirements | grep -c KILIX_VOICE_REF` printed `0`, so the approved commit carried none either.
- **The carrier**: binds `voice_ref` `1a4e63b11d0ad9c1664031e2773f5c4f5797913f`, `interface_licence_ref` 0984dd22…, and `interface_content_ref` d57fa62….
- **KILIX_REF's content gitlink**: `git rev-parse b0c8939b:third_party/kilix-content` printed `d57fa62f2393363284a29a6d4024e6f9dfa66ac4`, equal to the carrier `interface_content_ref` and to `PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF`.
- **The catalog's Needle ref**: reading the d57fa62 catalog printed `catalog needle ref ['5cbff3172224d5277adee5a3c826ee4b0698917a']`.

The SHA256SUMS line for ACCEPTANCE.json (5bc3b72a…) equals the receipt pin.

The kilix-voice licence gate the DELIVERY sentences name still exists at 1a4e63b:

- `kilix-stt` defines `_check_licence` and the `--check-licence` argument, and `git diff --quiet 1faf9fb 1a4e63b -- kilix-stt` exited 0.
- The 1faf9fb to 1a4e63b diff touches only `kilix-tts`, `voicelib/licensing.py` (adding the female-02 voice to `CHECK_TOOL_BY_MODEL`), `voicelib/system_voice.py` and one test.
- With an empty receipt store inside the work directory, `./kilix-stt --check-licence lgraph-en-us` and `./kilix-stt --check-licence vibevoice-asr-bitnet` each printed a refusal beginning `kilix-stt: refusing to fetch the … model weights` and exited 3.

## Generator check

This session made a writable copy of the candidate carrier at `…/work/carrier-copy`. It built one `--determination MODEL=PATH` per file under `determinations/` (MODEL is the parent directory name) and one `--seat PATH` per file under `seats/`, both in `LC_ALL=C sort` path order: nine determinations and two seats. From the plebian-os clone at 71aceb850bf5f08f2ef779a35ebf16b4b3c2f8a8 it ran:

`python3 build/generate-model-compliance.py --content-repo work/kilix-content --license-repo work/kilix-license <those arguments> --out <copy> --check`

with kilix-content checked out at d57fa62f2393363284a29a6d4024e6f9dfa66ac4 and kilix-license at 0984dd222bcb7f97859222b0dc2303b9225191fe. It printed nothing and exited 0. `diff -r -q` of the copy against the read-only candidate afterwards printed nothing.

## Full plebian-os suite

From the plebian-os clone at 71aceb8, `python3 -m unittest discover -s tests` (TMPDIR and HOME inside the work directory) exited 1. It reported failures in eight tests, 13 failing cases in all. To see which of them this candidate introduced, this session created worktrees of plebian-os at the approved c1e36124 and the rejected 458d48d next to the same sibling clones. At each of the three commits it ran the five affected modules, plus `discover -p test_runnable_models.py`. The modules were `tests.test_build_vm_image`, the carrier-wrapper test module, `tests.test_provision_lifecycle_behavior` and `tests.test_voice_release_contract`, and `tests.test_runnable_models` through `discover`.

**Failing already at the approved c1e36124, and unchanged:**

- `test_build_vm_image` `test_rollback_reaches_the_unpublished_selected_closure` and `test_successful_update_keeps_selected_closure_and_restart`. Both expect `SELECTED:0.2.2:…` and get `SELECTED:0.2.3:…`.
- The carrier-wrapper module's `test_building_wrapper_dry_runs_show_the_shared_carrier`, with `release 0.2.2 must match the manifest and checkout VERSION`.
- The carrier-wrapper module's `test_remaster_selects_argument_or_environment_and_canonicalizes`, with `PLEBIAN_OS_DEFAULT_MODELS_BUNDLE must name the release's default model archive`.
- Four subtests of `test_voice_release_contract` `test_documents_describe_the_first_use_route_the_code_takes`. RELEASING.md lacks four expected sentences.
- `test_runnable_models` `test_the_pinned_voice_runs_every_runnable_model`, in its `lfm2-kilix-commands` subtest, with `lfm2-kilix-commands is not in the pinned voice catalog`. The test skips only the diarization model, and LFM2 is not a kilix-voice model.

**New since the approved commit, present identically at the rejected 458d48d, and unchanged by 71aceb8:**

- `test_provision_lifecycle_behavior` `test_release_dictation_requires_the_complete_voice_closure` fails with `release mode requires KILIX_SECRETS_REF to be a full 40-character lowercase commit SHA`. The test's hermetic fixture does not supply the `KILIX_SECRETS_REF` that be1bd99 (`Install Kilix Secrets in the 0.2.3 closure.`) made mandatory. releases/0.2.3.env does pin `KILIX_SECRETS_REF=da05600d…`.
- `test_runnable_models` `test_the_pinned_kilix_builds_the_vibevoice_runtime` fails with `'KILIX_VOICE_REF:-1a4e63b11d0ad9c1664031e2773f5c4f5797913f}' not found` in KILIX_REF's `scripts/install-kilix-voice.sh`. Reading that script at each commit printed:
  - c1e36124: KILIX_REF d7cf37e8, env KILIX_VOICE_REF 1faf9fb0, Kilix default 1faf9fb0
  - 458d48d: KILIX_REF 52ba3cd1, env KILIX_VOICE_REF 1a4e63b1, Kilix default 1faf9fb0
  - 71aceb8: KILIX_REF b0c8939b, env KILIX_VOICE_REF 1a4e63b1, Kilix default 1faf9fb0

  The release moved KILIX_VOICE_REF to 1a4e63b in a1598db, between the approved and the rejected commits, but Kilix's voice installer still defaults to 1faf9fb. On the image this has no effect. `provision/plebian-os-provision.sh` passes `KILIX_VOICE_REF=$KILIX_VOICE_REF` explicitly to the install, verifies that the installed voice checkout equals the pinned ref, and writes `KILIX_VOICE_REF` into the session defaults. A `kilix voice install` run inside a Plebian-OS session therefore gets 1a4e63b. Only Kilix run outside such a session would fall back to 1faf9fb. In both commits `kilix-stt` and its `--check-licence` gate are identical (`git diff --quiet 1faf9fb 1a4e63b -- kilix-stt` exited 0). So the speech DELIVERY sentences describe a gate that exists whichever of the two is installed.

**Expected:** AC-7, as explained above.

None of these failures is introduced by 71aceb8. None involves LFM2's terms, records or receipts, the carrier bindings, or the release guard.

## No terms waived or hidden

The determination, the kilix-license record and CHANGELOG, the carrier DELIVERY, the release notes, the Needle README and install screen, and the Kilix `--from` wording all say that LFM2's terms, including the commercial-use limitation, are a notice: shown, shipped and not waived, with no agreement taken or recorded. This session found no route that hides the terms. The Needle screen carries the full licence, the full commercial-use condition, the runtime notice and the modified-model notice. The image ships the notices under `/usr/local/share/doc/plebian-os/models/`, which `provision/stage-command-model.py` and the installer's final message name. This session found no route that types or records an agreement for LFM2, and no route that drops the agreement LFM3 requires.

## Observations that are not defects

- The new test sits between the AC-4 and AC-5 blocks, with no `# AC-8` marker. ACCEPTANCE.json's `qualification` list still names only `test_delivery_statement_is_true_of_this_image` for AC-8. That list follows the same one-test-per-criterion convention the approved receipt used, which also leaves out `test_carried_records_are_the_ones_the_image_serves`. The new test runs in the normal suite and in CI, and it fails when the defect returns. This session does not count this as a defect.
- The shell guard accepts `affirmative` as well as `informational` for LFM2. It checks only the decision class. The actual value is bound by AC-1, AC-3 and the bindings. This is what the brief asks of the guard.
- The receipt Needle writes and the receipt the image writes carry different `catalogue_digest` values (3bc0dac2 and 4ad9e665), because Needle vendors 81f2321b and Kilix vendors d57fa62. Coverage does not compare that field, and the cross-coverage run above shows the image's receipt covers Needle's asset.
- Kilix's `kilix models install` accepts a yes or no answer for an `accept` record rather than the exact line. kilix-license also accepts `yes` and `y` for LFM3. Both predate this candidate and are unchanged by it. LFM3 still requires agreement on every route, and Needle still requires the exact line.
- Environmental test failures, all explained above: the kilix-license wheel test without setuptools, six Needle socket tests with a long path, and three Kilix subtests that refuse a store under the account's home.

## Known issues

These are defects this session found. Both are outside this candidate's delta, inherited unchanged from the rejected 458d48d, and unrelated to LFM2:

1. KILIX_REF b0c8939b's `scripts/install-kilix-voice.sh` defaults `KILIX_VOICE_REF` to 1faf9fb07ec04af3c7b6c130c4bd1fd315c25dc4, while releases/0.2.3.env pins, and the carrier binds, 1a4e63b11d0ad9c1664031e2773f5c4f5797913f. The release's own `test_the_pinned_kilix_builds_the_vibevoice_runtime` fails on this. Provisioning passes and session-defaults the pinned ref, so the image installs 1a4e63b, and both refs carry the same licence gate. The two should still be brought into agreement, or the test changed deliberately.
2. `test_release_dictation_requires_the_complete_voice_closure` fails because its fixture does not supply the KILIX_SECRETS_REF that release mode now requires.

The failures listed above that already fail at the approved c1e36124 are older test and document drift. This candidate neither introduced nor changed them.

## Result

Every required identity matched. The carrier differs from the rejected 458d48d carrier only by `interface_content_ref` and `bindings_sha256`, with CARRIER.env, BINDINGS.sha256 and SHA256SUMS following. Each commit's changes are the builder's claims 1 to 5 or their mechanical consequences. Every LFM2 install route serves the owner's notice decision and the carried records:

- the image installer;
- Needle 5cbff317 with its vendored 81f2321b;
- Kilix b0c8939b with d57fa62;
- kilix-license 0984dd22.

The new AC-8 test passes at the candidate and fails against Needle 3a8e41c5. The release guard admits only the affirmative and informational decisions. The generator check passes. Every pin and receipt gate the brief names matches. This session found no defect in what the candidate changes. The two known issues above are inherited, outside the LFM2 scope, and do not change what the image installs.

VERDICT: ship with known issues
