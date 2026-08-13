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
PLEBIAN_OS_ROOT_SESSION_HOME="${PLEBIAN_OS_ROOT_SESSION_HOME:-/var/lib/plebian-os/session}"

log()  { printf '\033[1;36m[deps]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[deps]\033[0m %s\n' "$*" >&2; }

prepare_root_session_home() {
    local resolved metadata
    case "$PLEBIAN_OS_ROOT_SESSION_HOME" in
        /var/lib/plebian-os/*) ;;
        *) warn "privileged staging must stay under /var/lib/plebian-os"; return 1 ;;
    esac
    resolved="$(readlink -m -- "$PLEBIAN_OS_ROOT_SESSION_HOME" 2>/dev/null)" \
        || { warn "could not resolve privileged staging path"; return 1; }
    [ "$resolved" = "$PLEBIAN_OS_ROOT_SESSION_HOME" ] \
        || { warn "privileged staging path contains a symlink"; return 1; }
    [ ! -L "$PLEBIAN_OS_ROOT_SESSION_HOME" ] \
        || { warn "privileged staging path is a symlink"; return 1; }
    if [ -e "$PLEBIAN_OS_ROOT_SESSION_HOME" ] \
        && [ ! -d "$PLEBIAN_OS_ROOT_SESSION_HOME" ]; then
        warn "privileged staging path is not a directory"
        return 1
    fi
    install -d -o root -g root -m 0700 -- "$PLEBIAN_OS_ROOT_SESSION_HOME" \
        || { warn "could not create privileged staging directory"; return 1; }
    [ -d "$PLEBIAN_OS_ROOT_SESSION_HOME" ] \
        && [ ! -L "$PLEBIAN_OS_ROOT_SESSION_HOME" ] \
        || { warn "privileged staging directory became unsafe"; return 1; }
    chown root:root -- "$PLEBIAN_OS_ROOT_SESSION_HOME" \
        && chmod 0700 -- "$PLEBIAN_OS_ROOT_SESSION_HOME" \
        || { warn "could not secure privileged staging directory"; return 1; }
    metadata="$(stat -c '%u:%g:%a' -- "$PLEBIAN_OS_ROOT_SESSION_HOME" 2>/dev/null)" \
        || { warn "could not inspect privileged staging directory"; return 1; }
    [ "$metadata" = 0:0:700 ] \
        || { warn "privileged staging directory must be root:root mode 0700"; return 1; }
}

# uv 0.12.3 adds its Rust target triple to `uv --version` while retaining the
# pinned semantic version as the second field. Accept that documented shape,
# but reject arbitrary suffix text so the release check still proves the exact
# requested binary version.
uv_version_matches_pin() {
    local actual="$1" expected="$2" prefix target
    [ -n "$actual" ] && [ -n "$expected" ] || return 1
    [ "$actual" != "uv $expected" ] || return 0
    prefix="uv $expected ("
    case "$actual" in
        "$prefix"*) target="${actual#"$prefix"}" ;;
        *) return 1 ;;
    esac
    case "$target" in
        *')') target="${target%)}" ;;
        *) return 1 ;;
    esac
    [ -n "$target" ] && [[ "$target" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]*$ ]]
}

# "group label|space-separated packages" — grouped so a failure is easy to
# locate. The base graphical stack + git/curl are usually already present from
# the Debian install; re-listing them here keeps this a complete, self-standing
# dependency manifest.
DEP_GROUPS=(
    "X + display manager + window manager|xserver-xorg xinit lightdm openbox x11-xserver-utils x11-utils xterm"
    "base system glue|sudo network-manager"
    "repo clone + engine fetch|git curl tar unzip ca-certificates"
    "bash tutorial prerequisites|bash python3 coreutils findutils grep sed gawk diffutils procps util-linux"
    "kilix GL + keyboard|libgl1 libegl1 libxkbcommon0 libxkbcommon-x11-0 libxcb-xkb1"
    # The session runs with TERM=xterm-kitty. Kilix installs the engine's own
    # entry into the user's ~/.terminfo, but root, sudo and any other account
    # resolve through the system database, so a strict ncurses program run
    # there would see an unknown terminal without this.
    "terminfo for the engine|kitty-terminfo"
    "fonts|fonts-jetbrains-mono fonts-noto-color-emoji"
    # PDF Conversion uses this standard-library venv support with a
    # hash-locked pip install independently of uv. The coordinated 0.1.9
    # release also installs its required, verified uv pin as system tooling.
    "kilix desktop + app providers (python)|python3-pil python3-xlib python3-websockets python3-venv"
    "audio|pulseaudio pulseaudio-utils pulsemixer alsa-utils fluidsynth fluid-soundfont-gm"
    # Read-aloud's synthesizer, plus the mbrola runtime its optional quality
    # tier drives. The mbrola *voice databases* (mbrola-us1) are non-free. The
    # image now enables the non-free component, so they are installable — but
    # they stay off this list deliberately: the quality tier is a user opt-in,
    # and plain espeak-ng remains the fallback. Enabling a component only makes
    # a package reachable; it does not oblige the image to ship it.
    # Dictation's library and model are pinned downloads owned by Kilix's
    # installer; unzip is listed in the fetch group above to extract both
    # verified archives.
    "voice (tts/stt)|espeak-ng mbrola"
    # mpv is the image's general media player: ffmpeg above is the codec and
    # capture toolchain rather than something a user opens, and kilix-amp
    # covers music only. Video, and anything else a file manager or desktop
    # link hands off, needs a player that is present on a fresh install.
    "media + nested-X auth + X dialogs|ffmpeg mpv xauth zenity"
    # Browsers can render a PDF, but a desktop install still needs a dedicated
    # local-document handler for file associations, printing, forms, and
    # annotations. Evince is the GTK viewer shipped by the image from 0.1.9.
    "documents|evince"
    "session-log archiving|zstd"
    # firefox-esr and chromium are the graphical browsers. The text browser
    # (Chawan, via `kilix chawan`) is built from source on first use rather
    # than packaged, so what it needs from apt is headers, not a program:
    # libssh2 is what gives it sftp://, and brotli is what lets it decode the
    # encoding most of the web now serves. Kilix's installer can build libssh2
    # itself and can drop SFTP entirely when it is missing, but both are
    # fallbacks — listing them here is what makes the ordinary install
    # complete.
    "web browsers|firefox-esr chromium libssh2-1-dev libbrotli-dev"
    "desktop notifications + portal|dbus-user-session dbus-x11 xfce4-notifyd libnotify-bin xdg-desktop-portal xdg-desktop-portal-gtk"
    "disk management|gparted"
    "app streaming (Xvfb/VNC)|xvfb tigervnc-standalone-server tigervnc-common x11-xkb-utils xfonts-base"
    # The catalog's completed Kilix NVR pin is built locally and links SQLite;
    # libsqlite3-dev supplies both sqlite3.h and the unversioned linker input.
    # Plebian-OS 0.2.0 offers Kilix IceWM as an on-demand program. Keep every
    # development module selected by its pinned CMake configuration explicit;
    # relying on transitive packages makes a fresh --no-install-recommends
    # image fail one pkg-config check at a time on first selection.
    "build toolchain|build-essential cmake pkg-config golang-go nodejs npm python3-dev zlib1g-dev libsqlite3-dev libx11-dev libxrandr-dev libxinerama-dev libxcursor-dev libxrender-dev libxcomposite-dev libxdamage-dev libxfixes-dev libimlib2-dev libxi-dev libxkbcommon-dev libxkbcommon-x11-dev libx11-xcb-dev libxcb-xkb-dev libdbus-1-dev libgl1-mesa-dev libfontconfig-dev libxft-dev libxext-dev libpng-dev liblcms2-dev libcairo2-dev libglib2.0-dev libpoppler-glib-dev libharfbuzz-dev libssl-dev libxxhash-dev libsimde-dev libwayland-dev wayland-protocols libsdl2-dev libsdl2-image-dev libsndfile1-dev libfluidsynth-dev"
    # ripgrep is what the coding agents reach for to search a tree. None of
    # the three bundles a copy, so without it here they fall back to
    # something slower or search nothing at all.
    "cli utilities|tmux ncdu rsync ufw jq glances ripgrep"
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

# uv is useful system tooling but is not a runtime prerequisite for Kilix's
# Python apps: their release installers use Debian's python3-venv and locked
# dependencies. Uncoordinated local builds retain a conservative opt-in
# default; the 0.1.9 release policy requires an immutable version and installer
# checksum and the release loader rejects any different setting.
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
    log "installing uv (image policy enabled; $uv_url -> /usr/local/bin)"
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + stage the uv installer under $PLEBIAN_OS_ROOT_SESSION_HOME (root:root 0700)"
        echo "    + curl -LsSf $uv_url -o <tmp>"
        if [ -n "$uv_sha" ]; then echo "    + verify sha256=$uv_sha"
        else echo "    + (WARNING: PLEBIAN_OS_UV_INSTALLER_SHA256 unset — installer unverified)"; fi
        echo "    + UV_INSTALL_DIR=<staging> UV_NO_MODIFY_PATH=1 sh <tmp>"
        echo "    + verify staged uv --version reports pinned uv $uv_ver (optional target triple accepted), then install it into /usr/local/bin"
    else
        uv_tmp=""; uv_stage=""
        if [ "$uv_ok" = 1 ]; then
            if prepare_root_session_home; then
                uv_tmp="$(mktemp "$PLEBIAN_OS_ROOT_SESSION_HOME/uv-installer.XXXXXX")" \
                    || { warn "could not create uv installer temp file"; uv_ok=0; }
                uv_stage="$(mktemp -d "$PLEBIAN_OS_ROOT_SESSION_HOME/uv-stage.XXXXXX")" \
                    || { warn "could not create uv staging directory"; uv_ok=0; }
            else
                warn "could not prepare privileged uv staging directory"
                uv_ok=0
            fi
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
            if [ -n "$uv_ver" ] && ! uv_version_matches_pin "$uv_actual" "$uv_ver"; then
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
                        uv_version_matches_pin "$uv_actual" "$uv_ver" || uv_ok=0
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
    log "skipping optional uv installer; python3-venv runtimes remain available (set PLEBIAN_OS_INSTALL_UV=1 to opt in)"
fi

if [ "${#failed[@]}" -gt 0 ]; then
    warn "dependency groups with failures: ${failed[*]}"
    warn "re-run this script to retry, or install the group's packages by hand."
    exit 1
fi
[ "$DRY_RUN" = 1 ] && { log "dry run complete."; exit 0; }
log "all dependency groups installed."
