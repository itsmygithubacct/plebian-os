# Seat A review of the Paradee RC8 candidate

Date: 2026-11-10. This review covers the five source gates in the seat A brief. The five gates pass. AC-7 remains open, and the Kilix 95 continuous-integration host pin is stale.

The SHA-256 this session computed for the committed `releases/0.2.3-model-compliance/CARRIER.json` is `9701a082220b3d5d6f5306a16875d66c0ab70f24f75769250bbc93b927312605`.

The `sha256` field this session read from that carrier's committed `DEFAULT-MODELS.json` is `e00614bf726154d09668820c061cbbcb402239a445bde666b0568d36f01528a6`.

## Eligibility

The builder session launched this pane on 2026-11-10 and wrote the brief, as the brief records. This session did not author the candidate. This session did not author the commits under review, the catalogue, the licence records, the wizard, the runtime, the image installer, or the compliance carrier. Seat A confirmed its eligibility before writing this report.

This session cloned the public repositories afresh into `work/` and checked out the named commits. It did not use an existing local worktree, consult the other seat's directory, the builder session's worktrees, or an earlier review folder, or start other agents. The required carrier tests process the old seat texts committed inside the candidate carrier; their contents were not used as review evidence. This session made no commits, pushed or published nothing, and changed no candidate source or release acceptance record. All candidate and dependency checkouts were clean at the end.

There was one review-procedure deviation. A preliminary native-state-library build inherited the live user cache destination and wrote generated build files outside the allowed work directory. This session corrected the build environment, rebuilt the library inside `work/runtime/`, and reran the affected checks there. The reported passing results use that subsequent build. The preliminary build changed no source checkout. This session did not attempt to delete shared cache files.

## Candidate identities

This session checked the full commit IDs, ordered parent lists, author and committer name and email fields, commit messages, and public `work/0.2.3-rc8-followups` branch tips. Every author and committer identity is the same repository owner account used by the builder session. Those identity fields agree across all five commits. No candidate message has a co-author trailer. The public tips matched at the initial check and again at the final check; no branch advance occurred during those checks.

The plebian-os commit is `43c1918bab88e0669dad4d80e4c7362e8f245291`. Its parent is `c3d2dceeb8b93da442344a0e01f473d9adcd76b4`.

The Kilix commit is `b1596021881e5239f2cba631361f66530905658d`. Its parent is `8128a11aed657ad78a87168ddd31d56d76cfff8e`.

The Kilix 95 commit is `9fae665d70e682f6274266dc8c75b1fcef03b206`. Its ordered parents are `a4e73d0595a677430fae1d67bc3284bcfe097c00` and `5c23839c6a6e97235795a0ce863efbbcd8340790`.

The kilix-license commit is `f33fdf2a0e8396bd32f3617633629bc3f7973e79`. Its parent is `2737f321c49371c08d2b624190fda7719a13a52a`.

The kilix-content commit is `f9ba621eb7ca41a8e3913f60118596929ca7f1cc`. Its ordered parents are `dfcda81bcbb9808f9645339338720f976123487d` and `543e46736e66e1f8ec1c94c80cc7eee8d8d9b63f`.

At the plebian-os commit, `VERSION` is `0.2.3`. `releases/0.2.3.env` names the four component commits above and sets `PLEBIAN_OS_REF=v0.2.3-rc8`. Its comments explicitly describe a local, unpushed tag and leave acceptance open. The fresh clone cannot resolve that tag, and the public tag lookup returns no matching ref. This is the stated local-tag condition. This session did not move or create the tag.

## Gate 1: voice selection and runtime notices

Kilix contains `config/paradee_runtime.py`, `config/paradee_synth.py`, and the launcher interception for Paradee. `config/model_wizard.py` installs `paradee-8m-v1.2` and saves engine `paradee`, voice `af_heart`, when there is no valid saved selection. It returns before installation or selection writes when a saved engine and voice already exist. Female-02 remains an offered speech choice; explicitly choosing it selects Piper and saves `kilix-female-02`. A Female-02 installation failure does not undo the fresh Paradee selection.

The runtime's `install_check()` and `synthesize()` both call `model_files()`. That function checks the weights, configuration, and `notices/LICENSE-apache-2.0.txt`. The Apache text must be a regular, nonsymlink file of 11358 bytes with SHA-256 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`. This session staged the actual pinned model files and confirmed a valid installation check. Its additional probes removed the notice, changed one byte while preserving its size, and replaced it with a symlink. Both installation and synthesis refused all three defects before launching synthesis.

Kilix's `third_party/kilix-content` gitlink is exactly `f9ba621eb7ca41a8e3913f60118596929ca7f1cc`. The Kilix 95 system-voice test passes against the candidate Kilix host and recognizes `System voice ready: paradee af_heart`. An additional direct check of `default_voice_command()` confirmed that a launcher whose basename is not `kilix` still installs and selects `kilix-female-02`.

## Gate 2: carrier and bundle

Both `paradee-8m-v1.2` and `en-core-web-sm-3.8.0` have delivery mode `image-offline-model` in the carrier. Each NOTICE says, "Plebian-OS distributes these model bytes in a verified archive on installation media." Neither NOTICE says those bytes are absent. Each DELIVERY says provisioning uses the supplied bytes offline, an online install uses the same archive, and a missing archive is an error.

The carrier binds the reviewed kilix-content and kilix-license commits. The record, catalogue, determination, delivery, and regeneration checks pass. The checked licensor fields are `Sahil Mahendrakar` for Paradee and `ExplosionAI GmbH` for en_core_web_sm. Every one of the carrier's 83 listed file checksums passes.

The carried default inventory equals `provision/default-models.json`, which is byte-identical to the candidate's parent version. It still contains nine assets including `kilix-female-02`. Neither Paradee nor en_core_web_sm is in that bundle. Both separate image pins declare `since_release` as `0.2.3-rc8`. The carrier digest and default-bundle digest are quoted at the beginning of this report and match the release environment.

## Gates 3 and 4: interpreter and image delivery

`install_paradee_venv()` creates the interpreter with the equivalent of `python3 -I -m venv --copies`. It refuses an existing symlink interpreter and checks that the newly created interpreter is a regular nonsymlink file. The image-model test creates a real copied interpreter and confirms `--no-index` wheel installation.

The archive builder includes `notices/LICENSE-apache-2.0.txt`. The runtime stage verifies and copies that member, and preseed explicitly extracts it beside the weights and configuration. The remaster step verifies the two model archives before putting them on the image. Provisioning stages the runtime before installing the image models. The Paradee and en_core_web_sm installation functions refuse missing archives for models not already verified; neither branch falls back to a download. This session also exercised both missing-archive refusals with downloading forbidden.

This session downloaded the pinned Paradee ONNX and configuration and the en_core_web_sm wheel. All three upstream files matched their committed sizes and hashes. Rebuilding with the committed archive builders produced Paradee at 8478720 bytes, SHA-256 `61e95049263a04897b1cc69923aaed0eb33d47d610763d9055de14b4f52b908a`, and en_core_web_sm at 12820480 bytes, SHA-256 `eedbef109150c8b8f0534fae3ac6ee1a79d9616f09f638247c35a7a309f180fb`. Both exactly match their image pins.

## Gate 5: espeak-ng provenance and loading

The downloaded espeakng_loader 0.2.4 wheel is 10078484 bytes with SHA-256 `08721baf27d13d461f6be6eed9a65277e70d68234ff484fd8b9897b222cdcb6d`, matching the lock and source pin. It contains `libespeak-ng.so` and the speech data. The library reports version `1.52.0` through `espeak_Info`. The corresponding source README states GPL-3.0-or-later, and its COPYING contains GPL version 3. The loader's MIT licence covers the loader separately.

The repository carries the loader MIT text, build instructions, and `build.sh`. The text is 1069 bytes with SHA-256 `b05c73bb1335b4320ec97edff106b3991c12d0acdc6e899c96f061a15039119f`. This session compared that text and the build script byte for byte with their recorded upstream revisions. The workflow at loader commit `146599e29be31bf17d99f0bcb7dbb2f92aef3d95` clones espeak-ng tag `1.52.0` and runs that script.

This session downloaded the exact URL in `provision/espeak-ng-source.json`: `https://github.com/espeak-ng/espeak-ng/archive/refs/tags/1.52.0.tar.gz`. The result is 17739803 bytes with SHA-256 `bb4338102ff3b49a81423da8a1a158b420124b055b60fa76cfb4b18677130a23`. Both values match the pin. The source tarball is not committed. The remaster step downloads and verifies it, and preseed installs it with the loader text and build materials.

The synthesis module imports `misaki.espeak`. In the exact locked Misaki wheel, that module calls `EspeakWrapper.set_library(espeakng_loader.get_library_path())` and sets its data path from the same loader. The locked phonemizer wrapper honors that explicit library before looking for a system library. The runtime therefore uses the library supplied by espeakng_loader.

## Test results and limits

`work/run_review_tests.py` removed `PYTHONPATH` and `PYTHONHOME` before every test invocation, selected only the fresh review clones, and redirected test storage and temporary files into `work/`. The final native library used the reviewed state gitlink. The only initialized Kilix submodules were kilix-content at `f9ba621eb7ca41a8e3913f60118596929ca7f1cc`, kilix-state at `1fe26a35b9ed661bfaeb8aa9f4d1e38faeb2faf9`, and kitty-frame-presenter at `7e20193544e90ab0c0084ecbf61dea3e8bd4fe7c`.

The carrier checks additionally used fresh public dependency clones: kilix-needle at `a887e2fae221272aece6b7b9aef143df8bc7ba64`, kilix-voice at `1a4e63b11d0ad9c1664031e2773f5c4f5797913f`, and kilix-bonsai at `630da3cf64d28b35fb65cafd4e7c8a4ad54b8685`. Those are the dependency refs selected by the candidate sources. Their checkouts were not committed.

The Kilix `test_paradee*.py` runtime and launcher suites pass all 13 tests. The additional `test_model_wizard.py` suite passes all 47 tests, and `test_piper_tts_runtime.py` passes all three. Kilix 95's `python3 -B tests/test_system_voice.py` exits zero. Plebian-os `python3 -B -m unittest tests.test_image_models -v` passes all 48 tests. `python3 -B -m unittest tests.test_model_compliance_carrier -v` passes 16 of 17 tests, with only the expected AC-7 failure. The independent probes in `work/probe_gates.py` also pass.

The logs and probe scripts are under `work/`. This session did not build or boot a complete ISO or perform hardware audio acceptance. The synthesis guards were exercised with the actual pinned files; a complete utterance through the full wheel environment was not run.

## Known issues

AC-7, `test_acceptance_receipt_names_two_independent_seats`, fails because the attached seat texts quote the older carrier instead of `9701a082220b3d5d6f5306a16875d66c0ab70f24f75769250bbc93b927312605`. This is the open gate identified in the brief. The other carrier tests pass. This report does not update the release acceptance record or claim that AC-7 has closed.

Kilix 95's `.github/workflows/test.yml` pins host commit `763e6e88a16cc3c6f56ba7b3a343715389b8ecae`, which differs from candidate Kilix `b1596021881e5239f2cba631361f66530905658d`. Its normal continuous-integration job therefore does not establish this candidate pairing. This session's required system-voice test passed against the candidate host.

No required candidate identity, parent, record, hash, gitlink, voice-selection behavior, notice refusal, image-delivery claim, or espeak-ng source pin mismatched in this review.

VERDICT: ship with known issues
