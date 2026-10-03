# Independent Seat 1 — RC5 Help Search Content rebinding

Carrier-review verdict: **ACCEPT**, limited to the provisional carrier and exact producing interfaces below. Reviewed on 2026-10-03. This is a fresh independent review of the new Content identity. It does not accept an ISO, upgrade artifact, provider readiness, performance result or release tag.

I did not author the Content change, host fix, carrier generator, provisional carrier or owner determinations. I independently inspected immutable Git objects, compared original research records, reproduced the provisional carrier and executed the checks reported here. I did not read the other current reviewer's output or communicate with that reviewer. Historical seat conclusions were not used as acceptance evidence. My earlier read-only integration audit reported the Qwen authority mismatch; the assembler authored its fix.

## Exact reviewed inputs

| Input | Identity |
| --- | --- |
| OS source base | `d33fbf23e5580e2f3c5f278e8cffe2b3ef1ab7df` |
| Provisional carrier directory | `/tmp/rc5-help-carrier-provisional-20261003` |
| CARRIER.json SHA-256 | `9254f293e60dcea2a9c99d19a39d25f17718837adb6984965e5182c983cefeb3` |
| BINDINGS.sha256 SHA-256 | `5380eb34ba9c01ec81b74b1f798144658a4448e163c86fc57de2f2703cc6434b` |
| Final host | `e20b9a9d8e2e86abac9355410d3184e1dcd2926d` |
| Content | `6ccbbeb432a503fee4945c9c3b29314b599fc85d` |
| Previous Content | `b7833f3f2986b1c5423898a2130bf345f04f568b` |
| Licence | `ca8a0f479893ab9c8cd6cadc2716c474aaad2820` |
| Voice | `a12be47e289ca03fccd46840276add1833df5760` |
| Selected TUI package | `ca12c7c03a87735f1bfcff2509d13c11fa2b7a9f` |
| Complete catalog SHA-256 | `83d83180cfc7418272deb5e82f51deaafd5e237092d47f60dc20e90e87c09e1b` |
| Asset/v3 schema SHA-256 | `07cb268fb8aa0c6131d6c230af3f7ede094270a1214efd3ae5deb407d6a8e870` |
| Private review environment SHA-256 | `7453a84c1e27ee1ba2d286d194d6156a622462195ab8fe66efcd422325c7bb95` |
| Private review requirements SHA-256 | `bb2c6d9f00603a3045918e988d00b3372dd913846edcc114b69965b12815afd7` |

I archived the immutable OS source base, copied the working integration manifests and replaced its carrier with the exact provisional directory. In that private review copy only, I set the carrier pin to the provisional digest and the acceptance pin to 64 zeroes. The provisional carrier has neither `ACCEPTANCE.json` nor a seats directory; no fictional receipt or seat was constructed. These private manifest digests identify the actual test inputs, not a final release transaction. The working manifests still require their genuine receipt/digest updates and coordinated desktop selection.

## Independent source and payload verification

The final host's immutable Content gitlink is exactly the reviewed Content commit. Its TUI installer selects `ca12c7c03a87735f1bfcff2509d13c11fa2b7a9f`, matching the catalog. The Content diff from its previous selection changes five files: CHANGELOG, one package ref, the complete catalog trust digest and two existing test expectations. The catalog's only semantic change is `/packages/0/source/ref`, from `15c31b69e648789737c1d7f3574db200fe76848d` to the selected TUI package. All **32 assets**, member identities, download sources, sizes, licence bindings and schema bytes are unchanged. Independent hashing agrees with production receipt.py's updated catalog trust pin.

All **139 vendored Licence Git members** match the authoritative Licence commit, including their modes and blob identities. Every provisional artifact record agrees with the actual host-served catalog; the dictation archive digest agrees with the selected release pin. All six owner determination/ruling files match both the immutable OS source base and their original research files byte for byte:

| File | SHA-256 |
| --- | --- |
| determinations/lgraph-en-us/OWNER-DETERMINATION-lgraph-en-us.md | `109fc3ad04b0bd7d76c00e8987a7bdbdc81e7dac389b4c3c46f7eea8b3ecdecf` |
| determinations/small-en-us/OWNER-DETERMINATION-small-en-us.md | `b6a44eca20a27c550b7fe1cf8e83e384f5ead0c2086130d24dd7684c1a536263` |
| determinations/vibevoice-asr-bitnet/OWNER-DETERMINATION-vibevoice-asr-bitnet.md | `889658d7317c30f3fc8cdd1780f961feaeb9017573dccdfc552185967228bd33` |
| determinations/vibevoice-asr-bitnet/OWNER-RULING-C2-AMENDMENT-2026-09-29.md | `8723530b4c230e08627dbd2a7dd94ad8e4b25c25cd9dfa40f265832fb6d4b3d6` |
| determinations/vibevoice-asr-bitnet/OWNER-RULING-J1-J2-2026-09-25.md | `3618c282d871e8333b53aec18561658fb2a9d94b91dd9861358c901cbff6dcf9` |
| determinations/whisper-small-en/OWNER-DETERMINATION-whisper-small-en.md | `48c5bd4c2e23f78e538dd1608fbd27c429b3e5c4b785b8284e63ce989472d6ba` |

Original sources are the three research directories under `~/research/gpu_terminal`: `f104-vosk-licence-evidence-2026-09-14`, `licence-evidence-vibevoice-asr-bitnet-2026-09-15`, and `licence-evidence-whisper-small-en-2026-09-29`. Their exact paths and hashes are retained in `integrity-summary.json`.

The existing Apache-2.0 Vosk, MIT Whisper, and Microsoft MIT plus Alibaba decoder Apache-2.0 VibeVoice determinations, advisory classifications, accepted evidence gaps and VibeVoice runnable-status amendment remain faithfully conveyed. Both VibeVoice licensors and licence texts are retained. This review checks their unchanged conveyance and binding; it makes no new licence determination or consent decision.

The provisional tree contains **37 regular files**, with no symbolic links or other special members. Both checksum populations are exact: **34 unique binding entries** and **36 unique SHA256SUMS entries**, every digest matching its file. CARRIER.json binds the independently computed binding digest. Comparing actual bytes to the immutable previous carrier finds **33 unchanged files**. Only CARRIER.env, BINDINGS.sha256, CARRIER.json and SHA256SUMS differ. CARRIER.json changes only `interface_content_ref` and the resulting `bindings_sha256`.

## Fresh execution and retained evidence

Execution used a minimal environment, private HOME/XDG/runtime/tmp/storage roots, bytecode disabled, Git replacement objects disabled and explicit source-checkout overrides. OS tests ran from the archived source; Qwen route tests ran from the clean exact final host with an archived exact provider source `e255d4af90eb3593c880e10894f2a128aa28eec7`.

| Check | Result |
| --- | --- |
| Carrier generator `--check`, with six original research determination inputs and no seats | Pass; byte-identical provisional output |
| Exact Content upstream-record generator `--check` | Pass |
| Seven applicable no-seat carrier tests | Pass; 7 tests, no skips |
| Direct AC-4 actual artifact and dictation-pin comparison | Pass for all four carried models |
| Exact provisional release guard | Expected refusal at missing ACCEPTANCE.json and required release-mode refusal line |
| Final host Qwen provider route suite | Pass; 9 tests, no skips |

The seven tests cover regeneration, environment projection, authoritative Licence records, actual host-served model records, advertised-model coverage, truthful first-use delivery and no-carrier refusal. Delivery checks inspect Content, Voice, final-host installers and its pinned Bonsai route, including receipt gates and the provisioner's no-weight setting.

An initial seven-test attempt included the full AC-4 unittest. Its positive assertions passed, but its forged-carrier control calls a helper that requires ACCEPTANCE.json; it therefore errored on the intentionally receipt-free provisional carrier. That failure remains in `pre-seat-seven.log`. I then ran the applicable host-served-record test instead and separately executed AC-4's actual artifact/dictation assertions. I did not fabricate acceptance data to make the receipt-dependent control pass. The complete AC-4 mutation control remains required after assembly.

The final host's Qwen `CONTENT_REF` equals its Content gitlink. I independently reran its actual checkout-authority regression and all eight other provider route tests successfully. The mismatch reproduced during my earlier read-only audit at host `04209012` is resolved in the final host. Qwen model identity and consent gates are unchanged and Qwen is outside this carrier's four speech models.

Retained evidence: `/tmp/rc5-help-seat-1-evidence-20261003/`. This contains the private source/input snapshots, `integrity-summary.json`, actual commands and exit statuses in `check-results.json`, and generator, upstream, applicable-seven, direct-asset, guard and Qwen route logs. Those logs record fresh execution by this seat.

## Scope and required final checks

Bind this genuine record with a second fresh independent review, regenerate the final acceptance receipt and checksum listing, update carrier/receipt pins in both release manifests and rerun the complete carrier, voice-contract, release-versioning and required OS closure checks. This pre-seat review does not claim positive acceptance-guard success, complete receipt-dependent mutation qualification or final manifest consistency.

F101/F104 runtime/quality qualification, retained capacity failures, hosted/installed integration and final artifact/upgrade acceptance remain open. This carrier rebinding does not supersede those gates or authorize a release tag. I made no repository edits, model acquisition, consent change, inference, installation, service operation, VM operation, artifact build, push or publication. Known owner-recorded licence evidence limitations remain as documented above.

VERDICT: ship with known issues
