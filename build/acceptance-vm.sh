#!/usr/bin/env bash
# acceptance-vm.sh — run a real end-to-end Plebian-OS VM acceptance install.
#
# This is intentionally an operator-run script, not a unit test: it creates a
# VirtualBox VM, builds a fresh ISO, boots the unattended installer, waits for
# firstboot provisioning, then verifies exact provenance, the provisioned
# system, failed/successful update paths, and clean catalog builds. It writes a
# checksummed JSON result and exits nonzero if any gate fails. Pass --no-verify
# only for diagnosis; it does not produce a passing acceptance result.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
. "$HERE/lib.sh"

RAM="${PLEBIAN_OS_ACCEPTANCE_RAM:-4096}"
CPUS="${PLEBIAN_OS_ACCEPTANCE_CPUS:-2}"
DISK="${PLEBIAN_OS_ACCEPTANCE_DISK_GB:-20}"
export PLEBIAN_OS_VERIFY_CATALOG_BUILDS=1
export PLEBIAN_OS_VERIFY_UPDATE_ROLLBACK=1
export PLEBIAN_OS_VERIFY_SUCCESSFUL_UPDATE=1

# Acceptance needs SSH, autoboot, and unattended partitioning, which a
# publishable release image correctly forbids. Load the coordinated release
# closure here, then deliberately clear only the release-mode label/gate. The
# resulting test image is non-publishable but still installs the exact source,
# media, snapshot, toolchain, and provider pins under review.
if [ -z "${PLEBIAN_OS_ACCEPTANCE_RELEASE+x}" ]; then
    PLEBIAN_OS_ACCEPTANCE_RELEASE="$(cat "$ROOT/VERSION")"
fi
[[ "$PLEBIAN_OS_ACCEPTANCE_RELEASE" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || {
    echo "acceptance-vm: PLEBIAN_OS_ACCEPTANCE_RELEASE must name a release" >&2
    exit 1
}

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
[ "${PLEBIAN_OS_RELEASE_MODE:-}" = 1 ] || {
    echo "acceptance-vm: manifest must set PLEBIAN_OS_RELEASE_MODE=1" >&2
    exit 1
}
[ "$(cat "$ROOT/VERSION")" = "$PLEBIAN_OS_ACCEPTANCE_RELEASE" ] || {
    echo "acceptance-vm: checkout VERSION does not match the acceptance release" >&2
    exit 1
}

# The instrumented image has to clear the publishable-image gate so it can add
# SSH, autoboot, and unattended partitioning. Prove the release identity before
# doing that: otherwise an arbitrary branch HEAD can silently replace the OS ref
# while the wrapper still announces that it tested the manifest's exact pins.
candidate_commit="$(git -C "$ROOT" rev-parse --verify 'HEAD^{commit}' 2>/dev/null)" || {
    echo "acceptance-vm: could not resolve the checkout HEAD" >&2
    exit 1
}
manifest_os_ref="${PLEBIAN_OS_REF:-}"
[ "$manifest_os_ref" = "v$PLEBIAN_OS_ACCEPTANCE_RELEASE" ] || {
    echo "acceptance-vm: manifest OS ref must be v$PLEBIAN_OS_ACCEPTANCE_RELEASE" >&2
    exit 1
}
[ "$(git -C "$ROOT" cat-file -t "refs/tags/$manifest_os_ref" 2>/dev/null || true)" = tag ] || {
    echo "acceptance-vm: $manifest_os_ref must be a local annotated candidate tag" >&2
    exit 1
}
manifest_commit="$(git -C "$ROOT" rev-parse --verify "${manifest_os_ref}^{commit}" 2>/dev/null)" || {
    echo "acceptance-vm: manifest PLEBIAN_OS_REF=$manifest_os_ref does not resolve locally" >&2
    exit 1
}
[ "$candidate_commit" = "$manifest_commit" ] || {
    echo "acceptance-vm: candidate mismatch: HEAD=$candidate_commit" >&2
    echo "acceptance-vm: $manifest_os_ref resolves to $manifest_commit" >&2
    echo "acceptance-vm: run from the clean candidate-tag checkout" >&2
    exit 1
}
[ -z "$(git -C "$ROOT" status --porcelain --untracked-files=normal)" ] || {
    echo "acceptance-vm: refusing a dirty Plebian-OS candidate checkout" >&2
    exit 1
}

manifest_sha256="$(sha256sum "$manifest" | awk '{print $1}')"
candidate_short="${candidate_commit:0:12}"
NAME="${PLEBIAN_OS_ACCEPTANCE_NAME:-plebian-acceptance-${PLEBIAN_OS_ACCEPTANCE_RELEASE}-${candidate_short}}"
OUT="${PLEBIAN_OS_ACCEPTANCE_ISO:-$PLEBIAN_OS_ARTIFACTS/plebian-os-${PLEBIAN_OS_ACCEPTANCE_RELEASE}-${candidate_short}-acceptance.iso}"
REPORT="${PLEBIAN_OS_ACCEPTANCE_REPORT:-$PLEBIAN_OS_ARTIFACTS/plebian-os-${PLEBIAN_OS_ACCEPTANCE_RELEASE}-${candidate_short}-acceptance.json}"

export PLEBIAN_OS_ACCEPTANCE_RELEASE
export PLEBIAN_OS_ACCEPTANCE_COMMIT="$candidate_commit"
export PLEBIAN_OS_ACCEPTANCE_MANIFEST_SHA256="$manifest_sha256"
PLEBIAN_OS_REF="$candidate_commit"
PLEBIAN_OS_RELEASE=
PLEBIAN_OS_RELEASE_MODE=0
# The publishable image uses the documented offline `pleb` / `plebian` login.
# This derivative enables SSH for its waiter, so exercise the manifest's
# generated-password option instead of exposing that default.
IMAGE_PASSWORD=
RANDOM_PASSWORD=1
export PLEBIAN_OS_REF PLEBIAN_OS_RELEASE PLEBIAN_OS_RELEASE_MODE \
    IMAGE_PASSWORD RANDOM_PASSWORD
echo "acceptance-vm: candidate $PLEBIAN_OS_ACCEPTANCE_RELEASE @ $candidate_commit"
echo "acceptance-vm: manifest sha256 $manifest_sha256"

command -v VBoxManage >/dev/null 2>&1 || {
    echo "acceptance-vm: VBoxManage not found; install VirtualBox first" >&2
    exit 1
}

exec "$HERE/build_vm_image.py" \
    --yes \
    --name "$NAME" \
    --ram "$RAM" \
    --cpus "$CPUS" \
    --disk "$DISK" \
    --out "$OUT" \
    --report "$REPORT" \
    "$@"
