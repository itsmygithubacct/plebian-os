# Independent seat 2 — Whisper small.en dictation carrier (0.2.2 RC3)

Reviewed commit: `9231407ecb32e99ace17633d0d72c1ffe4851387`.

I did not author this carrier, the Whisper determination, or the code it pins.

This is round 2.

**Sources.** All evidence comes from `git archive` of the exact pinned SHAs, unpacked
into my own scratch directory:

| Component | Commit |
| --- | --- |
| plebian-os | 9231407 |
| Kilix | 2d86841 |
| kilix-voice | a12be47 |
| Provider | 15ef23b, plus ffc4e71 for its new test |
| Content | b8258fb |
| Licence | 993c8ec |
| Kilix 95 | 3d825d3 |
| Sizer | b58b871 |

**Method.**

- I ran the OS suite in a fresh clone checked out at 9231407.
- I planted every mutation in a throwaway copy.
- I installed the runtime into sandboxes under my scratch directory.

**Constraints I kept.**

- I modified no repository, pushed nothing and accepted no licence.
- I ran no `kilix @` and no installed `kilix` verb.
- I did not touch the live store.

After I finished, the three author worktrees were clean at 9231407, 2d86841 and
a12be47.

## Findings

### Round-1 findings: status

| Round-1 finding | Status at 9231407 | How I checked |
| --- | --- | --- |
| Seat 1 High, editable install | **Closed** | Re-ran the attack and planted the defects back |
| M1, failed download recorded as "declined" | **Closed for the reported case** | Re-ran my round-1 probe |
| M2, ONNX weights in the runtime | **Closed for the runtime.** A residue remains (N1) | Census of the new generation |
| M3, advisory paraphrase | **Open, needs the owner** | Read the correction note |
| L1, guard does not bind content to KILIX_REF | **Closed** | Replayed my forged carrier |
| L2, DELIVERY text | **Closed** | Planted the defect back |
| L3, hand-placed weights | Unchanged, accepted as pre-existing for every model | — |
| L4, untested defences | **Closed** | Planted both defects back |

#### Seat 1 High: editable install

My round-1 sandbox (built by the c8070ee installer) did contain
`__editable__.kilix_whisper_stt-0.1.0.pth`.

- **Upgrade.** Running the 2d86841 installer over that sandbox rebuilt the generation,
  because the old stamp no longer matches. The new stamp is
  `kilix-whisper-stt=15ef23b… layout=copied-no-weights-1`. Afterwards no
  `__editable__` or `*.onnx` file remained, and a second run reused the generation.
- **The attack.** I appended `raise SystemExit` to the managed source checkout's
  `__init__.py`. `--version` still answered `kilix-whisper-stt 0.1.0`.
- **Planted defects.** Each of these was killed by `tests/test_whisper_stt_installer.py`:
  - `--no-editable` dropped;
  - the `__editable__` refusal dropped;
  - the old stamp restored.

#### M1: failed download recorded as "declined"

I re-ran my round-1 probe against a12be47:

| Case | Result |
| --- | --- |
| Installer exits 1 with a receipt present (the download failed) | `failed`, exit 2 |
| Model installed, runtime install fails, receipt present | `failed`, exit 2 |
| Installer exits 1 with no receipt | `declined`, exit 1 |

With a `failed` outcome, Kilix 95's `Controller` (with `durable_state` stubbed) left
the answer `None` and offered dictation again at the next start.

Planted defects: "always declined" was killed by
`test_an_accepted_licence_whose_download_fails_has_failed`. "Always failed" was killed
by `test_a_declined_licence_is_declined`. The residual cases are in N2 and N3.

#### M2: ONNX weights in the runtime

The new generation contains no `*.onnx` file and still transcribes correctly (see
check 5). Planted defects: no delete, delete without the refusal, and a delete limited
to `faster_whisper` were all killed. The residue is in N1.

#### M3: advisory paraphrase — still open

The builder's correction note is accurate. What users see (`whisper-card-caution`,
sha256 0e9d0d19…) is real text from the model card. It is also the same advisory the
determination points to "as for whisper-tiny-ggml".

It is not an adequate answer on its own, for three reasons:

1. **The owner accepted a described advisory.** The determination records that the
   owner was asked to accept "MIT with the card cautions carried as an advisory",
   and it describes those cautions as hallucination and accuracy variance. The owner's
   "I accept (MIT, advisory)" was therefore given against that description.
2. **The correction is not the owner's.** It is written by the builder, not the
   owner, and it sits outside the carrier.
3. **The cautions the owner was told about are shown nowhere.** No user will see the
   hallucination or accuracy cautions.

I do not think this blocks shipping. The licence, the licensors and the delivery are
all correct, and the advisory shown is genuine card text. But the owner should either
acknowledge the correction or ask for the other card caution to be added. I carry
this as a known issue.

#### L1: guard does not bind content to KILIX_REF

I replayed my round-1 forged carrier: content fork 39f8f16, a new `model.bin` URL, two
stand-in seat records, and every pin re-derived. The 9231407 guard refuses it with
"the carrier's content is not KILIX_REF's kilix-content gitlink".

Planted defects:

- The gitlink comparison replaced with `true`: killed by the subtests "host serves
  other content" and "carrier and pin agree on unserved content".
- An unreadable KILIX_REF tolerated: killed by "unreadable host tree".

#### L2: Whisper DELIVERY text

Whisper's DELIVERY now reads "The speech install command hands the download to that
model catalog and fetches no weights itself". That is true of `install_model()` at
a12be47.

Planted defect: an empty `CATALOG_INSTALLED_MODELS` was killed by AC-8 ("DELIVERY
claims a receipt check").

#### L4: untested defences

- The installer's dirty-source check is now tested. Replacing it with `true` is killed.
- The provider's fd-1 test exists only at ffc4e71. The pin stays at 15ef23b, whose
  runtime code is identical, because that commit is test-only.
- On ffc4e71, the `_protocol_stdout()` → `sys.stdout.buffer` mutation is killed by
  `test_serve_answers_on_the_private_stream`.

### New or residual findings

**Low**

**N1. The ONNX weights are still downloaded and kept on disk, and the runtime is
hardlinked to the uv cache.**

- **The weights.** After the 2d86841 install, the generation is clean. But
  `$HOME/.cache/uv/archive-v0/…/faster_whisper/assets/` still holds the two
  voice-activity `*_v5.onnx` files (713,415 and 532,505 bytes). The three onnxruntime
  sample models are also still there. So the install still fetches those weights and
  keeps them. They are unused, not in the image, and outside every census.
- **The hardlinks.** The "copied" runtime is not a copy. uv's default link mode
  hardlinks installed files to the cache. For example,
  `site-packages/kilix_whisper_stt/__init__.py` has a link count of 2, and
  `find -samefile` locates its twin in `~/.cache/uv/archive-v0/`. An in-place edit
  of the cache therefore changes the live runtime. This is the same user and the same
  trust level, so it is Low.
- **A possible fix.** Setting `UV_LINK_MODE=copy` and `--no-cache` (or a private
  cache that is deleted afterwards) would make the stamp literally true.

**N2. A few non-licence failures still permanently end the offer.**

- **How setup decides.** It judges "declined" by whether a receipt is absent.
- **When that is wrong.** A failure that happens before the licence screen writes
  anything still reads as "declined", and Kilix 95 then records "no". Examples:
  - catalog or trust-root errors;
  - an unwritable installer root;
  - an unreadable receipt authority, which raises `LicenseRefused`;
  - a runtime failure on hand-placed weights that no receipt covers.
- **The other half of the same gap.** Kilix 95 `prepare()` still maps a launcher exit
  of 1 with no result file to `declined`.
- **How much it matters.** All of these are rarer than the round-1 case.

**N3. One test gap.**

Reverting the fix in the first hand-off (the Vosk path, `if status != 0: raise
_installer_refused(...)` → `raise SetupDeclined`) leaves every test in these three
files green: `test_setup_default`, `test_weight_licence` and `test_stt_tool`.

**N4. A declined install confirmation can be read as a failure.**

With a covering receipt already on disk (a re-install), declining the
"Install this exact model?" prompt in `kilix models install` is reported as `failed`.
That keeps the offer open. This is the benign direction.

## Independent evidence

**1. The determinations are authentic.**

- **Byte comparison.** All six files under
  `releases/0.2.2-model-compliance/determinations/` are IDENTICAL to their originals
  under `~/research/gpu_terminal`. The originals are in
  `f104-vosk-licence-evidence-2026-09-14` (×2),
  `licence-evidence-vibevoice-asr-bitnet-2026-09-15` (×3) and
  `licence-evidence-whisper-small-en-2026-09-29`.
- **Unchanged from the parent.** Compared with 096dd9a, the only change is the added
  Whisper file.
- **Owner's words.** The Whisper file still contains "I accept (MIT, advisory)" and
  "faster-whisper (Recommended)".

**2. Independent regeneration.**

- **The run.** I ran the generator with the original content and licence repositories
  and the six original determination files in sorted order. It wrote 37 files.
- **The comparison.** `diff -r` against the committed carrier is byte-identical.
- **The pins.** `sha256(CARRIER.json)` =
  `9478ed218ddb172204621902ac6618a6dfa179eaf01d28e9e24b31e20841b7e2`. That equals
  `PLEBIAN_OS_VOICE_CARRIER_SHA256` in both `releases/0.2.2.env` and
  `releases/0.2.2.requirements`.

**3. The content-pin swap.**

- `interface_content_ref` = `PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF` = b8258fb. That is
  `git rev-parse 2d86841:third_party/kilix-content`.
- The guard now reads that gitlink from `KILIX_REPO` at `KILIX_REF` itself. The L1
  replay and the planted defects are above.
- The `PLEBIAN_OS_NATIVE_*` lines are unchanged from 096dd9a, and no carrier consumer
  reads the native content ref.

**4. Delivery.**

- The weight census tests are green in the suite, and I killed their mutations in
  round 1.
- The asset record and upstream pins are unchanged: content b8258fb, and the five
  member digests I verified against the upstream host in round 1.
- The provider install adds no model files to the runtime. The residue is N1.

**5. Runnable.**

- **The install.** The 2d86841 installer, run in a sandbox with a temp HOME,
  KILIX_DATA_HOME and GPU_TERMINAL_SOURCE_HOME, exited 0 and wrote the new stamp.
- **The model files.** I verified the bench model's five files against the pinned
  sha256.
- **The runs.** I ran everything under `unshare -rn`, with no network:
  - kilix-voice a12be47 `WhisperStt` transcribed p01–p08 in 14.9 s, including the
    model load. The output is identical to round 1: exact apart from number formatting,
    "Killix/plebeian" and "paint" for "pane".
  - The provider CLI transcribed p09, p13 and p16 exactly.
  - Silence, a pop and noise all gave `''`.
  - Replacing a file by rename during a session still loaded the held bytes. An
    in-place rewrite discarded the transcript. `close()` left no child running.

**6. Licensing.** The first-use screen inputs are unchanged, because content b8258fb
and licence 993c8ec are still pinned. The advisory issue is M3, still open.

**7. Code.**

- **kilix-voice.** The full suite at a12be47 passes: 1232 tests, 0 failures,
  3 skipped. M1 fix mutations are above.
- **Installer.** All seven mutations were killed.
- **Provider.** The fd-1 test is present at ffc4e71 and kills its mutation.
- **Kilix 95.** Its logic is unchanged. A `failed` outcome keeps the offer open.

**8. OS suite on 9231407.**

- **How I ran it.** In a fresh clone, with `env -i HOME=<tmp> PATH=/usr/bin:/bin
  PYTHONDONTWRITEBYTECODE=1`, the five overrides from the brief
  (`PLEBIAN_OS_KILIX_REPO` = whisper-host at 2d86841), and no `__pycache__`.
- **The result.** 900 tests ran: failures=6, errors=22, skipped=1. That is three more
  errors than round 1, one for each of the three new planted-defect subtests.
- **Every failure is the expected missing receipt or seat.** All 28 are in
  `test_model_compliance_carrier`. Each one is either the missing
  `ACCEPTANCE.json` / `seats/`, or a planted-defect subtest that the guard's
  "ACCEPTANCE.json is missing" refusal pre-empts.
- **With stand-in seats.** When I regenerated the carrier from the real content with
  two stand-in seat records and re-pinned it, all 13 carrier tests passed.

VERDICT: ship with known issues
