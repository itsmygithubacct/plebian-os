# Installing Plebian-OS

How installation and first-boot provisioning work, how to convert an existing
Debian, and how to build installer media. Updates are described in
[updates.md](updates.md); everyday desktop controls in
[desktop.md](desktop.md).

## How it works

1. **Install** — an ordinary Debian 13 (trixie) install. The only differences
   from a default install are that no desktop-environment task is selected and a
   thin graphical base (Xorg + LightDM) plus `git`/`curl`/`tar` are included.
   Either preseed it with [`preseed/preseed.cfg`](../preseed/preseed.cfg) (see the
   ISO recipe below) or install plain Debian and run [`bootstrap.sh`](../bootstrap.sh).
2. **First boot** — `plebian-os-firstboot.service` runs
   [`provision/plebian-os-provision.sh`](../provision/plebian-os-provision.sh) once,
   after the network is up. It:
   - apt-installs the runtime deps (Xorg, LightDM, GL, fonts, tmux,
     NetworkManager's `nmtui`, the `pulsemixer` volume control, the Evince PDF
     viewer, and the Poppler/GLib/Cairo headers for Kilix's native PDF viewer);
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
   - seeds the owner's `~/.bash_aliases` with a `tb` alias for that same
     installed `tb.py` under `~/.local/bin`, skipping it with a note when `tb`
     already resolves to an existing command, alias, or function;
   - seeds that same file with an `ask` alias for `kilix ask` (0.2.3 rc5 and
     onward), skipping it with a note when `ask` already resolves to an
     existing command, alias, or function;
   - installs and executes Kilix Voice's read-aloud tools; release 0.1.7 also
     installs the URL/SHA-256-pinned Vosk library and small US-English model,
     preserves their Apache-2.0 license and source provenance, and rejects
     firstboot unless the offline dictation diagnostic reports ready;
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

**GUI apps** — ordinary graphical commands (`chromium`, `firefox-esr`,
`evince`, `feh`, …) are
routed through `kilix run`, so their windows remain controlled inside Kilix
tabs and panes. The session still runs a deliberately bare **Openbox** safety
net underneath Kilix — one desktop, no panel, no root menu, no launcher keys —
for unavoidable native dialogs and an explicit native-window opt-out.

**`kilix run <app>`** is the explicit spelling: the app gets a private X server
and streams into a Kilix tab, tiling like any terminal program. Plebian-OS
persists `KILIX_RUN_ALIASES=1`; Kilix combines common Debian GUI commands with
visible, non-terminal entries in the installed XDG application catalogue. Set
the policy to `0` for native Openbox windows, extend it with
`KILIX_RUN_ALIAS_APPS="gimp mpv"`, or exempt a command with
`KILIX_RUN_ALIAS_EXCLUDE_APPS="gimp"`.

Updating an installed system is described in [updates.md](updates.md).

Because pleb is the source of truth for "kilix as a session", Plebian-OS is a
thin wrapper: it decides *which repos to pull and when*, and pleb does the rest.
Nothing here forks or vendors kilix/pleb — they come straight from GitHub, so the
installed system tracks upstream.

## Quick start

**Convert a running Debian (fastest to try):**

For 0.2.2, first obtain the offline release asset
[`ollama-0.32.14-kilix-unix-vulkan-r1.tar.xz`](https://github.com/itsmygithubacct/plebian-os/releases/download/v0.2.2/ollama-0.32.14-kilix-unix-vulkan-r1.tar.xz)
and verify it against the [published checksums](https://github.com/itsmygithubacct/plebian-os/releases/download/v0.2.2/SHA256SUMS). Keep it on a local disk. The
bootstrap does not download the carrier. Pass its path explicitly; preflight
checks the release manifest and archive before changing packages.

```sh
mkdir -p ~/.local/gpu_terminal/sources
git clone --branch v0.2.2 https://github.com/itsmygithubacct/plebian-os ~/.local/gpu_terminal/sources/plebian-os
carrier="$HOME/Downloads/ollama-0.32.14-kilix-unix-vulkan-r1.tar.xz"
sudo ~/.local/gpu_terminal/sources/plebian-os/bootstrap.sh --ollama-carrier "$carrier"         # add Pleb alongside your current desktop
sudo ~/.local/gpu_terminal/sources/plebian-os/bootstrap.sh --ollama-carrier "$carrier" --kiosk # …and boot straight into it
# preview without touching anything:
~/.local/gpu_terminal/sources/plebian-os/bootstrap.sh --ollama-carrier "$carrier" --dry-run
```

The provisioner also accepts `PLEBIAN_OS_OLLAMA_CARRIER=/path/to/<asset>`.
When running from a source checkout, it stages that checkout's
`releases/<VERSION>.env` as `ollama-release.env`; if an ISO-staged manifest is
also present, both copies must match byte for byte. The manifest must declare
the exact numeric OS version. For example, a `v0.2.3-rc1` source checkout with
`VERSION=0.2.3` requires `releases/0.2.3.env`. A missing or mismatched manifest
stops provisioning before package changes; another release's pins are never
substituted. OS updates deploy this manifest with `VERSION` and restore both
on rollback. Existing 0.2.2 installations may still use their legacy
`0.2.2.env` file when `ollama-release.env` is absent.

Log out, and at the LightDM greeter the session menu now offers **Pleb**.

What the desktop offers after that first login (thermal status, session
logging, Tmux Manager and PTY Sessions) is described in
[desktop.md](desktop.md).

**Build an installer ISO** (the Debian netinst is downloaded + signature/hash
verified for you; needs `xorriso`, GNU `cpio`, `gzip`, `gpgv`, and
`debian-archive-keyring`):

For 0.2.2, set `PLEBIAN_OS_OLLAMA_CARRIER` to the local release asset before
running an ISO-building command. The netinst may be fetched by the builder; the
Ollama carrier is always supplied locally and is never downloaded.

```sh
export PLEBIAN_OS_OLLAMA_CARRIER=/path/to/ollama-0.32.14-kilix-unix-vulkan-r1.tar.xz
build/remaster-iso.sh                          # auto-download the netinst, build the ISO
build/remaster-iso.sh my-netinst.iso out.iso   # …or point it at a local netinst
```

From 0.2.3 the remaster also requires the release's default model archive and
Ask command model archive as local files: set
`PLEBIAN_OS_DEFAULT_MODELS_BUNDLE` and `PLEBIAN_OS_COMMAND_MODEL_BUNDLE`. Their
URLs, sizes and SHA-256 values are pinned in
[`provision/default-models.json`](../provision/default-models.json) and
[`provision/command-model.json`](../provision/command-model.json).

For publishable, version-bound installation media, follow
[`RELEASING.md`](../RELEASING.md) rather than copying the newest ISO from an
artifacts directory. Automated VM images are isolated under
`~/.local/gpu_terminal/plebian-os/artifacts/acceptance/`; they auto-install,
erase the target disk, carry the volume label `PLEBIAN-TEST-ERASES-DISK`, and
must never be written to USB or booted on real hardware.

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

Install it like normal Debian; Debian Installer asks for hostname, full name,
username, and a concealed password twice. The normal image contains no shared
identity or known credential, keeps root login disabled, and ships no SSH
server. First boot records the account selected by the installer, pulls the
coordinated stack, and comes up as Pleb.

Automated VM/CI media is a separate, non-publishable profile. It requires an
explicit username and hostname plus either a crypt hash or password supplied
through an owner-only mode-0600 file. The acceptance harness can instead
generate a one-time password internally; it never prints or exports the secret
and expires it after verification. The old `IMAGE_PASSWORD`,
`RANDOM_PASSWORD`, and plaintext `--password` interfaces are rejected.

The remaster brands the shared BIOS/UEFI splash, every normal and accessible
GRUB theme, the BIOS menu title, and both graphical-installer banners from
[`assets/installer/`](../assets/installer/). Menu text renders the resolved
Plebian-OS release version at build time; versions are deliberately not baked
into the artwork.

**Build a bootable USB install stick** — one command downloads the netinst,
builds the (isohybrid) ISO, and flashes it to the stick:

For 0.2.2, set the same local carrier before invoking a command that builds the
ISO:

```sh
export PLEBIAN_OS_OLLAMA_CARRIER=/path/to/ollama-0.32.14-kilix-unix-vulkan-r1.tar.xz
build/make-usb.sh --list                       # find your USB device
build/build_usb_image.py --device /dev/sdX     # safest physical USB flow
build/make-usb.sh --device /dev/sdX            # shell flow; installer asks for identity
build/make-usb.sh --device /dev/sdX --dry-run  # preview, write nothing
build/make-usb.sh                              # just build the ISO (no --device)
build/make-usb.sh --netinst local.iso --device /dev/sdX   # use a local netinst
```

Both builders leave identity and target-disk selection to Debian Installer on
normal physical USB boots. A deliberately separate
`build_usb_image.py --unattended-profile` accepts protected CI/lab identity
inputs; unattended disk and SSH flags require that profile. Both flashers refuse
partitions and every disk beneath critical filesystems
or active swap (including multi-disk RAID/device-mapper stacks), show what they
will erase, and make you retype the device path. A target is admitted normally
when the kernel reports `RM=1`, `TRAN=usb`, or `HOTPLUG=1`, covering USB sticks
whose controllers expose fixed media. `--yes` skips the typed gate only with one
of those signals; `--force` overrides only that evidence check and still requires
the exact device path. The shell builder makes a fresh ISO by default; `--iso`
or `--reuse-iso` is required to trust an existing artifact.
