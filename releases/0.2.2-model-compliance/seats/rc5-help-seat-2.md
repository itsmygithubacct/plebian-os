# Independent Seat 2 — RC5 Help Search Content rebinding

Carrier rebinding verdict: **ACCEPT**, scoped to the provisional carrier at `/tmp/rc5-help-carrier-provisional-20261003` and the exact sources below. No new carrier defect was found. This accepts the source and carrier rebinding; it does not approve an ISO, live installation, model inference, or final release.

I did not author the carrier, selected implementation, licence records, or owner determinations. I independently read the selected source objects and original research records, ran the checks described here, and produced my own evidence. No peer or historical seat verdict was used as authority.

The reviewed host is `e20b9a9d8e2e86abac9355410d3184e1dcd2926d`. Its actual `third_party/kilix-content` gitlink is exactly `6ccbbeb432a503fee4945c9c3b29314b599fc85d`, matching both working OS manifests and the provisional carrier interface. The licence interface is `ca8a0f479893ab9c8cd6cadc2716c474aaad2820`. The OS source baseline is `d33fbf23e5580e2f3c5f278e8cffe2b3ef1ab7df`; the working release environment also selects Kilix 95 `f5ab3e329acc1a3a69a9ad844c04dec26ef3d43a`.

The exact provisional identities I measured are:

| File | SHA-256 |
| --- | --- |
| CARRIER.json | `9254f293e60dcea2a9c99d19a39d25f17718837adb6984965e5182c983cefeb3` |
| BINDINGS.sha256 | `5380eb34ba9c01ec81b74b1f798144658a4448e163c86fc57de2f2703cc6434b` |
| SHA256SUMS | `cc291392ada427e8addeb6ce12e7dfbd9cc7f5401350957c6123012999fc2175` |

My independent hashing verified all 37 files. `SHA256SUMS` lists exactly the other 36 files; `BINDINGS.sha256` lists exactly 34 payload files, including the environment projection and all six determination/ruling records. Both lists are sorted, complete and free of duplicate paths. No symlink, seat file, or `ACCEPTANCE.json` is present. The canonical carrier JSON binds the actual BINDINGS digest. An independently constructed projection matches every environment key and value, with no additional keys.

Comparing Content `6ccbbeb` with its parent `b7833f3f2986b1c5423898a2130bf345f04f568b`, all 32 asset mappings and all 49 content entries are identical. The single package changes only the TUI-utils source ref from `15c31b69e648789737c1d7f3574db200fe76848d` to `ca12c7c03a87735f1bfcff2509d13c11fa2b7a9f`. The catalog trust root equals the actual new catalog-byte digest `83d83180cfc7418272deb5e82f51deaafd5e237092d47f60dc20e90e87c09e1b`. The asset schema remains `07cb268fb8aa0c6131d6c230af3f7ede094270a1214efd3ae5deb407d6a8e870`.

Every carried artifact is byte-identical to the canonical asset mapping at the selected Content commit. Each of the four licence-record files is byte-identical to its record at the selected Licence commit. Every named licence, component-exception, advisory and attribution text is byte-identical to the selected Licence source and hashes to its named digest. All six determination/ruling files match the original files in the owner's Vosk, VibeVoice and Whisper research directories supplied for this review. Those comparisons use the originals, not another carrier copy.

Relative to the carrier in the immutable OS baseline, all 33 non-index payload files are unchanged. The only carrier JSON changes are its Content interface and derived binding digest. The generator's `--check` returned 0 when given the exact selected Content/Licence Git sources and the six original research files, reproducing all 37 provisional files byte for byte without seats.

The final host also updates its Qwen provider's Content authority to the exact selected Content commit and its TUI installer to the same `ca12c7c` catalog selection. Working manifest differences are limited to host, Kilix 95 and carrier Content selections. Voice, library, model, Licence and native archive/source/Content pins remain unchanged. Native Content remains the separate `d9a1335db520594c6796209b0f9342000a2b34e7` input.

Six relevant repository-owned OS assertions pass with their carrier paths directed to the actual provisional tree: faithful environment projection, exact licence records, host-served artifacts, advertised-model coverage, delivery/receipt-gating source checks, and absent-carrier refusal. Coverage retains all four advertised models in order, with their prescribed runnability. Source probes retain receipt-before-download checks at voice `a12be47e289ca03fccd46840276add1833df5760` and Bonsai `630da3cf64d28b35fb65cafd4e7c8a4ad54b8685`. Provisioning still declares `readonly PROVISION_VOICE_WEIGHTS=0`.

The real release guard, supplied this exact provisional carrier and digest but no acceptance, returns 1 for `ACCEPTANCE.json is missing or not a regular file`, followed by the unchanged F100 refusal. With no carrier directory, it returns 1 with only the byte-exact F100 refusal. I did not manufacture acceptance or seat records to make either control pass.

Content's own `make test` passes all **314 tests** in my private checkout of the exact selected commit. An initial plain-archive run had two failures caused by absent Git metadata; both checks require `git grep`. After populating private Git metadata for the exact commit, the full suite passes. Shared repository sources were not changed.

Known qualification limits remain: the working carrier and receipt SHA pins still name the previous carrier until final generation; the final carrier must include both genuine new reviews, update both manifests, and pass the complete final checks. This provisional tree is correctly not releasable on its own. F101/F104, image qualification and final release acceptance are outside this review. No actual model acquisition, real user licence acceptance, installation, deployment or live-store access was performed.

My reproducible evidence is in `/tmp/rc5-help-seat2-evidence/`: `audit.py`, `audit.log`, `no-seat-tests.py`, `no-seat-tests.log`, `source-pins.log`, both working manifest snapshots, and the initial/final Content test logs.

VERDICT: ship with known issues
