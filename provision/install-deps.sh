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
    "build toolchain|build-essential pkg-config golang-go python3-dev zlib1g-dev libx11-dev libxrandr-dev libxinerama-dev libxcursor-dev libxi-dev libxkbcommon-dev libxkbcommon-x11-dev libx11-xcb-dev libdbus-1-dev libgl1-mesa-dev libfontconfig-dev libsdl2-dev libsdl2-image-dev libsndfile1-dev libfluidsynth-dev"
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
    log "installing uv (operator-requested Astral standalone installer -> /usr/local/bin)"
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh"
    elif ! curl -LsSf https://astral.sh/uv/install.sh \
            | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh; then
        warn "uv install failed (optional tool — continuing)"
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
