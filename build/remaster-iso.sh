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

# The preseed to bake in. Defaults to the repo's; a builder (e.g.
# build_vm_image.py) can point PLEBIAN_OS_PRESEED at a customized one to set the
# username/password/hostname and first-boot options per image.
PRESEED="${PLEBIAN_OS_PRESEED:-$HERE/preseed/preseed.cfg}"
[ -f "$PRESEED" ] || { echo "no such preseed: $PRESEED" >&2; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
EXTRACT="$WORK/iso"
mkdir -p "$EXTRACT"

echo "==> extracting $SRC_ISO"
xorriso -osirrox on -indev "$SRC_ISO" -extract / "$EXTRACT" >/dev/null 2>&1
chmod -R u+w "$EXTRACT"

echo "==> injecting preseed + provisioner"
echo "    preseed: $PRESEED"
# The preseed itself, read by the installer.
cp "$PRESEED" "$EXTRACT/preseed.cfg"
# The files late_command copies into the target, staged under /cdrom/plebian-os.
mkdir -p "$EXTRACT/plebian-os"
cp "$HERE/provision/plebian-os-provision.sh"     "$EXTRACT/plebian-os/"
cp "$HERE/provision/plebian-os-firstboot.service" "$EXTRACT/plebian-os/"
cp "$HERE/provision/install-deps.sh"             "$EXTRACT/plebian-os/"
cp "$HERE/provision/plebian-os-update.sh"        "$EXTRACT/plebian-os/"

# Point the installer at the preseed and run it unattended. The language,
# country and keyboard questions are asked by localechooser BEFORE the preseed
# file is read, so priority=critical alone won't skip them — pass locale=/keymap=
# on the kernel command line. Both come from the preseed itself (edit them
# there), so the whole thing stays configurable in one place.
LOCALE="$(sed -n 's/^d-i debian-installer\/locale string //p'          "$PRESEED" | head -1)"
KEYMAP="$(sed -n 's/^d-i keyboard-configuration\/xkb-keymap select //p' "$PRESEED" | head -1)"
: "${LOCALE:=en_US.UTF-8}"; : "${KEYMAP:=us}"
BOOTARGS="auto=true priority=critical locale=$LOCALE keymap=$KEYMAP file=/cdrom/preseed.cfg"
echo "    boot args: $BOOTARGS"

# Patch both the BIOS (isolinux) and UEFI (grub) boot configs where present.
# CRUCIAL: insert our args right after the initrd/vmlinuz path — i.e. BEFORE the
# `---` marker. d-i's localechooser (language/country/keyboard) runs before it
# reads the preseed, and only honours locale=/keymap=/priority= that appear
# before `---`; args after `---` are processed too late to skip those prompts.
add_bootarg() { sed -i "/append/ s#\(initrd=[^[:space:]]*\)#\1 $BOOTARGS#" "$1" 2>/dev/null || true; }
for cfg in "$EXTRACT"/isolinux/*.cfg "$EXTRACT"/isolinux/*/*.cfg; do
    [ -f "$cfg" ] && add_bootarg "$cfg"
done
if [ -f "$EXTRACT/boot/grub/grub.cfg" ]; then
    sed -i "/vmlinuz/ s#\(vmlinuz\)#\1 $BOOTARGS#" "$EXTRACT/boot/grub/grub.cfg" || true
fi

# PLEBIAN_OS_AUTOBOOT=1 makes the installer boot menu auto-select the default
# install entry instead of waiting for a keypress — needed for a truly hands-off
# (e.g. VM) build. Left OFF by default so a USB stick still pauses at the menu
# rather than silently auto-wiping a machine it was booted on by accident.
if [ "${PLEBIAN_OS_AUTOBOOT:-0}" = 1 ]; then
    echo "    auto-boot: menu boots the preseeded install after a short timeout"
    # The stock isolinux menu's timeout action (ontimeout) is the SPEECH-SYNTHESIS
    # installer — an accessibility default we don't preseed. Drop every ontimeout,
    # shorten the timeout, and point the timeout at the preseeded text install
    # (its 'append' line already carries our BOOTARGS above).
    for cfg in "$EXTRACT"/isolinux/*.cfg; do
        [ -f "$cfg" ] || continue
        sed -i '/^[[:space:]]*ontimeout[[:space:]]/d' "$cfg"
        sed -i 's/^[[:space:]]*prompt[[:space:]].*/prompt 0/; s/^[[:space:]]*timeout[[:space:]].*/timeout 50/' "$cfg"
    done
    printf 'timeout 50\nontimeout install\n' >> "$EXTRACT/isolinux/isolinux.cfg"
    if [ -f "$EXTRACT/boot/grub/grub.cfg" ]; then
        sed -i 's/^set timeout=.*/set timeout=5/' "$EXTRACT/boot/grub/grub.cfg" || true
    fi
fi

echo "==> repacking -> $OUT_ISO"
# Reuse the source ISO's own boot layout so BIOS + UEFI both keep working.
xorriso -indev "$SRC_ISO" -report_el_torito as_mkisofs 2>/dev/null > "$WORK/mkisofs.args" || true
if [ -s "$WORK/mkisofs.args" ]; then
    # The report emits one option per line and shell-quotes any value with
    # spaces — notably the volume id, e.g.  -V 'Debian 13.5.0 amd64 1'. A bare
    # $(...) expansion word-splits on those spaces and strips the quotes, so
    # "13.5.0" gets passed as a stray source path (xorriso then dies with
    # "Cannot determine attributes of source file .../13.5.0"). Flatten to one
    # line and eval so the shell honours the quoting.
    mkisofs_args="$(sed 's#-outdev.*##' "$WORK/mkisofs.args" | tr '\n' ' ')"
    eval "xorriso -as mkisofs $mkisofs_args -o \"\$OUT_ISO\" \"\$EXTRACT\""
else
    echo "!! could not read the source ISO's El Torito layout; falling back to a" >&2
    echo "   basic build (verify BIOS/UEFI boot before trusting it)." >&2
    xorriso -as mkisofs -r -J -joliet-long -V PLEBIAN_OS \
        -o "$OUT_ISO" "$EXTRACT"
fi

echo "==> done: $OUT_ISO"
echo "    install it like normal Debian; first boot pulls pleb + kilix and"
echo "    comes up as the Pleb (fullscreen kilix) session."
