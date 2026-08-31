# Releasing Plebian-OS

Plebian-OS, [pleb](https://github.com/itsmygithubacct/pleb),
[kilix](https://github.com/itsmygithubacct/kilix), and
[kilix-95](https://github.com/itsmygithubacct/kilix-95) are one coordinated
stack. A release uses one version across all four repositories and pins every
network-fetched build input.

## Installer personas and identity inventory

The 0.2.1 installer has four deliberately separate personas. Identity never
crosses between them implicitly.

| Persona | Identity and credential contract | Disk/network contract | Acceptance |
|---|---|---|---|
| Normal release ISO | Debian Installer asks for hostname, display name, Unix username, and a concealed password twice. The image carries no answered identity field and no known password. | Boot menus wait; partitioning and destructive confirmation remain interactive; SSH is absent. | Install a non-default 32-character account and hostname in both BIOS and UEFI lanes. |
| Unattended VM/CI derivative | The caller explicitly supplies username and hostname and either a crypt hash through a protected input or lets the harness generate a strong one-time credential. Plaintext is never an argument, environment value, build record, or log field. | Explicitly non-publishable; SSH, autoboot, and unattended partitioning are enabled only for this derivative. | The harness owns the temporary credential, verifies the guest, then expires it. |
| Upgrade from 0.2.0 | Existing username, uid, home, password hash, hostname, login policy, and ownership are retained. Installer questions never run during an upgrade. | The selected release closure moves transactionally. If the legacy default hash remains, password-based remote login is disabled for that account without disabling console login. | Run distinct retained-default-hash and changed-password fixtures through update and rollback. |
| Offline install | Uses the normal interactive identity flow. | Base installation completes from media; network-dependent firstboot work reports a bounded resumable failure and never changes identity. Optional models are not part of the base image. | Reach the login/recovery boundary with the recorded account intact, then resume core provisioning when networking is restored. |

Phase-0 inventory was frozen against `work/0.2.1-iso` commit
`3a05ea9cd31bbc0f8d153daa46734ac4b29212ed`. These are the fixed-identity or
credential-bearing sites that 0.2.1 must either remove from the normal image or
confine to the explicit automated/legacy persona:

| Baseline site | Assumption at the frozen baseline | Required disposition |
|---|---|---|
| `preseed/preseed.cfg:14-20,30,39-49` | Documents and answers hostname `plebian`, account `pleb`, display name, plaintext password, and weak-password policy. | Remove every normal-image identity answer and let Debian Installer ask. |
| `preseed/preseed.cfg:152-184` | Stages firstboot files but does not record which account Debian Installer created. | Atomically record the single DI-created account for firstboot. |
| `build/remaster-iso.sh:268-325` | Release mode requires `IMAGE_PASSWORD` and `RANDOM_PASSWORD`. | Refuse either key in release mode. |
| `build/remaster-iso.sh:386-461` | Derives every guest path from the preseeded username. | Permit an identity-free normal preseed; defer per-user paths to firstboot. |
| `build/remaster-iso.sh:1021-1110` | Generates/replaces the image password and asserts the shipped password as validity evidence. | Replace with interactive-versus-automated profile validation; never generate a release credential. |
| `build/build_vm_image.py:275-431,434-500,531-575,1706-1782` | Defaults the account, accepts plaintext `--password`/`IMAGE_PASSWORD`, and prints generated values. | Require explicit automated identity, protected credential input or harness-owned generation, and redact all output/evidence. |
| `build/build_usb_image.py:64-101,526-609` | Treats a physical USB build as a pre-answered identity image and accepts plaintext `--password`. | Make the default physical image interactive; require an explicit non-publishable automated profile for pre-answered identity. |
| `build/install-vm-from-usb-iso.sh:18-69` | Places the VM password in an environment variable and twice in process arguments. | Use one private, short-lived credential file and delete it on every exit. |
| `releases/0.2.0.env` | Publishes `IMAGE_PASSWORD=plebian` and `RANDOM_PASSWORD=0`. | Preserve as historical 0.2.0 evidence; omit and forbid both keys in 0.2.1. |
| `provision/plebian-os-provision.sh:328,529,627-652,2937-3025,3793-3801` | Has generic passwd/home validation, but silently chooses the lowest eligible uid and installs the legacy transition path on every fresh install. | Prefer the DI record, refuse ambiguous fallback, enforce Debian's username policy, and install the legacy transition only when its hash remains. |
| `provision/plebian-os-passwd:1-163` | Detects and changes the legacy default password through a narrow helper. | Retain only for 0.2.0 upgrades; add per-account remote-login neutralization and never use it as a fresh-install password API. |
| `provision/plebian-os-update.sh` and `provision/plebian-os-select-closure.sh` | Carry paths from the running user's home/session closure and do not rename accounts. | Preserve that behavior and reconcile the legacy remote-login policy during the adjacent release hop. |
| `tests/test_deferred_hardening.py`, `tests/test_disk_safety.py`, `tests/test_passwd_nag.py`, `tests/test_release_versioning.py`, `tests/test_remaster_contract.py`, `tests/test_build_vm_image.py`, `tests/test_build_usb_image.py` | Assert the outgoing fixed-credential behavior. | Replace with interactive-release, protected-automation, arbitrary-user, ambiguity, and legacy-upgrade regressions. |

Product-name uses of “Pleb” and storage names such as `/etc/pleb/session.env`
are not account assumptions. No `/home/pleb` path is present in the owned
provision/update/session scripts; the remaining numeric `1000` uses are uid
range policy and are not an equality assumption.

The release login session is the main Kilix instance, with its clickable page
strip and pane controls visibly present, Kilix 95 in its 95 flavor loaded as
page 1, and hard-kiosk respawn off. A bare first-page shell is an explicit
`--session shell` override, not the release default. Kilix Cap, Kilix TUI, and Kilix Land are
additional desktops whose immutable default source commits are
inherited through whichever Kilix commit a release selects; they do not receive
independent coordinated tags or top-level release-manifest keys. Adding a
desktop does not change the four-repository governance boundary.

The publishable image uses the `interactive-v1` identity profile: it contains no
answered hostname, display-name, username, or password question and carries no
known login. `IMAGE_PASSWORD`, `RANDOM_PASSWORD`, custom preseeds, SSH,
autoboot, and unattended disk selection are forbidden in release mode. The
separate `automated-v1` VM/CI derivative requires explicit identity plus a
protected mode-0600 credential input, or a harness-generated password that is
never logged and is expired after verification.

The first publishable version is **0.1.1**. The existing `v0.1.0` tags identify
an incomplete candidate and must never be moved or used for a published image.
The last published coordinated release is **0.1.9**. The next planned release
is **0.2.0**; its closure is finalized only after the four final component
commits are known.
0.2.1 development is a separate, post-0.2.0 integration line. Its source or
planning work must not be folded into, or used to rebuild, a 0.2.0 candidate or
release worktree. Before 0.2.1 release preparation begins, freeze a distinct
0.2.1 manifest from the exact accepted parent, then advance all four coordinated
`VERSION` files together. Partial 0.2.1 prerequisites and planning documents do
not constitute that closure.
0.1.7 is the fresh-install upgrade baseline: no pre-0.1.7 in-place path is
supported. Every release after it must pass the adjacent published-release
upgrade gate in [UPGRADING.md](UPGRADING.md) as well as fresh-install
acceptance.

### Tags are created only by this procedure

A `vX.Y.Z` tag in any of the four repositories means "this commit is part of
published stack release X.Y.Z". Component repositories may bump their own
`VERSION` on `main` whenever their contract level changes, but **nobody pushes a
`vX.Y.Z` tag outside step 7 below**, and the four tags are pushed together.

### Published provenance corrections

If a published tag, note, manifest, or commit list disagrees with an immutable
artifact, do not move the tag and do not replace the original artifact. Establish
the artifact identity from its published checksum, embedded build info, and
checksummed source archive; verify that every recorded exact commit remains
fetchable. Then:

1. add a versioned provenance-correction document which records both the exact
   artifact closure and the conflicting public metadata;
2. correct the historical manifest to exact full commits and explain why a tag
   is not authoritative for that artifact;
3. update the release note, attach the correction as a new asset, and publish
   the correction asset's own SHA-256 without rewriting the original
   `SHA256SUMS`; and
4. add regression coverage for the corrected commits and correction-asset
   hash.

The correction must distinguish historical metadata from artifact identity and
state the authority order used for verification. Replacing one provenance error
with a moved public tag is forbidden.

### Why 0.1.3 through 0.1.6 do not exist as releases

The first two numbers were consumed by component `VERSION` bumps that marked Kilix SDK
levels 1.3 and 1.4 (and Kilix-95's adoption of them), without a closure, an
acceptance run, or an image. `0.1.3` was never tagged in any repository. `0.1.4`
was additionally pushed as a **Kilix-only** `v0.1.4` tag, before this rule
existed; that tag is published and is therefore left exactly where it is rather
than moved or reused. Neither number can become a coordinated release — a 0.1.4
closure would either have to pin Kilix at that tag, which no longer matches the
work the other three repositories depend on, or re-point a published tag. 
`0.1.5` failed differently, and is the more instructive case: it was prepared
in full — all four `VERSION` files mirrored, release notes written, and a
closure whose every upstream input was verified against its official source —
and then never built, accepted, or tagged while the components kept moving.
Preparation is not a release. Its notes and its verified pins were folded into
the 0.1.6 candidate rather than shipped under a number no artifact would carry,
and `releases/0.1.5.env` was renamed rather than kept: a closure file present
for a version with no image claims a reproducibility guarantee that does not
exist. 0.1.6 itself reached local candidate tags and an artifact, but neither
was published. Further flash-safety and acceptance fixes changed the intended
source before publication, so that candidate was retired and its work moved to
0.1.7 instead of moving or publishing a stale tag.

0.1.7 subsequently retired the candidate 0.1.6 closure and became the published
fresh-install baseline; no closure was back-filled for 0.1.3, 0.1.4, or 0.1.5.
`releases/<x.y.z>.env` is the reproducible input manifest for an image that was
actually built and accepted, not a changelog.

The lesson each of the four teaches is the same one: a version number is
spent the moment it appears in a `VERSION` file or a heading, whether or not
anything ships. Bump component `VERSION` files toward the release you are
actually cutting.

## Version commands

| Component | Command |
|---|---|
| Plebian-OS | `plebian-os-update --version`, `plebian-os-provision --version` |
| pleb | `pleb --version` |
| kilix | `kilix --kilix-version` (`kilix --version` reports its engine) |
| kilix-95 | `python3 main.py --version` |

## Release closure

`releases/<x.y.z>.env` must include:

- the coordinated source refs for all four repositories;
- for 0.2.1, complete exact-commit/canonical-repository/empty-branch tuples for
  `KILIX_SYSTEM_MONITOR`, `KILIX_DESKTOP_SDK`, `KILIX_ICEWM`,
  `KILIX_MEDIA_SDK`, and `KILIX_WAYDROID`. These are release-root selectors:
  component versions remain in their owner manifests and child gitlink commits
  remain facts of the selected Git trees rather than duplicate env pins;
- a stable Debian archive URL, SHA-256, and positive byte ceiling for the
  source netinst;
- a `snapshot.debian.org` timestamp covering installer and firstboot packages;
- the fallback kitty bundle version and SHA-256;
- the exact Go version and SHA-256 for every supported build architecture;
- pinned installer versions/checksums and a positive download byte bound for
  any optional network installers that are enabled (currently `uv`);
- when `PLEBIAN_OS_INSTALL_VOICE_MODEL=1`, the full Kilix Voice source ref,
  library version/URL/SHA-256, and acoustic-model URL/SHA-256. Both installed
  Vosk assets must retain readable upstream provenance and Apache-2.0 license
  material; a checksum-matching opaque binary or model is not releasable. The
  pinned Voice source must expose the exact `kilix.speech.models/v1` document
  through download-free `kilix-stt --models --json`; a consumer-specific
  copied catalog is not a release substitute.

Release mode fails closed when a required value is empty, still a placeholder,
malformed, dirty, or does not resolve to the checked-out Plebian-OS commit. The
image records the transformed preseed, source ISO, refs, runtime configuration,
and tool pins in `/etc/plebian-os/build-info.env`; final package and resolved
source/tool manifests are written under `/var/lib/plebian-os/`.

## Upgrade support

[`releases/upgrade-policy.json`](releases/upgrade-policy.json) is the
machine-readable contract and [UPGRADING.md](UPGRADING.md) is its normative
explanation. 0.1.7 must be installed fresh from any older build. Beginning with
the next published release, the supported default hop is from the immediately
previous published release, regardless of unused version numbers between them.
A skip over a published release is supported only when the exact path is named
and accepted.

An upgrade must move the complete release-controlled closure together while
preserving user files, application/game/provider state, shared settings,
operator session choices, and custom desktop state. An induced failure must
restore the prior coherent runtime and configuration. Reinstalling successfully
or passing fresh-install acceptance does not satisfy this gate.

### Every release ships its own closure selector

`plebian-os-update` revalidates the release the machine already has; it never
selects a new one. The mechanism that does is
[`provision/plebian-os-select-closure.sh`](provision/plebian-os-select-closure.sh),
and the release which ships it to an operator is the **target**, not the source:
it reads `releases/<x.y.z>.env` out of the published `v<x.y.z>` tag. A machine
running the previous release therefore fetches that tag and runs the selector out
of it, which is why the exact command block belongs in the target's release
notes.

`releases/<x.y.z>.env` is the closure; the selector is what makes it selectable.
So a release is only shippable when the selector accepts its manifest —
completeness, exact 40-character component commits, empty branch keys, a Debian
snapshot timestamp, engine and Go pins, an all-or-nothing optional closure such
as Kilix Voice, and a `PLEBIAN_OS_VERSION` that agrees with both the release
identifier and the release commit's `VERSION`. Selecting is the same discipline
`load_release_manifest` applies at build time, one step earlier in the operator's
hands. If a release introduces a new release-controlled key, add it to
`RELEASE_CONTROLLED_KEYS` in the selector (and to the required lists if the
release cannot build without it), to Pleb's F109 key-ledger/read surface, and
to the rendered `closure.env` contract in the same coordinated release change
that adds it to the manifest;
the selector adds keys the installed release never had, but only ones it knows
are release-controlled. The selector must prove that every selected component
commit is reachable from an advertised public head or tag; a server accepting
a fetch-by-SHA is not sufficient publication evidence. It compares the four
directly installed Git checkouts and verifies the five additional 0.2.1 release
roots through private advertised-ref mirrors before rendering the new
configuration, so a higher coordinated version cannot hide a component
downgrade or an unpublished pin.
It is installed on PATH as part of
the twelve-file transactional OS layer beginning with 0.1.9. The selection
transaction also installs the exact target updater and backs up the prior
updater, selector, and session together. This is required whenever the target
changes the updater's payload set, dependency policy, validation, or final
provenance contract: replacing an already-running source-release updater later
cannot change the process which is performing that hop.

The target release notes put the operator's
`pleb update --to <x.y.z> --dry-run` and `pleb update --to <x.y.z>` block beside
the selector recovery block. The release gate exercises both shapes: an image
delegates through the installed OS updater, while a standalone Pleb install
uses its private Plebian-OS object cache and deploys no OS-layer tools. A new
release key is incomplete unless the manifest, selector classification,
Pleb read/ledger surface, split-closure rendering, and both-shape fixtures move
together.

## Cutting `<x.y.z>`

1. Update `VERSION` and each repository's release notes
   (`CHANGELOG.md` in Plebian-OS/Pleb and the `README.md` release section in
   Kilix/Kilix-95). Create and review `releases/<x.y.z>.env`; verify every URL
   and checksum from its official upstream source. Advance
   `KILIX_COMMIT` in `kilix-95/.github/workflows/test.yml` to this release's
   Kilix commit: Kilix owns the SDK, so a stale pin leaves Kilix-95's CI testing
   an old pairing and reporting green while the shipped combination is untested.
   Its advisory `pairing` job runs the same suite against Kilix's branch head; a
   red result there is the early warning that this pin — or the provider — needs
   to move. Confirm the release manifest omits `IMAGE_PASSWORD` and
   `RANDOM_PASSWORD`; `remaster-iso.sh` must refuse either key and every custom
   identity input in release mode. For every release after 0.1.7, name the immediately
   previous published release as the supported upgrade source and reserve a
   provenance section for the upgrade acceptance result. Name any supported
   direct skip separately; silence means the skip is unsupported. Write the
   operator's exact closure-selection command into the release notes — the
   fetched-tag block in [UPGRADING.md](UPGRADING.md), with this version
   substituted throughout. A release whose notes do not carry that block has not
   shipped the mechanism UPGRADING.md requires; step 4 is where it gets proven.
2. Run each repository's complete test/lint suite and integration contract
   tests. Run them in a clean environment and outside a live Kilix session:
   exported `KILIX_*` values and a user's persisted `kilix.env`
   (`KILIX_DESKTOP_FLAVOR`, `KILIX_CHROME_*`) reach several suites and turn
   them red for reasons that have nothing to do with the code. Kilix-95's
   `tests/run.py` resolves Kilix from the shared source root, so
   its result reflects whatever is in that working tree. Confirm all four
   repositories also pass their 0.2.1 isolated-runner contract: a minimal,
   allowlisted environment; private HOME and XDG roots; no inherited Kilix
   session variables; bounded process, socket, service, display, input, audio,
   GPU, network, and clock dependencies; and no leaked state or child process.
   Record both clean-console and live-Kilix results in the release evidence.
   A suite that passes only because of the operator's ambient session is a
   release failure. Confirm all four `VERSION` files read the release version,
   confirm all four worktrees are
   clean, review their exact commits, and commit the coordinated changes.
   Immediately before tagging, confirm those
   commits are still the intended branch tips; classify any newer commit as
   either part of this release or explicitly post-release. For the pinned Kilix
   commit, inspect its `src/go.mod` `toolchain` line and make the manifest's
   exact Go version and architecture hashes match it.
3. Push the reviewed commits **without tags**. Firstboot fetches the exact
   component SHAs from GitHub, so the pinned acceptance guest cannot test an
   unpublished object. A failed acceptance is fixed with new commits; no
   immutable release ref has been published at this point.
4. Create **local, annotated** `v<x.y.z>` candidate tags on the reviewed
   commits. Do not push the tags yet. This lets `PLEBIAN_OS_REF=v<x.y.z>` resolve
   while the strict release-image checkout guard is active. The candidate tag is
   also the first point at which this release's closure can be *selected*, so
   prove it now: on a machine installed from the previous release, run this
   release's own `provision/plebian-os-select-closure.sh <x.y.z> --dry-run` out
   of the candidate tag and confirm it validates the closure and lists the
   release-controlled keys that move. A release whose own selector refuses its
   manifest is not cuttable — fix the manifest and retag rather than carrying an
   unselectable closure into the acceptance run.
5. Build the pinned artifact from the tagged Plebian-OS checkout:

   ```sh
   PLEBIAN_OS_RELEASE=<x.y.z> build/remaster-iso.sh '' \
       "plebian-os-<x.y.z>-amd64.iso"
   sha256sum "plebian-os-<x.y.z>-amd64.iso"
   ```

6. Run both VM acceptance lanes from the clean, tagged Plebian-OS candidate
   checkout. First run the instrumented automated lane:

   ```sh
   build/acceptance-vm.sh
   ```

   The wrapper refuses unless `HEAD`, `VERSION`, the manifest's OS ref, and the
   local candidate tag all identify the same clean commit. Only after proving
   that identity does it create a clearly non-publishable SSH/autoboot
   derivative while retaining the exact release-manifest media, snapshot,
   toolchain, component, voice, and provider pins. VM, ISO, and report names
   include the release and candidate commit; an older candidate or unrelated
   `plebian-acceptance` VM is never deleted implicitly. Do not use `--replace`
   for an ordinary run. If a same-candidate rerun must replace evidence, inspect
   it first and opt in explicitly (or select new name/output/report overrides).

   The automated gate checks exact embedded build provenance, firstboot,
   component/session/storage contracts, the installed closure selector, voice,
   a real induced OS-layer update failure with byte-exact rollback, a successful
   whole-stack update/restart, and clean builds of every installable catalog
   pin. Guest exit status—not output text—decides each check. The wrapper
   inherits the builder's 120-minute combined Debian-install and firstboot
   ceiling; pass a larger `--timeout` on a slower host or mirror. Retain the
   generated JSON and `.sha256`; only `status: "passed"` satisfies this lane.
   `--no-wait` or `--no-verify` is diagnostic and cannot satisfy release
   acceptance.

   Then validate and boot the exact, publishable bytes produced in step 5:

   ```sh
   build/acceptance-release-iso.sh \
       --iso "plebian-os-<x.y.z>-amd64.iso"
   ```

   This second wrapper parses (never sources) the ISO's embedded build info,
   compares its complete recorded closure with `releases/<x.y.z>.env`, requires
   the candidate-tag commit, clean/release-mode provenance, disabled
   SSH/autoboot/unattended-disk flags, the release volume ID, and both BIOS and
   UEFI El Torito entries. It then starts distinct BIOS and EFI VMs using that
   exact ISO without remastering it. Its prebuilt-ISO harness uses the
   identity-free `--interactive-installer` mode and supplies no guest username,
   hostname, password, session, or sudo policy. Use `--dry-run` to perform every
   artifact validation and print both VM plans without creating anything. These
   strict installs are interactive by design; their JSON reports say
   `vm-started-no-verification` and are provenance/start records, not passing
   acceptance results.

   Complete the installer and the remaining operator checks in both strict ISO
   VMs before publication. Check the versioned Plebian-OS titles in the
   default, advanced, and accessible-dark menus, then enter the graphical
   installer and verify both banner variants. The angular-P mark must retain
   one eye, two hair strokes, and the complete orange `>_` cursor.
   Confirm the ISO volume ID is `PLEBIAN-OS <x.y.z> AMD64` and `/.disk/info`
   identifies Plebian-OS—not an unmodified “Official” Debian image.
   Mount the ISO and confirm both root READMEs identify an unofficial,
   non-endorsed Plebian-OS remaster, route derivative support to Plebian-OS,
   and retain Debian 13 base attribution. Check BIOS Help F1/F2/F9 and the
   text/graphical installer main menu for the same product boundary. F2 must
   list 4 GiB RAM, 20 GiB disk, and first-boot networking; F9 must distinguish
   `/cdrom/plebian-os/build-info.env` from `/etc/plebian-os/build-info.env`.
   Log into the installed guest and confirm the initial screen is Kilix-95 in
   page 1 of the main Kilix instance, with its page strip, status widgets, and
   pane controls visible—not a shell or content-only terminal. Confirm the
   provider is external Kilix-95 with the 95—not XP—flavor, and closing the
   Kilix OS window returns to LightDM rather than respawning.
   In an installed guest, complete these distribution-asset checks:

   - confirm VirtualBox audio input and output are enabled; run
     `kilix-tts --version`, `kilix-stt --version`, and
     `kilix-voiced --version`, then require `kilix-stt --print` to report
     `dictation=ready`. Require `kilix-stt --models --json` to pass the
     `kilix.speech.models/v1` schema gate with all three 0.1.9 models, exactly
     one selected default, truthful runtime-support flags, positive exact byte
     sizes, and the shared explicit install-and-default argv. This listing must
     not open the network or change installed/default state. Require the
     device-free acceptance smoke to synthesize
     a phrase with real espeak, load the pinned Vosk library/model, and
     recognize nonempty text. Verify the installed library/model match the exact
     release stamp and each has regular, non-symlink provenance and
     Apache-2.0 license material. Grant VirtualBox host microphone permission
     and perform one click-to-talk dictation turn; the microphone must remain
     closed before that explicit action;
   - on the pristine guest, exercise all five model-management surfaces against
     the same catalog. `kilix stt --models` and the Models tab must show the two
     runnable Vosk models plus the installable-but-not-yet-runnable VibeVoice
     weights. `kilix settings --section voice`, built-in WM Settings, and Kilix
     95 Settings must each offer **Install + use** for the selected model. Before
     installing `lgraph-en-us`, make it the pending default, click the terminal
     microphone, require the 124.5 MiB lazy-install confirmation, cancel it, and
     prove no model directory appeared. Then install it through one settings
     surface, require checksum verification and coherent Vosk/model defaulting,
     and use the other surfaces to verify the same installed/default state.
     Restore the release default before recording acceptance. Do not download
     the 1.6 GiB VibeVoice weights solely for this check; require the truthful
     unsupported-runtime label and its explicit install/default action instead;
   - verify the Kilix engine is one physically contained
     `generations/build.*` directory selected by a relative `current`
     symlink, with regular executable `kitty` and `kitten` launchers,
     byte-exact `source-id`, and the single canonical
     `$KILIX_STATE_DIRECTORY/fork-built-ref`; reject any legacy Pleb-owned
     duplicate stamp;
   - exercise direct Kilix, Pleb, firstboot/provision, and whole-stack lock
     contention; inject a failure after a same-source promotion and verify the
     exact prior `current`, `previous`, and stamp are restored while failed
     and otherwise unreferenced generations are safely collected;
   - verify `/usr/local/share/plebian-os/wallpapers/plebian-os.png` is
     `root:root`, mode `0644`, and has the expected tracked/build-info SHA-256;
   - verify `/etc/lightdm/lightdm-gtk-greeter.conf.d/50-plebian-os.conf` is
     `root:root`, mode `0644`, matches the build-info SHA-256, selects that
     wallpaper with `user-background=false`, and shows Plebian branding in both
     the normal greeter and the exhausted-firstboot recovery path;
   - open **Start > Help > Pleb Recovery Guide**, confirm it displays the
     installed `/usr/local/share/doc/pleb/RECOVERY.md`, and verify the guide
     includes both the full Plebian-OS dependency helper and the
     `libxxhash-dev` fallback;
   - verify a fresh Kilix desktop selects that stable wallpaper path, while an
     existing `.state.json` (including a custom wallpaper choice) remains
     byte-for-byte unchanged across reprovisioning and update;
   - verify firstboot records
     `~/.local/gpu_terminal/sources/{plebian-os,pleb,kilix}` plus
     `~/.local/gpu_terminal/sources/kilix-desktops/kilix-95` as the coordinated
     source layout and `~/.local/gpu_terminal/` as the data root in build info,
     session defaults, and final provenance; confirm `external`, `builtin`, and
     both `auto` outcomes seed only Pleb's `data/desktop` state, while launching
     Kilix-95 standalone still uses its XP wallpaper;
   - verify the shared data root and its `pleb`, `kilix`, `kilix-95`, and
     `plebian-os` component roots are real, target-user-owned directories with
     mode `0700`; check every persisted category below them, including Pleb's
     config/state/cache/session/data and canonical `data/desktop`, Kilix's
     config/state/cache/session/build/data and every component of the configured
     prebuilt path, Kilix-95's config/state/cache/session/data, and Plebian-OS's
     session directory. Repeat after `pleb update`, `plebian-os-update`, and a
     reboot, preserving sentinel files throughout. Exercise Kilix-95 directly
     under a conventional umask, confirm its categories remain private, verify
     an external desktop override is not chmodded, and confirm a root invocation
     of `plebian-os-update` fails immediately with “run without sudo” guidance;
   - exercise a successful twelve-file OS-layer update and an induced failure,
     confirming rollback restores the prior wallpaper, LightDM greeter
     override, attribution, license, scripts, Pleb recovery guide (or removes
     newly introduced files/directories), and state;
   - verify the installed
     `/usr/local/share/doc/plebian-os/installer/ATTRIBUTION.md` and
     `/usr/local/share/doc/plebian-os/COPYING.GPL-2` are `root:root`, mode
     `0644`, match their expected hashes, and retain the attribution's working
     relative `../COPYING.GPL-2` reference.

   0.1.7 establishes the fresh-install baseline and has no supported upgrade
   source. For every later release, also install the immediately previous
   published ISO in a fresh VM and complete all six gates in
   [UPGRADING.md](UPGRADING.md): verify the starting artifact/commits, create
   preservation sentinels, prove rollback under an induced failure, select the
   target closure with this release's own
   `provision/plebian-os-select-closure.sh` and then
   complete the upgrade and reboot, verify the target closure plus preserved
   choices, and record the exact result in release notes/provenance. Gate 4 runs
   the selector and the updater in that order and nothing privileged between
   them. Perform this using the path documented for installed users, not an
   unpublished developer checkout. A failed or missing upgrade run blocks
   publication.
7. Re-check that every local tag resolves to the reviewed commit and that all
   worktrees remain clean. Only then push the four tags and publish the strict
   release artifact, its checksum, and a checksummed release source archive
   containing the exact tracked artwork, editable source, attribution, license
   text, and provenance records used for the image. Publish that source archive
   and provenance alongside the ISO as release assets, rather than relying only
   on a mutable branch checkout. These records support review and redistribution;
   they are evidence of the release inputs, not a legal opinion or guarantee.

If validation fails before publication, fix the problem in new commits and
delete/recreate only the **unpublished local candidate tags**. Once any tag is
published, never move or reuse it; increment the patch version instead.

## Installed version and update semantics

Release images keep exact refs in `/etc/pleb/session.env`. Consequently
`plebian-os-update` verifies and rechecks those same commits; it does not drift
to branch heads. To intentionally move an installed machine to another release,
select the target release's complete coordinated closure, then run
`plebian-os-update --restart`. Never mix pins from different releases. The
supported source versions, preservation guarantees, rollback behavior, and
release gate are defined in [UPGRADING.md](UPGRADING.md); anything older than
0.1.7 requires a fresh install.
