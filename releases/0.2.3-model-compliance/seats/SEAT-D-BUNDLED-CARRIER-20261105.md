# Seat D — bundled carrier review, 2026-11-05

Seat D. This session did not author the carrier, its generator, its determinations, or the 2026-11-05 bundled-delivery update.

Reviewed read-only:
`/mnt/nvme1n1p1/tmp/rc1-grok-lanes/model-carrier-bundled-20261105/carrier`

The reviewed carrier at `/home/pleb/research/lfm2-default-20261104/model-carrier/carrier` was not modified. Its `CARRIER.json` sha256 is still `1c250906758e39ee1286af1898c4e747c40aedc29a34993913c781986c0ecf75`.

New `CARRIER.json` sha256, hashed in this review: `842a91b2928655be47be477f331443f87cae5d6e5bbc39655e5b3d4317e2d52e`.

## Required identities

| Check | Result |
| --- | --- |
| New `CARRIER.json` sha256 | `842a91b2928655be47be477f331443f87cae5d6e5bbc39655e5b3d4317e2d52e` |
| `DEFAULT-MODELS.json` field `sha256` | `e00614bf726154d09668820c061cbbcb402239a445bde666b0568d36f01528a6` |
| `default-models-0221.tar.xz` | same sha256, 255638496 bytes |
| `COMMAND-MODEL.json` / LFM archive sha256 | `c0493cbe633d932da644b8e2acc58ed0ad0761ad952fa34eb8e797b4a2d2b453` |
| `lfm2-kilix-commands-20261104-v8.tar.gz` | same sha256, 1362204301 bytes |
| small-en-us determination body | `20f27e683074281634fdea130cbc6222b736707d177352c26f6454bb4355c9da` |
| whistle determination body | `63babf46e2c19e4d539fd2101d87c2a7eac756ba02762822735cb9f1bd3cf01e` |
| Reviewed `CARRIER.json` | `1c250906758e39ee1286af1898c4e747c40aedc29a34993913c781986c0ecf75` |

`sha256sum -c SHA256SUMS` and `sha256sum -c BINDINGS.sha256` both succeeded. Every file under `licence-texts/` hashes to its own filename. `CARRIER.json` `bindings_sha256` is the sha256 of `BINDINGS.sha256`. Each model's `licence_record_file_sha256` matches its `LICENCE-RECORD.json`, and each `licence_record_digest` matches the OD-AI binding digest of that record (licensor, licence text, licence ids, agreement-required binding texts, and component exception texts; `determinations_sha256` is not in that digest).

Against the reviewed carrier, the only content changes are the two replacement determinations, the two notice pointers to those files, `BINDINGS.sha256`, `SHA256SUMS`, and `CARRIER.json` `bindings_sha256`. Model delivery modes, licence records, artifacts, and `DELIVERY` files are unchanged.

## Supersession test (small-en-us and whistle)

Both new files keep the licence substance and replace only the distribution close.

small-en-us stays Apache-2.0, licensor Alpha Cephei Inc., archive sha256 `30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498`, with the same accepted gaps, basis, and 2026-09-15 owner selection. The 2026-09-15 OD-S close is not restated as a rule. The new file says those sentences said the model is never shipped and that the determination is the first-use download screen, and that those sentences no longer control. It then states bundled-default-model delivery and that installation creates local standard-policy receipts. The phrase "never shipped" occurs only inside that withdrawal.

whistle stays Apache-2.0, licensor Cactus Compute, Inc., revision `b358ddadd89b7a713b5aa131f23032d3cca1b251`, LICENSE sha256 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`. The new file says the older sentences said the release conveys no Whistle weights, that download followed a first-use agreement, and that the integration created no user receipt, and that those sentences no longer control. It then states the weights are in the default bundle and that installation creates local standard-policy receipts. "Conveys no weights" occurs only inside that withdrawal.

Those statements match the carrier. Both `CARRIER.json` entries and both `DELIVERY` files say `bundled-default-model`. Both licence records are Apache-2.0, with no binding conditions and no component exceptions, so they are standard-policy eligible. `kilix/config/default_models.py` installs `vosk-model-small-en-us-0.15` and `whistle` from the bundle, writes a local standard-policy receipt through the shared receipt store, and uses a temporary receipt store only for the build population that is not copied into the bundle. `provision/install-default-models.py` calls that installer. The bundle members named in the new determinations match the archive: whistle `whistle.cact`, `LICENSE`, `notices/LICENSE-apache-2.0.txt`, and `README.md` (`license: apache-2.0`); small-en-us `am/final.mdl`, `notices/LICENSE-apache-2.0.txt`, and `README` (`Copyright 2020 Alpha Cephei Inc`). Manifest digests match `DEFAULT-MODELS.json` and `CARRIER.json`.

The licence records still pin older determination corpora (`30381924…` for small-en-us, `80347a2c…` for whistle). Those corpora still quote the old distribution text. That pin is not part of the receipt digest, and the carrier determination that the notices name is the 2026-11-05 file, which withdraws the sentence. The old sentence and the bundled statement are not both controlling.

The small-en-us table still has its Publication row, which says the GitHub release upload waits for OD-D. The new text restores the notice obligations and does not repeat that row as a second "never shipped" rule. Installation-media delivery is the statement that now controls.

## Seven models

1. small-en-us. Determination, licence record, and delivery agree: Apache-2.0, Alpha Cephei Inc., bundled, local standard-policy receipt. Not deferred.

2. lgraph-en-us. Determination still says superseded by OD-S, never shipped, first-use screen. Licence record is Apache-2.0, Appen; Alpha Cephei, no extra terms. `DELIVERY` and the notice say weights are absent and no install proceeds without a kilix-license receipt. Deferred. Consistent.

3. vibevoice-asr-bitnet. Determination, J1/J2, and the C2 amendment say MIT (Microsoft) plus an Apache-2.0 Qwen2.5 component exception (Alibaba), research text as an advisory, never shipped, receipt-gated install, and runnable. The licence record binds Microsoft as licensor, MIT as `licence_ids`, the Qwen exception text `832dd9e0…`, and the advisory `9ef874ba…`. `CARRIER.json` and the notice list both licensors because the asset licence list does; the receipt binds the record, which carries Alibaba's text as that component exception. Delivery is first-use upstream download. The component exception makes the record ineligible for a silent standard-policy receipt. Deferred. Consistent.

4. whisper-small-en. Determination says MIT, OpenAI and SYSTRAN, never shipped, first-use download, runnable. The licence record matches (MIT, OpenAI; SYSTRAN, card advisory, no binding conditions). Delivery is first-use and receipt-gated. Deferred. Consistent.

5. whistle. Covered above. Bundled Apache-2.0, Cactus Compute, Inc., local standard-policy receipt. The withdrawn "conveys no weights" sentence does not still control.

6. kilix-diarization-cpu. Delivery is first-use upstream download from www.modelscope.cn, receipt required before download, not bundled. That matches the determination: digest-specific Apache-2.0 for checkpoint `5b1a88b6…`, local ONNX conversion, not selected by default. The pyannote exception text is on the record, so a standard-policy receipt cannot cover it. The receipt gate matches.

   The published licensors do not match the record a receipt binds. This is a defect. It was not repaired.

   - Notice: `IIC / Alibaba Cloud; pyannote contributors; sherpa-onnx contributors; Microsoft and bundled runtime contributors`
   - `CARRIER.json` `licensors`: `IIC / Alibaba Cloud`, `pyannote contributors`, `sherpa-onnx contributors`, `Microsoft and bundled runtime contributors`
   - `ARTIFACT.json` licence licensors: the same four names
   - `LICENCE-RECORD.json` `licensor`, which coverage compares onto the receipt: `IIC / Alibaba Cloud; pyannote contributors; sherpa-onnx and bundled runtime contributors`

   The receipt record drops Microsoft and joins sherpa-onnx with the bundled runtime. The native-runtime notice in the carrier does contain Microsoft copyright lines and a sherpa-onnx attribution, but the record's `native-runtime` component has no exception text and is not in the binding digest. The notice and `CARRIER.json` `licence_ids` say `apache-2.0` only. The bound record's `licence_ids` are Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause, and MPL-2.0.

7. lfm2-kilix-commands. Custom terms are LFM Open License v1.0, licensor Liquid AI, Inc., text sha256 `4d28ca14…`, plus the modified-model notice and the CPU runtime notices. The record's binding condition `commercial-use-limitation` has `agreement_required: true` and text sha256 `17f031acfa9fd5163a13f1ddd51e28df17c536d6969c6f65efff24309dde1e77`. That text is the Threshold definition together with section 5 (Commercial Use Limitation). Both passages are in the shipped `LICENSE-LFM.txt`; section 5 is not licensed under this agreement once a legal entity exceeds the $10,000,000 threshold. `LFM-Open-License-1.0` is outside the standard-policy set, and the binding condition makes `standard_policy_eligible` false, so `capture_standard_policy` refuses it.

   Selecting the model still requires a user receipt. `wizard_licenses.consent_and_install` shows the licence and the binding condition and writes a receipt only after an affirmative answer, bound to the record digest `9db4f674…` and the member manifest `db2674e0…`. `kilix models install` asks at a terminal and `Installer._select_asset` requires a covering receipt before it stages or selects an asset. `provision/stage-command-model.py` checks the archive pin and writes the archive and `notices/` documents. It does not import or write a licence receipt. The OS update calls that stager and states that user agreement and selection remain in Kilix. Staging does not create the receipt. Delivery mode `bundled-command-model-archive` matches that split. Notice, `CARRIER.json` licensors, and the record licensor agree: Liquid AI, Inc., and ggml and bundled runtime contributors.

## Verdict

Required hashes match. The small-en-us and whistle determinations now state bundled delivery and a local standard-policy receipt, and the older "never shipped" and "conveys no weights" sentences do not still control. The LFM receipt gate holds. The diarization notice and the licence record a receipt would bind do not name the same licensors.

VERDICT: ship with known issues
