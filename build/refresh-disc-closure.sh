#!/usr/bin/env bash
# refresh-disc-closure.sh SNAPSHOT
#
# Rewrite build/disc-apt-closure.lock: the Debian packages the installer disc
# carries so the OS packages and desktop task install with no mirror.
# SNAPSHOT selects the Debian archive state, e.g. 20261116T000000Z.
#
# The set is what apt would add to a minimal Debian 13 system to satisfy the
# dependencies of debian/control and the locked project debs, without
# Recommends. The installer can also use this set on a larger base system.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK="$HERE/build/disc-apt-closure.lock"
if [ "$#" -ne 1 ] || ! [[ "$1" =~ ^[0-9]{8}T[0-9]{6}Z$ ]]; then
    echo "usage: refresh-disc-closure.sh YYYYMMDDTHHMMSSZ" >&2
    exit 2
fi
snapshot="$1"

work="$(mktemp -d "${TMPDIR:-/tmp}/disc-closure.XXXXXX")"
trap 'rm -rf "$work"' EXIT
"$HERE/build/fetch-disc-closure.sh" --project "$work/project"

# Pass project debs to apt as local files. Ask the snapshot only for Debian
# packages, including whatever the control records of those local debs need.
wanted="$(python3 - "$HERE/debian/control" "$work/project" <<'PY'
import re, sys
from pathlib import Path
text = open(sys.argv[1]).read()
ours = set(re.findall(r"^Package: (\S+)$", text, flags=re.M))
project = {p.name.split("_", 1)[0] for p in Path(sys.argv[2]).glob("*.deb")}
names = []
for field in re.findall(r"^Depends:((?:.*\n(?:[ \t].*\n)*))", text, flags=re.M):
    for item in field.replace("\n", " ").split(","):
        item = item.strip()
        if not item or item.startswith("${"):
            continue
        if "|" in item:
            sys.exit(f"alternative dependency needs a decision: {item}")
        name = re.sub(r"\s*\(.*\)$", "", item).split(":")[0]
        if name not in ours and name not in project and name not in names:
            names.append(name)
print(" ".join(sorted(names)))
PY
)"
[ -n "$wanted" ] || { echo "debian/control names no outside dependency" >&2; exit 1; }

runtime=docker
command -v docker >/dev/null 2>&1 || runtime=podman
"$runtime" run --rm --platform linux/amd64 -v "$work/project:/project:ro" \
    -e "SNAPSHOT=$snapshot" -e "WANTED=$wanted" debian:trixie bash -euo pipefail -c '
    rm -f /etc/apt/sources.list.d/*
    base=http://snapshot.debian.org/archive
    {
        echo "deb [check-valid-until=no] $base/debian/$SNAPSHOT trixie main"
        echo "deb [check-valid-until=no] $base/debian/$SNAPSHOT trixie-updates main"
        echo "deb [check-valid-until=no] $base/debian-security/$SNAPSHOT trixie-security main"
    } > /etc/apt/sources.list
    apt-get -q --error-on=any update >&2
    # apt checks each download against the signed index; the digests below
    # are then taken from the files it accepted.
    read -ra packages <<< "$WANTED"
    packages+=(/project/*.deb)
    apt-get install -y --no-install-recommends --print-uris "${packages[@]}" \
        | grep -E "^.https?://" > /tmp/uris
    apt-get install -y --no-install-recommends --download-only "${packages[@]}" >&2
    while read -r url file _; do
        url=${url#?}; url=${url%?}
        echo "$url $(stat -c %s /var/cache/apt/archives/$file) $(sha256sum /var/cache/apt/archives/$file | cut -d" " -f1)"
    done < /tmp/uris
' > "$work/debian-uris"

python3 - "$work/debian-uris" "$LOCK" "$snapshot" "$wanted" <<'PY'
import os, re, sys, urllib.parse
rows = []
for line in open(sys.argv[1]):
    m = re.match(r"^(\S+) (\d+) ([0-9a-f]{64})$", line.strip())
    if not m:
        sys.exit(f"unreadable line from apt: {line!r}")
    url, size, digest = m.groups()
    url = re.sub(r"^http://", "https://", url)
    name = urllib.parse.unquote(os.path.basename(url))
    rows.append((name, digest, size, url))
if not rows:
    sys.exit("apt listed no packages")
rows.sort()
with open(sys.argv[2], "w") as lock:
    lock.write("# Debian packages carried in the installer disc repository.\n")
    lock.write("# Written by build/refresh-disc-closure.sh; do not edit by hand.\n")
    lock.write(f"# snapshot: {sys.argv[3]}\n")
    lock.write(f"# for: {sys.argv[4]}\n")
    lock.write("# FILE SHA256 BYTES URL\n")
    for row in rows:
        lock.write(" ".join(row) + "\n")
print(f"{len(rows)} package(s), {sum(int(r[2]) for r in rows)} bytes -> {sys.argv[2]}")
PY
