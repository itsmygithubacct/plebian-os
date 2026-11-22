"""The installer installs the OS packages and desktop task from the signed disc.

These checks are literals: the package names, the copied destinations, the
removal of the disc source, and the temporary directory that holds the
signing key.
"""
import hashlib
import itertools
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import test_debian_packaging


ROOT = Path(__file__).resolve().parents[1]
PRESEED = ROOT / "preseed" / "preseed.cfg"
REMASTER = ROOT / "build" / "remaster-iso.sh"
SIGN = ROOT / "build" / "write-disc-apt.sh"
BUILD = ROOT / "build" / "build-debs.sh"
DISC_ONLY = (
    "-o Dir::Etc::sourcelist=/etc/apt/sources.list.d/plebian-os-installer.list "
    "-o Dir::Etc::sourceparts=/var/empty"
)
INSTALL = "in-target apt-get install -y --no-install-recommends " + DISC_ONLY
LOCK = ROOT / "build" / "disc-apt-closure.lock"
PROJECT_LOCK = ROOT / "build" / "disc-project-debs.lock"
PROJECT_POOL = "https://itsmygithubacct.github.io/plebian-apt/pool/main/"
FETCH = ROOT / "build" / "fetch-disc-closure.sh"
REMOVE = (
    "rm -f /target/etc/apt/sources.list.d/plebian-os-installer.list "
    "/target/etc/apt/keyrings/plebian-os-installer.gpg"
)
ENABLE = "in-target systemctl enable plebian-os-firstboot.service"


def control_packages():
    return re.findall(
        r"^Package: (\S+)$",
        (ROOT / "debian" / "control").read_text(),
        flags=re.MULTILINE,
    )


def late_command():
    return PRESEED.read_text().split("d-i preseed/late_command string", 1)[1]


def write_destinations(late):
    """Literal cp/mv destinations and shell output redirections in late_command."""
    shell = shlex.shlex(late.replace("\\\n", " "), posix=True, punctuation_chars=";&|<>")
    shell.whitespace_split = True
    shell.commenters = ""
    command = []
    for token in itertools.chain(shell, [";"]):
        if token in (">", ">>", ">|"):
            yield next(shell)
        elif token in (";", "&&", "||", "|"):
            if "cp" in command or "mv" in command:
                yield command[-1]
            command.clear()
        else:
            command.append(token)


class InstallerPackageTests(unittest.TestCase):
    def test_late_command_installs_exactly_the_declared_packages(self):
        late = late_command()
        match = re.search(
            re.escape(INSTALL) + r" ([^;\\]+)",
            late,
        )
        self.assertIsNotNone(match)
        installed = match.group(1).split()
        declared = control_packages()
        self.assertEqual(installed, declared)
        self.assertEqual(set(installed), set(declared))
        self.assertEqual(
            declared,
            [
                "plebian-os-release",
                "plebian-os-tools",
                "plebian-os-firstboot",
                "plebian-desktop-base",
                "plebian-archive-keyring",
                "pleb-desktop",
                "task-pleb-desktop",
            ],
        )

    def test_late_command_leaves_packaged_files_to_dpkg(self):
        late = late_command()
        self.assertNotIn("cp /cdrom/plebian-os/$native_module", late)
        packaged = {"/target" + dst for _, _, _, dst in test_debian_packaging.install_map()}
        self.assertEqual(packaged.intersection(write_destinations(late)), set())

    def test_copy_printf_and_rename_destinations_are_checked(self):
        dst = "/target/etc/systemd/logind.conf.d/50-plebian-lid.conf"
        for command in (f"cp /cdrom/file '{dst}'", f"printf '%s;' value >'{dst}'",
                        f"mv -f /target/staged '{dst}'"):
            with self.subTest(command=command):
                self.assertIn(dst, list(write_destinations(command)))

    def test_optional_source_carrier_is_copied_into_the_payload_directory(self):
        late = late_command()
        carrier = "/target/var/lib/plebian-os/payloads/source-carrier"
        self.assertIn("if [ -d /cdrom/plebian-os/source-carrier ];", late)
        self.assertIn("cp -R /cdrom/plebian-os/source-carrier/. " + carrier + "/", late)
        self.assertIn("chown -R root:root " + carrier, late)
        self.assertIn("chmod -R a+rX,go-w " + carrier, late)
        self.assertNotIn("/target/usr/share/plebian-os/source-carrier", late)

    def test_disc_source_and_key_are_removed_before_firstboot_is_enabled(self):
        preseed = PRESEED.read_text()
        self.assertIn(
            "deb [signed-by=/etc/apt/keyrings/plebian-os-installer.gpg] "
            "file:/mnt/cdrom/plebian-os/apt trixie main",
            preseed,
        )
        self.assertIn(REMOVE, preseed)
        install_at = preseed.index(INSTALL)
        remove_at = preseed.index(REMOVE)
        enable_at = preseed.index(ENABLE)
        self.assertLess(install_at, remove_at)
        self.assertLess(remove_at, enable_at)
        self.assertLess(preseed.index("umount /target/mnt/cdrom"), enable_at)
        after = preseed[remove_at + len(REMOVE):]
        self.assertNotIn("plebian-os-installer.list", after)
        self.assertNotIn("plebian-os-installer.gpg", after)

    def test_remaster_signs_inside_a_temporary_directory_only(self):
        script = SIGN.read_text()
        self.assertIn("plebian-os-installer-gpg.XXXXXX", script)
        self.assertIn("trap cleanup_signing_key EXIT", script)
        self.assertIn('rm -rf "$GNUPGHOME"', script)
        self.assertNotIn("~/.gnupg", script)
        self.assertNotIn("$HOME/.gnupg", script)
        self.assertNotIn("/home/", script)
        remaster = REMASTER.read_text()
        refresh = remaster.index(
            'python3 "$INSTALLER_BRANDER" refresh-md5 "$EXTRACT"'
        )
        self.assertLess(remaster.index('"$HERE/build/build-debs.sh"'), refresh)
        self.assertLess(remaster.index('"$HERE/build/write-disc-apt.sh"'), refresh)
        self.assertNotRegex(remaster, r"\bgpg\b")
        builder = BUILD.read_text()
        self.assertIn("dpkg-buildpackage -b -us -uc", builder)
        self.assertIn('python3 "$HERE/build/check-debs.py" "$OUTDIR"', builder)
        self.assertIn("plebian-024-build:spike", builder)
        self.assertIn("debian:trixie", builder)

    def test_signing_script_leaves_no_key_outside_its_temporary_directory(self):
        for wrong in (False, True):
            with self.subTest(wrong_key=wrong):
                self._sign_and_check(wrong)

    def _sign_and_check(self, wrong):
        with tempfile.TemporaryDirectory(prefix="installer-apt-") as td:
            root = Path(td)
            home = root / "home"
            tmpdir = root / "tmp"
            sentinel = root / "caller-gnupg"
            debs = root / "debs"
            repo = root / "repo"
            for path in (home, tmpdir, sentinel, debs):
                path.mkdir(mode=0o700)
            (sentinel / "marker").write_text("untouched\n")
            self._write_deb(debs)
            env = os.environ.copy()
            env["HOME"] = str(home)
            env["TMPDIR"] = str(tmpdir)
            env["GNUPGHOME"] = str(sentinel)
            if wrong:
                env["PLEBIAN_OS_INSTALLER_APT_WRONG_KEY"] = "1"
            else:
                env.pop("PLEBIAN_OS_INSTALLER_APT_WRONG_KEY", None)
            result = subprocess.run(
                [str(SIGN), str(debs), str(repo)],
                env=env, text=True, capture_output=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((home / ".gnupg").exists())
            self.assertEqual(sorted(p.name for p in sentinel.iterdir()), ["marker"])
            self.assertEqual(list(tmpdir.glob("plebian-os-installer-gpg.*")), [])
            self.assertEqual((repo / ".aptignr").read_bytes(), b"")
            self.assertTrue((repo / "dists/trixie/main/binary-amd64/Packages").is_file())
            self.assertTrue((repo / "dists/trixie/main/binary-amd64/Packages.gz").is_file())
            inrelease = (repo / "dists/trixie/InRelease").read_text()
            self.assertIn("BEGIN PGP SIGNED MESSAGE", inrelease)
            names = {path.name for path in repo.rglob("*")}
            for forbidden in ("private-keys-v1.d", "trustdb.gpg", "pubring.kbx"):
                self.assertNotIn(forbidden, names)
            self.assertEqual(list(repo.rglob("*.key")), [])
            self._verify_published_key(repo, root / "verify-gpg", accepts=not wrong)
            update = self._apt_update(repo, root / "apt")
            if wrong:
                self.assertNotEqual(update.returncode, 0, update.stderr)
                self.assertRegex(update.stderr, r"Missing key|NO_PUBKEY [0-9A-F]+")
            else:
                self.assertEqual(update.returncode, 0, update.stderr)

    def _write_deb(self, debs):
        staging = debs / "staging"
        control_dir = staging / "DEBIAN"
        control_dir.mkdir(parents=True)
        staging.chmod(0o755)
        control_dir.chmod(0o755)
        payload = staging / "usr/share/sample"
        payload.mkdir(parents=True)
        payload.chmod(0o755)
        (payload.parent).chmod(0o755)
        (staging / "usr").chmod(0o755)
        (payload / "file").write_text("sample\n")
        (staging / "DEBIAN/control").write_text(
            "Package: sample-installer-package\n"
            "Version: 1\n"
            "Architecture: all\n"
            "Maintainer: Plebian-OS test <test@example.invalid>\n"
            "Description: sample\n"
            " sample package for the disc repository test\n"
        )
        subprocess.run(
            [
                "dpkg-deb", "--root-owner-group", "-b",
                str(staging), str(debs / "sample-installer-package_1_all.deb"),
            ],
            check=True, capture_output=True, timeout=20,
        )

    def _verify_published_key(self, repo, home, accepts):
        home.mkdir(mode=0o700)
        key = repo / "plebian-os-installer.gpg"
        subprocess.run(
            ["gpg", "--homedir", str(home), "--batch", "--import", str(key)],
            check=True, capture_output=True, timeout=20,
        )
        result = subprocess.run(
            ["gpg", "--homedir", str(home), "--batch", "--verify",
             str(repo / "dists/trixie/InRelease")],
            capture_output=True, text=True, timeout=20,
        )
        if accepts:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stderr)

    def _apt_update(self, repo, root):
        key = root / "etc/apt/keyrings/key.gpg"
        key.parent.mkdir(parents=True)
        shutil.copyfile(repo / "plebian-os-installer.gpg", key)
        src = root / "tmp/src.list"
        src.parent.mkdir(parents=True)
        src.write_text(
            "deb [signed-by=" + str(key) + "] file:" + str(repo) + " trixie main\n"
        )
        empty = root / "var/empty"
        empty.mkdir(parents=True)
        (root / "var/lib/dpkg").mkdir(parents=True)
        (root / "var/lib/dpkg/status").write_text("")
        (root / "var/lib/apt/lists/partial").mkdir(parents=True)
        (root / "var/cache/apt/archives/partial").mkdir(parents=True)
        return subprocess.run(
            [
                "apt-get",
                "-o", "Dir=" + str(root),
                "-o", "Dir::Etc::sourcelist=" + str(src),
                "-o", "Dir::Etc::sourceparts=" + str(empty),
                "-o", "APT::Get::List-Cleanup=false",
                "update",
            ],
            env={**os.environ, "LC_ALL": "C"}, capture_output=True, text=True, timeout=30,
        )


def outside_dependencies():
    text = (ROOT / "debian" / "control").read_text()
    ours = set(control_packages())
    names = set()
    for field in re.findall(r"^Depends:((?:.*\n(?:[ \t].*\n)*))", text, flags=re.M):
        for item in field.replace("\n", " ").split(","):
            item = item.strip()
            if item and not item.startswith("${"):
                names.add(re.sub(r"\s*\(.*\)$", "", item))
    return names - ours


def lock_rows(path=LOCK):
    rows = []
    for line in path.read_text().splitlines():
        if line and not line.startswith("#"):
            rows.append(line.split(" "))
    return rows


class DiscClosureTests(unittest.TestCase):
    def test_locks_cover_debian_and_project_dependencies_separately(self):
        debian = {row[0].split("_", 1)[0] for row in lock_rows()}
        project = {row[0].split("_", 1)[0] for row in lock_rows(PROJECT_LOCK)}
        direct_debian = {"python3", "git", "sudo", "curl", "ca-certificates", "systemd"}
        direct_project = {"kilix", "kilix-content", "kilix-multiplexer", "kilix-needle", "pleb"}
        self.assertEqual(outside_dependencies(), direct_debian | direct_project)
        self.assertLessEqual(direct_debian, debian)
        self.assertLessEqual({"python3-numpy", "python3-numpy-dev", "libblas3",
                              "liblapack3", "libgfortran5"}, debian)
        self.assertEqual(
            project,
            direct_project | {
                "kilix-engine", "kilix-ml", "kilix-native", "kilix-transcript-clean", "kilix-tui-utils",
                "libkilix-encodec", "libonnxruntime1.21", "libonnxruntime-dev",
            },
        )
        self.assertFalse(debian & project)

    def test_project_lock_pins_amd64_or_all_debs_from_the_project_pool(self):
        rows = lock_rows(PROJECT_LOCK)
        for name, digest, size, url in rows:
            self.assertRegex(name, r"^[a-z0-9][a-z0-9.+-]*_[^_/]+_(amd64|all)\.deb$")
            self.assertRegex(digest, r"^[0-9a-f]{64}$")
            self.assertRegex(size, r"^[1-9][0-9]*$")
            self.assertTrue(url.startswith(PROJECT_POOL), url)
            self.assertEqual(url.rsplit("/", 1)[-1], name)
        self.assertEqual(len({row[0].split("_", 1)[0] for row in rows}), len(rows))

    def test_lock_rows_are_pinned_to_a_dated_snapshot(self):
        rows = lock_rows()
        self.assertGreater(len(rows), len(outside_dependencies()))
        for row in rows:
            self.assertEqual(len(row), 4, row)
            name, digest, size, url = row
            self.assertRegex(name, r"^[a-z0-9][a-z0-9.+-]*_[^_/]+_(amd64|all)\.deb$")
            self.assertRegex(digest, r"^[0-9a-f]{64}$")
            self.assertRegex(size, r"^[1-9][0-9]*$")
            self.assertRegex(
                url, r"^https://snapshot\.debian\.org/archive/[a-z-]+/\d{8}T\d{6}Z/pool/"
            )
        self.assertEqual(len({row[0] for row in rows}), len(rows))

    def test_remaster_adds_the_closure_before_signing(self):
        remaster = REMASTER.read_text()
        build = remaster.index('"$HERE/build/build-debs.sh" "$pkg_debs"')
        fetch = remaster.index('"$HERE/build/fetch-disc-closure.sh" "$pkg_debs"')
        project = remaster.index('"$HERE/build/fetch-disc-closure.sh" --project "$pkg_debs"')
        sign = remaster.index('"$HERE/build/write-disc-apt.sh" "$pkg_debs"')
        self.assertLess(build, fetch)
        self.assertLess(fetch, project)
        self.assertLess(project, sign)

    def _fetch(self, tmp, content, recorded, project=False):
        tmp = Path(tmp)
        cache, dest = tmp / "cache", tmp / "dest"
        cache.mkdir()
        digest = hashlib.sha256(recorded).hexdigest()
        (cache / (digest + ".deb")).write_bytes(content)
        lock = tmp / "lock"
        pool = PROJECT_POOL if project else "https://snapshot.debian.org/archive/debian/20260101T000000Z/pool/main/"
        lock.write_text(f"demo_1_all.deb {digest} {len(recorded)} {pool}d/demo/demo_1_all.deb\n")
        env = dict(
            os.environ,
            PLEBIAN_OS_DISC_CLOSURE_LOCK=str(lock),
            PLEBIAN_OS_DISC_PROJECT_LOCK=str(lock),
            PLEBIAN_OS_DISC_CLOSURE_CACHE=str(cache),
            PLEBIAN_OS_DISC_CLOSURE_OFFLINE="1",
        )
        args = ["bash", str(FETCH)]
        if project:
            args.append("--project")
        result = subprocess.run(
            [*args, str(dest)],
            env=env, capture_output=True, text=True, timeout=30,
        )
        return result, dest / "demo_1_all.deb"

    def test_fetch_delivers_a_cached_file_that_matches_the_lock(self):
        for project in (False, True):
            with self.subTest(project=project), tempfile.TemporaryDirectory() as tmp:
                result, delivered = self._fetch(tmp, b"right bytes", b"right bytes", project)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(delivered.read_bytes(), b"right bytes")

    def test_fetch_refuses_a_file_that_does_not_match_the_lock(self):
        # Same length, different bytes: only the digest can tell them apart.
        for project in (False, True):
            with self.subTest(project=project), tempfile.TemporaryDirectory() as tmp:
                result, delivered = self._fetch(tmp, b"wrong bytes", b"right bytes", project)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertFalse(delivered.exists())


if __name__ == "__main__":
    unittest.main()
