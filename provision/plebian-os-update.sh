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
set -uo pipefail

log()  { printf '\033[1;35m[plebian-os]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[plebian-os]\033[0m %s\n' "$*" >&2; }

[ -r /etc/pleb/session.env ] && . /etc/pleb/session.env

KILIX_DIR="${KILIX_DIR:-$HOME/kilix}"
KILIX_REPO="${KILIX_REPO:-https://github.com/itsmygithubacct/kilix.git}"
KILIX_BRANCH="${KILIX_BRANCH:-}"
KILIX95_DIR="${KILIX95_DIR:-$HOME/kilix-95}"
KILIX95_REPO="${KILIX95_REPO:-https://github.com/itsmygithubacct/kilix-95.git}"
KILIX95_BRANCH="${KILIX95_BRANCH:-}"
KILIX95_REF="${KILIX95_REF:-}"
PLEB_DESKTOP="${PLEB_DESKTOP:-0}"
PLEB_DIR="${PLEB_DIR:-$HOME/pleb}"

if [ -d "$KILIX_DIR/.git" ]; then
    log "updating kilix  ($KILIX_DIR)"
    git -C "$KILIX_DIR" pull --ff-only || warn "kilix pull failed (continuing)"
else
    warn "no kilix checkout at $KILIX_DIR — skipping"
fi

if [ -d "$KILIX95_DIR/.git" ]; then
    log "updating kilix 95 ($KILIX95_DIR)"
    if ! git -C "$KILIX95_DIR" config --get remote.origin.url >/dev/null; then
        warn "kilix 95 checkout has no origin remote; skipping"
    elif [ -n "$KILIX95_REF" ]; then
        git -C "$KILIX95_DIR" fetch --tags origin \
            && git -C "$KILIX95_DIR" checkout --detach "$KILIX95_REF" \
            || warn "kilix 95 ref update failed (continuing)"
    else
        git -C "$KILIX95_DIR" pull --ff-only || warn "kilix 95 pull failed (continuing)"
    fi
elif [ "$PLEB_DESKTOP" = 1 ]; then
    log "kilix 95 missing at $KILIX95_DIR — pleb install will clone it"
else
    log "kilix 95 not configured for this session — skipping"
fi

if [ -d "$PLEB_DIR/.git" ]; then
    log "updating pleb   ($PLEB_DIR)"
    git -C "$PLEB_DIR" pull --ff-only || warn "pleb pull failed (continuing)"
else
    warn "no pleb checkout at $PLEB_DIR — skipping"
fi

if [ -x "$PLEB_DIR/bin/pleb" ]; then
    log "re-running 'pleb install' (re-links commands + refreshes the session)"
    env KILIX_DIR="$KILIX_DIR" KILIX_REPO="$KILIX_REPO" \
        ${KILIX_BRANCH:+KILIX_BRANCH="$KILIX_BRANCH"} \
        PLEB_DESKTOP="$PLEB_DESKTOP" KILIX95_DIR="$KILIX95_DIR" \
        KILIX95_REPO="$KILIX95_REPO" ${KILIX95_BRANCH:+KILIX95_BRANCH="$KILIX95_BRANCH"} \
        ${KILIX95_REF:+KILIX95_REF="$KILIX95_REF"} \
        "$PLEB_DIR/bin/pleb" install || { warn "'pleb install' failed"; exit 1; }
else
    warn "no pleb at $PLEB_DIR/bin/pleb — cannot run 'pleb install'"
    exit 1
fi

log "Plebian-OS stack updated."
log "restart the session to load the changes:  sudo systemctl restart lightdm"
