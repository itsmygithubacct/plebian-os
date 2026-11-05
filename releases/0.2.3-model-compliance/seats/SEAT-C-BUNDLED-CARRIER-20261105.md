# Seat C — bundled carrier review, 2026-11-05

Seat C. This session did not author the carrier, its generator, its determinations, or the 2026-11-05 bundled-delivery update. The review is read-only. No carrier file, reviewed carrier, source checkout, or other seat directory was modified.

New carrier: `/mnt/nvme1n1p1/tmp/rc1-grok-lanes/model-carrier-bundled-20261105/carrier`

Hashed `CARRIER.json`: `842a91b2928655be47be477f331443f87cae5d6e5bbc39655e5b3d4317e2d52e`

## Required identities

All of these were hashed or measured in this review. Each matches.

| Check | Result |
| --- | --- |
| New `CARRIER.json` sha256 | `842a91b2928655be47be477f331443f87cae5d6e5bbc39655e5b3d4317e2d52e` |
| `DEFAULT-MODELS.json` field `sha256` | `e00614bf726154d09668820c061cbbcb402239a445bde666b0568d36f01528a6` |
| `/home/pleb/storage/research/plebian-os/default-models-0221.tar.xz` | 255638496 bytes, same sha256 |
| LFM2 archive sha256 | `c0493cbe633d932da644b8e2acc58ed0ad0761ad952fa34eb8e797b4a2d2b453` |
| `/home/pleb/research/lfm2-default-20261104/delivery/lfm2-kilix-commands-20261104-v8.tar.gz` | 1362204301 bytes, same sha256 |
| small-en-us determination body | `20f27e683074281634fdea130cbc6222b736707d177352c26f6454bb4355c9da` (4233 bytes, full file) |
| whistle determination body | `63babf46e2c19e4d539fd2101d87c2a7eac756ba02762822735cb9f1bd3cf01e` (3665 bytes, full file) |
| Reviewed carrier `CARRIER.json`, re-hashed after the read | `1c250906758e39ee1286af1898c4e747c40aedc29a34993913c781986c0ecf75` |

`SHA256SUMS` (61 lines) matches the carrier files. `CARRIER.json` `bindings_sha256` is the sha256 of `BINDINGS.sha256` (`3c49895de3b9733f66b48c86ec976e5ece0090d29c65eccd5d73ac2140407379`). Every `licence-texts/*.txt` name is the sha256 of its bytes. Each model's `licence_record_file_sha256`, `licence_record_digest`, and `artifact_record_sha256` matches the file and the `LicenseRecord.digest` of that record.

Against the reviewed carrier, the only content changes are the two determination files, the two NOTICE lines that name them, `CARRIER.json` `bindings_sha256`, `BINDINGS.sha256`, and `SHA256SUMS`. No model object inside `CARRIER.json` changed. Both `DELIVERY` files were already `bundled-default-model` and are byte-identical.

## Supersession claim

The 2026-11-05 files claim to supersede only the older distribution sentences. That claim holds.

small-en-us. Diff against `OWNER-DETERMINATION-small-en-us.md` (sha256 `b6a44eca20a27c550b7fe1cf8e83e384f5ead0c2086130d24dd7684c1a536263`). The table is unchanged: Apache-2.0, Alpha Cephei Inc., archive sha256 `30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498`, the accepted gaps, the notice obligations, and the Publication row. The operative OD-S line was removed. That line was: the model is never shipped, the notice obligations and Publication row no longer describe a Kilix-shipped artefact, and the determination is the basis for the licence information shown at first-use download. The new file says those distribution sentences no longer control, says the notice obligations apply to the bundled copy, names the default-model bundle and the catalogued members, and says installation creates local standard-policy receipts. The words "never shipped" occur only as a description of the withdrawn sentences.

whistle. Diff against `OWNER-RC6-WHISTLE-2026-10-08.md` (sha256 `dfa8c6eb538084e1c4b2743c9ea4482dd998cf54e602998519189c81e3912bb2`). Licence stays Apache-2.0. Licensor stays Cactus Compute, Inc. Revision stays `b358ddadd89b7a713b5aa131f23032d3cca1b251`. Pinned LICENSE sha256 stays `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`. The operative paragraph that the release conveys no Whistle weights, that a user downloads them only after the licence screen and an explicit first-use agreement, and that the integration created no user licence receipt, was removed. The new file says those distribution sentences no longer control, states bundled delivery, and says installation creates local standard-policy receipts. The recorder sentence now dates the 2026-10-08 request and says the 2026-11-05 selection was recorded by someone who did not choose the licence. That is attribution, not a licence change.

The licence records are byte-identical to the reviewed carrier. small-en-us remains Apache-2.0, licensor `Alpha Cephei Inc.`, text `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`, no binding conditions, record digest `651e3930a3eade07d83099644fc08dec8db00c22e08dcf328194ab5ca1dbfd75`. whistle remains Apache-2.0, licensor `Cactus Compute, Inc.`, the same Apache text, no binding conditions, record digest `9fc99f4c1e75d83e1f069d82cddf4029ff83bc66287ea39390b52bf946f926f9`. Both are standard-policy eligible. `CARRIER.json` licensors match those records. `DELIVERY` for both is `bundled-default-model` and says installation creates local standard-policy receipts and that build-time receipts are never distributed.

`kilix/config/default_models.py` `authorize()` refuses a bundle member that is not standard-policy eligible, and on `CoverageRefused` writes a local standard-policy receipt. Build receipts go to a temporary store and are not copied into the archive. `install_archive` rejects unexpected members. `vosk-model-small-en-us-0.15` and `whistle` are in `DEFAULT_MODELS`. `lfm2-kilix-commands` is not.

The bundle listing matches. `manifest.json` is `plebian-os.default-models/v1` and its asset map equals `DEFAULT-MODELS.json` `assets`. All 19 catalogued small-en-us and whistle members are present with the artifact sizes and sha256 values, including `am/final.mdl` (`15962575`, `75370a0137f9daf8f469dedd7daa4513ae7a621f03240c6e512e2b50b656a7b6`), the small-en-us README (`Copyright 2020 Alpha Cephei Inc`), `whistle.cact` (`16919407`, `b6e02f048568ac5d01a2042556c658061e699acbc0aa2a1439f52f3d461dffeb`), and both Apache texts at `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`. Installed member manifest digests in the determinations match `CARRIER.json`: small-en-us `1523d976c7609d33dc4e908115e22126c9f06b0a670511cd0fd7090075900341`, whistle `407cec51d26bc0574b09619c271007a49ec3289d1cee8e5fb73271d1088669c1`.

The sealed `determinations.json` pin on the small-en-us record (`3038192435db0f5f9ea82667e5f35ab3f729a9bebc95dea96328221affb9a130`) still quotes the old OD-S sentence as basis quote `small-od-s-supersession`, sourced from the replaced file `b6a44eca…`. That quote records what the old file said. It is not republished as the carrier determination. The NOTICE names only `OWNER-DETERMINATION-small-en-us-BUNDLED-20261105.md`. Receipt coverage compares manifest, licence id, licensor, licence-text digest, binding-condition digests, decision, and record digest. It does not enforce that quote. The whistle app-determinations pin `80347a2c4616993a5fe77f3657ccc8d3010cf55364a883a5c905e8f82c1b2ebc` does not contain "conveys no" weights. The older sentences do not remain controlling beside the bundled statements.

## The other five models

lgraph-en-us. Determination distribution row still says superseded by OD-S, never shipped, first-use licence information. `DELIVERY` and `CARRIER.json` are `first-use-upstream-download`. The asset is not in the default bundle. Licence record is Apache-2.0, licensor `Appen; Alpha Cephei`, digest `3de52a5bdf4a53d6002aef63115f2e8efbf6a33c2424912fbea85f41aa7dacc7`. NOTICE licensors are `Appen; Alpha Cephei`. Deferred status matches. Standard-policy eligible, and the delivery text still requires a kilix-license receipt before any download.

vibevoice-asr-bitnet. Determination: MIT, licensor Microsoft, with a component exception that the Qwen2.5-1.5B decoder lineage is Apache-2.0, licensor Alibaba Cloud. Distribution: first use, never shipped. `DELIVERY` is `first-use-upstream-download`. Not in the bundle. Licence record is MIT, licensor `Microsoft Corporation`, component `qwen2.5-1.5b-decoder-lineage` exception text `832dd9e00a68dd83b3c3fb9f5588dad7dcf337a0db50f7d9483f310cd292e92e`, digest `cc29b19cb8fef40243a9c7239784760c67ad52e91a4d600b78b271c6f35f9c8a`. That record is not standard-policy eligible because of the exception, so a receipt is still required. NOTICE lists `mit, apache-2.0` and `Microsoft Corporation; Alibaba Cloud`, which is the catalog view of the same determination plus the exception. The bytes of this model were not changed by the 2026-11-05 update.

whisper-small-en. Determination: MIT, licensors OpenAI and SYSTRAN, first use, never shipped in the image. `DELIVERY` is `first-use-upstream-download`. Not in the bundle. Licence record id `faster-whisper-small-en`, MIT, licensor `OpenAI; SYSTRAN`, digest `3e64fa1bbdfff99f176f524473f02396fff13f4f81fff66229f158d6bbb34a4c`. NOTICE matches. Standard-policy eligible, and delivery still gates the download on a receipt.

kilix-diarization-cpu. See the defect below. Delivery mode itself matches the determination's deferred scope: `first-use-upstream-download`, weights not in the image, download only after a kilix-license receipt, local conversion of the pinned ModelScope checkpoint. The model is not in the default bundle. The CAM++ determination still grants Apache-2.0 for checkpoint `5b1a88b6f8d85826fabef804779c3372b42f3af21457fa48bd5c097c0686b2de` at revision `032b8131a7ad812f87061955ca974c99060c5a03`, and it does not say the weights are bundled.

lfm2-kilix-commands. See the receipt gate below. `DELIVERY` is `bundled-command-model-archive`. It is not in the default-model bundle.

## lfm2-kilix-commands receipt gate

The custom terms are the LFM Open License, not a standard permissive licence. The carrier determination is byte-identical to `determinations-lfm2.json` and to pin `b7306dfa93ff8b62056e9d50ed3e174714df83ccb7c440ae1d31a8e9dbd5a09e`. It requires `commercial-use-limitation`, `agreement_required` true, text id `liquid-ai/lfm-open-license-v1/commercial-use`, text sha256 `17f031acfa9fd5163a13f1ddd51e28df17c536d6969c6f65efff24309dde1e77`. The licence record copies that condition. Record digest `9db4f6745db84b5554907fdf78332599fbcecfeb87ec2d3151f57f59b05bd000` matches `CARRIER.json`. Licensor strings match: record `Liquid AI, Inc.; ggml and bundled runtime contributors`, and `CARRIER.json` `["Liquid AI, Inc.","ggml and bundled runtime contributors"]`. The full licence in the carrier is `4d28ca14dedc0b3d0fcc2b3339f0e79931faa33874f3d24f522183a8fc70068c`, and section 5 is the commercial-use limitation, including the annual-revenue threshold. The excerpt file `17f031ac…` is what the selector shows; it is in the kilix-license text store. The full licence text that contains it is in the carrier.

`standard_policy_eligible` is false because the binding condition is present. Selecting the model still requires a user receipt. `wizard_licenses.consent_and_install` skips the standard-policy path for this record, shows the licence and the binding condition, and writes a receipt only after an interactive yes. `model_wizard.finish` runs that consent batch before `check_workflows(..., select=True)`. `kilix_content.first_use.install_with_agreement` writes the receipt and calls `require` before `ensure_supplied_asset` or an upstream fetch. Declining writes nothing and does not fetch.

Staging does not create that receipt. `provision/stage-command-model.py` checks the archive size and sha256, extracts the pinned `notices/` documents, and publishes those bytes under `/usr/local/share/doc/plebian-os/models/`. It does not import kilix-license, open a receipt store, or call `capture_agreement` or `capture_standard_policy`. `plebian-os-provision.sh` runs that stager, then installs the default-model bundle. The default-model installer does not include `lfm2-kilix-commands`. The `DELIVERY` sentence "Staging bytes does not create a licence receipt or waive the model's custom terms" matches the code. The command-archive pin matches `COMMAND-MODEL.json`: 1362204301 bytes, sha256 `c0493cbe633d932da644b8e2acc58ed0ad0761ad952fa34eb8e797b4a2d2b453`, manifest `db2674e05b073e08e2ebbb25aea8a5f5d8ac3de2fcb0bba8d4c4a39512fdaa61`.

## Known issue: kilix-diarization-cpu licensors

A receipt binds `kilix-diarization-cpu/LICENCE-RECORD.json` (file sha256 `69d6168c32821c7397b6aea1bab5dc2d2b1503d9a35d20c99099c9fd986102be`, digest `e1feb5ca5f96b9725776f22ab0541d3997779674a23600dd6d17d987977cb2d3`). Coverage compares `receipt.licensor` to that record's `licensor` field.

The three licensor statements do not match.

- Published NOTICE: `IIC / Alibaba Cloud; pyannote contributors; sherpa-onnx contributors; Microsoft and bundled runtime contributors`
- `CARRIER.json` `licensors`: `IIC / Alibaba Cloud`, `pyannote contributors`, `sherpa-onnx contributors`, `Microsoft and bundled runtime contributors`
- Licence record a receipt would bind: `IIC / Alibaba Cloud; pyannote contributors; sherpa-onnx and bundled runtime contributors`

The notice and `CARRIER.json` name Microsoft and split sherpa-onnx from the bundled runtime contributors. The bound record does not name Microsoft and joins sherpa-onnx with the bundled runtime contributors. The same split appears on licence names: the NOTICE and `CARRIER.json` say `apache-2.0` only, while the bound record's `licence_ids` are Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause, and MPL-2.0. The five texts are present in `licence-texts/`. This review does not repair the mismatch.

This is a pre-existing identity defect. The 2026-11-05 diff did not touch this model. It is still in the carrier under review. Delivery mode and the receipt gate for this deferred model are otherwise intact: the record is not standard-policy eligible, and `DELIVERY` says no install route downloads it until a receipt covers it.

## Result

Required hashes match. The small-en-us and whistle determinations now state bundled delivery and local standard-policy receipts, withdraw the older distribution sentences, and leave licence identity unchanged. Those statements match the licence records, the delivery files, the bundle bytes, and the install-time standard-policy receipt path. Deferred models stay deferred. The LFM custom-term receipt gate still binds selection, and staging the archive does not create the receipt. The diarization licensor mismatch is a defect.

VERDICT: ship with known issues
