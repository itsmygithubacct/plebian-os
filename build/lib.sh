#!/usr/bin/env bash
# lib.sh — shared helpers for the Plebian-OS build scripts.
#   require_xorriso   refuse to run unless xorriso is installed
#   fetch_netinst     download + signature/hash-verify the current Debian
#                     netinst ISO, echo its path (cached; logs go to stderr)

# Current Debian stable netinst (amd64). "current" tracks the latest point
# release, so we read the exact filename + checksum from the mirror's signed
# SHA256SUMS rather than hardcoding a version.
: "${PLEBIAN_OS_CDIMAGE:=https://cdimage.debian.org/debian-cd/current/amd64/iso-cd}"
: "${PLEBIAN_OS_CACHE:=${XDG_CACHE_HOME:-$HOME/.cache}/plebian-os}"
: "${PLEBIAN_OS_DEBIAN_CD_KEY_URL:=https://www.debian.org/CD/key-DA87E80D6294BE9B.txt}"

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

    local sums="$PLEBIAN_OS_CACHE/SHA256SUMS"
    local sig="$PLEBIAN_OS_CACHE/SHA256SUMS.sign"

    _download_sums_pair() {
        local mode="${1:-normal}"
        local -a curl_args=(-fsSL)
        if [ "$mode" = refresh ]; then
            curl_args+=(-H "Cache-Control: no-cache" -H "Pragma: no-cache")
        fi
        _lib_log "fetching Debian netinst checksums ($PLEBIAN_OS_CDIMAGE/SHA256SUMS)"
        curl "${curl_args[@]}" "$PLEBIAN_OS_CDIMAGE/SHA256SUMS" -o "$sums.tmp" \
            || _lib_die "could not fetch SHA256SUMS (no network? mirror down?)"
        curl "${curl_args[@]}" "$PLEBIAN_OS_CDIMAGE/SHA256SUMS.sign" -o "$sig.tmp" \
            || _lib_die "could not fetch SHA256SUMS.sign (no network? mirror down?)"
        mv "$sums.tmp" "$sums"
        mv "$sig.tmp" "$sig"
    }

    _fetch_debian_cd_keyring() {
        local key_txt="$PLEBIAN_OS_CACHE/key-DA87E80D6294BE9B.txt"
        local keyring="$PLEBIAN_OS_CACHE/debian-cd-signing-key.gpg"
        command -v gpg >/dev/null 2>&1 || return 1
        _lib_log "fetching Debian CD signing key ($PLEBIAN_OS_DEBIAN_CD_KEY_URL)"
        curl -fsSL "$PLEBIAN_OS_DEBIAN_CD_KEY_URL" -o "$key_txt.tmp" \
            || return 1
        rm -f "$keyring.tmp"
        gpg --batch --yes --dearmor -o "$keyring.tmp" "$key_txt.tmp" >/dev/null 2>&1 \
            || { rm -f "$key_txt.tmp" "$keyring.tmp"; return 1; }
        mv "$key_txt.tmp" "$key_txt"
        mv "$keyring.tmp" "$keyring"
        return 0
    }

    _verify_sums_signature() {
        local kr keyrings=(
            /usr/share/keyrings/debian-archive-keyring.gpg
            /usr/share/keyrings/debian-role-keys.gpg
            /usr/share/keyrings/debian-role-keys.pgp
            "$PLEBIAN_OS_CACHE/debian-cd-signing-key.gpg"
        )
        command -v gpgv >/dev/null 2>&1 || return 2
        for kr in "${keyrings[@]}"; do
            [ -r "$kr" ] || continue
            if gpgv --keyring "$kr" "$sig" "$sums" >/dev/null 2>&1; then
                _lib_log "verified Debian SHA256SUMS signature with $(basename "$kr")"
                return 0
            fi
        done
        return 1
    }

    _download_sums_pair
    if command -v gpgv >/dev/null 2>&1; then
        if ! _verify_sums_signature; then
            _lib_log "Debian SHA256SUMS signature did not verify with installed keyrings; refreshing signing key and checksums"
            _fetch_debian_cd_keyring || true
            _download_sums_pair refresh
            _verify_sums_signature \
                || _lib_die "Debian SHA256SUMS signature verification failed"
        fi
    elif [ "${PLEBIAN_OS_ALLOW_UNSIGNED_SUMS:-0}" = 1 ]; then
        _lib_log "WARNING: skipping Debian SHA256SUMS signature verification by request"
    else
        _lib_die "cannot verify Debian SHA256SUMS signature; install gpgv and debian-archive-keyring, or set PLEBIAN_OS_ALLOW_UNSIGNED_SUMS=1"
    fi

    # the plain amd64 netinst — not debian-edu / debian-mac
    local sum name
    read -r sum name < <(awk '$2 ~ /^debian-[0-9].*-netinst\.iso$/ {print; exit}' "$sums")
    [ -n "$name" ] && [ -n "$sum" ] || _lib_die "no netinst entry in SHA256SUMS"
    local iso="$PLEBIAN_OS_CACHE/$name"

    if [ -f "$iso" ] && printf '%s  %s\n' "$sum" "$iso" | sha256sum -c --status 2>/dev/null; then
        _lib_log "using cached, verified $name"
    else
        _lib_log "downloading $name (~800 MB; cached in $PLEBIAN_OS_CACHE)"
        # Resume across transient drops: -C - continues the .part file, so a
        # mid-transfer close (curl error 18) is picked up where it stopped
        # instead of restarting from zero. --retry handles transient errors
        # within one attempt; the outer loop re-resumes on anything it doesn't
        # cover. A fully-downloaded .part makes -C - report 416 ("range not
        # satisfiable") — accept it when the checksum already matches.
        local attempts="${PLEBIAN_OS_DOWNLOAD_RETRIES:-5}" n=1
        while :; do
            curl -fL --progress-bar --retry 3 --retry-delay 2 \
                --retry-connrefused -C - "$PLEBIAN_OS_CDIMAGE/$name" \
                -o "$iso.part" && break
            printf '%s  %s\n' "$sum" "$iso.part" | sha256sum -c --status 2>/dev/null \
                && break                      # .part is actually complete
            if [ "$n" -ge "$attempts" ]; then
                rm -f "$iso.part"
                _lib_die "download failed after $attempts attempts"
            fi
            _lib_log "download interrupted (attempt $n/$attempts) — resuming in 3s…"
            n=$((n + 1))
            sleep 3
        done
        printf '%s  %s\n' "$sum" "$iso.part" | sha256sum -c --status 2>/dev/null \
            || { rm -f "$iso.part"; _lib_die "checksum mismatch — refusing (corrupt/tampered download)"; }
        mv "$iso.part" "$iso"
        _lib_log "verified $name (sha256 ok)"
    fi
    echo "$iso"
}
