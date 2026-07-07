#!/usr/bin/env bash
# plebian-os-update.sh — refresh the whole Plebian-OS software stack.
#
# Pulls the latest kilix AND pleb, then re-runs `pleb install`. This is MORE
# than `pleb update` (which only fetches + rebuilds kilix): it also updates the
# pleb repo itself and re-applies the install — the kilix/pleb command symlinks,
# the pleb-session launcher, and the xsession entry — so a change to any of
# those lands too.
#
# Run as the Pleb user; `pleb install` elevates via sudo where it needs root.
# Deployed to the target as /usr/local/bin/plebian-os-update and offered as a
# clickable item in the kilix 95 Start menu.
set -uo pipefail

log()  { printf '\033[1;35m[plebian-os]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[plebian-os]\033[0m %s\n' "$*" >&2; }

KILIX_DIR="${KILIX_DIR:-$HOME/kilix}"
PLEB_DIR="${PLEB_DIR:-$HOME/pleb}"

if [ -d "$KILIX_DIR/.git" ]; then
    log "updating kilix  ($KILIX_DIR)"
    git -C "$KILIX_DIR" pull --ff-only || warn "kilix pull failed (continuing)"
else
    warn "no kilix checkout at $KILIX_DIR — skipping"
fi

if [ -d "$PLEB_DIR/.git" ]; then
    log "updating pleb   ($PLEB_DIR)"
    git -C "$PLEB_DIR" pull --ff-only || warn "pleb pull failed (continuing)"
else
    warn "no pleb checkout at $PLEB_DIR — skipping"
fi

if [ -x "$PLEB_DIR/bin/pleb" ]; then
    log "re-running 'pleb install' (re-links commands + refreshes the session)"
    "$PLEB_DIR/bin/pleb" install || { warn "'pleb install' failed"; exit 1; }
else
    warn "no pleb at $PLEB_DIR/bin/pleb — cannot run 'pleb install'"
    exit 1
fi

log "Plebian-OS stack updated."
log "restart the session to load the changes:  sudo systemctl restart lightdm"
