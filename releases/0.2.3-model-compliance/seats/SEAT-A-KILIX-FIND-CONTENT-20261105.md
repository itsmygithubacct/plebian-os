# Seat A review: kilix-content pin c990180

This session did not author the carrier, the generator, or the determinations. The previous files under `/tmp/carrier-c990180/seats` were not used as evidence. Seat B output was not read.

Compared carriers:

- New: `/tmp/carrier-c990180`
- Previously reviewed: `/tmp/plebian-os-pin/releases/0.2.3-model-compliance`
- Content repository: `/home/pleb/storage/research/plebian-os/023-rc1-takeover-20261103/kilix/third_party/kilix-content`
- Old content commit: `00fe843d0ed22d8c237d616696276042a01b3232`
- New content commit: `c9901809375e16f32530f39b0c8a6774a42e4895`

## 1. CARRIER.json hash and content fields

`sha256sum /tmp/carrier-c990180/CARRIER.json` printed:

`c578757b715a87b8f366fabd0db268c0122d153cef1d26a8ba1f849b4a819726  /tmp/carrier-c990180/CARRIER.json`

Fields read from that document:

- `interface_content_ref`: `c9901809375e16f32530f39b0c8a6774a42e4895`
- `interface_content_schema_sha256`: `a884f259da5275016744f0a4ff08d970084404cc01ebf2e261692b0522162b20`

## 2. DEFAULT-MODELS.json sha256 field

The `sha256` field in `/tmp/carrier-c990180/DEFAULT-MODELS.json` is `e00614bf726154d09668820c061cbbcb402239a445bde666b0568d36f01528a6`.

## 3. Byte compare of the carrier trees

Compared every file in the two carrier directories except `CARRIER.json`, `CARRIER.env`, `BINDINGS.sha256`, `ACCEPTANCE.json`, `SHA256SUMS`, and everything under `seats/`.

Command result: 58 files on each side, 0 paths only in one tree, 58 files in common, 58 byte-identical, 0 differed.

## 4. CARRIER.env

`diff -u` of the two `CARRIER.env` files printed a single changed line. The old value was `interface_content_ref=00fe843d0ed22d8c237d616696276042a01b3232`. The new value was `interface_content_ref=c9901809375e16f32530f39b0c8a6774a42e4895`. No other line differed. That is the only allowed difference.

## 5. CARRIER.json documents

Parsed comparison of the two `CARRIER.json` documents found the same key set. The only differing keys were:

- `bindings_sha256`: old `234da3a6c6eec207c69ab6d514716100541b9d9c9e6d65c672c0740627e5255d`, new `e617cdbae472903c7a42379631970d272e01884db0856c343d34ae0558b5d6f5`
- `interface_content_ref`: old `00fe843d0ed22d8c237d616696276042a01b3232`, new `c9901809375e16f32530f39b0c8a6774a42e4895`

Those are the only allowed differences. `interface_content_ref` is `c9901809375e16f32530f39b0c8a6774a42e4895`. `interface_content_schema_sha256` is unchanged at `a884f259da5275016744f0a4ff08d970084404cc01ebf2e261692b0522162b20`. After removing those two allowed fields, the remaining documents were equal, including `models`, `model_order`, and `dictation_model`.

## 6. Catalog assets and schema between the two commits

`git diff --name-status 00fe843d0ed22d8c237d616696276042a01b3232 c9901809375e16f32530f39b0c8a6774a42e4895` printed:

- `M src/kilix_content/catalog/plebian.json`
- `M src/kilix_content/receipt.py`

`git diff --exit-code` on `contracts/kilix.content.asset-v3.schema.json` exited 0. `git show` of that schema at both commits hashed to the same value, `a884f259da5275016744f0a4ff08d970084404cc01ebf2e261692b0522162b20`, which matches the carrier schema field. The schema file did not differ.

`git show` of `src/kilix_content/catalog/plebian.json` at both commits:

- Top-level keys stayed `schema_version`, `packages`, `content`, and `assets`.
- `schema_version` and `packages` were equal.
- `assets` stayed a list of 39 objects. The asset id set and the asset id order were identical. No asset object differed. No asset id was added or removed.
- `content` went from 53 entries to 54. No existing content object differed. Exactly one content id was added: `kilix-find`.

`kilix-find` is a content entry with `kind` `app`. It is not in the `assets` array. Its keys are `actions`, `binary`, `build`, `capabilities`, `dependency_hint`, `description`, `icon`, `id`, `kind`, `label`, `launch`, and `source`. Content kinds moved from 35 app / 16 game / 2 tool to 36 app / 16 game / 2 tool. Asset records do not use those content kinds.

Carried model artifact ids, all present in `assets` at both commits and byte-for-record identical across the two commits:

- `kilix-diarization-cpu` → `kilix-diarization-cpu`
- `lfm2-kilix-commands` → `lfm2-kilix-commands`
- `lgraph-en-us` → `vosk-model-en-us-0.22-lgraph`
- `small-en-us` → `vosk-model-small-en-us-0.15`
- `vibevoice-asr-bitnet` → `vibevoice-asr-bitnet`
- `whisper-small-en` → `faster-whisper-small-en`
- `whistle` → `whistle`

The catalog diff itself is a single inserted object, the `kilix-find` content entry, placed before the existing `kilix-graphs` content entry. No model file in the carrier tree differed.

`receipt.py` also changed, outside the catalog and schema files. The change replaces the catalog digest pin. The old pin `8c6285f33ff3e420c1949b86f956598eec921bdf993ac7cb2d50bc6d1ed38c53` matches the old catalog bytes. The new pin `1e9c95eb5d14eef39ce61e613e02629b60f7f34ecfd54e71306495bd5bded178` matches the new catalog bytes. The asset v3 schema pin in that file stayed `a884f259da5275016744f0a4ff08d970084404cc01ebf2e261692b0522162b20`. That is not an asset, schema, model-file, or content-ref mismatch.

## Result

Every required check passed. Model files were byte-identical. Asset objects and the asset id set were identical. The schema file was identical. The content ref is the required commit. The only catalog addition is the non-asset content id `kilix-find`.

VERDICT: ship
