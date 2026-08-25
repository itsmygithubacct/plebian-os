#!/usr/bin/env python3
"""build_usb_image.py — build a Plebian-OS USB install stick.

By default it builds the normal identity-free installer: Debian Installer asks
the target operator for hostname, full name, username, and password. A separate
``--unattended-profile`` mode accepts an explicit identity and a protected
credential file for lab automation. The resulting ISO is isohybrid, so a USB
installer is just the ISO dd'd to the stick.

    build/build_usb_image.py --device /dev/sdX   # build + flash a stick
    build/build_usb_image.py                      # build the ISO only, no flash
    build/build_usb_image.py --list               # show removable/USB/hotplug candidates
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
    desktop: bool          # PLEBIAN_OS_DESKTOP: run the provider in Kilix page 1
    kiosk: bool            # PLEBIAN_OS_KIOSK: autologin straight into Pleb
    nopasswd_sudo: bool    # PLEBIAN_OS_NOPASSWD_SUDO: passwordless sudo for the user
    password_hash: str = ""
    credential_generated: bool = False

# ── prompting (reuse the VM builder's Prompter) ──────────────────────────────
def gather_config(args) -> Config:
    p = vm.Prompter(args.yes)
    print(vm.c("1", "\nPlebian-OS → USB installer builder\n"))
    if not args.yes:
        print("Answer the prompts (Enter accepts the [default]).\n")

    name = args.name or p.ask("image name", "plebian-automated")
    if args.yes and (not args.username or not args.hostname):
        die("--yes --unattended-profile requires explicit --username and --hostname")
    username = args.username or p.ask("username", "operator")
    fullname = args.fullname or p.ask("full name", username)
    password, password_hash, generated = vm.resolve_automated_credential(args, p)
    if generated:
        die("USB automated profiles refuse generated passwords because no harness "
            "can expire them; use --password-file or --password-hash-file")
    hostname = args.hostname or p.ask("hostname", name)
    desktop_default = vm.env_bool("PLEBIAN_OS_DESKTOP", True)
    kiosk_default = vm.env_bool("PLEBIAN_OS_KIOSK", False)
    nopasswd_default = vm.env_bool("PLEBIAN_OS_NOPASSWD_SUDO", False)
    if args.session:
        desktop = args.session == "desktop"
    else:
        desktop = p.ask_bool(
            "load the configured desktop provider in the first kilix page",
            desktop_default,
        )
    kiosk = args.kiosk if args.kiosk is not None \
                       else p.ask_bool("autologin (kiosk) instead of a login screen",
                                       kiosk_default)
    nopasswd = args.nopasswd_sudo if args.nopasswd_sudo is not None \
                       else p.ask_bool(f"passwordless sudo for {username}",
                                       nopasswd_default)

    vm.validate_identity(name=name, username=username, fullname=fullname,
                         password=password, password_hash=password_hash,
                         hostname=hostname)
    return Config(name=name, username=username, fullname=fullname, password=password,
                  hostname=hostname, desktop=desktop, kiosk=kiosk,
                  nopasswd_sudo=nopasswd, password_hash=password_hash)

def confirm_summary(cfg: Config | None, out_iso: Path, device: str | None,
                    autoboot: bool, unattended_disk: bool,
                    assume_yes: bool) -> None:
    print(vm.c("1", "\nAbout to build:"))
    rows = []
    if cfg is None:
        rows.extend([
            ("identity", "Debian Installer asks hostname, name, username, password"),
            ("profile", "normal interactive installer"),
        ])
    else:
        rows.extend([
            ("image name", cfg.name), ("username", cfg.username),
            ("hostname", cfg.hostname),
            ("session", "desktop provider in Kilix page 1" if cfg.desktop
                        else "Kilix shell in page 1"),
            ("login", "autologin (kiosk)" if cfg.kiosk else "greeter"),
            ("sudo", "passwordless" if cfg.nopasswd_sudo else "password required"),
        ])
    rows.extend([
        ("ISO out", out_iso),
        ("boot menu", "auto-selects install (--autoboot)" if autoboot
                      else "menu pause — pick the install entry"),
        ("disk setup", "unattended erase" if unattended_disk
                       else "installer asks for target disk"),
        ("flash to", device or "(none — build the ISO only)"),
    ])
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
def build_iso(cfg: Config | None, preseed: Path | None, out_iso: Path, autoboot: bool,
              unattended_disk: bool, dry_run: bool,
              ssh_enabled: bool = False) -> Path:
    profile = "custom automated preseed" if preseed is not None else "interactive identity"
    info(f"building installer ISO via {REMASTER.name} ({profile})")
    env = dict(os.environ)
    env.pop("IMAGE_PASSWORD", None)
    env.pop("RANDOM_PASSWORD", None)
    if cfg is not None and preseed is not None:
        env.update(vm.runtime_build_env(cfg))
        env["PLEBIAN_OS_PRESEED"] = str(preseed)
    else:
        for key in ("PLEBIAN_OS_PRESEED", "PLEBIAN_OS_USER",
                    "PLEBIAN_OS_TARGET_SOURCE_HOME",
                    "PLEBIAN_OS_TARGET_GPU_TERMINAL_HOME"):
            env.pop(key, None)
    env["PLEBIAN_OS_SSH_ENABLED"] = "1" if ssh_enabled else "0"
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
        seed = f"PLEBIAN_OS_PRESEED={preseed} " if preseed is not None else ""
        info(f"+ {auto}{disk}{seed}{REMASTER} '' {out_iso}")
        return out_iso
    vm.run([REMASTER, "", str(out_iso)], env=env)
    if not out_iso.exists():
        die(f"ISO build did not produce {out_iso}")
    return out_iso

def make_usb_preseed(cfg: Config, unattended_disk: bool,
                     enable_ssh: bool = False) -> Path:
    preseed = vm.generate_preseed(cfg, enable_ssh=enable_ssh)
    if unattended_disk:
        return preseed
    text = preseed.read_text()
    # Strip ALL partman preseeding (any partman* namespace) so the installer
    # prompts for the target disk, regardless of which partman keys the preseed
    # carries — not just the handful this used to enumerate.
    text = re.sub(r"^d-i\s+partman.*\n", "", text, flags=re.MULTILINE)
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

def _parent_map() -> dict[str, set[str]]:
    """Return every lower block device for each node, including stacked RAID.

    A single PKNAME chain loses parents for mdraid/multipath layouts. Combine all
    lsblk rows with sysfs `slaves` edges so protecting `/` protects every
    physical member disk underneath it.
    """
    parents: dict[str, set[str]] = {}
    for line in _lsblk(["-rno", "NAME,PKNAME"]).splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1]:
            parents.setdefault(parts[0], set()).add(parts[1])
    for node in Path("/sys/class/block").glob("*"):
        try:
            slaves = list((node / "slaves").iterdir())
        except OSError:
            continue
        for slave in slaves:
            parents.setdefault(node.name, set()).add(slave.name)
    return parents

def _ancestors(kname: str,
               parents: dict[str, str | set[str]] | None = None) -> set[str]:
    parents = parents or _parent_map()
    out: set[str] = set()
    todo = [kname]
    while todo:
        cur = todo.pop()
        if cur in out:
            continue
        out.add(cur)
        lower = parents.get(cur, set())
        if isinstance(lower, str):
            lower = {lower}
        todo.extend(lower - out)
    return out


_PROC_SWAPS_ESCAPES = {
    "011": "\t",
    "012": "\n",
    "040": " ",
    "134": "\\",
}


def _decode_proc_swaps_path(encoded: str) -> str:
    """Decode the characters escaped by Linux when it renders /proc/swaps.

    Linux's seq-file output octal-escapes tab, newline, space, and backslash.
    Decode them in one regex pass: sequential replacements can turn a literal
    ``\\040`` filename fragment (rendered as ``\\134040``) into a space.
    """
    return re.sub(
        r"\\(011|012|040|134)",
        lambda match: _PROC_SWAPS_ESCAPES[match.group(1)],
        encoded,
    )


def _root_disks() -> set[str]:
    """Block-device kernel names we must never flash.

    This protects the full ancestry of critical mounted filesystems, so LUKS,
    LVM, dm-crypt, mdraid, and /dev/disk/by-* symlinks resolve back to the
    physical disk before comparison.
    """
    parents = _parent_map()
    names: set[str] = set()
    sources: list[str] = []
    for target in ("/", "/boot", "/boot/efi", "/home", "/var", "/usr", "/srv"):
        src = subprocess.run(["findmnt", "-no", "SOURCE", "--target", target],
                             capture_output=True, text=True).stdout.strip()
        # btrfs reports SOURCE as /dev/xxx[/subvol]; drop the subvolume suffix so
        # the root disk still resolves to a real block device (else it silently
        # falls out of the protected set on btrfs/subvolume layouts).
        src = src.split("[", 1)[0]
        if src.startswith("/dev/"):
            sources.append(src)
    # Swap comes from /proc/swaps, not swapon(8): that binary sits in /usr/sbin,
    # which regular users don't have on PATH on Debian, and swap disks must stay
    # in the protected set (neither a crash nor a silent skip is safe here).
    try:
        swap_lines = Path("/proc/swaps").read_text(
            errors="surrogateescape",
        ).splitlines()[1:]
    except OSError:
        swap_lines = []
    for line in swap_lines:
        fields = line.split()
        if not fields:
            continue
        swap_source = _decode_proc_swaps_path(fields[0])
        if swap_source.startswith("/dev/"):
            sources.append(swap_source)
        elif swap_source:
            backing = subprocess.run(
                ["findmnt", "-no", "SOURCE", "--target", swap_source],
                capture_output=True, text=True,
            ).stdout.strip().split("[", 1)[0]
            if backing.startswith("/dev/"):
                sources.append(backing)
    for src in sources:
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


def _device_is_flash_candidate(removable: str, transport: str, hotplug: str) -> bool:
    """Whether kernel metadata identifies an inserted/removable target.

    USB controllers commonly expose real sticks as fixed media (RM=0), so RM,
    transport, and hotplug are independent evidence for the admission check.
    """
    return (removable.strip() == "1" or transport.strip().lower() == "usb"
            or hotplug.strip() == "1")


def _device_characteristics(base: str, device: str) -> tuple[str, str, str, str, str]:
    try:
        removable = Path(f"/sys/block/{base}/removable").read_text().strip()
    except OSError:
        removable = "0"
    transport = _lsblk(["-dnro", "TRAN", device]) or "?"
    hotplug = _lsblk(["-dnro", "HOTPLUG", device]) or "?"
    size = _lsblk(["-dno", "SIZE", device]) or "?"
    try:
        model = " ".join(Path(f"/sys/block/{base}/device/model").read_text().split()) or "?"
    except OSError:
        model = "?"
    return removable, transport, hotplug, size, model


def list_devices() -> None:
    info("removable, USB, or hotplug block devices:")
    any_found = False
    for d in sorted(Path("/sys/block").glob("*")):
        name = d.name
        if name.startswith(("loop", "ram", "sr", "dm-", "md", "zram")):
            continue
        removable, transport, hotplug, size, model = _device_characteristics(
            name, f"/dev/{name}")
        if not _device_is_flash_candidate(removable, transport, hotplug):
            continue
        print(f"    /dev/{name:<8} {size:>8}  RM={removable} TRAN={transport} "
              f"HOTPLUG={hotplug}  {model}")
        any_found = True
    if not any_found:
        print("    (none found — plug in a USB stick, or pass --force for a fixed disk)")

def _device_identity(device: str) -> tuple[int, int] | None:
    try:
        st = os.stat(device)
    except OSError:
        return None
    if not stat.S_ISBLK(st.st_mode):
        return None
    return os.major(st.st_rdev), os.minor(st.st_rdev)


def validate_device(device: str, force: bool) -> tuple[str, str, bool, tuple[int, int]]:
    """Refuse anything unsafe; return display data and stable device identity."""
    if not Path(device).is_block_device():
        die(f"{device} is not a block device")
    base = _block_kname(device) or Path(os.path.realpath(device)).name
    dev_type = _lsblk(["-dnro", "TYPE", device])
    if dev_type != "disk":
        die(f"{device} looks like a partition; you want the whole disk")
    if _lsblk(["-dnro", "RO", device]) == "1":
        die(f"{device} is read-only; refusing a partial/failed flash")
    # never the disk backing '/' (this refusal is NOT bypassed by --force)
    if base and base in _root_disks():
        die(f"{device} backs the running root filesystem — refusing")
    # Require removable/USB/hotplug evidence unless --force. This is the only
    # refusal --force bypasses; protected live disks above remain forbidden.
    removable, transport, hotplug, size, model = _device_characteristics(base, device)
    flash_candidate = _device_is_flash_candidate(removable, transport, hotplug)
    if not flash_candidate and not force:
        die(f"{device} is not marked removable (RM={removable}, TRAN={transport}, "
            f"HOTPLUG={hotplug}, MODEL={model}, SIZE={size}) — pass --force if "
            "this is the device you intend to erase")
    identity = _device_identity(device)
    if identity is None:
        die(f"could not capture a stable device identity for {device}")
    return size, model, flash_candidate, identity


def validate_image_fits(device: str, iso: Path, base: str | None = None) -> None:
    base = base or _block_kname(device)
    try:
        sectors = int(Path(f"/sys/class/block/{base}/size").read_text().strip())
        capacity = sectors * 512
        image_size = iso.stat().st_size
    except (OSError, TypeError, ValueError) as e:
        die(f"could not compare ISO and target sizes safely: {e}")
    if image_size > capacity:
        die(f"ISO is {image_size} bytes but {device} holds only {capacity} bytes")

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

def flash(device: str, iso: Path, expected_identity: tuple[int, int]) -> None:
    # A block device needs root; use sudo per-command so the typed confirmation
    # stays in the user's own shell (no re-exec).
    sudo: list[str] = []
    if os.geteuid() != 0:
        if not vm.have("sudo"):
            die(f"need root to write {device} (run with sudo)")
        sudo = ["sudo"]
    # The operator may spend time reading/confirming. Re-resolve immediately
    # before unmount/dd so an unplugged/reused /dev path cannot change targets.
    if _device_identity(device) != expected_identity:
        die(f"{device} changed after validation; refusing to write")
    base = _block_kname(device)
    if not base or base in _root_disks():
        die(f"{device} now backs a protected live filesystem/swap; refusing")
    validate_image_fits(device, iso, base)
    for mp in _mounted_targets(device):
        r = subprocess.run([*sudo, "umount", mp], capture_output=True, text=True)
        if r.returncode != 0:
            detail = (r.stderr or r.stdout or "").strip()
            die(f"failed to unmount {mp!r}; refusing to overwrite a mounted filesystem"
                + (f": {detail}" if detail else ""))
    info(f"writing {iso} -> {device} (this can take a few minutes)")
    # Recheck after unmounting, immediately before the destructive write. A
    # device path can be unplugged/reused or newly mounted during that gap.
    if _device_identity(device) != expected_identity:
        die(f"{device} changed during unmount; refusing to write")
    base = _block_kname(device)
    if not base or base in _root_disks():
        die(f"{device} now backs a protected live filesystem/swap; refusing")
    if _lsblk(["-dnro", "RO", device]) != "0":
        die(f"could not verify {device} is writable immediately before writing")
    validate_image_fits(device, iso, base)
    if _mounted_targets(device):
        die(f"{device} was mounted again before writing; refusing")
    vm.run([*sudo, "dd", f"if={iso}", f"of={device}", "bs=4M",
            "status=progress", "oflag=sync", "conv=fsync"])
    vm.run([*sudo, "sync"])

# ── summaries ────────────────────────────────────────────────────────────────
def iso_only_summary(iso: Path) -> None:
    info(f"ISO ready: {iso}")
    info("it is a USB-bootable (isohybrid) image. Write it with either:")
    info(f"    build/build_usb_image.py --iso {iso} --device /dev/sdX")
    info(f"    sudo dd if={iso} of=/dev/sdX bs=4M status=progress oflag=sync conv=fsync")

def final_summary(cfg: Config | None, iso: Path, device: str, autoboot: bool,
                  from_iso: bool) -> None:
    print(vm.c("1;32", "\n✓ Plebian-OS install stick is ready.\n"))
    print(f"  device    : {device}")
    if from_iso:
        # A prebuilt ISO carries its own preseed; the flags didn't set these, so
        # don't claim a username/session the image may not actually use.
        print("  login     : whatever the prebuilt ISO's preseed defines")
    elif cfg is None:
        print("  identity  : Debian Installer asks hostname, name, username, and password")
    else:
        kind = "protected crypt hash" if cfg.password_hash else "protected password file"
        print(f"  login     : {cfg.username} / ({kind})")
        print(f"  session   : {'desktop provider in Kilix page 1' if cfg.desktop else 'Kilix shell in page 1'}"
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
    ap.add_argument("--hostname")
    ap.add_argument("--unattended-profile", action="store_true",
                    help="use an explicit automated identity instead of installer questions")
    ap.add_argument("--password", help=argparse.SUPPRESS)
    ap.add_argument("--password-file", type=Path,
                    help="read the automated password from an owner-mode-0600 file")
    ap.add_argument("--password-hash-file", type=Path,
                    help="read a crypt hash from an owner-mode-0600 file")
    ap.add_argument("--generate-one-time-password", action="store_true",
                    help=argparse.SUPPRESS)
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
    ap.add_argument(
        "--out", type=Path, default=None,
        help=("ISO output path when building (release default: "
              "plebian-os-<version>-amd64.iso; otherwise "
              "plebian-os-<name>.iso)"))
    ap.add_argument("--autoboot", action="store_true",
                    help="build a hands-off stick that auto-selects the install "
                         "(it then ERASES the booted machine's disk with no prompt)")
    ap.add_argument("--unattended-disk", action="store_true",
                    help="preseed partitioning too, so choosing install erases the "
                         "target disk without another installer prompt")
    ap.add_argument("--with-ssh", action="store_true",
                    help="install ssh-server (off by default; protect the chosen password)")
    ap.add_argument("--list", action="store_true",
                    help="list removable/USB/hotplug candidates and exit")
    ap.add_argument("--force", action="store_true",
                    help="allow a disk without removable/USB/hotplug evidence "
                         "(never the system/root disk)")
    ap.add_argument("-y", "--yes", action="store_true", help="accept defaults, no prompts")
    ap.add_argument("--dry-run", action="store_true", help="show the plan; write nothing")
    args = ap.parse_args()

    if args.list:
        list_devices()
        return

    building = args.iso is None
    # preflight
    if building and not args.dry_run:
        for tool in ("xorriso", "openssl"):
            if not vm.have(tool):
                die(f"{tool} is required to build the ISO but is not installed.")
    if not PRESEED_TEMPLATE.exists() or not REMASTER.exists():
        die("run this from a Plebian-OS checkout (preseed/ + build/ not found).")

    # PLEBIAN_OS_RELEASE=<ver> pins every moving component from releases/<ver>.env.
    vm.apply_release_manifest()

    image_name = args.name or "plebian"
    if args.iso:
        cfg = None
        warn("using a prebuilt ISO: identity/profile flags are not applied")
    elif args.unattended_profile:
        cfg = gather_config(args)
        image_name = cfg.name
    else:
        custom_flags = (
            args.username, args.fullname, args.hostname, args.password,
            args.password_file, args.password_hash_file, args.session,
            args.kiosk, args.nopasswd_sudo,
        )
        if any(value is not None for value in custom_flags) or \
                args.generate_one_time_password or args.with_ssh or \
                args.autoboot or args.unattended_disk:
            die("identity, credential, SSH, and unattended options require "
                "--unattended-profile")
        for key in ("IMAGE_PASSWORD", "RANDOM_PASSWORD", "PLEBIAN_OS_USER"):
            if key in os.environ:
                die(f"normal interactive media refuses ambient {key}")
        cfg = None

    out_iso = (args.iso or args.out or (vm.storage_dir("artifacts") /
                                        vm.default_iso_filename(image_name))).resolve()
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
        preseed = None
        if cfg is not None and not args.dry_run:
            preseed = make_usb_preseed(
                cfg, unattended_disk, enable_ssh=args.with_ssh)
        iso = build_iso(cfg, preseed, out_iso, args.autoboot,
                        unattended_disk, args.dry_run, ssh_enabled=args.with_ssh)

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
        info(f"(dry-run) would validate {args.device} has removable/USB/hotplug "
             "evidence and is not a system disk, confirm, then:")
        info(f"    + umount <all mountpoints on {args.device}> ; dd if={iso} of={args.device} bs=4M "
             "status=progress oflag=sync conv=fsync ; sync")
        return

    size, model, flash_candidate, identity = validate_device(args.device, args.force)
    if not args.dry_run:
        validate_image_fits(args.device, iso)
    if args.dry_run:
        info(f"(dry-run) would ERASE {args.device} ({size}, {model}) and write {iso}")
        info(f"    + umount <all mountpoints on {args.device}> ; dd if={iso} of={args.device} bs=4M "
             "status=progress oflag=sync conv=fsync ; sync")
        return

    # A target admitted only by --force always requires typed confirmation,
    # even with --yes. Kernel-identified removable/USB/hotplug targets may skip it.
    if args.yes and not flash_candidate:
        warn(f"{args.device} lacks removable/USB/hotplug evidence (--force); "
             "requiring typed confirmation despite --yes")
    confirm_device(args.device, iso, size, model, args.yes and flash_candidate)
    flash(args.device, iso, identity)
    final_summary(cfg, iso, args.device, args.autoboot, from_iso=args.iso is not None)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        die("interrupted.")
