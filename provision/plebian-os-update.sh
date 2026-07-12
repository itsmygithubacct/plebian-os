#!/usr/bin/env bash
# plebian-os-update.sh — refresh the whole Plebian-OS software stack.
#
# Pulls or pins kilix, optional desktop provider, AND pleb, then re-runs
# `pleb install`. This is MORE than `pleb update` (which updates from the pleb
# side): it also updates the pleb repo itself and re-applies the install — the
# kilix/pleb command symlinks, the pleb-session launcher, and the xsession entry
# — so a change to any of those lands too. It ALSO refreshes the Plebian-OS layer
# itself (the provisioner, dependency installer, password helper, systemd unit,
# version marker, and this helper) from a plebian-os checkout. Updates are
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

PLEB_DIR="${PLEB_DIR:-$HOME/pleb}"
PLEB_REPO="${PLEB_REPO:-https://github.com/itsmygithubacct/pleb.git}"
PLEB_BRANCH="${PLEB_BRANCH:-}"
PLEB_REF="${PLEB_REF:-}"
PLEB_STATE_HOME="${PLEB_STATE_HOME:-${XDG_STATE_HOME:-$HOME/.local/state}/pleb}"
KILIX_DIR="${KILIX_DIR:-$HOME/kilix}"
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
KILIX95_DIR="${KILIX95_DIR:-$HOME/kilix-95}"
KILIX95_REPO="${KILIX95_REPO:-https://github.com/itsmygithubacct/kilix-95.git}"
KILIX95_BRANCH="${KILIX95_BRANCH:-}"
KILIX95_REF="${KILIX95_REF:-}"
KILIX95_AUTO_INSTALL="${KILIX95_AUTO_INSTALL:-1}"
PLEB_DESKTOP="${PLEB_DESKTOP:-0}"

# `pleb install` normally owns these four system paths. The stack updater
# snapshots the fixed, distribution-managed destinations before invoking it so
# a later failure can restore the complete previous install. Custom install
# destinations remain supported by `pleb install` directly, but are rejected by
# this privileged whole-stack transaction rather than feeding caller-controlled
# paths into its root rollback routine.
SESSION_BIN_DST="${SESSION_BIN_DST:-/usr/local/bin/pleb-session}"
XSESSION_DST="${XSESSION_DST:-/usr/share/xsessions/pleb.desktop}"
KILIX_LINK="${KILIX_LINK:-/usr/local/bin/kilix}"
PLEB_LINK="${PLEB_LINK:-/usr/local/bin/pleb}"

# Plebian-OS layer self-update: the OS's own scripts (provisioner, dependency
# installer, this update helper) come from a plebian-os checkout so an installed
# system can pull OS-layer fixes — not just pleb/kilix — with one command.
PLEBIAN_OS_DIR="${PLEBIAN_OS_DIR:-$HOME/plebian-os}"
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

acquire_update_lock() {
    local lock="$PLEB_STATE_HOME/update.lock"
    command -v flock >/dev/null 2>&1 \
        || die "flock is required to serialize stack updates (install util-linux)"
    mkdir -p "$PLEB_STATE_HOME"
    chmod 0700 "$PLEB_STATE_HOME" 2>/dev/null || true
    exec 9>>"$lock"
    flock -n 9 \
        || die "another Pleb/Plebian-OS update is already running (lock: $lock)"
}
acquire_update_lock

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
        || [ "$PLEB_LINK" != /usr/local/bin/pleb ]; then
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
    /usr/local/bin/pleb-session
    /usr/share/xsessions/pleb.desktop
    /usr/local/bin/kilix
    /usr/local/bin/pleb
)
cleanup() {
    rc=$?
    trap - EXIT
    [ "$rc" -eq 0 ] || rm -rf -- "$txn"
    exit "$rc"
}
trap cleanup EXIT
mkdir "$txn/items"
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
paths=(
    /usr/local/sbin/plebian-os-provision
    /usr/local/sbin/plebian-os-install-deps
    /usr/local/sbin/plebian-os-passwd
    /usr/local/bin/plebian-os-update
    /etc/systemd/system/plebian-os-firstboot.service
    /usr/local/sbin/plebian-os-firstboot-attempt
    /usr/local/share/plebian-os/VERSION
    /usr/local/bin/pleb-session
    /usr/share/xsessions/pleb.desktop
    /usr/local/bin/kilix
    /usr/local/bin/pleb
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
    local path="$1" key="$2"
    rm -rf -- "$path" || return 1
    if [ -f "$_STACK_TXN_DIR/$key.present" ]; then
        mkdir -p -- "$(dirname "$path")" || return 1
        cp -a -- "$_STACK_TXN_DIR/$key" "$path" || return 1
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

    restore_stack_path "$KILIX_DIR/kitty.app" kilix-prebuilt || failed=1
    restore_stack_path "$KILIX_DIR/src/kitty/launcher/kitty" fork-kitty || failed=1
    restore_stack_path "$KILIX_DIR/src/kitty/launcher/kitten" fork-kitten || failed=1
    restore_stack_path "$PLEB_STATE_HOME/kilix-fork-built-ref" fork-stamp || failed=1
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
    exit "$rc"
}

begin_stack_transaction() {
    require_standard_install_destinations
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
    snapshot_stack_path "$KILIX_DIR/kitty.app" kilix-prebuilt
    snapshot_stack_path "$KILIX_DIR/src/kitty/launcher/kitty" fork-kitty
    snapshot_stack_path "$KILIX_DIR/src/kitty/launcher/kitten" fork-kitten
    snapshot_stack_path "$PLEB_STATE_HOME/kilix-fork-built-ref" fork-stamp
    _STACK_ROOT_TXN_DIR="$(begin_root_stack_snapshot)" \
        || die "could not snapshot the installed OS/Pleb layer"
    validate_root_transaction_dir "$_STACK_ROOT_TXN_DIR" \
        || die "root stack snapshot returned an unsafe recovery path"
    _STACK_TXN_ACTIVE=1
}

commit_stack_transaction() {
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
    local required=(
        "$prov/plebian-os-provision.sh"
        "$prov/install-deps.sh"
        "$prov/plebian-os-passwd"
        "$prov/plebian-os-update.sh"
        "$prov/plebian-os-firstboot.service"
        "$prov/plebian-os-firstboot-attempt"
        "$PLEBIAN_OS_DIR/VERSION"
    )
    for file in "${required[@]}"; do
        [ -f "$file" ] || die "OS-layer checkout is incomplete; required file missing: $file"
    done

    install -m 0755 "$prov/plebian-os-provision.sh" "$stage/plebian-os-provision"
    install -m 0755 "$prov/install-deps.sh" "$stage/plebian-os-install-deps"
    install -m 0755 "$prov/plebian-os-passwd" "$stage/plebian-os-passwd"
    install -m 0755 "$prov/plebian-os-update.sh" "$stage/plebian-os-update"
    install -m 0644 "$prov/plebian-os-firstboot.service" "$stage/plebian-os-firstboot.service"
    install -m 0755 "$prov/plebian-os-firstboot-attempt" "$stage/plebian-os-firstboot-attempt"
    install -m 0644 "$PLEBIAN_OS_DIR/VERSION" "$stage/VERSION"

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
}

# Privileged deployment is transactional: first place every new file beside its
# destination, then back up every old file, and only then atomically rename each
# staged inode into place. Any error restores the previous complete set and
# exits nonzero; success is logged only after systemd has reloaded the new unit.
deploy_staged_os_layer() {
    local stage="$1"
    shift
    local -a expected_hashes=("$@")
    local -a elevate=()
    [ "${#expected_hashes[@]}" -eq 7 ] \
        || die "OS-layer deployment requires one expected hash per staged file"
    [ "$(id -u)" = 0 ] || elevate=(sudo)
    "${elevate[@]}" bash -s -- "$stage" "${expected_hashes[@]}" <<'ROOT_DEPLOY'
set -euo pipefail
stage="$1"
shift
expected_hashes=("$@")
names=(
    plebian-os-provision
    plebian-os-install-deps
    plebian-os-passwd
    plebian-os-update
    plebian-os-firstboot.service
    plebian-os-firstboot-attempt
    VERSION
)
dests=(
    /usr/local/sbin/plebian-os-provision
    /usr/local/sbin/plebian-os-install-deps
    /usr/local/sbin/plebian-os-passwd
    /usr/local/bin/plebian-os-update
    /etc/systemd/system/plebian-os-firstboot.service
    /usr/local/sbin/plebian-os-firstboot-attempt
    /usr/local/share/plebian-os/VERSION
)
modes=(0755 0755 0755 0755 0644 0755 0644)
new_paths=() backup_paths=() existed=() changed=()
[ "${#expected_hashes[@]}" -eq "${#names[@]}" ] || exit 2
for hash in "${expected_hashes[@]}"; do
    [[ "$hash" =~ ^[0-9a-f]{64}$ ]] || exit 2
done

cleanup_transaction_files() {
    local path
    for path in "${new_paths[@]:-}" "${backup_paths[@]:-}"; do
        [ -n "$path" ] && rm -f -- "$path"
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

# Root-stage every file on the destination filesystem before changing anything.
for i in "${!dests[@]}"; do
    dest="${dests[$i]}"
    mkdir -p -- "$(dirname "$dest")"
    new="$(dirname "$dest")/.$(basename "$dest").plebian-os-new.$$"
    install -m "${modes[$i]}" -- "$stage/${names[$i]}" "$new"
    new_paths[$i]="$new"
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
        exit 1
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
    )
    stage="$(mktemp -d "${TMPDIR:-/tmp}/plebian-os-layer.XXXXXX")"
    _OS_LAYER_STAGE="$stage"
    stage_and_validate_os_layer "$stage"
    for file in "${stage_names[@]}"; do
        stage_hashes+=("$(sha256sum "$stage/$file" | awk '{print $1}')")
    done
    log "atomically redeploying the validated OS layer (needs root)"
    deploy_staged_os_layer "$stage" "${stage_hashes[@]}" \
        || die "OS-layer deployment failed and was rolled back"
    rm -rf "$stage"
    _OS_LAYER_STAGE=""
    log "OS layer refreshed to $(cat "$PLEBIAN_OS_DIR/VERSION" 2>/dev/null || echo unknown)"
    log "  (a full 'sudo plebian-os-provision' re-run applies deeper OS-layer changes, e.g. new deps)"
}

stack_env=(
    "PLEB_STATE_HOME=$PLEB_STATE_HOME"
    "PLEB_UPDATE_LOCK_FD=9"
    "KILIX_DIR=$KILIX_DIR"
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
log "Plebian-OS stack updated."
restart_session_after_commit
if [ "$restart_arg" = --no-restart ]; then
    log "restart the session to load the changes when ready:  sudo systemctl restart lightdm"
fi
