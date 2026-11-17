#!/usr/bin/env bash
# write-disc-apt.sh DEBDIR REPODIR
#
# Turn the .deb files in DEBDIR into a signed apt repository at REPODIR:
# dists/trixie plus pool/, an empty .aptignr beside dists/, and the public
# half of the signing key at plebian-os-installer.gpg.
#
# The signing key is created in a temporary directory for this run, used once
# to sign InRelease, and removed before this script returns, including when
# it fails. It is never read from or written to any other directory.
# Set PLEBIAN_OS_INSTALLER_APT_WRONG_KEY=1 to publish a second key from that
# same temporary directory, so a signature check of this repository fails.
set -euo pipefail
umask 022

if [ "$#" -ne 2 ]; then
    echo "usage: write-disc-apt.sh DEBDIR REPODIR" >&2
    exit 2
fi

DEBDIR=$(readlink -f "$1")
REPO=$(readlink -f "$2")
[ -d "$DEBDIR" ] || { echo "package directory not found: $DEBDIR" >&2; exit 1; }

# Ignore any caller-supplied home. The only key directory is the one created
# below, and the exit trap removes it.
unset GNUPGHOME
GNUPGHOME=$(mktemp -d "${TMPDIR:-/tmp}/plebian-os-installer-gpg.XXXXXX")
export GNUPGHOME
chmod 700 "$GNUPGHOME"

cleanup_signing_key() {
    if [ -n "${GNUPGHOME:-}" ] && [ -d "$GNUPGHOME" ]; then
        gpgconf --homedir "$GNUPGHOME" --kill all >/dev/null 2>&1 || true
        rm -rf "$GNUPGHOME"
    fi
    GNUPGHOME=
}
trap cleanup_signing_key EXIT

shopt -s nullglob
debs=("$DEBDIR"/*.deb)
shopt -u nullglob
[ "${#debs[@]}" -gt 0 ] || { echo "no packages in $DEBDIR" >&2; exit 1; }

rm -rf "$REPO"
mkdir -p "$REPO/pool/main" "$REPO/dists/trixie/main/binary-amd64"
: > "$REPO/.aptignr"

for deb in "${debs[@]}"; do
    name=$(basename "$deb")
    pkg=${name%%_*}
    letter=${pkg:0:1}
    dest="$REPO/pool/main/$letter/$pkg"
    mkdir -p "$dest"
    cp -a "$deb" "$dest/$name"
done

(
    cd "$REPO"
    apt-ftparchive packages pool > dists/trixie/main/binary-amd64/Packages
    gzip -9nc dists/trixie/main/binary-amd64/Packages > dists/trixie/main/binary-amd64/Packages.gz
    apt-ftparchive \
        -o APT::FTPArchive::Release::Origin=Plebian-OS \
        -o APT::FTPArchive::Release::Label="Plebian-OS installer" \
        -o APT::FTPArchive::Release::Suite=trixie \
        -o APT::FTPArchive::Release::Codename=trixie \
        -o APT::FTPArchive::Release::Architectures=amd64 \
        -o APT::FTPArchive::Release::Components=main \
        release dists/trixie > dists/trixie/Release
)

sign_uid='Plebian-OS per-image installer key'
wrong_uid='Plebian-OS per-image installer key wrong'
gpg --homedir "$GNUPGHOME" --batch --pinentry-mode loopback --passphrase '' \
    --quick-generate-key "$sign_uid" ed25519 sign 0
sign_fpr=$(gpg --homedir "$GNUPGHOME" --batch --list-keys --with-colons \
    | awk -F: '/^fpr:/{print $10; exit}')
[ -n "$sign_fpr" ] || { echo "signing key has no fingerprint" >&2; exit 1; }

publish_fpr=$sign_fpr
if [ "${PLEBIAN_OS_INSTALLER_APT_WRONG_KEY:-0}" = 1 ]; then
    gpg --homedir "$GNUPGHOME" --batch --pinentry-mode loopback --passphrase '' \
        --quick-generate-key "$wrong_uid" ed25519 sign 0
    publish_fpr=$(gpg --homedir "$GNUPGHOME" --batch --list-keys --with-colons \
        | awk -F: -v skip="$sign_fpr" '$1 == "fpr" && $10 != skip { print $10; exit }')
    [ -n "$publish_fpr" ] && [ "$publish_fpr" != "$sign_fpr" ] \
        || { echo "wrong-key control did not create a second key" >&2; exit 1; }
fi

gpg --homedir "$GNUPGHOME" --batch --pinentry-mode loopback --passphrase '' \
    --yes -u "$sign_fpr" --clearsign -o "$REPO/dists/trixie/InRelease" \
    "$REPO/dists/trixie/Release"
gpg --homedir "$GNUPGHOME" --batch --export "$publish_fpr" \
    > "$REPO/plebian-os-installer.gpg"

if find "$REPO" \( -name 'private-keys-v1.d' -o -name 'trustdb.gpg' -o -name '*.key' -o -name 'pubring.kbx' \) | grep -q .; then
    echo "refusing to leave private key material in $REPO" >&2
    exit 1
fi
