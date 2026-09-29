# Independent seat 1 — Whisper small.en dictation carrier (0.2.2 RC3)

Reviewed commit: `9231407ecb32e99ace17633d0d72c1ffe4851387`.

I did not author this carrier, the Whisper determination, or the code it pins.

## Findings

Medium — the provider installation still fetches and retains neural-network
weights, only now outside the published generation. I ran the pinned installer
with isolated `HOME`, `KILIX_DATA_HOME`, and `GPU_TERMINAL_SOURCE_HOME`. The
generation contained no `*.onnx`, but the isolated home's uv cache contained
five ONNX files. Two were the same bundled VAD weights reported in round 1:
532,505 and 713,415 bytes, with SHA-256
`8c20344f509846a07ccd85827e8857017fae67fabd58689bec1af79e1d488307` and
`0e9fc8f56407693d283f99045fb95c2b90fdca3433ce5f83e2c121fb4e615075`.
Three example models from the runtime dependency also remained there. Thus the
new post-sync deletion makes the generation weight-free but does not make the
installer's claim that it installs code, not weights, true. Reproduce with a
fresh isolated `HOME`, run `scripts/install-kilix-whisper-stt.sh`, then compare
`find $KILIX_DATA_HOME/voice/whisper -name '*.onnx'` with
`find $HOME/.cache/uv -name '*.onnx'`. The first is empty and the second is not.

Medium — the vendored owner determination still falsely describes the advisory
that the first-use screen shows. It says the shown caution concerns invented
text and accuracy variation, while the pinned record and rendered screen carry
the consent, subjective-classification, and high-risk-use caution. The
builder's separate correction accurately identifies this mismatch, but it is
not owner-authored and is deliberately absent from the carrier. The owner's
verbatim acceptance says only `MIT, advisory`; it does not establish that the
different specific caution was the one accepted. Byte authenticity is intact,
but a private builder correction is not enough provenance for the contradictory
owner determination shipped in the acceptance evidence. The owner should amend
or reaffirm the determination before this is treated as closed.

## Independent evidence

1. I archived every reviewed SHA. All six vendored determination/ruling files
byte-matched their originals: the two compact-recognizer determinations, the
three existing large-recognizer files, and the new determination. All five
pre-existing files byte-matched parent
`096dd9abbff79ce90ca8c877dec25ef144cb9430`. The new file contains all three
owner quotations verbatim. Comparing its advisory description with the pinned
advisory exposed the documentary finding above.

2. I independently regenerated from content `b8258fb`, licence `993c8ec`, and
the six original determination files in sorted path order. All 37 pre-seat
files were byte-identical. `CARRIER.json` hashed to
`9478ed218ddb172204621902ac6618a6dfa179eaf01d28e9e24b31e20841b7e2`,
equal to both release pin files.

3. `git rev-parse 2d86841:third_party/kilix-content` returned
`b8258fbbd72e012262be4e64ac4e42d790785841`, equal to the carrier-content pin.
No carrier consumer compares against the native-content pin, and all five
`PLEBIAN_OS_NATIVE_*` values equal the parent values. I made a synthetic
accepted carrier: the guard accepted it unchanged, refused the original attack
where only `KILIX_REF` moved, refused a fully rebound carrier and release pin at
older content, and refused an unreadable host tree. The split-pin finding is
closed.

4. The image/provisioning delivery tests passed 7/7; their census mutations
included both `voice/models/whisper-small-en` and
`desktop-apps/assets/faster-whisper-small-en`. Provisioning leaves its weight
switch at zero. Independent size and SHA-256 checks of the five upstream
members matched the pinned 486,100,128-byte manifest. The pinned content tests
passed 3/3 and demonstrated screen, decline-without-fetch, receipt-before-fetch,
and digest verification. The provider itself forces local-only model loading.
The runtime install's cached dependency weights are the exception reported
above.

5. The pinned installer completed in temporary homes. Three real recordings
produced “The quick brown fox jumps over the lazy dog.”, “Please open a new
terminal tab and list the files in my home directory.”, and “Remind me to call
the dentist tomorrow at 3.30 in the afternoon.” Synthetic two-second silence
and a two-millisecond impulse both produced empty transcripts. All five local
model-member digests matched before use. Provider protocol tests passed 9/9.

6. The exact pinned first-use tests passed 3/3 and proved MIT, both licensors,
the pinned revision, the actual advisory, no receipt or fetch on decline, and a
covering receipt before fetch on acceptance. The direct speech install hands
the content asset id to that licence screen and fetches no model bytes itself;
omitting a receipt pre-check there is necessary and sound. The relevant voice
licence, setup, and engine tests passed 99/99. Manually placed bytes remain
outside an install route, as for the other catalog models.

7. Source review and mutation tests confirmed that `WhisperStt` holds the four
required regular files, hashes their descriptors, gives the child links to
those same descriptors, rechecks racy bytes after load and transcription,
bounds protocol I/O, kills and reaps the child, and has no engine fallback.
Changing the managed source after a real install left the loaded threshold at
`0.6` from the copied generation rather than the edited `0.61`; its module path
was inside the generation and there was no editable hook. Installer mutations
for an old stamp, editable hook, undeletable ONNX path, dirty source, wrong ref,
and failed sync all refused or rebuilt as intended; its suite passed 9/9.
Setup now distinguishes a failed accepted download from a decline, so failure
leaves the desktop offer unanswered; the offer test passed. The full sizer
component suite passed 43/43.

8. With the prescribed scrubbed environment, exact overrides, and no bytecode
caches, the OS suite ran 900 tests: 6 failures, 22 errors, and 3 skips. Every
failure/error was in the carrier module and followed from the deliberately
absent pre-seat `ACCEPTANCE.json` and seat directory; no unrelated test failed.
The guard refused the reviewed pre-seat artifact for the missing acceptance
receipt, as required.

VERDICT: ship with known issues
