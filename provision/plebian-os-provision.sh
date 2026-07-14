#!/usr/bin/env bash
# plebian-os-provision.sh — turn a stock graphical Debian into Plebian-OS.
#
# Plebian-OS is a regular Debian install whose desktop session is Pleb — a
# single fullscreen kilix as the whole "desktop" — in place of XFCE/GNOME.
# The OS ships none of that; this script pulls it from GitHub on first boot:
#
#   1. apt-installs the runtime deps (Xorg, LightDM, git/curl/tar, GL, fonts)
#   2. clones  github.com/itsmygithubacct/pleb  into ~/gpu_terminal/pleb
#   3. runs    pleb install  — which itself clones github.com/itsmygithubacct/kilix
#      into ~/gpu_terminal/kilix, optionally clones github.com/itsmygithubacct/kilix-95
#      into ~/gpu_terminal/kilix-95, fetches a prebuilt kitty engine, and
#      registers "Pleb" as a
#      LightDM session (/usr/share/xsessions/pleb.desktop) + puts kilix and pleb
#      on PATH. This provisioner then builds and verifies the kilix fork so the
#      first boot uses the clickable-chrome engine instead of the fallback.
#   4. (optional) enables Pleb autologin — a hard kiosk that boots straight in
#   5. (optional) grants the target user passwordless sudo (--nopasswd-sudo)
#
# It is idempotent: re-running updates the checkouts, reconciles snapshot/live
# apt and kiosk/sudo state, re-asserts the session, and rewrites final provenance.
# Run as root (the firstboot service does) or via sudo. --dry-run prints the
# plan without touching anything.
set -euo pipefail

# ── config (env-overridable) ─────────────────────────────────────────────────
PLEB_REPO="${PLEB_REPO:-https://github.com/itsmygithubacct/pleb.git}"
KILIX_REPO="${KILIX_REPO:-https://github.com/itsmygithubacct/kilix.git}"
KILIX95_REPO="${KILIX95_REPO:-https://github.com/itsmygithubacct/kilix-95.git}"
PLEB_BRANCH="${PLEB_BRANCH:-}"                 # empty = repo default
PLEB_REF="${PLEB_REF:-}"                       # optional exact commit/tag
KILIX_BRANCH="${KILIX_BRANCH:-}"
KILIX_REF="${KILIX_REF:-}"
KILIX_PREBUILT_VERSION="${KILIX_PREBUILT_VERSION:-0.47.4}" # verified amd64 fallback
KILIX_PREBUILT_SHA256="${KILIX_PREBUILT_SHA256:-bc230142b2bd27f2a4bf1b1b67575f3d397a4ea2cc83f4ac2b912c306a939693}"
KILIX_DESKTOP_PROVIDER="${KILIX_DESKTOP_PROVIDER:-auto}"
KILIX_DESKTOP_COMMAND="${KILIX_DESKTOP_COMMAND:-}"
KILIX_DESKTOP_NAME="${KILIX_DESKTOP_NAME:-desktop}"
KILIX_DESKTOP_FLAVOR="${KILIX_DESKTOP_FLAVOR:-}"
BUILD_KILIX_FORK="${PLEBIAN_OS_BUILD_KILIX_FORK:-1}"
KILIX_GO_MIN_VERSION="${PLEBIAN_OS_KILIX_GO_MIN_VERSION:-1.26}"
KILIX_GO_VERSION="${PLEBIAN_OS_KILIX_GO_VERSION:-}"
KILIX_GO_SHA256_AMD64="${PLEBIAN_OS_KILIX_GO_SHA256_AMD64:-}"
KILIX_GO_SHA256_ARM64="${PLEBIAN_OS_KILIX_GO_SHA256_ARM64:-}"
KILIX95_BRANCH="${KILIX95_BRANCH:-}"
KILIX95_REF="${KILIX95_REF:-}"
KILIX95_AUTO_INSTALL="${KILIX95_AUTO_INSTALL:-1}"
# Plebian-OS layer itself: where the provisioner/update-helper/deps script come
# from, so `plebian-os-update` can refresh the OS layer (not just pleb/kilix).
PLEBIAN_OS_REPO="${PLEBIAN_OS_REPO:-https://github.com/itsmygithubacct/plebian-os.git}"
PLEBIAN_OS_BRANCH="${PLEBIAN_OS_BRANCH:-}"     # empty = repo default
PLEBIAN_OS_REF="${PLEBIAN_OS_REF:-}"           # optional exact commit/tag
PLEBIAN_OS_DIR="${PLEBIAN_OS_DIR:-}"           # default after target user is known
PLEBIAN_OS_VERSION="${PLEBIAN_OS_VERSION:-}"   # resolved from the VERSION file below if empty
PLEBIAN_OS_RELEASE="${PLEBIAN_OS_RELEASE:-}"
PLEBIAN_OS_RELEASE_MODE="${PLEBIAN_OS_RELEASE_MODE:-0}"
PLEBIAN_OS_APT_SNAPSHOT="${PLEBIAN_OS_APT_SNAPSHOT:-}" # snapshot.debian.org ts = reproducible apt
INSTALL_UV="${PLEBIAN_OS_INSTALL_UV:-0}"
UV_VERSION_PIN="${PLEBIAN_OS_UV_VERSION:-}"
UV_INSTALLER_SHA256="${PLEBIAN_OS_UV_INSTALLER_SHA256:-}"
# The apt root is overridable only to exercise snapshot transactions in an
# isolated test tree. Production and firstboot leave it at /etc.
APT_ETC_ROOT="${PLEBIAN_OS_APT_ETC_ROOT:-/etc}"
PLEB_DIR="${PLEB_DIR:-}"                       # defaults after target user is known
KILIX_DIR="${KILIX_DIR:-}"                     # default after target user is known
KILIX95_DIR="${KILIX95_DIR:-}"                 # default after target user is known
KIOSK="${PLEBIAN_OS_KIOSK:-0}"                 # 1 = autologin straight into Pleb
NOPASSWD_SUDO="${PLEBIAN_OS_NOPASSWD_SUDO:-0}" # 1 = passwordless sudo for the user
DESKTOP="${PLEBIAN_OS_DESKTOP:-1}"             # 1 = Pleb boots into `kilix desktop`
TARGET_USER="${PLEBIAN_OS_USER:-}"             # empty = first regular (uid>=1000) user
DRY_RUN=0

# Stable, distribution-owned wallpaper path shared by the builtin Kilix desktop
# and the external Kilix 95 provider.  Keep this checksum in sync with the
# tracked asset: firstboot and in-repo bootstrap fail closed rather than seed a
# desktop state that points at missing or substituted artwork.
DESKTOP_WALLPAPER_DST=/usr/local/share/plebian-os/wallpapers/plebian-os.png
DESKTOP_WALLPAPER_SHA256=60f63c37f054f7ffd061b47e09a3c22fbf595eec6f161c13e95344ca1a724778
DESKTOP_WALLPAPER_MAX_BYTES=$((32 * 1024 * 1024))
LIGHTDM_GREETER_CONFIG_DST=/etc/lightdm/lightdm-gtk-greeter.conf.d/50-plebian-os.conf
LIGHTDM_GREETER_CONFIG_SHA256=985fe09dbbb4ee83949967a83960f71746c054da8d79196a4eac98a32cd76560
INSTALLER_ATTRIBUTION_DST=/usr/local/share/doc/plebian-os/installer/ATTRIBUTION.md
INSTALLER_ATTRIBUTION_SHA256=5216b6ee1ef154dab56cc5d0a026d28f67ed50feec4129d4fedd6ae2fc2b2fb6
GPL2_LICENSE_DST=/usr/local/share/doc/plebian-os/COPYING.GPL-2
GPL2_LICENSE_SHA256=8177f97513213526df2cf6184d8ff986c675afb514d4e68a404010521b880643
ARTWORK_NOTICE_MAX_BYTES=$((1024 * 1024))

# Where this script lives (deployed as /usr/local/sbin/plebian-os-provision, or
# run in-repo from provision/). The runtime dependency set now lives beside us
# in install-deps.sh (deployed as plebian-os-install-deps) — the single source
# of truth — which step 1 below calls.
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"

# Release version: prefer an explicit env (the builders bake it into
# /etc/default/plebian-os); otherwise read the VERSION file shipped beside us.
if [ -z "$PLEBIAN_OS_VERSION" ]; then
    for _vf in "$SELF_DIR/../VERSION" "$SELF_DIR/VERSION" /usr/local/share/plebian-os/VERSION; do
        [ -r "$_vf" ] && { PLEBIAN_OS_VERSION="$(cat "$_vf" 2>/dev/null)"; break; }
    done
fi
: "${PLEBIAN_OS_VERSION:=unknown}"

usage() {
    sed -n '2,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//'
    cat <<EOF

Usage: $0 [--user NAME] [--kiosk] [--nopasswd-sudo] [--no-desktop] [--branch REF] [--dry-run]
  --user NAME    provision for this user (default: first uid>=1000 account)
  --kiosk        enable autologin straight into Pleb (no greeter)
  --nopasswd-sudo grant the target user passwordless sudo
  --no-desktop   boot into a plain fullscreen kilix shell, not a desktop provider
  --branch REF   pleb branch/tag to clone (default: repo default)
  --dry-run      print what would happen; change nothing
  --version      print the Plebian-OS version and exit
EOF
}

log()  { printf '\033[1;36m[plebian-os]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[plebian-os]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[plebian-os] %s\033[0m\n' "$*" >&2; exit 1; }
run()  { if [ "$DRY_RUN" = 1 ]; then echo "    + $*"; else "$@"; fi; }

validate_release_inputs() {
    [ "$PLEBIAN_OS_RELEASE_MODE" = 1 ] || return 0
    local key
    for key in PLEBIAN_OS_REF PLEB_REF KILIX_REF KILIX95_REF; do
        [[ "${!key}" =~ ^[0-9a-fA-F]{40}$ ]] \
            || die "release mode requires $key to be a full 40-character commit SHA"
    done
    for key in KILIX_PREBUILT_SHA256 KILIX_GO_SHA256_AMD64 KILIX_GO_SHA256_ARM64; do
        [[ "${!key}" =~ ^[0-9a-fA-F]{64}$ ]] \
            || die "release mode requires a 64-character $key"
    done
    [[ "$KILIX_GO_VERSION" =~ ^(go)?[0-9]+\.[0-9]+\.[0-9]+$ ]] \
        || die "release mode requires an exact PLEBIAN_OS_KILIX_GO_VERSION"
    if [ "$INSTALL_UV" = 1 ]; then
        [[ "$UV_VERSION_PIN" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
            || die "release mode requires an exact PLEBIAN_OS_UV_VERSION when uv is enabled"
        [[ "$UV_INSTALLER_SHA256" =~ ^[0-9a-fA-F]{64}$ ]] \
            || die "release mode requires a 64-character PLEBIAN_OS_UV_INSTALLER_SHA256 when uv is enabled"
    fi
}

as_user() {
    if [ "$DRY_RUN" = 1 ]; then echo "    + (as $TARGET_USER) $*"; return 0; fi
    command -v setpriv >/dev/null 2>&1 \
        || die "setpriv is required to run provisioning commands as $TARGET_USER"
    setpriv --reuid "$TARGET_UID" --regid "$TARGET_GID" --init-groups \
        --reset-env -- "$@"
}

validate_target_user() {
    local entry shell home_uid
    entry="$(getent passwd "$TARGET_USER" 2>/dev/null)" \
        || die "no such user: $TARGET_USER"
    IFS=: read -r _ _ TARGET_UID TARGET_GID _ USER_HOME shell <<<"$entry"
    case "$TARGET_UID" in ''|*[!0-9]*) die "invalid uid for $TARGET_USER" ;; esac
    if [ "$TARGET_UID" -lt 1000 ] || [ "$TARGET_UID" -ge 65534 ]; then
        die "target user $TARGET_USER must be a regular non-root account (uid 1000-65533)"
    fi
    case "$USER_HOME" in
        /*) ;;
        *) die "target user $TARGET_USER has a non-absolute home: $USER_HOME" ;;
    esac
    if [ "$USER_HOME" = / ] || [ "$USER_HOME" = /root ]; then
        die "target user $TARGET_USER has a system home: $USER_HOME"
    fi
    if [ ! -d "$USER_HOME" ] || [ -L "$USER_HOME" ]; then
        die "home for $TARGET_USER must be an existing non-symlink directory: $USER_HOME"
    fi
    home_uid="$(stat -c '%u' "$USER_HOME" 2>/dev/null)" \
        || die "could not inspect home for $TARGET_USER: $USER_HOME"
    [ "$home_uid" = "$TARGET_UID" ] \
        || die "home for $TARGET_USER is not owned by that user: $USER_HOME"
    case "$shell" in ''|*/false|*/nologin) die "target user $TARGET_USER has a non-login shell: ${shell:-<empty>}" ;; esac
    [ -x "$shell" ] || die "target user $TARGET_USER has an unusable login shell: $shell"
}

ensure_private_storage_root() {
    local path="$1" anchor="$2" label="$3"
    local secure_intermediates="${4:-0}"
    local resolved anchor_real path_real metadata current remaining component
    local -a allocations
    case "$path" in
        /*) ;;
        *) die "$label must be an absolute path: $path" ;;
    esac
    case "$path" in
        "$anchor"/*) ;;
        *) die "$label must be a strict descendant of $anchor: $path" ;;
    esac

    # readlink -m resolves both dot components and every existing symlink.  An
    # exact match therefore establishes a normal, symlink-free path before an
    # as-user mkdir/chmod can touch it.  Repeat the check after creation to
    # catch a path that changed during allocation.
    resolved="$(readlink -m -- "$path" 2>/dev/null)" \
        || die "could not resolve $label: $path"
    [ "$resolved" = "$path" ] \
        || die "$label must not contain symlinks or non-normal components: $path"

    allocations=("$path")
    if [ "$secure_intermediates" = 1 ]; then
        allocations=()
        current="$anchor"
        remaining="${path#"$anchor"/}"
        while [ -n "$remaining" ]; do
            component="${remaining%%/*}"
            [ -n "$component" ] \
                || die "$label contains an empty path component: $path"
            current="$current/$component"
            allocations+=("$current")
            if [ "$component" = "$remaining" ]; then
                remaining=""
            else
                remaining="${remaining#*/}"
            fi
        done
    fi

    for current in "${allocations[@]}"; do
        if [ "$DRY_RUN" = 1 ]; then
            echo "    + (as $TARGET_USER) install -d -m 0700 $current"
            continue
        fi
        as_user install -d -m 0700 -- "$current" \
            || die "could not create or secure $label as $TARGET_USER: $current"
        resolved="$(readlink -m -- "$current" 2>/dev/null)" \
            || die "could not resolve allocated $label component: $current"
        if [ "$resolved" != "$current" ] || [ ! -d "$current" ] \
            || [ -L "$current" ]; then
            die "$label acquired an unsafe directory component: $current"
        fi
        metadata="$(stat -c '%u:%a' -- "$current" 2>/dev/null)" \
            || die "could not inspect allocated $label component: $current"
        [ "$metadata" = "$TARGET_UID:700" ] \
            || die "$label components must be owned by $TARGET_USER with mode 0700: $current ($metadata)"
    done
    [ "$DRY_RUN" != 1 ] || return 0

    resolved="$(readlink -m -- "$path" 2>/dev/null)" \
        || die "could not resolve allocated $label: $path"
    if [ "$resolved" != "$path" ] || [ ! -d "$path" ] || [ -L "$path" ]; then
        die "$label became an unsafe directory during allocation: $path"
    fi

    anchor_real="$(readlink -f -- "$anchor" 2>/dev/null)" \
        || die "could not resolve $label parent: $anchor"
    path_real="$(readlink -f -- "$path" 2>/dev/null)" \
        || die "could not resolve allocated $label: $path"
    case "$path_real" in
        "$anchor_real"/*) ;;
        *) die "$label escaped its private parent $anchor: $path" ;;
    esac

}

secure_managed_pleb_desktop_dir() {
    local state_dir="$1"
    # KILIX_DESKTOP_DIR can deliberately point at operator-shared storage for
    # custom providers.  Only the canonical Pleb-owned location (or a child of
    # it) is ours to create or chmod.
    case "$state_dir" in
        "$PLEB_DATA_HOME")
            ensure_private_storage_root "$PLEB_DATA_HOME" \
                "$PLEB_STORAGE_HOME" PLEB_DATA_HOME 1
            ;;
        "$PLEB_DATA_HOME"/*)
            ensure_private_storage_root "$PLEB_DATA_HOME" \
                "$PLEB_STORAGE_HOME" PLEB_DATA_HOME 1
            ensure_private_storage_root "$state_dir" "$PLEB_DATA_HOME" \
                KILIX_DESKTOP_DIR 1
            ;;
        *) return 0 ;;
    esac
}

allocate_coordinated_private_storage() {
    local resolved home_real data_real i
    local -a labels roots category_labels category_roots category_paths
    case "$GPU_TERMINAL_HOME" in
        /*) ;;
        *) die "GPU_TERMINAL_HOME must be an absolute path: $GPU_TERMINAL_HOME" ;;
    esac
    case "$GPU_TERMINAL_HOME" in
        "$USER_HOME"/*) ;;
        *) die "GPU_TERMINAL_HOME must be a strict descendant of $USER_HOME: $GPU_TERMINAL_HOME" ;;
    esac
    resolved="$(readlink -m -- "$GPU_TERMINAL_HOME" 2>/dev/null)" \
        || die "could not resolve GPU_TERMINAL_HOME: $GPU_TERMINAL_HOME"
    [ "$resolved" = "$GPU_TERMINAL_HOME" ] \
        || die "GPU_TERMINAL_HOME must not contain symlinks or non-normal components: $GPU_TERMINAL_HOME"

    # Treat the target user's existing home as the trust anchor.  The generic
    # helper establishes the shared data root first; component roots can then
    # be proven to remain strict real-path descendants of it.
    ensure_private_storage_root "$GPU_TERMINAL_HOME" "$USER_HOME" \
        "GPU_TERMINAL_HOME"
    if [ "$DRY_RUN" != 1 ]; then
        home_real="$(readlink -f -- "$USER_HOME" 2>/dev/null)" \
            || die "could not resolve target home: $USER_HOME"
        data_real="$(readlink -f -- "$GPU_TERMINAL_HOME" 2>/dev/null)" \
            || die "could not resolve allocated GPU_TERMINAL_HOME: $GPU_TERMINAL_HOME"
        case "$data_real" in
            "$home_real"/*) ;;
            *) die "GPU_TERMINAL_HOME escaped $TARGET_USER's home: $GPU_TERMINAL_HOME" ;;
        esac
    fi

    labels=(
        PLEB_STORAGE_HOME
        KILIX_STORAGE_HOME
        KILIX95_STORAGE_HOME
        PLEBIAN_OS_STORAGE_HOME
    )
    roots=(
        "$PLEB_STORAGE_HOME"
        "$KILIX_STORAGE_HOME"
        "$KILIX95_STORAGE_HOME"
        "$PLEBIAN_OS_STORAGE_HOME"
    )
    for i in "${!roots[@]}"; do
        ensure_private_storage_root "${roots[$i]}" "$GPU_TERMINAL_HOME" \
            "${labels[$i]}" 1
    done

    # Secure every app-owned category before the provision lock or a version
    # probe can become its first writer.  Each category has its own component
    # root as the trust anchor: a misplaced override is rejected instead of
    # chmodding an operator-managed directory elsewhere.  KILIX_DESKTOP_DIR is
    # handled separately below: its canonical PLEB_DATA_HOME location is
    # private, while a cross-provider/shared-data override remains untouched.
    category_labels=(
        PLEB_CONFIG_HOME
        PLEB_STATE_HOME
        PLEB_CACHE_HOME
        PLEB_SESSION_HOME
        PLEB_DATA_HOME
        KILIX_CONFIG_HOME
        KILIX_STATE_DIRECTORY
        KILIX_CACHE_HOME
        KILIX_SESSION_HOME
        KILIX_BUILD_DIRECTORY
        KILIX_DATA_HOME
        KILIX_PREBUILT_HOME
        KILIX95_CONFIG_HOME
        KILIX95_STATE_HOME
        KILIX95_CACHE_HOME
        KILIX95_SESSION_HOME
        KILIX95_DATA_HOME
        PLEBIAN_OS_SESSION_HOME
    )
    category_roots=(
        "$PLEB_STORAGE_HOME"
        "$PLEB_STORAGE_HOME"
        "$PLEB_STORAGE_HOME"
        "$PLEB_STORAGE_HOME"
        "$PLEB_STORAGE_HOME"
        "$KILIX_STORAGE_HOME"
        "$KILIX_STORAGE_HOME"
        "$KILIX_STORAGE_HOME"
        "$KILIX_STORAGE_HOME"
        "$KILIX_STORAGE_HOME"
        "$KILIX_STORAGE_HOME"
        "$KILIX_STORAGE_HOME"
        "$KILIX95_STORAGE_HOME"
        "$KILIX95_STORAGE_HOME"
        "$KILIX95_STORAGE_HOME"
        "$KILIX95_STORAGE_HOME"
        "$KILIX95_STORAGE_HOME"
        "$PLEBIAN_OS_STORAGE_HOME"
    )
    category_paths=(
        "$PLEB_CONFIG_HOME"
        "$PLEB_STATE_HOME"
        "$PLEB_CACHE_HOME"
        "$PLEB_SESSION_HOME"
        "$PLEB_DATA_HOME"
        "$KILIX_CONFIG_HOME"
        "$KILIX_STATE_DIRECTORY"
        "$KILIX_CACHE_HOME"
        "$KILIX_SESSION_HOME"
        "$KILIX_BUILD_DIRECTORY"
        "$KILIX_DATA_HOME"
        "$KILIX_PREBUILT_HOME"
        "$KILIX95_CONFIG_HOME"
        "$KILIX95_STATE_HOME"
        "$KILIX95_CACHE_HOME"
        "$KILIX95_SESSION_HOME"
        "$KILIX95_DATA_HOME"
        "$PLEBIAN_OS_SESSION_HOME"
    )
    for i in "${!category_paths[@]}"; do
        ensure_private_storage_root "${category_paths[$i]}" \
            "${category_roots[$i]}" "${category_labels[$i]}" 1
    done
    secure_managed_pleb_desktop_dir "$KILIX_DESKTOP_DIR"
}

PROVISION_LOCK_FD=""
DESKTOP_WALLPAPER_TMP=""
DESKTOP_WALLPAPER_CREATED_DIRS=()
ARTWORK_NOTICE_TMP=""
ARTWORK_NOTICE_CREATED_DIRS=()
SUDOERS=/etc/sudoers.d/plebian-os-provision

cleanup() {
    if [ "$DRY_RUN" != 1 ]; then
        rm -f "$SUDOERS"
        [ -z "${DESKTOP_WALLPAPER_TMP:-}" ] \
            || rm -f -- "$DESKTOP_WALLPAPER_TMP"
        [ -z "${ARTWORK_NOTICE_TMP:-}" ] \
            || rm -f -- "$ARTWORK_NOTICE_TMP"
        local i
        for ((i=${#DESKTOP_WALLPAPER_CREATED_DIRS[@]}-1; i>=0; i--)); do
            rmdir -- "${DESKTOP_WALLPAPER_CREATED_DIRS[$i]}" 2>/dev/null || true
        done
        for ((i=${#ARTWORK_NOTICE_CREATED_DIRS[@]}-1; i>=0; i--)); do
            rmdir -- "${ARTWORK_NOTICE_CREATED_DIRS[$i]}" 2>/dev/null || true
        done
        if [ -n "${PROVISION_LOCK_FD:-}" ]; then
            flock -u "$PROVISION_LOCK_FD" 2>/dev/null || true
            exec {PROVISION_LOCK_FD}>&-
        fi
    fi
}

restore_provision_signal_traps() {
    if [ -n "${PROVISION_LOCK_FD:-}" ]; then
        trap 'cleanup; trap - EXIT; exit 143' INT TERM HUP
    else
        trap - INT TERM HUP
    fi
}

acquire_provision_lock() {
    local lock owner
    lock="$PLEB_STATE_HOME/update.lock"
    log "serializing provisioning with Pleb updates -> $lock"
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + (as $TARGET_USER) create $lock (0600), then acquire a nonblocking flock"
        return 0
    fi
    command -v flock >/dev/null 2>&1 \
        || die "flock is required to serialize provisioning with Pleb updates"
    as_user mkdir -p "$PLEB_STATE_HOME" \
        || die "could not create Pleb state directory as $TARGET_USER: $PLEB_STATE_HOME"
    if [ ! -d "$PLEB_STATE_HOME" ] || [ -L "$PLEB_STATE_HOME" ]; then
        die "Pleb state path is not a safe directory: $PLEB_STATE_HOME"
    fi
    owner="$(stat -c '%u' "$PLEB_STATE_HOME" 2>/dev/null)" \
        || die "could not inspect Pleb state directory: $PLEB_STATE_HOME"
    [ "$owner" = "$TARGET_UID" ] \
        || die "Pleb state directory is not owned by $TARGET_USER: $PLEB_STATE_HOME"
    as_user touch "$lock" || die "could not create Pleb update lock as $TARGET_USER: $lock"
    if [ ! -f "$lock" ] || [ -L "$lock" ]; then
        die "Pleb update lock is not a safe regular file: $lock"
    fi
    owner="$(stat -c '%u' "$lock" 2>/dev/null)" \
        || die "could not inspect Pleb update lock: $lock"
    [ "$owner" = "$TARGET_UID" ] \
        || die "Pleb update lock is not owned by $TARGET_USER: $lock"
    as_user chmod 0600 "$lock" || die "could not secure Pleb update lock: $lock"
    exec {PROVISION_LOCK_FD}>>"$lock"
    flock -n "$PROVISION_LOCK_FD" \
        || die "another Pleb update or provisioning run is active (lock: $lock)"
    trap cleanup EXIT
    trap 'cleanup; trap - EXIT; exit 143' INT TERM HUP
}

write_session_default() {
    local name="$1" value="$2"
    printf 'if [ -z "${%s+x}" ]; then %s=%q; fi\n' "$name" "$name" "$value"
}

install_no_beep_defaults() {
    local conf=/etc/modprobe.d/plebian-os-no-beep.conf
    log "disabling kernel speaker beeps -> $conf"
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + write $conf (blacklist pcspkr snd_pcsp)"
        echo "    + modprobe -r snd_pcsp pcspkr"
        return
    fi
    mkdir -p "$(dirname "$conf")"
    cat > "$conf" <<'EOF'
# Managed by plebian-os-provision. Keep kernel console/system beeps silent.
blacklist pcspkr
blacklist snd_pcsp
install pcspkr /bin/false
install snd_pcsp /bin/false
EOF
    modprobe -r snd_pcsp pcspkr 2>/dev/null || true
}

validate_desktop_wallpaper() {
    local path="$1" actual
    [ -f "$path" ] && [ ! -L "$path" ] \
        || die "desktop wallpaper is not a safe regular file: $path"
    command -v sha256sum >/dev/null 2>&1 \
        || die "sha256sum is required to validate the desktop wallpaper"
    actual="$(sha256sum "$path" | awk '{print $1}')" \
        || die "could not hash desktop wallpaper: $path"
    [ "$actual" = "$DESKTOP_WALLPAPER_SHA256" ] \
        || die "desktop wallpaper checksum mismatch: $path"
    python3 - "$path" <<'PY' \
        || die "desktop wallpaper does not satisfy the 1920x1080 RGB PNG contract: $path"
import pathlib
import struct
import sys

data = pathlib.Path(sys.argv[1]).read_bytes()
if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
    raise SystemExit(1)
width, height, depth, color_type, compression, filtering, interlace = \
    struct.unpack(">IIBBBBB", data[16:29])
if (width, height, depth, color_type, compression, filtering, interlace) != \
        (1920, 1080, 8, 2, 0, 0, 0):
    raise SystemExit(1)
PY
}

as_target_readonly() {
    if [ "$(id -u)" = "$TARGET_UID" ] && [ "$(id -g)" = "$TARGET_GID" ]; then
        "$@"
        return
    fi
    if [ "$(id -u)" != 0 ]; then
        die "cannot validate $TARGET_USER's Plebian-OS checkout without root"
    fi
    command -v setpriv >/dev/null 2>&1 \
        || die "setpriv is required to validate the target user's Plebian-OS checkout"
    setpriv --reuid "$TARGET_UID" --regid "$TARGET_GID" --init-groups \
        --reset-env -- "$@"
}

validated_checkout_wallpaper() {
    local checkout="$PLEBIAN_OS_DIR" asset remote dirty tracked_blob working_blob
    local owner checkout_real home_real actual resolved fetch_head fetch_mode fetch_lines
    local tag_marker branch_marker
    [ -n "$checkout" ] \
        || die "no PLEBIAN_OS checkout configured for the wallpaper migration"
    case "$checkout" in /*) ;; *) die "PLEBIAN_OS_DIR must be absolute: $checkout" ;; esac
    [ -d "$checkout" ] && [ ! -L "$checkout" ] \
        || die "target user's Plebian-OS checkout is missing or unsafe: $checkout"
    checkout_real="$(readlink -f -- "$checkout" 2>/dev/null)" \
        || die "could not resolve Plebian-OS checkout: $checkout"
    home_real="$(readlink -f -- "$USER_HOME" 2>/dev/null)" \
        || die "could not resolve target home: $USER_HOME"
    case "$checkout_real" in
        "$home_real"/*) ;;
        *) die "Plebian-OS checkout must remain inside $TARGET_USER's home: $checkout" ;;
    esac
    owner="$(stat -c '%u' "$checkout_real" 2>/dev/null)" \
        || die "could not inspect Plebian-OS checkout: $checkout"
    [ "$owner" = "$TARGET_UID" ] \
        || die "Plebian-OS checkout is not owned by $TARGET_USER: $checkout"
    if [ -L "$checkout/.git" ] \
        || { [ ! -d "$checkout/.git" ] && [ ! -f "$checkout/.git" ]; }; then
        die "Plebian-OS path is not a safe git checkout: $checkout"
    fi
    remote="$(as_target_readonly git -C "$checkout" config --get remote.origin.url 2>/dev/null)" \
        || die "could not validate Plebian-OS checkout origin"
    if [ "$remote" != "$PLEBIAN_OS_REPO" ] \
        && [ "${PLEBIAN_OS_TRUST_EXISTING_CHECKOUT:-0}" != 1 ]; then
        die "Plebian-OS checkout at $checkout has origin '$remote', expected '$PLEBIAN_OS_REPO'"
    fi
    dirty="$(as_target_readonly git -C "$checkout" status --porcelain --untracked-files=normal 2>/dev/null)" \
        || die "could not inspect Plebian-OS checkout state"
    [ -z "$dirty" ] \
        || die "Plebian-OS checkout has local changes; refusing wallpaper migration"

    asset="$checkout/assets/desktop/plebian-os.png"
    [ -f "$asset" ] && [ ! -L "$asset" ] \
        || die "validated Plebian-OS checkout lacks the tracked desktop wallpaper: $asset"
    tracked_blob="$(as_target_readonly git -C "$checkout" rev-parse \
        'HEAD:assets/desktop/plebian-os.png' 2>/dev/null)" \
        || die "desktop wallpaper is not tracked at Plebian-OS checkout HEAD"
    working_blob="$(as_target_readonly git -C "$checkout" hash-object -- "$asset" 2>/dev/null)" \
        || die "could not bind desktop wallpaper to Plebian-OS checkout HEAD"
    [ "$working_blob" = "$tracked_blob" ] \
        || die "desktop wallpaper differs from Plebian-OS checkout HEAD"
    if [ -n "$PLEBIAN_OS_REF" ]; then
        actual="$(as_target_readonly git -C "$checkout" rev-parse --verify HEAD 2>/dev/null)" \
            || die "could not resolve Plebian-OS checkout HEAD"
        resolved="$(as_target_readonly git -C "$checkout" rev-parse --verify \
            "${PLEBIAN_OS_REF}^{commit}" 2>/dev/null || true)"
        if [ -z "$resolved" ]; then
            # checkout_pinned_ref deliberately resolves the fetched object from
            # FETCH_HEAD and detaches without creating a local tag. Preserve
            # that trust shape for release-tag upgrades: accept only the one
            # safe FETCH_HEAD record naming the requested tag/branch and only
            # when its commit is exactly the current detached HEAD.
            fetch_head="$(as_target_readonly git -C "$checkout" rev-parse \
                --path-format=absolute --git-path FETCH_HEAD 2>/dev/null)" \
                || die "could not locate FETCH_HEAD for PLEBIAN_OS_REF=$PLEBIAN_OS_REF"
            [ -f "$fetch_head" ] && [ ! -L "$fetch_head" ] \
                || die "missing or unsafe FETCH_HEAD for PLEBIAN_OS_REF=$PLEBIAN_OS_REF"
            owner="$(stat -c '%u' "$fetch_head" 2>/dev/null)" \
                || die "could not inspect Plebian-OS FETCH_HEAD"
            fetch_mode="$(stat -c '%a' "$fetch_head" 2>/dev/null)" \
                || die "could not inspect Plebian-OS FETCH_HEAD mode"
            [ "$owner" = "$TARGET_UID" ] && (( (8#$fetch_mode & 8#22) == 0 )) \
                || die "Plebian-OS FETCH_HEAD has unsafe ownership or mode"
            fetch_lines="$(as_target_readonly awk 'END { print NR }' "$fetch_head")"
            [ "$fetch_lines" = 1 ] \
                || die "PLEBIAN_OS_REF fallback requires exactly one FETCH_HEAD record"
            tag_marker="$(printf "\t\ttag '%s' of " "$PLEBIAN_OS_REF")"
            branch_marker="$(printf "\t\tbranch '%s' of " "$PLEBIAN_OS_REF")"
            if ! as_target_readonly grep -Fq -- "$tag_marker" "$fetch_head" \
                && ! as_target_readonly grep -Fq -- "$branch_marker" "$fetch_head"; then
                die "FETCH_HEAD does not name PLEBIAN_OS_REF=$PLEBIAN_OS_REF"
            fi
            resolved="$(as_target_readonly git -C "$checkout" rev-parse --verify \
                'FETCH_HEAD^{commit}' 2>/dev/null)" \
                || die "FETCH_HEAD does not resolve to a commit"
        fi
        [ "$actual" = "$resolved" ] \
            || die "Plebian-OS checkout HEAD does not match PLEBIAN_OS_REF=$PLEBIAN_OS_REF"
    fi
    printf '%s\n' "$asset"
}

copy_wallpaper_as_target_bounded() {
    local source="$1" destination="$2"
    local limit="${3:-$DESKTOP_WALLPAPER_MAX_BYTES}" label="${4:-desktop wallpaper}"
    local output_fd rc=0
    command -v timeout >/dev/null 2>&1 \
        || die "timeout is required for the unprivileged wallpaper copy"
    exec {output_fd}>"$destination" \
        || die "could not open private wallpaper staging file"
    if as_target_readonly timeout 30s python3 - \
        "$source" "$limit" "$label" >&"$output_fd" <<'PY'
import sys

source, limit_text, label = sys.argv[1:]
limit = int(limit_text)
total = 0
with open(source, "rb", buffering=0) as stream:
    while True:
        chunk = stream.read(min(1024 * 1024, limit + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise SystemExit(f"{label} exceeds bounded copy limit")
        sys.stdout.buffer.write(chunk)
PY
    then
        rc=0
    else
        rc=$?
    fi
    exec {output_fd}>&-
    return "$rc"
}

install_desktop_wallpaper() {
    local repo_root="$SELF_DIR/.." repo_asset source="" dest_dir tmp owner mode size path
    repo_asset="$repo_root/assets/desktop/plebian-os.png"

    # Establish a trusted fixed path before probing or reading the installed
    # asset.  Only the two distribution-owned children may be absent; their
    # fixed ancestors must already be real, root-owned, non-writable dirs.
    for path in / /usr /usr/local /usr/local/share; do
        [ -d "$path" ] && [ ! -L "$path" ] \
            || die "wallpaper destination ancestor is unsafe: $path"
        owner="$(stat -c '%u' "$path" 2>/dev/null)" \
            || die "could not inspect wallpaper destination ancestor: $path"
        mode="$(stat -c '%a' "$path" 2>/dev/null)" \
            || die "could not inspect wallpaper destination ancestor mode: $path"
        [ "$owner" = 0 ] && (( (8#$mode & 8#22) == 0 )) \
            || die "wallpaper destination ancestor is not safely root-owned: $path"
    done
    dest_dir="$(dirname "$DESKTOP_WALLPAPER_DST")"
    for path in /usr/local/share/plebian-os "$dest_dir"; do
        [ ! -L "$path" ] || die "refusing symlink in wallpaper destination: $path"
        if [ -e "$path" ] && [ ! -d "$path" ]; then
            die "wallpaper destination component is not a directory: $path"
        fi
        if [ ! -e "$path" ] && [ "$DRY_RUN" != 1 ]; then
            install -d -o root -g root -m 0755 "$path" \
                || die "could not create wallpaper destination: $path"
            DESKTOP_WALLPAPER_CREATED_DIRS+=("$path")
        fi
        if [ -e "$path" ]; then
            owner="$(stat -c '%u' "$path" 2>/dev/null)" \
                || die "could not inspect wallpaper destination: $path"
            mode="$(stat -c '%a' "$path" 2>/dev/null)" \
                || die "could not inspect wallpaper destination mode: $path"
            [ "$owner" = 0 ] && (( (8#$mode & 8#22) == 0 )) \
                && (( (8#$mode & 8#1) != 0 )) \
                || die "wallpaper destination is not safely root-owned: $path"
        fi
    done

    # A repository checkout is authoritative.  Do not silently reuse an older
    # installed copy if the tracked asset disappeared from a bootstrap checkout.
    if [ -f "$repo_root/VERSION" ]; then
        [ -f "$repo_asset" ] && [ ! -L "$repo_asset" ] \
            || die "tracked desktop wallpaper missing or unsafe: $repo_asset"
        source="$repo_asset"
    elif [ -f "$DESKTOP_WALLPAPER_DST" ] && [ ! -L "$DESKTOP_WALLPAPER_DST" ]; then
        # The remastered ISO stages the asset before firstboot starts.
        source="$DESKTOP_WALLPAPER_DST"
    elif [ -e "$DESKTOP_WALLPAPER_DST" ] || [ -L "$DESKTOP_WALLPAPER_DST" ]; then
        die "installed desktop wallpaper is present but unsafe: $DESKTOP_WALLPAPER_DST"
    else
        # Upgrade bridge: the immutable v0.1.1 updater can deploy this new
        # provisioner but cannot know about the newly added OS-layer payloads.
        # A full reprovision may recover the wallpaper only from the target user's
        # clean, origin-checked checkout and exact tracked blob.
        source="$(validated_checkout_wallpaper)"
    fi

    log "installing Plebian-OS desktop wallpaper -> $DESKTOP_WALLPAPER_DST"
    if [ "$DRY_RUN" = 1 ]; then
        if [ "$source" = "$DESKTOP_WALLPAPER_DST" ]; then
            owner="$(stat -c '%u' "$source" 2>/dev/null)" \
                || die "could not inspect installed desktop wallpaper"
            mode="$(stat -c '%a' "$source" 2>/dev/null)" \
                || die "could not inspect installed desktop wallpaper mode"
            size="$(stat -c '%s' "$source" 2>/dev/null)" \
                || die "could not inspect installed desktop wallpaper size"
            [[ "$size" =~ ^[0-9]+$ ]] && [ "$size" -le "$DESKTOP_WALLPAPER_MAX_BYTES" ] \
                && [ "$owner" = 0 ] && (( (8#$mode & 8#22) == 0 )) \
                || die "installed desktop wallpaper has unsafe ownership, mode, or size"
            validate_desktop_wallpaper "$source"
        else
            tmp="$(mktemp "${TMPDIR:-/tmp}/plebian-os-wallpaper-validate.XXXXXX")" \
                || die "could not create private wallpaper validation file"
            chmod 0600 "$tmp" || { rm -f -- "$tmp"; die "could not secure wallpaper validation file"; }
            if ! copy_wallpaper_as_target_bounded "$source" "$tmp"; then
                rm -f -- "$tmp"
                die "could not copy the desktop wallpaper as $TARGET_USER"
            fi
            if ! (validate_desktop_wallpaper "$tmp"); then
                rm -f -- "$tmp"
                return 1
            fi
            rm -f -- "$tmp"
        fi
        echo "    + install root:root 0644 $source $DESKTOP_WALLPAPER_DST (atomic replace)"
        return 0
    fi

    [ ! -L "$DESKTOP_WALLPAPER_DST" ] \
        || die "refusing symlink wallpaper destination: $DESKTOP_WALLPAPER_DST"

    if [ "$source" != "$DESKTOP_WALLPAPER_DST" ]; then
        tmp="$(mktemp "$dest_dir/.plebian-os.png.XXXXXX")" \
            || die "could not stage the desktop wallpaper"
        DESKTOP_WALLPAPER_TMP="$tmp"
        chown root:root "$tmp" && chmod 0600 "$tmp" \
            || die "could not secure private wallpaper staging file"
        if ! copy_wallpaper_as_target_bounded "$source" "$tmp"; then
            rm -f -- "$tmp"
            DESKTOP_WALLPAPER_TMP=""
            die "could not copy the desktop wallpaper as $TARGET_USER"
        fi
        if ! validate_desktop_wallpaper "$tmp"; then
            rm -f -- "$tmp"
            return 1
        fi
        chmod 0644 "$tmp" \
            || die "could not publish validated wallpaper staging permissions"
        if ! mv -fT -- "$tmp" "$DESKTOP_WALLPAPER_DST"; then
            rm -f -- "$tmp"
            DESKTOP_WALLPAPER_TMP=""
            die "could not atomically install the desktop wallpaper"
        fi
        DESKTOP_WALLPAPER_TMP=""
    else
        owner="$(stat -c '%u' "$source" 2>/dev/null)" \
            || die "could not inspect installed desktop wallpaper"
        mode="$(stat -c '%a' "$source" 2>/dev/null)" \
            || die "could not inspect installed desktop wallpaper mode"
        size="$(stat -c '%s' "$source" 2>/dev/null)" \
            || die "could not inspect installed desktop wallpaper size"
        [[ "$size" =~ ^[0-9]+$ ]] && [ "$size" -le "$DESKTOP_WALLPAPER_MAX_BYTES" ] \
            && [ "$owner" = 0 ] && (( (8#$mode & 8#22) == 0 )) \
            || die "installed desktop wallpaper has unsafe ownership, mode, or size"
        validate_desktop_wallpaper "$source"
        chown root:root "$DESKTOP_WALLPAPER_DST" \
            || die "could not enforce wallpaper ownership"
        chmod 0644 "$DESKTOP_WALLPAPER_DST" \
            || die "could not enforce wallpaper permissions"
    fi
    validate_desktop_wallpaper "$DESKTOP_WALLPAPER_DST"
}

validate_artwork_notice() {
    local path="$1" expected="$2" label="$3" kind="$4" actual size
    [ -f "$path" ] && [ ! -L "$path" ] \
        || die "$label is not a safe regular file: $path"
    size="$(stat -c '%s' "$path" 2>/dev/null)" \
        || die "could not inspect $label size: $path"
    [[ "$size" =~ ^[0-9]+$ ]] && [ "$size" -le "$ARTWORK_NOTICE_MAX_BYTES" ] \
        || die "$label exceeds its bounded size contract: $path"
    actual="$(sha256sum "$path" | awk '{print $1}')" \
        || die "could not hash $label: $path"
    [ "$actual" = "$expected" ] || die "$label checksum mismatch: $path"
    python3 - "$path" "$kind" <<'PY' \
        || die "$label text contract failed: $path"
import pathlib
import sys

data = pathlib.Path(sys.argv[1]).read_bytes()
kind = sys.argv[2]
if not data or b"\x00" in data or not data.endswith(b"\n"):
    raise SystemExit(1)
text = data.decode("utf-8")
if kind == "attribution":
    if "../COPYING.GPL-2" not in text or "GPL-2.0-or-later" not in text:
        raise SystemExit(1)
elif kind == "license":
    if "GNU GENERAL PUBLIC LICENSE" not in text or "Version 2, June 1991" not in text:
        raise SystemExit(1)
elif kind == "greeter":
    required = {
        "[greeter]",
        "background=/usr/local/share/plebian-os/wallpapers/plebian-os.png",
        "user-background=false",
    }
    lines = {line.strip() for line in text.splitlines()
             if line.strip() and not line.lstrip().startswith("#")}
    if lines != required or "Debian" in text:
        raise SystemExit(1)
else:
    raise SystemExit(1)
PY
}

validate_artwork_notice_destination_dirs() {
    local path owner mode
    for path in / /usr /usr/local /usr/local/share; do
        [ -d "$path" ] && [ ! -L "$path" ] \
            || die "artwork notice destination ancestor is unsafe: $path"
        owner="$(stat -c '%u' "$path" 2>/dev/null)" \
            || die "could not inspect artwork notice destination ancestor: $path"
        mode="$(stat -c '%a' "$path" 2>/dev/null)" \
            || die "could not inspect artwork notice destination ancestor mode: $path"
        [ "$owner" = 0 ] && (( (8#$mode & 8#22) == 0 )) \
            || die "artwork notice destination ancestor is not safely root-owned: $path"
    done
    for path in \
        /usr/local/share/doc \
        /usr/local/share/doc/plebian-os \
        /usr/local/share/doc/plebian-os/installer; do
        [ ! -L "$path" ] || die "refusing symlink in artwork notice destination: $path"
        if [ -e "$path" ] && [ ! -d "$path" ]; then
            die "artwork notice destination component is not a directory: $path"
        fi
        if [ ! -e "$path" ] && [ "$DRY_RUN" != 1 ]; then
            install -d -o root -g root -m 0755 "$path" \
                || die "could not create artwork notice destination: $path"
            ARTWORK_NOTICE_CREATED_DIRS+=("$path")
        fi
        if [ -e "$path" ]; then
            owner="$(stat -c '%u' "$path" 2>/dev/null)" \
                || die "could not inspect artwork notice destination: $path"
            mode="$(stat -c '%a' "$path" 2>/dev/null)" \
                || die "could not inspect artwork notice destination mode: $path"
            [ "$owner" = 0 ] && (( (8#$mode & 8#22) == 0 )) \
                && (( (8#$mode & 8#1) != 0 )) \
                || die "artwork notice destination is not safely root-owned: $path"
        fi
    done
}

install_artwork_notice() {
    local source="$1" destination="$2" expected="$3" label="$4" kind="$5"
    local tmp owner group mode size dest_dir
    dest_dir="$(dirname "$destination")"
    log "installing $label -> $destination"

    if [ "$source" = "$destination" ]; then
        owner="$(stat -c '%u' "$source" 2>/dev/null)" \
            || die "could not inspect installed $label owner"
        group="$(stat -c '%g' "$source" 2>/dev/null)" \
            || die "could not inspect installed $label group"
        mode="$(stat -c '%a' "$source" 2>/dev/null)" \
            || die "could not inspect installed $label mode"
        size="$(stat -c '%s' "$source" 2>/dev/null)" \
            || die "could not inspect installed $label size"
        [ "$owner" = 0 ] && [ "$group" = 0 ] \
            && [[ "$size" =~ ^[0-9]+$ ]] \
            && [ "$size" -le "$ARTWORK_NOTICE_MAX_BYTES" ] \
            && (( (8#$mode & 8#22) == 0 )) \
            || die "installed $label has unsafe ownership, mode, or size"
        validate_artwork_notice "$source" "$expected" "$label" "$kind"
        if [ "$DRY_RUN" = 1 ]; then
            echo "    + enforce root:root 0644 $destination"
        else
            chown root:root "$destination" && chmod 0644 "$destination" \
                || die "could not enforce installed $label ownership and permissions"
        fi
        return 0
    fi

    if [ "$DRY_RUN" = 1 ]; then
        tmp="$(mktemp "${TMPDIR:-/tmp}/plebian-os-notice-validate.XXXXXX")" \
            || die "could not create private $label validation file"
    else
        tmp="$(mktemp "$dest_dir/.$(basename "$destination").XXXXXX")" \
            || die "could not create private $label staging file"
        ARTWORK_NOTICE_TMP="$tmp"
    fi
    chmod 0600 "$tmp" || { rm -f -- "$tmp"; die "could not secure $label staging file"; }
    if ! copy_wallpaper_as_target_bounded \
        "$source" "$tmp" "$ARTWORK_NOTICE_MAX_BYTES" "$label"; then
        rm -f -- "$tmp"
        ARTWORK_NOTICE_TMP=""
        die "could not copy $label as $TARGET_USER"
    fi
    if ! (validate_artwork_notice "$tmp" "$expected" "$label" "$kind"); then
        rm -f -- "$tmp"
        ARTWORK_NOTICE_TMP=""
        return 1
    fi
    if [ "$DRY_RUN" = 1 ]; then
        rm -f -- "$tmp"
        echo "    + install root:root 0644 $source $destination (atomic replace)"
        return 0
    fi
    chown root:root "$tmp" && chmod 0644 "$tmp" \
        || die "could not publish validated $label staging permissions"
    if ! mv -fT -- "$tmp" "$destination"; then
        rm -f -- "$tmp"
        ARTWORK_NOTICE_TMP=""
        die "could not atomically install $label"
    fi
    ARTWORK_NOTICE_TMP=""
    validate_artwork_notice "$destination" "$expected" "$label" "$kind"
    [ "$(stat -c '%u:%g:%a' "$destination")" = 0:0:644 ] \
        || die "installed $label does not have root:root 0644 metadata"
}

install_artwork_notices() {
    local repo_root="$SELF_DIR/.." attribution_source license_source
    validate_artwork_notice_destination_dirs
    if [ -f "$repo_root/VERSION" ]; then
        attribution_source="$repo_root/assets/installer/ATTRIBUTION.md"
        license_source="$repo_root/assets/COPYING.GPL-2"
        [ -f "$attribution_source" ] && [ ! -L "$attribution_source" ] \
            || die "tracked installer artwork attribution missing or unsafe: $attribution_source"
        [ -f "$license_source" ] && [ ! -L "$license_source" ] \
            || die "tracked GPL version 2 license missing or unsafe: $license_source"
    else
        attribution_source="$INSTALLER_ATTRIBUTION_DST"
        license_source="$GPL2_LICENSE_DST"
        [ -e "$attribution_source" ] || [ -L "$attribution_source" ] \
            || die "installed installer artwork attribution is missing: $attribution_source"
        [ -e "$license_source" ] || [ -L "$license_source" ] \
            || die "installed GPL version 2 license is missing: $license_source"
    fi

    # Publish the license first so the attribution's relative link is never
    # introduced before its target exists.
    install_artwork_notice "$license_source" "$GPL2_LICENSE_DST" \
        "$GPL2_LICENSE_SHA256" "GPL version 2 license" license
    install_artwork_notice "$attribution_source" "$INSTALLER_ATTRIBUTION_DST" \
        "$INSTALLER_ATTRIBUTION_SHA256" "installer artwork attribution" attribution
}

install_lightdm_greeter_branding() {
    local repo_root="$SELF_DIR/.." source path owner mode config_dir
    config_dir="$(dirname "$LIGHTDM_GREETER_CONFIG_DST")"

    # LightDM owns /etc/lightdm. Plebian-OS owns only its drop-in directory and
    # file; reject link tricks or writable ancestors before creating either.
    for path in / /etc /etc/lightdm; do
        [ -d "$path" ] && [ ! -L "$path" ] \
            || die "LightDM greeter destination ancestor is unsafe: $path"
        owner="$(stat -c '%u' "$path" 2>/dev/null)" \
            || die "could not inspect LightDM greeter destination ancestor: $path"
        mode="$(stat -c '%a' "$path" 2>/dev/null)" \
            || die "could not inspect LightDM greeter destination ancestor mode: $path"
        [ "$owner" = 0 ] && (( (8#$mode & 8#22) == 0 )) \
            || die "LightDM greeter destination ancestor is not safely root-owned: $path"
    done
    [ ! -L "$config_dir" ] \
        || die "refusing symlink LightDM greeter configuration directory: $config_dir"
    if [ -e "$config_dir" ] && [ ! -d "$config_dir" ]; then
        die "LightDM greeter configuration path is not a directory: $config_dir"
    fi
    if [ ! -e "$config_dir" ] && [ "$DRY_RUN" != 1 ]; then
        install -d -o root -g root -m 0755 "$config_dir" \
            || die "could not create LightDM greeter configuration directory"
        ARTWORK_NOTICE_CREATED_DIRS+=("$config_dir")
    fi
    if [ -e "$config_dir" ]; then
        owner="$(stat -c '%u' "$config_dir" 2>/dev/null)"
        mode="$(stat -c '%a' "$config_dir" 2>/dev/null)"
        [ "$owner" = 0 ] && (( (8#$mode & 8#22) == 0 )) \
            && (( (8#$mode & 8#1) != 0 )) \
            || die "LightDM greeter configuration directory is not safely root-owned"
        if [ "$DRY_RUN" = 1 ]; then
            echo "    + enforce root:root 0755 $config_dir"
        else
            chown root:root "$config_dir" && chmod 0755 "$config_dir" \
                || die "could not enforce LightDM greeter configuration directory metadata"
        fi
    fi
    [ ! -L "$LIGHTDM_GREETER_CONFIG_DST" ] \
        || die "refusing symlink LightDM greeter configuration"

    if [ -f "$repo_root/VERSION" ]; then
        source="$SELF_DIR/lightdm-gtk-greeter.conf"
        [ -f "$source" ] && [ ! -L "$source" ] \
            || die "tracked LightDM greeter configuration missing or unsafe: $source"
    else
        source="$LIGHTDM_GREETER_CONFIG_DST"
        [ -e "$source" ] || [ -L "$source" ] \
            || die "installed LightDM greeter configuration is missing: $source"
    fi
    install_artwork_notice "$source" "$LIGHTDM_GREETER_CONFIG_DST" \
        "$LIGHTDM_GREETER_CONFIG_SHA256" "LightDM greeter branding" greeter
}

selected_desktop_wallpaper_state_dir() {
    case "$KILIX_DESKTOP_PROVIDER" in
        external|builtin|auto) printf '%s\n' "$KILIX_DESKTOP_DIR" ;;
        *) return 1 ;;
    esac
}

seed_selected_desktop_wallpaper_state() {
    local state_dir
    state_dir="$(selected_desktop_wallpaper_state_dir)" || {
        log "desktop provider $KILIX_DESKTOP_PROVIDER does not use managed Pleb wallpaper state"
        return 0
    }
    seed_desktop_wallpaper_state "$state_dir" "$DESKTOP_WALLPAPER_DST"
}

seed_desktop_wallpaper_state() {
    local state_dir="${1:?desktop state directory is required}"
    local wallpaper="${2:-$DESKTOP_WALLPAPER_DST}"
    local state_path="$state_dir/.state.json" owner rc

    [ "$DESKTOP" = 1 ] || return 0
    secure_managed_pleb_desktop_dir "$state_dir"
    if [ -e "$state_path" ] || [ -L "$state_path" ]; then
        log "preserving existing Pleb desktop state (including wallpaper): $state_path"
        return 0
    fi
    log "seeding the Plebian-OS wallpaper for a new Pleb desktop -> $state_path"
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + (as $TARGET_USER) create $state_path (0600) only if it still does not exist"
        return 0
    fi

    as_user mkdir -p -- "$state_dir" \
        || die "could not create Pleb desktop state directory as $TARGET_USER: $state_dir"
    [ -d "$state_dir" ] && [ ! -L "$state_dir" ] \
        || die "Pleb desktop state path is not a safe directory: $state_dir"
    owner="$(stat -c '%u' "$state_dir" 2>/dev/null)" \
        || die "could not inspect Pleb desktop state directory: $state_dir"
    [ "$owner" = "$TARGET_UID" ] \
        || die "Pleb desktop state directory is not owned by $TARGET_USER: $state_dir"

    # Write to a user-owned temporary inode, fsync it, then link it into place.
    # link(2) is an atomic create-if-absent: a concurrent first desktop launch or
    # user choice wins, and this provisioner never overwrites it.
    if as_user python3 - "$state_dir" "$state_path" "$wallpaper" <<'PY'
import json
import os
import sys
import tempfile

state_dir, state_path, wallpaper = sys.argv[1:]
fd, temporary = tempfile.mkstemp(prefix=".state.json.plebian-os.", dir=state_dir)
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump({
            "wall_image": wallpaper,
            "wall_mode": "stretch",
            "wall_custom": True,
        }, stream, indent=1)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.link(temporary, state_path, follow_symlinks=False)
    except FileExistsError:
        raise SystemExit(17)
finally:
    try:
        os.unlink(temporary)
    except FileNotFoundError:
        pass
PY
    then
        log "new Kilix desktop will use $wallpaper"
    else
        rc=$?
        [ "$rc" = 17 ] \
            || die "could not seed Pleb desktop wallpaper state"
        log "Pleb desktop state appeared concurrently; preserving it"
    fi
}

install_quiet_console_defaults() {
    local conf=/etc/systemd/system.conf.d/50-plebian-os-quiet-console.conf
    log "disabling systemd console status spam -> $conf"
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + write $conf (ShowStatus=no)"
        return
    fi
    mkdir -p "$(dirname "$conf")"
    cat > "$conf" <<'EOF'
# Managed by plebian-os-provision. Keep boot/login scope status lines off tty1.
[Manager]
ShowStatus=no
EOF
}

_apt_source_path_allowed() {
    case "$1" in
        "$APT_ETC_ROOT/apt/sources.list"|\
        "$APT_ETC_ROOT/apt/sources.list.d/"*.list|\
        "$APT_ETC_ROOT/apt/sources.list.d/"*.sources) return 0 ;;
        *) return 1 ;;
    esac
}

_load_apt_snapshot_inventory() {
    local inventory="$1" out_name="$2" path
    local -A seen=()
    # shellcheck disable=SC2178  # nameref intentionally targets an array
    local -n out="$out_name"
    out=()
    [ -f "$inventory" ] || return 0
    while IFS= read -r path || [ -n "$path" ]; do
        [ -n "$path" ] || die "corrupt empty path in apt snapshot inventory: $inventory"
        _apt_source_path_allowed "$path" \
            || die "unsafe path in apt snapshot inventory: $path"
        case "$path" in *$'\n'*|*$'\r'*) die "invalid newline in apt snapshot inventory path" ;; esac
        if [ -n "${seen[$path]+x}" ]; then
            die "duplicate path in apt snapshot inventory: $path"
        fi
        seen["$path"]=1
        out+=("$path")
    done < "$inventory"
}

_discover_legacy_apt_snapshot_inventory() {
    local out_name="$1" backup live
    # shellcheck disable=SC2178  # nameref intentionally targets an array
    local -n out="$out_name"
    local -a backups
    shopt -s nullglob
    backups=(
        "$APT_ETC_ROOT/apt/sources.list.plebian-os-disabled"
        "$APT_ETC_ROOT/apt/sources.list.d/"*.plebian-os-disabled
    )
    shopt -u nullglob
    for backup in "${backups[@]}"; do
        [ -e "$backup" ] || [ -L "$backup" ] || continue
        live="${backup%.plebian-os-disabled}"
        case "$live" in *$'\n'*|*$'\r'*) die "invalid newline in legacy apt source path" ;; esac
        _apt_source_path_allowed "$live" \
            || die "unsafe legacy apt snapshot backup path: $backup"
        out+=("$live")
    done
}

_active_apt_source_paths() {
    local managed="$1" out_name="$2" path
    # shellcheck disable=SC2178  # nameref intentionally targets an array
    local -n out="$out_name"
    local -a candidates
    out=()
    shopt -s nullglob
    candidates=(
        "$APT_ETC_ROOT/apt/sources.list"
        "$APT_ETC_ROOT/apt/sources.list.d/"*.list
        "$APT_ETC_ROOT/apt/sources.list.d/"*.sources
    )
    shopt -u nullglob
    for path in "${candidates[@]}"; do
        [ "$path" = "$managed" ] && continue
        [ -f "$path" ] || [ -L "$path" ] || continue
        case "$path" in *$'\n'*|*$'\r'*) die "invalid newline in apt source path" ;; esac
        out+=("$path")
    done
}

_restore_managed_apt_file() {
    local path="$1" backup="$2" existed="$3"
    rm -f "$path" 2>/dev/null || true
    if [ "$existed" = 1 ]; then
        cp -a "$backup" "$path" 2>/dev/null || return 1
    fi
}

restore_live_apt_sources() {
    local apt_dir="$APT_ETC_ROOT/apt" state_dir="$APT_ETC_ROOT/plebian-os"
    local src="$APT_ETC_ROOT/apt/sources.list.d/plebian-os-snapshot.sources"
    local cfg="$APT_ETC_ROOT/apt/apt.conf.d/99plebian-os-snapshot"
    local marker="$state_dir/apt-snapshot" inventory="$state_dir/apt-snapshot-sources"
    local live backup txn codename live_tmp failed=0 rollback_ok=1 signal_rc=0
    local src_old=0 cfg_old=0 marker_old=0 inventory_old=0
    local -a managed=() restored=() active=()
    log "apt snapshot disabled; restoring the exact sources disabled by Plebian-OS"
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + preflight $inventory and every managed backup before changing apt"
        echo "    + restore exactly the inventoried *.plebian-os-disabled sources, then remove only Plebian-OS snapshot files"
        return 0
    fi
    case "$APT_ETC_ROOT" in /*) ;; *) die "PLEBIAN_OS_APT_ETC_ROOT must be absolute" ;; esac
    mkdir -p "$apt_dir/sources.list.d" "$apt_dir/apt.conf.d" "$state_dir"
    _load_apt_snapshot_inventory "$inventory" managed
    if [ "${#managed[@]}" -eq 0 ] && [ ! -f "$inventory" ]; then
        # Migrate machines configured by the pre-inventory implementation. The
        # suffix was private to this provisioner, so these are its backups.
        _discover_legacy_apt_snapshot_inventory managed
    fi

    # Complete conflict validation happens before the first rename. Never guess
    # whether a newly recreated live file or a backup should win.
    for live in "${managed[@]}"; do
        backup="$live.plebian-os-disabled"
        { [ -e "$backup" ] || [ -L "$backup" ]; } \
            || die "apt snapshot inventory names a missing backup: $backup"
        if [ -e "$live" ] || [ -L "$live" ]; then
            die "cannot restore apt sources safely: both $live and $backup exist"
        fi
    done

    txn="$(mktemp -d "$state_dir/.apt-restore.XXXXXX")" \
        || die "could not create apt restore transaction directory"
    if [ -e "$src" ] || [ -L "$src" ]; then cp -a "$src" "$txn/src"; src_old=1; fi
    if [ -e "$cfg" ] || [ -L "$cfg" ]; then cp -a "$cfg" "$txn/cfg"; cfg_old=1; fi
    if [ -e "$marker" ] || [ -L "$marker" ]; then cp -a "$marker" "$txn/marker"; marker_old=1; fi
    if [ -e "$inventory" ] || [ -L "$inventory" ]; then cp -a "$inventory" "$txn/inventory"; inventory_old=1; fi

    # Defer termination only across the mutation window so every signal takes
    # the same rollback path as an ordinary command failure.
    trap 'signal_rc=143' INT TERM HUP
    for live in "${managed[@]}"; do
        if [ "$failed" != 0 ] || [ "$signal_rc" != 0 ]; then failed=1; break; fi
        backup="$live.plebian-os-disabled"
        if mv -T "$backup" "$live"; then
            restored+=("$live")
        else
            failed=1
            break
        fi
    done
    if [ "$failed" = 0 ]; then
        rm -f "$src" "$cfg" "$marker" "$inventory" || failed=1
    fi
    [ "$signal_rc" = 0 ] || failed=1
    if [ "$failed" != 0 ]; then
        for ((i=${#restored[@]}-1; i>=0; i--)); do
            live="${restored[$i]}"
            mv -T "$live" "$live.plebian-os-disabled" 2>/dev/null || rollback_ok=0
        done
        _restore_managed_apt_file "$src" "$txn/src" "$src_old" || rollback_ok=0
        _restore_managed_apt_file "$cfg" "$txn/cfg" "$cfg_old" || rollback_ok=0
        _restore_managed_apt_file "$marker" "$txn/marker" "$marker_old" || rollback_ok=0
        _restore_managed_apt_file "$inventory" "$txn/inventory" "$inventory_old" || rollback_ok=0
        if [ "$rollback_ok" = 1 ]; then
            rm -rf "$txn"
            restore_provision_signal_traps
            [ "$signal_rc" = 0 ] || exit "$signal_rc"
            die "apt source restoration failed; the previous snapshot configuration was restored"
        fi
        restore_provision_signal_traps
        die "apt source restoration and rollback were incomplete; recovery files remain at $txn"
    fi
    rm -rf "$txn"
    restore_provision_signal_traps
    [ "$signal_rc" = 0 ] || exit "$signal_rc"

    _active_apt_source_paths "$src" active
    if [ "${#active[@]}" -eq 0 ]; then
        codename="$(. /etc/os-release 2>/dev/null; printf '%s' "${VERSION_CODENAME:-trixie}")"
        live_tmp="$(mktemp "$apt_dir/sources.list.d/.plebian-os-live.XXXXXX")"
        cat > "$live_tmp" <<EOF
# Managed by plebian-os-provision after leaving snapshot mode with no saved source.
Types: deb
URIs: https://deb.debian.org/debian
Suites: $codename ${codename}-updates
Components: main contrib non-free-firmware
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg

Types: deb
URIs: https://security.debian.org/debian-security
Suites: ${codename}-security
Components: main contrib non-free-firmware
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
EOF
        chmod 0644 "$live_tmp"
        mv -fT "$live_tmp" "$apt_dir/sources.list.d/debian.sources"
    fi
}

# Pin apt to a snapshot.debian.org timestamp so the first-boot package closure is
# reproducible. Turning the knob back off actively restores the stock/live
# sources instead of leaving a machine permanently stranded on the snapshot.
configure_apt_snapshot() {
    if [ -z "$PLEBIAN_OS_APT_SNAPSHOT" ]; then
        [ "$PLEBIAN_OS_RELEASE_MODE" = 1 ] \
            && die "release mode requires PLEBIAN_OS_APT_SNAPSHOT; refusing live package drift"
        restore_live_apt_sources
        return 0
    fi
    local ts="$PLEBIAN_OS_APT_SNAPSHOT"
    local apt_dir="$APT_ETC_ROOT/apt" state_dir="$APT_ETC_ROOT/plebian-os"
    local src="$APT_ETC_ROOT/apt/sources.list.d/plebian-os-snapshot.sources"
    local cfg="$APT_ETC_ROOT/apt/apt.conf.d/99plebian-os-snapshot"
    local marker="$state_dir/apt-snapshot" inventory="$state_dir/apt-snapshot-sources"
    [[ "$ts" =~ ^[0-9]{8}(T[0-9]{6}Z)?$ ]] \
        || die "invalid PLEBIAN_OS_APT_SNAPSHOT=$ts (expected YYYYMMDD or YYYYMMDDTHHMMSSZ)"
    log "pinning apt to snapshot.debian.org/$ts (reproducible package closure)"
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + disable stock apt sources (sources.list, sources.list.d/debian.sources)"
        echo "    + write $src (deb822 snapshot sources for $ts) + $cfg (Check-Valid-Until false)"
        echo "    + apt-get update"
        return 0
    fi
    case "$APT_ETC_ROOT" in /*) ;; *) die "PLEBIAN_OS_APT_ETC_ROOT must be absolute" ;; esac
    mkdir -p "$apt_dir/sources.list.d" "$apt_dir/apt.conf.d" "$state_dir"
    # Inventory every source this provisioner disables. Existing inventories are
    # extended when an operator adds a source while snapshot mode is active.
    local d backup txn src_tmp cfg_tmp marker_tmp inventory_tmp failed=0 rollback_ok=1 signal_rc=0
    local src_old=0 cfg_old=0 marker_old=0 inventory_old=0
    local -a managed=() active=() moved=() combined=()
    _load_apt_snapshot_inventory "$inventory" managed
    if [ "${#managed[@]}" -eq 0 ] && [ ! -f "$inventory" ]; then
        _discover_legacy_apt_snapshot_inventory managed
    fi
    for d in "${managed[@]}"; do
        backup="$d.plebian-os-disabled"
        { [ -e "$backup" ] || [ -L "$backup" ]; } \
            || die "apt snapshot inventory names a missing backup: $backup"
        if [ -e "$d" ] || [ -L "$d" ]; then
            die "cannot snapshot apt safely: both $d and its Plebian-OS backup exist"
        fi
        combined+=("$d")
    done
    _active_apt_source_paths "$src" active
    for d in "${active[@]}"; do
        backup="$d.plebian-os-disabled"
        if [ -e "$backup" ] || [ -L "$backup" ]; then
            die "cannot snapshot apt safely: both $d and its Plebian-OS backup exist"
        fi
        combined+=("$d")
    done

    txn="$(mktemp -d "$state_dir/.apt-enable.XXXXXX")" \
        || die "could not create apt snapshot transaction directory"
    src_tmp="$(mktemp "$apt_dir/sources.list.d/.plebian-os-snapshot.XXXXXX")"
    cat > "$src_tmp" <<EOF
# Managed by plebian-os-provision. Reproducible apt via snapshot.debian.org.
Types: deb
URIs: https://snapshot.debian.org/archive/debian/$ts
Suites: trixie trixie-updates
Components: main contrib non-free-firmware
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg

Types: deb
URIs: https://snapshot.debian.org/archive/debian-security/$ts
Suites: trixie-security
Components: main contrib non-free-firmware
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
EOF
    # snapshot archives carry an old Valid-Until, which apt would otherwise reject.
    cfg_tmp="$(mktemp "$apt_dir/apt.conf.d/.plebian-os-snapshot.XXXXXX")"
    marker_tmp="$(mktemp "$state_dir/.apt-snapshot.XXXXXX")"
    inventory_tmp="$(mktemp "$state_dir/.apt-snapshot-sources.XXXXXX")"
    printf '%s\n' 'Acquire::Check-Valid-Until "false";' > "$cfg_tmp"
    printf '%s\n' "$ts" > "$marker_tmp"
    : > "$inventory_tmp"
    if [ "${#combined[@]}" -gt 0 ]; then
        printf '%s\n' "${combined[@]}" > "$inventory_tmp"
    fi
    chmod 0644 "$src_tmp" "$cfg_tmp" "$marker_tmp"
    chmod 0600 "$inventory_tmp"
    if [ -e "$src" ] || [ -L "$src" ]; then cp -a "$src" "$txn/src"; src_old=1; fi
    if [ -e "$cfg" ] || [ -L "$cfg" ]; then cp -a "$cfg" "$txn/cfg"; cfg_old=1; fi
    if [ -e "$marker" ] || [ -L "$marker" ]; then cp -a "$marker" "$txn/marker"; marker_old=1; fi
    if [ -e "$inventory" ] || [ -L "$inventory" ]; then cp -a "$inventory" "$txn/inventory"; inventory_old=1; fi

    # Once source renames begin, defer signals into the explicit rollback path.
    trap 'signal_rc=143' INT TERM HUP
    for d in "${active[@]}"; do
        if [ "$signal_rc" != 0 ]; then failed=1; break; fi
        if mv -T "$d" "$d.plebian-os-disabled"; then
            moved+=("$d")
        else
            failed=1
            break
        fi
    done
    if [ "$failed" = 0 ] && [ "$signal_rc" = 0 ]; then mv -fT "$src_tmp" "$src" || failed=1; fi
    if [ "$failed" = 0 ] && [ "$signal_rc" = 0 ]; then mv -fT "$cfg_tmp" "$cfg" || failed=1; fi
    if [ "$failed" = 0 ] && [ "$signal_rc" = 0 ]; then mv -fT "$marker_tmp" "$marker" || failed=1; fi
    if [ "$failed" = 0 ] && [ "$signal_rc" = 0 ]; then mv -fT "$inventory_tmp" "$inventory" || failed=1; fi
    if [ "$failed" = 0 ] && [ "$signal_rc" = 0 ] && ! apt-get update -y; then failed=1; fi
    [ "$signal_rc" = 0 ] || failed=1
    if [ "$failed" != 0 ]; then
        _restore_managed_apt_file "$src" "$txn/src" "$src_old" || rollback_ok=0
        _restore_managed_apt_file "$cfg" "$txn/cfg" "$cfg_old" || rollback_ok=0
        _restore_managed_apt_file "$marker" "$txn/marker" "$marker_old" || rollback_ok=0
        _restore_managed_apt_file "$inventory" "$txn/inventory" "$inventory_old" || rollback_ok=0
        for ((i=${#moved[@]}-1; i>=0; i--)); do
            d="${moved[$i]}"
            mv -T "$d.plebian-os-disabled" "$d" 2>/dev/null || rollback_ok=0
        done
        rm -f "$src_tmp" "$cfg_tmp" "$marker_tmp" "$inventory_tmp"
        if [ "$rollback_ok" = 1 ]; then
            rm -rf "$txn"
            restore_provision_signal_traps
            [ "$signal_rc" = 0 ] || exit "$signal_rc"
            die "apt-get update against snapshot $ts failed; restored the previous apt configuration; refusing an unpinned/stale package closure"
        fi
        restore_provision_signal_traps
        die "apt snapshot activation and rollback were incomplete; recovery files remain at $txn"
    fi
    rm -rf "$txn"
    restore_provision_signal_traps
    [ "$signal_rc" = 0 ] || exit "$signal_rc"
}

# Record the exact final installed package set for provenance. This is called
# only after pleb, Go, Kilix, and all system configuration steps have completed.
write_package_manifest() {
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + record installed packages -> /var/lib/plebian-os/packages.list"
        return 0
    fi
    command -v dpkg-query >/dev/null 2>&1 \
        || die "dpkg-query is unavailable; cannot record final package provenance"
    mkdir -p /var/lib/plebian-os
    local tmp
    tmp="$(mktemp /var/lib/plebian-os/.packages.list.XXXXXX)"
    dpkg-query -W -f='${Package}=${Version}\n' 2>/dev/null | sort > "$tmp" \
        || { rm -f "$tmp"; die "could not record final installed package set"; }
    chmod 0644 "$tmp"
    mv -fT "$tmp" /var/lib/plebian-os/packages.list
}

provenance_kv() {
    printf '%s=%q\n' "$1" "$2"
}

validate_component_versions() {
    local pleb_version="$1" kilix_version="$2" kilix95_version="$3"
    [ "$pleb_version" = "pleb $PLEBIAN_OS_VERSION" ] \
        || die "pleb reports '$pleb_version', expected exactly 'pleb $PLEBIAN_OS_VERSION'"
    [ "$kilix_version" = "$PLEBIAN_OS_VERSION" ] \
        || die "kilix reports '$kilix_version', expected exactly '$PLEBIAN_OS_VERSION'"
    [ "$kilix95_version" = "kilix-95 $PLEBIAN_OS_VERSION" ] \
        || die "kilix 95 reports '$kilix95_version', expected exactly 'kilix-95 $PLEBIAN_OS_VERSION'"
}

write_source_tool_manifest() {
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + record resolved source commits, apt indexes, and tool versions -> /var/lib/plebian-os/{versions.env,apt-sources.list}"
        return 0
    fi
    local state=/var/lib/plebian-os versions_tmp sources_tmp
    local plebian_os_commit pleb_commit kilix_commit kilix_source_commit kilix95_commit
    local pleb_version kilix_version kilix95_version go_version engine engine_version uv_version
    mkdir -p "$state"
    versions_tmp="$(mktemp "$state/.versions.env.XXXXXX")"
    sources_tmp="$(mktemp "$state/.apt-sources.list.XXXXXX")"

    plebian_os_commit="$(as_user git -C "$PLEBIAN_OS_DIR" rev-parse HEAD 2>/dev/null || true)"
    pleb_commit="$(as_user git -C "$PLEB_DIR" rev-parse HEAD 2>/dev/null || true)"
    kilix_commit="$(as_user git -C "$KILIX_DIR" rev-parse HEAD 2>/dev/null || true)"
    kilix_source_commit="$(as_user git -C "$KILIX_DIR/src" rev-parse HEAD 2>/dev/null || true)"
    kilix95_commit="$(as_user git -C "$KILIX95_DIR" rev-parse HEAD 2>/dev/null || true)"
    pleb_version="$(as_user env "${install_env[@]}" "$PLEB_DIR/bin/pleb" --version 2>/dev/null || true)"
    kilix_version="$(as_user env "${install_env[@]}" "$KILIX_DIR/kilix" --kilix-version 2>/dev/null || true)"
    if [ -f "$KILIX95_DIR/main.py" ]; then
        kilix95_version="$(as_user env "${install_env[@]}" python3 "$KILIX95_DIR/main.py" --version 2>/dev/null || true)"
    else
        kilix95_version=""
    fi
    go_version="$(as_user bash -lc 'go version' 2>/dev/null || true)"
    uv_version="$(/usr/local/bin/uv --version 2>/dev/null || true)"
    engine="$(as_user env "${install_env[@]}" "$KILIX_DIR/kilix" --which 2>/dev/null | head -1 || true)"
    if [ -n "$engine" ] && [ -x "$engine" ]; then
        engine_version="$(as_user env "${install_env[@]}" "$engine" --version 2>/dev/null | head -1 || true)"
    else
        engine_version=""
    fi

    {
        echo "# Final resolved Plebian-OS source/tool provenance."
        provenance_kv PLEBIAN_OS_VERSION "$PLEBIAN_OS_VERSION"
        provenance_kv PLEBIAN_OS_RELEASE "$PLEBIAN_OS_RELEASE"
        provenance_kv PLEBIAN_OS_RELEASE_MODE "$PLEBIAN_OS_RELEASE_MODE"
        provenance_kv PLEBIAN_OS_APT_SNAPSHOT "$PLEBIAN_OS_APT_SNAPSHOT"
        provenance_kv GPU_TERMINAL_SOURCE_HOME "$GPU_TERMINAL_SOURCE_HOME"
        provenance_kv GPU_TERMINAL_HOME "$GPU_TERMINAL_HOME"
        provenance_kv PLEBIAN_OS_REPO "$PLEBIAN_OS_REPO"
        provenance_kv PLEBIAN_OS_BRANCH "$PLEBIAN_OS_BRANCH"
        provenance_kv PLEBIAN_OS_REF "$PLEBIAN_OS_REF"
        provenance_kv PLEBIAN_OS_COMMIT "$plebian_os_commit"
        provenance_kv PLEBIAN_OS_DIR "$PLEBIAN_OS_DIR"
        provenance_kv PLEBIAN_OS_STORAGE_HOME "$PLEBIAN_OS_STORAGE_HOME"
        provenance_kv PLEBIAN_OS_SESSION_HOME "$PLEBIAN_OS_SESSION_HOME"
        provenance_kv PLEB_DIR "$PLEB_DIR"
        provenance_kv PLEB_STORAGE_HOME "$PLEB_STORAGE_HOME"
        provenance_kv PLEB_CONFIG_HOME "$PLEB_CONFIG_HOME"
        provenance_kv PLEB_STATE_HOME "$PLEB_STATE_HOME"
        provenance_kv PLEB_CACHE_HOME "$PLEB_CACHE_HOME"
        provenance_kv PLEB_SESSION_HOME "$PLEB_SESSION_HOME"
        provenance_kv PLEB_DATA_HOME "$PLEB_DATA_HOME"
        provenance_kv PLEB_REF "$PLEB_REF"
        provenance_kv PLEB_COMMIT "$pleb_commit"
        provenance_kv PLEB_VERSION "$pleb_version"
        provenance_kv KILIX_REF "$KILIX_REF"
        provenance_kv KILIX_DIR "$KILIX_DIR"
        provenance_kv KILIX_STORAGE_HOME "$KILIX_STORAGE_HOME"
        provenance_kv KILIX_CONFIG_HOME "$KILIX_CONFIG_HOME"
        provenance_kv KILIX_STATE_DIRECTORY "$KILIX_STATE_DIRECTORY"
        provenance_kv KILIX_CACHE_HOME "$KILIX_CACHE_HOME"
        provenance_kv KILIX_SESSION_HOME "$KILIX_SESSION_HOME"
        provenance_kv KILIX_BUILD_DIRECTORY "$KILIX_BUILD_DIRECTORY"
        provenance_kv KILIX_DATA_HOME "$KILIX_DATA_HOME"
        provenance_kv KILIX_DESKTOP_DIR "$KILIX_DESKTOP_DIR"
        provenance_kv KILIX_PREBUILT_HOME "$KILIX_PREBUILT_HOME"
        provenance_kv KILIX_COMMIT "$kilix_commit"
        provenance_kv KILIX_SOURCE_COMMIT "$kilix_source_commit"
        provenance_kv KILIX_VERSION "$kilix_version"
        provenance_kv KILIX_ENGINE "$engine"
        provenance_kv KILIX_ENGINE_VERSION "$engine_version"
        provenance_kv KILIX95_REF "$KILIX95_REF"
        provenance_kv KILIX95_DIR "$KILIX95_DIR"
        provenance_kv KILIX95_STORAGE_HOME "$KILIX95_STORAGE_HOME"
        provenance_kv KILIX95_CONFIG_HOME "$KILIX95_CONFIG_HOME"
        provenance_kv KILIX95_STATE_HOME "$KILIX95_STATE_HOME"
        provenance_kv KILIX95_CACHE_HOME "$KILIX95_CACHE_HOME"
        provenance_kv KILIX95_SESSION_HOME "$KILIX95_SESSION_HOME"
        provenance_kv KILIX95_DATA_HOME "$KILIX95_DATA_HOME"
        provenance_kv KILIX95_COMMIT "$kilix95_commit"
        provenance_kv KILIX95_VERSION "$kilix95_version"
        provenance_kv PLEBIAN_OS_KILIX_GO_VERSION "$KILIX_GO_VERSION"
        provenance_kv PLEBIAN_OS_KILIX_GO_SHA256_AMD64 "$KILIX_GO_SHA256_AMD64"
        provenance_kv PLEBIAN_OS_KILIX_GO_SHA256_ARM64 "$KILIX_GO_SHA256_ARM64"
        provenance_kv GO_VERSION "$go_version"
        provenance_kv PLEBIAN_OS_INSTALL_UV "$INSTALL_UV"
        provenance_kv PLEBIAN_OS_UV_VERSION "$UV_VERSION_PIN"
        provenance_kv PLEBIAN_OS_UV_INSTALLER_SHA256 "$UV_INSTALLER_SHA256"
        provenance_kv UV_VERSION "$uv_version"
        provenance_kv GIT_VERSION "$(git --version 2>/dev/null || true)"
        provenance_kv PYTHON3_VERSION "$(python3 --version 2>&1 || true)"
        provenance_kv KERNEL_VERSION "$(uname -srmo 2>/dev/null || true)"
    } > "$versions_tmp"

    apt-get indextargets \
        --format '$(SITE) $(RELEASE) $(COMPONENT) $(ARCHITECTURE)' 2>/dev/null \
        | sed '/^[[:space:]]*$/d' | sort -u > "$sources_tmp" \
        || { rm -f "$versions_tmp" "$sources_tmp"; die "could not record final apt source indexes"; }
    if [ "$PLEBIAN_OS_RELEASE_MODE" = 1 ]; then
        [ -s "$sources_tmp" ] || die "release apt index provenance is empty"
        if grep -v 'snapshot\.debian\.org' "$sources_tmp" | grep -q .; then
            rm -f "$versions_tmp" "$sources_tmp"
            die "release apt provenance contains a non-snapshot index"
        fi
        [ "$plebian_os_commit" = "${PLEBIAN_OS_REF,,}" ] \
            || die "resolved plebian-os commit $plebian_os_commit does not match PLEBIAN_OS_REF=$PLEBIAN_OS_REF"
        [ "$pleb_commit" = "${PLEB_REF,,}" ] \
            || die "resolved pleb commit $pleb_commit does not match PLEB_REF=$PLEB_REF"
        [ "$kilix_commit" = "${KILIX_REF,,}" ] \
            || die "resolved kilix commit $kilix_commit does not match KILIX_REF=$KILIX_REF"
        [ "$kilix95_commit" = "${KILIX95_REF,,}" ] \
            || die "resolved kilix 95 commit $kilix95_commit does not match KILIX95_REF=$KILIX95_REF"
        validate_component_versions "$pleb_version" "$kilix_version" "$kilix95_version"
        if [ "$INSTALL_UV" = 1 ]; then
            [ "$uv_version" = "uv $UV_VERSION_PIN" ] \
                || die "release uv provenance mismatch: expected 'uv $UV_VERSION_PIN', got '${uv_version:-<missing>}'"
        fi
    fi
    chmod 0644 "$versions_tmp" "$sources_tmp"
    mv -fT "$versions_tmp" "$state/versions.env"
    mv -fT "$sources_tmp" "$state/apt-sources.list"
}

# Kiosk appliance: pin the target user's remembered LightDM session to Pleb so a
# stale ~/.dmrc / AccountsService entry can't override the seat's user-session
# default. Only done in kiosk mode (a dedicated appliance); a bootstrap install
# alongside another desktop leaves the user's session choice alone.
pin_remembered_session() {
    local dmrc="$USER_HOME/.dmrc"
    local asvc="/var/lib/AccountsService/users/$TARGET_USER"
    log "pinning $TARGET_USER's remembered session to Pleb (kiosk)"
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + (as $TARGET_USER) atomically replace $dmrc ([Desktop] Session=pleb; do not follow symlinks)"
        echo "    + create $asvc with Session=pleb (if absent)"
        return 0
    fi
    # $USER_HOME is controlled by the target user. Never redirect or chown this
    # path as root: a pre-created ~/.dmrc symlink could otherwise truncate and
    # hand ownership of an arbitrary root file to the user. Create the file as
    # the user and atomically replace the directory entry with `mv -T`, which
    # replaces a symlink itself instead of following it (including dir symlinks).
    as_user bash -c '
set -euo pipefail
dmrc="$1"
tmp="$(mktemp "${dmrc}.tmp.XXXXXX")"
trap '\''rm -f "$tmp"'\'' EXIT
printf '\''%s\n'\'' '\''[Desktop]'\'' '\''Session=pleb'\'' > "$tmp"
chmod 0600 "$tmp"
mv -fT -- "$tmp" "$dmrc"
trap - EXIT
' plebian-os-dmrc-writer "$dmrc" \
        || die "could not safely write $dmrc as $TARGET_USER"
    # Best-effort AccountsService (LightDM prefers it when present). Only create
    # it when absent, so we never clobber an existing profile's other keys.
    if [ ! -e "$asvc" ] && mkdir -p /var/lib/AccountsService/users 2>/dev/null; then
        printf '%s\n' '[User]' 'Session=pleb' 'XSession=pleb' 'SystemAccount=false' > "$asvc"
    fi
}

# Install the narrow password check/change helper (plebian-os-passwd) and a
# SCOPED NOPASSWD sudoers rule for the target user, so the Kilix 95 desktop —
# running unprivileged — can detect the default password ('plebian') and let
# the owner change it, WITHOUT granting general passwordless sudo. The helper
# only ever acts on the invoking user's own account.
install_passwd_nag() {
    local dst=/usr/local/sbin/plebian-os-passwd
    local rule=/etc/sudoers.d/plebian-os-passwd
    local src=""
    for cand in "$SELF_DIR/plebian-os-passwd" "$dst"; do
        [ -r "$cand" ] && src="$cand" && break
    done
    log "installing password-change helper + scoped sudoers for $TARGET_USER"
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + install -m 0755 ${src:-<staged>} $dst"
        echo "    + if $TARGET_USER still uses the shipped password: write $rule (NOPASSWD: $dst)"
        echo "    + otherwise: remove $rule (the one-time transition is no longer needed)"
        return 0
    fi
    if [ -n "$src" ] && [ "$src" != "$dst" ]; then
        install -m 0755 "$src" "$dst" || die "could not install $dst"
    fi
    if [ ! -x "$dst" ]; then
        rm -f "$rule"
        die "plebian-os-passwd helper missing; refusing to leave the shipped password without its transition helper"
    fi
    # The NOPASSWD helper is only safe while it is a one-time transition away
    # from the shipped password. A reprovision after the owner changes the
    # password must remove, not recreate, the grant. Fail closed if the helper
    # cannot determine the shadow state.
    local password_state
    if SUDO_USER="$TARGET_USER" "$dst" check; then
        password_state=default
    else
        case "$?" in
            1) password_state=changed ;;
            *) password_state=unknown ;;
        esac
    fi
    if [ "$password_state" != default ]; then
        rm -f "$rule"
        if [ "$password_state" = changed ]; then
            log "$TARGET_USER no longer uses the shipped password; scoped password-change grant retired"
        else
            warn "could not verify $TARGET_USER's password state; refusing to install $rule"
        fi
        return 0
    fi
    printf '%s ALL=(root) NOPASSWD: %s\n' "$TARGET_USER" "$dst" > "$rule"
    chmod 0440 "$rule"
    visudo -cf "$rule" >/dev/null 2>&1 \
        || { warn "passwd-helper sudoers invalid — removing $rule"; rm -f "$rule"; }
}

desktop_provider_needs_kilix95() {
    case "$KILIX_DESKTOP_PROVIDER" in
        external) return 0 ;;
        auto) [ ! -f "$KILIX_DIR/desktop/main.py" ] ;;
        *) return 1 ;;
    esac
}

validate_checkout() {
    local dir="$1" repo="$2" name="$3" remote
    [ -d "$dir" ] && [ ! -L "$dir" ] \
        || die "$name checkout is not a safe directory: $dir"
    if [ -L "$dir/.git" ] \
        || { [ ! -d "$dir/.git" ] && [ ! -f "$dir/.git" ]; }; then
        die "$name path is not a safe git checkout: $dir"
    fi
    remote="$(as_target_readonly git -C "$dir" config --get remote.origin.url 2>/dev/null)" \
        || die "could not validate $name checkout origin at $dir"
    if [ "$remote" != "$repo" ] \
        && [ "${PLEBIAN_OS_TRUST_EXISTING_CHECKOUT:-0}" != 1 ]; then
        die "$name checkout at $dir has origin '$remote', expected '$repo' (set PLEBIAN_OS_TRUST_EXISTING_CHECKOUT=1 to override)"
    fi
}

require_clean_pinned_checkout() {
    local dir="$1" name="$2" dirty
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + verify pinned $name checkout has no tracked/index changes: $dir"
        return 0
    fi
    dirty="$(as_user git -C "$dir" status --porcelain --untracked-files=normal 2>/dev/null)" \
        || die "could not inspect pinned $name checkout at $dir"
    [ -z "$dirty" ] \
        || die "pinned $name checkout at $dir has local changes; refusing to overwrite or execute it"
}

checkout_pinned_ref() {
    local dir="$1" ref="$2" name="$3" resolved actual
    require_clean_pinned_checkout "$dir" "$name"
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + fetch and verify pinned $name ref $ref from origin"
        return 0
    fi
    # Resolve the ref from this fetch's FETCH_HEAD, not a potentially stale or
    # attacker-created local tag. Then verify checkout HEAD is exactly that commit.
    as_user git -C "$dir" fetch --force origin "$ref" \
        || die "$name fetch of pinned ref $ref failed"
    resolved="$(as_user git -C "$dir" rev-parse --verify 'FETCH_HEAD^{commit}' 2>/dev/null)" \
        || die "pinned $name ref $ref did not resolve to a commit"
    as_user git -C "$dir" checkout --detach "$resolved" \
        || die "could not check out pinned $name ref $ref ($resolved)"
    actual="$(as_user git -C "$dir" rev-parse --verify HEAD 2>/dev/null)" \
        || die "could not verify pinned $name checkout HEAD"
    [ "$actual" = "$resolved" ] \
        || die "pinned $name checkout resolved to $resolved but HEAD is $actual"
    require_clean_pinned_checkout "$dir" "$name"
    log "$name pinned ref $ref verified at $actual"
}

ensure_plebian_os_checkout() {
    local clone_args=()
    if [ -d "$PLEBIAN_OS_DIR/.git" ]; then
        log "plebian-os source present at $PLEBIAN_OS_DIR"
        validate_checkout "$PLEBIAN_OS_DIR" "$PLEBIAN_OS_REPO" "plebian-os"
        if [ -n "$PLEBIAN_OS_REF" ]; then
            checkout_pinned_ref "$PLEBIAN_OS_DIR" "$PLEBIAN_OS_REF" "plebian-os"
        fi
        return 0
    fi
    [ ! -e "$PLEBIAN_OS_DIR" ] && [ ! -L "$PLEBIAN_OS_DIR" ] \
        || die "plebian-os source path exists but is not a git checkout: $PLEBIAN_OS_DIR"

    log "cloning plebian-os source -> $PLEBIAN_OS_DIR"
    [ -n "$PLEBIAN_OS_BRANCH" ] && clone_args=(--branch "$PLEBIAN_OS_BRANCH")
    as_user git clone "${clone_args[@]}" "$PLEBIAN_OS_REPO" "$PLEBIAN_OS_DIR" \
        || die "git clone of plebian-os failed ($PLEBIAN_OS_REPO)"
    if [ -n "$PLEBIAN_OS_REF" ]; then
        checkout_pinned_ref "$PLEBIAN_OS_DIR" "$PLEBIAN_OS_REF" "plebian-os"
    fi
}

update_pleb_checkout() {
    validate_checkout "$PLEB_DIR" "$PLEB_REPO" "pleb"
    if [ -n "$PLEB_REF" ]; then
        checkout_pinned_ref "$PLEB_DIR" "$PLEB_REF" "pleb"
        return
    fi

    if [ -n "$PLEB_BRANCH" ]; then
        as_user git -C "$PLEB_DIR" fetch --prune origin "$PLEB_BRANCH" \
            || die "pleb fetch failed"
        current="$(as_target_readonly git -C "$PLEB_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo HEAD)"
        if [ "$current" != "$PLEB_BRANCH" ]; then
            if as_target_readonly git -C "$PLEB_DIR" show-ref --verify --quiet "refs/heads/$PLEB_BRANCH"; then
                as_user git -C "$PLEB_DIR" checkout "$PLEB_BRANCH" \
                    || die "could not check out PLEB_BRANCH=$PLEB_BRANCH"
            else
                as_user git -C "$PLEB_DIR" checkout --track -b "$PLEB_BRANCH" "origin/$PLEB_BRANCH" \
                    || die "could not track PLEB_BRANCH=$PLEB_BRANCH"
            fi
        fi
        as_user git -C "$PLEB_DIR" merge --ff-only "origin/$PLEB_BRANCH" \
            || die "pleb branch $PLEB_BRANCH cannot fast-forward"
        return
    fi

    as_user git -C "$PLEB_DIR" pull --ff-only || die "pleb pull failed"
}

kilix_go_ok_script() {
    cat <<'EOF'
command -v go >/dev/null 2>&1 || exit 1
min="${PLEBIAN_OS_KILIX_GO_MIN_VERSION:-1.26}"
exact="${PLEBIAN_OS_KILIX_GO_VERSION:-}"
ver="$(go version 2>/dev/null | awk '{print $3}' | sed 's/^go//')"
[ -n "$ver" ] || exit 1
if [ -n "$exact" ]; then
    exact="${exact#go}"
    [ "$ver" = "$exact" ] || exit 1
fi
awk -v have="$ver" -v min="$min" '
function splitver(v, out) {
    gsub(/[^0-9.].*$/, "", v)
    n = split(v, parts, ".")
    out[1] = (n >= 1 && parts[1] != "") ? parts[1] + 0 : 0
    out[2] = (n >= 2 && parts[2] != "") ? parts[2] + 0 : 0
    out[3] = (n >= 3 && parts[3] != "") ? parts[3] + 0 : 0
}
BEGIN {
    splitver(have, h)
    splitver(min, m)
    for (i = 1; i <= 3; i++) {
        if (h[i] > m[i]) exit 0
        if (h[i] < m[i]) exit 1
    }
    exit 0
}'
EOF
}

pinned_go_provenance_ok() {
    local arch="$1" sha="${2,,}" root=/usr/local/go stamp version path owner mode
    local -a provenance=()
    stamp="$root/.pleb-source"
    [ -d "$root" ] && [ ! -L "$root" ] \
        && [ -f "$stamp" ] && [ ! -L "$stamp" ] \
        && [ -x "$root/bin/go" ] && [ ! -L "$root/bin/go" ] \
        || return 1
    for path in "$root" "$stamp" "$root/bin/go"; do
        owner="$(stat -c '%u' "$path" 2>/dev/null)" || return 1
        mode="$(stat -c '%a' "$path" 2>/dev/null)" || return 1
        [ "$owner" = 0 ] || return 1
        (( (8#$mode & 8#22) == 0 )) || return 1
    done
    mapfile -t provenance < "$stamp" || return 1
    [ "${#provenance[@]}" -eq 3 ] \
        && [ "${provenance[0]}" = "go${KILIX_GO_VERSION#go}" ] \
        && [ "${provenance[1]}" = "$arch" ] \
        && [ "${provenance[2],,}" = "$sha" ] \
        || return 1
    version="$($root/bin/go version 2>/dev/null)" || return 1
    [ "$version" = "go version go${KILIX_GO_VERSION#go} linux/$arch" ] || return 1
    path="$(as_user bash -lc 'command -v go' 2>/dev/null)" || return 1
    [ "$(readlink -f "$path" 2>/dev/null)" = "$root/bin/go" ] || return 1
}

ensure_go_for_kilix_build() {
    local arch sha="" version_ok=0
    case "$(uname -m)" in
        x86_64|amd64) arch=amd64; sha="$KILIX_GO_SHA256_AMD64" ;;
        aarch64|arm64) arch=arm64; sha="$KILIX_GO_SHA256_ARM64" ;;
        *) die "unsupported architecture for Go toolchain: $(uname -m)" ;;
    esac
    if [ -n "$KILIX_GO_VERSION" ]; then
        [ -n "$sha" ] \
            || die "PLEBIAN_OS_KILIX_GO_VERSION=$KILIX_GO_VERSION requires PLEBIAN_OS_KILIX_GO_SHA256_${arch^^}"
        [[ "$sha" =~ ^[0-9a-fA-F]{64}$ ]] \
            || die "invalid PLEBIAN_OS_KILIX_GO_SHA256_${arch^^} (expected 64 hex characters)"
    elif [ -n "$KILIX_GO_SHA256_AMD64$KILIX_GO_SHA256_ARM64" ]; then
        die "a pinned Go checksum requires PLEBIAN_OS_KILIX_GO_VERSION"
    fi

    log "checking Go toolchain for kilix fork build (>= $KILIX_GO_MIN_VERSION${KILIX_GO_VERSION:+, exactly $KILIX_GO_VERSION with verified archive provenance})"
    if as_user env \
        "PLEBIAN_OS_KILIX_GO_MIN_VERSION=$KILIX_GO_MIN_VERSION" \
        "PLEBIAN_OS_KILIX_GO_VERSION=$KILIX_GO_VERSION" \
        bash -lc "$(kilix_go_ok_script)"; then
        version_ok=1
    fi
    if [ "$version_ok" = 1 ] && [ -z "$KILIX_GO_VERSION" ]; then
        log "Go is ready: $(as_user bash -lc 'go version' 2>/dev/null || true)"
        return 0
    fi
    if [ "$version_ok" = 1 ] && pinned_go_provenance_ok "$arch" "$sha"; then
        log "Go is ready with matching root-owned archive provenance: $(as_user bash -lc 'go version' 2>/dev/null || true)"
        return 0
    fi
    if [ "$version_ok" = 1 ]; then
        warn "Go reports the requested version but its root-owned .pleb-source archive stamp is absent or mismatched; reinstalling"
    fi

    [ -x "$PLEB_DIR/scripts/install-go.sh" ] \
        || die "Go >= $KILIX_GO_MIN_VERSION is required, and $PLEB_DIR/scripts/install-go.sh is missing"
    log "installing/upgrading Go via pleb helper${KILIX_GO_VERSION:+ (pinned $KILIX_GO_VERSION/$arch)}"
    as_user env \
        "GO_VERSION=$KILIX_GO_VERSION" \
        "GO_SHA256=$sha" \
        "$PLEB_DIR/scripts/install-go.sh" all "$KILIX_GO_VERSION" \
        || die "Go toolchain install failed"
    as_user env \
        "PLEBIAN_OS_KILIX_GO_MIN_VERSION=$KILIX_GO_MIN_VERSION" \
        "PLEBIAN_OS_KILIX_GO_VERSION=$KILIX_GO_VERSION" \
        bash -lc "$(kilix_go_ok_script)" \
        || die "Go toolchain does not satisfy the requested min/exact version after install"
    if [ -n "$KILIX_GO_VERSION" ]; then
        pinned_go_provenance_ok "$arch" "$sha" \
            || die "Go toolchain has missing or mismatched root-owned archive provenance after install"
    fi
    log "Go is ready: $(as_user bash -lc 'go version' 2>/dev/null || true)"
}

build_kilix_fork() {
    case "$BUILD_KILIX_FORK" in
        1|yes|true|on) ;;
        0|no|false|off)
            warn "PLEBIAN_OS_BUILD_KILIX_FORK=$BUILD_KILIX_FORK; keeping kilix fallback engine if no fork is present"
            return 0 ;;
        *) die "invalid PLEBIAN_OS_BUILD_KILIX_FORK=$BUILD_KILIX_FORK (expected 0/1)" ;;
    esac

    if [ "$DRY_RUN" = 1 ]; then
        echo "    + (as $TARGET_USER) git -C $KILIX_DIR submodule update --init --recursive"
        echo "    + ensure Go >= $KILIX_GO_MIN_VERSION${KILIX_GO_VERSION:+ (exactly $KILIX_GO_VERSION, sha256-pinned with root-owned .pleb-source stamp)} using $PLEB_DIR/scripts/install-go.sh if needed"
        echo "    + (as $TARGET_USER) $KILIX_DIR/kilix --build"
        echo "    + verify $KILIX_DIR/kilix --which uses $KILIX_BUILD_DIRECTORY/current/src/kitty/launcher/kitty"
        return 0
    fi

    [ -d "$KILIX_DIR/.git" ] || die "kilix checkout missing at $KILIX_DIR after pleb install"
    [ -x "$KILIX_DIR/kilix" ] || die "kilix launcher missing at $KILIX_DIR/kilix"

    log "initializing kilix source submodules"
    as_user git -C "$KILIX_DIR" submodule update --init --recursive \
        || die "kilix submodule initialization failed"

    ensure_go_for_kilix_build

    log "building kilix clickable-chrome fork"
    as_user env "${install_env[@]}" "$KILIX_DIR/kilix" --build \
        || die "kilix fork build failed"

    local fork engine
    fork="$KILIX_BUILD_DIRECTORY/current/src/kitty/launcher/kitty"
    [ -x "$fork" ] || die "kilix fork build did not produce $fork"
    engine="$(as_user env "${install_env[@]}" "$KILIX_DIR/kilix" --which 2>/dev/null | head -1 || true)"
    [ "$engine" = "$fork" ] \
        || die "kilix is not using the fork engine after build (got: ${engine:-<empty>})"
    log "kilix engine verified: $engine"
}

# Tests source the path-agnostic transaction/version helpers without running the
# root provisioning workflow. Normal execution never sets this internal flag.
if [ "${PLEBIAN_OS_PROVISION_LIB_ONLY:-0}" = 1 ]; then
    # shellcheck disable=SC2317  # exit is the direct-execution fallback
    return 0 2>/dev/null || exit 0
fi

# ── args ─────────────────────────────────────────────────────────────────────
while [ $# -gt 0 ]; do
    case "$1" in
        --user)   TARGET_USER="${2:?}"; shift 2 ;;
        --kiosk)  KIOSK=1; shift ;;
        --nopasswd-sudo) NOPASSWD_SUDO=1; shift ;;
        --no-desktop) DESKTOP=0; shift ;;
        --branch) PLEB_BRANCH="${2:?}"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        --version) echo "plebian-os-provision $PLEBIAN_OS_VERSION"; exit 0 ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown option: $1 (see --help)" ;;
    esac
done

validate_release_inputs

[ "$(id -u)" = 0 ] || [ "$DRY_RUN" = 1 ] || die "must run as root (try: sudo $0)"

# ── pick the target user ─────────────────────────────────────────────────────
pick_user() {
    # the account d-i created: lowest uid >= 1000 with a real shell and home
    getent passwd | awk -F: '$3>=1000 && $3<65534 && $7!~/(nologin|false)$/ {print $3":"$1}' \
        | sort -n | head -1 | cut -d: -f2
}
[ -n "$TARGET_USER" ] || TARGET_USER="$(pick_user)"
[ -n "$TARGET_USER" ] || die "no regular user found — create one, or pass --user"
validate_target_user
GPU_TERMINAL_SOURCE_HOME="${GPU_TERMINAL_SOURCE_HOME:-$USER_HOME/gpu_terminal}"
PLEB_DIR="${PLEB_DIR:-$GPU_TERMINAL_SOURCE_HOME/pleb}"
KILIX_DIR="${KILIX_DIR:-$GPU_TERMINAL_SOURCE_HOME/kilix}"
KILIX95_DIR="${KILIX95_DIR:-$GPU_TERMINAL_SOURCE_HOME/kilix-95}"
PLEBIAN_OS_DIR="${PLEBIAN_OS_DIR:-$GPU_TERMINAL_SOURCE_HOME/plebian-os}"
GPU_TERMINAL_HOME="${GPU_TERMINAL_HOME:-$USER_HOME/.local/gpu_terminal}"
PLEB_STORAGE_HOME="${PLEB_STORAGE_HOME:-$GPU_TERMINAL_HOME/pleb}"
PLEB_CONFIG_HOME="${PLEB_CONFIG_HOME:-$PLEB_STORAGE_HOME/config}"
PLEB_STATE_HOME="${PLEB_STATE_HOME:-$PLEB_STORAGE_HOME/state}"
PLEB_CACHE_HOME="${PLEB_CACHE_HOME:-$PLEB_STORAGE_HOME/cache}"
PLEB_SESSION_HOME="${PLEB_SESSION_HOME:-$PLEB_STORAGE_HOME/session}"
PLEB_DATA_HOME="${PLEB_DATA_HOME:-$PLEB_STORAGE_HOME/data}"
KILIX_STORAGE_HOME="${KILIX_STORAGE_HOME:-$GPU_TERMINAL_HOME/kilix}"
KILIX_CONFIG_HOME="${KILIX_CONFIG_HOME:-$KILIX_STORAGE_HOME/config}"
KILIX_STATE_DIRECTORY="${KILIX_STATE_DIRECTORY:-$KILIX_STORAGE_HOME/state}"
KILIX_CACHE_HOME="${KILIX_CACHE_HOME:-$KILIX_STORAGE_HOME/cache}"
KILIX_SESSION_HOME="${KILIX_SESSION_HOME:-$KILIX_STORAGE_HOME/session}"
KILIX_BUILD_DIRECTORY="${KILIX_BUILD_DIRECTORY:-$KILIX_STORAGE_HOME/build}"
KILIX_DATA_HOME="${KILIX_DATA_HOME:-$KILIX_STORAGE_HOME/data}"
KILIX_DESKTOP_DIR="${KILIX_DESKTOP_DIR:-$PLEB_DATA_HOME/desktop}"
KILIX_PREBUILT_HOME="${KILIX_PREBUILT_HOME:-$KILIX_STORAGE_HOME/prebuilt/kitty.app}"
KILIX95_STORAGE_HOME="${KILIX95_STORAGE_HOME:-$GPU_TERMINAL_HOME/kilix-95}"
KILIX95_CONFIG_HOME="${KILIX95_CONFIG_HOME:-$KILIX95_STORAGE_HOME/config}"
KILIX95_STATE_HOME="${KILIX95_STATE_HOME:-$KILIX95_STORAGE_HOME/state}"
KILIX95_CACHE_HOME="${KILIX95_CACHE_HOME:-$KILIX95_STORAGE_HOME/cache}"
KILIX95_SESSION_HOME="${KILIX95_SESSION_HOME:-$KILIX95_STORAGE_HOME/session}"
KILIX95_DATA_HOME="${KILIX95_DATA_HOME:-$KILIX95_STORAGE_HOME/data}"
PLEBIAN_OS_STORAGE_HOME="${PLEBIAN_OS_STORAGE_HOME:-$GPU_TERMINAL_HOME/plebian-os}"
PLEBIAN_OS_SESSION_HOME="${PLEBIAN_OS_SESSION_HOME:-$PLEBIAN_OS_STORAGE_HOME/session}"
export GPU_TERMINAL_SOURCE_HOME GPU_TERMINAL_HOME
export PLEBIAN_OS_STORAGE_HOME PLEBIAN_OS_SESSION_HOME

# Allocate the shared private data tree before even the provision/update lock
# is created.  This prevents the first target-user write from inheriting the
# firstboot service's permissive umask and makes reruns repair older 0755 roots.
allocate_coordinated_private_storage

log "plebian-os  : version $PLEBIAN_OS_VERSION"
log "target user : $TARGET_USER ($USER_HOME)"
log "source root : $GPU_TERMINAL_SOURCE_HOME"
log "data root   : $GPU_TERMINAL_HOME"
log "pleb repo   : $PLEB_REPO ${PLEB_BRANCH:+(branch $PLEB_BRANCH)}"
log "kilix repo  : $KILIX_REPO -> $KILIX_DIR (cloned by pleb)"
if [ "$DESKTOP" = 1 ]; then
    log "desktop    : provider=$KILIX_DESKTOP_PROVIDER name=$KILIX_DESKTOP_NAME"
    if desktop_provider_needs_kilix95; then
        log "kilix 95   : $KILIX95_REPO -> $KILIX95_DIR (cloned by pleb)"
    fi
fi
log "kiosk       : $([ "$KIOSK" = 1 ] && echo 'yes (autologin)' || echo 'no (greeter)')"
log "session     : $([ "$DESKTOP" = 1 ] && echo "kilix desktop ($KILIX_DESKTOP_PROVIDER)" || echo 'plain kilix shell')"

# Hold the same target-user lock used by direct `pleb update` before the first
# provisioning mutation and through final provenance/session reconciliation.
acquire_provision_lock

# ── 1. dependencies ──────────────────────────────────────────────────────────
# Delegated to the standalone installer (install-deps.sh, deployed alongside us
# as plebian-os-install-deps) — the single source of truth for the dep set, and
# runnable on its own to debug a bad dependency. Look for it next to this script
# under either its deployed name or its in-repo name.
DEPS_SCRIPT=""
for cand in \
    "$SELF_DIR/plebian-os-install-deps" \
    "$SELF_DIR/install-deps.sh" \
    /usr/local/sbin/plebian-os-install-deps; do
    [ -r "$cand" ] && DEPS_SCRIPT="$cand" && break
done
[ -n "$DEPS_SCRIPT" ] || die "dependency installer not found (plebian-os-install-deps / install-deps.sh)"
configure_apt_snapshot
log "installing runtime dependencies via $DEPS_SCRIPT"
if [ "$DRY_RUN" = 1 ]; then
    bash "$DEPS_SCRIPT" --dry-run
else
    bash "$DEPS_SCRIPT" || die "dependency install failed (see the group summary above)"
fi
install_no_beep_defaults
install_quiet_console_defaults
install_desktop_wallpaper
install_lightdm_greeter_branding
install_artwork_notices

# The ISO path stages plebian-os-update via preseed late_command. The bootstrap
# path runs this provisioner directly from the checkout, so install the same
# helper here when the source file is available.
UPDATE_SRC=""
for cand in \
    "$SELF_DIR/plebian-os-update.sh" \
    "$SELF_DIR/plebian-os-update"; do
    [ -r "$cand" ] && UPDATE_SRC="$cand" && break
done
if [ -n "$UPDATE_SRC" ]; then
    log "installing update helper -> /usr/local/bin/plebian-os-update"
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + install -m 0755 $UPDATE_SRC /usr/local/bin/plebian-os-update"
    else
        install -m 0755 "$UPDATE_SRC" /usr/local/bin/plebian-os-update
    fi
elif [ -x /usr/local/bin/plebian-os-update ]; then
    log "update helper already present at /usr/local/bin/plebian-os-update"
else
    warn "update helper not found; continuing without plebian-os-update"
fi

# Password-change helper + scoped sudoers (the default-password desktop nag).
install_passwd_nag

# ── 2. allocate all coordinated source checkouts under the shared root ───────
case "$GPU_TERMINAL_SOURCE_HOME" in
    /*) ;;
    *) die "GPU_TERMINAL_SOURCE_HOME must be absolute: $GPU_TERMINAL_SOURCE_HOME" ;;
esac
if [ "$DRY_RUN" = 1 ]; then
    echo "    + (as $TARGET_USER) mkdir -p $GPU_TERMINAL_SOURCE_HOME"
else
    as_user mkdir -p -- "$GPU_TERMINAL_SOURCE_HOME" \
        || die "could not create source root as $TARGET_USER: $GPU_TERMINAL_SOURCE_HOME"
    [ -d "$GPU_TERMINAL_SOURCE_HOME" ] && [ ! -L "$GPU_TERMINAL_SOURCE_HOME" ] \
        || die "source root is not a safe directory: $GPU_TERMINAL_SOURCE_HOME"
    [ "$(stat -c '%u' "$GPU_TERMINAL_SOURCE_HOME" 2>/dev/null)" = "$TARGET_UID" ] \
        || die "source root is not owned by $TARGET_USER: $GPU_TERMINAL_SOURCE_HOME"
fi
ensure_plebian_os_checkout
if [ -d "$PLEB_DIR/.git" ]; then
    log "pleb present at $PLEB_DIR — updating"
    update_pleb_checkout
else
    log "cloning pleb -> $PLEB_DIR"
    clone_args=()
    [ -n "$PLEB_BRANCH" ] && clone_args=(--branch "$PLEB_BRANCH")
    as_user git clone "${clone_args[@]}" "$PLEB_REPO" "$PLEB_DIR" \
        || die "git clone of pleb failed ($PLEB_REPO)"
    if [ -n "$PLEB_REF" ]; then
        checkout_pinned_ref "$PLEB_DIR" "$PLEB_REF" "pleb"
    fi
fi

# ── 3. run `pleb install` (clones kilix + engine, registers the Pleb session) ─
# pleb does its system writes through sudo; grant the user passwordless sudo for
# the duration of provisioning, then revoke it (leaves the system as it found it).
# Remove the temporary grant on normal exit AND on signals: a SIGTERM window
# (e.g. the firstboot TimeoutStartSec) must never leave passwordless sudo behind.
# SIGKILL can't be trapped, so the firstboot unit's ExecStartPre also clears any
# stale file before each attempt.
if [ "$DRY_RUN" = 1 ]; then
    echo "    + echo '$TARGET_USER ALL=(ALL) NOPASSWD:ALL' > $SUDOERS  (temporary)"
else
    printf '%s ALL=(ALL) NOPASSWD:ALL\n' "$TARGET_USER" > "$SUDOERS"
    chmod 0440 "$SUDOERS"
    visudo -cf "$SUDOERS" >/dev/null 2>&1 \
        || { rm -f "$SUDOERS"; die "temporary sudoers validation failed"; }
fi

log "running 'pleb install' (clones kilix + optional desktop provider, adds the Pleb session)"
install_env=(
    "GPU_TERMINAL_SOURCE_HOME=$GPU_TERMINAL_SOURCE_HOME"
    "GPU_TERMINAL_HOME=$GPU_TERMINAL_HOME"
    "PLEBIAN_OS_MANAGED_INSTALL=1"
    "PLEBIAN_OS_DIR=$PLEBIAN_OS_DIR"
    "PLEBIAN_OS_STORAGE_HOME=$PLEBIAN_OS_STORAGE_HOME"
    "PLEBIAN_OS_SESSION_HOME=$PLEBIAN_OS_SESSION_HOME"
    "PLEB_DIR=$PLEB_DIR"
    "PLEB_STORAGE_HOME=$PLEB_STORAGE_HOME"
    "PLEB_CONFIG_HOME=$PLEB_CONFIG_HOME"
    "PLEB_STATE_HOME=$PLEB_STATE_HOME"
    "PLEB_CACHE_HOME=$PLEB_CACHE_HOME"
    "PLEB_SESSION_HOME=$PLEB_SESSION_HOME"
    "PLEB_DATA_HOME=$PLEB_DATA_HOME"
    "KILIX_STORAGE_HOME=$KILIX_STORAGE_HOME"
    "KILIX_CONFIG_HOME=$KILIX_CONFIG_HOME"
    "KILIX_STATE_DIRECTORY=$KILIX_STATE_DIRECTORY"
    "KILIX_CACHE_HOME=$KILIX_CACHE_HOME"
    "KILIX_SESSION_HOME=$KILIX_SESSION_HOME"
    "KILIX_BUILD_DIRECTORY=$KILIX_BUILD_DIRECTORY"
    "KILIX_DATA_HOME=$KILIX_DATA_HOME"
    "KILIX_DESKTOP_DIR=$KILIX_DESKTOP_DIR"
    "KILIX_PREBUILT_HOME=$KILIX_PREBUILT_HOME"
    "KILIX95_STORAGE_HOME=$KILIX95_STORAGE_HOME"
    "KILIX95_CONFIG_HOME=$KILIX95_CONFIG_HOME"
    "KILIX95_STATE_HOME=$KILIX95_STATE_HOME"
    "KILIX95_CACHE_HOME=$KILIX95_CACHE_HOME"
    "KILIX95_SESSION_HOME=$KILIX95_SESSION_HOME"
    "KILIX95_DATA_HOME=$KILIX95_DATA_HOME"
    "KILIX_DIR=$KILIX_DIR"
    "KILIX_REPO=$KILIX_REPO"
    "KILIX_BRANCH=$KILIX_BRANCH"
    "KILIX_REF=$KILIX_REF"
    "KILIX_PREBUILT_VERSION=$KILIX_PREBUILT_VERSION"
    "KILIX_PREBUILT_SHA256=$KILIX_PREBUILT_SHA256"
    "PLEBIAN_OS_BUILD_KILIX_FORK=$BUILD_KILIX_FORK"
    "PLEBIAN_OS_KILIX_GO_MIN_VERSION=$KILIX_GO_MIN_VERSION"
    "PLEBIAN_OS_KILIX_GO_VERSION=$KILIX_GO_VERSION"
    "PLEBIAN_OS_KILIX_GO_SHA256_AMD64=$KILIX_GO_SHA256_AMD64"
    "PLEBIAN_OS_KILIX_GO_SHA256_ARM64=$KILIX_GO_SHA256_ARM64"
    "KILIX_DESKTOP_PROVIDER=$KILIX_DESKTOP_PROVIDER"
    "KILIX_DESKTOP_COMMAND=$KILIX_DESKTOP_COMMAND"
    "KILIX_DESKTOP_NAME=$KILIX_DESKTOP_NAME"
    "KILIX_DESKTOP_FLAVOR=$KILIX_DESKTOP_FLAVOR"
    "PLEB_DESKTOP=$DESKTOP"
    "KILIX95_AUTO_INSTALL=$KILIX95_AUTO_INSTALL"
    "KILIX95_DIR=$KILIX95_DIR"
    "KILIX95_REPO=$KILIX95_REPO"
    "KILIX95_BRANCH=$KILIX95_BRANCH"
    "KILIX95_REF=$KILIX95_REF"
)
[ -n "${PROVISION_LOCK_FD:-}" ] \
    && install_env+=("PLEB_UPDATE_LOCK_FD=$PROVISION_LOCK_FD")
as_user env "${install_env[@]}" "$PLEB_DIR/bin/pleb" install \
    || die "pleb install failed (see above)"
build_kilix_fork
seed_selected_desktop_wallpaper_state

# ── 4. make Pleb the session ────────────────────────────────────────────────
# With no other desktop task installed, Pleb is the only /usr/share/xsessions
# entry, so LightDM already defaults to it. Pin it explicitly anyway, and enable
# autologin for a hard kiosk if asked.
LIGHTDM_CONF=/etc/lightdm/lightdm.conf.d/50-plebian-os.conf
log "pinning Pleb as the default LightDM session"
if [ "$DRY_RUN" = 1 ]; then
    echo "    + write $LIGHTDM_CONF ([Seat:*] user-session=pleb)"
else
    mkdir -p "$(dirname "$LIGHTDM_CONF")"
    cat > "$LIGHTDM_CONF" <<EOF
# Managed by plebian-os-provision. Plebian-OS default session: Pleb.
[Seat:*]
user-session=pleb
EOF
fi

# ── 5. session mode: boot into `kilix desktop` (disablable) ─────────────────
# pleb-session reads /etc/pleb/session.env on every login; PLEB_DESKTOP=1 brings
# the Pleb session up as the kilix desktop instead of a bare shell. This is a
# plain root-managed config file: edit it with sudo to flip to 0 (or remove it)
# for a plain fullscreen kilix — no reprovision needed.
PLEB_ENV=/etc/pleb/session.env
log "writing session config -> $PLEB_ENV (PLEB_DESKTOP=$DESKTOP)"
if [ "$DRY_RUN" = 1 ]; then
    echo "    + write $PLEB_ENV (PLEB_DESKTOP=$DESKTOP)"
else
    mkdir -p "$(dirname "$PLEB_ENV")"
    PLEB_ENV_TMP="$(mktemp /etc/pleb/.session.env.XXXXXX)"
    {
    cat <<'EOF'
# Managed by plebian-os-provision — Plebian-OS Pleb session config.
# PLEB_DESKTOP=1 starts `kilix desktop`; set it to 0 for a plain fullscreen
# kilix shell. KILIX_DESKTOP_PROVIDER selects auto, builtin, external, command,
# or none. pleb-session documents the other knobs.
EOF
    write_session_default GPU_TERMINAL_SOURCE_HOME "$GPU_TERMINAL_SOURCE_HOME"
    write_session_default GPU_TERMINAL_HOME "$GPU_TERMINAL_HOME"
    write_session_default PLEBIAN_OS_MANAGED_INSTALL 1
    write_session_default PLEB_DIR "$PLEB_DIR"
    write_session_default PLEB_STORAGE_HOME "$PLEB_STORAGE_HOME"
    write_session_default PLEB_CONFIG_HOME "$PLEB_CONFIG_HOME"
    write_session_default PLEB_STATE_HOME "$PLEB_STATE_HOME"
    write_session_default PLEB_CACHE_HOME "$PLEB_CACHE_HOME"
    write_session_default PLEB_SESSION_HOME "$PLEB_SESSION_HOME"
    write_session_default PLEB_DATA_HOME "$PLEB_DATA_HOME"
    write_session_default PLEB_REPO "$PLEB_REPO"
    write_session_default PLEB_BRANCH "$PLEB_BRANCH"
    write_session_default PLEB_REF "$PLEB_REF"
    write_session_default KILIX_DIR "$KILIX_DIR"
    write_session_default KILIX_STORAGE_HOME "$KILIX_STORAGE_HOME"
    write_session_default KILIX_CONFIG_HOME "$KILIX_CONFIG_HOME"
    write_session_default KILIX_STATE_DIRECTORY "$KILIX_STATE_DIRECTORY"
    write_session_default KILIX_CACHE_HOME "$KILIX_CACHE_HOME"
    write_session_default KILIX_SESSION_HOME "$KILIX_SESSION_HOME"
    write_session_default KILIX_BUILD_DIRECTORY "$KILIX_BUILD_DIRECTORY"
    write_session_default KILIX_DATA_HOME "$KILIX_DATA_HOME"
    write_session_default KILIX_DESKTOP_DIR "$KILIX_DESKTOP_DIR"
    write_session_default KILIX_PREBUILT_HOME "$KILIX_PREBUILT_HOME"
    write_session_default KILIX "$KILIX_DIR/kilix"
    write_session_default KILIX_REPO "$KILIX_REPO"
    write_session_default KILIX_BRANCH "$KILIX_BRANCH"
    write_session_default KILIX_REF "$KILIX_REF"
    write_session_default KILIX_PREBUILT_VERSION "$KILIX_PREBUILT_VERSION"
    write_session_default KILIX_PREBUILT_SHA256 "$KILIX_PREBUILT_SHA256"
    write_session_default PLEBIAN_OS_BUILD_KILIX_FORK "$BUILD_KILIX_FORK"
    write_session_default PLEBIAN_OS_KILIX_GO_MIN_VERSION "$KILIX_GO_MIN_VERSION"
    write_session_default PLEBIAN_OS_KILIX_GO_VERSION "$KILIX_GO_VERSION"
    write_session_default PLEBIAN_OS_KILIX_GO_SHA256_AMD64 "$KILIX_GO_SHA256_AMD64"
    write_session_default PLEBIAN_OS_KILIX_GO_SHA256_ARM64 "$KILIX_GO_SHA256_ARM64"
    write_session_default PLEB_DESKTOP "$DESKTOP"
    write_session_default KILIX_DESKTOP_PROVIDER "$KILIX_DESKTOP_PROVIDER"
    write_session_default KILIX_DESKTOP_COMMAND "$KILIX_DESKTOP_COMMAND"
    write_session_default KILIX_DESKTOP_NAME "$KILIX_DESKTOP_NAME"
    write_session_default KILIX_DESKTOP_FLAVOR "$KILIX_DESKTOP_FLAVOR"
    write_session_default KILIX95_AUTO_INSTALL "$KILIX95_AUTO_INSTALL"
    write_session_default KILIX95_STORAGE_HOME "$KILIX95_STORAGE_HOME"
    write_session_default KILIX95_CONFIG_HOME "$KILIX95_CONFIG_HOME"
    write_session_default KILIX95_STATE_HOME "$KILIX95_STATE_HOME"
    write_session_default KILIX95_CACHE_HOME "$KILIX95_CACHE_HOME"
    write_session_default KILIX95_SESSION_HOME "$KILIX95_SESSION_HOME"
    write_session_default KILIX95_DATA_HOME "$KILIX95_DATA_HOME"
    write_session_default KILIX95_DIR "$KILIX95_DIR"
    write_session_default KILIX95_REPO "$KILIX95_REPO"
    write_session_default KILIX95_BRANCH "$KILIX95_BRANCH"
    write_session_default KILIX95_REF "$KILIX95_REF"
    write_session_default PLEBIAN_OS_VERSION "$PLEBIAN_OS_VERSION"
    write_session_default PLEBIAN_OS_RELEASE "$PLEBIAN_OS_RELEASE"
    write_session_default PLEBIAN_OS_RELEASE_MODE "$PLEBIAN_OS_RELEASE_MODE"
    write_session_default PLEBIAN_OS_REPO "$PLEBIAN_OS_REPO"
    write_session_default PLEBIAN_OS_BRANCH "$PLEBIAN_OS_BRANCH"
    write_session_default PLEBIAN_OS_REF "$PLEBIAN_OS_REF"
    write_session_default PLEBIAN_OS_DIR "$PLEBIAN_OS_DIR"
    write_session_default PLEBIAN_OS_STORAGE_HOME "$PLEBIAN_OS_STORAGE_HOME"
    write_session_default PLEBIAN_OS_SESSION_HOME "$PLEBIAN_OS_SESSION_HOME"
    write_session_default PLEBIAN_OS_APT_SNAPSHOT "$PLEBIAN_OS_APT_SNAPSHOT"
    # Pleb versions predating these category-level names do not explicitly
    # re-export them after sourcing session.env.  Export them here so the
    # coordinated values still reach the Kilix launcher and Kilix 95 provider.
    printf '%s\n' 'export KILIX_CONFIG_HOME KILIX_STATE_DIRECTORY KILIX_CACHE_HOME KILIX_SESSION_HOME KILIX_PREBUILT_HOME'
    printf '%s\n' 'export KILIX95_CONFIG_HOME KILIX95_STATE_HOME KILIX95_CACHE_HOME KILIX95_SESSION_HOME KILIX95_DATA_HOME'
    [ "$KIOSK" = 1 ] && printf '%s\n' 'PLEB_RESPAWN=1   # hard kiosk: respawn kilix if it exits (set by --kiosk)'
    } > "$PLEB_ENV_TMP"
    chmod 0644 "$PLEB_ENV_TMP"
    mv -fT "$PLEB_ENV_TMP" "$PLEB_ENV"
fi

if [ "$KIOSK" = 1 ]; then
    log "enabling autologin into Pleb (kiosk)"
    as_user env "${install_env[@]}" "$PLEB_DIR/bin/pleb" autologin on "$TARGET_USER" \
        || die "pleb autologin failed; requested kiosk state was not applied"
    pin_remembered_session
else
    log "ensuring Pleb autologin is disabled (non-kiosk mode)"
    as_user env "${install_env[@]}" "$PLEB_DIR/bin/pleb" autologin off \
        || die "could not disable Pleb autologin; refusing to report reconciled state"
fi

# Passwordless sudo for the owner. Plebian-OS is a single-user appliance and the
# VM builder turns this on by default, so `pleb install`, the Start-menu update
# actions and Shut Down (systemctl poweroff) never stop for a password. This is
# a PERMANENT file — the grant used during provisioning above is temporary and
# removed by cleanup.
NOPASSWD_FILE=/etc/sudoers.d/plebian-os-nopasswd
if [ "$NOPASSWD_SUDO" = 1 ]; then
    log "granting $TARGET_USER passwordless sudo"
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + echo '$TARGET_USER ALL=(ALL) NOPASSWD:ALL' > $NOPASSWD_FILE (0440, visudo-checked)"
    else
        printf '%s ALL=(ALL) NOPASSWD:ALL\n' "$TARGET_USER" > "$NOPASSWD_FILE"
        chmod 0440 "$NOPASSWD_FILE"
        visudo -cf "$NOPASSWD_FILE" >/dev/null 2>&1 \
            || { rm -f "$NOPASSWD_FILE"; die "sudoers validation failed; requested passwordless-sudo state was not applied"; }
    fi
else
    log "ensuring sudo for $TARGET_USER requires a password"
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + rm -f $NOPASSWD_FILE"
    else
        rm -f "$NOPASSWD_FILE"
    fi
fi

# Capture the final state only now: dependency installation, pleb install, Go
# setup, Kilix fork compilation, and all optional providers have completed.
write_package_manifest
write_source_tool_manifest

cleanup; trap - EXIT

log "done. Plebian-OS is provisioned."
log "  reboot → LightDM → Pleb → $([ "$DESKTOP" = 1 ] && echo "kilix desktop ($KILIX_DESKTOP_PROVIDER)" || echo 'fullscreen kilix')."
[ "$KIOSK" = 1 ] && log "  (kiosk: autologin + kilix respawn on exit; rescue console on Ctrl+Alt+F2)"
[ "$NOPASSWD_SUDO" = 1 ] && log "  ($TARGET_USER has passwordless sudo)"
exit 0
