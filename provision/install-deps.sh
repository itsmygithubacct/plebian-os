#!/usr/bin/env bash
# install-deps.sh — install every APT runtime dependency Plebian-OS needs.
#
# The single source of truth for the first-boot dependency set: the provisioner
# (plebian-os-provision) calls this, and it is deployed to the target as
# /usr/local/sbin/plebian-os-install-deps so you can re-run it to debug a bad
# dependency later.  Packages are installed in labelled groups, and a summary at
# the end names any group that failed — so a broken/renamed package is easy to
# find instead of hiding inside one giant apt line.
#
#   sudo plebian-os-install-deps            # install everything
#   plebian-os-install-deps --dry-run       # just print what it would do
#
# NOTE: preseed/preseed.cfg's pkgsel/include mirrors these packages for the
# Debian-installer path (d-i can't call a script); keep the two in sync.
set -uo pipefail

DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

log()  { printf '\033[1;36m[deps]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[deps]\033[0m %s\n' "$*" >&2; }

# "group label|space-separated packages" — grouped so a failure is easy to
# locate. The base graphical stack + git/curl are usually already present from
# the Debian install; re-listing them here keeps this a complete, self-standing
# dependency manifest.
DEP_GROUPS=(
    "X + display manager|xserver-xorg xinit lightdm x11-xserver-utils x11-utils xterm"
    "base system glue|sudo network-manager"
    "repo clone + engine fetch|git curl tar ca-certificates"
    "bash tutorial prerequisites|bash python3 coreutils findutils grep sed gawk diffutils procps util-linux"
    "kilix GL + keyboard|libgl1 libegl1 libxkbcommon0 libxkbcommon-x11-0 libxcb-xkb1"
    "fonts|fonts-jetbrains-mono fonts-noto-color-emoji"
    "kilix desktop provider (python)|python3-pil python3-xlib python3-websockets"
    "audio|pulseaudio pulseaudio-utils alsa-utils fluidsynth fluid-soundfont-gm"
    "media + nested-X auth + X dialogs|ffmpeg xauth zenity"
    "web browsers|firefox-esr chromium"
    "desktop notifications + portal|dbus-user-session dbus-x11 xfce4-notifyd libnotify-bin xdg-desktop-portal xdg-desktop-portal-gtk"
    "app streaming (Xvfb/VNC)|xvfb tigervnc-standalone-server tigervnc-common x11-xkb-utils xfonts-base"
    "build toolchain|build-essential pkg-config golang-go python3-dev zlib1g-dev libx11-dev libxrandr-dev libxinerama-dev libxcursor-dev libxi-dev libxkbcommon-dev libxkbcommon-x11-dev libx11-xcb-dev libxcb-xkb-dev libdbus-1-dev libgl1-mesa-dev libfontconfig-dev libpng-dev liblcms2-dev libcairo2-dev libharfbuzz-dev libssl-dev libxxhash-dev libsimde-dev libwayland-dev wayland-protocols libsdl2-dev libsdl2-image-dev libsndfile1-dev libfluidsynth-dev"
    "cli utilities|tmux ncdu rsync ufw jq glances"
)

if [ "$DRY_RUN" != 1 ] && [ "$(id -u)" -ne 0 ]; then
    warn "must run as root (try: sudo $0)"; exit 1
fi

export DEBIAN_FRONTEND=noninteractive
if [ "$DRY_RUN" = 1 ]; then
    echo "    + apt-get update -y"
else
    apt-get update -y || warn "apt-get update failed (continuing; installs may still work)"
fi

failed=()
for entry in "${DEP_GROUPS[@]}"; do
    name="${entry%%|*}"; pkgs="${entry#*|}"
    log "installing group: $name"
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + apt-get install -y --no-install-recommends $pkgs"
        continue
    fi
    # shellcheck disable=SC2086  # deliberate word-splitting of the package list
    if ! apt-get install -y --no-install-recommends $pkgs; then
        warn "GROUP FAILED: $name"
        warn "    packages: $pkgs"
        failed+=("$name")
    fi
done

# uv is useful but not core to booting Plebian-OS. Do not execute mutable remote
# installer code as root by default; make the tradeoff explicit for local images.
if [ "${PLEBIAN_OS_INSTALL_UV:-0}" = 1 ]; then
    # Pin the uv version via the versioned installer URL, download to a file (not
    # a pipe), and verify its sha256 before executing it as root. Set
    # PLEBIAN_OS_UV_VERSION (e.g. 0.5.11) and PLEBIAN_OS_UV_INSTALLER_SHA256 to
    # pin + verify; without the sha it runs unverified with a loud warning.
    uv_ver="${PLEBIAN_OS_UV_VERSION:-}"
    uv_sha="${PLEBIAN_OS_UV_INSTALLER_SHA256:-}"
    uv_release="${PLEBIAN_OS_RELEASE_MODE:-0}"
    uv_ok=1
    if [ "$uv_release" = 1 ]; then
        if ! [[ "$uv_ver" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            warn "release mode requires an exact PLEBIAN_OS_UV_VERSION when uv is enabled"
            uv_ok=0
        fi
        if ! [[ "$uv_sha" =~ ^[0-9a-fA-F]{64}$ ]]; then
            warn "release mode requires a 64-character PLEBIAN_OS_UV_INSTALLER_SHA256 when uv is enabled"
            uv_ok=0
        fi
    fi
    uv_url="https://astral.sh/uv/${uv_ver:+$uv_ver/}install.sh"
    log "installing uv (operator-requested; $uv_url -> /usr/local/bin)"
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + curl -LsSf $uv_url -o <tmp>"
        if [ -n "$uv_sha" ]; then echo "    + verify sha256=$uv_sha"
        else echo "    + (WARNING: PLEBIAN_OS_UV_INSTALLER_SHA256 unset — installer unverified)"; fi
        echo "    + UV_INSTALL_DIR=<staging> UV_NO_MODIFY_PATH=1 sh <tmp>"
        echo "    + verify staged uv --version reports exactly uv $uv_ver, then install it into /usr/local/bin"
    else
        uv_tmp=""; uv_stage=""
        if [ "$uv_ok" = 1 ]; then
            uv_tmp="$(mktemp)" || { warn "could not create uv installer temp file"; uv_ok=0; }
            uv_stage="$(mktemp -d)" || { warn "could not create uv staging directory"; uv_ok=0; }
        fi
        if [ "$uv_ok" = 1 ] && ! curl -LsSf "$uv_url" -o "$uv_tmp"; then
            warn "uv installer download failed"
            uv_ok=0
        fi
        if [ "$uv_ok" = 1 ] && [ -n "$uv_sha" ] \
            && ! printf '%s  %s\n' "$uv_sha" "$uv_tmp" | sha256sum -c --status; then
            warn "uv installer sha256 mismatch — refusing to run it (expected $uv_sha)"
            uv_ok=0
        fi
        if [ "$uv_ok" = 1 ]; then
            [ -n "$uv_sha" ] \
                || warn "uv installer NOT pinned — set PLEBIAN_OS_UV_INSTALLER_SHA256 to verify it"
            if ! env UV_INSTALL_DIR="$uv_stage" UV_NO_MODIFY_PATH=1 sh "$uv_tmp"; then
                warn "uv install failed"
                uv_ok=0
            fi
        fi
        if [ "$uv_ok" = 1 ]; then
            uv_actual="$("$uv_stage/uv" --version 2>/dev/null || true)"
            if [ -n "$uv_ver" ] && [ "$uv_actual" != "uv $uv_ver" ]; then
                warn "uv version verification failed (expected 'uv $uv_ver', got '${uv_actual:-<missing>}')"
                uv_ok=0
            elif [ -z "$uv_actual" ]; then
                warn "uv installer completed but /usr/local/bin/uv is not runnable"
                uv_ok=0
            else
                install -m 0755 "$uv_stage/uv" /usr/local/bin/uv || uv_ok=0
                if [ -x "$uv_stage/uvx" ]; then
                    install -m 0755 "$uv_stage/uvx" /usr/local/bin/uvx || uv_ok=0
                fi
                if [ "$uv_ok" = 1 ]; then
                    uv_actual="$(/usr/local/bin/uv --version 2>/dev/null || true)"
                    if [ -n "$uv_ver" ]; then
                        [ "$uv_actual" = "uv $uv_ver" ] || uv_ok=0
                    else
                        [ -n "$uv_actual" ] || uv_ok=0
                    fi
                fi
                [ "$uv_ok" = 1 ] \
                    && log "verified installed $uv_actual" \
                    || warn "uv final installation verification failed"
            fi
        fi
        [ -z "$uv_tmp" ] || rm -f "$uv_tmp"
        [ -z "$uv_stage" ] || rm -rf "$uv_stage"
    fi
    if [ "$uv_ok" != 1 ]; then
        if [ "$uv_release" = 1 ]; then
            failed+=("uv (release-required)")
        else
            warn "uv is optional outside release mode; continuing without a verified install"
        fi
    fi
else
    log "skipping uv installer (set PLEBIAN_OS_INSTALL_UV=1 to opt in)"
fi

if [ "${#failed[@]}" -gt 0 ]; then
    warn "dependency groups with failures: ${failed[*]}"
    warn "re-run this script to retry, or install the group's packages by hand."
    exit 1
fi
[ "$DRY_RUN" = 1 ] && { log "dry run complete."; exit 0; }
log "all dependency groups installed."
