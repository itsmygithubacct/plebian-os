#!/usr/bin/env bash
# plebian-os-update.sh — refresh the whole Plebian-OS software stack.
#
# Pulls or pins kilix, optional desktop provider, AND pleb, then re-runs
# `pleb install`. This is MORE than `pleb update` (which updates from the pleb
# side): it also updates the pleb repo itself and re-applies the install — the
# kilix/pleb command symlinks, the pleb-session launcher, and the xsession entry
# — so a change to any of those lands too. It ALSO refreshes the Plebian-OS layer
# itself (the provisioner, dependency installer, and this helper) from a
# plebian-os checkout, so OS-layer fixes reach installed systems, not just
# pleb/kilix. Disable that with PLEBIAN_OS_SELF_UPDATE=0.
#
# Run as the Pleb user; `pleb install` elevates via sudo where it needs root.
# Deployed to the target as /usr/local/bin/plebian-os-update and offered by
# desktop providers as a clickable stack update action.
set -euo pipefail

log()  { printf '\033[1;35m[plebian-os]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[plebian-os]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[plebian-os] %s\033[0m\n' "$*" >&2; exit 1; }

[ -r /etc/pleb/session.env ] && . /etc/pleb/session.env

PLEB_DIR="${PLEB_DIR:-$HOME/pleb}"
PLEB_REPO="${PLEB_REPO:-https://github.com/itsmygithubacct/pleb.git}"
PLEB_BRANCH="${PLEB_BRANCH:-}"
PLEB_REF="${PLEB_REF:-}"
KILIX_DIR="${KILIX_DIR:-$HOME/kilix}"
KILIX_REPO="${KILIX_REPO:-https://github.com/itsmygithubacct/kilix.git}"
KILIX_BRANCH="${KILIX_BRANCH:-}"
KILIX_REF="${KILIX_REF:-}"
KILIX_PREBUILT_VERSION="${KILIX_PREBUILT_VERSION:-}"
KILIX_PREBUILT_SHA256="${KILIX_PREBUILT_SHA256:-}"
PLEBIAN_OS_BUILD_KILIX_FORK="${PLEBIAN_OS_BUILD_KILIX_FORK:-1}"
PLEBIAN_OS_KILIX_GO_MIN_VERSION="${PLEBIAN_OS_KILIX_GO_MIN_VERSION:-1.26}"
KILIX_DESKTOP_PROVIDER="${KILIX_DESKTOP_PROVIDER:-external}"
KILIX_DESKTOP_COMMAND="${KILIX_DESKTOP_COMMAND:-}"
KILIX_DESKTOP_NAME="${KILIX_DESKTOP_NAME:-desktop}"
KILIX_DESKTOP_FLAVOR="${KILIX_DESKTOP_FLAVOR:-}"
KILIX95_DIR="${KILIX95_DIR:-$HOME/kilix-95}"
KILIX95_REPO="${KILIX95_REPO:-https://github.com/itsmygithubacct/kilix-95.git}"
KILIX95_BRANCH="${KILIX95_BRANCH:-}"
KILIX95_REF="${KILIX95_REF:-}"
KILIX95_AUTO_INSTALL="${KILIX95_AUTO_INSTALL:-1}"
PLEB_DESKTOP="${PLEB_DESKTOP:-0}"

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

case "${1:-}" in
    --version|-V) echo "plebian-os-update $PLEBIAN_OS_VERSION"; exit 0 ;;
    -h|--help) sed -n '2,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//'; exit 0 ;;
    "") ;;
    *) die "unknown option: $1 (try --help)" ;;
esac

validate_checkout_origin() {
    local dir="$1" repo="$2" label="$3" remote
    [ -d "$dir/.git" ] || return 0
    remote="$(git -C "$dir" config --get remote.origin.url 2>/dev/null || true)"
    if [ -n "$remote" ] && [ "$remote" != "$repo" ] \
        && [ "${PLEBIAN_OS_TRUST_EXISTING_CHECKOUT:-0}" != 1 ]; then
        die "$label checkout at $dir has origin '$remote', expected '$repo' (set PLEBIAN_OS_TRUST_EXISTING_CHECKOUT=1 to override)"
    fi
}

update_pleb_checkout() {
    validate_checkout_origin "$PLEB_DIR" "$PLEB_REPO" "pleb"
    if [ -n "$PLEB_REF" ]; then
        log "checking out pinned pleb ref $PLEB_REF"
        git -C "$PLEB_DIR" fetch --tags origin
        git -C "$PLEB_DIR" checkout --detach "$PLEB_REF"
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
# pin or a branch, mirroring update_pleb_checkout. Returns non-zero on any
# failure so the caller can warn-and-continue rather than abort the whole update.
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
        git -C "$PLEBIAN_OS_DIR" fetch --tags origin || return 1
        git -C "$PLEBIAN_OS_DIR" checkout --detach "$PLEBIAN_OS_REF" || return 1
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

# Redeploy the OS-layer scripts from the checkout into their system locations, so
# the next boot/run uses the updated code. Replacing this running script's own
# file is safe: git/install swap the inode, and our open fd keeps the old content
# for the rest of this run; the new code takes effect on the next invocation.
self_update_os_layer() {
    case "$PLEBIAN_OS_SELF_UPDATE" in
        1|yes|true|on) ;;
        *) log "OS-layer self-update disabled (PLEBIAN_OS_SELF_UPDATE=$PLEBIAN_OS_SELF_UPDATE)"; return 0 ;;
    esac
    log "refreshing the Plebian-OS layer ($PLEBIAN_OS_DIR)"
    if ! update_os_checkout; then
        warn "OS-layer checkout refresh failed — continuing with the pleb/kilix update only"
        return 0
    fi
    local prov="$PLEBIAN_OS_DIR/provision"
    if [ ! -f "$prov/plebian-os-provision.sh" ]; then
        warn "no provisioner at $prov — skipping OS-layer script redeploy"
        return 0
    fi
    local SUDO=""
    [ "$(id -u)" = 0 ] || SUDO="sudo"
    log "redeploying OS-layer scripts into place (needs root)"
    $SUDO install -m 0755 "$prov/plebian-os-provision.sh" /usr/local/sbin/plebian-os-provision \
        || warn "failed to update /usr/local/sbin/plebian-os-provision"
    $SUDO install -m 0755 "$prov/install-deps.sh" /usr/local/sbin/plebian-os-install-deps \
        || warn "failed to update /usr/local/sbin/plebian-os-install-deps"
    if [ -f "$prov/plebian-os-passwd" ]; then
        $SUDO install -m 0755 "$prov/plebian-os-passwd" /usr/local/sbin/plebian-os-passwd \
            || warn "failed to update /usr/local/sbin/plebian-os-passwd (nag helper)"
    fi
    if [ -f "$prov/plebian-os-firstboot.service" ]; then
        $SUDO install -m 0644 "$prov/plebian-os-firstboot.service" \
            /etc/systemd/system/plebian-os-firstboot.service \
            || warn "failed to update the firstboot unit (harmless: it is already disabled)"
    fi
    $SUDO install -m 0755 "$prov/plebian-os-update.sh" /usr/local/bin/plebian-os-update \
        || warn "failed to update /usr/local/bin/plebian-os-update"
    log "OS layer refreshed to $(cat "$PLEBIAN_OS_DIR/VERSION" 2>/dev/null || echo unknown)"
    log "  (a full 'sudo plebian-os-provision' re-run applies deeper OS-layer changes, e.g. new deps)"
}

stack_env=(
    "KILIX_DIR=$KILIX_DIR"
    "KILIX_REPO=$KILIX_REPO"
    "KILIX_BRANCH=$KILIX_BRANCH"
    "KILIX_REF=$KILIX_REF"
    "KILIX_PREBUILT_VERSION=$KILIX_PREBUILT_VERSION"
    "KILIX_PREBUILT_SHA256=$KILIX_PREBUILT_SHA256"
    "PLEBIAN_OS_BUILD_KILIX_FORK=$PLEBIAN_OS_BUILD_KILIX_FORK"
    "PLEBIAN_OS_KILIX_GO_MIN_VERSION=$PLEBIAN_OS_KILIX_GO_MIN_VERSION"
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

# Pleb does its system writes via sudo; on a non-passwordless box a clickable
# "update" action would silently prompt or fail. Warn early rather than hang.
if [ "$(id -u)" != 0 ] && ! sudo -n true 2>/dev/null; then
    warn "passwordless sudo unavailable — 'pleb install'/OS-layer redeploy may prompt for a password or fail in a non-interactive (Start-menu) context"
fi

# Refresh the OS layer itself (provisioner/deps/update helper) first, then pleb.
self_update_os_layer

if [ -d "$PLEB_DIR/.git" ]; then
    log "updating pleb   ($PLEB_DIR)"
    update_pleb_checkout
else
    warn "no pleb checkout at $PLEB_DIR — cannot update stack"
    exit 1
fi

if [ -x "$PLEB_DIR/bin/pleb" ]; then
    log "re-running 'pleb install' (re-links commands + refreshes the session)"
    env "${stack_env[@]}" "$PLEB_DIR/bin/pleb" install
    log "updating kilix, submodules, fork engine, and optional desktop provider"
    env "${stack_env[@]}" "$PLEB_DIR/bin/pleb" update --no-restart
else
    warn "no pleb at $PLEB_DIR/bin/pleb — cannot run 'pleb install'"
    exit 1
fi

log "Plebian-OS stack updated."
log "restart the session to load the changes when ready:  sudo systemctl restart lightdm"
