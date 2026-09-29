# Independent seat 2 — Whisper small.en dictation carrier (0.2.2 RC3)

Reviewed commit: `3fa9c80f19f54e7b207d87bd5cf8aa0ef05ff907`.

I did not author this carrier, the Whisper determination, or the code it pins.

This is round 3, the carrier regenerated for Kilix's content move. I took all evidence
from a fresh clone at 3fa9c80, `git archive` copies, and my own scratch directories.

I modified no repository, pushed nothing and accepted no licence. I ran no `kilix @`
and no installed `kilix` verb, and I did not touch the live store. After I finished,
the whisper-os, whisper-host and whisper-k95 worktrees were clean.

## Findings

### High / Medium

None.

### Low

**Stale receipt pin, by design.**

- **What.** `PLEBIAN_OS_VOICE_CARRIER_RECEIPT_SHA256` in both release files still
  names the round-2 receipt (`2e5950eb…`). That receipt has been removed from the
  carrier.
- **Why that is acceptable.** This is the expected pre-seat state: the guard refuses
  the carrier until a new `ACCEPTANCE.json` is generated and re-pinned.
- **What to do.** The acceptance commit must move this pin in both files. AC-12
  enforces that.

**Round-2 known issues.**

- **Unchanged.** M3 (the advisory paraphrase, which needs the owner) and N1–N4.
- **Why nothing moved.** This delta touches no installer, no voice code, no licence
  data and no speech asset record.

## Independent evidence

**1. No speech record changed.**

*kilix-content `b8258fb..19fa9f9`* is one commit.

- **What it changes.**
  - The kilix-needle `ref` (`2a5b856` → `67b97ac`) in `catalog/plebian.json`.
  - The catalog trust-root digest in `receipt.py`.
  - The CHANGELOG.
- **Parsed comparison of both catalogs.**
  - The asset count is 32 in both, with the same ids.
  - No asset record differs, including `vosk-model-small-en-us-0.15`,
    `vosk-model-en-us-0.22-lgraph`, `vibevoice-asr-bitnet` and
    `faster-whisper-small-en`.
  - The only top-level key that differs is `content`, which holds the needle entry.
- **Vendored licence data.** `git diff --quiet b8258fb 19fa9f9 -- third_party/`
  reports that the vendored kilix-license is unchanged.
- **Existing receipts.** kilix-license coverage looks receipts up by record digest
  and manifest digest, not by the catalogue digest. Existing speech receipts therefore
  still cover.

*The carrier, `c0518db..3fa9c80`.*

- **CARRIER.json.** A field-by-field comparison shows exactly two changes:
  `interface_content_ref` (`b8258fb` → `19fa9f9`) and `bindings_sha256`.
- **Other carrier files.**
  - `CARRIER.env`: only `interface_content_ref` changed.
  - `BINDINGS.sha256`: only the `CARRIER.env` line changed.
  - `SHA256SUMS`: the `CARRIER.env`, `BINDINGS`, `CARRIER.json` lines changed, and the
    `ACCEPTANCE.json` and two seat lines were removed.
  - `ACCEPTANCE.json` and both round-2 seat records were removed.
- **Outside the carrier.** `build/`, `provision/` and `tests/` are unchanged from
  c0518db.

**2. Independent regeneration.**

- **Determinations.** All six vendored files are IDENTICAL to the originals under
  `~/research/gpu_terminal`.
- **The run.** I ran `build/generate-model-compliance.py` with the original content
  and licence repositories and those six originals in sorted order. It wrote 37 files.
- **The comparison.** `diff -r` against the committed carrier is byte-identical.
- **The pins.** `sha256(CARRIER.json)` =
  `3181ae2b6806d122dd437854b81781029b151183c5fce92452a6241439521e71`. That equals
  `PLEBIAN_OS_VOICE_CARRIER_SHA256` in both `releases/0.2.2.env` and
  `releases/0.2.2.requirements`.

**3. The guard binding at the new pins.**

- **The pins agree.**
  - `git rev-parse f5c66d3:third_party/kilix-content` = `19fa9f9`. That equals the
    carrier's `interface_content_ref` and `PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF`.
  - 2d86841 is an ancestor of f5c66d3.
- **The replayed attacks.** In a copy regenerated with two stand-in seat records and
  every pin re-derived (all 13 carrier tests green):
  - **Attack 1: only `KILIX_REF` moved back to 2d86841** (gitlink b8258fb). The guard
    refused it with "the carrier's content is not KILIX_REF's kilix-content gitlink".
    The record-equality test alone passes here, because the records are identical.
    The guard is what catches it.
  - **Attack 2: `KILIX_REF` and the content pin both moved back while the carrier
    stayed.** The guard refused it with "the carrier's producing interfaces are not
    the release's pins", and AC-1 failed.
- **Native selection.** The `PLEBIAN_OS_NATIVE_*` lines are identical to 096dd9a.

**4. The Kilix delta `2d86841..f5c66d3` weakens no speech guarantee.**

- **The commits.**
  - 73bfcec: `docs/AGENTS.md`.
  - f45661f: the `kilix games play` branch in `kilix`, plus `tests/test_games_verb.py`.
    This new block only runs `desktop/games.py --setup-only` and a remote-control
    new-tab. It touches no stt, voice, models or licence path.
  - f5c66d3: the content gitlink only.
- **Speech files unchanged.** These are byte-unchanged across the delta:
  - `scripts/install-kilix-whisper-stt.sh` (still provider `15ef23b`, stamp
    `layout=copied-no-weights-1`);
  - `scripts/install-kilix-voice.sh` (still kilix-voice `a12be47`);
  - `scripts/install-kilix-bonsai.sh`;
  - `scripts/install-kilix-vibeasr.sh`;
  - `config/content_models.py`.
- **Content catalog.** The asset count stays at 32.
- **Kilix 95.** `3d825d3..0acdb4a` changes one line: the CI `KILIX_COMMIT` in
  `.github/workflows/test.yml`.

**5. OS suite on 3fa9c80.**

- **How I ran it.** In a fresh clone with no `__pycache__`, using `env -i
  HOME=<tmp> PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1` and the five overrides from
  the brief. `PLEBIAN_OS_KILIX_REPO` was `/home/pleb/scratch-workers/whisper-host`,
  which holds f5c66d3.
- **The result.** 900 tests ran: failures=6, errors=22, skipped=1. That is the same
  count as the round-2 pre-seat run.
- **Every failure is the expected missing receipt or seat.** All 28 are in
  `test_model_compliance_carrier`. Each one is either the missing
  `ACCEPTANCE.json` / `seats/`, or a planted-defect subtest that the guard's
  "ACCEPTANCE.json is missing" refusal pre-empts.
- **With stand-in seats.** In a temporary copy with the carrier regenerated from two
  stand-in seat records and re-pinned, all 13 carrier tests passed.

VERDICT: ship with known issues
