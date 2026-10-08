# Seat 1: RC5 main-match carrier review, 2026-10-05
VERDICT: ship

I did not author the reviewed changes, the generator, or the provisional carrier.

This verdict approves the reviewed model-compliance carrier rebind for final assembly. It does not accept the unassembled provisional directory as a release carrier. I reviewed independently, did not consult or coordinate with the other seat, and did not use earlier seat records as approval. All review files, extracted trees, local clones, fixture state and logs were written inside this seat directory. The supplied repositories were read only; no push, remote fetch or external network access occurred.

**Exact inputs**

The component inputs were the following accepted-base and candidate commits. Their identities and the base-to-candidate ancestry were checked with `git rev-parse` and `git merge-base --is-ancestor`; tree extraction commands are retained in `logs/extraction.log`, and full diffs in `logs/<component>-diff.log`.

| Component | Accepted base | Candidate |
| --- | --- | --- |
| Plebian-OS | `bfd82ad25aa3810b03cdaa6a712027b6d659c0b5` | `4588779fbd9f9fbe99ab33ad0727dee2558c47bb` |
| Kilix host | `2e1638e8392f88160b2a6343a8672c32c98fb188` | `798db9c92fdb4b372b985c17ce5a28164e4b9448` |
| Kilix 95 | `14b466a998074d151d2e63dee6b0d8f2763034d0` | `13a501cc37a32342b3047c4ce09741827af2d1a6` |
| Pleb | `4c08e6aff6e8a0c216a5d8c4fc3bca1042d66236` | `4cf84b44ee5fb7c43eff0f288a62829bb959cdb4` |
| Content | `ce6c0c63a852b10c6ca2b2f7ed8087934d75f4d0` | `ad620c1429d825230e1c337a20f8a9682ff060d4` |
| Needle | `7de641763c403f8c54873ef4d044277c946d4445` | `53e881ef7bee42964882d40ad51713f2526b7cea` |
| TUI utils | `8b461045715f176218c57b17ff16ccfd756aace1` | unchanged |
| Licence | `ca8a0f479893ab9c8cd6cadc2716c474aaad2820` | unchanged |
| Amp selection | `92f252b3cf64ad85c252b7e0ab00c6325ea8442f` | `e5ce674e40212b3ca410e430d922926fff770094` |

The OS candidate was reviewed with `../os-candidate-pins.patch` applied only to the extracted copy. The patch SHA-256 is `9c2ffa7ad9be0343a20ff85d41212827b9395b077292b02be54b41133befeff5`. Its three resulting release files match the supplied candidate working tree byte for byte. Carrier and receipt hash pins still name the accepted base, as disclosed in the brief.

The provisional input is `../provisional-carrier`, with `CARRIER.json` SHA-256 `276c8bb766b6b7b3ef8f31d6ddba4376d3ec4fb79686142495a133160a6e5caf`. The comparison carrier is `releases/0.2.2-model-compliance` extracted from OS `bfd82ad25aa3810b03cdaa6a712027b6d659c0b5`. The generator is the candidate's unchanged `build/generate-model-compliance.py`, SHA-256 `aa79df818f82d97f996202a5ec7bb07256989c8e1a9843195591ec964fa40d27`.

The abbreviated integration inputs in the brief resolve to:

| Input | Full commit |
| --- | --- |
| OS desktop merge `c4fbfb5` | `c4fbfb5a3ea6bbe4472b401e6773fea530aeabd2` |
| OS transaction fix `c788a3d` | `c788a3d9709585870ad3cc015b4ef1aad94c47be` |
| OS transaction test `4588779` | `4588779fbd9f9fbe99ab33ad0727dee2558c47bb` |
| Host main `44740f4` | `44740f4cc1e964ed0530026105b07d5afce9730c` |
| Host desktop `784adf9` | `784adf956e4214ddbc5920d0bfe2c4574d26e85c` |
| Host multiplexer pin `bb436d9` | `bb436d92d562db2839aafedfb6a006ec9c57527f` |
| Content main `34ef86a` | `34ef86a57789f5b065f34cf0203bd43001e61396` |
| Needle main `ecf5110` | `ecf5110d2229f25806b88b386d122ca842eaa2f8` |

The six owner determination inputs in `../determinations` match both carriers byte for byte. Their SHA-256 values are recorded in `logs/evidence.log`: `109fc3ad04b0bd7d76c00e8987a7bdbdc81e7dac389b4c3c46f7eea8b3ecdecf`, `b6a44eca20a27c550b7fe1cf8e83e384f5ead0c2086130d24dd7684c1a536263`, `889658d7317c30f3fc8cdd1780f961feaeb9017573dccdfc552185967228bd33`, `48c5bd4c2e23f78e538dd1608fbd27c429b3e5c4b785b8284e63ce989472d6ba`, `3618c282d871e8333b53aec18561658fb2a9d94b91dd9861358c901cbff6dcf9`, and `8723530b4c230e08627dbd2a7dd94ad8e4b25c25cd9dfa40f265832fb6d4b3d6`.

**Selection and Content findings**

`git rev-parse 798db9c92fdb4b372b985c17ce5a28164e4b9448:third_party/kilix-content` equals `ad620c1429d825230e1c337a20f8a9682ff060d4`, exactly the carrier's Content interface. The host's `config/kilix_sdk/qwen_provider.py` `CONTENT_REF` equals that same full commit. Its authority-check test passes against the actual local candidate host and Content checkouts.

The host TUI installer default, every Content entry selecting TUI utils, and both the accepted and candidate Needle TUI gitlinks equal `8b461045715f176218c57b17ff16ccfd756aace1`. Content selects Needle `53e881ef7bee42964882d40ad51713f2526b7cea`. The Needle diff preserves the TUI selection and Help Search work; its added functionality is terminal-transcript replay, with build plumbing, documentation and tests. Host and Needle select the same replay helper, `638b7919d196bb8c5efce51355d42fca73bf24eb`. These are code and log-processing changes, with no changed model record or model-delivery route.

Content's complete diff has exactly four changed files: `CHANGELOG.md`, `src/kilix_content/catalog/plebian.json`, `src/kilix_content/receipt.py`, and `tests/test_consumer_selection.py`. The catalog changes only the Needle and Amp source refs. The changelog preserves the transcript-replay Needle line from main and describes the Amp move; the consumer test updates its typed Amp literal and explanation. All 32 asset mappings and every other catalog field are unchanged. Both asset/v3 schema copies remain byte-identical, SHA-256 `07cb268fb8aa0c6131d6c230af3f7ede094270a1214efd3ae5deb407d6a8e870`. The vendored licence selection is unchanged.

The catalog byte digest moves from `4a9ad875438f7b82ad6dd185298de858c85510e65f802c4ef7dcddc8d8149b75` to `aa7034c9cab85a2c3edf12b0dbd4764138dd4529d068548dfe8cee7d71629dd7`. The new value equals the actual catalog SHA-256 and the production trust-root literal. `tools/generate_upstream_records.py --check` passes.

Amp's move is a strict descendant and changes only `LIVE-FORMAT.md`, `src/encodec_source.c`, and `tests/native_live.c` (`logs/amp-diff.log`). It reads the live header's epoch-start profile, selects that decoder profile, and rejects incompatible markers; tests cover C5 live paths. The build remains `make all ENCODEC=1`. Its installed model loading and admission path remains in place. The move does not change model delivery, introduce weights or alter model licence obligations; no new licence determination is required by this carrier rebind.

Kilix 95's CI `KILIX_COMMIT` is exactly the candidate host `798db9c92fdb4b372b985c17ce5a28164e4b9448`. I checked that binding directly; I did not run its optional full desktop runner.

**Carrier findings**

The only changed common carrier files are `CARRIER.json`, `CARRIER.env`, `BINDINGS.sha256`, and `SHA256SUMS`. JSON changes only `interface_content_ref` and `bindings_sha256`; the environment projection changes only the Content ref. The provisional directory intentionally omits `ACCEPTANCE.json` and the two prior seat files, and adds no files. All 33 other common files are byte-identical, including every `ARTIFACT.json`, licence record, licence text, determination, NOTICE and DELIVERY file.

The preserved four-model set, in order, is `small-en-us`, `lgraph-en-us`, `vibevoice-asr-bitnet`, `whisper-small-en`. Dictation remains `small-en-us`, archive SHA-256 `30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498`. The other archive digest, all four member-manifest digests, download sizes and source selections, speech library digest, voice ref and licence pin are unchanged. The generator, release guard and F100 acceptance test source are also unchanged.

Regeneration from the exact pins and the six unchanged determinations reproduces all 37 provisional files byte for byte, both through existing AC-1 and through the generator's explicit `--check`. `SHA256SUMS` verifies all 36 entries; `BINDINGS.sha256` verifies all 33 entries.

**Commands, results and limitations**

Every suite ran through `sandbox-run.py`. It removes inherited `KILIX*`, `GPU_TERMINAL*`, `KITTY*`, `PLEB*`, `XDG_*`, exported shell functions and Git overrides, then sets HOME, TMPDIR and XDG storage inside `seat1/sandbox`. Only explicit source-repository locators and isolated fixture inputs are added back. Git remote protocols are disabled. The F100 adapter also propagates private HOME/TMPDIR/XDG paths to subprocesses that provide minimal environments. Full argv, paths, results and elapsed times are retained in each log. Source adaptations are confined to the seat's copies or memory; no acceptance receipt or substitute seat approvals were manufactured.

| Command/check | Result | Log |
| --- | --- | --- |
| `python3 sandbox-run.py evidence . python3 evidence.py` | All independent SHA, ancestry, selection, catalog and carrier byte assertions pass | `logs/evidence.log` |
| Generator with `--content-repo`, `--license-repo`, six `--determination` arguments, `--out ../provisional-carrier --check` | exit 0 | `logs/generator-check.log` |
| `sha256sum -c SHA256SUMS`; `sha256sum -c BINDINGS.sha256` in provisional directory | both exit 0 | `logs/checksum-sums.log`, `logs/checksum-bindings.log` |
| `python3 f100-provisional.py` through sandbox runner | 7 existing tests pass: AC-1, AC-2, AC-3, served-record binding, AC-5, AC-8, AC-9; AC-4's exact catalog/dictation `artifact_gaps` assertion also passes | `logs/f100-provisional.log` |
| Focused Content `python3 -m unittest -v` invocation over catalog, consumer, contracts, model-record and weight checks | 108 tests pass, no skips | `logs/content-offline.log` |
| `python3 tools/generate_upstream_records.py --check` | exit 0 | `logs/content-pins.log` |
| Host modules run individually with `python3 -m unittest -v tests.test_<module>`: consumer selection, component pin delivery, content runtime, SDK enumeration, model runtimes | respectively 2, 12, 13, 24, 39 tests pass | corresponding `logs/host-*.log` |
| Host content-model suite | 37 tests; 3 failing subtests in one fixture, 4 loopback skips | `logs/host-content_models.log` |
| Host provider-route suite, exact provider source `e255d4af90eb3593c880e10894f2a128aa28eec7` extracted inside seat | 9 tests; 2 fixture errors; candidate Content authority and launcher tamper checks pass | `logs/host-qwen.log` |
| Existing no-speech-weight census tests, dependency manifest tests, portal transaction tests | 4, 43, 8 tests pass respectively; no remaining skips | `logs/no-speech-weights.log`, `logs/desktop-dependencies.log`, `logs/portal-transactions.log` |

The full Content `make test` invocation ran 314 tests and exited 2 with four failures and 65 errors. The accepted-base invocation under the same sandbox has exactly the same failing/error test identities and counts (`logs/content-suite.log`, `logs/content-base-suite.log`, `logs/baseline-comparison.log`). Of the errors, 64 are socket-creation `EPERM`, and one is an overlength local socket path. Two failures are network-guard controls that cannot observe successful socket calls here; two are Git scans invoked in an archive without `.git`. The Git-dependent record checks pass in the focused run against the local candidate clone. The broad suite is not represented as green.

The host content-model failures explicitly demand fixture paths outside the account's NSS home, incompatible with this seat's required location under that home. Its four skips report unavailable loopback. The two isolated provider-route errors arise because the unchanged private-chain guard rejects `/home`, owned by UID 65534, as a foreign ancestor. The three affected test methods reproduce the same three failures and two errors against the accepted host and Content base (`logs/host-baseline-fixtures.log`). Their test files and relevant delivery installers are byte-identical between base and candidate. These results identify local fixture constraints, not a new delivery or licence regression.

An initial combined host run recorded 136 tests, three failures, nine errors and four skips (`logs/host-focused.log`). Seven additional errors came from initially pointing the provider fixture at a local checkout that lacks `runtime.py`; that checkout is `9b2923d6608a7097e9197ca79f3c764264217a32`, not the selected provider commit. Separate process runs using the exact selected provider archive remove those errors (`logs/provider-fixture-diagnosis.log`). Review-helper mistakes were corrected and retained: `evidence-initial-harness-error.log` records an optional catalog `source` key assumption, `evidence-second-harness-error.log` a wrong determination directory, and `content-offline-initial-command-error.log` an invalid named-test argument to discovery. The initial portal run skipped the sibling Git checkout comparison; adding the exact local Pleb clone resolves that skip (`logs/portal-transactions-initial-skip.log`). The record-link validator also initially treated the illustrative `logs/<component>-diff.log` template as a concrete filename; excluding templates resolves that helper error (`logs/record-validator-initial-error.log`). None of these corrections changes product source or acceptance criteria.

The provisional guard itself exits 1 with `carrier: ACCEPTANCE.json is missing or not a regular file` and the expected release refusal. AC-4's receipt-dependent forgery branch, AC-6, AC-7, AC-10, the full AC-11 defect battery, AC-12 and the extra accepted-carrier gitlink attack controls remain final-assembly checks. Their accepted-carrier controls cannot truthfully pass without both fresh seat records, an acceptance receipt and the final hash pins.

**Acceptance boundary**

Desktop completion—capture, portals, clipboard, notifications and provisioning of capture dependencies—was considered only for effects on this carrier, model delivery and licence obligations. It has separate code review. The reviewed changes introduce no new model, weight population or model licence determination. The focused dependency and transaction checks support the inspected provisioning boundaries; they are not a full desktop qualification.

Final assembly must regenerate the carrier with both fresh independent seat files, pin the actual `CARRIER.json` and `ACCEPTANCE.json` SHA-256 values in both `releases/0.2.2.env` and `releases/0.2.2.requirements`, and pass the full carrier acceptance and defect suite. This seat makes no runtime VM, ISO, F101/F104 or release qualification claim.
