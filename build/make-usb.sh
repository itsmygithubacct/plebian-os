#!/usr/bin/env bash
# make-usb.sh — build a bootable Plebian-OS USB install stick.
#
# The Plebian-OS ISO (build/remaster-iso.sh) is an isohybrid image, so a USB
# installer is just that ISO written byte-for-byte to a USB device. This script
# ties the two steps together and — most importantly — writes to the device
# *safely*: it refuses system/non-removable disks, shows you what it's about to
# erase, and makes you confirm.
#
#   # build a USB stick end-to-end (downloads the Debian netinst for you):
#   build/make-usb.sh --device /dev/sdX
#
#   # use a local netinst instead of downloading it:
#   build/make-usb.sh --netinst debian-13.x-amd64-netinst.iso --device /dev/sdX
#
#   # flash an already-built Plebian-OS ISO (no build, no xorriso needed):
#   build/make-usb.sh --iso plebian-os-netinst-amd64.iso --device /dev/sdX
#   # explicitly trust/reuse the default output path (never inferred by mtime):
#   build/make-usb.sh --reuse-iso --device /dev/sdX
#
#   # just build the ISO (it *is* the USB image — dd it yourself later):
#   build/make-usb.sh                       # no --device
#
#   build/make-usb.sh --list        # show candidate removable devices
#   build/make-usb.sh ... --dry-run # print the plan; write nothing
#   build/make-usb.sh ... --unattended-disk # installer erases after boot-menu selection
#
# The Debian netinst is downloaded + signature/hash-verified automatically when
# no --netinst is given. Refuses to run without xorriso (the ISO packer).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HERE/lib.sh"
NETINST="" ISO="" DEVICE="" ASSUME_YES=0 DRY_RUN=0 FORCE=0 UNATTENDED_DISK=0 ISO_EXPLICIT=0 REUSE_ISO=0

usage() { sed -n '2,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//'; }
log()  { printf '\033[1;36m[make-usb]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[make-usb]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[make-usb] %s\033[0m\n' "$*" >&2; exit 1; }

block_kname() {
    local majmin sys
    [ -b "$1" ] || return 1
    majmin="$(lsblk -dnro MAJ:MIN "$1" 2>/dev/null | head -1 || true)"
    [ -n "$majmin" ] || return 1
    sys="$(readlink -f "/sys/dev/block/$majmin" 2>/dev/null || true)"
    [ -n "$sys" ] || return 1
    basename "$sys"
}

ancestor_names() {
    local cur="$1" seen="${2:-}" pk slave
    [ -n "$cur" ] || return 0
    case " $seen " in *" $cur "*) return 0 ;; esac
    echo "$cur"
    seen="$seen $cur"
    while IFS= read -r pk; do
        [ -n "$pk" ] && ancestor_names "$pk" "$seen"
    done < <(
        lsblk -rno PKNAME "/dev/$cur" 2>/dev/null || true
        for slave in "/sys/class/block/$cur/slaves/"*; do
            [ -e "$slave" ] && basename "$slave"
        done
    )
}

protected_device_names() {
    local target src kname
    for target in / /boot /boot/efi /home /var /usr /srv; do
        src="$(findmnt -no SOURCE --target "$target" 2>/dev/null || true)"
        # btrfs reports SOURCE as /dev/xxx[/subvol]; strip the subvolume suffix so
        # the disk still resolves to a real block device. Without this, the root
        # disk silently drops out of the protected set on btrfs/subvolume layouts
        # and the root-disk refusal never fires.
        src="${src%%[*}"
        case "$src" in /dev/*) ;; *) continue ;; esac
        kname="$(block_kname "$src" 2>/dev/null || true)"
        [ -n "$kname" ] && ancestor_names "$kname"
    done
    if command -v swapon >/dev/null 2>&1; then
        while IFS= read -r src; do
            case "$src" in
                /dev/*) ;;
                *) src="$(findmnt -no SOURCE --target "$src" 2>/dev/null || true)"; src="${src%%[*}" ;;
            esac
            case "$src" in /dev/*) ;; *) continue ;; esac
            kname="$(block_kname "$src" 2>/dev/null || true)"
            [ -n "$kname" ] && ancestor_names "$kname"
        done < <(swapon --noheadings --raw --show=NAME 2>/dev/null || true)
    fi
}

mounted_targets_for_device() {
    local name mp
    while read -r name; do
        [ -n "$name" ] || continue
        while IFS= read -r mp; do
            [ -n "$mp" ] && printf '%s\n' "$mp"
        done < <(findmnt -rn -S "/dev/$name" -o TARGET 2>/dev/null || true)
    done < <(lsblk -rno NAME "$1" 2>/dev/null || true)
}

# ── list removable block devices (candidates for a USB stick) ────────────────
list_devices() {
    log "removable block devices:"
    local any=0 d name rm size model
    for d in /sys/block/*; do
        name="$(basename "$d")"
        case "$name" in loop*|ram*|sr*|dm-*|md*|zram*) continue ;; esac
        rm="$(cat "$d/removable" 2>/dev/null || echo 0)"
        [ "$rm" = 1 ] || continue
        size="$(lsblk -dno SIZE "/dev/$name" 2>/dev/null || echo '?')"
        model="$(cat "$d/device/model" 2>/dev/null | tr -s ' ' || echo '?')"
        printf '    /dev/%-8s %8s  %s\n' "$name" "$size" "$model"
        any=1
    done
    [ "$any" = 1 ] || echo "    (none found — plug in a USB stick, or pass --force for a fixed disk)"
}

# ── args ─────────────────────────────────────────────────────────────────────
while [ $# -gt 0 ]; do
    case "$1" in
        --netinst) NETINST="${2:?}"; shift 2 ;;
        --iso)     ISO="${2:?}"; ISO_EXPLICIT=1; shift 2 ;;
        --reuse-iso) REUSE_ISO=1; shift ;;
        --device)  DEVICE="${2:?}"; shift 2 ;;
        --list)    list_devices; exit 0 ;;
        --yes|-y)  ASSUME_YES=1; shift ;;
        --force)   FORCE=1; shift ;;
        --unattended-disk) UNATTENDED_DISK=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown option: $1 (see --help)" ;;
    esac
done

# ── 1. get the Plebian-OS ISO (build it, pulling the netinst, unless one exists)
: "${ISO:=plebian-os-netinst-amd64.iso}"
# Default to a fresh build. Reuse is only allowed through the explicit --iso or
# --reuse-iso gates; mtimes cannot represent all baked environment/release inputs.
need_build=1
if [ "$ISO_EXPLICIT" = 1 ]; then
    [ -z "$NETINST" ] || die "--iso and --netinst are mutually exclusive"
    [ -f "$ISO" ] || die "--iso not found: $ISO"
    need_build=0
elif [ "$REUSE_ISO" = 1 ]; then
    [ -z "$NETINST" ] || die "--reuse-iso and --netinst are mutually exclusive"
    [ -f "$ISO" ] || die "--reuse-iso requested but ISO not found: $ISO"
    warn "explicitly reusing $ISO without checking its baked inputs"
    need_build=0
fi

if [ "$need_build" = 1 ]; then
    # refuse to run without xorriso (a dry-run only warns, so it can still preview)
    if [ "$DRY_RUN" = 1 ]; then
        command -v xorriso >/dev/null 2>&1 \
            || warn "(dry-run) xorriso not installed — a real run would refuse here"
    else
        require_xorriso
    fi
    # Let remaster-iso.sh fetch the netinst when none was supplied. It loads a
    # release manifest first, so archival URL/checksum pins apply to the fetch.
    if [ -z "$NETINST" ]; then
        if [ "$DRY_RUN" = 1 ]; then
            log "(dry-run) would download + signature/hash-verify the Debian netinst ISO"
        fi
    elif [ ! -f "$NETINST" ] && [ "$DRY_RUN" != 1 ]; then
        die "no such netinst ISO: $NETINST"
    fi
    source_desc="${NETINST:-auto-downloaded Debian netinst}"
    log "building Plebian-OS ISO from $(basename "$source_desc") -> $ISO"
    if [ "$DRY_RUN" = 1 ]; then
        prefix=""
        [ "$UNATTENDED_DISK" = 1 ] && prefix="PLEBIAN_OS_UNATTENDED_DISK=1 "
        echo "    + ${prefix}$HERE/remaster-iso.sh \"$NETINST\" \"$ISO\""
    else
        if [ "$UNATTENDED_DISK" = 1 ]; then
            PLEBIAN_OS_UNATTENDED_DISK=1 "$HERE/remaster-iso.sh" "$NETINST" "$ISO"
        else
            "$HERE/remaster-iso.sh" "$NETINST" "$ISO"
        fi
    fi
else
    log "flashing existing $ISO (explicit reuse; omit --iso/--reuse-iso to rebuild)"
fi
[ "$DRY_RUN" = 1 ] || [ -f "$ISO" ] || die "ISO not found: $ISO"

# Debian's installer ISOs are isohybrid (USB-bootable as-is); our remaster
# preserves that layout. Sanity-check the MBR boot signature when we can.
if [ "$DRY_RUN" != 1 ] && [ -f "$ISO" ]; then
    sig="$(dd if="$ISO" bs=1 skip=510 count=2 2>/dev/null | od -An -tx1 | tr -d ' ')"
    [ "$sig" = "55aa" ] || warn "ISO has no MBR boot signature — it may not boot from USB (isohybrid?)"
fi

# ── 2. no device? we're done: the ISO IS the USB image ───────────────────────
if [ -z "$DEVICE" ]; then
    log "ISO ready: $ISO"
    log "it is a USB-bootable (isohybrid) image. Write it with either:"
    log "    build/make-usb.sh --iso $ISO --device /dev/sdX"
    log "    sudo dd if=$ISO of=/dev/sdX bs=4M status=progress oflag=sync"
    exit 0
fi

# ── 3. write to the USB device — carefully ───────────────────────────────────
# In a dry-run against a placeholder (non-existent) device, just print the plan;
# the safety gating below only makes sense against a real block device.
if [ "$DRY_RUN" = 1 ] && [ ! -b "$DEVICE" ]; then
    log "(dry-run) would validate $DEVICE is a removable non-system disk, confirm, then:"
    echo "    + umount <all mountpoints on $DEVICE> ; dd if=$ISO of=$DEVICE bs=4M status=progress oflag=sync conv=fsync ; sync"
    exit 0
fi
[ -b "$DEVICE" ] || die "$DEVICE is not a block device"
base="$(block_kname "$DEVICE" || true)"
[ -n "$base" ] || die "could not resolve kernel block-device name for $DEVICE"
dev_type="$(lsblk -dnro TYPE "$DEVICE" 2>/dev/null | head -1 || true)"
if [ "$dev_type" != disk ]; then
    die "$DEVICE looks like a partition; you want the whole disk"
fi
readonly="$(lsblk -dnro RO "$DEVICE" 2>/dev/null | head -1 || true)"
[ "$readonly" != 1 ] || die "$DEVICE is read-only; refusing a partial/failed flash"
device_identity="$(lsblk -dnro MAJ:MIN "$DEVICE" 2>/dev/null | head -1 || true)"
[ -n "$device_identity" ] || die "could not capture a stable identity for $DEVICE"

removable="$(cat "/sys/block/$base/removable" 2>/dev/null || echo 0)"
# find the disk backing '/' so we never offer to flash the system drive
while read -r rootdev; do
    [ -n "$rootdev" ] || continue
    [ "$base" = "$rootdev" ] && die "$DEVICE backs the running root filesystem — refusing"
done < <(protected_device_names | sort -u)

if [ "$removable" != 1 ] && [ "$FORCE" != 1 ]; then
    die "$DEVICE is not marked removable — refusing (pass --force if you are certain)"
fi

model="$(cat "/sys/block/$base/device/model" 2>/dev/null | tr -s ' ' || echo '?')"
size="$(lsblk -dno SIZE "$DEVICE" 2>/dev/null || echo '?')"
iso_bytes="$(stat -c '%s' "$ISO" 2>/dev/null || true)"
device_sectors="$(cat "/sys/class/block/$base/size" 2>/dev/null || true)"
case "$device_sectors" in ''|*[!0-9]*) device_bytes="" ;; *) device_bytes=$((device_sectors * 512)) ;; esac
[ -n "$iso_bytes" ] && [ -n "$device_bytes" ] \
    || die "could not compare ISO and target sizes safely"
[ "$iso_bytes" -le "$device_bytes" ] \
    || die "ISO is $iso_bytes bytes but $DEVICE holds only $device_bytes bytes"
warn "about to ERASE $DEVICE  ($size, $model) and write $ISO"
lsblk "$DEVICE" 2>/dev/null | sed 's/^/    /' || true

# A forced (non-removable) target is a fixed disk — never let --yes skip the
# typed confirmation for one. Only a genuinely removable stick may be flashed
# unattended; forcing a fixed disk always requires you to retype its path.
if [ "$DRY_RUN" != 1 ] && { [ "$ASSUME_YES" != 1 ] || [ "$removable" != 1 ]; }; then
    if [ "$ASSUME_YES" = 1 ] && [ "$removable" != 1 ]; then
        warn "$DEVICE is a non-removable disk (--force); requiring typed confirmation despite --yes"
    fi
    printf '\033[1;31mType the device path to confirm (%s): \033[0m' "$DEVICE"
    read -r confirm
    [ "$confirm" = "$DEVICE" ] || die "confirmation did not match — aborted"
fi

# writing a block device needs root; use sudo per-command so the confirmation
# above stays in the user's own shell (no re-exec gymnastics).
SUDO=""
if [ "$(id -u)" != 0 ]; then
    command -v sudo >/dev/null || die "need root to write $DEVICE (run with sudo)"
    SUDO=sudo
fi
if [ "$DRY_RUN" = 1 ]; then
    echo "    + $SUDO umount <all mountpoints on $DEVICE and its partitions>"
    echo "    + $SUDO dd if=$ISO of=$DEVICE bs=4M status=progress oflag=sync conv=fsync"
else
    current_identity="$(lsblk -dnro MAJ:MIN "$DEVICE" 2>/dev/null | head -1 || true)"
    [ "$current_identity" = "$device_identity" ] \
        || die "$DEVICE changed after validation; refusing to write"
    current_base="$(block_kname "$DEVICE" || true)"
    [ -n "$current_base" ] || die "could not re-resolve $DEVICE before writing"
    while read -r protected; do
        [ "$current_base" != "$protected" ] \
            || die "$DEVICE now backs a protected live filesystem/swap; refusing"
    done < <(protected_device_names | sort -u)
    mapfile -t mountpoints < <(mounted_targets_for_device "$DEVICE" | sort -u | sort -r)
    for mp in "${mountpoints[@]}"; do
        $SUDO umount "$mp" || die "failed to unmount $mp; refusing to overwrite a mounted filesystem"
    done
    log "writing $ISO -> $DEVICE (this can take a few minutes)"
    # Final destructive-write gate: repeat every mutable property after
    # unmounting, with no intervening operation before dd.
    current_identity="$(lsblk -dnro MAJ:MIN "$DEVICE" 2>/dev/null | head -1 || true)"
    [ "$current_identity" = "$device_identity" ] \
        || die "$DEVICE changed during unmount; refusing to write"
    current_base="$(block_kname "$DEVICE" || true)"
    [ -n "$current_base" ] || die "could not re-resolve $DEVICE immediately before writing"
    while read -r protected; do
        [ "$current_base" != "$protected" ] \
            || die "$DEVICE now backs a protected live filesystem/swap; refusing"
    done < <(protected_device_names | sort -u)
    readonly="$(lsblk -dnro RO "$DEVICE" 2>/dev/null | head -1 || true)"
    [ "$readonly" = 0 ] || die "could not verify $DEVICE is writable immediately before writing"
    device_sectors="$(cat "/sys/class/block/$current_base/size" 2>/dev/null || true)"
    case "$device_sectors" in ''|*[!0-9]*) device_bytes="" ;; *) device_bytes=$((device_sectors * 512)) ;; esac
    [ -n "$device_bytes" ] && [ "$iso_bytes" -le "$device_bytes" ] \
        || die "target capacity changed or cannot be verified immediately before writing"
    [ -z "$(mounted_targets_for_device "$DEVICE")" ] \
        || die "$DEVICE was mounted again before writing; refusing"
    $SUDO dd if="$ISO" of="$DEVICE" bs=4M status=progress oflag=sync conv=fsync
    $SUDO sync
    log "done. $DEVICE is a Plebian-OS install stick — boot a machine from it."
fi
