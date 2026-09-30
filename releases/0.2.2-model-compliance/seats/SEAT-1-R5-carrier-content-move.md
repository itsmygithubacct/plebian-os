# Independent seat 1 — Whisper small.en dictation carrier (0.2.2 RC3)

Reviewed commit: `4ff589a3543e793e8caf4c66773d9d0c563d0011`.

I did not author this carrier, the Whisper determination, or the code it pins.

## Findings

No new findings. The remaining Medium known issue is unchanged: installing the
pinned runtime leaves five dependency weight files in the isolated user's package
cache even though the published runtime generation is weight-free. The round-2 Low
setup-outcome edge cases and test gap are also unchanged. This content move changes
neither issue.

## Independent evidence

1. I compared the exact content objects `5b1a446..716a672`. The only changes are
`CHANGELOG.md`, the kilix-needle and kilix-rtsp refs in `catalog/plebian.json`, and
the catalog trust-root digest in `receipt.py`. Both catalogs contain the same 32
asset ids, no asset object other than those two unrelated records differs, and the
entire vendored licence tree has the same tree object. Canonical hashes for the four
speech records are identical at both refs:
`deb2229003414d42a423bea8188a47bd2d1d8c0abfd3b4d83b4ba17429733755`,
`23b8774a07c0c9cd0bbe0b02ba2e12238668a5e996f35e45a24756338fd4c3e6`,
`019407e57febbabf2e08d11888cf74ced9db3239c8bb5a9e084a70c7e02db6a2`,
and `5a18902af21e6b451e9c3cecf33e7210b3f5944e026a0d5e2c2b66306ac7542c`.
The exact carrier diff `ad4306d..4ff589a` changes only `interface_content_ref` in
`CARRIER.env` and `CARRIER.json`, the derived binding and manifest digests, and
removal of the prior acceptance receipt and two round-4 seat records. All six
determinations are unchanged and still byte-match their original owner files.

2. In a fresh archive I independently regenerated from content `716a672`, licence
`993c8ec`, and the six original owner files in sorted carrier-path order. All 37
pre-seat files were byte-identical. `CARRIER.json` hashes to
`cbb067cee5eca78b38e4fa3157a470df90f6ea234a2306b2801b25e563b78a4e`,
equal to `PLEBIAN_OS_VOICE_CARRIER_SHA256` in both release files.

3. Exact tree reads show
`7aaf72424a8c5bec8e51000339c92936268ab0c7:third_party/kilix-content` is
`716a672b62ff80b014b586523bfa407d05b89191`, while `0b34f93` serves
`5b1a446bbbd0e29f16f59121be89cdf714b992a1`. In an independently generated
accepted stand-in, all 13 carrier tests passed and the guard accepted the new pins.
Moving only `KILIX_REF` back to `0b34f93` was refused specifically because the
carrier content did not equal that host commit's content gitlink. The committed
pre-seat carrier was refused for its absent `ACCEPTANCE.json`. All five
`PLEBIAN_OS_NATIVE_*` values are byte-for-byte unchanged from `ad4306d`.

4. The exact Kilix range `0b34f93..7aaf724` is one commit and changes only the
content gitlink and the kilix-rtsp installer default; the two refs agree at
`74a8eb6`. Every speech launcher, installer, catalog consumer, and setting is a
byte-identical blob across the range. The voice pin remains `a12be47`, the runtime
pin remains `15ef23b`, the sizer pin remains `b58b871`, and the engine gitlink
remains `84e9f1d`. The content catalog still has 32 assets. The Kilix 95 delta is
only its CI host-pin line. Thus this delta weakens no speech guarantee.

5. With a fresh archive of `4ff589a`, an empty temporary home, bytecode disabled,
and the prescribed exact repository overrides, the OS suite ran 902 tests: 8
failures, 21 errors, and 3 skips. Every failure and error was in
`test_model_compliance_carrier` and followed from the deliberately absent receipt
or seat directory, including defect subtests whose intended reason was pre-empted
by that absence. No unrelated test failed. In a separate temporary accepted
stand-in copy, the complete carrier module passed 13/13.

VERDICT: ship with known issues
