#!/usr/bin/env python3
"""check-debs.py DIRECTORY: compare built packages with debian/install-map.

The source-level tests compare lists. This reads the packages themselves:
every regular file each .deb carries, with its mode and owner, must be a row
of the map, and every row must be in its package. Files the packaging tools
add under /usr/share/doc are allowed. Exit 0 when they agree, 1 when they do
not, 2 when a package could not be read.
"""
import pathlib
import subprocess
import sys
import tarfile
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALLOWED_EXTRA = ("/usr/share/doc/",)


def expected():
    rows = {}
    for line in (ROOT / "debian" / "install-map").read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            package, mode, _, destination = line.split()
            rows.setdefault(package, {})[destination] = int(mode, 8)
    return rows


def contents(deb):
    with tempfile.TemporaryDirectory() as tmp:
        data = pathlib.Path(tmp) / "data.tar"
        with open(data, "wb") as out:
            subprocess.run(["dpkg-deb", "--fsys-tarfile", str(deb)], stdout=out, check=True)
        found = {}
        with tarfile.open(data) as archive:
            for member in archive:
                if member.isdir():
                    continue
                name = "/" + member.name.lstrip("./")
                found[name] = (member.mode, member.uname, member.gname, member.isreg())
        return found


def main(argv):
    if len(argv) != 1:
        print(__doc__.strip().splitlines()[0])
        return 2
    wanted = expected()
    problems = []
    for package, rows in sorted(wanted.items()):
        debs = sorted(pathlib.Path(argv[0]).glob(f"{package}_*.deb"))
        if len(debs) != 1:
            print(f"BROKEN {package}: expected one package file, found {len(debs)}")
            return 2
        try:
            found = contents(debs[0])
        except (subprocess.CalledProcessError, tarfile.TarError, OSError) as error:
            print(f"BROKEN {package}: {error}")
            return 2
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
        print(f"read   {debs[0].name}: {len(rows)} mapped file(s)")
    for problem in problems:
        print("FAIL   " + problem)
    if problems:
        print(f"check-debs: FAIL ({len(problems)} problem(s))")
        return 1
    print("check-debs: packages match debian/install-map")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
