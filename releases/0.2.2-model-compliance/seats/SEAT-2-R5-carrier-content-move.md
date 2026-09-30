# Independent seat 2 — Whisper small.en dictation carrier (0.2.2 RC3)

Reviewed commit: `4ff589a3543e793e8caf4c66773d9d0c563d0011`.

I did not author this carrier, the Whisper determination, or the code it pins.

This is round 5: the carrier regenerated for Kilix `7aaf724`, whose content gitlink
is `716a672`. Its parent is the accepted rc3 `ad4306d`. I took all evidence from fresh
clones checked out at 4ff589a, `git archive` copies of the exact SHAs, and my own
scratch directories.

I modified no repository, pushed nothing and accepted no licence. I ran no `kilix @`
and no installed `kilix` verb, and I did not read or write the live store. Kilix
tests ran from an archive with `env -i`, a temporary `HOME` and `KILIX_HOME` set to
the archive. When I finished, the whisper-os, whisper-host and whisper-k95 worktrees
were clean (whisper-os HEAD still 4ff589a).

## Findings

### High / Medium

None.

### Low

**L1. The receipt pin is stale, by design.**

- `PLEBIAN_OS_VOICE_CARRIER_RECEIPT_SHA256` in both release files is still
  `e8ac9487…`. That is the sha256 of `ad4306d`'s round-4 `ACCEPTANCE.json`, which
  this commit removes.
- This is the expected pre-seat state. The guard refuses with "ACCEPTANCE.json is
  missing or not a regular file".
- The acceptance commit must move this pin in both files. In my stand-in copy the
  suite passes only after that re-pin.

**L2. The gitlink test covers a host behind the carrier, not a host ahead of it.**

- The shipped comparison in `build/remaster-iso.sh` is correct: a full 40-hex
  string equality between `FETCH_HEAD:third_party/kilix-content` and the carrier's
  `interface_content_ref`. On the real SHAs it refuses every wrong pairing I tried
  (table under check 3).
- Two mutants I planted survive all 902 OS tests:
  - **M6.** Also accept when the carrier's content equals the gitlink of
    `KILIX_REF~1`. This is "the host is one commit ahead of the carrier". This round
    is exactly that move (`7aaf724~1` = `0b34f93`, gitlink `5b1a446`). With M6 in
    place, the guard accepts the round-4 carrier (content `5b1a446`, R4 pins) under
    `KILIX_REF=7aaf724`, with rc 0. Unmutated, it refuses with "is not KILIX_REF's
    kilix-content gitlink".
  - **M4.** Compare only the first 7 hex characters. Every wrong gitlink in the
    suite differs within its first 7 characters, so M4 survives.
- **Impact.** None on this artefact: the reviewed guard has neither weakening.
  This is a test gap, and a later relaxation of either kind would go unnoticed.
- **Suggested fix.** The hermetic `gitlink_repo` case could add two arms: a served
  commit whose parent carries the carrier's content, and a gitlink that shares the
  carrier's 7-character prefix.

**L3/L4. Round 4's L2 and L3 are unchanged.**

- They are the sizer `--print-path` trust on a plain `kilix stt` open, and the
  chrome's presence-only Whisper availability hint.
- This delta touches neither the launcher nor the engine. The engine gitlink (`src`)
  is `84e9f1d` at both `0b34f93` and `7aaf724`. The only other gitlink change is
  kilix-content.

**Rounds 2–4 known issues.** They are unchanged. This delta touches no weight
installer, no voice code, no licence data and no speech asset record.

## Independent evidence

**1. No speech record changed.**

*Content `5b1a446..716a672`* is one commit (`716a672`), and `5b1a446` is its
ancestor. It changes three files:

- `src/kilix_content/catalog/plebian.json`: the kilix-rtsp ref (`dc83447` →
  `74a8eb6`) and the kilix-needle ref (`03c3462` → `747ae37`);
- `receipt.py` `_CATALOG_SHA256`. The new value, `ed0d44de…`, equals the sha256 of
  the new catalog bytes;
- the CHANGELOG.

I parsed both catalogs and compared them:

- Each has 32 assets, with the same ids, and no asset record differs.
- The only top-level key that differs is `content`, which holds the two component
  refs.
- Every speech asset is equal at both commits: `vosk-model-small-en-us-0.15`,
  `vosk-model-en-us-0.22-lgraph`, `vibevoice-asr-bitnet`, `faster-whisper-small-en`,
  `whisper-tiny-ggml` and `piper-en-us-kristin-medium`.
- `third_party` is the same tree object (`1ac8d6fa…`) at both commits.

*The carrier against `ad4306d`.*

- **CARRIER.json.** A recursive field diff shows exactly two changes:
  `interface_content_ref` (`5b1a446` → `716a672`) and `bindings_sha256`.
- **CARRIER.env.** Only `interface_content_ref` changed.
- **BINDINGS.sha256.** Only the `CARRIER.env` line changed.
- **SHA256SUMS.** Three lines changed (BINDINGS, CARRIER.env, CARRIER.json). The
  ACCEPTANCE line and the two round-4 seat lines were removed.
- **Removed files.** `ACCEPTANCE.json` and both round-4 seat records.
- **Outside the carrier.** `build/`, `provision/`, `tests/`, `config/` and
  `scripts/` are unchanged from ad4306d. Otherwise only the CHANGELOG, the notes pin
  table, and the three pins in `releases/0.2.2.env`/`.requirements` changed.

**2. Independent regeneration.**

- **Determinations.** All six vendored files `cmp`-match their originals:
  - small and lgraph, in `f104-vosk-licence-evidence-2026-09-14`;
  - VibeVoice, J1-J2 and C2, in `licence-evidence-vibevoice-asr-bitnet-2026-09-15`;
  - Whisper, in `licence-evidence-whisper-small-en-2026-09-29`.
- **The run.** I ran `build/generate-model-compliance.py` under `env -i`, with the
  original content and licence repos and the six originals in sorted order. It
  wrote 37 files.
- **The comparison.** `diff -r` against the committed carrier is byte-identical.
- **The pins.** `sha256(CARRIER.json)` =
  `cbb067cee5eca78b38e4fa3157a470df90f6ea234a2306b2801b25e563b78a4e`. That equals
  `PLEBIAN_OS_VOICE_CARRIER_SHA256` in both `releases/0.2.2.env` and
  `releases/0.2.2.requirements`.

**3. The guard binding at the new pins.**

- **The pins agree.**
  - `7aaf724:third_party/kilix-content` = `716a672…`. That equals the carrier's
    `interface_content_ref` and `PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF`.
  - `0b34f93:third_party/kilix-content` = `5b1a446…`.
  - 0b34f93 is the parent of 7aaf724.
- **The stand-in copy.** In a second clone of 4ff589a, I regenerated the carrier with
  two stand-in seat records. CARRIER.json was unchanged (`cbb067ce…`), and the
  receipt was `e0b9e2ad…`. I re-pinned both files. I then ran the real guard through
  the suite's own `release_env`/`run_guard`. `KILIX_REPO` was the local whisper-host,
  or a scratch clone for the synthetic commits.

| Case | Stand-in | Guard message |
| --- | --- | --- |
| Served pins (KILIX_REF 7aaf724) | rc 0 | (accepted) |
| Only `KILIX_REF` moved to 0b34f93 | rc 1 | "the carrier's content is not KILIX_REF's kilix-content gitlink" |
| `KILIX_REF` 0b34f93 and content pin 5b1a446 | rc 1 | "producing interfaces are not the release's pins" |
| Only the content pin moved to 5b1a446 | rc 1 | "producing interfaces" |
| A 7aaf724 child with the gitlink removed | rc 1 | "is not KILIX_REF's kilix-content gitlink" |
| A 7aaf724 child with gitlink 5b1a446 | rc 1 | "is not KILIX_REF's kilix-content gitlink" |
| The round-4 carrier and pins under KILIX_REF 7aaf724 | rc 1 | "is not KILIX_REF's kilix-content gitlink" |
| The committed pre-seat carrier (any case above) | rc 1 | "ACCEPTANCE.json is missing" |

- **Against the public remote.** With `KILIX_REPO=https://github.com/itsmygithubacct/kilix.git`
  - 7aaf724 → rc 0;
  - 0b34f93 → rc 1, "is not KILIX_REF's kilix-content gitlink".
  - 7aaf724, 716a672, d0732cf, needle 747ae37 and rtsp 74a8eb6 are all branch heads on
    their remotes.
- **Native selection.** The six `PLEBIAN_OS_NATIVE_*` lines are identical at
  ad4306d and 4ff589a.
- **Mutants in `build/remaster-iso.sh`.** I planted each one in its own copy of the
  stand-in tree:

| Mutant | What it does | Result |
| --- | --- | --- |
| M1 | Deletes the gitlink comparison | KILLED: "host serves other content" and "carrier and pin agree on unserved content" fail |
| M2 | Compares the release pin with the carrier instead of the fetched gitlink | KILLED: the same two subtests fail |
| M3 | Fails open when KILIX_REF cannot be read | KILLED: "unreadable host tree" fails |
| M5 | Fetches the local repo's HEAD instead of KILIX_REF | KILLED: the control arm, "host serves other content" and two acceptance tests fail |
| M4 | Compares only a 7-hex prefix | SURVIVED all 902 tests (L2) |
| M6 | Also accepts `KILIX_REF~1`'s gitlink | SURVIVED all 902 tests. My real-SHA case catches it: it accepts the R4 carrier under 7aaf724 (L2) |

- **The unmutated copy.** All carrier tests pass.

**4. The Kilix delta `0b34f93..7aaf724` weakens no speech guarantee.**

- **What changed.** Two paths:
  - the `third_party/kilix-content` gitlink (`5b1a446` → `716a672`);
  - `scripts/install-kilix-rtsp.sh` `KILIX_RTSP_DEFAULT_REF` (`dc83447` → `74a8eb6`,
    which equals the new catalog ref).
  - The other six gitlinks are identical, including the engine at `src` = `84e9f1d`.
- **Pins at 7aaf724.**
  - `install-kilix-voice.sh` pins `a12be47…`, which equals `KILIX_VOICE_REF`.
  - `install-kilix-whisper-stt.sh` pins `15ef23b…`.
  - `install-kilix-tts-sizer.sh` pins `b58b871…`, which equals
    `KILIX_SYSTEM_MONITOR_REF`.
- **Content catalog.** 32 assets, with no speech asset changed (check 1).
- **Kilix 95.** `35a8908..d0732cf` is one line: the CI `KILIX_COMMIT` moves to
  7aaf724.
- **The Kilix test run.** In an archive of 7aaf724 with content 716a672 populated:
  - `test_content_models`, `test_voice_installer` and `test_whisper_stt_installer`:
    85 ran, OK;
  - `test_component_pin_delivery` (covers the rtsp pin): 12 ran, OK.

**5. OS suite on 4ff589a.**

- **How I ran it.** In a fresh clone with no `__pycache__`, using `env -i
  HOME=<tmp> PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1` and the five overrides from
  `SEAT-BRIEF.md`. `PLEBIAN_OS_KILIX_REPO` was
  `/home/pleb/scratch-workers/whisper-host`, which holds 7aaf724.
- **The result.** 902 tests ran: failures=8, errors=21, skipped=1.
- **Every failure is the missing receipt or seats.** All 29 are in
  `test_model_compliance_carrier`:
  - 28 cite `ACCEPTANCE.json` or `seats/` in their traceback or in the guard's
    stderr;
  - the 29th is the hermetic control arm (rc 1, not 0). The guard refuses it for the
    same missing receipt.
- **Against round 4.** The count, 29 of 902, is the same.
- **With stand-in seats.** In the re-pinned copy, all 902 passed (OK, skipped=1).

VERDICT: ship with known issues
