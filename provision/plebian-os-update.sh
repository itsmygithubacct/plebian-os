#!/usr/bin/env bash
# plebian-os-update.sh — refresh the whole Plebian-OS software stack.
#
# Pulls or pins kilix, optional desktop provider, AND pleb, then re-runs
# `pleb install`. This is MORE than `pleb update` (which updates from the pleb
# side): it also updates the pleb repo itself and re-applies the install — the
# kilix/pleb command symlinks, the pleb-session launcher, and the xsession entry
# — so a change to any of those lands too.
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
KILIX95_DIR="${KILIX95_DIR:-$HOME/kilix-95}"
KILIX95_REPO="${KILIX95_REPO:-https://github.com/itsmygithubacct/kilix-95.git}"
KILIX95_BRANCH="${KILIX95_BRANCH:-}"
KILIX95_REF="${KILIX95_REF:-}"
KILIX95_AUTO_INSTALL="${KILIX95_AUTO_INSTALL:-1}"
PLEB_DESKTOP="${PLEB_DESKTOP:-0}"

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
    "PLEB_DESKTOP=$PLEB_DESKTOP"
    "KILIX95_AUTO_INSTALL=$KILIX95_AUTO_INSTALL"
    "KILIX95_DIR=$KILIX95_DIR"
    "KILIX95_REPO=$KILIX95_REPO"
    "KILIX95_BRANCH=$KILIX95_BRANCH"
    "KILIX95_REF=$KILIX95_REF"
)

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
