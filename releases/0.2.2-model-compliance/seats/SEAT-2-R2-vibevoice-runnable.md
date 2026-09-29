# Independent seat 2 — VibeVoice runnable carrier (0.2.2 RC3)

Reviewed commit: `c227894f0388af254ef2ca63253ff95f281682a5`.

I did not author this carrier, the C2 amendment record, or the code it pins.

Round 2, per `SEAT-BRIEF-R2.md`. It supersedes my round-1 record on `d59b5b2`.

Pins reviewed:

| Component | Commit |
| --- | --- |
| Kilix | `dacb868` |
| Bonsai | `7464828` |
| Engine | `5b5bb03` |
| kilix-voice | `296ccea` |
| Kilix 95 | `85d0530` |
| VibeASR.cpp | `c4334009` |

Method:
- All evidence comes from `git archive` / `git clone` extractions of those exact SHAs,
  under `/home/pleb/scratch-workers/seat2-r2/`.
- The author's worktrees moved again during the review (Kilix `b62bc7d`, dirty;
  kilix-voice `52b4cfc`). Nothing from them is reviewed here.
- I modified no repository. The one synthetic commit below was made in my own throwaway
  clone and then deleted.
- I accepted no licence, wrote nothing under `~/.local/gpu_terminal`, and ran no `kilix`
  launcher verb against the live desktop. Kilix tests ran under `env -i` with a temp
  HOME and a sandbox `GPU_TERMINAL_HOME`.

## Findings

### Round-1 findings: status

| Round-1 finding | Status at the new SHAs | Evidence |
| --- | --- | --- |
| Seat 1 High: consent vs loaded bytes | **Closed for path replacement and ordinary rewrites.** Two narrow residuals remain (Low, below). | A1, A2, A3, A4; V1–V3, V7, V8 killed |
| Seat 1 Medium: Bonsai digest bypass | **Partly closed.** `--no-verify` is gone and null digests are refused, but one size-only shortcut still installs unverified bytes (Medium, below). | B1, B2 |
| Seat 1 Medium: no-weights checks | **Closed for the named locations.** The census is still name-based (Low, below). | census tests; staging-dir plant |
| Seat 2 Medium: runnable not tied to pins | **Closed for rollback.** The new test is structural only (Low, below). | P4a–P4d fail; synthetic fork passes |
| Seat 2 Low: timeout reaping, concurrent close | **Closed.** | A6, A7 |
| Seat 2 Low: runtime generation bound to its ref | **Closed**, with the expected residual that a forged `REF` is trusted. | C7a, C7c rebuilt; C7b accepted |
| Seat 2 Low: static-link wording, fork disclosure | **Closed** (Kilix README and installer header; release notes). | — |
| Seat 2 Low: surviving mutants M7 and M8 | **Closed**: both now fail the author's tests. Two new survivors appear (Low, below). | M7, M8 killed |

### Medium — Bonsai reports "already complete" without verifying digests when every member has the right size

In `models/_shared/pull.sh` at `7464828`, `outstanding` counts only files whose size is
wrong. The line `[ "$outstanding" = 0 ] && [ "$FORCE" = 0 ] && { log "already complete";
exit 0; }` therefore returns before the per-file loop, which is the only place existing
files are hashed.

Reproduction (B2):
1. Private data home under `unshare -n --map-current-user`, fake gate returning 0.
2. Hard-link 7 genuine members; replace `config.json` with a same-length copy that has
   one byte changed (sha `427f9a19…`).
3. Run `models/vibevoice-asr-bitnet/pull.sh`: `8 files, 1.6G total, 0B to fetch` /
   `already complete`, `rc=0`. The installed `config.json` is still `427f9a19…`, not the
   pinned `4873cb75…`.

This is the outcome of seat 1's Medium (installed hash ≠ pinned, route exits 0), now
without any flag.

Realistic path: a machine that pulled with the RC2 Bonsai `186fd98`. That version left
`tokenizer.json`, `tokenizer_config.json`, `vocab.json` and `README.md` undigested and
honoured `--no-verify`. Re-running `kilix stt --install vibevoice-asr-bitnet` with the
fixed Bonsai reports success without ever checking the newly pinned digests. The carrier
says the model is "verified against the pinned digests before installation".

Mitigations:
- It is not a C3 bypass: the receipt gate runs first and exits 3 with no receipt.
- asr_infer loads only the two GGUFs, whose digests were pinned before, and dictation
  consent binds their bytes.

Fix: hash existing members before the early exit, or drop the size-only shortcut for
licence-gated models.

This was not introduced by the fix. It is where seat 1's finding remains open.

### Low — two residual consent windows in `VibeVoiceStt`

The fd-holding design closes path replacement (A1: `os.replace` of the LM mid-turn; the
child still hashes A) and rewrites (A2: in-place rewrite before the child, refused; A3:
in-place rewrite during the child, refused). Two narrow cases remain.

- **R1, rewrite during the child, then restore.** Fake `asr_infer` hashes
  `/proc/self/fd/N` at 0.6 s. A thread writes B in place at 0.3 s and restores A at
  1.1 s. The child hashed B (`725bcd6c…`). The post-check sees ctime moved, re-hashes,
  finds A, and **accepts** the transcript. A held descriptor names the inode, not a
  snapshot; with mmap (asr_infer's default) the child sees in-place writes live.
- **R2, same timestamp tick.** `_require_unchanged` compares
  `(dev, ino, size, mtime_ns, ctime_ns)` and skips re-hashing when they are equal. It
  has none of the racy rule that the digest cache has. On this machine (ext4,
  `CONFIG_HZ=250`) 2000 rewrites with an fstat between each produced 5 distinct ctimes
  (4 ms ticks). If a model file was last written in the same tick as the engine's
  construction and is rewritten again in that tick, the change is invisible. Result:
  18 of 20 trials loaded B and were accepted. The comment "A rewrite always moves ctime"
  is false within a tick.

Both need a writer in the user's 0700 model directory at the right moment. That same
writer could also rewrite the unsigned consent record (`consent._write`, plain JSON in
the same data dir), so neither widens the trust boundary.

### Low — the no-weights census and guest check are name-based

`voice_dictation_asset_paths` and `build_vm_image._no_speech_weights_check` test fixed
directory names. I planted `desktop-apps/assets/.asset-install-abc123/vibeasr-lm-i2_s-embed-q6_k.gguf`
(kilix-content's own staging prefix, `install.py:1590`) and
`voice/models/.stage/vibeasr-vae-encoder-i8_s.gguf`. The census printed nothing and the
guest check returned 0. A content sweep (`find "$d" -name '*.gguf'`, or a size bound)
would not depend on each route's layout. Provisioning runs none of these routes, so this
is hardening, not a defect of this image.

### Low — `test_runnable_models` checks shape, not the pin

In my own scratch clone of Kilix I committed only
`KILIX_VIBEASR_REF=0123456789abcdef0123456789abcdef01234567` on top of `dacb868`
(`b11f4ce`). I pointed `PLEBIAN_OS_KILIX_REPO` at that clone and pinned
`KILIX_REF=b11f4ce` in the completed copy. Result: `Ran 899 tests … OK`. A Kilix whose
runtime installer pins a nonexistent VibeASR commit (so nothing is ever runnable) passes.
The test checks only `^KILIX_VIBEASR_REF=[0-9a-f]{40}$`. Rollback, the round-1 attack,
is now caught (P4a–P4d fail). Suggested fix: pin `c4334009…` in the release manifest and
assert equality.

### Low — new surviving mutants

Author suites used for the kilix-voice mutants: `test_vibevoice_consent_binding`,
`test_stt_binding`, `test_consent_digest_cache`, `test_consent_gate`, `test_p1_mechanisms`,
`test_stt_tool` (187 tests).

- **V4**, removing the post-child `_require_unchanged`, survives those 187 tests. My A3
  kills it.
- **V5**, reverting the timeout reap to `process.wait()` so the pipes leak again,
  survives them. My A7, which asserts no `ResourceWarning`, kills it.
- **V9**, dropping `O_NOFOLLOW`, survives both theirs and mine.
- In Bonsai, deleting the post-download `sha256sum` comparison
  (`if [ "$sha" != "-" ]` → `if false`) leaves its 166-test suite `OK`. Deleting the new
  null-digest refusal loop is caught.

### Informational — scope beyond the brief's fixes

Kilix `dacb868` also brings:
- `184f98f`: docs and skills only.
- `e161f0d` plus engine `5b5bb03`: `map ctrl+shift+d kilix_dictate`.

The new action routes through the same `toggle_dictation` as the tab-bar button (hidden
prompt and pixel-pane refusals, install offer, and the daemon consent gate). It cannot be
reached by unauthenticated remote control: `kilix_rc_auth.py` allows only
`action load_config_file`. No other `ctrl+shift+d` or `kitty_mod+d` binding exists in
Kilix `config/` or the engine's option definitions.

## Independent evidence

### Round-1 attacks reproduced against the new SHAs

**Consent.** My test file `s2r2_test.py` ran against `296ccea` under `tests/cleanenv.sh`,
using a fake `asr_infer` that hashes its `--lm-model`.

| Attack | Result |
| --- | --- |
| A1 path replaced mid-turn | child hashes A (fixed) |
| A2 in-place rewrite before end | `SttError … modified` |
| A3 in-place rewrite during the child | `SttError` |
| A4 rewrite between gate and construction | `… changed after dictation consent was checked` |
| A6 concurrent `close()` | returns `""`, no `AttributeError` |
| A7 timeout | child PID gone, no `ResourceWarning`, WAV removed, under 5 s |

My round-1 `toctou.py` outcome (the engine loaded B) no longer occurs.

**Mutants planted back into a copy of `296ccea`.** Baselines: author suites 187 OK;
mine 6 OK.

| Mutant | Author | Seat 2 |
| --- | --- | --- |
| V1 no consented compare | killed | killed |
| V2 paths instead of fds | killed | killed |
| V3 no pre-check | killed | survived |
| V4 no post-check | **survived** | killed |
| V5 wait() instead of communicate() | **survived** | killed |
| V6 close race restored | killed | killed |
| V7 daemon drops the payload | killed | survived |
| V8 make_stt drops the payload | killed | killed |
| V9 no `O_NOFOLLOW` | survived | survived |
| V10 byte-equal shortcut removed | killed | killed |
| round-1 M7 no kill on timeout | killed | killed |
| round-1 M8 settled on mtime only | killed | survived |

**Bonsai `7464828`** (fake gate on PATH, `unshare -n`):
- B1 `--no-verify` → `unknown option`, rc 2 (seat 1's attack closed).
- A null digest planted in `MODEL.json` → `README.md … has no pinned sha256; refusing`
  before creating any directory.
- A gate exiting 3 → rc 3, no directory.
- A tampered `--from` copy falls through to download (no network here, so the fetch
  failed).
- B2 → `already complete`, rc 0 (Medium above).
- All 8 Bonsai digests equal both the live store's files and the carrier's `ARTIFACT.json`.
- Suite: 166 OK, 9 skipped.

**OS rollbacks.** Completed copy (synthetic labelled seats plus receipt), full suite each
time:

| Probe | Result |
| --- | --- |
| P4a `KILIX_REF=a9d6fee` | `test_the_pinned_kilix_builds_the_vibevoice_runtime` fails |
| P4b `KILIX_REF=848ceea` | same |
| P4c `KILIX_VOICE_REF=00a6cff`, carrier regenerated | same (install-kilix-voice default mismatch) |
| P4d all three old refs, carrier regenerated | both runnable tests fail |

**Census.** Seat 1's planted `voice/models/vibevoice-asr-bitnet` is now reported by the
production function and fails the guest check (`test_speech_weight_census`, 4 tests,
green).

### 1. Determination authenticity

`cmp` of all 5 vendored determinations against the originals: all identical. Digests:

| Record | SHA-256 (prefix) |
| --- | --- |
| small-en-us | `b6a44eca…` |
| lgraph-en-us | `109fc3ad…` |
| VibeVoice | `889658d7…` |
| C2 amendment | `8723530b…` |
| J1/J2 | `3618c282…` |

`git diff d59b5b2 c227894 -- …/determinations` is empty, and the original amendment file
is unchanged (mtime 07:54). My round-1 transcript check of the owner's two quoted phrases
therefore still applies.

### 2. Independent regeneration

From the original records, in sorted order: `wrote 29 files`, and `diff -r` against the
committed carrier is identical. `CARRIER.json` =
`b249611d6ba61a3c67b39b0d9466e322e0af366e65b4eab88e6cc231c826e2ac`, equal to both
`releases/0.2.2.env` and `releases/0.2.2.requirements`. The only carrier change from
round 1 is `voice_ref` → `296ccea` in CARRIER.env/json, the three DELIVERY files,
BINDINGS and SHA256SUMS.

### 3. Delivery claims

- `readonly PROVISION_VOICE_WEIGHTS=0` is unchanged.
- Provisioning runs no weight route.
- The runtime installer fetched `c4334009` with llama.cpp `a2fdadc2` and kompute
  `4565194e` (code only; round-1 offline-build and zero-tensor vocab evidence still
  applies). It now writes `REF=vibeasr=c4334009…`.
- Installer controls: C1 tracked edit, C2 untracked file, C3 submodule edit, C4 extra
  commit and C5 outside link are all refused. The round-1 fake binary (C7a) and a stale
  `REF` (C7c) now trigger a rebuild. A forged `REF` (C7b) is accepted, which is the same
  trust as the data home. `shellcheck -S warning` is clean.
- AC-8 gates at the pinned Kilix and Bonsai pass in the completed copy.
- The Bonsai digest shortcut is the Medium above.

### 4. The runnable claim is true

I built the runtime with the `dacb868` installer in a sandbox (1m07s). kilix-voice
`296ccea` ran it through the full path: `resolve_stt` → `consent_identity` →
`consented_payload` → `make_stt`. Weights were hard-linked into a private data home and
removed afterwards; the live store was untouched (GGUF mtimes still 2026-07-28).
asr_infer received `/proc/self/fd/N`.

- My espeak phrase transcribed as "The aftermath of seven legends from the harbour master
  up to date." (5.1 s).
- `kristin.wav` at 16 kHz transcribed as "Quick brown fox jumps over the lazy dog.
  Dictation with five voice should transcribe this sentence correctly." (8.0 s).
- No temp WAV remained. `close()` released both held fds.

### 5. C1 and C3 intact

The VibeVoice carrier entry is unchanged apart from `voice_ref`:
- MIT and Apache-2.0
- Microsoft Corporation and Alibaba Cloud
- 4 digest-verified texts

No new weight route. The Bonsai gate still precedes any fetch (exit 3 with no receipt),
and the new null-digest refusal also precedes it.

### 6. Code review and suites

- **Consent/engine:** reviewed above.
- **kilix-voice `296ccea`:** full suite under `tests/cleanenv.sh`, with the pinned
  licence `78417e4` and Kilix's content gitlink `9a4a84d`: 1190 tests `OK` (3 skipped).
- **Kilix `dacb868`:** `test_vibeasr_installer`, `test_voice_installer` and
  `test_voice_chrome`, with engine `5b5bb03`'s `kitty/` in `src/`: 98 OK.
- **Kilix 95 `85d0530`:** changes only the CI `KILIX_COMMIT` (via `457f2e3`).
- **Publication:** every pin descends from its round-1 predecessor and is reachable from
  a published branch (`git ls-remote`).

### 7. OS suite on the reviewed commit

The suite ran in a clone at `c227894` with `env -i HOME=<tmp> PATH=/usr/bin:/bin` and the
five overrides (Bonsai = `/home/pleb/gpu_terminal/kilix-apps/kilix-bonsai`, which holds
`7464828`). Result: `Ran 899 tests … FAILED (failures=6, errors=19, skipped=1)`.

All 25 are in `test_model_compliance_carrier`: AC-4, AC-6, AC-7, AC-10, AC-11 subtests
and AC-12. Every one fails on `ACCEPTANCE.json` or `seats/` being absent, so all are the
expected missing-receipt/seat failures. The 6 new tests (runnable ×2, census ×4) pass.

The real guard refuses: `carrier: ACCEPTANCE.json is missing or not a regular file` plus
the release refusal line.

Completed copy (two labelled synthetic seats, receipt, and its pin): the guard returns 0,
and the suite gives `Ran 899 tests … OK (skipped=1)`.

VERDICT: ship with known issues
