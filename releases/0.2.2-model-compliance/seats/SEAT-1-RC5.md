# Independent seat 1 — RC5 model compliance carrier

Carrier-review verdict: **ACCEPT**, scoped to the carrier payload and selected
producing interfaces below. No carrier defect was found in this snapshot.
The actual pre-seat release guard correctly refuses advertisement until the
real independent records are bound into an acceptance receipt. This record
does not accept a release artifact or authorize publication.

Reviewed OS snapshot: `18717da145fc435110572f0abeae7a46cdcfe50f`.

I did not author this carrier, its determinations, generator, validator, or
selected implementation. I independently inspected and exercised this RC5
snapshot; RC4 acceptance was not substituted for current evidence. I did not
communicate with the other reviewer.

## Exact inputs

| Input | Exact identity |
| --- | --- |
| Carrier SHA-256 | `82e807a96225ea21910fdb88747924c182959c62afee0bd81aae6741149c6c4c` |
| Bindings SHA-256 | `84463e19b9ee1203515f68868410696aae136a175ae55b184b1e5427b1cfd4b0` |
| Content | `247d3caf1a05370b848ba0c558c6fb3bef04066f` |
| Licence | `ca8a0f479893ab9c8cd6cadc2716c474aaad2820` |
| Selected host | `9ff20e76ec61bb15f85f783e3258f8d6c92534d4` |
| Voice | `a12be47e289ca03fccd46840276add1833df5760` |
| Content asset schema SHA-256 | `07cb268fb8aa0c6131d6c230af3f7ede094270a1214efd3ae5deb407d6a8e870` |
| Vosk wheel SHA-256 | `25e025093c4399d7278f543568ed8cc5460ac3a4bf48c23673ace1e25d26619f` |
| Dictation archive SHA-256 | `30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498` |

I read immutable Git archives of the exact OS, Content and Licence commits.
The selected host serves the exact Content gitlink above. Content's vendored
Licence pin names the exact selected Licence commit; all 30 determination
records and 80 stored texts match its original tree byte for byte. Both release
environment and requirements pin the selected interfaces and actual carrier
digest. Their receipt pins are deliberately zero at this pre-seat snapshot;
`ACCEPTANCE.json` and reviewer records were absent.

## Authenticity, obligations and delivery

I compared all six vendored owner records against their original research
records: the two Vosk determinations, the VibeVoice determination and its
J1/J2 ruling and C2 amendment, and the Whisper determination. Every comparison
was byte-identical. Original SHA-256 values were:

| Original record | SHA-256 |
| --- | --- |
| small-en-us determination | `b6a44eca20a27c550b7fe1cf8e83e384f5ead0c2086130d24dd7684c1a536263` |
| lgraph-en-us determination | `109fc3ad04b0bd7d76c00e8987a7bdbdc81e7dac389b4c3c46f7eea8b3ecdecf` |
| VibeVoice determination | `889658d7317c30f3fc8cdd1780f961feaeb9017573dccdfc552185967228bd33` |
| VibeVoice J1/J2 ruling | `3618c282d871e8333b53aec18561658fb2a9d94b91dd9861358c901cbff6dcf9` |
| VibeVoice C2 amendment | `8723530b4c230e08627dbd2a7dd94ad8e4b25c25cd9dfa40f265832fb6d4b3d6` |
| Whisper determination | `48c5bd4c2e23f78e538dd1608fbd27c429b3e5c4b785b8284e63ce989472d6ba` |

Supplying those originals and the exact producing Git trees to the snapshot's
generator reproduced all 37 pre-seat carrier files byte for byte. Both
`BINDINGS.sha256` and `SHA256SUMS` verified, and the carrier binds the actual
bindings digest. The four advertised models are covered in the provisioner's
order, with exact asset objects, upstream sources, member manifests, licence
records, text digests, notices and delivery statements.

The carrier preserves the owner's Apache-2.0 determinations for both Vosk
models, MIT plus the Alibaba Apache-2.0 decoder exception for VibeVoice, and
MIT with both OpenAI and SYSTRAN identified for Whisper. VibeVoice's later C2
amendment authorizes runnable status; the older runtime note is explicitly
superseded. The owner's accepted evidence gaps and advisory rulings remain
visible and unchanged. This review verifies their faithful conveyance; it does
not independently resolve those legal unknowns.

Provisioning fixes `PROVISION_VOICE_WEIGHTS=0`. The pinned Content, Voice,
host installer and Bonsai route checks pass: first-use acquisition requires
covering consent, verifies declared bytes, and installs atomically. Whisper's
speech command delegates acquisition to the model catalog. DELIVERY states
that delegation accurately. The no-weights census tests pass. These are source
and fixture checks; no actual image or live model installation was examined.

The RC5 Licence change accepts explicit `yes` or `y` while retaining legacy
exact-line consent. It preserves record, binding-text and capture metadata.
In-memory independent controls exercised both affirmative inputs and five
negative inputs for every carried record, and refused changed record and
manifest identities: 40 controls passed. No receipt was stored by those controls.
The complete Licence tests and original advisory-source verifier also passed.

## Independent qualification

All execution used a minimal environment with private HOME, XDG and temporary
roots, explicit selected repository overrides, and no inherited session values.
Logs are retained outside the carrier under review run identifier
`carrier-seat-1-18717da`.

| Fresh execution | Result |
| --- | --- |
| Exact pre-seat carrier suite | 15 tests; 10 failure blocks and 21 error blocks from missing acceptance/seats |
| Private acceptance-copy carrier suite | 15 tests, pass |
| Private acceptance-copy complete OS suite | 910 tests, pass with 4 skips |
| OS socket-shape check with short temporary path | 1 test, pass; resolves the temporary-path skip above |
| Exact Licence `make test` | 198 tests, pass with 8 skips |
| Licence original advisory-source verification | Pass |
| Exact Content `make test` in detached private Git clone | 314 tests; one AF_UNIX path-length error |
| Content AF_UNIX check with short temporary path | 1 test, pass; resolves that error |
| Independent guard probes | 12 expected outcomes, pass |
| Independent authority controls | 40 expected outcomes, pass |
| Validator comparison weakenings | 2/2 detected |

The private acceptance copy added explicitly fictional reviewer records and a
generated receipt solely to reach positive and later refusal branches. Compared
with the exact OS archive, only these three added files, `SHA256SUMS`, and the
two receipt-pin lines differ. These fictional inputs are not acceptance records
and must never enter the real carrier.

My own guard probes separately established: exact pre-seat refusal; silent
positive acceptance in the private control; byte-exact no-carrier refusal;
wrong receipt digest; altered seat; a repinned one-seat receipt; a repinned
receipt naming a foreign carrier; altered artifact bytes despite a refreshed
listing; a hermetic matching host; a host whose content differs only after
39 matching hexadecimal digits; mutually moved carrier/release content pins
against the actual host; and an unreadable full host ref. Every refusal
occurred at its intended check and retained the existing final refusal line.

I independently weakened the validator in memory by removing the full content
comparison and by comparing only seven hexadecimal digits. Both incorrectly
accepted the crafted foreign gitlink; the expected-refusal assertion detected
both. No validator file was edited. The carrier suite also executes its complete
planted-defect battery and distinguishes fully repinned evidence forgeries
through source comparisons and qualification. Shell validation alone does not
establish authenticity after an operator repins the evidence chain.

Commands included immutable `git archive` reads, generator invocation with
each original `--determination`, `sha256sum --strict --quiet -c` for both
listings, `python3 -B -m unittest discover -s tests -v`, Content `make test`,
Licence `make test UV=/usr/local/bin/uv`, and
`python3 -B tools/verify_note_sources.py --packets <original-packets>`.

## Limits and disposition

The initial Content archive run had two Git-context failures and an AF_UNIX
path-length error. Repeating against an exact detached private clone removed
both Git failures; the short-path targeted rerun passed the remaining socket
check. The private OS run's other three skips remain unqualified: released
0.2.1 history, the released native inspector, and a sibling Pleb identity
comparison. Licence's eight skips concern archive Git/commit observability and
two live-store sentinel checks. No skip is counted as a passing qualification.

I performed no real model acquisition, user consent, receipt-store update,
inference, installation, live-store access, installed-session launch, artifact
build, benchmark, publication, push, restart or reboot. The temporary fixture
receipts and mocked operations are test evidence only. The builder must bind
the actual independent records, generate the real receipt, update its pins,
and rerun acceptance before claiming that strict advertisement is accepted.

VERDICT: ship with known issues
