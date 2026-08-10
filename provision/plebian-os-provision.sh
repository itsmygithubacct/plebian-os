#!/usr/bin/env bash
# plebian-os-provision.sh — turn a stock graphical Debian into Plebian-OS.
#
# Plebian-OS is a regular Debian install whose desktop session is Pleb — a
# single screen-filling Kilix with visible chrome as the whole "desktop" — in
# place of XFCE/GNOME.
# The OS ships none of that; this script pulls it from GitHub on first boot:
#
#   1. apt-installs the runtime deps (Xorg, LightDM, git/curl/tar, GL, fonts)
#   2. clones  github.com/itsmygithubacct/pleb  into ~/.local/gpu_terminal/sources/pleb
#   3. runs    pleb install  — which itself clones github.com/itsmygithubacct/kilix
#      into ~/.local/gpu_terminal/sources/kilix, optionally clones github.com/itsmygithubacct/kilix-95
#      into ~/.local/gpu_terminal/sources/kilix-desktops/kilix-95, fetches a prebuilt kitty
#      engine, and
#      registers "Pleb" as a
#      LightDM session (/usr/share/xsessions/pleb.desktop) + puts kilix and pleb
#      on PATH. This provisioner then builds and verifies the kilix fork so the
#      first boot uses the clickable-chrome engine instead of the fallback.
#   4. (optional) enables Pleb autologin — a hard kiosk that boots straight in
#   5. (optional) grants the target user passwordless sudo (--nopasswd-sudo)
#
# It is idempotent: re-running updates the checkouts, reconciles snapshot/live
# apt and kiosk/sudo state, re-asserts the session, and rewrites final provenance.
# Run as root (the firstboot service does) or via sudo. --dry-run prints the
# plan without touching anything.
set -euo pipefail

# ── what a release closure controls ──────────────────────────────────────────
# This list is plebian-os-select-closure.sh's RELEASE_CONTROLLED_KEYS, which
# UPGRADING.md defines: "the coordinated version/release mode, the four source
# refs, the Debian snapshot and installer input, the Kilix engine and Go pins,
# and enabled optional-closure pins such as Kilix Voice". That tool moves all of
# them as one unit; this one must not move a single one of them by accident,
# because step 5 below rewrites /etc/pleb/session.env — where an installed
# machine keeps them — wholesale on every run.
#
# Both scripts declare the set, and neither can read the other's copy at the
# moment it needs it: this provisioner is installed as one file in
# /usr/local/sbin (the preseed's late_command and the updater's OS layer both
# copy exactly this file, with no siblings to source), and UPGRADING.md has the
# operator run the selector as a standalone file extracted straight out of the
# target release's tag. tests/test_provision_pin_integrity.py reads both
# declarations and refuses to pass unless they are identical, so neither side
# can move alone. Add a key in one place and that test names the other.
RELEASE_CONTROLLED_KEYS=(
    PLEBIAN_OS_VERSION
    PLEBIAN_OS_RELEASE
    PLEBIAN_OS_RELEASE_MODE
    PLEBIAN_OS_REPO
    PLEBIAN_OS_BRANCH
    PLEBIAN_OS_REF
    PLEB_REPO
    PLEB_BRANCH
    PLEB_REF
    KILIX_REPO
    KILIX_BRANCH
    KILIX_REF
    KILIX95_REPO
    KILIX95_BRANCH
    KILIX95_REF
    PLEBIAN_OS_APT_SNAPSHOT
    KILIX_PREBUILT_VERSION
    KILIX_PREBUILT_SHA256
    PLEBIAN_OS_BUILD_KILIX_FORK
    PLEBIAN_OS_KILIX_GO_MIN_VERSION
    PLEBIAN_OS_KILIX_GO_VERSION
    PLEBIAN_OS_KILIX_GO_SHA256_AMD64
    PLEBIAN_OS_KILIX_GO_SHA256_ARM64
    PLEBIAN_OS_INSTALL_VOICE_MODEL
    KILIX_VOICE_REF
    KILIX_VOICE_LIB_VERSION
    KILIX_VOICE_LIB_URL
    KILIX_VOICE_LIB_SHA256
    KILIX_VOICE_MODEL_URL
    KILIX_VOICE_MODEL_SHA256
)

# Optional desktop-provider checkouts this script also positions by ref. A
# release closure does not pin them, but a re-run that dropped them would move
# those checkouts off whatever the machine was installed with just the same.
PROVIDER_PIN_KEYS=(
    KILIX_CAP_REF
    KILIX_TUI_UTILS_REF
    KILIX_LAND_DESKTOP_REF
)

# The desktop selection. plebian-os-select-closure classifies these as
# operator-controlled and copies them through byte for byte; the reason they
# must survive a re-provision is the same one, and the release image pins them
# too (the 0.1.8 closure ships KILIX_DESKTOP_PROVIDER=external). PLEB_WM and
# KILIX_RUN_ALIASES are the same family and already have
# resolve_session_wm_defaults.
SESSION_SELECTION_KEYS=(
    KILIX_DESKTOP_PROVIDER
    KILIX_DESKTOP_COMMAND
    KILIX_DESKTOP_NAME
    KILIX_DESKTOP_FLAVOR
)

# These switches are operator policy stored in session.env. Merging that file
# preserves their written values, but the values also have to be restored before
# `pleb install` runs; otherwise a bare re-provision acts on the built-in `1`
# while leaving an honest-looking `0` in the file.
OPTIONAL_DESKTOP_AUTO_INSTALL_KEYS=(
    KILIX_CAP_AUTO_INSTALL
    KILIX_TUI_UTILS_AUTO_INSTALL
    KILIX_LAND_DESKTOP_AUTO_INSTALL
)

# Release-controlled, but this run is its authority rather than its reader: the
# installed version comes from the VERSION marker deployed beside this script,
# and plebian-os-update replaces the two together. Reading it back out of
# session.env would pin a machine to the version it already had and no update
# could ever move it.
PROVISION_OWNED_KEYS=(
    PLEBIAN_OS_VERSION
)

# session.env key -> the variable this script keeps its value in, where the two
# names differ. Everything else is stored under its own name.
declare -A PERSISTED_KEY_VARS=(
    [PLEBIAN_OS_BUILD_KILIX_FORK]=BUILD_KILIX_FORK
    [PLEBIAN_OS_KILIX_GO_MIN_VERSION]=KILIX_GO_MIN_VERSION
    [PLEBIAN_OS_KILIX_GO_VERSION]=KILIX_GO_VERSION
    [PLEBIAN_OS_KILIX_GO_SHA256_AMD64]=KILIX_GO_SHA256_AMD64
    [PLEBIAN_OS_KILIX_GO_SHA256_ARM64]=KILIX_GO_SHA256_ARM64
    [PLEBIAN_OS_INSTALL_VOICE_MODEL]=INSTALL_VOICE_MODEL
)

# Everything a re-run must reproduce from the machine it is re-running on, and
# which of those this run was told about explicitly. Explicitness has to be read
# here, before the defaults below fill the same names in: afterwards a built-in
# default (KILIX_DESKTOP_PROVIDER=auto, the fallback engine version, the Go
# minimum) is indistinguishable from a value an operator passed.
PERSISTED_SESSION_KEYS=()
declare -A PERSISTED_KEY_EXPLICIT=()
declare -A PERSISTED_KEY_RESTORED=()
for _persisted_key in "${RELEASE_CONTROLLED_KEYS[@]}" "${PROVIDER_PIN_KEYS[@]}" \
                      "${SESSION_SELECTION_KEYS[@]}" \
                      "${OPTIONAL_DESKTOP_AUTO_INSTALL_KEYS[@]}"; do
    case " ${PROVISION_OWNED_KEYS[*]} " in *" $_persisted_key "*) continue ;; esac
    PERSISTED_SESSION_KEYS+=("$_persisted_key")
    [ -z "${!_persisted_key:-}" ] || PERSISTED_KEY_EXPLICIT["$_persisted_key"]=1
done
unset _persisted_key

# ── what this run owns in /etc/pleb/session.env ─────────────────────────────
# The storage layout this run resolves from the target account and then creates
# on disk, plus the marker it stamps into every managed install. These are the
# only keys whose value a re-provision decides for itself: it just built those
# directories, so the file it leaves behind has to describe the ones that are
# there. `--user` changes all of them at once, and nothing else does.
#
# Everything NOT named here — and not named in PROVISION_OWNED_KEYS, and not
# handed to this run explicitly — belongs to whoever put it in the file. That
# includes the release closure (restored above), the desktop selection, the
# optional-component switches, and keys this script has never heard of. Which
# way an unclassified key falls is the whole point: it is preserved.
SESSION_LAYOUT_KEYS=(
    GPU_TERMINAL_SOURCE_HOME
    GPU_TERMINAL_HOME
    GPU_TERMINAL_SETTINGS_FILE
    PLEBIAN_OS_MANAGED_INSTALL
    PLEB_DIR
    PLEB_STORAGE_HOME
    PLEB_CONFIG_HOME
    PLEB_STATE_HOME
    PLEB_CACHE_HOME
    PLEB_SESSION_HOME
    PLEB_DATA_HOME
    KILIX
    KILIX_DIR
    KILIX_STORAGE_HOME
    KILIX_CONFIG_HOME
    KILIX_STATE_DIRECTORY
    KILIX_CACHE_HOME
    KILIX_SESSION_HOME
    KILIX_BUILD_DIRECTORY
    KILIX_DATA_HOME
    KILIX_DESKTOP_DIR
    KILIX_PREBUILT_HOME
    KILIX_CAP_DIR
    KILIX_TUI_UTILS_DIR
    KILIX_LAND_DESKTOP_DIR
    KILIX95_DIR
    KILIX95_STORAGE_HOME
    KILIX95_CONFIG_HOME
    KILIX95_STATE_HOME
    KILIX95_CACHE_HOME
    KILIX95_SESSION_HOME
    KILIX95_DATA_HOME
    PLEBIAN_OS_DIR
    PLEBIAN_OS_STORAGE_HOME
    PLEBIAN_OS_SESSION_HOME
)

# session.env key -> the flag that records "an operator asked for this on this
# run", where the operator does not set the key by its own name. Everything
# else is explicit exactly when the environment carried it, which is what
# SESSION_ENV_EXPLICIT captures immediately below.
declare -A SESSION_KEY_EXPLICIT_FLAG=(
    [PLEB_DESKTOP]=DESKTOP_EXPLICIT
    [PLEB_RESPAWN]=KIOSK_EXPLICIT
)

# Which session.env keys this run was handed in its environment. Read here for
# the same reason PERSISTED_KEY_EXPLICIT is: once the config block below runs,
# a built-in default is indistinguishable from an operator's value. `sudo`
# resets the environment, so a bare `sudo plebian-os-provision` records nothing
# and every key in the installed file stays the machine's own.
declare -A SESSION_ENV_EXPLICIT=()
_session_explicit_names=()
mapfile -t _session_explicit_names < <(compgen -e)
for _session_explicit_name in "${_session_explicit_names[@]}"; do
    [ -n "${!_session_explicit_name:-}" ] || continue
    SESSION_ENV_EXPLICIT["$_session_explicit_name"]=1
done
unset _session_explicit_name _session_explicit_names

# ── config (env-overridable) ─────────────────────────────────────────────────
PLEB_REPO="${PLEB_REPO:-https://github.com/itsmygithubacct/pleb.git}"
KILIX_REPO="${KILIX_REPO:-https://github.com/itsmygithubacct/kilix.git}"
KILIX95_REPO="${KILIX95_REPO:-https://github.com/itsmygithubacct/kilix-95.git}"
PLEB_BRANCH="${PLEB_BRANCH:-}"                 # empty = repo default
PLEB_REF="${PLEB_REF:-}"                       # optional exact commit/tag
KILIX_BRANCH="${KILIX_BRANCH:-}"
KILIX_REF="${KILIX_REF:-}"
KILIX_PREBUILT_VERSION="${KILIX_PREBUILT_VERSION:-0.47.4}" # verified amd64 fallback
KILIX_PREBUILT_SHA256="${KILIX_PREBUILT_SHA256:-bc230142b2bd27f2a4bf1b1b67575f3d397a4ea2cc83f4ac2b912c306a939693}"
# Read-aloud/dictation. Empty pins mean "use the ones the Kilix checkout carries"
# outside release mode. A release with dictation enabled must state the entire
# network-fetched closure explicitly, including both URLs and checksums.
KILIX_VOICE_REF="${KILIX_VOICE_REF:-}"
KILIX_VOICE_LIB_VERSION="${KILIX_VOICE_LIB_VERSION:-}"
KILIX_VOICE_LIB_URL="${KILIX_VOICE_LIB_URL:-}"
KILIX_VOICE_LIB_SHA256="${KILIX_VOICE_LIB_SHA256:-}"
KILIX_VOICE_MODEL_URL="${KILIX_VOICE_MODEL_URL:-}"
KILIX_VOICE_MODEL_SHA256="${KILIX_VOICE_MODEL_SHA256:-}"
INSTALL_VOICE_MODEL="${PLEBIAN_OS_INSTALL_VOICE_MODEL:-0}"
INSTALL_VOICE_MODEL_EXPLICIT="${PLEBIAN_OS_INSTALL_VOICE_MODEL:+1}"
KILIX_DESKTOP_PROVIDER="${KILIX_DESKTOP_PROVIDER:-auto}"
KILIX_DESKTOP_COMMAND="${KILIX_DESKTOP_COMMAND:-}"
KILIX_DESKTOP_NAME="${KILIX_DESKTOP_NAME:-desktop}"
KILIX_DESKTOP_FLAVOR="${KILIX_DESKTOP_FLAVOR:-95}"
KILIX_CAP_REPO="${KILIX_CAP_REPO:-https://github.com/itsmygithubacct/kilix-cap.git}"
KILIX_CAP_REF="${KILIX_CAP_REF:-}"
KILIX_CAP_AUTO_INSTALL="${KILIX_CAP_AUTO_INSTALL:-1}"
KILIX_CAP_TRUST_EXISTING_CHECKOUT="${KILIX_CAP_TRUST_EXISTING_CHECKOUT:-0}"
KILIX_CAP_ALLOW_MUTABLE_REF="${KILIX_CAP_ALLOW_MUTABLE_REF:-0}"
KILIX_TUI_UTILS_REPO="${KILIX_TUI_UTILS_REPO:-https://github.com/itsmygithubacct/kilix-tui-utils.git}"
KILIX_TUI_UTILS_REF="${KILIX_TUI_UTILS_REF:-}"
KILIX_TUI_UTILS_AUTO_INSTALL="${KILIX_TUI_UTILS_AUTO_INSTALL:-1}"
KILIX_TUI_UTILS_TRUST_EXISTING_CHECKOUT="${KILIX_TUI_UTILS_TRUST_EXISTING_CHECKOUT:-0}"
KILIX_TUI_UTILS_ALLOW_MUTABLE_REF="${KILIX_TUI_UTILS_ALLOW_MUTABLE_REF:-0}"
KILIX_LAND_DESKTOP_REPO="${KILIX_LAND_DESKTOP_REPO:-https://github.com/itsmygithubacct/kilix-land-desktop.git}"
KILIX_LAND_DESKTOP_REF="${KILIX_LAND_DESKTOP_REF:-}"
KILIX_LAND_DESKTOP_AUTO_INSTALL="${KILIX_LAND_DESKTOP_AUTO_INSTALL:-1}"
KILIX_LAND_DESKTOP_TRUST_EXISTING_CHECKOUT="${KILIX_LAND_DESKTOP_TRUST_EXISTING_CHECKOUT:-0}"
KILIX_LAND_DESKTOP_ALLOW_MUTABLE_REF="${KILIX_LAND_DESKTOP_ALLOW_MUTABLE_REF:-0}"
KILIX_LAND_DESKTOP_ASSETS="${KILIX_LAND_DESKTOP_ASSETS:-}"
KILIX_LAND_DESKTOP_CONFIG_HOME="${KILIX_LAND_DESKTOP_CONFIG_HOME:-}"
KILIX_LAND_DESKTOP_EXTERNAL_APPS="${KILIX_LAND_DESKTOP_EXTERNAL_APPS:-}"
KILIX_LAND_DESKTOP_AUDIO="${KILIX_LAND_DESKTOP_AUDIO:-}"
BUILD_KILIX_FORK="${PLEBIAN_OS_BUILD_KILIX_FORK:-1}"
KILIX_GO_MIN_VERSION="${PLEBIAN_OS_KILIX_GO_MIN_VERSION:-1.26}"
KILIX_GO_VERSION="${PLEBIAN_OS_KILIX_GO_VERSION:-}"
KILIX_GO_SHA256_AMD64="${PLEBIAN_OS_KILIX_GO_SHA256_AMD64:-}"
KILIX_GO_SHA256_ARM64="${PLEBIAN_OS_KILIX_GO_SHA256_ARM64:-}"
KILIX95_BRANCH="${KILIX95_BRANCH:-}"
KILIX95_REF="${KILIX95_REF:-}"
KILIX95_AUTO_INSTALL="${KILIX95_AUTO_INSTALL:-1}"
# Plebian-OS layer itself: where the provisioner/update-helper/deps script come
# from, so `plebian-os-update` can refresh the OS layer (not just pleb/kilix).
PLEBIAN_OS_REPO="${PLEBIAN_OS_REPO:-https://github.com/itsmygithubacct/plebian-os.git}"
PLEBIAN_OS_BRANCH="${PLEBIAN_OS_BRANCH:-}"     # empty = repo default
PLEBIAN_OS_REF="${PLEBIAN_OS_REF:-}"           # optional exact commit/tag
PLEBIAN_OS_DIR="${PLEBIAN_OS_DIR:-}"           # default after target user is known
PLEBIAN_OS_VERSION="${PLEBIAN_OS_VERSION:-}"   # resolved from the VERSION file below if empty
PLEBIAN_OS_RELEASE="${PLEBIAN_OS_RELEASE:-}"
PLEBIAN_OS_RELEASE_MODE="${PLEBIAN_OS_RELEASE_MODE:-0}"
PLEBIAN_OS_APT_SNAPSHOT="${PLEBIAN_OS_APT_SNAPSHOT:-}" # snapshot.debian.org ts = reproducible apt
PLEBIAN_OS_APT_SNAPSHOT_EXPLICIT="${PLEBIAN_OS_APT_SNAPSHOT:+1}"
INSTALL_UV="${PLEBIAN_OS_INSTALL_UV:-0}"
INSTALL_UV_EXPLICIT="${PLEBIAN_OS_INSTALL_UV:+1}"
UV_VERSION_PIN="${PLEBIAN_OS_UV_VERSION:-}"
UV_INSTALLER_SHA256="${PLEBIAN_OS_UV_INSTALLER_SHA256:-}"
# The apt root is overridable only to exercise snapshot transactions in an
# isolated test tree. Production and firstboot leave it at /etc.
APT_ETC_ROOT="${PLEBIAN_OS_APT_ETC_ROOT:-/etc}"
PLEB_DIR="${PLEB_DIR:-}"                       # defaults after target user is known
KILIX_DIR="${KILIX_DIR:-}"                     # default after target user is known
KILIX95_DIR="${KILIX95_DIR:-}"                 # default after target user is known
KILIX_CAP_DIR="${KILIX_CAP_DIR:-}"              # default after target user is known
KILIX_TUI_UTILS_DIR="${KILIX_TUI_UTILS_DIR:-}"  # default after target user is known
KILIX_LAND_DESKTOP_DIR="${KILIX_LAND_DESKTOP_DIR:-}" # default after target user is known
KIOSK="${PLEBIAN_OS_KIOSK:-0}"                 # 1 = autologin straight into Pleb
KIOSK_EXPLICIT="${PLEBIAN_OS_KIOSK:+1}"
NOPASSWD_SUDO="${PLEBIAN_OS_NOPASSWD_SUDO:-0}" # 1 = passwordless sudo for the user
NOPASSWD_SUDO_EXPLICIT="${PLEBIAN_OS_NOPASSWD_SUDO:+1}"
DESKTOP="${PLEBIAN_OS_DESKTOP:-1}"             # 1 = desktop provider in Kilix page 1
DESKTOP_EXPLICIT="${PLEBIAN_OS_DESKTOP:+1}"
PLEB_WM="${PLEB_WM:-}"                         # empty = keep an existing pin, else openbox
KILIX_RUN_ALIASES="${KILIX_RUN_ALIASES:-}"     # empty = keep an existing pin, else 1
TARGET_USER="${PLEBIAN_OS_USER:-}"             # empty = first regular (uid>=1000) user
TARGET_USER_EXPLICIT="${PLEBIAN_OS_USER:+1}"
DRY_RUN=0
PLEB_BRANCH_EXPLICIT=0                         # 1 = --branch given on the command line

# Stable, distribution-owned wallpaper path shared by the builtin Kilix desktop
# and the external Kilix 95 provider.  Keep this checksum in sync with the
# tracked asset: firstboot and in-repo bootstrap fail closed rather than seed a
# desktop state that points at missing or substituted artwork.
DESKTOP_WALLPAPER_DST=/usr/local/share/plebian-os/wallpapers/plebian-os.png
DESKTOP_WALLPAPER_SHA256=60f63c37f054f7ffd061b47e09a3c22fbf595eec6f161c13e95344ca1a724778
DESKTOP_WALLPAPER_MAX_BYTES=$((32 * 1024 * 1024))
VERSION_MARKER_DST=/usr/local/share/plebian-os/VERSION
LIGHTDM_GREETER_CONFIG_DST=/etc/lightdm/lightdm-gtk-greeter.conf.d/50-plebian-os.conf
LIGHTDM_GREETER_CONFIG_SHA256=985fe09dbbb4ee83949967a83960f71746c054da8d79196a4eac98a32cd76560
INSTALLER_ATTRIBUTION_DST=/usr/local/share/doc/plebian-os/installer/ATTRIBUTION.md
INSTALLER_ATTRIBUTION_SHA256=5f5996a32c0a92debe2fef972463d28d53495e6e64af78e0e14aa4a109196ce9
GPL2_LICENSE_DST=/usr/local/share/doc/plebian-os/COPYING.GPL-2
GPL2_LICENSE_SHA256=8177f97513213526df2cf6184d8ff986c675afb514d4e68a404010521b880643
ARTWORK_NOTICE_MAX_BYTES=$((1024 * 1024))

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
# A failed or not-yet-completed firstboot can still leave the immutable ISO
# provenance available before the installed VERSION marker exists. Read only
# the version field as inert data; never source the provenance file.
if [ -z "$PLEBIAN_OS_VERSION" ] && [ -r /etc/plebian-os/build-info.env ]; then
    _build_info_version="$(
        sed -n 's/^PLEBIAN_OS_VERSION=//p' /etc/plebian-os/build-info.env 2>/dev/null
    )"
    if [[ "$_build_info_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        PLEBIAN_OS_VERSION="$_build_info_version"
    fi
fi
: "${PLEBIAN_OS_VERSION:=unknown}"

usage() {
    sed -n '2,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//'
    cat <<EOF

Usage: $0 [--user NAME] [--kiosk] [--nopasswd-sudo] [--desktop|--no-desktop] [--branch REF] [--dry-run]
  --user NAME    provision for this user (default: first uid>=1000 account)
  --kiosk        enable autologin straight into Pleb (no greeter)
  --nopasswd-sudo grant the target user passwordless sudo
  --desktop      load the configured desktop provider in Kilix page 1 (default)
  --no-desktop   load a shell in the first screen-filling Kilix page
  --branch REF   pleb branch/tag to clone (default: repo default)
  --dry-run      print what would happen; change nothing
  --version      print the Plebian-OS version and exit
EOF
}

log()  { printf '\033[1;36m[plebian-os]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[plebian-os]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[plebian-os] %s\033[0m\n' "$*" >&2; exit 1; }
run()  { if [ "$DRY_RUN" = 1 ]; then echo "    + $*"; else "$@"; fi; }

# ── the installed closure ────────────────────────────────────────────────────
# The refs this machine is provisioned from live in /etc/pleb/session.env — the
# same file pleb-session, `pleb`, plebian-os-update and plebian-os-select-closure
# read, and the one this script rewrites at the end of every successful run, so
# it tracks the installed closure rather than the image the disk shipped with.
#
# Nothing fed those refs back into a *re-run* of this provisioner. It received
# them only from its environment, and the only thing that ever set that
# environment was plebian-os-firstboot.service via
# EnvironmentFile=/etc/default/plebian-os — a unit gated on
# ConditionPathExists=!/var/lib/plebian-os/provisioned, so it never runs twice.
# A later `sudo plebian-os-provision` — which plebian-os-update recommends for
# OS-layer changes — therefore started with no pins at all and fell through to
# `git pull --ff-only`, which cannot work on the detached HEAD every pinned
# install has. Read the pins back so a re-run reproduces the installed closure.
PLEBIAN_OS_SESSION_ENV="${PLEBIAN_OS_SESSION_ENV:-/etc/pleb/session.env}"

# Refuse to source root configuration that a non-root account could have
# written. Mirrors plebian-os-update.sh; both run as root.
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

restore_installed_closure() {
    local key var value state skip="${1:-}"
    local -a candidates=() restored=() missing=()
    [ -r "$PLEBIAN_OS_SESSION_ENV" ] || return 0
    root_config_safe_to_source "$PLEBIAN_OS_SESSION_ENV" \
        || die "refusing to source unsafe $PLEBIAN_OS_SESSION_ENV as root"
    # An explicit value from the environment or the command line always wins —
    # that is how a pin is deliberately changed — so only the keys this run was
    # not told about are candidates.
    for key in "${PERSISTED_SESSION_KEYS[@]}"; do
        [ "$key" != "$skip" ] || continue
        [ -z "${PERSISTED_KEY_EXPLICIT[$key]:-}" ] || continue
        candidates+=("$key")
    done
    [ "${#candidates[@]}" -gt 0 ] || return 0
    # session.env assigns only what the environment leaves unset
    # (`if [ -z "${NAME+x}" ]`), and the config block above already set every one
    # of these names to at least the empty string. Unset the candidates and
    # source the file in a subshell, so it can fill them without any of its other
    # assignments reaching this run: the storage paths, the install policy and
    # the window-manager choice stay exactly as resolved here.
    while IFS=$'\t' read -r key state value; do
        case " ${candidates[*]} " in *" $key "*) ;; *) continue ;; esac
        if [ "$state" != set ]; then
            missing+=("$key")
            continue
        fi
        [ -n "$value" ] || continue
        # The machine answered for this key, so /etc/default must not answer for
        # it again below, even where the value matches what this run already had.
        PERSISTED_KEY_RESTORED["$key"]=1
        var="${PERSISTED_KEY_VARS[$key]:-$key}"
        [ "${!var-}" != "$value" ] || continue
        declare -g "$var=$value"
        restored+=("$key=$value")
    done < <(
        for key in "${candidates[@]}"; do unset "$key"; done
        # shellcheck source=/dev/null
        . "$PLEBIAN_OS_SESSION_ENV" >/dev/null 2>&1 || exit 0
        for key in "${candidates[@]}"; do
            printf '%s\t%s\t%s\n' "$key" "${!key+set}" "${!key-}"
        done
    )
    if [ "${#restored[@]}" -gt 0 ]; then
        log "restored the installed closure from $PLEBIAN_OS_SESSION_ENV: ${restored[*]}"
    fi
    # A key the machine has no answer for is not a key to quietly default: the
    # built-in fallback would be written back over the pin as if it were one.
    if [ "${#missing[@]}" -gt 0 ]; then
        warn "$PLEBIAN_OS_SESSION_ENV records no value for ${#missing[@]} key(s) this run must otherwise default: ${missing[*]}"
        warn "this run will use its built-in defaults for them; select the release closure again to restore the pins"
    fi
}

# ── persisted install policy ─────────────────────────────────────────────────
# The session mode, sudo grant and optional components a machine was installed
# with. These are not refs and updates never move them, so they do not belong
# in session.env; they live where firstboot read them —
# EnvironmentFile=/etc/default/plebian-os, written by the image builder.
#
# This script reconciles all of them on every run, and a run that saw none of
# them reconciled to the defaults: a kiosk image re-provisioned with a plain
# `sudo plebian-os-provision` lost its autologin and had its passwordless sudo
# revoked, silently, at the very end. That never surfaced only because the run
# died earlier, on the detached checkout. Read them back so a re-run reproduces
# the install, which is what "idempotent" is supposed to mean here.
#
# Values are matched against a strict pattern and taken as inert data; this
# file is never sourced. An explicit environment value or command-line flag
# still wins — those are how you deliberately change policy.
#
# Two of these keys are release-controlled as well, and for those this file is
# the older witness: it records the install, while a closure selection moves the
# same key in session.env and never touches /etc/default. So a value the
# installed closure already answered for is left alone below.
PLEBIAN_OS_FIRSTBOOT_ENV="${PLEBIAN_OS_FIRSTBOOT_ENV:-/etc/default/plebian-os}"

# key, the variable it feeds, and the only values accepted for it.
PERSISTED_POLICY=(
    "PLEBIAN_OS_USER"               "TARGET_USER"            '^[a-z_][a-z0-9_-]{0,31}$'
    "PLEBIAN_OS_KIOSK"              "KIOSK"                  '^[01]$'
    "PLEBIAN_OS_NOPASSWD_SUDO"      "NOPASSWD_SUDO"          '^[01]$'
    "PLEBIAN_OS_DESKTOP"            "DESKTOP"                '^[01]$'
    "PLEBIAN_OS_INSTALL_UV"         "INSTALL_UV"             '^[01]$'
    "PLEBIAN_OS_INSTALL_VOICE_MODEL" "INSTALL_VOICE_MODEL"   '^[01]$'
    "PLEBIAN_OS_APT_SNAPSHOT"       "PLEBIAN_OS_APT_SNAPSHOT" '^[0-9]{8}(T[0-9]{6}Z)?$'
)

read_firstboot_env_value() {
    local key="$1" value
    value="$(sed -n "s/^[[:space:]]*$key=//p" "$PLEBIAN_OS_FIRSTBOOT_ENV" \
        2>/dev/null | tail -1)" || return 1
    value="${value%\"}"; value="${value#\"}"
    value="${value%\'}"; value="${value#\'}"
    [ -n "$value" ] || return 1
    printf '%s\n' "$value"
}

restore_persisted_policy() {
    local i key var pattern value explicit restored=()
    [ -r "$PLEBIAN_OS_FIRSTBOOT_ENV" ] || return 0
    for ((i = 0; i < ${#PERSISTED_POLICY[@]}; i += 3)); do
        key="${PERSISTED_POLICY[i]}"
        var="${PERSISTED_POLICY[i + 1]}"
        pattern="${PERSISTED_POLICY[i + 2]}"
        explicit="${var}_EXPLICIT"
        [ "${!explicit:-0}" != 1 ] || continue
        [ -z "${PERSISTED_KEY_RESTORED[$key]:-}" ] || continue
        value="$(read_firstboot_env_value "$key")" || continue
        [[ "$value" =~ $pattern ]] || continue
        [ "$value" != "${!var}" ] || continue
        declare -g "$var=$value"
        restored+=("$key=$value")
    done
    [ "${#restored[@]}" -gt 0 ] || return 0
    log "restored install policy from $PLEBIAN_OS_FIRSTBOOT_ENV: ${restored[*]}"
}

validate_release_inputs() {
    [ "$PLEBIAN_OS_RELEASE_MODE" = 1 ] || return 0
    local key
    for key in PLEBIAN_OS_REF PLEB_REF KILIX_REF KILIX95_REF; do
        [[ "${!key}" =~ ^[0-9a-fA-F]{40}$ ]] \
            || die "release mode requires $key to be a full 40-character commit SHA"
    done
    for key in KILIX_PREBUILT_SHA256 KILIX_GO_SHA256_AMD64 KILIX_GO_SHA256_ARM64; do
        [[ "${!key}" =~ ^[0-9a-fA-F]{64}$ ]] \
            || die "release mode requires a 64-character $key"
    done
    [[ "$KILIX_GO_VERSION" =~ ^(go)?[0-9]+\.[0-9]+\.[0-9]+$ ]] \
        || die "release mode requires an exact PLEBIAN_OS_KILIX_GO_VERSION"
    if [ "$INSTALL_UV" = 1 ]; then
        [[ "$UV_VERSION_PIN" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
            || die "release mode requires an exact PLEBIAN_OS_UV_VERSION when uv is enabled"
        [[ "$UV_INSTALLER_SHA256" =~ ^[0-9a-fA-F]{64}$ ]] \
            || die "release mode requires a 64-character PLEBIAN_OS_UV_INSTALLER_SHA256 when uv is enabled"
    fi
    case "$INSTALL_VOICE_MODEL" in
        0) ;;
        1)
            [[ "$KILIX_VOICE_REF" =~ ^[0-9a-fA-F]{40}$ ]] \
                || die "release mode requires KILIX_VOICE_REF to be a full 40-character commit SHA when dictation is enabled"
            [[ "$KILIX_VOICE_LIB_VERSION" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ ]] \
                || die "release mode requires an exact KILIX_VOICE_LIB_VERSION when dictation is enabled"
            [[ "$KILIX_VOICE_LIB_URL" == https://* ]] \
                || die "release mode requires an HTTPS KILIX_VOICE_LIB_URL when dictation is enabled"
            [[ "$KILIX_VOICE_LIB_SHA256" =~ ^[0-9a-fA-F]{64}$ ]] \
                || die "release mode requires a 64-character KILIX_VOICE_LIB_SHA256 when dictation is enabled"
            [[ "$KILIX_VOICE_MODEL_URL" == https://* ]] \
                || die "release mode requires an HTTPS KILIX_VOICE_MODEL_URL when dictation is enabled"
            [[ "$KILIX_VOICE_MODEL_SHA256" =~ ^[0-9a-fA-F]{64}$ ]] \
                || die "release mode requires a 64-character KILIX_VOICE_MODEL_SHA256 when dictation is enabled"
            ;;
        *) die "invalid PLEBIAN_OS_INSTALL_VOICE_MODEL=$INSTALL_VOICE_MODEL (expected 0/1)" ;;
    esac
}

as_user() {
    if [ "$DRY_RUN" = 1 ]; then echo "    + (as $TARGET_USER) $*"; return 0; fi
    command -v setpriv >/dev/null 2>&1 \
        || die "setpriv is required to run provisioning commands as $TARGET_USER"
    setpriv --reuid "$TARGET_UID" --regid "$TARGET_GID" --init-groups \
        --reset-env -- "$@"
}

validate_target_user() {
    local entry shell home_uid
    entry="$(getent passwd "$TARGET_USER" 2>/dev/null)" \
        || die "no such user: $TARGET_USER"
    IFS=: read -r _ _ TARGET_UID TARGET_GID _ USER_HOME shell <<<"$entry"
    case "$TARGET_UID" in ''|*[!0-9]*) die "invalid uid for $TARGET_USER" ;; esac
    if [ "$TARGET_UID" -lt 1000 ] || [ "$TARGET_UID" -ge 65534 ]; then
        die "target user $TARGET_USER must be a regular non-root account (uid 1000-65533)"
    fi
    case "$USER_HOME" in
        /*) ;;
        *) die "target user $TARGET_USER has a non-absolute home: $USER_HOME" ;;
    esac
    if [ "$USER_HOME" = / ] || [ "$USER_HOME" = /root ]; then
        die "target user $TARGET_USER has a system home: $USER_HOME"
    fi
    if [ ! -d "$USER_HOME" ] || [ -L "$USER_HOME" ]; then
        die "home for $TARGET_USER must be an existing non-symlink directory: $USER_HOME"
    fi
    home_uid="$(stat -c '%u' "$USER_HOME" 2>/dev/null)" \
        || die "could not inspect home for $TARGET_USER: $USER_HOME"
    [ "$home_uid" = "$TARGET_UID" ] \
        || die "home for $TARGET_USER is not owned by that user: $USER_HOME"
    case "$shell" in ''|*/false|*/nologin) die "target user $TARGET_USER has a non-login shell: ${shell:-<empty>}" ;; esac
    [ -x "$shell" ] || die "target user $TARGET_USER has an unusable login shell: $shell"
}

ensure_private_storage_root() {
    local path="$1" anchor="$2" label="$3"
    local secure_intermediates="${4:-0}"
    local resolved anchor_real path_real metadata current remaining component
    local -a allocations
    case "$path" in
        /*) ;;
        *) die "$label must be an absolute path: $path" ;;
    esac
    case "$path" in
        "$anchor"/*) ;;
        *) die "$label must be a strict descendant of $anchor: $path" ;;
    esac

    # readlink -m resolves both dot components and every existing symlink.  An
    # exact match therefore establishes a normal, symlink-free path before an
    # as-user mkdir/chmod can touch it.  Repeat the check after creation to
    # catch a path that changed during allocation.
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
        if [ "$DRY_RUN" = 1 ]; then
            echo "    + (as $TARGET_USER) install -d -m 0700 $current"
            continue
        fi
        as_user install -d -m 0700 -- "$current" \
            || die "could not create or secure $label as $TARGET_USER: $current"
        resolved="$(readlink -m -- "$current" 2>/dev/null)" \
            || die "could not resolve allocated $label component: $current"
        if [ "$resolved" != "$current" ] || [ ! -d "$current" ] \
            || [ -L "$current" ]; then
            die "$label acquired an unsafe directory component: $current"
        fi
        metadata="$(stat -c '%u:%a' -- "$current" 2>/dev/null)" \
            || die "could not inspect allocated $label component: $current"
        [ "$metadata" = "$TARGET_UID:700" ] \
            || die "$label components must be owned by $TARGET_USER with mode 0700: $current ($metadata)"
    done
    [ "$DRY_RUN" != 1 ] || return 0

    resolved="$(readlink -m -- "$path" 2>/dev/null)" \
        || die "could not resolve allocated $label: $path"
    if [ "$resolved" != "$path" ] || [ ! -d "$path" ] || [ -L "$path" ]; then
        die "$label became an unsafe directory during allocation: $path"
    fi

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
    # KILIX_DESKTOP_DIR can deliberately point at operator-shared storage for
    # custom providers.  Only the canonical Pleb-owned location (or a child of
    # it) is ours to create or chmod.
    case "$state_dir" in
        "$PLEB_DATA_HOME")
            ensure_private_storage_root "$PLEB_DATA_HOME" \
                "$PLEB_STORAGE_HOME" PLEB_DATA_HOME 1
            ;;
        "$PLEB_DATA_HOME"/*)
            ensure_private_storage_root "$PLEB_DATA_HOME" \
                "$PLEB_STORAGE_HOME" PLEB_DATA_HOME 1
            ensure_private_storage_root "$state_dir" "$PLEB_DATA_HOME" \
                KILIX_DESKTOP_DIR 1
            ;;
        *) return 0 ;;
    esac
}

allocate_coordinated_private_storage() {
    local resolved home_real data_real i
    local -a labels roots category_labels category_roots category_paths
    case "$GPU_TERMINAL_HOME" in
        /*) ;;
        *) die "GPU_TERMINAL_HOME must be an absolute path: $GPU_TERMINAL_HOME" ;;
    esac
    case "$GPU_TERMINAL_HOME" in
        "$USER_HOME"/*) ;;
        *) die "GPU_TERMINAL_HOME must be a strict descendant of $USER_HOME: $GPU_TERMINAL_HOME" ;;
    esac
    resolved="$(readlink -m -- "$GPU_TERMINAL_HOME" 2>/dev/null)" \
        || die "could not resolve GPU_TERMINAL_HOME: $GPU_TERMINAL_HOME"
    [ "$resolved" = "$GPU_TERMINAL_HOME" ] \
        || die "GPU_TERMINAL_HOME must not contain symlinks or non-normal components: $GPU_TERMINAL_HOME"

    # Treat the target user's existing home as the trust anchor.  The generic
    # helper establishes the shared data root first; component roots can then
    # be proven to remain strict real-path descendants of it.
    ensure_private_storage_root "$GPU_TERMINAL_HOME" "$USER_HOME" \
        "GPU_TERMINAL_HOME"
    if [ "$DRY_RUN" != 1 ]; then
        home_real="$(readlink -f -- "$USER_HOME" 2>/dev/null)" \
            || die "could not resolve target home: $USER_HOME"
        data_real="$(readlink -f -- "$GPU_TERMINAL_HOME" 2>/dev/null)" \
            || die "could not resolve allocated GPU_TERMINAL_HOME: $GPU_TERMINAL_HOME"
        case "$data_real" in
            "$home_real"/*) ;;
            *) die "GPU_TERMINAL_HOME escaped $TARGET_USER's home: $GPU_TERMINAL_HOME" ;;
        esac
    fi

    labels=(
        PLEB_STORAGE_HOME
        KILIX_STORAGE_HOME
        KILIX95_STORAGE_HOME
        PLEBIAN_OS_STORAGE_HOME
    )
    roots=(
        "$PLEB_STORAGE_HOME"
        "$KILIX_STORAGE_HOME"
        "$KILIX95_STORAGE_HOME"
        "$PLEBIAN_OS_STORAGE_HOME"
    )
    for i in "${!roots[@]}"; do
        ensure_private_storage_root "${roots[$i]}" "$GPU_TERMINAL_HOME" \
            "${labels[$i]}" 1
    done

    # Secure every app-owned category before the provision lock or a version
    # probe can become its first writer.  Each category has its own component
    # root as the trust anchor: a misplaced override is rejected instead of
    # chmodding an operator-managed directory elsewhere.  KILIX_DESKTOP_DIR is
    # handled separately below: its canonical PLEB_DATA_HOME location is
    # private, while a cross-provider/shared-data override remains untouched.
    category_labels=(
        PLEB_CONFIG_HOME
        PLEB_STATE_HOME
        PLEB_CACHE_HOME
        PLEB_SESSION_HOME
        PLEB_DATA_HOME
        KILIX_CONFIG_HOME
        KILIX_STATE_DIRECTORY
        KILIX_CACHE_HOME
        KILIX_SESSION_HOME
        KILIX_BUILD_DIRECTORY
        KILIX_DATA_HOME
        KILIX_PREBUILT_HOME
        KILIX95_CONFIG_HOME
        KILIX95_STATE_HOME
        KILIX95_CACHE_HOME
        KILIX95_SESSION_HOME
        KILIX95_DATA_HOME
        PLEBIAN_OS_SESSION_HOME
    )
    category_roots=(
        "$PLEB_STORAGE_HOME"
        "$PLEB_STORAGE_HOME"
        "$PLEB_STORAGE_HOME"
        "$PLEB_STORAGE_HOME"
        "$PLEB_STORAGE_HOME"
        "$KILIX_STORAGE_HOME"
        "$KILIX_STORAGE_HOME"
        "$KILIX_STORAGE_HOME"
        "$KILIX_STORAGE_HOME"
        "$KILIX_STORAGE_HOME"
        "$KILIX_STORAGE_HOME"
        "$KILIX_STORAGE_HOME"
        "$KILIX95_STORAGE_HOME"
        "$KILIX95_STORAGE_HOME"
        "$KILIX95_STORAGE_HOME"
        "$KILIX95_STORAGE_HOME"
        "$KILIX95_STORAGE_HOME"
        "$PLEBIAN_OS_STORAGE_HOME"
    )
    category_paths=(
        "$PLEB_CONFIG_HOME"
        "$PLEB_STATE_HOME"
        "$PLEB_CACHE_HOME"
        "$PLEB_SESSION_HOME"
        "$PLEB_DATA_HOME"
        "$KILIX_CONFIG_HOME"
        "$KILIX_STATE_DIRECTORY"
        "$KILIX_CACHE_HOME"
        "$KILIX_SESSION_HOME"
        "$KILIX_BUILD_DIRECTORY"
        "$KILIX_DATA_HOME"
        "$KILIX_PREBUILT_HOME"
        "$KILIX95_CONFIG_HOME"
        "$KILIX95_STATE_HOME"
        "$KILIX95_CACHE_HOME"
        "$KILIX95_SESSION_HOME"
        "$KILIX95_DATA_HOME"
        "$PLEBIAN_OS_SESSION_HOME"
    )
    for i in "${!category_paths[@]}"; do
        ensure_private_storage_root "${category_paths[$i]}" \
            "${category_roots[$i]}" "${category_labels[$i]}" 1
    done
    secure_managed_pleb_desktop_dir "$KILIX_DESKTOP_DIR"
}

PROVISION_LOCK_FD=""
KILIX_PROVISION_LOCK_FD=""
KILIX_PROVISION_LOCK_PATH=""
DESKTOP_WALLPAPER_TMP=""
DESKTOP_WALLPAPER_CREATED_DIRS=()
VERSION_MARKER_TMP=""
ARTWORK_NOTICE_TMP=""
ARTWORK_NOTICE_CREATED_DIRS=()
SUDOERS=/etc/sudoers.d/plebian-os-provision

cleanup() {
    if [ "$DRY_RUN" != 1 ]; then
        rm -f "$SUDOERS"
        [ -z "${DESKTOP_WALLPAPER_TMP:-}" ] \
            || rm -f -- "$DESKTOP_WALLPAPER_TMP"
        [ -z "${VERSION_MARKER_TMP:-}" ] \
            || rm -f -- "$VERSION_MARKER_TMP"
        [ -z "${ARTWORK_NOTICE_TMP:-}" ] \
            || rm -f -- "$ARTWORK_NOTICE_TMP"
        local i
        for ((i=${#DESKTOP_WALLPAPER_CREATED_DIRS[@]}-1; i>=0; i--)); do
            rmdir -- "${DESKTOP_WALLPAPER_CREATED_DIRS[$i]}" 2>/dev/null || true
        done
        for ((i=${#ARTWORK_NOTICE_CREATED_DIRS[@]}-1; i>=0; i--)); do
            rmdir -- "${ARTWORK_NOTICE_CREATED_DIRS[$i]}" 2>/dev/null || true
        done
        if [ -n "${PROVISION_LOCK_FD:-}" ]; then
            flock -u "$PROVISION_LOCK_FD" 2>/dev/null || true
            exec {PROVISION_LOCK_FD}>&-
        fi
        if [ -n "${KILIX_PROVISION_LOCK_FD:-}" ]; then
            flock -u "$KILIX_PROVISION_LOCK_FD" 2>/dev/null || true
            exec {KILIX_PROVISION_LOCK_FD}>&-
        fi
    fi
}

restore_provision_signal_traps() {
    if [ -n "${PROVISION_LOCK_FD:-}" ] \
        || [ -n "${KILIX_PROVISION_LOCK_FD:-}" ]; then
        trap 'cleanup; trap - EXIT; exit 143' INT TERM HUP
    else
        trap - INT TERM HUP
    fi
}

acquire_provision_lock() {
    local lock owner
    lock="$PLEB_STATE_HOME/update.lock"
    log "serializing provisioning with Pleb updates -> $lock"
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + (as $TARGET_USER) create $lock (0600), then acquire a nonblocking flock"
        return 0
    fi
    command -v flock >/dev/null 2>&1 \
        || die "flock is required to serialize provisioning with Pleb updates"
    as_user mkdir -p "$PLEB_STATE_HOME" \
        || die "could not create Pleb state directory as $TARGET_USER: $PLEB_STATE_HOME"
    if [ ! -d "$PLEB_STATE_HOME" ] || [ -L "$PLEB_STATE_HOME" ]; then
        die "Pleb state path is not a safe directory: $PLEB_STATE_HOME"
    fi
    owner="$(stat -c '%u' "$PLEB_STATE_HOME" 2>/dev/null)" \
        || die "could not inspect Pleb state directory: $PLEB_STATE_HOME"
    [ "$owner" = "$TARGET_UID" ] \
        || die "Pleb state directory is not owned by $TARGET_USER: $PLEB_STATE_HOME"
    as_user touch "$lock" || die "could not create Pleb update lock as $TARGET_USER: $lock"
    if [ ! -f "$lock" ] || [ -L "$lock" ]; then
        die "Pleb update lock is not a safe regular file: $lock"
    fi
    owner="$(stat -c '%u' "$lock" 2>/dev/null)" \
        || die "could not inspect Pleb update lock: $lock"
    [ "$owner" = "$TARGET_UID" ] \
        || die "Pleb update lock is not owned by $TARGET_USER: $lock"
    as_user chmod 0600 "$lock" || die "could not secure Pleb update lock: $lock"
    exec {PROVISION_LOCK_FD}>>"$lock"
    flock -n "$PROVISION_LOCK_FD" \
        || die "another Pleb update or provisioning run is active (lock: $lock)"
    trap cleanup EXIT
    trap 'cleanup; trap - EXIT; exit 143' INT TERM HUP
}

acquire_kilix_provision_lock() {
    local lock owner metadata path_identity fd_identity
    lock="$KILIX_STATE_DIRECTORY/build-update.lock"
    log "serializing provisioning with Kilix builds/updates -> $lock"
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + (as $TARGET_USER) create $lock (0600), then acquire a nonblocking flock"
        return 0
    fi
    command -v flock >/dev/null 2>&1 \
        || die "flock is required to serialize provisioning with Kilix builds/updates"
    [ -d "$KILIX_STATE_DIRECTORY" ] && [ ! -L "$KILIX_STATE_DIRECTORY" ] \
        || die "Kilix state path is not a safe directory: $KILIX_STATE_DIRECTORY"
    metadata="$(stat -c '%u:%a' -- "$KILIX_STATE_DIRECTORY" 2>/dev/null)" \
        || die "could not inspect Kilix state directory"
    [ "$metadata" = "$TARGET_UID:700" ] \
        || die "Kilix state directory is not private and owned by $TARGET_USER"
    if [ -e "$lock" ] || [ -L "$lock" ]; then
        [ -f "$lock" ] && [ ! -L "$lock" ] \
            || die "refusing unsafe Kilix transaction lock: $lock"
        owner="$(stat -c '%u' -- "$lock" 2>/dev/null)" \
            || die "could not inspect Kilix transaction lock owner"
        [ "$owner" = "$TARGET_UID" ] \
            || die "Kilix transaction lock is not owned by $TARGET_USER"
    else
        as_user touch "$lock" \
            || die "could not create Kilix transaction lock as $TARGET_USER: $lock"
    fi
    as_user chmod 0600 "$lock" \
        || die "could not secure Kilix transaction lock: $lock"
    [ -f "$lock" ] && [ ! -L "$lock" ] \
        || die "Kilix transaction lock is not a safe regular file: $lock"
    owner="$(stat -c '%u' -- "$lock" 2>/dev/null)" \
        || die "could not inspect Kilix transaction lock owner"
    [ "$owner" = "$TARGET_UID" ] \
        || die "Kilix transaction lock is not owned by $TARGET_USER"
    [ "$(stat -c '%a:%h' -- "$lock" 2>/dev/null)" = 600:1 ] \
        || die "Kilix transaction lock must be mode 0600 and singly linked"
    exec {KILIX_PROVISION_LOCK_FD}>>"$lock" \
        || die "could not open Kilix transaction lock"
    [ -f "$lock" ] && [ ! -L "$lock" ] \
        || die "Kilix transaction lock changed while it was opened"
    path_identity="$(stat -c '%d:%i' -- "$lock" 2>/dev/null)" \
        || die "could not inspect Kilix transaction lock identity"
    fd_identity="$(stat -Lc '%d:%i' -- "/proc/$$/fd/$KILIX_PROVISION_LOCK_FD" 2>/dev/null)" \
        || die "could not inspect Kilix transaction lock descriptor"
    [ "$fd_identity" = "$path_identity" ] \
        || die "Kilix transaction lock changed while it was opened"
    flock -n "$KILIX_PROVISION_LOCK_FD" \
        || die "another Kilix build/update is active (lock: $lock)"
    KILIX_PROVISION_LOCK_PATH="$(cd "$KILIX_STATE_DIRECTORY" && pwd -P)/build-update.lock"
    trap cleanup EXIT
    trap 'cleanup; trap - EXIT; exit 143' INT TERM HUP
}

write_session_default() {
    local name="$1" value="$2"
    printf 'if [ -z "${%s+x}" ]; then %s=%q; fi\n' "$name" "$name" "$value"
}

# ── merging the rendered session config into the installed one ───────────────
# Step 5 renders every value this run resolved and then wrote the whole of
# /etc/pleb/session.env from that render. Anything the render did not contain
# was therefore dropped: a key this script has never emitted, the comment an
# operator wrote above it, the block they appended at the end. And every key the
# render defaulted — the three optional-desktop `*_AUTO_INSTALL` switches among
# them — was reset on top of the operator's answer. That is the defect eaca706
# fixed for the release closure, on the half a release does not control, and it
# cannot be fixed the same way: there is no list of operator keys to read back,
# because an operator may add keys nothing here has ever heard of.
#
# So the render is merged into the file the machine already has instead of
# replacing it. plebian-os-select-closure does exactly this to move a closure
# without disturbing anything else, and it classifies by the same rule: what a
# release controls is enumerated, and everything else in the file is somebody
# else's. The shape both tools rewrite in place is the one write_session_default
# emits; keep this regex in step with that tool's MANAGED_LINE_RE.
SESSION_MANAGED_LINE_RE='^if \[ -z "\$\{([A-Za-z_][A-Za-z0-9_]*)\+x\}" \]; then ([A-Za-z_][A-Za-z0-9_]*)=(.*); fi$'
# A line that opens like a managed one but is not one any more — the selector
# refuses to rewrite these; here they count as a hand edit of that same key, so
# nothing is appended underneath them to argue with.
SESSION_MANAGED_PREFIX_RE='^if \[ -z "\$\{([A-Za-z_][A-Za-z0-9_]*)\+x\}" \]; then '
# Any other assignment of a name at the start of a line: a hand edit.
SESSION_ASSIGNMENT_RE='^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)='

# The key one session.env line assigns, and how. Prints "<key>\t<managed|bare>"
# for an assignment and nothing for anything else (comments, exports, blanks).
session_env_line_assignment() {
    local line="$1"
    if [[ $line =~ $SESSION_MANAGED_LINE_RE ]] \
            && [ "${BASH_REMATCH[1]}" = "${BASH_REMATCH[2]}" ]; then
        printf '%s\tmanaged\n' "${BASH_REMATCH[1]}"
    elif [[ $line =~ $SESSION_MANAGED_PREFIX_RE ]]; then
        printf '%s\tbare\n' "${BASH_REMATCH[1]}"
    elif [[ $line =~ $SESSION_ASSIGNMENT_RE ]]; then
        printf '%s\tbare\n' "${BASH_REMATCH[1]}"
    fi
}

# Whether this run — rather than the machine it is re-running on — is the
# authority for one key. Explicit environment or command line first, because
# that is how a value is deliberately changed; then the two sets this script
# owns by definition. Everything else answers "no", including every key nobody
# ever classified, which is the safe direction for a file operators are invited
# to edit by hand.
session_key_is_run_owned() {
    local key="$1" flag
    [ -z "${PERSISTED_KEY_EXPLICIT[$key]:-}" ] || return 0
    [ -z "${SESSION_ENV_EXPLICIT[$key]:-}" ] || return 0
    flag="${SESSION_KEY_EXPLICIT_FLAG[$key]:-}"
    if [ -n "$flag" ] && [ "${!flag:-0}" = 1 ]; then
        return 0
    fi
    case " ${SESSION_LAYOUT_KEYS[*]} ${PROVISION_OWNED_KEYS[*]} " in
        *" $key "*) return 0 ;;
    esac
    return 1
}

# Merge the rendered file into the installed one, writing the result to a third
# path. Line for line:
#
#   * a managed line for a key this run owns  -> the rendered line
#   * any other managed line                  -> kept exactly as it stands
#   * a hand-written `NAME=value`             -> kept exactly as it stands, and
#     the render adds no competing line for that key: the operator's assignment
#     is what a login shell already resolves, so a guarded default underneath it
#     would be dead text
#   * comments, exports, blanks, anything else -> kept exactly as it stands
#
# then keys the render has and the file does not (a release can introduce one,
# and `--kiosk` introduces PLEB_RESPAWN) are appended under a comment naming who
# added them, and the rendered lines that assign nothing — the export block — are
# appended only if the file does not already carry them. Comments the template
# carries are decoration and are never appended: the file keeps its own.
# Ordering follows the installed file, so a run that resolves what the machine
# already records rewrites every line to itself and the file comes out
# byte-identical.
merge_session_env() {
    local rendered="$1" installed="$2" out="$3"
    local line key form assignment
    local -A rendered_managed=() rendered_seen=() installed_lines=()
    local -a rendered_keys=() rendered_literals=() appended=() unmanaged=()

    if ! bash -n "$installed" 2>/dev/null; then
        warn "$installed does not parse as shell, so nothing here can tell what it means"
        return 1
    fi

    while IFS= read -r line || [ -n "$line" ]; do
        assignment="$(session_env_line_assignment "$line")"
        if [ -n "$assignment" ]; then
            key="${assignment%%$'\t'*}"
            rendered_managed["$key"]="$line"
            rendered_keys+=("$key")
        elif [ -n "$line" ] && [ "${line#\#}" = "$line" ]; then
            rendered_literals+=("$line")
        fi
    done <"$rendered"

    : >"$out"
    while IFS= read -r line || [ -n "$line" ]; do
        [ -z "$line" ] || installed_lines["$line"]=1
        assignment="$(session_env_line_assignment "$line")"
        if [ -n "$assignment" ]; then
            key="${assignment%%$'\t'*}"
            form="${assignment#*$'\t'}"
            if [ -n "${rendered_managed[$key]+x}" ] && [ -z "${rendered_seen[$key]:-}" ]; then
                rendered_seen["$key"]=1
                if session_key_is_run_owned "$key"; then
                    if [ "$form" = managed ]; then
                        printf '%s\n' "${rendered_managed[$key]}" >>"$out"
                        continue
                    fi
                    [ "$line" = "${rendered_managed[$key]}" ] || unmanaged+=("$key")
                fi
            fi
        fi
        printf '%s\n' "$line" >>"$out"
    done <"$installed"

    for key in "${rendered_keys[@]}"; do
        [ -z "${rendered_seen[$key]:-}" ] || continue
        rendered_seen["$key"]=1
        appended+=("$key")
    done
    if [ "${#appended[@]}" -gt 0 ]; then
        printf '%s\n' "# Added by plebian-os-provision $PLEBIAN_OS_VERSION." >>"$out"
        for key in "${appended[@]}"; do
            printf '%s\n' "${rendered_managed[$key]}" >>"$out"
        done
        log "session config gains ${#appended[@]} key(s) this release introduces: ${appended[*]}"
    fi
    for line in "${rendered_literals[@]}"; do
        [ -z "${installed_lines[$line]:-}" ] || continue
        printf '%s\n' "$line" >>"$out"
    done
    if [ "${#unmanaged[@]}" -gt 0 ]; then
        warn "$installed assigns ${#unmanaged[@]} key(s) this run resolves for itself outside the managed form: ${unmanaged[*]}"
        warn "those lines were left exactly as they are; they win over anything written here"
    fi
}

# Every key one session config assigns, in first-assignment order.
session_env_assigned_keys() {
    local line key assignment
    local -A seen=()
    while IFS= read -r line || [ -n "$line" ]; do
        assignment="$(session_env_line_assignment "$line")"
        [ -n "$assignment" ] || continue
        key="${assignment%%$'\t'*}"
        [ -z "${seen[$key]:-}" ] || continue
        seen["$key"]=1
        printf '%s\n' "$key"
    done <"$1"
}

# What a login shell would read out of one session config for a given set of
# names: "<key>\t<set|unset>\t<value>", resolved by sourcing in a subshell with
# all of them unset first, so guarded defaults, bare operator edits and later
# overrides all land where they really land. The caller passes the same names
# for every file it compares, so a key one file assigns in a shape nothing here
# recognizes is still read out of it rather than counted as absent.
session_env_resolved_values() {
    local file="$1"
    shift
    [ "$#" -gt 0 ] || return 0
    (
        for _name in "$@"; do unset "$_name"; done
        # shellcheck source=/dev/null
        . "$file" >/dev/null 2>&1 || exit 1
        for _name in "$@"; do
            printf '%s\t%s\t%s\n' "$_name" "${!_name+set}" "${!_name-}"
        done
    )
}

# Prove the merged candidate before anything is swapped in, the way the closure
# selector proves its own: read all three files back the way a login shell would
# and refuse unless every key resolves to the value the merge promised — this
# run's for the keys it owns, the machine's for every other key it already had,
# and no key lost on the way. A candidate that cannot be read at all is refused
# for the same reason.
verify_merged_session_env() {
    local rendered="$1" installed="$2" candidate="$3"
    local key state value expected line
    local -A rendered_set=() rendered_values=()
    local -A installed_set=() installed_values=()
    local -A candidate_set=() candidate_values=()
    local -A installed_forms=() union=()
    local -a names=()

    if ! bash -n "$candidate" 2>/dev/null; then
        warn "the merged session config does not parse as shell"
        return 1
    fi
    while IFS= read -r key; do union["$key"]=1; done < <(
        session_env_assigned_keys "$rendered"
        session_env_assigned_keys "$installed"
        session_env_assigned_keys "$candidate"
    )
    names=("${!union[@]}")
    [ "${#names[@]}" -gt 0 ] || return 0
    while IFS=$'\t' read -r key state value; do
        rendered_set["$key"]="$state"; rendered_values["$key"]="$value"
    done < <(session_env_resolved_values "$rendered" "${names[@]}")
    while IFS=$'\t' read -r key state value; do
        installed_set["$key"]="$state"; installed_values["$key"]="$value"
    done < <(session_env_resolved_values "$installed" "${names[@]}")
    while IFS=$'\t' read -r key state value; do
        candidate_set["$key"]="$state"; candidate_values["$key"]="$value"
    done < <(session_env_resolved_values "$candidate" "${names[@]}")
    if [ "${#candidate_set[@]}" -eq 0 ]; then
        warn "the merged session config could not be read back"
        return 1
    fi
    while IFS=$'\t' read -r key state; do
        [ -n "${installed_forms[$key]:-}" ] || installed_forms["$key"]="$state"
    done < <(
        while IFS= read -r line || [ -n "$line" ]; do
            session_env_line_assignment "$line"
        done <"$installed"
    )

    for key in "${names[@]}"; do
        if [ "${installed_set[$key]:-}" = set ] && [ "${candidate_set[$key]:-}" != set ]; then
            warn "the merged session config would drop $key"
            return 1
        fi
        # The machine answers for every key it already had, unless this run owns
        # it and answered in the shape this script writes.
        if [ "${installed_set[$key]:-}" = set ] \
                && { [ "${installed_forms[$key]:-}" != managed ] \
                     || ! session_key_is_run_owned "$key"; }; then
            expected="${installed_values[$key]}"
        elif [ "${rendered_set[$key]:-}" = set ]; then
            expected="${rendered_values[$key]}"
        elif [ "${installed_set[$key]:-}" = set ]; then
            expected="${installed_values[$key]}"
        else
            continue
        fi
        if [ "${candidate_set[$key]:-}" != set ] \
                || [ "${candidate_values[$key]}" != "$expected" ]; then
            warn "the merged session config would read $key='${candidate_values[$key]-}' instead of '$expected'"
            return 1
        fi
    done
}

# Read one knob back out of the session config the way a login shell would see
# it: sourcing in a SUBSHELL with that name unset resolves both the guarded
# defaults write_session_default emits and a bare `NAME=value` operator edit,
# and leaves this script's own variables untouched. Only a root-owned,
# non-symlink regular file that is not group/world-writable is trusted —
# anything else is treated as "no pin" and the caller keeps its default.
session_env_pin() {
    local name="$1" env="$2" owner mode
    [ -f "$env" ] && [ ! -L "$env" ] || return 1
    owner="$(stat -c '%u' "$env" 2>/dev/null)" || return 1
    mode="$(stat -c '%a' "$env" 2>/dev/null)" || return 1
    [ "$owner" = 0 ] && (( (8#$mode & 8#22) == 0 )) || return 1
    (
        unset "$name"
        # shellcheck source=/dev/null
        . "$env" >/dev/null 2>&1 || exit 1
        [ -n "${!name+x}" ] || exit 1
        printf '%s' "${!name}"
    )
}

# Step 5 rewrites /etc/pleb/session.env wholesale, so a window-manager choice an
# operator pinned there by hand would silently revert on a reprovision. Explicit
# environment wins, then that existing pin (an operator who set PLEB_WM=none
# keeps a no-WM session), then the distribution defaults: Openbox as a safety
# net, with GUI applications kept inside Kilix pages and panes.
resolve_session_wm_defaults() {
    local env=/etc/pleb/session.env pinned
    if [ -z "$PLEB_WM" ] && pinned="$(session_env_pin PLEB_WM "$env")"; then
        PLEB_WM="$pinned"
    fi
    if [ -z "$KILIX_RUN_ALIASES" ] \
            && pinned="$(session_env_pin KILIX_RUN_ALIASES "$env")"; then
        KILIX_RUN_ALIASES="$pinned"
    fi
    PLEB_WM="${PLEB_WM:-openbox}"
    KILIX_RUN_ALIASES="${KILIX_RUN_ALIASES:-1}"
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

validate_desktop_wallpaper() {
    local path="$1" actual
    [ -f "$path" ] && [ ! -L "$path" ] \
        || die "desktop wallpaper is not a safe regular file: $path"
    command -v sha256sum >/dev/null 2>&1 \
        || die "sha256sum is required to validate the desktop wallpaper"
    actual="$(sha256sum "$path" | awk '{print $1}')" \
        || die "could not hash desktop wallpaper: $path"
    [ "$actual" = "$DESKTOP_WALLPAPER_SHA256" ] \
        || die "desktop wallpaper checksum mismatch: $path"
    python3 - "$path" <<'PY' \
        || die "desktop wallpaper does not satisfy the 1920x1080 RGB PNG contract: $path"
import pathlib
import struct
import sys

data = pathlib.Path(sys.argv[1]).read_bytes()
if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
    raise SystemExit(1)
width, height, depth, color_type, compression, filtering, interlace = \
    struct.unpack(">IIBBBBB", data[16:29])
if (width, height, depth, color_type, compression, filtering, interlace) != \
        (1920, 1080, 8, 2, 0, 0, 0):
    raise SystemExit(1)
PY
}

as_target_readonly() {
    if [ "$(id -u)" = "$TARGET_UID" ] && [ "$(id -g)" = "$TARGET_GID" ]; then
        "$@"
        return
    fi
    if [ "$(id -u)" != 0 ]; then
        die "cannot validate $TARGET_USER's Plebian-OS checkout without root"
    fi
    command -v setpriv >/dev/null 2>&1 \
        || die "setpriv is required to validate the target user's Plebian-OS checkout"
    setpriv --reuid "$TARGET_UID" --regid "$TARGET_GID" --init-groups \
        --reset-env -- "$@"
}

validated_checkout_wallpaper() {
    local checkout="$PLEBIAN_OS_DIR" asset remote dirty tracked_blob working_blob
    local owner checkout_real home_real actual resolved fetch_head fetch_mode fetch_lines
    local tag_marker branch_marker
    [ -n "$checkout" ] \
        || die "no PLEBIAN_OS checkout configured for the wallpaper migration"
    case "$checkout" in /*) ;; *) die "PLEBIAN_OS_DIR must be absolute: $checkout" ;; esac
    [ -d "$checkout" ] && [ ! -L "$checkout" ] \
        || die "target user's Plebian-OS checkout is missing or unsafe: $checkout"
    checkout_real="$(readlink -f -- "$checkout" 2>/dev/null)" \
        || die "could not resolve Plebian-OS checkout: $checkout"
    home_real="$(readlink -f -- "$USER_HOME" 2>/dev/null)" \
        || die "could not resolve target home: $USER_HOME"
    case "$checkout_real" in
        "$home_real"/*) ;;
        *) die "Plebian-OS checkout must remain inside $TARGET_USER's home: $checkout" ;;
    esac
    owner="$(stat -c '%u' "$checkout_real" 2>/dev/null)" \
        || die "could not inspect Plebian-OS checkout: $checkout"
    [ "$owner" = "$TARGET_UID" ] \
        || die "Plebian-OS checkout is not owned by $TARGET_USER: $checkout"
    if [ -L "$checkout/.git" ] \
        || { [ ! -d "$checkout/.git" ] && [ ! -f "$checkout/.git" ]; }; then
        die "Plebian-OS path is not a safe git checkout: $checkout"
    fi
    remote="$(as_target_readonly git -C "$checkout" config --get remote.origin.url 2>/dev/null)" \
        || die "could not validate Plebian-OS checkout origin"
    if [ "$remote" != "$PLEBIAN_OS_REPO" ] \
        && [ "${PLEBIAN_OS_TRUST_EXISTING_CHECKOUT:-0}" != 1 ]; then
        die "Plebian-OS checkout at $checkout has origin '$remote', expected '$PLEBIAN_OS_REPO'"
    fi
    dirty="$(as_target_readonly git -C "$checkout" status --porcelain --untracked-files=normal 2>/dev/null)" \
        || die "could not inspect Plebian-OS checkout state"
    [ -z "$dirty" ] \
        || die "Plebian-OS checkout has local changes; refusing wallpaper migration"

    asset="$checkout/assets/desktop/plebian-os.png"
    [ -f "$asset" ] && [ ! -L "$asset" ] \
        || die "validated Plebian-OS checkout lacks the tracked desktop wallpaper: $asset"
    tracked_blob="$(as_target_readonly git -C "$checkout" rev-parse \
        'HEAD:assets/desktop/plebian-os.png' 2>/dev/null)" \
        || die "desktop wallpaper is not tracked at Plebian-OS checkout HEAD"
    working_blob="$(as_target_readonly git -C "$checkout" hash-object -- "$asset" 2>/dev/null)" \
        || die "could not bind desktop wallpaper to Plebian-OS checkout HEAD"
    [ "$working_blob" = "$tracked_blob" ] \
        || die "desktop wallpaper differs from Plebian-OS checkout HEAD"
    if [ -n "$PLEBIAN_OS_REF" ]; then
        actual="$(as_target_readonly git -C "$checkout" rev-parse --verify HEAD 2>/dev/null)" \
            || die "could not resolve Plebian-OS checkout HEAD"
        resolved="$(as_target_readonly git -C "$checkout" rev-parse --verify \
            "${PLEBIAN_OS_REF}^{commit}" 2>/dev/null || true)"
        if [ -z "$resolved" ]; then
            # checkout_pinned_ref deliberately resolves the fetched object from
            # FETCH_HEAD and detaches without creating a local tag. Preserve
            # that trust shape for release-tag upgrades: accept only the one
            # safe FETCH_HEAD record naming the requested tag/branch and only
            # when its commit is exactly the current detached HEAD.
            fetch_head="$(as_target_readonly git -C "$checkout" rev-parse \
                --path-format=absolute --git-path FETCH_HEAD 2>/dev/null)" \
                || die "could not locate FETCH_HEAD for PLEBIAN_OS_REF=$PLEBIAN_OS_REF"
            [ -f "$fetch_head" ] && [ ! -L "$fetch_head" ] \
                || die "missing or unsafe FETCH_HEAD for PLEBIAN_OS_REF=$PLEBIAN_OS_REF"
            owner="$(stat -c '%u' "$fetch_head" 2>/dev/null)" \
                || die "could not inspect Plebian-OS FETCH_HEAD"
            fetch_mode="$(stat -c '%a' "$fetch_head" 2>/dev/null)" \
                || die "could not inspect Plebian-OS FETCH_HEAD mode"
            [ "$owner" = "$TARGET_UID" ] && (( (8#$fetch_mode & 8#22) == 0 )) \
                || die "Plebian-OS FETCH_HEAD has unsafe ownership or mode"
            fetch_lines="$(as_target_readonly awk 'END { print NR }' "$fetch_head")"
            [ "$fetch_lines" = 1 ] \
                || die "PLEBIAN_OS_REF fallback requires exactly one FETCH_HEAD record"
            tag_marker="$(printf "\t\ttag '%s' of " "$PLEBIAN_OS_REF")"
            branch_marker="$(printf "\t\tbranch '%s' of " "$PLEBIAN_OS_REF")"
            if ! as_target_readonly grep -Fq -- "$tag_marker" "$fetch_head" \
                && ! as_target_readonly grep -Fq -- "$branch_marker" "$fetch_head"; then
                die "FETCH_HEAD does not name PLEBIAN_OS_REF=$PLEBIAN_OS_REF"
            fi
            resolved="$(as_target_readonly git -C "$checkout" rev-parse --verify \
                'FETCH_HEAD^{commit}' 2>/dev/null)" \
                || die "FETCH_HEAD does not resolve to a commit"
        fi
        [ "$actual" = "$resolved" ] \
            || die "Plebian-OS checkout HEAD does not match PLEBIAN_OS_REF=$PLEBIAN_OS_REF"
    fi
    printf '%s\n' "$asset"
}

copy_wallpaper_as_target_bounded() {
    local source="$1" destination="$2"
    local limit="${3:-$DESKTOP_WALLPAPER_MAX_BYTES}" label="${4:-desktop wallpaper}"
    local output_fd rc=0
    command -v timeout >/dev/null 2>&1 \
        || die "timeout is required for the unprivileged wallpaper copy"
    exec {output_fd}>"$destination" \
        || die "could not open private wallpaper staging file"
    if as_target_readonly timeout 30s python3 - \
        "$source" "$limit" "$label" >&"$output_fd" <<'PY'
import sys

source, limit_text, label = sys.argv[1:]
limit = int(limit_text)
total = 0
with open(source, "rb", buffering=0) as stream:
    while True:
        chunk = stream.read(min(1024 * 1024, limit + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise SystemExit(f"{label} exceeds bounded copy limit")
        sys.stdout.buffer.write(chunk)
PY
    then
        rc=0
    else
        rc=$?
    fi
    exec {output_fd}>&-
    return "$rc"
}

install_desktop_wallpaper() {
    local repo_root="$SELF_DIR/.." repo_asset source="" dest_dir tmp owner mode size path
    repo_asset="$repo_root/assets/desktop/plebian-os.png"

    # Establish a trusted fixed path before probing or reading the installed
    # asset.  Only the two distribution-owned children may be absent; their
    # fixed ancestors must already be real, root-owned, non-writable dirs.
    for path in / /usr /usr/local /usr/local/share; do
        [ -d "$path" ] && [ ! -L "$path" ] \
            || die "wallpaper destination ancestor is unsafe: $path"
        owner="$(stat -c '%u' "$path" 2>/dev/null)" \
            || die "could not inspect wallpaper destination ancestor: $path"
        mode="$(stat -c '%a' "$path" 2>/dev/null)" \
            || die "could not inspect wallpaper destination ancestor mode: $path"
        [ "$owner" = 0 ] && (( (8#$mode & 8#22) == 0 )) \
            || die "wallpaper destination ancestor is not safely root-owned: $path"
    done
    dest_dir="$(dirname "$DESKTOP_WALLPAPER_DST")"
    for path in /usr/local/share/plebian-os "$dest_dir"; do
        [ ! -L "$path" ] || die "refusing symlink in wallpaper destination: $path"
        if [ -e "$path" ] && [ ! -d "$path" ]; then
            die "wallpaper destination component is not a directory: $path"
        fi
        if [ ! -e "$path" ] && [ "$DRY_RUN" != 1 ]; then
            install -d -o root -g root -m 0755 "$path" \
                || die "could not create wallpaper destination: $path"
            DESKTOP_WALLPAPER_CREATED_DIRS+=("$path")
        fi
        if [ -e "$path" ]; then
            owner="$(stat -c '%u' "$path" 2>/dev/null)" \
                || die "could not inspect wallpaper destination: $path"
            mode="$(stat -c '%a' "$path" 2>/dev/null)" \
                || die "could not inspect wallpaper destination mode: $path"
            [ "$owner" = 0 ] && (( (8#$mode & 8#22) == 0 )) \
                && (( (8#$mode & 8#1) != 0 )) \
                || die "wallpaper destination is not safely root-owned: $path"
        fi
    done

    # A repository checkout is authoritative.  Do not silently reuse an older
    # installed copy if the tracked asset disappeared from a bootstrap checkout.
    if [ -f "$repo_root/VERSION" ]; then
        [ -f "$repo_asset" ] && [ ! -L "$repo_asset" ] \
            || die "tracked desktop wallpaper missing or unsafe: $repo_asset"
        source="$repo_asset"
    elif [ -f "$DESKTOP_WALLPAPER_DST" ] && [ ! -L "$DESKTOP_WALLPAPER_DST" ]; then
        # The remastered ISO stages the asset before firstboot starts.
        source="$DESKTOP_WALLPAPER_DST"
    elif [ -e "$DESKTOP_WALLPAPER_DST" ] || [ -L "$DESKTOP_WALLPAPER_DST" ]; then
        die "installed desktop wallpaper is present but unsafe: $DESKTOP_WALLPAPER_DST"
    else
        # Upgrade bridge: the immutable v0.1.1 updater can deploy this new
        # provisioner but cannot know about the newly added OS-layer payloads.
        # A full reprovision may recover the wallpaper only from the target user's
        # clean, origin-checked checkout and exact tracked blob.
        source="$(validated_checkout_wallpaper)"
    fi

    log "installing Plebian-OS desktop wallpaper -> $DESKTOP_WALLPAPER_DST"
    if [ "$DRY_RUN" = 1 ]; then
        if [ "$source" = "$DESKTOP_WALLPAPER_DST" ]; then
            owner="$(stat -c '%u' "$source" 2>/dev/null)" \
                || die "could not inspect installed desktop wallpaper"
            mode="$(stat -c '%a' "$source" 2>/dev/null)" \
                || die "could not inspect installed desktop wallpaper mode"
            size="$(stat -c '%s' "$source" 2>/dev/null)" \
                || die "could not inspect installed desktop wallpaper size"
            [[ "$size" =~ ^[0-9]+$ ]] && [ "$size" -le "$DESKTOP_WALLPAPER_MAX_BYTES" ] \
                && [ "$owner" = 0 ] && (( (8#$mode & 8#22) == 0 )) \
                || die "installed desktop wallpaper has unsafe ownership, mode, or size"
            validate_desktop_wallpaper "$source"
        else
            tmp="$(mktemp "${TMPDIR:-/tmp}/plebian-os-wallpaper-validate.XXXXXX")" \
                || die "could not create private wallpaper validation file"
            chmod 0600 "$tmp" || { rm -f -- "$tmp"; die "could not secure wallpaper validation file"; }
            if ! copy_wallpaper_as_target_bounded "$source" "$tmp"; then
                rm -f -- "$tmp"
                die "could not copy the desktop wallpaper as $TARGET_USER"
            fi
            if ! (validate_desktop_wallpaper "$tmp"); then
                rm -f -- "$tmp"
                return 1
            fi
            rm -f -- "$tmp"
        fi
        echo "    + install root:root 0644 $source $DESKTOP_WALLPAPER_DST (atomic replace)"
        return 0
    fi

    [ ! -L "$DESKTOP_WALLPAPER_DST" ] \
        || die "refusing symlink wallpaper destination: $DESKTOP_WALLPAPER_DST"

    if [ "$source" != "$DESKTOP_WALLPAPER_DST" ]; then
        tmp="$(mktemp "$dest_dir/.plebian-os.png.XXXXXX")" \
            || die "could not stage the desktop wallpaper"
        DESKTOP_WALLPAPER_TMP="$tmp"
        chown root:root "$tmp" && chmod 0600 "$tmp" \
            || die "could not secure private wallpaper staging file"
        if ! copy_wallpaper_as_target_bounded "$source" "$tmp"; then
            rm -f -- "$tmp"
            DESKTOP_WALLPAPER_TMP=""
            die "could not copy the desktop wallpaper as $TARGET_USER"
        fi
        if ! validate_desktop_wallpaper "$tmp"; then
            rm -f -- "$tmp"
            return 1
        fi
        chmod 0644 "$tmp" \
            || die "could not publish validated wallpaper staging permissions"
        if ! mv -fT -- "$tmp" "$DESKTOP_WALLPAPER_DST"; then
            rm -f -- "$tmp"
            DESKTOP_WALLPAPER_TMP=""
            die "could not atomically install the desktop wallpaper"
        fi
        DESKTOP_WALLPAPER_TMP=""
    else
        owner="$(stat -c '%u' "$source" 2>/dev/null)" \
            || die "could not inspect installed desktop wallpaper"
        mode="$(stat -c '%a' "$source" 2>/dev/null)" \
            || die "could not inspect installed desktop wallpaper mode"
        size="$(stat -c '%s' "$source" 2>/dev/null)" \
            || die "could not inspect installed desktop wallpaper size"
        [[ "$size" =~ ^[0-9]+$ ]] && [ "$size" -le "$DESKTOP_WALLPAPER_MAX_BYTES" ] \
            && [ "$owner" = 0 ] && (( (8#$mode & 8#22) == 0 )) \
            || die "installed desktop wallpaper has unsafe ownership, mode, or size"
        validate_desktop_wallpaper "$source"
        chown root:root "$DESKTOP_WALLPAPER_DST" \
            || die "could not enforce wallpaper ownership"
        chmod 0644 "$DESKTOP_WALLPAPER_DST" \
            || die "could not enforce wallpaper permissions"
    fi
    validate_desktop_wallpaper "$DESKTOP_WALLPAPER_DST"
}

install_version_marker() {
    local dest_dir tmp path owner mode

    if ! [[ "$PLEBIAN_OS_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        [ "$PLEBIAN_OS_RELEASE_MODE" != 1 ] \
            || die "release provisioning requires a semantic Plebian-OS version marker"
        warn "not installing a VERSION marker for non-semantic version '$PLEBIAN_OS_VERSION'"
        return 0
    fi

    dest_dir="$(dirname "$VERSION_MARKER_DST")"
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + install root:root 0644 Plebian-OS $PLEBIAN_OS_VERSION marker -> $VERSION_MARKER_DST (atomic replace)"
        return 0
    fi

    # install_desktop_wallpaper establishes this distribution-owned directory
    # immediately before us. Revalidate its complete fixed ancestry before
    # writing a value later trusted by the public --version command.
    for path in / /usr /usr/local /usr/local/share "$dest_dir"; do
        [ -d "$path" ] && [ ! -L "$path" ] \
            || die "VERSION marker destination ancestor is unsafe: $path"
        owner="$(stat -c '%u' "$path" 2>/dev/null)" \
            || die "could not inspect VERSION marker destination ancestor: $path"
        mode="$(stat -c '%a' "$path" 2>/dev/null)" \
            || die "could not inspect VERSION marker destination mode: $path"
        [ "$owner" = 0 ] && (( (8#$mode & 8#22) == 0 )) \
            || die "VERSION marker destination is not safely root-owned: $path"
    done
    [ ! -L "$VERSION_MARKER_DST" ] \
        || die "refusing symlink VERSION marker destination: $VERSION_MARKER_DST"
    if [ -e "$VERSION_MARKER_DST" ] && [ ! -f "$VERSION_MARKER_DST" ]; then
        die "VERSION marker destination is not a regular file: $VERSION_MARKER_DST"
    fi

    tmp="$(mktemp "$dest_dir/.VERSION.XXXXXX")" \
        || die "could not stage the Plebian-OS VERSION marker"
    VERSION_MARKER_TMP="$tmp"
    printf '%s\n' "$PLEBIAN_OS_VERSION" >"$tmp" \
        || die "could not write the Plebian-OS VERSION marker"
    chown root:root "$tmp" && chmod 0644 "$tmp" \
        || die "could not secure the Plebian-OS VERSION marker"
    if ! mv -fT -- "$tmp" "$VERSION_MARKER_DST"; then
        rm -f -- "$tmp"
        VERSION_MARKER_TMP=""
        die "could not atomically install the Plebian-OS VERSION marker"
    fi
    VERSION_MARKER_TMP=""
    [ -f "$VERSION_MARKER_DST" ] && [ ! -L "$VERSION_MARKER_DST" ] \
        && [ "$(cat "$VERSION_MARKER_DST")" = "$PLEBIAN_OS_VERSION" ] \
        && [ "$(stat -c '%u:%g:%a' "$VERSION_MARKER_DST")" = 0:0:644 ] \
        || die "installed Plebian-OS VERSION marker failed validation"
}

validate_artwork_notice() {
    local path="$1" expected="$2" label="$3" kind="$4" actual size
    [ -f "$path" ] && [ ! -L "$path" ] \
        || die "$label is not a safe regular file: $path"
    size="$(stat -c '%s' "$path" 2>/dev/null)" \
        || die "could not inspect $label size: $path"
    [[ "$size" =~ ^[0-9]+$ ]] && [ "$size" -le "$ARTWORK_NOTICE_MAX_BYTES" ] \
        || die "$label exceeds its bounded size contract: $path"
    actual="$(sha256sum "$path" | awk '{print $1}')" \
        || die "could not hash $label: $path"
    [ "$actual" = "$expected" ] || die "$label checksum mismatch: $path"
    python3 - "$path" "$kind" <<'PY' \
        || die "$label text contract failed: $path"
import pathlib
import sys

data = pathlib.Path(sys.argv[1]).read_bytes()
kind = sys.argv[2]
if not data or b"\x00" in data or not data.endswith(b"\n"):
    raise SystemExit(1)
text = data.decode("utf-8")
if kind == "attribution":
    if "../COPYING.GPL-2" not in text or "GPL-2.0-or-later" not in text:
        raise SystemExit(1)
elif kind == "license":
    if "GNU GENERAL PUBLIC LICENSE" not in text or "Version 2, June 1991" not in text:
        raise SystemExit(1)
elif kind == "greeter":
    required = {
        "[greeter]",
        "background=/usr/local/share/plebian-os/wallpapers/plebian-os.png",
        "user-background=false",
    }
    lines = {line.strip() for line in text.splitlines()
             if line.strip() and not line.lstrip().startswith("#")}
    if lines != required or "Debian" in text:
        raise SystemExit(1)
else:
    raise SystemExit(1)
PY
}

validate_artwork_notice_destination_dirs() {
    local path owner mode
    for path in / /usr /usr/local /usr/local/share; do
        [ -d "$path" ] && [ ! -L "$path" ] \
            || die "artwork notice destination ancestor is unsafe: $path"
        owner="$(stat -c '%u' "$path" 2>/dev/null)" \
            || die "could not inspect artwork notice destination ancestor: $path"
        mode="$(stat -c '%a' "$path" 2>/dev/null)" \
            || die "could not inspect artwork notice destination ancestor mode: $path"
        [ "$owner" = 0 ] && (( (8#$mode & 8#22) == 0 )) \
            || die "artwork notice destination ancestor is not safely root-owned: $path"
    done
    for path in \
        /usr/local/share/doc \
        /usr/local/share/doc/plebian-os \
        /usr/local/share/doc/plebian-os/installer; do
        [ ! -L "$path" ] || die "refusing symlink in artwork notice destination: $path"
        if [ -e "$path" ] && [ ! -d "$path" ]; then
            die "artwork notice destination component is not a directory: $path"
        fi
        if [ ! -e "$path" ] && [ "$DRY_RUN" != 1 ]; then
            install -d -o root -g root -m 0755 "$path" \
                || die "could not create artwork notice destination: $path"
            ARTWORK_NOTICE_CREATED_DIRS+=("$path")
        fi
        if [ -e "$path" ]; then
            owner="$(stat -c '%u' "$path" 2>/dev/null)" \
                || die "could not inspect artwork notice destination: $path"
            mode="$(stat -c '%a' "$path" 2>/dev/null)" \
                || die "could not inspect artwork notice destination mode: $path"
            [ "$owner" = 0 ] && (( (8#$mode & 8#22) == 0 )) \
                && (( (8#$mode & 8#1) != 0 )) \
                || die "artwork notice destination is not safely root-owned: $path"
        fi
    done
}

install_artwork_notice() {
    local source="$1" destination="$2" expected="$3" label="$4" kind="$5"
    local tmp owner group mode size dest_dir
    dest_dir="$(dirname "$destination")"
    log "installing $label -> $destination"

    if [ "$source" = "$destination" ]; then
        owner="$(stat -c '%u' "$source" 2>/dev/null)" \
            || die "could not inspect installed $label owner"
        group="$(stat -c '%g' "$source" 2>/dev/null)" \
            || die "could not inspect installed $label group"
        mode="$(stat -c '%a' "$source" 2>/dev/null)" \
            || die "could not inspect installed $label mode"
        size="$(stat -c '%s' "$source" 2>/dev/null)" \
            || die "could not inspect installed $label size"
        [ "$owner" = 0 ] && [ "$group" = 0 ] \
            && [[ "$size" =~ ^[0-9]+$ ]] \
            && [ "$size" -le "$ARTWORK_NOTICE_MAX_BYTES" ] \
            && (( (8#$mode & 8#22) == 0 )) \
            || die "installed $label has unsafe ownership, mode, or size"
        validate_artwork_notice "$source" "$expected" "$label" "$kind"
        if [ "$DRY_RUN" = 1 ]; then
            echo "    + enforce root:root 0644 $destination"
        else
            chown root:root "$destination" && chmod 0644 "$destination" \
                || die "could not enforce installed $label ownership and permissions"
        fi
        return 0
    fi

    if [ "$DRY_RUN" = 1 ]; then
        tmp="$(mktemp "${TMPDIR:-/tmp}/plebian-os-notice-validate.XXXXXX")" \
            || die "could not create private $label validation file"
    else
        tmp="$(mktemp "$dest_dir/.$(basename "$destination").XXXXXX")" \
            || die "could not create private $label staging file"
        ARTWORK_NOTICE_TMP="$tmp"
    fi
    chmod 0600 "$tmp" || { rm -f -- "$tmp"; die "could not secure $label staging file"; }
    if ! copy_wallpaper_as_target_bounded \
        "$source" "$tmp" "$ARTWORK_NOTICE_MAX_BYTES" "$label"; then
        rm -f -- "$tmp"
        ARTWORK_NOTICE_TMP=""
        die "could not copy $label as $TARGET_USER"
    fi
    if ! (validate_artwork_notice "$tmp" "$expected" "$label" "$kind"); then
        rm -f -- "$tmp"
        ARTWORK_NOTICE_TMP=""
        return 1
    fi
    if [ "$DRY_RUN" = 1 ]; then
        rm -f -- "$tmp"
        echo "    + install root:root 0644 $source $destination (atomic replace)"
        return 0
    fi
    chown root:root "$tmp" && chmod 0644 "$tmp" \
        || die "could not publish validated $label staging permissions"
    if ! mv -fT -- "$tmp" "$destination"; then
        rm -f -- "$tmp"
        ARTWORK_NOTICE_TMP=""
        die "could not atomically install $label"
    fi
    ARTWORK_NOTICE_TMP=""
    validate_artwork_notice "$destination" "$expected" "$label" "$kind"
    [ "$(stat -c '%u:%g:%a' "$destination")" = 0:0:644 ] \
        || die "installed $label does not have root:root 0644 metadata"
}

install_artwork_notices() {
    local repo_root="$SELF_DIR/.." attribution_source license_source
    validate_artwork_notice_destination_dirs
    if [ -f "$repo_root/VERSION" ]; then
        attribution_source="$repo_root/assets/installer/ATTRIBUTION.md"
        license_source="$repo_root/assets/COPYING.GPL-2"
        [ -f "$attribution_source" ] && [ ! -L "$attribution_source" ] \
            || die "tracked installer artwork attribution missing or unsafe: $attribution_source"
        [ -f "$license_source" ] && [ ! -L "$license_source" ] \
            || die "tracked GPL version 2 license missing or unsafe: $license_source"
    else
        attribution_source="$INSTALLER_ATTRIBUTION_DST"
        license_source="$GPL2_LICENSE_DST"
        [ -e "$attribution_source" ] || [ -L "$attribution_source" ] \
            || die "installed installer artwork attribution is missing: $attribution_source"
        [ -e "$license_source" ] || [ -L "$license_source" ] \
            || die "installed GPL version 2 license is missing: $license_source"
    fi

    # Publish the license first so the attribution's relative link is never
    # introduced before its target exists.
    install_artwork_notice "$license_source" "$GPL2_LICENSE_DST" \
        "$GPL2_LICENSE_SHA256" "GPL version 2 license" license
    install_artwork_notice "$attribution_source" "$INSTALLER_ATTRIBUTION_DST" \
        "$INSTALLER_ATTRIBUTION_SHA256" "installer artwork attribution" attribution
}

install_lightdm_greeter_branding() {
    local repo_root="$SELF_DIR/.." source path owner mode config_dir
    config_dir="$(dirname "$LIGHTDM_GREETER_CONFIG_DST")"

    # LightDM owns /etc/lightdm. Plebian-OS owns only its drop-in directory and
    # file; reject link tricks or writable ancestors before creating either.
    for path in / /etc /etc/lightdm; do
        [ -d "$path" ] && [ ! -L "$path" ] \
            || die "LightDM greeter destination ancestor is unsafe: $path"
        owner="$(stat -c '%u' "$path" 2>/dev/null)" \
            || die "could not inspect LightDM greeter destination ancestor: $path"
        mode="$(stat -c '%a' "$path" 2>/dev/null)" \
            || die "could not inspect LightDM greeter destination ancestor mode: $path"
        [ "$owner" = 0 ] && (( (8#$mode & 8#22) == 0 )) \
            || die "LightDM greeter destination ancestor is not safely root-owned: $path"
    done
    [ ! -L "$config_dir" ] \
        || die "refusing symlink LightDM greeter configuration directory: $config_dir"
    if [ -e "$config_dir" ] && [ ! -d "$config_dir" ]; then
        die "LightDM greeter configuration path is not a directory: $config_dir"
    fi
    if [ ! -e "$config_dir" ] && [ "$DRY_RUN" != 1 ]; then
        install -d -o root -g root -m 0755 "$config_dir" \
            || die "could not create LightDM greeter configuration directory"
        ARTWORK_NOTICE_CREATED_DIRS+=("$config_dir")
    fi
    if [ -e "$config_dir" ]; then
        owner="$(stat -c '%u' "$config_dir" 2>/dev/null)"
        mode="$(stat -c '%a' "$config_dir" 2>/dev/null)"
        [ "$owner" = 0 ] && (( (8#$mode & 8#22) == 0 )) \
            && (( (8#$mode & 8#1) != 0 )) \
            || die "LightDM greeter configuration directory is not safely root-owned"
        if [ "$DRY_RUN" = 1 ]; then
            echo "    + enforce root:root 0755 $config_dir"
        else
            chown root:root "$config_dir" && chmod 0755 "$config_dir" \
                || die "could not enforce LightDM greeter configuration directory metadata"
        fi
    fi
    [ ! -L "$LIGHTDM_GREETER_CONFIG_DST" ] \
        || die "refusing symlink LightDM greeter configuration"

    if [ -f "$repo_root/VERSION" ]; then
        source="$SELF_DIR/lightdm-gtk-greeter.conf"
        [ -f "$source" ] && [ ! -L "$source" ] \
            || die "tracked LightDM greeter configuration missing or unsafe: $source"
    else
        source="$LIGHTDM_GREETER_CONFIG_DST"
        [ -e "$source" ] || [ -L "$source" ] \
            || die "installed LightDM greeter configuration is missing: $source"
    fi
    install_artwork_notice "$source" "$LIGHTDM_GREETER_CONFIG_DST" \
        "$LIGHTDM_GREETER_CONFIG_SHA256" "LightDM greeter branding" greeter
}

selected_desktop_wallpaper_state_dir() {
    case "$KILIX_DESKTOP_PROVIDER" in
        external|builtin|auto) printf '%s\n' "$KILIX_DESKTOP_DIR" ;;
        *) return 1 ;;
    esac
}

record_default_desktop() {
    # Persist the image's desktop choice where every desktop reads and writes
    # it. Firstboot knew which provider it was provisioning and kept that in
    # its own environment, so the running system had no record a user could
    # see or change: choosing another desktop meant editing a file the
    # installer had written and nothing offered.
    local provider="${KILIX_DESKTOP_PROVIDER:-auto}"
    [ -x "$KILIX_DIR/kilix" ] || return 0
    if as_user env "${install_env[@]}" "$KILIX_DIR/kilix" \
            default-desktop set "$provider" >/dev/null 2>&1; then
        log "desktop    : default recorded as $provider"
    else
        # Not fatal: the session still starts with the provisioned provider,
        # and the desktops can set it later.
        log "desktop    : could not record the default ($provider)"
    fi
}

seed_selected_desktop_wallpaper_state() {
    local state_dir
    state_dir="$(selected_desktop_wallpaper_state_dir)" || {
        log "desktop provider $KILIX_DESKTOP_PROVIDER does not use managed Pleb wallpaper state"
        return 0
    }
    seed_desktop_wallpaper_state "$state_dir" "$DESKTOP_WALLPAPER_DST"
}

seed_desktop_wallpaper_state() {
    local state_dir="${1:?desktop state directory is required}"
    local wallpaper="${2:-$DESKTOP_WALLPAPER_DST}"
    local state_path="$state_dir/.state.json" owner rc

    [ "$DESKTOP" = 1 ] || return 0
    secure_managed_pleb_desktop_dir "$state_dir"
    if [ -e "$state_path" ] || [ -L "$state_path" ]; then
        log "preserving existing Pleb desktop state (including wallpaper): $state_path"
        return 0
    fi
    log "seeding the Plebian-OS wallpaper for a new Pleb desktop -> $state_path"
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + (as $TARGET_USER) create $state_path (0600) only if it still does not exist"
        return 0
    fi

    as_user mkdir -p -- "$state_dir" \
        || die "could not create Pleb desktop state directory as $TARGET_USER: $state_dir"
    [ -d "$state_dir" ] && [ ! -L "$state_dir" ] \
        || die "Pleb desktop state path is not a safe directory: $state_dir"
    owner="$(stat -c '%u' "$state_dir" 2>/dev/null)" \
        || die "could not inspect Pleb desktop state directory: $state_dir"
    [ "$owner" = "$TARGET_UID" ] \
        || die "Pleb desktop state directory is not owned by $TARGET_USER: $state_dir"

    # Write to a user-owned temporary inode, fsync it, then link it into place.
    # link(2) is an atomic create-if-absent: a concurrent first desktop launch or
    # user choice wins, and this provisioner never overwrites it.
    if as_user python3 - "$state_dir" "$state_path" "$wallpaper" <<'PY'
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
        [ "$rc" = 17 ] \
            || die "could not seed Pleb desktop wallpaper state"
        log "Pleb desktop state appeared concurrently; preserving it"
    fi
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

_apt_source_path_allowed() {
    case "$1" in
        "$APT_ETC_ROOT/apt/sources.list"|\
        "$APT_ETC_ROOT/apt/sources.list.d/"*.list|\
        "$APT_ETC_ROOT/apt/sources.list.d/"*.sources) return 0 ;;
        *) return 1 ;;
    esac
}

_load_apt_snapshot_inventory() {
    local inventory="$1" out_name="$2" path
    local -A seen=()
    # shellcheck disable=SC2178  # nameref intentionally targets an array
    local -n out="$out_name"
    out=()
    [ -f "$inventory" ] || return 0
    while IFS= read -r path || [ -n "$path" ]; do
        [ -n "$path" ] || die "corrupt empty path in apt snapshot inventory: $inventory"
        _apt_source_path_allowed "$path" \
            || die "unsafe path in apt snapshot inventory: $path"
        case "$path" in *$'\n'*|*$'\r'*) die "invalid newline in apt snapshot inventory path" ;; esac
        if [ -n "${seen[$path]+x}" ]; then
            die "duplicate path in apt snapshot inventory: $path"
        fi
        seen["$path"]=1
        out+=("$path")
    done < "$inventory"
}

_discover_legacy_apt_snapshot_inventory() {
    local out_name="$1" backup live
    # shellcheck disable=SC2178  # nameref intentionally targets an array
    local -n out="$out_name"
    local -a backups
    shopt -s nullglob
    backups=(
        "$APT_ETC_ROOT/apt/sources.list.plebian-os-disabled"
        "$APT_ETC_ROOT/apt/sources.list.d/"*.plebian-os-disabled
    )
    shopt -u nullglob
    for backup in "${backups[@]}"; do
        [ -e "$backup" ] || [ -L "$backup" ] || continue
        live="${backup%.plebian-os-disabled}"
        case "$live" in *$'\n'*|*$'\r'*) die "invalid newline in legacy apt source path" ;; esac
        _apt_source_path_allowed "$live" \
            || die "unsafe legacy apt snapshot backup path: $backup"
        out+=("$live")
    done
}

_active_apt_source_paths() {
    local managed="$1" out_name="$2" path
    # shellcheck disable=SC2178  # nameref intentionally targets an array
    local -n out="$out_name"
    local -a candidates
    out=()
    shopt -s nullglob
    candidates=(
        "$APT_ETC_ROOT/apt/sources.list"
        "$APT_ETC_ROOT/apt/sources.list.d/"*.list
        "$APT_ETC_ROOT/apt/sources.list.d/"*.sources
    )
    shopt -u nullglob
    for path in "${candidates[@]}"; do
        [ "$path" = "$managed" ] && continue
        [ -f "$path" ] || [ -L "$path" ] || continue
        case "$path" in *$'\n'*|*$'\r'*) die "invalid newline in apt source path" ;; esac
        out+=("$path")
    done
}

_restore_managed_apt_file() {
    local path="$1" backup="$2" existed="$3"
    rm -f "$path" 2>/dev/null || true
    if [ "$existed" = 1 ]; then
        cp -a "$backup" "$path" 2>/dev/null || return 1
    fi
}

restore_live_apt_sources() {
    local apt_dir="$APT_ETC_ROOT/apt" state_dir="$APT_ETC_ROOT/plebian-os"
    local src="$APT_ETC_ROOT/apt/sources.list.d/plebian-os-snapshot.sources"
    local cfg="$APT_ETC_ROOT/apt/apt.conf.d/99plebian-os-snapshot"
    local marker="$state_dir/apt-snapshot" inventory="$state_dir/apt-snapshot-sources"
    local live backup txn codename live_tmp failed=0 rollback_ok=1 signal_rc=0
    local src_old=0 cfg_old=0 marker_old=0 inventory_old=0
    local -a managed=() restored=() active=()
    log "apt snapshot disabled; restoring the exact sources disabled by Plebian-OS"
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + preflight $inventory and every managed backup before changing apt"
        echo "    + restore exactly the inventoried *.plebian-os-disabled sources, then remove only Plebian-OS snapshot files"
        return 0
    fi
    case "$APT_ETC_ROOT" in /*) ;; *) die "PLEBIAN_OS_APT_ETC_ROOT must be absolute" ;; esac
    mkdir -p "$apt_dir/sources.list.d" "$apt_dir/apt.conf.d" "$state_dir"
    _load_apt_snapshot_inventory "$inventory" managed
    if [ "${#managed[@]}" -eq 0 ] && [ ! -f "$inventory" ]; then
        # Migrate machines configured by the pre-inventory implementation. The
        # suffix was private to this provisioner, so these are its backups.
        _discover_legacy_apt_snapshot_inventory managed
    fi

    # Complete conflict validation happens before the first rename. Never guess
    # whether a newly recreated live file or a backup should win.
    for live in "${managed[@]}"; do
        backup="$live.plebian-os-disabled"
        { [ -e "$backup" ] || [ -L "$backup" ]; } \
            || die "apt snapshot inventory names a missing backup: $backup"
        if [ -e "$live" ] || [ -L "$live" ]; then
            die "cannot restore apt sources safely: both $live and $backup exist"
        fi
    done

    txn="$(mktemp -d "$state_dir/.apt-restore.XXXXXX")" \
        || die "could not create apt restore transaction directory"
    if [ -e "$src" ] || [ -L "$src" ]; then cp -a "$src" "$txn/src"; src_old=1; fi
    if [ -e "$cfg" ] || [ -L "$cfg" ]; then cp -a "$cfg" "$txn/cfg"; cfg_old=1; fi
    if [ -e "$marker" ] || [ -L "$marker" ]; then cp -a "$marker" "$txn/marker"; marker_old=1; fi
    if [ -e "$inventory" ] || [ -L "$inventory" ]; then cp -a "$inventory" "$txn/inventory"; inventory_old=1; fi

    # Defer termination only across the mutation window so every signal takes
    # the same rollback path as an ordinary command failure.
    trap 'signal_rc=143' INT TERM HUP
    for live in "${managed[@]}"; do
        if [ "$failed" != 0 ] || [ "$signal_rc" != 0 ]; then failed=1; break; fi
        backup="$live.plebian-os-disabled"
        if mv -T "$backup" "$live"; then
            restored+=("$live")
        else
            failed=1
            break
        fi
    done
    if [ "$failed" = 0 ]; then
        rm -f "$src" "$cfg" "$marker" "$inventory" || failed=1
    fi
    [ "$signal_rc" = 0 ] || failed=1
    if [ "$failed" != 0 ]; then
        for ((i=${#restored[@]}-1; i>=0; i--)); do
            live="${restored[$i]}"
            mv -T "$live" "$live.plebian-os-disabled" 2>/dev/null || rollback_ok=0
        done
        _restore_managed_apt_file "$src" "$txn/src" "$src_old" || rollback_ok=0
        _restore_managed_apt_file "$cfg" "$txn/cfg" "$cfg_old" || rollback_ok=0
        _restore_managed_apt_file "$marker" "$txn/marker" "$marker_old" || rollback_ok=0
        _restore_managed_apt_file "$inventory" "$txn/inventory" "$inventory_old" || rollback_ok=0
        if [ "$rollback_ok" = 1 ]; then
            rm -rf "$txn"
            restore_provision_signal_traps
            [ "$signal_rc" = 0 ] || exit "$signal_rc"
            die "apt source restoration failed; the previous snapshot configuration was restored"
        fi
        restore_provision_signal_traps
        die "apt source restoration and rollback were incomplete; recovery files remain at $txn"
    fi
    rm -rf "$txn"
    restore_provision_signal_traps
    [ "$signal_rc" = 0 ] || exit "$signal_rc"

    _active_apt_source_paths "$src" active
    if [ "${#active[@]}" -eq 0 ]; then
        codename="$(. /etc/os-release 2>/dev/null; printf '%s' "${VERSION_CODENAME:-trixie}")"
        live_tmp="$(mktemp "$apt_dir/sources.list.d/.plebian-os-live.XXXXXX")"
        cat > "$live_tmp" <<EOF
# Managed by plebian-os-provision after leaving snapshot mode with no saved source.
Types: deb
URIs: https://deb.debian.org/debian
Suites: $codename ${codename}-updates
Components: main contrib non-free non-free-firmware
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg

Types: deb
URIs: https://security.debian.org/debian-security
Suites: ${codename}-security
Components: main contrib non-free non-free-firmware
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
EOF
        chmod 0644 "$live_tmp"
        mv -fT "$live_tmp" "$apt_dir/sources.list.d/debian.sources"
    fi
}

# Pin apt to a snapshot.debian.org timestamp so the first-boot package closure is
# reproducible. Turning the knob back off actively restores the stock/live
# sources instead of leaving a machine permanently stranded on the snapshot.
configure_apt_snapshot() {
    if [ -z "$PLEBIAN_OS_APT_SNAPSHOT" ]; then
        [ "$PLEBIAN_OS_RELEASE_MODE" = 1 ] \
            && die "release mode requires PLEBIAN_OS_APT_SNAPSHOT; refusing live package drift"
        restore_live_apt_sources
        return 0
    fi
    local ts="$PLEBIAN_OS_APT_SNAPSHOT"
    local apt_dir="$APT_ETC_ROOT/apt" state_dir="$APT_ETC_ROOT/plebian-os"
    local src="$APT_ETC_ROOT/apt/sources.list.d/plebian-os-snapshot.sources"
    local cfg="$APT_ETC_ROOT/apt/apt.conf.d/99plebian-os-snapshot"
    local marker="$state_dir/apt-snapshot" inventory="$state_dir/apt-snapshot-sources"
    [[ "$ts" =~ ^[0-9]{8}(T[0-9]{6}Z)?$ ]] \
        || die "invalid PLEBIAN_OS_APT_SNAPSHOT=$ts (expected YYYYMMDD or YYYYMMDDTHHMMSSZ)"
    log "pinning apt to snapshot.debian.org/$ts (reproducible package closure)"
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + disable stock apt sources (sources.list, sources.list.d/debian.sources)"
        echo "    + write $src (deb822 snapshot sources for $ts) + $cfg (Check-Valid-Until false)"
        echo "    + apt-get update"
        return 0
    fi
    case "$APT_ETC_ROOT" in /*) ;; *) die "PLEBIAN_OS_APT_ETC_ROOT must be absolute" ;; esac
    mkdir -p "$apt_dir/sources.list.d" "$apt_dir/apt.conf.d" "$state_dir"
    # Inventory every source this provisioner disables. Existing inventories are
    # extended when an operator adds a source while snapshot mode is active.
    local d backup txn src_tmp cfg_tmp marker_tmp inventory_tmp failed=0 rollback_ok=1 signal_rc=0
    local src_old=0 cfg_old=0 marker_old=0 inventory_old=0
    local -a managed=() active=() moved=() combined=()
    _load_apt_snapshot_inventory "$inventory" managed
    if [ "${#managed[@]}" -eq 0 ] && [ ! -f "$inventory" ]; then
        _discover_legacy_apt_snapshot_inventory managed
    fi
    for d in "${managed[@]}"; do
        backup="$d.plebian-os-disabled"
        { [ -e "$backup" ] || [ -L "$backup" ]; } \
            || die "apt snapshot inventory names a missing backup: $backup"
        if [ -e "$d" ] || [ -L "$d" ]; then
            die "cannot snapshot apt safely: both $d and its Plebian-OS backup exist"
        fi
        combined+=("$d")
    done
    _active_apt_source_paths "$src" active
    for d in "${active[@]}"; do
        backup="$d.plebian-os-disabled"
        if [ -e "$backup" ] || [ -L "$backup" ]; then
            die "cannot snapshot apt safely: both $d and its Plebian-OS backup exist"
        fi
        combined+=("$d")
    done

    txn="$(mktemp -d "$state_dir/.apt-enable.XXXXXX")" \
        || die "could not create apt snapshot transaction directory"
    src_tmp="$(mktemp "$apt_dir/sources.list.d/.plebian-os-snapshot.XXXXXX")"
    cat > "$src_tmp" <<EOF
# Managed by plebian-os-provision. Reproducible apt via snapshot.debian.org.
Types: deb
URIs: https://snapshot.debian.org/archive/debian/$ts
Suites: trixie trixie-updates
Components: main contrib non-free non-free-firmware
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg

Types: deb
URIs: https://snapshot.debian.org/archive/debian-security/$ts
Suites: trixie-security
Components: main contrib non-free non-free-firmware
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
EOF
    # snapshot archives carry an old Valid-Until, which apt would otherwise reject.
    cfg_tmp="$(mktemp "$apt_dir/apt.conf.d/.plebian-os-snapshot.XXXXXX")"
    marker_tmp="$(mktemp "$state_dir/.apt-snapshot.XXXXXX")"
    inventory_tmp="$(mktemp "$state_dir/.apt-snapshot-sources.XXXXXX")"
    printf '%s\n' 'Acquire::Check-Valid-Until "false";' > "$cfg_tmp"
    printf '%s\n' "$ts" > "$marker_tmp"
    : > "$inventory_tmp"
    if [ "${#combined[@]}" -gt 0 ]; then
        printf '%s\n' "${combined[@]}" > "$inventory_tmp"
    fi
    chmod 0644 "$src_tmp" "$cfg_tmp" "$marker_tmp"
    chmod 0600 "$inventory_tmp"
    if [ -e "$src" ] || [ -L "$src" ]; then cp -a "$src" "$txn/src"; src_old=1; fi
    if [ -e "$cfg" ] || [ -L "$cfg" ]; then cp -a "$cfg" "$txn/cfg"; cfg_old=1; fi
    if [ -e "$marker" ] || [ -L "$marker" ]; then cp -a "$marker" "$txn/marker"; marker_old=1; fi
    if [ -e "$inventory" ] || [ -L "$inventory" ]; then cp -a "$inventory" "$txn/inventory"; inventory_old=1; fi

    # Once source renames begin, defer signals into the explicit rollback path.
    trap 'signal_rc=143' INT TERM HUP
    for d in "${active[@]}"; do
        if [ "$signal_rc" != 0 ]; then failed=1; break; fi
        if mv -T "$d" "$d.plebian-os-disabled"; then
            moved+=("$d")
        else
            failed=1
            break
        fi
    done
    if [ "$failed" = 0 ] && [ "$signal_rc" = 0 ]; then mv -fT "$src_tmp" "$src" || failed=1; fi
    if [ "$failed" = 0 ] && [ "$signal_rc" = 0 ]; then mv -fT "$cfg_tmp" "$cfg" || failed=1; fi
    if [ "$failed" = 0 ] && [ "$signal_rc" = 0 ]; then mv -fT "$marker_tmp" "$marker" || failed=1; fi
    if [ "$failed" = 0 ] && [ "$signal_rc" = 0 ]; then mv -fT "$inventory_tmp" "$inventory" || failed=1; fi
    if [ "$failed" = 0 ] && [ "$signal_rc" = 0 ] && ! apt-get update -y; then failed=1; fi
    [ "$signal_rc" = 0 ] || failed=1
    if [ "$failed" != 0 ]; then
        _restore_managed_apt_file "$src" "$txn/src" "$src_old" || rollback_ok=0
        _restore_managed_apt_file "$cfg" "$txn/cfg" "$cfg_old" || rollback_ok=0
        _restore_managed_apt_file "$marker" "$txn/marker" "$marker_old" || rollback_ok=0
        _restore_managed_apt_file "$inventory" "$txn/inventory" "$inventory_old" || rollback_ok=0
        for ((i=${#moved[@]}-1; i>=0; i--)); do
            d="${moved[$i]}"
            mv -T "$d.plebian-os-disabled" "$d" 2>/dev/null || rollback_ok=0
        done
        rm -f "$src_tmp" "$cfg_tmp" "$marker_tmp" "$inventory_tmp"
        if [ "$rollback_ok" = 1 ]; then
            rm -rf "$txn"
            restore_provision_signal_traps
            [ "$signal_rc" = 0 ] || exit "$signal_rc"
            die "apt-get update against snapshot $ts failed; restored the previous apt configuration; refusing an unpinned/stale package closure"
        fi
        restore_provision_signal_traps
        die "apt snapshot activation and rollback were incomplete; recovery files remain at $txn"
    fi
    rm -rf "$txn"
    restore_provision_signal_traps
    [ "$signal_rc" = 0 ] || exit "$signal_rc"
}

# Record the exact final installed package set for provenance. This is called
# only after pleb, Go, Kilix, and all system configuration steps have completed.
write_package_manifest() {
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + record installed packages -> /var/lib/plebian-os/packages.list"
        return 0
    fi
    command -v dpkg-query >/dev/null 2>&1 \
        || die "dpkg-query is unavailable; cannot record final package provenance"
    mkdir -p /var/lib/plebian-os
    local tmp
    tmp="$(mktemp /var/lib/plebian-os/.packages.list.XXXXXX)"
    dpkg-query -W -f='${Package}=${Version}\n' 2>/dev/null | sort > "$tmp" \
        || { rm -f "$tmp"; die "could not record final installed package set"; }
    chmod 0644 "$tmp"
    mv -fT "$tmp" /var/lib/plebian-os/packages.list
}

provenance_kv() {
    printf '%s=%q\n' "$1" "$2"
}

validate_component_versions() {
    local pleb_version="$1" kilix_version="$2" kilix95_version="$3"
    [ "$pleb_version" = "pleb $PLEBIAN_OS_VERSION" ] \
        || die "pleb reports '$pleb_version', expected exactly 'pleb $PLEBIAN_OS_VERSION'"
    [ "$kilix_version" = "$PLEBIAN_OS_VERSION" ] \
        || die "kilix reports '$kilix_version', expected exactly '$PLEBIAN_OS_VERSION'"
    [ "$kilix95_version" = "kilix-95 $PLEBIAN_OS_VERSION" ] \
        || die "kilix 95 reports '$kilix95_version', expected exactly 'kilix-95 $PLEBIAN_OS_VERSION'"
}

write_source_tool_manifest() {
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + record resolved source commits, apt indexes, and tool versions -> /var/lib/plebian-os/{versions.env,apt-sources.list}"
        return 0
    fi
    local state=/var/lib/plebian-os versions_tmp sources_tmp
    local plebian_os_commit pleb_commit kilix_commit kilix_source_commit kilix95_commit
    local pleb_version kilix_version kilix95_version go_version engine engine_version uv_version
    mkdir -p "$state"
    versions_tmp="$(mktemp "$state/.versions.env.XXXXXX")"
    sources_tmp="$(mktemp "$state/.apt-sources.list.XXXXXX")"

    plebian_os_commit="$(as_user git -C "$PLEBIAN_OS_DIR" rev-parse HEAD 2>/dev/null || true)"
    pleb_commit="$(as_user git -C "$PLEB_DIR" rev-parse HEAD 2>/dev/null || true)"
    kilix_commit="$(as_user git -C "$KILIX_DIR" rev-parse HEAD 2>/dev/null || true)"
    kilix_source_commit="$(as_user git -C "$KILIX_DIR/src" rev-parse HEAD 2>/dev/null || true)"
    kilix95_commit="$(as_user git -C "$KILIX95_DIR" rev-parse HEAD 2>/dev/null || true)"
    pleb_version="$(as_user env "${install_env[@]}" "$PLEB_DIR/bin/pleb" --version 2>/dev/null || true)"
    kilix_version="$(as_user env "${install_env[@]}" "$KILIX_DIR/kilix" --kilix-version 2>/dev/null || true)"
    if [ -f "$KILIX95_DIR/main.py" ]; then
        kilix95_version="$(as_user env "${install_env[@]}" python3 "$KILIX95_DIR/main.py" --version 2>/dev/null || true)"
    else
        kilix95_version=""
    fi
    go_version="$(as_user bash -lc 'go version' 2>/dev/null || true)"
    uv_version="$(/usr/local/bin/uv --version 2>/dev/null || true)"
    engine="$(as_user env "${install_env[@]}" "$KILIX_DIR/kilix" --which 2>/dev/null | head -1 || true)"
    if [ -n "$engine" ] && [ -x "$engine" ]; then
        engine_version="$(as_user env "${install_env[@]}" "$engine" --version 2>/dev/null | head -1 || true)"
    else
        engine_version=""
    fi

    {
        echo "# Final resolved Plebian-OS source/tool provenance."
        provenance_kv PLEBIAN_OS_VERSION "$PLEBIAN_OS_VERSION"
        provenance_kv PLEBIAN_OS_RELEASE "$PLEBIAN_OS_RELEASE"
        provenance_kv PLEBIAN_OS_RELEASE_MODE "$PLEBIAN_OS_RELEASE_MODE"
        provenance_kv PLEBIAN_OS_APT_SNAPSHOT "$PLEBIAN_OS_APT_SNAPSHOT"
        provenance_kv GPU_TERMINAL_SOURCE_HOME "$GPU_TERMINAL_SOURCE_HOME"
        provenance_kv GPU_TERMINAL_HOME "$GPU_TERMINAL_HOME"
        provenance_kv GPU_TERMINAL_SETTINGS_FILE "$GPU_TERMINAL_SETTINGS_FILE"
        provenance_kv PLEBIAN_OS_REPO "$PLEBIAN_OS_REPO"
        provenance_kv PLEBIAN_OS_BRANCH "$PLEBIAN_OS_BRANCH"
        provenance_kv PLEBIAN_OS_REF "$PLEBIAN_OS_REF"
        provenance_kv PLEBIAN_OS_COMMIT "$plebian_os_commit"
        provenance_kv PLEBIAN_OS_DIR "$PLEBIAN_OS_DIR"
        provenance_kv PLEBIAN_OS_STORAGE_HOME "$PLEBIAN_OS_STORAGE_HOME"
        provenance_kv PLEBIAN_OS_SESSION_HOME "$PLEBIAN_OS_SESSION_HOME"
        provenance_kv PLEB_DIR "$PLEB_DIR"
        provenance_kv PLEB_STORAGE_HOME "$PLEB_STORAGE_HOME"
        provenance_kv PLEB_CONFIG_HOME "$PLEB_CONFIG_HOME"
        provenance_kv PLEB_STATE_HOME "$PLEB_STATE_HOME"
        provenance_kv PLEB_CACHE_HOME "$PLEB_CACHE_HOME"
        provenance_kv PLEB_SESSION_HOME "$PLEB_SESSION_HOME"
        provenance_kv PLEB_DATA_HOME "$PLEB_DATA_HOME"
        provenance_kv PLEB_REF "$PLEB_REF"
        provenance_kv PLEB_COMMIT "$pleb_commit"
        provenance_kv PLEB_VERSION "$pleb_version"
        provenance_kv KILIX_REF "$KILIX_REF"
        provenance_kv KILIX_DIR "$KILIX_DIR"
        provenance_kv KILIX_STORAGE_HOME "$KILIX_STORAGE_HOME"
        provenance_kv KILIX_CONFIG_HOME "$KILIX_CONFIG_HOME"
        provenance_kv KILIX_STATE_DIRECTORY "$KILIX_STATE_DIRECTORY"
        provenance_kv KILIX_CACHE_HOME "$KILIX_CACHE_HOME"
        provenance_kv KILIX_SESSION_HOME "$KILIX_SESSION_HOME"
        provenance_kv KILIX_BUILD_DIRECTORY "$KILIX_BUILD_DIRECTORY"
        provenance_kv KILIX_DATA_HOME "$KILIX_DATA_HOME"
        provenance_kv KILIX_DESKTOP_DIR "$KILIX_DESKTOP_DIR"
        provenance_kv KILIX_PREBUILT_HOME "$KILIX_PREBUILT_HOME"
        provenance_kv KILIX_COMMIT "$kilix_commit"
        provenance_kv KILIX_SOURCE_COMMIT "$kilix_source_commit"
        provenance_kv KILIX_VERSION "$kilix_version"
        provenance_kv KILIX_ENGINE "$engine"
        provenance_kv KILIX_ENGINE_VERSION "$engine_version"
        provenance_kv KILIX_VOICE_REF "$KILIX_VOICE_REF"
        provenance_kv KILIX_VOICE_LIB_VERSION "$KILIX_VOICE_LIB_VERSION"
        provenance_kv KILIX_VOICE_LIB_URL "$KILIX_VOICE_LIB_URL"
        provenance_kv KILIX_VOICE_LIB_SHA256 "$KILIX_VOICE_LIB_SHA256"
        provenance_kv KILIX_VOICE_MODEL_URL "$KILIX_VOICE_MODEL_URL"
        provenance_kv KILIX_VOICE_MODEL_SHA256 "$KILIX_VOICE_MODEL_SHA256"
        provenance_kv PLEBIAN_OS_INSTALL_VOICE_MODEL "$INSTALL_VOICE_MODEL"
        provenance_kv KILIX_CAP_DIR "$KILIX_CAP_DIR"
        provenance_kv KILIX_CAP_REPO "$KILIX_CAP_REPO"
        provenance_kv KILIX_CAP_REF "$KILIX_CAP_REF"
        provenance_kv KILIX_TUI_UTILS_DIR "$KILIX_TUI_UTILS_DIR"
        provenance_kv KILIX_TUI_UTILS_REPO "$KILIX_TUI_UTILS_REPO"
        provenance_kv KILIX_TUI_UTILS_REF "$KILIX_TUI_UTILS_REF"
        provenance_kv KILIX_LAND_DESKTOP_DIR "$KILIX_LAND_DESKTOP_DIR"
        provenance_kv KILIX_LAND_DESKTOP_REPO "$KILIX_LAND_DESKTOP_REPO"
        provenance_kv KILIX_LAND_DESKTOP_REF "$KILIX_LAND_DESKTOP_REF"
        provenance_kv KILIX95_REF "$KILIX95_REF"
        provenance_kv KILIX95_DIR "$KILIX95_DIR"
        provenance_kv KILIX95_STORAGE_HOME "$KILIX95_STORAGE_HOME"
        provenance_kv KILIX95_CONFIG_HOME "$KILIX95_CONFIG_HOME"
        provenance_kv KILIX95_STATE_HOME "$KILIX95_STATE_HOME"
        provenance_kv KILIX95_CACHE_HOME "$KILIX95_CACHE_HOME"
        provenance_kv KILIX95_SESSION_HOME "$KILIX95_SESSION_HOME"
        provenance_kv KILIX95_DATA_HOME "$KILIX95_DATA_HOME"
        provenance_kv KILIX95_COMMIT "$kilix95_commit"
        provenance_kv KILIX95_VERSION "$kilix95_version"
        provenance_kv PLEBIAN_OS_KILIX_GO_VERSION "$KILIX_GO_VERSION"
        provenance_kv PLEBIAN_OS_KILIX_GO_SHA256_AMD64 "$KILIX_GO_SHA256_AMD64"
        provenance_kv PLEBIAN_OS_KILIX_GO_SHA256_ARM64 "$KILIX_GO_SHA256_ARM64"
        provenance_kv GO_VERSION "$go_version"
        provenance_kv PLEBIAN_OS_INSTALL_UV "$INSTALL_UV"
        provenance_kv PLEBIAN_OS_UV_VERSION "$UV_VERSION_PIN"
        provenance_kv PLEBIAN_OS_UV_INSTALLER_SHA256 "$UV_INSTALLER_SHA256"
        provenance_kv UV_VERSION "$uv_version"
        provenance_kv GIT_VERSION "$(git --version 2>/dev/null || true)"
        provenance_kv PYTHON3_VERSION "$(python3 --version 2>&1 || true)"
        provenance_kv KERNEL_VERSION "$(uname -srmo 2>/dev/null || true)"
    } > "$versions_tmp"

    apt-get indextargets \
        --format '$(SITE) $(RELEASE) $(COMPONENT) $(ARCHITECTURE)' 2>/dev/null \
        | sed '/^[[:space:]]*$/d' | sort -u > "$sources_tmp" \
        || { rm -f "$versions_tmp" "$sources_tmp"; die "could not record final apt source indexes"; }
    if [ "$PLEBIAN_OS_RELEASE_MODE" = 1 ]; then
        [ -s "$sources_tmp" ] || die "release apt index provenance is empty"
        if grep -v 'snapshot\.debian\.org' "$sources_tmp" | grep -q .; then
            rm -f "$versions_tmp" "$sources_tmp"
            die "release apt provenance contains a non-snapshot index"
        fi
        [ "$plebian_os_commit" = "${PLEBIAN_OS_REF,,}" ] \
            || die "resolved plebian-os commit $plebian_os_commit does not match PLEBIAN_OS_REF=$PLEBIAN_OS_REF"
        [ "$pleb_commit" = "${PLEB_REF,,}" ] \
            || die "resolved pleb commit $pleb_commit does not match PLEB_REF=$PLEB_REF"
        [ "$kilix_commit" = "${KILIX_REF,,}" ] \
            || die "resolved kilix commit $kilix_commit does not match KILIX_REF=$KILIX_REF"
        [ "$kilix95_commit" = "${KILIX95_REF,,}" ] \
            || die "resolved kilix 95 commit $kilix95_commit does not match KILIX95_REF=$KILIX95_REF"
        validate_component_versions "$pleb_version" "$kilix_version" "$kilix95_version"
        if [ "$INSTALL_UV" = 1 ]; then
            [ "$uv_version" = "uv $UV_VERSION_PIN" ] \
                || die "release uv provenance mismatch: expected 'uv $UV_VERSION_PIN', got '${uv_version:-<missing>}'"
        fi
    fi
    chmod 0644 "$versions_tmp" "$sources_tmp"
    mv -fT "$versions_tmp" "$state/versions.env"
    mv -fT "$sources_tmp" "$state/apt-sources.list"
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
        echo "    + (as $TARGET_USER) atomically replace $dmrc ([Desktop] Session=pleb; do not follow symlinks)"
        echo "    + create $asvc with Session=pleb (if absent)"
        return 0
    fi
    # $USER_HOME is controlled by the target user. Never redirect or chown this
    # path as root: a pre-created ~/.dmrc symlink could otherwise truncate and
    # hand ownership of an arbitrary root file to the user. Create the file as
    # the user and atomically replace the directory entry with `mv -T`, which
    # replaces a symlink itself instead of following it (including dir symlinks).
    as_user bash -c '
set -euo pipefail
dmrc="$1"
tmp="$(mktemp "${dmrc}.tmp.XXXXXX")"
trap '\''rm -f "$tmp"'\'' EXIT
printf '\''%s\n'\'' '\''[Desktop]'\'' '\''Session=pleb'\'' > "$tmp"
chmod 0600 "$tmp"
mv -fT -- "$tmp" "$dmrc"
trap - EXIT
' plebian-os-dmrc-writer "$dmrc" \
        || die "could not safely write $dmrc as $TARGET_USER"
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
        echo "    + if $TARGET_USER still uses the shipped password: write $rule (NOPASSWD: $dst)"
        echo "    + otherwise: remove $rule (the one-time transition is no longer needed)"
        return 0
    fi
    if [ -n "$src" ] && [ "$src" != "$dst" ]; then
        install -m 0755 "$src" "$dst" || die "could not install $dst"
    fi
    if [ ! -x "$dst" ]; then
        rm -f "$rule"
        die "plebian-os-passwd helper missing; refusing to leave the shipped password without its transition helper"
    fi
    # The NOPASSWD helper is only safe while it is a one-time transition away
    # from the shipped password. A reprovision after the owner changes the
    # password must remove, not recreate, the grant. Fail closed if the helper
    # cannot determine the shadow state.
    local password_state
    if SUDO_USER="$TARGET_USER" "$dst" check; then
        password_state=default
    else
        case "$?" in
            1) password_state=changed ;;
            *) password_state=unknown ;;
        esac
    fi
    if [ "$password_state" != default ]; then
        rm -f "$rule"
        if [ "$password_state" = changed ]; then
            log "$TARGET_USER no longer uses the shipped password; scoped password-change grant retired"
        else
            warn "could not verify $TARGET_USER's password state; refusing to install $rule"
        fi
        return 0
    fi
    printf '%s ALL=(root) NOPASSWD: %s\n' "$TARGET_USER" "$dst" > "$rule"
    chmod 0440 "$rule"
    visudo -cf "$rule" >/dev/null 2>&1 \
        || { warn "passwd-helper sudoers invalid — removing $rule"; rm -f "$rule"; }
}

desktop_provider_needs_kilix95() {
    case "$KILIX_DESKTOP_PROVIDER" in
        external|xp|kilix-xp) return 0 ;;
        auto) [ ! -f "$KILIX_DIR/desktop/main.py" ] ;;
        *) return 1 ;;
    esac
}

kilix95_install_required() {
    [ "$KILIX95_AUTO_INSTALL" = 1 ] && desktop_provider_needs_kilix95
}

validate_checkout() {
    local dir="$1" repo="$2" name="$3" remote
    [ -d "$dir" ] && [ ! -L "$dir" ] \
        || die "$name checkout is not a safe directory: $dir"
    if [ -L "$dir/.git" ] \
        || { [ ! -d "$dir/.git" ] && [ ! -f "$dir/.git" ]; }; then
        die "$name path is not a safe git checkout: $dir"
    fi
    remote="$(as_target_readonly git -C "$dir" config --get remote.origin.url 2>/dev/null)" \
        || die "could not validate $name checkout origin at $dir"
    if [ "$remote" != "$repo" ] \
        && [ "${PLEBIAN_OS_TRUST_EXISTING_CHECKOUT:-0}" != 1 ]; then
        die "$name checkout at $dir has origin '$remote', expected '$repo' (set PLEBIAN_OS_TRUST_EXISTING_CHECKOUT=1 to override)"
    fi
}

require_clean_pinned_checkout() {
    local dir="$1" name="$2" dirty
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + verify pinned $name checkout has no tracked/index changes: $dir"
        return 0
    fi
    dirty="$(as_user git -C "$dir" status --porcelain --untracked-files=normal 2>/dev/null)" \
        || die "could not inspect pinned $name checkout at $dir"
    [ -z "$dirty" ] \
        || die "pinned $name checkout at $dir has local changes; refusing to overwrite or execute it"
}

checkout_pinned_ref() {
    local dir="$1" ref="$2" name="$3" resolved actual
    require_clean_pinned_checkout "$dir" "$name"
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + fetch and verify pinned $name ref $ref from origin"
        return 0
    fi
    # Resolve the ref from this fetch's FETCH_HEAD, not a potentially stale or
    # attacker-created local tag. Then verify checkout HEAD is exactly that commit.
    as_user git -C "$dir" fetch --force origin "$ref" \
        || die "$name fetch of pinned ref $ref failed"
    resolved="$(as_user git -C "$dir" rev-parse --verify 'FETCH_HEAD^{commit}' 2>/dev/null)" \
        || die "pinned $name ref $ref did not resolve to a commit"
    as_user git -C "$dir" checkout --detach "$resolved" \
        || die "could not check out pinned $name ref $ref ($resolved)"
    actual="$(as_user git -C "$dir" rev-parse --verify HEAD 2>/dev/null)" \
        || die "could not verify pinned $name checkout HEAD"
    [ "$actual" = "$resolved" ] \
        || die "pinned $name checkout resolved to $resolved but HEAD is $actual"
    require_clean_pinned_checkout "$dir" "$name"
    log "$name pinned ref $ref verified at $actual"
}

ensure_plebian_os_checkout() {
    local clone_args=()
    if [ -d "$PLEBIAN_OS_DIR/.git" ]; then
        log "plebian-os source present at $PLEBIAN_OS_DIR"
        validate_checkout "$PLEBIAN_OS_DIR" "$PLEBIAN_OS_REPO" "plebian-os"
        if [ -n "$PLEBIAN_OS_REF" ]; then
            checkout_pinned_ref "$PLEBIAN_OS_DIR" "$PLEBIAN_OS_REF" "plebian-os"
        fi
        return 0
    fi
    [ ! -e "$PLEBIAN_OS_DIR" ] && [ ! -L "$PLEBIAN_OS_DIR" ] \
        || die "plebian-os source path exists but is not a git checkout: $PLEBIAN_OS_DIR"

    log "cloning plebian-os source -> $PLEBIAN_OS_DIR"
    [ -n "$PLEBIAN_OS_BRANCH" ] && clone_args=(--branch "$PLEBIAN_OS_BRANCH")
    as_user git clone "${clone_args[@]}" "$PLEBIAN_OS_REPO" "$PLEBIAN_OS_DIR" \
        || die "git clone of plebian-os failed ($PLEBIAN_OS_REPO)"
    if [ -n "$PLEBIAN_OS_REF" ]; then
        checkout_pinned_ref "$PLEBIAN_OS_DIR" "$PLEBIAN_OS_REF" "plebian-os"
    fi
}

update_pleb_checkout() {
    validate_checkout "$PLEB_DIR" "$PLEB_REPO" "pleb"
    if [ -n "$PLEB_REF" ]; then
        checkout_pinned_ref "$PLEB_DIR" "$PLEB_REF" "pleb"
        return
    fi

    if [ -n "$PLEB_BRANCH" ]; then
        as_user git -C "$PLEB_DIR" fetch --prune origin "$PLEB_BRANCH" \
            || die "pleb fetch failed"
        current="$(as_target_readonly git -C "$PLEB_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo HEAD)"
        if [ "$current" != "$PLEB_BRANCH" ]; then
            if as_target_readonly git -C "$PLEB_DIR" show-ref --verify --quiet "refs/heads/$PLEB_BRANCH"; then
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

    # Nothing left to position the checkout by. A detached HEAD is what every
    # pinned install has, and `git pull --ff-only` can only report that in git's
    # own words; say which pin is missing instead.
    as_target_readonly git -C "$PLEB_DIR" symbolic-ref --quiet HEAD >/dev/null \
        || die "pleb checkout at $PLEB_DIR is not on a branch and no PLEB_REF/PLEB_BRANCH is set (expected a pin in $PLEBIAN_OS_SESSION_ENV)"
    as_user git -C "$PLEB_DIR" pull --ff-only || die "pleb pull failed"
}

kilix_go_ok_script() {
    cat <<'EOF'
command -v go >/dev/null 2>&1 || exit 1
min="${PLEBIAN_OS_KILIX_GO_MIN_VERSION:-1.26}"
exact="${PLEBIAN_OS_KILIX_GO_VERSION:-}"
ver="$(go version 2>/dev/null | awk '{print $3}' | sed 's/^go//')"
[ -n "$ver" ] || exit 1
if [ -n "$exact" ]; then
    exact="${exact#go}"
    [ "$ver" = "$exact" ] || exit 1
fi
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

pinned_go_provenance_ok() {
    local arch="$1" sha="${2,,}" root=/usr/local/go stamp version path owner mode
    local -a provenance=()
    stamp="$root/.pleb-source"
    [ -d "$root" ] && [ ! -L "$root" ] \
        && [ -f "$stamp" ] && [ ! -L "$stamp" ] \
        && [ -x "$root/bin/go" ] && [ ! -L "$root/bin/go" ] \
        || return 1
    for path in "$root" "$stamp" "$root/bin/go"; do
        owner="$(stat -c '%u' "$path" 2>/dev/null)" || return 1
        mode="$(stat -c '%a' "$path" 2>/dev/null)" || return 1
        [ "$owner" = 0 ] || return 1
        (( (8#$mode & 8#22) == 0 )) || return 1
    done
    mapfile -t provenance < "$stamp" || return 1
    [ "${#provenance[@]}" -eq 3 ] \
        && [ "${provenance[0]}" = "go${KILIX_GO_VERSION#go}" ] \
        && [ "${provenance[1]}" = "$arch" ] \
        && [ "${provenance[2],,}" = "$sha" ] \
        || return 1
    version="$($root/bin/go version 2>/dev/null)" || return 1
    [ "$version" = "go version go${KILIX_GO_VERSION#go} linux/$arch" ] || return 1
    path="$(as_user bash -lc 'command -v go' 2>/dev/null)" || return 1
    [ "$(readlink -f "$path" 2>/dev/null)" = "$root/bin/go" ] || return 1
}

ensure_go_for_kilix_build() {
    local arch sha="" version_ok=0
    case "$(uname -m)" in
        x86_64|amd64) arch=amd64; sha="$KILIX_GO_SHA256_AMD64" ;;
        aarch64|arm64) arch=arm64; sha="$KILIX_GO_SHA256_ARM64" ;;
        *) die "unsupported architecture for Go toolchain: $(uname -m)" ;;
    esac
    if [ -n "$KILIX_GO_VERSION" ]; then
        [ -n "$sha" ] \
            || die "PLEBIAN_OS_KILIX_GO_VERSION=$KILIX_GO_VERSION requires PLEBIAN_OS_KILIX_GO_SHA256_${arch^^}"
        [[ "$sha" =~ ^[0-9a-fA-F]{64}$ ]] \
            || die "invalid PLEBIAN_OS_KILIX_GO_SHA256_${arch^^} (expected 64 hex characters)"
    elif [ -n "$KILIX_GO_SHA256_AMD64$KILIX_GO_SHA256_ARM64" ]; then
        die "a pinned Go checksum requires PLEBIAN_OS_KILIX_GO_VERSION"
    fi

    log "checking Go toolchain for kilix fork build (>= $KILIX_GO_MIN_VERSION${KILIX_GO_VERSION:+, exactly $KILIX_GO_VERSION with verified archive provenance})"
    if as_user env \
        "PLEBIAN_OS_KILIX_GO_MIN_VERSION=$KILIX_GO_MIN_VERSION" \
        "PLEBIAN_OS_KILIX_GO_VERSION=$KILIX_GO_VERSION" \
        bash -lc "$(kilix_go_ok_script)"; then
        version_ok=1
    fi
    if [ "$version_ok" = 1 ] && [ -z "$KILIX_GO_VERSION" ]; then
        log "Go is ready: $(as_user bash -lc 'go version' 2>/dev/null || true)"
        return 0
    fi
    if [ "$version_ok" = 1 ] && pinned_go_provenance_ok "$arch" "$sha"; then
        log "Go is ready with matching root-owned archive provenance: $(as_user bash -lc 'go version' 2>/dev/null || true)"
        return 0
    fi
    if [ "$version_ok" = 1 ]; then
        warn "Go reports the requested version but its root-owned .pleb-source archive stamp is absent or mismatched; reinstalling"
    fi

    [ -x "$PLEB_DIR/scripts/install-go.sh" ] \
        || die "Go >= $KILIX_GO_MIN_VERSION is required, and $PLEB_DIR/scripts/install-go.sh is missing"
    log "installing/upgrading Go via pleb helper${KILIX_GO_VERSION:+ (pinned $KILIX_GO_VERSION/$arch)}"
    as_user env \
        "GO_VERSION=$KILIX_GO_VERSION" \
        "GO_SHA256=$sha" \
        "$PLEB_DIR/scripts/install-go.sh" all "$KILIX_GO_VERSION" \
        || die "Go toolchain install failed"
    as_user env \
        "PLEBIAN_OS_KILIX_GO_MIN_VERSION=$KILIX_GO_MIN_VERSION" \
        "PLEBIAN_OS_KILIX_GO_VERSION=$KILIX_GO_VERSION" \
        bash -lc "$(kilix_go_ok_script)" \
        || die "Go toolchain does not satisfy the requested min/exact version after install"
    if [ -n "$KILIX_GO_VERSION" ]; then
        pinned_go_provenance_ok "$arch" "$sha" \
            || die "Go toolchain has missing or mismatched root-owned archive provenance after install"
    fi
    log "Go is ready: $(as_user bash -lc 'go version' 2>/dev/null || true)"
}

probe_kilix_launcher() {
    if command -v timeout >/dev/null 2>&1; then
        as_user env "${install_env[@]}" timeout 15 "$1" --version >/dev/null 2>&1
    else
        as_user env "${install_env[@]}" "$1" --version >/dev/null 2>&1
    fi
}

run_voice_tool() {
    if command -v timeout >/dev/null 2>&1; then
        as_user env "${install_env[@]}" timeout 15 "$@"
    else
        as_user env "${install_env[@]}" "$@"
    fi
}

run_voice_functional_smoke() {
    local runtime_lib code
    runtime_lib="$KILIX_DATA_HOME/voice/runtime/current/lib/kilix-voice"
    code="$(cat <<'PY'
import os

from voicelib.stt import VoskStt
from voicelib.tts import EspeakTts

pcm, rate = EspeakTts(voice="en-us", rate=135).synth(
    "kilix voice is working"
)
if not pcm or rate <= 0:
    raise SystemExit("espeak produced no PCM")
data_home = os.environ["KILIX_DATA_HOME"]
library_path = os.path.join(data_home, "voice/lib/current/libvosk.so")
model_path = os.path.join(data_home, "voice/models/small-en-us")
recognizer = VoskStt(
    rate=rate, lib_path=library_path, model_path=model_path
)
try:
    if recognizer.lib_path != os.path.abspath(library_path):
        raise SystemExit("Vosk did not open the pinned library path")
    if recognizer.model_path != os.path.abspath(model_path):
        raise SystemExit("Vosk did not open the pinned model path")
    recognizer.start_utterance()
    for offset in range(0, len(pcm), 4096):
        recognizer.feed(pcm[offset:offset + 4096])
    recognized = recognizer.end_utterance().strip()
    if not recognized:
        raise SystemExit("Vosk recognized no text from synthesized speech")
finally:
    recognizer.close()
PY
)"
    if command -v timeout >/dev/null 2>&1; then
        as_user env "${install_env[@]}" "PYTHONPATH=$runtime_lib" \
            timeout 180 python3 -c "$code"
    else
        as_user env "${install_env[@]}" "PYTHONPATH=$runtime_lib" \
            python3 -c "$code"
    fi
}

verify_kilix_voice_install() {
    local tool path stamp stt_report="" library_root model_root
    local library_notice library_license model_notice model_license
    local library_target="" model_target=""
    local voice_source="" voice_head="" voice_version="" version_report=""
    local -a problems=()
    stamp="$KILIX_STATE_DIRECTORY/kilix-voice-install.refs"
    library_root="$KILIX_DATA_HOME/voice/lib/current"
    model_root="$KILIX_DATA_HOME/voice/models/small-en-us"
    library_notice="$library_root/README.kilix-provenance"
    library_license="$library_root/LICENSE.Apache-2.0"
    model_notice="$model_root/README.kilix-provenance"
    model_license="$model_root/LICENSE.Apache-2.0"

    if [ "$INSTALL_VOICE_MODEL" = 1 ] && [ -n "$KILIX_VOICE_REF" ]; then
        voice_source="$GPU_TERMINAL_SOURCE_HOME/.kilix-voice-sources/kilix-voice-$KILIX_VOICE_REF"
        if [ ! -d "$voice_source/.git" ] || [ -L "$voice_source" ]; then
            problems+=("missing or unsafe pinned Kilix Voice checkout $voice_source")
        else
            voice_head="$(as_user git -C "$voice_source" rev-parse --verify HEAD 2>/dev/null)" \
                || problems+=("could not resolve the installed Kilix Voice checkout")
            [ "${voice_head,,}" = "${KILIX_VOICE_REF,,}" ] \
                || problems+=("installed Kilix Voice checkout does not match the requested ref")
            voice_version="$(
                as_user git -C "$voice_source" show "${KILIX_VOICE_REF}:VERSION" 2>/dev/null
            )" || problems+=("pinned Kilix Voice commit has no VERSION")
            [[ "$voice_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
                || problems+=("pinned Kilix Voice VERSION is not semantic")
            [ "$(as_user cat "$voice_source/VERSION" 2>/dev/null)" = "$voice_version" ] \
                || problems+=("Kilix Voice working VERSION differs from its pinned commit")
        fi
    fi

    for tool in kilix-tts kilix-stt kilix-voiced; do
        path="$USER_HOME/.local/bin/$tool"
        if [ ! -x "$path" ]; then
            problems+=("missing executable $path")
        elif ! version_report="$(run_voice_tool "$path" --version 2>/dev/null)"; then
            problems+=("$tool --version could not execute")
        elif ! [[ "$version_report" =~ ^${tool}\ [0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            problems+=("$tool --version returned an invalid version")
        elif [ -n "$voice_version" ] \
                && [ "$version_report" != "$tool $voice_version" ]; then
            problems+=("$tool --version does not match Kilix Voice $voice_version")
        fi
    done
    if [ -x "$USER_HOME/.local/bin/kilix-tts" ]; then
        run_voice_tool "$USER_HOME/.local/bin/kilix-tts" --print >/dev/null 2>&1 \
            || problems+=("kilix-tts --print could not execute")
    fi
    if [ -x "$USER_HOME/.local/bin/kilix-stt" ]; then
        stt_report="$(run_voice_tool "$USER_HOME/.local/bin/kilix-stt" --print 2>/dev/null)" \
            || problems+=("kilix-stt --print could not execute")
    fi

    if [ ! -f "$stamp" ] || [ -L "$stamp" ]; then
        problems+=("missing or unsafe install stamp $stamp")
    elif [ "$INSTALL_VOICE_MODEL" = 1 ]; then
        [ "$(stat -c '%u:%a:%h' -- "$stamp" 2>/dev/null)" \
            = "$TARGET_UID:600:1" ] \
            || problems+=("Kilix Voice install stamp has unsafe ownership, mode, or links")
        if [ -n "$KILIX_VOICE_REF" ] \
                && [ -n "$KILIX_VOICE_LIB_VERSION" ] \
                && [ -n "$KILIX_VOICE_LIB_SHA256" ] \
                && [ -n "$KILIX_VOICE_MODEL_SHA256" ]; then
            printf '%s\n' \
                "kilix-voice=$KILIX_VOICE_REF" \
                "libvosk=$KILIX_VOICE_LIB_VERSION+$KILIX_VOICE_LIB_SHA256" \
                "model-small-en-us=$KILIX_VOICE_MODEL_SHA256" \
                | cmp -s - "$stamp" \
                || problems+=("Kilix Voice install stamp does not exactly match the requested closure")
        else
            grep -Eq '^kilix-voice=[0-9a-fA-F]{40}$' "$stamp" \
                || problems+=("Kilix Voice install stamp has no immutable source ref")
            grep -Eq '^libvosk=[A-Za-z0-9._-]+\+[0-9a-fA-F]{64}$' "$stamp" \
                || problems+=("Kilix Voice install stamp has no verified library pin")
            grep -Eq '^model-small-en-us=[0-9a-fA-F]{64}$' "$stamp" \
                || problems+=("Kilix Voice install stamp has no verified model pin")
        fi
    else
        grep -Fqx -- 'libvosk=skipped' "$stamp" \
            || problems+=("read-aloud install did not record the skipped Vosk library")
        grep -Fqx -- 'model-small-en-us=skipped' "$stamp" \
            || problems+=("read-aloud install did not record the skipped Vosk model")
    fi

    if [ "$INSTALL_VOICE_MODEL" = 1 ]; then
        if [ -L "$library_root" ]; then
            library_target="$(readlink -- "$library_root" 2>/dev/null)"
            if [ -n "$KILIX_VOICE_LIB_VERSION" ] \
                    && [ -n "$KILIX_VOICE_LIB_SHA256" ]; then
                [ "$library_target" \
                    = "vosk-$KILIX_VOICE_LIB_VERSION-${KILIX_VOICE_LIB_SHA256,,}" ] \
                    || problems+=("Vosk library generation link does not match the requested version and digest")
            else
                [[ "$library_target" =~ ^vosk-[A-Za-z0-9._-]+-[0-9a-fA-F]{64}$ ]] \
                    || problems+=("Vosk library generation link has no immutable digest")
            fi
            [ -d "$KILIX_DATA_HOME/voice/lib/$library_target" ] \
                && [ ! -L "$KILIX_DATA_HOME/voice/lib/$library_target" ] \
                || problems+=("Vosk library generation target is missing or unsafe")
        else
            problems+=("Vosk library current path is not a generation symlink")
        fi
        if [ -L "$model_root" ]; then
            model_target="$(readlink -- "$model_root" 2>/dev/null)"
            if [ -n "$KILIX_VOICE_MODEL_SHA256" ]; then
                [ "$model_target" \
                    = "vosk-model-small-en-us-0.15-${KILIX_VOICE_MODEL_SHA256,,}" ] \
                    || problems+=("Vosk model generation link does not match small-en-us 0.15 and its digest")
            else
                [[ "$model_target" =~ ^vosk-model-small-en-us-0\.15-[0-9a-fA-F]{64}$ ]] \
                    || problems+=("Vosk model generation link has no immutable digest")
            fi
            [ -d "$KILIX_DATA_HOME/voice/models/$model_target" ] \
                && [ ! -L "$KILIX_DATA_HOME/voice/models/$model_target" ] \
                || problems+=("Vosk model generation target is missing or unsafe")
        else
            problems+=("Vosk model small-en-us path is not a generation symlink")
        fi
        [ -f "$library_root/libvosk.so" ] \
            && [ ! -L "$library_root/libvosk.so" ] \
            || problems+=("verified Vosk library is missing")
        [ -d "$model_root" ] \
            || problems+=("verified Vosk small-en-us model is missing")
        for path in "$library_notice" "$library_license" \
                "$model_notice" "$model_license"; do
            [ -f "$path" ] && [ ! -L "$path" ] \
                || problems+=("missing or unsafe Vosk attribution artifact $path")
        done
        if [ -f /usr/share/common-licenses/Apache-2.0 ]; then
            cmp -s -- /usr/share/common-licenses/Apache-2.0 "$library_license" \
                || problems+=("Vosk library Apache-2.0 license is missing or altered")
            cmp -s -- /usr/share/common-licenses/Apache-2.0 "$model_license" \
                || problems+=("Vosk model Apache-2.0 license is missing or altered")
        else
            problems+=("Debian Apache-2.0 license source is missing")
        fi
        if [ -n "$KILIX_VOICE_REF" ] \
                && [ -n "$KILIX_VOICE_LIB_VERSION" ] \
                && [ -n "$KILIX_VOICE_LIB_URL" ] \
                && [ -n "$KILIX_VOICE_LIB_SHA256" ] \
                && [ -n "$KILIX_VOICE_MODEL_URL" ] \
                && [ -n "$KILIX_VOICE_MODEL_SHA256" ]; then
            printf '%s\n' \
                'Kilix Voice native speech-recognition library' \
                'Upstream: https://github.com/alphacep/vosk-api' \
                "Version: $KILIX_VOICE_LIB_VERSION" \
                "Wheel: $KILIX_VOICE_LIB_URL" \
                "Wheel SHA-256: $KILIX_VOICE_LIB_SHA256" \
                'Extracted member: vosk/libvosk.so' \
                'License: Apache-2.0 (see LICENSE.Apache-2.0)' \
                | cmp -s - "$library_notice" \
                || problems+=("Vosk library provenance does not match the requested closure")
            printf '%s\n' \
                'Vosk small US English acoustic model' \
                'Upstream catalog: https://alphacephei.com/vosk/models' \
                "Archive: $KILIX_VOICE_MODEL_URL" \
                "Archive SHA-256: $KILIX_VOICE_MODEL_SHA256" \
                'Archive directory: vosk-model-small-en-us-0.15' \
                'License: Apache-2.0 (see LICENSE.Apache-2.0)' \
                | cmp -s - "$model_notice" \
                || problems+=("Vosk model provenance does not match the requested closure")
        fi
        grep -Fqx -- 'dictation=ready' <<<"$stt_report" \
            || problems+=("kilix-stt did not report dictation=ready")
        run_voice_functional_smoke >/dev/null 2>&1 \
            || problems+=("espeak/Vosk synthesis-recognition smoke test failed")
    fi

    if [ "${#problems[@]}" -gt 0 ]; then
        if [ "$PLEBIAN_OS_RELEASE_MODE" = 1 ] || [ "$INSTALL_VOICE_MODEL" = 1 ]; then
            die "Kilix Voice verification failed: ${problems[*]}"
        fi
        warn "Kilix Voice is unavailable: ${problems[*]} (run 'kilix voice doctor' after login)"
        return 0
    fi
    if [ "$INSTALL_VOICE_MODEL" = 1 ]; then
        log "voice: all tools execute and the verified offline-dictation closure is ready"
    else
        log "voice: all read-aloud tools execute; dictation assets were explicitly skipped"
    fi
}

verify_kilix_fork_build() {
    local current target generation generation_owner build_root generation_root
    local fork kitten root head source_id_path stamp_path
    local stamp_owner stamp_mode stamp_links
    local which_output engine
    current="$KILIX_BUILD_DIRECTORY/current"
    [ -L "$current" ] \
        || die "kilix fork build did not publish a current generation symlink"
    target="$(readlink -- "$current" 2>/dev/null || true)"
    [[ "$target" =~ ^generations/build\.[A-Za-z0-9]+$ ]] \
        || die "kilix fork build published an unsafe current generation target"
    generation="$KILIX_BUILD_DIRECTORY/$target"
    [ -d "$generation" ] && [ ! -L "$generation" ] \
        || die "kilix fork build current generation is missing or unsafe"
    build_root="$(cd "$KILIX_BUILD_DIRECTORY" && pwd -P 2>/dev/null || true)"
    generation_root="$(cd "$generation" && pwd -P 2>/dev/null || true)"
    [ -n "$build_root" ] && [ "$generation_root" = "$build_root/$target" ] \
        || die "kilix fork build current generation escapes the build root"
    generation_owner="$(stat -c '%u' -- "$generation" 2>/dev/null || true)"
    [ "$generation_owner" = "$TARGET_UID" ] \
        || die "kilix fork build generation is not owned by $TARGET_USER"
    fork="$KILIX_BUILD_DIRECTORY/current/src/kitty/launcher/kitty"
    kitten="$KILIX_BUILD_DIRECTORY/current/src/kitty/launcher/kitten"
    [ -f "$fork" ] && [ ! -L "$fork" ] && [ -x "$fork" ] \
        || die "kilix fork build did not produce a regular executable $fork"
    [ -f "$kitten" ] && [ ! -L "$kitten" ] && [ -x "$kitten" ] \
        || die "kilix fork build did not produce a regular executable $kitten"
    probe_kilix_launcher "$kitten" \
        || die "kilix fork kitten failed its post-build version probe"

    root="$(cd "$KILIX_DIR" && pwd -P 2>/dev/null || true)"
    [ -n "$root" ] || die "kilix fork build has no physical checkout root to verify"
    head="$(as_user git -C "$KILIX_DIR/src" rev-parse --verify HEAD 2>/dev/null || true)"
    [ -n "$head" ] || die "kilix fork build has no source commit to verify"

    source_id_path="$KILIX_BUILD_DIRECTORY/current/source-id"
    [ -f "$source_id_path" ] && [ ! -L "$source_id_path" ] \
        || die "kilix fork build has no safe source-id: $source_id_path"
    printf '%s\n' "$head" | cmp -s - "$source_id_path" \
        || die "kilix fork build source-id does not match the source checkout"

    # `kilix --build` owns this canonical, atomically-published source-ref
    # stamp.  Pleb update reads and rolls back the same file; firstboot must not
    # create a second stamp that can diverge from the promoted generation.
    stamp_path="$KILIX_STATE_DIRECTORY/fork-built-ref"
    [ -f "$stamp_path" ] && [ ! -L "$stamp_path" ] \
        || die "kilix fork build has no safe source-ref stamp: $stamp_path"
    stamp_owner="$(stat -c '%u' -- "$stamp_path" 2>/dev/null || true)"
    [ "$stamp_owner" = "$TARGET_UID" ] \
        || die "kilix fork build stamp is not owned by $TARGET_USER: $stamp_path"
    stamp_mode="$(stat -c '%a' -- "$stamp_path" 2>/dev/null || true)"
    [ "$stamp_mode" = 600 ] \
        || die "kilix fork build stamp must have mode 0600: $stamp_path"
    stamp_links="$(stat -c '%h' -- "$stamp_path" 2>/dev/null || true)"
    [ "$stamp_links" = 1 ] \
        || die "kilix fork build stamp must have exactly one hard link: $stamp_path"
    printf '%s\t%s\n' "$root" "$head" | cmp -s - "$stamp_path" \
        || die "kilix fork build stamp does not match the source checkout"

    which_output="$(as_user env "${install_env[@]}" "$KILIX_DIR/kilix" --which 2>/dev/null)" \
        || die "kilix fork engine failed its post-build version probe"
    engine="${which_output%%$'\n'*}"
    [ "$engine" = "$fork" ] \
        || die "kilix is not using the fork engine after build (got: ${engine:-<empty>})"
    log "kilix engine verified: $engine (source ${head:0:12})"
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
        echo "    + ensure Go >= $KILIX_GO_MIN_VERSION${KILIX_GO_VERSION:+ (exactly $KILIX_GO_VERSION, sha256-pinned with root-owned .pleb-source stamp)} using $PLEB_DIR/scripts/install-go.sh if needed"
        echo "    + (as $TARGET_USER) $KILIX_DIR/kilix --build"
        echo "    + verify fork + kitten, source-id, $KILIX_STATE_DIRECTORY/fork-built-ref, and $KILIX_DIR/kilix --which"
        return 0
    fi

    [ -d "$KILIX_DIR/.git" ] || die "kilix checkout missing at $KILIX_DIR after pleb install"
    [ -x "$KILIX_DIR/kilix" ] || die "kilix launcher missing at $KILIX_DIR/kilix"

    log "initializing kilix source submodules"
    as_user git -C "$KILIX_DIR" submodule update --init --recursive \
        || die "kilix submodule initialization failed"

    ensure_go_for_kilix_build

    log "building kilix clickable-chrome fork"
    as_user env "${install_env[@]}" "$KILIX_DIR/kilix" --build \
        || die "kilix fork build failed"
    verify_kilix_fork_build
}

# Tests source the path-agnostic transaction/version helpers without running the
# root provisioning workflow. Normal execution never sets this internal flag.
if [ "${PLEBIAN_OS_PROVISION_LIB_ONLY:-0}" = 1 ]; then
    # shellcheck disable=SC2317  # exit is the direct-execution fallback
    return 0 2>/dev/null || exit 0
fi

# ── args ─────────────────────────────────────────────────────────────────────
while [ $# -gt 0 ]; do
    case "$1" in
        --user)   TARGET_USER="${2:?}"; shift 2; TARGET_USER_EXPLICIT=1 ;;
        --kiosk)  KIOSK=1; shift; KIOSK_EXPLICIT=1 ;;
        --nopasswd-sudo) NOPASSWD_SUDO=1; shift; NOPASSWD_SUDO_EXPLICIT=1 ;;
        --desktop) DESKTOP=1; shift; DESKTOP_EXPLICIT=1 ;;
        --no-desktop) DESKTOP=0; shift; DESKTOP_EXPLICIT=1 ;;
        --branch)
            PLEB_BRANCH="${2:?}"; shift 2
            PLEB_BRANCH_EXPLICIT=1; PERSISTED_KEY_EXPLICIT[PLEB_BRANCH]=1 ;;
        --dry-run) DRY_RUN=1; shift ;;
        --version) echo "plebian-os-provision $PLEBIAN_OS_VERSION"; exit 0 ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown option: $1 (see --help)" ;;
    esac
done

# `--branch` asks to track a branch, so it must not be overruled by a persisted
# exact pleb ref; every other key still resolves from the installed closure.
if [ "$PLEB_BRANCH_EXPLICIT" = 1 ]; then
    restore_installed_closure PLEB_REF
else
    restore_installed_closure
fi
restore_persisted_policy

validate_release_inputs

[ "$(id -u)" = 0 ] || [ "$DRY_RUN" = 1 ] || die "must run as root (try: sudo $0)"

# ── pick the target user ─────────────────────────────────────────────────────
pick_user() {
    # the account d-i created: lowest uid >= 1000 with a real shell and home
    getent passwd | awk -F: '$3>=1000 && $3<65534 && $7!~/(nologin|false)$/ {print $3":"$1}' \
        | sort -n | head -1 | cut -d: -f2
}
[ -n "$TARGET_USER" ] || TARGET_USER="$(pick_user)"
[ -n "$TARGET_USER" ] || die "no regular user found — create one, or pass --user"
validate_target_user
GPU_TERMINAL_SOURCE_HOME="${GPU_TERMINAL_SOURCE_HOME:-$USER_HOME/.local/gpu_terminal/sources}"
PLEB_DIR="${PLEB_DIR:-$GPU_TERMINAL_SOURCE_HOME/pleb}"
KILIX_DIR="${KILIX_DIR:-$GPU_TERMINAL_SOURCE_HOME/kilix}"
KILIX95_DIR="${KILIX95_DIR:-$GPU_TERMINAL_SOURCE_HOME/kilix-desktops/kilix-95}"
KILIX_CAP_DIR="${KILIX_CAP_DIR:-$GPU_TERMINAL_SOURCE_HOME/kilix-desktops/kilix-cap}"
KILIX_TUI_UTILS_DIR="${KILIX_TUI_UTILS_DIR:-$GPU_TERMINAL_SOURCE_HOME/kilix-desktops/kilix-tui-utils}"
KILIX_LAND_DESKTOP_DIR="${KILIX_LAND_DESKTOP_DIR:-$GPU_TERMINAL_SOURCE_HOME/kilix-desktops/kilix-land-desktop}"
if [ "$KILIX95_DIR" = "$GPU_TERMINAL_SOURCE_HOME/kilix-95" ] \
   && [ ! -e "$KILIX95_DIR" ] && [ ! -L "$KILIX95_DIR" ]; then
    KILIX95_DIR="$GPU_TERMINAL_SOURCE_HOME/kilix-desktops/kilix-95"
fi
if [ "$KILIX_CAP_DIR" = "$GPU_TERMINAL_SOURCE_HOME/kilix-cap" ] \
   && [ ! -e "$KILIX_CAP_DIR" ] && [ ! -L "$KILIX_CAP_DIR" ]; then
    KILIX_CAP_DIR="$GPU_TERMINAL_SOURCE_HOME/kilix-desktops/kilix-cap"
fi
if [ "$KILIX_TUI_UTILS_DIR" = "$GPU_TERMINAL_SOURCE_HOME/kilix-tui-utils" ] \
   && [ ! -e "$KILIX_TUI_UTILS_DIR" ] && [ ! -L "$KILIX_TUI_UTILS_DIR" ]; then
    KILIX_TUI_UTILS_DIR="$GPU_TERMINAL_SOURCE_HOME/kilix-desktops/kilix-tui-utils"
fi
if [ "$KILIX_LAND_DESKTOP_DIR" = "$GPU_TERMINAL_SOURCE_HOME/kilix-land-desktop" ] \
   && [ ! -e "$KILIX_LAND_DESKTOP_DIR" ] \
   && [ ! -L "$KILIX_LAND_DESKTOP_DIR" ]; then
    KILIX_LAND_DESKTOP_DIR="$GPU_TERMINAL_SOURCE_HOME/kilix-desktops/kilix-land-desktop"
fi
PLEBIAN_OS_DIR="${PLEBIAN_OS_DIR:-$GPU_TERMINAL_SOURCE_HOME/plebian-os}"
GPU_TERMINAL_HOME="${GPU_TERMINAL_HOME:-$USER_HOME/.local/gpu_terminal}"
GPU_TERMINAL_SETTINGS_FILE="${GPU_TERMINAL_SETTINGS_FILE:-$GPU_TERMINAL_HOME/settings.conf}"
PLEB_STORAGE_HOME="${PLEB_STORAGE_HOME:-$GPU_TERMINAL_HOME/pleb}"
PLEB_CONFIG_HOME="${PLEB_CONFIG_HOME:-$PLEB_STORAGE_HOME/config}"
PLEB_STATE_HOME="${PLEB_STATE_HOME:-$PLEB_STORAGE_HOME/state}"
PLEB_CACHE_HOME="${PLEB_CACHE_HOME:-$PLEB_STORAGE_HOME/cache}"
PLEB_SESSION_HOME="${PLEB_SESSION_HOME:-$PLEB_STORAGE_HOME/session}"
PLEB_DATA_HOME="${PLEB_DATA_HOME:-$PLEB_STORAGE_HOME/data}"
KILIX_STORAGE_HOME="${KILIX_STORAGE_HOME:-$GPU_TERMINAL_HOME/kilix}"
KILIX_CONFIG_HOME="${KILIX_CONFIG_HOME:-$KILIX_STORAGE_HOME/config}"
KILIX_STATE_DIRECTORY="${KILIX_STATE_DIRECTORY:-$KILIX_STORAGE_HOME/state}"
KILIX_CACHE_HOME="${KILIX_CACHE_HOME:-$KILIX_STORAGE_HOME/cache}"
KILIX_SESSION_HOME="${KILIX_SESSION_HOME:-$KILIX_STORAGE_HOME/session}"
KILIX_BUILD_DIRECTORY="${KILIX_BUILD_DIRECTORY:-$KILIX_STORAGE_HOME/build}"
KILIX_DATA_HOME="${KILIX_DATA_HOME:-$KILIX_STORAGE_HOME/data}"
KILIX_DESKTOP_DIR="${KILIX_DESKTOP_DIR:-$PLEB_DATA_HOME/desktop}"
KILIX_PREBUILT_HOME="${KILIX_PREBUILT_HOME:-$KILIX_STORAGE_HOME/prebuilt/kitty.app}"
KILIX95_STORAGE_HOME="${KILIX95_STORAGE_HOME:-$GPU_TERMINAL_HOME/kilix-95}"
KILIX95_CONFIG_HOME="${KILIX95_CONFIG_HOME:-$KILIX95_STORAGE_HOME/config}"
KILIX95_STATE_HOME="${KILIX95_STATE_HOME:-$KILIX95_STORAGE_HOME/state}"
KILIX95_CACHE_HOME="${KILIX95_CACHE_HOME:-$KILIX95_STORAGE_HOME/cache}"
KILIX95_SESSION_HOME="${KILIX95_SESSION_HOME:-$KILIX95_STORAGE_HOME/session}"
KILIX95_DATA_HOME="${KILIX95_DATA_HOME:-$KILIX95_STORAGE_HOME/data}"
PLEBIAN_OS_STORAGE_HOME="${PLEBIAN_OS_STORAGE_HOME:-$GPU_TERMINAL_HOME/plebian-os}"
PLEBIAN_OS_SESSION_HOME="${PLEBIAN_OS_SESSION_HOME:-$PLEBIAN_OS_STORAGE_HOME/session}"
export GPU_TERMINAL_SOURCE_HOME GPU_TERMINAL_HOME GPU_TERMINAL_SETTINGS_FILE
export PLEBIAN_OS_STORAGE_HOME PLEBIAN_OS_SESSION_HOME
resolve_session_wm_defaults

# The login-session choice and the installed desktop closure are independent.
# A main-Kilix login must still make the selected external desktop available to
# an explicit `kilix desktop` invocation.  Pleb intentionally exposes
# PLEB_INSTALL_KILIX95 for this distribution-policy case; honor the provider's
# auto-install switch while keeping unrelated providers free of a K95 clone.
PLEB_INSTALL_KILIX95=0
if kilix95_install_required; then
    PLEB_INSTALL_KILIX95=1
fi

# Allocate the shared private data tree before even the provision/update lock
# is created.  This prevents the first target-user write from inheriting the
# firstboot service's permissive umask and makes reruns repair older 0755 roots.
allocate_coordinated_private_storage

log "plebian-os  : version $PLEBIAN_OS_VERSION"
log "target user : $TARGET_USER ($USER_HOME)"
log "source root : $GPU_TERMINAL_SOURCE_HOME"
log "data root   : $GPU_TERMINAL_HOME"
log "pleb repo   : $PLEB_REPO ${PLEB_BRANCH:+(branch $PLEB_BRANCH)}"
log "kilix repo  : $KILIX_REPO -> $KILIX_DIR (cloned by pleb)"
if [ "$DESKTOP" = 1 ]; then
    log "desktop    : provider=$KILIX_DESKTOP_PROVIDER name=$KILIX_DESKTOP_NAME"
    if [ "$KILIX_DESKTOP_PROVIDER" = cap ]; then
        log "kilix cap  : $KILIX_CAP_REPO -> $KILIX_CAP_DIR (first launch)"
    elif [ "$KILIX_DESKTOP_PROVIDER" = tui ]; then
        log "kilix tui  : $KILIX_TUI_UTILS_REPO -> $KILIX_TUI_UTILS_DIR (first launch)"
    elif [ "$KILIX_DESKTOP_PROVIDER" = land ]; then
        log "kilix land : $KILIX_LAND_DESKTOP_REPO -> $KILIX_LAND_DESKTOP_DIR (first launch)"
    fi
fi
if [ "$PLEB_INSTALL_KILIX95" = 1 ]; then
    log "kilix 95   : $KILIX95_REPO -> $KILIX95_DIR (cloned by pleb)"
fi
log "kiosk       : $([ "$KIOSK" = 1 ] && echo 'yes (autologin)' || echo 'no (greeter)')"
log "session     : $([ "$DESKTOP" = 1 ] && echo "kilix desktop ($KILIX_DESKTOP_PROVIDER)" || echo 'plain kilix shell')"
log "window mgr  : $PLEB_WM (KILIX_RUN_ALIASES=$KILIX_RUN_ALIASES)"

# Hold the same target-user lock used by direct `pleb update` before the first
# provisioning mutation and through final provenance/session reconciliation.
acquire_provision_lock
acquire_kilix_provision_lock

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
install_no_beep_defaults
install_quiet_console_defaults
install_desktop_wallpaper
install_version_marker
install_lightdm_greeter_branding
install_artwork_notices

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

# Starting with 0.1.9 the target-release closure selector is part of the
# installed OS layer too. This makes every later adjacent release hop available
# from PATH while retaining the target tag as the authority for its manifest.
SELECTOR_SRC=""
for cand in \
    "$SELF_DIR/plebian-os-select-closure.sh" \
    "$SELF_DIR/plebian-os-select-closure"; do
    [ -r "$cand" ] && SELECTOR_SRC="$cand" && break
done
if [ -n "$SELECTOR_SRC" ]; then
    log "installing closure selector -> /usr/local/bin/plebian-os-select-closure"
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + install -m 0755 $SELECTOR_SRC /usr/local/bin/plebian-os-select-closure"
    else
        install -m 0755 "$SELECTOR_SRC" /usr/local/bin/plebian-os-select-closure
    fi
elif [ -x /usr/local/bin/plebian-os-select-closure ]; then
    log "closure selector already present at /usr/local/bin/plebian-os-select-closure"
else
    warn "closure selector not found; continuing without plebian-os-select-closure"
fi

# Optional NVIDIA driver helper. Installed onto PATH so it is discoverable, and
# never run: the image ships nouveau, which drives a display on any supported
# card. Only a machine that needs CUDA, NVENC/NVDEC or full clocks has a reason
# to run this, and that is the owner's call, not the provisioner's.
NVIDIA_SRC=""
for cand in \
    "$SELF_DIR/plebian-os-nvidia-driver" \
    "$SELF_DIR/plebian-os-nvidia-driver.sh"; do
    [ -r "$cand" ] && NVIDIA_SRC="$cand" && break
done
if [ -n "$NVIDIA_SRC" ]; then
    log "installing optional NVIDIA driver helper -> /usr/local/bin/plebian-os-nvidia-driver"
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + install -m 0755 $NVIDIA_SRC /usr/local/bin/plebian-os-nvidia-driver"
    else
        install -m 0755 "$NVIDIA_SRC" /usr/local/bin/plebian-os-nvidia-driver
    fi
elif [ -x /usr/local/bin/plebian-os-nvidia-driver ]; then
    log "NVIDIA driver helper already present at /usr/local/bin/plebian-os-nvidia-driver"
else
    warn "NVIDIA driver helper not found; continuing without plebian-os-nvidia-driver"
fi

# Password-change helper + scoped sudoers (the default-password desktop nag).
install_passwd_nag

# ── 2. allocate all coordinated source checkouts under the shared root ───────
case "$GPU_TERMINAL_SOURCE_HOME" in
    /*) ;;
    *) die "GPU_TERMINAL_SOURCE_HOME must be absolute: $GPU_TERMINAL_SOURCE_HOME" ;;
esac
if [ "$DRY_RUN" = 1 ]; then
    echo "    + (as $TARGET_USER) mkdir -p $GPU_TERMINAL_SOURCE_HOME"
else
    as_user mkdir -p -- "$GPU_TERMINAL_SOURCE_HOME" \
        || die "could not create source root as $TARGET_USER: $GPU_TERMINAL_SOURCE_HOME"
    [ -d "$GPU_TERMINAL_SOURCE_HOME" ] && [ ! -L "$GPU_TERMINAL_SOURCE_HOME" ] \
        || die "source root is not a safe directory: $GPU_TERMINAL_SOURCE_HOME"
    [ "$(stat -c '%u' "$GPU_TERMINAL_SOURCE_HOME" 2>/dev/null)" = "$TARGET_UID" ] \
        || die "source root is not owned by $TARGET_USER: $GPU_TERMINAL_SOURCE_HOME"
fi
ensure_plebian_os_checkout
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
        checkout_pinned_ref "$PLEB_DIR" "$PLEB_REF" "pleb"
    fi
fi

# ── 3. run `pleb install` (clones kilix + engine, registers the Pleb session) ─
# pleb does its system writes through sudo; grant the user passwordless sudo for
# the duration of provisioning, then revoke it (leaves the system as it found it).
# Remove the temporary grant on normal exit AND on signals: a SIGTERM window
# (e.g. the firstboot TimeoutStartSec) must never leave passwordless sudo behind.
# SIGKILL can't be trapped, so the firstboot unit's ExecStartPre also clears any
# stale file before each attempt.
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
    "GPU_TERMINAL_SOURCE_HOME=$GPU_TERMINAL_SOURCE_HOME"
    "GPU_TERMINAL_HOME=$GPU_TERMINAL_HOME"
    "GPU_TERMINAL_SETTINGS_FILE=$GPU_TERMINAL_SETTINGS_FILE"
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
    "KILIX_STORAGE_HOME=$KILIX_STORAGE_HOME"
    "KILIX_CONFIG_HOME=$KILIX_CONFIG_HOME"
    "KILIX_STATE_DIRECTORY=$KILIX_STATE_DIRECTORY"
    "KILIX_CACHE_HOME=$KILIX_CACHE_HOME"
    "KILIX_SESSION_HOME=$KILIX_SESSION_HOME"
    "KILIX_BUILD_DIRECTORY=$KILIX_BUILD_DIRECTORY"
    "KILIX_DATA_HOME=$KILIX_DATA_HOME"
    "KILIX_DESKTOP_DIR=$KILIX_DESKTOP_DIR"
    "KILIX_PREBUILT_HOME=$KILIX_PREBUILT_HOME"
    "KILIX95_STORAGE_HOME=$KILIX95_STORAGE_HOME"
    "KILIX95_CONFIG_HOME=$KILIX95_CONFIG_HOME"
    "KILIX95_STATE_HOME=$KILIX95_STATE_HOME"
    "KILIX95_CACHE_HOME=$KILIX95_CACHE_HOME"
    "KILIX95_SESSION_HOME=$KILIX95_SESSION_HOME"
    "KILIX95_DATA_HOME=$KILIX95_DATA_HOME"
    "KILIX_DIR=$KILIX_DIR"
    "KILIX_REPO=$KILIX_REPO"
    "KILIX_BRANCH=$KILIX_BRANCH"
    "KILIX_REF=$KILIX_REF"
    "KILIX_PREBUILT_VERSION=$KILIX_PREBUILT_VERSION"
    "KILIX_PREBUILT_SHA256=$KILIX_PREBUILT_SHA256"
    "KILIX_VOICE_REF=$KILIX_VOICE_REF"
    "KILIX_VOICE_LIB_VERSION=$KILIX_VOICE_LIB_VERSION"
    "KILIX_VOICE_LIB_URL=$KILIX_VOICE_LIB_URL"
    "KILIX_VOICE_LIB_SHA256=$KILIX_VOICE_LIB_SHA256"
    "KILIX_VOICE_MODEL_URL=$KILIX_VOICE_MODEL_URL"
    "KILIX_VOICE_MODEL_SHA256=$KILIX_VOICE_MODEL_SHA256"
    "PLEB_INSTALL_VOICE_MODEL=$INSTALL_VOICE_MODEL"
    "PLEBIAN_OS_BUILD_KILIX_FORK=$BUILD_KILIX_FORK"
    "PLEBIAN_OS_KILIX_GO_MIN_VERSION=$KILIX_GO_MIN_VERSION"
    "PLEBIAN_OS_KILIX_GO_VERSION=$KILIX_GO_VERSION"
    "PLEBIAN_OS_KILIX_GO_SHA256_AMD64=$KILIX_GO_SHA256_AMD64"
    "PLEBIAN_OS_KILIX_GO_SHA256_ARM64=$KILIX_GO_SHA256_ARM64"
    "KILIX_DESKTOP_PROVIDER=$KILIX_DESKTOP_PROVIDER"
    "KILIX_DESKTOP_COMMAND=$KILIX_DESKTOP_COMMAND"
    "KILIX_DESKTOP_NAME=$KILIX_DESKTOP_NAME"
    "KILIX_DESKTOP_FLAVOR=$KILIX_DESKTOP_FLAVOR"
    "PLEB_INSTALL_KILIX95=$PLEB_INSTALL_KILIX95"
    "KILIX_CAP_AUTO_INSTALL=$KILIX_CAP_AUTO_INSTALL"
    "KILIX_CAP_DIR=$KILIX_CAP_DIR"
    "KILIX_CAP_REPO=$KILIX_CAP_REPO"
    "KILIX_CAP_REF=$KILIX_CAP_REF"
    "KILIX_CAP_TRUST_EXISTING_CHECKOUT=$KILIX_CAP_TRUST_EXISTING_CHECKOUT"
    "KILIX_CAP_ALLOW_MUTABLE_REF=$KILIX_CAP_ALLOW_MUTABLE_REF"
    "KILIX_TUI_UTILS_AUTO_INSTALL=$KILIX_TUI_UTILS_AUTO_INSTALL"
    "KILIX_TUI_UTILS_DIR=$KILIX_TUI_UTILS_DIR"
    "KILIX_TUI_UTILS_REPO=$KILIX_TUI_UTILS_REPO"
    "KILIX_TUI_UTILS_REF=$KILIX_TUI_UTILS_REF"
    "KILIX_TUI_UTILS_TRUST_EXISTING_CHECKOUT=$KILIX_TUI_UTILS_TRUST_EXISTING_CHECKOUT"
    "KILIX_TUI_UTILS_ALLOW_MUTABLE_REF=$KILIX_TUI_UTILS_ALLOW_MUTABLE_REF"
    "KILIX_LAND_DESKTOP_AUTO_INSTALL=$KILIX_LAND_DESKTOP_AUTO_INSTALL"
    "KILIX_LAND_DESKTOP_DIR=$KILIX_LAND_DESKTOP_DIR"
    "KILIX_LAND_DESKTOP_REPO=$KILIX_LAND_DESKTOP_REPO"
    "KILIX_LAND_DESKTOP_REF=$KILIX_LAND_DESKTOP_REF"
    "KILIX_LAND_DESKTOP_TRUST_EXISTING_CHECKOUT=$KILIX_LAND_DESKTOP_TRUST_EXISTING_CHECKOUT"
    "KILIX_LAND_DESKTOP_ALLOW_MUTABLE_REF=$KILIX_LAND_DESKTOP_ALLOW_MUTABLE_REF"
    "KILIX_LAND_DESKTOP_ASSETS=$KILIX_LAND_DESKTOP_ASSETS"
    "KILIX_LAND_DESKTOP_CONFIG_HOME=$KILIX_LAND_DESKTOP_CONFIG_HOME"
    "KILIX_LAND_DESKTOP_EXTERNAL_APPS=$KILIX_LAND_DESKTOP_EXTERNAL_APPS"
    "KILIX_LAND_DESKTOP_AUDIO=$KILIX_LAND_DESKTOP_AUDIO"
    "PLEB_DESKTOP=$DESKTOP"
    "PLEB_WM=$PLEB_WM"
    "KILIX_RUN_ALIASES=$KILIX_RUN_ALIASES"
    "KILIX95_AUTO_INSTALL=$KILIX95_AUTO_INSTALL"
    "KILIX95_DIR=$KILIX95_DIR"
    "KILIX95_REPO=$KILIX95_REPO"
    "KILIX95_BRANCH=$KILIX95_BRANCH"
    "KILIX95_REF=$KILIX95_REF"
)
[ -n "${PROVISION_LOCK_FD:-}" ] \
    && install_env+=("PLEB_UPDATE_LOCK_FD=$PROVISION_LOCK_FD")
[ -n "${KILIX_PROVISION_LOCK_FD:-}" ] \
    && install_env+=(
        "KILIX_TRANSACTION_LOCK_FD=$KILIX_PROVISION_LOCK_FD"
        "KILIX_TRANSACTION_LOCK_PATH=$KILIX_PROVISION_LOCK_PATH"
    )
as_user env "${install_env[@]}" "$PLEB_DIR/bin/pleb" install \
    || die "pleb install failed (see above)"
if [ "$DRY_RUN" != 1 ]; then
    if [ ! -f "$GPU_TERMINAL_SETTINGS_FILE" ] \
            || [ -L "$GPU_TERMINAL_SETTINGS_FILE" ] \
            || [ "$(stat -c '%u:%a' -- "$GPU_TERMINAL_SETTINGS_FILE" 2>/dev/null)" \
                 != "$TARGET_UID:600" ]; then
        die "shared Kilix settings were not safely initialized: $GPU_TERMINAL_SETTINGS_FILE"
    fi
    # Session logging ships on. `kilix-settings --ensure` seeds it through the
    # shared SDK, so this asserts the delivered default rather than setting it
    # here — a second source of truth for the same value would drift.
    settings_logging="$(
        as_user env "GPU_TERMINAL_SETTINGS_FILE=$GPU_TERMINAL_SETTINGS_FILE" \
            python3 -c "
import sys
sys.path.insert(0, '$KILIX_DIR/config')
from kilix_sdk import settings
print('on' if settings.transcript_enabled() else 'off')
" 2>/dev/null
    )" || settings_logging=""
    [ "$settings_logging" = on ] \
        || die "session logging was not enabled by default in $GPU_TERMINAL_SETTINGS_FILE"
    log "session logs: on by default (kilix settings --set transcript=off to disable)"
    if [ ! -x "$USER_HOME/.local/bin/kilix-temps" ] \
            || [ ! -x "$USER_HOME/.local/bin/kilix-memory" ] \
            || [ ! -L /usr/local/bin/kilix-temps ] \
            || [ "$(readlink /usr/local/bin/kilix-temps 2>/dev/null)" \
                 != "$USER_HOME/.local/bin/kilix-temps" ]; then
        die "Pleb did not install the unified Temps/Memory utilities and publish Temps"
    fi
    if [ ! -x "$USER_HOME/.local/bin/tmux-tui" ] \
            || [ ! -x "$USER_HOME/.local/bin/tb" ] \
            || [ ! -L /usr/local/bin/tmux-tui ] \
            || [ "$(readlink /usr/local/bin/tmux-tui 2>/dev/null)" \
                 != "$USER_HOME/.local/bin/tmux-tui" ] \
            || [ ! -L /usr/local/bin/tb ] \
            || [ "$(readlink /usr/local/bin/tb 2>/dev/null)" \
                 != "$USER_HOME/.local/bin/tb" ]; then
        die "Pleb did not install Tmux Manager and publish tmux-cli's tb alias"
    fi
    _pty_broker="$KILIX_BUILD_DIRECTORY/libraries/kitty-pty-broker/kitty-pty-broker"
    if [ ! -x "$_pty_broker" ] || [ -L "$_pty_broker" ] \
            || ! as_user "$_pty_broker" version >/dev/null 2>&1; then
        die "Pleb did not build Kilix's pinned persistent PTY manager"
    fi
    # Import and execute every installed entrypoint. An enabled dictation
    # policy is a required release closure, so Pleb's intentionally graceful
    # read-aloud fallback must not let a release image pass firstboot.
    verify_kilix_voice_install
fi
build_kilix_fork
seed_selected_desktop_wallpaper_state
record_default_desktop

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

# ── 5. session mode: desktop provider or shell in the first Kilix page ────
# pleb-session reads /etc/pleb/session.env on every login. PLEB_DESKTOP=1
# starts the main Kilix window with `kilix desktop` as page 1's program;
# PLEB_DESKTOP=0 starts that window with a shell instead.
# PLEB_WM
# selects the window manager it starts (openbox, or none for the historic
# fixed-geometry session). This is a plain root-managed config file: edit it with
# sudo to flip either knob — no reprovision needed, and a reprovision keeps the
# window-manager choice it finds here.
#
# A machine that already has this file gets the render merged into it rather
# than written over it (merge_session_env above): a re-provision rewrites the
# keys it owns and leaves every other line — the operator's values, their
# unknown keys, their comments, whatever they appended — exactly where it found
# them. A first-ever provision has nothing to merge and gets the whole template.
PLEB_ENV=/etc/pleb/session.env
log "writing session config -> $PLEB_ENV (PLEB_DESKTOP=$DESKTOP, PLEB_WM=$PLEB_WM, KILIX_RUN_ALIASES=$KILIX_RUN_ALIASES)"
if [ "$DRY_RUN" = 1 ]; then
    echo "    + write $PLEB_ENV (PLEB_DESKTOP=$DESKTOP, PLEB_WM=$PLEB_WM, KILIX_RUN_ALIASES=$KILIX_RUN_ALIASES)"
else
    mkdir -p "$(dirname "$PLEB_ENV")"
    PLEB_ENV_TMP="$(mktemp /etc/pleb/.session.env.XXXXXX)"
    {
    cat <<'EOF'
# Managed by plebian-os-provision — Plebian-OS Pleb session config.
# PLEB_DESKTOP=1 starts `kilix desktop` in the first screen-filling Kilix page;
# set it to 0 for a shell there instead. KILIX_DESKTOP_PROVIDER selects
# auto, builtin, external, xp, cap,
# tui, land, command, or none. PLEB_WM selects the window manager (openbox,
# none, or a command line); an explicit choice here is kept by a reprovision.
# pleb-session documents the other knobs.
EOF
    write_session_default GPU_TERMINAL_SOURCE_HOME "$GPU_TERMINAL_SOURCE_HOME"
    write_session_default GPU_TERMINAL_HOME "$GPU_TERMINAL_HOME"
    write_session_default GPU_TERMINAL_SETTINGS_FILE "$GPU_TERMINAL_SETTINGS_FILE"
    write_session_default PLEBIAN_OS_MANAGED_INSTALL 1
    write_session_default PLEB_DIR "$PLEB_DIR"
    write_session_default PLEB_STORAGE_HOME "$PLEB_STORAGE_HOME"
    write_session_default PLEB_CONFIG_HOME "$PLEB_CONFIG_HOME"
    write_session_default PLEB_STATE_HOME "$PLEB_STATE_HOME"
    write_session_default PLEB_CACHE_HOME "$PLEB_CACHE_HOME"
    write_session_default PLEB_SESSION_HOME "$PLEB_SESSION_HOME"
    write_session_default PLEB_DATA_HOME "$PLEB_DATA_HOME"
    write_session_default PLEB_REPO "$PLEB_REPO"
    write_session_default PLEB_BRANCH "$PLEB_BRANCH"
    write_session_default PLEB_REF "$PLEB_REF"
    write_session_default KILIX_DIR "$KILIX_DIR"
    write_session_default KILIX_STORAGE_HOME "$KILIX_STORAGE_HOME"
    write_session_default KILIX_CONFIG_HOME "$KILIX_CONFIG_HOME"
    write_session_default KILIX_STATE_DIRECTORY "$KILIX_STATE_DIRECTORY"
    write_session_default KILIX_CACHE_HOME "$KILIX_CACHE_HOME"
    write_session_default KILIX_SESSION_HOME "$KILIX_SESSION_HOME"
    write_session_default KILIX_BUILD_DIRECTORY "$KILIX_BUILD_DIRECTORY"
    write_session_default KILIX_DATA_HOME "$KILIX_DATA_HOME"
    write_session_default KILIX_DESKTOP_DIR "$KILIX_DESKTOP_DIR"
    write_session_default KILIX_PREBUILT_HOME "$KILIX_PREBUILT_HOME"
    write_session_default KILIX "$KILIX_DIR/kilix"
    write_session_default KILIX_REPO "$KILIX_REPO"
    write_session_default KILIX_BRANCH "$KILIX_BRANCH"
    write_session_default KILIX_REF "$KILIX_REF"
    write_session_default KILIX_PREBUILT_VERSION "$KILIX_PREBUILT_VERSION"
    write_session_default KILIX_PREBUILT_SHA256 "$KILIX_PREBUILT_SHA256"
    write_session_default KILIX_VOICE_REF "$KILIX_VOICE_REF"
    write_session_default KILIX_VOICE_LIB_VERSION "$KILIX_VOICE_LIB_VERSION"
    write_session_default KILIX_VOICE_LIB_URL "$KILIX_VOICE_LIB_URL"
    write_session_default KILIX_VOICE_LIB_SHA256 "$KILIX_VOICE_LIB_SHA256"
    write_session_default KILIX_VOICE_MODEL_URL "$KILIX_VOICE_MODEL_URL"
    write_session_default KILIX_VOICE_MODEL_SHA256 "$KILIX_VOICE_MODEL_SHA256"
    write_session_default PLEBIAN_OS_INSTALL_VOICE_MODEL "$INSTALL_VOICE_MODEL"
    write_session_default PLEBIAN_OS_BUILD_KILIX_FORK "$BUILD_KILIX_FORK"
    write_session_default PLEBIAN_OS_KILIX_GO_MIN_VERSION "$KILIX_GO_MIN_VERSION"
    write_session_default PLEBIAN_OS_KILIX_GO_VERSION "$KILIX_GO_VERSION"
    write_session_default PLEBIAN_OS_KILIX_GO_SHA256_AMD64 "$KILIX_GO_SHA256_AMD64"
    write_session_default PLEBIAN_OS_KILIX_GO_SHA256_ARM64 "$KILIX_GO_SHA256_ARM64"
    write_session_default PLEB_DESKTOP "$DESKTOP"
    write_session_default PLEB_WM "$PLEB_WM"
    write_session_default KILIX_RUN_ALIASES "$KILIX_RUN_ALIASES"
    write_session_default KILIX_DESKTOP_PROVIDER "$KILIX_DESKTOP_PROVIDER"
    write_session_default KILIX_DESKTOP_COMMAND "$KILIX_DESKTOP_COMMAND"
    write_session_default KILIX_DESKTOP_NAME "$KILIX_DESKTOP_NAME"
    write_session_default KILIX_DESKTOP_FLAVOR "$KILIX_DESKTOP_FLAVOR"
    write_session_default KILIX_CAP_AUTO_INSTALL "$KILIX_CAP_AUTO_INSTALL"
    write_session_default KILIX_CAP_DIR "$KILIX_CAP_DIR"
    write_session_default KILIX_CAP_REPO "$KILIX_CAP_REPO"
    write_session_default KILIX_CAP_REF "$KILIX_CAP_REF"
    write_session_default KILIX_CAP_TRUST_EXISTING_CHECKOUT "$KILIX_CAP_TRUST_EXISTING_CHECKOUT"
    write_session_default KILIX_CAP_ALLOW_MUTABLE_REF "$KILIX_CAP_ALLOW_MUTABLE_REF"
    write_session_default KILIX_TUI_UTILS_AUTO_INSTALL "$KILIX_TUI_UTILS_AUTO_INSTALL"
    write_session_default KILIX_TUI_UTILS_DIR "$KILIX_TUI_UTILS_DIR"
    write_session_default KILIX_TUI_UTILS_REPO "$KILIX_TUI_UTILS_REPO"
    write_session_default KILIX_TUI_UTILS_REF "$KILIX_TUI_UTILS_REF"
    write_session_default KILIX_TUI_UTILS_TRUST_EXISTING_CHECKOUT "$KILIX_TUI_UTILS_TRUST_EXISTING_CHECKOUT"
    write_session_default KILIX_TUI_UTILS_ALLOW_MUTABLE_REF "$KILIX_TUI_UTILS_ALLOW_MUTABLE_REF"
    write_session_default KILIX_LAND_DESKTOP_AUTO_INSTALL "$KILIX_LAND_DESKTOP_AUTO_INSTALL"
    write_session_default KILIX_LAND_DESKTOP_DIR "$KILIX_LAND_DESKTOP_DIR"
    write_session_default KILIX_LAND_DESKTOP_REPO "$KILIX_LAND_DESKTOP_REPO"
    write_session_default KILIX_LAND_DESKTOP_REF "$KILIX_LAND_DESKTOP_REF"
    write_session_default KILIX_LAND_DESKTOP_TRUST_EXISTING_CHECKOUT "$KILIX_LAND_DESKTOP_TRUST_EXISTING_CHECKOUT"
    write_session_default KILIX_LAND_DESKTOP_ALLOW_MUTABLE_REF "$KILIX_LAND_DESKTOP_ALLOW_MUTABLE_REF"
    write_session_default KILIX_LAND_DESKTOP_ASSETS "$KILIX_LAND_DESKTOP_ASSETS"
    write_session_default KILIX_LAND_DESKTOP_CONFIG_HOME "$KILIX_LAND_DESKTOP_CONFIG_HOME"
    write_session_default KILIX_LAND_DESKTOP_EXTERNAL_APPS "$KILIX_LAND_DESKTOP_EXTERNAL_APPS"
    write_session_default KILIX_LAND_DESKTOP_AUDIO "$KILIX_LAND_DESKTOP_AUDIO"
    write_session_default KILIX95_AUTO_INSTALL "$KILIX95_AUTO_INSTALL"
    write_session_default KILIX95_STORAGE_HOME "$KILIX95_STORAGE_HOME"
    write_session_default KILIX95_CONFIG_HOME "$KILIX95_CONFIG_HOME"
    write_session_default KILIX95_STATE_HOME "$KILIX95_STATE_HOME"
    write_session_default KILIX95_CACHE_HOME "$KILIX95_CACHE_HOME"
    write_session_default KILIX95_SESSION_HOME "$KILIX95_SESSION_HOME"
    write_session_default KILIX95_DATA_HOME "$KILIX95_DATA_HOME"
    write_session_default KILIX95_DIR "$KILIX95_DIR"
    write_session_default KILIX95_REPO "$KILIX95_REPO"
    write_session_default KILIX95_BRANCH "$KILIX95_BRANCH"
    write_session_default KILIX95_REF "$KILIX95_REF"
    write_session_default PLEBIAN_OS_VERSION "$PLEBIAN_OS_VERSION"
    write_session_default PLEBIAN_OS_RELEASE "$PLEBIAN_OS_RELEASE"
    write_session_default PLEBIAN_OS_RELEASE_MODE "$PLEBIAN_OS_RELEASE_MODE"
    write_session_default PLEBIAN_OS_REPO "$PLEBIAN_OS_REPO"
    write_session_default PLEBIAN_OS_BRANCH "$PLEBIAN_OS_BRANCH"
    write_session_default PLEBIAN_OS_REF "$PLEBIAN_OS_REF"
    write_session_default PLEBIAN_OS_DIR "$PLEBIAN_OS_DIR"
    write_session_default PLEBIAN_OS_STORAGE_HOME "$PLEBIAN_OS_STORAGE_HOME"
    write_session_default PLEBIAN_OS_SESSION_HOME "$PLEBIAN_OS_SESSION_HOME"
    write_session_default PLEBIAN_OS_APT_SNAPSHOT "$PLEBIAN_OS_APT_SNAPSHOT"
    # Pleb versions predating these category-level names do not explicitly
    # re-export them after sourcing session.env. Export both storage and desktop
    # selection provenance here so a main-Kilix login passes the same pinned
    # provider contract to a later interactive `kilix desktop` invocation.
    printf '%s\n' 'export GPU_TERMINAL_SETTINGS_FILE'
    printf '%s\n' 'export KILIX_CONFIG_HOME KILIX_STATE_DIRECTORY KILIX_CACHE_HOME KILIX_SESSION_HOME KILIX_PREBUILT_HOME'
    printf '%s\n' 'export KILIX_DESKTOP_PROVIDER KILIX_DESKTOP_COMMAND KILIX_DESKTOP_NAME KILIX_DESKTOP_FLAVOR KILIX_RUN_ALIASES'
    printf '%s\n' 'export KILIX95_AUTO_INSTALL KILIX95_DIR KILIX95_REPO KILIX95_BRANCH KILIX95_REF'
    printf '%s\n' 'export KILIX95_CONFIG_HOME KILIX95_STATE_HOME KILIX95_CACHE_HOME KILIX95_SESSION_HOME KILIX95_DATA_HOME'
    [ "$KIOSK" = 1 ] && printf '%s\n' 'PLEB_RESPAWN=1   # hard kiosk: respawn kilix if it exits (set by --kiosk)'
    } > "$PLEB_ENV_TMP"
    # Only a root-owned regular file is merged from: content carried out of a
    # file a non-root account could have written would be content this script
    # signs off on as root. restore_installed_closure has already refused to run
    # at all in that case, so this is the second lock on the same door.
    if [ -f "$PLEB_ENV" ] && [ ! -L "$PLEB_ENV" ] && root_config_safe_to_source "$PLEB_ENV"; then
        PLEB_ENV_MERGED="$(mktemp /etc/pleb/.session.env.XXXXXX)"
        if ! merge_session_env "$PLEB_ENV_TMP" "$PLEB_ENV" "$PLEB_ENV_MERGED" \
                || ! verify_merged_session_env "$PLEB_ENV_TMP" "$PLEB_ENV" "$PLEB_ENV_MERGED"; then
            rm -f "$PLEB_ENV_MERGED" "$PLEB_ENV_TMP"
            die "refusing to rewrite $PLEB_ENV over configuration this run cannot account for; nothing was written. Resolve the reported line by hand, or move the file aside to have this run write a fresh one."
        fi
        mv -fT "$PLEB_ENV_MERGED" "$PLEB_ENV_TMP"
    elif [ -e "$PLEB_ENV" ] || [ -L "$PLEB_ENV" ]; then
        warn "$PLEB_ENV is not a plain root-owned file; writing a fresh session config over it"
    fi
    chmod 0644 "$PLEB_ENV_TMP"
    mv -fT "$PLEB_ENV_TMP" "$PLEB_ENV"
fi

if [ "$KIOSK" = 1 ]; then
    log "enabling autologin into Pleb (kiosk)"
    as_user env "${install_env[@]}" "$PLEB_DIR/bin/pleb" autologin on "$TARGET_USER" \
        || die "pleb autologin failed; requested kiosk state was not applied"
    pin_remembered_session
else
    log "ensuring Pleb autologin is disabled (non-kiosk mode)"
    as_user env "${install_env[@]}" "$PLEB_DIR/bin/pleb" autologin off \
        || die "could not disable Pleb autologin; refusing to report reconciled state"
fi

# Passwordless sudo for the owner. Plebian-OS is a single-user appliance and the
# VM builder turns this on by default, so `pleb install`, the Start-menu update
# actions and Shut Down (systemctl poweroff) never stop for a password. This is
# a PERMANENT file — the grant used during provisioning above is temporary and
# removed by cleanup.
NOPASSWD_FILE=/etc/sudoers.d/plebian-os-nopasswd
if [ "$NOPASSWD_SUDO" = 1 ]; then
    log "granting $TARGET_USER passwordless sudo"
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + echo '$TARGET_USER ALL=(ALL) NOPASSWD:ALL' > $NOPASSWD_FILE (0440, visudo-checked)"
    else
        printf '%s ALL=(ALL) NOPASSWD:ALL\n' "$TARGET_USER" > "$NOPASSWD_FILE"
        chmod 0440 "$NOPASSWD_FILE"
        visudo -cf "$NOPASSWD_FILE" >/dev/null 2>&1 \
            || { rm -f "$NOPASSWD_FILE"; die "sudoers validation failed; requested passwordless-sudo state was not applied"; }
    fi
else
    log "ensuring sudo for $TARGET_USER requires a password"
    if [ "$DRY_RUN" = 1 ]; then
        echo "    + rm -f $NOPASSWD_FILE"
    else
        rm -f "$NOPASSWD_FILE"
    fi
fi

# Capture the final state only now: dependency installation, pleb install, Go
# setup, Kilix fork compilation, and all optional providers have completed.
write_package_manifest
write_source_tool_manifest

cleanup; trap - EXIT

log "done. Plebian-OS is provisioned."
log "  reboot → LightDM → Pleb → $([ "$DESKTOP" = 1 ] && echo "kilix desktop ($KILIX_DESKTOP_PROVIDER)" || echo 'screen-filling Kilix with visible chrome')."
[ "$KIOSK" = 1 ] && log "  (kiosk: autologin + kilix respawn on exit; rescue console on Ctrl+Alt+F2)"
[ "$NOPASSWD_SUDO" = 1 ] && log "  ($TARGET_USER has passwordless sudo)"
exit 0
