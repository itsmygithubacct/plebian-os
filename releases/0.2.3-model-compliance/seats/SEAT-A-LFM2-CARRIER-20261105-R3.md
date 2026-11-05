# Seat A — LFM2 carrier review, 2026-11-05 R3

Seat A. This session did not author the carrier, the generator, the determinations, or the LFM2 promotion.

Carrier, read only: `/mnt/nvme1n1p1/tmp/rc1-grok-lanes/model-carrier-bundled-20261105/carrier-licensor-fix`. Candidate trees, read only: `023-rc1-takeover-20261103/plebian-os` and `023-rc1-takeover-20261103/kilix`. `sha256sum -c SHA256SUMS` in the carrier completed with every file OK. Each `licence-texts/*.txt` name is the sha256 of its bytes. Each model's computed licence-record digest and licence-record file sha256 match `CARRIER.json`.

## Required hashes

Computed on the named files. Each digest below is identical to the required value.

- `CARRIER.json` sha256 `455dc464e4e32382512d33ecbdfc21fc950fff0fd5c10cd852c1764c4fefe368`
- `DEFAULT-MODELS.json` field `sha256` `e00614bf726154d09668820c061cbbcb402239a445bde666b0568d36f01528a6`, equal to `/home/pleb/storage/research/plebian-os/default-models-0221.tar.xz` (255638496 bytes). The archive `manifest.json` asset map equals that file's `assets` map.
- LFM2 command archive sha256 `c0493cbe633d932da644b8e2acc58ed0ad0761ad952fa34eb8e797b4a2d2b453`, equal to `/home/pleb/research/lfm2-default-20261104/delivery/lfm2-kilix-commands-20261104-v8.tar.gz` (1362204301 bytes) and to `COMMAND-MODEL.json` `sha256`.

`provision/default-models.json` and `provision/command-model.json` parse equal to the carrier copies. `provision/command-model-determination.json` is byte-identical to `determinations/lfm2-kilix-commands/command-model-determination.json`.

## small-en-us

The controlling text is `OWNER-DETERMINATION-small-en-us-BUNDLED-20261105.md`. Licence Apache-2.0, licensor Alpha Cephei Inc., decision affirmative. The licence record, notice, and artifact licence row use that same licensor string, so a receipt binds `Alpha Cephei Inc.`. Delivery is `bundled-default-model`. The 2026-11-05 paragraphs supersede the older never-shipped / first-use-only sentences in the same file.

The default bundle contains the members that determination names: `vosk-model-small-en-us-0.15/am/final.mdl` (15962575 bytes, sha256 `75370a0137f9daf8f469dedd7daa4513ae7a621f03240c6e512e2b50b656a7b6`), `vosk-model-small-en-us-0.15/README` (199 bytes, sha256 `c0cf286e4f7783306c5f6469b37db69228fb16803b03cae661edb2d7bba64ebb`), and `vosk-model-small-en-us-0.15/notices/LICENSE-apache-2.0.txt` (11358 bytes, sha256 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`). The installed member manifest digest `1523d976c7609d33dc4e908115e22126c9f06b0a670511cd0fd7090075900341` is the bundle inventory entry.

`kilix/config/default_models.py` lists `vosk-model-small-en-us-0.15`. The record is standard-policy eligible and has no agreement-required condition. `authorize()` writes a `capture_standard_policy` receipt into the shared store when coverage is absent. A build uses a scratch receipt store and does not copy those receipts into the bundle. That is the receipt the bundled determination and `DELIVERY` describe.

## lgraph-en-us

`OWNER-DETERMINATION-lgraph-en-us.md` determines Apache-2.0, licensors Appen and Alpha Cephei, and keeps the model unshipped as the basis for the first-use screen. The record licensor is `Appen; Alpha Cephei`, matching the notice. Delivery is `first-use-upstream-download`. No 2026-11-05 bundled supersession is in this file. Deferred delivery matches the determination that still controls.

## vibevoice-asr-bitnet

`OWNER-DETERMINATION-vibevoice-asr-bitnet.md` plus the J1/J2 ruling and the 2026-09-29 C2 amendment determine MIT for Microsoft, with the Qwen2.5-1.5B decoder lineage as an Apache-2.0 component exception for Alibaba Cloud, a research-use advisory, first-use download, and runnable status. The record matches that shape: licensor `Microsoft Corporation`, `licence_ids` `MIT`, advisory `9ef874baa37eb4edc5fd731ad7c2587149986f9dff4760679421735e5b6daee3`, and component `qwen2.5-1.5b-decoder-lineage` bound to Apache text `832dd9e0a68dd83b3c3fb9f5588dad7dcf337a0db50f7d9483f310cd292e92e`. Both texts are in `licence-texts/`. The asset has two licence rows, MIT/Microsoft and Apache-2.0/Alibaba, sharing record digest `cc29b19cb8fef40243a9c7239784760c67ad52e91a4d600b78b271c6f35f9c8a`. The notice lists both rows. The receipt binds the record licensor `Microsoft Corporation` and the exception text through the record digest. Delivery is `first-use-upstream-download` and `runnable` is true. The record is outside standard policy because of the component exception, and it has no agreement-required condition, so selection takes an ordinary accept receipt. C3's receipt gate matches `DELIVERY`.

## whisper-small-en

`OWNER-DETERMINATION-whisper-small-en.md` determines MIT, licensors OpenAI and SYSTRAN, the card caution as an advisory, first-use download, and a runnable faster-whisper runtime. The record id is `faster-whisper-small-en`, licensor `OpenAI; SYSTRAN`, advisory `0e9d0d19fa02b8f246d9902d93a2b0b0fac7cb07a518257ffa7d102d1c37c638`, statement `94536c807e7ad8257102a5db0496db0bf1753fc8b32cba9188e337d9796db7d0`. The notice matches. Delivery is `first-use-upstream-download`.

## whistle

The controlling text is `OWNER-RC6-WHISTLE-BUNDLED-20261105.md`. Licence Apache-2.0, licensor Cactus Compute, Inc., revision `b358ddadd89b7a713b5aa131f23032d3cca1b251`, pinned LICENSE sha256 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`. The record and notice use that licensor string. The older sentences that withheld the weights and said the integration created no user receipt are withdrawn in this file. Delivery is `bundled-default-model`.

The default bundle contains `whistle/whistle.cact` (16919407 bytes, sha256 `b6e02f048568ac5d01a2042556c658061e699acbc0aa2a1439f52f3d461dffeb`), `whistle/LICENSE` and `whistle/notices/LICENSE-apache-2.0.txt` (each 11358 bytes, the Apache digest above), and `whistle/README.md` (6882 bytes, sha256 `7c288d7eded692c795cc932902ee3f7fe6aa7c6417ca28a954088f1aa8a9f8f4`). Manifest digest `407cec51d26bc0574b09619c271007a49ec3289d1cee8e5fb73271d1088669c1` is the bundle inventory entry. The record is standard-policy eligible. `default_models.py` includes `whistle` and writes the same local standard-policy receipt described for small-en-us. Build-time receipts stay in the scratch store.

## kilix-diarization-cpu

Notice licensors and the licence-record licensor string are the same string: `IIC / Alibaba Cloud; pyannote contributors; sherpa-onnx and bundled runtime contributors`. `coverage.py` binds `receipt.licensor` to `record.licensor`. The asset licence row lists those three names in that order. A receipt therefore binds the notice string.

The stored machine determination is `determinations-diarization.json`, sha256 `36518b7f540f06d4f177a541cf3fa7df747ca2ad533acc729f19af678f4d7377`, which is the record's `determinations_sha256` and the pin file. Its record fields match `LICENCE-RECORD.json` once that pin is applied. The carrier markdown `0.2.1-F104-CAMPP-WEIGHT-LICENCE.md` is byte-identical to licence text `54b36539688fe450074a0105a2e43719837c321e4cf0eff8d7884a2d92ad21ad`, and that digest is both `authority.weight_determination_sha256` and statement `campp-digest-specific-grant`. The markdown is the digest-specific Apache-2.0 grant for English CAM++ checkpoint `5b1a88b6f8d85826fabef804779c3372b42f3af21457fa48bd5c097c0686b2de` at commit `032b8131a7ad812f87061955ca974c99060c5a03`, plus the local ONNX conversion conditions. The record carries that grant, the local-ONNX statement `598ee20c7456841a757590b5c4ba7ad044893b4df768a3195cf8efe2d036a611`, the pyannote segmentation MIT text `14d7016ad68e7394d6e6b78d96cc2ae431c905287b89674cfdf021e79e62b8ba` (Copyright CNRS), and runtime notice `8923cff8327b3291650bb1658bb7f3d12dd117a6a66aabaf67926221c19a0439`. The artifact converts the pinned checkpoint locally and records embedding sha256 `7cfea971b2231ed7d7dd6324de1de33f8f9dbe65bbb30cf64b4b0b203b566292`. It does not use the uncleared `csukuangfj/speaker-embedding-models` mirror. Delivery is `first-use-upstream-download`. The record is outside standard policy because of the pyannote exception text, so the catalog records an accept receipt before download and conversion. `transcribe_provider.py` opens that installed asset and binds `manifest_sha256` before diarization preparation.

## lfm2-kilix-commands

`command-model-determination.json` and `LICENCE-RECORD.json` set `agreement_required` true on `commercial-use-limitation`, text id `liquid-ai/lfm-open-license-v1/commercial-use`, text sha256 `17f031acfa9fd5163a13f1ddd51e28df17c536d6969c6f65efff24309dde1e77`. That text is in the candidate licence store, 560 bytes, and its hash matches. Its sentences are present in carried licence `4d28ca14dedc0b3d0fcc2b3339f0e79931faa33874f3d24f522183a8fc70068c`. The record also binds runtime notice `571c0295ffbb60b79627a8956e2990826448eee7678b8d9a1e37c82bbf779f4c` and modified-model statement `e03643ad3853ac201afb79ae9561b50936f82b02d77eb317daa82245cf0364a5`. Those three digests are the carrier `licence_text_sha256s`. Licensor `Liquid AI, Inc.; ggml and bundled runtime contributors` matches the notice and the asset row. `determinations_sha256` equals the determination file.

The four `COMMAND-MODEL.json` documents were read from the archive and match its sizes and digests, including `notices/LICENSE-kilix-needle.txt` sha256 `938e0db7e6acd7e99d205863bcbdeda47f5fbd053802519f411dbefe0799071e`. `DELIVERY` mode is `bundled-command-model-archive`.

`provision/stage-command-model.py` verifies the archive, caches it by sha256, and writes the notice documents. It writes no licence receipt. `default_models.py` does not list this asset. The record is not standard-policy eligible and `requires_typed_agreement` is true, so a distribution-policy receipt cannot cover it. `Installer._select_asset` requires a covering receipt before it reads `KILIX_CONTENT_ARCHIVE_CACHE` (`/usr/local/share/kilix/model-archives` by default); `tests/test_upstream_install.py` `test_receipt_is_required_before_cache_access` holds that gate. First selection still requires a user receipt for this licence record and member manifest. Staging the archive does not create that receipt and does not waive the commercial-use term.

## Result

All seven models are in `CARRIER.json`. The required hashes match. The 2026-11-05 small-en-us and whistle texts match bundled delivery and the standard-policy receipts installation writes. The LFM2 custom terms and receipt gate match the candidate sources. The diarization notice licensors match the licensor string a receipt binds, and the pinned determination matches the record.

VERDICT: ship
