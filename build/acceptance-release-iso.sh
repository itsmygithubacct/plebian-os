#!/usr/bin/env bash
# acceptance-release-iso.sh — prepare BIOS and EFI installs of the exact,
# publishable Plebian-OS ISO without changing that ISO's bytes or policy.
#
# This is the second release lane. acceptance-vm.sh builds an instrumented,
# unattended derivative so it can verify the guest over SSH. This script takes
# the already-built strict artifact, proves its release identity and dual-boot
# layout, then starts operator-driven VirtualBox installs under both firmware
# implementations. Their reports deliberately say
# "vm-started-no-verification"; the interactive checklist remains a separate
# operator gate.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
. "$HERE/lib.sh"

RELEASE="$(cat "$ROOT/VERSION")"
ISO=""
FIRMWARE=both
REPLACE=0
DRY_RUN=0

usage() {
    cat <<'EOF'
Usage: build/acceptance-release-iso.sh --iso PATH [options]

Options:
  --release X.Y.Z       release recorded in the strict ISO (default: VERSION)
  --firmware MODE       bios, efi, or both (default: both)
  --replace             explicitly replace same-candidate VMs/reports
  --dry-run             validate the ISO and print both VM plans only
  -h, --help            show this help

Resource defaults can be changed with PLEBIAN_OS_ACCEPTANCE_RAM,
PLEBIAN_OS_ACCEPTANCE_CPUS, and PLEBIAN_OS_ACCEPTANCE_DISK_GB.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --iso)
            [ "$#" -ge 2 ] || { echo "acceptance-release-iso: --iso needs a path" >&2; exit 1; }
            ISO="$2"; shift 2 ;;
        --iso=*) ISO="${1#--iso=}"; shift ;;
        --release)
            [ "$#" -ge 2 ] || { echo "acceptance-release-iso: --release needs a version" >&2; exit 1; }
            RELEASE="$2"; shift 2 ;;
        --release=*) RELEASE="${1#--release=}"; shift ;;
        --firmware)
            [ "$#" -ge 2 ] || { echo "acceptance-release-iso: --firmware needs a mode" >&2; exit 1; }
            FIRMWARE="$2"; shift 2 ;;
        --firmware=*) FIRMWARE="${1#--firmware=}"; shift ;;
        --replace) REPLACE=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "acceptance-release-iso: unknown option: $1" >&2; exit 1 ;;
    esac
done

[[ "$RELEASE" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
    || { echo "acceptance-release-iso: invalid release: $RELEASE" >&2; exit 1; }
case "$FIRMWARE" in bios|efi|both) ;; *)
    echo "acceptance-release-iso: firmware must be bios, efi, or both" >&2
    exit 1 ;;
esac
[ -n "$ISO" ] || ISO="$PLEBIAN_OS_ARTIFACTS/plebian-os-$RELEASE-amd64.iso"
resolved_iso="$(readlink -f -- "$ISO" 2>/dev/null || true)"
[ -n "$resolved_iso" ] || {
    echo "acceptance-release-iso: could not resolve ISO path: $ISO" >&2
    exit 1
}
ISO="$resolved_iso"
[ -f "$ISO" ] || { echo "acceptance-release-iso: ISO not found: $ISO" >&2; exit 1; }

for tool in xorriso git sha256sum; do
    command -v "$tool" >/dev/null 2>&1 \
        || { echo "acceptance-release-iso: $tool is required" >&2; exit 1; }
done

mkdir -p "$PLEBIAN_OS_SESSION_HOME"
stage="$(mktemp -d "${PLEBIAN_OS_SESSION_HOME}/strict-iso.XXXXXX")"
cleanup() { rm -rf -- "$stage"; }
trap cleanup EXIT HUP INT TERM
xorriso -osirrox on -indev "$ISO" \
    -extract /plebian-os/build-info.env "$stage/build-info.env" \
    >/dev/null 2>&1 \
    || { echo "acceptance-release-iso: ISO has no readable build-info.env" >&2; exit 1; }

# Treat both files as data. In particular, never source metadata extracted from
# an ISO: a candidate artifact is not trusted until these checks finish.
read_kv_file() {
    local path="$1" destination_name="$2" label="$3"
    local line key value
    local -n destination="$destination_name"
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in ''|\#*) continue ;; *=*) ;; *)
            echo "acceptance-release-iso: invalid $label line: $line" >&2
            exit 1 ;;
        esac
        key="${line%%=*}"
        value="${line#*=}"
        case "$key" in ''|[0-9]*|*[!A-Za-z0-9_]*)
            echo "acceptance-release-iso: invalid $label key: $key" >&2
            exit 1 ;;
        esac
        [ -z "${destination[$key]+x}" ] || {
            echo "acceptance-release-iso: duplicate $label key: $key" >&2
            exit 1
        }
        destination["$key"]="$value"
    done < "$path"
}

# remaster-iso.sh writes build-info values with printf %q. Decode its ordinary
# backslash escapes without eval; control-character ($'...') forms are not
# valid release-closure values and fail closed.
decode_build_value() {
    local remaining="$1" decoded="" character
    [ "$remaining" != "''" ] || { printf '%s' ""; return; }
    case "$remaining" in \$\'*)
        echo "acceptance-release-iso: unsupported quoted build-info value" >&2
        return 1 ;;
    esac
    while [ -n "$remaining" ]; do
        character="${remaining:0:1}"
        if [ "$character" = "\\" ]; then
            [ "${#remaining}" -ge 2 ] || {
                echo "acceptance-release-iso: malformed build-info escape" >&2
                return 1
            }
            decoded+="${remaining:1:1}"
            remaining="${remaining:2}"
        else
            decoded+="$character"
            remaining="${remaining:1}"
        fi
    done
    printf '%s' "$decoded"
}

manifest="$ROOT/releases/$RELEASE.env"
[ -f "$manifest" ] \
    || { echo "acceptance-release-iso: release manifest not found: $manifest" >&2; exit 1; }
declare -A build_info=() release_manifest=()
read_kv_file "$stage/build-info.env" build_info "ISO build-info"
read_kv_file "$manifest" release_manifest "release manifest"

build_value() {
    local key="$1"
    [ -n "${build_info[$key]+x}" ] || return 0
    decode_build_value "${build_info[$key]}"
}

iso_version="$(build_value PLEBIAN_OS_VERSION)"
iso_release="$(build_value PLEBIAN_OS_RELEASE)"
iso_commit="$(build_value PLEBIAN_OS_COMMIT)"
expected_volume_id="PLEBIAN-OS $RELEASE AMD64"
if [ "$iso_version" != "$RELEASE" ] || [ "$iso_release" != "$RELEASE" ]; then
    echo "acceptance-release-iso: ISO release identity does not equal $RELEASE" >&2
    exit 1
fi
[ "$(build_value PLEBIAN_OS_RELEASE_MODE)" = 1 ] \
    || { echo "acceptance-release-iso: ISO is not a strict release-mode artifact" >&2; exit 1; }
[ "$(build_value PLEBIAN_OS_DIRTY)" = 0 ] \
    || { echo "acceptance-release-iso: ISO records a dirty checkout" >&2; exit 1; }
for key in PLEBIAN_OS_SSH_ENABLED PLEBIAN_OS_AUTOBOOT PLEBIAN_OS_UNATTENDED_DISK; do
    [ "$(build_value "$key")" = 0 ] \
        || { echo "acceptance-release-iso: strict ISO records $key=1" >&2; exit 1; }
done
[[ "$iso_commit" =~ ^[0-9a-f]{40}$ ]] \
    || { echo "acceptance-release-iso: invalid ISO commit: $iso_commit" >&2; exit 1; }
[ "${release_manifest[PLEBIAN_OS_REF]-}" = "v$RELEASE" ] \
    || { echo "acceptance-release-iso: manifest OS ref must be v$RELEASE" >&2; exit 1; }
[ "$(git -C "$ROOT" cat-file -t "refs/tags/v$RELEASE" 2>/dev/null || true)" = tag ] \
    || { echo "acceptance-release-iso: v$RELEASE must be an annotated candidate tag" >&2; exit 1; }
tag_commit="$(git -C "$ROOT" rev-parse --verify "v$RELEASE^{commit}" 2>/dev/null)" \
    || { echo "acceptance-release-iso: local candidate tag v$RELEASE is missing" >&2; exit 1; }
[ "$iso_commit" = "$tag_commit" ] \
    || { echo "acceptance-release-iso: ISO commit $iso_commit is not v$RELEASE ($tag_commit)" >&2; exit 1; }

for retired in IMAGE_PASSWORD RANDOM_PASSWORD; do
    [ -z "${release_manifest[$retired]+x}" ] || {
        echo "acceptance-release-iso: manifest must omit retired key $retired" >&2
        exit 1
    }
done
for key in "${!release_manifest[@]}"; do
    [ -n "${build_info[$key]+x}" ] || {
        echo "acceptance-release-iso: ISO build-info does not record manifest key $key" >&2
        exit 1
    }
    actual="$(build_value "$key")" || exit 1
    [ "$actual" = "${release_manifest[$key]}" ] || {
        echo "acceptance-release-iso: ISO $key does not match releases/$RELEASE.env" >&2
        exit 1
    }
done

xorriso -indev "$ISO" -report_el_torito plain 2>/dev/null >"$stage/boot-report"
grep -q 'El Torito boot img.*BIOS' "$stage/boot-report" \
    || { echo "acceptance-release-iso: ISO has no BIOS boot image" >&2; exit 1; }
grep -q 'El Torito boot img.*UEFI' "$stage/boot-report" \
    || { echo "acceptance-release-iso: ISO has no UEFI boot image" >&2; exit 1; }
volume_id="$(xorriso -indev "$ISO" -pvd_info 2>&1 \
    | sed -n "s/^Volume id    : '\(.*\)'$/\1/p" | head -1)"
[ "$volume_id" = "$expected_volume_id" ] \
    || { echo "acceptance-release-iso: unexpected volume ID: $volume_id" >&2; exit 1; }
[ "$(build_value PLEBIAN_OS_ISO_VOLUME_ID)" = "$expected_volume_id" ] \
    || { echo "acceptance-release-iso: build-info volume ID does not match the ISO" >&2; exit 1; }

iso_sha256="$(sha256sum "$ISO" | awk '{print $1}')"
manifest_sha256="$(sha256sum "$manifest" | awk '{print $1}')"
short="${iso_commit:0:12}"
ram="${PLEBIAN_OS_ACCEPTANCE_RAM:-4096}"
cpus="${PLEBIAN_OS_ACCEPTANCE_CPUS:-2}"
disk="${PLEBIAN_OS_ACCEPTANCE_DISK_GB:-20}"
echo "acceptance-release-iso: strict $RELEASE artifact $iso_sha256"
echo "acceptance-release-iso: candidate $iso_commit"

# Populate the report's identity-free release input section without activating
# the builder's release/remaster path; this lane always consumes the ISO as-is.
for key in "${!release_manifest[@]}"; do
    export "$key=${release_manifest[$key]}"
done
export PLEBIAN_OS_ACCEPTANCE_RELEASE="$RELEASE"
export PLEBIAN_OS_ACCEPTANCE_COMMIT="$iso_commit"
export PLEBIAN_OS_ACCEPTANCE_MANIFEST_SHA256="$manifest_sha256"
unset PLEBIAN_OS_RELEASE

firmwares=(bios efi)
[ "$FIRMWARE" = both ] || firmwares=("$FIRMWARE")
for firmware in "${firmwares[@]}"; do
    name="plebian-release-${RELEASE}-${short}-${firmware}"
    report="$PLEBIAN_OS_ARTIFACTS/plebian-os-${RELEASE}-${short}-exact-iso-${firmware}.json"
    args=(
        --yes --iso "$ISO" --interactive-installer --name "$name"
        --firmware "$firmware" --ram "$ram" --cpus "$cpus" --disk "$disk"
        --gui --no-wait --no-verify --report "$report"
    )
    [ "$REPLACE" = 0 ] || args+=(--replace)
    [ "$DRY_RUN" = 0 ] || args+=(--dry-run)
    "$HERE/build_vm_image.py" "${args[@]}"
done

if [ "$DRY_RUN" = 0 ]; then
    echo "acceptance-release-iso: complete the installer in each VM, including target-disk confirmation."
    echo "acceptance-release-iso: neither VM is accepted merely because it was started; finish the strict-media checklist in RELEASING.md."
fi
