# Changelog

All notable changes to Plebian-OS — and its coordinated
pleb / kilix / kilix-95 release — are recorded here. The stack uses a single
shared version across all four repositories (see [RELEASING.md](RELEASING.md)).

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
