# `build_usb_image.py` — build a Plebian-OS USB install stick

`build/build_usb_image.py` builds a bootable **Plebian-OS USB installer**. It asks
a few questions (username, password, session, …), bakes them into a customized
installer ISO with the repo's own tooling, then — **safely** — writes that ISO
byte-for-byte to a physical USB device. The Plebian-OS ISO is isohybrid, so a USB
installer is just that ISO `dd`'d to the stick.

```
answers ─▶ custom preseed ─▶ ISO (remaster-iso.sh) ─▶ dd ─▶ USB stick
                                                             │
                boot a machine from it ─▶ pick install ─▶ confirm target disk
                                                          + first-boot provision
```

It reuses the preseed substitution from
[`build_vm_image.py`](build_vm_image.md) (username / password hashing / session
injection), so that intricate logic lives in **one** place and stays in sync with
`preseed.cfg`.

## Requirements

- **xorriso** — builds the ISO. The first download also needs `curl`,
  `sha256sum`, `gpgv`, and `debian-archive-keyring` to verify Debian's signed
  checksums. Not needed with `--iso`.
- **openssl** — hashes the password so the plaintext never lands on the ISO (falls
  back to a plaintext preseed line, with a warning, if absent).
- **lsblk / findmnt** (util-linux) — device inspection + safety checks.
- **sudo** (or run as root) — writing a block device needs root.
- Run it from inside a Plebian-OS checkout (it uses `preseed/` and `build/`).

Internet access is required at build time (the netinst download) and at install
time (apt + the GitHub clones on first boot).

## Quick start

```sh
build/build_usb_image.py --device /dev/sdX   # build the ISO and flash the stick
build/build_usb_image.py                      # build the ISO only; print how to flash
build/build_usb_image.py --list               # list removable devices
build/build_usb_image.py --device /dev/sdX --dry-run   # print the plan; write nothing
```

## What it asks

Each prompt shows a `[default]`; press Enter to accept it.

| Prompt | Default | Notes |
|--------|---------|-------|
| image name | `plebian` | ISO output name + default hostname |
| username | `pleb` | the uid-1000 account Pleb runs as |
| full name | `Plebian User` | GECOS field |
| password | `plebian` | hidden entry; stored **hashed** in the preseed |
| hostname | *image name* | |
| session | **desktop** | the configured `kilix desktop` provider, or a plain fullscreen kilix shell |
| autologin (kiosk) | **no** | boot straight into Pleb, or show a login greeter |
| passwordless sudo | **no** | optional single-user appliance convenience |

## Options

Every prompt has a matching flag, so the whole thing can run non-interactively.

```
--name NAME            --username NAME       --fullname "Full Name"
--hostname NAME        --password PASS
--session desktop|shell --kiosk / --no-kiosk
--sudo-nopasswd / --no-sudo-nopasswd

--device /dev/sdX      target USB stick (omit → build the ISO only, then print how to flash)
--iso PATH             flash a prebuilt ISO, skip building (see note below)
--out PATH             ISO output path (default: plebian-os-<name>.iso in the repo)
--autoboot             build a hands-off stick that auto-selects the install (see warning)
--unattended-disk      preseed partitioning too; choosing install erases without another prompt
--list                 list removable devices and exit
--force                allow a non-removable disk (never the system/root disk)
-y, --yes              accept defaults / skip the typed confirmation
--dry-run              show the plan; write nothing (no ISO build, no dd)
-h, --help             usage
```

> `--iso` reuses an already-built image as-is, so the username / password /
> session choices are **not** applied (those live in that ISO's own preseed).

## Boot behavior — menu pause by default

By default the finished stick boots to the **Debian installer menu with its normal
pause** and then leaves disk selection/confirmation interactive. Boot the target
machine from the stick, pick the install entry, confirm the disk in the installer,
and first boot provisions pleb + kilix.

### `--autoboot` (opt-in, hands-off)

`--autoboot` builds a stick whose boot menu **auto-selects the install after a
timeout** and also enables unattended disk partitioning — for a kiosk /
hands-off deployment. `--unattended-disk` enables the same partitioning behavior
without auto-selecting the boot-menu entry. Raw `remaster-iso.sh` builds are also
interactive by default; set `PLEBIAN_OS_UNATTENDED_DISK=1` only for VM or
known-target unattended installs.

> **WARNING:** booting any machine from an `--autoboot` stick **auto-installs and
> ERASES that machine's disk with no prompt.** With `--unattended-disk`, the erase
> happens after you choose the install entry. Only use these flags when that is
> exactly what you want.

## Device safety

Writing to the wrong device destroys data, so the flasher refuses anything unsafe:

- **Never a partition** — it wants the whole disk (e.g. `/dev/sdb`, not `/dev/sdb1`).
  Whole-disk NVMe/eMMC names that end in a digit (`/dev/nvme0n1`, `/dev/mmcblk0`)
  are recognized as disks, not partitions.
- **Never a non-removable disk** unless you pass `--force`.
- **Never the disk backing `/`** (the running system) — this refusal is **not**
  bypassed by `--force`.
- It shows the device size + model + `lsblk` tree and makes you **type the device
  path** to confirm (skipped only with `--yes`).
- It **unmounts** every mounted filesystem on the device before writing and aborts
  if any unmount fails, then
  `dd … oflag=sync conv=fsync` and `sync`.

Use `--list` to see the candidate removable devices first.

## Rebuilding / cleanup

The ISO is a plain file; delete it to force a rebuild, or pass a fresh `--out`:

```sh
rm -f plebian-os-<name>.iso
```

Re-flashing overwrites the stick; to reclaim it as ordinary storage afterwards,
repartition it with your usual tool (e.g. `wipefs -a /dev/sdX` then create a new
filesystem).

## Troubleshooting

- **`xorriso is required`** — install it, or pass `--iso` to flash a prebuilt image
  (no build, no xorriso).
- **`ISO has no MBR boot signature`** — the image isn't isohybrid and likely won't
  boot from USB; rebuild it with this tool (or `remaster-iso.sh`).
- **`… is not marked removable — refusing`** — you targeted a fixed disk; double-check
  with `--list`, and pass `--force` only if you are certain.
- **`… backs the running root filesystem`** — you targeted the system disk; that is
  always refused. Pick the USB stick instead.
- **`need root to write …`** — run under `sudo`, or install `sudo`.
- **Stick pauses at a menu** — that's intended (see above); pick the install entry.
  Use `--autoboot` for a hands-off stick.

## See also

- [`build_vm_image.md`](build_vm_image.md) — the VM builder this reuses (preseed logic)
- [`make-usb.sh`](make-usb.sh) — the shell USB writer whose safety logic this ports
- [`remaster-iso.sh`](remaster-iso.sh) — the ISO builder this drives
- [`../preseed/preseed.cfg`](../preseed/preseed.cfg) — the install answers
- [`../README.md`](../README.md) — what Plebian-OS is
