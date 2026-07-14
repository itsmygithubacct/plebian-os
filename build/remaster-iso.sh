#!/usr/bin/env bash
# remaster-iso.sh — build a Plebian-OS netinst ISO from a stock Debian trixie
# netinst by injecting the preseed + the first-boot provisioner. Phase-1
# "preseeded remaster" approach (same as the plebian sibling project): stock
# installer and repos, with unsigned artwork/config/initrd payloads branded for
# Plebian-OS. Secure Boot's signed shim/GRUB/kernel binaries stay untouched.
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
INSTALLER_ASSETS="$HERE/assets/installer"
INSTALLER_BRANDER="$HERE/build/brand-installer.py"
DESKTOP_WALLPAPER="$HERE/assets/desktop/plebian-os.png"
DESKTOP_WALLPAPER_SHA256=60f63c37f054f7ffd061b47e09a3c22fbf595eec6f161c13e95344ca1a724778
LIGHTDM_GREETER_CONFIG="$HERE/provision/lightdm-gtk-greeter.conf"
LIGHTDM_GREETER_CONFIG_SHA256=985fe09dbbb4ee83949967a83960f71746c054da8d79196a4eac98a32cd76560
INSTALLER_ATTRIBUTION="$HERE/assets/installer/ATTRIBUTION.md"
INSTALLER_ATTRIBUTION_SHA256=5216b6ee1ef154dab56cc5d0a026d28f67ed50feec4129d4fedd6ae2fc2b2fb6
GPL2_LICENSE="$HERE/assets/COPYING.GPL-2"
GPL2_LICENSE_SHA256=8177f97513213526df2cf6184d8ff986c675afb514d4e68a404010521b880643

require_xorriso                          # refuse to run without the ISO packer
for tool in python3 gzip cpio; do
    command -v "$tool" >/dev/null 2>&1 || {
        echo "$tool is required to brand and preserve the source ISO" >&2
        exit 1
    }
done
LC_ALL=C cpio --help 2>&1 | grep -q -- '--reproducible' || {
    echo "GNU cpio with --reproducible support is required" >&2
    exit 1
}
[ -f "$INSTALLER_BRANDER" ] || {
    echo "installer branding helper not found: $INSTALLER_BRANDER" >&2
    exit 1
}
python3 "$INSTALLER_BRANDER" validate-assets "$INSTALLER_ASSETS"
[ -f "$DESKTOP_WALLPAPER" ] && [ ! -L "$DESKTOP_WALLPAPER" ] || {
    echo "tracked desktop wallpaper missing or unsafe: $DESKTOP_WALLPAPER" >&2
    exit 1
}
[ "$(sha256sum "$DESKTOP_WALLPAPER" | awk '{print $1}')" = "$DESKTOP_WALLPAPER_SHA256" ] || {
    echo "tracked desktop wallpaper checksum mismatch: $DESKTOP_WALLPAPER" >&2
    exit 1
}
if [ ! -f "$LIGHTDM_GREETER_CONFIG" ] || [ -L "$LIGHTDM_GREETER_CONFIG" ]; then
    echo "tracked LightDM greeter configuration missing or unsafe: $LIGHTDM_GREETER_CONFIG" >&2
    exit 1
fi
[ "$(sha256sum "$LIGHTDM_GREETER_CONFIG" | awk '{print $1}')" = "$LIGHTDM_GREETER_CONFIG_SHA256" ] || {
    echo "tracked LightDM greeter configuration checksum mismatch: $LIGHTDM_GREETER_CONFIG" >&2
    exit 1
}
if ! grep -Fxq 'background=/usr/local/share/plebian-os/wallpapers/plebian-os.png' \
        "$LIGHTDM_GREETER_CONFIG" \
        || ! grep -Fxq 'user-background=false' "$LIGHTDM_GREETER_CONFIG"; then
    echo "tracked LightDM greeter configuration does not select fixed Plebian branding" >&2
    exit 1
fi
for notice_contract in \
    "$INSTALLER_ATTRIBUTION|$INSTALLER_ATTRIBUTION_SHA256|installer artwork attribution" \
    "$GPL2_LICENSE|$GPL2_LICENSE_SHA256|GPL version 2 license"; do
    IFS='|' read -r notice_path notice_sha notice_label <<<"$notice_contract"
    [ -f "$notice_path" ] && [ ! -L "$notice_path" ] || {
        echo "tracked $notice_label missing or unsafe: $notice_path" >&2
        exit 1
    }
    [ "$(sha256sum "$notice_path" | awk '{print $1}')" = "$notice_sha" ] || {
        echo "tracked $notice_label checksum mismatch: $notice_path" >&2
        exit 1
    }
done
python3 - "$INSTALLER_ATTRIBUTION" "$GPL2_LICENSE" <<'PY' || {
import pathlib
import sys

attribution = pathlib.Path(sys.argv[1]).read_bytes()
license_text = pathlib.Path(sys.argv[2]).read_bytes()
for data in (attribution, license_text):
    if not data or b"\x00" in data or not data.endswith(b"\n"):
        raise SystemExit(1)
    data.decode("utf-8")
if b"../COPYING.GPL-2" not in attribution:
    raise SystemExit(1)
if b"GNU GENERAL PUBLIC LICENSE" not in license_text or b"Version 2, June 1991" not in license_text:
    raise SystemExit(1)
PY
    echo "tracked artwork attribution/license text contract failed" >&2
    exit 1
}

# ── release manifest + version ───────────────────────────────────────────────
# PLEBIAN_OS_RELEASE=<x.y.z> loads releases/<x.y.z>.env — the coordinated pin
# manifest. A named release is an immutable contract: manifest values replace
# ambient values so `PLEBIAN_OS_RELEASE_MODE=0` or a substituted ref cannot keep
# a release label while bypassing its gates. Loaded before the version fallback.
load_release_manifest() {
    local rel="$1"
    local manifest="$HERE/releases/$rel.env"
    [[ "$rel" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
        || { echo "invalid release identifier: $rel" >&2; exit 1; }
    [ -f "$manifest" ] || { echo "no release manifest: releases/$rel.env" >&2; exit 1; }
    echo "==> release $rel: applying pins from releases/$rel.env"
    local line key val
    declare -A seen=()
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in ''|\#*) continue ;; esac
        case "$line" in *=*) ;; *) echo "invalid release manifest line: $line" >&2; exit 1 ;; esac
        key="${line%%=*}"; val="${line#*=}"
        val="${val%\"}"; val="${val#\"}"          # tolerate optional quotes
        case "$key" in
            ''|[0-9]*|*[!A-Za-z0-9_]*) echo "invalid release manifest key: $key" >&2; exit 1 ;;
        esac
        [ -z "${seen[$key]:-}" ] \
            || { echo "duplicate release manifest key: $key" >&2; exit 1; }
        seen[$key]=1
        if [ "$val" = "REPLACE_ME" ]; then
            echo "release $rel: $key is still REPLACE_ME in releases/$rel.env — fill it before building (see RELEASING.md)" >&2
            exit 1
        fi
        export "$key=$val"
    done < "$manifest"
    [ "${PLEBIAN_OS_RELEASE_MODE:-}" = 1 ] \
        || { echo "release $rel manifest must set PLEBIAN_OS_RELEASE_MODE=1" >&2; exit 1; }
    [ "${PLEBIAN_OS_VERSION:-}" = "$rel" ] \
        || { echo "release $rel manifest version mismatch: ${PLEBIAN_OS_VERSION:-unset}" >&2; exit 1; }
    [ "$(cat "$HERE/VERSION" 2>/dev/null)" = "$rel" ] \
        || { echo "release $rel does not match the checkout VERSION" >&2; exit 1; }
}
[ -n "${PLEBIAN_OS_RELEASE:-}" ] && load_release_manifest "$PLEBIAN_OS_RELEASE"

# The version baked into the image (recorded in build-info + firstboot env).
# A named release manifest is authoritative; without one, an explicit value
# takes precedence over the repo VERSION file.
PLEBIAN_OS_VERSION="${PLEBIAN_OS_VERSION:-$(cat "$HERE/VERSION" 2>/dev/null || echo 0.0.0-dev)}"
PLEBIAN_OS_ISO_VOLUME_ID="PLEBIAN-OS $PLEBIAN_OS_VERSION AMD64"
PLEBIAN_OS_MEDIA_INFO="Plebian-OS $PLEBIAN_OS_VERSION amd64 installer (Debian 13 trixie base)"
# Plebian-OS builds amd64 images, so even non-release installs use a known-good
# verified fallback engine instead of silently consenting to an unpinned asset.
: "${KILIX_PREBUILT_VERSION:=0.47.4}"
: "${KILIX_PREBUILT_SHA256:=bc230142b2bd27f2a4bf1b1b67575f3d397a4ea2cc83f4ac2b912c306a939693}"

is_hex_len() {
    local value="$1" length="$2"
    [[ "$value" =~ ^[0-9a-fA-F]+$ ]] && [ "${#value}" -eq "$length" ]
}

# Run before fetch_netinst or mkdir: a release build must verify its immutable
# closure and checkout before it causes any cache/output filesystem changes.
release_preflight() {
    [ "${PLEBIAN_OS_RELEASE_MODE:-0}" = 1 ] || return 0
    local key missing=() actual_commit expected_commit
    for key in \
        PLEBIAN_OS_REF PLEBIAN_OS_NETINST_URL PLEBIAN_OS_NETINST_SHA256 \
        PLEBIAN_OS_APT_SNAPSHOT PLEB_REF KILIX_REF KILIX95_REF \
        KILIX_PREBUILT_VERSION KILIX_PREBUILT_SHA256 \
        PLEBIAN_OS_KILIX_GO_VERSION PLEBIAN_OS_KILIX_GO_SHA256_AMD64 \
        PLEBIAN_OS_KILIX_GO_SHA256_ARM64; do
        [ -n "${!key:-}" ] || missing+=("$key")
    done
    if [ "${PLEBIAN_OS_INSTALL_UV:-0}" = 1 ]; then
        for key in PLEBIAN_OS_UV_VERSION PLEBIAN_OS_UV_INSTALLER_SHA256; do
            [ -n "${!key:-}" ] || missing+=("$key")
        done
    fi
    [ "${#missing[@]}" -eq 0 ] || {
        printf 'PLEBIAN_OS_RELEASE_MODE=1 requires pinned values for: %s\n' "${missing[*]}" >&2
        exit 1
    }
    for key in PLEBIAN_OS_SSH_ENABLED PLEBIAN_OS_AUTOBOOT PLEBIAN_OS_UNATTENDED_DISK; do
        [ "${!key:-0}" != 1 ] || {
            echo "release artifacts refuse $key=1 (network/default-credential or unattended-erase risk)" >&2
            exit 1
        }
    done
    for key in PLEB_REF KILIX_REF KILIX95_REF; do
        is_hex_len "${!key}" 40 || {
            echo "release mode requires $key to be a full 40-character commit SHA" >&2
            exit 1
        }
    done
    for key in PLEBIAN_OS_NETINST_SHA256 KILIX_PREBUILT_SHA256 \
        PLEBIAN_OS_KILIX_GO_SHA256_AMD64 PLEBIAN_OS_KILIX_GO_SHA256_ARM64; do
        is_hex_len "${!key}" 64 || { echo "release mode requires a 64-character $key" >&2; exit 1; }
    done
    case "$PLEBIAN_OS_APT_SNAPSHOT" in
        [0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z|\
        [0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]) ;;
        *) echo "invalid PLEBIAN_OS_APT_SNAPSHOT=$PLEBIAN_OS_APT_SNAPSHOT" >&2; exit 1 ;;
    esac
    actual_commit="$(git -C "$HERE" rev-parse HEAD 2>/dev/null || true)"
    expected_commit="$(git -C "$HERE" rev-parse "${PLEBIAN_OS_REF}^{commit}" 2>/dev/null || true)"
    [ -n "$expected_commit" ] && [ "$actual_commit" = "$expected_commit" ] || {
        echo "release checkout mismatch: HEAD=$actual_commit; PLEBIAN_OS_REF=$PLEBIAN_OS_REF must resolve to it" >&2
        exit 1
    }
    [ -z "$(git -C "$HERE" status --porcelain --untracked-files=normal 2>/dev/null)" ] \
        || { echo "release mode refuses a dirty Plebian-OS checkout" >&2; exit 1; }
}
release_preflight

SRC_ISO="${1:-}"
default_iso_name=plebian-os-netinst-amd64.iso
if [ "${PLEBIAN_OS_RELEASE_MODE:-0}" = 1 ]; then
    [[ "$PLEBIAN_OS_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
        || { echo "release ISO filename requires a semantic PLEBIAN_OS_VERSION" >&2; exit 1; }
    default_iso_name="plebian-os-$PLEBIAN_OS_VERSION-amd64.iso"
fi
OUT_ISO="${2:-$PLEBIAN_OS_ARTIFACTS/$default_iso_name}"
OUT_REAL="$(readlink -m "$OUT_ISO")"
[ ! -b "$OUT_REAL" ] || { echo "refusing to use a block device as ISO output: $OUT_REAL" >&2; exit 1; }
[ ! -d "$OUT_REAL" ] || { echo "ISO output is a directory: $OUT_REAL" >&2; exit 1; }
if [ -z "$SRC_ISO" ]; then
    SRC_ISO="$(fetch_netinst)"           # auto-pull the Debian netinst
else
    [ -f "$SRC_ISO" ] || { echo "no such ISO: $SRC_ISO" >&2; exit 1; }
fi

SRC_REAL="$(readlink -f "$SRC_ISO")"
[ "$SRC_REAL" != "$OUT_REAL" ] || {
    echo "refusing to overwrite the source ISO: $SRC_REAL" >&2
    exit 1
}
OUT_ISO="$OUT_REAL"

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
mkdir -p "$(dirname "$OUT_REAL")"

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

# Resolve the future guest's source/data layout independently from this build
# host's cache and scratch paths. Python builders provide the same values
# explicitly; a direct remaster derives them from the effective preseed user so
# build-info.env and firstboot.env remain complete for the release path too.
resolve_target_layout() {
    local configured_user="${PLEBIAN_OS_USER:-}" preseed_user target_home key
    preseed_user="$(sed -n \
        's/^d-i[[:space:]]\+passwd\/username[[:space:]]\+string[[:space:]]\+\([^[:space:]]\+\)[[:space:]]*$/\1/p' \
        "$PRESEED" | tail -1)"
    [[ "$preseed_user" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] \
        && [ "$preseed_user" != root ] || {
        echo "could not resolve a safe regular target username for firstboot layout" >&2
        exit 1
    }
    if [ -n "$configured_user" ] && [ "$configured_user" != "$preseed_user" ]; then
        echo "PLEBIAN_OS_USER=$configured_user disagrees with preseed target user $preseed_user" >&2
        exit 1
    fi
    PLEBIAN_OS_USER="$preseed_user"
    target_home="/home/$preseed_user"

    # Only target-prefixed variables may transport guest roots across the
    # host/guest boundary. The unprefixed names are commonly exported by a
    # developer's live Pleb session and must never leak into installed media.
    : "${PLEBIAN_OS_TARGET_SOURCE_HOME:=$target_home/gpu_terminal}"
    : "${PLEBIAN_OS_TARGET_GPU_TERMINAL_HOME:=$target_home/.local/gpu_terminal}"
    GPU_TERMINAL_SOURCE_HOME="$PLEBIAN_OS_TARGET_SOURCE_HOME"
    GPU_TERMINAL_HOME="$PLEBIAN_OS_TARGET_GPU_TERMINAL_HOME"
    PLEBIAN_OS_DIR="$GPU_TERMINAL_SOURCE_HOME/plebian-os"
    PLEB_DIR="$GPU_TERMINAL_SOURCE_HOME/pleb"
    KILIX_DIR="$GPU_TERMINAL_SOURCE_HOME/kilix"
    KILIX95_DIR="$GPU_TERMINAL_SOURCE_HOME/kilix-95"
    PLEB_STORAGE_HOME="$GPU_TERMINAL_HOME/pleb"
    PLEB_CONFIG_HOME="$PLEB_STORAGE_HOME/config"
    PLEB_STATE_HOME="$PLEB_STORAGE_HOME/state"
    PLEB_CACHE_HOME="$PLEB_STORAGE_HOME/cache"
    PLEB_SESSION_HOME="$PLEB_STORAGE_HOME/session"
    PLEB_DATA_HOME="$PLEB_STORAGE_HOME/data"
    KILIX_STORAGE_HOME="$GPU_TERMINAL_HOME/kilix"
    KILIX_CONFIG_HOME="$KILIX_STORAGE_HOME/config"
    KILIX_STATE_DIRECTORY="$KILIX_STORAGE_HOME/state"
    KILIX_CACHE_HOME="$KILIX_STORAGE_HOME/cache"
    KILIX_SESSION_HOME="$KILIX_STORAGE_HOME/session"
    KILIX_BUILD_DIRECTORY="$KILIX_STORAGE_HOME/build"
    KILIX_DATA_HOME="$KILIX_STORAGE_HOME/data"
    KILIX_DESKTOP_DIR="$PLEB_DATA_HOME/desktop"
    KILIX_PREBUILT_HOME="$KILIX_STORAGE_HOME/prebuilt/kitty.app"
    KILIX95_STORAGE_HOME="$GPU_TERMINAL_HOME/kilix-95"
    KILIX95_CONFIG_HOME="$KILIX95_STORAGE_HOME/config"
    KILIX95_STATE_HOME="$KILIX95_STORAGE_HOME/state"
    KILIX95_CACHE_HOME="$KILIX95_STORAGE_HOME/cache"
    KILIX95_SESSION_HOME="$KILIX95_STORAGE_HOME/session"
    KILIX95_DATA_HOME="$KILIX95_STORAGE_HOME/data"
    PLEBIAN_OS_STORAGE_HOME="$GPU_TERMINAL_HOME/plebian-os"
    PLEBIAN_OS_SESSION_HOME="$PLEBIAN_OS_STORAGE_HOME/session"

    for key in PLEBIAN_OS_TARGET_SOURCE_HOME \
        PLEBIAN_OS_TARGET_GPU_TERMINAL_HOME GPU_TERMINAL_SOURCE_HOME \
        GPU_TERMINAL_HOME PLEBIAN_OS_STORAGE_HOME PLEBIAN_OS_SESSION_HOME \
        PLEBIAN_OS_DIR PLEB_DIR KILIX_DIR KILIX95_DIR PLEB_STORAGE_HOME \
        PLEB_CONFIG_HOME PLEB_STATE_HOME PLEB_CACHE_HOME PLEB_SESSION_HOME \
        PLEB_DATA_HOME KILIX_STORAGE_HOME KILIX_CONFIG_HOME \
        KILIX_STATE_DIRECTORY KILIX_CACHE_HOME KILIX_SESSION_HOME \
        KILIX_BUILD_DIRECTORY KILIX_DATA_HOME KILIX_DESKTOP_DIR \
        KILIX_PREBUILT_HOME KILIX95_STORAGE_HOME KILIX95_CONFIG_HOME \
        KILIX95_STATE_HOME KILIX95_CACHE_HOME KILIX95_SESSION_HOME \
        KILIX95_DATA_HOME; do
        case "${!key}" in
            /*) ;;
            *) echo "target layout requires absolute $key: ${!key}" >&2; exit 1 ;;
        esac
    done
}
resolve_target_layout

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
    for key in \
        PLEBIAN_OS_REF PLEBIAN_OS_NETINST_URL PLEBIAN_OS_NETINST_SHA256 \
        PLEBIAN_OS_APT_SNAPSHOT \
        PLEB_REF KILIX_REF KILIX95_REF \
        KILIX_PREBUILT_VERSION KILIX_PREBUILT_SHA256 \
        PLEBIAN_OS_KILIX_GO_VERSION \
        PLEBIAN_OS_KILIX_GO_SHA256_AMD64 \
        PLEBIAN_OS_KILIX_GO_SHA256_ARM64; do
        [ -n "${!key:-}" ] || missing+=("$key")
    done
    if [ "${PLEBIAN_OS_INSTALL_UV:-0}" = 1 ]; then
        for key in PLEBIAN_OS_UV_VERSION PLEBIAN_OS_UV_INSTALLER_SHA256; do
            [ -n "${!key:-}" ] || missing+=("$key")
        done
    fi
    if [ "${#missing[@]}" -gt 0 ]; then
        printf 'PLEBIAN_OS_RELEASE_MODE=1 requires pinned values for: %s\n' "${missing[*]}" >&2
        exit 1
    fi
    case "$PLEBIAN_OS_APT_SNAPSHOT" in
        [0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z|\
        [0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]) ;;
        *) echo "invalid PLEBIAN_OS_APT_SNAPSHOT=$PLEBIAN_OS_APT_SNAPSHOT" >&2; exit 1 ;;
    esac
    local actual_commit expected_commit
    actual_commit="$(git -C "$HERE" rev-parse HEAD 2>/dev/null || true)"
    expected_commit="$(git -C "$HERE" rev-parse "${PLEBIAN_OS_REF}^{commit}" 2>/dev/null || true)"
    [ -n "$expected_commit" ] || {
        echo "release ref PLEBIAN_OS_REF=$PLEBIAN_OS_REF does not resolve locally; finalize and tag before building" >&2
        exit 1
    }
    [ "$actual_commit" = "$expected_commit" ] || {
        echo "release checkout mismatch: HEAD=$actual_commit but PLEBIAN_OS_REF=$PLEBIAN_OS_REF resolves to $expected_commit" >&2
        exit 1
    }
    [ -z "$(git -C "$HERE" status --porcelain --untracked-files=normal 2>/dev/null)" ] || {
            echo "release mode refuses a dirty Plebian-OS checkout" >&2
            exit 1
        }
}

write_build_info() {
    local out="$1" commit dirty iso_sha preseed_sha splash_sha banner_sha banner_dark_sha
    local desktop_wallpaper_sha lightdm_greeter_config_sha
    local installer_attribution_sha gpl2_license_sha
    commit="$(git -C "$HERE" rev-parse HEAD 2>/dev/null || true)"
    if [ -z "$(git -C "$HERE" status --porcelain --untracked-files=normal 2>/dev/null)" ]; then
        dirty=0
    else
        dirty=1
    fi
    iso_sha="$(sha256sum "$SRC_ISO" 2>/dev/null | awk '{print $1}')"
    preseed_sha="$(sha256sum "$PRESEED" 2>/dev/null | awk '{print $1}')"
    splash_sha="$(sha256sum "$INSTALLER_ASSETS/splash.png" | awk '{print $1}')"
    banner_sha="$(sha256sum "$INSTALLER_ASSETS/banner.png" | awk '{print $1}')"
    banner_dark_sha="$(sha256sum "$INSTALLER_ASSETS/banner-dark.png" | awk '{print $1}')"
    desktop_wallpaper_sha="$(sha256sum "$DESKTOP_WALLPAPER" | awk '{print $1}')"
    lightdm_greeter_config_sha="$(sha256sum "$LIGHTDM_GREETER_CONFIG" | awk '{print $1}')"
    installer_attribution_sha="$(sha256sum "$INSTALLER_ATTRIBUTION" | awk '{print $1}')"
    gpl2_license_sha="$(sha256sum "$GPL2_LICENSE" | awk '{print $1}')"
    {
        echo "# Generated by build/remaster-iso.sh. Sourced as shell by tools."
        manifest_kv PLEBIAN_OS_BUILD_TIME_UTC "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        manifest_kv PLEBIAN_OS_VERSION "$PLEBIAN_OS_VERSION"
        manifest_kv PLEBIAN_OS_RELEASE "${PLEBIAN_OS_RELEASE:-}"
        manifest_kv PLEBIAN_OS_COMMIT "$commit"
        manifest_kv PLEBIAN_OS_DIRTY "$dirty"
        manifest_kv PLEBIAN_OS_ISO_VOLUME_ID "$PLEBIAN_OS_ISO_VOLUME_ID"
        manifest_kv PLEBIAN_OS_SOURCE_ISO "$(basename "$SRC_ISO")"
        manifest_kv PLEBIAN_OS_SOURCE_ISO_SHA256 "$iso_sha"
        manifest_kv PLEBIAN_OS_PRESEED_SHA256 "$preseed_sha"
        manifest_kv PLEBIAN_OS_INSTALLER_SPLASH_SHA256 "$splash_sha"
        manifest_kv PLEBIAN_OS_INSTALLER_BANNER_SHA256 "$banner_sha"
        manifest_kv PLEBIAN_OS_INSTALLER_BANNER_DARK_SHA256 "$banner_dark_sha"
        manifest_kv PLEBIAN_OS_DESKTOP_WALLPAPER_SHA256 "$desktop_wallpaper_sha"
        manifest_kv PLEBIAN_OS_LIGHTDM_GREETER_CONFIG_SHA256 "$lightdm_greeter_config_sha"
        manifest_kv PLEBIAN_OS_INSTALLER_ATTRIBUTION_SHA256 "$installer_attribution_sha"
        manifest_kv PLEBIAN_OS_GPL2_LICENSE_SHA256 "$gpl2_license_sha"
        manifest_kv PLEBIAN_OS_NETINST_URL "$PLEBIAN_OS_NETINST_URL"
        manifest_kv PLEBIAN_OS_NETINST_SHA256 "${PLEBIAN_OS_NETINST_SHA256:-}"
        manifest_kv PLEBIAN_OS_RELEASE_MODE "${PLEBIAN_OS_RELEASE_MODE:-0}"
        manifest_kv PLEBIAN_OS_APT_SNAPSHOT "${PLEBIAN_OS_APT_SNAPSHOT:-}"
        manifest_kv PLEBIAN_OS_DESKTOP "${PLEBIAN_OS_DESKTOP:-1}"
        manifest_kv PLEBIAN_OS_KIOSK "${PLEBIAN_OS_KIOSK:-0}"
        manifest_kv PLEBIAN_OS_USER "${PLEBIAN_OS_USER:-}"
        manifest_kv PLEBIAN_OS_NOPASSWD_SUDO "${PLEBIAN_OS_NOPASSWD_SUDO:-0}"
        manifest_kv PLEBIAN_OS_INSTALL_UV "${PLEBIAN_OS_INSTALL_UV:-0}"
        manifest_kv PLEBIAN_OS_SSH_ENABLED "${PLEBIAN_OS_SSH_ENABLED:-0}"
        manifest_kv PLEBIAN_OS_AUTOBOOT "${PLEBIAN_OS_AUTOBOOT:-0}"
        manifest_kv PLEBIAN_OS_UNATTENDED_DISK "${PLEBIAN_OS_UNATTENDED_DISK:-0}"
        manifest_kv PLEBIAN_OS_UV_VERSION "${PLEBIAN_OS_UV_VERSION:-}"
        manifest_kv PLEBIAN_OS_UV_INSTALLER_SHA256 "${PLEBIAN_OS_UV_INSTALLER_SHA256:-}"
        manifest_kv GPU_TERMINAL_SOURCE_HOME "${GPU_TERMINAL_SOURCE_HOME:-}"
        manifest_kv GPU_TERMINAL_HOME "${GPU_TERMINAL_HOME:-}"
        manifest_kv PLEBIAN_OS_REPO "${PLEBIAN_OS_REPO:-https://github.com/itsmygithubacct/plebian-os.git}"
        manifest_kv PLEBIAN_OS_BRANCH "${PLEBIAN_OS_BRANCH:-}"
        manifest_kv PLEBIAN_OS_REF "${PLEBIAN_OS_REF:-}"
        manifest_kv PLEBIAN_OS_DIR "${PLEBIAN_OS_DIR:-}"
        manifest_kv PLEBIAN_OS_STORAGE_HOME "${PLEBIAN_OS_STORAGE_HOME:-}"
        manifest_kv PLEBIAN_OS_SESSION_HOME "${PLEBIAN_OS_SESSION_HOME:-}"
        manifest_kv PLEBIAN_OS_CDIMAGE "$PLEBIAN_OS_CDIMAGE"
        manifest_kv PLEB_REPO "${PLEB_REPO:-https://github.com/itsmygithubacct/pleb.git}"
        manifest_kv PLEB_BRANCH "${PLEB_BRANCH:-}"
        manifest_kv PLEB_REF "${PLEB_REF:-}"
        manifest_kv PLEB_DIR "${PLEB_DIR:-}"
        manifest_kv PLEB_STORAGE_HOME "${PLEB_STORAGE_HOME:-}"
        manifest_kv PLEB_CONFIG_HOME "${PLEB_CONFIG_HOME:-}"
        manifest_kv PLEB_STATE_HOME "${PLEB_STATE_HOME:-}"
        manifest_kv PLEB_CACHE_HOME "${PLEB_CACHE_HOME:-}"
        manifest_kv PLEB_SESSION_HOME "${PLEB_SESSION_HOME:-}"
        manifest_kv PLEB_DATA_HOME "${PLEB_DATA_HOME:-}"
        manifest_kv KILIX_REPO "${KILIX_REPO:-https://github.com/itsmygithubacct/kilix.git}"
        manifest_kv KILIX_BRANCH "${KILIX_BRANCH:-}"
        manifest_kv KILIX_REF "${KILIX_REF:-}"
        manifest_kv KILIX_PREBUILT_VERSION "${KILIX_PREBUILT_VERSION:-}"
        manifest_kv KILIX_PREBUILT_SHA256 "${KILIX_PREBUILT_SHA256:-}"
        manifest_kv PLEBIAN_OS_BUILD_KILIX_FORK "${PLEBIAN_OS_BUILD_KILIX_FORK:-1}"
        manifest_kv PLEBIAN_OS_KILIX_GO_MIN_VERSION "${PLEBIAN_OS_KILIX_GO_MIN_VERSION:-1.26}"
        manifest_kv PLEBIAN_OS_KILIX_GO_VERSION "${PLEBIAN_OS_KILIX_GO_VERSION:-}"
        manifest_kv PLEBIAN_OS_KILIX_GO_SHA256_AMD64 "${PLEBIAN_OS_KILIX_GO_SHA256_AMD64:-}"
        manifest_kv PLEBIAN_OS_KILIX_GO_SHA256_ARM64 "${PLEBIAN_OS_KILIX_GO_SHA256_ARM64:-}"
        manifest_kv KILIX_DESKTOP_PROVIDER "${KILIX_DESKTOP_PROVIDER:-auto}"
        manifest_kv KILIX_DESKTOP_COMMAND "${KILIX_DESKTOP_COMMAND:-}"
        manifest_kv KILIX_DESKTOP_NAME "${KILIX_DESKTOP_NAME:-desktop}"
        manifest_kv KILIX_DESKTOP_FLAVOR "${KILIX_DESKTOP_FLAVOR:-}"
        manifest_kv KILIX95_REPO "${KILIX95_REPO:-https://github.com/itsmygithubacct/kilix-95.git}"
        manifest_kv KILIX95_BRANCH "${KILIX95_BRANCH:-}"
        manifest_kv KILIX95_REF "${KILIX95_REF:-}"
        manifest_kv KILIX95_AUTO_INSTALL "${KILIX95_AUTO_INSTALL:-1}"
        manifest_kv KILIX_DIR "${KILIX_DIR:-}"
        manifest_kv KILIX_STORAGE_HOME "${KILIX_STORAGE_HOME:-}"
        manifest_kv KILIX_CONFIG_HOME "${KILIX_CONFIG_HOME:-}"
        manifest_kv KILIX_STATE_DIRECTORY "${KILIX_STATE_DIRECTORY:-}"
        manifest_kv KILIX_CACHE_HOME "${KILIX_CACHE_HOME:-}"
        manifest_kv KILIX_SESSION_HOME "${KILIX_SESSION_HOME:-}"
        manifest_kv KILIX_BUILD_DIRECTORY "${KILIX_BUILD_DIRECTORY:-}"
        manifest_kv KILIX_DATA_HOME "${KILIX_DATA_HOME:-}"
        manifest_kv KILIX_DESKTOP_DIR "${KILIX_DESKTOP_DIR:-}"
        manifest_kv KILIX_PREBUILT_HOME "${KILIX_PREBUILT_HOME:-}"
        manifest_kv KILIX95_DIR "${KILIX95_DIR:-}"
        manifest_kv KILIX95_STORAGE_HOME "${KILIX95_STORAGE_HOME:-}"
        manifest_kv KILIX95_CONFIG_HOME "${KILIX95_CONFIG_HOME:-}"
        manifest_kv KILIX95_STATE_HOME "${KILIX95_STATE_HOME:-}"
        manifest_kv KILIX95_CACHE_HOME "${KILIX95_CACHE_HOME:-}"
        manifest_kv KILIX95_SESSION_HOME "${KILIX95_SESSION_HOME:-}"
        manifest_kv KILIX95_DATA_HOME "${KILIX95_DATA_HOME:-}"
    } > "$out"
}

write_firstboot_env() {
    local runtime_os_ref="${PLEBIAN_OS_REF:-}"
    if [ "${PLEBIAN_OS_RELEASE_MODE:-0}" = 1 ]; then
        runtime_os_ref="$(git -C "$HERE" rev-parse HEAD 2>/dev/null)" \
            || { echo "could not resolve release checkout commit" >&2; exit 1; }
    fi
    {
        echo "# Generated by build/remaster-iso.sh. Read by plebian-os-firstboot.service."
        env_kv PLEBIAN_OS_DESKTOP "${PLEBIAN_OS_DESKTOP:-1}"
        env_kv PLEBIAN_OS_KIOSK "${PLEBIAN_OS_KIOSK:-0}"
        env_kv PLEBIAN_OS_USER "${PLEBIAN_OS_USER:-}"
        env_kv PLEBIAN_OS_NOPASSWD_SUDO "${PLEBIAN_OS_NOPASSWD_SUDO:-0}"
        env_kv PLEBIAN_OS_INSTALL_UV "${PLEBIAN_OS_INSTALL_UV:-0}"
        env_kv PLEBIAN_OS_SSH_ENABLED "${PLEBIAN_OS_SSH_ENABLED:-0}"
        env_kv PLEBIAN_OS_UV_VERSION "${PLEBIAN_OS_UV_VERSION:-}"
        env_kv PLEBIAN_OS_UV_INSTALLER_SHA256 "${PLEBIAN_OS_UV_INSTALLER_SHA256:-}"
        env_kv GPU_TERMINAL_SOURCE_HOME "${GPU_TERMINAL_SOURCE_HOME:-}"
        env_kv GPU_TERMINAL_HOME "${GPU_TERMINAL_HOME:-}"
        env_kv PLEBIAN_OS_VERSION "$PLEBIAN_OS_VERSION"
        env_kv PLEBIAN_OS_RELEASE "${PLEBIAN_OS_RELEASE:-}"
        env_kv PLEBIAN_OS_RELEASE_MODE "${PLEBIAN_OS_RELEASE_MODE:-0}"
        env_kv PLEBIAN_OS_APT_SNAPSHOT "${PLEBIAN_OS_APT_SNAPSHOT:-}"
        env_kv PLEBIAN_OS_REPO "${PLEBIAN_OS_REPO:-https://github.com/itsmygithubacct/plebian-os.git}"
        env_kv PLEBIAN_OS_BRANCH "${PLEBIAN_OS_BRANCH:-}"
        # Installed release updates pin the resolved build commit. Build-info
        # separately retains the human release tag as artifact metadata.
        env_kv PLEBIAN_OS_REF "$runtime_os_ref"
        env_kv PLEBIAN_OS_DIR "${PLEBIAN_OS_DIR:-}"
        env_kv PLEBIAN_OS_STORAGE_HOME "${PLEBIAN_OS_STORAGE_HOME:-}"
        env_kv PLEBIAN_OS_SESSION_HOME "${PLEBIAN_OS_SESSION_HOME:-}"
        env_kv PLEB_REPO "${PLEB_REPO:-https://github.com/itsmygithubacct/pleb.git}"
        env_kv PLEB_BRANCH "${PLEB_BRANCH:-}"
        env_kv PLEB_REF "${PLEB_REF:-}"
        env_kv PLEB_DIR "${PLEB_DIR:-}"
        env_kv PLEB_STORAGE_HOME "${PLEB_STORAGE_HOME:-}"
        env_kv PLEB_CONFIG_HOME "${PLEB_CONFIG_HOME:-}"
        env_kv PLEB_STATE_HOME "${PLEB_STATE_HOME:-}"
        env_kv PLEB_CACHE_HOME "${PLEB_CACHE_HOME:-}"
        env_kv PLEB_SESSION_HOME "${PLEB_SESSION_HOME:-}"
        env_kv PLEB_DATA_HOME "${PLEB_DATA_HOME:-}"
        env_kv KILIX_REPO "${KILIX_REPO:-https://github.com/itsmygithubacct/kilix.git}"
        env_kv KILIX_BRANCH "${KILIX_BRANCH:-}"
        env_kv KILIX_REF "${KILIX_REF:-}"
        env_kv KILIX_PREBUILT_VERSION "${KILIX_PREBUILT_VERSION:-}"
        env_kv KILIX_PREBUILT_SHA256 "${KILIX_PREBUILT_SHA256:-}"
        env_kv PLEBIAN_OS_BUILD_KILIX_FORK "${PLEBIAN_OS_BUILD_KILIX_FORK:-1}"
        env_kv PLEBIAN_OS_KILIX_GO_MIN_VERSION "${PLEBIAN_OS_KILIX_GO_MIN_VERSION:-1.26}"
        env_kv PLEBIAN_OS_KILIX_GO_VERSION "${PLEBIAN_OS_KILIX_GO_VERSION:-}"
        env_kv PLEBIAN_OS_KILIX_GO_SHA256_AMD64 "${PLEBIAN_OS_KILIX_GO_SHA256_AMD64:-}"
        env_kv PLEBIAN_OS_KILIX_GO_SHA256_ARM64 "${PLEBIAN_OS_KILIX_GO_SHA256_ARM64:-}"
        env_kv KILIX_DESKTOP_PROVIDER "${KILIX_DESKTOP_PROVIDER:-auto}"
        env_kv KILIX_DESKTOP_COMMAND "${KILIX_DESKTOP_COMMAND:-}"
        env_kv KILIX_DESKTOP_NAME "${KILIX_DESKTOP_NAME:-desktop}"
        env_kv KILIX_DESKTOP_FLAVOR "${KILIX_DESKTOP_FLAVOR:-}"
        env_kv KILIX95_REPO "${KILIX95_REPO:-https://github.com/itsmygithubacct/kilix-95.git}"
        env_kv KILIX95_BRANCH "${KILIX95_BRANCH:-}"
        env_kv KILIX95_REF "${KILIX95_REF:-}"
        env_kv KILIX95_AUTO_INSTALL "${KILIX95_AUTO_INSTALL:-1}"
        env_kv KILIX_DIR "${KILIX_DIR:-}"
        env_kv KILIX_STORAGE_HOME "${KILIX_STORAGE_HOME:-}"
        env_kv KILIX_CONFIG_HOME "${KILIX_CONFIG_HOME:-}"
        env_kv KILIX_STATE_DIRECTORY "${KILIX_STATE_DIRECTORY:-}"
        env_kv KILIX_CACHE_HOME "${KILIX_CACHE_HOME:-}"
        env_kv KILIX_SESSION_HOME "${KILIX_SESSION_HOME:-}"
        env_kv KILIX_BUILD_DIRECTORY "${KILIX_BUILD_DIRECTORY:-}"
        env_kv KILIX_DATA_HOME "${KILIX_DATA_HOME:-}"
        env_kv KILIX_DESKTOP_DIR "${KILIX_DESKTOP_DIR:-}"
        env_kv KILIX_PREBUILT_HOME "${KILIX_PREBUILT_HOME:-}"
        env_kv KILIX95_DIR "${KILIX95_DIR:-}"
        env_kv KILIX95_STORAGE_HOME "${KILIX95_STORAGE_HOME:-}"
        env_kv KILIX95_CONFIG_HOME "${KILIX95_CONFIG_HOME:-}"
        env_kv KILIX95_STATE_HOME "${KILIX95_STATE_HOME:-}"
        env_kv KILIX95_CACHE_HOME "${KILIX95_CACHE_HOME:-}"
        env_kv KILIX95_SESSION_HOME "${KILIX95_SESSION_HOME:-}"
        env_kv KILIX95_DATA_HOME "${KILIX95_DATA_HOME:-}"
    } > "$1"
}

release_mode_check

mkdir -p "$PLEBIAN_OS_BUILD_HOME" "$(dirname "$OUT_ISO")"
WORK="$(mktemp -d "$PLEBIAN_OS_BUILD_HOME/remaster.XXXXXX")"
OUT_STAGE="$(mktemp -d --tmpdir="$(dirname "$OUT_ISO")" .plebian-os-iso.XXXXXX)"
trap 'rm -rf "$WORK" "$OUT_STAGE"' EXIT
EXTRACT="$WORK/iso"
mkdir -p "$EXTRACT"

replace_installer_asset() {
    local src="$1" dest="$2" metadata_ref mode
    [ -f "$src" ] || { echo "installer asset missing: $src" >&2; exit 1; }
    [ -f "$dest" ] && [ ! -L "$dest" ] \
        || { echo "installer destination missing or unsafe: $dest" >&2; exit 1; }
    metadata_ref="$(mktemp "$WORK/installer-metadata.XXXXXX")"
    touch --reference="$dest" "$metadata_ref"
    mode="$(stat -c '%a' "$dest")"
    install -m "$mode" "$src" "$dest"
    touch --reference="$metadata_ref" "$dest"
    rm -f "$metadata_ref"
}

brand_media_identity() {
    local disk_info="$EXTRACT/.disk/info" mkisofs_info="$EXTRACT/.disk/mkisofs"
    local metadata_ref mode
    [ -f "$disk_info" ] && [ ! -L "$disk_info" ] \
        || { echo "installer media identity missing or unsafe: $disk_info" >&2; exit 1; }
    metadata_ref="$(mktemp "$WORK/media-info-metadata.XXXXXX")"
    touch --reference="$disk_info" "$metadata_ref"
    mode="$(stat -c '%a' "$disk_info")"
    printf '%s\n' "$PLEBIAN_OS_MEDIA_INFO" > "$disk_info"
    chmod "$mode" "$disk_info"
    touch --reference="$metadata_ref" "$disk_info"
    rm -f "$metadata_ref"

    [ -f "$mkisofs_info" ] && [ ! -L "$mkisofs_info" ] \
        || { echo "installer build identity missing or unsafe: $mkisofs_info" >&2; exit 1; }
    metadata_ref="$(mktemp "$WORK/media-build-metadata.XXXXXX")"
    touch --reference="$mkisofs_info" "$metadata_ref"
    mode="$(stat -c '%a' "$mkisofs_info")"
    printf '%s\n' \
        "Plebian-OS $PLEBIAN_OS_VERSION remaster; source $(basename "$SRC_ISO"); see /plebian-os/build-info.env" \
        > "$mkisofs_info"
    chmod "$mode" "$mkisofs_info"
    touch --reference="$metadata_ref" "$mkisofs_info"
    rm -f "$metadata_ref"
}

brand_installer_main_menu() {
    local initrd="$1" label="$2"
    local template="$WORK/$label-main-menu.templates"
    local overlay="$WORK/$label-main-menu-overlay"
    local overlay_cpio="$WORK/$label-main-menu.cpio"
    local combined="$WORK/$label-main-menu-initrd.gz"
    local original_size mode

    [ -f "$initrd" ] && [ ! -L "$initrd" ] \
        || { echo "$label installer initrd missing or unsafe: $initrd" >&2; exit 1; }
    gzip -dc "$initrd" \
        | cpio -i --quiet --to-stdout var/lib/dpkg/info/main-menu.templates \
        > "$template" \
        || { echo "could not extract $label installer main-menu template" >&2; exit 1; }
    [ -s "$template" ] \
        || { echo "$label installer main-menu template is empty" >&2; exit 1; }
    python3 "$INSTALLER_BRANDER" patch-main-menu "$template" "$PLEBIAN_OS_VERSION"

    mkdir -p "$overlay/var/lib/dpkg/info"
    install -m 0644 "$template" "$overlay/var/lib/dpkg/info/main-menu.templates"
    touch -d @0 "$overlay/var/lib/dpkg/info/main-menu.templates"
    (
        cd "$overlay"
        printf '%s\0' var/lib/dpkg/info/main-menu.templates \
            | LC_ALL=C cpio --null --create --format=newc --owner=0:0 \
                --reproducible --quiet
    ) > "$overlay_cpio"
    [ -s "$overlay_cpio" ] \
        || { echo "$label installer main-menu overlay is empty" >&2; exit 1; }

    original_size="$(stat -c '%s' "$initrd")"
    mode="$(stat -c '%a' "$initrd")"
    cp --preserve=mode,timestamps "$initrd" "$combined"
    chmod u+w "$combined"
    gzip -n -9 -c "$overlay_cpio" >> "$combined"
    gzip -t "$combined"
    cmp -n "$original_size" "$initrd" "$combined" \
        || { echo "$label installer initrd prefix changed" >&2; exit 1; }
    tail -c "+$((original_size + 1))" "$combined" \
        | gzip -dc \
        | cpio -i --quiet --to-stdout var/lib/dpkg/info/main-menu.templates \
        | cmp - "$template" \
        || { echo "$label installer main-menu overlay validation failed" >&2; exit 1; }

    touch --reference="$initrd" "$combined"
    chmod "$mode" "$combined"
    mv -f "$combined" "$initrd"
}

brand_graphical_installer() {
    local initrd="$EXTRACT/install.amd/gtk/initrd.gz"
    local inventory="$WORK/gtk-initrd.inventory"
    local overlay="$WORK/gtk-banner-overlay"
    local overlay_cpio="$WORK/gtk-banner.cpio"
    local combined="$WORK/gtk-initrd.gz"
    local original_size mode path asset

    [ -f "$initrd" ] && [ ! -L "$initrd" ] \
        || { echo "graphical installer initrd missing or unsafe: $initrd" >&2; exit 1; }
    if ! gzip -dc "$initrd" | cpio -it --quiet > "$inventory"; then
        echo "could not inventory graphical installer initrd" >&2
        exit 1
    fi
    for path in \
        var/lib/dpkg/info/main-menu.templates \
        usr/share/graphics/logo_debian.png \
        usr/share/graphics/logo_debian_dark.png \
        usr/share/graphics/logo_installer.png \
        usr/share/graphics/logo_installer_dark.png; do
        grep -Fxq "$path" "$inventory" || {
            echo "graphical installer initrd lacks expected path: $path" >&2
            exit 1
        }
    done

    mkdir -p "$overlay/usr/share/graphics" "$overlay/var/lib/dpkg/info"
    gzip -dc "$initrd" \
        | cpio -i --quiet --to-stdout var/lib/dpkg/info/main-menu.templates \
        > "$overlay/var/lib/dpkg/info/main-menu.templates" \
        || { echo "could not extract graphical installer main-menu template" >&2; exit 1; }
    [ -s "$overlay/var/lib/dpkg/info/main-menu.templates" ] \
        || { echo "graphical installer main-menu template is empty" >&2; exit 1; }
    python3 "$INSTALLER_BRANDER" patch-main-menu \
        "$overlay/var/lib/dpkg/info/main-menu.templates" "$PLEBIAN_OS_VERSION"
    install -m 0644 "$INSTALLER_ASSETS/banner.png" \
        "$overlay/usr/share/graphics/logo_debian.png"
    install -m 0644 "$INSTALLER_ASSETS/banner-dark.png" \
        "$overlay/usr/share/graphics/logo_debian_dark.png"
    touch -d @0 \
        "$overlay/var/lib/dpkg/info/main-menu.templates" \
        "$overlay/usr/share/graphics/logo_debian.png" \
        "$overlay/usr/share/graphics/logo_debian_dark.png"

    (
        cd "$overlay"
        printf '%s\0' \
            var/lib/dpkg/info/main-menu.templates \
            usr/share/graphics/logo_debian.png \
            usr/share/graphics/logo_debian_dark.png \
            | LC_ALL=C cpio --null --create --format=newc --owner=0:0 \
                --reproducible --quiet
    ) > "$overlay_cpio"
    [ -s "$overlay_cpio" ] \
        || { echo "graphical installer banner overlay is empty" >&2; exit 1; }

    original_size="$(stat -c '%s' "$initrd")"
    mode="$(stat -c '%a' "$initrd")"
    cp --preserve=mode,timestamps "$initrd" "$combined"
    chmod u+w "$combined"
    gzip -n -9 -c "$overlay_cpio" >> "$combined"
    gzip -t "$combined"
    cmp -n "$original_size" "$initrd" "$combined" \
        || { echo "graphical installer initrd prefix changed" >&2; exit 1; }

    for path in logo_debian.png logo_debian_dark.png; do
        case "$path" in
            logo_debian.png) asset="$INSTALLER_ASSETS/banner.png" ;;
            logo_debian_dark.png) asset="$INSTALLER_ASSETS/banner-dark.png" ;;
        esac
        tail -c "+$((original_size + 1))" "$combined" \
            | gzip -dc \
            | cpio -i --quiet --to-stdout "usr/share/graphics/$path" \
            | cmp - "$asset" \
            || { echo "graphical installer overlay validation failed: $path" >&2; exit 1; }
    done
    tail -c "+$((original_size + 1))" "$combined" \
        | gzip -dc \
        | cpio -i --quiet --to-stdout var/lib/dpkg/info/main-menu.templates \
        | cmp - "$overlay/var/lib/dpkg/info/main-menu.templates" \
        || { echo "graphical installer main-menu overlay validation failed" >&2; exit 1; }

    touch --reference="$initrd" "$combined"
    chmod "$mode" "$combined"
    mv -f "$combined" "$initrd"
}

BUILD_PRESEED="$WORK/preseed.cfg"
cp "$PRESEED" "$BUILD_PRESEED"

apply_installer_snapshot() {
    local seed="$1" ts="${PLEBIAN_OS_APT_SNAPSHOT:-}"
    [ -n "$ts" ] || return 0
    case "$ts" in
        [0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z|\
        [0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]) ;;
        *) echo "invalid PLEBIAN_OS_APT_SNAPSHOT=$ts" >&2; exit 1 ;;
    esac
    echo "    apt snapshot: pinning Debian Installer and first boot to $ts"
    sed -i -E \
        -e 's#^d-i mirror/http/hostname string .*#d-i mirror/http/hostname string snapshot.debian.org#' \
        -e "s#^d-i mirror/http/directory string .*#d-i mirror/http/directory string /archive/debian/$ts#" \
        "$seed"
    cat >> "$seed" <<EOF

### Plebian-OS release snapshot (generated by remaster-iso.sh)
d-i mirror/suite string trixie
d-i apt-setup/services-select multiselect
d-i preseed/early_command string set -e; \\
    mkdir -p /usr/lib/apt-setup/generators; \\
    install -m 0755 /cdrom/plebian-os/plebian-os-apt-snapshot-generator /usr/lib/apt-setup/generators/02plebian-snapshot; \\
    mkdir -p /etc/apt/apt.conf.d; \\
    printf '%s\\n' 'Acquire::Check-Valid-Until "false";' > /etc/apt/apt.conf.d/99plebian-os-snapshot
EOF
}

apply_installer_snapshot "$BUILD_PRESEED"
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

# Derive network exposure from the effective transformed preseed rather than a
# caller-controlled metadata flag. Comments are ignored; any active ssh-server
# task/package/late-command token counts as SSH enabled.
if sed '/^[[:space:]]*#/d' "$PRESEED" \
    | grep -Eq '(^|[[:space:],])(ssh-server|openssh-server)([[:space:],\\]|$)'; then
    PLEBIAN_OS_SSH_ENABLED=1
else
    PLEBIAN_OS_SSH_ENABLED=0
fi
export PLEBIAN_OS_SSH_ENABLED
if [ "${PLEBIAN_OS_RELEASE_MODE:-0}" = 1 ] \
    && [ "$PLEBIAN_OS_SSH_ENABLED" = 1 ]; then
    echo "release artifacts refuse an effective preseed that installs SSH" >&2
    exit 1
fi

echo "==> extracting $SRC_ISO"
xorriso -osirrox on -indev "$SRC_ISO" -extract / "$EXTRACT" >/dev/null 2>&1
chmod -R u+w "$EXTRACT"

echo "==> applying Plebian-OS installer branding ($PLEBIAN_OS_VERSION)"
replace_installer_asset \
    "$INSTALLER_ASSETS/splash.png" \
    "$EXTRACT/isolinux/splash.png"
python3 "$INSTALLER_BRANDER" patch-text "$EXTRACT" "$PLEBIAN_OS_VERSION"
brand_media_identity
brand_installer_main_menu "$EXTRACT/install.amd/initrd.gz" text
brand_graphical_installer

echo "==> injecting preseed + provisioner"
echo "    preseed: $PRESEED"
# The preseed itself, read by the installer.
cp "$PRESEED" "$EXTRACT/preseed.cfg"
# The files late_command copies into the target, staged under /cdrom/plebian-os.
mkdir -p "$EXTRACT/plebian-os"
cp "$HERE/provision/plebian-os-provision.sh"     "$EXTRACT/plebian-os/"
cp "$HERE/provision/plebian-os-firstboot.service" "$EXTRACT/plebian-os/"
cp "$HERE/provision/plebian-os-firstboot-attempt" "$EXTRACT/plebian-os/"
cp "$HERE/provision/install-deps.sh"             "$EXTRACT/plebian-os/"
cp "$HERE/provision/plebian-os-update.sh"        "$EXTRACT/plebian-os/"
cp "$HERE/provision/plebian-os-passwd"           "$EXTRACT/plebian-os/"
cp "$HERE/provision/plebian-os-apt-snapshot-generator" "$EXTRACT/plebian-os/"
install -m 0644 "$DESKTOP_WALLPAPER" "$EXTRACT/plebian-os/desktop-wallpaper.png"
install -m 0644 "$LIGHTDM_GREETER_CONFIG" "$EXTRACT/plebian-os/lightdm-gtk-greeter.conf"
mkdir -p "$EXTRACT/plebian-os/doc/installer"
install -m 0644 "$INSTALLER_ATTRIBUTION" "$EXTRACT/plebian-os/doc/installer/ATTRIBUTION.md"
install -m 0644 "$GPL2_LICENSE" "$EXTRACT/plebian-os/doc/COPYING.GPL-2"
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

echo "==> refreshing installer media checksums"
python3 "$INSTALLER_BRANDER" refresh-md5 "$EXTRACT"

echo "==> repacking -> $OUT_ISO"
OUT_TMP="$OUT_STAGE/output.iso"
# Reuse the source ISO's own boot layout so BIOS + UEFI both keep working.
xorriso -indev "$SRC_ISO" -report_el_torito as_mkisofs 2>/dev/null > "$WORK/mkisofs.args" \
    || { echo "could not read the source ISO boot layout" >&2; exit 1; }
[ -s "$WORK/mkisofs.args" ] || { echo "source ISO reported an empty boot layout" >&2; exit 1; }
mapfile -t mkisofs_argv < <(python3 - "$WORK/mkisofs.args" <<'PY'
import shlex
import sys

text = []
for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    if line.lstrip().startswith("-outdev"):
        continue
    text.append(line)
tokens = shlex.split("".join(text))
i = 0
while i < len(tokens):
    token = tokens[i]
    if token in ("-V", "-volid"):
        i += 2
        continue
    print(token)
    i += 1
PY
)
[ "${#mkisofs_argv[@]}" -gt 0 ] || {
    echo "source ISO boot layout parsed to an empty argument list" >&2
    exit 1
}
xorriso -as mkisofs -V "$PLEBIAN_OS_ISO_VOLUME_ID" \
    "${mkisofs_argv[@]}" -o "$OUT_TMP" "$EXTRACT"

# Refuse to replace a known-good output with a nominally successful but
# non-bootable image. Debian amd64 netinst media should retain both an MBR boot
# signature and at least one El Torito boot entry.
sig="$(dd if="$OUT_TMP" bs=1 skip=510 count=2 2>/dev/null | od -An -tx1 | tr -d ' ')"
[ "$sig" = 55aa ] || { echo "rebuilt ISO lacks an isohybrid MBR signature" >&2; exit 1; }
xorriso -indev "$OUT_TMP" -report_el_torito plain 2>/dev/null > "$WORK/boot-report"
grep -q 'El Torito boot img.*BIOS' "$WORK/boot-report" \
    || { echo "rebuilt ISO has no BIOS El Torito boot image" >&2; exit 1; }
grep -q 'El Torito boot img.*UEFI' "$WORK/boot-report" \
    || { echo "rebuilt ISO has no UEFI El Torito boot image" >&2; exit 1; }
actual_volume_id="$(xorriso -indev "$OUT_TMP" -pvd_info 2>&1 \
    | sed -n "s/^Volume id    : '\(.*\)'$/\1/p" | head -1)"
[ "$actual_volume_id" = "$PLEBIAN_OS_ISO_VOLUME_ID" ] \
    || { echo "rebuilt ISO has wrong volume ID: $actual_volume_id" >&2; exit 1; }
mv -f "$OUT_TMP" "$OUT_ISO"

echo "==> done: $OUT_ISO"
echo "    install it like normal Debian; first boot pulls pleb + kilix and"
echo "    comes up as the Pleb (fullscreen kilix) session."
