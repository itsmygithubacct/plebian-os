# Seat A review: Plebian-OS 0.2.3 RC5 model-compliance carrier, round 5 (Playalong default models)

Seat: A. Reviewer: this session. Date: 2026-11-09 (UTC). This record is complete in itself and replaces seat A's round-4 record in the carrier.

Candidate CARRIER.json sha256, as this session computed it: `4fdbffce1f96882bbdc16724b3472895e10296ec603d1441249ff3a2e7470ebc`.
DEFAULT-MODELS.json field "sha256", as this session read it in the candidate carrier: `e00614bf726154d09668820c061cbbcb402239a445bde666b0568d36f01528a6`.

Candidate:
- kilix `c90d48efab8c79a0011c9737fa9747f22fe98837`, one commit on 9e58d314;
- plebian-os `ee97037e343ac0c474bdbb9bc319d17509f8a5cf`, one commit on 8f8af4fc;
- kilix-license f8486ed3, kilix-content c8f0b0f5, kilix-playalong a11a0219, kilix-needle a887e2fa and kilix-voice 1a4e63b1, all unchanged since round 4.

## Summary

The blocking defect from seat A's round-4 record is fixed. After a failed download of a Playalong default, the next run of `provision/install-image-models.py` now treats the receipt without files as "not installed" and tries again. This session ran that sequence against the real Kilix, with the installer CLI that `provision/plebian-os-update.sh` uses:
- a fresh offline install;
- an online run with no network, whose downloads failed;
- an online run with network, which downloaded, verified and installed both Demucs and medium.en and exited 0;
- a further run, which found everything verified.

The archive route after a failed Demucs download also works. 8f8af4fc's installer still exits 1 on the same states. The command model still stops on an incomplete install, as it did at 6942536f.

The carried medium.en DELIVERY is now true of the candidate, sentence by sentence.

Seat B's round-4 item (1) is also fixed: refusing only large-v3's licence no longer declines the three defaults. So is the mirror case the builder sessions found. A refused default licence on any wizard page now declines the defaults.

The candidate differs from round 4 only as the two claims state. The carrier is byte-identical. Every pin agrees. The generator check passes. The full plebian-os suite shows AC-7 as the only failure that is not environmental, as the brief expects.

What remains is non-blocking:
- the Demucs distribution entry's upgrade sentence (seat B's item 2);
- provisioning that never downloads during setup (seat A's known issue 2);
- the new refused-licence decline, which the real wizard cannot reach for these four MIT records.

The verdict is "ship with known issues".

## Eligibility

The builder session launched this pane for round 4 with `kilix @ launch` at 2026-11-08T23:27:12Z. It wrote the round-5 brief at 2026-11-09T00:33:35Z. This session's first round-5 command ran at 2026-11-09T00:33:42Z.

This session did not author the carrier or either fix. It wrote nothing in kilix c90d48ef, plebian-os ee97037e, or any earlier candidate commit. Nor did it write anything in the carrier, its generator, its determinations, the kilix-license records, the kilix-content catalog, Kilix Playalong, or any other repository under review. It has written only under its own work directory and this file.

The review was read-only:
- no commit, push or publication, and no ACCEPTANCE.json;
- no reading of the other seat's directory, the builders' notes, or earlier seat records outside the carriers;
- no other agents started;
- every licence receipt it caused went into a receipt store inside its work directory.

Every Kilix, kilix-content, kilix-license and plebian-os command ran under `env -i`. HOME, TMPDIR, KILIX_STORAGE_HOME, KILIX_DATA_HOME (inside KILIX_STORAGE_HOME), GPU_TERMINAL_HOME, GPU_TERMINAL_SETTINGS_FILE, KILIX95_STATE_HOME and KILIX_LICENSE_RECEIPTS all pointed inside `/home/pleb/storage/research/kilix-playalong/023-rc5-audio-models-20261108/r4/seats/a/work`, written `W` below. KILIX_STATE_LIBRARY pointed at a libkilix-state that this session built with Kilix's `scripts/build-state-library.sh` into `W/storage`. Tests ran from a virtual environment at `W/venv` holding pytest and setuptools. Each scenario used a fresh env tree `W/<name>`, set up by `W/mkenv.sh`.

## Sources and the delta

This session fetched its round-4 clones in `W/src` from the public repositories.
- `git cat-file -t` printed `commit` for c90d48ef and ee97037e.
- `git branch -r --contains` put each one on `origin/work/0.2.3-rc5-playalong-models-20261108`, and `git rev-parse` showed each as that branch's tip.
- `git log --oneline 9e58d314..c90d48ef` printed only `c90d48e Decline Playalong's defaults on a refused licence, not on large-v3 alone`.
- `git log --oneline 8f8af4fc..ee97037e` printed only `ee97037 Retry Playalong defaults after a failed download, and pin Kilix c90d48ef`.
- Kilix's `third_party/kilix-content` gitlink at c90d48ef is `c8f0b0f51966925c5872c70c246434cce6784982` (`git ls-tree`), unchanged.

### Kilix 9e58d314 to c90d48ef, file by file

`git diff --stat` printed four files, 120 insertions and 14 deletions.

**config/model_wizard.py**
- `record()` gains a keyword `refused=()`, stored as `saved[segment]['refused']` only when non-empty.
- `finish()` computes `refused = [model for model in plan['models'] if model in declined]` for each page and passes it to all four `record` calls: no models; planned yes; yes after activation; no after a failed activation. So the list is written whatever the page's final answer.
- The Playalong page note adds "Refusing one of their licences in this wizard also declines them" and "refusing its licence declines nothing else" for large-v3.

`declined` here is `consent_and_install`'s set: selected models whose licence groups were not all accepted. This session read `wizard_licenses.consent_and_install` (unchanged in this range). Install failures are reported separately, through `InstallFailures.failures`, so the refused list holds licence refusals only and never a failed download.

**config/playalong_models.py**
- `_wizard_answer()` becomes `_wizard_decline()`, which:
  - iterates every saved page;
  - raises `ValueError('Invalid saved wizard answer.')` for a `refused` value that is not a non-empty list of strings;
  - returns `the model wizard refused the licence of …` if any `DEFAULT_MODELS` entry was refused;
  - otherwise returns the old Playalong-page reason only when that page's answer is `no` and it has no `refused` key.
- `declined()` calls it first, then reads the setting as before.
- The module docstring names the new trigger.

**README.md**
- The two-way decline list gains "or refuse the licence of any of the three on a model wizard page (refusing only Whisper large-v3's licence declines nothing)".
- "Plebian-OS installs nothing when the answer cannot be read" becomes "installs none of the three". That resolves one of seat A's round-4 observations.

**tests/test_playalong_models.py** adds seven tests:
- `test_refusing_only_large_v3s_licence_declines_nothing`
- `test_refusing_a_default_licence_on_the_page_declines`
- `test_refusing_a_default_licence_declines_even_when_the_page_ends_yes`
- `test_refusing_a_default_licence_on_another_page_declines`
- `test_a_page_with_no_refusal_records_none`
- `test_a_page_answered_no_still_declines`
- `test_an_unreadable_refusal_is_never_read_as_install`

`git diff --quiet 9e58d314 c90d48ef -- config/content_models.py config/default_models.py config/wizard_licenses.py kilix_sdk third_party` exited 0. `scripts/patch-whisper-medium-model.py` is outside the diff and still exists at c90d48ef. Claim 1 holds, with no other difference.

### plebian-os 8f8af4fc to ee97037e, file by file

`git diff --stat` printed seven files, 110 insertions and 18 deletions.

**provision/install-image-models.py**
- Adds `_playalong_installed(cm, asset_id)`. It returns `_installed(cm, asset_id)`, but on `cm._api().InstallError` it prints `<asset> is not completely installed (<error>); installing it again.` to stderr and returns False.
- `_install_from_image`, `install_demucs` and `install_whisper_medium` each replace their one `_installed` call with it.
- An AST comparison of every function printed:
  - only those three functions and the new one changed against 8f8af4fc;
  - `main` and `fetch_default` are identical to 8f8af4fc;
  - `install_command_model` and `_installed` are identical to 6942536f.
- `cm._api()` is the imported `kilix_content` module. Its `InstallError` is the RuntimeError subclass that `content_models._verify` lets through when a receipt exists but its files do not. `SetupError` (no receipt) is still caught by `_installed` itself.

**tests/test_model_compliance_carrier.py**: AC-8's `playalong_installer_gaps` adds two checks:
- each of the three functions must call `_playalong_installed` and not `_installed`;
- `_playalong_installed` must handle `cm._api().InstallError` by returning False.

It adds two plants to match.

**tests/test_image_models.py** adds three tests:
- `test_the_upgrade_after_a_failed_download_downloads_again`
- `test_an_incomplete_image_model_is_installed_again_from_the_image`
- `test_the_command_model_still_stops_on_an_incomplete_install`

**releases/0.2.3.env**
- `KILIX_REF=c90d48efab8c79a0011c9737fa9747f22fe98837`.
- Its comment now starts "Advanced from 9e58d31473d8de5ea12a6005afb18665fa0b6e2c". That is correct: 9e58d314 was the previous value.

**releases/0.2.3-command-model.json**: `source_pins.kilix` moves to c90d48ef. Nothing else in the file changes.

**releases/0.2.3-notes.md**: the pin table's KILIX_REF moves. The Playalong paragraph describes the retry ("the receipt it leaves without files reads as 'not installed', not as a failed upgrade"), the refused-licence decline, "Refusing only Whisper large-v3's licence declines nothing", and "none of the three is installed" for an unreadable answer.

**CHANGELOG.md**: the RC5 paragraph says the same and names Kilix `c90d48ef`.

`git diff --quiet 8f8af4fc ee97037e` exited 0 for:
- `releases/0.2.3-model-compliance` and `releases/0.2.3.requirements`;
- `build` and `preseed`;
- `provision/plebian-os-update.sh` and `provision/plebian-os-provision.sh`;
- `provision/playalong-models.json`, `demucs-model.json`, `command-model.json`, `default-models.json` and `basic-pitch-model.json`.

Claim 2 holds, with no other difference. The KILIX_REF moves are mechanical consequences of claim 1.

### Carrier equality

```
git archive ee97037e releases/0.2.3-model-compliance | tar -x -C W/tmp/exp5
diff -r W/tmp/exp5/releases/0.2.3-model-compliance <seat-inputs>/candidate-carrier
```

This printed nothing. The export at ee97037e is identical to the round-4 candidate carrier, including seats/ and ACCEPTANCE.json. `sha256sum` printed:
- CARRIER.json `4fdbffce1f96882bbdc16724b3472895e10296ec603d1441249ff3a2e7470ebc`;
- ACCEPTANCE.json `89e5abff8e25136adec5ac92d8a0cccbd74d5b606177c96f76db939999b0f0a1`.

`json.load(...)['sha256']` of DEFAULT-MODELS.json printed `e00614bf…28a6`.

## Required identities (round 4, unchanged)

The delta touches no repository, file or pin these come from. kilix-license, kilix-content and kilix-playalong are at the same commits. In plebian-os, `provision/demucs-model.json`, `provision/playalong-models.json`, `build/` and the carrier have empty diffs (above). So these round-4 results stand as measured then:

| Identity | Round-4 measurement | Result |
| --- | --- | --- |
| Candidate CARRIER.json | `sha256sum`, re-run this round | `4fdbffce…0ebc`, matches |
| Approved CARRIER.json | `sha256sum` | `0e544b97…ead7`, matches |
| DEFAULT-MODELS.json "sha256" | read in both carriers, re-read this round | `e00614bf…28a6`, matches |
| LFM2 notice record | kilix-license `LicenseRecord.digest` at 80aab439 and f8486ed3 | `e4d08e2c53ab…5016`, decision `record`, unchanged |
| large-v3 model.bin | upstream API tree at edaa852e | size 3087284237, oid `69f74147…d4f1`, matches the record |
| large-v3 small files and card | fetched at edaa852e; `stat`, `sha256sum`, `git hash-object` | equal to the determination, `whisper_large_v3.FILES` and the catalog; card 2052 bytes `39e96252…`, `license: mit` |
| Demucs weights | fetched from the pinned url | 54996327 bytes, `34c22ccb…2ddd`, matches |
| Demucs LICENSE at eeac1d15 | fetched | 1087 bytes, `cf9b1782…8173`, byte-identical to the owner's copy |
| Demucs image archive | built twice with `--build-demucs-archive` | 55009280 bytes, `904731cf…5c2b` both times, `cmp` silent, matches `provision/demucs-model.json` |

In round 5, this session's own copy of the Demucs weights and LICENSE was re-used for the archive runs. `cmp` of the installed `notices/LICENSE-mit.txt` against that LICENSE printed nothing (see "Demucs route").

## Round-4 checks for claims 1 to 6, carried forward

**Claim 6, the carrier files.** Unchanged, because the carrier is byte-identical (above). It differs from the approved carrier exactly as round 4 found:
- BINDINGS.sha256, CARRIER.env, CARRIER.json and SHA256SUMS changed;
- whisper-medium-en/DELIVERY, LICENCE-RECORD.json (`determinations_sha256` only) and NOTICE changed;
- PLAYALONG-MODELS.json and the medium owner distribution record (2515 bytes, `6798bb89…0a65`) added.

CARRIER.json has five changed fields and no entry for Demucs, Basic Pitch or large-v3. ACCEPTANCE.json still names the round-3 seats.

**Claim 1, kilix-license 80aab439 to f8486ed3.** Unchanged, because kilix-license is still f8486ed3. The round-4 results stand:
- record digests from `load_determined_records()`: 43 records, then 44, with one added line, `faster-whisper-large-v3 ee7369d9417178ee39b23d23f5159d602207d37816adba336a039866992cb172 accept`;
- Demucs `02f182d7…` and medium `c33e44c1…` identical at both commits;
- the large-v3 record pins the MIT text, the record's two licensors, and the owner record (3218 bytes, `8d8c1cf3…1311`);
- `tools/generate_records.py --check` exits 0;
- this session's mutations of each family's `owner_record` or `distribution` are refused by the generators.

The round-5 runs below wrote receipts under exactly these digests (`02f182d7`, `a8cc7437`, `c33e44c1`, `e4d08e2c`, `ee7369d9`).

**Claim 2, kilix-content de2764f8 to c8f0b0f5.** Unchanged, because kilix-content and the Kilix gitlink are still c8f0b0f5. The catalog adds only faster-whisper-large-v3, with its six pinned files and its MIT notice, and changes only the playalong ref. `_CATALOG_SHA256` equals the catalog. The nine kilix-content test failures are environmental and the same at de2764f8.

**Claim 3, Kilix to 9e58d314.** Superseded by c90d48ef for `config/playalong_models.py`, `config/model_wizard.py` and the README section, all re-tested below. The rest of 9e58d314 is outside the delta and stands as round 4 found it:
- the split_cli docstrings;
- the gitlink;
- `list --json` printing the three defaults and `optional ["faster-whisper-large-v3"]`;
- the Playalong page not pre-selecting large-v3.

**Claim 4, Kilix Playalong a11a0219.** Unchanged, because the catalog still selects a11a0219. Every provider runs `licensed.verify` (`kilix models verify <asset>`) and passes only the verified directory. The Whisper worker always uses `local_files_only=True`, and no code path downloads weights itself.

**Claim 5, plebian-os 6942536f to 8f8af4fc.** Superseded by ee97037e for the four installer functions above, re-run below. Everything else stands:
- the Demucs archive's layout: two members, mode 0644, uid/gid 0, mtime 0, ustar;
- its refusal of an existing output and of a truncated input;
- the remaster harness, which refused an all-zero archive and on the staging path fetched the pinned url under a byte ceiling, built and re-verified the archive, and staged `plebian-os/demucs-htdemucs-6s.tar` with sha256 `904731cf…5c2b`;
- the preseed copy to `/target/usr/local/share/plebian-os/`, root, 0644;
- `plebian-os-provision.sh` running the installer with `--offline`.

These all rest on build/, preseed and the provisioning script, whose diffs are empty.

## Round-5 installer runs against the real Kilix

These used Kilix c90d48ef with its content submodule at c8f0b0f5, plus the host's read-only staged command-model archive. Basic Pitch came from the repository's vendored bundle. The command line is the one `provision/plebian-os-update.sh` uses, `python3 provision/install-image-models.py --kilix W/src/kilix`, with `--offline` where provisioning adds it. `unshare -rn` gives a run no network.

### Sequence A: medium.en and Demucs by download (tree `W/t5`, no image archive)

**A1, fresh offline install.** `strace -f -e trace=connect … --kilix W/src/kilix --offline` printed:

```
Basic Pitch installed: basic-pitch-icassp-2022-onnx
Demucs: the installation media did not supply its archive; the first online upgrade downloads it.
Command model: recording the published notice terms for lfm2-kilix-commands
Command model installed: lfm2-kilix-v5e1-wse-20261106.9
Whisper medium.en is not in the image; the first online upgrade downloads it.
```

It exited 0 with zero AF_INET or AF_INET6 connects. The receipts were `a8cc7437` (Basic Pitch) and `e4d08e2c` (command model).

**A2, online with no network.** `unshare -rn … --kilix W/src/kilix` printed:

```
Demucs was not installed (offline: check the network or proxy, then re-run; download resumes); the next upgrade tries again.
Whisper medium.en was not installed (offline: check the network or proxy, then re-run; download resumes); the next upgrade tries again.
Basic Pitch already verified; no bundle install needed.
Command model already verified; no archive install needed.
```

It exited 0. The receipts were `02f182d7 a8cc7437 c33e44c1 e4d08e2c`, with no Demucs or medium.en asset and a `.partial` directory. This is the state that made 8f8af4fc fail. This session copied it to `W/t5snap`.

**A3, online with network, on the A2 state.** `strace -f -tt -e trace=connect,rename … --kilix W/src/kilix` ran from 2026-11-09T00:36:55Z to 01:07:15Z. It printed:

```
demucs-htdemucs-6s is not completely installed (could not open supplied file: W/t5/storage/data/desktop-apps/assets/demucs-htdemucs-6s/models/5c90dfd2-34c22ccb.th); installing it again.
faster-whisper-medium-en is not completely installed (could not open supplied file: W/t5/storage/data/desktop-apps/assets/faster-whisper-medium-en/README.md); installing it again.
Basic Pitch already verified; no bundle install needed.
Demucs installed: demucs-htdemucs-6s
Command model already verified; no archive install needed.
Whisper medium.en installed: faster-whisper-medium-en
exit=0
```

In the trace:
- The two Playalong receipts are the ones A2 recorded before its own failed downloads. Their files are dated 00:36:34Z (Demucs) and 00:36:40Z (medium.en), before A3 started, and A3 has no rename into the receipt store.
- A3's first AF_INET connect (the resolver) came at 00:36:56Z, after both receipts existed.
- The Demucs asset was renamed into place at 00:37:23Z and the medium.en asset at 01:07:12Z.
- No connect occurred during the command-model step.

Afterwards, `python3 config/content_models.py verify` in the same tree printed:
- `declared_files_verified 2, manifest 21c129345826` for Demucs;
- `6, manifest 133afbde25b1` for medium.en;
- `3, manifest 231f6d8ed0fd` for Basic Pitch.

The installed Demucs weights hash to `34c22ccb…`. The installed `notices/LICENSE-mit.txt` is byte-identical to the upstream LICENSE (`cmp` silent). Receipts `02f182d7…-21c12934….json` and `c33e44c1…-133afbde….json` are decision `accept`, under the round-4 record digests. `verify faster-whisper-large-v3` printed `SetupError: no stored receipt covers this exact model and manifest`, and the tree holds no `ee7369d9` receipt.

This is the Demucs download route after a failed download, as well as medium.en's: no image archive, a failed download in A2, then a download in A3.

**A4, a further run.** `strace -f -e trace=connect … --kilix W/src/kilix` printed:

```
Basic Pitch already verified; no bundle install needed.
Demucs already verified; no download needed.
Command model already verified; no archive install needed.
Whisper medium.en already verified; no download needed.
exit=0
```

It printed no "not completely installed" note and had zero AF_INET or AF_INET6 connects.

### 8f8af4fc on the same states

On a copy of the post-A2 state (`W/t5old`), 8f8af4fc's installer (`W/plant` at 8f8af4fc, the same Kilix) printed `Basic Pitch already verified; no bundle install needed.` both without network (`unshare -rn`) and with it. Each time it then raised a traceback through `_install_from_image` → `_installed` ending `kilix_content.install.InstallError: could not open supplied file: W/t5old/storage/data/desktop-apps/assets/demucs-htdemucs-6s/models/5c90dfd2-34c22ccb.th`, and exited 1. The post-B2 state with `--demucs W/arch/one.tar` (below) gave the same InstallError and exit 1. The round-4 defect is therefore still present at 8f8af4fc and absent at ee97037e on identical states.

### An offline run still downloads nothing

On another copy of the post-A2 state (`W/t5off`), with the network present, `strace -f -e trace=connect … --kilix W/src/kilix --offline` at ee97037e printed:

```
demucs-htdemucs-6s is not completely installed (could not open supplied file: …/demucs-htdemucs-6s/models/5c90dfd2-34c22ccb.th); installing it again.
faster-whisper-medium-en is not completely installed (could not open supplied file: …/faster-whisper-medium-en/README.md); installing it again.
Basic Pitch already verified; no bundle install needed.
Demucs: the installation media did not supply its archive; the first online upgrade downloads it.
Command model already verified; no archive install needed.
Whisper medium.en is not in the image; the first online upgrade downloads it.
```

It exited 0 with zero AF_INET or AF_INET6 connects. The receipts were unchanged. A1 above also had zero connects.

### Demucs route: a failed download, then the image archive (tree `W/t6`)

B1, the fresh offline install, and B2, the online run with no network, printed exactly what A1 and A2 printed, and both exited 0. B2 left receipts `02f182d7 a8cc7437 c33e44c1 e4d08e2c` and no Demucs asset.

B3 was `strace -f -e trace=connect unshare -rn … --kilix W/src/kilix --demucs W/arch/one.tar`, as an upgrade of a machine whose image supplied the archive. It printed:

```
demucs-htdemucs-6s is not completely installed (could not open supplied file: …); installing it again.
faster-whisper-medium-en is not completely installed (could not open supplied file: …); installing it again.
Whisper medium.en was not installed (offline: check the network or proxy, then re-run; download resumes); the next upgrade tries again.
Basic Pitch already verified; no bundle install needed.
Demucs installed: demucs-htdemucs-6s
Command model already verified; no archive install needed.
```

It exited 0 with zero inet connects. `python3 config/content_models.py verify demucs-htdemucs-6s` then printed `"declared_files_verified": 2, "manifest_digest": "21c129345826c583e5327902dde4e7fe610282c2b0594bc058afb003ec8b03ff"`. `cmp` of the installed `notices/LICENSE-mit.txt` against the upstream LICENSE printed nothing. The Demucs download route after a failed download (A3) is reported above.

### The command model still stops on an incomplete install

Tree `W/t7` had `KILIX_PLAYALONG_MODELS=0` set, so only the command model is in play. A first run under `unshare -rn` printed `Playalong's default models skipped: KILIX_PLAYALONG_MODELS=0 in W/t7/gpuhome/settings.conf` and `Command model installed: lfm2-kilix-v5e1-wse-20261106.9`, exit 0, receipt `e4d08e2c`. This session then deleted the command model's asset directory and kept its receipt.

The next run printed the same "skipped" line, then a traceback through `main` → `install_command_model` ending `kilix_content.install.InstallError: could not open supplied file: …`, exit 1, at:
- ee97037e;
- 8f8af4fc;
- 6942536f (which has no "skipped" line, because it has no Playalong step).

So the command model's behaviour is unchanged. ee97037e prints no "not completely installed" note for it, matching the claim that `install_command_model` keeps `_installed`.

## The wizard, with its real code and a stubbed licence step

`W/wizharness.py` imports Kilix's real `config/model_wizard.py` and `wizard_licenses.py`. It replaces only `wizard_licenses.consent_and_install` with a stub that returns (selected minus REFUSE, selected ∩ REFUSE), as if the listed licences were refused. It also replaces the default-voice step and the external command runner with no-ops. It calls the real `apply(page, models, answer)` and `finish(input_fn=yes)`, prints the saved answers, and then runs `python3 config/playalong_models.py declined --json` in a fresh env tree (`W/wizrun.sh`).

At c90d48ef:

| Scenario | Saved by the real wizard | `declined --json` | Exit |
| --- | --- | --- | --- |
| S1: Playalong page yes [large-v3], large-v3's licence refused (seat B's case) | `kilix-playalong: answer no, models [], refused [faster-whisper-large-v3]` | `{"declined": false, "reason": null}` | 3 |
| S2: Playalong page yes [Basic Pitch, large-v3], Basic Pitch refused | `answer yes, models [faster-whisper-large-v3], refused [basic-pitch-icassp-2022-onnx]` | `declined true`, `the model wizard refused the licence of basic-pitch-icassp-2022-onnx` | 0 |
| S3: dictation page yes [medium.en], medium.en refused | `dictation: answer no, models [], refused [faster-whisper-medium-en]` | `declined true`, `… refused the licence of faster-whisper-medium-en` | 0 |
| S4: kilix-split page yes [Demucs], Demucs refused | `kilix-split: answer no, refused [demucs-htdemucs-6s]` | `declined true`, `… refused the licence of demucs-htdemucs-6s` | 0 |
| S5: Playalong page answered no | `answer no, models []` | `declined true`, `the model wizard's Playalong page was answered no` | 0 |
| S6: Playalong page yes [Basic Pitch, large-v3], nothing refused | `answer yes, models [both]`, no `refused` key | `declined false` | 3 |
| S7: `KILIX_PLAYALONG_MODELS=0`, no wizard state | `{}` | `declined true`, `KILIX_PLAYALONG_MODELS=0 in W/wz/S7/gpuhome/settings.conf` | 0 |
| M-string: hand-written `refused: "x"` | as written | `cannot read whether Playalong models were declined: Invalid saved wizard answer.` | 4 |
| M-empty: `refused: []` | as written | same message | 4 |
| M-int: `refused: [1]` | as written | same message | 4 |

As a contrast, this session ran S1 to S4 with 9e58d314's `model_wizard.py` and `playalong_models.py` in an overlay:
- S1 saved `answer no, models []` and printed `declined true … Playalong page was answered no` (seat B's item 1);
- S2, S3 and S4 each printed `declined false`, exit 3 (the mirror case the builder sessions describe).

c90d48ef fixes both.

On the installer side, `install-image-models.py --offline` under `unshare -rn` at ee97037e with c90d48ef:
- a wizard "no" state printed `Playalong's default models skipped: the model wizard's Playalong page was answered no` and installed only the command model;
- a malformed refused list printed `… skipped: whether this machine declined them cannot be read (Invalid saved wizard answer.)` and installed only the command model;
- the S1 state installed Basic Pitch and deferred Demucs and medium.en.

The installer reads Kilix's answer and does not interpret the list itself.

### The real licence step

`W/wizreal.py` uses the real `consent_and_install`. It applies `yes` on the Playalong page with [large-v3], and then with [Basic Pitch, large-v3], and calls `finish` with an `input_fn` that records every prompt and answers "no". It ran under `unshare -rn`. Both runs printed:
- `prompts asked: []`;
- a page saved as `answer yes … phase planned`;
- standard-policy receipts written for the chosen models (`ee7369d9`, and `a8cc7437`);
- `finish raised: SetupIncomplete … offline`, because there was no network;
- `{"declined": false, "reason": null}`.

`lic.standard_policy_eligible(record)` is True for the records of Basic Pitch, Demucs, medium.en and large-v3, and False for the LFM2 record. `consent_and_install` skips eligible records before it asks anything (`if lic.standard_policy_eligible(record): … continue`). So for the four MIT models, the real wizard never shows a licence question that could be refused, and the new `refused` list stays empty. That is true at c90d48ef and at 9e58d314 alike; `wizard_licenses.py` is unchanged. The new decline is a correct guard for any future default whose record needs an answer, but no current wizard path reaches it (see "Observations").

### `declined()` against the owner's opt-out words

The owner's words: "Skip the install if the wizard says no or if settings.conf sets the key to 0."
- **"The wizard says no."** A Playalong page answered no with no refused list declines (S5). A page saved as "no" only because large-v3's licence was refused does not (S1). That page's own answer was yes, and the "no" came from the licence screen. The comment in `record` says so: "A 'no' that carries them came from those screens, not from the page itself".
- **"The key to 0."** `=0` declines (S7), alone or together with any wizard state. Other off spellings still decline too.
- **New trigger.** A refused licence of a default declines. The owner's words do not name it. It only ever installs less, never more, and it follows from a refusal of terms, which no install may override. It does not conflict with the owner's decision.
- **Unreadable state.** It raises, and the installer installs none of the three (M-*).

`declined()` honours both of the owner's opt-outs and adds nothing that installs.

## Kilix tests and planted defects at c90d48ef

`python -m pytest -q tests/test_playalong_models.py tests/test_model_wizard.py` printed `59 passed, 35 subtests passed`. `tests/test_playalong_models.py -v` lists 15 tests, all PASSED, the seven new ones included.

This session planted four defects of its own, one at a time, in a copy (`W/kplants.py`):

| Plant | Caught by |
| --- | --- |
| K1: only the Playalong page's `refused` is read | test_refusing_a_default_licence_on_another_page_declines |
| K2: a large-v3 refusal also declines (`DEFAULT_MODELS + OPTIONAL_MODELS`) | test_refusing_a_default_licence_on_the_page_declines, test_refusing_only_large_v3s_licence_declines_nothing |
| K3: a malformed list is skipped instead of raising | test_an_unreadable_refusal_is_never_read_as_install (three subtests) |
| K4: refusals dropped when the page ends yes | test_refusing_a_default_licence_declines_even_when_the_page_ends_yes |

All four were caught.

## AC-8 and plebian-os planted defects at ee97037e

`python -m pytest tests/test_image_models.py tests/test_mixed_model_delivery.py` printed `46 passed, 39 subtests passed`. `python -m pytest tests/test_model_compliance_carrier.py -k "delivery_statement_is_true or command_model_records_needle"` printed `2 passed`. The sibling variables were set, PLEBIAN_OS_KILIX_BONSAI_REPO included.

Calling the test module's own helper `playalong_installer_gaps` (`W/ac8probe.py`):
- On ee97037e's installer it printed `[]`.
- On 8f8af4fc's installer it printed four gaps:
  - `_install_from_image does not retry an install a failed download left incomplete`;
  - the same for `install_demucs`;
  - the same for `install_whisper_medium`;
  - `an install a failed download left incomplete stops the next upgrade`.
- AC-8 plants six defects itself, its four from round 4 and its two new ones (`if _playalong_installed(cm, WHISPER_MEDIUM):` reverted, and the InstallError handler changed), and asserts that each produces a gap (`assertTrue(playalong_installer_gaps(planted))`). That test passed. Calling the helper on the two new plants printed their gaps.
- `delivery_gaps` on the carrier printed `[]`.

This session planted four defects of its own in the new installer code, one at a time, in the scratch worktree `W/plant` (`W/qplants.py`). It re-ran its eight round-4 plants (`W/plants.py`) on ee97037e:

| Plant | AC-8 | Caught by test_image_models.py / test_mixed_model_delivery.py |
| --- | --- | --- |
| Q1: an incomplete install reads as installed (`return True`) | fails (caught) | test_an_incomplete_image_model_is_installed_again_from_the_image, test_the_upgrade_after_a_failed_download_downloads_again |
| Q2: the command model also uses `_playalong_installed` | passes | test_the_command_model_still_stops_on_an_incomplete_install |
| Q3: `except Exception` instead of InstallError | fails (caught) | none |
| Q4: the image route reverted to `_installed` | fails (caught) | test_an_incomplete_image_model_is_installed_again_from_the_image |
| P1: offline Demucs downloads | passes | test_image_models_first_and_the_large_download_last |
| P2: an unreadable answer means install | passes | test_the_kilix_answer_decides |
| P3: no manifest check before a download | passes | test_a_download_runs_only_for_the_pinned_asset |
| P4: download before receipt | fails (caught) | test_online_downloads_what_the_image_did_not_supply, test_the_upgrade_after_a_failed_download_downloads_again |
| P5: a failed download is fatal | passes | test_a_failed_download_is_reported_and_does_not_stop_the_run, test_the_upgrade_after_a_failed_download_downloads_again |
| P6: no standard-policy gate | passes | test_demucs_refuses_custom_terms_before_a_download |
| P7: the wizard "no" ignored | passes | test_the_kilix_answer_decides |
| P8: Basic Pitch outside the guard | fails (caught) | test_a_declining_machine_still_gets_the_command_model |

Every plant is caught by at least one of AC-8 or the installer tests. AC-8 alone catches Q3; the installer tests alone catch Q2. AC-8 reads the installer's structure statically, as in round 4.

## The medium.en DELIVERY, sentence by sentence, at ee97037e

The carried DELIVERY is unchanged (the carrier is byte-identical).
1. "mode: playalong-default-upstream-download". True.
2. "This model's weights are not present in the image or downloaded by provisioning." True:
   - the remaster stages only the Basic Pitch, Demucs and default-model archives (build/ unchanged);
   - provisioning always passes `--offline`;
   - the offline runs above had zero connects, including the run on a post-failure state, where the retry does not override `--offline`.
3. "Plebian-OS installs it by default for Kilix Playalong: when it is missing, an online upgrade downloads it from [its upstream host] and verifies it against the pinned digests before installation." True, shown by A3: medium.en was downloaded, verified (6 files, manifest `133afbde…`) and only then renamed into place.
4. "The upgrade first records a local standard-policy receipt; build-time receipts are never distributed." True. In A2 the medium.en receipt `c33e44c1…` was recorded before the failed download, and A3 downloaded under that same receipt, whose file predates A3's first connect. The image carries no receipt for it.
5. "It is not installed when the model wizard's kilix-playalong page was answered no, or when KILIX_PLAYALONG_MODELS=0 is set in the shared settings file." **Still accurate**, as two sufficient conditions:
   - a page the user answered no declines (S5, and the installer's "skipped" line);
   - `=0` declines (S7, and tree `W/t7`).

   The sentence does not say "only when", so the new third trigger does not make it false. It is no longer the complete list, though. A refused default licence also declines, and the sentence omits that, as it omits the unreadable case. For these MIT records no real wizard path writes a refusal, so today the omission changes no outcome. In the one state where a stored "no" does not decline, a "no" carrying only large-v3's refusal, the user's page answer was yes. And that state, too, cannot be reached through the real wizard today. See "Observations".
6. "A failed download installs nothing, and the next upgrade tries again." **True at ee97037e** (false at 8f8af4fc). A2 and B2 installed nothing and exited 0; A3 tried again and installed, exit 0; 8f8af4fc exits 1 on the same state.
7. "A user can also install whisper-medium-en directly." and the route sentences: "No install route downloads it until a kilix-license receipt covers it", the model catalog recording the receipt, the speech install command handing the download to it at kilix-voice 1a4e63b1, and the patcher `scripts/patch-whisper-medium-model.py` at the release's KILIX_REF. All true. The patcher exists unchanged at c90d48ef, kilix-voice is unchanged, and AC-8 asserts both patcher sentences (it passed).

Every sentence of the carried medium.en DELIVERY is true of ee97037e.

## Large-v3 routes

Unchanged in substance. faster-whisper-large-v3 is not in:
- `provision/playalong-models.json` (unchanged);
- `playalong_models.DEFAULT_MODELS`, `config/default_models.py` or `provision/default-models.json` (unchanged);
- the image (build/ unchanged).

The wizard page does not pre-select it. After A1, A2, the offline post-failure run, B1 to B3 and the t7 runs, no `ee7369d9` receipt existed in any of those trees. The new code makes large-v3 even less able to affect the defaults: refusing its licence declines nothing (S1).

## LFM2's notice on every route

Unchanged:
- kilix-license and kilix-content are at the same commits, so the lfm2 records, texts and catalog asset are as round 4 found them (record `e4d08e2c53ab…`, decision informational);
- `install_command_model` is AST-identical to 6942536f, and it ran in every tree above, declined or not;
- every run recorded the `record` (notice) receipt `e4d08e2c…-ef701ec2…json` and accepted no typed agreement;
- `test_command_model_records_needle_serves_are_the_carried_ones` passed.

No terms are waived or hidden on any route this session ran.

## Pins

At ee97037e:
- `releases/0.2.3.env`: `KILIX_REF=c90d48efab8c79a0011c9737fa9747f22fe98837`, whose `third_party/kilix-content` gitlink is `c8f0b0f51966925c5872c70c246434cce6784982`. That equals the carrier's `interface_content_ref` and `PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF` in both `releases/0.2.3.env` and `releases/0.2.3.requirements`.
- `KILIX_LICENSE_REF=f8486ed3df562bd512b0d948494c76b7e7ae0349` in both files equals `interface_licence_ref`.
- `PLEBIAN_OS_VOICE_CARRIER_SHA256=4fdbffce…0ebc` in both files equals the candidate CARRIER.json sha256.
- `PLEBIAN_OS_VOICE_CARRIER_RECEIPT_SHA256=89e5abff…f0a1` in both equals `sha256sum` of the carrier's ACCEPTANCE.json, which the brief says is regenerated after review.
- `releases/0.2.3-command-model.json` `source_pins`: kilix c90d48ef, kilix-content c8f0b0f5, kilix-license f8486ed3 and kilix-needle a887e2fa. Those are the candidate's commits.
- `KILIX_VOICE_REF=1a4e63b11d0ad9c1664031e2773f5c4f5797913f`, unchanged.
- The notes' pin table names KILIX_REF c90d48ef.

CARRIER.json does not bind KILIX_REF, as the brief says, so the move needs no carrier change.

## The carrier generator check

This ran from `W/src/plebian-os` at ee97037e, with `W/src/kilix-content` at c8f0b0f5 and `W/src/kilix-license` at f8486ed3, on a fresh writable copy `W/carrier-copy` of the candidate carrier:

```
python3 build/generate-model-compliance.py --content-repo W/src/kilix-content --license-repo W/src/kilix-license \
  --determination <id>=W/carrier-copy/determinations/<id>/<file>   (the eleven carried determinations, as in round 4) \
  --seat W/carrier-copy/seats/SEAT-A-MEDIUM-SPLIT-LFM2-FIXES-CARRIER-R3-20261108.md \
  --seat W/carrier-copy/seats/SEAT-B-MEDIUM-SPLIT-LFM2-FIXES-CARRIER-R3-20261108.md \
  --out W/carrier-copy --check
```

It printed nothing and exited 0, and `diff -r` of the copy against the read-only carrier printed nothing. As a control, one added byte in the copy's whisper-medium-en/DELIVERY made the same command print `carrier differs: whisper-medium-en/DELIVERY` and exit 1.

## Full plebian-os suite, ee97037e against 8f8af4fc

`python -m pytest -q -p no:cacheprovider -rfE tests` ran at both commits, each in its own env tree (`W/ts1`, `W/ts2`). The sibling variables PLEBIAN_OS_KILIX_REPO, PLEBIAN_OS_KILIX_CONTENT_REPO, PLEBIAN_OS_KILIX_LICENSE_REPO, PLEBIAN_OS_KILIX_NEEDLE_REPO, PLEBIAN_OS_NEEDLE_REPO, PLEBIAN_OS_KILIX_VOICE_REPO and PLEBIAN_OS_KILIX_BONSAI_REPO pointed at this session's clones.
- ee97037e: `9 failed, 1425 passed, 5 skipped, 2728 subtests passed in 267.15s`.
- 8f8af4fc: `9 failed, 1422 passed, 5 skipped, 2728 subtests passed in 266.69s`.

`diff` of the two sorted FAILED and SUBFAILED lists printed nothing. The three extra passes are the three new test_image_models tests.

The nine failures at both commits:
- AC-7, `test_model_compliance_carrier.py::test_acceptance_receipt_names_two_independent_seats`, with `AssertionError: '4fdbffce…0ebc' not found in '# Seat A review: … round 3 …'`. This is expected until this round's seats are attached.
- The eight environmental failures round 4 recorded. They are identical at 6942536f, and RELEASING.md and those tests are outside the delta:
  - two `test_build_vm_image.py` closure tests, which expect release 0.2.2;
  - two `test_ollama_carrier_wrappers.py` tests;
  - four RELEASING.md subtests of `test_voice_release_contract.py::test_documents_describe_the_first_use_route_the_code_takes`.

AC-1 to AC-6 and AC-8 to AC-12 pass at ee97037e.

## Owner decisions against the candidate

- **The request.** Install by default on install or upgrade, if missing and not declined: implemented for the three defaults, now including the run after a failed download (A3).
- **"Both".** medium.en is a default, and large-v3 has its own record and is installed only after a yes: implemented, and refusing large-v3 no longer affects the defaults.
- **"Demucs in ISO, Whisper online (Recommended)".**
  - Demucs ships in the image with its MIT text, and is installed from the archive even after a failed download (B3).
  - Whisper is fetched from its source on the first online upgrade, and again after a failure.
  - The option's "or setup" is the second known issue.
- **"Either one".** The wizard "no" or the key at 0 each decline. A refused default licence also declines, which only installs less.
- **Earlier rounds' decisions.** These are intact, since kilix-license, kilix-content, the carrier and the command-model path are unchanged:
  - the medium record;
  - LFM2's notice terms (a `record` receipt, terms shipped, nothing waived);
  - the Demucs determination (`02f182d7`, owner record unchanged);
  - the round-3 wording fixes.

## Declared items

- **Seat B's round-4 item (1)**, refusing only large-v3's licence declines all three: fixed (S1, with 9e58d314's contrast).
- **Seat A's round-4 blocking defect**: fixed (A2 → A3 → A4, B2 → B3, with 8f8af4fc exiting 1 on the same states).
- **Seat B's round-4 item (2)**, the Demucs distribution entry's upgrade sentence. The entry's `upgrade` text in kilix-license f8486ed3 `determinations-demucs.json` is "An online upgrade downloads the weights from the pinned URL. Both routes verify the pinned size and sha256 before installing." It is a defect, and it does not block (known issue 2):
  - The installer downloads only when the image supplied no archive (`install_demucs`, unchanged in this respect).
  - A machine installed from the RC5 image, which has the archive at `/usr/local/share/plebian-os/demucs-htdemucs-6s.tar`, reinstalls from that archive, even after a failed download (B3).
  - So the sentence is broader than the installer.
  - It is not blocking because both routes install the same pinned bytes under the same record and its MIT text, as the next sentence says. No route serves other terms, and nothing is installed that the owner did not decide.
  - It is wording in the owner's distribution entry, not in a carried DELIVERY. Demucs has no carrier entry.
- **Seat A's round-4 known issue 2**, provisioning always runs offline: still a defect, still not blocking (known issue 3). `provision/plebian-os-provision.sh` has an empty diff, and every provisioning run passes `--offline`. An online setup gets medium.en, and Demucs where the image supplied no archive, at its first online upgrade, not during setup. The records and DELIVERY describe this accurately, and it installs less, not more. It is still a narrowing of the owner's "or setup".
- **Seat A's round-4 observations**: see "Observations" below. One is resolved (the README's "installs nothing"), and one became known issue 2.

## Known issues (defects this session found)

1. **Not blocking.** The new refused-licence decline cannot be reached through the real wizard for the four MIT records. Yet the wizard's Playalong note ("Refusing one of their licences in this wizard also declines them"), the README, the release notes and the CHANGELOG describe it as something a user can do. `consent_and_install` never asks about a standard-policy-eligible record, so for Basic Pitch, Demucs, medium.en and large-v3 there is no licence question to refuse, and `prompts asked: []` in both real-wizard runs. The code is a correct guard. The user-facing sentences are true only vacuously today, and a reader will look for a refusal the wizard does not offer.
2. **Not blocking.** The Demucs distribution entry's upgrade sentence is broader than the installer (seat B's item 2, above).
3. **Not blocking.** Provisioning always runs the installer offline, so an online setup defers medium.en, and Demucs without an archive, to the first online upgrade (seat A's round-4 known issue 2, above).

## Observations (not counted as defects)

- The medium.en DELIVERY opt-out sentence and the medium owner distribution record name two declines. The code now has three: page no, refused default licence, and the key at 0. It also has the unreadable case. Because the sentence states sufficient conditions, it stays true. The third trigger only installs less and is unreachable today.
- A hand-written wizard state with a Playalong page "no" and `refused: [faster-whisper-large-v3]` installs the defaults. The code reads such a "no" as coming from the licence screen, not from the page. The real wizard writes that state only when the user said yes on the page. And for large-v3's MIT record it cannot write it at all today.
- `_playalong_installed`'s stderr note says "installing it again" also in an `--offline` run, where the next line then defers the install ("the first online upgrade downloads it"). The note is accurate about the state and imprecise about that run.
- On the retry, the installer reuses the standard-policy receipt that the failed run recorded before its download; in A3 the receipt files kept their A2 times. A receipt covering the exact record and manifest therefore still precedes every download.
- `declined()` treats any off value of the shared settings convention (empty, no, false, off, disabled) as declining, not only "0" (round 4, unchanged). This only installs less.
- The large-v3 owner record names the first-use screen as its install route. Kilix's README and wizard note also offer the wizard's Playalong page, where choosing the row and finishing applies the standard policy to the MIT record. That is also a yes (round 4, unchanged).
- The large-v3 determination's `card_bytes` (2052) is true but not checked by the generator; `card_sha256` is checked (round 4, unchanged).
- An older CHANGELOG paragraph still says "Kilix is `44b992ae`, kilix-content is `de2764f8`", the state at 7b1b1630. The RC5 paragraph now names c90d48ef (round 4, unchanged).
- Resolved since round 4: Kilix's README now says Plebian-OS "installs none of the three when the answer cannot be read", instead of "installs nothing".

VERDICT: ship with known issues
