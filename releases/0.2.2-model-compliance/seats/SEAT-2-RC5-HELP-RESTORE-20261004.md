# RC5 Help Search restoration — independent F100 seat 2

VERDICT: ship

Reviewed 2026-10-04. I did not author the candidate changes. I independently inspected sources and executed the checks below without consulting another fresh seat review or coordinating with another seat. No blocking defect found in the reviewed F100 payload and source closure.

Exact reviewed inputs:

- OS candidate based on `7d44dea9c64876835a4d7264f941d72a2771ebfc`, with candidate release-manifest changes.
- Host `e76ea0beb4c7d3340490e6d2dc3bd1a97bd9f3ab`.
- Kilix95 `03da5ffb303c1483a733b4bd2230c13612b4871c`; its committed CI host pin is the exact host above.
- Content `1210151be1757d8f62b402b7b3196e1564d976b3`, Needle `7de641763c403f8c54873ef4d044277c946d4445`, TUI `8b461045715f176218c57b17ff16ccfd756aace1`, licence `ca8a0f479893ab9c8cd6cadc2716c474aaad2820`.
- Provisional carrier generated from the exact pins above, `CARRIER.json` SHA256 `96ec0550c5adb5bcd155102cdb0fe3d82fdce65ff82a2001ebfdd2079290de79`.

Evidence and findings:

- The host's Content gitlink equals the full carrier Content SHA. Content selects the exact Needle and TUI SHAs above; Needle's bundled TUI gitlink and the host TUI installer select that same TUI revision. The candidate OS manifest and closure table carry the final Kilix95 SHA.
- Comparing the provisional carrier with the base carrier found identical four-model entries and identical model artifact, licence record, licence/advisory text, six owner determination/ruling, NOTICE, and DELIVERY bytes. Only `CARRIER.json`, `CARRIER.env`, `BINDINGS.sha256`, and `SHA256SUMS` changed among their common files. The model set remains small-en-us, lgraph-en-us, vibevoice-asr-bitnet, and whisper-small-en; the licence pin and dictation/download digests are preserved.
- The unchanged generator, run with the exact Content/licence commits and all six carried determinations, passed `--check` against the provisional directory: byte-identical regeneration. Both `sha256sum --check SHA256SUMS` and `sha256sum --check BINDINGS.sha256` passed.
- Focused existing carrier checks, redirected in memory to the provisional directory, passed AC-2 projection, AC-3 licence bytes, exact records served by the host, AC-5 advertised coverage, AC-8 delivery/receipt gates, and AC-9 absent-carrier refusal: six tests. A separate AC-4 artifact comparison returned no gaps. The first AC-8 attempt lacked an explicit local Voice checkout; rerunning with the pinned Voice and Bonsai repositories passed. Source checks preserve `PROVISION_VOICE_WEIGHTS=0` and receipt gates before downloads.
- At the exact TUI revision, all four `test_help_search.py` tests passed, including temporary-prefix launcher installation and literal argv handling. At final Kilix95 against the exact host, my independent `tests/run.py helpsearch start_help_menu` passed both files (2/2), covering cited passages, wrapping, cleanup, and menu entry.

Acceptance boundary: this verdict covers the named source closure and provisional carrier payload. The provisional directory intentionally contains no acceptance receipt or seats; at review time the OS manifests still retained the previous carrier/receipt hashes. Before committing the closure, regenerate the final carrier with both fresh independent seat files, pin its actual `CARRIER.json` and `ACCEPTANCE.json` hashes consistently in `.env` and `.requirements`, and pass the complete carrier acceptance/defect suite including AC-6, AC-7, AC-10, AC-11, and AC-12. These are required assembly checks, not evidence already produced by this seat. Adding seats must preserve the reviewed carrier SHA. No runtime VM, F101/F104, strict-media, or release-artifact qualification is claimed.
