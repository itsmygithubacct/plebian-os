# `build_vm_image.py` — build a Plebian-OS VM image from scratch

`build/build_vm_image.py` builds a complete, ready-to-run **Plebian-OS virtual
machine** end to end. It asks a few questions (username, password, RAM, disk,
…), builds a customized installer ISO with the repo's own tooling, creates a
VirtualBox VM, runs the install **completely unattended**, and waits for
first-boot provisioning (pleb + kilix) to finish. When it returns, you have a VM
that boots into the Pleb session.

```
answers ─▶ custom preseed ─▶ ISO (remaster-iso.sh) ─▶ VBox VM ─▶ unattended
                                                                 install
                                                                    │
   ready-to-run VM ◀── first-boot provisioning (pleb + kilix) ◀─────┘
```

> Only **VirtualBox** is implemented today. `qemu` and `docker` targets are
> planned; the ISO-building half is deliberately target-agnostic so they can
> reuse it.

## Requirements

- **VirtualBox** (`VBoxManage` on `PATH`)
- **xorriso** — builds the ISO (also needs `curl` + `sha256sum` the first time,
  to download + verify the Debian netinst; it's then cached)
- **openssl** — hashes the password so the plaintext never lands on the ISO
  (falls back to a plaintext preseed line, with a warning, if absent)
- **ssh** — used to detect when the install + provisioning have finished
- Run it from inside a Plebian-OS checkout (it uses `preseed/` and `build/`).

Internet access is required: the installer pulls packages from the Debian
mirror, and first boot clones pleb + kilix from GitHub.

## Quick start

```sh
build/build_vm_image.py            # interactive — answer the prompts
build/build_vm_image.py --yes      # accept every default, no prompts
build/build_vm_image.py --dry-run  # print the plan and the generated preseed path; build nothing
```

A full run takes roughly **20–40 minutes** (unattended Debian install + apt +
the GitHub clones + the kilix engine). It streams progress the whole time.

## What it asks

Each prompt shows a `[default]`; press Enter to accept it.

| Prompt | Default | Notes |
|--------|---------|-------|
| VM name | `plebian` | VirtualBox VM name (and default hostname) |
| username | `pleb` | the uid-1000 account Pleb runs as |
| full name | `Plebian User` | GECOS field |
| password | `plebian` | hidden entry; stored **hashed** in the preseed |
| hostname | *VM name* | |
| RAM (MB) | **¼ of host RAM** | rounded to 256 MB, min 1024 |
| vCPUs | **½ of host cores** | min 1 |
| disk (GB) | **200** | **sparse** — grows on demand, doesn't preallocate |
| session | **desktop** | the kilix "95" desktop, or a plain fullscreen kilix shell |
| autologin (kiosk) | **yes** | boot straight into Pleb, or show a login greeter |
| passwordless sudo | **yes** | useful for update/restart actions inside the desktop |
| SSH host port | first free from **2222** | forwarded to the guest's port 22 |

## Options

Every prompt has a matching flag, so the whole thing can run non-interactively.

```
--name NAME            --username NAME       --fullname "Full Name"
--hostname NAME        --password PASS        --ram MB
--cpus N               --disk GB              --port HOSTPORT
--session desktop|shell --kiosk / --no-kiosk
--sudo-nopasswd / --no-sudo-nopasswd

--target virtualbox    only virtualbox today (qemu/docker planned)
--iso PATH             use a prebuilt ISO, skip building (see note below)
--out PATH             ISO output path (default: plebian-os-<name>.iso)
--gui                  start the VM with a window instead of headless
--no-wait              create + start the VM, but don't block on provisioning
--timeout MIN          how long to wait for provisioning (default 60)
-y, --yes              accept defaults / skip confirmations
--dry-run              show the plan; build nothing
-h, --help             usage
```

> `--iso` reuses an already-built image as-is, so the username / password /
> session choices are **not** applied (those live in that ISO's own preseed).

## What you get

A registered VirtualBox VM configured with:

- **Disk**: a sparse (`--variant Standard`) VDI of the chosen size — it only
  consumes real space as the guest writes.
- **Network**: NAT, with a host→guest port-forward so `ssh -p <port>
  <user>@127.0.0.1` reaches the guest.
- **Boot**: disk first, DVD second — the empty disk falls through to the ISO for
  the install, and every boot after that comes up from disk.
- **Session**: boots into the Pleb session — the kilix "95" desktop (or a plain
  kilix shell), with a greeter or straight-in autologin per your answers.
- **sudo**: passwordless by default for the generated user, unless you pass
  `--no-sudo-nopasswd`.

On success the tool detaches the install ISO and prints how to start and reach
the VM:

```
✓ Plebian-OS VirtualBox image is ready.
  VM        : plebian
  login     : pleb / (the password you set)
  session   : kilix 95 desktop (autologin)
  start GUI : VBoxManage startvm plebian --type gui
  ssh in    : ssh -p 2222 pleb@127.0.0.1
```

## Changing the session later

The session mode is a plain config file the image owns — no rebuild needed.
Inside the VM, edit **`/etc/pleb/session.env`**:

- `PLEB_DESKTOP=1` → boots the kilix "95" desktop; `0` → a plain fullscreen
  kilix shell (or delete the file).
- Autologin: `~/pleb/bin/pleb autologin on|off`.
- Passwordless sudo: remove or edit `/etc/sudoers.d/plebian-os-nopasswd`.

At build time these come from `--session` / `--kiosk` /
`--sudo-nopasswd` (or `PLEBIAN_OS_DESKTOP` / `PLEBIAN_OS_KIOSK` /
`PLEBIAN_OS_NOPASSWD_SUDO`).

## How it works

1. **Customized preseed.** It starts from `preseed/preseed.cfg`, substitutes the
   username / full name / hostname, replaces the password with an
   `openssl passwd -6` hash, and injects the first-boot options
   (`/etc/default/plebian-os` → `PLEBIAN_OS_DESKTOP` / `PLEBIAN_OS_KIOSK` /
   `PLEBIAN_OS_NOPASSWD_SUDO`, which the provisioner reads via the unit's
   `EnvironmentFile`).
2. **ISO build.** It calls **`build/remaster-iso.sh`** with
   `PLEBIAN_OS_PRESEED=<generated>` and `PLEBIAN_OS_AUTOBOOT=1`. The latter makes
   the installer's boot menu auto-select the (preseeded) install after a short
   timeout instead of waiting for a keypress — needed for a hands-off VM build.
   `remaster-iso.sh` also puts `locale=`/`keymap=` (read from the preseed) on the
   kernel command line so the language/keyboard prompts are answered before the
   preseed is even read. To change the language, edit the preseed's
   `debian-installer/locale` and `keyboard-configuration/xkb-keymap`.
3. **VM creation.** Standard `VBoxManage` calls: create + register, set
   memory/CPUs/VRAM, NAT + port-forward, a sparse VDI on a SATA controller, and
   the disk-first boot order.
4. **Install + wait.** It starts the VM and polls over SSH until
   `/var/lib/plebian-os/provisioned` appears (or the unit reports failure, in
   which case it dumps the journal). With no SSH yet, it's still installing; once
   SSH answers, provisioning is running.

## Rebuilding / cleanup

Re-running with the same `--name` offers to delete and recreate the VM (auto
under `--yes`). To remove one by hand:

```sh
VBoxManage controlvm <name> poweroff
VBoxManage unregistervm <name> --delete
rm -f plebian-os-<name>.iso
```

## Troubleshooting

- **Stuck at the boot menu / a language prompt** — you're on an ISO built
  without the auto-boot + `locale=` handling; rebuild with this tool (it sets
  both). For a plain USB stick the menu pause is intentional.
- **`first-boot provisioning FAILED`** — the tool prints the unit's journal.
  Common causes are no network (the clones/apt fail) or a GitHub outage.
- **Timed out waiting** — the VM is left running; open it with
  `VBoxManage startvm <name> --type gui` to see where it is, and raise
  `--timeout` on a slow link.
- **Can't SSH in** — confirm the forwarded port (`ssh -p <port> <user>@127.0.0.1`)
  and that the guest finished booting.

## See also

- [`../README.md`](../README.md) — what Plebian-OS is
- [`remaster-iso.sh`](remaster-iso.sh) — the ISO builder this drives
- [`../preseed/preseed.cfg`](../preseed/preseed.cfg) — the install answers
- [`../provision/plebian-os-provision.sh`](../provision/plebian-os-provision.sh)
  — the first-boot provisioner
