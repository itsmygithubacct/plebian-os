# Seat B review: kilix-content pin c990180

This session did not author the carrier, the generator, or the determinations. The notes under `/tmp/carrier-c990180/seats` were not used as evidence. The previously reviewed carrier is `/tmp/plebian-os-pin/releases/0.2.3-model-compliance`. The candidate carrier is `/tmp/carrier-c990180`. The content repository is `/home/pleb/storage/research/plebian-os/023-rc1-takeover-20261103/kilix/third_party/kilix-content`. Old commit `00fe843d0ed22d8c237d616696276042a01b3232`. New commit `c9901809375e16f32530f39b0c8a6774a42e4895`.

## 1. CARRIER.json hash and content fields

`sha256sum /tmp/carrier-c990180/CARRIER.json` printed:

`c578757b715a87b8f366fabd0db268c0122d153cef1d26a8ba1f849b4a819726  /tmp/carrier-c990180/CARRIER.json`

Read from that JSON:

- `interface_content_ref`: `c9901809375e16f32530f39b0c8a6774a42e4895`
- `interface_content_schema_sha256`: `a884f259da5275016744f0a4ff08d970084404cc01ebf2e261692b0522162b20`

## 2. DEFAULT-MODELS.json sha256 field

The `sha256` field in `/tmp/carrier-c990180/DEFAULT-MODELS.json` is `e00614bf726154d09668820c061cbbcb402239a445bde666b0568d36f01528a6`.

## 3. Carrier tree byte compare

Every file in the two carrier directories was compared except `CARRIER.json`, `CARRIER.env`, `BINDINGS.sha256`, `ACCEPTANCE.json`, `SHA256SUMS`, and everything under `seats/`. Both trees had 58 files in that set. None existed on only one side. All 58 common files were byte-identical. Differed: 0.

## 4. CARRIER.env

`diff -u` showed one changed line. Parsing both files found 93 keys on each side and one differing key: `interface_content_ref`, from `00fe843d0ed22d8c237d616696276042a01b3232` to `c9901809375e16f32530f39b0c8a6774a42e4895`. No other env difference.

## 5. CARRIER.json documents

A structural compare found two value changes and no added or removed keys:

- `bindings_sha256`: `234da3a6c6eec207c69ab6d514716100541b9d9c9e6d65c672c0740627e5255d` to `e617cdbae472903c7a42379631970d272e01884db0856c343d34ae0558b5d6f5`
- `interface_content_ref`: `00fe843d0ed22d8c237d616696276042a01b3232` to `c9901809375e16f32530f39b0c8a6774a42e4895`

`interface_content_ref` is `c9901809375e16f32530f39b0c8a6774a42e4895`. `interface_content_schema_sha256` is unchanged at `a884f259da5275016744f0a4ff08d970084404cc01ebf2e261692b0522162b20` on both documents.

## 6. Catalog assets and schema

`git diff --name-status` between the two commits lists `src/kilix_content/catalog/plebian.json` and `src/kilix_content/receipt.py`. `git diff --exit-code` on `contracts/kilix.content.asset-v3.schema.json` exited 0. `git show` of that schema at both commits is 7713 bytes and byte-identical. Its sha256 is `a884f259da5275016744f0a4ff08d970084404cc01ebf2e261692b0522162b20`, the same value carried in `CARRIER.json`.

`git show` of `src/kilix_content/catalog/plebian.json`:

- `schema_version` stayed 4. `packages` are identical.
- `assets` stayed 39 records, in the same order, with the same id set. The asset lists compare equal. Changed asset objects: none.
- `content` went from 53 entries to 54. No existing content object changed, and no content id was removed. Existing ids keep their order. The only addition is `kilix-find`, inserted at index 45, between `kilix-tmux-manager` and `kilix-graphs`. Its `kind` is `app`. It is not an asset record.

Carried model artifact ids all resolve to identical catalog asset objects at both commits: `kilix-diarization-cpu`, `lfm2-kilix-commands`, `vosk-model-en-us-0.22-lgraph`, `vosk-model-small-en-us-0.15`, `vibevoice-asr-bitnet`, `faster-whisper-small-en`, and `whistle`.

`receipt.py` is outside the catalog and schema compare. Its only change is `_CATALOG_SHA256`, from `8c6285f33ff3e420c1949b86f956598eec921bdf993ac7cb2d50bc6d1ed38c53` to `1e9c95eb5d14eef39ce61e613e02629b60f7f34ecfd54e71306495bd5bded178`. Those pins match the sha256 of the catalog blob at the old and new commits. `_ASSET_V3_SCHEMA_SHA256` in that file is unchanged.

Added content id: `kilix-find`.

## Result

Model files in the compared carrier set did not differ. Asset records, the asset id set, and the schema file did not differ. The content ref is the required commit. Every check above passed.

VERDICT: ship
