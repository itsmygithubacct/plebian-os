#!/usr/bin/env bash
# fetch-disc-closure.sh [--project] DESTDIR
#
# Put every package named in build/disc-apt-closure.lock (or, with --project,
# build/disc-project-debs.lock) into DESTDIR, each
# checked against the SHA-256 and size the lock records. A file already in the
# cache with the right digest is not downloaded again. Any mismatch, missing
# file or failed download stops the build: nothing unchecked reaches DESTDIR.
#
# PLEBIAN_OS_DISC_CLOSURE_CACHE names the cache directory (default
# ~/.cache/plebian-os/disc-closure). PLEBIAN_OS_DISC_CLOSURE_OFFLINE=1 forbids
# downloads, so a build with a full cache needs no network.
set -euo pipefail
umask 022

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK="${PLEBIAN_OS_DISC_CLOSURE_LOCK:-$HERE/build/disc-apt-closure.lock}"
origin=https://snapshot.debian.org/archive/
if [ "${1:-}" = --project ]; then
    LOCK="${PLEBIAN_OS_DISC_PROJECT_LOCK:-$HERE/build/disc-project-debs.lock}"
    origin=https://itsmygithubacct.github.io/plebian-apt/pool/main/
    shift
fi
if [ "$#" -ne 1 ] || [ -z "${1:-}" ]; then
    echo "usage: fetch-disc-closure.sh [--project] DESTDIR" >&2
    exit 2
fi
mkdir -p "$1"
DEST="$(readlink -f "$1")"
CACHE="${PLEBIAN_OS_DISC_CLOSURE_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/plebian-os/disc-closure}"
mkdir -p "$CACHE"
[ -r "$LOCK" ] || { echo "closure lock not found: $LOCK" >&2; exit 1; }
stage=$(mktemp -d "$DEST/.disc-fetch.XXXXXX")
trap 'rm -rf -- "$stage"' EXIT

matches() {  # matches FILE SHA256 BYTES
    [ -f "$1" ] || return 1
    [ "$(stat -c %s "$1")" = "$3" ] || return 1
    [ "$(sha256sum "$1" | cut -d' ' -f1)" = "$2" ]
}

count=0
while read -r file digest bytes url extra; do
    case "$file" in ''|'#'*) continue ;; esac
    if [ -n "${extra:-}" ] || [ -z "${url:-}" ] \
        || ! [[ "$file" =~ ^[A-Za-z0-9][A-Za-z0-9.+~_-]*\.deb$ ]] \
        || ! [[ "$digest" =~ ^[0-9a-f]{64}$ ]] || ! [[ "$bytes" =~ ^[1-9][0-9]*$ ]] \
        || [[ "$url" != "$origin"* ]]; then
        echo "unreadable closure lock row: $file" >&2
        exit 1
    fi
    cached="$CACHE/$digest.deb"
    if ! matches "$cached" "$digest" "$bytes"; then
        if [ "${PLEBIAN_OS_DISC_CLOSURE_OFFLINE:-0}" = 1 ]; then
            echo "not in the closure cache and downloads are off: $file" >&2
            exit 1
        fi
        part="$cached.part.$$"
        if ! curl -fsSL --retry 3 --max-time 600 -o "$part" "$url"; then
            rm -f "$part"
            echo "download failed: $file" >&2
            exit 1
        fi
        if ! matches "$part" "$digest" "$bytes"; then
            rm -f "$part"
            echo "digest or size mismatch, refusing: $file" >&2
            exit 1
        fi
        mv -f "$part" "$cached"
    fi
    install -m 0644 -- "$cached" "$stage/$file"
    matches "$stage/$file" "$digest" "$bytes" \
        || { echo "copy did not verify: $file" >&2; exit 1; }
    mv -fT -- "$stage/$file" "$DEST/$file"
    count=$((count + 1))
done < "$LOCK"

[ "$count" -gt 0 ] || { echo "closure lock names no package: $LOCK" >&2; exit 1; }
echo "disc closure: $count package(s) verified in $DEST"
