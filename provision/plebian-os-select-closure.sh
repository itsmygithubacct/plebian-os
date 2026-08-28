#!/usr/bin/env bash
# plebian-os-select-closure.sh — validate and atomically select one coordinated
# Plebian-OS release closure on an already-installed machine.
#
# Release images keep exact refs in /etc/pleb/session.env.  Beginning with
# 0.2.1, plebian-os-update resolves the newest published stable release and
# bootstraps this selector from that target's immutable tag before refreshing
# the stack.  This tool remains the atomic boundary that validates and selects
# every release-controlled key together; it is also available directly for an
# exact target, dry-run, inspection, and rollback.
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
# The release-controlled keys move as one unit or not at all: the whole file is
# rendered and verified by sourcing it before the transaction begins. The exact
# selector and updater from the target release are deployed in the same
# transaction. This bootstraps payloads and update behavior introduced after
# the starting release without asking an older installed updater to know the
# future OS-layer file list or final-provenance contract.
# Operator-controlled choices — session, provider, storage, kiosk, appearance,
# logging, thermal, audio, network, games, wallpaper, and layout — are copied
# through byte for byte and are proven unchanged before the swap. Rollback also
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

# Installed locations. The test hook reroots them so the whole selection can be
# exercised end to end without root, exactly as PLEBIAN_OS_APT_ETC_ROOT does for
# the provisioner's apt handling.
CLOSURE_ROOT="${PLEBIAN_OS_CLOSURE_TEST_ROOT:-}"
case "$CLOSURE_ROOT" in
    ''|/) CLOSURE_ROOT="" ;;
    /*) CLOSURE_ROOT="${CLOSURE_ROOT%/}" ;;
    *) die "PLEBIAN_OS_CLOSURE_TEST_ROOT must be an absolute path" ;;
esac
SESSION_ENV="$CLOSURE_ROOT/etc/pleb/session.env"
RECOVERY_BASE="$CLOSURE_ROOT/var/lib/plebian-os"
SELECTOR_DST="$CLOSURE_ROOT/usr/local/bin/plebian-os-select-closure"
UPDATER_DST="$CLOSURE_ROOT/usr/local/bin/plebian-os-update"

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
    local remote expected
    # A bare repository is a source too, and is in fact what Pleb hands us:
    # `_pleb_release_cache_prepare` builds the hop cache with `git init --bare`
    # and then *validates* that it is bare. Requiring a `.git` directory here
    # therefore rejected every real caller, and `pleb update --to`/`--latest`
    # could not complete on any machine -- it died at
    # "no Plebian-OS source checkout" after fetching the target tag, leaving the
    # installed closure untouched. Nothing below needs a working tree: this
    # function reads the object store only, as the comment further down says.
    { [ -d "$SOURCE_DIR/.git" ] \
        || [ "$(git -C "$SOURCE_DIR" rev-parse --is-bare-repository 2>/dev/null)" = true ]; } \
        || die "no Plebian-OS source checkout at $SOURCE_DIR — pass --source DIR"
    expected="${BEFORE[PLEBIAN_OS_REPO]:-}"
    remote="$(git -C "$SOURCE_DIR" config --get remote.origin.url 2>/dev/null || true)"
    if [ -n "$remote" ] && [ -n "$expected" ] && [ "$remote" != "$expected" ] \
        && [ "${PLEBIAN_OS_TRUST_EXISTING_CHECKOUT:-0}" != 1 ]; then
        die "Plebian-OS checkout at $SOURCE_DIR has origin '$remote', expected '$expected' (set PLEBIAN_OS_TRUST_EXISTING_CHECKOUT=1 to override)"
    fi
    if [ "$OFFLINE" = 1 ]; then
        OS_COMMIT="$(git -C "$SOURCE_DIR" rev-parse --verify --quiet "refs/tags/v$TARGET^{commit}")" \
            || die "release tag v$TARGET is not in $SOURCE_DIR and --offline forbids fetching it"
    else
        log "fetching the published release tag v$TARGET into $SOURCE_DIR"
        git -C "$SOURCE_DIR" fetch --force origin "refs/tags/v$TARGET" \
            || die "could not fetch release tag v$TARGET from origin — is $TARGET published?"
        OS_COMMIT="$(git -C "$SOURCE_DIR" rev-parse --verify 'FETCH_HEAD^{commit}' 2>/dev/null)" \
            || die "release tag v$TARGET did not resolve to a commit"
    fi
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

# ── proving every component's direction ────────────────────────────────────
# A release number can rise while one hand-built component pin falls. Fetch the
# exact target commit into the installed checkout's object store, without moving
# HEAD or any branch, then compare the two commits rather than inferring every
# component's direction from PLEBIAN_OS_VERSION.
prepare_component_ancestry() {
    local label="$1" ref_key="$2" repo_key="$3" dir="$4"
    local installed="${BEFORE[$ref_key]:-}" target="${CLOSURE[$ref_key]:-}"
    local repo="${CLOSURE[$repo_key]:-}" resolved shallow
    local -a deepen=()

    [[ "$installed" =~ ^[0-9a-f]{40}$ ]] \
        || closure_reject "installed $ref_key must be a full 40-character commit before $label ancestry can be checked (got '$installed')"
    [[ "$target" =~ ^[0-9a-f]{40}$ ]] \
        || closure_reject "selected $ref_key is not a full 40-character commit"
    case "$dir" in
        /*) ;;
        *) closure_reject "$label checkout path must be absolute before ancestry can be checked (got '$dir')" ;;
    esac
    git -C "$dir" rev-parse --git-dir >/dev/null 2>&1 \
        || closure_reject "no $label git checkout at $dir; cannot compare $installed with $target"
    resolved="$(git -C "$dir" rev-parse --verify "$installed^{commit}" 2>/dev/null || true)"
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

prepare_component_ancestry_checks() {
    # The existing closure-fixture suite reroots /etc and tests rendering/write
    # behavior without component repositories. The explicit test-only bypass is
    # impossible for the live root; dedicated ancestry fixtures exercise this
    # path without it.
    if [ -n "$CLOSURE_ROOT" ] \
            && [ "${PLEBIAN_OS_SELECT_TEST_SKIP_COMPONENT_ANCESTRY:-0}" = 1 ]; then
        return 0
    fi
    prepare_component_ancestry \
        "Plebian-OS" PLEBIAN_OS_REF PLEBIAN_OS_REPO "$SOURCE_DIR"
    prepare_component_ancestry \
        "Pleb" PLEB_REF PLEB_REPO "${BEFORE[PLEB_DIR]:-}"
    prepare_component_ancestry \
        "Kilix" KILIX_REF KILIX_REPO "${BEFORE[KILIX_DIR]:-}"
    prepare_component_ancestry \
        "Kilix 95" KILIX95_REF KILIX95_REPO "${BEFORE[KILIX95_DIR]:-}"
}

# ── rendering /etc/pleb/session.env ─────────────────────────────────────────
# The provisioner writes every managed value in one exact shape:
#     if [ -z "${NAME+x}" ]; then NAME=value; fi
# Only those lines are rewritten, in place, so comments, ordering, export lines,
# and every operator-owned line survive byte for byte.
MANAGED_LINE_RE='^if \[ -z "\$\{([A-Za-z_][A-Za-z0-9_]*)\+x\}" \]; then ([A-Za-z_][A-Za-z0-9_]*)=(.*); fi$'
MANAGED_PREFIX_RE='^if \[ -z "\$\{([A-Za-z_][A-Za-z0-9_]*)\+x\}" \]; then '

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
    for ref_key in PLEBIAN_OS_REF PLEB_REF KILIX_REF KILIX95_REF; do
        case "$ref_key" in
            PLEBIAN_OS_REF) label="Plebian-OS" ;;
            PLEB_REF) label="Pleb" ;;
            KILIX_REF) label="Kilix" ;;
            KILIX95_REF) label="Kilix 95" ;;
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

write_closure_record() {
    local key
    {
        printf '%s\n' "# Plebian-OS release $TARGET closure selected by plebian-os-select-closure."
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
    read_env_file_into BEFORE "$SESSION_ENV"
    log "release-controlled keys currently selected in $SESSION_ENV:"
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

select_closure() {
    read_env_file_into BEFORE "$SESSION_ENV"
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
    scan_for_unmanaged_release_keys "$SESSION_ENV"
    announce_closure_move
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
    log "Next, and only next, run:"
    log "    plebian-os-update --restart"
    log "Do not run plebian-os-provision or any other privileged provisioner between this selection and the updater."
    log "To put the previous closure back before updating, run this tool again with --rollback."
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

[ -f "$SESSION_ENV" ] \
    || die "no installed session configuration at $SESSION_ENV — this tool runs on a provisioned machine, not in a source checkout"

case "$MODE" in
    show)
        [ -z "$TARGET" ] || die "--show takes no release argument"
        show_installed_closure
        ;;
    rollback)
        [ -z "$TARGET" ] || die "--rollback takes no release argument"
        rollback_previous_closure
        ;;
    select)
        [ -n "$TARGET" ] \
            || die "name the target release, e.g. plebian-os-select-closure 0.1.8 (try --help)"
        [[ "$TARGET" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
            || die "invalid release identifier: $TARGET"
        select_closure
        ;;
esac
