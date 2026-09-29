# Independent seat 1 — Whisper small.en dictation carrier (0.2.2 RC3)

Reviewed commit: `3fa9c80f19f54e7b207d87bd5cf8aa0ef05ff907`.

I did not author this carrier, the Whisper determination, or the code it pins.

## Findings

No new findings. The two Medium known issues from round 2 remain: the runtime
installer's dependency fetch leaves weight files in its package cache, and the
owner determination misdescribes the specific advisory carried by the pinned
record. This content move changes neither issue.

## Independent evidence

1. I compared content `b8258fb..19fa9f9` from the exact objects. The only
changed files are `CHANGELOG.md`, the unrelated kilix-needle ref in
`catalog/plebian.json`, and the catalog trust-root digest in `receipt.py`.
The catalog still contains 32 assets. Canonical hashes of the four speech
assets are identical at both commits:
`deb2229003414d42a423bea8188a47bd2d1d8c0abfd3b4d83b4ba17429733755`,
`23b8774a07c0c9cd0bbe0b02ba2e12238668a5e996f35e45a24756338fd4c3e6`,
`019407e57febbabf2e08d11888cf74ced9db3239c8bb5a9e084a70c7e02db6a2`,
and `5a18902af21e6b451e9c3cecf33e7210b3f5944e026a0d5e2c2b66306ac7542c`.
The entire vendored kilix-license tree is the same tree object. All six
vendored owner files still byte-match their originals.

2. The exact `c0518db..3fa9c80` carrier diff contains only the content ref in
`CARRIER.env` and `CARRIER.json`, its derived `BINDINGS.sha256` and
`SHA256SUMS` hashes, and removal of the prior acceptance receipt and two seat
records. I independently regenerated from content `19fa9f9`, licence
`993c8ec`, and the six original owner files in sorted path order. All 37
pre-seat files were byte-identical. `CARRIER.json` hashes to
`3181ae2b6806d122dd437854b81781029b151183c5fce92452a6241439521e71`,
equal to the pin in both release files.

3. Exact tree reads show `f5c66d3:third_party/kilix-content` is `19fa9f9`,
equal to the carrier content ref, while `2d86841` serves `b8258fb`. A
synthetic accepted carrier passed the guard at `f5c66d3`. Replaying the attack
by changing only `KILIX_REF` to `2d86841` failed specifically because the
carrier content was not that host commit's content gitlink. The reviewed
pre-seat carrier failed for its absent `ACCEPTANCE.json`, as required. All
five `PLEBIAN_OS_NATIVE_*` values are byte-for-byte unchanged from the
accepted parent.

4. The exact Kilix range `2d86841..f5c66d3` has three commits and changes only
the agent guide, the `kilix games play` branch and its tests, and the content
gitlink. The speech installer and model-catalog implementation have identical
blob ids across the range; the speech-provider pin remains `15ef23b`, the
voice pin remains `a12be47`, and the packaged catalog count remains 32. In an
archive of `f5c66d3` populated with content `19fa9f9`, the installer, speech
CLI, and model-catalog suites passed 60/60. Thus the delta does not weaken an
installer, `kilix stt`, `kilix models`, a voice pin, the runtime pin, or the
catalog population guarantee.

5. With the prescribed scrubbed environment and repository overrides, the OS
suite ran 900 tests: 6 failures, 22 errors, and 3 skips. Every failure and
error was in `test_model_compliance_carrier` and resulted from the deliberate
absence of `ACCEPTANCE.json` and the seat directory; no unrelated test failed.
In a temporary copy, a freshly generated stand-in acceptance made that module
pass 13/13.

VERDICT: ship with known issues
