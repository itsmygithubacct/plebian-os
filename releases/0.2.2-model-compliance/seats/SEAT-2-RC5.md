# Independent seat 2 — RC5 model compliance carrier

Carrier review verdict: **ACCEPT**, with the limitations recorded below.

Reviewed snapshot: `18717da145fc435110572f0abeae7a46cdcfe50f`, extracted with
`git --no-replace-objects archive` before writing this review. I did not author
this carrier, its determinations, or the selected implementation. This is a new
independent assessment; RC4 acceptance is not evidence of RC5 acceptance. I did
not consult the other RC5 reviewer or their findings.

The accepted scope is the carrier's source records, determinations, delivery
claims, exact input bindings, and offline acceptance/refusal controls. The real
snapshot has no `ACCEPTANCE.json` and a zero receipt pin. It correctly refuses
release-mode advertising until a new receipt binds both actual RC5 reviews.
This review does not establish completed image, installation, or runtime
qualification.

## Exact selection and integrity

| Input | Independently verified value |
| --- | --- |
| OS snapshot | `18717da145fc435110572f0abeae7a46cdcfe50f` |
| Carrier SHA-256 | `82e807a96225ea21910fdb88747924c182959c62afee0bd81aae6741149c6c4c` |
| Carrier bindings SHA-256 | `84463e19b9ee1203515f68868410696aae136a175ae55b184b1e5427b1cfd4b0` |
| Kilix host | `9ff20e76ec61bb15f85f783e3258f8d6c92534d4` |
| Host content gitlink and carrier Content | `247d3caf1a05370b848ba0c558c6fb3bef04066f` |
| Licence interface and Content vendored authority | `ca8a0f479893ab9c8cd6cadc2716c474aaad2820` |
| Content asset schema SHA-256 | `07cb268fb8aa0c6131d6c230af3f7ede094270a1214efd3ae5deb407d6a8e870` |
| Voice | `a12be47e289ca03fccd46840276add1833df5760` |
| Host-selected Bonsai | `46da3ffdb1e2eb6d7068435424f1d13e3d00b326` |

The generator, run against the selected Git objects and all six original owner
determination files, reproduces every pre-seat carrier byte. I separately
verified 34 distinct `BINDINGS.sha256` entries and 36 distinct `SHA256SUMS`
entries, their complete file coverage, regular file types, canonical artifact
JSON, and the bindings digest in `CARRIER.json`. All 139 files in Content's
vendored Licence tree match the selected Licence tree byte for byte. Both
release manifests carry the same Content, Licence, carrier, and zero receipt
pins. The native EnCodec content pin is a separate input.

All four advertised speech models are covered in the provisioner's order.
Their artifact records match what the exact selected host serves. Their
licence records and 11 licence/advisory/attribution texts match the selected
authority. The archive identities remain small-en-us `30f26242...`, 41,205,931
bytes, and lgraph-en-us `d9838b4a...`, 130,557,655 bytes. VibeVoice and Whisper
retain their pinned upstream revisions and complete member manifests, with
download sizes 1,705,771,590 and 486,100,128 bytes respectively. All four are
advertised as runnable; the delivery records agree with the selected catalog.

## Determinations and consent boundary

Each of the six vendored determination/ruling files is byte-identical to its
original under `f104-vosk-licence-evidence-2026-09-14`,
`licence-evidence-vibevoice-asr-bitnet-2026-09-15`, or
`licence-evidence-whisper-small-en-2026-09-29` in the research tree.

Small-en-us and lgraph-en-us retain the owner's Apache-2.0 determinations and
accepted provenance gaps. VibeVoice carries Microsoft's MIT licence, Alibaba
Cloud's Apache-2.0 decoder-lineage exception, both licensors and texts, the
research-use advisory, J1/J2, and the C2 amendment permitting runnable delivery.
Whisper carries the owner's MIT determination, both OpenAI and SYSTRAN, and
the accepted model-card caution. These owner rulings remain the legal basis;
this review verifies their faithful carriage and does not replace them.

The selected Licence change permits actual `yes`/`y` consent while preserving
the legacy agreement phrase and the record, binding-text, manifest and capture
identities. Its documentation requires the affected models and complete terms
to be presented and separate receipts to be emitted. I reviewed the authority
diff and ran its own tests. No user's agreement or receipt was created by this
review. The build acceptance schema remains distinct from a user's receipt.

The provisioning source fixes `PROVISION_VOICE_WEIGHTS=0`. The exact Voice,
host voice installer, and host-selected Bonsai source checks preserve the
receipt gates before acquisition. Whisper delegates installation to the model
catalog. The offline delivery and voice-contract tests pass.

## Executed controls

Evidence, execution scripts, failed attempts, and logs are outside the carrier:
`/home/pleb/research/gpu_terminal/0.2.2-rc5/carrier-seat-2-18717da/`.

| Check | Result |
| --- | --- |
| Generator `--check`, checksum manifests, original determinations | Pass; exact pre-seat bytes |
| Actual pre-seat carrier suite | 15 tests; 10 failure reports and 21 error reports caused by absent acceptance/seats |
| Private synthetic-receipt carrier suite | 15/15 pass, including AC-1 through AC-12 and full-SHA host controls |
| Private synthetic-receipt full OS suite | 910 tests, OK; 4 explicit skips |
| Short-TMPDIR recheck of the skipped socket control | 1/1 pass; 3 other OS skips remain |
| Voice release contract | 26/26 pass |
| F120 authority profiles | 6/6 pass |
| Bash parsing, Python compilation, ShellCheck warning gate | Pass |
| Content `make check`, exact detached selected clone | 314 tests, OK; pin-generation check passes |
| Licence `make check OFFLINE=1 PACKETS=/home/pleb/research/gpu_terminal`, exact detached selected clone | 198 tests, OK, 2 explicit live-store sentinel skips; packaging, wheel import and packet witnesses pass |

The synthetic controls are fictional test fixtures and were never added to
the real carrier. Their source differs from the snapshot only in two fictional
seat files, `ACCEPTANCE.json`, `SHA256SUMS`, and the two receipt-pin lines.
`synthetic-differences.log` records that comparison. They establish validator
behavior, not genuine release approval. The commands used are preserved in
`run-review.py`, `verify-more.py`, and the adjacent suite logs.

Six additional direct guard probes independently passed their intended checks:
matching synthetic carrier acceptance; real pre-seat missing-receipt refusal;
empty-carrier refusal with the exact refusal line; changed NOTICE refusal even
after recomputing `SHA256SUMS`; one remaining seat refusal even with a newly
pinned receipt; and a host whose content differs only in its final hexadecimal
digit. The last two demonstrate that a rewritten checksum and a matching short
SHA prefix do not establish the required independent reviews or exact host
binding. Diagnostics are in `independent-guard-probes.log`.

The first Content archive run failed at two Git-metadata tests and one
overlong AF_UNIX path. The final detached clone contains byte-identical selected
source and uses short temporary paths; its unchanged `make check` passes.
The first Licence archive run passed with eight skips; a detached clone reduced
those to the two documented live-store sentinel checks. All initial logs are
retained.

## Limitations and remaining gates

There is no blocking carrier integrity finding. Three OS archive checks remain
unexercised: the historical `v0.2.1` provisioner, released native inspector, and
sibling Pleb desktop identity. The two Licence sentinel checks require a
dedicated live-store overlay and were not run.

The release notes still record Whisper runtime concerns involving model files
inside cached wheels, cache hardlinks, and setup failures being reported as
declines. This review does not clear those concerns. It also does not clear the
owner's accepted upstream evidence gaps, establish real model inference or
runtime fit, or grade hosted engine CI. No model weights were acquired, installed
or exercised, and no live setup, restart, reboot, publication, or tag change
occurred.

Release must generate acceptance from the actual two RC5 reviews, update both
receipt pins, and run the acceptance checks on that real final carrier. Hosted
CI, exact release artifact and installed-guest gates remain separate.

VERDICT: ship with known issues
