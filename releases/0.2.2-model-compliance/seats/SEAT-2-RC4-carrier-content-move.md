# Independent seat 2 — RC4 model carrier content move

Reviewed commit: `35442a8be862ef375b3a992737b03138bdf1b542`.

I did not author this carrier, the determinations, or the code it pins.

This review covers the VM-only carrier closure. I independently archived the
initial pre-seat `4c1a53c30603115c462f89bfb8a4a3a0d4125823` and the final
pre-seat above into my own temporary directories. I did not coordinate with
the other seat. The final pre-seat differs from the initial one only in the
release-notes table correction described below; all carrier bytes are identical.

## Findings

- **Low, fixed before this verdict:** the initial pre-seat release notes still
  named content `716a672b62ff80b014b586523bfa407d05b89191`, while the manifest
  selected `2f5f3d7c28fdfe088ea24573f4c7fceea1f53013`. The independently run
  full suite failed `test_notes_closure_table_mirrors_every_pin_in_the_manifest`.
  The final pre-seat corrects exactly that table entry. I byte-compared both
  complete archives, reviewed the one-file diff, and ran all 30 versioning
  tests successfully on the final exact archive.
- **Expected pre-seat state:** neither exact archive contains an acceptance
  receipt or seats. The guard exits 1 specifically because `ACCEPTANCE.json`
  is missing, with the required release-mode refusal. This is intentional;
  the exact pre-seat is not an accepted release artifact. Actual independent
  seat records, regenerated acceptance, and final release validation must
  follow this review.
- **Known limitation retained:** the prior engine CI result remains non-green
  for the reported libdrm, lint, and macOS issues. The unchanged engine pin
  and this carrier review do not resolve or reclassify those results.

No unresolved defect in the carrier content binding or speech inputs was found.

## Independent evidence

1. **Original determinations and generation.** I byte-compared all six
   vendored determinations against the original paths in `PREPARATION.json`
   and independently computed their SHA-256 values. All six match, including
   both supplemental rulings. I regenerated using those ORIGINAL records in
   sorted model/path order, the pinned content tree and pinned licence tree.
   The initial carrier's entire 37-file set is byte-identical. A separate
   regeneration `--check` against the final exact archive exits 0. Both release
   files pin `CARRIER.json` to
   `ce3eb0676c0a978c8d6a9f73bdb2e9e96c1bc670d3212d1d5d6f4a8f9e37d46a`.

2. **Exact source bindings and unchanged inputs.** The full host pin is
   `e97e52a98e2babe6220ee0f3d2f5f4e06ff01f66`; its content gitlink is exactly
   `2f5f3d7c28fdfe088ea24573f4c7fceea1f53013`, and its engine `src` gitlink
   remains `84e9f1de2b71d18fcbb0bf080ca6ea40910ac9fd`. Compared with accepted
   OS `47f6be4b23f953c19ecab582aab1bf5a9a45d6de`, only four release values
   change: host, K95, carrier content, and carrier digest. All native inputs,
   licence inputs, speech-library pins and voice pin remain equal. The voice
   pin remains `a12be47e289ca03fccd46840276add1833df5760`, and the licence
   pin remains `993c8ec0df87c677521652b7c3a8ca9797ce2cba`.

   I compared all 32 complete asset mappings between baseline content
   `716a672b62ff80b014b586523bfa407d05b89191` and the selected content. All
   are equal. All four complete speech records in `CARRIER.json` are equal;
   the carrier JSON changes only its content ref and derived bindings digest.
   Content changes only the Needle application ref, catalog trust digest,
   and changelog. The K95 delta from `d0732cf` to full
   `fdc50f8fdcf48ec0290043fdf3473e2922fc1fcf` changes only its exact-host
   CI pairing in `.github/workflows/test.yml`.

3. **Speech guarantees.** I compared the host's speech/model paths as exact
   Git blobs against accepted host `7aaf72424a8c5bec8e51000339c92936268ab0c7`;
   all 17 matched. This includes the voice, Whisper, Piper and other TTS
   installers and model installer. I reviewed the launcher delta: its added
   structured-action and explicit-socket tmux dispatch do not change the
   existing speech/model dispatch branches. The pinned Whisper installer
   still selects runtime `15ef23b32da497a41198d3028e34715801de6196`, verifies
   its clean pinned source, installs with `uv sync --locked`, and removes
   bundled ONNX weights. The voice installer's receipt check precedes its
   verified model fetch. The full OS delivery, receipt-chain and weight-census
   checks pass on the final private control. The sizer and speech runtime
   installers are unchanged, so this content move adds no automatic model
   acquisition or alternate consent route.

4. **Own adversarial controls.** I independently executed 15 guard controls
   against private copies. The accepted private control serves the exact
   carrier content. Changing only the host back to the accepted baseline is
   refused for the gitlink mismatch. A locally constructed host fixture whose
   gitlink differs only in the final hex character is refused, despite sharing
   a 39-character prefix. Short and uppercase host refs are refused; a short
   content ref is refused even after private re-pinning. A carrier and release
   pin agreeing on an unserved full content SHA are also refused. Acceptance
   for another carrier, one seat with re-pinned acceptance, an altered seat
   with updated checksum listing, and an altered bound notice are refused
   for their specific reasons. Removing the exact-content comparison or
   weakening it to seven characters makes the same final-hex defect pass:
   these planted validator defects prove the control reaches the comparison.

5. **Suites and failure attribution.** I ran tests with `env -i`, a temporary
   HOME, `/usr/bin:/bin`, `PYTHONDONTWRITEBYTECODE=1`, and all five repository
   overrides from `PREPARATION.json`. The initial exact archive full OS suite
   ran **904 tests**, with **11 failure reports, 21 error reports, and 3 skips**.
   All failure/error reports arise from absent receipt/seats except the one
   stale-notes finding above. A private stand-in acceptance control reduced
   this to that single notes failure. After applying the independently
   verified exact successor notes bytes, the final private control ran the
   full **904 tests: OK, 3 skips**, including **15/15 carrier tests** and their
   supplied defect scenarios. The exact final archive's versioning suite is
   **30/30**, and authority-profile tests are **6/6**.

   The three skips are archive/environment limits: no local `v0.2.1` tag for
   the historical self-update provisioner check, no released native inspector
   in this checkout, and no sibling pleb checkout for the desktop-session
   identity check. They are retained as skips, not claimed as passes.

   Stand-in seats are explicitly labelled PRIVATE TEST STAND-IN, kept only
   in my temporary test tree, and are never release records. This green
   control demonstrates the remaining checks after acceptance exists; it
   does not accept the pre-seat or replace validation with the actual seats.

## Scope and preserved evidence

Logs and the independently executed source/guard scripts are in
`seat-2-evidence/` beside this record. Initial failures, the one-file successor
diff, final regeneration, final missing-acceptance refusal, and all suite
results are preserved separately. The working archives were under
`/tmp/rc4-carrier-seat2.ogynUy/`.

I made no original repository/ref changes, publication, installation, licence
acceptance, model download, live-store access, or installed-launcher call.
I read no held-out/task data. I did not rerun transcription or download the
unchanged runtime. Source-level census checks are not a newly built image
inspection. This review makes no claim about VM execution, laptop acceptance,
Needle benchmark reliability, or fresh hosted engine CI. Those retain their
separate evidence and owners.

VERDICT: ship with known issues
