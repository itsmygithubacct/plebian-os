# Plebian-OS

<p align="center">
  <img src="assets/installer/logo.png" width="160" alt="Plebian-OS angular-P geek logo">
</p>

**A regular Debian install whose desktop is [Pleb](https://github.com/itsmygithubacct/pleb) —
a single screen-filling [Kilix](https://github.com/itsmygithubacct/kilix), with
its clickable chrome visible, as the whole session — in place of XFCE.**

Plebian-OS is stock Debian in every way except the "desktop": where a normal
Debian+XFCE install would give you a panel and a full desktop environment, Plebian-OS logs
you into one screen-filling Kilix (a Tilix-styled kitty fork: clickable pane buttons,
splits, pages, images, and desktop providers that open in Kilix tabs). The
login default is the main Kilix instance. `kilix desktop` selects Kilix 95 with
its 95 flavor by default; Kilix Cap and Kilix TUI are Kilix-pinned optional
desktops, and Kilix Land is a Kilix-pinned optional walkable desktop. The OS
itself ships none of that — it **installs like a regular Debian system and then
pulls its pieces from GitHub**:

```
regular Debian install  ─▶  first boot  ─▶  pull deps + pleb + kilix  ─▶  Pleb session
   (no desktop task)          (networked)     (+ desktop provider)      (visible Kilix chrome)
```

## How it works

1. **Install** — an ordinary Debian 13 (trixie) install. The only differences
   from a default install are that no desktop-environment task is selected and a
   thin graphical base (Xorg + LightDM) plus `git`/`curl`/`tar` are included.
   Either preseed it with [`preseed/preseed.cfg`](preseed/preseed.cfg) (see the
   ISO recipe below) or install plain Debian and run [`bootstrap.sh`](bootstrap.sh).
2. **First boot** — `plebian-os-firstboot.service` runs
   [`provision/plebian-os-provision.sh`](provision/plebian-os-provision.sh) once,
   after the network is up. It:
   - apt-installs the runtime deps (Xorg, LightDM, GL, fonts, tmux,
     NetworkManager's `nmtui`, and the `pulsemixer` volume control);
   - creates the shared source root `~/.local/gpu_terminal/sources`, clones/pins the
     Plebian-OS source at `~/.local/gpu_terminal/sources/plebian-os`, and clones `pleb` beside
     it at `~/.local/gpu_terminal/sources/pleb`;
   - runs a Plebian-OS-managed `pleb install`, which clones `kilix` into
     `~/.local/gpu_terminal/sources/kilix`, optionally places Kilix-95 beside it, and sets up
     the selected `kilix desktop` provider, fetches a prebuilt kitty engine, and
     registers **Pleb** as a LightDM session;
   - initializes the Kilix source submodule, installs/upgrades Go when needed,
     builds the clickable-chrome fork, and verifies Kilix uses that fork engine;
   - initializes the shared clickable-chrome settings at
     `~/.local/gpu_terminal/settings.conf` and installs `kilix-settings` on
     `PATH`, then verifies that session logging came up enabled;
   - installs Kilix’s pinned `kilix-tui-utils` checkout, including the Kilix TUI
     desktop and the unified terminal utilities;
   - initializes and builds Kilix's pinned persistent PTY broker, making
     `kilix pty` and the Kilix-95 **PTY Sessions** Start-menu entry ready on the
     first boot;
   - installs Kilix's pinned `tmux-tui`/`tmux-cli` source closure and publishes
     Tmux Manager plus tmux-cli's `tb.py` as the `tb` command on `PATH`;
   - installs the Plebian-OS wallpaper at a stable system path and selects it
     only in Pleb's persisted desktop state (existing Pleb state is preserved,
     while standalone Kilix-95 retains its XP wallpaper);
   - selects that same branded asset for the LightDM GTK greeter and disables
     per-user greeter backgrounds, including before firstboot succeeds;
   - validates and installs the artwork attribution and GPL version 2 text under
     `/usr/local/share/doc/plebian-os/`, preserving their relative link;
   - installs Pleb's update recovery guide under
     `/usr/local/share/doc/pleb/` so Kilix-95 can open it from Help;
   - pins Pleb as the default session (and, with `--kiosk`, enables autologin);
   - marks itself done and disables the service.
3. **Every boot after** — LightDM → Pleb → screen-filling Kilix with its page
   and pane chrome visible. Log out to return to
   the greeter. `Ctrl+Alt+F2` is always a plain text console.

**GUI apps** — the session runs a minimal **Openbox** underneath kilix, so
ordinary GUI commands (`chromium`, `firefox-esr`, …) open **native windows**:
focusable, closable, and reachable with `Alt-Tab` over the main Kilix window.
Openbox is deliberately bare — one desktop, no panel, no root menu, no launcher
keys.

**`kilix run <app>`** remains the explicit alternative: the app gets a private X
server and streams into a kilix tab, tiling like any terminal program. Those
in-tab clients are not host windows, so they intentionally do not appear in
Alt-Tab. Plebian-OS persists `KILIX_RUN_ALIASES=0` for native windows; set it to
`1` to send GUI commands back into kilix tabs, or use
`KILIX_RUN_ALIAS_APPS="gimp mpv"` to extend the aliased list (the mechanism is
kilix's `config/kilix.bashrc`, keyed off the Pleb session markers).

**Updating later** — refresh the whole stack with **`plebian-os-update`**. It
pulls `~/.local/gpu_terminal/sources/pleb`, re-runs `pleb install`, then delegates the Kilix, submodule,
engine, and optional desktop-provider update to `pleb update --no-restart`.
It **also refreshes the Plebian-OS layer itself** as one validated, rollback-safe
transaction (provisioner, dependency installer, unit, helpers, version,
branded wallpaper, and artwork notices) from a `plebian-os` checkout, so OS-layer fixes reach
installed systems too — pinned
by `PLEBIAN_OS_REF` and disablable with
`PLEBIAN_OS_SELF_UPDATE=0`. If `/etc/pleb/session.env` pins `PLEB_REF`,
`KILIX_REF`, `KILIX95_REF`, or `PLEBIAN_OS_REF`, the update helper keeps using
those exact refs instead of drifting to branch heads. Updates are serialized;
participating checkouts with local changes are refused. Before the first change,
the updater snapshots the deployed OS/Pleb files, checkout positions, and engine
artifacts. A failure after the OS refresh, Pleb refresh, install, or component
update restores that previous coherent stack. The OS-layer stage is also bound
to pre-sudo SHA-256 values and revalidated as root before any destination is
replaced; success is reported only after the entire outer transaction commits.
Pass `--restart` to restart the graphical session after a successful update.
Firstboot and manual reprovisioning hold the same target-user Pleb state lock,
so their checkout, engine, and provider mutations cannot race a direct update.
Downloaded git objects, package-manager additions, and a newly installed Go
toolchain are intentionally not removed during rollback; they are additive and
not selected by the restored runtime. A checkout created during a failed update
is moved into the reported recovery directory instead of being deleted.

**Upgrading from v0.1.1:** run `plebian-os-update` twice as the desktop user
after moving the Plebian-OS ref/branch to this newer revision. The immutable
v0.1.1 updater has a fixed seven-file OS-layer manifest: its first invocation
can deploy the new updater and provisioner, but cannot deploy the newly added
four files (the wallpaper, LightDM greeter override, attribution, and license
text). The second invocation runs the new eleven-file transaction, installs all
four validated payloads,
commits the complete stack, and only then seeds the wallpaper for a Pleb session
with no existing desktop state. Both invocations
are required; do not run a bare `sudo plebian-os-provision` between them because
sudo does not preserve all coordinated provider/ref/kiosk settings. The
new provisioner's validated-checkout fallback exists only for an externally
orchestrated, configuration-preserving reprovision. The normal upgrade contract
is two updater runs, and neither run overwrites existing desktop state or a
wallpaper choice.

Because pleb is the source of truth for "kilix as a session", Plebian-OS is a
thin wrapper: it decides *which repos to pull and when*, and pleb does the rest.
Nothing here forks or vendors kilix/pleb — they come straight from GitHub, so the
installed system tracks upstream.

## Quick start

**Convert a running Debian (fastest to try):**

```sh
mkdir -p ~/.local/gpu_terminal/sources
git clone https://github.com/itsmygithubacct/plebian-os ~/.local/gpu_terminal/sources/plebian-os
sudo ~/.local/gpu_terminal/sources/plebian-os/bootstrap.sh            # add Pleb alongside your current desktop
sudo ~/.local/gpu_terminal/sources/plebian-os/bootstrap.sh --kiosk    # …and boot straight into it
# preview without touching anything:
~/.local/gpu_terminal/sources/plebian-os/bootstrap.sh --dry-run
```

Log out, and at the LightDM greeter the session menu now offers **Pleb**.

The Kilix page strip includes a default-off thermometer that reports the
hottest readable sensor in green/yellow/red and opens `kilix-temps` in a new
tab. Firstboot builds and verifies Kilix's exact pinned dashboard and graphics
closure and publishes the command on `PATH`, so this works on a clean OS install
without a developer checkout. The volume control opens `pulsemixer`, with
`alsamixer` as a fallback. It appears immediately left of the network/Wi-Fi
control; Network remains immediately left of the calendar and opens `nmtui`.
Run `kilix-settings` (or `pleb settings`), or use Kilix 95's Settings menu, to
enable **Thermal status** and remove or re-add every top-bar item and pane-title
button. For scripts, use `kilix settings --set temperature=on`. All of those
interfaces use
`~/.local/gpu_terminal/settings.conf` as their single source of truth.

**Session logging is on by default.** Each pane's output is recorded by the PTY
broker to `~/.local/gpu_terminal/kilix/state/transcripts/<session>.log` — one
bounded 8 MiB log per pane, mode `0600`, with kitty graphics payloads replaced
by a byte-count marker so a pixel desktop cannot flood the log. Because the
broker owns the PTY, a detached, recovered, or crashed pane is still recorded,
including whatever it printed on its way out. Only output is captured; typed
input appears solely where the pane echoes it, so hidden password prompts are
not recorded.

```sh
kilix transcript                       # list recorded panes, newest first
kilix transcript show <session>        # print one
pleb status                            # current policy + how many logs exist
kilix settings --set transcript=off    # turn recording off
```

The same three controls (on/off, `elide`/`keep` graphics, and a `2M`/`8M`/`32M`/
`128M` per-pane budget) are in `kilix-settings` under **Session logging** and in
Kilix 95's Settings under **Session logs**; all of them write the shared
`~/.local/gpu_terminal/settings.conf`.

The Kilix 95 Start menu includes **Tmux Manager**. It opens in a new tab and
uses the pinned `tmux-tui` plus `tmux-cli` closure installed during firstboot.
Both `tmux-tui` and the `tb` alias are also available directly from a shell.

The same Programs menu includes **PTY Sessions**, a terminal UI for Kilix's
persistent panes. It lists detached sessions first and can attach, refresh, or
terminate one after confirmation; `kilix pty` opens it directly from a shell.

**Build an installer ISO** (the Debian netinst is downloaded + signature/hash
verified for you; needs `xorriso`, GNU `cpio`, `gzip`, `gpgv`, and
`debian-archive-keyring`):

```sh
build/remaster-iso.sh                          # auto-download the netinst, build the ISO
build/remaster-iso.sh my-netinst.iso out.iso   # …or point it at a local netinst
```

Fresh installations keep the core source checkouts in
`~/.local/gpu_terminal/sources/{plebian-os,pleb,kilix}`, Kilix-95 in
`~/.local/gpu_terminal/sources/kilix-desktops/kilix-95`, and runtime data in
`~/.local/gpu_terminal/{plebian-os,pleb,kilix,kilix-95}`, with shared chrome
preferences in `~/.local/gpu_terminal/settings.conf`. No legacy checkout or
data directories are moved automatically. Build cache, remaster work, session
files, and ordinary ISO artifacts live in
`~/.local/gpu_terminal/plebian-os/{cache,build,session,artifacts}`. The source
checkout stays clean. An explicit ISO output argument is always honored, so a
named release ISO can remain at its deliberate release location. Strict release
builds default to `plebian-os-<version>-amd64.iso`.

Install it like normal Debian; the first boot pulls everything and comes up as
Pleb. The raw template's offline login is **`pleb` / `plebian`** so the install
is usable out of the box; it ships no ssh-server, and the desktop persistently
prompts for the one-time transition to a new password. Python `--yes` builds
instead generate and print a random password. Any builder path that enables SSH
refuses the shipped password. Pass `--password` to choose your own secret.

The remaster brands the shared BIOS/UEFI splash, every normal and accessible
GRUB theme, the BIOS menu title, and both graphical-installer banners from
[`assets/installer/`](assets/installer/). Menu text renders the resolved
Plebian-OS release version at build time; versions are deliberately not baked
into the artwork.

**Build a bootable USB install stick** — one command downloads the netinst,
builds the (isohybrid) ISO, and flashes it to the stick:

```sh
build/make-usb.sh --list                       # find your USB device
build/build_usb_image.py --device /dev/sdX     # safest physical USB flow
build/make-usb.sh --device /dev/sdX            # shell flow; ships default pleb/plebian creds
build/make-usb.sh --device /dev/sdX --dry-run  # preview, write nothing
build/make-usb.sh                              # just build the ISO (no --device)
build/make-usb.sh --netinst local.iso --device /dev/sdX   # use a local netinst
```

The Python builder asks for credentials and, by default, leaves target-disk
selection to the Debian installer on physical USB boots. The shell/remaster path
does the same unless `--unattended-disk` or `PLEBIAN_OS_UNATTENDED_DISK=1` is
set. Both flashers refuse partitions and every disk beneath critical filesystems
or active swap (including multi-disk RAID/device-mapper stacks), show what they
will erase, and make you retype the device path. `--yes` skips that gate only for
a genuinely removable device; `--force` overrides only the removable flag. The
shell builder makes a fresh ISO by default; `--iso` or `--reuse-iso` is required
to trust an existing artifact.

## Layout

| Path | What |
|---|---|
| `provision/plebian-os-provision.sh` | the provisioner: apt deps → clone pleb → `pleb install` → set the session |
| `provision/plebian-os-firstboot.service` | systemd oneshot that runs it once on first boot |
| `provision/lightdm-gtk-greeter.conf` | fixed greeter override selecting the installed Plebian wallpaper |
| `preseed/preseed.cfg` | a regular Debian install, no desktop task, wires in the provisioner |
| `build/remaster-iso.sh` | inject the preseed + provisioner into a trixie netinst ISO |
| `build/brand-installer.py` | validate artwork, brand BIOS/UEFI text, and refresh Debian's existing media-check entries |
| `assets/installer/` | editable logo, installer-ready artwork, provenance, and licensing |
| `assets/desktop/` | matching desktop wallpaper, installed at `/usr/local/share/plebian-os/wallpapers/plebian-os.png` |
| `build/make-usb.sh` | build the ISO and flash it to a USB stick (with safety guards) |
| `build/acceptance-vm.sh` | operator-run VirtualBox acceptance: build ISO, install, wait for firstboot |
| `build/install-vm-from-usb-iso.sh` | build a USB-style ISO, then install it in a 4 GB / 4-core VirtualBox VM |
| `bootstrap.sh` | run the provisioner on an already-installed Debian |
| `VERSION` / `releases/*.env` | shared release version + coordinated pin manifests |
| `RELEASING.md` | how to cut a coordinated pleb/kilix/kilix-95/plebian-os release |

Every remastered ISO also stages `/etc/plebian-os/build-info.env` and
`/etc/default/plebian-os` into the installed system. The manifest records the
Plebian-OS commit/dirty state, source Debian ISO checksum, installer and desktop
artwork checksums, and the repo/ref/provider knobs used for that image; the firstboot env is what
`plebian-os-firstboot.service` reads when it provisions the installed system.
After provisioning finishes, `/var/lib/plebian-os/packages.list`,
`versions.env`, and `apt-sources.list` record the final installed packages,
resolved source commits, tool/engine versions, and apt indexes actually used.

## Plebian-OS vs. Plebian

The sibling **plebian** project is the *console-only* take: no X, no display
manager — kilix runs on the bare virtual terminals via a per-VT cage compositor,
`Ctrl+Alt+F1…F11` switching between independent kilix VTs. **Plebian-OS** is the
*graphical desktop* take: a normal LightDM login whose session is a
screen-filling Kilix with its own controls visible (via Pleb + Xorg). Same
spirit — "a machine whose desktop is Kilix" — reached the way a desktop distro does it (display manager + X session)
rather than by replacing the console. Pick plebian for a headless/console box,
Plebian-OS for a desktop-shaped one.

## Requirements

- A GPU with a KMS/DRM driver for hardware GL, or llvmpipe software GL as a
  fallback (kilix is a GPU terminal). No graphics at all → the greeter still
  works; the Pleb session falls back to a screen-filled kilix or a plain xterm.
- Network on first boot (it clones from GitHub).
- Go ≥ 1.26 for the Kilix fork build. Firstboot installs or upgrades the exact
  pinned Go archive through pleb's checksum-verifying, rollback-safe helper when
  the target does not already have a suitable toolchain.
  `PLEBIAN_OS_KILIX_GO_VERSION` plus the architecture-specific
  `PLEBIAN_OS_KILIX_GO_SHA256_AMD64` / `_ARM64` pins make that toolchain exact
  and integrity-checked. Exact installs must also carry Pleb's root-owned
  `.pleb-source` archive stamp; a same-version binary without the matching stamp
  is reinstalled. The pins persist into `/etc/pleb/session.env`.
- 4 GiB RAM is the release-tested installation baseline because the fork build
  compiles large generated Go packages during firstboot. Lower-memory runtime
  use remains possible after installation, but builders warn below 4 GiB.

Session and desktop-provider selection are controlled by `/etc/pleb/session.env`
after install, or by environment at image-build/provision time. Fresh images
default to `PLEBIAN_OS_DESKTOP=0` and `PLEBIAN_OS_KIOSK=0`: LightDM logs into
the main screen-filling Kilix instance with its chrome visible, and exiting it returns to the greeter
instead of respawning it. `kilix desktop` opens the selected provider in a
Kilix tab; the release pins the external Kilix-95 provider and
`KILIX_DESKTOP_FLAVOR=95`. Setting `PLEBIAN_OS_DESKTOP=1` deliberately replaces
the main instance with that provider for a desktop-only session. In that mode,
`KILIX_DESKTOP_PROVIDER` can be
`auto`, `builtin`, `external`, `xp`, `cap`, `tui`, `land`, `command`, or
`none`; `cap` downloads and locally builds Kilix Cap, `tui` installs the Kilix
TUI desktop from the pinned `kilix-tui-utils` checkout, and `land` downloads
and builds Kilix Land with its recursive dependencies. `command` uses
`KILIX_DESKTOP_COMMAND` for other desktops. `KILIX_DESKTOP_FLAVOR=95|xp`
selects the first-launch Kilix 95 flavor, and `none` behaves like a plain shell
session. Kilix Cap uses `KILIX_CAP_*`, Kilix TUI uses
`KILIX_TUI_UTILS_*`, Kilix Land uses `KILIX_LAND_DESKTOP_*`, and external
Kilix 95 uses `KILIX95_*`. The Cap, TUI, and Land source commits are inherited
through the pinned Kilix commit rather than receiving independent
coordinated-release keys. Set
`PLEBIAN_OS_BUILD_KILIX_FORK=0` only when
you deliberately want to allow the prebuilt fallback engine. Release-style
images can set `PLEBIAN_OS_RELEASE_MODE=1`, `PLEBIAN_OS_NETINST_URL`,
`PLEBIAN_OS_NETINST_SHA256`, `PLEBIAN_OS_APT_SNAPSHOT`, `PLEB_REF`, `KILIX_REF`,
`KILIX95_REF`, `KILIX_PREBUILT_VERSION`, `KILIX_PREBUILT_SHA256`, and the exact
Go version/architecture checksums before building. Simpler: set
`PLEBIAN_OS_RELEASE=0.1.2` to load the coordinated pin manifest from
[`releases/0.1.2.env`](releases/0.1.2.env) (see
[RELEASING.md](RELEASING.md)). The snapshot pin covers Debian Installer and
firstboot resolution. Snapshot switching inventories and transactionally
restores only the sources Plebian-OS disabled, preserving operator-owned files.
Enabled release-mode `uv` installs require exact version/checksum pins and are
verified after installation. Installed package/source/tool manifests make the
resolved result auditable.

## License

Except where a file says otherwise, Plebian-OS code and project documentation
are released under the [MIT License](LICENSE). The installer and desktop
artwork listed in
[`assets/installer/ATTRIBUTION.md`](assets/installer/ATTRIBUTION.md) are
separate works distributed under `GPL-2.0-or-later`; the complete license text
is in [`assets/COPYING.GPL-2`](assets/COPYING.GPL-2). Components supplied by
Debian or fetched from Pleb, Kilix, and other upstream projects retain their own
licenses.
