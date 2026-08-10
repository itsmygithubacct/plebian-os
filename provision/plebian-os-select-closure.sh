#!/usr/bin/env bash
# plebian-os-select-closure.sh — validate and atomically select one coordinated
# Plebian-OS release closure on an already-installed machine.
#
# Release images keep exact refs in /etc/pleb/session.env, so plebian-os-update
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
# The release-controlled keys move as one unit or not at all: the whole file is
# rendered, verified by sourcing it, and then swapped in with a single rename.
# Operator-controlled choices — session, provider, storage, kiosk, appearance,
# logging, thermal, audio, network, games, wallpaper, and layout — are copied
# through byte for byte and are proven unchanged before the swap.
#
# Run as the Pleb user; the two bounded writes under /etc and /var/lib elevate
# through sudo.
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

# Release-controlled too, but consumed only while building the image: the
# installed system has no copy to move. They are still validated, because a
# closure which cannot build is not a closure, and then reported as build-only.
BUILD_ONLY_RELEASE_KEYS=(
    PLEBIAN_OS_NETINST_URL
    PLEBIAN_OS_NETINST_SHA256
    PLEBIAN_OS_INSTALL_UV
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
    PLEBIAN_OS_APT_SNAPSHOT
    PLEBIAN_OS_NETINST_URL
    PLEBIAN_OS_NETINST_SHA256
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
        MANIFEST["$key"]="$val"
    done <"$manifest"
}

require_manifest_format() {
    local key="$1" pattern="$2" description="$3"
    local value="${MANIFEST[$key]:-}"
    [[ "$value" =~ $pattern ]] \
        || closure_reject "$key must be $description (got '$value')"
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

    for key in "${REQUIRED_VALUE_KEYS[@]}"; do
        [ -n "${MANIFEST[$key]:-}" ] || missing+=("$key")
    done
    [ "${#missing[@]}" -eq 0 ] \
        || closure_reject "incomplete closure — no value for: ${missing[*]}"

    for key in "${REQUIRED_EMPTY_KEYS[@]}"; do
        [ -n "${MANIFEST[$key]+x}" ] || present+=("$key")
    done
    [ "${#present[@]}" -eq 0 ] \
        || closure_reject "incomplete closure — these must be declared, even empty: ${present[*]}"
    for key in "${REQUIRED_EMPTY_KEYS[@]}"; do
        [ -z "${MANIFEST[$key]}" ] \
            || closure_reject "$key must be empty in a release closure — a release pins exact commits, not branches (got '${MANIFEST[$key]}')"
    done

    for key in PLEB_REF KILIX_REF KILIX95_REF; do
        require_manifest_format "$key" '^[0-9a-f]{40}$' \
            "a full 40-character lowercase commit SHA"
    done
    for key in PLEBIAN_OS_REPO PLEB_REPO KILIX_REPO KILIX95_REPO; do
        require_manifest_format "$key" '^https://[A-Za-z0-9._~:/?#@!$&+,;=%-]+\.git$' \
            "an https git URL"
    done
    require_manifest_format PLEBIAN_OS_APT_SNAPSHOT \
        '^[0-9]{8}T[0-9]{6}Z$' "a snapshot.debian.org timestamp"
    require_manifest_format PLEBIAN_OS_NETINST_URL '^https://' "an https URL"
    require_manifest_format PLEBIAN_OS_NETINST_SHA256 '^[0-9a-f]{64}$' \
        "a 64-character lowercase SHA-256"
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
        CLOSURE["$key"]=""
    done
    if [ "${MANIFEST[PLEBIAN_OS_INSTALL_VOICE_MODEL]:-0}" != 1 ]; then
        for key in "${VOICE_CLOSURE_KEYS[@]}"; do
            CLOSURE["$key"]=""
        done
        CLOSURE[PLEBIAN_OS_INSTALL_VOICE_MODEL]=0
    fi
}

# ── resolving the immutable closure source ──────────────────────────────────
resolve_closure_source() {
    local remote expected
    [ -d "$SOURCE_DIR/.git" ] \
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
# One rename, after a full backup: either every release-controlled key moves or
# none does. Same shape as the updater's root transaction — validate the
# destination under root, snapshot into /var/lib/plebian-os, prepare the new
# object beside its destination, then swap.
apply_selected_closure() {
    local pre_sha post_sha rc=0 record
    pre_sha="$(sha256sum "$SESSION_ENV" | awk '{print $1}')"
    sha256sum "$STAGE/session.env.new" | awk '{print $1}' >"$STAGE/candidate.sha256"
    # The record path comes back on stdout into a file this user owns: a root
    # shell writing into the stage would leave something root cannot hand back.
    closure_elevate bash -s -- \
        "$SESSION_ENV" "$STAGE" "$RECOVERY_BASE" \
        "${PLEBIAN_OS_SELECT_TEST_FAIL_AFTER:-}" >"$STAGE/record" <<'ROOT_APPLY' || rc=$?
set -euo pipefail
umask 077
env_path="$1"; stage="$2"; base="$3"; fail_after="$4"
case "$env_path" in */etc/pleb/session.env) ;; *) exit 2 ;; esac
[ -d "$stage" ] && [ ! -L "$stage" ] || exit 2
if [ "$EUID" = 0 ]; then
    [ "$(stat -c '%u' -- "$stage")" = "${SUDO_UID:-0}" ] || exit 2
    for dir in / /etc /etc/pleb /var /var/lib; do
        [ -d "$dir" ] && [ ! -L "$dir" ] && [ "$(stat -c '%u' -- "$dir")" = 0 ] \
            || exit 2
        dir_mode="$(stat -c '%a' -- "$dir")"
        (( (8#$dir_mode & 8#22) == 0 )) || exit 2
    done
fi
[ -f "$env_path" ] && [ ! -L "$env_path" ] || exit 2
expected="$(cat -- "$stage/candidate.sha256")"
[[ "$expected" =~ ^[0-9a-f]{64}$ ]] || exit 2
[ "$(sha256sum -- "$stage/session.env.new" | awk '{print $1}')" = "$expected" ] || exit 3
mkdir -p -- "$base"
[ -d "$base" ] && [ ! -L "$base" ] || exit 2
record="$(mktemp -d "$base/closure-rollback.$(date -u +%Y%m%dT%H%M%SZ).XXXXXX")"
tmp=""
cleanup() {
    rc=$?
    trap - EXIT
    [ -z "$tmp" ] || rm -f -- "$tmp"
    [ "$rc" -eq 0 ] || rm -rf -- "$record"
    exit "$rc"
}
trap cleanup EXIT
cp -a -- "$env_path" "$record/session.env"
cp -- "$stage/closure.env" "$record/closure.env"
cp -- "$stage/meta" "$record/meta"
[ "$fail_after" != backup ] || exit 9
tmp="$(mktemp "$(dirname -- "$env_path")/.session.env.XXXXXX")"
cat -- "$stage/session.env.new" >"$tmp"
[ "$(sha256sum -- "$tmp" | awk '{print $1}')" = "$expected" ] || exit 3
chmod 0644 -- "$tmp"
[ "$fail_after" != stage ] || exit 9
mv -fT -- "$tmp" "$env_path"
tmp=""
printf '%s\n' "$record"
ROOT_APPLY
    if [ "$rc" -ne 0 ]; then
        post_sha="$(sha256sum "$SESSION_ENV" 2>/dev/null | awk '{print $1}')" || post_sha=""
        if [ "$post_sha" = "$pre_sha" ]; then
            case "$rc" in
                9) die "injected closure write failure; $SESSION_ENV is unchanged and the previous closure is still selected" ;;
                *) die "could not write $SESSION_ENV (status $rc); the previous closure is intact and still selected" ;;
            esac
        fi
        die "could not write $SESSION_ENV (status $rc) AND it no longer matches the previous closure; restore it with 'plebian-os-select-closure --rollback' before running plebian-os-update"
    fi
    record="$(cat "$STAGE/record")"
    log "previous closure saved for recovery: $record"
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
    closure_elevate bash -s -- "$SESSION_ENV" "$RECOVERY_BASE" \
        >"$STAGE/record" <<'ROOT_ROLLBACK' || rc=$?
set -euo pipefail
umask 077
env_path="$1"; base="$2"
case "$env_path" in */etc/pleb/session.env) ;; *) exit 2 ;; esac
[ -d "$base" ] && [ ! -L "$base" ] || exit 4
record=""
for candidate in "$base"/closure-rollback.*; do
    [ -d "$candidate" ] && [ ! -L "$candidate" ] || continue
    [ -f "$candidate/session.env" ] || continue
    if [ -e "$candidate/restored" ]; then continue; fi
    record="$candidate"                    # timestamped names sort oldest first
done
[ -n "$record" ] || exit 4
new="$(dirname -- "$env_path")/.session.env.plebian-os-restore.$$"
cleanup() {
    rc=$?
    trap - EXIT
    [ "$rc" -eq 0 ] || rm -f -- "$new"
    exit "$rc"
}
trap cleanup EXIT
cp -a -- "$record/session.env" "$new"
chmod 0644 -- "$new"
mv -fT -- "$new" "$env_path"
: >"$record/restored"
printf '%s\n' "$record"
ROOT_ROLLBACK
    case "$rc" in
        0) ;;
        4) die "no closure to roll back to under $RECOVERY_BASE — this tool has not replaced a closure on this machine" ;;
        *) die "could not restore the previous closure (status $rc); $SESSION_ENV was not changed" ;;
    esac
    record="$(cat "$STAGE/record")"
    log "previous closure restored into $SESSION_ENV from $record"
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
    validate_release_closure
    build_selected_closure
    prepare_component_ancestry_checks
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
