# Independent seat 1 — RC4 carrier content move, VM-only closure

Reviewed commit: `35442a8be862ef375b3a992737b03138bdf1b542`.

I did not author this carrier, its owner determinations, or the code it pins.

This review began at pre-seat `4c1a53c30603115c462f89bfb8a4a3a0d4125823` and concludes on its exact successor above. Both commits were independently archived into `/tmp/rc4-seat1-4c6pk063`; original repositories and refs were read only. No other review seat's findings or evidence were used.

## Findings

**Low — stale release-notes content pin, fixed in the reviewed successor.** At initial `4c1a53c`, `releases/0.2.2-notes.md:304` still listed carrier content `716a672b62ff80b014b586523bfa407d05b89191`, while both release manifests selected `2f5f3d7c28fdfe088ea24573f4c7fceea1f53013`. The independently executed full suite failed `test_notes_closure_table_mirrors_every_pin_in_the_manifest` for that exact disagreement. I preserved that failure, archived successor `35442a8`, and proved the only changed file and bytes are this one table entry. The corrected notes test passes in both successor full-suite runs. See [initial full log](seat-1-logs/initial-preseat-full.log) and [successor identity proof](seat-1-logs/successor-identity.log).

No remaining Critical, High, or Medium finding in the carrier move. The missing acceptance and seat records are intentional pre-seat state: the exact reviewed tree refuses release advertisement. The approval represented by this record permits subsequent generation and validation of the real acceptance receipt; it does not assert that the pre-seat tree itself is accepted already.

## Independent evidence

**Original determinations and regeneration.** I byte-compared all six vendored files against the original paths in `PREPARATION.json`: lgraph, small, the VibeVoice determination and both C2 and J1-J2 rulings, and Whisper. Their independent SHA-256 results match the source records; this checks originals rather than trusting a receipt's assertion. I supplied those ORIGINAL files, in sorted determination-path order, to the archived generator with the exact pinned content and licence object trees. Every one of the 37 generated pre-seat files was byte-identical. Both `releases/0.2.2.env` and `.requirements` pin `CARRIER.json` as `ce3eb0676c0a978c8d6a9f73bdb2e9e96c1bc670d3212d1d5d6f4a8f9e37d46a`. Successor identity comparison proves these same bytes are present in the final reviewed commit. See [authenticity and regeneration](seat-1-logs/authenticity-regeneration.log).

**Exact selection and unchanged inputs.** Independent Git object reads confirm:

| Selection | Full commit |
| --- | --- |
| Selected VM host | `e97e52a98e2babe6220ee0f3d2f5f4e06ff01f66` |
| Host's `third_party/kilix-content` gitlink and carrier interface | `2f5f3d7c28fdfe088ea24573f4c7fceea1f53013` |
| Host's `src` engine gitlink | `84e9f1de2b71d18fcbb0bf080ca6ea40910ac9fd` |
| K95 | `fdc50f8fdcf48ec0290043fdf3473e2922fc1fcf` |
| Voice | `a12be47e289ca03fccd46840276add1833df5760` |
| Licence authority | `993c8ec0df87c677521652b7c3a8ca9797ce2cba` |

Against accepted OS `47f6be4b23f953c19ecab582aab1bf5a9a45d6de` and its content `716a672b62ff80b014b586523bfa407d05b89191`, all 32 complete asset records are identical. The content delta consists of the Needle program pin, its catalog trust-root digest and the changelog. `CARRIER.json` changes only `interface_content_ref` and its derived `bindings_sha256`; all other 33 carrier payload files, including the six determinations, artifact records, licence records, all eleven licence/advisory texts, delivery and notices, remain byte-identical. Previous seats and acceptance were removed for renewed review.

All `KILIX_VOICE_*`, licence and sizer pins are unchanged. Every `PLEBIAN_OS_NATIVE_*` selection is unchanged, including native content `d9a1335db520594c6796209b0f9342000a2b34e7`, source `e0655faaf57cc5f14baf449afe937fcbe87d204b`, archive size 750896 and archive digest `d875539b47e6e6b607853f2a69a7a17b28e698087560fb78a2cac350c5a0d332`. The native selection remains separate from the speech catalog interface. See [pin and payload audit](seat-1-logs/pin-payload-audit.log).

**Host speech guarantees.** I reviewed the complete host delta from `7aaf72424a8c5bec8e51000339c92936268ab0c7` to the selected host and compared its archived speech paths. Voice, Whisper and sizer installers, `config/content_models.py`, and every wrapper byte from the TTS branch through the STT branch to EOF are unchanged. Sizer acquisition remains limited to `--setup-default` and `--recommend`; ordinary STT uses its existing path. Whisper runtime remains `15ef23b32da497a41198d3028e34715801de6196`, copied with `uv sync --locked --no-editable` and bundled ONNX weights removed. The existing model-catalog route still owns presentation, receipt and digest-verified acquisition. New structured-action operations handle panes, agent launch/delivery and operation status; they add no speech acquisition or default-setting verb. K95's complete delta changes only its CI host pin, leaving the dictation offer unchanged. OS provisioning, generator and release guard are byte-identical to the accepted baseline. The carrier delivery, receipt-gate and speech census tests pass with private acceptance controls. See [speech-path audit](seat-1-logs/speech-path-audit.log) and [command-wrapper diff](seat-1-logs/host-command-diff.log).

**Independent refusal controls and planted regressions.** I ran 14 independently designed guard probes plus an additional pre-seat hermetic control. Positive controls use clearly labeled PRIVATE stand-in seats, never release review records. The actual pre-seat refuses specifically for missing `ACCEPTANCE.json`. The private accepted carrier accepts its exact host. The following independent defects are refused for their intended reasons:

- Older exact accepted host with the new carrier; truncated or unreadable current host SHA.
- A private host whose content gitlink shares the first 39 hexadecimal digits with the carrier but differs in its final digit; the matching full-SHA control passes.
- Old carrier content and the release content pin moved together, with all carrier/receipt digests recomputed, while the current host continues serving the new content.
- Deleted acceptance; altered receipt with outer checksums recomputed; fully repinned receipt naming a different carrier; fully repinned one-seat receipt.
- Changed seat bytes with outer checksums recomputed, and a symlinked seat retaining identical bytes.

I then planted two regressions only in the isolated validator source: deleting its content-gitlink comparison, and comparing only seven hexadecimal digits. Each wrongly accepted my same-prefix attack, and each caused the committed full-SHA regression test to fail with `0 != 1`. Both mutants were therefore detected, 2/2. See [own mutations](seat-1-logs/own-mutations.log) and [additional refusal/classification evidence](seat-1-logs/suite-classification.log).

**Executed suites.** Tests ran with a scrubbed environment, temporary HOME/TMPDIR, `/usr/bin:/bin`, disabled bytecode writes and explicit host/content/licence/voice/Bonsai repository overrides from the preparation record. No installed Kilix command or live store was used.

| Tree/control | Result |
| --- | --- |
| Initial exact pre-seat `4c1a53c`, full OS | 904 tests; 11 failure blocks, 21 error blocks, 3 skips. One unrelated stale-notes failure, now fixed. |
| Final exact pre-seat `35442a8`, full OS | 904 tests; 10 failure blocks, 21 error blocks, 3 skips. All eight affected test methods concern absent acceptance/seats; no unrelated failure remains. |
| Private stand-in acceptance, carrier suite | 15 tests, all pass. |
| Private stand-in acceptance, exact successor source, full OS | 904 tests, pass with 3 skips. |

Counts of failure/error blocks include mutation subtests; they are not counts of independent broken implementation paths. One hermetic positive control omits stderr in its assertion; I independently reproduced it against the final pre-seat and confirmed the missing-receipt diagnostic. The private stand-in source was explicitly compared against the successor archive; only generated private receipt/seats, checksums and their receipt pins differ. Logs: [pre-seat full](seat-1-logs/preseat-full.log), [stand-in full](seat-1-logs/standin-full.log), [carrier suite](seat-1-logs/standin-carrier.log), [classification](seat-1-logs/suite-classification.log). Reproduction scripts and configuration are saved beside these logs.

## Known issues and limits

The three archive-environment skips are explicit: no `v0.2.1` history in the archive, no released native inspector in the checkout, and no sibling `pleb` checkout for desktop-identity comparison. They are not missing-acceptance failures or successful qualifications.

The held engine's prior hosted CI remains non-green for libdrm/lint/macOS. Nothing in this carrier review changes that status. I did not rebuild the unchanged engine or requalify its prior runtime findings.

This is an offline carrier/content-binding review for the selected VM chain. No model was downloaded, no licence accepted, and no live voice storage, installed launcher, held-out/task data, transcription, ISO installation, VM execution or reboot was accessed or performed. Unchanged speech runtime behavior relies on its prior qualification plus the unchanged-input and current contract checks above. The new Needle pin establishes selection only; this review makes no inference about benchmark reliability or task success. Later laptop-only refs are outside this record. Real-seat receipt generation and final acceptance checks remain the release owner's next step; private test fixtures must never be used as release records.

VERDICT: ship with known issues
