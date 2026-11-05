# Seat B — LFM2 carrier review, 2026-11-05 R3

Seat B. Independent review of `carrier-licensor-fix`. This seat did not author the carrier, the generator, the determinations, or the LFM2 promotion. The carrier directory predates this session, and this workspace held only the brief.

Carrier, read only: `/mnt/nvme1n1p1/tmp/rc1-grok-lanes/model-carrier-bundled-20261105/carrier-licensor-fix`.

Candidate sources, read only: `023-rc1-takeover-20261103/plebian-os` and `023-rc1-takeover-20261103/kilix`.

## Required identities

Computed sha256 of `CARRIER.json` is `455dc464e4e32382512d33ecbdfc21fc950fff0fd5c10cd852c1764c4fefe368`.

Computed sha256 of `/home/pleb/storage/research/plebian-os/default-models-0221.tar.xz` (255638496 bytes) is `e00614bf726154d09668820c061cbbcb402239a445bde666b0568d36f01528a6`, the same value as the `sha256` field in `DEFAULT-MODELS.json`. The archive manifest lists the same asset digests as that pin, including `vosk-model-small-en-us-0.15` and `whistle`.

Computed sha256 of `/home/pleb/research/lfm2-default-20261104/delivery/lfm2-kilix-commands-20261104-v8.tar.gz` (1362204301 bytes) is `c0493cbe633d932da644b8e2acc58ed0ad0761ad952fa34eb8e797b4a2d2b453`. That is the archive digest in `CARRIER.json`, `COMMAND-MODEL.json`, and `provision/command-model.json`. The four notice members inside the archive match the `COMMAND-MODEL.json` document sizes and digests, including `notices/LICENSE-LFM.txt`, `notices/LICENSE-runtime.txt`, `notices/NOTICE.txt`, and `notices/LICENSE-kilix-needle.txt`.

Every `licence-texts/*.txt` file hashes to its filename. Recomputing each licence-record digest with `LicenseRecord.digest` matches `CARRIER.json` `licence_record_digest` for all seven models.

## small-en-us

`OWNER-DETERMINATION-small-en-us-BUNDLED-20261105.md` is the controlling text. It keeps Apache-2.0 and licensor Alpha Cephei Inc., and it records bundled delivery. The older never-shipped distribution sentences in that file are withdrawn by the file itself.

The licence record matches that licence and licensor, with no binding conditions and no component exceptions. `DELIVERY` is `bundled-default-model` and says installation creates local standard-policy receipts while build-time receipts are not distributed. `NOTICE` names the same licensor and the bundled conveyance. `CARRIER.json` delivery is `bundled-default-model`. The model is the dictation model.

The claimed bundle members are in `default-models-0221.tar.xz` at the stated sizes and digests: `am/final.mdl`, `notices/LICENSE-apache-2.0.txt`, and `README` (`Copyright 2020 Alpha Cephei Inc`). The installed member manifest digest matches `DEFAULT-MODELS.json`.

`config/default_models.py` includes `vosk-model-small-en-us-0.15`. The record is standard-policy eligible. Install calls `authorize`, which writes a `capture_standard_policy` receipt into `ReceiptStore.shared()` when coverage is missing, then `ensure_supplied_asset`. The build path uses a temporary receipt store and does not copy receipts into the bundle. Provisioning runs `install-default-models.py --offline` through `as_user`, so the receipt is written for the desktop user. `PROVISION_VOICE_WEIGHTS=0` keeps `kilix voice install` on `--without-dictation`, so that leg does not fetch the Vosk zip during provisioning.

## lgraph-en-us

The determination is Apache-2.0, licensors Appen and Alpha Cephei, distribution superseded by the never-shipped / first-use rule. The licence record licensor is `Appen; Alpha Cephei`, Apache-2.0, affirmative, no extra conditions. `DELIVERY` and `CARRIER.json` are `first-use-upstream-download`. `NOTICE` says these bytes are not distributed. The receipt gate is `kilix-stt --check-licence` before `fetch_verified` in `scripts/install-kilix-voice.sh` (`require_dictation_receipt` runs before the model fetch).

## vibevoice-asr-bitnet

The determination is MIT, licensor Microsoft Corporation, with the Qwen2.5-1.5B decoder lineage as an Apache-2.0 component exception, licensor Alibaba Cloud. J1 keeps the research-use text as an advisory. The C2 amendment makes the engine runnable. Distribution remains first-use download, receipt-gated, weights not shipped.

The licence record matches that shape: licensor `Microsoft Corporation`, licence id MIT, component `qwen2.5-1.5b-decoder-lineage` bound to the Apache-2.0 text, advisory `vibevoice-research-advisory`, affirmative. `CARRIER.json` and `NOTICE` list both `mit` and `apache-2.0` and both licensors. The catalog asset carries both licence entries on one record digest, `cc29b19cb8fef40243a9c7239784760c67ad52e91a4d600b78b271c6f35f9c8a`. `DELIVERY` is `first-use-upstream-download` and runnable. The component exception keeps the record outside standard policy, so selection still takes a user agreement. `CARRIER.json` `runnable` is true.

## whisper-small-en

The determination is MIT, licensors OpenAI and SYSTRAN, card cautions as an advisory, first-use download, never shipped, runnable. The licence record licensor is `OpenAI; SYSTRAN`, licence id MIT, advisory `whisper-card-caution`. `DELIVERY` is `first-use-upstream-download` and says the speech install command hands the download to the model catalog and fetches no weights itself. `NOTICE` says these bytes are not distributed. `CARRIER.json` matches that deferred, runnable mode.

## whistle

`OWNER-RC6-WHISTLE-BUNDLED-20261105.md` is the controlling text. Licence remains Apache-2.0, licensor Cactus Compute, Inc., revision `b358ddadd89b7a713b5aa131f23032d3cca1b251`. The older sentences that said the release conveys no Whistle weights and that integration created no receipt are withdrawn by this file. Bundled delivery is what it records now.

The licence record matches that licence and licensor, with no binding conditions and no component exceptions, so it is standard-policy eligible. `DELIVERY` is the same `bundled-default-model` receipt paragraph as small-en-us. `NOTICE` and `CARRIER.json` say bundled. `whistle` is in `DEFAULT_MODELS` and in the bundle manifest.

The claimed bundle members match: `whistle.cact`, `LICENSE`, `notices/LICENSE-apache-2.0.txt`, and `README.md`. Installation writes the same local standard-policy receipt as small-en-us, through `authorize` and `ReceiptStore.shared()`, and does not distribute build-time receipts. Whisper small.en stays the recommended dictation default; the carrier dictation model remains `small-en-us`. Bundling does not change an existing selection.

## kilix-diarization-cpu

The stored determination is the F104 CAM++ weight grant: Apache-2.0, English checkpoint `campplus_voxceleb.bin` at ModelScope commit `032b8131a7ad812f87061955ca974c99060c5a03`, sha256 `5b1a88b6f8d85826fabef804779c3372b42f3af21457fa48bd5c097c0686b2de`. That file's sha256 is the record statement `campp-digest-specific-grant` and the candidate authority `weight_determination_sha256`. The artifact input is that same checkpoint. The local ONNX modification statement matches the artifact output digest. Delivery is first-use conversion, not a bundle. `DELIVERY` and `NOTICE` say the bytes are not distributed and that no install proceeds until a kilix-license receipt covers the model. Transcribe's prepare path opens the diarization runtime, which is the receipt and manifest check, before it stages the tool.

Notice licensors and the licence-record licensor string are the same string: `IIC / Alibaba Cloud; pyannote contributors; sherpa-onnx and bundled runtime contributors`. That string is the `licensor` field inside the binding JSON. The recomputed record digest is `e1feb5ca5f96b9725776f22ab0541d3997779674a23600dd6d17d987977cb2d3`, the digest a receipt binds, and it matches `CARRIER.json`. The asset `licensors` array joins to the same notice line. The weight determination stays the CAM++ Apache-2.0 grant. The pyannote segmentation MIT text and the native-runtime notice (which names sherpa-onnx) are the other parties in that same string. The candidate `determinations-diarization.json` record uses that same licensor string. Notice, record, and receipt binding agree.

## lfm2-kilix-commands

The determination and the licence record both set `agreement_required` true on `commercial-use-limitation`, text id `liquid-ai/lfm-open-license-v1/commercial-use`, text sha256 `17f031acfa9fd5163a13f1ddd51e28df17c536d6969c6f65efff24309dde1e77`. The licence text, runtime notice, and modified-model statement are the three texts named by `CARRIER.json`: `4d28ca14dedc0b3d0fcc2b3339f0e79931faa33874f3d24f522183a8fc70068c`, `571c0295ffbb60b79627a8956e2990826448eee7678b8d9a1e37c82bbf779f4c`, and `e03643ad3853ac201afb79ae9561b50936f82b02d77eb317daa82245cf0364a5`. Those files are in the carrier and in the archive. The commercial-use excerpt is the Threshold definition plus section 5 of that LFM licence, and the candidate licence pack stores it at that digest. Licensor is `Liquid AI, Inc.; ggml and bundled runtime contributors`. `determinations_sha256` on the record is the determination file hash, and it matches `determinations-lfm2.sha256` in the candidate tree. `COMMAND-MODEL.json` matches the candidate `provision/command-model.json` and the catalog asset's archive identity.

`DELIVERY` is `bundled-command-model-archive`. It says staging does not create a licence receipt or waive the custom terms, and that first selection requires coverage of the current licence record and member manifest.

That is what the candidate sources do. `provision/stage-command-model.py` verifies the archive, links it at `/usr/local/share/kilix/model-archives/<sha256>`, and publishes the notice files. It writes no receipt. Provisioning runs that stager outside `as_user`. The record has a binding condition, so `standard_policy_eligible` is false and the default-model installer does not mint a policy receipt for it. `lfm2-kilix-commands` is not in `DEFAULT_MODELS`.

Selecting it still requires a user receipt. `wizard_licenses.consent_and_install` shows the licence and the binding condition, takes an explicit yes, and writes `capture_agreement` for a record whose expected decision is accept. `kilix models install` does the same on an interactive terminal and refuses without one. `Installer._select_asset` calls `require_license` before it reads the cached archive, again under the lock, and again after the staged tree is verified. The cache reader in `_populate_upstream_asset` runs only after that coverage gate. Staging the archive does not create the receipt. Selection does.

## Result

All seven models are affirmative and runnable in `CARRIER.json`. Bundled models are small-en-us, whistle, and the separate LFM2 command archive. The other four stay first-use downloads behind a covering receipt. The required hashes, the bundled determinations, the delivery statements, and the LFM2 receipt gate match the files and the candidate sources.

VERDICT: ship
