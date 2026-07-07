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
#
#   # just build the ISO (it *is* the USB image — dd it yourself later):
#   build/make-usb.sh                       # no --device
#
#   build/make-usb.sh --list        # show candidate removable devices
#   build/make-usb.sh ... --dry-run # print the plan; write nothing
#
# The Debian netinst is downloaded + checksum-verified automatically when no
# --netinst is given. Refuses to run without xorriso (the ISO packer).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HERE/lib.sh"
NETINST="" ISO="" DEVICE="" ASSUME_YES=0 DRY_RUN=0 FORCE=0

usage() { sed -n '2,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//'; }
log()  { printf '\033[1;36m[make-usb]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[make-usb]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[make-usb] %s\033[0m\n' "$*" >&2; exit 1; }

is_partition_name() {
    local base="$1"
    if [[ "$base" =~ ^(nvme[0-9]+n[0-9]+|mmcblk[0-9]+)$ ]]; then
        return 1
    fi
    if [[ "$base" =~ ^(nvme[0-9]+n[0-9]+p[0-9]+|mmcblk[0-9]+p[0-9]+)$ ]]; then
        return 0
    fi
    [[ "$base" =~ [0-9]$ ]]
}

root_device_names() {
    local src real pk
    src="$(findmnt -no SOURCE / 2>/dev/null || true)"
    [ -n "$src" ] || return 0
    basename "$src"
    real="$(readlink -f "$src" 2>/dev/null || printf '%s' "$src")"
    [ "$real" = "$src" ] || basename "$real"
    pk="$(lsblk -no pkname "$src" 2>/dev/null | head -1 || true)"
    [ -n "$pk" ] && echo "$pk"
    if [ "$real" != "$src" ]; then
        pk="$(lsblk -no pkname "$real" 2>/dev/null | head -1 || true)"
        [ -n "$pk" ] && echo "$pk"
    fi
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
        --iso)     ISO="${2:?}"; shift 2 ;;
        --device)  DEVICE="${2:?}"; shift 2 ;;
        --list)    list_devices; exit 0 ;;
        --yes|-y)  ASSUME_YES=1; shift ;;
        --force)   FORCE=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown option: $1 (see --help)" ;;
    esac
done

# ── 1. get the Plebian-OS ISO (build it, pulling the netinst, unless one exists)
: "${ISO:=plebian-os-netinst-amd64.iso}"
# Build when the user passed a --netinst, or when the target ISO doesn't exist
# yet. A pure flash of an existing --iso (no --netinst) needs no build — and no
# xorriso, no download.
need_build=0
[ -n "$NETINST" ] && need_build=1
[ -f "$ISO" ] || need_build=1

if [ "$need_build" = 1 ]; then
    # refuse to run without xorriso (a dry-run only warns, so it can still preview)
    if [ "$DRY_RUN" = 1 ]; then
        command -v xorriso >/dev/null 2>&1 \
            || warn "(dry-run) xorriso not installed — a real run would refuse here"
    else
        require_xorriso
    fi
    # pull the Debian netinst automatically when none was supplied
    if [ -z "$NETINST" ]; then
        if [ "$DRY_RUN" = 1 ]; then
            log "(dry-run) would download + checksum-verify the Debian netinst ISO"
            NETINST="<auto-downloaded Debian netinst>"
        else
            NETINST="$(fetch_netinst)"
        fi
    elif [ ! -f "$NETINST" ] && [ "$DRY_RUN" != 1 ]; then
        die "no such netinst ISO: $NETINST"
    fi
    if [ -f "$ISO" ] && [ -f "$NETINST" ] && [ "$ISO" -nt "$NETINST" ]; then
        log "using existing $ISO (newer than the netinst; delete it to rebuild)"
    else
        log "building Plebian-OS ISO from $(basename "$NETINST") -> $ISO"
        if [ "$DRY_RUN" = 1 ]; then
            echo "    + $HERE/remaster-iso.sh \"$NETINST\" \"$ISO\""
        else
            "$HERE/remaster-iso.sh" "$NETINST" "$ISO"
        fi
    fi
else
    log "flashing existing $ISO (no build; pass --netinst to rebuild)"
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
    echo "    + umount ${DEVICE}* ; dd if=$ISO of=$DEVICE bs=4M status=progress oflag=sync conv=fsync ; sync"
    exit 0
fi
[ -b "$DEVICE" ] || die "$DEVICE is not a block device"
base="$(basename "$DEVICE")"
# refuse a partition (want the whole disk, e.g. /dev/sdb not /dev/sdb1)
if is_partition_name "$base"; then
    die "$DEVICE looks like a partition; you want the whole disk"
fi

removable="$(cat "/sys/block/$base/removable" 2>/dev/null || echo 0)"
# find the disk backing '/' so we never offer to flash the system drive
while read -r rootdev; do
    [ -n "$rootdev" ] || continue
    [ "$base" = "$rootdev" ] && die "$DEVICE backs the running root filesystem — refusing"
done < <(root_device_names | sort -u)

if [ "$removable" != 1 ] && [ "$FORCE" != 1 ]; then
    die "$DEVICE is not marked removable — refusing (pass --force if you are certain)"
fi

model="$(cat "/sys/block/$base/device/model" 2>/dev/null | tr -s ' ' || echo '?')"
size="$(lsblk -dno SIZE "$DEVICE" 2>/dev/null || echo '?')"
warn "about to ERASE $DEVICE  ($size, $model) and write $ISO"
lsblk "$DEVICE" 2>/dev/null | sed 's/^/    /' || true

if [ "$ASSUME_YES" != 1 ] && [ "$DRY_RUN" != 1 ]; then
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
    echo "    + $SUDO umount ${DEVICE}* (any mounted partitions)"
    echo "    + $SUDO dd if=$ISO of=$DEVICE bs=4M status=progress oflag=sync conv=fsync"
else
    # unmount anything mounted off the device first
    for part in $(lsblk -lno NAME "$DEVICE" 2>/dev/null | tail -n +2); do
        $SUDO umount "/dev/$part" 2>/dev/null || true
    done
    log "writing $ISO -> $DEVICE (this can take a few minutes)"
    $SUDO dd if="$ISO" of="$DEVICE" bs=4M status=progress oflag=sync conv=fsync
    $SUDO sync
    log "done. $DEVICE is a Plebian-OS install stick — boot a machine from it."
fi
