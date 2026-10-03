# Independent seat 1 — RC5 Content-only carrier rebinding

Carrier-review verdict: **ACCEPT**, limited to the freshly inspected carrier
payload and its producing interfaces below. This is a new independent review;
the prior RC5 seat approval is not an approval of this new Content identity.
It does not accept a release artifact, provider readiness, performance, or a
release tag.

I did not author the Content change, carrier generator, owner determinations,
or provisional carrier under review. I independently inspected immutable Git
inputs, compared the carrier payload, regenerated it, and executed the checks
reported here. I did not communicate with the other reviewer.

## Exact reviewed inputs

| Input | Identity |
| --- | --- |
| OS source snapshot | `895328ad82ea4636d6afd8e6f67cdc37307cfe9b` |
| Working release environment SHA-256 | `48c1d1d837747710416628622373591ba850c986d75bdf03fe2685f1b8d23a75` |
| Working requirements SHA-256 | `42d1e7830781ef343868de2074c525cdecc2da39305cf8754c409305e36fbef9` |
| Carrier SHA-256 | `d81951166a4983757499cc21c09f44396e1fc13c9f97bba6816e6328b45c140d` |
| Bindings SHA-256 | `65c0680587fa4980502334124e4fef3c11fb6dd23ec028d9795ba0cb570c3028` |
| Content | `b7833f3f2986b1c5423898a2130bf345f04f568b` |
| Licence | `ca8a0f479893ab9c8cd6cadc2716c474aaad2820` |
| Final host checked for its Content gitlink and carried-model routes | `65edc6422e50797f248cb0bc3926eed0b87af31c` |
| Voice | `a12be47e289ca03fccd46840276add1833df5760` |
| Content asset schema SHA-256 | `07cb268fb8aa0c6131d6c230af3f7ede094270a1214efd3ae5deb407d6a8e870` |
| New complete catalog SHA-256 | `d1a80a9c027bc406fe23d447e0e56a311d276e597b2f80d256ee417b51ebf778` |

The environment and requirements are explicitly working integration inputs,
not a claim that the OS snapshot already commits the new selection. Both name
Content `b7833f3f`; their carrier and acceptance digest lines still name the
old carrier pending the new genuine seat records. The provisional carrier has
no acceptance receipt and no seat directory.

## Fresh comparison and binding evidence

Content `b7833f3f` is exactly `247d3caf` plus four changed files. Its only
semantic catalog change is the `kilix-tui-utils` package source revision,
`d910110abf485c0e3e823989e320d19a63e1a901` to
`15c31b69e648789737c1d7f3574db200fe76848d`. The complete catalog trust digest
and two existing test expectations move with it. All 32 model assets, content
entries, schema version, member digests, upstream sources, sizes and licence
bindings are unchanged. Independent calculation of the catalog hash agrees
with the receipt module's new trust pin. The guarded upstream-record
generator's read-only `--check` passes.

All 133 vendored Licence source files match the authoritative `ca8a0f4` tree
byte for byte, including all 30 determination records and 80 stored texts.
The host's exact immutable gitlink is `b7833f3f`; the advertised model objects
it serves match this carrier's four artifact records.

I compared the original carrier backup with the immutable OS snapshot above:
every backed-up file matches that tree. I then compared the provisional
carrier with those actual bytes. All 33 model, licence-text, determination,
notice and delivery files are unchanged. In `CARRIER.json` only
`interface_content_ref` and the resulting `bindings_sha256` change. The
projected environment and checksum listings change accordingly.

The six actual owner determination/ruling files remain byte-identical. Their
Apache-2.0 Vosk, MIT plus Alibaba decoder exception for VibeVoice, and MIT
Whisper determinations, accepted evidence limitations, advisories and
VibeVoice runnable-status amendment are faithfully retained. This review
verifies the conveyance and binding of those determinations; it makes no new
legal determination or model-consent decision.

## Independent execution

I used an immutable OS source archive with copies of the exact working
integration manifests and the provisional carrier. Execution used a minimal
environment, private HOME/XDG/TMP roots and explicit selected source-checkout
overrides. No live session or receipt-store values were inherited. The source
copy was temporary; retained logs are outside the carrier under review run
identifier `rebind-seat1-evidence`.

| Fresh check | Result |
| --- | --- |
| Upstream-record generator `--check` | Pass |
| Carrier generator `--check` using the six actual determinations | Pass; all 37 provisional files reproduced byte for byte |
| `BINDINGS.sha256` and `SHA256SUMS` verification | Both pass |
| Applicable pre-seat carrier tests, repeated at final host `65edc642` | 7 tests pass; no skips |
| Final host Qwen preparation route suite | 9 tests pass; no skips |
| Direct artifact comparison against exact Content `b7833f3f` | Pass for all four carried models |
| Exact provisional guard with the new carrier digest and no receipt | Expected refusal at missing `ACCEPTANCE.json` |

The seven carrier tests cover regeneration, environment projection, authoritative
licence records, actual host-served artifacts, advertised-model coverage,
truthful first-use delivery and no-carrier refusal. The delivery checks cover
Content, Voice, host and the host-pinned Bonsai route and verify the
provisioner's no-weight setting. These are source and fixture checks.

Commands included immutable `git --no-replace-objects archive/show` reads,
`python3 -S -B tools/generate_upstream_records.py --check`, the carrier
generator with exact `--content-repo`, `--license-repo`, six real
`--determination` inputs and `--check`, and
`sha256sum --strict --quiet -c` for both listings. The seven named unittest
methods and the direct comparison/refusal runner are retained with their
actual exit results in the review evidence. The independent final host route
command was `python3 -S -B -m unittest discover -s tests -p
test_qwen_provider_route.py -v` with the exact Qwen provider source override.
No fictional seats or acceptance
receipts were created or used.

## Limits and disposition

This pre-seat review does not claim a passing positive acceptance guard,
two-seat receipt checks, the complete planted-defect suite, or final
requirements/digest consistency. The assembler must bind the two genuine new
independent records, update both manifest and requirements digest pins, and
rerun all carrier acceptance checks on the final integrated tree. The old
receipt and old seat decisions cannot supply that acceptance.

I found and reported a host integration regression at initial host
`d7c3a69d74c08b1bd49df5c849c480e311c41088`: Qwen provider preparation still
expected Content `247d3caf` while the host gitlink served `b7833f3f`, so its
actual authority check would refuse preparation. The final host
`65edc6422e50797f248cb0bc3926eed0b87af31c` corrects that constant and adds a
regression exercising the actual Content checkout rather than a mocked
reference derived from the constant. I independently inspected the concrete
fix and ran all nine Qwen route tests successfully, including the actual
checkout guard, with no skips. Model identity, receipt checks and provider
runtime semantics are unchanged. The issue is resolved in the final source
selection reviewed here.

The final host also selects engine
`07b2932f1e3f04b3505e585f6ee46c74299d9e1f`; its diff from the already selected
`79f4272` consists solely of two import-order corrections. I reran the seven
applicable carrier tests and the exact-source artifact and pre-seat refusal
checks against the final host and the working manifest digest recorded above;
all passed. The carrier payload remains exactly `d8195116`.

My first independent nine-test route run used a private data directory outside
its private storage root, so the help test correctly refused that invalid
harness configuration. I corrected the private root hierarchy and reran all
nine tests successfully; the original failure log is retained. No production
root or source was changed to resolve that harness error. These targeted
results do not claim a completed full host/desktop suite or actual provider
readiness. Qwen remains outside this carrier's four advertised speech models.

F101/F104 runtime, quality and artifact qualification remain open; the strict
H1 EnCodec capacity failure is not superseded. Source merging does not close
those gates or authorize a release tag. I performed no model acquisition,
consent/receipt change, inference, installation, service operation, benchmark,
VM operation, artifact build, push or publication. Unselected EnCodec
dependency and scheduling experiments are not part of this acceptance.

VERDICT: ship with known issues
