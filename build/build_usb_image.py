#!/usr/bin/env python3
"""build_usb_image.py — build a Plebian-OS USB install stick.

Interactively asks the same few questions as the VM builder (username, password,
session, …), bakes them into a customized Plebian-OS installer ISO with the
repo's own tooling, then — safely — writes that ISO byte-for-byte to a physical
USB device. The ISO is isohybrid, so a USB installer is just the ISO dd'd to the
stick.

    build/build_usb_image.py --device /dev/sdX   # build + flash a stick
    build/build_usb_image.py                      # build the ISO only, no flash
    build/build_usb_image.py --list               # show removable devices
    build/build_usb_image.py --device /dev/sdX --dry-run   # print the plan only

By default the finished stick boots to the Debian installer MENU with its normal
pause — a deliberate gate on physical hardware. Pick the install entry and the
installer asks you to confirm the target disk before first-boot provisioning
pulls pleb + kilix. Pass --unattended-disk to preseed partitioning too; pass
--autoboot for a hands-off stick that auto-selects the install after a timeout
and erases without another prompt (see the flag's warning).

The intricate preseed substitution is reused from build_vm_image.py so it stays
in one place, in sync with preseed.cfg.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import build_vm_image as vm  # sibling module: reuse its preseed/crypt/prompt logic

REPO = Path(__file__).resolve().parent.parent
PRESEED_TEMPLATE = REPO / "preseed" / "preseed.cfg"
REMASTER = REPO / "build" / "remaster-iso.sh"

# ── terminal helpers ("[build-usb]" label; reuse vm.have/vm.run) ──────────────
def info(s: str) -> None: print(vm.c("1;36", "[build-usb]"), s)
def warn(s: str) -> None: print(vm.c("1;33", "[build-usb]"), s, file=sys.stderr)
def die(s: str) -> None:
    print(vm.c("1;31", "[build-usb] " + s), file=sys.stderr)
    sys.exit(1)

# ── config ────────────────────────────────────────────────────────────────────
# Exactly the fields vm.generate_preseed reads (+ name for the ISO/hostname).
@dataclass
class Config:
    name: str
    username: str
    fullname: str
    password: str
    hostname: str
    desktop: bool          # PLEBIAN_OS_DESKTOP: boot into `kilix desktop`
    kiosk: bool            # PLEBIAN_OS_KIOSK: autologin straight into Pleb
    nopasswd_sudo: bool    # PLEBIAN_OS_NOPASSWD_SUDO: passwordless sudo for the user

# ── prompting (reuse the VM builder's Prompter) ──────────────────────────────
def gather_config(args) -> Config:
    p = vm.Prompter(args.yes)
    print(vm.c("1", "\nPlebian-OS → USB installer builder\n"))
    if not args.yes:
        print("Answer the prompts (Enter accepts the [default]).\n")

    name     = args.name     or p.ask("image name", "plebian")
    username = args.username or p.ask("username", "pleb")
    fullname = args.fullname or p.ask("full name", "Plebian User")
    password = args.password or p.ask_password("plebian")
    hostname = args.hostname or p.ask("hostname", name)
    if args.session:
        desktop = args.session == "desktop"
    else:
        desktop = p.ask_bool("boot into the configured kilix desktop (vs plain shell)", True)
    kiosk = args.kiosk if args.kiosk is not None \
                       else p.ask_bool("autologin (kiosk) instead of a login screen", False)
    nopasswd = args.nopasswd_sudo if args.nopasswd_sudo is not None \
                       else p.ask_bool(f"passwordless sudo for {username}", False)

    return Config(name=name, username=username, fullname=fullname, password=password,
                  hostname=hostname, desktop=desktop, kiosk=kiosk,
                  nopasswd_sudo=nopasswd)

def confirm_summary(cfg: Config, out_iso: Path, device: str | None,
                    autoboot: bool, unattended_disk: bool,
                    assume_yes: bool) -> None:
    print(vm.c("1", "\nAbout to build:"))
    rows = [
        ("image name", cfg.name), ("username", cfg.username), ("hostname", cfg.hostname),
        ("session", "kilix desktop" if cfg.desktop else "plain kilix shell"),
        ("login", "autologin (kiosk)" if cfg.kiosk else "greeter"),
        ("sudo", "passwordless" if cfg.nopasswd_sudo else "password required"),
        ("ISO out", out_iso),
        ("boot menu", "auto-selects install (--autoboot)" if autoboot
                      else "menu pause — pick the install entry"),
        ("disk setup", "unattended erase" if unattended_disk
                       else "installer asks for target disk"),
        ("flash to", device or "(none — build the ISO only)"),
    ]
    for k, v in rows:
        print(f"  {k:<10}: {v}")
    print()
    if assume_yes:
        return
    try:
        if input("Proceed? [Y/n]: ").strip().lower() in ("n", "no"):
            die("aborted.")
    except EOFError:
        pass

# ── ISO build (reuse remaster-iso.sh; autoboot only when asked) ──────────────
def build_iso(preseed: Path | None, out_iso: Path, autoboot: bool,
              unattended_disk: bool, dry_run: bool) -> Path:
    info(f"building installer ISO via {REMASTER.name} (custom preseed baked in)")
    env = {**os.environ, "PLEBIAN_OS_PRESEED": str(preseed)}
    # Default: NO autoboot — the stick pauses at the installer menu on purpose.
    # --autoboot makes it auto-select the (unattended) install for a kiosk stick.
    # Clear any inherited value so a pre-exported PLEBIAN_OS_AUTOBOOT can't
    # silently turn a default menu-pause stick into an auto-erase one.
    if autoboot:
        env["PLEBIAN_OS_AUTOBOOT"] = "1"
    else:
        env.pop("PLEBIAN_OS_AUTOBOOT", None)
    if unattended_disk:
        env["PLEBIAN_OS_UNATTENDED_DISK"] = "1"
    else:
        env.pop("PLEBIAN_OS_UNATTENDED_DISK", None)
    if dry_run:
        auto = "PLEBIAN_OS_AUTOBOOT=1 " if autoboot else ""
        disk = "PLEBIAN_OS_UNATTENDED_DISK=1 " if unattended_disk else ""
        seed = preseed if preseed is not None else "<generated preseed>"
        info(f"+ {auto}{disk}PLEBIAN_OS_PRESEED={seed} {REMASTER} '' {out_iso}")
        return out_iso
    vm.run([REMASTER, "", str(out_iso)], env=env)
    if not out_iso.exists():
        die(f"ISO build did not produce {out_iso}")
    return out_iso

def make_usb_preseed(cfg: Config, unattended_disk: bool) -> Path:
    preseed = vm.generate_preseed(cfg)
    if unattended_disk:
        return preseed
    text = preseed.read_text()
    text = re.sub(r"^d-i partman-auto/.*\n", "", text, flags=re.MULTILINE)
    text = re.sub(r"^d-i partman-partitioning/.*\n", "", text, flags=re.MULTILINE)
    text = re.sub(r"^d-i partman/choose_partition .*\n", "", text, flags=re.MULTILINE)
    text = re.sub(r"^d-i partman/confirm.*\n", "", text, flags=re.MULTILINE)
    preseed.write_text(text)
    return preseed

def check_iso_bootsig(iso: Path) -> None:
    # Isohybrid images carry an MBR boot signature at offset 510; warn if missing.
    try:
        with open(iso, "rb") as fh:
            fh.seek(510)
            sig = fh.read(2)
    except OSError as e:
        warn(f"could not read ISO boot signature: {e}")
        return
    if sig != b"\x55\xaa":
        warn("ISO has no MBR boot signature — it may not boot from USB (isohybrid?)")

# ── device safety (ported from make-usb.sh) ──────────────────────────────────
def _lsblk(args) -> str:
    r = subprocess.run(["lsblk", *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""

def _block_kname(device: str) -> str | None:
    try:
        st = os.stat(device)
    except OSError:
        return None
    if not stat.S_ISBLK(st.st_mode):
        return None
    sysdev = Path(f"/sys/dev/block/{os.major(st.st_rdev)}:{os.minor(st.st_rdev)}")
    try:
        return sysdev.resolve().name
    except OSError:
        return Path(os.path.realpath(device)).name

def _parent_map() -> dict[str, str]:
    parents: dict[str, str] = {}
    for line in _lsblk(["-rno", "NAME,PKNAME"]).splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1]:
            parents[parts[0]] = parts[1]
    return parents

def _ancestors(kname: str, parents: dict[str, str] | None = None) -> set[str]:
    parents = parents or _parent_map()
    out = {kname}
    cur = kname
    while parents.get(cur) and parents[cur] not in out:
        cur = parents[cur]
        out.add(cur)
    return out

def _root_disks() -> set[str]:
    """Block-device kernel names we must never flash.

    This protects the full ancestry of critical mounted filesystems, so LUKS,
    LVM, dm-crypt, mdraid, and /dev/disk/by-* symlinks resolve back to the
    physical disk before comparison.
    """
    parents = _parent_map()
    names: set[str] = set()
    for target in ("/", "/boot", "/home", "/var"):
        src = subprocess.run(["findmnt", "-no", "SOURCE", "--target", target],
                             capture_output=True, text=True).stdout.strip()
        if not src or not src.startswith("/dev/"):
            continue
        kname = _block_kname(src)
        if kname:
            names.update(_ancestors(kname, parents))
    return names

def _is_partition(base: str) -> bool:
    """True if `base` names a partition rather than a whole disk.

    NVMe/eMMC whole disks legitimately end in a digit (nvme0n1, mmcblk0); their
    partitions carry a 'p' suffix (nvme0n1p1). For everything else (sdX) a
    trailing digit means a partition.
    """
    if re.fullmatch(r"(nvme\d+n\d+|mmcblk\d+)", base):
        return False
    if re.fullmatch(r"(nvme\d+n\d+|mmcblk\d+)p\d+", base):
        return True
    return bool(base) and base[-1].isdigit()

def list_devices() -> None:
    info("removable block devices:")
    any_found = False
    for d in sorted(Path("/sys/block").glob("*")):
        name = d.name
        if name.startswith(("loop", "ram", "sr", "dm-", "md", "zram")):
            continue
        try:
            if (d / "removable").read_text().strip() != "1":
                continue
        except OSError:
            continue
        size = _lsblk(["-dno", "SIZE", f"/dev/{name}"]) or "?"
        try:
            model = " ".join((d / "device" / "model").read_text().split()) or "?"
        except OSError:
            model = "?"
        print(f"    /dev/{name:<8} {size:>8}  {model}")
        any_found = True
    if not any_found:
        print("    (none found — plug in a USB stick, or pass --force for a fixed disk)")

def validate_device(device: str, force: bool) -> tuple[str, str]:
    """Refuse anything unsafe; return (size, model) for a valid target."""
    if not Path(device).is_block_device():
        die(f"{device} is not a block device")
    base = _block_kname(device) or Path(os.path.realpath(device)).name
    dev_type = _lsblk(["-dnro", "TYPE", device])
    if dev_type != "disk":
        die(f"{device} looks like a partition; you want the whole disk")
    # never the disk backing '/' (this refusal is NOT bypassed by --force)
    if base and base in _root_disks():
        die(f"{device} backs the running root filesystem — refusing")
    # never a non-removable disk unless --force (which bypasses ONLY this check)
    try:
        removable = Path(f"/sys/block/{base}/removable").read_text().strip()
    except OSError:
        removable = "0"
    if removable != "1" and not force:
        die(f"{device} is not marked removable — refusing (pass --force if certain)")
    try:
        model = " ".join(Path(f"/sys/block/{base}/device/model").read_text().split()) or "?"
    except OSError:
        model = "?"
    size = _lsblk(["-dno", "SIZE", device]) or "?"
    return size, model

def _mounted_targets(device: str) -> list[str]:
    r = subprocess.run(["lsblk", "-J", "-o", "NAME,MOUNTPOINTS", device],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        return []
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []
    mounts: list[str] = []

    def walk(node) -> None:
        for mp in node.get("mountpoints") or []:
            if mp:
                mounts.append(mp)
        for child in node.get("children") or []:
            walk(child)

    for dev in data.get("blockdevices") or []:
        walk(dev)
    return sorted(set(mounts), key=len, reverse=True)

def confirm_device(device: str, iso: Path, size: str, model: str, assume_yes: bool) -> None:
    warn(f"about to ERASE {device}  ({size}, {model}) and write {iso}")
    out = _lsblk([device])
    if out:
        print("\n".join("    " + ln for ln in out.splitlines()))
    if assume_yes:
        return
    prompt = vm.c("1;31", f"Type the device path to confirm ({device}): ")
    try:
        typed = input(prompt).strip()
    except EOFError:
        typed = ""
    if typed != device:
        die("confirmation did not match — aborted")

def flash(device: str, iso: Path) -> None:
    # A block device needs root; use sudo per-command so the typed confirmation
    # stays in the user's own shell (no re-exec).
    sudo: list[str] = []
    if os.geteuid() != 0:
        if not vm.have("sudo"):
            die(f"need root to write {device} (run with sudo)")
        sudo = ["sudo"]
    for mp in _mounted_targets(device):
        r = subprocess.run([*sudo, "umount", mp], capture_output=True, text=True)
        if r.returncode != 0:
            detail = (r.stderr or r.stdout or "").strip()
            die(f"failed to unmount {mp!r}; refusing to overwrite a mounted filesystem"
                + (f": {detail}" if detail else ""))
    info(f"writing {iso} -> {device} (this can take a few minutes)")
    vm.run([*sudo, "dd", f"if={iso}", f"of={device}", "bs=4M",
            "status=progress", "oflag=sync", "conv=fsync"])
    vm.run([*sudo, "sync"])

# ── summaries ────────────────────────────────────────────────────────────────
def iso_only_summary(iso: Path) -> None:
    info(f"ISO ready: {iso}")
    info("it is a USB-bootable (isohybrid) image. Write it with either:")
    info(f"    build/build_usb_image.py --iso {iso} --device /dev/sdX")
    info(f"    sudo dd if={iso} of=/dev/sdX bs=4M status=progress oflag=sync conv=fsync")

def final_summary(cfg: Config, iso: Path, device: str, autoboot: bool,
                  from_iso: bool) -> None:
    print(vm.c("1;32", "\n✓ Plebian-OS install stick is ready.\n"))
    print(f"  device    : {device}")
    if from_iso:
        # A prebuilt ISO carries its own preseed; the flags didn't set these, so
        # don't claim a username/session the image may not actually use.
        print("  login     : whatever the prebuilt ISO's preseed defines")
    else:
        print(f"  login     : {cfg.username} / (the password you set)")
        print(f"  session   : {'kilix desktop' if cfg.desktop else 'kilix shell'}"
              f"{' (autologin)' if cfg.kiosk else ' (greeter)'}")
        print(f"  sudo      : {'passwordless' if cfg.nopasswd_sudo else 'password required'}")
    print(f"  ISO       : {iso}")
    if autoboot:
        print(vm.c("1;31",
              "  WARNING   : this stick AUTO-BOOTS the install — booting a machine\n"
              "              from it ERASES that machine's disk with no prompt."))
    else:
        print("  to install: boot the target from this stick, pick the install entry;\n"
              "              then confirm the target disk in the installer.")
    print()

# ── main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(description="Build a Plebian-OS USB install stick.")
    ap.add_argument("--name"); ap.add_argument("--username"); ap.add_argument("--fullname")
    ap.add_argument("--hostname"); ap.add_argument("--password")
    ap.add_argument("--session", choices=["desktop", "shell"])
    ap.add_argument("--kiosk", dest="kiosk", action="store_true", default=None,
                    help="autologin straight into Pleb")
    ap.add_argument("--no-kiosk", dest="kiosk", action="store_false")
    ap.add_argument("--sudo-nopasswd", dest="nopasswd_sudo", action="store_true",
                    default=None, help="grant the user passwordless sudo")
    ap.add_argument("--no-sudo-nopasswd", dest="nopasswd_sudo", action="store_false",
                    help="require a password for sudo")
    ap.add_argument("--device", help="target USB device, e.g. /dev/sdX "
                    "(omit to build the ISO only)")
    ap.add_argument("--iso", type=Path, help="flash this prebuilt ISO, skip building")
    ap.add_argument("--out", type=Path, default=None,
                    help="ISO output path when building (default: plebian-os-<name>.iso)")
    ap.add_argument("--autoboot", action="store_true",
                    help="build a hands-off stick that auto-selects the install "
                         "(it then ERASES the booted machine's disk with no prompt)")
    ap.add_argument("--unattended-disk", action="store_true",
                    help="preseed partitioning too, so choosing install erases the "
                         "target disk without another installer prompt")
    ap.add_argument("--list", action="store_true", help="list removable devices and exit")
    ap.add_argument("--force", action="store_true",
                    help="allow a non-removable disk (never the system/root disk)")
    ap.add_argument("-y", "--yes", action="store_true", help="accept defaults, no prompts")
    ap.add_argument("--dry-run", action="store_true", help="show the plan; write nothing")
    args = ap.parse_args()

    if args.list:
        list_devices()
        return

    building = args.iso is None
    # preflight
    if building and not args.dry_run and not vm.have("xorriso"):
        die("xorriso is required to build the ISO but is not installed.")
    if not PRESEED_TEMPLATE.exists() or not REMASTER.exists():
        die("run this from a Plebian-OS checkout (preseed/ + build/ not found).")

    if args.iso:
        cfg = Config(name=args.name or "plebian", username=args.username or "pleb",
                     fullname=args.fullname or "Plebian User",
                     password=args.password or "", hostname=args.hostname or "",
                     desktop=args.session != "shell", kiosk=bool(args.kiosk),
                     nopasswd_sudo=bool(args.nopasswd_sudo))
        warn("using a prebuilt ISO: custom username/password/session are NOT applied "
             "(they live in the ISO's preseed).")
    else:
        cfg = gather_config(args)

    out_iso = (args.iso or args.out or (REPO / f"plebian-os-{cfg.name}.iso")).resolve()
    unattended_disk = args.autoboot or args.unattended_disk
    confirm_summary(cfg, out_iso, args.device, args.autoboot, unattended_disk, args.yes)

    # ── build the ISO (unless flashing a prebuilt one) ──
    if args.iso:
        iso = out_iso
        if not iso.exists() and not args.dry_run:
            die(f"--iso not found: {iso}")
    else:
        # --dry-run writes NOTHING: skip generating the temp preseed (which would
        # spawn openssl and drop a /tmp file) since build_iso won't consume it.
        preseed = None if args.dry_run else make_usb_preseed(cfg, unattended_disk)
        iso = build_iso(preseed, out_iso, args.autoboot, unattended_disk, args.dry_run)

    if not args.dry_run and iso.exists():
        check_iso_bootsig(iso)

    # ── no device: the ISO IS the USB image; we're done ──
    if not args.device:
        if args.dry_run:
            info("dry run: would have built the ISO above; no device to flash.")
        else:
            iso_only_summary(iso)
        return

    # ── flash to the device — carefully ──
    # A dry-run against a placeholder (non-existent) device just prints the plan;
    # the safety gating only makes sense against a real block device.
    if args.dry_run and not Path(args.device).is_block_device():
        info(f"(dry-run) would validate {args.device} is a removable non-system disk, "
             "confirm, then:")
        info(f"    + umount <all mountpoints on {args.device}> ; dd if={iso} of={args.device} bs=4M "
             "status=progress oflag=sync conv=fsync ; sync")
        return

    size, model = validate_device(args.device, args.force)
    if args.dry_run:
        info(f"(dry-run) would ERASE {args.device} ({size}, {model}) and write {iso}")
        info(f"    + umount <all mountpoints on {args.device}> ; dd if={iso} of={args.device} bs=4M "
             "status=progress oflag=sync conv=fsync ; sync")
        return

    confirm_device(args.device, iso, size, model, args.yes)
    flash(args.device, iso)
    final_summary(cfg, iso, args.device, args.autoboot, from_iso=args.iso is not None)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        die("interrupted.")
