#!/usr/bin/env bash
# plebian-os-update.sh — refresh the whole Plebian-OS software stack.
#
# Pulls or pins kilix, optional desktop provider, AND pleb, then re-runs
# `pleb install`. This is MORE than `pleb update` (which updates from the pleb
# side): it also updates the pleb repo itself and re-applies the install — the
# kilix/pleb command symlinks, the pleb-session launcher, and the xsession entry
# — so a change to any of those lands too. It ALSO refreshes the Plebian-OS layer
# itself (the provisioner, dependency installer, password helper, systemd unit,
# version marker, branded desktop/greeter wallpaper configuration, artwork
# notices, and this helper) from a plebian-os
# checkout. Updates are
# serialized; participating checkouts must be clean and pinned refs resolve to
# the fetched commit. One outer recovery transaction covers the deployed OS
# layer, checkout positions, engine artifacts, and `pleb install` outputs.
# Disable OS-layer refresh with PLEBIAN_OS_SELF_UPDATE=0.
#
# Usage: plebian-os-update [--restart]
# By default the running graphical session is left alone. Pass --restart to ask
# Pleb to restart it only after the stack update has completed successfully.
#
# Run as the Pleb user; `pleb install` elevates via sudo where it needs root.
# Deployed to the target as /usr/local/bin/plebian-os-update and offered by
# desktop providers as a clickable stack update action.
set -euo pipefail

log()  { printf '\033[1;35m[plebian-os]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[plebian-os]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[plebian-os] %s\033[0m\n' "$*" >&2; exit 1; }

require_unprivileged_updater() {
    [ "${1:-$EUID}" -ne 0 ] \
        || die "run plebian-os-update without sudo (it elevates only bounded system steps)"
}
# The library-only hook lets focused tests load functions as root.  Every real
# invocation rejects root before config loading, allocation, locking, or writes.
if [ "${PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY:-0}" != 1 ]; then
    require_unprivileged_updater "$EUID"
fi

DESKTOP_WALLPAPER_DST=/usr/local/share/plebian-os/wallpapers/plebian-os.png
DESKTOP_WALLPAPER_SHA256=60f63c37f054f7ffd061b47e09a3c22fbf595eec6f161c13e95344ca1a724778
# shellcheck disable=SC2034
LIGHTDM_GREETER_CONFIG_DST=/etc/lightdm/lightdm-gtk-greeter.conf.d/50-plebian-os.conf
# These notice constants are also an exact staged-script contract consumed by
# stage_and_validate_os_layer; they are deliberately not expanded at runtime.
# shellcheck disable=SC2034
INSTALLER_ATTRIBUTION_DST=/usr/local/share/doc/plebian-os/installer/ATTRIBUTION.md
# shellcheck disable=SC2034
INSTALLER_ATTRIBUTION_SHA256=5216b6ee1ef154dab56cc5d0a026d28f67ed50feec4129d4fedd6ae2fc2b2fb6
# shellcheck disable=SC2034
GPL2_LICENSE_DST=/usr/local/share/doc/plebian-os/COPYING.GPL-2
# shellcheck disable=SC2034
GPL2_LICENSE_SHA256=8177f97513213526df2cf6184d8ff986c675afb514d4e68a404010521b880643
_DEPLOYED_DESKTOP_WALLPAPER_SHA256="$DESKTOP_WALLPAPER_SHA256"

desktop_wallpaper_matches_expected_hash() {
    local path="$1" expected="$2" actual
    [[ "$expected" =~ ^[0-9a-f]{64}$ ]] || return 1
    actual="$(sha256sum "$path" 2>/dev/null | awk '{print $1}')" || return 1
    [ "$actual" = "$expected" ]
}

ensure_private_update_dir() {
    local path="$1" anchor="$2" label="$3"
    local secure_intermediates="${4:-0}"
    local resolved anchor_real path_real owner mode current remaining component
    local -a allocations
    case "$path" in
        /*) ;;
        *) die "$label must be an absolute path: $path" ;;
    esac
    case "$path" in
        "$anchor"/*) ;;
        *) die "$label must be a strict descendant of $anchor: $path" ;;
    esac
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
        install -d -m 0700 -- "$current" \
            || die "could not create or secure $label: $current"
        resolved="$(readlink -m -- "$current" 2>/dev/null)" \
            || die "could not resolve allocated $label component: $current"
        [ "$resolved" = "$current" ] && [ -d "$current" ] \
            && [ ! -L "$current" ] \
            || die "$label acquired an unsafe directory component: $current"
        owner="$(stat -c '%u' -- "$current" 2>/dev/null)" \
            || die "could not inspect allocated $label component: $current"
        mode="$(stat -c '%a' -- "$current" 2>/dev/null)" \
            || die "could not inspect allocated $label component mode: $current"
        [ "$owner" = "$EUID" ] && [ "$mode" = 700 ] \
            || die "$label components must be owned by the updating user with mode 0700: $current"
    done
    resolved="$(readlink -m -- "$path" 2>/dev/null)" \
        || die "could not resolve allocated $label: $path"
    [ "$resolved" = "$path" ] && [ -d "$path" ] && [ ! -L "$path" ] \
        || die "$label became an unsafe directory during allocation: $path"
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
    # An explicit desktop outside PLEB_DATA_HOME belongs to its operator.  The
    # updater may seed its state file, but must not chmod the directory.
    case "$state_dir" in
        "$PLEB_DATA_HOME")
            ensure_private_update_dir "$PLEB_DATA_HOME" \
                "$PLEB_STORAGE_HOME" PLEB_DATA_HOME 1
            ;;
        "$PLEB_DATA_HOME"/*)
            ensure_private_update_dir "$PLEB_DATA_HOME" \
                "$PLEB_STORAGE_HOME" PLEB_DATA_HOME 1
            ensure_private_update_dir "$state_dir" "$PLEB_DATA_HOME" \
                KILIX_DESKTOP_DIR 1
            ;;
        *) return 0 ;;
    esac
}

allocate_coordinated_private_storage() {
    local i
    local -a labels roots category_labels category_roots category_paths
    labels=(
        GPU_TERMINAL_HOME
        PLEB_STORAGE_HOME
        KILIX_STORAGE_HOME
        KILIX95_STORAGE_HOME
        PLEBIAN_OS_STORAGE_HOME
    )
    roots=(
        "$GPU_TERMINAL_HOME"
        "$PLEB_STORAGE_HOME"
        "$KILIX_STORAGE_HOME"
        "$KILIX95_STORAGE_HOME"
        "$PLEBIAN_OS_STORAGE_HOME"
    )
    ensure_private_update_dir "${roots[0]}" "$HOME" "${labels[0]}"
    for i in 1 2 3 4; do
        ensure_private_update_dir "${roots[$i]}" "$GPU_TERMINAL_HOME" \
            "${labels[$i]}" 1
    done

    category_labels=(
        PLEB_CONFIG_HOME PLEB_STATE_HOME PLEB_CACHE_HOME PLEB_SESSION_HOME
        PLEB_DATA_HOME KILIX_CONFIG_HOME KILIX_STATE_DIRECTORY
        KILIX_CACHE_HOME KILIX_SESSION_HOME KILIX_BUILD_DIRECTORY
        KILIX_DATA_HOME KILIX_PREBUILT_HOME KILIX95_CONFIG_HOME
        KILIX95_STATE_HOME KILIX95_CACHE_HOME KILIX95_SESSION_HOME
        KILIX95_DATA_HOME PLEBIAN_OS_SESSION_HOME
    )
    category_roots=(
        "$PLEB_STORAGE_HOME" "$PLEB_STORAGE_HOME" "$PLEB_STORAGE_HOME"
        "$PLEB_STORAGE_HOME" "$PLEB_STORAGE_HOME" "$KILIX_STORAGE_HOME"
        "$KILIX_STORAGE_HOME" "$KILIX_STORAGE_HOME" "$KILIX_STORAGE_HOME"
        "$KILIX_STORAGE_HOME" "$KILIX_STORAGE_HOME" "$KILIX_STORAGE_HOME"
        "$KILIX95_STORAGE_HOME" "$KILIX95_STORAGE_HOME"
        "$KILIX95_STORAGE_HOME" "$KILIX95_STORAGE_HOME"
        "$KILIX95_STORAGE_HOME" "$PLEBIAN_OS_STORAGE_HOME"
    )
    category_paths=(
        "$PLEB_CONFIG_HOME" "$PLEB_STATE_HOME" "$PLEB_CACHE_HOME"
        "$PLEB_SESSION_HOME" "$PLEB_DATA_HOME" "$KILIX_CONFIG_HOME"
        "$KILIX_STATE_DIRECTORY" "$KILIX_CACHE_HOME" "$KILIX_SESSION_HOME"
        "$KILIX_BUILD_DIRECTORY" "$KILIX_DATA_HOME" "$KILIX_PREBUILT_HOME"
        "$KILIX95_CONFIG_HOME" "$KILIX95_STATE_HOME" "$KILIX95_CACHE_HOME"
        "$KILIX95_SESSION_HOME" "$KILIX95_DATA_HOME"
        "$PLEBIAN_OS_SESSION_HOME"
    )
    for i in "${!category_paths[@]}"; do
        ensure_private_update_dir "${category_paths[$i]}" \
            "${category_roots[$i]}" "${category_labels[$i]}" 1
    done
    secure_managed_pleb_desktop_dir "$KILIX_DESKTOP_DIR"
}

seed_desktop_wallpaper_state_if_absent() {
    local state_dir="$1" wallpaper="$2" state_path="$1/.state.json" owner rc
    secure_managed_pleb_desktop_dir "$state_dir" || return 1
    if [ -e "$state_path" ] || [ -L "$state_path" ]; then
        log "preserving existing Pleb desktop state (including wallpaper): $state_path"
        return 0
    fi
    mkdir -p -- "$state_dir" \
        || { warn "could not create Pleb desktop state directory: $state_dir"; return 1; }
    [ -d "$state_dir" ] && [ ! -L "$state_dir" ] \
        || { warn "Pleb desktop state path is not a safe directory: $state_dir"; return 1; }
    owner="$(stat -c '%u' "$state_dir" 2>/dev/null)" \
        || { warn "could not inspect Pleb desktop state directory: $state_dir"; return 1; }
    [ "$owner" = "$(id -u)" ] \
        || { warn "Pleb desktop state directory is not owned by the updating user: $state_dir"; return 1; }

    if python3 - "$state_dir" "$state_path" "$wallpaper" <<'PY'
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
        if [ "$rc" = 17 ]; then
            log "Pleb desktop state appeared concurrently; preserving it"
            return 0
        fi
        warn "could not seed Pleb desktop wallpaper state"
        return 1
    fi
}

selected_desktop_wallpaper_state_dir() {
    case "$KILIX_DESKTOP_PROVIDER" in
        external|builtin|auto) printf '%s\n' "$KILIX_DESKTOP_DIR" ;;
        *) return 1 ;;
    esac
}

seed_desktop_wallpaper_after_commit() {
    local state_dir owner mode dir
    case "${PLEB_DESKTOP:-0}" in 1|yes|true|on) ;; *) return 0 ;; esac
    if [ "$(id -u)" = 0 ]; then
        warn "stack committed; run plebian-os-update as the desktop user to seed its wallpaper"
        return 0
    fi
    for dir in / /usr /usr/local /usr/local/share; do
        [ -d "$dir" ] && [ ! -L "$dir" ] || {
            warn "installed desktop wallpaper has an unsafe fixed ancestor: $dir"
            return 1
        }
        owner="$(stat -c '%u' "$dir" 2>/dev/null)" || return 1
        mode="$(stat -c '%a' "$dir" 2>/dev/null)" || return 1
        [ "$owner" = 0 ] && (( (8#$mode & 8#22) == 0 )) || {
            warn "desktop wallpaper ancestor is not safely root-owned: $dir"
            return 1
        }
    done
    for dir in /usr/local/share/plebian-os \
        /usr/local/share/plebian-os/wallpapers; do
        [ -d "$dir" ] && [ ! -L "$dir" ] || {
            warn "installed desktop wallpaper has an unsafe parent directory"
            return 1
        }
        owner="$(stat -c '%u' "$dir" 2>/dev/null)" || return 1
        mode="$(stat -c '%a' "$dir" 2>/dev/null)" || return 1
        [ "$owner" = 0 ] && (( (8#$mode & 8#22) == 0 )) \
            && (( (8#$mode & 8#1) != 0 )) || {
            warn "desktop wallpaper directory is not safely user-traversable: $dir"
            return 1
        }
    done
    if [ ! -f "$DESKTOP_WALLPAPER_DST" ] || [ -L "$DESKTOP_WALLPAPER_DST" ]; then
        warn "stack committed, but the validated desktop wallpaper is not installed; not seeding user state"
        return 0
    fi
    owner="$(stat -c '%u' "$DESKTOP_WALLPAPER_DST" 2>/dev/null)" || return 1
    mode="$(stat -c '%a' "$DESKTOP_WALLPAPER_DST" 2>/dev/null)" || return 1
    [ "$owner" = 0 ] && [ "$mode" = 644 ] || {
        warn "installed desktop wallpaper has unsafe ownership or mode; not seeding user state"
        return 1
    }
    desktop_wallpaper_matches_expected_hash \
        "$DESKTOP_WALLPAPER_DST" "$_DEPLOYED_DESKTOP_WALLPAPER_SHA256" || {
        warn "installed desktop wallpaper checksum mismatch; not seeding user state"
        return 1
    }
    state_dir="$(selected_desktop_wallpaper_state_dir)" || {
        log "desktop provider $KILIX_DESKTOP_PROVIDER does not use managed Pleb wallpaper state"
        return 0
    }
    case "$state_dir" in
        /*) ;;
        *) warn "KILIX_DESKTOP_DIR must be absolute to seed the wallpaper"; return 1 ;;
    esac
    seed_desktop_wallpaper_state_if_absent "$state_dir" "$DESKTOP_WALLPAPER_DST"
}

root_config_safe_to_source() {
    local cfg="$1" owner mode dir
    [ "$(id -u)" = 0 ] || return 0
    [ -f "$cfg" ] && [ ! -L "$cfg" ] || return 1
    owner="$(stat -c '%u' "$cfg" 2>/dev/null)" || return 1
    mode="$(stat -c '%a' "$cfg" 2>/dev/null)" || return 1
    [ "$owner" = 0 ] && (( (8#$mode & 8#22) == 0 )) || return 1
    dir="$(dirname "$cfg")"
    while [ "$dir" != / ]; do
        owner="$(stat -c '%u' "$dir" 2>/dev/null)" || return 1
        mode="$(stat -c '%a' "$dir" 2>/dev/null)" || return 1
        [ "$owner" = 0 ] && (( (8#$mode & 8#22) == 0 )) || return 1
        dir="$(dirname "$dir")"
    done
}

if [ -r /etc/pleb/session.env ]; then
    root_config_safe_to_source /etc/pleb/session.env \
        || die "refusing to source unsafe /etc/pleb/session.env as root"
    # shellcheck source=/dev/null
    . /etc/pleb/session.env
fi

GPU_TERMINAL_SOURCE_HOME="${GPU_TERMINAL_SOURCE_HOME:-$HOME/gpu_terminal}"
PLEB_DIR="${PLEB_DIR:-$GPU_TERMINAL_SOURCE_HOME/pleb}"
PLEB_REPO="${PLEB_REPO:-https://github.com/itsmygithubacct/pleb.git}"
PLEB_BRANCH="${PLEB_BRANCH:-}"
PLEB_REF="${PLEB_REF:-}"
GPU_TERMINAL_HOME="${GPU_TERMINAL_HOME:-$HOME/.local/gpu_terminal}"
PLEB_STORAGE_HOME="${PLEB_STORAGE_HOME:-$GPU_TERMINAL_HOME/pleb}"
PLEB_CONFIG_HOME="${PLEB_CONFIG_HOME:-$PLEB_STORAGE_HOME/config}"
PLEB_STATE_HOME="${PLEB_STATE_HOME:-$PLEB_STORAGE_HOME/state}"
PLEB_CACHE_HOME="${PLEB_CACHE_HOME:-$PLEB_STORAGE_HOME/cache}"
PLEB_SESSION_HOME="${PLEB_SESSION_HOME:-$PLEB_STORAGE_HOME/session}"
PLEB_DATA_HOME="${PLEB_DATA_HOME:-$PLEB_STORAGE_HOME/data}"
KILIX_DIR="${KILIX_DIR:-$GPU_TERMINAL_SOURCE_HOME/kilix}"
KILIX_STORAGE_HOME="${KILIX_STORAGE_HOME:-$GPU_TERMINAL_HOME/kilix}"
KILIX_CONFIG_HOME="${KILIX_CONFIG_HOME:-$KILIX_STORAGE_HOME/config}"
KILIX_STATE_DIRECTORY="${KILIX_STATE_DIRECTORY:-$KILIX_STORAGE_HOME/state}"
KILIX_CACHE_HOME="${KILIX_CACHE_HOME:-$KILIX_STORAGE_HOME/cache}"
KILIX_SESSION_HOME="${KILIX_SESSION_HOME:-$KILIX_STORAGE_HOME/session}"
KILIX_BUILD_DIRECTORY="${KILIX_BUILD_DIRECTORY:-$KILIX_STORAGE_HOME/build}"
KILIX_DATA_HOME="${KILIX_DATA_HOME:-$KILIX_STORAGE_HOME/data}"
KILIX_DESKTOP_DIR="${KILIX_DESKTOP_DIR:-$PLEB_DATA_HOME/desktop}"
KILIX_PREBUILT_HOME="${KILIX_PREBUILT_HOME:-$KILIX_STORAGE_HOME/prebuilt/kitty.app}"
KILIX_REPO="${KILIX_REPO:-https://github.com/itsmygithubacct/kilix.git}"
KILIX_BRANCH="${KILIX_BRANCH:-}"
KILIX_REF="${KILIX_REF:-}"
KILIX_PREBUILT_VERSION="${KILIX_PREBUILT_VERSION:-0.47.4}"
KILIX_PREBUILT_SHA256="${KILIX_PREBUILT_SHA256:-bc230142b2bd27f2a4bf1b1b67575f3d397a4ea2cc83f4ac2b912c306a939693}"
PLEBIAN_OS_BUILD_KILIX_FORK="${PLEBIAN_OS_BUILD_KILIX_FORK:-1}"
PLEBIAN_OS_KILIX_GO_MIN_VERSION="${PLEBIAN_OS_KILIX_GO_MIN_VERSION:-1.26}"
PLEBIAN_OS_KILIX_GO_VERSION="${PLEBIAN_OS_KILIX_GO_VERSION:-}"
PLEBIAN_OS_KILIX_GO_SHA256_AMD64="${PLEBIAN_OS_KILIX_GO_SHA256_AMD64:-}"
PLEBIAN_OS_KILIX_GO_SHA256_ARM64="${PLEBIAN_OS_KILIX_GO_SHA256_ARM64:-}"
KILIX_DESKTOP_PROVIDER="${KILIX_DESKTOP_PROVIDER:-auto}"
KILIX_DESKTOP_COMMAND="${KILIX_DESKTOP_COMMAND:-}"
KILIX_DESKTOP_NAME="${KILIX_DESKTOP_NAME:-desktop}"
KILIX_DESKTOP_FLAVOR="${KILIX_DESKTOP_FLAVOR:-}"
KILIX95_DIR="${KILIX95_DIR:-$GPU_TERMINAL_SOURCE_HOME/kilix-95}"
KILIX95_STORAGE_HOME="${KILIX95_STORAGE_HOME:-$GPU_TERMINAL_HOME/kilix-95}"
KILIX95_CONFIG_HOME="${KILIX95_CONFIG_HOME:-$KILIX95_STORAGE_HOME/config}"
KILIX95_STATE_HOME="${KILIX95_STATE_HOME:-$KILIX95_STORAGE_HOME/state}"
KILIX95_CACHE_HOME="${KILIX95_CACHE_HOME:-$KILIX95_STORAGE_HOME/cache}"
KILIX95_SESSION_HOME="${KILIX95_SESSION_HOME:-$KILIX95_STORAGE_HOME/session}"
KILIX95_DATA_HOME="${KILIX95_DATA_HOME:-$KILIX95_STORAGE_HOME/data}"
KILIX95_REPO="${KILIX95_REPO:-https://github.com/itsmygithubacct/kilix-95.git}"
KILIX95_BRANCH="${KILIX95_BRANCH:-}"
KILIX95_REF="${KILIX95_REF:-}"
KILIX95_AUTO_INSTALL="${KILIX95_AUTO_INSTALL:-1}"
PLEB_DESKTOP="${PLEB_DESKTOP:-0}"
PLEBIAN_OS_STORAGE_HOME="${PLEBIAN_OS_STORAGE_HOME:-$GPU_TERMINAL_HOME/plebian-os}"
PLEBIAN_OS_SESSION_HOME="${PLEBIAN_OS_SESSION_HOME:-$PLEBIAN_OS_STORAGE_HOME/session}"

# `pleb install` normally owns these five system paths. The stack updater
# snapshots the fixed, distribution-managed destinations before invoking it so
# a later failure can restore the complete previous install. Custom install
# destinations remain supported by `pleb install` directly, but are rejected by
# this privileged whole-stack transaction rather than feeding caller-controlled
# paths into its root rollback routine.
SESSION_BIN_DST="${SESSION_BIN_DST:-/usr/local/bin/pleb-session}"
XSESSION_DST="${XSESSION_DST:-/usr/share/xsessions/pleb.desktop}"
KILIX_LINK="${KILIX_LINK:-/usr/local/bin/kilix}"
PLEB_LINK="${PLEB_LINK:-/usr/local/bin/pleb}"
PLEB_RECOVERY_DOC_DST="${PLEB_RECOVERY_DOC_DST:-/usr/local/share/doc/pleb/RECOVERY.md}"

# Plebian-OS layer self-update: the OS's own scripts (provisioner, dependency
# installer, this update helper) come from a plebian-os checkout so an installed
# system can pull OS-layer fixes — not just pleb/kilix — with one command.
PLEBIAN_OS_DIR="${PLEBIAN_OS_DIR:-$GPU_TERMINAL_SOURCE_HOME/plebian-os}"
PLEBIAN_OS_REPO="${PLEBIAN_OS_REPO:-https://github.com/itsmygithubacct/plebian-os.git}"
PLEBIAN_OS_BRANCH="${PLEBIAN_OS_BRANCH:-}"
PLEBIAN_OS_REF="${PLEBIAN_OS_REF:-}"
PLEBIAN_OS_SELF_UPDATE="${PLEBIAN_OS_SELF_UPDATE:-1}"
PLEBIAN_OS_VERSION="${PLEBIAN_OS_VERSION:-}"
[ -n "$PLEBIAN_OS_VERSION" ] || PLEBIAN_OS_VERSION="$(cat "$PLEBIAN_OS_DIR/VERSION" 2>/dev/null || echo unknown)"

restart_arg=--no-restart
[ "$#" -le 1 ] || die "expected at most one option (try --help)"
case "${1:-}" in
    --version|-V) echo "plebian-os-update $PLEBIAN_OS_VERSION"; exit 0 ;;
    -h|--help) sed -n '2,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//'; exit 0 ;;
    --restart) restart_arg=--restart ;;
    "") ;;
    *) die "unknown option: $1 (try --help)" ;;
esac

# Repair the complete coordinated data tree before the update lock is the first
# writer on an older or freshly created installation.
if [ "${PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY:-0}" != 1 ]; then
    allocate_coordinated_private_storage
fi

acquire_update_lock() {
    local lock="$PLEB_STATE_HOME/update.lock"
    command -v flock >/dev/null 2>&1 \
        || die "flock is required to serialize stack updates (install util-linux)"
    mkdir -p "$PLEB_STATE_HOME"
    exec 9>>"$lock"
    chmod 0600 "$lock" \
        || die "could not secure update lock: $lock"
    flock -n 9 \
        || die "another Pleb/Plebian-OS update is already running (lock: $lock)"
}

_STACK_KILIX_LOCK_FD=""
_STACK_KILIX_LOCK_BORROWED=0

release_kilix_transaction_lock() {
    if [ -n "${_STACK_KILIX_LOCK_FD:-}" ]; then
        if [ "${_STACK_KILIX_LOCK_BORROWED:-0}" != 1 ]; then
            flock -u "$_STACK_KILIX_LOCK_FD" 2>/dev/null || true
            exec {_STACK_KILIX_LOCK_FD}>&-
        fi
        _STACK_KILIX_LOCK_FD=""
        _STACK_KILIX_LOCK_BORROWED=0
    fi
}

acquire_kilix_transaction_lock() {
    local lock_path fd fd_path path_identity fd_identity existed=0
    [ -z "${_STACK_KILIX_LOCK_FD:-}" ] || return 0
    command -v flock >/dev/null 2>&1 \
        || die "flock is required to serialize Kilix build/update transactions"
    [ -d "$KILIX_STATE_DIRECTORY" ] && [ ! -L "$KILIX_STATE_DIRECTORY" ] \
        && [ "$(stat -c '%u:%a' -- "$KILIX_STATE_DIRECTORY" 2>/dev/null)" \
            = "$EUID:700" ] \
        || die "KILIX_STATE_DIRECTORY must be a private allocated directory"
    lock_path="$(cd "$KILIX_STATE_DIRECTORY" && pwd -P)/build-update.lock" \
        || die "could not resolve the Kilix transaction lock path"
    if [ -e "$lock_path" ] || [ -L "$lock_path" ]; then
        existed=1
        [ -f "$lock_path" ] && [ ! -L "$lock_path" ] \
            && [ "$(stat -c '%u:%a:%h' -- "$lock_path" 2>/dev/null)" \
                = "$EUID:600:1" ] \
            || die "refusing unsafe Kilix transaction lock: $lock_path"
    fi
    if [ -n "${KILIX_TRANSACTION_LOCK_FD:-}" ]; then
        fd="$KILIX_TRANSACTION_LOCK_FD"
        [[ "$fd" =~ ^[0-9]+$ ]] \
            || die "KILIX_TRANSACTION_LOCK_FD must be a numeric inherited descriptor"
        fd_path="/proc/$$/fd/$fd"
        [ -e "$fd_path" ] \
            || die "KILIX_TRANSACTION_LOCK_FD=$fd is not open in this process"
        _STACK_KILIX_LOCK_FD="$fd"
        _STACK_KILIX_LOCK_BORROWED=1
    else
        exec {_STACK_KILIX_LOCK_FD}>"$lock_path" \
            || die "could not open the Kilix transaction lock: $lock_path"
        fd="$_STACK_KILIX_LOCK_FD"
        fd_path="/proc/$$/fd/$fd"
        _STACK_KILIX_LOCK_BORROWED=0
    fi
    [ "$existed" = 1 ] || chmod 0600 -- "$lock_path" \
        || die "could not protect the Kilix transaction lock: $lock_path"
    [ -f "$lock_path" ] && [ ! -L "$lock_path" ] \
        && [ "$(stat -c '%u:%a:%h' -- "$lock_path" 2>/dev/null)" \
            = "$EUID:600:1" ] \
        || die "Kilix transaction lock is not a private regular file: $lock_path"
    path_identity="$(stat -c '%d:%i' -- "$lock_path" 2>/dev/null)" \
        || die "could not inspect the Kilix transaction lock"
    fd_identity="$(stat -Lc '%d:%i' -- "$fd_path" 2>/dev/null)" \
        || die "could not inspect the inherited Kilix transaction-lock descriptor"
    [ "$fd_identity" = "$path_identity" ] \
        || die "KILIX_TRANSACTION_LOCK_FD does not refer to $lock_path"
    flock -x "$fd" || die "could not acquire the Kilix transaction lock"
    KILIX_TRANSACTION_LOCK_FD="$fd"
    KILIX_TRANSACTION_LOCK_PATH="$lock_path"
    export KILIX_TRANSACTION_LOCK_FD KILIX_TRANSACTION_LOCK_PATH
}
if [ "${PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY:-0}" != 1 ]; then
    acquire_update_lock
    acquire_kilix_transaction_lock
fi

_STACK_TXN_DIR=""
_STACK_ROOT_TXN_DIR=""
_STACK_TXN_ACTIVE=0
_STACK_TXN_COMMITTED=0
_STACK_TXN_RETAIN=0
_OS_LAYER_STAGE=""

require_standard_install_destinations() {
    if [ "$SESSION_BIN_DST" != /usr/local/bin/pleb-session ] \
        || [ "$XSESSION_DST" != /usr/share/xsessions/pleb.desktop ] \
        || [ "$KILIX_LINK" != /usr/local/bin/kilix ] \
        || [ "$PLEB_LINK" != /usr/local/bin/pleb ] \
        || [ "$PLEB_RECOVERY_DOC_DST" != /usr/local/share/doc/pleb/RECOVERY.md ]; then
        die "plebian-os-update cannot transactionally protect custom Pleb install destinations; run 'pleb install' directly"
    fi
}

require_clean_transaction_checkout() {
    local dir="$1" label="$2" dirty
    dirty="$(git -C "$dir" status --porcelain --untracked-files=normal 2>/dev/null)" \
        || die "could not inspect $label checkout at $dir"
    [ -z "$dirty" ] \
        || die "$label checkout at $dir has local changes; refusing a whole-stack update whose rollback could overwrite them"
}

record_stack_checkout() {
    local dir="$1" key="$2" label="$3"
    if [ -d "$dir/.git" ] || [ -f "$dir/.git" ]; then
        require_clean_transaction_checkout "$dir" "$label"
        printf '%s\n' 1 >"$_STACK_TXN_DIR/$key.existed"
        git -C "$dir" rev-parse --verify HEAD >"$_STACK_TXN_DIR/$key.head" \
            || die "could not record the pre-update $label commit"
        git -C "$dir" symbolic-ref --quiet HEAD >"$_STACK_TXN_DIR/$key.ref" \
            || : >"$_STACK_TXN_DIR/$key.ref"
    elif [ -e "$dir" ] || [ -L "$dir" ]; then
        die "$label path at $dir exists but is not a git checkout"
    else
        printf '%s\n' 0 >"$_STACK_TXN_DIR/$key.existed"
    fi
}

snapshot_stack_path() {
    local path="$1" key="$2"
    if [ -e "$path" ] || [ -L "$path" ]; then
        : >"$_STACK_TXN_DIR/$key.present"
        cp -a -- "$path" "$_STACK_TXN_DIR/$key" \
            || die "could not snapshot install-managed path $path"
    fi
}

begin_root_stack_snapshot() {
    local -a elevate=()
    [ "$(id -u)" = 0 ] || elevate=(sudo)
    "${elevate[@]}" bash -s <<'ROOT_SNAPSHOT'
set -euo pipefail
umask 077
base=/var/lib/plebian-os
mkdir -p -- "$base"
[ -d "$base" ] && [ ! -L "$base" ] && [ "$(stat -c '%u' "$base")" = 0 ] || exit 2
mode="$(stat -c '%a' "$base")"
(( (8#$mode & 8#22) == 0 )) || exit 2
txn="$(mktemp -d "$base/update-rollback.XXXXXX")"
paths=(
    /usr/local/sbin/plebian-os-provision
    /usr/local/sbin/plebian-os-install-deps
    /usr/local/sbin/plebian-os-passwd
    /usr/local/bin/plebian-os-update
    /etc/systemd/system/plebian-os-firstboot.service
    /usr/local/sbin/plebian-os-firstboot-attempt
    /usr/local/share/plebian-os/VERSION
    /usr/local/share/plebian-os/wallpapers/plebian-os.png
    /usr/local/share/doc/plebian-os/installer/ATTRIBUTION.md
    /usr/local/share/doc/plebian-os/COPYING.GPL-2
    /etc/lightdm/lightdm-gtk-greeter.conf.d/50-plebian-os.conf
    /usr/local/bin/pleb-session
    /usr/share/xsessions/pleb.desktop
    /usr/local/bin/kilix
    /usr/local/bin/pleb
    /usr/local/share/doc/pleb/RECOVERY.md
)
managed_dirs=(
    /usr/local/share/plebian-os
    /usr/local/share/plebian-os/wallpapers
    /usr/local/share/doc
    /usr/local/share/doc/plebian-os
    /usr/local/share/doc/plebian-os/installer
    /usr/local/share/doc/pleb
    /etc/lightdm/lightdm-gtk-greeter.conf.d
)
cleanup() {
    rc=$?
    trap - EXIT
    [ "$rc" -eq 0 ] || rm -rf -- "$txn"
    exit "$rc"
}
trap cleanup EXIT
mkdir "$txn/items"
for dir in / /usr /usr/local /usr/local/share /etc /etc/lightdm; do
    [ -d "$dir" ] && [ ! -L "$dir" ] && [ "$(stat -c '%u' "$dir")" = 0 ] \
        || exit 2
    dir_mode="$(stat -c '%a' "$dir")"
    (( (8#$dir_mode & 8#22) == 0 )) || exit 2
done
for i in "${!managed_dirs[@]}"; do
    dir="${managed_dirs[$i]}"
    if [ -e "$dir" ] || [ -L "$dir" ]; then
        [ -d "$dir" ] && [ ! -L "$dir" ] && [ "$(stat -c '%u' "$dir")" = 0 ] \
            || exit 2
        dir_mode="$(stat -c '%a' "$dir")"
        (( (8#$dir_mode & 8#22) == 0 )) \
            && (( (8#$dir_mode & 8#1) != 0 )) || exit 2
        : >"$txn/dir.$i.present"
    fi
done
for i in "${!paths[@]}"; do
    if [ -e "${paths[$i]}" ] || [ -L "${paths[$i]}" ]; then
        : >"$txn/$i.present"
        cp -a -- "${paths[$i]}" "$txn/items/$i"
    fi
done
printf '%s\n' "$txn"
ROOT_SNAPSHOT
}

validate_root_transaction_dir() {
    case "$1" in
        /var/lib/plebian-os/update-rollback.*) ;;
        *) return 1 ;;
    esac
}

restore_root_stack_snapshot() {
    local root_txn="$1"
    local -a elevate=()
    validate_root_transaction_dir "$root_txn" || return 1
    [ "$(id -u)" = 0 ] || elevate=(sudo)
    "${elevate[@]}" bash -s -- "$root_txn" <<'ROOT_RESTORE'
set -euo pipefail
txn="$1"
case "$txn" in /var/lib/plebian-os/update-rollback.*) ;; *) exit 2 ;; esac
[ -d "$txn" ] && [ ! -L "$txn" ] && [ "$(stat -c '%u' "$txn")" = 0 ] || exit 2
mode="$(stat -c '%a' "$txn")"
(( (8#$mode & 8#077) == 0 )) || exit 2
for dir in / /usr /usr/local /usr/local/share /etc /etc/lightdm; do
    [ -d "$dir" ] && [ ! -L "$dir" ] && [ "$(stat -c '%u' "$dir")" = 0 ] \
        || exit 2
    dir_mode="$(stat -c '%a' "$dir")"
    (( (8#$dir_mode & 8#22) == 0 )) || exit 2
done
paths=(
    /usr/local/sbin/plebian-os-provision
    /usr/local/sbin/plebian-os-install-deps
    /usr/local/sbin/plebian-os-passwd
    /usr/local/bin/plebian-os-update
    /etc/systemd/system/plebian-os-firstboot.service
    /usr/local/sbin/plebian-os-firstboot-attempt
    /usr/local/share/plebian-os/VERSION
    /usr/local/share/plebian-os/wallpapers/plebian-os.png
    /usr/local/share/doc/plebian-os/installer/ATTRIBUTION.md
    /usr/local/share/doc/plebian-os/COPYING.GPL-2
    /etc/lightdm/lightdm-gtk-greeter.conf.d/50-plebian-os.conf
    /usr/local/bin/pleb-session
    /usr/share/xsessions/pleb.desktop
    /usr/local/bin/kilix
    /usr/local/bin/pleb
    /usr/local/share/doc/pleb/RECOVERY.md
)
managed_dirs=(
    /usr/local/share/plebian-os
    /usr/local/share/plebian-os/wallpapers
    /usr/local/share/doc
    /usr/local/share/doc/plebian-os
    /usr/local/share/doc/plebian-os/installer
    /usr/local/share/doc/pleb
    /etc/lightdm/lightdm-gtk-greeter.conf.d
)
new_paths=()
cleanup_new() {
    local path
    for path in "${new_paths[@]:-}"; do
        [ -n "$path" ] && rm -rf -- "$path"
    done
}
trap cleanup_new EXIT
# Prepare every old object beside its destination before changing any path.
for i in "${!paths[@]}"; do
    [ -f "$txn/$i.present" ] || continue
    dest="${paths[$i]}"
    mkdir -p -- "$(dirname "$dest")"
    new="$(dirname "$dest")/.$(basename "$dest").plebian-os-restore.$$"
    cp -a -- "$txn/items/$i" "$new"
    new_paths[$i]="$new"
done
for i in "${!paths[@]}"; do
    dest="${paths[$i]}"
    if [ -f "$txn/$i.present" ]; then
        mv -fT -- "${new_paths[$i]}" "$dest"
        new_paths[$i]=""
    else
        rm -rf -- "$dest"
    fi
done
for ((i=${#managed_dirs[@]}-1; i>=0; i--)); do
    [ -f "$txn/dir.$i.present" ] && continue
    dir="${managed_dirs[$i]}"
    if [ -d "$dir" ] && [ ! -L "$dir" ]; then
        rmdir -- "$dir"
    elif [ -e "$dir" ] || [ -L "$dir" ]; then
        exit 1
    fi
done
systemctl daemon-reload
trap - EXIT
cleanup_new
ROOT_RESTORE
}

remove_root_stack_snapshot() {
    local root_txn="$1"
    local -a elevate=()
    validate_root_transaction_dir "$root_txn" || return 1
    [ "$(id -u)" = 0 ] || elevate=(sudo)
    "${elevate[@]}" bash -s -- "$root_txn" <<'ROOT_CLEAN'
set -euo pipefail
txn="$1"
case "$txn" in /var/lib/plebian-os/update-rollback.*) ;; *) exit 2 ;; esac
[ -d "$txn" ] && [ ! -L "$txn" ] && [ "$(stat -c '%u' "$txn")" = 0 ] || exit 2
mode="$(stat -c '%a' "$txn")"
(( (8#$mode & 8#077) == 0 )) || exit 2
rm -rf -- "$txn"
ROOT_CLEAN
}

restore_stack_checkout() {
    local dir="$1" key="$2" label="$3" existed head ref branch dirty
    existed="$(cat "$_STACK_TXN_DIR/$key.existed" 2>/dev/null || echo 0)"
    if [ "$existed" = 0 ]; then
        if [ -e "$dir" ] || [ -L "$dir" ]; then
            # It was created by this update. Move it out of the live location
            # but retain it with the recovery state in case anything external
            # wrote into it while the command was running.
            mv -- "$dir" "$_STACK_TXN_DIR/$key.created" || return 1
            _STACK_TXN_RETAIN=1
            warn "$label was newly created; preserved it at $_STACK_TXN_DIR/$key.created"
        fi
        return 0
    fi
    [ -d "$dir/.git" ] || [ -f "$dir/.git" ] || return 1
    dirty="$(git -C "$dir" status --porcelain --untracked-files=normal 2>/dev/null)" \
        || return 1
    if [ -n "$dirty" ]; then
        warn "$label acquired local changes while the updater was running; preserving them and retaining recovery state"
        return 1
    fi
    head="$(cat "$_STACK_TXN_DIR/$key.head")"
    ref="$(cat "$_STACK_TXN_DIR/$key.ref")"
    if [ -n "$ref" ]; then
        branch="${ref#refs/heads/}"
        git -C "$dir" checkout "$branch" >/dev/null 2>&1 \
            && git -C "$dir" reset --hard "$head" >/dev/null 2>&1
    else
        git -C "$dir" checkout --detach "$head" >/dev/null 2>&1 \
            && git -C "$dir" reset --hard "$head" >/dev/null 2>&1
    fi
}

restore_stack_path() {
    local path="$1" key="$2" kind="${3:-tree}" tmp
    if [ "$kind" = file ]; then
        [ ! -d "$path" ] || [ -L "$path" ] || return 1
        if [ -f "$_STACK_TXN_DIR/$key.present" ]; then
            mkdir -p -- "$(dirname "$path")" || return 1
            tmp="$(mktemp "${path}.restore.XXXXXX")" || return 1
            rm -f -- "$tmp" || return 1
            if ! cp -a -- "$_STACK_TXN_DIR/$key" "$tmp" \
                || ! mv -Tf -- "$tmp" "$path"; then
                rm -f -- "$tmp"
                return 1
            fi
        else
            rm -f -- "$path" || return 1
        fi
    else
        rm -rf -- "$path" || return 1
        if [ -f "$_STACK_TXN_DIR/$key.present" ]; then
            mkdir -p -- "$(dirname "$path")" || return 1
            cp -a -- "$_STACK_TXN_DIR/$key" "$path" || return 1
        fi
    fi
}

validate_kilix_fork_stamp_path() {
    local stamp="$KILIX_STATE_DIRECTORY/fork-built-ref" owner mode links
    if [ -e "$stamp" ] || [ -L "$stamp" ]; then
        [ -f "$stamp" ] && [ ! -L "$stamp" ] \
            || die "refusing unsafe Kilix fork-build stamp: $stamp"
        owner="$(stat -c '%u' -- "$stamp" 2>/dev/null)" \
            || die "could not inspect Kilix fork-build stamp: $stamp"
        [ "$owner" = "$EUID" ] \
            || die "Kilix fork-build stamp is not owned by the updating user: $stamp"
        mode="$(stat -c '%a' -- "$stamp" 2>/dev/null)" \
            || die "could not inspect Kilix fork-build stamp mode: $stamp"
        [ "$mode" = 600 ] \
            || die "Kilix fork-build stamp must have mode 0600: $stamp"
        links="$(stat -c '%h' -- "$stamp" 2>/dev/null)" \
            || die "could not inspect Kilix fork-build stamp links: $stamp"
        [ "$links" = 1 ] \
            || die "Kilix fork-build stamp must have exactly one hard link: $stamp"
    fi
}

validate_legacy_kilix_fork_stamp_path() {
    local stamp="$PLEB_STATE_HOME/kilix-fork-built-ref" owner links
    if [ -e "$stamp" ] || [ -L "$stamp" ]; then
        [ -f "$stamp" ] && [ ! -L "$stamp" ] \
            || die "refusing unsafe legacy Pleb-side Kilix fork stamp: $stamp"
        owner="$(stat -c '%u' -- "$stamp" 2>/dev/null)" \
            || die "could not inspect legacy Pleb-side Kilix fork stamp: $stamp"
        [ "$owner" = "$EUID" ] \
            || die "legacy Pleb-side Kilix fork stamp is not owned by the updating user: $stamp"
        links="$(stat -c '%h' -- "$stamp" 2>/dev/null)" \
            || die "could not inspect legacy Pleb-side Kilix fork stamp links: $stamp"
        [ "$links" = 1 ] \
            || die "legacy Pleb-side Kilix fork stamp must have exactly one hard link: $stamp"
    fi
}

kilix_generation_entry_identity() {
    local path="$1" output="$2" device inode target
    if [ -L "$path" ]; then
        target="$(readlink -- "$path")" || return 1
        [[ "$target" =~ ^generations/build\.[A-Za-z0-9]+$ ]] || return 1
        kilix_generation_target_is_contained "$target" || return 1
        device="$(stat -c '%d' -- "$path")" || return 1
        inode="$(stat -c '%i' -- "$path")" || return 1
        printf 'symlink\t%s\t%s\t%s\n' "$device" "$inode" "$target" >"$output"
    elif [ -d "$path" ]; then
        device="$(stat -c '%d' -- "$path")" || return 1
        inode="$(stat -c '%i' -- "$path")" || return 1
        printf 'directory\t%s\t%s\n' "$device" "$inode" >"$output"
    elif [ -e "$path" ]; then
        return 1
    else
        printf '%s\n' absent >"$output"
    fi
}

kilix_generation_target_is_contained() {
    local target="$1" build_root candidate candidate_root
    [[ "$target" =~ ^generations/build\.[A-Za-z0-9]+$ ]] || return 1
    candidate="$KILIX_BUILD_DIRECTORY/$target"
    [ -d "$candidate" ] && [ ! -L "$candidate" ] || return 1
    build_root="$(cd "$KILIX_BUILD_DIRECTORY" && pwd -P)" || return 1
    candidate_root="$(cd "$candidate" && pwd -P)" || return 1
    [ "$candidate_root" = "$build_root/$target" ]
}

kilix_generation_target() {
    local entry="$1" target
    [ -L "$entry" ] || return 1
    target="$(readlink -- "$entry")" || return 1
    [[ "$target" =~ ^generations/build\.[A-Za-z0-9]+$ ]] || return 1
    printf '%s\n' "$target"
}

collect_unreferenced_kilix_generation() {
    local target="$1" link path owner
    [[ "$target" =~ ^generations/build\.[A-Za-z0-9]+$ ]] || return 1
    for link in current previous prepared; do
        if [ -L "$KILIX_BUILD_DIRECTORY/$link" ] \
            && [ "$(readlink -- "$KILIX_BUILD_DIRECTORY/$link")" = "$target" ]; then
            return 0
        fi
    done
    path="$KILIX_BUILD_DIRECTORY/$target"
    [ -e "$path" ] || [ -L "$path" ] || return 0
    kilix_generation_target_is_contained "$target" || return 1
    owner="$(stat -c '%u' -- "$path" 2>/dev/null)" || return 1
    [ "$owner" = "$EUID" ] || return 1
    rm -rf -- "$path"
}

kilix_engine_park_path() {
    local park
    park="$(cat "$_STACK_TXN_DIR/kilix-engine.park" 2>/dev/null || true)"
    [ -n "$park" ] || return 1
    [ "$(dirname "$park")" = "$KILIX_BUILD_DIRECTORY" ] || return 1
    [[ "$(basename "$park")" =~ ^\.plebian-os-update\.[A-Za-z0-9]+$ ]] || return 1
    printf '%s\n' "$park"
}

snapshot_kilix_engine_generation() {
    local current="$KILIX_BUILD_DIRECTORY/current"
    local previous="$KILIX_BUILD_DIRECTORY/previous"
    kilix_generation_entry_identity "$current" \
        "$_STACK_TXN_DIR/kilix-engine.current.identity" \
        || die "refusing unsafe Kilix current generation entry: $current"
    kilix_generation_entry_identity "$previous" \
        "$_STACK_TXN_DIR/kilix-engine.previous.identity" \
        || die "refusing unsafe Kilix previous generation entry: $previous"
    if [ -L "$current" ]; then
        cp -a -- "$current" "$_STACK_TXN_DIR/kilix-engine.current.entry" \
            || die "could not snapshot the Kilix current generation entry"
    fi
    printf '%s\n' 0 >"$_STACK_TXN_DIR/kilix-engine.previous.parked"
}

begin_kilix_engine_mutation() {
    local previous="$KILIX_BUILD_DIRECTORY/previous" park
    if [ -e "$previous" ] || [ -L "$previous" ]; then
        park="$(mktemp -d "$KILIX_BUILD_DIRECTORY/.plebian-os-update.XXXXXX")" \
            || die "could not create Kilix generation rollback state"
        chmod 0700 -- "$park" \
            || die "could not protect Kilix generation rollback state"
        printf '%s\n' "$park" >"$_STACK_TXN_DIR/kilix-engine.park"
        mv -- "$previous" "$park/previous" \
            || die "could not park the previous Kilix generation"
        printf '%s\n' 1 >"$_STACK_TXN_DIR/kilix-engine.previous.parked"
    fi
}

remove_kilix_generation_entry() {
    local entry="$1"
    if [ -d "$entry" ] && [ ! -L "$entry" ]; then
        rm -rf -- "$entry"
    elif [ -e "$entry" ] || [ -L "$entry" ]; then
        rm -f -- "$entry"
    fi
}

restore_kilix_engine_generation() {
    local current="$KILIX_BUILD_DIRECTORY/current"
    local previous="$KILIX_BUILD_DIRECTORY/previous"
    local old_current current_after previous_after park parked new_target=""
    old_current="$(cat "$_STACK_TXN_DIR/kilix-engine.current.identity")" \
        || return 1
    kilix_generation_entry_identity "$current" \
        "$_STACK_TXN_DIR/kilix-engine.current.after" || return 1
    current_after="$(cat "$_STACK_TXN_DIR/kilix-engine.current.after")" \
        || return 1
    if [ "$current_after" != "$old_current" ]; then
        new_target="$(kilix_generation_target "$current" 2>/dev/null || true)"
        if [ "$old_current" != absent ]; then
            kilix_generation_entry_identity "$previous" \
                "$_STACK_TXN_DIR/kilix-engine.previous.after" || return 1
            previous_after="$(cat "$_STACK_TXN_DIR/kilix-engine.previous.after")" \
                || return 1
            if [ "$previous_after" = "$old_current" ]; then
                remove_kilix_generation_entry "$current" || return 1
                mv -- "$previous" "$current" || return 1
            elif [ -L "$_STACK_TXN_DIR/kilix-engine.current.entry" ]; then
                remove_kilix_generation_entry "$current" || return 1
                cp -a -- "$_STACK_TXN_DIR/kilix-engine.current.entry" "$current" \
                    || return 1
            else
                return 1
            fi
        else
            remove_kilix_generation_entry "$current" || return 1
        fi
    fi
    parked="$(cat "$_STACK_TXN_DIR/kilix-engine.previous.parked" 2>/dev/null || echo 0)"
    if [ "$parked" = 1 ]; then
        park="$(kilix_engine_park_path)" || return 1
        [ -e "$park/previous" ] || [ -L "$park/previous" ] || return 1
        [ ! -e "$previous" ] && [ ! -L "$previous" ] || return 1
        mv -- "$park/previous" "$previous" || return 1
        rmdir -- "$park" || return 1
    else
        [ ! -e "$previous" ] && [ ! -L "$previous" ] || return 1
    fi
    [ -z "$new_target" ] \
        || collect_unreferenced_kilix_generation "$new_target" || return 1
}

commit_kilix_engine_generation() {
    local current="$KILIX_BUILD_DIRECTORY/current"
    local previous="$KILIX_BUILD_DIRECTORY/previous"
    local old_current current_after previous_after park parked retired_target=""
    old_current="$(cat "$_STACK_TXN_DIR/kilix-engine.current.identity")" \
        || return 1
    kilix_generation_entry_identity "$current" \
        "$_STACK_TXN_DIR/kilix-engine.current.commit" || return 1
    current_after="$(cat "$_STACK_TXN_DIR/kilix-engine.current.commit")" \
        || return 1
    parked="$(cat "$_STACK_TXN_DIR/kilix-engine.previous.parked" 2>/dev/null || echo 0)"
    if [ "$current_after" = "$old_current" ]; then
        if [ "$parked" = 1 ]; then
            park="$(kilix_engine_park_path)" || return 1
            [ ! -e "$previous" ] && [ ! -L "$previous" ] || return 1
            mv -- "$park/previous" "$previous" || return 1
            rmdir -- "$park" || return 1
        else
            [ ! -e "$previous" ] && [ ! -L "$previous" ] || return 1
        fi
        return 0
    fi
    if [ "$old_current" != absent ]; then
        kilix_generation_entry_identity "$previous" \
            "$_STACK_TXN_DIR/kilix-engine.previous.commit" || return 1
        previous_after="$(cat "$_STACK_TXN_DIR/kilix-engine.previous.commit")" \
            || return 1
        [ "$previous_after" = "$old_current" ] || return 1
    else
        [ ! -e "$previous" ] && [ ! -L "$previous" ] || return 1
    fi
    if [ "$parked" = 1 ]; then
        park="$(kilix_engine_park_path)" || return 1
        retired_target="$(kilix_generation_target "$park/previous" 2>/dev/null || true)"
        if ! remove_kilix_generation_entry "$park/previous" \
            || ! rmdir -- "$park"; then
            warn "stack committed, but old Kilix generation recovery data remains at $park"
            return 0
        fi
        if [ -n "$retired_target" ] \
            && ! collect_unreferenced_kilix_generation "$retired_target"; then
            warn "stack committed, but superseded Kilix generation cleanup was incomplete: $retired_target"
        fi
    fi
}

rollback_stack_transaction() {
    local failed=0
    warn "stack update failed; restoring the previous coherent installation"

    # Restore parent repositories before their nested submodule checkout.
    restore_stack_checkout "$PLEB_DIR" pleb pleb || failed=1
    if [ ! -f "$_STACK_TXN_DIR/os.skipped" ]; then
        restore_stack_checkout "$PLEBIAN_OS_DIR" os plebian-os || failed=1
    fi
    restore_stack_checkout "$KILIX_DIR" kilix kilix || failed=1
    if [ -f "$_STACK_TXN_DIR/kilix-src.existed" ]; then
        restore_stack_checkout "$KILIX_DIR/src" kilix-src "kilix source" || failed=1
    fi
    restore_stack_checkout "$KILIX95_DIR" kilix95 "kilix 95" || failed=1

    restore_stack_path "$KILIX_PREBUILT_HOME" kilix-prebuilt || failed=1
    restore_kilix_engine_generation || failed=1
    restore_stack_path "$KILIX_STATE_DIRECTORY/fork-built-ref" fork-stamp file || failed=1
    restore_stack_path "$PLEB_STATE_HOME/kilix-fork-built-ref" legacy-fork-stamp file || failed=1
    restore_root_stack_snapshot "$_STACK_ROOT_TXN_DIR" || failed=1

    if [ "$failed" = 0 ]; then
        log "restored the pre-update OS layer, checkout positions, engine, and Pleb install outputs"
    else
        warn "automatic stack rollback was incomplete; recovery data retained at $_STACK_TXN_DIR and $_STACK_ROOT_TXN_DIR"
    fi
    return "$failed"
}

stack_transaction_cleanup() {
    local rc=$? rollback_ok=1
    trap - EXIT INT TERM HUP
    set +e
    [ -z "${_OS_LAYER_STAGE:-}" ] || rm -rf -- "$_OS_LAYER_STAGE"
    if [ "${_STACK_TXN_ACTIVE:-0}" = 1 ] \
        && [ "${_STACK_TXN_COMMITTED:-0}" != 1 ]; then
        [ "$rc" -ne 0 ] || rc=1
        rollback_stack_transaction || rollback_ok=0
    fi
    if [ "$rollback_ok" = 1 ] && [ "${_STACK_TXN_RETAIN:-0}" != 1 ]; then
        [ -z "${_STACK_ROOT_TXN_DIR:-}" ] \
            || remove_root_stack_snapshot "$_STACK_ROOT_TXN_DIR" || rollback_ok=0
        [ "$rollback_ok" = 0 ] || rm -rf -- "${_STACK_TXN_DIR:-}"
    fi
    if [ "$rollback_ok" = 0 ] || [ "${_STACK_TXN_RETAIN:-0}" = 1 ]; then
        warn "stack update recovery data was retained for manual inspection"
        [ "$rollback_ok" = 1 ] || rc=70
    fi
    release_kilix_transaction_lock
    exit "$rc"
}

begin_stack_transaction() {
    require_standard_install_destinations
    acquire_kilix_transaction_lock
    validate_kilix_fork_stamp_path
    validate_legacy_kilix_fork_stamp_path
    mkdir -p "$PLEB_STATE_HOME"
    chmod 0700 "$PLEB_STATE_HOME" 2>/dev/null || true
    _STACK_TXN_DIR="$(mktemp -d "$PLEB_STATE_HOME/stack-rollback.XXXXXX")" \
        || die "could not create stack rollback state"
    chmod 0700 "$_STACK_TXN_DIR"
    trap stack_transaction_cleanup EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    trap 'exit 129' HUP

    record_stack_checkout "$PLEB_DIR" pleb pleb
    case "$PLEBIAN_OS_SELF_UPDATE" in
        1|yes|true|on) record_stack_checkout "$PLEBIAN_OS_DIR" os plebian-os ;;
        *) : >"$_STACK_TXN_DIR/os.skipped" ;;
    esac
    record_stack_checkout "$KILIX_DIR" kilix kilix
    if [ -d "$KILIX_DIR/src/.git" ] || [ -f "$KILIX_DIR/src/.git" ]; then
        record_stack_checkout "$KILIX_DIR/src" kilix-src "kilix source"
    fi
    record_stack_checkout "$KILIX95_DIR" kilix95 "kilix 95"
    snapshot_stack_path "$KILIX_PREBUILT_HOME" kilix-prebuilt
    snapshot_kilix_engine_generation
    snapshot_stack_path "$KILIX_STATE_DIRECTORY/fork-built-ref" fork-stamp
    snapshot_stack_path "$PLEB_STATE_HOME/kilix-fork-built-ref" legacy-fork-stamp
    _STACK_ROOT_TXN_DIR="$(begin_root_stack_snapshot)" \
        || die "could not snapshot the installed OS/Pleb layer"
    validate_root_transaction_dir "$_STACK_ROOT_TXN_DIR" \
        || die "root stack snapshot returned an unsafe recovery path"
    _STACK_TXN_ACTIVE=1
    begin_kilix_engine_mutation
    rm -f -- "$PLEB_STATE_HOME/kilix-fork-built-ref" \
        || die "could not retire the legacy Pleb-side Kilix fork stamp"
}

commit_stack_transaction() {
    commit_kilix_engine_generation \
        || die "could not commit the coherent Kilix generation transaction"
    _STACK_TXN_COMMITTED=1
    _STACK_TXN_ACTIVE=0
    if ! remove_root_stack_snapshot "$_STACK_ROOT_TXN_DIR"; then
        warn "updated stack is coherent, but root recovery data could not be removed: $_STACK_ROOT_TXN_DIR"
    else
        _STACK_ROOT_TXN_DIR=""
    fi
    rm -rf -- "$_STACK_TXN_DIR"
    _STACK_TXN_DIR=""
    trap - EXIT INT TERM HUP
    release_kilix_transaction_lock
}

test_fail_after_boundary() {
    [ "${PLEBIAN_OS_UPDATE_TEST_FAIL_AFTER:-}" != "$1" ] \
        || die "injected stack update failure after $1"
}

restart_session_after_commit() {
    [ "$restart_arg" = --restart ] || return 0
    local -a elevate=()
    [ "$(id -u)" = 0 ] || elevate=(sudo)
    log "stack committed; restarting LightDM to load it"
    if command -v systemd-run >/dev/null 2>&1; then
        # $svc is intentionally expanded by the detached root shell.
        # shellcheck disable=SC2016
        if ! "${elevate[@]}" systemd-run \
            --unit="plebian-os-restart-lightdm-$$" --collect \
            --description="Restart LightDM after Plebian-OS update" \
            /bin/sh -c '
svc=lightdm
systemctl stop "$svc" --no-block >/dev/null 2>&1 || true
sleep 2
systemctl kill -s KILL "$svc" >/dev/null 2>&1 || true
systemctl reset-failed "$svc" >/dev/null 2>&1 || true
systemctl start "$svc"
'; then
            warn "stack updated, but the requested LightDM restart could not be scheduled"
        fi
    elif ! "${elevate[@]}" systemctl restart lightdm; then
        warn "stack updated, but the requested LightDM restart failed"
    fi
}

validate_checkout_origin() {
    local dir="$1" repo="$2" label="$3" remote
    [ -d "$dir/.git" ] || return 0
    remote="$(git -C "$dir" config --get remote.origin.url 2>/dev/null || true)"
    if [ -n "$remote" ] && [ "$remote" != "$repo" ] \
        && [ "${PLEBIAN_OS_TRUST_EXISTING_CHECKOUT:-0}" != 1 ]; then
        die "$label checkout at $dir has origin '$remote', expected '$repo' (set PLEBIAN_OS_TRUST_EXISTING_CHECKOUT=1 to override)"
    fi
}

require_clean_pinned_checkout() {
    local dir="$1" label="$2" dirty
    dirty="$(git -C "$dir" status --porcelain --untracked-files=normal 2>/dev/null)" \
        || die "could not inspect pinned $label checkout at $dir"
    [ -z "$dirty" ] \
        || die "pinned $label checkout at $dir has local changes; refusing to overwrite or execute it"
}

checkout_pinned_ref() {
    local dir="$1" ref="$2" label="$3" resolved actual
    require_clean_pinned_checkout "$dir" "$label"
    # FETCH_HEAD binds resolution to the object returned by this origin fetch;
    # do not trust an existing local tag with the same spelling.
    git -C "$dir" fetch --force origin "$ref" \
        || die "$label fetch of pinned ref $ref failed"
    resolved="$(git -C "$dir" rev-parse --verify 'FETCH_HEAD^{commit}' 2>/dev/null)" \
        || die "pinned $label ref $ref did not resolve to a commit"
    git -C "$dir" checkout --detach "$resolved" \
        || die "could not check out pinned $label ref $ref ($resolved)"
    actual="$(git -C "$dir" rev-parse --verify HEAD 2>/dev/null)" \
        || die "could not verify pinned $label checkout HEAD"
    [ "$actual" = "$resolved" ] \
        || die "pinned $label checkout resolved to $resolved but HEAD is $actual"
    require_clean_pinned_checkout "$dir" "$label"
    log "$label pinned ref $ref verified at $actual"
}

update_pleb_checkout() {
    validate_checkout_origin "$PLEB_DIR" "$PLEB_REPO" "pleb"
    if [ -n "$PLEB_REF" ]; then
        log "checking out pinned pleb ref $PLEB_REF"
        checkout_pinned_ref "$PLEB_DIR" "$PLEB_REF" "pleb"
        return
    fi

    if [ -n "$PLEB_BRANCH" ]; then
        log "updating pleb branch $PLEB_BRANCH"
        git -C "$PLEB_DIR" fetch --prune origin "$PLEB_BRANCH"
        current="$(git -C "$PLEB_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo HEAD)"
        if [ "$current" != "$PLEB_BRANCH" ]; then
            if git -C "$PLEB_DIR" show-ref --verify --quiet "refs/heads/$PLEB_BRANCH"; then
                git -C "$PLEB_DIR" checkout "$PLEB_BRANCH"
            else
                git -C "$PLEB_DIR" checkout --track -b "$PLEB_BRANCH" "origin/$PLEB_BRANCH"
            fi
        fi
        git -C "$PLEB_DIR" merge --ff-only "origin/$PLEB_BRANCH"
        return
    fi

    git -C "$PLEB_DIR" pull --ff-only
}

# Refresh (or clone) the plebian-os checkout, honoring an exact PLEBIAN_OS_REF
# pin or a branch, mirroring update_pleb_checkout. Any enabled self-update
# failure aborts the command; reporting success after a partial OS redeploy is
# worse than leaving the previous coherent layer in place.
update_os_checkout() {
    local current
    if [ -d "$PLEBIAN_OS_DIR/.git" ]; then
        local remote
        remote="$(git -C "$PLEBIAN_OS_DIR" config --get remote.origin.url 2>/dev/null || true)"
        if [ -n "$remote" ] && [ "$remote" != "$PLEBIAN_OS_REPO" ] \
            && [ "${PLEBIAN_OS_TRUST_EXISTING_CHECKOUT:-0}" != 1 ]; then
            warn "plebian-os checkout at $PLEBIAN_OS_DIR has origin '$remote', expected '$PLEBIAN_OS_REPO' — skipping self-update"
            return 1
        fi
    else
        log "cloning plebian-os -> $PLEBIAN_OS_DIR"
        local clone_args=()
        [ -n "$PLEBIAN_OS_BRANCH" ] && clone_args=(--branch "$PLEBIAN_OS_BRANCH")
        git clone "${clone_args[@]}" "$PLEBIAN_OS_REPO" "$PLEBIAN_OS_DIR" || return 1
    fi
    if [ -n "$PLEBIAN_OS_REF" ]; then
        checkout_pinned_ref "$PLEBIAN_OS_DIR" "$PLEBIAN_OS_REF" "plebian-os"
        return 0
    fi
    if [ -n "$PLEBIAN_OS_BRANCH" ]; then
        git -C "$PLEBIAN_OS_DIR" fetch --prune origin "$PLEBIAN_OS_BRANCH" || return 1
        current="$(git -C "$PLEBIAN_OS_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo HEAD)"
        if [ "$current" != "$PLEBIAN_OS_BRANCH" ]; then
            if git -C "$PLEBIAN_OS_DIR" show-ref --verify --quiet "refs/heads/$PLEBIAN_OS_BRANCH"; then
                git -C "$PLEBIAN_OS_DIR" checkout "$PLEBIAN_OS_BRANCH" || return 1
            else
                git -C "$PLEBIAN_OS_DIR" checkout --track -b "$PLEBIAN_OS_BRANCH" "origin/$PLEBIAN_OS_BRANCH" || return 1
            fi
        fi
        git -C "$PLEBIAN_OS_DIR" merge --ff-only "origin/$PLEBIAN_OS_BRANCH" || return 1
        return 0
    fi
    git -C "$PLEBIAN_OS_DIR" pull --ff-only || return 1
}

# Copy every required OS-layer file into an unprivileged staging directory and
# validate the complete set before any privileged destination is touched.
stage_and_validate_os_layer() {
    local prov="$PLEBIAN_OS_DIR/provision" stage="$1" file
    local wallpaper_expected wallpaper_update_expected wallpaper_actual
    local attribution_expected attribution_update_expected attribution_actual
    local license_expected license_update_expected license_actual
    local required=(
        "$prov/plebian-os-provision.sh"
        "$prov/install-deps.sh"
        "$prov/plebian-os-passwd"
        "$prov/plebian-os-update.sh"
        "$prov/plebian-os-firstboot.service"
        "$prov/plebian-os-firstboot-attempt"
        "$PLEBIAN_OS_DIR/VERSION"
        "$PLEBIAN_OS_DIR/assets/desktop/plebian-os.png"
        "$PLEBIAN_OS_DIR/assets/installer/ATTRIBUTION.md"
        "$PLEBIAN_OS_DIR/assets/COPYING.GPL-2"
        "$prov/lightdm-gtk-greeter.conf"
    )
    for file in "${required[@]}"; do
        [ -f "$file" ] || die "OS-layer checkout is incomplete; required file missing: $file"
    done
    [ ! -L "$PLEBIAN_OS_DIR/assets/desktop/plebian-os.png" ] \
        || die "OS-layer checkout has an unsafe wallpaper symlink"
    [ ! -L "$PLEBIAN_OS_DIR/assets/installer/ATTRIBUTION.md" ] \
        || die "OS-layer checkout has an unsafe attribution symlink"
    [ ! -L "$PLEBIAN_OS_DIR/assets/COPYING.GPL-2" ] \
        || die "OS-layer checkout has an unsafe GPL license symlink"
    [ ! -L "$prov/lightdm-gtk-greeter.conf" ] \
        || die "OS-layer checkout has an unsafe LightDM greeter configuration symlink"

    install -m 0755 "$prov/plebian-os-provision.sh" "$stage/plebian-os-provision"
    install -m 0755 "$prov/install-deps.sh" "$stage/plebian-os-install-deps"
    install -m 0755 "$prov/plebian-os-passwd" "$stage/plebian-os-passwd"
    install -m 0755 "$prov/plebian-os-update.sh" "$stage/plebian-os-update"
    install -m 0644 "$prov/plebian-os-firstboot.service" "$stage/plebian-os-firstboot.service"
    install -m 0755 "$prov/plebian-os-firstboot-attempt" "$stage/plebian-os-firstboot-attempt"
    install -m 0644 "$PLEBIAN_OS_DIR/VERSION" "$stage/VERSION"
    install -m 0644 "$PLEBIAN_OS_DIR/assets/desktop/plebian-os.png" "$stage/desktop-wallpaper.png"
    install -m 0644 "$PLEBIAN_OS_DIR/assets/installer/ATTRIBUTION.md" "$stage/ATTRIBUTION.md"
    install -m 0644 "$PLEBIAN_OS_DIR/assets/COPYING.GPL-2" "$stage/COPYING.GPL-2"
    install -m 0644 "$prov/lightdm-gtk-greeter.conf" "$stage/lightdm-gtk-greeter.conf"

    bash -n "$stage/plebian-os-provision" "$stage/plebian-os-install-deps" \
        "$stage/plebian-os-update" "$stage/plebian-os-firstboot-attempt" \
        || die "staged OS-layer shell validation failed"
    python3 - "$stage/plebian-os-passwd" <<'PY' \
        || die "staged password helper Python validation failed"
import pathlib
import sys
compile(pathlib.Path(sys.argv[1]).read_text(), sys.argv[1], "exec")
PY
    if ! grep -q '^\[Unit\]$' "$stage/plebian-os-firstboot.service" \
        || ! grep -q '^\[Service\]$' "$stage/plebian-os-firstboot.service" \
        || ! grep -q '^ExecStart=/usr/local/sbin/plebian-os-provision$' "$stage/plebian-os-firstboot.service" \
        || ! grep -q '^ExecStopPost=-/bin/rm -f /etc/sudoers.d/plebian-os-provision$' "$stage/plebian-os-firstboot.service" \
        || ! grep -q '^ExecCondition=/usr/local/sbin/plebian-os-firstboot-attempt check$' "$stage/plebian-os-firstboot.service"; then
        die "staged firstboot unit is missing required lifecycle directives"
    fi
    if command -v systemd-analyze >/dev/null 2>&1; then
        systemd-analyze verify "$stage/plebian-os-firstboot.service" >/dev/null 2>&1 \
            || die "staged firstboot unit failed systemd-analyze verification"
    fi
    grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' "$stage/VERSION" \
        || die "staged VERSION is not semantic MAJOR.MINOR.PATCH"
    python3 - "$stage/desktop-wallpaper.png" <<'PY' \
        || die "staged desktop wallpaper is not a 1920x1080 RGB PNG"
import pathlib
import struct
import sys

data = pathlib.Path(sys.argv[1]).read_bytes()
if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
    raise SystemExit(1)
ihdr = struct.unpack(">IIBBBBB", data[16:29])
if ihdr != (1920, 1080, 8, 2, 0, 0, 0):
    raise SystemExit(1)
PY
    wallpaper_expected="$(sed -n \
        's/^DESKTOP_WALLPAPER_SHA256=\([0-9a-f]\{64\}\)$/\1/p' \
        "$stage/plebian-os-provision")"
    [[ "$wallpaper_expected" =~ ^[0-9a-f]{64}$ ]] \
        || die "staged provisioner has no exact desktop wallpaper checksum"
    wallpaper_update_expected="$(sed -n \
        's/^DESKTOP_WALLPAPER_SHA256=\([0-9a-f]\{64\}\)$/\1/p' \
        "$stage/plebian-os-update")"
    [[ "$wallpaper_update_expected" =~ ^[0-9a-f]{64}$ ]] \
        || die "staged updater has no exact desktop wallpaper checksum"
    wallpaper_actual="$(sha256sum "$stage/desktop-wallpaper.png" | awk '{print $1}')"
    [ "$wallpaper_actual" = "$wallpaper_expected" ] \
        || die "staged desktop wallpaper does not match the staged provisioner"
    [ "$wallpaper_actual" = "$wallpaper_update_expected" ] \
        || die "staged desktop wallpaper does not match the staged updater"

    python3 - "$stage/ATTRIBUTION.md" "$stage/COPYING.GPL-2" <<'PY' \
        || die "staged artwork attribution/license text contract failed"
import pathlib
import sys

attribution = pathlib.Path(sys.argv[1]).read_bytes()
license_text = pathlib.Path(sys.argv[2]).read_bytes()
for data in (attribution, license_text):
    if not data or b"\x00" in data or not data.endswith(b"\n"):
        raise SystemExit(1)
    data.decode("utf-8")
if b"../COPYING.GPL-2" not in attribution or b"GPL-2.0-or-later" not in attribution:
    raise SystemExit(1)
if b"GNU GENERAL PUBLIC LICENSE" not in license_text or b"Version 2, June 1991" not in license_text:
    raise SystemExit(1)
PY
    attribution_expected="$(sed -n \
        's/^INSTALLER_ATTRIBUTION_SHA256=\([0-9a-f]\{64\}\)$/\1/p' \
        "$stage/plebian-os-provision")"
    attribution_update_expected="$(sed -n \
        's/^INSTALLER_ATTRIBUTION_SHA256=\([0-9a-f]\{64\}\)$/\1/p' \
        "$stage/plebian-os-update")"
    license_expected="$(sed -n \
        's/^GPL2_LICENSE_SHA256=\([0-9a-f]\{64\}\)$/\1/p' \
        "$stage/plebian-os-provision")"
    license_update_expected="$(sed -n \
        's/^GPL2_LICENSE_SHA256=\([0-9a-f]\{64\}\)$/\1/p' \
        "$stage/plebian-os-update")"
    for file in "$attribution_expected" "$attribution_update_expected" \
        "$license_expected" "$license_update_expected"; do
        [[ "$file" =~ ^[0-9a-f]{64}$ ]] \
            || die "staged provisioner/updater has no exact artwork notice checksum"
    done
    attribution_actual="$(sha256sum "$stage/ATTRIBUTION.md" | awk '{print $1}')"
    license_actual="$(sha256sum "$stage/COPYING.GPL-2" | awk '{print $1}')"
    [ "$attribution_actual" = "$attribution_expected" ] \
        && [ "$attribution_actual" = "$attribution_update_expected" ] \
        || die "staged artwork attribution does not match the staged provisioner/updater"
    [ "$license_actual" = "$license_expected" ] \
        && [ "$license_actual" = "$license_update_expected" ] \
        || die "staged GPL license does not match the staged provisioner/updater"
    python3 - "$stage/lightdm-gtk-greeter.conf" <<'PY' \
        || die "staged LightDM greeter configuration contract failed"
import pathlib
import sys

text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
lines = {line.strip() for line in text.splitlines()
         if line.strip() and not line.lstrip().startswith("#")}
if lines != {
    "[greeter]",
    "background=/usr/local/share/plebian-os/wallpapers/plebian-os.png",
    "user-background=false",
} or "Debian" in text:
    raise SystemExit(1)
PY
}

# Privileged deployment is transactional: first place every new file beside its
# destination, then back up every old file, and only then atomically rename each
# staged inode into place. Any error restores the previous complete set and
# exits nonzero; success is logged only after systemd has reloaded the new unit.
deploy_staged_os_layer() {
    local stage="$1"
    shift
    local -a expected_hashes=("$@")
    local -a root_command
    [ "${#expected_hashes[@]}" -eq 11 ] \
        || die "OS-layer deployment requires one expected hash per staged file"
    if [ "$EUID" = 0 ]; then
        # A root-run updater stages root-owned files. Clear inherited sudo
        # metadata so the inner boundary cannot mistake the original login UID
        # for the owner of this root-created stage.
        root_command=(env -u SUDO_UID -u SUDO_GID -u SUDO_USER)
    else
        root_command=(sudo)
    fi
    "${root_command[@]}" bash -s -- "$stage" "${expected_hashes[@]}" <<'ROOT_DEPLOY'
set -euo pipefail
stage="$1"
shift
expected_hashes=("$@")
caller_uid="${SUDO_UID:-0}"
[[ "$caller_uid" =~ ^[0-9]+$ ]] || exit 2
[ "$EUID" = 0 ] || exit 2
if [ -n "${SUDO_UID:-}" ]; then
    [ "$caller_uid" -gt 0 ] || exit 2
else
    [ "$caller_uid" = 0 ] || exit 2
fi
[ -d "$stage" ] && [ ! -L "$stage" ] \
    && [ "$(stat -c '%u' "$stage")" = "$caller_uid" ] \
    && [ "$(stat -c '%a' "$stage")" = 700 ] || exit 2
names=(
    plebian-os-provision
    plebian-os-install-deps
    plebian-os-passwd
    plebian-os-update
    plebian-os-firstboot.service
    plebian-os-firstboot-attempt
    VERSION
    desktop-wallpaper.png
    ATTRIBUTION.md
    COPYING.GPL-2
    lightdm-gtk-greeter.conf
)
dests=(
    /usr/local/sbin/plebian-os-provision
    /usr/local/sbin/plebian-os-install-deps
    /usr/local/sbin/plebian-os-passwd
    /usr/local/bin/plebian-os-update
    /etc/systemd/system/plebian-os-firstboot.service
    /usr/local/sbin/plebian-os-firstboot-attempt
    /usr/local/share/plebian-os/VERSION
    /usr/local/share/plebian-os/wallpapers/plebian-os.png
    /usr/local/share/doc/plebian-os/installer/ATTRIBUTION.md
    /usr/local/share/doc/plebian-os/COPYING.GPL-2
    /etc/lightdm/lightdm-gtk-greeter.conf.d/50-plebian-os.conf
)
modes=(0755 0755 0755 0755 0644 0755 0644 0644 0644 0644 0644)
max_sizes=(33554432 33554432 33554432 33554432 33554432 33554432 33554432 33554432 1048576 1048576 1048576)
new_paths=() backup_paths=() existed=() changed=() created_dirs=()
[ "${#expected_hashes[@]}" -eq "${#names[@]}" ] || exit 2
[ "${#dests[@]}" -eq "${#names[@]}" ] || exit 2
[ "${#modes[@]}" -eq "${#names[@]}" ] || exit 2
[ "${#max_sizes[@]}" -eq "${#names[@]}" ] || exit 2
for hash in "${expected_hashes[@]}"; do
    [[ "$hash" =~ ^[0-9a-f]{64}$ ]] || exit 2
done

cleanup_transaction_files() {
    local path i
    for path in "${new_paths[@]:-}" "${backup_paths[@]:-}"; do
        [ -n "$path" ] && rm -f -- "$path"
    done
    for ((i=${#created_dirs[@]}-1; i>=0; i--)); do
        rmdir -- "${created_dirs[$i]}" 2>/dev/null || true
    done
}

rollback() {
    local rc=$? i rollback_ok=1
    [ "$rc" -ne 0 ] || rc=1
    trap - ERR INT TERM HUP
    set +e
    for ((i=${#dests[@]}-1; i>=0; i--)); do
        [ "${changed[$i]:-0}" = 1 ] || continue
        if [ "${existed[$i]:-0}" = 1 ]; then
            if mv -fT -- "${backup_paths[$i]}" "${dests[$i]}"; then
                backup_paths[$i]=""
            else
                rollback_ok=0
                printf 'plebian-os-update: rollback could not restore %s; backup retained at %s\n' \
                    "${dests[$i]}" "${backup_paths[$i]}" >&2
            fi
        else
            rm -f -- "${dests[$i]}" || rollback_ok=0
        fi
    done
    systemctl daemon-reload >/dev/null 2>&1 || true
    if [ "$rollback_ok" = 1 ]; then
        cleanup_transaction_files
    else
        printf '%s\n' 'plebian-os-update: rollback was incomplete; recovery files were preserved' >&2
        rc=70
    fi
    exit "$rc"
}
trap rollback ERR INT TERM HUP

# Distribution assets live below fixed root-owned directories. Reject any
# symlink or user-writable fixed ancestor before root stages bytes beneath it.
for dir in / /usr /usr/local /usr/local/share /etc /etc/lightdm; do
    if [ ! -d "$dir" ] || [ -L "$dir" ]; then
        printf 'plebian-os-update: unsafe distribution asset destination ancestor: %s\n' "$dir" >&2
        false
    fi
    owner="$(stat -c '%u' "$dir")"
    mode="$(stat -c '%a' "$dir")"
    if [ "$owner" != 0 ] || (( (8#$mode & 8#22) != 0 )); then
        printf 'plebian-os-update: unsafe distribution asset ancestor ownership/mode: %s\n' "$dir" >&2
        false
    fi
done

# The managed children may be created here, but must remain root-controlled and
# traversable by the desktop user.
for dir in \
    /usr/local/share/plebian-os \
    /usr/local/share/plebian-os/wallpapers \
    /usr/local/share/doc \
    /usr/local/share/doc/plebian-os \
    /usr/local/share/doc/plebian-os/installer \
    /etc/lightdm/lightdm-gtk-greeter.conf.d; do
    if [ -L "$dir" ]; then
        printf 'plebian-os-update: unsafe distribution asset destination symlink: %s\n' "$dir" >&2
        false
    elif [ -e "$dir" ] && [ ! -d "$dir" ]; then
        printf 'plebian-os-update: distribution asset destination is not a directory: %s\n' "$dir" >&2
        false
    elif [ ! -e "$dir" ]; then
        install -d -o root -g root -m 0755 -- "$dir"
        created_dirs+=("$dir")
    fi
    owner="$(stat -c '%u' "$dir")"
    mode="$(stat -c '%a' "$dir")"
    if [ "$owner" != 0 ] || (( (8#$mode & 8#22) != 0 )) \
        || (( (8#$mode & 8#1) == 0 )); then
        printf 'plebian-os-update: unsafe distribution asset destination ownership/mode: %s\n' "$dir" >&2
        false
    fi
done

# Root-stage every file privately on the destination filesystem before changing
# anything. Open each caller-owned source exactly once with O_NOFOLLOW, reject
# non-regular or writable inputs and bound the read, so a same-user path race
# cannot make root follow a FIFO/device/symlink or disclose substituted bytes.
for i in "${!dests[@]}"; do
    dest="${dests[$i]}"
    mkdir -p -- "$(dirname "$dest")"
    new="$(dirname "$dest")/.$(basename "$dest").plebian-os-new.$$"
    new_paths[$i]="$new"
    python3 - "$stage/${names[$i]}" "$new" "$caller_uid" "${max_sizes[$i]}" <<'PY'
import os
import stat
import sys

source, destination, caller_uid_text, limit_text = sys.argv[1:]
caller_uid = int(caller_uid_text)
limit = int(limit_text)
read_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK | os.O_NOFOLLOW
source_fd = os.open(source, read_flags)
destination_fd = None
try:
    source_stat = os.fstat(source_fd)
    if not stat.S_ISREG(source_stat.st_mode):
        raise RuntimeError("OS-layer source is not a regular file")
    if source_stat.st_uid != caller_uid:
        raise RuntimeError("OS-layer source is not owned by the invoking updater")
    if source_stat.st_mode & 0o022:
        raise RuntimeError("OS-layer source is group/world writable")
    if source_stat.st_size > limit:
        raise RuntimeError("OS-layer source exceeds its copy limit")
    write_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
    destination_fd = os.open(destination, write_flags, 0o600)
    os.fchown(destination_fd, 0, 0)
    os.fchmod(destination_fd, 0o600)
    total = 0
    while True:
        chunk = os.read(source_fd, min(1024 * 1024, limit + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise RuntimeError("OS-layer source grew beyond its copy limit")
        view = memoryview(chunk)
        while view:
            written = os.write(destination_fd, view)
            view = view[written:]
    os.fsync(destination_fd)
except BaseException:
    if destination_fd is not None:
        os.close(destination_fd)
        destination_fd = None
    try:
        os.unlink(destination)
    except FileNotFoundError:
        pass
    raise
finally:
    os.close(source_fd)
    if destination_fd is not None:
        os.close(destination_fd)
PY
done

# Re-validate the root-owned copies, not only the user-owned staging directory.
# Expected hashes were computed before entering sudo. Verify the exact bytes of
# every root-owned copy first, closing a same-user replacement race while the
# caller is waiting at the privilege prompt.
for i in "${!new_paths[@]}"; do
    actual="$(sha256sum "${new_paths[$i]}" | awk '{print $1}')"
    [ "$actual" = "${expected_hashes[$i]}" ] || {
        printf 'plebian-os-update: staged %s changed before privileged deployment\n' \
            "${names[$i]}" >&2
        false
    }
done
bash -n "${new_paths[0]}" "${new_paths[1]}" "${new_paths[3]}" "${new_paths[5]}"
python3 - "${new_paths[2]}" <<'PY'
import pathlib
import sys
compile(pathlib.Path(sys.argv[1]).read_text(), sys.argv[1], "exec")
PY
grep -q '^\[Unit\]$' "${new_paths[4]}" \
    && grep -q '^\[Service\]$' "${new_paths[4]}" \
    && grep -q '^ExecStart=/usr/local/sbin/plebian-os-provision$' "${new_paths[4]}" \
    && grep -q '^ExecCondition=/usr/local/sbin/plebian-os-firstboot-attempt check$' "${new_paths[4]}"
grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' "${new_paths[6]}"
python3 - "${new_paths[7]}" <<'PY'
import pathlib
import struct
import sys

data = pathlib.Path(sys.argv[1]).read_bytes()
if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
    raise SystemExit(1)
if struct.unpack(">IIBBBBB", data[16:29]) != (1920, 1080, 8, 2, 0, 0, 0):
    raise SystemExit(1)
PY
python3 - "${new_paths[8]}" "${new_paths[9]}" <<'PY'
import pathlib
import sys

attribution = pathlib.Path(sys.argv[1]).read_bytes()
license_text = pathlib.Path(sys.argv[2]).read_bytes()
for data in (attribution, license_text):
    if not data or b"\x00" in data or not data.endswith(b"\n"):
        raise SystemExit(1)
    data.decode("utf-8")
if b"../COPYING.GPL-2" not in attribution or b"GPL-2.0-or-later" not in attribution:
    raise SystemExit(1)
if b"GNU GENERAL PUBLIC LICENSE" not in license_text or b"Version 2, June 1991" not in license_text:
    raise SystemExit(1)
PY
python3 - "${new_paths[10]}" <<'PY'
import pathlib
import sys

text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
lines = {line.strip() for line in text.splitlines()
         if line.strip() and not line.lstrip().startswith("#")}
if lines != {
    "[greeter]",
    "background=/usr/local/share/plebian-os/wallpapers/plebian-os.png",
    "user-background=false",
} or "Debian" in text:
    raise SystemExit(1)
PY

# Nothing becomes destination-readable until all private root-owned copies have
# passed their exact hashes and type-specific validation.
for i in "${!new_paths[@]}"; do
    [ "$(stat -c '%u' "${new_paths[$i]}")" = 0 ] \
        && [ "$(stat -c '%g' "${new_paths[$i]}")" = 0 ] \
        && [ "$(stat -c '%a' "${new_paths[$i]}")" = 600 ]
    chmod "${modes[$i]}" -- "${new_paths[$i]}"
done

# Back up the complete old set before the first rename.
for i in "${!dests[@]}"; do
    dest="${dests[$i]}"
    backup="$(dirname "$dest")/.$(basename "$dest").plebian-os-old.$$"
    backup_paths[$i]="$backup"
    if [ -e "$dest" ] || [ -L "$dest" ]; then
        cp -a -- "$dest" "$backup"
        existed[$i]=1
    else
        existed[$i]=0
    fi
done

for i in "${!dests[@]}"; do
    changed[$i]=1
    mv -fT -- "${new_paths[$i]}" "${dests[$i]}"
    new_paths[$i]=""
done
systemctl daemon-reload
trap - ERR INT TERM HUP
cleanup_transaction_files
ROOT_DEPLOY
}

# Redeploy the OS-layer scripts from the checkout into their system locations, so
# the next boot/run uses the updated code. Replacing this running script's own
# inode is safe; the current shell keeps reading the already-open script.
self_update_os_layer() {
    case "$PLEBIAN_OS_SELF_UPDATE" in
        1|yes|true|on) ;;
        *) log "OS-layer self-update disabled (PLEBIAN_OS_SELF_UPDATE=$PLEBIAN_OS_SELF_UPDATE)"; return 0 ;;
    esac
    log "refreshing the Plebian-OS layer ($PLEBIAN_OS_DIR)"
    update_os_checkout || die "OS-layer checkout refresh failed"
    command -v sha256sum >/dev/null 2>&1 \
        || die "sha256sum is required to bind the validated OS-layer stage"
    local stage file
    local -a stage_names stage_hashes
    stage_names=(
        plebian-os-provision
        plebian-os-install-deps
        plebian-os-passwd
        plebian-os-update
        plebian-os-firstboot.service
        plebian-os-firstboot-attempt
        VERSION
        desktop-wallpaper.png
        ATTRIBUTION.md
        COPYING.GPL-2
        lightdm-gtk-greeter.conf
    )
    mkdir -p "$PLEBIAN_OS_SESSION_HOME"
    stage="$(mktemp -d "$PLEBIAN_OS_SESSION_HOME/os-layer.XXXXXX")"
    _OS_LAYER_STAGE="$stage"
    stage_and_validate_os_layer "$stage"
    for file in "${stage_names[@]}"; do
        stage_hashes+=("$(sha256sum "$stage/$file" | awk '{print $1}')")
    done
    log "atomically redeploying the validated OS layer (needs root)"
    deploy_staged_os_layer "$stage" "${stage_hashes[@]}" \
        || die "OS-layer deployment failed and was rolled back"
    _DEPLOYED_DESKTOP_WALLPAPER_SHA256="${stage_hashes[7]}"
    rm -rf "$stage"
    _OS_LAYER_STAGE=""
    log "OS layer refreshed to $(cat "$PLEBIAN_OS_DIR/VERSION" 2>/dev/null || echo unknown)"
    log "  (a full 'sudo plebian-os-provision' re-run applies deeper OS-layer changes, e.g. new deps)"
}

stack_env=(
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
    "PLEB_UPDATE_LOCK_FD=9"
    "KILIX_DIR=$KILIX_DIR"
    "KILIX_STORAGE_HOME=$KILIX_STORAGE_HOME"
    "KILIX_CONFIG_HOME=$KILIX_CONFIG_HOME"
    "KILIX_STATE_DIRECTORY=$KILIX_STATE_DIRECTORY"
    "KILIX_TRANSACTION_LOCK_FD=${KILIX_TRANSACTION_LOCK_FD:-}"
    "KILIX_TRANSACTION_LOCK_PATH=${KILIX_TRANSACTION_LOCK_PATH:-}"
    "KILIX_CACHE_HOME=$KILIX_CACHE_HOME"
    "KILIX_SESSION_HOME=$KILIX_SESSION_HOME"
    "KILIX_BUILD_DIRECTORY=$KILIX_BUILD_DIRECTORY"
    "KILIX_DATA_HOME=$KILIX_DATA_HOME"
    "KILIX_DESKTOP_DIR=$KILIX_DESKTOP_DIR"
    "KILIX_PREBUILT_HOME=$KILIX_PREBUILT_HOME"
    "KILIX_REPO=$KILIX_REPO"
    "KILIX_BRANCH=$KILIX_BRANCH"
    "KILIX_REF=$KILIX_REF"
    "KILIX_PREBUILT_VERSION=$KILIX_PREBUILT_VERSION"
    "KILIX_PREBUILT_SHA256=$KILIX_PREBUILT_SHA256"
    "PLEBIAN_OS_BUILD_KILIX_FORK=$PLEBIAN_OS_BUILD_KILIX_FORK"
    "PLEBIAN_OS_KILIX_GO_MIN_VERSION=$PLEBIAN_OS_KILIX_GO_MIN_VERSION"
    "PLEBIAN_OS_KILIX_GO_VERSION=$PLEBIAN_OS_KILIX_GO_VERSION"
    "PLEBIAN_OS_KILIX_GO_SHA256_AMD64=$PLEBIAN_OS_KILIX_GO_SHA256_AMD64"
    "PLEBIAN_OS_KILIX_GO_SHA256_ARM64=$PLEBIAN_OS_KILIX_GO_SHA256_ARM64"
    "KILIX_DESKTOP_PROVIDER=$KILIX_DESKTOP_PROVIDER"
    "KILIX_DESKTOP_COMMAND=$KILIX_DESKTOP_COMMAND"
    "KILIX_DESKTOP_NAME=$KILIX_DESKTOP_NAME"
    "KILIX_DESKTOP_FLAVOR=$KILIX_DESKTOP_FLAVOR"
    "PLEB_DESKTOP=$PLEB_DESKTOP"
    "KILIX95_AUTO_INSTALL=$KILIX95_AUTO_INSTALL"
    "KILIX95_STORAGE_HOME=$KILIX95_STORAGE_HOME"
    "KILIX95_CONFIG_HOME=$KILIX95_CONFIG_HOME"
    "KILIX95_STATE_HOME=$KILIX95_STATE_HOME"
    "KILIX95_CACHE_HOME=$KILIX95_CACHE_HOME"
    "KILIX95_SESSION_HOME=$KILIX95_SESSION_HOME"
    "KILIX95_DATA_HOME=$KILIX95_DATA_HOME"
    "KILIX95_DIR=$KILIX95_DIR"
    "KILIX95_REPO=$KILIX95_REPO"
    "KILIX95_BRANCH=$KILIX95_BRANCH"
    "KILIX95_REF=$KILIX95_REF"
)

# Focused regression harnesses source the transaction functions without
# executing an update. This hook is deliberately test-namespaced and checked
# only after all production functions have been parsed.
if [ "${PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY:-0}" = 1 ]; then
    return 0
fi

# Pleb does its system writes via sudo; on a non-passwordless box a clickable
# "update" action would silently prompt or fail. Warn early rather than hang.
if [ "$(id -u)" != 0 ] && ! sudo -n true 2>/dev/null; then
    warn "passwordless sudo unavailable — 'pleb install'/OS-layer redeploy may prompt for a password or fail in a non-interactive (Start-menu) context"
fi

# Refuse before taking the privileged snapshot rather than discovering a missing
# mandatory checkout after the OS layer has already changed.
if [ ! -d "$PLEB_DIR/.git" ]; then
    die "no pleb checkout at $PLEB_DIR — cannot update stack"
fi

# Capture the complete old runtime boundary before the first checkout or
# deployed file is changed. The inherited fd keeps Pleb's nested component
# transaction under the same serialization lock.
begin_stack_transaction

# Refresh the OS layer itself (provisioner/deps/update helper) first, then pleb.
self_update_os_layer
test_fail_after_boundary os-layer

log "updating pleb   ($PLEB_DIR)"
update_pleb_checkout
test_fail_after_boundary pleb-checkout

if [ -x "$PLEB_DIR/bin/pleb" ]; then
    log "re-running 'pleb install' (re-links commands + refreshes the session)"
    env "${stack_env[@]}" "$PLEB_DIR/bin/pleb" install
    test_fail_after_boundary pleb-install
    log "updating kilix, submodules, fork engine, and optional desktop provider"
    env "${stack_env[@]}" "$PLEB_DIR/bin/pleb" update --no-restart
    test_fail_after_boundary component-update
else
    warn "no pleb at $PLEB_DIR/bin/pleb — cannot run 'pleb install'"
    exit 1
fi

commit_stack_transaction
if ! seed_desktop_wallpaper_after_commit; then
    warn "stack committed, but wallpaper state seeding failed; existing state was not changed"
fi
log "Plebian-OS stack updated."
restart_session_after_commit
if [ "$restart_arg" = --no-restart ]; then
    log "restart the session to load the changes when ready:  sudo systemctl restart lightdm"
fi
