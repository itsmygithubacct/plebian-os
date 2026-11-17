#!/usr/bin/env bash
# build-debs.sh OUTDIR
#
# Build the five binary packages from this tree and check them against
# debian/install-map. The build is reproducible for a given SOURCE_DATE_EPOCH:
# the same tree and epoch produce the same package contents. Exit non-zero if
# the build or the check fails.
#
# On Debian 13 with debhelper installed, the packages are built on the host.
# Otherwise they are built in plebian-024-build:spike when that image is
# present, or in debian:trixie, using docker or podman.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ "$#" -ne 1 ] || [ -z "${1:-}" ]; then
    echo "usage: build-debs.sh OUTDIR" >&2
    exit 2
fi
OUTDIR="$(readlink -f "$1")"
mkdir -p "$OUTDIR"

if [[ "${SOURCE_DATE_EPOCH:-}" =~ ^[1-9][0-9]{8,11}$ ]]; then
    epoch="$SOURCE_DATE_EPOCH"
else
    epoch="$(git -C "$HERE" log -1 --format=%ct 2>/dev/null || true)"
fi
[ -n "${epoch:-}" ] || { echo "could not resolve SOURCE_DATE_EPOCH" >&2; exit 1; }
export SOURCE_DATE_EPOCH="$epoch"
export TZ=UTC
export LC_ALL=C

on_trixie_with_debhelper() {
    [ -r /etc/os-release ] || return 1
    # shellcheck disable=SC1091
    . /etc/os-release
    { [ "${VERSION_CODENAME:-}" = trixie ] || [ "${VERSION_ID:-}" = 13 ]; } || return 1
    command -v dpkg-buildpackage >/dev/null 2>&1 || return 1
    dpkg-query -W -f '${Status}' debhelper 2>/dev/null | grep -qx 'install ok installed'
}

build_tree() {
    local src="$1"
    (
        cd "$src"
        dpkg-buildpackage -b -us -uc
    )
}

stage="$(mktemp -d "${TMPDIR:-/tmp}/plebian-os-debs.XXXXXX")"
cleanup_stage() { rm -rf "$stage"; }
trap cleanup_stage EXIT
mkdir -p "$stage/src"
tar -C "$HERE" --exclude .git -cf - . | tar -C "$stage/src" -xf -

if on_trixie_with_debhelper; then
    build_tree "$stage/src"
else
    runtime=""
    if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
        runtime=docker
    elif command -v podman >/dev/null 2>&1 && podman info >/dev/null 2>&1; then
        runtime=podman
    else
        echo "building the packages needs debhelper on Debian 13, or docker/podman" >&2
        exit 1
    fi
    image=""
    if "$runtime" image inspect plebian-024-build:spike >/dev/null 2>&1; then
        image=plebian-024-build:spike
    elif "$runtime" image inspect debian:trixie >/dev/null 2>&1; then
        image=debian:trixie
    else
        echo "no plebian-024-build:spike or debian:trixie image for $runtime" >&2
        exit 1
    fi
    uid="$(id -u)"
    gid="$(id -g)"
    if "$runtime" run --rm "$image" bash -lc 'command -v dh >/dev/null && command -v dpkg-buildpackage >/dev/null'; then
        "$runtime" run --rm --user "$uid:$gid" \
            -e HOME=/tmp/home \
            -e SOURCE_DATE_EPOCH \
            -e TZ=UTC \
            -e LC_ALL=C \
            -v "$stage:/work" -w /work/src \
            "$image" \
            bash -lc 'mkdir -p "$HOME" && dpkg-buildpackage -b -us -uc'
    else
        # debian:trixie has the operating system and not the packaging tools.
        "$runtime" run --rm \
            -e SOURCE_DATE_EPOCH \
            -e TZ=UTC \
            -e LC_ALL=C \
            -e "HOST_UID=$uid" \
            -e "HOST_GID=$gid" \
            -v "$stage:/work" -w /work/src \
            "$image" \
            bash -lc 'apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y debhelper && dpkg-buildpackage -b -us -uc && chown "$HOST_UID:$HOST_GID" /work/*.deb /work/*.changes /work/*.buildinfo'
    fi
fi

shopt -s nullglob
built=("$stage"/*.deb)
shopt -u nullglob
if [ "${#built[@]}" -ne 5 ]; then
    echo "expected 5 packages, found ${#built[@]}" >&2
    exit 1
fi
rm -f "$OUTDIR"/*.deb
cp -a "${built[@]}" "$OUTDIR/"
python3 "$HERE/build/check-debs.py" "$OUTDIR"
