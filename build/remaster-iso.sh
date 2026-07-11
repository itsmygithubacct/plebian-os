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
# signature/hash-verified) from the Debian mirror automatically and cached.
# Refuses to run without xorriso. The result installs like a regular Debian
# system and, on first boot, pulls pleb + kilix from GitHub and comes up as the
# Pleb session (see preseed.cfg).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$HERE/build/lib.sh"

require_xorriso                          # refuse to run without the ISO packer

# ── release manifest + version ───────────────────────────────────────────────
# PLEBIAN_OS_RELEASE=<x.y.z> loads releases/<x.y.z>.env — the coordinated pin
# manifest — applying each pin ONLY when not already set in the environment (so
# an explicit CLI override still wins). Loaded BEFORE the version fallback below
# so the manifest can also pin PLEBIAN_OS_VERSION. A still-placeholder aborts.
load_release_manifest() {
    local rel="$1"
    local manifest="$HERE/releases/$rel.env"
    [ -f "$manifest" ] || { echo "no release manifest: releases/$rel.env" >&2; exit 1; }
    echo "==> release $rel: applying pins from releases/$rel.env"
    local line key val
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in ''|\#*) continue ;; esac
        case "$line" in *=*) ;; *) continue ;; esac
        key="${line%%=*}"; val="${line#*=}"
        val="${val%\"}"; val="${val#\"}"          # tolerate optional quotes
        # Only apply well-formed KEY=VALUE lines (KEY a shell identifier); skip
        # anything else — an indented comment, stray spaces — rather than abort
        # the build with a raw "invalid variable name" from ${!key}/export.
        case "$key" in ''|[0-9]*|*[!A-Za-z0-9_]*) continue ;; esac
        if [ -z "${!key:-}" ]; then               # env override wins
            if [ "$val" = "REPLACE_ME" ]; then
                echo "release $rel: $key is still REPLACE_ME in releases/$rel.env — fill it before building (see RELEASING.md)" >&2
                exit 1
            fi
            export "$key=$val"
        fi
    done < "$manifest"
}
[ -n "${PLEBIAN_OS_RELEASE:-}" ] && load_release_manifest "$PLEBIAN_OS_RELEASE"

# The version baked into the image (recorded in build-info + firstboot env).
# Precedence: explicit env > release manifest (above) > repo VERSION file.
PLEBIAN_OS_VERSION="${PLEBIAN_OS_VERSION:-$(cat "$HERE/VERSION" 2>/dev/null || echo 0.0.0-dev)}"

SRC_ISO="${1:-}"
OUT_ISO="${2:-plebian-os-netinst-amd64.iso}"
if [ -z "$SRC_ISO" ]; then
    SRC_ISO="$(fetch_netinst)"           # auto-pull the Debian netinst
else
    [ -f "$SRC_ISO" ] || { echo "no such ISO: $SRC_ISO" >&2; exit 1; }
fi

verify_source_iso_pin() {
    local actual
    if [ -n "${PLEBIAN_OS_NETINST_SHA256:-}" ]; then
        actual="$(sha256sum "$SRC_ISO" | awk '{print $1}')"
        [ "$actual" = "$PLEBIAN_OS_NETINST_SHA256" ] || {
            echo "source ISO checksum mismatch:" >&2
            echo "  expected: $PLEBIAN_OS_NETINST_SHA256" >&2
            echo "  actual  : $actual" >&2
            exit 1
        }
    elif [ "${PLEBIAN_OS_RELEASE_MODE:-0}" = 1 ]; then
        echo "PLEBIAN_OS_RELEASE_MODE=1 requires PLEBIAN_OS_NETINST_SHA256 for the source ISO" >&2
        exit 1
    fi
}
verify_source_iso_pin

# The preseed to bake in. Defaults to the repo's; a builder (e.g.
# build_vm_image.py) can point PLEBIAN_OS_PRESEED at a customized one to set the
# username/password/hostname and first-boot options per image.
PRESEED="${PLEBIAN_OS_PRESEED:-$HERE/preseed/preseed.cfg}"
[ -f "$PRESEED" ] || { echo "no such preseed: $PRESEED" >&2; exit 1; }
# The default password 'plebian' is a supported, deliberate default (the Kilix
# 95 desktop prompts to change it on first run). Just note it — do NOT refuse,
# even in release mode. If ssh-server is ALSO enabled the box would be
# network-reachable with a weak password, so that combination warns louder.
if grep -q '^d-i passwd/user-password password plebian$' "$PRESEED"; then
    if grep -q '^tasksel tasksel/first multiselect .*ssh-server' "$PRESEED"; then
        echo "WARNING: image uses the default password 'plebian' AND enables" >&2
        echo "  ssh-server — it is network-reachable with a weak credential." >&2
        echo "  Set a real password (builders' --password) for anything exposed." >&2
    else
        echo "note: image uses the default password 'plebian' (user 'pleb'); no" >&2
        echo "  ssh-server, and the Kilix 95 desktop prompts to change it on first" >&2
        echo "  run. Pass a real --password to the builders to override." >&2
    fi
fi

manifest_kv() {
    printf '%s=%q\n' "$1" "$2"
}

env_kv() {
    local value="${2//\\/\\\\}"
    value="${value//\"/\\\"}"
    printf '%s="%s"\n' "$1" "$value"
}

release_mode_check() {
    [ "${PLEBIAN_OS_RELEASE_MODE:-0}" = 1 ] || return 0
    local missing=()
    for key in PLEB_REF KILIX_REF KILIX95_REF KILIX_PREBUILT_VERSION KILIX_PREBUILT_SHA256; do
        [ -n "${!key:-}" ] || missing+=("$key")
    done
    if [ "${#missing[@]}" -gt 0 ]; then
        printf 'PLEBIAN_OS_RELEASE_MODE=1 requires pinned values for: %s\n' "${missing[*]}" >&2
        exit 1
    fi
    if [ -z "${PLEBIAN_OS_APT_SNAPSHOT:-}" ]; then
        echo "release mode: PLEBIAN_OS_APT_SNAPSHOT is unset — Debian package versions will" >&2
        echo "  float to first-boot mirror state (not fully reproducible). Pin a" >&2
        echo "  snapshot.debian.org timestamp for a reproducible apt closure." >&2
    fi
}

write_build_info() {
    local out="$1" commit dirty iso_sha
    commit="$(git -C "$HERE" rev-parse HEAD 2>/dev/null || true)"
    if git -C "$HERE" diff --quiet --ignore-submodules -- 2>/dev/null \
        && git -C "$HERE" diff --cached --quiet --ignore-submodules -- 2>/dev/null; then
        dirty=0
    else
        dirty=1
    fi
    iso_sha="$(sha256sum "$SRC_ISO" 2>/dev/null | awk '{print $1}')"
    {
        echo "# Generated by build/remaster-iso.sh. Sourced as shell by tools."
        manifest_kv PLEBIAN_OS_BUILD_TIME_UTC "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        manifest_kv PLEBIAN_OS_VERSION "$PLEBIAN_OS_VERSION"
        manifest_kv PLEBIAN_OS_RELEASE "${PLEBIAN_OS_RELEASE:-}"
        manifest_kv PLEBIAN_OS_COMMIT "$commit"
        manifest_kv PLEBIAN_OS_DIRTY "$dirty"
        manifest_kv PLEBIAN_OS_SOURCE_ISO "$(basename "$SRC_ISO")"
        manifest_kv PLEBIAN_OS_SOURCE_ISO_SHA256 "$iso_sha"
        manifest_kv PLEBIAN_OS_NETINST_SHA256 "${PLEBIAN_OS_NETINST_SHA256:-}"
        manifest_kv PLEBIAN_OS_RELEASE_MODE "${PLEBIAN_OS_RELEASE_MODE:-0}"
        manifest_kv PLEBIAN_OS_APT_SNAPSHOT "${PLEBIAN_OS_APT_SNAPSHOT:-}"
        manifest_kv PLEBIAN_OS_DESKTOP "${PLEBIAN_OS_DESKTOP:-1}"
        manifest_kv PLEBIAN_OS_KIOSK "${PLEBIAN_OS_KIOSK:-0}"
        manifest_kv PLEBIAN_OS_USER "${PLEBIAN_OS_USER:-}"
        manifest_kv PLEBIAN_OS_NOPASSWD_SUDO "${PLEBIAN_OS_NOPASSWD_SUDO:-0}"
        manifest_kv PLEBIAN_OS_INSTALL_UV "${PLEBIAN_OS_INSTALL_UV:-0}"
        manifest_kv PLEBIAN_OS_REPO "${PLEBIAN_OS_REPO:-https://github.com/itsmygithubacct/plebian-os.git}"
        manifest_kv PLEBIAN_OS_BRANCH "${PLEBIAN_OS_BRANCH:-}"
        manifest_kv PLEBIAN_OS_REF "${PLEBIAN_OS_REF:-}"
        manifest_kv PLEBIAN_OS_CDIMAGE "$PLEBIAN_OS_CDIMAGE"
        manifest_kv PLEB_REPO "${PLEB_REPO:-https://github.com/itsmygithubacct/pleb.git}"
        manifest_kv PLEB_BRANCH "${PLEB_BRANCH:-}"
        manifest_kv PLEB_REF "${PLEB_REF:-}"
        manifest_kv KILIX_REPO "${KILIX_REPO:-https://github.com/itsmygithubacct/kilix.git}"
        manifest_kv KILIX_BRANCH "${KILIX_BRANCH:-}"
        manifest_kv KILIX_REF "${KILIX_REF:-}"
        manifest_kv KILIX_PREBUILT_VERSION "${KILIX_PREBUILT_VERSION:-}"
        manifest_kv KILIX_PREBUILT_SHA256 "${KILIX_PREBUILT_SHA256:-}"
        manifest_kv PLEBIAN_OS_BUILD_KILIX_FORK "${PLEBIAN_OS_BUILD_KILIX_FORK:-1}"
        manifest_kv PLEBIAN_OS_KILIX_GO_MIN_VERSION "${PLEBIAN_OS_KILIX_GO_MIN_VERSION:-1.26}"
        manifest_kv KILIX_DESKTOP_PROVIDER "${KILIX_DESKTOP_PROVIDER:-external}"
        manifest_kv KILIX_DESKTOP_COMMAND "${KILIX_DESKTOP_COMMAND:-}"
        manifest_kv KILIX_DESKTOP_NAME "${KILIX_DESKTOP_NAME:-desktop}"
        manifest_kv KILIX_DESKTOP_FLAVOR "${KILIX_DESKTOP_FLAVOR:-}"
        manifest_kv KILIX95_REPO "${KILIX95_REPO:-https://github.com/itsmygithubacct/kilix-95.git}"
        manifest_kv KILIX95_BRANCH "${KILIX95_BRANCH:-}"
        manifest_kv KILIX95_REF "${KILIX95_REF:-}"
        manifest_kv KILIX95_AUTO_INSTALL "${KILIX95_AUTO_INSTALL:-1}"
    } > "$out"
}

write_firstboot_env() {
    {
        echo "# Generated by build/remaster-iso.sh. Read by plebian-os-firstboot.service."
        env_kv PLEBIAN_OS_DESKTOP "${PLEBIAN_OS_DESKTOP:-1}"
        env_kv PLEBIAN_OS_KIOSK "${PLEBIAN_OS_KIOSK:-0}"
        env_kv PLEBIAN_OS_USER "${PLEBIAN_OS_USER:-}"
        env_kv PLEBIAN_OS_NOPASSWD_SUDO "${PLEBIAN_OS_NOPASSWD_SUDO:-0}"
        env_kv PLEBIAN_OS_INSTALL_UV "${PLEBIAN_OS_INSTALL_UV:-0}"
        env_kv PLEBIAN_OS_VERSION "$PLEBIAN_OS_VERSION"
        env_kv PLEBIAN_OS_APT_SNAPSHOT "${PLEBIAN_OS_APT_SNAPSHOT:-}"
        env_kv PLEBIAN_OS_REPO "${PLEBIAN_OS_REPO:-https://github.com/itsmygithubacct/plebian-os.git}"
        env_kv PLEBIAN_OS_BRANCH "${PLEBIAN_OS_BRANCH:-}"
        env_kv PLEBIAN_OS_REF "${PLEBIAN_OS_REF:-}"
        env_kv PLEB_REPO "${PLEB_REPO:-https://github.com/itsmygithubacct/pleb.git}"
        env_kv PLEB_BRANCH "${PLEB_BRANCH:-}"
        env_kv PLEB_REF "${PLEB_REF:-}"
        env_kv KILIX_REPO "${KILIX_REPO:-https://github.com/itsmygithubacct/kilix.git}"
        env_kv KILIX_BRANCH "${KILIX_BRANCH:-}"
        env_kv KILIX_REF "${KILIX_REF:-}"
        env_kv KILIX_PREBUILT_VERSION "${KILIX_PREBUILT_VERSION:-}"
        env_kv KILIX_PREBUILT_SHA256 "${KILIX_PREBUILT_SHA256:-}"
        env_kv PLEBIAN_OS_BUILD_KILIX_FORK "${PLEBIAN_OS_BUILD_KILIX_FORK:-1}"
        env_kv PLEBIAN_OS_KILIX_GO_MIN_VERSION "${PLEBIAN_OS_KILIX_GO_MIN_VERSION:-1.26}"
        env_kv KILIX_DESKTOP_PROVIDER "${KILIX_DESKTOP_PROVIDER:-external}"
        env_kv KILIX_DESKTOP_COMMAND "${KILIX_DESKTOP_COMMAND:-}"
        env_kv KILIX_DESKTOP_NAME "${KILIX_DESKTOP_NAME:-desktop}"
        env_kv KILIX_DESKTOP_FLAVOR "${KILIX_DESKTOP_FLAVOR:-}"
        env_kv KILIX95_REPO "${KILIX95_REPO:-https://github.com/itsmygithubacct/kilix-95.git}"
        env_kv KILIX95_BRANCH "${KILIX95_BRANCH:-}"
        env_kv KILIX95_REF "${KILIX95_REF:-}"
        env_kv KILIX95_AUTO_INSTALL "${KILIX95_AUTO_INSTALL:-1}"
    } > "$1"
}

release_mode_check

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
EXTRACT="$WORK/iso"
mkdir -p "$EXTRACT"

BUILD_PRESEED="$WORK/preseed.cfg"
cp "$PRESEED" "$BUILD_PRESEED"
if [ "${PLEBIAN_OS_UNATTENDED_DISK:-0}" = 1 ]; then
    echo "    disk setup: unattended partitioning enabled"
else
    echo "    disk setup: installer will ask for target disk/confirmation"
    # Strip ALL partman preseeding (any partman* namespace) so the installer
    # always asks for the target disk, regardless of which partman keys a custom
    # preseed carries — not just the four this used to enumerate.
    sed -i -E '/^d-i[[:space:]]+partman/d' "$BUILD_PRESEED"
fi
PRESEED="$BUILD_PRESEED"

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
cp "$HERE/provision/plebian-os-passwd"           "$EXTRACT/plebian-os/"
write_build_info "$EXTRACT/plebian-os/build-info.env"
write_firstboot_env "$EXTRACT/plebian-os/firstboot.env"

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
    mapfile -t mkisofs_argv < <(python3 - "$WORK/mkisofs.args" <<'PY'
import shlex
import sys

text = []
for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    if line.lstrip().startswith("-outdev"):
        continue
    text.append(line)
for token in shlex.split("".join(text)):
    print(token)
PY
)
    xorriso -as mkisofs "${mkisofs_argv[@]}" -o "$OUT_ISO" "$EXTRACT"
else
    echo "!! could not read the source ISO's El Torito layout; falling back to a" >&2
    echo "   basic build (verify BIOS/UEFI boot before trusting it)." >&2
    xorriso -as mkisofs -r -J -joliet-long -V PLEBIAN_OS \
        -o "$OUT_ISO" "$EXTRACT"
fi

echo "==> done: $OUT_ISO"
echo "    install it like normal Debian; first boot pulls pleb + kilix and"
echo "    comes up as the Pleb (fullscreen kilix) session."
