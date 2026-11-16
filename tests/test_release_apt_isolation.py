"""Release apt installs see only source files inside the Debian archive.

A signed third-party repository, including one that offers a higher version of
a release package, is left on disk and is not a candidate. Packages already
installed from it are not removed or downgraded.
"""

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPDATE = ROOT / "provision" / "plebian-os-update.sh"
DEPS = ROOT / "provision" / "install-deps.sh"
SNAPSHOT = "20260727T000000Z"


def codename() -> str:
    return subprocess.run(
        ["bash", "-c", '. /etc/os-release 2>/dev/null; printf %s "${VERSION_CODENAME:-trixie}"'],
        text=True, capture_output=True, check=True,
    ).stdout


def debian_sources(suite: str) -> str:
    return (
        "Types: deb\n"
        "URIs: https://deb.debian.org/debian\n"
        f"Suites: {suite} {suite}-updates\n"
        "Components: main\n"
        "Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg\n"
        "\n"
        "Types: deb\n"
        "URIs: https://security.debian.org/debian-security\n"
        f"Suites: {suite}-security\n"
        "Components: main\n"
        "Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg\n"
    )


def snapshot_sources(suite: str) -> str:
    return (
        "Types: deb\n"
        f"URIs: https://snapshot.debian.org/archive/debian/{SNAPSHOT}\n"
        f"Suites: {suite} {suite}-updates\n"
        "Components: main contrib non-free non-free-firmware\n"
        "Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg\n"
        "Check-Valid-Until: no\n"
        "\n"
        "Types: deb\n"
        f"URIs: https://snapshot.debian.org/archive/debian-security/{SNAPSHOT}\n"
        f"Suites: {suite}-security\n"
        "Components: main contrib non-free non-free-firmware\n"
        "Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg\n"
        "Check-Valid-Until: no\n"
    )


CUDA_LIST = (
    "deb [signed-by=/usr/share/keyrings/cuda-archive-keyring.gpg] "
    "https://developer.download.nvidia.com/compute/cuda/repos/debian13/x86_64/ /\n"
)


def write_apt(tmp: Path, parts: dict[str, str]) -> Path:
    apt = tmp / "apt"
    (apt / "sources.list.d").mkdir(parents=True)
    (apt / "sources.list").write_text("")
    for name, text in parts.items():
        target = apt / "sources.list.d" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    return apt


def shell_function(source: str, name: str) -> str:
    start = source.index(f"\n{name}() {{\n") + 1
    return source[start:source.index("\n}\n", start) + 3]


class ReleaseAptIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if shutil.which("apt-get") is None:
            raise unittest.SkipTest("apt-get is required")

    def _prepare(self, apt: Path, phase: str, snapshot: str, *, require_lifetime: bool):
        home = apt.parent / "home"
        state = apt.parent / "state"
        script = (
            "set -euo pipefail\n"
            "export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1\n"
            f"PLEB_STATE_HOME={str(state)!r}\n"
            f"source {str(UPDATE)!r}\n"
            "dest=$(mktemp -d)\n"
            "rc=0\n"
            "prepare_release_apt_config "
            f"$dest {phase} {snapshot!r} {codename()!r} {str(apt)!r} || rc=$?\n"
        )
        if require_lifetime:
            script += (
                'if [ "$rc" = 0 ]; then\n'
                '  require_lifetime_release_apt_provenance "$dest/indexes" || rc=$?\n'
                "fi\n"
            )
        script += (
            "printf 'RC=%s\\n' \"$rc\"\n"
            "failure=$(cat -- \"$dest/failure\" 2>/dev/null || true)\n"
            "printf 'FAIL=%s\\n' \"$failure\"\n"
            "printf '%s\\n' 'INDEXES<<'\n"
            "cat -- \"$dest/indexes\"\n"
            "printf '%s\\n' '>>INDEXES'\n"
            "printf '%s\\n' 'COPIED<<'\n"
            "for copied in \"$dest/sources.list.d\"/*; do\n"
            "  [ -f \"$copied\" ] || continue\n"
            "  printf '%s\\n' \"${copied##*/}\"\n"
            "done | LC_ALL=C sort\n"
            "printf '%s\\n' '>>COPIED'\n"
            "rm -rf -- \"$dest\"\n"
        )
        env = {k: v for k, v in os.environ.items() if not k.startswith("PLEBIAN_OS_")}
        env.update({
            "HOME": str(home),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PLEBIAN_OS_APT_SOURCES_ROOT": str(apt),
        })
        result = subprocess.run(
            ["bash", "-c", script], env=env, text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        def between(text: str, start: str, end: str) -> str:
            return text.split(start, 1)[1].split(end, 1)[0].strip("\n")

        rc = int(result.stdout.split("RC=", 1)[1].splitlines()[0])
        failure = result.stdout.split("FAIL=", 1)[1].splitlines()[0]
        indexes = between(result.stdout, "INDEXES<<\n", ">>INDEXES")
        copied = between(result.stdout, "COPIED<<\n", ">>COPIED")
        copied_names = [line for line in copied.splitlines() if line]
        return rc, failure, indexes, copied_names, result.stderr

    def test_cuda_is_omitted_and_debian_indexes_pass(self):
        suite = codename()
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            apt = write_apt(tmp, {
                "debian.sources": debian_sources(suite),
                "cuda-debian13-x86_64.list": CUDA_LIST,
            })
            cuda = apt / "sources.list.d" / "cuda-debian13-x86_64.list"
            debian = apt / "sources.list.d" / "debian.sources"
            cuda_hash = hashlib.sha256(cuda.read_bytes()).hexdigest()
            debian_hash = hashlib.sha256(debian.read_bytes()).hexdigest()
            rc, failure, indexes, copied, stderr = self._prepare(
                apt, "lifetime", "", require_lifetime=True,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(failure, "")
            self.assertEqual(copied, ["debian.sources"])
            self.assertNotIn("nvidia", indexes)
            self.assertNotIn("developer.download", indexes)
            self.assertIn(f"https://deb.debian.org/debian {suite} main amd64", indexes)
            self.assertIn(
                f"https://security.debian.org/debian-security {suite}-security main amd64",
                indexes,
            )
            self.assertNotIn("outside the Debian archive", stderr)
            self.assertEqual(hashlib.sha256(cuda.read_bytes()).hexdigest(), cuda_hash)
            self.assertEqual(hashlib.sha256(debian.read_bytes()).hexdigest(), debian_hash)

    def test_install_phase_keeps_only_the_snapshot_file(self):
        suite = codename()
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            apt = write_apt(tmp, {
                "debian.sources": debian_sources(suite),
                "cuda-debian13-x86_64.list": CUDA_LIST,
                "plebian-os-snapshot.sources": snapshot_sources(suite),
            })
            before = {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (apt / "sources.list.d").iterdir()
            }
            rc, failure, indexes, copied, stderr = self._prepare(
                apt, "install", SNAPSHOT, require_lifetime=False,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(failure, "")
            self.assertEqual(copied, ["plebian-os-snapshot.sources"])
            self.assertIn(
                f"https://snapshot.debian.org/archive/debian/{SNAPSHOT} {suite} main amd64",
                indexes,
            )
            self.assertIn(
                f"https://snapshot.debian.org/archive/debian-security/{SNAPSHOT} "
                f"{suite}-security main amd64",
                indexes,
            )
            self.assertNotIn("deb.debian.org", indexes)
            self.assertNotIn("nvidia", indexes)
            after = {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (apt / "sources.list.d").iterdir()
            }
            self.assertEqual(after, before)

    def test_install_phase_without_the_snapshot_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            apt = write_apt(tmp, {"debian.sources": debian_sources(codename())})
            rc, failure, indexes, copied, stderr = self._prepare(
                apt, "install", SNAPSHOT, require_lifetime=False,
            )
            self.assertEqual(rc, 1)
            self.assertEqual(copied, [])
            self.assertEqual(indexes.strip(), "")
            self.assertEqual(
                failure,
                "release install closure resolved from an index other than "
                f"snapshot {SNAPSHOT}",
            )
            self.assertIn("apt index outside the install snapshot:", stderr)

    def test_an_empty_source_list_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            apt = write_apt(tmp, {})
            rc, failure, _indexes, copied, _stderr = self._prepare(
                apt, "lifetime", "", require_lifetime=False,
            )
            self.assertEqual(rc, 1)
            self.assertEqual(copied, [])
            self.assertEqual(failure, "release apt index provenance is empty")

    def test_a_mixed_file_is_excluded_whole(self):
        suite = codename()
        mixed = (
            f"deb https://deb.debian.org/debian {suite} main\n"
            "deb [signed-by=/usr/share/keyrings/cuda-archive-keyring.gpg] "
            "https://developer.download.nvidia.com/compute/cuda/repos/debian13/x86_64/ /\n"
        )
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            apt = write_apt(tmp, {
                "debian.sources": debian_sources(suite),
                "mixed.list": mixed,
            })
            mixed_hash = hashlib.sha256((apt / "sources.list.d" / "mixed.list").read_bytes()).hexdigest()
            rc, failure, indexes, copied, stderr = self._prepare(
                apt, "lifetime", "", require_lifetime=True,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(failure, "")
            self.assertEqual(copied, ["debian.sources"])
            self.assertNotIn("nvidia", indexes)
            self.assertEqual(
                hashlib.sha256((apt / "sources.list.d" / "mixed.list").read_bytes()).hexdigest(),
                mixed_hash,
            )

    def test_a_symlink_source_is_not_followed(self):
        suite = codename()
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            outside = tmp / "outside.list"
            outside.write_text(CUDA_LIST)
            apt = write_apt(tmp, {"debian.sources": debian_sources(suite)})
            (apt / "sources.list.d" / "linked.list").symlink_to(outside)
            rc, _failure, indexes, copied, stderr = self._prepare(
                apt, "lifetime", "", require_lifetime=True,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(copied, ["debian.sources"])
            self.assertNotIn("nvidia", indexes)
            self.assertEqual(outside.read_text(), CUDA_LIST)

    def test_a_disabled_third_party_source_is_not_a_release_source(self):
        suite = codename()
        disabled = (
            "Types: deb\n"
            "URIs: https://dl.google.com/linux/chrome/deb\n"
            "Suites: stable\n"
            "Components: main\n"
            "Enabled: no\n"
        )
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            apt = write_apt(tmp, {
                "debian.sources": debian_sources(suite),
                "chrome.sources": disabled,
            })
            rc, failure, indexes, copied, stderr = self._prepare(
                apt, "lifetime", "", require_lifetime=True,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(failure, "")
            self.assertEqual(copied, ["debian.sources"])
            self.assertNotIn("google", indexes)
            self.assertNotIn("outside the Debian archive", stderr)

    def test_release_dry_run_plans_the_private_configuration(self):
        suite = codename()
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            apt = write_apt(tmp, {
                "debian.sources": debian_sources(suite),
                "cuda-debian13-x86_64.list": CUDA_LIST,
            })
            cuda = apt / "sources.list.d" / "cuda-debian13-x86_64.list"
            before = cuda.read_bytes()
            env = {k: v for k, v in os.environ.items() if not k.startswith("PLEBIAN_OS_")}
            env.update({
                "HOME": str(tmp / "home"),
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "PLEBIAN_OS_RELEASE_MODE": "1",
                "PLEBIAN_OS_APT_SOURCES_ROOT": str(apt),
                "APT_PROVENANCE_PHASE": "lifetime",
                "PLEBIAN_OS_APT_CODENAME": suite,
                "PLEBIAN_OS_INSTALL_UV": "0",
            })
            result = subprocess.run(
                ["bash", str(DEPS), "--dry-run"],
                env=env, text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            plans = [line for line in result.stdout.splitlines()
                     if line.strip().startswith("+") and "apt-get" in line]
            self.assertTrue(plans)
            self.assertTrue(any(" update -y" in line for line in plans))
            self.assertTrue(any("bubblewrap" in line for line in plans))
            for line in plans:
                self.assertIn("Dir::Etc::SourceList=", line)
                self.assertIn("Dir::Etc::SourceParts=", line)
                self.assertNotIn(str(apt), line)
                self.assertNotIn("/etc/apt", line)
            self.assertIn(
                "cuda-debian13-x86_64.list is left unchanged and is not used "
                "to install release packages",
                result.stdout,
            )
            self.assertNotIn("disable each source above", result.stderr)
            self.assertEqual(cuda.read_bytes(), before)

    def test_development_dry_run_keeps_the_system_apt_command(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            env = {k: v for k, v in os.environ.items() if not k.startswith("PLEBIAN_OS_")}
            env.update({
                "HOME": str(tmp / "home"),
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "PLEBIAN_OS_RELEASE_MODE": "0",
                "PLEBIAN_OS_INSTALL_UV": "0",
            })
            result = subprocess.run(
                ["bash", str(DEPS), "--dry-run"],
                env=env, text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("    + apt-get update -y\n", result.stdout)
            self.assertIn("    + apt-get install -y --no-install-recommends ", result.stdout)
            self.assertNotIn("Dir::Etc::SourceList=", result.stdout)

    def test_security_only_accepted_set_is_missing_the_main_archive(self):
        suite = codename()
        mixed = (
            f"deb https://deb.debian.org/debian {suite} main\n"
            "deb [signed-by=/usr/share/keyrings/cuda-archive-keyring.gpg] "
            "https://developer.download.nvidia.com/compute/cuda/repos/debian13/x86_64/ /\n"
        )
        security = (
            "Types: deb\n"
            "URIs: https://security.debian.org/debian-security\n"
            f"Suites: {suite}-security\n"
            "Components: main\n"
            "Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg\n"
        )
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            apt = write_apt(tmp, {
                "debian.list": mixed,
                "security.sources": security,
            })
            rc, failure, indexes, _copied, stderr = self._prepare(
                apt, "lifetime", "", require_lifetime=False,
            )
            self.assertEqual(rc, 1, stderr)
            self.assertEqual(
                failure, f"release apt provenance is missing the {suite} main archive",
            )
            self.assertNotIn("release apt index provenance is empty", failure)
            self.assertNotIn("outside the Debian archive", failure)
            self.assertIn(f"{suite}-security", indexes)
            self.assertNotIn(f" {suite} main", indexes)

    def test_trusted_yes_on_a_debian_url_is_not_admitted(self):
        suite = codename()
        trusted = (
            f"deb [trusted=yes check-valid-until=no] "
            f"http://deb.debian.org/debian {suite} main\n"
        )
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            apt = write_apt(tmp, {"trusted.list": trusted})
            before = (apt / "sources.list.d" / "trusted.list").read_bytes()
            rc, failure, _indexes, copied, stderr = self._prepare(
                apt, "lifetime", "", require_lifetime=False,
            )
            self.assertNotEqual(rc, 0, stderr)
            self.assertEqual(copied, [])
            self.assertNotIn("trusted.list", copied)
            self.assertEqual((apt / "sources.list.d" / "trusted.list").read_bytes(), before)
            self.assertTrue(failure, stderr)

    def test_a_symlink_to_a_valid_debian_source_is_not_admitted(self):
        suite = codename()
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            outside = tmp / "real.sources"
            outside.write_text(debian_sources(suite))
            apt = write_apt(tmp, {})
            link = apt / "sources.list.d" / "linked.sources"
            link.symlink_to(outside)
            rc, failure, _indexes, copied, stderr = self._prepare(
                apt, "lifetime", "", require_lifetime=False,
            )
            self.assertNotEqual(rc, 0, stderr)
            self.assertEqual(copied, [])
            self.assertNotIn("linked.sources", copied)
            self.assertTrue(link.is_symlink())
            self.assertEqual(failure, "release apt index provenance is empty")

    def test_a_configuration_inside_the_operator_apt_directory_is_refused(self):
        suite = codename()
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            apt = write_apt(tmp, {"debian.sources": debian_sources(suite)})
            dest = apt / "private"
            dest.mkdir()
            script = (
                "set -euo pipefail\n"
                "export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1\n"
                f"PLEB_STATE_HOME={str(tmp / 'state')!r}\n"
                f"source {str(UPDATE)!r}\n"
                f"dest={str(dest)!r}\n"
                "rc=0\n"
                "prepare_release_apt_config "
                f"\"$dest\" lifetime '' {suite!r} {str(apt)!r} || rc=$?\n"
                "printf 'RC=%s\\n' \"$rc\"\n"
                "printf 'FAIL=%s\\n' \"$(cat -- \"$dest/failure\" 2>/dev/null || true)\"\n"
            )
            result = subprocess.run(
                ["bash", "-c", script],
                env={"PATH": "/usr/bin:/bin", "HOME": str(tmp / "home"),
                     "PLEB_STATE_HOME": str(tmp / "state")},
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("RC=1", result.stdout)
            self.assertIn(
                "release apt configuration must stay outside the operator apt directory",
                result.stdout,
            )

    def test_an_unparseable_uri_line_is_not_copied(self):
        suite = codename()
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            bindir = tmp / "bin"
            bindir.mkdir()
            (bindir / "apt-get").write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' \"'http://deb.debian.org/debian/dists/{suite}/InRelease' file 1\"\n"
                "printf '%s\\n' '://'\n"
                "exit 0\n"
            )
            (bindir / "apt-get").chmod(0o755)
            apt = write_apt(tmp, {"debian.sources": debian_sources(suite)})
            env = {k: v for k, v in os.environ.items() if not k.startswith("PLEBIAN_OS_")}
            env.update({
                "HOME": str(tmp / "home"),
                "PATH": f"{bindir}:/usr/bin:/bin",
                "PLEBIAN_OS_APT_SOURCES_ROOT": str(apt),
            })
            script = (
                "set -euo pipefail\n"
                "export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1\n"
                f"PLEB_STATE_HOME={str(tmp / 'state')!r}\n"
                f"source {str(UPDATE)!r}\n"
                "dest=$(mktemp -d)\n"
                "rc=0\n"
                "prepare_release_apt_config "
                f"\"$dest\" lifetime '' {suite!r} {str(apt)!r} || rc=$?\n"
                "printf 'RC=%s\\n' \"$rc\"\n"
                "printf 'FAIL=%s\\n' \"$(cat -- \"$dest/failure\" 2>/dev/null || true)\"\n"
                "printf '%s\\n' 'COPIED<<'\n"
                "for copied in \"$dest/sources.list.d\"/*; do\n"
                "  [ -f \"$copied\" ] || continue\n"
                "  printf '%s\\n' \"${copied##*/}\"\n"
                "done\n"
                "printf '%s\\n' '>>COPIED'\n"
                "rm -rf -- \"$dest\"\n"
            )
            result = subprocess.run(
                ["bash", "-c", script], env=env, text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            copied = result.stdout.split("COPIED<<\n", 1)[1].split(">>COPIED", 1)[0]
            self.assertNotIn("debian.sources", copied)
            self.assertIn("RC=1", result.stdout)

    def test_classification_uses_an_empty_private_list_directory(self):
        body = shell_function((ROOT / "provision" / "install-deps.sh").read_text(),
                              "prepare_release_apt_config")
        self.assertIn('-o "Dir::State::lists=$work/one/lists"', body)
        self.assertNotIn("/var/lib/apt/lists", body)
        # apt 3.0.4 prints the same URIs for an empty private lists directory
        # and for /var/lib/apt/lists. The source assertion is what fails if
        # classification is pointed at the operator cache.


def _deb(path: Path, name: str, version: str, arch: str, depends: str = "") -> None:
    root = path.parent / "build" / f"{name}_{version}"
    debian = root / "DEBIAN"
    debian.mkdir(parents=True)
    os.chmod(debian, 0o755)
    control = (
        f"Package: {name}\n"
        f"Version: {version}\n"
        f"Architecture: {arch}\n"
        "Maintainer: Plebian OS <release@example.invalid>\n"
        "Section: misc\n"
        "Priority: optional\n"
    )
    if depends:
        control += f"Depends: {depends}\n"
    control += "Description: fixture\n"
    (debian / "control").write_text(control)
    os.chmod(debian / "control", 0o644)
    subprocess.run(
        ["dpkg-deb", "--build", str(root), str(path)],
        check=True, text=True, capture_output=True,
    )


def _packages(repo: Path, debs: list[Path]) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    stanzas = []
    for deb in debs:
        target = repo / deb.name
        if target.resolve() != deb.resolve():
            target.write_bytes(deb.read_bytes())
        data = target.read_bytes()
        info = subprocess.run(
            ["dpkg-deb", "-f", str(target), "Package", "Version", "Architecture", "Depends"],
            check=True, text=True, capture_output=True,
        ).stdout.splitlines()
        fields = dict(line.split(": ", 1) for line in info)
        depends = f"Depends: {fields['Depends']}\n" if "Depends" in fields else ""
        stanzas.append(
            f"Package: {fields['Package']}\n"
            f"Version: {fields['Version']}\n"
            f"Architecture: {fields['Architecture']}\n"
            "Maintainer: Plebian OS <release@example.invalid>\n"
            "Installed-Size: 1\n"
            f"Filename: {target.name}\n"
            f"Size: {len(data)}\n"
            f"MD5sum: {hashlib.md5(data).hexdigest()}\n"
            f"SHA1: {hashlib.sha1(data).hexdigest()}\n"
            f"SHA256: {hashlib.sha256(data).hexdigest()}\n"
            "Section: misc\n"
            "Priority: optional\n"
            f"{depends}"
            "Description: fixture\n"
        )
    (repo / "Packages").write_text("\n".join(stanzas) + "\n")


def _config(path: Path, sources: dict[str, str]) -> None:
    (path / "sources.list.d").mkdir(parents=True)
    (path / "lists" / "partial").mkdir(parents=True)
    (path / "archives" / "partial").mkdir(parents=True)
    (path / "cache").mkdir()
    (path / "preferences.d").mkdir()
    (path / "apt.conf.d").mkdir()
    (path / "sources.list").write_text(sources.pop("sources.list", ""))
    (path / "preferences").write_text("")
    (path / "apt.conf").write_text(
        f'Dir::Etc::Parts "{path / "apt.conf.d"}";\n'
        'APT::Get::AllowUnauthenticated "false";\n'
        'Acquire::AllowInsecureRepositories "false";\n'
        'Acquire::AllowWeakRepositories "false";\n'
        'Acquire::AllowDowngradeToInsecureRepositories "false";\n'
        'Acquire::Check-Valid-Until "true";\n'
    )
    for name, text in sources.items():
        (path / "sources.list.d" / name).write_text(text)
    for directory in (path, path / "sources.list.d", path / "lists", path / "lists" / "partial",
                      path / "archives", path / "archives" / "partial", path / "cache",
                      path / "preferences.d", path / "apt.conf.d"):
        directory.chmod(0o755)


def _release_options() -> list[str]:
    function = shell_function(UPDATE.read_text(), "release_apt_get")
    return re.findall(r'-o "([^"]+)"', function)


class ReleaseAptCandidateTests(unittest.TestCase):
    def _run(self, tmp: Path, body: str, status: Path, extended: Path):
        env = {k: v for k, v in os.environ.items() if not k.startswith("PLEBIAN_OS_")}
        env.update({
            "HOME": str(tmp / "home"),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PLEBIAN_OS_DPKG_STATUS": str(status),
            "PLEBIAN_OS_APT_EXTENDED_STATES": str(extended),
        })
        script = (
            "set -euo pipefail\n"
            "export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1\n"
            f"PLEB_STATE_HOME={str(tmp / 'state')!r}\n"
            f"source {str(UPDATE)!r}\n"
            + body
        )
        return subprocess.run(
            ["bash", "-c", script], env=env, text=True, capture_output=True, check=False,
        )

    def test_third_party_version_and_pin_do_not_supply_release_packages(self):
        if shutil.which("dpkg-deb") is None or shutil.which("apt-cache") is None:
            self.skipTest("dpkg-deb and apt-cache are required")
        arch = subprocess.run(
            ["dpkg", "--print-architecture"], text=True, capture_output=True, check=True,
        ).stdout.strip()
        options = _release_options()
        self.assertIn("Dir::Etc::SourceList=$config/sources.list", options)
        self.assertIn("Dir::Etc::Preferences=$config/preferences", options)
        self.assertIn("Dir::State::lists=$config/lists", options)
        option_text = "\n".join(f'  -o "{option}" \\' for option in options)
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            debs = tmp / "debs"
            debs.mkdir()
            _deb(debs / "release-pkg_1.0.deb", "release-pkg", "1.0", arch)
            _deb(debs / "release-pkg_2.0.deb", "release-pkg", "2.0", arch)
            _deb(debs / "release-pkg_9.0.deb", "release-pkg", "9.0", arch)
            _deb(debs / "operator-pkg_1.0.deb", "operator-pkg", "1.0", arch)
            debian = tmp / "debian"
            third = tmp / "third"
            low_third = tmp / "low-third"
            _packages(debian, [debs / "release-pkg_1.0.deb"])
            _packages(third, [debs / "release-pkg_9.0.deb", debs / "operator-pkg_1.0.deb"])
            _packages(low_third, [debs / "release-pkg_1.0.deb"])
            # The pin case needs a Debian package newer than the third-party one.
            debian_newer = tmp / "debian-newer"
            _packages(debian_newer, [debs / "release-pkg_2.0.deb"])

            deb_cfg = tmp / "deb-config"
            both_cfg = tmp / "both-config"
            pin_cfg = tmp / "pin-config"
            _config(deb_cfg, {
                "sources.list": f"deb [trusted=yes] file://{debian} ./\n",
            })
            _config(both_cfg, {
                "sources.list": f"deb [trusted=yes] file://{debian} ./\n",
                "third.list": f"deb [trusted=yes] file://{third} ./\n",
            })
            _config(pin_cfg, {
                "sources.list": f"deb [trusted=yes] file://{debian_newer} ./\n",
                "third.list": f"deb [trusted=yes] file://{low_third} ./\n",
            })
            status = tmp / "status"
            status.write_text("")
            installed = tmp / "installed"
            installed.write_text(
                "Package: release-pkg\n"
                "Status: install ok installed\n"
                "Priority: optional\n"
                "Section: misc\n"
                "Installed-Size: 1\n"
                "Maintainer: Plebian OS <release@example.invalid>\n"
                f"Architecture: {arch}\n"
                "Version: 9.0\n"
                "Description: fixture\n"
                "\n"
                "Package: operator-pkg\n"
                "Status: install ok installed\n"
                "Priority: optional\n"
                "Section: misc\n"
                "Installed-Size: 1\n"
                "Maintainer: Plebian OS <release@example.invalid>\n"
                f"Architecture: {arch}\n"
                "Version: 1.0\n"
                "Description: fixture\n"
                "\n"
            )
            extended = tmp / "extended"
            extended.write_text("")
            before_status = installed.read_bytes()

            def policy(config: Path) -> str:
                result = self._run(
                    tmp,
                    f"config={str(config)!r}\n"
                    "release_apt_get \"$config\" update\n"
                    "apt-cache \\\n"
                    f"{option_text}\n"
                    "  policy release-pkg\n",
                    status, extended,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                return result.stdout

            isolated = policy(deb_cfg)
            self.assertIn("Candidate: 1.0", isolated)
            self.assertNotIn("Candidate: 9.0", isolated)
            self.assertNotIn(str(third), isolated)

            both = policy(both_cfg)
            self.assertIn("Candidate: 9.0", both)
            self.assertIn(str(third), both)

            unpinned = policy(pin_cfg)
            self.assertIn("Candidate: 2.0", unpinned)
            self.assertNotIn("Candidate: 1.0", unpinned)

            # The same lists, with an operator pin in place of the empty
            # preferences, select the lower third-party version. The release
            # command keeps the empty preferences file, so that pin does not apply.
            (pin_cfg / "preferences").write_text(
                "Package: release-pkg\nPin: version 1.0\nPin-Priority: 1001\n"
            )
            pinned_again = self._run(
                tmp,
                f"config={str(pin_cfg)!r}\n"
                "apt-cache \\\n"
                f"{option_text}\n"
                "  policy release-pkg\n",
                status, extended,
            )
            self.assertEqual(pinned_again.returncode, 0, pinned_again.stderr)
            self.assertIn("Candidate: 1.0", pinned_again.stdout)

            (pin_cfg / "preferences").write_text("")
            unpinned = self._run(
                tmp,
                f"config={str(pin_cfg)!r}\n"
                "apt-cache \\\n"
                f"{option_text}\n"
                "  policy release-pkg\n",
                status, extended,
            )
            self.assertEqual(unpinned.returncode, 0, unpinned.stderr)
            self.assertIn("Candidate: 2.0", unpinned.stdout)

            install = self._run(
                tmp,
                f"config={str(deb_cfg)!r}\n"
                "release_apt_get \"$config\" install -s -y release-pkg\n",
                installed, extended,
            )
            self.assertEqual(install.returncode, 0, install.stderr)
            self.assertIn("already the newest version (9.0)", install.stdout)
            self.assertIn("0 to remove", install.stdout)
            self.assertNotIn("operator-pkg", install.stdout)
            self.assertEqual(installed.read_bytes(), before_status)

    def test_a_preferences_directory_pin_is_consulted(self):
        if shutil.which("dpkg-deb") is None or shutil.which("apt-cache") is None:
            self.skipTest("dpkg-deb and apt-cache are required")
        arch = subprocess.run(
            ["dpkg", "--print-architecture"], text=True, capture_output=True, check=True,
        ).stdout.strip()
        options = _release_options()
        self.assertIn("Dir::Etc::PreferencesParts=$config/preferences.d", options)
        option_text = "\n".join(f'  -o "{option}" \\' for option in options)
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            debs = tmp / "debs"
            debs.mkdir()
            _deb(debs / "release-pkg_1.0.deb", "release-pkg", "1.0", arch)
            _deb(debs / "release-pkg_2.0.deb", "release-pkg", "2.0", arch)
            low = tmp / "low"
            high = tmp / "high"
            _packages(low, [debs / "release-pkg_1.0.deb"])
            _packages(high, [debs / "release-pkg_2.0.deb"])
            config = tmp / "config"
            _config(config, {
                "sources.list": f"deb [trusted=yes] file://{high} ./\n",
                "low.list": f"deb [trusted=yes] file://{low} ./\n",
            })
            (config / "preferences").write_text("")
            (config / "preferences.d" / "pin").write_text(
                "Package: release-pkg\nPin: version 1.0\nPin-Priority: 1001\n"
            )
            status = tmp / "status"
            status.write_text("")
            extended = tmp / "extended"
            extended.write_text("")
            result = self._run(
                tmp,
                f"config={str(config)!r}\n"
                "release_apt_get \"$config\" update\n"
                "apt-cache \\\n"
                f"{option_text}\n"
                "  policy release-pkg\n",
                status, extended,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Candidate: 1.0", result.stdout)
            self.assertNotIn("Candidate: 2.0", result.stdout)

    def test_sources_with_does_not_supply_a_release_package(self):
        if shutil.which("dpkg-deb") is None:
            self.skipTest("dpkg-deb is required")
        arch = subprocess.run(
            ["dpkg", "--print-architecture"], text=True, capture_output=True, check=True,
        ).stdout.strip()
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            debs = tmp / "debs"
            debs.mkdir()
            _deb(debs / "release-pkg_1.0.deb", "release-pkg", "1.0", arch)
            _deb(debs / "release-pkg_9.0.deb", "release-pkg", "9.0", arch)
            debian = tmp / "debian"
            _packages(debian, [debs / "release-pkg_1.0.deb"])
            config = tmp / "config"
            _config(config, {"sources.list": f"deb [trusted=yes] file://{debian} ./\n"})
            hostile = tmp / "hostile.conf"
            hostile.write_text(
                'APT::Sources::With { "' + str(debs / "release-pkg_9.0.deb") + '"; };\n'
                'DPkg::Post-Invoke { "echo HOSTHOOK"; };\n'
            )
            status = tmp / "status"
            status.write_text("")
            extended = tmp / "extended"
            extended.write_text("")
            direct = subprocess.run(
                [
                    "apt-get", "-s",
                    "-o", f"Dir::Etc::SourceList={config / 'sources.list'}",
                    "-o", f"Dir::Etc::SourceParts={config / 'sources.list.d'}",
                    "-o", f"Dir::State::lists={config / 'lists'}",
                    "-o", f"Dir::State::status={status}",
                    "-o", f"Dir::Cache={config / 'cache'}",
                    "install", "release-pkg",
                ],
                env={**os.environ, "APT_CONFIG": str(hostile), "DEBIAN_FRONTEND": "noninteractive"},
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(direct.returncode, 0, direct.stderr)
            self.assertIn("Inst release-pkg (9.0", direct.stdout)
            wrapped = self._run(
                tmp,
                f"config={str(config)!r}\n"
                "release_apt_get \"$config\" update\n"
                "release_apt_get \"$config\" -s install release-pkg\n",
                status, extended,
            )
            self.assertEqual(wrapped.returncode, 0, wrapped.stderr)
            self.assertNotIn("(9.0", wrapped.stdout)
            self.assertIn("1.0", wrapped.stdout)
            dumped = subprocess.run(
                ["bash", "-c",
                 'env -u APT_CONFIG APT_CONFIG="$1" apt-config dump DPkg::Post-Invoke',
                 "dump", str(config / "apt.conf")],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(dumped.returncode, 0, dumped.stderr)
            self.assertNotIn("HOSTHOOK", dumped.stdout)
            self.assertNotIn("qt-runtime", dumped.stdout)

    def test_a_debian_upgrade_does_not_remove_an_operator_package(self):
        if shutil.which("dpkg-deb") is None:
            self.skipTest("dpkg-deb is required")
        arch = subprocess.run(
            ["dpkg", "--print-architecture"], text=True, capture_output=True, check=True,
        ).stdout.strip()
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            debs = tmp / "debs"
            debs.mkdir()
            _deb(debs / "libdep-sim_1.0_all.deb", "libdep-sim", "1.0", "all")
            _deb(debs / "libdep-sim_2.0_all.deb", "libdep-sim", "2.0", "all")
            _deb(debs / "cuda-x_1.0_all.deb", "cuda-x", "1.0", "all", "libdep-sim (= 1.0)")
            _deb(debs / "release-pkg_1.0_all.deb", "release-pkg", "1.0", "all",
                 "libdep-sim (>= 2.0)")
            debian = tmp / "debian"
            _packages(debian, [debs / "libdep-sim_2.0_all.deb", debs / "release-pkg_1.0_all.deb"])
            config = tmp / "config"
            _config(config, {"sources.list": f"deb [trusted=yes] file://{debian} ./\n"})
            status = tmp / "status"
            status.write_text(
                "Package: libdep-sim\n"
                "Status: install ok installed\n"
                "Priority: optional\n"
                "Section: misc\n"
                "Installed-Size: 1\n"
                "Maintainer: Plebian OS <release@example.invalid>\n"
                "Architecture: all\n"
                "Version: 1.0\n"
                "Description: fixture\n"
                "\n"
                "Package: cuda-x\n"
                "Status: install ok installed\n"
                "Priority: optional\n"
                "Section: misc\n"
                "Installed-Size: 1\n"
                "Maintainer: Plebian OS <release@example.invalid>\n"
                "Architecture: all\n"
                "Version: 1.0\n"
                "Depends: libdep-sim (= 1.0)\n"
                "Description: fixture\n"
                "\n"
            )
            extended = tmp / "extended"
            extended.write_text("")
            install_log = tmp / "install.log"
            body = shell_function(DEPS.read_text(), "release_install")
            getter = shell_function(DEPS.read_text(), "release_apt_get")
            script = (
                "set -euo pipefail\n"
                + getter + "\n" + body + "\n"
                "warn() { printf 'WARN %s\\n' \"$*\" >&2; }\n"
                f"RELEASE_APT_CONFIG={str(config)!r}\n"
                "deps_apt() {\n"
                "  case \" $* \" in\n"
                "    *' -s '*) ;;\n"
                f"    *) printf '%s\\n' \"$*\" >> {str(install_log)!r} ;;\n"
                "  esac\n"
                "  release_apt_get \"$RELEASE_APT_CONFIG\" \"$@\"\n"
                "}\n"
                "release_apt_get \"$RELEASE_APT_CONFIG\" update\n"
                "release_install release-pkg\n"
            )
            result = self._run(tmp, script, status, extended)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("cuda-x", result.stderr)
            self.assertIn("those packages stay installed", result.stderr)
            self.assertFalse(install_log.exists(), result.stderr)
            self.assertEqual(status.read_text().count("Package: cuda-x"), 1)


class ReleaseAptRouteTests(unittest.TestCase):
    """A new release-path apt command has to go through the private configuration.

    Image build scripts are not on the guest release path. pleb and kilix
    live in other repositories; the updater invokes them, and those apt
    calls are recorded in STATE.md rather than routed here.
    """

    SCOPE = (
        "install-deps.sh",
        "plebian-os-update.sh",
        "plebian-os-provision.sh",
        "plebian-os-firstboot-attempt",
        "plebian-os-qt-runtime",
        "plebian-os-mpv-runtime",
        "plebian-os-ssh-server",
        "plebian-os-waydroid-setup",
        "plebian-os-nvidia-driver",
    )

    def test_every_release_path_apt_call_is_classified(self):
        unclassified = []
        seen = []
        for name in self.SCOPE:
            path = ROOT / "provision" / name
            self.assertTrue(path.is_file(), name)
            for number, line in enumerate(path.read_text().splitlines(), 1):
                if "apt-get" not in line and "aptitude" not in line:
                    continue
                why = self._reason(name, line.strip())
                seen.append((name, number, why))
                if why is None:
                    unclassified.append(f"{name}:{number}: {line.strip()}")
        self.assertFalse(unclassified, "\n".join(unclassified))
        self.assertGreaterEqual(len(seen), 20)

    def test_helpers_keep_their_own_private_configuration(self):
        ssh = (ROOT / "provision" / "plebian-os-ssh-server").read_text()
        self.assertIn('Dir::Etc::Parts "', ssh)
        self.assertIn('env["APT_CONFIG"]', ssh)
        self.assertIn("Dir::Etc::SourceList=/dev/null", ssh)
        firstboot = (ROOT / "provision" / "plebian-os-firstboot-attempt").read_text()
        self.assertIn("APT_CONFIG=", firstboot)
        self.assertIn("Dir::Etc::SourceList=/dev/null", firstboot)
        command = firstboot[firstboot.index("apt-get -y -f install"):]
        command = command[:command.index("rm -rf")]
        self.assertNotIn("--no-remove", command)
        qt = (ROOT / "provision" / "plebian-os-qt-runtime").read_text()
        mpv = (ROOT / "provision" / "plebian-os-mpv-runtime").read_text()
        self.assertNotIn('subprocess.run(["/usr/bin/apt-get"', qt)
        self.assertNotIn("subprocess.run(['/usr/bin/apt-get'", mpv)
        updater = (ROOT / "provision" / "plebian-os-update.sh").read_text()
        self.assertIn("PLEBIAN_OS_RELEASE_APT_CONFIG=$RELEASE_APT_CONFIG", updater)
        self.assertNotIn("build/lib.sh", updater)
        self.assertNotIn("build_vm_image.py", updater)
        self.assertNotIn("_prepare_removal_apt_config", updater)
        self.assertNotIn("release-apt-get.fn", updater)
        runner = updater[updater.index("root-owned when this step is elevated"):]
        runner = runner[:runner.index("\n}\n")]
        self.assertIn("\n_run_release_apt() {\n", runner)
        self.assertIn(
            'config="$(mktemp -d /tmp/plebian-os-removal-apt.XXXXXX)"', runner)
        self.assertIn('prepare_release_apt_config "$config"', runner)
        self.assertIn('release_apt_get "$config" "$@"', runner)
        self.assertNotIn('. "$1"', runner)
        self.assertNotIn("apt-get ", runner)
        simulated = updater[updater.index("\n_apt_simulated_removals() {\n"):]
        simulated = simulated[:simulated.index("\n}\n")]
        self.assertIn(
            "_run_release_apt -s remove -y --no-install-recommends",
            simulated)
        self.assertNotIn("$_REMOVAL_APT_CONFIG", simulated)
        self.assertNotIn("apt-get ", simulated)
        removal = updater[updater.index("\nremove_transaction_package_additions() {\n"):]
        removal = removal[:removal.index("\n}\n")]
        self.assertIn(
            "_run_release_apt remove -y --no-install-recommends",
            removal)
        self.assertIn("command -v apt-get", removal)
        self.assertNotIn("apt-get remove", removal)
        self.assertNotIn("apt-get -s remove", removal)
        self.assertNotIn("--no-remove", removal)
        provision = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
        self.assertIn('export PLEBIAN_OS_RELEASE_APT_CONFIG="$PROVISION_RELEASE_APT_CONFIG"', provision)
        self.assertIn('cp -a -- "$PROVISION_RELEASE_APT_CONFIG/indexes"', provision)
        self.assertNotIn('release_apt="$(mktemp -d "$state/.release-apt.XXXXXX")"', provision)

    def test_release_children_receive_the_pinned_machine_marker(self):
        updater = (ROOT / "provision" / "plebian-os-update.sh").read_text()
        stack = updater[updater.index("\nstack_env=("):]
        stack = stack[:stack.index("\n)")]
        self.assertIn('"PLEBIAN_OS_RELEASE_MODE=$PLEBIAN_OS_RELEASE_MODE"', stack)
        self.assertIn(
            '"PLEBIAN_OS_MACHINE_MARKER=/etc/plebian-os/build-info.env"', stack)
        provision = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
        install = provision[provision.index("\ninstall_env=("):]
        install = install[:install.index("\n)")]
        self.assertIn('"PLEBIAN_OS_RELEASE_MODE=$PLEBIAN_OS_RELEASE_MODE"', install)
        self.assertIn(
            '"PLEBIAN_OS_MACHINE_MARKER=/etc/plebian-os/build-info.env"', install)
        self.assertIn('"PLEBIAN_OS_MANAGED_INSTALL=1"', install)

    @staticmethod
    def _reason(name: str, text: str) -> str | None:
        if text.startswith("#"):
            return "comment"
        if name == "plebian-os-waydroid-setup":
            return "staged during provision and update, not executed on the release path"
        if name == "plebian-os-nvidia-driver":
            return "operator-facing helper, not called by release install, update, or first boot"
        if name in ("plebian-os-qt-runtime", "plebian-os-mpv-runtime"):
            if "apt_run(" in text or text.startswith("print(") or "Run apt-get" in text:
                return "release mode routes this through the private configuration"
            if (text.startswith('"""') or text.startswith("command = ")
                    or text.startswith('["/usr/bin/apt-get"')
                    or text.startswith("['/usr/bin/apt-get'")):
                return "argument list passed to apt_run"
            return None
        if name == "plebian-os-ssh-server":
            if "apt-get" in text:
                return "own Debian-only configuration, not release_apt_get"
            return None
        if name == "plebian-os-firstboot-attempt":
            if "apt-get -y -f install" in text:
                return "one Debian-only recovery install"
            if text.startswith("say ") or "apt-get -f install" in text or "One apt-get" in text:
                return "recovery message, not a second apt command"
            return None
        if "print-uris" in text:
            return "classification uses the private list directory"
        if text == "apt-get \\" or text.endswith("apt-get \\"):
            return "release_apt_get"
        if 'apt-get "$@"' in text:
            return "non-release deps_apt falls through to system apt"
        if text.startswith("echo "):
            return "dry-run text"
        if "deps_apt " in text and "warn" in text:
            return "install-deps update goes through deps_apt"
        if "indextargets" in text:
            return "non-install query; release mode does not use this branch"
        if "apt-get update -y" in text or "apt-get update against" in text or text.startswith("echo "):
            return "provisioner list refresh after operator sources were renamed aside"
        # Removal builds its configuration inside the child. A raw apt-get
        # remove stays unclassified, so the scanner still fails if system apt
        # comes back. A sourced release-apt-get.fn is the same failure.
        if ("apt-get -s remove" in text or "apt-get remove " in text
                or "release-apt-get.fn" in text):
            return None
        if "command -v" in text and "apt-get" in text:
            return "presence check"
        if "apt-get -f install" in text and ("die " in text or text.startswith("die ")):
            return "guidance text, not a command"
        if "Classification runs apt-get" in text:
            return "comment"
        return None


if __name__ == "__main__":
    unittest.main()
