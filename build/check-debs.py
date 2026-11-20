#!/usr/bin/env python3
"""check-debs.py DIRECTORY: check all binary packages declared in debian/control.

The source-level tests compare lists. This reads the packages themselves:
every regular file each .deb carries, with its mode and owner, must be a row
of the map, and every row must be in its package. Files the packaging tools
add under /usr/share/doc are allowed. Exit 0 when they agree, 1 when they do
not, 2 when a package could not be read.
"""
from collections import Counter
import pathlib
import subprocess
import sys
import tarfile
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALLOWED_EXTRA = ("/usr/share/doc/",)
DOC_PARENTS = {"/", "/usr", "/usr/share", "/usr/share/doc"}


def expected():
    control = (ROOT / "debian" / "control").read_text()
    rows = {
        line.split(":", 1)[1].strip(): {}
        for line in control.splitlines() if line.lower().startswith("package:")
    }
    for line in (ROOT / "debian" / "install-map").read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            package, mode, _, destination = line.split()
            if package not in rows:
                raise ValueError(f"install-map names undeclared package {package}")
            rows[package][destination] = int(mode, 8)
    return rows


def contents(deb, *, docs_only):
    with tempfile.TemporaryDirectory() as tmp:
        data = pathlib.Path(tmp) / "data.tar"
        with open(data, "wb") as out:
            subprocess.run(["dpkg-deb", "--fsys-tarfile", str(deb)], stdout=out, check=True)
        found = {}
        with tarfile.open(data) as archive:
            for member in archive:
                path = pathlib.PurePosixPath(member.name)
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError(f"invalid archive path {member.name}")
                name = "/" + "/".join(path.parts)
                if member.isdir() and (not docs_only or name in DOC_PARENTS):
                    continue
                if name in found:
                    raise ValueError(f"duplicate archive member {name}")
                found[name] = (member.mode, member.uname, member.gname, member.isreg())
        return found


def main(argv):
    if len(argv) != 1:
        print(__doc__.strip().splitlines()[0])
        return 2
    try:
        wanted = expected()
    except (ValueError, OSError) as error:
        print(f"BROKEN package declarations: {error}")
        return 2
    problems = []
    counts = Counter()
    for deb in sorted(pathlib.Path(argv[0]).glob("*.deb")):
        try:
            package = subprocess.check_output(["dpkg-deb", "-f", deb, "Package"], text=True).strip()
            rows = wanted.get(package, {})
            found = contents(deb, docs_only=not rows)
        except (subprocess.CalledProcessError, tarfile.TarError, ValueError, OSError) as error:
            print(f"BROKEN {deb.name}: {error}")
            return 2
        if package not in wanted:
            problems.append(f"{deb.name}: undeclared package {package}")
        if not deb.name.startswith(package + "_"):
            problems.append(f"{deb.name}: filename does not match package {package}")
        counts[package] += 1
        for destination, mode in sorted(rows.items()):
            if destination not in found:
                problems.append(f"{package}: missing {destination}")
                continue
            actual, user, group, regular = found.pop(destination)
            if not regular:
                problems.append(f"{package}: {destination} is not a regular file")
            if actual != mode:
                problems.append(f"{package}: {destination} mode {actual:04o}, wanted {mode:04o}")
            if (user, group) != ("root", "root"):
                problems.append(f"{package}: {destination} owned by {user}:{group}")
        for extra in sorted(found):
            if not extra.startswith(ALLOWED_EXTRA):
                problems.append(f"{package}: unlisted file {extra}")
        print(f"read   {deb.name}: {len(rows)} mapped file(s)")
    for package in sorted(wanted):
        if counts[package] != 1:
            print(f"BROKEN {package}: expected one package file, found {counts[package]}")
            return 2
    for problem in problems:
        print("FAIL   " + problem)
    if problems:
        print(f"check-debs: FAIL ({len(problems)} problem(s))")
        return 1
    print("check-debs: packages match debian/install-map")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
