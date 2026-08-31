#!/usr/bin/env bash
# plebian-os-select-closure.sh — validate and atomically select one coordinated
# Plebian-OS release closure on an already-installed machine.
#
# Release images historically kept exact refs in /etc/pleb/session.env; 0.2.1
# migrates them to /etc/pleb/closure.env. In either layout plebian-os-update
# deliberately revalidates the release the machine already has instead of
# drifting to a branch head. Nothing in the updater selects a NEW release. This
# is the other half: UPGRADING.md's "Operator procedure" requires every release
# after 0.1.7 to ship an actionable mechanism which validates and atomically
# selects all of its release-controlled keys as one closure, and requires that
# mechanism to succeed BEFORE the operator runs `plebian-os-update --restart`.
#
# Usage:
#   plebian-os-select-closure <x.y.z> [--source DIR] [--offline] [--dry-run]
#   plebian-os-select-closure --show
#   plebian-os-select-closure --rollback
#
#   <x.y.z>       the target release. Its closure is read from
#                 releases/<x.y.z>.env inside the published v<x.y.z> tag, never
#                 from a working tree, so the pins are the immutable ones the
#                 release was accepted with.
#   --source DIR  the Plebian-OS source checkout to read the tag from
#                 (default: PLEBIAN_OS_DIR, i.e. the checkout the installed
#                 system already uses). Only its object store is read; the
#                 working tree and HEAD are left exactly where they were, so
#                 the updater's clean-pinned-checkout contract still holds.
#   --offline     require the tag, component commits, and complete ancestry to
#                 be present locally already; do not fetch.
#   --dry-run     validate, compare, and report; write nothing.
#   --show        print the release-controlled keys this machine currently has.
#   --rollback    put the previous closure back (the most recent one this tool
#                 replaced), atomically.
#
# The release-controlled keys move as one unit or not at all: the complete
# session/closure pair is rendered and verified by sourcing it before the
# transaction begins. The exact
# selector and updater from the target release are deployed in the same
# transaction. This bootstraps payloads and update behavior introduced after
# the starting release without asking an older installed updater to know the
# future OS-layer file list or final-provenance contract.
# Operator-controlled choices — session, provider, storage, kiosk, appearance,
# logging, thermal, audio, network, games, wallpaper, and layout — stay in
# session.env and are proven unchanged before the swap. Rollback also
# restores the selector and updater bytes which preceded the selection, or
# either file's absence.
#
# Run as the Pleb user; the bounded writes under /etc, /var/lib, and
# /usr/local/bin elevate through sudo.
set -euo pipefail

log()  { printf '\033[1;35m[plebian-os]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[plebian-os]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[plebian-os] %s\033[0m\n' "$*" >&2; exit 1; }

# Same boundary as the updater: this tool asks for exactly the privilege each
# write needs and no more, so running the whole thing as root is a mistake
# worth refusing rather than tolerating.
require_unprivileged_selector() {
    [ "${1:-$EUID}" -ne 0 ] \
        || die "run plebian-os-select-closure without sudo (it elevates only bounded system steps)"
}
require_unprivileged_selector "$EUID"

# Installed locations.  F109 adds an explicitly injected standalone shape; the
# original rerooted image shape remains the default and retains its exact
# destination contract.
CLOSURE_ROOT="${PLEBIAN_OS_CLOSURE_TEST_ROOT:-}"
case "$CLOSURE_ROOT" in
    ''|/) CLOSURE_ROOT="" ;;
    /*) CLOSURE_ROOT="${CLOSURE_ROOT%/}" ;;
    *) die "PLEBIAN_OS_CLOSURE_TEST_ROOT must be an absolute path" ;;
esac
SELECTOR_MODE="${PLEBIAN_OS_SELECTOR_MODE:-image}"
case "$SELECTOR_MODE" in image|standalone) ;; *) die "invalid selector mode: $SELECTOR_MODE" ;; esac
CLOSURE_LAYOUT="${PLEBIAN_OS_CLOSURE_LAYOUT:-auto}"
case "$CLOSURE_LAYOUT" in auto|legacy|split) ;; *) die "invalid closure layout: $CLOSURE_LAYOUT" ;; esac
SESSION_ENV="${PLEBIAN_OS_SESSION_ENV:-$CLOSURE_ROOT/etc/pleb/session.env}"
CLOSURE_ENV="${PLEBIAN_OS_CLOSURE_ENV:-$CLOSURE_ROOT/etc/pleb/closure.env}"
RECOVERY_BASE="${PLEBIAN_OS_RECOVERY_BASE:-$CLOSURE_ROOT/var/lib/plebian-os}"
SELECTOR_DST="${PLEBIAN_OS_SELECTOR_DST-$CLOSURE_ROOT/usr/local/bin/plebian-os-select-closure}"
UPDATER_DST="${PLEBIAN_OS_UPDATER_DST-$CLOSURE_ROOT/usr/local/bin/plebian-os-update}"
for closure_path in "$SESSION_ENV" "$CLOSURE_ENV" "$RECOVERY_BASE"; do
    case "$closure_path" in /*) ;; *) die "closure path must be absolute: $closure_path" ;; esac
    [[ "$closure_path" != *$'\n'* && "$closure_path" != *$'\r'* ]] \
        || die "closure path contains a line break"
done
if [ "$SELECTOR_MODE" = image ]; then
    [ -n "$SELECTOR_DST" ] && [ -n "$UPDATER_DST" ] \
        || die "image selector mode requires selector and updater destinations"
    if [ -z "$CLOSURE_ROOT" ]; then
        [ "$SESSION_ENV" = /etc/pleb/session.env ] \
            && [ "$CLOSURE_ENV" = /etc/pleb/closure.env ] \
            && [ "$RECOVERY_BASE" = /var/lib/plebian-os ] \
            && [ "$SELECTOR_DST" = /usr/local/bin/plebian-os-select-closure ] \
            && [ "$UPDATER_DST" = /usr/local/bin/plebian-os-update ] \
            || die "live image mode uses only the installed Plebian-OS closure paths"
    fi
else
    [ -z "$SELECTOR_DST" ] && [ -z "$UPDATER_DST" ] \
        || die "standalone selector mode must not deploy Plebian-OS tools"
fi

closure_elevate() {
    if [ -n "$CLOSURE_ROOT" ] || [ "$(id -u)" = 0 ]; then
        "$@"
    else
        sudo "$@"
    fi
}

# Mirrors the updater's test_fail_after_boundary: a named boundary an induced
# failure can be aimed at, so rollback is provable rather than asserted.
select_test_fail_after() {
    [ "${PLEBIAN_OS_SELECT_TEST_FAIL_AFTER:-}" != "$1" ] \
        || die "injected closure selection failure after $1"
}

# ── what a release controls ─────────────────────────────────────────────────
# UPGRADING.md: "the coordinated version/release mode, the four source refs, the
# Debian snapshot and installer input, the Kilix engine and Go pins, and enabled
# optional-closure pins such as Kilix Voice". These are the keys an installed
# machine persists in /etc/pleb/session.env; they move together or not at all.
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
    KILIX_SYSTEM_MONITOR_REPO
    KILIX_SYSTEM_MONITOR_BRANCH
    KILIX_SYSTEM_MONITOR_REF
    KILIX_DESKTOP_SDK_REPO
    KILIX_DESKTOP_SDK_BRANCH
    KILIX_DESKTOP_SDK_REF
    KILIX_ICEWM_REPO
    KILIX_ICEWM_BRANCH
    KILIX_ICEWM_REF
    KILIX_MEDIA_SDK_REPO
    KILIX_MEDIA_SDK_BRANCH
    KILIX_MEDIA_SDK_REF
    KILIX_WAYDROID_REPO
    KILIX_WAYDROID_BRANCH
    KILIX_WAYDROID_REF
    PLEBIAN_OS_APT_SNAPSHOT
    PLEBIAN_OS_INSTALL_UV
    PLEBIAN_OS_UV_VERSION
    PLEBIAN_OS_UV_INSTALLER_SHA256
    PLEBIAN_OS_UV_INSTALLER_MAX_BYTES
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
    PLEBIAN_OS_INSTALL_WAYDROID
    PLEBIAN_OS_WAYDROID_CLOSURE_SHA256
)

# Release-controlled too, but consumed only while building the image: the
# installed system has no copy to move. They are still validated, because a
# closure which cannot build is not a closure, and then reported as build-only.
BUILD_ONLY_RELEASE_KEYS=(
    PLEBIAN_OS_NETINST_URL
    PLEBIAN_OS_NETINST_SHA256
    PLEBIAN_OS_NETINST_MAX_BYTES
)

# Must be present in the manifest and non-empty.
REQUIRED_VALUE_KEYS=(
    PLEBIAN_OS_VERSION
    PLEBIAN_OS_RELEASE_MODE
    PLEBIAN_OS_REPO
    PLEBIAN_OS_REF
    PLEB_REPO
    PLEB_REF
    KILIX_REPO
    KILIX_REF
    KILIX95_REPO
    KILIX95_REF
    KILIX_SYSTEM_MONITOR_REPO
    KILIX_SYSTEM_MONITOR_REF
    KILIX_DESKTOP_SDK_REPO
    KILIX_DESKTOP_SDK_REF
    KILIX_ICEWM_REPO
    KILIX_ICEWM_REF
    KILIX_MEDIA_SDK_REPO
    KILIX_MEDIA_SDK_REF
    KILIX_WAYDROID_REPO
    KILIX_WAYDROID_REF
    PLEBIAN_OS_APT_SNAPSHOT
    PLEBIAN_OS_NETINST_URL
    PLEBIAN_OS_NETINST_SHA256
    PLEBIAN_OS_INSTALL_UV
    KILIX_PREBUILT_VERSION
    KILIX_PREBUILT_SHA256
    PLEBIAN_OS_BUILD_KILIX_FORK
    PLEBIAN_OS_KILIX_GO_MIN_VERSION
    PLEBIAN_OS_KILIX_GO_VERSION
    PLEBIAN_OS_KILIX_GO_SHA256_AMD64
    PLEBIAN_OS_KILIX_GO_SHA256_ARM64
)

# Must be present, and must be empty: a release pins exact commits, and a branch
# left behind on the machine is exactly how a closure silently becomes a mixture.
REQUIRED_EMPTY_KEYS=(
    PLEBIAN_OS_BRANCH
    PLEB_BRANCH
    KILIX_BRANCH
    KILIX95_BRANCH
    KILIX_SYSTEM_MONITOR_BRANCH
    KILIX_DESKTOP_SDK_BRANCH
    KILIX_ICEWM_BRANCH
    KILIX_MEDIA_SDK_BRANCH
    KILIX_WAYDROID_BRANCH
)

VOICE_CLOSURE_KEYS=(
    KILIX_VOICE_REF
    KILIX_VOICE_LIB_VERSION
    KILIX_VOICE_LIB_URL
    KILIX_VOICE_LIB_SHA256
    KILIX_VOICE_MODEL_URL
    KILIX_VOICE_MODEL_SHA256
)

declare -A MANIFEST=()
declare -A REQUIREMENTS=()
declare -A CLOSURE=()
declare -A BEFORE=()
declare -A AFTER=()
declare -A COMPONENT_INSTALLED=()
declare -A COMPONENT_TARGET=()
declare -A COMPONENT_DIRECTION=()

TARGET=""
SOURCE_DIR=""
OFFLINE=0
DRY_RUN=0
MODE=select
OS_COMMIT=""
SOURCE_VERSION=""
STAGE=""

cleanup_stage() {
    [ -z "$STAGE" ] || rm -rf -- "$STAGE"
    STAGE=""
}
trap cleanup_stage EXIT

closure_reject() {
    die "release $TARGET closure is not selectable: $*"
}

# ── reading shell configuration ─────────────────────────────────────────────
# /etc/pleb/session.env is read the way pleb-session and the updater read it —
# by sourcing it. Nothing else agrees with its self-guarding
# `if [ -z "${NAME+x}" ]` form, where the first definition of a name wins.
dump_env_file_values() {
    local file="$1"
    env -i HOME="${HOME:-/nonexistent}" PATH="${PATH:-/usr/bin:/bin}" \
        bash --noprofile --norc -c '
set -e
__closure_pre=" $(compgen -v | tr "\n" " ") "
# shellcheck source=/dev/null
. "$1"
for __closure_name in $(compgen -v); do
    case "$__closure_pre" in *" $__closure_name "*) continue ;; esac
    case "$__closure_name" in __closure_pre|__closure_name) continue ;; esac
    printf "%s=%s\0" "$__closure_name" "${!__closure_name}"
done
' bash "$file"
}

read_env_file_into() {
    local -n _values="$1"
    local file="$2" dump="$STAGE/env-dump" kv name
    dump_env_file_values "$file" >"$dump" \
        || die "could not read $file as shell configuration"
    _values=()
    while IFS= read -r -d '' kv; do
        name="${kv%%=*}"
        _values["$name"]="${kv#*=}"
    done <"$dump"
    rm -f -- "$dump"
}

# ── the release manifest ────────────────────────────────────────────────────
# Same parse as build/remaster-iso.sh's load_release_manifest, and the same
# refusals: a malformed line, a bad key, a duplicate, or a placeholder is not a
# closure. Nothing is exported here — the manifest is data, not environment.
parse_release_manifest() {
    local manifest="$1" line key val
    local -A seen=()
    MANIFEST=()
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in ''|\#*) continue ;; esac
        case "$line" in
            *=*) ;;
            *) closure_reject "invalid manifest line: $line" ;;
        esac
        key="${line%%=*}"
        val="${line#*=}"
        val="${val%\"}"; val="${val#\"}"          # tolerate optional quotes
        case "$key" in
            ''|[0-9]*|*[!A-Za-z0-9_]*) closure_reject "invalid manifest key: $key" ;;
        esac
        [ -z "${seen[$key]:-}" ] \
            || closure_reject "duplicate manifest key: $key"
        seen[$key]=1
        [ "$val" != REPLACE_ME ] \
            || closure_reject "$key is still REPLACE_ME — the release was never finished"
        case "${val^^}" in
            REPLACE-ME|TBD|TODO|FIXME|XXX|CHANGEME|CHANGE_ME|PLACEHOLDER|UNSET|NONE|*\<*|*\>*)
                closure_reject "$key is still a placeholder ('$val') — the release was never finished"
                ;;
        esac
        MANIFEST["$key"]="$val"
    done <"$manifest"
}

parse_release_requirements() {
    local requirements="$1" line key val
    local -A seen=()
    REQUIREMENTS=()
    [ -f "$requirements" ] || return 0
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in ''|\#*) continue ;; esac
        case "$line" in
            *=*) ;;
            *) closure_reject "invalid requirements line: $line" ;;
        esac
        key="${line%%=*}"
        val="${line#*=}"
        val="${val%\"}"; val="${val#\"}"
        case "$key" in
            ''|[0-9]*|*[!A-Za-z0-9_]*) closure_reject "invalid requirements key: $key" ;;
        esac
        [ -z "${seen[$key]:-}" ] \
            || closure_reject "duplicate requirements key: $key"
        seen[$key]=1
        [ "$val" != REPLACE_ME ] \
            || closure_reject "requirement $key is still REPLACE_ME"
        case "${val^^}" in
            REPLACE-ME|TBD|TODO|FIXME|XXX|CHANGEME|CHANGE_ME|PLACEHOLDER|UNSET|NONE|*\<*|*\>*)
                closure_reject "requirement $key is still a placeholder ('$val')"
                ;;
        esac
        REQUIREMENTS["$key"]="$val"
    done <"$requirements"
}

validate_release_requirements() {
    local key
    for key in "${!REQUIREMENTS[@]}"; do
        [ -n "${MANIFEST[$key]+x}" ] \
            || closure_reject "manifest must declare required key $key"
        [ "${MANIFEST[$key]}" = "${REQUIREMENTS[$key]}" ] \
            || closure_reject "release requirements demand $key=${REQUIREMENTS[$key]} (manifest has ${MANIFEST[$key]})"
    done
}

require_manifest_format() {
    local key="$1" pattern="$2" description="$3"
    local value="${MANIFEST[$key]:-}"
    [[ "$value" =~ $pattern ]] \
        || closure_reject "$key must be $description (got '$value')"
}

release_requires_f120_roots() {
    [ "$TARGET" = 0.2.1 ]
}

is_f120_root_key() {
    case "$1" in
        KILIX_SYSTEM_MONITOR_*|KILIX_DESKTOP_SDK_*|KILIX_ICEWM_*|\
        KILIX_MEDIA_SDK_*|KILIX_WAYDROID_*) return 0 ;;
        *) return 1 ;;
    esac
}

validate_release_closure() {
    local key value missing=() present=()

    # The precedent is load_release_manifest: a manifest whose version disagrees
    # with its own identifier, or with the VERSION of the commit it came from,
    # is refused before anything else is believed.
    [ "${MANIFEST[PLEBIAN_OS_RELEASE_MODE]:-}" = 1 ] \
        || closure_reject "PLEBIAN_OS_RELEASE_MODE must be 1 (got '${MANIFEST[PLEBIAN_OS_RELEASE_MODE]:-unset}')"
    [ "${MANIFEST[PLEBIAN_OS_VERSION]:-}" = "$TARGET" ] \
        || closure_reject "PLEBIAN_OS_VERSION is '${MANIFEST[PLEBIAN_OS_VERSION]:-unset}', not $TARGET"
    [ "$SOURCE_VERSION" = "$TARGET" ] \
        || closure_reject "the release commit's VERSION reads '$SOURCE_VERSION', not $TARGET"
    validate_release_requirements

    for key in "${REQUIRED_VALUE_KEYS[@]}"; do
        if is_f120_root_key "$key" && ! release_requires_f120_roots; then
            continue
        fi
        [ -n "${MANIFEST[$key]:-}" ] || missing+=("$key")
    done
    [ "${#missing[@]}" -eq 0 ] \
        || closure_reject "incomplete closure — no value for: ${missing[*]}"

    for key in "${REQUIRED_EMPTY_KEYS[@]}"; do
        if is_f120_root_key "$key" && ! release_requires_f120_roots; then
            continue
        fi
        [ -n "${MANIFEST[$key]+x}" ] || present+=("$key")
    done
    [ "${#present[@]}" -eq 0 ] \
        || closure_reject "incomplete closure — these must be declared, even empty: ${present[*]}"
    for key in "${REQUIRED_EMPTY_KEYS[@]}"; do
        if is_f120_root_key "$key" && ! release_requires_f120_roots; then
            continue
        fi
        [ -z "${MANIFEST[$key]}" ] \
            || closure_reject "$key must be empty in a release closure — a release pins exact commits, not branches (got '${MANIFEST[$key]}')"
    done

    for key in PLEB_REF KILIX_REF KILIX95_REF; do
        require_manifest_format "$key" '^[0-9a-f]{40}$' \
            "a full 40-character lowercase commit SHA"
    done
    if release_requires_f120_roots; then
        for key in KILIX_SYSTEM_MONITOR_REF KILIX_DESKTOP_SDK_REF \
            KILIX_ICEWM_REF KILIX_MEDIA_SDK_REF KILIX_WAYDROID_REF; do
            require_manifest_format "$key" '^[0-9a-f]{40}$' \
                "a full 40-character lowercase commit SHA"
        done
        [ "${MANIFEST[KILIX_SYSTEM_MONITOR_REPO]}" = \
            https://github.com/itsmygithubacct/kilix-system-monitor.git ] \
            || closure_reject "KILIX_SYSTEM_MONITOR_REPO must name the canonical release repository"
        [ "${MANIFEST[KILIX_DESKTOP_SDK_REPO]}" = \
            https://github.com/itsmygithubacct/kilix-desktop-sdk.git ] \
            || closure_reject "KILIX_DESKTOP_SDK_REPO must name the canonical release repository"
        [ "${MANIFEST[KILIX_ICEWM_REPO]}" = \
            https://github.com/itsmygithubacct/kilix-icewm.git ] \
            || closure_reject "KILIX_ICEWM_REPO must name the canonical release repository"
        [ "${MANIFEST[KILIX_MEDIA_SDK_REPO]}" = \
            https://github.com/itsmygithubacct/kilix-media-sdk.git ] \
            || closure_reject "KILIX_MEDIA_SDK_REPO must name the canonical release repository"
        [ "${MANIFEST[KILIX_WAYDROID_REPO]}" = \
            https://github.com/itsmygithubacct/kilix-waydroid.git ] \
            || closure_reject "KILIX_WAYDROID_REPO must name the canonical release repository"
    fi
    for key in PLEBIAN_OS_REPO PLEB_REPO KILIX_REPO KILIX95_REPO; do
        require_manifest_format "$key" '^https://[A-Za-z0-9._~:/?#@!$&+,;=%-]+\.git$' \
            "an https git URL"
    done
    require_manifest_format PLEBIAN_OS_APT_SNAPSHOT \
        '^[0-9]{8}T[0-9]{6}Z$' "a snapshot.debian.org timestamp"
    require_manifest_format PLEBIAN_OS_NETINST_URL '^https://' "an https URL"
    require_manifest_format PLEBIAN_OS_NETINST_SHA256 '^[0-9a-f]{64}$' \
        "a 64-character lowercase SHA-256"
    if [ -n "${MANIFEST[PLEBIAN_OS_NETINST_MAX_BYTES]+x}" ]; then
        require_manifest_format PLEBIAN_OS_NETINST_MAX_BYTES \
            '^[1-9][0-9]*$' "a positive byte count"
    fi
    require_manifest_format KILIX_PREBUILT_VERSION \
        '^[0-9][0-9A-Za-z.+-]*$' "an engine version"
    require_manifest_format KILIX_PREBUILT_SHA256 '^[0-9a-f]{64}$' \
        "a 64-character lowercase SHA-256"
    require_manifest_format PLEBIAN_OS_BUILD_KILIX_FORK '^[01]$' "0 or 1"
    require_manifest_format PLEBIAN_OS_KILIX_GO_MIN_VERSION \
        '^[0-9]+\.[0-9]+$' "a Go MAJOR.MINOR floor"
    require_manifest_format PLEBIAN_OS_KILIX_GO_VERSION \
        '^go[0-9]+\.[0-9]+(\.[0-9]+)?$' "an exact goX.Y.Z toolchain version"
    for key in PLEBIAN_OS_KILIX_GO_SHA256_AMD64 PLEBIAN_OS_KILIX_GO_SHA256_ARM64; do
        require_manifest_format "$key" '^[0-9a-f]{64}$' \
            "a 64-character lowercase SHA-256"
    done

    value="${MANIFEST[PLEBIAN_OS_INSTALL_UV]:-}"
    case "$value" in
        0) ;;
        1)
            for key in PLEBIAN_OS_UV_VERSION PLEBIAN_OS_UV_INSTALLER_SHA256; do
                [ -n "${MANIFEST[$key]:-}" ] \
                    || closure_reject "PLEBIAN_OS_INSTALL_UV=1 needs a pinned $key"
            done
            require_manifest_format PLEBIAN_OS_UV_VERSION \
                '^[0-9]+\.[0-9]+\.[0-9]+$' "an exact semantic version"
            require_manifest_format PLEBIAN_OS_UV_INSTALLER_SHA256 \
                '^[0-9a-f]{64}$' "a 64-character lowercase SHA-256"
            if release_requires_f120_roots; then
                [ -n "${MANIFEST[PLEBIAN_OS_UV_INSTALLER_MAX_BYTES]:-}" ] \
                    || closure_reject "PLEBIAN_OS_INSTALL_UV=1 needs a pinned PLEBIAN_OS_UV_INSTALLER_MAX_BYTES"
                require_manifest_format PLEBIAN_OS_UV_INSTALLER_MAX_BYTES \
                    '^[1-9][0-9]*$' "a positive byte count"
            fi
            ;;
        *) closure_reject "PLEBIAN_OS_INSTALL_UV must be 0 or 1 (got '$value')" ;;
    esac

    # The Kilix Voice closure is optional, but "enabled" and "complete" are the
    # only two acceptable states; a half-pinned optional closure is the mixture
    # the upgrade policy forbids.
    value="${MANIFEST[PLEBIAN_OS_INSTALL_VOICE_MODEL]:-0}"
    case "$value" in
        0|1) ;;
        *) closure_reject "PLEBIAN_OS_INSTALL_VOICE_MODEL must be 0 or 1 (got '$value')" ;;
    esac
    if [ "$value" = 1 ]; then
        missing=()
        for key in "${VOICE_CLOSURE_KEYS[@]}"; do
            [ -n "${MANIFEST[$key]:-}" ] || missing+=("$key")
        done
        [ "${#missing[@]}" -eq 0 ] \
            || closure_reject "PLEBIAN_OS_INSTALL_VOICE_MODEL=1 needs pinned values for: ${missing[*]}"
        require_manifest_format KILIX_VOICE_REF '^[0-9a-f]{40}$' \
            "a full 40-character lowercase commit SHA"
        require_manifest_format KILIX_VOICE_LIB_VERSION \
            '^[A-Za-z0-9][A-Za-z0-9._-]*$' "a library version"
        require_manifest_format KILIX_VOICE_LIB_URL '^https://' "an https URL"
        require_manifest_format KILIX_VOICE_MODEL_URL '^https://' "an https URL"
        for key in KILIX_VOICE_LIB_SHA256 KILIX_VOICE_MODEL_SHA256; do
            require_manifest_format "$key" '^[0-9a-f]{64}$' \
                "a 64-character lowercase SHA-256"
        done
    else
        for key in "${VOICE_CLOSURE_KEYS[@]}"; do
            [ -z "${MANIFEST[$key]:-}" ] \
                || closure_reject "$key is pinned but PLEBIAN_OS_INSTALL_VOICE_MODEL is $value"
        done
    fi

    value="${MANIFEST[PLEBIAN_OS_INSTALL_WAYDROID]:-0}"
    if release_requires_f120_roots && [ "$value" != 1 ]; then
        closure_reject "0.2.1 requires PLEBIAN_OS_INSTALL_WAYDROID=1 so the accepted first-use helper is staged"
    fi
    case "$value" in
        0)
            [ -z "${MANIFEST[PLEBIAN_OS_WAYDROID_CLOSURE_SHA256]:-}" ] \
                || closure_reject "Waydroid closure hash is pinned while installation is disabled"
            ;;
        1)
            require_manifest_format PLEBIAN_OS_WAYDROID_CLOSURE_SHA256 \
                '^[0-9a-f]{64}$' "a 64-character lowercase SHA-256"
            ;;
        *) closure_reject "PLEBIAN_OS_INSTALL_WAYDROID must be 0 or 1 (got '$value')" ;;
    esac

    # PLEBIAN_OS_REF names the release tag while the image is built; the
    # installed system persists the commit that tag resolved to, never the
    # movable name.
    value="${MANIFEST[PLEBIAN_OS_REF]}"
    case "$value" in
        "v$TARGET") ;;
        "$OS_COMMIT") ;;
        *) closure_reject "PLEBIAN_OS_REF must be v$TARGET or its exact commit $OS_COMMIT (got '$value')" ;;
    esac
}

# Build the closure exactly as the machine will persist it.
build_selected_closure() {
    local key
    CLOSURE=()
    for key in "${RELEASE_CONTROLLED_KEYS[@]}"; do
        [ -n "${MANIFEST[$key]+x}" ] || continue
        CLOSURE["$key"]="${MANIFEST[$key]}"
    done
    CLOSURE[PLEBIAN_OS_RELEASE]="$TARGET"
    CLOSURE[PLEBIAN_OS_VERSION]="$TARGET"
    CLOSURE[PLEBIAN_OS_REF]="$OS_COMMIT"
    for key in "${REQUIRED_EMPTY_KEYS[@]}"; do
        if is_f120_root_key "$key" && ! release_requires_f120_roots; then
            continue
        fi
        CLOSURE["$key"]=""
    done
    if [ "${MANIFEST[PLEBIAN_OS_INSTALL_VOICE_MODEL]:-0}" != 1 ]; then
        for key in "${VOICE_CLOSURE_KEYS[@]}"; do
            CLOSURE["$key"]=""
        done
        CLOSURE[PLEBIAN_OS_INSTALL_VOICE_MODEL]=0
    fi
    # Optional closures only become part of a release when its manifest names
    # them.  In particular, do not synthesize Waydroid=0 into historical
    # closures: selecting an older published release must not rewrite that
    # release's byte-for-byte operator configuration merely because a newer
    # selector knows about a future optional feature.
}

# ── resolving the immutable closure source ──────────────────────────────────
resolve_closure_source() {
    local remote expected tag_ref tag_object trusted
    git -C "$SOURCE_DIR" rev-parse --git-dir >/dev/null 2>&1 \
        || die "no Plebian-OS object store at $SOURCE_DIR — pass --source DIR"
    expected="${BEFORE[PLEBIAN_OS_REPO]:-${PLEBIAN_OS_REPO:-}}"
    remote="$(git -C "$SOURCE_DIR" config --get remote.origin.url 2>/dev/null || true)"
    if [ -n "$remote" ] && [ -n "$expected" ] && [ "$remote" != "$expected" ] \
        && [ "${PLEBIAN_OS_TRUST_EXISTING_CHECKOUT:-0}" != 1 ]; then
        die "Plebian-OS checkout at $SOURCE_DIR has origin '$remote', expected '$expected' (set PLEBIAN_OS_TRUST_EXISTING_CHECKOUT=1 to override)"
    fi
    if [ "$OFFLINE" = 1 ]; then
        tag_ref="refs/tags/v$TARGET"
        tag_object="$(git -C "$SOURCE_DIR" rev-parse --verify --quiet "$tag_ref")" \
            || die "release tag v$TARGET is not in $SOURCE_DIR and --offline forbids fetching it"
    else
        log "fetching the published release tag v$TARGET into $SOURCE_DIR"
        tag_ref="refs/plebian-os-select/tags/v$TARGET"
        git -C "$SOURCE_DIR" fetch --force --no-tags origin \
            "refs/tags/v$TARGET:$tag_ref" \
            || die "could not fetch release tag v$TARGET from origin — is $TARGET published?"
        tag_object="$(git -C "$SOURCE_DIR" rev-parse --verify "$tag_ref" 2>/dev/null)" \
            || die "release tag v$TARGET did not resolve to an object"
    fi
    trusted="${PLEBIAN_OS_TRUSTED_TAG_OBJECT_SHA:-}"
    if [ -n "$trusted" ]; then
        [[ "$trusted" =~ ^[0-9a-f]{40}$ ]] \
            || die "PLEBIAN_OS_TRUSTED_TAG_OBJECT_SHA must be a full lowercase object SHA"
        [ "$tag_object" = "$trusted" ] \
            || die "release tag v$TARGET object is $tag_object, not trusted object $trusted"
    elif [ "$OFFLINE" = 1 ]; then
        die "--offline requires PLEBIAN_OS_TRUSTED_TAG_OBJECT_SHA; a local tag name is not a trust anchor"
    fi
    OS_COMMIT="$(git -C "$SOURCE_DIR" rev-parse --verify "$tag_ref^{commit}" 2>/dev/null)" \
        || die "release tag v$TARGET did not resolve to a commit"
    # Only the object store is read. HEAD and the working tree stay put, so the
    # updater still finds the clean pinned checkout it insists on.
    SOURCE_VERSION="$(git -C "$SOURCE_DIR" show "$OS_COMMIT:VERSION" 2>/dev/null)" \
        || closure_reject "the release commit $OS_COMMIT has no VERSION file"
    SOURCE_VERSION="${SOURCE_VERSION%$'\n'}"
    git -C "$SOURCE_DIR" show "$OS_COMMIT:releases/$TARGET.env" >"$STAGE/manifest.env" 2>/dev/null \
        || closure_reject "the release commit $OS_COMMIT has no releases/$TARGET.env"
    if git -C "$SOURCE_DIR" cat-file -e \
            "$OS_COMMIT:releases/$TARGET.requirements" 2>/dev/null; then
        git -C "$SOURCE_DIR" show \
            "$OS_COMMIT:releases/$TARGET.requirements" >"$STAGE/requirements"
    elif [ "$TARGET" = 0.1.9 ]; then
        closure_reject "the release commit $OS_COMMIT has no releases/$TARGET.requirements"
    fi
}

# Stage the selector and updater from the exact target commit, not from its
# mutable working tree. Requiring the running selector bytes to match that
# object enforces the documented rule that an upgrade executes the target
# release's own selector. Both hashes are rechecked inside the privileged
# transaction before either installed tool is replaced.
stage_target_tools() {
    local self tool label
    git -C "$SOURCE_DIR" show \
        "$OS_COMMIT:provision/plebian-os-select-closure.sh" \
        >"$STAGE/plebian-os-select-closure" 2>/dev/null \
        || closure_reject "the release commit $OS_COMMIT has no target selector"
    git -C "$SOURCE_DIR" show \
        "$OS_COMMIT:provision/plebian-os-update.sh" \
        >"$STAGE/plebian-os-update" 2>/dev/null \
        || closure_reject "the release commit $OS_COMMIT has no target updater"
    [ -s "$STAGE/plebian-os-select-closure" ] \
        || closure_reject "the release commit $OS_COMMIT has an empty target selector"
    [ -s "$STAGE/plebian-os-update" ] \
        || closure_reject "the release commit $OS_COMMIT has an empty target updater"
    for tool in plebian-os-select-closure plebian-os-update; do
        case "$tool" in
            plebian-os-select-closure) label=selector ;;
            plebian-os-update) label=updater ;;
        esac
        bash -n "$STAGE/$tool" \
            || closure_reject "the release commit $OS_COMMIT has an invalid target $label"
    done
    self="$(readlink -f -- "$0" 2>/dev/null || true)"
    [ -n "$self" ] && [ -f "$self" ] \
        || closure_reject "could not resolve the running target selector"
    cmp -s -- "$self" "$STAGE/plebian-os-select-closure" \
        || closure_reject "the running selector does not match provision/plebian-os-select-closure.sh in target commit $OS_COMMIT"
    chmod 0700 "$STAGE/plebian-os-select-closure" "$STAGE/plebian-os-update"
    sha256sum "$STAGE/plebian-os-select-closure" | awk '{print $1}' \
        >"$STAGE/selector.sha256"
    sha256sum "$STAGE/plebian-os-update" | awk '{print $1}' \
        >"$STAGE/updater.sha256"
}

# ── proving every component's publication and direction ────────────────────
# A server may allow fetch-by-SHA for an object which is not on any advertised
# ref. Fetchability is therefore not publication. Keep a private mirror of the
# advertised heads/tags for each component and require the selected commit to
# be reachable from at least one of them. Offline selection trusts only a
# previously populated mirror; an arbitrary loose object is not enough.
component_public_cache() {
    local label="$1" repo="$2" cache_name="$3"
    local cache_root cache remote
    cache_root="${PLEBIAN_OS_COMPONENT_CACHE_HOME:-${XDG_CACHE_HOME:-$HOME/.cache}/plebian-os/closure-components}"
    case "$cache_root" in /*) ;; *) closure_reject "component cache root must be absolute" ;; esac
    cache="$cache_root/$cache_name.git"
    mkdir -p -- "$cache_root"
    chmod 0700 -- "$cache_root"
    if [ ! -d "$cache" ]; then
        git init --bare --quiet "$cache" \
            || closure_reject "could not create the $label public-ref cache"
        git -C "$cache" remote add origin "$repo" \
            || closure_reject "could not configure the $label public-ref cache"
    fi
    [ ! -L "$cache" ] \
        && [ "$(git -C "$cache" rev-parse --is-bare-repository 2>/dev/null)" = true ] \
        || closure_reject "$label public-ref cache is not a safe bare repository"
    remote="$(git -C "$cache" config --get remote.origin.url 2>/dev/null || true)"
    [ "$remote" = "$repo" ] \
        || closure_reject "$label public-ref cache origin is '$remote', expected '$repo'"
    printf '%s\n' "$cache"
}

verify_component_public_reachability() {
    local label="$1" ref_key="$2" repo="$3" cache_name="$4"
    local target="$5" cache ref tip support="" ref_count=0
    cache="$(component_public_cache "$label" "$repo" "$cache_name")"
    if [ "$OFFLINE" != 1 ]; then
        log "refreshing advertised refs for $label public reachability"
        git -C "$cache" fetch --quiet --prune --force --no-tags origin \
            '+refs/heads/*:refs/plebian-os-public/heads/*' \
            '+refs/tags/*:refs/plebian-os-public/tags/*' \
            || closure_reject "could not fetch advertised refs for $label from $repo"
    fi
    while IFS= read -r ref; do
        [ -n "$ref" ] || continue
        ref_count=$((ref_count + 1))
        tip="$(git -C "$cache" rev-parse --verify "$ref^{commit}" 2>/dev/null || true)"
        [ -n "$tip" ] || continue
        if git -C "$cache" merge-base --is-ancestor "$target" "$tip" 2>/dev/null; then
            support="$ref"
            break
        fi
    done < <(git -C "$cache" for-each-ref --format='%(refname)' \
        refs/plebian-os-public/heads refs/plebian-os-public/tags)
    [ "$ref_count" -gt 0 ] \
        || closure_reject "$label has no cached advertised refs; --offline cannot prove public reachability"
    [ -n "$support" ] \
        || closure_reject "$label target $ref_key=$target is not reachable from any advertised head or tag"
    COMPONENT_PUBLIC_CACHE="$cache"
}

# A release number can rise while one hand-built component pin falls. Fetch the
# exact target commit into the installed checkout's object store, without moving
# HEAD or any branch, then compare the two commits rather than inferring every
# component's direction from PLEBIAN_OS_VERSION.
prepare_component_ancestry() {
    local label="$1" ref_key="$2" repo_key="$3" dir="$4" cache_name="$5"
    local installed="${BEFORE[$ref_key]:-}" target="${CLOSURE[$ref_key]:-}"
    local repo="${CLOSURE[$repo_key]:-}" resolved shallow
    local -a deepen=()

    [[ "$installed" =~ ^[0-9a-f]{40}$ ]] \
        || closure_reject "installed $ref_key must be a full 40-character commit before $label ancestry can be checked (got '$installed')"
    [[ "$target" =~ ^[0-9a-f]{40}$ ]] \
        || closure_reject "selected $ref_key is not a full 40-character commit"
    verify_component_public_reachability \
        "$label" "$ref_key" "$repo" "$cache_name" "$target"
    case "$dir" in
        /*) ;;
        *) closure_reject "$label checkout path must be absolute before ancestry can be checked (got '$dir')" ;;
    esac
    git -C "$dir" rev-parse --git-dir >/dev/null 2>&1 \
        || closure_reject "no $label git checkout at $dir; cannot compare $installed with $target"
    resolved="$(git -C "$dir" rev-parse --verify "$installed^{commit}" 2>/dev/null || true)"
    if [ "$resolved" != "$installed" ] && [ "$OFFLINE" != 1 ]; then
        log "fetching installed $label identity ${installed:0:12} for component ancestry"
        git -C "$dir" -c fetch.recurseSubmodules=false fetch \
            --no-tags --no-recurse-submodules "$repo" "$installed" \
            || closure_reject "installed $label $ref_key=$installed is not publicly fetchable from $repo"
        resolved="$(git -C "$dir" rev-parse --verify 'FETCH_HEAD^{commit}' 2>/dev/null || true)"
    fi
    [ "$resolved" = "$installed" ] \
        || closure_reject "$label checkout at $dir does not contain installed $ref_key=$installed"

    shallow="$(git -C "$dir" rev-parse --is-shallow-repository 2>/dev/null || true)"
    case "$shallow" in true|false) ;; *) closure_reject "could not inspect $label checkout history at $dir" ;; esac
    if [ "$OFFLINE" = 1 ]; then
        [ "$shallow" = false ] \
            || closure_reject "$label checkout at $dir is shallow; --offline cannot prove component ancestry"
        resolved="$(git -C "$dir" rev-parse --verify "$target^{commit}" 2>/dev/null || true)"
        [ "$resolved" = "$target" ] \
            || closure_reject "$label target $ref_key=$target is not in $dir and --offline forbids fetching it"
    else
        [ "$shallow" = false ] || deepen=(--unshallow)
        log "fetching $label target ${target:0:12} for component ancestry"
        git -C "$dir" -c fetch.recurseSubmodules=false fetch \
            --no-tags --no-recurse-submodules "${deepen[@]}" "$repo" "$target" \
            || closure_reject "could not fetch $label target $ref_key=$target from $repo"
        resolved="$(git -C "$dir" rev-parse --verify 'FETCH_HEAD^{commit}' 2>/dev/null || true)"
        [ "$resolved" = "$target" ] \
            || closure_reject "$label fetch resolved to '$resolved', not selected $ref_key=$target"
        [ "$(git -C "$dir" rev-parse --is-shallow-repository 2>/dev/null || true)" = false ] \
            || closure_reject "$label history remains shallow after fetching; component ancestry is not provable"
    fi

    COMPONENT_INSTALLED["$ref_key"]="$installed"
    COMPONENT_TARGET["$ref_key"]="$target"
    if [ "$installed" = "$target" ]; then
        COMPONENT_DIRECTION["$ref_key"]=unchanged
    elif git -C "$dir" merge-base --is-ancestor "$installed" "$target"; then
        COMPONENT_DIRECTION["$ref_key"]=forward
    elif git -C "$dir" merge-base --is-ancestor "$target" "$installed"; then
        COMPONENT_DIRECTION["$ref_key"]=downgrade
    else
        COMPONENT_DIRECTION["$ref_key"]=diverged
    fi
}

prepare_component_target_only() {
    local label="$1" ref_key="$2" repo_key="$3" cache_name="$4"
    local target="${CLOSURE[$ref_key]:-}" repo="${CLOSURE[$repo_key]:-}"
    local installed="${BEFORE[$ref_key]:-}" cache
    [[ "$target" =~ ^[0-9a-f]{40}$ ]] \
        || closure_reject "selected $ref_key is not a full 40-character commit"
    verify_component_public_reachability \
        "$label" "$ref_key" "$repo" "$cache_name" "$target"
    cache="$COMPONENT_PUBLIC_CACHE"
    COMPONENT_INSTALLED["$ref_key"]="$installed"
    COMPONENT_TARGET["$ref_key"]="$target"
    if [ "$installed" = "$target" ]; then
        COMPONENT_DIRECTION["$ref_key"]=unchanged
    elif ! [[ "$installed" =~ ^[0-9a-f]{40}$ ]] \
            || ! git -C "$cache" cat-file -e "$installed^{commit}" 2>/dev/null; then
        COMPONENT_DIRECTION["$ref_key"]=install
    elif git -C "$cache" merge-base --is-ancestor "$installed" "$target"; then
        COMPONENT_DIRECTION["$ref_key"]=forward
    elif git -C "$cache" merge-base --is-ancestor "$target" "$installed"; then
        COMPONENT_DIRECTION["$ref_key"]=downgrade
    else
        COMPONENT_DIRECTION["$ref_key"]=diverged
    fi
}

prepare_component_ancestry_checks() {
    # The existing closure-fixture suite reroots /etc and tests rendering/write
    # behavior without component repositories. The explicit test-only bypass is
    # impossible for the live root; dedicated ancestry fixtures exercise this
    # path without it.
    if [ -n "$CLOSURE_ROOT" ] \
            && [ "${PLEBIAN_OS_SELECT_TEST_SKIP_COMPONENT_ANCESTRY:-0}" = 1 ]; then
        return 0
    fi
    if [ "$SELECTOR_MODE" = standalone ]; then
        prepare_component_target_only \
            "Plebian-OS" PLEBIAN_OS_REF PLEBIAN_OS_REPO plebian-os
    else
        prepare_component_ancestry \
            "Plebian-OS" PLEBIAN_OS_REF PLEBIAN_OS_REPO "$SOURCE_DIR" plebian-os
    fi
    prepare_component_ancestry \
        "Pleb" PLEB_REF PLEB_REPO "${PLEBIAN_OS_PLEB_DIR:-${BEFORE[PLEB_DIR]:-}}" pleb
    prepare_component_ancestry \
        "Kilix" KILIX_REF KILIX_REPO "${PLEBIAN_OS_KILIX_DIR:-${BEFORE[KILIX_DIR]:-}}" kilix
    if git -C "${PLEBIAN_OS_KILIX95_DIR:-${BEFORE[KILIX95_DIR]:-}}" \
            rev-parse --git-dir >/dev/null 2>&1; then
        prepare_component_ancestry \
            "Kilix 95" KILIX95_REF KILIX95_REPO \
            "${PLEBIAN_OS_KILIX95_DIR:-${BEFORE[KILIX95_DIR]:-}}" kilix-95
    elif [ "$SELECTOR_MODE" = standalone ]; then
        prepare_component_target_only \
            "Kilix 95" KILIX95_REF KILIX95_REPO kilix-95
    else
        closure_reject "no Kilix 95 git checkout is available for component comparison"
    fi
    if release_requires_f120_roots; then
        prepare_component_target_only \
            "Kilix System Monitor" KILIX_SYSTEM_MONITOR_REF \
            KILIX_SYSTEM_MONITOR_REPO kilix-system-monitor
        prepare_component_target_only \
            "Kilix Desktop SDK" KILIX_DESKTOP_SDK_REF \
            KILIX_DESKTOP_SDK_REPO kilix-desktop-sdk
        prepare_component_target_only \
            "Kilix IceWM" KILIX_ICEWM_REF KILIX_ICEWM_REPO kilix-icewm
        prepare_component_target_only \
            "Kilix Media SDK" KILIX_MEDIA_SDK_REF \
            KILIX_MEDIA_SDK_REPO kilix-media-sdk
        prepare_component_target_only \
            "Kilix Waydroid" KILIX_WAYDROID_REF \
            KILIX_WAYDROID_REPO kilix-waydroid
    fi
}

# ── rendering /etc/pleb/session.env ─────────────────────────────────────────
# The provisioner writes every managed value in one exact shape:
#     if [ -z "${NAME+x}" ]; then NAME=value; fi
# Only those lines are rewritten, in place, so comments, ordering, export lines,
# and every operator-owned line survive byte for byte.
MANAGED_LINE_RE='^if \[ -z "\$\{([A-Za-z_][A-Za-z0-9_]*)\+x\}" \]; then ([A-Za-z_][A-Za-z0-9_]*)=(.*); fi$'
MANAGED_PREFIX_RE='^if \[ -z "\$\{([A-Za-z_][A-Za-z0-9_]*)\+x\}" \]; then '
SIMPLE_ASSIGN_RE='^(export[[:space:]]+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$'

# A release-controlled key assigned in any other shape is a hand edit this tool
# must not silently overwrite or silently lose to. Name it and stop.
scan_for_unmanaged_release_keys() {
    local src="$1" line stripped key managed lineno=0
    while IFS= read -r line || [ -n "$line" ]; do
        lineno=$((lineno + 1))
        managed=""
        if [[ $line =~ $MANAGED_LINE_RE ]] \
            && [ "${BASH_REMATCH[1]}" = "${BASH_REMATCH[2]}" ]; then
            managed="${BASH_REMATCH[1]}"
        elif [[ $line =~ $MANAGED_PREFIX_RE ]]; then
            die "$src line $lineno defines ${BASH_REMATCH[1]} in a managed form this tool cannot rewrite safely; restore the provisioner's exact line or reprovision before selecting a closure"
        fi
        stripped="${line%%#*}"
        for key in "${RELEASE_CONTROLLED_KEYS[@]}"; do
            [ "$key" != "$managed" ] || continue
            if [[ $stripped =~ (^|[^A-Za-z0-9_])"$key"[=+] ]]; then
                die "$src line $lineno sets the release-controlled key $key outside the managed form; resolve that edit by hand before selecting a closure"
            fi
        done
    done <"$src"
}

split_release_assignment_name() {
    local line="$1" name key
    if [[ $line =~ $MANAGED_LINE_RE ]] \
            && [ "${BASH_REMATCH[1]}" = "${BASH_REMATCH[2]}" ]; then
        name="${BASH_REMATCH[1]}"
    elif [[ $line =~ $SIMPLE_ASSIGN_RE ]]; then
        name="${BASH_REMATCH[2]}"
    else
        return 1
    fi
    for key in "${RELEASE_CONTROLLED_KEYS[@]}"; do
        if [ "$name" = "$key" ]; then
            printf '%s\n' "$name"
            return 0
        fi
    done
    return 1
}

scan_for_ambiguous_split_release_keys() {
    local src="$1" line stripped key lineno=0
    [ -f "$src" ] || return 0
    while IFS= read -r line || [ -n "$line" ]; do
        lineno=$((lineno + 1))
        if split_release_assignment_name "$line" >/dev/null; then
            continue
        fi
        stripped="${line%%#*}"
        for key in "${RELEASE_CONTROLLED_KEYS[@]}"; do
            if [[ $stripped =~ (^|[^A-Za-z0-9_])"$key"[=+] ]]; then
                die "$src line $lineno sets release-controlled key $key in an ambiguous form; use a plain KEY=value assignment or resolve the edit before migration"
            fi
        done
    done <"$src"
}

render_candidate_session_env() {
    local src="$1" dst="$2" line name key
    local -A written=()
    local -a appended=()
    : >"$dst"
    while IFS= read -r line || [ -n "$line" ]; do
        if [[ $line =~ $MANAGED_LINE_RE ]] \
            && [ "${BASH_REMATCH[1]}" = "${BASH_REMATCH[2]}" ] \
            && [ -n "${CLOSURE[${BASH_REMATCH[1]}]+x}" ]; then
            name="${BASH_REMATCH[1]}"
            printf 'if [ -z "${%s+x}" ]; then %s=%q; fi\n' \
                "$name" "$name" "${CLOSURE[$name]}" >>"$dst"
            written["$name"]=1
            continue
        fi
        printf '%s\n' "$line" >>"$dst"
    done <"$src"
    # A target release may introduce a pin the installed release never had.
    for key in "${RELEASE_CONTROLLED_KEYS[@]}"; do
        [ -n "${CLOSURE[$key]+x}" ] || continue
        [ -z "${written[$key]:-}" ] || continue
        appended+=("$key")
    done
    if [ "${#appended[@]}" -gt 0 ]; then
        printf '%s\n' "# Added by plebian-os-select-closure — release $TARGET closure keys." >>"$dst"
        for key in "${appended[@]}"; do
            printf 'if [ -z "${%s+x}" ]; then %s=%q; fi\n' \
                "$key" "$key" "${CLOSURE[$key]}" >>"$dst"
        done
        log "closure adds ${#appended[@]} key(s) this release introduces: ${appended[*]}"
    fi
}

# The rendered file is proven, by sourcing it, to be exactly the old
# configuration with exactly the closure moved — before anything is written.
verify_candidate_closure() {
    local candidate="$1" key
    read_env_file_into AFTER "$candidate"
    for key in "${!CLOSURE[@]}"; do
        [ -n "${AFTER[$key]+x}" ] \
            || die "rendered configuration does not define the closure key $key; nothing was written"
        [ "${AFTER[$key]}" = "${CLOSURE[$key]}" ] \
            || die "rendered configuration would read $key='${AFTER[$key]}' instead of the selected '${CLOSURE[$key]}'; nothing was written"
    done
    for key in "${!BEFORE[@]}"; do
        [ -z "${CLOSURE[$key]+x}" ] || continue
        [ -n "${AFTER[$key]+x}" ] \
            || die "rendered configuration would drop the operator-controlled key $key; nothing was written"
        [ "${AFTER[$key]}" = "${BEFORE[$key]}" ] \
            || die "rendered configuration would change the operator-controlled key $key from '${BEFORE[$key]}' to '${AFTER[$key]}'; nothing was written"
    done
    for key in "${!AFTER[@]}"; do
        [ -z "${BEFORE[$key]+x}" ] || continue
        [ -z "${CLOSURE[$key]+x}" ] || continue
        die "rendered configuration would introduce $key, which is not part of the $TARGET closure; nothing was written"
    done
}

split_layout_active() {
    case "$CLOSURE_LAYOUT" in
        split) return 0 ;;
        legacy) return 1 ;;
    esac
    [ -f "$CLOSURE_ENV" ] && return 0
    [ -n "$TARGET" ] && ! version_is_older "$TARGET" 0.2.1
}

read_installed_configuration() {
    local combined="$STAGE/installed.env"
    : >"$combined"
    if [ -f "$SESSION_ENV" ]; then
        cat -- "$SESSION_ENV" >>"$combined"
        printf '\n' >>"$combined"
    fi
    if split_layout_active && [ -f "$CLOSURE_ENV" ]; then
        cat -- "$CLOSURE_ENV" >>"$combined"
        printf '\n' >>"$combined"
    fi
    read_env_file_into BEFORE "$combined"
}

render_split_session_env() {
    local src="$1" dst="$2" line
    : >"$dst"
    [ -f "$src" ] || return 0
    while IFS= read -r line || [ -n "$line" ]; do
        split_release_assignment_name "$line" >/dev/null && continue
        printf '%s\n' "$line" >>"$dst"
    done <"$src"
}

verify_split_candidate() {
    local combined="$STAGE/candidate-pair.env" key
    : >"$combined"
    cat -- "$STAGE/session.env.new" >>"$combined"
    printf '\n' >>"$combined"
    cat -- "$STAGE/closure.env" >>"$combined"
    read_env_file_into AFTER "$combined"
    for key in "${!CLOSURE[@]}"; do
        [ -n "${AFTER[$key]+x}" ] \
            || die "rendered closure.env does not define $key; nothing was written"
        [ "${AFTER[$key]}" = "${CLOSURE[$key]}" ] \
            || die "rendered closure.env would read $key='${AFTER[$key]}' instead of '${CLOSURE[$key]}'; nothing was written"
    done
    for key in "${!BEFORE[@]}"; do
        [ -z "${CLOSURE[$key]+x}" ] || continue
        [ -n "${AFTER[$key]+x}" ] \
            || die "split configuration would drop operator-controlled key $key; nothing was written"
        [ "${AFTER[$key]}" = "${BEFORE[$key]}" ] \
            || die "split configuration would change operator-controlled key $key; nothing was written"
    done
    for key in "${!AFTER[@]}"; do
        [ -z "${BEFORE[$key]+x}" ] || continue
        [ -z "${CLOSURE[$key]+x}" ] || continue
        die "split configuration would introduce non-closure key $key; nothing was written"
    done
}

# ── announcing the move ─────────────────────────────────────────────────────
version_is_older() {
    [ "$1" != "$2" ] \
        && [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -n 1)" = "$1" ]
}

short_value() {
    local value="$1"
    if [[ "$value" =~ ^[0-9a-f]{40}$ ]]; then
        printf '%s\n' "${value:0:12}"
    elif [ -z "$value" ]; then
        printf '%s\n' "(unset)"
    else
        printf '%s\n' "$value"
    fi
}

# Same discipline as pleb's announce_component_move: name both ends and the
# thing that decided them, and say "DOWNGRADE" out loud when the machine is
# being walked backwards. The coordinated release and every Git component are
# judged independently; a rising release number cannot hide a falling pin.
announce_component_moves() {
    local ref_key label installed target direction pinned_by
    for ref_key in PLEBIAN_OS_REF PLEB_REF KILIX_REF KILIX95_REF \
            KILIX_SYSTEM_MONITOR_REF KILIX_DESKTOP_SDK_REF KILIX_ICEWM_REF \
            KILIX_MEDIA_SDK_REF KILIX_WAYDROID_REF; do
        case "$ref_key" in
            PLEBIAN_OS_REF) label="Plebian-OS" ;;
            PLEB_REF) label="Pleb" ;;
            KILIX_REF) label="Kilix" ;;
            KILIX95_REF) label="Kilix 95" ;;
            KILIX_SYSTEM_MONITOR_REF) label="Kilix System Monitor" ;;
            KILIX_DESKTOP_SDK_REF) label="Kilix Desktop SDK" ;;
            KILIX_ICEWM_REF) label="Kilix IceWM" ;;
            KILIX_MEDIA_SDK_REF) label="Kilix Media SDK" ;;
            KILIX_WAYDROID_REF) label="Kilix Waydroid" ;;
        esac
        installed="${COMPONENT_INSTALLED[$ref_key]:-}"
        target="${COMPONENT_TARGET[$ref_key]:-}"
        direction="${COMPONENT_DIRECTION[$ref_key]:-unchecked}"
        [ "$direction" != unchecked ] || continue
        pinned_by="$ref_key in releases/$TARGET.env@${OS_COMMIT:0:12}"
        case "$direction" in
            unchanged)
                log "component $label: ${installed:0:12} -> ${target:0:12} (unchanged; $pinned_by)"
                ;;
            forward)
                log "component $label: ${installed:0:12} -> ${target:0:12} (forward; $pinned_by)"
                ;;
            downgrade)
                warn "component $label: ${installed:0:12} -> ${target:0:12} (DOWNGRADE; $pinned_by)"
                ;;
            diverged)
                warn "component $label: ${installed:0:12} -> ${target:0:12} (DIVERGED, neither commit is an ancestor; $pinned_by)"
                ;;
            install)
                log "component $label: not installed -> ${target:0:12} (install; $pinned_by)"
                ;;
        esac
    done
}

announce_closure_move() {
    local installed="${BEFORE[PLEBIAN_OS_VERSION]:-}" pinned_by key moved=0 unchanged=0
    pinned_by="releases/$TARGET.env@${OS_COMMIT:0:12}"
    if [ -z "$installed" ]; then
        warn "closure: this machine records no PLEBIAN_OS_VERSION; treating $TARGET as a first selection"
    elif [ "$installed" = "$TARGET" ]; then
        log "closure: $installed -> $TARGET (reselecting the same release, pinned by $pinned_by)"
    elif version_is_older "$TARGET" "$installed"; then
        warn "closure: $installed -> $TARGET (DOWNGRADE, pinned by $pinned_by)"
        warn "closure: the installed release was newer; select $installed again to keep it"
    else
        log "closure: $installed -> $TARGET (pinned by $pinned_by)"
    fi
    announce_component_moves
    for key in "${RELEASE_CONTROLLED_KEYS[@]}"; do
        [ -n "${CLOSURE[$key]+x}" ] || continue
        if [ "${BEFORE[$key]:-}" = "${CLOSURE[$key]}" ] && [ -n "${BEFORE[$key]+x}" ]; then
            unchanged=$((unchanged + 1))
            continue
        fi
        moved=$((moved + 1))
        log "  $key: $(short_value "${BEFORE[$key]:-}") -> $(short_value "${CLOSURE[$key]}")"
    done
    log "closure: $moved release-controlled key(s) move, $unchanged already match"
    for key in "${BUILD_ONLY_RELEASE_KEYS[@]}"; do
        [ -n "${MANIFEST[$key]+x}" ] || continue
        log "  $key: validated, image-build input only (not persisted on an installed machine)"
    done
}

# ── applying it ─────────────────────────────────────────────────────────────
# The target selector, target updater, and session configuration form one
# rollback unit. This lets a target release teach an older installed image both
# its payload list and its end-of-transaction validation before the operator
# invokes the updater. All replacements are prepared beside their destinations
# before any is moved; a later failure restores prior bytes or prior absence.
installed_tool_fingerprint() {
    local path="$1"
    if [ -L "$path" ]; then
        printf 'symlink:%s:%s\n' "$(stat -c '%u:%g:%a' -- "$path")" "$(readlink -- "$path")"
    elif [ -f "$path" ]; then
        printf 'file:%s:%s\n' "$(stat -c '%u:%g:%a' -- "$path")" \
            "$(sha256sum -- "$path" | awk '{print $1}')"
    elif [ -e "$path" ]; then
        printf 'other:%s\n' "$(stat -c '%F:%u:%g:%a' -- "$path")"
    else
        printf '%s\n' absent
    fi
}

apply_selected_closure() {
    local pre_sha post_sha selector_pre selector_post selector_expected
    local updater_pre updater_post updater_expected rc=0 record
    pre_sha="$(sha256sum "$SESSION_ENV" | awk '{print $1}')"
    selector_pre="$(installed_tool_fingerprint "$SELECTOR_DST")"
    updater_pre="$(installed_tool_fingerprint "$UPDATER_DST")"
    sha256sum "$STAGE/session.env.new" | awk '{print $1}' >"$STAGE/candidate.sha256"
    selector_expected="$(cat "$STAGE/selector.sha256")"
    updater_expected="$(cat "$STAGE/updater.sha256")"
    # The record path comes back on stdout into a file this user owns: a root
    # shell writing into the stage would leave something root cannot hand back.
    closure_elevate bash -s -- \
        "$SESSION_ENV" "$SELECTOR_DST" "$UPDATER_DST" "$STAGE" "$RECOVERY_BASE" \
        "${PLEBIAN_OS_SELECT_TEST_FAIL_AFTER:-}" >"$STAGE/record" <<'ROOT_APPLY' || rc=$?
set -euo pipefail
umask 077
env_path="$1"; selector_path="$2"; updater_path="$3"; stage="$4"; base="$5"; fail_after="$6"
case "$env_path" in */etc/pleb/session.env) ;; *) exit 2 ;; esac
case "$selector_path" in */usr/local/bin/plebian-os-select-closure) ;; *) exit 2 ;; esac
case "$updater_path" in */usr/local/bin/plebian-os-update) ;; *) exit 2 ;; esac
[ -d "$stage" ] && [ ! -L "$stage" ] || exit 2
if [ "$EUID" = 0 ]; then
    [ "$(stat -c '%u' -- "$stage")" = "${SUDO_UID:-0}" ] || exit 2
    for dir in / /etc /etc/pleb /var /var/lib /usr /usr/local /usr/local/bin; do
        [ -d "$dir" ] && [ ! -L "$dir" ] && [ "$(stat -c '%u' -- "$dir")" = 0 ] \
            || exit 2
        dir_mode="$(stat -c '%a' -- "$dir")"
        (( (8#$dir_mode & 8#22) == 0 )) || exit 2
    done
fi
[ -f "$env_path" ] && [ ! -L "$env_path" ] || exit 2
[ -d "$(dirname -- "$selector_path")" ] \
    && [ ! -L "$(dirname -- "$selector_path")" ] \
    && [ "$(dirname -- "$selector_path")" = "$(dirname -- "$updater_path")" ] || exit 2
tool_names=(plebian-os-select-closure plebian-os-update)
tool_paths=("$selector_path" "$updater_path")
tool_hash_files=(selector.sha256 updater.sha256)
tool_record_keys=(selector updater)
tool_expected=() tool_tmp=() tool_moved=(0 0)
for i in "${!tool_paths[@]}"; do
    path="${tool_paths[$i]}"
    if [ -e "$path" ] || [ -L "$path" ]; then
        [ -f "$path" ] && [ ! -L "$path" ] || exit 2
        if [ "$EUID" = 0 ]; then
            [ "$(stat -c '%u:%g' -- "$path")" = 0:0 ] || exit 2
            tool_mode="$(stat -c '%a' -- "$path")"
            (( (8#$tool_mode & 8#22) == 0 )) || exit 2
        fi
    fi
done
expected="$(cat -- "$stage/candidate.sha256")"
[[ "$expected" =~ ^[0-9a-f]{64}$ ]] || exit 2
[ -f "$stage/session.env.new" ] && [ ! -L "$stage/session.env.new" ] || exit 2
[ "$(sha256sum -- "$stage/session.env.new" | awk '{print $1}')" = "$expected" ] || exit 3
for i in "${!tool_names[@]}"; do
    tool_expected[$i]="$(cat -- "$stage/${tool_hash_files[$i]}")"
    [[ "${tool_expected[$i]}" =~ ^[0-9a-f]{64}$ ]] || exit 2
    [ -f "$stage/${tool_names[$i]}" ] \
        && [ ! -L "$stage/${tool_names[$i]}" ] || exit 2
    [ "$(sha256sum -- "$stage/${tool_names[$i]}" | awk '{print $1}')" \
        = "${tool_expected[$i]}" ] || exit 3
    bash -n "$stage/${tool_names[$i]}" || exit 3
done
mkdir -p -- "$base"
[ -d "$base" ] && [ ! -L "$base" ] || exit 2
if [ "$EUID" = 0 ]; then
    [ "$(stat -c '%u' -- "$base")" = 0 ] || exit 2
    base_mode="$(stat -c '%a' -- "$base")"
    (( (8#$base_mode & 8#22) == 0 )) || exit 2
fi
record="$(mktemp -d "$base/closure-rollback.$(date -u +%Y%m%dT%H%M%SZ).XXXXXX")"
env_tmp="" env_moved=0
restore_copy() {
    local src="$1" dst="$2" tmp
    tmp="$(mktemp "$(dirname -- "$dst")/.plebian-os-restore.XXXXXX")" || return 1
    rm -f -- "$tmp" || return 1
    cp -a -- "$src" "$tmp" && mv -fT -- "$tmp" "$dst"
}
cleanup() {
    rc=$?
    trap - EXIT
    [ -z "$env_tmp" ] || rm -f -- "$env_tmp"
    for path in "${tool_tmp[@]:-}"; do
        [ -z "$path" ] || rm -f -- "$path"
    done
    if [ "$rc" -ne 0 ]; then
        set +e
        rollback_ok=1
        if [ "$env_moved" = 1 ]; then
            restore_copy "$record/session.env" "$env_path" || rollback_ok=0
        fi
        for ((i=${#tool_paths[@]}-1; i>=0; i--)); do
            [ "${tool_moved[$i]}" = 1 ] || continue
            name="${tool_names[$i]}"
            key="${tool_record_keys[$i]}"
            if [ "$(cat "$record/$key.existed" 2>/dev/null)" = 1 ]; then
                restore_copy "$record/$name" "${tool_paths[$i]}" || rollback_ok=0
            else
                rm -f -- "${tool_paths[$i]}" || rollback_ok=0
            fi
        done
        if [ "$rollback_ok" = 1 ]; then
            rm -rf -- "$record"
        else
            rc=10
        fi
    fi
    exit "$rc"
}
trap cleanup EXIT
cp -a -- "$env_path" "$record/session.env"
for i in "${!tool_paths[@]}"; do
    name="${tool_names[$i]}"
    key="${tool_record_keys[$i]}"
    if [ -e "${tool_paths[$i]}" ]; then
        printf '%s\n' 1 >"$record/$key.existed"
        cp -a -- "${tool_paths[$i]}" "$record/$name"
    else
        printf '%s\n' 0 >"$record/$key.existed"
    fi
done
cp -- "$stage/closure.env" "$record/closure.env"
cp -- "$stage/meta" "$record/meta"
[ "$fail_after" != backup ] || exit 9
env_tmp="$(mktemp "$(dirname -- "$env_path")/.session.env.XXXXXX")"
cat -- "$stage/session.env.new" >"$env_tmp"
[ "$(sha256sum -- "$env_tmp" | awk '{print $1}')" = "$expected" ] || exit 3
chmod 0644 -- "$env_tmp"
for i in "${!tool_paths[@]}"; do
    tool_tmp[$i]="$(mktemp "$(dirname -- "${tool_paths[$i]}")/.${tool_names[$i]}.XXXXXX")"
    install -m 0755 -- "$stage/${tool_names[$i]}" "${tool_tmp[$i]}"
    [ "$(sha256sum -- "${tool_tmp[$i]}" | awk '{print $1}')" \
        = "${tool_expected[$i]}" ] || exit 3
done
[ "$fail_after" != stage ] || exit 9
mv -fT -- "${tool_tmp[0]}" "${tool_paths[0]}"
tool_tmp[0]=""
tool_moved[0]=1
[ "$fail_after" != selector ] || exit 9
mv -fT -- "${tool_tmp[1]}" "${tool_paths[1]}"
tool_tmp[1]=""
tool_moved[1]=1
[ "$fail_after" != updater ] || exit 9
mv -fT -- "$env_tmp" "$env_path"
env_tmp=""
env_moved=1
printf '%s\n' "$record"
ROOT_APPLY
    if [ "$rc" -ne 0 ]; then
        post_sha="$(sha256sum "$SESSION_ENV" 2>/dev/null | awk '{print $1}')" || post_sha=""
        selector_post="$(installed_tool_fingerprint "$SELECTOR_DST")"
        updater_post="$(installed_tool_fingerprint "$UPDATER_DST")"
        if [ "$post_sha" = "$pre_sha" ] \
            && [ "$selector_post" = "$selector_pre" ] \
            && [ "$updater_post" = "$updater_pre" ]; then
            case "$rc" in
                9) die "injected closure write failure; the session and installed tools are unchanged and the previous closure is still selected" ;;
                *) die "could not select the closure (status $rc); the previous session and installed tools are intact" ;;
            esac
        fi
        die "could not select the closure (status $rc) AND the session or installed tools no longer match their previous state; recover from $RECOVERY_BASE before running plebian-os-update"
    fi
    record="$(cat "$STAGE/record")"
    log "previous closure saved for recovery: $record"
    selector_post="$(installed_tool_fingerprint "$SELECTOR_DST")"
    updater_post="$(installed_tool_fingerprint "$UPDATER_DST")"
    case "$selector_pre" in
        absent) log "installed the target selector -> $SELECTOR_DST ($selector_expected)" ;;
        "$selector_post") log "target selector already matched -> $SELECTOR_DST ($selector_expected)" ;;
        *) log "updated the installed target selector -> $SELECTOR_DST ($selector_expected)" ;;
    esac
    case "$updater_pre" in
        absent) log "installed the target updater -> $UPDATER_DST ($updater_expected)" ;;
        "$updater_post") log "target updater already matched -> $UPDATER_DST ($updater_expected)" ;;
        *) log "updated the installed target updater -> $UPDATER_DST ($updater_expected)" ;;
    esac
}

apply_split_closure() {
    local session_pre closure_pre session_post closure_post rc=0 record
    local selector_pre=absent updater_pre=absent selector_post=absent updater_post=absent
    session_pre="$(installed_tool_fingerprint "$SESSION_ENV")"
    closure_pre="$(installed_tool_fingerprint "$CLOSURE_ENV")"
    if [ -n "$SELECTOR_DST" ]; then
        selector_pre="$(installed_tool_fingerprint "$SELECTOR_DST")"
        updater_pre="$(installed_tool_fingerprint "$UPDATER_DST")"
    fi
    sha256sum "$STAGE/session.env.new" | awk '{print $1}' >"$STAGE/session.sha256"
    sha256sum "$STAGE/closure.env" | awk '{print $1}' >"$STAGE/closure.sha256"
    closure_elevate bash -s -- \
        "$SESSION_ENV" "$CLOSURE_ENV" "$SELECTOR_DST" "$UPDATER_DST" \
        "$STAGE" "$RECOVERY_BASE" "$SELECTOR_MODE" \
        "${PLEBIAN_OS_SELECT_TEST_FAIL_AFTER:-}" >"$STAGE/record" <<'ROOT_SPLIT_APPLY' || rc=$?
set -euo pipefail
umask 077
session_path="$1"; closure_path="$2"; selector_path="$3"; updater_path="$4"
stage="$5"; base="$6"; mode="$7"; fail_after="$8"
[ "$session_path" != "$closure_path" ] || exit 2
case "$session_path:$closure_path:$base" in *$'\n'*|*$'\r'*) exit 2 ;; esac
case "$mode" in
    image)
        case "$session_path" in */etc/pleb/session.env) ;; *) exit 2 ;; esac
        case "$closure_path" in */etc/pleb/closure.env) ;; *) exit 2 ;; esac
        case "$selector_path" in */usr/local/bin/plebian-os-select-closure) ;; *) exit 2 ;; esac
        case "$updater_path" in */usr/local/bin/plebian-os-update) ;; *) exit 2 ;; esac
        file_mode=0644
        ;;
    standalone)
        [ -z "$selector_path" ] && [ -z "$updater_path" ] || exit 2
        [ "$(dirname -- "$session_path")" = "$(dirname -- "$closure_path")" ] || exit 2
        file_mode=0600
        ;;
    *) exit 2 ;;
esac
[ -d "$stage" ] && [ ! -L "$stage" ] || exit 2
for path in "$session_path" "$closure_path"; do
    parent="$(dirname -- "$path")"
    mkdir -p -- "$parent"
    [ -d "$parent" ] && [ ! -L "$parent" ] || exit 2
done
mkdir -p -- "$base"
[ -d "$base" ] && [ ! -L "$base" ] || exit 2
if [ "$mode" = standalone ]; then
    chmod 0700 -- "$(dirname -- "$session_path")" "$base"
fi
names=(session.env closure.env)
paths=("$session_path" "$closure_path")
stage_names=(session.env.new closure.env)
hash_names=(session.sha256 closure.sha256)
keys=(session closure)
boundaries=(session closure)
modes=("$file_mode" "$file_mode")
if [ "$mode" = image ]; then
    names+=(plebian-os-select-closure plebian-os-update)
    paths+=("$selector_path" "$updater_path")
    stage_names+=(plebian-os-select-closure plebian-os-update)
    hash_names+=(selector.sha256 updater.sha256)
    keys+=(selector updater)
    boundaries+=(selector updater)
    modes+=(0755 0755)
fi
expected=() tmps=() moved=()
for i in "${!paths[@]}"; do
    path="${paths[$i]}"
    if [ -e "$path" ] || [ -L "$path" ]; then
        [ -f "$path" ] && [ ! -L "$path" ] || exit 2
    fi
    expected[$i]="$(cat -- "$stage/${hash_names[$i]}")"
    [[ "${expected[$i]}" =~ ^[0-9a-f]{64}$ ]] || exit 2
    [ -f "$stage/${stage_names[$i]}" ] && [ ! -L "$stage/${stage_names[$i]}" ] || exit 2
    [ "$(sha256sum "$stage/${stage_names[$i]}" | awk '{print $1}')" = "${expected[$i]}" ] || exit 3
    moved[$i]=0
done
record="$(mktemp -d "$base/closure-rollback.$(date -u +%Y%m%dT%H%M%SZ).XXXXXX")"
restore_copy() {
    local src="$1" dst="$2" tmp
    tmp="$(mktemp "$(dirname -- "$dst")/.plebian-os-restore.XXXXXX")" || return 1
    rm -f -- "$tmp" || return 1
    cp -a -- "$src" "$tmp" && mv -fT -- "$tmp" "$dst"
}
cleanup() {
    rc=$?
    trap - EXIT
    for tmp in "${tmps[@]:-}"; do [ -z "$tmp" ] || rm -f -- "$tmp"; done
    if [ "$rc" -ne 0 ]; then
        set +e
        rollback_ok=1
        for ((i=${#paths[@]}-1; i>=0; i--)); do
            [ "${moved[$i]}" = 1 ] || continue
            key="${keys[$i]}"; path="${paths[$i]}"
            if [ "$(cat "$record/$key.existed" 2>/dev/null)" = 1 ]; then
                restore_copy "$record/${names[$i]}" "$path" || rollback_ok=0
            else
                rm -f -- "$path" || rollback_ok=0
            fi
        done
        if [ "$rollback_ok" = 1 ]; then rm -rf -- "$record"; else rc=10; fi
    fi
    exit "$rc"
}
trap cleanup EXIT
for i in "${!paths[@]}"; do
    path="${paths[$i]}"; key="${keys[$i]}"
    if [ -e "$path" ]; then
        printf '%s\n' 1 >"$record/$key.existed"
        cp -a -- "$path" "$record/${names[$i]}"
    else
        printf '%s\n' 0 >"$record/$key.existed"
    fi
done
cp -- "$stage/meta" "$record/meta"
cp -- "$stage/closure.env" "$record/selected-closure.env"
for file in "$record"/*; do sync -f "$file"; done
sync -f "$record"
sync -f "$base"
[ "$fail_after" != backup ] || exit 9
for i in "${!paths[@]}"; do
    path="${paths[$i]}"
    tmps[$i]="$(mktemp "$(dirname -- "$path")/.${names[$i]}.XXXXXX")"
    install -m "${modes[$i]}" -- "$stage/${stage_names[$i]}" "${tmps[$i]}"
    [ "$(sha256sum "${tmps[$i]}" | awk '{print $1}')" = "${expected[$i]}" ] || exit 3
    sync -f "${tmps[$i]}"
done
[ "$fail_after" != stage ] || exit 9
# Tools first: the target behavior is installed before its target closure is
# made active.  The operator/session file then migrates, and closure.env is the
# commit point because both readers load it last.
order=()
if [ "$mode" = image ]; then order=(2 3 0 1); else order=(0 1); fi
for i in "${order[@]}"; do
    mv -fT -- "${tmps[$i]}" "${paths[$i]}"
    tmps[$i]=""
    moved[$i]=1
    [ "$fail_after" != "${boundaries[$i]}" ] || exit 9
done
sync -f "$(dirname -- "$closure_path")"
printf '%s\n' "$record"
ROOT_SPLIT_APPLY
    if [ "$rc" -ne 0 ]; then
        session_post="$(installed_tool_fingerprint "$SESSION_ENV")"
        closure_post="$(installed_tool_fingerprint "$CLOSURE_ENV")"
        if [ -n "$SELECTOR_DST" ]; then
            selector_post="$(installed_tool_fingerprint "$SELECTOR_DST")"
            updater_post="$(installed_tool_fingerprint "$UPDATER_DST")"
        fi
        if [ "$session_post" = "$session_pre" ] && [ "$closure_post" = "$closure_pre" ] \
                && [ "$selector_post" = "$selector_pre" ] \
                && [ "$updater_post" = "$updater_pre" ]; then
            case "$rc" in
                9) die "injected split-closure failure; session.env, closure.env, and installed tools are unchanged" ;;
                *) die "could not select the split closure (status $rc); previous bytes are intact" ;;
            esac
        fi
        die "could not select the split closure (status $rc) AND rollback was incomplete; recover from $RECOVERY_BASE"
    fi
    record="$(cat "$STAGE/record")"
    log "previous session and closure saved for one-generation recovery: $record"
    if [ "$SELECTOR_MODE" = standalone ]; then
        log "validated the target OS updater but did not deploy it: standalone mode has no OS layer"
    fi
}

write_closure_record() {
    local key
    {
        printf '%s\n' "# Plebian-OS release $TARGET closure selected by plebian-os-select-closure."
        printf '%s\n' "# Release-controlled file; hand editing is unsupported. Use 'pleb update'."
        for key in "${RELEASE_CONTROLLED_KEYS[@]}"; do
            [ -n "${CLOSURE[$key]+x}" ] || continue
            printf '%s=%s\n' "$key" "${CLOSURE[$key]}"
        done
    } >"$STAGE/closure.env"
    {
        printf 'from=%s\n' "${BEFORE[PLEBIAN_OS_VERSION]:-unknown}"
        printf 'to=%s\n' "$TARGET"
        printf 'os_commit=%s\n' "$OS_COMMIT"
        printf 'source=%s\n' "$SOURCE_DIR"
        printf 'at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } >"$STAGE/meta"
}

# ── subcommands ─────────────────────────────────────────────────────────────
show_installed_closure() {
    local key
    read_installed_configuration
    log "release-controlled keys currently selected from $SESSION_ENV and $CLOSURE_ENV:"
    for key in "${RELEASE_CONTROLLED_KEYS[@]}"; do
        if [ -n "${BEFORE[$key]+x}" ]; then
            printf '  %s=%s\n' "$key" "${BEFORE[$key]}"
        else
            printf '  %s (not set)\n' "$key"
        fi
    done
}

rollback_previous_closure() {
    local rc=0 record
    closure_elevate bash -s -- \
        "$SESSION_ENV" "$SELECTOR_DST" "$UPDATER_DST" "$RECOVERY_BASE" \
        "${PLEBIAN_OS_SELECT_TEST_FAIL_AFTER:-}" \
        >"$STAGE/record" <<'ROOT_ROLLBACK' || rc=$?
set -euo pipefail
umask 077
env_path="$1"; selector_path="$2"; updater_path="$3"; base="$4"; fail_after="$5"
case "$env_path" in */etc/pleb/session.env) ;; *) exit 2 ;; esac
case "$selector_path" in */usr/local/bin/plebian-os-select-closure) ;; *) exit 2 ;; esac
case "$updater_path" in */usr/local/bin/plebian-os-update) ;; *) exit 2 ;; esac
[ -d "$base" ] && [ ! -L "$base" ] || exit 4
if [ "$EUID" = 0 ]; then
    for dir in / /etc /etc/pleb /var /var/lib /usr /usr/local /usr/local/bin "$base"; do
        [ -d "$dir" ] && [ ! -L "$dir" ] && [ "$(stat -c '%u' -- "$dir")" = 0 ] \
            || exit 2
        dir_mode="$(stat -c '%a' -- "$dir")"
        (( (8#$dir_mode & 8#22) == 0 )) || exit 2
    done
fi
record=""
for candidate in "$base"/closure-rollback.*; do
    [ -d "$candidate" ] && [ ! -L "$candidate" ] || continue
    [ -f "$candidate/session.env" ] || continue
    if [ -e "$candidate/restored" ]; then continue; fi
    record="$candidate"                    # timestamped names sort oldest first
done
[ -n "$record" ] || exit 4
if [ "$EUID" = 0 ]; then
    [ "$(stat -c '%u' -- "$record")" = 0 ] || exit 2
    record_mode="$(stat -c '%a' -- "$record")"
    (( (8#$record_mode & 8#22) == 0 )) || exit 2
fi
manage_selector=0
selector_before_selection=""
if [ -f "$record/selector.existed" ] && [ ! -L "$record/selector.existed" ]; then
    selector_before_selection="$(cat "$record/selector.existed")"
    case "$selector_before_selection" in
        0) ;;
        1)
            [ -f "$record/plebian-os-select-closure" ] \
                && [ ! -L "$record/plebian-os-select-closure" ] || exit 2
            bash -n "$record/plebian-os-select-closure" || exit 2
            ;;
        *) exit 2 ;;
    esac
    manage_selector=1
fi
manage_updater=0
updater_before_selection=""
if [ -f "$record/updater.existed" ] && [ ! -L "$record/updater.existed" ]; then
    updater_before_selection="$(cat "$record/updater.existed")"
    case "$updater_before_selection" in
        0) ;;
        1)
            [ -f "$record/plebian-os-update" ] \
                && [ ! -L "$record/plebian-os-update" ] || exit 2
            bash -n "$record/plebian-os-update" || exit 2
            ;;
        *) exit 2 ;;
    esac
    manage_updater=1
fi
[ -f "$env_path" ] && [ ! -L "$env_path" ] || exit 2
[ -f "$record/session.env" ] && [ ! -L "$record/session.env" ] || exit 2
if [ -e "$selector_path" ] || [ -L "$selector_path" ]; then
    [ -f "$selector_path" ] && [ ! -L "$selector_path" ] || exit 2
    if [ "$EUID" = 0 ]; then
        [ "$(stat -c '%u:%g' -- "$selector_path")" = 0:0 ] || exit 2
        selector_mode="$(stat -c '%a' -- "$selector_path")"
        (( (8#$selector_mode & 8#22) == 0 )) || exit 2
    fi
fi
if [ -e "$updater_path" ] || [ -L "$updater_path" ]; then
    [ -f "$updater_path" ] && [ ! -L "$updater_path" ] || exit 2
    if [ "$EUID" = 0 ]; then
        [ "$(stat -c '%u:%g' -- "$updater_path")" = 0:0 ] || exit 2
        updater_mode="$(stat -c '%a' -- "$updater_path")"
        (( (8#$updater_mode & 8#22) == 0 )) || exit 2
    fi
fi
env_new="$(mktemp "$(dirname -- "$env_path")/.session.env.plebian-os-restore.XXXXXX")"
env_current="$(mktemp "$(dirname -- "$env_path")/.session.env.plebian-os-current.XXXXXX")"
selector_new="" selector_current="" selector_current_existed=0
updater_new="" updater_current="" updater_current_existed=0
env_moved=0 selector_moved=0 updater_moved=0 restored_marked=0
rm -f -- "$env_new" "$env_current"
cp -a -- "$record/session.env" "$env_new"
cp -a -- "$env_path" "$env_current"
chmod 0644 -- "$env_new"
if [ "$manage_selector" = 1 ]; then
    if [ -e "$selector_path" ]; then
        selector_current_existed=1
        selector_current="$(mktemp "$(dirname -- "$selector_path")/.plebian-os-selector-current.XXXXXX")"
        rm -f -- "$selector_current"
        cp -a -- "$selector_path" "$selector_current"
    fi
    if [ "$selector_before_selection" = 1 ]; then
        selector_new="$(mktemp "$(dirname -- "$selector_path")/.plebian-os-selector-restore.XXXXXX")"
        rm -f -- "$selector_new"
        cp -a -- "$record/plebian-os-select-closure" "$selector_new"
    fi
fi
if [ "$manage_updater" = 1 ]; then
    if [ -e "$updater_path" ]; then
        updater_current_existed=1
        updater_current="$(mktemp "$(dirname -- "$updater_path")/.plebian-os-updater-current.XXXXXX")"
        rm -f -- "$updater_current"
        cp -a -- "$updater_path" "$updater_current"
    fi
    if [ "$updater_before_selection" = 1 ]; then
        updater_new="$(mktemp "$(dirname -- "$updater_path")/.plebian-os-updater-restore.XXXXXX")"
        rm -f -- "$updater_new"
        cp -a -- "$record/plebian-os-update" "$updater_new"
    fi
fi
restore_copy() {
    local src="$1" dst="$2" tmp
    tmp="$(mktemp "$(dirname -- "$dst")/.plebian-os-rollback-undo.XXXXXX")" || return 1
    rm -f -- "$tmp" || return 1
    cp -a -- "$src" "$tmp" && mv -fT -- "$tmp" "$dst"
}

cleanup() {
    rc=$?
    trap - EXIT
    if [ "$rc" -ne 0 ]; then
        set +e
        undo_ok=1
        if [ "$env_moved" = 1 ]; then
            restore_copy "$env_current" "$env_path" || undo_ok=0
        fi
        if [ "$selector_moved" = 1 ]; then
            if [ "$selector_current_existed" = 1 ]; then
                restore_copy "$selector_current" "$selector_path" || undo_ok=0
            else
                rm -f -- "$selector_path" || undo_ok=0
            fi
        fi
        if [ "$updater_moved" = 1 ]; then
            if [ "$updater_current_existed" = 1 ]; then
                restore_copy "$updater_current" "$updater_path" || undo_ok=0
            else
                rm -f -- "$updater_path" || undo_ok=0
            fi
        fi
        if [ "$restored_marked" = 1 ]; then
            rm -f -- "$record/restored" || undo_ok=0
        fi
        [ "$undo_ok" = 1 ] || rc=10
    fi
    [ -z "$env_new" ] || rm -f -- "$env_new"
    [ -z "$env_current" ] || rm -f -- "$env_current"
    [ -z "$selector_new" ] || rm -f -- "$selector_new"
    [ -z "$selector_current" ] || rm -f -- "$selector_current"
    [ -z "$updater_new" ] || rm -f -- "$updater_new"
    [ -z "$updater_current" ] || rm -f -- "$updater_current"
    exit "$rc"
}
trap cleanup EXIT
if [ "$manage_selector" = 1 ]; then
    if [ "$selector_before_selection" = 1 ]; then
        mv -fT -- "$selector_new" "$selector_path"
        selector_new=""
    else
        rm -f -- "$selector_path"
    fi
    selector_moved=1
fi
[ "$fail_after" != rollback-selector ] || exit 9
if [ "$manage_updater" = 1 ]; then
    if [ "$updater_before_selection" = 1 ]; then
        mv -fT -- "$updater_new" "$updater_path"
        updater_new=""
    else
        rm -f -- "$updater_path"
    fi
    updater_moved=1
fi
[ "$fail_after" != rollback-updater ] || exit 9
mv -fT -- "$env_new" "$env_path"
env_new=""
env_moved=1
[ "$fail_after" != rollback-session ] || exit 9
: >"$record/restored"
restored_marked=1
printf '%s\n' "$record"
ROOT_ROLLBACK
    case "$rc" in
        0) ;;
        4) die "no closure to roll back to under $RECOVERY_BASE — this tool has not replaced a closure on this machine" ;;
        *) die "could not restore the previous closure (status $rc); the selected session and installed tools were retained" ;;
    esac
    record="$(cat "$STAGE/record")"
    log "previous closure restored into $SESSION_ENV from $record"
    log "the installed selector and updater were restored to their pre-selection states"
    log "run 'plebian-os-update --restart' to put the machine back on it"
    log "Do not run plebian-os-provision or any other privileged provisioner in between."
}

rollback_split_closure() {
    local rc=0 session_pre closure_pre session_post closure_post record
    local selector_pre=absent updater_pre=absent selector_post=absent updater_post=absent
    session_pre="$(installed_tool_fingerprint "$SESSION_ENV")"
    closure_pre="$(installed_tool_fingerprint "$CLOSURE_ENV")"
    if [ -n "$SELECTOR_DST" ]; then
        selector_pre="$(installed_tool_fingerprint "$SELECTOR_DST")"
        updater_pre="$(installed_tool_fingerprint "$UPDATER_DST")"
    fi
    closure_elevate bash -s -- \
        "$SESSION_ENV" "$CLOSURE_ENV" "$SELECTOR_DST" "$UPDATER_DST" \
        "$RECOVERY_BASE" "$SELECTOR_MODE" \
        "${PLEBIAN_OS_SELECT_TEST_FAIL_AFTER:-}" >"$STAGE/record" <<'ROOT_SPLIT_ROLLBACK' || rc=$?
set -euo pipefail
umask 077
session_path="$1"; closure_path="$2"; selector_path="$3"; updater_path="$4"
base="$5"; mode="$6"; fail_after="$7"
[ -d "$base" ] && [ ! -L "$base" ] || exit 4
record=""
for candidate in "$base"/closure-rollback.*; do
    [ -d "$candidate" ] && [ ! -L "$candidate" ] || continue
    [ -f "$candidate/session.existed" ] && [ -f "$candidate/closure.existed" ] || continue
    [ ! -e "$candidate/restored" ] || continue
    record="$candidate"
done
[ -n "$record" ] || exit 4
names=(session.env closure.env)
paths=("$session_path" "$closure_path")
keys=(session closure)
boundaries=(rollback-session rollback-closure)
if [ "$mode" = image ]; then
    names+=(plebian-os-select-closure plebian-os-update)
    paths+=("$selector_path" "$updater_path")
    keys+=(selector updater)
    boundaries+=(rollback-selector rollback-updater)
fi
current_dir="$(mktemp -d "$base/.closure-rollback-current.XXXXXX")"
current_existed=() moved=()
restore_copy() {
    local src="$1" dst="$2" tmp
    tmp="$(mktemp "$(dirname -- "$dst")/.plebian-os-restore.XXXXXX")" || return 1
    rm -f -- "$tmp" || return 1
    cp -a -- "$src" "$tmp" && mv -fT -- "$tmp" "$dst"
}
cleanup() {
    rc=$?
    trap - EXIT
    if [ "$rc" -ne 0 ]; then
        set +e
        rollback_ok=1
        for ((i=${#paths[@]}-1; i>=0; i--)); do
            [ "${moved[$i]}" = 1 ] || continue
            if [ "${current_existed[$i]}" = 1 ]; then
                restore_copy "$current_dir/${names[$i]}" "${paths[$i]}" || rollback_ok=0
            else
                rm -f -- "${paths[$i]}" || rollback_ok=0
            fi
        done
        [ "$rollback_ok" = 1 ] || rc=10
    fi
    rm -rf -- "$current_dir"
    exit "$rc"
}
trap cleanup EXIT
for i in "${!paths[@]}"; do
    path="${paths[$i]}"; key="${keys[$i]}"
    case "$(cat "$record/$key.existed" 2>/dev/null || true)" in
        0) ;;
        1) [ -f "$record/${names[$i]}" ] && [ ! -L "$record/${names[$i]}" ] || exit 2 ;;
        *) exit 2 ;;
    esac
    if [ -e "$path" ] || [ -L "$path" ]; then
        [ -f "$path" ] && [ ! -L "$path" ] || exit 2
        current_existed[$i]=1
        cp -a -- "$path" "$current_dir/${names[$i]}"
    else
        current_existed[$i]=0
    fi
    moved[$i]=0
done
sync -f "$current_dir"
[ "$fail_after" != rollback-stage ] || exit 9
order=(1 0)
if [ "$mode" = image ]; then order+=(3 2); fi
for i in "${order[@]}"; do
    key="${keys[$i]}"; path="${paths[$i]}"
    if [ "$(cat "$record/$key.existed")" = 1 ]; then
        restore_copy "$record/${names[$i]}" "$path"
    else
        rm -f -- "$path"
    fi
    moved[$i]=1
    [ "$fail_after" != "${boundaries[$i]}" ] || exit 9
done
printf '%s\n' "restored=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$record/restored"
sync -f "$record/restored"
sync -f "$record"
printf '%s\n' "$record"
ROOT_SPLIT_ROLLBACK
    if [ "$rc" -ne 0 ]; then
        session_post="$(installed_tool_fingerprint "$SESSION_ENV")"
        closure_post="$(installed_tool_fingerprint "$CLOSURE_ENV")"
        if [ -n "$SELECTOR_DST" ]; then
            selector_post="$(installed_tool_fingerprint "$SELECTOR_DST")"
            updater_post="$(installed_tool_fingerprint "$UPDATER_DST")"
        fi
        if [ "$session_post" = "$session_pre" ] && [ "$closure_post" = "$closure_pre" ] \
                && [ "$selector_post" = "$selector_pre" ] \
                && [ "$updater_post" = "$updater_pre" ]; then
            case "$rc" in
                4) die "no split closure to roll back to" ;;
                9) die "injected split rollback failure; the selected session, closure, and tools were retained" ;;
                *) die "split closure rollback failed with status $rc; the selected bytes were retained" ;;
            esac
        fi
        die "split closure rollback failed with status $rc AND recovery was incomplete; inspect $RECOVERY_BASE"
    fi
    record="$(cat "$STAGE/record")"
    log "previous split closure restored from $record"
    if [ "$SELECTOR_MODE" = image ]; then
        log "the installed selector and updater were restored to their pre-selection states"
    fi
}

select_closure() {
    read_installed_configuration
    if [ -z "$SOURCE_DIR" ]; then
        SOURCE_DIR="${BEFORE[PLEBIAN_OS_DIR]:-}"
        [ -n "$SOURCE_DIR" ] \
            || die "this machine records no PLEBIAN_OS_DIR — pass --source DIR"
    fi
    resolve_closure_source
    parse_release_manifest "$STAGE/manifest.env"
    parse_release_requirements "$STAGE/requirements"
    validate_release_closure
    build_selected_closure
    prepare_component_ancestry_checks
    stage_target_tools
    log "release $TARGET closure validated from ${SOURCE_DIR}: releases/$TARGET.env @ $OS_COMMIT"
    announce_closure_move
    if split_layout_active; then
        scan_for_ambiguous_split_release_keys "$SESSION_ENV"
        render_split_session_env "$SESSION_ENV" "$STAGE/session.env.new"
        write_closure_record
        select_test_fail_after render
        verify_split_candidate
        select_test_fail_after verify
        if [ "$DRY_RUN" = 1 ]; then
            log "--dry-run: the $TARGET split closure is complete and selectable; nothing was written"
            return 0
        fi
        apply_split_closure
        log "release $TARGET closure selected in $CLOSURE_ENV; operator choices remain in $SESSION_ENV."
    else
        scan_for_unmanaged_release_keys "$SESSION_ENV"
        render_candidate_session_env "$SESSION_ENV" "$STAGE/session.env.new"
        select_test_fail_after render
        verify_candidate_closure "$STAGE/session.env.new"
        select_test_fail_after verify
        if [ "$DRY_RUN" = 1 ]; then
            log "--dry-run: the $TARGET closure is complete and selectable; nothing was written"
            return 0
        fi
        write_closure_record
        apply_selected_closure
        log "release $TARGET closure selected in $SESSION_ENV."
    fi
    if [ "$SELECTOR_MODE" = image ]; then
        log "Next, and only next, run:"
        log "    plebian-os-update --restart"
        log "Do not run plebian-os-provision or any other privileged provisioner between this selection and the updater."
    else
        log "Standalone closure selection complete; the invoking Pleb updater now applies the selected component refs."
    fi
    log "To put the previous closure back, invoke this selector with --rollback."
}

usage() {
    sed -n '2,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//'
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        --show) MODE=show ;;
        --rollback) MODE=rollback ;;
        --dry-run) DRY_RUN=1 ;;
        --offline) OFFLINE=1 ;;
        --source)
            [ "$#" -ge 2 ] || die "--source needs a directory"
            SOURCE_DIR="$2"; shift ;;
        --source=*) SOURCE_DIR="${1#--source=}" ;;
        [0-9]*.[0-9]*.[0-9]*)
            [ -z "$TARGET" ] || die "select one release at a time (already given $TARGET)"
            TARGET="$1" ;;
        *) die "unknown option: $1 (try --help)" ;;
    esac
    shift
done

umask 077
STAGE="$(mktemp -d "${TMPDIR:-/tmp}/plebian-os-closure.XXXXXX")"

if [ ! -f "$SESSION_ENV" ] && [ "$SELECTOR_MODE" != standalone ]; then
    die "no installed session configuration at $SESSION_ENV — this tool runs on a provisioned machine, not in a source checkout"
fi

case "$MODE" in
    show)
        [ -z "$TARGET" ] || die "--show takes no release argument"
        show_installed_closure
        ;;
    rollback)
        [ -z "$TARGET" ] || die "--rollback takes no release argument"
        if split_layout_active; then
            rollback_split_closure
        else
            rollback_previous_closure
        fi
        ;;
    select)
        [ -n "$TARGET" ] \
            || die "name the target release, e.g. plebian-os-select-closure 0.1.8 (try --help)"
        [[ "$TARGET" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
            || die "invalid release identifier: $TARGET"
        select_closure
        ;;
esac
