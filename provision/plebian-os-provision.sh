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
#      into ~/kilix, optionally clones github.com/itsmygithubacct/kilix-95 into
#      ~/kilix-95, fetches a prebuilt kitty engine, and registers "Pleb" as a
#      LightDM session (/usr/share/xsessions/pleb.desktop) + puts kilix and pleb
#      on PATH
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
KILIX95_REPO="${KILIX95_REPO:-https://github.com/itsmygithubacct/kilix-95.git}"
PLEB_BRANCH="${PLEB_BRANCH:-}"                 # empty = repo default
PLEB_REF="${PLEB_REF:-}"                       # optional exact commit/tag
KILIX_BRANCH="${KILIX_BRANCH:-}"
KILIX_REF="${KILIX_REF:-}"
KILIX_PREBUILT_VERSION="${KILIX_PREBUILT_VERSION:-}" # optional exact kitty fallback version
KILIX_PREBUILT_SHA256="${KILIX_PREBUILT_SHA256:-}"   # optional checksum for the fallback bundle
KILIX_DESKTOP_PROVIDER="${KILIX_DESKTOP_PROVIDER:-external}"
KILIX_DESKTOP_COMMAND="${KILIX_DESKTOP_COMMAND:-}"
KILIX_DESKTOP_NAME="${KILIX_DESKTOP_NAME:-desktop}"
KILIX95_BRANCH="${KILIX95_BRANCH:-}"
KILIX95_REF="${KILIX95_REF:-}"
KILIX95_AUTO_INSTALL="${KILIX95_AUTO_INSTALL:-1}"
KILIX_DIR="${KILIX_DIR:-}"                     # default after target user is known
KILIX95_DIR="${KILIX95_DIR:-}"                 # default after target user is known
KIOSK="${PLEBIAN_OS_KIOSK:-0}"                 # 1 = autologin straight into Pleb
NOPASSWD_SUDO="${PLEBIAN_OS_NOPASSWD_SUDO:-0}" # 1 = passwordless sudo for the user
DESKTOP="${PLEBIAN_OS_DESKTOP:-1}"             # 1 = Pleb boots into `kilix desktop`
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
  --no-desktop   boot into a plain fullscreen kilix shell, not a desktop provider
  --branch REF   pleb branch/tag to clone (default: repo default)
  --dry-run      print what would happen; change nothing
EOF
}

log()  { printf '\033[1;36m[plebian-os]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[plebian-os]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[plebian-os] %s\033[0m\n' "$*" >&2; exit 1; }
run()  { if [ "$DRY_RUN" = 1 ]; then echo "    + $*"; else "$@"; fi; }

write_session_default() {
    local name="$1" value="$2"
    printf 'if [ -z "${%s+x}" ]; then %s=%q; fi\n' "$name" "$name" "$value"
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
    [ -d "$dir/.git" ] || return 0
    remote="$(git -C "$dir" config --get remote.origin.url 2>/dev/null || true)"
    if [ -n "$remote" ] && [ "$remote" != "$repo" ] \
        && [ "${PLEBIAN_OS_TRUST_EXISTING_CHECKOUT:-0}" != 1 ]; then
        die "$name checkout at $dir has origin '$remote', expected '$repo' (set PLEBIAN_OS_TRUST_EXISTING_CHECKOUT=1 to override)"
    fi
}

update_pleb_checkout() {
    validate_checkout "$PLEB_DIR" "$PLEB_REPO" "pleb"
    if [ -n "$PLEB_REF" ]; then
        as_user git -C "$PLEB_DIR" fetch --tags origin || die "pleb fetch failed"
        as_user git -C "$PLEB_DIR" checkout --detach "$PLEB_REF" \
            || die "could not check out PLEB_REF=$PLEB_REF"
        return
    fi

    if [ -n "$PLEB_BRANCH" ]; then
        as_user git -C "$PLEB_DIR" fetch --prune origin "$PLEB_BRANCH" \
            || die "pleb fetch failed"
        current="$(git -C "$PLEB_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo HEAD)"
        if [ "$current" != "$PLEB_BRANCH" ]; then
            if git -C "$PLEB_DIR" show-ref --verify --quiet "refs/heads/$PLEB_BRANCH"; then
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
KILIX_DIR="${KILIX_DIR:-$USER_HOME/kilix}"
KILIX95_DIR="${KILIX95_DIR:-$USER_HOME/kilix-95}"

log "target user : $TARGET_USER ($USER_HOME)"
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

# ── 2. clone pleb into the user's home (as the user, correct ownership) ──────
PLEB_DIR="$USER_HOME/pleb"
as_user() {
    if [ "$DRY_RUN" = 1 ]; then echo "    + (as $TARGET_USER) $*"; return 0; fi
    runuser -u "$TARGET_USER" -- "$@"
}
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
        as_user git -C "$PLEB_DIR" fetch --tags origin || die "pleb fetch failed"
        as_user git -C "$PLEB_DIR" checkout --detach "$PLEB_REF" \
            || die "could not check out PLEB_REF=$PLEB_REF"
    fi
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
    visudo -cf "$SUDOERS" >/dev/null 2>&1 \
        || { rm -f "$SUDOERS"; die "temporary sudoers validation failed"; }
fi

log "running 'pleb install' (clones kilix + optional desktop provider, adds the Pleb session)"
install_env=(
    "KILIX_DIR=$KILIX_DIR"
    "KILIX_REPO=$KILIX_REPO"
    "KILIX_BRANCH=$KILIX_BRANCH"
    "KILIX_REF=$KILIX_REF"
    "KILIX_PREBUILT_VERSION=$KILIX_PREBUILT_VERSION"
    "KILIX_PREBUILT_SHA256=$KILIX_PREBUILT_SHA256"
    "KILIX_DESKTOP_PROVIDER=$KILIX_DESKTOP_PROVIDER"
    "KILIX_DESKTOP_COMMAND=$KILIX_DESKTOP_COMMAND"
    "KILIX_DESKTOP_NAME=$KILIX_DESKTOP_NAME"
    "PLEB_DESKTOP=$DESKTOP"
    "KILIX95_AUTO_INSTALL=$KILIX95_AUTO_INSTALL"
    "KILIX95_DIR=$KILIX95_DIR"
    "KILIX95_REPO=$KILIX95_REPO"
    "KILIX95_BRANCH=$KILIX95_BRANCH"
    "KILIX95_REF=$KILIX95_REF"
)
as_user env "${install_env[@]}" "$PLEB_DIR/bin/pleb" install \
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

# ── 5. session mode: boot into `kilix desktop` (disablable) ─────────────────
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
    {
    cat <<'EOF'
# Managed by plebian-os-provision — Plebian-OS Pleb session config.
# PLEB_DESKTOP=1 starts `kilix desktop`; set it to 0 for a plain fullscreen
# kilix shell. KILIX_DESKTOP_PROVIDER selects auto, builtin, external, command,
# or none. pleb-session documents the other knobs.
EOF
    write_session_default PLEB_DIR "$PLEB_DIR"
    write_session_default PLEB_REPO "$PLEB_REPO"
    write_session_default PLEB_BRANCH "$PLEB_BRANCH"
    write_session_default PLEB_REF "$PLEB_REF"
    write_session_default KILIX_DIR "$KILIX_DIR"
    write_session_default KILIX "$KILIX_DIR/kilix"
    write_session_default KILIX_REPO "$KILIX_REPO"
    write_session_default KILIX_BRANCH "$KILIX_BRANCH"
    write_session_default KILIX_REF "$KILIX_REF"
    write_session_default KILIX_PREBUILT_VERSION "$KILIX_PREBUILT_VERSION"
    write_session_default KILIX_PREBUILT_SHA256 "$KILIX_PREBUILT_SHA256"
    write_session_default PLEB_DESKTOP "$DESKTOP"
    write_session_default KILIX_DESKTOP_PROVIDER "$KILIX_DESKTOP_PROVIDER"
    write_session_default KILIX_DESKTOP_COMMAND "$KILIX_DESKTOP_COMMAND"
    write_session_default KILIX_DESKTOP_NAME "$KILIX_DESKTOP_NAME"
    write_session_default KILIX95_AUTO_INSTALL "$KILIX95_AUTO_INSTALL"
    write_session_default KILIX95_DIR "$KILIX95_DIR"
    write_session_default KILIX95_REPO "$KILIX95_REPO"
    write_session_default KILIX95_BRANCH "$KILIX95_BRANCH"
    write_session_default KILIX95_REF "$KILIX95_REF"
    } > "$PLEB_ENV"
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
log "  reboot → LightDM → Pleb → $([ "$DESKTOP" = 1 ] && echo "kilix desktop ($KILIX_DESKTOP_PROVIDER)" || echo 'fullscreen kilix')."
[ "$KIOSK" = 1 ] && log "  (kiosk: boots straight in; rescue console on Ctrl+Alt+F2)"
[ "$NOPASSWD_SUDO" = 1 ] && log "  ($TARGET_USER has passwordless sudo)"
exit 0
