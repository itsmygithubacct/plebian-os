# Independent seat 1 — Whisper small.en dictation carrier (0.2.2 RC3)

Reviewed commit: `e3fcdc23894f09a904c01ddb9e95bdc4efbb110a`.

I did not author this carrier, the Whisper determination, or the code it pins.

## Findings

No new findings. The remaining Medium known issue is unchanged: installing the
pinned runtime leaves five dependency weight files in the isolated user's package
cache even though the published runtime generation is weight-free. The round-2 Low
setup-outcome edge cases and test gap are also unchanged. The earlier advisory
paraphrase issue is closed by the owner's verbatim acceptance of the correction in
the correction note's “Owner acknowledgement” section.

## Independent evidence

1. I compared exact content objects `19fa9f9..5b1a446`. The only changes are
`CHANGELOG.md`, the unrelated kilix-needle ref in `catalog/plebian.json`, and the
catalog trust-root digest in `receipt.py`. Both catalogs contain the same 32 asset
ids. Canonical hashes for the four speech asset records are identical at both refs:
`deb2229003414d42a423bea8188a47bd2d1d8c0abfd3b4d83b4ba17429733755`,
`23b8774a07c0c9cd0bbe0b02ba2e12238668a5e996f35e45a24756338fd4c3e6`,
`019407e57febbabf2e08d11888cf74ced9db3239c8bb5a9e084a70c7e02db6a2`,
and `5a18902af21e6b451e9c3cecf33e7210b3f5944e026a0d5e2c2b66306ac7542c`.
The entire vendored licence tree has the same tree object. Regeneration from the
six original owner files also proves that every committed determination remains a
byte-identical copy of its original.

2. The exact carrier diff `1612483..e3fcdc2` contains only the new content ref in
`CARRIER.env` and `CARRIER.json`, their derived `BINDINGS.sha256` and `SHA256SUMS`
hashes, and removal of the previous receipt and two seat records. I independently
regenerated from content `5b1a446`, licence `993c8ec`, and the six original owner
files in sorted carrier-path order. All 37 pre-seat files were byte-identical.
`CARRIER.json` hashes to
`285136a69451d857d16d27eae6302e3cce83f6eafa47788c86ad17579c72c3ec`,
equal to the pin in both release files.

3. Exact tree reads show that
`0b34f933b498b25b9035da7ea523544f73095ad2:third_party/kilix-content` is
`5b1a446bbbd0e29f16f59121be89cdf714b992a1`, while `f5c66d3` serves
`19fa9f9009779b275601e6df2b075063896663b1`. A stand-in accepted carrier passed
all 13 carrier tests and the guard at the new pins. Moving only `KILIX_REF` back to
`f5c66d3` was refused specifically because its gitlink did not equal the carrier
content. The reviewed pre-seat carrier was refused for its absent receipt/seats.
All five native-selection values are byte-for-byte unchanged from `1612483`.
Deleting the guard's gitlink comparison in a temporary copy made the hermetic
planted-defect test fail for “host serves other content”, the fully re-pinned
unserved-content case, and the unreadable-host-tree case.

4. I reviewed every commit and changed blob in the exact Kilix range
`f5c66d3..0b34f93`, including engine refs `5483c25` and `84e9f1d`. The sizer is
fetched from the full pin `b58b871` only for `--setup-default` or `--recommend`;
a plain `kilix stt` use only adopts an already executable copy and does not fetch.
The chrome requires the selected model files and executable runtime before
dictation becomes available, and requires both the provider and an audio player
before read-aloud becomes available. Its install offer invokes exactly
`kilix stt --install whisper-small-en --default whisper-small-en`, whose existing
model-catalog path is receipt-gated. The runtime and voice pins remain `15ef23b`
and `a12be47`, their installers are byte-unchanged across the range, and the content
catalog remains at 32 assets. The relevant host suites passed 116/116. The Kilix 95
delta changes only its CI host pin.

5. With a fresh archive of `e3fcdc2`, an empty temporary home, bytecode disabled,
the prescribed repository overrides, and the exact new host checkout, the OS suite
ran 902 tests: 8 failures, 21 errors, and 3 skips. Every failure and error was in
`test_model_compliance_carrier` and followed from the deliberate absence of
`ACCEPTANCE.json` and the seat directory, including defect subtests whose expected
reason was pre-empted by that absence. No unrelated test failed. In a temporary
accepted stand-in copy, the carrier module passed 13/13.

VERDICT: ship with known issues
