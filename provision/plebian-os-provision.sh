#!/usr/bin/env bash
# plebian-os-provision.sh — turn a stock graphical Debian into Plebian-OS.
#
# Plebian-OS is a regular Debian install whose desktop session is Pleb — a
# single fullscreen kilix as the whole "desktop" — in place of XFCE/GNOME.
# The OS ships none of that; this script pulls it from GitHub on first boot:
#
#   1. apt-installs the runtime deps (Xorg, LightDM, git/curl/tar, GL, fonts)
#   2. clones  github.com/itsmygithubacct/pleb  into the target user's ~/pleb
#   3. runs    pleb install  — which itself clones github.com/itsmygithubacct/kilix
#      into ~/kilix, fetches a prebuilt kitty engine, and registers "Pleb" as a
#      LightDM session (/usr/share/xsessions/pleb.desktop) + puts kilix and pleb on PATH
#   4. (optional) enables Pleb autologin — a hard kiosk that boots straight in
#   5. (optional) grants the target user passwordless sudo (--nopasswd-sudo)
#
# It is idempotent: re-running updates the checkouts and re-asserts the session.
# Run as root (the firstboot service does) or via sudo. --dry-run prints the
# plan without touching anything.
set -euo pipefail

# ── config (env-overridable) ─────────────────────────────────────────────────
PLEB_REPO="${PLEB_REPO:-https://github.com/itsmygithubacct/pleb.git}"
KILIX_REPO="${KILIX_REPO:-https://github.com/itsmygithubacct/kilix.git}"
PLEB_BRANCH="${PLEB_BRANCH:-}"                 # empty = repo default
KILIX_BRANCH="${KILIX_BRANCH:-}"
KIOSK="${PLEBIAN_OS_KIOSK:-0}"                 # 1 = autologin straight into Pleb
NOPASSWD_SUDO="${PLEBIAN_OS_NOPASSWD_SUDO:-0}" # 1 = passwordless sudo for the user
DESKTOP="${PLEBIAN_OS_DESKTOP:-1}"             # 1 = Pleb boots into the kilix "95" desktop
TARGET_USER="${PLEBIAN_OS_USER:-}"             # empty = first regular (uid>=1000) user
DRY_RUN=0

# Where this script lives (deployed as /usr/local/sbin/plebian-os-provision, or
# run in-repo from provision/). The runtime dependency set now lives beside us
# in install-deps.sh (deployed as plebian-os-install-deps) — the single source
# of truth — which step 1 below calls.
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"

usage() {
    sed -n '2,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//'
    cat <<EOF

Usage: $0 [--user NAME] [--kiosk] [--nopasswd-sudo] [--no-desktop] [--branch REF] [--dry-run]
  --user NAME    provision for this user (default: first uid>=1000 account)
  --kiosk        enable autologin straight into Pleb (no greeter)
  --nopasswd-sudo grant the target user passwordless sudo
  --no-desktop   boot into a plain fullscreen kilix shell, not the "95" desktop
  --branch REF   pleb branch/tag to clone (default: repo default)
  --dry-run      print what would happen; change nothing
EOF
}

log()  { printf '\033[1;36m[plebian-os]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[plebian-os]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[plebian-os] %s\033[0m\n' "$*" >&2; exit 1; }
run()  { if [ "$DRY_RUN" = 1 ]; then echo "    + $*"; else "$@"; fi; }

# ── args ─────────────────────────────────────────────────────────────────────
while [ $# -gt 0 ]; do
    case "$1" in
        --user)   TARGET_USER="${2:?}"; shift 2 ;;
        --kiosk)  KIOSK=1; shift ;;
        --nopasswd-sudo) NOPASSWD_SUDO=1; shift ;;
        --no-desktop) DESKTOP=0; shift ;;
        --branch) PLEB_BRANCH="${2:?}"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown option: $1 (see --help)" ;;
    esac
done

[ "$(id -u)" = 0 ] || [ "$DRY_RUN" = 1 ] || die "must run as root (try: sudo $0)"

# ── pick the target user ─────────────────────────────────────────────────────
pick_user() {
    # the account d-i created: lowest uid >= 1000 with a real shell and home
    getent passwd | awk -F: '$3>=1000 && $3<65534 && $7!~/(nologin|false)$/ {print $3":"$1}' \
        | sort -n | head -1 | cut -d: -f2
}
[ -n "$TARGET_USER" ] || TARGET_USER="$(pick_user)"
[ -n "$TARGET_USER" ] || die "no regular user found — create one, or pass --user"
id "$TARGET_USER" >/dev/null 2>&1 || die "no such user: $TARGET_USER"
USER_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
[ -d "$USER_HOME" ] || die "home for $TARGET_USER not found: $USER_HOME"

log "target user : $TARGET_USER ($USER_HOME)"
log "pleb repo   : $PLEB_REPO ${PLEB_BRANCH:+(branch $PLEB_BRANCH)}"
log "kilix repo  : $KILIX_REPO (cloned by pleb)"
log "kiosk       : $([ "$KIOSK" = 1 ] && echo 'yes (autologin)' || echo 'no (greeter)')"
log "session     : $([ "$DESKTOP" = 1 ] && echo 'kilix "95" desktop' || echo 'plain kilix shell')"

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
log "installing runtime dependencies via $DEPS_SCRIPT"
if [ "$DRY_RUN" = 1 ]; then
    bash "$DEPS_SCRIPT" --dry-run
else
    bash "$DEPS_SCRIPT" || die "dependency install failed (see the group summary above)"
fi

# ── 2. clone pleb into the user's home (as the user, correct ownership) ──────
PLEB_DIR="$USER_HOME/pleb"
as_user() {
    if [ "$DRY_RUN" = 1 ]; then echo "    + (as $TARGET_USER) $*"; return 0; fi
    runuser -u "$TARGET_USER" -- "$@"
}
if [ -d "$PLEB_DIR/.git" ]; then
    log "pleb present at $PLEB_DIR — updating"
    as_user git -C "$PLEB_DIR" pull --ff-only || warn "pleb pull failed; using existing checkout"
else
    log "cloning pleb -> $PLEB_DIR"
    as_user git clone ${PLEB_BRANCH:+--branch "$PLEB_BRANCH"} "$PLEB_REPO" "$PLEB_DIR" \
        || die "git clone of pleb failed ($PLEB_REPO)"
fi

# ── 3. run `pleb install` (clones kilix + engine, registers the Pleb session) ─
# pleb does its system writes through sudo; grant the user passwordless sudo for
# the duration of provisioning, then revoke it (leaves the system as it found it).
SUDOERS=/etc/sudoers.d/plebian-os-provision
cleanup() { [ "$DRY_RUN" = 1 ] || rm -f "$SUDOERS"; }
trap cleanup EXIT
if [ "$DRY_RUN" = 1 ]; then
    echo "    + echo '$TARGET_USER ALL=(ALL) NOPASSWD:ALL' > $SUDOERS  (temporary)"
else
    printf '%s ALL=(ALL) NOPASSWD:ALL\n' "$TARGET_USER" > "$SUDOERS"
    chmod 0440 "$SUDOERS"
fi

log "running 'pleb install' (clones kilix + engine, adds the Pleb session)"
as_user env KILIX_REPO="$KILIX_REPO" ${KILIX_BRANCH:+KILIX_BRANCH="$KILIX_BRANCH"} \
    "$PLEB_DIR/bin/pleb" install \
    || die "pleb install failed (see above)"

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

# ── 5. session mode: boot into the kilix "95" desktop (disablable) ──────────
# pleb-session reads /etc/pleb/session.env on every login; PLEB_DESKTOP=1 brings
# the Pleb session up as the kilix desktop instead of a bare shell. This is a
# plain config file the user owns: flip it to 0, or delete it, for a plain
# fullscreen kilix — no reprovision needed.
PLEB_ENV=/etc/pleb/session.env
log "writing session config -> $PLEB_ENV (PLEB_DESKTOP=$DESKTOP)"
if [ "$DRY_RUN" = 1 ]; then
    echo "    + write $PLEB_ENV (PLEB_DESKTOP=$DESKTOP)"
else
    mkdir -p "$(dirname "$PLEB_ENV")"
    cat > "$PLEB_ENV" <<EOF
# Managed by plebian-os-provision — Plebian-OS Pleb session config.
# PLEB_DESKTOP=1 boots straight into the kilix "95" desktop; set it to 0 (or
# delete this file) for a plain fullscreen kilix shell. pleb-session documents
# the other knobs (PLEB_RESPAWN, PLEB_WM, PLEB_BG, …).
PLEB_DESKTOP=$DESKTOP
EOF
fi

if [ "$KIOSK" = 1 ]; then
    log "enabling autologin into Pleb (kiosk)"
    as_user "$PLEB_DIR/bin/pleb" autologin on "$TARGET_USER" \
        || warn "pleb autologin failed; the greeter will still offer Pleb"
fi

# Passwordless sudo for the owner. Plebian-OS is a single-user appliance and the
# VM builder turns this on by default, so `pleb install`, the Start-menu update
# actions and Shut Down (systemctl poweroff) never stop for a password. This is
# a PERMANENT file — the grant used during provisioning above is temporary and
# removed by cleanup.
if [ "$NOPASSWD_SUDO" = 1 ]; then
    log "granting $TARGET_USER passwordless sudo"
    NOPASSWD_FILE=/etc/sudoers.d/plebian-os-nopasswd
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + echo '$TARGET_USER ALL=(ALL) NOPASSWD:ALL' > $NOPASSWD_FILE (0440, visudo-checked)"
    else
        printf '%s ALL=(ALL) NOPASSWD:ALL\n' "$TARGET_USER" > "$NOPASSWD_FILE"
        chmod 0440 "$NOPASSWD_FILE"
        visudo -cf "$NOPASSWD_FILE" >/dev/null 2>&1 \
            || { warn "sudoers validation failed — removing $NOPASSWD_FILE"; rm -f "$NOPASSWD_FILE"; }
    fi
fi

cleanup; trap - EXIT

log "done. Plebian-OS is provisioned."
log "  reboot → LightDM → Pleb → $([ "$DESKTOP" = 1 ] && echo 'kilix "95" desktop' || echo 'fullscreen kilix')."
[ "$KIOSK" = 1 ] && log "  (kiosk: boots straight in; rescue console on Ctrl+Alt+F2)"
[ "$NOPASSWD_SUDO" = 1 ] && log "  ($TARGET_USER has passwordless sudo)"
exit 0
