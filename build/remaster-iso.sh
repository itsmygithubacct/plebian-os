#!/usr/bin/env bash
# remaster-iso.sh — build a Plebian-OS netinst ISO from a stock Debian trixie
# netinst by injecting the preseed + the first-boot provisioner. Phase-1
# "preseeded remaster" approach (same as the plebian sibling project): stock
# installer, stock repos, we only ADD files — so Secure Boot's signed
# shim/GRUB stay untouched.
#
#   build/remaster-iso.sh [debian-13.x-amd64-netinst.iso] [out.iso]
#
# The source netinst is optional: with no argument it is downloaded (and
# checksum-verified) from the Debian mirror automatically and cached. Refuses
# to run without xorriso. The result installs like a regular Debian system and,
# on first boot, pulls pleb + kilix from GitHub and comes up as the Pleb
# session (see preseed.cfg).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$HERE/build/lib.sh"

require_xorriso                          # refuse to run without the ISO packer

SRC_ISO="${1:-}"
OUT_ISO="${2:-plebian-os-netinst-amd64.iso}"
if [ -z "$SRC_ISO" ]; then
    SRC_ISO="$(fetch_netinst)"           # auto-pull the Debian netinst
else
    [ -f "$SRC_ISO" ] || { echo "no such ISO: $SRC_ISO" >&2; exit 1; }
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
EXTRACT="$WORK/iso"
mkdir -p "$EXTRACT"

echo "==> extracting $SRC_ISO"
xorriso -osirrox on -indev "$SRC_ISO" -extract / "$EXTRACT" >/dev/null 2>&1
chmod -R u+w "$EXTRACT"

echo "==> injecting preseed + provisioner"
# The preseed itself, read by the installer.
cp "$HERE/preseed/preseed.cfg" "$EXTRACT/preseed.cfg"
# The files late_command copies into the target, staged under /cdrom/plebian-os.
mkdir -p "$EXTRACT/plebian-os"
cp "$HERE/provision/plebian-os-provision.sh"     "$EXTRACT/plebian-os/"
cp "$HERE/provision/plebian-os-firstboot.service" "$EXTRACT/plebian-os/"

# Point the installer at the preseed and run it unattended. Patch both the
# BIOS (isolinux) and UEFI (grub) boot configs where present.
add_bootarg() { sed -i "s#\(append.*vga=.*\)#\1 auto=true priority=critical file=/cdrom/preseed.cfg#" "$1" 2>/dev/null || true; }
for cfg in "$EXTRACT"/isolinux/*.cfg "$EXTRACT"/isolinux/*/*.cfg; do
    [ -f "$cfg" ] && add_bootarg "$cfg"
done
if [ -f "$EXTRACT/boot/grub/grub.cfg" ]; then
    sed -i 's#\(linux.*vmlinuz.*\)#\1 auto=true priority=critical file=/cdrom/preseed.cfg#' \
        "$EXTRACT/boot/grub/grub.cfg" || true
fi

echo "==> repacking -> $OUT_ISO"
# Reuse the source ISO's own boot layout so BIOS + UEFI both keep working.
xorriso -indev "$SRC_ISO" -report_el_torito as_mkisofs 2>/dev/null > "$WORK/mkisofs.args" || true
if [ -s "$WORK/mkisofs.args" ]; then
    # shellcheck disable=SC2046
    xorriso -as mkisofs $(sed 's#-outdev.*##' "$WORK/mkisofs.args") \
        -o "$OUT_ISO" "$EXTRACT"
else
    echo "!! could not read the source ISO's El Torito layout; falling back to a" >&2
    echo "   basic build (verify BIOS/UEFI boot before trusting it)." >&2
    xorriso -as mkisofs -r -J -joliet-long -V PLEBIAN_OS \
        -o "$OUT_ISO" "$EXTRACT"
fi

echo "==> done: $OUT_ISO"
echo "    install it like normal Debian; first boot pulls pleb + kilix and"
echo "    comes up as the Pleb (fullscreen kilix) session."
