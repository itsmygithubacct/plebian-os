#!/usr/bin/env bash
# plebian-os-update.sh — refresh the whole Plebian-OS software stack.
#
# Pulls the latest kilix, optional kilix-95 desktop, AND pleb, then re-runs
# `pleb install`. This is MORE than `pleb update` (which updates from the pleb
# side): it also updates the pleb repo itself and re-applies the install — the
# kilix/pleb command symlinks, the pleb-session launcher, and the xsession entry
# — so a change to any of those lands too.
#
# Run as the Pleb user; `pleb install` elevates via sudo where it needs root.
# Deployed to the target as /usr/local/bin/plebian-os-update and offered as a
# clickable item in the kilix 95 Start menu.
set -euo pipefail

log()  { printf '\033[1;35m[plebian-os]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[plebian-os]\033[0m %s\n' "$*" >&2; }

[ -r /etc/pleb/session.env ] && . /etc/pleb/session.env

KILIX_DIR="${KILIX_DIR:-$HOME/kilix}"
KILIX_REPO="${KILIX_REPO:-https://github.com/itsmygithubacct/kilix.git}"
KILIX_BRANCH="${KILIX_BRANCH:-}"
KILIX_REF="${KILIX_REF:-}"
KILIX_DESKTOP_PROVIDER="${KILIX_DESKTOP_PROVIDER:-external}"
KILIX_DESKTOP_COMMAND="${KILIX_DESKTOP_COMMAND:-}"
KILIX_DESKTOP_NAME="${KILIX_DESKTOP_NAME:-desktop}"
KILIX95_DIR="${KILIX95_DIR:-$HOME/kilix-95}"
KILIX95_REPO="${KILIX95_REPO:-https://github.com/itsmygithubacct/kilix-95.git}"
KILIX95_BRANCH="${KILIX95_BRANCH:-}"
KILIX95_REF="${KILIX95_REF:-}"
PLEB_DESKTOP="${PLEB_DESKTOP:-0}"
PLEB_DIR="${PLEB_DIR:-$HOME/pleb}"

if [ -d "$PLEB_DIR/.git" ]; then
    log "updating pleb   ($PLEB_DIR)"
    git -C "$PLEB_DIR" pull --ff-only
else
    warn "no pleb checkout at $PLEB_DIR — cannot update stack"
    exit 1
fi

if [ -x "$PLEB_DIR/bin/pleb" ]; then
    log "re-running 'pleb install' (re-links commands + refreshes the session)"
    env KILIX_DIR="$KILIX_DIR" KILIX_REPO="$KILIX_REPO" \
        ${KILIX_BRANCH:+KILIX_BRANCH="$KILIX_BRANCH"} \
        ${KILIX_REF:+KILIX_REF="$KILIX_REF"} \
        KILIX_DESKTOP_PROVIDER="$KILIX_DESKTOP_PROVIDER" \
        KILIX_DESKTOP_COMMAND="$KILIX_DESKTOP_COMMAND" \
        KILIX_DESKTOP_NAME="$KILIX_DESKTOP_NAME" \
        PLEB_DESKTOP="$PLEB_DESKTOP" KILIX95_DIR="$KILIX95_DIR" \
        KILIX95_REPO="$KILIX95_REPO" ${KILIX95_BRANCH:+KILIX95_BRANCH="$KILIX95_BRANCH"} \
        ${KILIX95_REF:+KILIX95_REF="$KILIX95_REF"} \
        "$PLEB_DIR/bin/pleb" install
    log "updating kilix, submodules, fork engine, and optional kilix 95"
    env KILIX_DIR="$KILIX_DIR" KILIX_REPO="$KILIX_REPO" \
        ${KILIX_BRANCH:+KILIX_BRANCH="$KILIX_BRANCH"} \
        ${KILIX_REF:+KILIX_REF="$KILIX_REF"} \
        KILIX_DESKTOP_PROVIDER="$KILIX_DESKTOP_PROVIDER" \
        KILIX_DESKTOP_COMMAND="$KILIX_DESKTOP_COMMAND" \
        KILIX_DESKTOP_NAME="$KILIX_DESKTOP_NAME" \
        PLEB_DESKTOP="$PLEB_DESKTOP" KILIX95_DIR="$KILIX95_DIR" \
        KILIX95_REPO="$KILIX95_REPO" ${KILIX95_BRANCH:+KILIX95_BRANCH="$KILIX95_BRANCH"} \
        ${KILIX95_REF:+KILIX95_REF="$KILIX95_REF"} \
        "$PLEB_DIR/bin/pleb" update --no-restart
else
    warn "no pleb at $PLEB_DIR/bin/pleb — cannot run 'pleb install'"
    exit 1
fi

log "Plebian-OS stack updated."
log "restart the session to load the changes when ready:  sudo systemctl restart lightdm"
