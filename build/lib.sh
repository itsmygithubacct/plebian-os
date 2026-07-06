#!/usr/bin/env bash
# lib.sh — shared helpers for the Plebian-OS build scripts.
#   require_xorriso   refuse to run unless xorriso is installed
#   fetch_netinst     download + checksum-verify the current Debian netinst ISO,
#                     echo its path (cached; logs go to stderr)

# Current Debian stable netinst (amd64). "current" tracks the latest point
# release, so we read the exact filename + checksum from the mirror's
# SHA256SUMS rather than hardcoding a version.
: "${PLEBIAN_OS_CDIMAGE:=https://cdimage.debian.org/debian-cd/current/amd64/iso-cd}"
: "${PLEBIAN_OS_CACHE:=${XDG_CACHE_HOME:-$HOME/.cache}/plebian-os}"

_lib_log()  { printf '\033[1;36m[plebian-os]\033[0m %s\n' "$*" >&2; }
_lib_die()  { printf '\033[1;31m[plebian-os] %s\033[0m\n' "$*" >&2; exit 1; }

# Refuse to run without xorriso — the ISO (un)packer both build steps need.
require_xorriso() {
    command -v xorriso >/dev/null 2>&1 || _lib_die \
        "xorriso is required to build the image but is not installed.
   Install it first:  sudo apt-get install xorriso   (Debian/Ubuntu)
                      sudo dnf install xorriso        (Fedora)"
}

# fetch_netinst — ensure a verified Debian netinst ISO is cached; echo its path.
# Set PLEBIAN_OS_NETINST to a local ISO to skip the download entirely.
fetch_netinst() {
    if [ -n "${PLEBIAN_OS_NETINST:-}" ]; then
        [ -f "$PLEBIAN_OS_NETINST" ] || _lib_die "PLEBIAN_OS_NETINST not found: $PLEBIAN_OS_NETINST"
        echo "$PLEBIAN_OS_NETINST"; return 0
    fi
    command -v curl >/dev/null 2>&1 || _lib_die "curl is required to download the netinst ISO"
    command -v sha256sum >/dev/null 2>&1 || _lib_die "sha256sum is required to verify the download"
    mkdir -p "$PLEBIAN_OS_CACHE"

    _lib_log "fetching Debian netinst checksums ($PLEBIAN_OS_CDIMAGE/SHA256SUMS)"
    local sums="$PLEBIAN_OS_CACHE/SHA256SUMS"
    curl -fsSL "$PLEBIAN_OS_CDIMAGE/SHA256SUMS" -o "$sums" \
        || _lib_die "could not fetch SHA256SUMS (no network? mirror down?)"

    # the plain amd64 netinst — not debian-edu / debian-mac
    local sum name
    read -r sum name < <(awk '$2 ~ /^debian-[0-9].*-netinst\.iso$/ {print; exit}' "$sums")
    [ -n "$name" ] && [ -n "$sum" ] || _lib_die "no netinst entry in SHA256SUMS"
    local iso="$PLEBIAN_OS_CACHE/$name"

    if [ -f "$iso" ] && printf '%s  %s\n' "$sum" "$iso" | sha256sum -c --status 2>/dev/null; then
        _lib_log "using cached, verified $name"
    else
        _lib_log "downloading $name (~800 MB; cached in $PLEBIAN_OS_CACHE)"
        curl -fL --progress-bar "$PLEBIAN_OS_CDIMAGE/$name" -o "$iso.part" \
            || _lib_die "download failed"
        printf '%s  %s\n' "$sum" "$iso.part" | sha256sum -c --status 2>/dev/null \
            || { rm -f "$iso.part"; _lib_die "checksum mismatch — refusing (corrupt/tampered download)"; }
        mv "$iso.part" "$iso"
        _lib_log "verified $name (sha256 ok)"
    fi
    echo "$iso"
}
