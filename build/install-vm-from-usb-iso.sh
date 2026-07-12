#!/usr/bin/env bash
# install-vm-from-usb-iso.sh — build a USB-style installer ISO, then install it in VirtualBox.
#
# Defaults are sized for end-to-end acceptance:
#   - 4 GB RAM
#   - 4 vCPUs
#   - 256 MB VRAM with VirtualBox 3D acceleration
#   - 20 GB sparse disk
#
# The ISO is created with build_usb_image.py and no --device, so this never
# writes a USB stick. It then boots that ISO through build_vm_image.py's
# VirtualBox/provisioning waiter.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

NAME="${PLEBIAN_OS_VM_NAME:-plebian-e2e}"
USER_NAME="${PLEBIAN_OS_VM_USER:-pleb}"
PASSWORD="${PLEBIAN_OS_VM_PASSWORD:-}"
ISO="${PLEBIAN_OS_VM_ISO:-$ROOT/plebian-os-${NAME}.iso}"
RAM="${PLEBIAN_OS_VM_RAM_MB:-4096}"
CPUS="${PLEBIAN_OS_VM_CPUS:-4}"
VRAM="${PLEBIAN_OS_VM_VRAM_MB:-256}"
DISK="${PLEBIAN_OS_VM_DISK_GB:-20}"
TIMEOUT="${PLEBIAN_OS_VM_TIMEOUT_MIN:-90}"

if [ -z "$PASSWORD" ]; then
    command -v openssl >/dev/null 2>&1 || {
        echo "install-vm-from-usb-iso: openssl is required to generate a VM password" >&2
        exit 1
    }
    PASSWORD="$(openssl rand -hex 18)"
    echo "==> generated one-time VM password for $USER_NAME: $PASSWORD" >&2
fi

echo "==> building USB-style installer ISO: $ISO"
"$HERE/build_usb_image.py" \
    --yes \
    --name "$NAME" \
    --username "$USER_NAME" \
    --fullname "Plebian User" \
    --password "$PASSWORD" \
    --hostname "$NAME" \
    --session desktop \
    --kiosk \
    --no-sudo-nopasswd \
    --with-ssh \
    --autoboot \
    --unattended-disk \
    --out "$ISO"

echo "==> installing ISO in VirtualBox VM: $NAME"
"$HERE/build_vm_image.py" \
    --yes \
    --iso "$ISO" \
    --name "$NAME" \
    --username "$USER_NAME" \
    --password "$PASSWORD" \
    --hostname "$NAME" \
    --ram "$RAM" \
    --cpus "$CPUS" \
    --vram "$VRAM" \
    --accelerate-3d \
    --disk "$DISK" \
    --session desktop \
    --kiosk \
    --no-sudo-nopasswd \
    --replace \
    --timeout "$TIMEOUT" \
    "$@"
