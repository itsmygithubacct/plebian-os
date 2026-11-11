# Seat A review of the PP-OCR RC8 candidate

Date: 2026-11-10. This session checked the seven gates in the seat A brief. The gates hold. The failures this session observed are the known issues the brief names.

The SHA-256 this session computed for the committed `releases/0.2.3-model-compliance/CARRIER.json` is `09ef84aef8826e45fb133fb8b3ef1de8f72fa4fb772f89dc8bc9ea79caf4e28e`.

The `sha256` field this session read from that carrier's committed `DEFAULT-MODELS.json` is `e00614bf726154d09668820c061cbbcb402239a445bde666b0568d36f01528a6`.

## Eligibility

The builder session launched this pane on 2026-11-10 and wrote the brief. This session did not author the candidate. This session did not author the commits under review, the page OCR engine, the catalogue, the licence records, the image installer, the updater, or the compliance carrier.

This session cloned the public repositories into the work directory and checked out the named commits. It did not use an existing local worktree, read the other seat's directory, the builder session's worktrees, or an earlier review folder, or start other agents. It made no commits, pushed or published nothing, and wrote no release acceptance record. The source checkouts were clean at the end. Probes of root-only paths used directories inside the work directory. `PYTHONPATH` and `PYTHONHOME` were unset before every test.

## Candidate identities

This session checked the public `work/0.2.3-rc8-followups` tips at the start of the review and again after the tests. Each tip is the named commit. On every reviewed commit the author and the committer are the same repository account, and no message has a co-author trailer.

kilix-pdf-conversion is `2cff8ffde2a64367ca2e3e567acfcb740866fb9f`. Its parent is `e841241b0134fef42045a946199a92e9fa35ffbf`.

kilix-license is `596ada2ab68b9ec441674ff4da2d431559d47378`. Its parent is `f33fdf2a0e8396bd32f3617633629bc3f7973e79`.

kilix-content is `32722d0be0e00974635ba3ab2ee9543fa35db92f`. Its parent is `c7aaac12049277b38e4876f24d11d4588a6e9698`.

Kilix is `b77e49b37068a8fad7be110cad830c17407edbaa`. Its parent is `f93c100cf2b3c17c6b0b9d0b5b8d310a63f47e05`.

Kilix 95 is `fdf62f1e798820f70a5646df379e2df0b9ab8e71`. Its parent is `e54c1862e075145008cf4c22231296a47196bfc9`.

plebian-os is `61d100712f1451484eb28559be304ab52602095c`. The five commits on `f581b010539ef80e6d238a7545d81a7c5893cded`, in order, are `a19dd19cd5e7795febb750ee596bb3c5f6e5b4ef`, `89ac8787b71d68139d0ad365080f5db3cf17b113`, `0e3bf967b9bcb05e8aab9f6ba2810df8eb8ef49e`, `9196f739ae4dfe65d3f8a0f5e6f2429b36615ce3`, and `61d100712f1451484eb28559be304ab52602095c`. Each parent is the commit before it.

`VERSION` is `0.2.3`. `releases/0.2.3.env` names Kilix `b77e49b37068a8fad7be110cad830c17407edbaa`, Kilix 95 `fdf62f1e798820f70a5646df379e2df0b9ab8e71`, and kilix-license `596ada2ab68b9ec441674ff4da2d431559d47378`. `PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF` is `32722d0be0e00974635ba3ab2ee9543fa35db92f`. `PLEBIAN_OS_REF` is `v0.2.3-rc8`. The file says that tag is local and is not pushed. A fresh clone does not resolve it. This session did not move the tag. That local tag is not a defect by itself.

## Gate 1: licence records

kilix-license records `pp-ocrv6-small-det` and `pp-ocrv6-small-rec` as Apache-2.0. The licensor field is PaddlePaddle. The licence text id is `debian/common-licenses/Apache-2.0`, and the text hash is `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`. The statement id is `pp-ocrv6-card-only-grant`. The determination says the grant is each model card's `license: apache-2.0` line, that neither repository has a LICENSE or NOTICE file, and that no copyright holder is named. `repository_licence_file` is null. The generator raises if that field is not null.

The records quote the owner's verbatim answer: "go with Apache-2.0, note the reality. 2: go with 5. ship them with the image if they are small. work this into RC8." The owner's determination file contains that same answer, decides Apache-2.0 for both models, and says the PaddlePaddle licensor name is the builder's reading of the publishing organization. The file is 4431 bytes with SHA-256 `733df4a6c6ce287cc2a066ddd1faf8aba35010497fba31cf78de31d30cea8f85`, which is the hash the record pins. The Apache-2.0 text shipped in `provision/bundles/pp-ocrv6-small-LICENSE-apache-2.0.txt` is 11358 bytes and matches Debian's common-licenses Apache-2.0 byte for byte.

This session read both Hugging Face repositories at the pinned revisions. Each README front matter says `license: apache-2.0`. Each tree contains `.gitattributes`, `README.md`, `inference.json`, `inference.onnx`, and `inference.yml`. Neither tree contains a LICENSE file or a NOTICE file. The downloaded `inference.onnx` files and the recogniser `inference.yml` match the pinned sizes and SHA-256 values.

The two records are their own family. Compared with parent `f33fdf2a0e8396bd32f3617633629bc3f7973e79`, the pre-existing record digests are unchanged.

## Gate 2: catalogue

kilix-content catalogues both assets for the kilix-pdf-conversion provider at those Hugging Face revisions, with the same member paths, sizes, and SHA-256 values as `src/kilix_pdf_conversion/data/pp-ocrv6-small.json`, including the Apache-2.0 notice. The catalogue selects kilix-pdf-conversion `2cff8ffde2a64367ca2e3e567acfcb740866fb9f`. The PDF record tests name five PDF models, including these two. The vendored kilix-license tree is the declared subset, and the content check's vendored-byte test passed against `596ada2ab68b9ec441674ff4da2d431559d47378`.

Kilix's `third_party/kilix-content` gitlink is `32722d0be0e00974635ba3ab2ee9543fa35db92f`. The packaged catalogue has 47 assets, and Kilix's content-model tests require that count. Kilix 95's workflow pins `KILIX_COMMIT` to `b77e49b37068a8fad7be110cad830c17407edbaa`.

## Gate 3: page OCR

The engine chooses Tesseract or RapidOCR for each page and writes the decision to `ocr-pages.json`. Tesseract is run as the operating system's program. Each model file is checked for a regular file, confinement inside the asset directory, size, and SHA-256 before use. The ONNX sessions are built from those verified bytes. RapidOCR's download helper is replaced by a function that raises `OcrFailed`.

This session copied the installed asset directories and called the real verifier. The unchanged files verified: the detector model is 9880512 bytes, the recogniser model is 21159378 bytes, and the character table has 18708 entries. A changed byte was refused as a hash mismatch. A short file was refused as a size mismatch. A symlink was refused as an unsafe path. A missing file was refused as unavailable. A direct call of the download helper raised `OcrFailed`.

`THIRD-PARTY-NOTICES.md` names RapidOCR as Apache-2.0 and ONNX Runtime as MIT. The runtime lock pins `rapidocr==3.10.0` and `onnxruntime==1.31.1`. The omission of Colorama is a known issue below. `make test` passed. This session did not reproduce the character error rates. Those page images are not public.

## Gate 4: image archives

This session downloaded each pinned upstream file and rebuilt both archives with the image builder. The detector archive is 9902080 bytes, SHA-256 `dbd78e6646688f55b167ffc6f27548ae52952f82bb746c2eea77293a715bf21c`. The recogniser archive is 21329920 bytes, SHA-256 `b358b3821a26000da53ebb8bdbd59dafdefe09c7797d7a820d848ad38368cda6`. Both match `provision/pp-ocrv6-small-det-model.json` and `provision/pp-ocrv6-small-rec-model.json`. The licence text in each archive is the same 11358-byte Debian Apache-2.0 text.

## Gate 5: image delivery

`build/remaster-iso.sh` builds both page OCR archives from the pins, verifies them, and puts them on the image. `preseed/preseed.cfg` copies both archives onto the installed system. `tesseract-ocr` and `tesseract-ocr-eng` are in preseed's package list and in `provision/install-deps.sh`.

With an archive, the installer uses that archive. With no archive and `--offline`, it installs nothing and says the first online upgrade downloads the model. With no archive on an online run, it fetches that asset at the manifest digest in the image pin. A Playalong decline skips Basic Pitch, Demucs, and Whisper medium, and still runs both page OCR installs. The image-model tests passed these cases.

The voice carrier's model order is small-en-us, lgraph-en-us, vibevoice-asr-bitnet, whisper-small-en, whisper-medium-en, whistle, kilix-diarization-cpu, lfm2-kilix-commands, paradee-8m-v1.2, and en-core-web-sm-3.8.0. Basic Pitch, Demucs, and both page OCR assets are outside that carrier. Their licence records live in kilix-content and kilix-license, which is how the carrier treats the other image models that are not voice models.

## Gate 6: Paradee upgrade path

`provision/plebian-os-update.sh` runs `install-image-models.py --install-paradee-runtime` as root after the default models and before the desktop user's image-model step. `provision/plebian-os-provision.sh` passes `--offline` to that root step and to the user step, so a fresh install does not download models the image ships.

This session called the real `fetch_paradee_media` with the shared directory inside the work directory. It downloaded 163341710 bytes over https, the pinned sizes only. The Paradee archive it placed is 8478720 bytes, SHA-256 `61e95049263a04897b1cc69923aaed0eb33d47d610763d9055de14b4f52b908a`. The en_core_web_sm archive is 12820480 bytes, SHA-256 `eedbef109150c8b8f0534fae3ac6ee1a79d9616f09f638247c35a7a309f180fb`. All 76 remote wheels match the lock, and the bundled docopt wheel matches `provision/bundles`. The wheelhouse check runs before the interpreter is created. This session did not create the interpreter. The image-model test that does create one calls the hash check first and then `python3 -I -m venv --copies`.

An offline root run with no Paradee archive raised `ValueError` saying the installation media did not supply the Paradee model. It downloaded nothing and created nothing. A download of the right size and the wrong bytes made `main` return 0, print that the next upgrade tries again, and place no archive.

The desktop user's `main` was then run online, with no Paradee, en_core_web_sm, or page OCR archive in the shared directory, and with Playalong not declined. It installed Basic Pitch from the vendored archive, downloaded Demucs, and reached both page OCR installs. Both page OCR models were installed from their pinned revisions. The installed detector and recogniser bytes, the recogniser `inference.yml`, and both Apache-2.0 notices match the pins. The pinned downloader was not called for Paradee or en_core_web_sm. Paradee stopped because the runtime file was missing and said the next upgrade tries again. en_core_web_sm said this machine has no archive and the download before this step did not supply one.

A second call, with the verified Paradee runtime files present and still no archive, printed that same next-upgrade sentence for Paradee and for en_core_web_sm and downloaded nothing. The fixture marked the command model already verified, because the updater stages that archive before this step, so the large command-model archive was not downloaded. Whisper medium's function was reached after both page OCR installs and was not executed, so that large model was not downloaded. The image-model tests cover that function and the install order, and they passed.

## Gate 7: carrier

The carrier binds kilix-content `32722d0be0e00974635ba3ab2ee9543fa35db92f` and kilix-license `596ada2ab68b9ec441674ff4da2d431559d47378`. `sha256sum -c SHA256SUMS` in the carrier directory reported 83 OK and 0 FAILED. `build/generate-model-compliance.py --check`, against the fresh kilix-content and kilix-license clones and the committed determinations and seats, exited 0 and reported no difference.

The Paradee DELIVERY says an online upgrade without the archive downloads the pinned files from huggingface.co, builds the same archive, checks it against the image pin, and installs nothing if the download fails. The en_core_web_sm DELIVERY says the same, with the download from github.com. Both say a fresh install without the archive is an error and that provisioning uses the supplied bytes offline.

## Tests

kilix-pdf-conversion `make test` reported 236 passed and 6 skipped.

kilix-license `make test` reported 246 tests, with one failure: `test_all_record_families_and_notice_bytes_survive_wheel_install`. The build step raised `ModuleNotFoundError: No module named 'setuptools'`. The same `make test` on parent `f33fdf2a0e8396bd32f3617633629bc3f7973e79` reported 242 tests and the same single failure.

kilix-content `make check` reported 413 tests passed, 3 skipped, and the pin check exited 0. One earlier run of that suite errored because the partial clone lacked one historical catalogue blob and because a temporary socket path was too long. This session fetched that blob, shortened the temporary path, and the repeated run passed.

Kilix `tests.test_content_models` reported 40 tests passed. An earlier run failed three receipt-location checks because the temporary directory was inside the account home, which that test refuses. The repeated run, with the temporary directory outside that home, passed.

From the plebian-os tests directory, `test_image_models`, `test_model_compliance_carrier`, `test_dependency_manifest`, `test_runnable_models`, `test_voice_release_contract`, and `test_ollama_carrier_wrappers` reported 167 tests and one failure, `test_acceptance_receipt_names_two_independent_seats`. The carrier tests used fresh clones of kilix-needle, kilix-voice, and kilix-bonsai at the refs the candidate selects. The Kilix content submodule was initialized at its recorded gitlink and was not committed.

## Known issues

AC-7, `test_acceptance_receipt_names_two_independent_seats`, fails because the attached seat texts quote carrier `9701a082220b3d5d6f5306a16875d66c0ab70f24f75769250bbc93b927312605`. The current carrier hash is `09ef84aef8826e45fb133fb8b3ef1de8f72fa4fb772f89dc8bc9ea79caf4e28e`. The other tests in those modules passed.

kilix-license's wheel test fails because the uv environment has no setuptools. The same failure occurs on `f33fdf2a0e8396bd32f3617633629bc3f7973e79`.

kilix-pdf-conversion's `main` has diverged from this branch and is not merged. `origin/main` is `29debafba9062eedd5b0c22c67c4ba05e395ed00`. The merge base is `07ee29296e1c0c3fc2a8e4899a53c1098e96b05d`. Twelve commits are on this branch and not on main. Four commits are on main and not on this branch.

`THIRD-PARTY-NOTICES.md` omits Colorama 0.4.6. The runtime lock names it only for Windows, as a dependency of colorlog 6.12.0 and tqdm 4.70.1 with the marker `sys_platform == 'win32'`. The published wheel's licence file is the three-clause BSD licence.

This session did not build an image with the page OCR archives. It did not run page OCR on an installed system. It did not upgrade a machine from 0.2.2 or RC7.

An upgraded machine gets the espeakng-loader wheel from PyPI. The downloaded wheel is `espeakng_loader-0.2.4`, 10078484 bytes, SHA-256 `08721baf27d13d461f6be6eed9a65277e70d68234ff484fd8b9897b222cdcb6d`, matching the lock. The updater script does not install the espeak-ng source or the loader texts. The image install does: remaster downloads `espeak-ng-1.52.0` and preseed copies that source and the loader texts under `/usr/local/share/doc/plebian-os/espeak-ng`.

No required identity, parent, record, hash, or gitlink mismatched. The records state the owner's decision and what the upstream repositories hold. Both rebuilt page OCR archives match their pins. The app refused an unverified model file and a download. A fresh install, which is the offline path, did not download a model the image ships. The online user step reached both page OCR installs and did not download Paradee or en_core_web_sm. The failed upgrade download placed nothing. Tesseract is on both install routes. The carrier regenerated identically.

VERDICT: ship with known issues
