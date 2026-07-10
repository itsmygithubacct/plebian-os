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
RAM="${PLEBIAN_OS_ACCEPTANCE_RAM:-2048}"
CPUS="${PLEBIAN_OS_ACCEPTANCE_CPUS:-2}"
DISK="${PLEBIAN_OS_ACCEPTANCE_DISK_GB:-20}"
OUT="${PLEBIAN_OS_ACCEPTANCE_ISO:-$ROOT/plebian-os-acceptance.iso}"

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
    "$@"
