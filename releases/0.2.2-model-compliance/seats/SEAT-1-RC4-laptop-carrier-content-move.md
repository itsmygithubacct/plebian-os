# Independent seat 1 — separate laptop RC4 carrier

Reviewed commit: `7ff93259f6eecbcffab7474c826c8347aba9a60e`.

I did not author the laptop carrier, the determinations it includes, or its pinned code.

## Findings

No new Critical, High, Medium or Low defect was found in this offline carrier change. The release-notes closure-table entry selects the current laptop content and agrees with both manifests. The exact pre-seat artifact has neither `ACCEPTANCE.json` nor a seats directory and correctly refuses release advertisement for the missing receipt. Its retained old receipt pin cannot make that absent receipt pass.

The verdict below concerns review of the carrier and its exact source selection. It leaves the existing engine qualification limits in place and requires release to generate and check acceptance from the real reviewer records.

## What I independently established

I extracted the specified commit directly from `/home/pleb/scratch-workers/rc4-voice-carrier-laptop` into `/tmp/rc4-laptop-seat1-_uokqj3h/preseat`. Its parent is `e9fc7750016df67b1a72153ee619d2383c5418dc`. The originals and repository refs remained untouched. This review uses its own measurements and test fixtures; it does not use another seat's review record.

The exact laptop selections resolve as follows:

| Input | Commit |
| --- | --- |
| Host | `296a8f862176991d023061e4a2bd8df6e5df0625` |
| Content | `191abbcbf11ceae03f40e732c20d394c8d53578a` |
| K95 | `cea38b7f6a85a473877888f0250fb8083e6a7e33` |
| Engine | `84e9f1de2b71d18fcbb0bf080ca6ea40910ac9fd` |
| Voice | `a12be47e289ca03fccd46840276add1833df5760` |
| Licence authority | `993c8ec0df87c677521652b7c3a8ca9797ce2cba` |

The host tree's `third_party/kilix-content` and `src` gitlinks match the content and engine above. K95's workflow names the full selected host SHA. Its difference from frozen VM K95 `fdc50f8fdcf48ec0290043fdf3473e2922fc1fcf` is only that workflow pin; the speech offer code does not change.

I compared the six determinations against their ORIGINAL research files: the small and lgraph determinations, the VibeVoice determination plus C2 and J1-J2 rulings, and the Whisper determination. All six comparisons matched bytes and SHA-256. I then invoked the archived generator with those original files and the pinned content/licence object trees, rather than regenerating from vendored copies. Its complete output of 37 files matched the pre-seat carrier. `CARRIER.json` hashes to `0293655bcae0fa4380a4f89025c1fe50dce294a7f7781d576badaa734cb36709`; both manifests pin this digest and content `191abbcbf11ceae03f40e732c20d394c8d53578a`. Evidence: [original comparisons and generation](laptop-seat-1-logs/authenticity-regeneration.log).

Against accepted VM OS `f962317a4d49cc1e81acecfb9c9955bc5b24a800` and content `2f5f3d7c28fdfe088ea24573f4c7fceea1f53013`, all 32 full asset mappings are equal. The content change updates the Needle program pin to `083f1fb02c5d74212e1d4e4cdb41f3af927235e5`, the catalog trust-root digest and the changelog. I verified the new trust-root digest against the actual catalog bytes. Carrier model entries, licence records and texts, notices, delivery statements and determinations remain identical: 33 unchanged payload files. Only the carrier interface ref and its derived binding digest move inside `CARRIER.json`; old seats and acceptance are removed.

Every voice/library/model, licence, sizer and native selection pin remains equal to the accepted VM manifest. In particular, native content stays `d9a1335db520594c6796209b0f9342000a2b34e7`, source stays `e0655faaf57cc5f14baf449afe937fcbe87d204b`, and the 750896-byte native archive retains digest `d875539b47e6e6b607853f2a69a7a17b28e698087560fb78a2cac350c5a0d332`. Evidence: [object, pin and payload audit](laptop-seat-1-logs/pin-payload-audit.log).

I inspected the host changes from frozen VM host `e97e52a98e2babe6220ee0f3d2f5f4e06ff01f66`. They add startup context inspection and connection metadata handling, documentation and tests; the wrapper change adds the context verb to help. The voice, Whisper and sizer installers and model-catalog command are byte-identical, as are the TTS/STT wrapper branches. No new speech acquisition or default-selection route is introduced. Whisper keeps provider `15ef23b32da497a41198d3028e34715801de6196`, the locked copied installation and bundled ONNX weight deletion. OS provisioning, carrier generation and the release validator also match the accepted VM bytes. The existing first-use licence/receipt and no-provisioning-weights contracts therefore retain their implementation, and their current carrier tests pass. Evidence, including the complete host delta and the notes-table check: [source audit](laptop-seat-1-logs/source-audit.log).

## Execution and adversarial controls

All test runs used the private tree with temporary HOME/TMPDIR, `/usr/bin:/bin`, disabled bytecode writes and explicit preparation-record overrides for the host, content, licence, voice and Bonsai sources. The independent probe scripts additionally used `python3 -B`. Only clearly labeled PRIVATE stand-in seat documents were generated for private positive controls. I checked all 226 archive files against the stand-in source: differences are limited to the added private receipt/seats, its checksums and the receipt-pin lines. Those stand-ins are fictional test inputs and cannot be release records.

| Independently executed run | Outcome |
| --- | --- |
| Exact pre-seat full OS suite | 904 tests; 10 failure blocks, 21 error blocks, 3 skips |
| Private accepted-control carrier suite | 15 tests; all pass |
| Private accepted-control full OS suite | 904 tests; pass, 3 skips |

The 31 pre-seat failure/error blocks affect eight carrier methods and all arise from absent acceptance or seats. Mutation subtests contribute several blocks. None is a separate notes, pin, delivery, provisioning or native regression. A hermetic positive-control assertion suppresses its guard diagnostic, so I reproduced that control directly against the actual pre-seat and observed the missing-`ACCEPTANCE.json` refusal. Raw failing output is retained in [pre-seat full log](laptop-seat-1-logs/preseat-full.log). Passing output is in [carrier log](laptop-seat-1-logs/standin-carrier.log) and [full control log](laptop-seat-1-logs/standin-full.log); [classification and source-identity evidence](laptop-seat-1-logs/qualification-classification.log) records the distinction.

My own 14 guard probes include two positive controls and refusals for the following independently planted inputs:

- The frozen VM host presented with the laptop carrier, plus short and unreadable host SHAs.
- A private host gitlink sharing 39 hexadecimal digits with laptop content but differing in the final digit.
- VM content selected consistently by a fully rehashed carrier and release pin while the host still serves laptop content.
- Missing or modified acceptance; a fully repinned receipt bound to a different carrier; a fully repinned receipt with one seat.
- Modified seat bytes despite recomputed outer checksums, and a symlinked seat with unchanged bytes.

Each refused at its expected check. The extra pre-seat hermetic control described above also refused for missing acceptance. I weakened the private validator twice: removing the full gitlink comparison, then retaining only a seven-digit comparison. Both mutants accepted the crafted wrong-content host, and both were detected by a failing full-SHA regression test (`0 != 1`). Result: 2/2 validator mutants killed. Evidence: [independent mutation log](laptop-seat-1-logs/own-mutations.log). Reproduction scripts and configuration accompany the logs.

## Limits retained

The three skips are archive-environment limitations: the archive lacks the `v0.2.1` tag/history, the released native inspector is absent, and there is no sibling `pleb` checkout for the desktop-identity check. These do not count as passes.

Prior hosted engine CI remains non-green for libdrm/lint/macOS. I neither reran that CI nor replaced its status with the passing OS/carrier results. The fixed engine and speech runtime have not been freshly built or exercised by this review.

This separate laptop carrier review does not accept a laptop install, DEB, ISO, runtime or benchmark result. I did not download models, accept licences, install or set up providers, launch installed Kilix, access live voice storage or held-out/task data, or perform a reboot. Needle selection is verified as a pin; reliability is outside this evidence. Final receipt generation must use the actual independent review records and pass the release's remaining acceptance gates.

VERDICT: ship with known issues
