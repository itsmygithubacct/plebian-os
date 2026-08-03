# Changelog

All notable changes to Plebian-OS — and its coordinated
pleb / kilix / kilix-95 release — are recorded here. The stack uses a single
shared version across all four repositories (see [RELEASING.md](RELEASING.md)).

## [0.1.7] — 2026-08-02

0.1.3, 0.1.4, and 0.1.5 were never stack releases. 0.1.3 and 0.1.4 appeared only
as Kilix and Kilix-95 component `VERSION` markers for their SDK levels, and Kilix
additionally published a `v0.1.4` tag of its own. 0.1.5 was prepared in full —
notes, version mirroring, and a verified pin closure — but never built, accepted,
or tagged. 0.1.6 then reached an unpublished local candidate, but further flash
safety and catalog acceptance fixes landed before publication and invalidated
that candidate's tag and artifact. Their work is folded into this section
rather than shipped under numbers no artifact will carry. 0.1.7 is therefore
the first coordinated release since 0.1.2 and restores one version across all
four repositories; see [RELEASING.md](RELEASING.md). It is the fresh-install
upgrade baseline: older installations are reinstalled, while every later
release must preserve data and settings from the immediately previous
published release.

### Added

- Support **Kilix Cap desktop sessions**. `KILIX_DESKTOP_PROVIDER` gains `cap`
  alongside `auto`, `builtin`, `external`, `command`, and `none`; it downloads
  and locally builds the Kilix-pinned Kilix Cap source on first launch. Kilix
  Cap reads `KILIX_CAP_*`, while external Kilix 95 keeps `KILIX95_*`, so the two
  providers can be configured independently on one image.
- Support **Kilix TUI desktop sessions**. `KILIX_DESKTOP_PROVIDER=tui` selects
  the text-native desktop, and firstboot installs Kilix’s pinned
  `kilix-tui-utils` checkout so the provider and its unified utilities are
  available without a developer checkout. Like Kilix Cap, Kilix TUI inherits
  its exact commit through Kilix rather than becoming a fifth coordinated
  release-core repository.
- Support **Kilix Land desktop sessions**.
  `KILIX_DESKTOP_PROVIDER=land` selects the walkable graphical desktop, while
  first launch clones its Kilix-pinned commit, initializes its recursive
  dependencies, and builds the native executable. Like Cap and TUI, Land
  inherits its immutable source revision through Kilix rather than expanding
  the coordinated release core.
- Route Kilix 95 web links through Kilix's canonical URL dispatcher. Installed
  Chrome, Chromium, or Firefox browsers are preferred; the experimental
  in-pane renderer remains the fallback when none is available.
- Ship **Tmux Manager**. Firstboot installs Kilix's pinned `tmux-tui`/`tmux-cli`
  closure and publishes Tmux Manager plus tmux-cli's `tb.py` as `tb` on `PATH`;
  the Kilix 95 Start menu entry opens it in a new tab, and both are usable
  directly from a shell.
- Provision the complete **Kilix Voice** closure for read-aloud and offline
  dictation. The release pins Kilix Voice commit
  `f05b64a7b2bc25fa9a7e2c3ae1e0b848f04a23f6` (version 0.1.2), the official
  Vosk 0.3.45
  x86_64 wheel from PyPI by URL and SHA-256, and Vosk's small US-English 0.15
  acoustic model by URL and SHA-256. The dependency manifest installs `unzip`
  before the pinned wheel and model archives are extracted. Firstboot executes
  all three installed tools and requires the exact source/library/model stamp,
  runtime library,
  model, provenance, license material, and `dictation=ready` diagnostic; an
  enabled release can no longer silently fall back to read-aloud-only. Both
  firstboot and VM acceptance also synthesize a fixed phrase with real espeak
  and require the pinned Vosk library/model to recognize nonempty text, without
  opening a microphone or playback device.
  The microphone remains local and click-to-talk: no device opens until the
  user invokes dictation. Release VirtualBox guests now expose host audio input
  as well as output so that path is testable (subject to the host's microphone
  permission). `espeak-ng` is the default synthesizer, while `mbrola` supplies
  an optional quality tier; its non-free voice databases remain a deliberate
  user opt-in and plain espeak-ng is the fallback.

- Provision the shared clickable-chrome settings file at
  `~/.local/gpu_terminal/settings.conf` and install `kilix-settings` on `PATH`,
  so the thermal, volume, network, calendar, date/time, battery, pane-memory,
  and game toggles have one source of truth across Kilix, Kilix-95, Pleb, and
  Plebian-OS.
- Install `pulsemixer` (with `alsamixer` as fallback) for the top-bar volume
  widget, placed immediately left of the network/Wi-Fi control.
- Build, verify, and publish Kilix's exact pinned Kilix Temps dashboard and its
  graphics closure during firstboot, so the page-strip thermometer works on a
  clean install without a developer checkout.
- Provision the pinned persistent PTY session manager so panes survive a Kilix
  crash and detached sessions are recovered on the next start.
- Ship **session logging on by default**: the PTY broker that owns each pane
  records that pane's output to a private, bounded transcript under
  `~/.local/gpu_terminal/kilix/state/transcripts`, so a detached, recovered, or
  crashed pane keeps what it printed. Firstboot verifies the delivered default
  rather than setting it, keeping the shared settings file the single source of
  truth. Kitty graphics payloads are elided to a byte-count marker so a pixel
  desktop cannot flood the log; only output is captured, so hidden password
  prompts are not recorded. Disable with `kilix settings --set transcript=off`.
  The transcript tree is bounded by two budgets rather than only a per-pane
  cap: dead-pane logs are compressed with `zstd -3` into a 5 GiB recent tier;
  the oldest are recompressed with `zstd -9` into a separate 1 GiB tier, and
  the oldest archives are dropped only once both are full. Terminal output compresses
  substantially, so the archive retains more history per byte while leaving
  headroom on the release-tested 20 GiB disk, and archiving is lossless. Both
  budgets are configurable from the settings file, `kilix settings --set`,
  the settings TUI, and Kilix 95's Settings app. `zstd` is provisioned for
  it.
- Install **Openbox** as a safety net under Kilix, while routing installed GUI
  applications through `kilix run` so Chromium and other clients remain inside
  Kilix tabs and panes. The graphical session previously had no manager for
  unavoidable native clients. `openbox` is added to both dependency paths and
  `/etc/pleb/session.env` persists `PLEB_WM=openbox` plus
  `KILIX_RUN_ALIASES=1`; `0` remains an explicit native-window opt-out.

### Fixed / hardened

- Pass the resolved Kilix voice data root into the acceptance smoke process.
  Session defaults are sourced as shell variables rather than exported
  environment entries; the old harness therefore raised `KeyError` before its
  real espeak-to-Vosk check even though the installed voice closure was ready.
- Raise the VM builder's combined Debian-install and firstboot wait from 90 to
  120 minutes. Real pinned acceptance showed that snapshot browser/development
  packages can consume most of the old budget before firstboot begins; explicit
  `--timeout` overrides remain available for slower hosts and mirrors.
- Install a root-owned `0644` `/usr/local/share/plebian-os/VERSION` marker
  before first boot and reassert it atomically during provisioning. The
  installed `plebian-os-provision --version` now reports the exact release
  instead of `unknown`; acceptance rejects any future image that regresses.
- Keep Kilix-95's `--version` and `--help` paths independent of its native
  runtime library, while retaining the fail-closed library gate for desktop
  launches. Acceptance now runs all four documented component version commands
  on the freshly installed system and requires the exact coordinated version.
- Make release acceptance clean-build every pinned optional game and app in a
  temporary guest directory, catching broken default targets and missing final
  executables before an image can pass acceptance. Reject a vacuous catalog and
  re-check that each installer result is the selected runnable executable.
- Protect swap-backed disks even when a swap-file path contains a space, tab,
  newline, or backslash. Both USB writers decode Linux's `/proc/swaps` octal
  escapes in one pass, preserving literal escape-looking filename fragments.
- Make the release credential policy explicit in its config:
  `IMAGE_PASSWORD=plebian` and `RANDOM_PASSWORD=0` publish the usable offline
  `pleb` / `plebian` login, while `RANDOM_PASSWORD=1` opts private images into a
  generated one-time password without recording that secret in provenance.
- Keep Kilix visibly identifiable at login by starting the main Pleb session
  maximized and without host decorations instead of using Kilix's content-only
  fullscreen mode. Acceptance now rejects an installed session that would hide
  the page strip and pane controls and look like a plain terminal.
- Make the installed-system and image-builder default the main Kilix instance
  with external Kilix-95 loaded as page 1, the login greeter enabled, and hard
  respawn off. Pin the coordinated release's provider to the 95 flavor, and make
  VM/USB builders honor manifest or environment session choices unless an
  explicit CLI flag overrides them.
- Install the pinned Kilix-95 checkout before the login session starts, so page
  1 loads flavor 95 without falling back to XP or downloading mutable source
  on first use. Export that
  provider, flavor, and exact ref into the main session so later interactive
  launches retain the pinned contract without a false unpinned-provider
  warning. Install the non-secret build provenance as root-owned mode `0644`,
  allowing the normal user session and acceptance tooling to verify the
  selected session contract.
- Align the direct remaster, VM/USB builders, provisioner, documentation, and
  acceptance checks on the private
  `~/.local/gpu_terminal/sources` checkout root. Acceptance now verifies the
  coordinated Kilix-95 checkout as well as the OS, Pleb, and Kilix checkouts.
- Track newly added Kilix submodules, and the content and presenter submodules
  specifically, in the whole-stack update rollback, so a failed update restores
  a coherent submodule state instead of a partially advanced one.
- Cover the Pleb-owned Openbox profile
  (`/usr/local/share/pleb/openbox/rc.xml`) and `/etc/pleb/session.env` in the
  privileged root snapshot and restore lists, and add `/etc/pleb`,
  `/usr/local/share/pleb` and `/usr/local/share/pleb/openbox` to managed-path
  validation, so a failed update cannot leave a new launcher paired with an old
  window-manager profile.
- Migrate an existing `/etc/pleb/session.env` atomically when updating, adding
  the window-manager defaults only when they are absent: an operator's explicit
  `PLEB_WM` — including `none` — or `KILIX_RUN_ALIASES` is preserved.

### Licensing

- License the Plebian-OS layer under MIT.

### Release inputs

- Advance the package snapshot to `20260727T000000Z`, picking up two weeks of
  `trixie-security` / `trixie-updates` movement; the trixie base suite is
  unchanged from 0.1.2's snapshot.
- Retain the Debian 13.5.0 archived netinst (13.6.0 has no stable
  `/cdimage/archive/` URL yet), the 0.47.4 fallback kitty engine (matching the
  pinned fork's declared engine version), and `go1.26.5` (matching the fork's
  `src/go.mod` toolchain). The exact coordinated source closure is recorded in
  [`releases/0.1.7.env`](releases/0.1.7.env).

## [0.1.2] — 2026-07-15

### Fresh-install layout

- Place all four coordinated source checkouts under
  `~/.local/gpu_terminal/sources/{plebian-os,pleb,kilix,kilix-95}` and keep runtime data under
  `~/.local/gpu_terminal/`, with the resolved source/data paths carried through
  builder metadata, firstboot configuration, session defaults, and installed
  provenance.
- Mark Pleb installs launched by Plebian-OS as managed installs, preserving the
  distribution's coordinated storage and provider configuration.
- Make Pleb's complete Kilix dependency verifier authoritative for
  `pleb update`, install a recovery guide with the preferred Plebian-OS
  dependency helper and `libxxhash-dev` fallback, and expose that guide from
  the Kilix-95 Help menu.
- Seed the branded wallpaper only in Pleb's persisted desktop state for
  Plebian-OS/Pleb sessions, independent of the selected desktop provider.
  Provider-owned state is untouched, so standalone Kilix-95 keeps its XP
  wallpaper, and existing Pleb desktop state is never replaced.
- Allocate the shared runtime-data root, every coordinated component root, and
  every Pleb, Kilix, Kilix-95, and Plebian-OS config/state/cache/session/data,
  build, prebuilt, and managed-desktop boundary as user-owned `0700`
  directories before the first provisioning or update lock, cache, or
  provenance probe can create them under a conventional umask. Nested
  boundaries are repaired component by component without replacing their
  contents; linked, escaped, or foreign-owned paths are rejected. Kilix-95 and
  Pleb also reconcile the private boundaries they own on direct launches and
  standalone operations, while genuine external desktop overrides remain
  untouched.
- Reject `sudo plebian-os-update` immediately with recovery guidance, and make
  Pleb validate both fetched and direct-install Go caches before any privileged
  staging. Traversing, linked, loosely permissioned, or unsafely owned external
  cache paths are refused.

### Coordinated release closure

- Serialize firstboot, direct Kilix, Pleb, and whole-stack updates through the
  same validated private Kilix transaction lock. Fork builds atomically
  promote contained `generations/build.*` entries with coherent `current`
  and `previous` links and one exact Kilix-owned source stamp.
- Restore the exact prior generation after any failed or signaled update,
  including same-source rebuilds; retire the legacy duplicate Pleb stamp only
  when the outer transaction commits, and collect only generations that no
  live or protected link references. Both Kitty launchers and the canonical
  source identity must pass bounded probes before provisioning or update can
  commit. Privileged rollback cleanup now reports success after every staged
  path has already moved into place while still surfacing genuine removal
  failures.
- Pin the final Pleb, Kilix, and Kilix-95 commits together with the archived
  Debian installer, package snapshot, verified Kitty fallback, and exact Go
  archives. The closure includes Kilix's current-kitty clickable-chrome rebase,
  content-only fullscreen behavior, matching Kilix-95 help, and Go 1.26.5.
- Include Kilix's fresh-storage bootstrap repair so the verified fallback
  creates its `prebuilt/` parent before publishing `kitty.app`, preventing
  firstboot retry exhaustion on a newly installed data root.
- Give every streamed graphics frame a unique, privately owned transport file
  and retire it only after the terminal engine has consumed it. This prevents
  delayed `SIGBUS` crashes caused by truncating a still-mapped framebuffer and
  bounds both Kilix and Kilix-95 frame/cache churn during long desktop or AMP
  sessions.

### Installer identity

- Added the editable angular-P geek logo, matching desktop wallpaper, and
  GPL-2.0-or-later attribution/provenance records.
- Brand the shared BIOS/UEFI splash, the BIOS title, all normal and accessible
  GRUB themes, and both graphical-installer banners. Bootloader-rendered text
  carries the coordinated Plebian-OS version so release numbers never become
  stale inside artwork.
- Replace Debian's source volume label, “Official” media descriptor, mounted
  READMEs, BIOS help identity/support route, and default English installer menu
  title with versioned Plebian-OS identity while retaining an honest Debian 13
  base description and upstream documentation links. BIOS help now advertises
  the tested 4 GiB RAM / 20 GiB disk baseline, first-boot network requirement,
  and the correct media and installed build-manifest paths.
- Validate exact PNG contracts, preserve Debian's original GTK initrd as an
  exact prefix with a deterministic three-file overlay, and refresh every entry
  in Debian's existing ISO media-check manifest after all remaster mutations.
- Install the matching desktop wallpaper as a root-owned OS asset, select it
  only for Pleb sessions without existing desktop state, record its build-time
  hash, and carry future artwork revisions through transactional self-update.
- Override Debian 13's LightDM GTK greeter with that same Plebian wallpaper,
  disabling per-user background substitution so failed-firstboot recovery and
  normal non-kiosk login screens retain the distribution identity.
- Ship the artwork attribution and complete GPL version 2 text on installer
  media and installed systems, record their hashes, and update or roll them
  back with the same OS-layer transaction as the wallpaper.
- Bridge upgrades from v0.1.1's immutable seven-file updater explicitly: the
  first update deploys the new scripts and a required second update transaction
  runs the eleven-file manifest and installs all four new payloads; updater
  state seeding occurs only after the complete stack commits.
  Configuration-preserving reprovisioning retains a strict validated-checkout
  recovery path without making bare sudo safe. This records the historical
  0.1.1-to-0.1.2 behavior only; the path is retired now that 0.1.7 is the
  fresh-install upgrade baseline.

## [0.1.1] — 2026-07-12

This is the first publishable coordinated release. It supersedes the incomplete
`v0.1.0` candidate without moving or reusing that tag.

### Security and safety

- Replaced noninteractive known passwords with printed, randomly generated
  per-image credentials; builders refuse the shipped password when enabling
  SSH. Existing VirtualBox machines now require an explicit `--replace` gate.
- Made the password-change helper a locked, one-time transition away from the
  shipped credential and retire its narrow sudo grant after use. Provisioning
  no longer follows a user-controlled `~/.dmrc` symlink as root and always
  reconciles kiosk and passwordless-sudo off states.
- Made installer `late_command` fail closed, bounded firstboot retries, and
  added systemd cleanup for temporary provisioning privileges.
- Extended both USB flashers' protected-disk graph to EFI, `/usr`, `/srv`,
  active swap, and every member below RAID/device-mapper stacks. ISO output is
  staged atomically and must retain BIOS and UEFI boot entries before replacing
  an existing artifact.

### Reproducibility and lifecycle

- Added a complete `0.1.1` release closure: archival Debian netinst URL and
  checksum, Debian Installer plus firstboot apt snapshot, immutable component
  refs, exact Go archives/checksums, and complete runtime/build provenance.
- Pinned downloaded Go archives by architecture and made their replacement
  rollback-safe. The Debian CD fallback signing key is now checked against its
  full fingerprint, and concurrent ISO-cache downloads are serialized.
- Hardened stack updates with a shared lock, clean-checkout enforcement,
  pre-sudo hash binding, and an outer recovery transaction that restores the OS
  layer, checkout positions, engine artifacts, and Pleb install outputs after a
  failure at any update boundary. Session restart is now explicit opt-in.
- Moved Pleb/Kilix state to XDG state/config locations, made first-run forks
  version-aware, and aligned the external Kilix 95 provider with the bundled
  desktop contract and shared SDK version.

### Build and verification

- Removed the duplicate Python preseed environment writer; remastering now
  produces one authoritative firstboot configuration and matching build-info.
- Made the release acceptance image inherit every immutable manifest pin while
  remaining clearly non-publishable, raised the release-tested build baseline
  to 4 GiB, and detect exhausted inactive firstboot attempts immediately.
- Made snapshot-pinned installer setup create its apt generator directory before
  staging the validity-policy hook, preventing an early-command abort in a real
  Debian Installer boot.
- Completed the system build dependency closure for the pinned Kilix fork,
  including its image/color, crypto, xxHash, SIMDe, and Wayland headers and
  protocol definitions.
- Bounded Kilix Go package compilation by default after real 2 GiB acceptance
  testing exposed repeatable compiler OOM kills in a generated dependency.
- Made shell USB builds fresh by default; reusing an ISO is now an explicit
  `--iso`/`--reuse-iso` decision. Fixed the USB-to-VM acceptance wrapper to
  include SSH intentionally and use matching secure credentials.
- Added behavioral regressions for privilege boundaries, symlink attacks,
  update rollback, exact pins, source/provider parity, input validation,
  destructive-operation gates, and multi-parent disk safety, plus CI test
  workflows for all four repositories.

## [0.1.0] — withdrawn release candidate

The coordinated `v0.1.0` tags were created before their release manifest and
integration boundary were valid. They are retained as immutable history but
must not be used to publish an image; release mode now rejects that incomplete
manifest. The notes below describe that candidate.

First coordinated, versioned release of the Plebian-OS stack.

### Added
- Shared `VERSION` (0.1.0) across plebian-os, pleb, kilix, and kilix-95, recorded
  into every image as `PLEBIAN_OS_VERSION` and reported by each component's
  version flag.
- `releases/0.1.0.env` release-pin manifest and `PLEBIAN_OS_RELEASE=<ver>` build
  plumbing, so a release image pins every moving component to its `v0.1.0` tag.
- OS-layer self-update: `plebian-os-update` now refreshes the deployed
  provisioner, dependency installer, and update helper from a pinned plebian-os
  checkout before updating pleb + kilix (`PLEBIAN_OS_REPO` / `PLEBIAN_OS_REF`).
- `PLEBIAN_OS_APT_SNAPSHOT` to pin the first-boot apt closure to a
  snapshot.debian.org timestamp, plus a recorded installed-package manifest
  (`/var/lib/plebian-os/packages.list`) for build provenance.
- Post-provision **acceptance verification** in the VM builder (`build_vm_image.py`
  / `acceptance-vm.sh`): after firstboot it checks the provisioned marker,
  Pleb xsession, `session.env`, LightDM default, kilix engine, and update helper
  over SSH (honoring an overridden `KILIX_DIR`); `--no-verify` skips it.
- kilix's **builtin desktop now honors `KILIX_DESKTOP_FLAVOR`** (95/xp) — palette,
  title-bar/taskbar gradients, and Start button — matching the external Kilix 95.
- The optional `uv` installer is now **pinnable and integrity-verified**
  (`PLEBIAN_OS_UV_VERSION` + `PLEBIAN_OS_UV_INSTALLER_SHA256`) instead of a blind
  `curl | sh`.

### Security / defaults
- Default credentials are **user `pleb` / password `plebian`** (overridable with
  the builders' `--password` or a custom preseed) so a fresh install is usable out
  of the box. The **ISO/USB install ships no ssh-server** (nothing network-reachable
  with the weak password) and the **Kilix 95 desktop shows a persistent tray
  notification** prompting the user to change it on first run, until the password is
  no longer `plebian`. This is backed by a narrow root helper (`plebian-os-passwd`)
  + a scoped NOPASSWD sudoers rule — the desktop can verify and change the password
  without any general passwordless sudo.
- The **VM builder** additionally installs `ssh-server` (for its loopback
  provisioning watch and `ssh -p … 127.0.0.1` access) and, under `--yes`, ships the
  default `plebian` password — so a `--yes` VM runs sshd with weak credentials on a
  host-loopback forward. Keep the forward local, pass `--password`, or boot the
  desktop (which nags); a `--session shell` VM has no desktop nag. `remaster-iso.sh`
  only warns on the default password, never refuses.
- `--kiosk` now enables pleb's **hard respawn** (`PLEB_RESPAWN`) and pins the
  user's remembered LightDM session to Pleb (`~/.dmrc` + AccountsService), so a
  stale remembered session can't override the seat default on the appliance.

### Fixed / hardened
- USB flasher (`make-usb.sh`, `build_usb_image.py`) now recognises the running
  root disk on btrfs/subvolume layouts — previously the `[subvol]` suffix on
  `findmnt` output defeated the root-disk refusal — and `--force` against a
  non-removable disk always requires typed confirmation even with `--yes`.
- Interactive-disk builds strip *all* `d-i partman*` directives, so the
  installer always prompts for the target disk regardless of which partitioning
  keys a preseed carries.
- The temporary provisioning sudoers grant is now removed on signals as well as
  normal exit, and cleared before every first-boot attempt.
- install-deps and the preseed share one Recommends policy
  (`--no-install-recommends` ↔ `pkgsel/install-recommends false`), so both
  provisioning paths install the same closure.
- The build-time test-credential guard fires on the weak repository password
  independently of the ssh-server task, and `build-info.env` records the full
  runtime configuration (`PLEBIAN_OS_KIOSK` / `USER` / `NOPASSWD_SUDO` /
  `INSTALL_UV` / `DESKTOP`) that was baked into the image.
