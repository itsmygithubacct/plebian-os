# Independent seat 2 — Whisper small.en dictation carrier (0.2.2 RC3)

Reviewed commit: `e3fcdc23894f09a904c01ddb9e95bdc4efbb110a`.

I did not author this carrier, the Whisper determination, or the code it pins.

This is round 4: the carrier regenerated for Kilix `0b34f93`, whose content gitlink
is `5b1a446`. I took all evidence from a fresh clone checked out at e3fcdc2,
`git archive` copies of the exact SHAs, and my own scratch directories.

I modified no repository, pushed nothing and accepted no licence. I ran no `kilix @`
and no installed `kilix` verb, and I did not read or write the live store. Kilix
tests ran from an archive with `env -i`, a temporary `HOME` and `KILIX_HOME` set to
the archive. When I finished, the whisper-os, whisper-host and whisper-k95 worktrees
were clean.

## Findings

### High / Medium

None.

### Low

**L1. The receipt pin is stale, by design.**

- `PLEBIAN_OS_VOICE_CARRIER_RECEIPT_SHA256` in both release files still names the
  round-3 receipt (`375a3635…`). That receipt is removed from the carrier.
- This is the expected pre-seat state. The guard refuses with "ACCEPTANCE.json is
  missing".
- The acceptance commit must move this pin in both files. AC-12 enforces that: it
  errors pre-seat and passes in my stand-in copy only after the re-pin.

**L2. A plain `kilix stt` open trusts an existing sizer without checking the checkout.**

- In Kilix `0b34f93` (`kilix`, the new block in `stt)`), a run without
  `--setup-default`/`--recommend` calls `install-kilix-tts-sizer.sh --print-path`.
  It exports the result whenever that path is executable.
- `--print-path` returns before the installer's "HEAD is the pin and
  `status --porcelain` is empty" check. The fetch route does run that check.
- So a modified checkout at `sources/.kilix-tts-sizer-b58b871…` is used as-is on a
  plain open.
- **Impact.** The sizer only names a recommended model. It fetches nothing, and it
  sits in the user's own source home. No licence, receipt or weight path depends on
  it.
- **The brief's claim holds.** A plain open never fetches. I planted "always fetch"
  (S1) and "setup does not fetch" (S2) in copies of the launcher, and
  `test_opening_stt_never_fetches_the_sizer` killed both.

**L3. The chrome's Whisper availability check is presence only.**

- Engine `5483c25`/`84e9f1d`: `_stt_available("whisper", …)` needs four things:
  - a recorder;
  - non-empty `model.bin`, `config.json`, `tokenizer.json` and `vocabulary.txt`, in
    `voice/models/whisper-small-en` or else in
    `desktop-apps/assets/faster-whisper-small-en`;
  - an executable `kilix-whisper-stt` runtime;
  - no digest check.
- The author's own test shows it: 7-byte `fixture` files plus a `#!/bin/sh` stub make
  the microphone read as available.
- **Why this is not a weakening.** It is only the button's hint, the same model as
  Vosk. Loading goes through kilix-voice `a12be47`: `make_stt` → `WhisperStt` →
  `_hold()`. That step opens the files with `O_NOFOLLOW` and compares the held-bytes
  digest with `consented_payload`. None of that changed in this delta: the voice pin
  is still `a12be47`.
- **Piper.** The Piper check only looks for the provider binary and a player. It does
  not check the voice files. That is outside the speech carrier.

**Round 2 and 3 known issues.** They are unchanged. This delta touches no installer
for weights, no voice code, no licence data and no speech asset record. The
advisory-paraphrase item is now owner-acknowledged, as the brief states.

## Independent evidence

**1. No speech record changed.**

*Content `19fa9f9..5b1a446`* is one commit (`5b1a446`). It changes three files:

- the kilix-needle `ref` (`67b97ac` → `03c3462`) in `catalog/plebian.json`;
- `_CATALOG_SHA256` in `receipt.py`. The new value, `9bebd09d…`, equals the sha256 of
  the new catalog bytes;
- the CHANGELOG.

I parsed both catalogs and compared them:

- There are 32 assets in each, with the same ids, and no asset record differs.
- The only top-level key that differs is `content`.
- The canonical hashes of the four speech assets are unchanged:
  - small `deb22290…`
  - lgraph `23b8774a…`
  - vibevoice `019407e5…`
  - faster-whisper `5a18902a…`
- `third_party` is the same tree object (`1ac8d6fa…`) at both commits.

*The carrier against `1612483`.*

- **CARRIER.json.** A recursive field diff shows exactly two changes:
  `interface_content_ref` (`19fa9f9` → `5b1a446`) and `bindings_sha256`.
- **CARRIER.env.** Only `interface_content_ref` changed.
- **BINDINGS.sha256.** Only the `CARRIER.env` line changed.
- **SHA256SUMS.** Three lines changed (CARRIER.env, BINDINGS, CARRIER.json). The
  ACCEPTANCE line and the two seat lines were removed.
- **Removed files.** `ACCEPTANCE.json` and both round-3 seat records.
- **Outside the carrier.** `build/`, `provision/`, `tests/`, `config/` and `scripts/`
  are unchanged from 1612483.

**2. Independent regeneration.**

- **Determinations.** All six vendored files `cmp`-match their originals under
  `~/research/gpu_terminal`.
- **The run.** I ran `build/generate-model-compliance.py` in a scrubbed environment,
  with the original content and licence repos and the six originals in sorted order.
  It wrote 37 files.
- **The comparison.** `diff -r` against the committed carrier is byte-identical.
- **The pins.** `sha256(CARRIER.json)` =
  `285136a69451d857d16d27eae6302e3cce83f6eafa47788c86ad17579c72c3ec`. That equals
  `PLEBIAN_OS_VOICE_CARRIER_SHA256` in both `releases/0.2.2.env` and
  `releases/0.2.2.requirements`.

**3. The guard binding at the new pins.**

- **The pins agree.**
  - `git rev-parse 0b34f93:third_party/kilix-content` = `5b1a446…`. That equals the
    carrier's `interface_content_ref` and `PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF`.
  - `f5c66d3:third_party/kilix-content` = `19fa9f9…`.
  - f5c66d3 is an ancestor of 0b34f93.
- **The stand-in copy.** In an archive of e3fcdc2, I regenerated the carrier with two
  stand-in seat records. CARRIER.json was unchanged (`285136a6…`), and the receipt
  was `7d30b7da…`. I re-pinned both files. I then ran the real guard through the
  suite's own `release_env`/`run_guard`, with `KILIX_REPO` set to the local
  whisper-host.

| Case | Result | Guard message |
| --- | --- | --- |
| Served pins (KILIX_REF 0b34f93) | rc 0 | (accepted) |
| Only `KILIX_REF` moved to f5c66d3 | rc 1 | "the carrier's content is not KILIX_REF's kilix-content gitlink" |
| `KILIX_REF` and the content pin both moved to f5c66d3/19fa9f9 | rc 1 | "the carrier's producing interfaces are not the release's pins" |
| Only the content pin moved to 19fa9f9 | rc 1 | "producing interfaces" |
| A Kilix commit with no content gitlink | rc 1 | "is not KILIX_REF's kilix-content gitlink" |
| The committed pre-seat carrier | rc 1 | "ACCEPTANCE.json is missing" |

- **Native selection.** The five `PLEBIAN_OS_NATIVE_*` lines hash identically at
  096dd9a, 1612483 and e3fcdc2.
- **The hermetic test from 3da2a0e still proves the comparison.** I planted these in
  `build/remaster-iso.sh`, in copies of the stand-in tree:

| Mutant | What it does | Result |
| --- | --- | --- |
| M1 | Deletes the gitlink comparison | KILLED: "host serves other content" and "carrier and pin agree on unserved content" fail |
| M2 | Only requires a non-empty gitlink | KILLED: the same two subtests fail |
| M3 | Fetches `HEAD` instead of `KILIX_REF` | KILLED: the control arm and "host serves other content" fail |
| M4 | Also accepts an empty gitlink | Survived, but equivalent |

  M4 is equivalent because `git rev-parse REV:missing/path` prints its argument on
  stdout. The gitlink therefore never comes back empty, and I proved it.
- **The unmutated copy.** All 13 carrier tests pass.

**4. The Kilix delta `f5c66d3..0b34f93` weakens no speech guarantee.**

- **What changed.**
  - `584317a`, `4bc7b88`: `docs/AGENTS.md` only.
  - `2a9d28c`: the AGENTS doc and the content gitlink.
  - `76eed61`: the `kilix` stt block, the sizer installer pin `01aa6b7` → `b58b871`,
    and tests.
  - `d1f126c`/`0b34f93`: `kilix_sdk/settings.py` gains `whisper`,
    `whisper-small-en` and `piper`. The engine gitlink moves
    `5b5bb03` → `5483c25` → `84e9f1d`. Only `kitty/kilix_voice.py` changed there.
- **The sizer.**
  - It is fetched only when an argument is `--setup-default` or `--recommend`, and
    only from the pinned, depth-1, staged-then-moved checkout.
  - Other uses take `--print-path` and never fetch (see L2).
  - It fetches code only, no weights.
- **The chrome.**
  - The install offer's argv is fixed as
    `(kilix, 'stt', '--install', model, '--default', model)`. It is reached only
    when `STT_MODEL_ENGINES[model] == engine`, and it is launched only after the
    confirmation (`launch_model_install` returns when not confirmed).
  - I planted a different argv (`models install`, C2). It was killed by two chrome
    tests.
  - Dropping the payload check (C1) or the runtime check (C3) for Whisper was killed
    by `test_whisper_dictates_from_the_content_store_once_its_runtime_is_installed`.
- **Pins.** These are unchanged at 0b34f93:
  - kilix-voice `a12be47` in `install-kilix-voice.sh` and in `KILIX_VOICE_REF` in the
    release env;
  - kilix-whisper-stt `15ef23b` in `install-kilix-whisper-stt.sh`.
- **Byte-unchanged across the delta.** `scripts/` other than the sizer installer, and
  `config/content_models.py`.
- **Content catalog.** 32 assets.
- **Kilix 95.** `0acdb4a..35a8908` is one line: the CI `KILIX_COMMIT`.
- **The Kilix test run.** I ran the speech suites in an archive of 0b34f93, with
  engine 84e9f1d and content 5b1a446 populated: `test_voice_cli`,
  `test_voice_chrome`, `test_shared_settings`, `test_content_models`,
  `test_whisper_stt_installer`, `test_voice_installer` and `test_model_runtimes`.
  - 240 ran, and 2 failed.
  - Both failures are `TranscriptArchiveIntegrationTests`, and they fail identically
    at f5c66d3. They are environmental, not speech.

**5. OS suite on e3fcdc2.**

- **How I ran it.** In a fresh clone with no `__pycache__`, using `env -i
  HOME=<tmp> PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1` and the five overrides from
  `SEAT-BRIEF.md`. `PLEBIAN_OS_KILIX_REPO` was `/home/pleb/scratch-workers/whisper-host`,
  which holds 0b34f93.
- **The result.** 902 tests ran: failures=8, errors=21, skipped=1.
- **Every failure is the missing receipt or seats.** All 29 are in
  `test_model_compliance_carrier`. Each one is one of these:
  - a `FileNotFoundError` for `ACCEPTANCE.json` or `seats/`;
  - an assertion whose stderr is the guard's "ACCEPTANCE.json is missing" refusal,
    which pre-empts the planted-defect reason;
  - the new hermetic control arm (rc 1, not 0) for the same reason.
- **Against round 3.** That was 28 failures of 900 tests. The one extra failure is
  that control arm. The two new tests from 1612483 pass.
- **With stand-in seats.** In the re-pinned copy, all 902 passed (OK, skipped=3). The
  two extra skips are the archive's lack of a v0.2.1 tag and of the released
  inspector.

VERDICT: ship with known issues
