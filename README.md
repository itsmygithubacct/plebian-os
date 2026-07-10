# Plebian-OS

**A regular Debian install whose desktop is [Pleb](https://github.com/itsmygithubacct/pleb) —
a single fullscreen [kilix](https://github.com/itsmygithubacct/kilix) as the whole
session — in place of XFCE.**

Plebian-OS is stock Debian in every way except the "desktop": where a normal
Debian+XFCE install would give you a panel and a window manager, Plebian-OS logs
you into one fullscreen kilix (a Tilix-styled kitty fork: clickable pane buttons,
splits, pages, images, and an optional desktop provider such as Kilix 95). The OS itself ships none of
that — it **installs like a regular Debian system and then pulls its pieces from
GitHub**:

```
regular Debian install  ─▶  first boot  ─▶  pull deps + pleb + kilix  ─▶  Pleb session
   (no desktop task)          (networked)     (+ desktop provider)        (fullscreen kilix)
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
   - apt-installs the runtime deps (Xorg, LightDM, GL, fonts, tmux);
   - clones `pleb` into the user's `~/pleb`;
   - runs `pleb install`, which clones `kilix` into `~/kilix`, optionally sets up
     the selected `kilix desktop` provider, fetches a prebuilt kitty engine, and
     registers **Pleb** as a LightDM session;
   - initializes the Kilix source submodule, installs/upgrades Go when needed,
     builds the clickable-chrome fork, and verifies Kilix uses that fork engine;
   - pins Pleb as the default session (and, with `--kiosk`, enables autologin);
   - marks itself done and disables the service.
3. **Every boot after** — LightDM → Pleb → fullscreen kilix. Log out to return to
   the greeter. `Ctrl+Alt+F2` is always a plain text console.

**Updating later** — refresh the whole stack with **`plebian-os-update`**. It
pulls `~/pleb`, re-runs `pleb install`, then delegates the Kilix, submodule,
engine, and optional desktop-provider update to `pleb update --no-restart`.
It **also refreshes the Plebian-OS layer itself** (the provisioner, dependency
installer, and this helper) from a `plebian-os` checkout, so OS-layer fixes reach
installed systems too — pinned by `PLEBIAN_OS_REF` and disablable with
`PLEBIAN_OS_SELF_UPDATE=0`. If `/etc/pleb/session.env` pins `PLEB_REF`,
`KILIX_REF`, `KILIX95_REF`, or `PLEBIAN_OS_REF`, the update helper keeps using
those exact refs instead of drifting to branch heads.

Because pleb is the source of truth for "kilix as a session", Plebian-OS is a
thin wrapper: it decides *which repos to pull and when*, and pleb does the rest.
Nothing here forks or vendors kilix/pleb — they come straight from GitHub, so the
installed system tracks upstream.

## Quick start

**Convert a running Debian (fastest to try):**

```sh
git clone https://github.com/itsmygithubacct/plebian-os ~/plebian-os
sudo ~/plebian-os/bootstrap.sh            # add Pleb alongside your current desktop
sudo ~/plebian-os/bootstrap.sh --kiosk    # …and boot straight into it
# preview without touching anything:
~/plebian-os/bootstrap.sh --dry-run
```

Log out, and at the LightDM greeter the session menu now offers **Pleb**.

**Build an installer ISO** (the Debian netinst is downloaded + signature/hash
verified for you; needs `xorriso`, `gpgv`, and `debian-archive-keyring`):

```sh
build/remaster-iso.sh                          # auto-download the netinst, build the ISO
build/remaster-iso.sh my-netinst.iso out.iso   # …or point it at a local netinst
```

Install it like normal Debian; the first boot pulls everything and comes up as
Pleb. Edit `preseed/preseed.cfg` first. The repository preseed's test
credentials are refused by default when SSH is enabled; use the Python builders
for generated credentials, or set `PLEBIAN_OS_ALLOW_TEST_PRESEED=1` only for an
isolated throwaway image.

**Build a bootable USB install stick** — one command downloads the netinst,
builds the (isohybrid) ISO, and flashes it to the stick:

```sh
build/make-usb.sh --list                       # find your USB device
build/build_usb_image.py --device /dev/sdX     # safest physical USB flow
build/make-usb.sh --device /dev/sdX            # shell flow; requires edited/allowed preseed
build/make-usb.sh --device /dev/sdX --dry-run  # preview, write nothing
build/make-usb.sh                              # just build the ISO (no --device)
build/make-usb.sh --netinst local.iso --device /dev/sdX   # use a local netinst
```

The Python builder asks for credentials and, by default, leaves target-disk
selection to the Debian installer on physical USB boots. The shell/remaster path
does the same unless `--unattended-disk` or `PLEBIAN_OS_UNATTENDED_DISK=1` is
set. Both flashers refuse
partitions and system disks, show what they will erase, and make you retype the
device path to confirm (skip with `--yes`; override only the removable check
with `--force`).

## Layout

| Path | What |
|---|---|
| `provision/plebian-os-provision.sh` | the provisioner: apt deps → clone pleb → `pleb install` → set the session |
| `provision/plebian-os-firstboot.service` | systemd oneshot that runs it once on first boot |
| `preseed/preseed.cfg` | a regular Debian install, no desktop task, wires in the provisioner |
| `build/remaster-iso.sh` | inject the preseed + provisioner into a trixie netinst ISO |
| `build/make-usb.sh` | build the ISO and flash it to a USB stick (with safety guards) |
| `build/acceptance-vm.sh` | operator-run VirtualBox acceptance: build ISO, install, wait for firstboot |
| `build/install-vm-from-usb-iso.sh` | build a USB-style ISO, then install it in a 4 GB / 4-core VirtualBox VM |
| `bootstrap.sh` | run the provisioner on an already-installed Debian |
| `VERSION` / `releases/*.env` | shared release version + coordinated pin manifests |
| `RELEASING.md` | how to cut a coordinated pleb/kilix/kilix-95/plebian-os release |

Every remastered ISO also stages `/etc/plebian-os/build-info.env` and
`/etc/default/plebian-os` into the installed system. The manifest records the
Plebian-OS commit/dirty state, source Debian ISO checksum, and the
repo/ref/provider knobs used for that image; the firstboot env is what
`plebian-os-firstboot.service` reads when it provisions the installed system.

## Plebian-OS vs. Plebian

The sibling **plebian** project is the *console-only* take: no X, no display
manager — kilix runs on the bare virtual terminals via a per-VT cage compositor,
`Ctrl+Alt+F1…F11` switching between independent kilix VTs. **Plebian-OS** is the
*graphical desktop* take: a normal LightDM login whose session happens to be a
fullscreen kilix (via pleb + Xorg). Same spirit — "a machine whose desktop is
kilix" — reached the way a desktop distro does it (display manager + X session)
rather than by replacing the console. Pick plebian for a headless/console box,
Plebian-OS for a desktop-shaped one.

## Requirements

- A GPU with a KMS/DRM driver for hardware GL, or llvmpipe software GL as a
  fallback (kilix is a GPU terminal). No graphics at all → the greeter still
  works; the Pleb session falls back to a screen-filled kilix or a plain xterm.
- Network on first boot (it clones from GitHub).
- Go ≥ 1.26 for the Kilix fork build. Firstboot installs or upgrades Go through
  pleb's helper when the target does not already have a new enough toolchain.

Desktop selection is controlled by `/etc/pleb/session.env` after install, or by
environment at image-build/provision time. `PLEBIAN_OS_DESKTOP=0` gives a plain
fullscreen kilix shell. With desktop mode on, `KILIX_DESKTOP_PROVIDER` can be
`auto`, `builtin`, `external`, `command`, or `none`; `command` uses
`KILIX_DESKTOP_COMMAND`, `KILIX_DESKTOP_FLAVOR=95|xp` selects the first-launch
desktop flavor, and `none` behaves like a plain shell session. External
Kilix 95 still uses `KILIX95_*`. Set `PLEBIAN_OS_BUILD_KILIX_FORK=0` only when
you deliberately want to allow the prebuilt fallback engine. Release-style
images can set `PLEBIAN_OS_RELEASE_MODE=1`, `PLEBIAN_OS_NETINST_SHA256`,
`PLEB_REF`, `KILIX_REF`, `KILIX95_REF`, `KILIX_PREBUILT_VERSION`, and
`KILIX_PREBUILT_SHA256` before building; the builder refuses release mode unless
all of those pins are present. Simpler: set `PLEBIAN_OS_RELEASE=0.1.0` to load
the coordinated pin manifest from [`releases/0.1.0.env`](releases/0.1.0.env) (see
[RELEASING.md](RELEASING.md)) — every moving component is pinned to its `v0.1.0`
tag. `PLEBIAN_OS_APT_SNAPSHOT=<timestamp>` additionally pins the first-boot apt
closure to [snapshot.debian.org](https://snapshot.debian.org) for a fully
reproducible package set.
