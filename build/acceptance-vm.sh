#!/usr/bin/env bash
# acceptance-vm.sh — run a real end-to-end Plebian-OS VM acceptance install.
#
# This is intentionally an operator-run script, not a unit test: it creates a
# VirtualBox VM, builds a fresh ISO, boots the unattended installer, waits for
# firstboot provisioning, then verifies the provisioned system (provisioned
# marker, pleb xsession, session.env, kilix fork engine, update helper) and
# exits nonzero if provisioning or any acceptance check fails. Pass --no-verify
# to skip the post-provision checks.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

NAME="${PLEBIAN_OS_ACCEPTANCE_NAME:-plebian-acceptance}"
RAM="${PLEBIAN_OS_ACCEPTANCE_RAM:-4096}"
CPUS="${PLEBIAN_OS_ACCEPTANCE_CPUS:-2}"
DISK="${PLEBIAN_OS_ACCEPTANCE_DISK_GB:-20}"
OUT="${PLEBIAN_OS_ACCEPTANCE_ISO:-$ROOT/plebian-os-acceptance.iso}"

# Acceptance needs SSH, autoboot, and unattended partitioning, which a
# publishable release image correctly forbids. Load the coordinated release
# closure here, then deliberately clear only the release-mode label/gate. The
# resulting test image is non-publishable but still installs the exact source,
# media, snapshot, toolchain, and provider pins under review.
if [ -z "${PLEBIAN_OS_ACCEPTANCE_RELEASE+x}" ]; then
    PLEBIAN_OS_ACCEPTANCE_RELEASE="$(cat "$ROOT/VERSION")"
fi
if [ -n "$PLEBIAN_OS_ACCEPTANCE_RELEASE" ]; then
    manifest="$ROOT/releases/$PLEBIAN_OS_ACCEPTANCE_RELEASE.env"
    [ -f "$manifest" ] || {
        echo "acceptance-vm: missing release manifest: $manifest" >&2
        exit 1
    }
    declare -A seen=()
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in ''|\#*) continue ;; *=*) ;; *)
            echo "acceptance-vm: invalid release manifest line: $line" >&2
            exit 1 ;;
        esac
        key="${line%%=*}"; value="${line#*=}"
        case "$key" in ''|[0-9]*|*[!A-Za-z0-9_]*)
            echo "acceptance-vm: invalid release manifest key: $key" >&2
            exit 1 ;;
        esac
        [ -z "${seen[$key]+x}" ] || {
            echo "acceptance-vm: duplicate release manifest key: $key" >&2
            exit 1
        }
        [ "$value" != REPLACE_ME ] || {
            echo "acceptance-vm: unresolved release pin: $key" >&2
            exit 1
        }
        seen[$key]=1
        export "$key=$value"
    done < "$manifest"
    [ "${PLEBIAN_OS_VERSION:-}" = "$PLEBIAN_OS_ACCEPTANCE_RELEASE" ] || {
        echo "acceptance-vm: manifest version mismatch" >&2
        exit 1
    }
    PLEBIAN_OS_REF="$(git -C "$ROOT" rev-parse HEAD)"
    PLEBIAN_OS_RELEASE=
    PLEBIAN_OS_RELEASE_MODE=0
    export PLEBIAN_OS_REF PLEBIAN_OS_RELEASE PLEBIAN_OS_RELEASE_MODE
    echo "acceptance-vm: testing exact $PLEBIAN_OS_ACCEPTANCE_RELEASE pins from $(basename "$manifest")"
fi

command -v VBoxManage >/dev/null 2>&1 || {
    echo "acceptance-vm: VBoxManage not found; install VirtualBox first" >&2
    exit 1
}

exec "$HERE/build_vm_image.py" \
    --yes \
    --replace \
    --name "$NAME" \
    --ram "$RAM" \
    --cpus "$CPUS" \
    --disk "$DISK" \
    --out "$OUT" \
    "$@"
