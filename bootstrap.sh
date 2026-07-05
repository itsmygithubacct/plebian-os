#!/usr/bin/env bash
# bootstrap.sh — turn an ALREADY-installed, stock Debian into Plebian-OS,
# without reinstalling. This is the "install regular Debian, then pull kilix +
# pleb off GitHub to run" path — handy for converting an existing VM/box or for
# testing the provisioner without building an ISO.
#
#   sudo ./bootstrap.sh [--user NAME] [--kiosk] [--dry-run]
#
# It just runs the same provisioner the ISO's first-boot service runs. On a
# fresh graphical Debian this installs the Pleb session alongside your current
# desktop (reversible: `~/pleb/bin/pleb uninstall`). On a base (no-desktop)
# Debian it pulls the whole graphical stack too.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$HERE/provision/plebian-os-provision.sh" "$@"
