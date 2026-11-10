# Seat B Paradee RC8 review, 2026-11-10

## Eligibility

The builder session launched this pane on 2026-11-10 and wrote the brief. This session did not author the candidate. This session did not author any commit under review, the catalogue, the licence records, the wizard, the runtime, the image installer, or the compliance carrier. Seat B confirmed eligibility before writing this report.

Candidate source and executable evidence came from fresh clones of the public repositories in the designated seat B work directory. No existing local checkout or external review folder supplied candidate evidence. The five candidate checkouts remained clean. No candidate source, tag, or committed acceptance receipt was changed. This session did not commit candidate changes, push, publish, or start additional agents.

## Commit identity and release pins

Seat B checked the public `work/0.2.3-rc8-followups` branch in each repository after cloning and again at the end of verification. At the final check, beginning at 2026-11-10 11:15:58 UTC, every remote branch tip equalled its named candidate. There was no Kilix branch advance to assess.

The plebian-os commit is `43c1918bab88e0669dad4d80e4c7362e8f245291`. Its sole parent is `c3d2dceeb8b93da442344a0e01f473d9adcd76b4`.

The Kilix commit is `b1596021881e5239f2cba631361f66530905658d`. Its sole parent is `8128a11aed657ad78a87168ddd31d56d76cfff8e`.

The Kilix 95 commit is `9fae665d70e682f6274266dc8c75b1fcef03b206`. Its parents, in recorded order, are `a4e73d0595a677430fae1d67bc3284bcfe097c00` and `5c23839c6a6e97235795a0ce863efbbcd8340790`.

The kilix-license commit is `f33fdf2a0e8396bd32f3617633629bc3f7973e79`. Its sole parent is `2737f321c49371c08d2b624190fda7719a13a52a`.

The kilix-content commit is `f9ba621eb7ca41a8e3913f60118596929ca7f1cc`. Its parents, in recorded order, are `dfcda81bcbb9808f9645339338720f976123487d` and `543e46736e66e1f8ec1c94c80cc7eee8d8d9b63f`.

All commit identities and parents match the brief. Each commit records the builder session's public repository account as both author and committer. The author and committer identity fields are identical across all five commits. Their SHA-256 fingerprint, using the recorded UTF-8 name, a space, and the angle-bracketed address, is `ff4d58ecc47678d6c136490d48b9786eb6ddc40121a6eddddc7aaba9733fa03d`. No candidate message contains a co-author trailer.

At the plebian-os commit, `VERSION` is `0.2.3`. `releases/0.2.3.env` names the four component commits above through `KILIX_REF`, `KILIX95_REF`, `KILIX_LICENSE_REF`, and `PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF`. It sets `PLEBIAN_OS_REF=v0.2.3-rc8` and explicitly describes that tag as local and unpushed. The fresh clone cannot resolve that tag, and the public remote has no matching tag. Seat B did not move it. This state is disclosed and is not itself a defect in these gates.

## Gate 1: Runtime and system voice

Kilix contains `config/paradee_runtime.py`, `config/paradee_synth.py`, and the launcher dispatch for Paradee. The wizard's fresh-install default is `paradee-8m-v1.2`, with engine `paradee` and voice `af_heart`. `ensure_default_system_voice()` returns before installation or persistence when a valid selection already exists. Female-02 remains offered and can be selected explicitly, which records engine `piper` and voice `kilix-female-02`. The wizard tests exercise fresh selection, preservation, explicit Female-02 selection, and continued Paradee selection when the optional Female-02 installation fails.

Both runtime installation and synthesis call `model_files()`. That check requires the regular file `notices/LICENSE-apache-2.0.txt`, exactly 11,358 bytes, with SHA-256 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`. Seat B also tested the actual pinned model files with the notice missing, truncated, replaced by different bytes of the same length, and replaced by a symlink. Installation and synthesis refused every case before launching synthesis.

Kilix's recorded `third_party/kilix-content` gitlink is exactly `f9ba621eb7ca41a8e3913f60118596929ca7f1cc`. Kilix 95 recognizes `System voice ready: paradee af_heart` and reports that Paradee is ready. Its system-voice test passes against the candidate Kilix checkout. `default_voice_command()` sends a launcher whose basename is `kilix` through the wizard; another launcher retains the Female-02 installation and Piper selection arguments. Gate 1 passes.

## Gate 2: Carrier, inventory, and records

The computed SHA-256 of committed `releases/0.2.3-model-compliance/CARRIER.json` is `9701a082220b3d5d6f5306a16875d66c0ab70f24f75769250bbc93b927312605`. The `sha256` field read from that carrier's committed `DEFAULT-MODELS.json` is `e00614bf726154d09668820c061cbbcb402239a445bde666b0568d36f01528a6`.

The default inventory equals `provision/default-models.json`, is unchanged from the named plebian-os parent, and contains nine assets including `kilix-female-02`. Neither Paradee nor en_core_web_sm belongs to that bundle. Both separate image pins record `since_release` as `0.2.3-rc8`.

The carrier records both `paradee-8m-v1.2` and `en-core-web-sm-3.8.0` as `image-offline-model`. Each NOTICE says that Plebian-OS distributes these model bytes in a verified archive on installation media. Neither notice says those bytes are absent. Each DELIVERY says provisioning uses supplied bytes offline, that online installation uses the same archive, and that a missing archive is an error.

The carrier's catalogue records, licence records, interface pins, text hashes, and regeneration checks pass. The Paradee licensor field is Sahil Mahendrakar with Apache-2.0; the en_core_web_sm licensor field is ExplosionAI GmbH with MIT. The downloaded spaCy wheel's licence and training-source notice match both committed notice hashes. The content repository's vendored licence pin is `f33fdf2a0e8396bd32f3617633629bc3f7973e79`; its verifier confirms all 217 vendored files equal the corresponding archive members at that commit. Gate 2 passes.

## Gate 3: Copied interpreter

`install_paradee_venv()` invokes the image interpreter with `-I -m venv --copies`. It refuses an existing symlink interpreter before installation and checks the resulting interpreter again after creation. The required image-model tests cover the invocation and refusal. Seat B separately created a real venv with `--copies`, confirmed its interpreter is a regular file, and exercised both the image installer's and runtime installation check's symlink refusal. Gate 3 passes.

## Gate 4: Archive, staging, and offline installation

Seat B downloaded the pinned Paradee ONNX and configuration and the pinned en_core_web_sm wheel, verified their lengths and hashes, and reproduced both image archives with the committed builder functions. Paradee reproduced at 8,478,720 bytes with SHA-256 `61e95049263a04897b1cc69923aaed0eb33d47d610763d9055de14b4f52b908a`. Its members are the ONNX file, `config.json`, and `notices/LICENSE-apache-2.0.txt`. The spaCy archive reproduced at 12,820,480 bytes with SHA-256 `eedbef109150c8b8f0534fae3ac6ee1a79d9616f09f638247c35a7a309f180fb`. Both results match their image pins.

`stage_paradee_runtime()` stages and verifies all three Paradee members, including the notice. Seat B exercised staging with the reproduced archive. `preseed/preseed.cfg` explicitly extracts that same notice with the weights and configuration. The remaster step builds, verifies, and includes the model archives; preseed preserves both archives for provisioning.

`install_paradee()` and `install_spacy()` raise errors when an installation needs an archive that the media did not supply. Neither falls back to a model download. An already verified installation may return without reinstalling. Runtime wheel installation uses `--no-index`, `--no-deps`, and `--require-hashes`. Gate 4 passes.

## Gate 5: espeak-ng source and loader

Seat B downloaded the pinned espeakng_loader 0.2.4 wheel. Its 10,078,484-byte length and SHA-256 `08721baf27d13d461f6be6eed9a65277e70d68234ff484fd8b9897b222cdcb6d` match the lock. It contains `libespeak-ng.so` and the data directory, and contains no licence document. The library's source headers state GPL version 3 or later; the loader's MIT licence does not replace those terms.

The repository supplies the loader's 1,069-byte MIT text with SHA-256 `b05c73bb1335b4320ec97edff106b3991c12d0acdc6e899c96f061a15039119f`. It matches the upstream text at its recorded source commit. The supplied `espeakng-loader-0.2.4-build.sh` also matches upstream at loader commit `146599e29be31bf17d99f0bcb7dbb2f92aef3d95`.

Seat B downloaded the [upstream espeak-ng 1.52.0 source tarball](https://github.com/espeak-ng/espeak-ng/archive/refs/tags/1.52.0.tar.gz). Its computed size is 17,739,803 bytes and its computed SHA-256 is `bb4338102ff3b49a81423da8a1a158b420124b055b60fa76cfb4b18677130a23`, exactly matching `provision/espeak-ng-source.json`. The archive includes the GPL version 3 COPYING text. The source tarball is not committed; remaster downloads and verifies it, and preseed installs it with the loader licence and build materials.

The runtime imports Misaki's espeak fallback. Inspection of the pinned Misaki wheel confirms that it explicitly sets the phonemizer library and data paths through `espeakng_loader`. The loader returns its bundled shared-library path. This Paradee path uses the wheel's library, even though Debian's espeak-ng package is also listed for other system uses. Gate 5 passes.

## Tests and known issues

`PYTHONPATH` and `PYTHONHOME` were unset before every test invocation. Temporary data, logs, caches, and native builds stayed in the designated work directory. Only the needed Kilix submodules were initialized: content at `f9ba621eb7ca41a8e3913f60118596929ca7f1cc`, state at `1fe26a35b9ed661bfaeb8aa9f4d1e38faeb2faf9`, and frame presenter at `7e20193544e90ab0c0084ecbf61dea3e8bd4fe7c`. The pinned state library was built outside the source tree. Additional public object stores supplied the exact voice, needle, and bonsai commits required by the compliance tests.

The two Kilix Paradee runtime test modules pass all 13 tests. The Kilix model wizard module passes all 47 tests. The Kilix 95 system-voice script passes. `tests.test_image_models` passes all 48 tests. `tests.test_model_compliance_carrier` passes 16 of 17 tests, including record binding, byte-identical regeneration, delivery, and refusal of planted defects.

The sole compliance failure is AC-7, `test_acceptance_receipt_names_two_independent_seats`: the attached seat evidence does not contain the current carrier hash. This is the expected open gate described in the brief. Those attachments reviewed the older RC7 carrier, so this report does not claim completed carrier acceptance or change its receipt.

Kilix 95's committed CI workflow still pins Kilix `763e6e88a16cc3c6f56ba7b3a343715389b8ecae`, rather than the candidate `b1596021881e5239f2cba631361f66530905658d`. That pairing remains a known issue; this session's desktop test used the candidate directly and passed.

This review establishes the five source and artifact gates above. This session did not build or boot a complete ISO and does not claim BIOS, EFI, upgrade, rollback, or user-data preservation acceptance.

VERDICT: ship with known issues
