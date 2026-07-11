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
#      on PATH. This provisioner then builds and verifies the kilix fork so the
#      first boot uses the clickable-chrome engine instead of the fallback.
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
KILIX_DESKTOP_FLAVOR="${KILIX_DESKTOP_FLAVOR:-}"
BUILD_KILIX_FORK="${PLEBIAN_OS_BUILD_KILIX_FORK:-1}"
KILIX_GO_MIN_VERSION="${PLEBIAN_OS_KILIX_GO_MIN_VERSION:-1.26}"
KILIX95_BRANCH="${KILIX95_BRANCH:-}"
KILIX95_REF="${KILIX95_REF:-}"
KILIX95_AUTO_INSTALL="${KILIX95_AUTO_INSTALL:-1}"
# Plebian-OS layer itself: where the provisioner/update-helper/deps script come
# from, so `plebian-os-update` can refresh the OS layer (not just pleb/kilix).
PLEBIAN_OS_REPO="${PLEBIAN_OS_REPO:-https://github.com/itsmygithubacct/plebian-os.git}"
PLEBIAN_OS_BRANCH="${PLEBIAN_OS_BRANCH:-}"     # empty = repo default
PLEBIAN_OS_REF="${PLEBIAN_OS_REF:-}"           # optional exact commit/tag
PLEBIAN_OS_VERSION="${PLEBIAN_OS_VERSION:-}"   # resolved from the VERSION file below if empty
PLEBIAN_OS_APT_SNAPSHOT="${PLEBIAN_OS_APT_SNAPSHOT:-}" # snapshot.debian.org ts = reproducible apt
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

# Pin apt to a snapshot.debian.org timestamp so the first-boot package closure is
# reproducible. Opt-in via PLEBIAN_OS_APT_SNAPSHOT; a no-op when unset (default),
# so ordinary installs track the live mirror exactly as before.
configure_apt_snapshot() {
    [ -n "$PLEBIAN_OS_APT_SNAPSHOT" ] || return 0
    local ts="$PLEBIAN_OS_APT_SNAPSHOT"
    local src=/etc/apt/sources.list.d/plebian-os-snapshot.sources
    local cfg=/etc/apt/apt.conf.d/99plebian-os-snapshot
    log "pinning apt to snapshot.debian.org/$ts (reproducible package closure)"
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + disable stock apt sources (sources.list, sources.list.d/debian.sources)"
        echo "    + write $src (deb822 snapshot sources for $ts) + $cfg (Check-Valid-Until false)"
        echo "    + apt-get update"
        return 0
    fi
    mkdir -p /etc/apt/sources.list.d /etc/apt/apt.conf.d /etc/plebian-os
    # Move the stock trixie sources aside so only the snapshot is consulted.
    local d
    for d in /etc/apt/sources.list /etc/apt/sources.list.d/debian.sources; do
        [ -f "$d" ] && [ ! -e "$d.plebian-os-disabled" ] \
            && mv "$d" "$d.plebian-os-disabled"
    done
    cat > "$src" <<EOF
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
    printf '%s\n' 'Acquire::Check-Valid-Until "false";' > "$cfg"
    printf '%s\n' "$ts" > /etc/plebian-os/apt-snapshot
    apt-get update -y || warn "apt-get update against snapshot $ts failed (continuing)"
}

# Record the exact installed package set for build provenance / reproducibility
# auditing (what a given image actually resolved to at first boot).
write_package_manifest() {
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + record installed packages -> /var/lib/plebian-os/packages.list"
        return 0
    fi
    command -v dpkg-query >/dev/null 2>&1 || return 0
    mkdir -p /var/lib/plebian-os
    dpkg-query -W -f='${Package}=${Version}\n' 2>/dev/null \
        | sort > /var/lib/plebian-os/packages.list || true
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
        echo "    + write $dmrc ([Desktop] Session=pleb)"
        echo "    + create $asvc with Session=pleb (if absent)"
        return 0
    fi
    printf '%s\n' '[Desktop]' 'Session=pleb' > "$dmrc"
    chown "$TARGET_UID:$TARGET_GID" "$dmrc" 2>/dev/null || true
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
        echo "    + write $rule ($TARGET_USER NOPASSWD: $dst)"
        return 0
    fi
    if [ -n "$src" ] && [ "$src" != "$dst" ]; then
        install -m 0755 "$src" "$dst" || warn "could not install $dst"
    fi
    if [ ! -x "$dst" ]; then
        warn "plebian-os-passwd helper missing; skipping default-password nag setup"
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

kilix_go_ok_script() {
    cat <<'EOF'
command -v go >/dev/null 2>&1 || exit 1
min="${PLEBIAN_OS_KILIX_GO_MIN_VERSION:-1.26}"
ver="$(go version 2>/dev/null | awk '{print $3}' | sed 's/^go//')"
[ -n "$ver" ] || exit 1
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

ensure_go_for_kilix_build() {
    log "checking Go toolchain for kilix fork build (>= $KILIX_GO_MIN_VERSION)"
    if as_user env "PLEBIAN_OS_KILIX_GO_MIN_VERSION=$KILIX_GO_MIN_VERSION" \
        bash -lc "$(kilix_go_ok_script)"; then
        log "Go is ready: $(as_user bash -lc 'go version' 2>/dev/null || true)"
        return 0
    fi

    [ -x "$PLEB_DIR/scripts/install-go.sh" ] \
        || die "Go >= $KILIX_GO_MIN_VERSION is required, and $PLEB_DIR/scripts/install-go.sh is missing"
    log "installing/upgrading Go via pleb helper"
    as_user "$PLEB_DIR/scripts/install-go.sh" all \
        || die "Go toolchain install failed"
    as_user env "PLEBIAN_OS_KILIX_GO_MIN_VERSION=$KILIX_GO_MIN_VERSION" \
        bash -lc "$(kilix_go_ok_script)" \
        || die "Go toolchain is still below $KILIX_GO_MIN_VERSION after install"
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
        echo "    + ensure Go >= $KILIX_GO_MIN_VERSION using $PLEB_DIR/scripts/install-go.sh if needed"
        echo "    + (as $TARGET_USER) $KILIX_DIR/kilix --build"
        echo "    + verify $KILIX_DIR/kilix --which uses $KILIX_DIR/src/kitty/launcher/kitty"
        return 0
    fi

    [ -d "$KILIX_DIR/.git" ] || die "kilix checkout missing at $KILIX_DIR after pleb install"
    [ -x "$KILIX_DIR/kilix" ] || die "kilix launcher missing at $KILIX_DIR/kilix"

    log "initializing kilix source submodules"
    as_user git -C "$KILIX_DIR" submodule update --init --recursive \
        || die "kilix submodule initialization failed"

    ensure_go_for_kilix_build

    log "building kilix clickable-chrome fork"
    as_user "$KILIX_DIR/kilix" --build \
        || die "kilix fork build failed"

    local fork engine
    fork="$KILIX_DIR/src/kitty/launcher/kitty"
    [ -x "$fork" ] || die "kilix fork build did not produce $fork"
    engine="$(as_user "$KILIX_DIR/kilix" --which 2>/dev/null | head -1 || true)"
    [ "$engine" = "$fork" ] \
        || die "kilix is not using the fork engine after build (got: ${engine:-<empty>})"
    log "kilix engine verified: $engine"
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
        --version) echo "plebian-os-provision $PLEBIAN_OS_VERSION"; exit 0 ;;
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
TARGET_UID="$(id -u "$TARGET_USER")"
TARGET_GID="$(id -g "$TARGET_USER")"
KILIX_DIR="${KILIX_DIR:-$USER_HOME/kilix}"
KILIX95_DIR="${KILIX95_DIR:-$USER_HOME/kilix-95}"

log "plebian-os  : version $PLEBIAN_OS_VERSION"
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
configure_apt_snapshot
log "installing runtime dependencies via $DEPS_SCRIPT"
if [ "$DRY_RUN" = 1 ]; then
    bash "$DEPS_SCRIPT" --dry-run
else
    bash "$DEPS_SCRIPT" || die "dependency install failed (see the group summary above)"
fi
write_package_manifest
install_no_beep_defaults
install_quiet_console_defaults

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

# ── 2. clone pleb into the user's home (as the user, correct ownership) ──────
PLEB_DIR="$USER_HOME/pleb"
as_user() {
    if [ "$DRY_RUN" = 1 ]; then echo "    + (as $TARGET_USER) $*"; return 0; fi
    command -v setpriv >/dev/null 2>&1 \
        || die "setpriv is required to run provisioning commands as $TARGET_USER"
    setpriv --reuid "$TARGET_UID" --regid "$TARGET_GID" --init-groups \
        --reset-env -- "$@"
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
# Remove the temporary grant on normal exit AND on signals: a SIGTERM window
# (e.g. the firstboot TimeoutStartSec) must never leave passwordless sudo behind.
# SIGKILL can't be trapped, so the firstboot unit's ExecStartPre also clears any
# stale file before each attempt.
trap cleanup EXIT
trap 'cleanup; trap - EXIT; exit 143' INT TERM HUP
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
    "KILIX_DESKTOP_FLAVOR=$KILIX_DESKTOP_FLAVOR"
    "PLEB_DESKTOP=$DESKTOP"
    "KILIX95_AUTO_INSTALL=$KILIX95_AUTO_INSTALL"
    "KILIX95_DIR=$KILIX95_DIR"
    "KILIX95_REPO=$KILIX95_REPO"
    "KILIX95_BRANCH=$KILIX95_BRANCH"
    "KILIX95_REF=$KILIX95_REF"
)
as_user env "${install_env[@]}" "$PLEB_DIR/bin/pleb" install \
    || die "pleb install failed (see above)"
build_kilix_fork

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
    write_session_default PLEBIAN_OS_BUILD_KILIX_FORK "$BUILD_KILIX_FORK"
    write_session_default PLEBIAN_OS_KILIX_GO_MIN_VERSION "$KILIX_GO_MIN_VERSION"
    write_session_default PLEB_DESKTOP "$DESKTOP"
    write_session_default KILIX_DESKTOP_PROVIDER "$KILIX_DESKTOP_PROVIDER"
    write_session_default KILIX_DESKTOP_COMMAND "$KILIX_DESKTOP_COMMAND"
    write_session_default KILIX_DESKTOP_NAME "$KILIX_DESKTOP_NAME"
    write_session_default KILIX_DESKTOP_FLAVOR "$KILIX_DESKTOP_FLAVOR"
    write_session_default KILIX95_AUTO_INSTALL "$KILIX95_AUTO_INSTALL"
    write_session_default KILIX95_DIR "$KILIX95_DIR"
    write_session_default KILIX95_REPO "$KILIX95_REPO"
    write_session_default KILIX95_BRANCH "$KILIX95_BRANCH"
    write_session_default KILIX95_REF "$KILIX95_REF"
    write_session_default PLEBIAN_OS_VERSION "$PLEBIAN_OS_VERSION"
    write_session_default PLEBIAN_OS_REPO "$PLEBIAN_OS_REPO"
    write_session_default PLEBIAN_OS_BRANCH "$PLEBIAN_OS_BRANCH"
    write_session_default PLEBIAN_OS_REF "$PLEBIAN_OS_REF"
    write_session_default PLEBIAN_OS_APT_SNAPSHOT "$PLEBIAN_OS_APT_SNAPSHOT"
    [ "$KIOSK" = 1 ] && printf '%s\n' 'PLEB_RESPAWN=1   # hard kiosk: respawn kilix if it exits (set by --kiosk)'
    } > "$PLEB_ENV"
fi

if [ "$KIOSK" = 1 ]; then
    log "enabling autologin into Pleb (kiosk)"
    as_user "$PLEB_DIR/bin/pleb" autologin on "$TARGET_USER" \
        || warn "pleb autologin failed; the greeter will still offer Pleb"
    pin_remembered_session
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
[ "$KIOSK" = 1 ] && log "  (kiosk: autologin + kilix respawn on exit; rescue console on Ctrl+Alt+F2)"
[ "$NOPASSWD_SUDO" = 1 ] && log "  ($TARGET_USER has passwordless sudo)"
exit 0
