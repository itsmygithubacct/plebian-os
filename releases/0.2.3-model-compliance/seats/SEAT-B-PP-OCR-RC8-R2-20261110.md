# Seat B review: Plebian-OS 0.2.3 RC8 page OCR follow-ups

## Eligibility

The builder session launched this pane on 2026-11-10. This session did not author the candidate. It did not author the commits under review, the page OCR engine, the catalogue, the licence records, the image installer, the updater, or the compliance carrier. This session cloned the public repositories into its work directory, checked out the named commits, read them, probed them with fixtures, and ran the named tests. It left those checkouts clean. It did not commit, push, publish, move a tag, or write ACCEPTANCE.json.

## Identity

All six public repositories were reviewed on branch `work/0.2.3-rc8-followups`. At the end of this review, each remote tip was still the named commit, and each review checkout was clean at that commit.

| Repository | Commit | Parent |
| --- | --- | --- |
| kilix-pdf-conversion | `2cff8ffde2a64367ca2e3e567acfcb740866fb9f` | `e841241b0134fef42045a946199a92e9fa35ffbf` |
| kilix-license | `596ada2ab68b9ec441674ff4da2d431559d47378` | `f33fdf2a0e8396bd32f3617633629bc3f7973e79` |
| kilix-content | `32722d0be0e00974635ba3ab2ee9543fa35db92f` | `c7aaac12049277b38e4876f24d11d4588a6e9698` |
| kilix | `b77e49b37068a8fad7be110cad830c17407edbaa` | `f93c100cf2b3c17c6b0b9d0b5b8d310a63f47e05` |
| kilix-95 | `fdf62f1e798820f70a5646df379e2df0b9ab8e71` | `e54c1862e075145008cf4c22231296a47196bfc9` |
| plebian-os | `61d100712f1451484eb28559be304ab52602095c` | see the chain below |

The five plebian-os commits under review, each with one parent, are `a19dd19cd5e7795febb750ee596bb3c5f6e5b4ef`, `89ac8787b71d68139d0ad365080f5db3cf17b113`, `0e3bf967b9bcb05e8aab9f6ba2810df8eb8ef49e`, `9196f739ae4dfe65d3f8a0f5e6f2429b36615ce3`, and `61d100712f1451484eb28559be304ab52602095c`, in that order, on top of `f581b010539ef80e6d238a7545d81a7c5893cded`.

On these ten commits the author and the committer are the same person, there is one identity, and no message carries a co-author trailer.

`releases/0.2.3.env` at the plebian-os commit names Kilix `b77e49b37068a8fad7be110cad830c17407edbaa`, Kilix 95 `fdf62f1e798820f70a5646df379e2df0b9ab8e71`, and kilix-license `596ada2ab68b9ec441674ff4da2d431559d47378`. `PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF` is `32722d0be0e00974635ba3ab2ee9543fa35db92f`. `PLEBIAN_OS_VOICE_CARRIER_SHA256` is `09ef84aef8826e45fb133fb8b3ef1de8f72fa4fb772f89dc8bc9ea79caf4e28e`. `PLEBIAN_OS_VERSION` is `0.2.3`, and the repository `VERSION` file is `0.2.3`. `PLEBIAN_OS_REF` is `v0.2.3-rc8`. The env says that tag is a local annotated tag and is not pushed. A fresh clone does not resolve it: `git rev-parse` fails, and the remote tag lookup returns nothing. This session did not move the tag. The missing tag is recorded here and is not, by itself, a defect.

kilix-pdf-conversion `origin/main` is `29debafba9062eedd5b0c22c67c4ba05e395ed00`. Its merge base with `2cff8ffde2a64367ca2e3e567acfcb740866fb9f` is `07ee29296e1c0c3fc2a8e4899a53c1098e96b05d`. Neither commit is an ancestor of the other, so this branch is not merged to main. That is a known issue.

## Gate 1: licence records

kilix-license `596ada2ab68b9ec441674ff4da2d431559d47378` records `pp-ocrv6-small-det` and `pp-ocrv6-small-rec` as Apache-2.0. The licensor field is PaddlePaddle. The Apache-2.0 text stored with the records is 11358 bytes, sha256 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`. Statement `d10106e0139030f2ea1f330c9a165c418114909d32838719f2aa35cf5d9c95d6` says the grant is each model card's `license: apache-2.0` line, that neither repository contains a LICENSE or NOTICE file, that each card's licence badge links to a LICENSE file that does not exist, that no copyright holder is named, that the text shown with the models is Debian's copy of the Apache License 2.0, and that the training data and its terms are not stated.

The generator refuses a determination whose `repository_licence_file` is not null. The determination JSON used to build these records has that field null, and it quotes the owner's words. The two records are their own family. From parent `f33fdf2a0e8396bd32f3617633629bc3f7973e79` to this commit, the data tree adds five files and removes none, so no existing record digest moved.

This session read the owner's determination file and did not change it. The file is 4431 bytes, sha256 `733df4a6c6ce287cc2a066ddd1faf8aba35010497fba31cf78de31d30cea8f85`, which is the pin the records carry. The owner answered, verbatim: "go with Apache-2.0, note the reality. 2: go with 5. ship them with the image if they are small. work this into RC8." The determination's licensor field is PaddlePaddle, and the same file says that naming the publisher is the builder's reading, not the owner's words. The records state that recorded determination. They do not claim a repository LICENSE file, a NOTICE file, or a copyright holder.

This session checked the upstream cards. The detector README at Hugging Face revision `28fe5895c24fd108c19eb3e8479f4ab385fbfc62` is 16076 bytes, sha256 `e9403667f0f92055d8ce9e73a2beb1002fc489d9342697db74039eb7178bb5fb`, and line 2 is `license: apache-2.0`. The recogniser README at revision `b8f84f0b80c529de40b4fbb3544b84fa7233a513` is 16585 bytes, sha256 `7d46dbd183ac09bd5a2e6b4577dcb29240751b1c00eb6813eca308d529f86806`, with the same line. Each pinned tree contains `.gitattributes`, `README.md`, `inference.json`, `inference.onnx`, and `inference.yml`. Requests for LICENSE, NOTICE, LICENSE.md, and COPYING returned HTTP 404. The detector `inference.onnx` is 9880512 bytes, sha256 `d73e0058b7a8086bbd57f3d10b8bcd4ff95363f67e06e2762b5e814fe9c9410e`. The recogniser `inference.onnx` is 21159378 bytes, sha256 `5435fd747c9e0efe15a96d0b378d5bd157e9492ed8fd80edf08f30d02fa24634`. The recogniser `inference.yml` is 150579 bytes, sha256 `ab078671bb49f06228eadccd34f1bb501e157f7a047095ffb943ba81512c77d1`. This session does not judge whether Apache-2.0 was the right choice. Gate 1 holds.

## Gate 2: catalogue

kilix-content `32722d0be0e00974635ba3ab2ee9543fa35db92f` catalogues both assets for provider kilix-pdf-conversion. The catalogue members match `src/kilix_pdf_conversion/data/pp-ocrv6-small.json`: the detector ONNX file, the recogniser ONNX file, the recogniser YAML file, and `notices/LICENSE-apache-2.0.txt` at 11358 bytes, sha256 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`. The provenance revisions are the Hugging Face revisions above. `plebian.json` has 47 assets. `tests/test_pdf_pin.py` requires provider ref `2cff8ffde2a64367ca2e3e567acfcb740866fb9f` and five PDF models, including these two. `tests/test_c2f_pdf_records.py` names the two page OCR models, names the owner's determination, and quotes the owner's words.

The vendored licence tree is the declared subset of kilix-license `596ada2ab68b9ec441674ff4da2d431559d47378`. `third_party/kilix-license.objects.json` pins that commit and excludes `.gitignore`, `.python-version`, `Makefile`, `PUBLICATION.md`, `tests`, `tools`, and `uv.lock`. Of 279 licence-repository files, 223 are kept and 56 are dropped by those exclusions. This session found 0 missing files, 0 byte differences, and 0 extra files.

Kilix `b77e49b37068a8fad7be110cad830c17407edbaa` records gitlink `160000 commit 32722d0be0e00974635ba3ab2ee9543fa35db92f` for `third_party/kilix-content`. `tests/test_content_models.py` sets `PACKAGED_ASSETS = 47`. Kilix 95 `fdf62f1e798820f70a5646df379e2df0b9ab8e71` sets `KILIX_COMMIT` to `b77e49b37068a8fad7be110cad830c17407edbaa` in `.github/workflows/test.yml`. Gate 2 holds.

## Gate 3: page OCR

kilix-pdf-conversion `2cff8ffde2a64367ca2e3e567acfcb740866fb9f` chooses Tesseract or RapidOCR for each page and writes the decision to `ocr-pages.json`, including `router_policy_version`. Tesseract is the operating-system program: `shutil.which("tesseract")` or `KILIX_OCR_TESSERACT`, run as a subprocess with `--psm 3`. The RapidOCR 3.10.0 path calls `verify_models` before use. Verification requires a regular file, refuses a symlink, confines the path, and checks size and sha256. The ONNX sessions are `InferenceSession` objects built from those verified bytes with `CPUExecutionProvider`. Before RapidOCR is constructed, `download_file.DownloadFile.run` is replaced by `_refuse_download`.

This session probed that path with the real detector bytes. A missing file raises `EngineUnavailable` with "OCR model file unavailable". A symlink raises "OCR model path is unsafe". A short file raises "OCR model size mismatch". One changed byte raises "OCR model hash mismatch". Calling the download helper raises `OcrFailed` with "RapidOCR attempted a download; models must come from verified assets".

`THIRD-PARTY-NOTICES.md` names RapidOCR as Apache-2.0, ONNX Runtime as MIT, and the closure the runtime lock adds. It does not name Colorama. `runtime/uv.lock` names colorama 0.4.6 only with the marker `sys_platform == 'win32'`. That omission is a known issue. This session did not reproduce the character error rates in the commit message. Gate 3 holds.

## Gate 4: image archives

`provision/pp-ocrv6-small-det-model.json` pins an archive of 9902080 bytes, sha256 `dbd78e6646688f55b167ffc6f27548ae52952f82bb746c2eea77293a715bf21c`. `provision/pp-ocrv6-small-rec-model.json` pins an archive of 21329920 bytes, sha256 `b358b3821a26000da53ebb8bdbd59dafdefe09c7797d7a820d848ad38368cda6`. This session downloaded each pinned upstream file over https and checked its size and sha256. The detector ONNX, recogniser ONNX, and recogniser YAML matched the hashes in gate 1. `provision/bundles/pp-ocrv6-small-LICENSE-apache-2.0.txt` is the same 11358-byte text, sha256 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`.

This session rebuilt both archives with `provision/install-image-models.py --build-pp-ocr-archive`. Both rebuilt archives match their pins. The manifest digests are `953752951e3805d83e0da54d24566d75d1e9a52d95101c6d900d45940fbd511e` for the detector and `19566d34492f0fc80fa188a24195abd485777d3a211a99ae0fa9b17ef85d7a4e` for the recogniser. Gate 4 holds.

## Gate 5: image delivery

`build/remaster-iso.sh` function `build_pp_ocr_bundle` downloads each pin URL at the pinned size over https, builds the archive, verifies both archives, and installs them onto the image. `preseed/preseed.cfg` includes `tesseract-ocr` and `tesseract-ocr-eng` in `pkgsel/include` and copies both archives to `/target/usr/local/share/plebian-os/`. `provision/install-deps.sh` lists the same two packages on the page OCR install route.

`install_pp_ocr` uses the image archive when it is present. With no archive and no network, it prints that the first online upgrade downloads the model, and it does not download. With no archive and a network, it fetches the files at the pin's manifest digest with `pinned_by` set to "its image pin". A Playalong decline skips Basic Pitch, Demucs, and Whisper medium.en. It does not skip page OCR, Paradee, `en_core_web_sm`, or the command model.

The voice carrier's `model_order` contains no page OCR model, no Basic Pitch, and no Demucs. Paradee and `en_core_web_sm` are recorded as `image-offline-model`. The page OCR licence records live in kilix-content, in the same way those other image models sit outside the voice carrier while their catalogue and licence records are bound through it. The carrier binds content `32722d0be0e00974635ba3ab2ee9543fa35db92f` and licence `596ada2ab68b9ec441674ff4da2d431559d47378`. Gate 5 holds. This session did not build an image.

## Gate 6: Paradee upgrade path

`61d100712f1451484eb28559be304ab52602095c` is the upgrade change. `provision/plebian-os-update.sh` runs `install-image-models.py --install-paradee-runtime` as root after the default models and before the desktop user's image-model step. The root step uses sudo when the caller is not uid 0. The desktop user's step is not given `--offline`. A caught download failure returns 0, so the update continues. `provision/plebian-os-provision.sh` passes `--offline` to both the root step and the user step, so a fresh install does not download these models.

`fetch_paradee_media` downloads only over https and only at the exact pinned size. It builds the archives with the image builders. It copies bundled docopt from `provision/bundles` and does not fetch docopt. It checks the wheel lock, then places each archive only after a second check against the image pin. A mismatch raises before placement. If the destination already exists, the existing file is checked again. `install_paradee_runtime` catches an online download error, prints that the next upgrade tries again, returns false, and `main` returns 0. An offline run with no Paradee archive raises `ValueError` with "the installation media did not supply the Paradee model" and downloads nothing. `install_paradee` and `install_spacy` contain no download. On an online run with no archive they print that the next upgrade tries again, and they do not fail the update.

The published byte total of 163341710 is the sum of the 76 remote wheels in `provision/paradee-wheels.json`, the Paradee ONNX file, `config.json`, and the `en_core_web_sm` wheel. That wheel is also one of the 76, so the total counts it twice. docopt is the one bundled wheel and is outside the download. This session downloaded every pinned URL: three page OCR files, the Paradee ONNX and config, the spaCy wheel, and the 76 remote wheels, 82 files. Each matched its pinned size and sha256. The download log records `counted-bytes 163341710` and `DOWNLOADS_OK`.

This session then ran `fetch_paradee_media` against local copies of those already checked files. The probe still required https and the pinned size, and it used the real image builders. It placed `paradee-8m-v1.2.tar` at 8478720 bytes, sha256 `61e95049263a04897b1cc69923aaed0eb33d47d610763d9055de14b4f52b908a`, and `en-core-web-sm-3.8.0.tar` at 12820480 bytes, sha256 `eedbef109150c8b8f0534fae3ac6ee1a79d9616f09f638247c35a7a309f180fb`. The wheelhouse had 77 wheels, including bundled docopt, and every wheel matched the lock. The success path made 79 writes that sum to 163341710, because the spaCy wheel is fetched for the archive and again as a lock wheel. That success path did not create an interpreter. The code checks the wheelhouse before it would run the virtual-environment step. A one-byte change to the ONNX file placed nothing. A changed wheel byte raised before an interpreter was created.

This session ran the real `install-image-models.py` main entry point as the desktop user's step, against a fixture machine with no image archives. On an online run it reached both page OCR fetches, each at the manifest digest with `pinned_by` "its image pin". It did not download Paradee or `en_core_web_sm`. It printed the next-upgrade sentences and exited 0. A Playalong decline fetched only the two page OCR assets. An offline page OCR run printed the first-online-upgrade sentence and downloaded nothing. An offline root run raised and downloaded nothing. An online root run whose upstream bytes were forced to mismatch exited 0, placed nothing, and printed that the next upgrade tries again.

The fixture has these boundaries. Basic Pitch was reported already verified, so the content installer was not invoked. The vendored Basic Pitch archive beside the script is still resolved, and `verify_archive` runs. Demucs and Whisper medium.en were recorded through a replaced `fetch_default` and were not downloaded. `_download_pinned` was stubbed to raise if called. Within those boundaries, an upgrade without the image archives reaches page OCR, the desktop user's step does not download Paradee or `en_core_web_sm`, and unchecked bytes are not placed. Gate 6 holds on the code and on this fixture. This session did not upgrade a machine from 0.2.2 or RC7.

The image install copies `espeak-ng-1.52.0.tar.gz` and the espeakng-loader LICENSE, build text, and build script to `/usr/local/share/doc/plebian-os/espeak-ng/`. The upgrade path takes the espeakng-loader wheel named in `provision/paradee-wheels.json` from PyPI. The installer has no espeak source path. An upgraded machine therefore does not receive the espeak-ng source or loader texts that the image installs. That is a known issue.

## Gate 7: carrier

This session computed sha256 `09ef84aef8826e45fb133fb8b3ef1de8f72fa4fb772f89dc8bc9ea79caf4e28e` for `releases/0.2.3-model-compliance/CARRIER.json` (12295 bytes). The committed `DEFAULT-MODELS.json` in that carrier has sha256 field `e00614bf726154d09668820c061cbbcb402239a445bde666b0568d36f01528a6`. Both match the builder's claim. The carrier binds kilix-content `32722d0be0e00974635ba3ab2ee9543fa35db92f` and kilix-license `596ada2ab68b9ec441674ff4da2d431559d47378`.

`SHA256SUMS` lists 83 files. Rechecking it found no mismatch, no missing file, and no extra file. `build/generate-model-compliance.py --check`, pointed at the kilix-content and kilix-license clones and at the committed determinations and seats, exited 0 and reported no difference. The Paradee and `en_core_web_sm` DELIVERY texts describe the gate 6 upgrade download and the existing image-offline wording.

The attached carrier seats quote carrier `9701a082220b3d5d6f5306a16875d66c0ab70f24f75769250bbc93b927312605`. They do quote the current `DEFAULT-MODELS.json` sha256. They do not quote carrier `09ef84aef8826e45fb133fb8b3ef1de8f72fa4fb772f89dc8bc9ea79caf4e28e`. Gate 7 holds for regeneration and bindings. The seat-text mismatch is the AC-7 known issue below. This session did not treat those committed seats as the other live reviewer.

## Tests

`PYTHONPATH` and `PYTHONHOME` were unset before every test. The uv cache, the Python install, bytecode, and the pytest cache stayed under this session's work directory. Two harness exceptions were required and then removed: the Kilix receipt-store test needs its temporary directory outside the account home, and one kilix-content socket test needs a short temporary directory.

kilix-pdf-conversion `make test` passed 236 tests and skipped 6, with no failure. This session did not record the six skip reasons. The command was the repository's `make test`. A separate frozen runtime was not built.

kilix-license `make test` ran 246 tests, with 1 failure and 2 skips. The failure is `test_wheel_records.WheelRecordTests.test_all_record_families_and_notice_bytes_survive_wheel_install`, `ModuleNotFoundError: No module named 'setuptools'`. The same missing module fails at the same line on parent `f33fdf2a0e8396bd32f3617633629bc3f7973e79`. The two skips need a tmpfs sentinel over the live store. This is a known issue.

Kilix `tests/test_content_models.py` first failed three subtests of `test_from_real_install_reads_the_directory_and_fetches_nothing` because the receipt store follows the account home and the temporary directory was inside that home. The same module passed when the temporary directory was outside the account home: the wrapper ran the one test plus the module, 41 tests, OK. That first failure is a harness limit, not a product defect.

kilix-content `make check` first stopped in `test_getent_and_af_unix_are_invisible_too` because the AF_UNIX path was longer than the system allows when the temporary directory sat inside the work directory. The pins target did not run on that attempt. A rerun with a short temporary directory ran 413 tests in 104.929 seconds, OK, with 3 skips, and `tools/generate_upstream_records.py --check` produced no difference and exited 0. The three skips are the Basic Pitch external file, the Demucs upstream weights file, and an LFM3 typed-agreement skip. The long-path error is a harness limit, not a product defect.

From the plebian-os tests directory, `test_image_models`, `test_model_compliance_carrier`, `test_dependency_manifest`, `test_runnable_models`, `test_voice_release_contract`, and `test_ollama_carrier_wrappers` together ran 167 tests with 1 failure. The failure is AC-7, `test_acceptance_receipt_names_two_independent_seats`. The carrier tests used fresh clones of the candidate's selected needle, voice, and bonsai commits: needle `30ee74fe770a6c3b19b23e68e3a4c7dbe4deae77`, voice `1a4e63b11d0ad9c1664031e2773f5c4f5797913f`, and bonsai `630da3cf64d28b35fb65cafd4e7c8a4ad54b8685`. Those checkouts were not committed. No other failure appeared in the named modules.

## Known issues

These defects do not break the gates above.

- AC-7 fails because the attached seat texts quote carrier `9701a082220b3d5d6f5306a16875d66c0ab70f24f75769250bbc93b927312605` and do not quote `09ef84aef8826e45fb133fb8b3ef1de8f72fa4fb772f89dc8bc9ea79caf4e28e`.
- The kilix-license wheel test fails without setuptools, the same way on `f33fdf2a0e8396bd32f3617633629bc3f7973e79`. Two licence tests skip unless a tmpfs sentinel covers the live store.
- kilix-pdf-conversion main `29debafba9062eedd5b0c22c67c4ba05e395ed00` has diverged from `2cff8ffde2a64367ca2e3e567acfcb740866fb9f` at `07ee29296e1c0c3fc2a8e4899a53c1098e96b05d` and is not merged.
- `THIRD-PARTY-NOTICES.md` omits Colorama 0.4.6 (BSD-3-Clause). The runtime lock names that package only for Windows.
- No image was built with the page OCR archives. Page OCR was not run on an installed system. An upgrade from 0.2.2 or RC7 was not run on a machine.
- An upgraded machine gets the espeakng-loader wheel from PyPI and does not get the espeak-ng source or loader texts that the image installs under `/usr/local/share/doc/plebian-os/espeak-ng`.

`v0.2.3-rc8` remains an unpushed local tag. A fresh clone will not resolve it. That is not, by itself, a defect.

## Verdict

The required identities, parents, records, hashes, and gitlinks match. The licence records state the owner's recorded decision and the card-only grant, and they do not claim a repository LICENSE, a NOTICE, or a copyright holder. The rebuilt page OCR archives match their pins. The app refuses an unverified model file and refuses a model download. A fresh install is offline for the models the image ships. On the fixture, an upgrade without the image archives reaches both page OCR installs, places an archive only after the pin check, and does not create an interpreter from unchecked bytes. The desktop user's step does not download Paradee or `en_core_web_sm`. Tesseract is on both install routes. The carrier regenerates identically. The known issues above remain.

VERDICT: ship with known issues
