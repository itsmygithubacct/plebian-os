# Plebian-OS

**A regular Debian install whose desktop is [Pleb](https://github.com/itsmygithubacct/pleb) —
a single fullscreen [kilix](https://github.com/itsmygithubacct/kilix) as the whole
session — in place of XFCE.**

Plebian-OS is stock Debian in every way except the "desktop": where a normal
Debian+XFCE install would give you a panel and a window manager, Plebian-OS logs
you into one fullscreen kilix (a Tilix-styled kitty fork: clickable pane buttons,
splits, pages, images, and the "kilix 95" desktop). The OS itself ships none of
that — it **installs like a regular Debian system and then pulls its pieces from
GitHub**:

```
regular Debian install  ─▶  first boot  ─▶  pull deps + pleb + kilix  ─▶  Pleb session
   (no desktop task)          (networked)     (apt + git clone)           (fullscreen kilix)
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
   - apt-installs the runtime deps (Xorg, LightDM, GL, fonts);
   - clones `pleb` into the user's `~/pleb`;
   - runs `pleb install`, which clones `kilix` into `~/kilix`, fetches a prebuilt
     kitty engine, and registers **Pleb** as a LightDM session;
   - pins Pleb as the default session (and, with `--kiosk`, enables autologin);
   - marks itself done and disables the service.
3. **Every boot after** — LightDM → Pleb → fullscreen kilix. Log out to return to
   the greeter. `Ctrl+Alt+F2` is always a plain text console.

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

**Build an installer ISO:**

```sh
build/remaster-iso.sh  debian-13.x-amd64-netinst.iso  plebian-os-netinst.iso
```

Install it like normal Debian; the first boot pulls everything and comes up as
Pleb. Edit `preseed/preseed.cfg` first — the account/password there are
unattended-test defaults.

**Build a bootable USB install stick** (builds the ISO, then flashes it — the
Debian installer ISO is isohybrid, so the USB image *is* that ISO):

```sh
build/make-usb.sh --list                                   # find your USB device
build/make-usb.sh --netinst debian-13.x-amd64-netinst.iso --device /dev/sdX
build/make-usb.sh --netinst debian-...-netinst.iso --iso out.iso   # build only, no flash
build/make-usb.sh --netinst ... --device /dev/sdX --dry-run        # preview, write nothing
```

It refuses non-removable / system disks, shows what it will erase, and makes you
retype the device path to confirm (skip with `--yes`; override the removable
check with `--force`).

## Layout

| Path | What |
|---|---|
| `provision/plebian-os-provision.sh` | the provisioner: apt deps → clone pleb → `pleb install` → set the session |
| `provision/plebian-os-firstboot.service` | systemd oneshot that runs it once on first boot |
| `preseed/preseed.cfg` | a regular Debian install, no desktop task, wires in the provisioner |
| `build/remaster-iso.sh` | inject the preseed + provisioner into a trixie netinst ISO |
| `build/make-usb.sh` | build the ISO and flash it to a USB stick (with safety guards) |
| `bootstrap.sh` | run the provisioner on an already-installed Debian |

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
- amd64 (the kilix prebuilt engine pleb fetches is x86_64; the fork builds
  elsewhere with Go ≥ 1.26).
