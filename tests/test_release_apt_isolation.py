"""Release apt installs see only source files inside the Debian archive.

A signed third-party repository, including one that offers a higher version of
a release package, is left on disk and is not a candidate. Packages already
installed from it are not removed or downgraded.
"""

import hashlib
import json
import os
import re
import shlex
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
        'Dir::Etc::main "/dev/null";\n'
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
        """Operator apt.conf and apt.conf.d do not reach a prepared release apt.

        The configuration comes from prepare_release_apt_config. A bind-mounted
        /etc/apt holds Sources::With, the trust overrides, and a Pre-Invoke.
        Dir::Etc::main /dev/null and the empty Parts directory drop both files.
        Operator hooks stay out; the owned Qt pin is a preferences file and is
        covered by its own test.
        """
        if shutil.which("dpkg-deb") is None:
            self.skipTest("dpkg-deb is required")
        if shutil.which("unshare") is None:
            self.skipTest("unshare is not available")
        probe = subprocess.run(["unshare", "-rm", "true"], capture_output=True)
        if probe.returncode != 0:
            self.skipTest("unshare -rm is not available")
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            debs = tmp / "debs"
            debs.mkdir()
            _deb(debs / "libdep-sim_1.0_all.deb", "libdep-sim", "1.0", "all")
            _deb(debs / "libdep-sim_9.0_all.deb", "libdep-sim", "9.0", "all")
            debian = tmp / "debian"
            _packages(debian, [debs / "libdep-sim_1.0_all.deb"])
            suite = codename()
            apt = write_apt(tmp, {"debian.sources": debian_sources(suite)})
            dest = tmp / "dest"
            dest.mkdir()
            prepared = self._run(
                tmp,
                f"dest={str(dest)!r}\n"
                f"prepare_release_apt_config \"$dest\" lifetime '' {suite!r} {str(apt)!r}\n"
                "printf 'CONF<<\\n'\n"
                "cat -- \"$dest/apt.conf\"\n"
                "printf '\\n>>CONF\\n'\n",
                tmp / "status-unused", tmp / "extended-unused",
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            kept = dest
            conf = prepared.stdout.split("CONF<<\n", 1)[1].split(">>CONF", 1)[0]
            self.assertIn('Dir::Etc::main "/dev/null";', conf)
            self.assertIn("Dir::Etc::Parts ", conf)
            # The user namespace cannot setuid to _apt. This is test-only;
            # the prepared file still has the function's main and Parts lines.
            (kept / "apt.conf").write_text(
                (kept / "apt.conf").read_text() + 'APT::Sandbox::User "root";\n')
            # The candidate under test is the local Debian 1.0. The prepared
            # file keeps the apt.conf the function wrote.
            for copied in (kept / "sources.list.d").glob("*"):
                if copied.is_file():
                    copied.unlink()
            (kept / "sources.list").write_text(
                f"deb [trusted=yes] file://{debian} ./\n")
            hostile = tmp / "hostile-apt"
            (hostile / "apt.conf.d").mkdir(parents=True)
            (hostile / "sources.list.d").mkdir()
            higher = str(debs / "libdep-sim_9.0_all.deb")
            prehook = tmp / "prehook"
            parts_hook = tmp / "parts-hook"
            main_text = (
                f'APT::Sources::With {{ "{higher}"; }};\n'
                'APT::Get::AllowUnauthenticated "true";\n'
                'Acquire::AllowInsecureRepositories "true";\n'
                f'DPkg::Pre-Invoke {{ "touch {prehook}"; }};\n'
                'Dir::Bin::dpkg "/no/such/dpkg-from-main";\n'
            )
            (hostile / "apt.conf").write_text(main_text)
            (hostile / "apt.conf.d" / "99operator.conf").write_text(
                f'APT::Sources::With {{ "{higher}"; }};\n'
                'APT::Get::AllowUnauthenticated "true";\n'
                'Acquire::AllowInsecureRepositories "true";\n'
                f'DPkg::Pre-Invoke {{ "touch {parts_hook}"; }};\n'
                'Dir::Bin::dpkg "/no/such/dpkg-from-parts";\n'
            )
            (hostile / "sources.list").write_text(
                f"deb [trusted=yes] file://{debian} ./\n")
            status = tmp / "status"
            status.write_text("")
            extended = tmp / "extended"
            extended.write_text("")
            out = tmp / "out"
            out.mkdir()
            script = tmp / "probe.sh"
            script.write_text(
                "#!/bin/bash\n"
                "set -u\n"
                'mount --bind "$HOSTILE" /etc/apt || { echo MOUNT_FAILED >&2; exit 97; }\n'
                'mkdir -p "$EMPTY_PLEB"\n'
                'mount --bind "$EMPTY_PLEB" /etc/pleb || { echo MOUNT_PLEB_FAILED >&2; exit 97; }\n'
                "export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1\n"
                'export PLEBIAN_OS_DPKG_STATUS="$STATUS"\n'
                'export PLEBIAN_OS_APT_EXTENDED_STATES="$EXTENDED"\n'
                'export PLEB_STATE_HOME="$STATE"\n'
                'export DEBIAN_FRONTEND=noninteractive\n'
                'source "$UPDATE"\n'
                "set +e\n"
                'release_apt_get "$DEST" update >"$OUT/update.txt" 2>"$OUT/update.err"\n'
                "update_rc=$?\n"
                'plan="$(release_apt_get "$DEST" -s install libdep-sim 2>"$OUT/plan.err")"\n'
                "plan_rc=$?\n"
                "set -e\n"
                'printf "%s\\n" "$plan" >"$OUT/plan.txt"\n'
                'printf "UPDATE_RC=%s\\nPLAN_RC=%s\\n" "$update_rc" "$plan_rc" >"$OUT/rc"\n'
                'env -u APT_CONFIG APT_CONFIG="$DEST/apt.conf" apt-config dump '
                "APT::Get::AllowUnauthenticated Acquire::AllowInsecureRepositories "
                'DPkg::Pre-Invoke Dir::Bin::dpkg >"$OUT/dump.txt" 2>"$OUT/dump.err"\n'
            )
            script.chmod(0o755)
            ran = subprocess.run(
                ["unshare", "-rm", "bash", str(script)],
                env={
                    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                    "HOSTILE": str(hostile),
                    "STATUS": str(status),
                    "EXTENDED": str(extended),
                    "STATE": str(tmp / "state"),
                    "UPDATE": str(UPDATE),
                    "DEST": str(kept),
                    "OUT": str(out),
                    "EMPTY_PLEB": str(tmp / "empty-pleb"),
                    "HOME": str(tmp / "home"),
                    "LC_ALL": "C",
                },
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(ran.returncode, 0, ran.stderr + ran.stdout)
            plan = (out / "plan.txt").read_text()
            dump = (out / "dump.txt").read_text()
            rc_text = (out / "rc").read_text()
            self.assertIn("UPDATE_RC=0", rc_text, (out / "update.err").read_text())
            self.assertIn("PLAN_RC=0", rc_text, (out / "plan.err").read_text() + plan)
            self.assertIn("Inst libdep-sim (1.0", plan)
            self.assertNotIn("(9.0", plan)
            self.assertIn('APT::Get::AllowUnauthenticated "false";', dump)
            self.assertIn('Acquire::AllowInsecureRepositories "false";', dump)
            self.assertNotIn("/no/such/dpkg-from-main", dump)
            self.assertNotIn("/no/such/dpkg-from-parts", dump)
            self.assertNotIn("PREHOOK", dump)
            self.assertNotIn("touch", dump)
            self.assertNotIn("plebian-os-qt-runtime --verify", dump)
            self.assertFalse(prehook.exists(), plan)
            self.assertFalse(parts_hook.exists(), plan)
            self.assertEqual(list((kept / "apt.conf.d").iterdir()), [])

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


class ReleaseAptGuardTests(unittest.TestCase):
    """The seat's surviving mutants have to fail against the real functions."""

    def _prepare(self, apt: Path, dest: Path) -> subprocess.CompletedProcess:
        script = (
            "set -euo pipefail\n"
            "export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1\n"
            f"PLEB_STATE_HOME={str(dest.parent / 'state')!r}\n"
            f"source {str(UPDATE)!r}\n"
            f"prepare_release_apt_config {str(dest)!r} lifetime '' {codename()!r} {str(apt)!r} || true\n"
            "printf 'CONF<<\\n'\n"
            "cat -- \"$1/apt.conf\"\n"
            "printf '\\n>>CONF\\n'\n"
        )
        # $1 is not set. Write the conf path into the script instead.
        script = script.replace('cat -- "$1/apt.conf"', f"cat -- {str(dest / 'apt.conf')!r}")
        env = {k: v for k, v in os.environ.items() if not k.startswith("PLEBIAN_OS_")}
        env.update({
            "HOME": str(dest.parent / "home"),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        })
        return subprocess.run(
            ["bash", "-c", script], env=env, text=True, capture_output=True, check=False,
        )

    def test_only_the_root_owned_qt_pin_is_copied(self):
        if shutil.which("unshare") is None:
            self.skipTest("unshare is not available")
        probe = subprocess.run(["unshare", "-rm", "true"], capture_output=True)
        if probe.returncode != 0:
            self.skipTest("unshare -rm is not available")
        if os.geteuid() == 0:
            self.skipTest("the user-owned rejection runs as a non-root user")
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            owned = tmp / "owned-apt"
            (owned / "preferences.d").mkdir(parents=True)
            (owned / "sources.list.d").mkdir()
            (owned / "sources.list").write_text("")
            pin = owned / "preferences.d" / "plebian-os-qt-runtime"
            pin.write_text("Package: libqt\nPin: version *+plebian*\nPin-Priority: 1001\n")
            pin.chmod(0o644)
            (owned / "preferences.d" / "operator-pin").write_text(
                "Package: *\nPin-Priority: 1001\n")
            dest = tmp / "user-dest"
            dest.mkdir()
            user_prepare = self._prepare(owned, dest)
            self.assertEqual(user_prepare.returncode, 0, user_prepare.stderr)
            self.assertFalse((dest / "preferences.d" / "plebian-os-qt-runtime").exists())
            self.assertFalse((dest / "preferences.d" / "operator-pin").exists())
            self.assertIn('Dir::Etc::main "/dev/null";', (dest / "apt.conf").read_text())

            debs = tmp / "debs"
            debs.mkdir()
            _deb(debs / "libqt_1.0+plebian_all.deb", "libqt", "1.0+plebian", "all")
            _deb(debs / "libqt_1.1_all.deb", "libqt", "1.1", "all")
            _deb(debs / "app_1.0_all.deb", "app", "1.0", "all")
            _deb(debs / "app_2.0_all.deb", "app", "2.0", "all", "libqt (>= 1.1)")
            debian = tmp / "debian"
            _packages(debian, [debs / "libqt_1.1_all.deb", debs / "app_2.0_all.deb"])
            status = tmp / "status"
            status.write_text(
                "Package: libqt\nStatus: install ok installed\nPriority: optional\n"
                "Section: misc\nInstalled-Size: 1\n"
                "Maintainer: Plebian OS <release@example.invalid>\n"
                "Architecture: all\nVersion: 1.0+plebian\nDescription: fixture\n\n"
                "Package: app\nStatus: install ok installed\nPriority: optional\n"
                "Section: misc\nInstalled-Size: 1\n"
                "Maintainer: Plebian OS <release@example.invalid>\n"
                "Architecture: all\nVersion: 1.0\nDescription: fixture\n\n"
            )
            extended = tmp / "extended"
            extended.write_text("")
            script = tmp / "pin.sh"
            script.write_text(r"""#!/bin/bash
set -u
mkdir -p "$EMPTY_PLEB"
mount --bind "$EMPTY_PLEB" /etc/pleb || { echo MOUNT_PLEB_FAILED >&2; exit 97; }
export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1
export PLEB_STATE_HOME="$STATE"
export PLEBIAN_OS_DPKG_STATUS="$STATUS"
export PLEBIAN_OS_APT_EXTENDED_STATES="$EXTENDED"
export DEBIAN_FRONTEND=noninteractive
source "$UPDATE"
write_pin() {
  local apt="$1" mode="$2" kind="$3"
  mkdir -p "$apt/preferences.d" "$apt/sources.list.d"
  : >"$apt/sources.list"
  case "$kind" in
    file)
      printf '%s\n' 'Package: libqt' 'Pin: version *+plebian*' 'Pin-Priority: 1001' \
        >"$apt/preferences.d/plebian-os-qt-runtime"
      chmod "$mode" "$apt/preferences.d/plebian-os-qt-runtime"
      ;;
    link)
      printf '%s\n' 'Package: libqt' >"$apt/real-pin"
      ln -s "$apt/real-pin" "$apt/preferences.d/plebian-os-qt-runtime"
      ;;
  esac
  printf '%s\n' 'Package: *' 'Pin-Priority: 1001' >"$apt/preferences.d/operator-pin"
  chmod 644 "$apt/preferences.d/operator-pin"
}
try_copy() {
  local label="$1" apt="$2" dest="$3"
  mkdir -p "$dest"
  prepare_release_apt_config "$dest" lifetime "" "$CODENAME" "$apt" || true
  if [ -f "$dest/preferences.d/plebian-os-qt-runtime" ] && [ ! -L "$dest/preferences.d/plebian-os-qt-runtime" ]; then
    printf '%s copied\n' "$label"
  else
    printf '%s absent\n' "$label"
  fi
  if [ -e "$dest/preferences.d/operator-pin" ]; then
    printf '%s operator\n' "$label"
  fi
  if [ -n "$(find "$dest/apt.conf.d" -type f -print -quit 2>/dev/null)" ]; then
    printf '%s hook\n' "$label"
  fi
}
try_copy good "$GOOD" "$GOOD_DEST" 644 file
try_copy writable "$WRITABLE" "$WRITABLE_DEST" 666 file
try_copy groupwrite "$GROUP" "$GROUP_DEST" 664 file
try_copy symlink "$LINK" "$LINK_DEST" 644 link
chmod -R a+rX "$GOOD_DEST"
printf '%s\n' 'APT::Sandbox::User "root";' >>"$GOOD_DEST/apt.conf"
: >"$GOOD_DEST/sources.list.d/.keep" || true
find "$GOOD_DEST/sources.list.d" -type f ! -name .keep -delete
printf '%s\n' "deb [trusted=yes] file://$DEBIAN ./" >"$GOOD_DEST/sources.list"
set +e
release_apt_get "$GOOD_DEST" update >"$OUT/update.txt" 2>"$OUT/update.err"
update_rc=$?
plan="$(release_apt_get "$GOOD_DEST" -s install app 2>"$OUT/plan.err")"
plan_rc=$?
set -e
printf '%s\n' "$plan" >"$OUT/plan.txt"
printf 'UPDATE_RC=%s\nPLAN_RC=%s\n' "$update_rc" "$plan_rc" >"$OUT/rc"
""")
            # The heredoc above is a template; fill the try_copy calls properly.
            text = script.read_text()
            text = text.replace(
                'try_copy good "$GOOD" "$GOOD_DEST" 644 file\n'
                'try_copy writable "$WRITABLE" "$WRITABLE_DEST" 666 file\n'
                'try_copy groupwrite "$GROUP" "$GROUP_DEST" 664 file\n'
                'try_copy symlink "$LINK" "$LINK_DEST" 644 link\n',
                'write_pin "$GOOD" 644 file; try_copy good "$GOOD" "$GOOD_DEST"\n'
                'write_pin "$WRITABLE" 666 file; try_copy writable "$WRITABLE" "$WRITABLE_DEST"\n'
                'write_pin "$GROUP" 664 file; try_copy groupwrite "$GROUP" "$GROUP_DEST"\n'
                'write_pin "$LINK" 644 link; try_copy symlink "$LINK" "$LINK_DEST"\n',
            )
            script.write_text(text)
            script.chmod(0o755)
            out = tmp / "out"
            out.mkdir()
            env = {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "HOME": str(tmp / "home"),
                "LC_ALL": "C",
                "UPDATE": str(UPDATE),
                "EMPTY_PLEB": str(tmp / "empty-pleb"),
                "STATE": str(tmp / "state"),
                "STATUS": str(status),
                "EXTENDED": str(extended),
                "CODENAME": codename(),
                "DEBIAN": str(debian),
                "OUT": str(out),
                "GOOD": str(tmp / "good"),
                "GOOD_DEST": str(tmp / "good-dest"),
                "WRITABLE": str(tmp / "writable"),
                "WRITABLE_DEST": str(tmp / "writable-dest"),
                "GROUP": str(tmp / "group"),
                "GROUP_DEST": str(tmp / "group-dest"),
                "LINK": str(tmp / "link"),
                "LINK_DEST": str(tmp / "link-dest"),
            }
            ran = subprocess.run(
                ["unshare", "-rm", "bash", str(script)],
                env=env, text=True, capture_output=True, check=False,
            )
            detail = ran.stdout + ran.stderr
            self.assertEqual(ran.returncode, 0, detail)
            self.assertIn("good copied", detail)
            self.assertNotIn("good operator", detail)
            self.assertNotIn("good hook", detail)
            self.assertIn("writable absent", detail)
            self.assertIn("groupwrite absent", detail)
            self.assertIn("symlink absent", detail)
            plan = (out / "plan.txt").read_text()
            rc_text = (out / "rc").read_text()
            self.assertIn("UPDATE_RC=0", rc_text, (out / "update.err").read_text())
            self.assertNotIn("Inst libqt [1.0+plebian] (1.1)", plan, plan)
            self.assertNotEqual(
                rc_text.split("PLAN_RC=", 1)[1].splitlines()[0], "0", plan)

            bare = tmp / "bare"
            _config(bare, {"sources.list": f"deb [trusted=yes] file://{debian} ./\n"})
            (bare / "preferences").write_text("")
            options = _release_options()
            option_text = "\n".join(f'  -o "{option}" \\' for option in options)
            control = self._run_release(
                tmp, bare, status, extended,
                "release_apt_get \"$config\" update\n"
                "release_apt_get \"$config\" -s install app\n",
            )
            self.assertEqual(control.returncode, 0, control.stderr)
            inst = [line for line in control.stdout.splitlines() if line.startswith("Inst libqt ")]
            self.assertTrue(inst, control.stdout)
            self.assertIn("1.0+plebian", inst[0])
            self.assertIn("(1.1 ", inst[0])

    def _run_release(self, tmp, config, status, extended, body):
        env = {k: v for k, v in os.environ.items() if not k.startswith("PLEBIAN_OS_")}
        env.update({
            "HOME": str(tmp / "home"),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PLEBIAN_OS_DPKG_STATUS": str(status),
            "PLEBIAN_OS_APT_EXTENDED_STATES": str(extended),
            "DEBIAN_FRONTEND": "noninteractive",
        })
        script = (
            "set -euo pipefail\n"
            "export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1\n"
            f"PLEB_STATE_HOME={str(tmp / 'state')!r}\n"
            f"source {str(UPDATE)!r}\n"
            f"config={str(config)!r}\n"
            + body
        )
        return subprocess.run(
            ["bash", "-c", script], env=env, text=True, capture_output=True, check=False,
        )

    def test_helper_apt_run_uses_the_private_config_and_refuses_without_it(self):
        import importlib.machinery
        import importlib.util
        from unittest import mock

        def load(name):
            path = ROOT / "provision" / name
            loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"), str(path))
            spec = importlib.util.spec_from_loader(loader.name, loader)
            module = importlib.util.module_from_spec(spec)
            loader.exec_module(module)
            return module

        with tempfile.TemporaryDirectory() as td:
            config = Path(td) / "config"
            _config(config, {})
            for name in ("plebian-os-qt-runtime", "plebian-os-mpv-runtime"):
                module = load(name)
                recorded = {}

                def fake_run(argv, **kwargs):
                    recorded["argv"] = list(argv)
                    recorded["env"] = kwargs.get("env")
                    completed = subprocess.CompletedProcess(argv, 0, "", "")
                    return completed

                with mock.patch.object(module.subprocess, "run", fake_run):
                    with mock.patch.dict(os.environ, {
                        "PLEBIAN_OS_RELEASE_MODE": "1",
                        "PLEBIAN_OS_RELEASE_APT_CONFIG": str(config),
                    }, clear=False):
                        module.apt_run(["/usr/bin/apt-get", "install", "libdep-sim"])
                self.assertIn(f"Dir::Etc::SourceList={config}/sources.list", recorded["argv"])
                self.assertEqual(recorded["env"]["APT_CONFIG"], str(config / "apt.conf"))
                recorded.clear()
                with mock.patch.object(module.subprocess, "run", fake_run):
                    with mock.patch.dict(os.environ, {"PLEBIAN_OS_RELEASE_MODE": "0"}, clear=False):
                        os.environ.pop("PLEBIAN_OS_RELEASE_APT_CONFIG", None)
                        module.apt_run(["/usr/bin/apt-get", "install", "libdep-sim"])
                self.assertEqual(recorded["argv"], ["/usr/bin/apt-get", "install", "libdep-sim"])
                self.assertNotIn("Dir::Etc::SourceList", " ".join(recorded["argv"]))
                called = []

                def refuse_run(*args, **kwargs):
                    called.append(args)
                    raise AssertionError("system apt was called")

                with mock.patch.object(module.subprocess, "run", refuse_run):
                    with mock.patch.dict(os.environ, {"PLEBIAN_OS_RELEASE_MODE": "1"}, clear=False):
                        os.environ.pop("PLEBIAN_OS_RELEASE_APT_CONFIG", None)
                        with self.assertRaises(SystemExit) as raised:
                            module.apt_run(["/usr/bin/apt-get", "install", "libdep-sim"])
                self.assertIn("refusing the system apt configuration", str(raised.exception))
                self.assertEqual(called, [])

    def test_install_deps_refuses_a_missing_release_config(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            record = tmp / "apt-record"
            bindir = tmp / "bin"
            bindir.mkdir()
            apt = bindir / "apt-get"
            apt.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> {record!s}\nexit 0\n")
            apt.chmod(0o755)
            missing = tmp / "missing"
            missing.mkdir()
            sources = tmp / "apt"
            (sources / "sources.list.d").mkdir(parents=True)
            (sources / "sources.list").write_text("")
            env = {k: v for k, v in os.environ.items() if not k.startswith("PLEBIAN_OS_")}
            env.update({
                "PATH": f"{bindir}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}",
                "HOME": str(tmp / "home"),
                "DRY_RUN": "1",
                "PLEBIAN_OS_RELEASE_MODE": "1",
                "PLEBIAN_OS_RELEASE_APT_CONFIG": str(missing),
                "PLEBIAN_OS_APT_SOURCES_ROOT": str(sources),
                "PLEBIAN_OS_INSTALL_UV": "0",
                "LC_ALL": "C",
            })
            result = subprocess.run(
                ["bash", str(DEPS), "--dry-run"],
                env=env, text=True, capture_output=True, check=False,
            )
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("release apt configuration is missing", result.stderr)
            self.assertIn("refusing the system apt configuration", result.stderr)
            self.assertFalse(record.exists(), result.stdout)
            self.assertNotIn("+ apt-get", result.stdout)

    def test_operator_proxies_are_copied_and_hostile_values_are_dropped(self):
        """Validated proxies reach the private apt.conf. Nothing else does.

        A proxy in apt.conf, one in apt.conf.d, and a per-host DIRECT are
        copied. A proxy auto-detect program is not run. A value that carries
        a Pre-Invoke payload is dropped. Debian's package is still chosen
        over a higher third-party version.
        """
        if shutil.which("dpkg-deb") is None:
            self.skipTest("dpkg-deb is required")
        if shutil.which("unshare") is None:
            self.skipTest("unshare is not available")
        probe = subprocess.run(["unshare", "-rm", "true"], capture_output=True)
        if probe.returncode != 0:
            self.skipTest("unshare -rm is not available")
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            debs = tmp / "debs"
            debs.mkdir()
            _deb(debs / "libdep-sim_1.0_all.deb", "libdep-sim", "1.0", "all")
            _deb(debs / "libdep-sim_9.0_all.deb", "libdep-sim", "9.0", "all")
            debian = tmp / "debian"
            _packages(debian, [debs / "libdep-sim_1.0_all.deb"])
            suite = codename()
            apt = write_apt(tmp, {"debian.sources": debian_sources(suite)})
            ran_marker = tmp / "autodetect-ran"
            script_path = tmp / "autodetect"
            script_path.write_text(f"#!/bin/sh\necho RAN >> {ran_marker}\n")
            script_path.chmod(0o755)
            prehook = tmp / "prehook"
            parts_hook = tmp / "parts-hook"
            inject_hook = tmp / "inject-hook"
            higher = str(debs / "libdep-sim_9.0_all.deb")
            hostile = tmp / "hostile-apt"
            (hostile / "apt.conf.d").mkdir(parents=True)
            (hostile / "sources.list.d").mkdir()
            (hostile / "sources.list").write_text("")
            (hostile / "apt.conf").write_text(
                'Acquire::http::Proxy "http://proxy.example:3128";\n'
                'Acquire::ftp::Proxy "http://evil.example; DPkg::Pre-Invoke {touch '
                f'{inject_hook}' + '}";\n'
                f'Acquire::http::Proxy-Auto-Detect "{script_path}";\n'
                f'Acquire::http::ProxyAutoDetect "{script_path}";\n'
                'Acquire::http::Proxy::bad_host "DIRECT";\n'
                f'APT::Sources::With {{ "{higher}"; }};\n'
                'APT::Get::AllowUnauthenticated "true";\n'
                'Acquire::AllowInsecureRepositories "true";\n'
                f'DPkg::Pre-Invoke {{ "touch {prehook}"; }};\n'
                'Dir::Bin::dpkg "/no/such/dpkg-from-main";\n'
            )
            (hostile / "apt.conf.d" / "99proxy.conf").write_text(
                'Acquire::https::Proxy "http://parts.example:8080";\n'
                'Acquire::http::Proxy::deb.debian.org "DIRECT";\n'
                'Acquire::ftp::Proxy::mirror.example "http://mirror.example"; '
                f'DPkg::Pre-Invoke {{ "touch {inject_hook}"; }};\n'
                f'APT::Sources::With {{ "{higher}"; }};\n'
                f'DPkg::Pre-Invoke {{ "touch {parts_hook}"; }};\n'
                'Dir::Bin::dpkg "/no/such/dpkg-from-parts";\n'
            )
            dest = tmp / "dest"
            dest.mkdir()
            status = tmp / "status"
            status.write_text("")
            extended = tmp / "extended"
            extended.write_text("")
            out = tmp / "out"
            out.mkdir()
            probe_sh = tmp / "probe.sh"
            probe_sh.write_text(
                "#!/bin/bash\n"
                "set -u\n"
                'mount --bind "$HOSTILE" /etc/apt || { echo MOUNT_FAILED >&2; exit 97; }\n'
                'mkdir -p "$EMPTY_PLEB"\n'
                'mount --bind "$EMPTY_PLEB" /etc/pleb || { echo MOUNT_PLEB_FAILED >&2; exit 97; }\n'
                "export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1\n"
                'export PLEBIAN_OS_DPKG_STATUS="$STATUS"\n'
                'export PLEBIAN_OS_APT_EXTENDED_STATES="$EXTENDED"\n'
                'export PLEB_STATE_HOME="$STATE"\n'
                "export DEBIAN_FRONTEND=noninteractive\n"
                'source "$UPDATE"\n'
                'mkdir -p "$DEST"\n'
                'prepare_release_apt_config "$DEST" lifetime "" "$CODENAME" "$APT" '
                '>"$OUT/prepare.txt" 2>"$OUT/prepare.err"\n'
                'prep_rc=$?\n'
                'printf "PREP_RC=%s\\n" "$prep_rc" >"$OUT/prep"\n'
                '[ "$prep_rc" = 0 ] || exit 0\n'
                'printf "%s\\n" \'APT::Sandbox::User "root";\' >>"$DEST/apt.conf"\n'
                'find "$DEST/sources.list.d" -type f -delete\n'
                'printf "%s\\n" "deb [trusted=yes] file://$DEBIAN ./" >"$DEST/sources.list"\n'
                "set +e\n"
                'release_apt_get "$DEST" update >"$OUT/update.txt" 2>"$OUT/update.err"\n'
                "update_rc=$?\n"
                'plan="$(release_apt_get "$DEST" -s install libdep-sim 2>"$OUT/plan.err")"\n'
                "plan_rc=$?\n"
                "set -e\n"
                'printf "%s\\n" "$plan" >"$OUT/plan.txt"\n'
                'printf "UPDATE_RC=%s\\nPLAN_RC=%s\\n" "$update_rc" "$plan_rc" >"$OUT/rc"\n'
            )
            probe_sh.chmod(0o755)
            ran = subprocess.run(
                ["unshare", "-rm", "bash", str(probe_sh)],
                env={
                    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                    "HOSTILE": str(hostile),
                    "STATUS": str(status),
                    "EXTENDED": str(extended),
                    "STATE": str(tmp / "state"),
                    "UPDATE": str(UPDATE),
                    "DEST": str(dest),
                    "APT": str(apt),
                    "OUT": str(out),
                    "EMPTY_PLEB": str(tmp / "empty-pleb"),
                    "DEBIAN": str(debian),
                    "CODENAME": suite,
                    "HOME": str(tmp / "home"),
                    "LC_ALL": "C",
                },
                text=True, capture_output=True, check=False, timeout=90,
            )
            detail = ran.stdout + ran.stderr
            prep_err = (out / "prepare.err").read_text() if (out / "prepare.err").exists() else ""
            self.assertEqual(ran.returncode, 0, detail + prep_err)
            self.assertIn("PREP_RC=0", (out / "prep").read_text(), prep_err)
            conf = (dest / "apt.conf").read_text()
            self.assertIn('Acquire::http::Proxy "http://proxy.example:3128";', conf)
            self.assertIn('Acquire::https::Proxy "http://parts.example:8080";', conf)
            self.assertIn('Acquire::http::Proxy::deb.debian.org "DIRECT";', conf)
            self.assertIn('Acquire::ftp::Proxy::mirror.example "http://mirror.example";', conf)
            self.assertNotIn("evil.example", conf)
            self.assertNotIn("Pre-Invoke", conf)
            self.assertNotIn("Proxy-Auto-Detect", conf)
            self.assertNotIn("ProxyAutoDetect", conf)
            self.assertNotIn(str(script_path), conf)
            self.assertNotIn("bad_host", conf)
            self.assertNotIn("Sources::With", conf)
            self.assertNotIn("/no/such/dpkg", conf)
            self.assertIn('APT::Get::AllowUnauthenticated "false";', conf)
            self.assertNotIn('AllowUnauthenticated "true"', conf)
            self.assertIn("dropping proxy setting Acquire::ftp::Proxy", prep_err)
            self.assertIn("dropping proxy setting Acquire::http::Proxy::bad_host", prep_err)
            self.assertFalse(ran_marker.exists(), detail)
            self.assertFalse(prehook.exists(), detail)
            self.assertFalse(parts_hook.exists(), detail)
            self.assertFalse(inject_hook.exists(), detail)
            self.assertEqual(list((dest / "apt.conf.d").iterdir()), [])
            plan = (out / "plan.txt").read_text()
            rc_text = (out / "rc").read_text()
            self.assertIn("UPDATE_RC=0", rc_text, (out / "update.err").read_text())
            self.assertIn("PLAN_RC=0", rc_text, (out / "plan.err").read_text() + plan)
            self.assertIn("Inst libdep-sim (1.0", plan)
            self.assertNotIn("(9.0", plan)

    def test_authenticated_proxy_userinfo_is_carried_and_not_logged(self):
        """debian-installer's user:pass form is copied. A quote or semicolon is not.

        Percent-encoding is the password form that stays. The warning names
        the key. No credential is printed. A carried userinfo makes apt.conf
        mode 0600.
        """
        if shutil.which("unshare") is None:
            self.skipTest("unshare is not available")
        probe = subprocess.run(["unshare", "-rm", "true"], capture_output=True)
        if probe.returncode != 0:
            self.skipTest("unshare -rm is not available")
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            suite = codename()
            apt = write_apt(tmp, {"debian.sources": debian_sources(suite)})
            hostile = tmp / "hostile-apt"
            (hostile / "apt.conf.d").mkdir(parents=True)
            (hostile / "sources.list.d").mkdir()
            (hostile / "sources.list").write_text("")
            (hostile / "apt.conf").write_text(
                'Acquire::http::Proxy "http://alice:s3cret-token@proxy.example:3128/";\n'
                'Acquire::https::Proxy "http://bob:p%40ss-token@proxy.example:3128/";\n'
                'Acquire::http::Proxy::deb.debian.org "http://dave:s3cret;semi@proxy.example/";\n'
            )
            quote_dump = tmp / "quote.dump"
            quote_dump.write_bytes(
                b'Acquire::ftp::Proxy\thttp://carol:s3cret"quote@proxy.example/\n'
            )
            stubbin = tmp / "stubbin"
            stubbin.mkdir()
            stub = stubbin / "apt-config"
            stub.write_text('#!/bin/sh\ncat "$QUOTE_DUMP"\n')
            stub.chmod(0o755)
            dest = tmp / "dest"
            dest2 = tmp / "dest2"
            dest.mkdir()
            dest2.mkdir()
            out = tmp / "out"
            out.mkdir()
            probe_sh = tmp / "probe.sh"
            probe_sh.write_text(
                "#!/bin/bash\n"
                "set -u\n"
                'mount --bind "$HOSTILE" /etc/apt || { echo MOUNT_FAILED >&2; exit 97; }\n'
                'mkdir -p "$EMPTY_PLEB"\n'
                'mount --bind "$EMPTY_PLEB" /etc/pleb || { echo MOUNT_PLEB_FAILED >&2; exit 97; }\n'
                "export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1\n"
                'export PLEB_STATE_HOME="$STATE"\n'
                "export DEBIAN_FRONTEND=noninteractive\n"
                'source "$UPDATE"\n'
                'prepare_release_apt_config "$DEST" lifetime "" "$CODENAME" "$APT" '
                '>"$OUT/prepare.txt" 2>"$OUT/prepare.err"\n'
                'printf "PREP_RC=%s\\n" "$?" >"$OUT/prep"\n'
                'stat -c %a "$DEST/apt.conf" >"$OUT/mode"\n'
                'export PATH="$STUBBIN:$PATH"\n'
                'export QUOTE_DUMP\n'
                'prepare_release_apt_config "$DEST2" lifetime "" "$CODENAME" "$APT" '
                '>"$OUT/quote.txt" 2>"$OUT/quote.err"\n'
                'printf "QUOTE_RC=%s\\n" "$?" >"$OUT/quote.rc"\n'
                'stat -c %a "$DEST2/apt.conf" >"$OUT/quote.mode"\n'
            )
            probe_sh.chmod(0o755)
            ran = subprocess.run(
                ["unshare", "-rm", "bash", str(probe_sh)],
                env={
                    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                    "HOSTILE": str(hostile),
                    "EMPTY_PLEB": str(tmp / "empty-pleb"),
                    "STATE": str(tmp / "state"),
                    "UPDATE": str(UPDATE),
                    "DEST": str(dest),
                    "DEST2": str(dest2),
                    "APT": str(apt),
                    "OUT": str(out),
                    "CODENAME": suite,
                    "STUBBIN": str(stubbin),
                    "QUOTE_DUMP": str(quote_dump),
                    "HOME": str(tmp / "home"),
                    "LC_ALL": "C",
                },
                text=True, capture_output=True, check=False, timeout=90,
            )
            detail = ran.stdout + ran.stderr
            prep_out = (out / "prepare.txt").read_text() if (out / "prepare.txt").exists() else ""
            prep_err = (out / "prepare.err").read_text() if (out / "prepare.err").exists() else ""
            quote_out = (out / "quote.txt").read_text() if (out / "quote.txt").exists() else ""
            quote_err = (out / "quote.err").read_text() if (out / "quote.err").exists() else ""
            logged = detail + prep_out + prep_err + quote_out + quote_err
            self.assertEqual(ran.returncode, 0, logged)
            self.assertIn("PREP_RC=0", (out / "prep").read_text(), prep_err)
            self.assertIn("QUOTE_RC=0", (out / "quote.rc").read_text(), quote_err)
            conf = (dest / "apt.conf").read_text()
            self.assertIn(
                'Acquire::http::Proxy "http://alice:s3cret-token@proxy.example:3128/";',
                conf)
            self.assertIn(
                'Acquire::https::Proxy "http://bob:p%40ss-token@proxy.example:3128/";',
                conf)
            self.assertNotIn("s3cret;semi", conf)
            self.assertNotIn('s3cret"quote', conf)
            self.assertIn("dropping proxy setting Acquire::http::Proxy::deb.debian.org", prep_err)
            self.assertIn("dropping proxy setting Acquire::ftp::Proxy", quote_err)
            self.assertNotIn("s3cret", logged)
            self.assertNotIn("p%40ss-token", logged)
            self.assertEqual((out / "mode").read_text().strip(), "600")
            self.assertEqual((out / "quote.mode").read_text().strip(), "644")
            quoted = (dest2 / "apt.conf").read_text()
            self.assertNotIn("carol", quoted)
            self.assertNotIn("s3cret", quoted)

    def test_an_unreachable_debian_archive_is_reported(self):
        """A release update that cannot fetch Debian says so, and names no proxy value.

        apt-get update without --error-on=any exits 0 when the fetch fails.
        install-deps and the updater both pass that flag and refuse.
        """
        if shutil.which("unshare") is None:
            self.skipTest("unshare is not available")
        probe = subprocess.run(["unshare", "-rm", "true"], capture_output=True)
        if probe.returncode != 0:
            self.skipTest("unshare -rm is not available")
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            suite = codename()
            apt = write_apt(tmp, {"debian.sources": debian_sources(suite)})
            hostile = tmp / "hostile-apt"
            (hostile / "apt.conf.d").mkdir(parents=True)
            (hostile / "sources.list.d").mkdir()
            (hostile / "sources.list").write_text("")
            (hostile / "apt.conf").write_text(
                'Acquire::https::Proxy "http://alice:s3cret-token@127.0.0.1:9";\n'
                'Acquire::http::Proxy "http://alice:s3cret-token@127.0.0.1:9";\n'
            )
            dest = tmp / "dest"
            dest.mkdir()
            status = tmp / "status"
            status.write_text("")
            extended = tmp / "extended"
            extended.write_text("")
            out = tmp / "out"
            out.mkdir()
            probe_sh = tmp / "probe.sh"
            probe_sh.write_text(
                "#!/bin/bash\n"
                "set -u\n"
                'mount --bind "$HOSTILE" /etc/apt || { echo MOUNT_FAILED >&2; exit 97; }\n'
                'mkdir -p "$EMPTY_PLEB"\n'
                'mount --bind "$EMPTY_PLEB" /etc/pleb || { echo MOUNT_PLEB_FAILED >&2; exit 97; }\n'
                "export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1\n"
                'export PLEB_STATE_HOME="$STATE"\n'
                'export PLEBIAN_OS_DPKG_STATUS="$STATUS"\n'
                'export PLEBIAN_OS_APT_EXTENDED_STATES="$EXTENDED"\n'
                "export DEBIAN_FRONTEND=noninteractive\n"
                "export PLEBIAN_OS_RELEASE_MODE=1\n"
                'source "$UPDATE"\n'
                'prepare_release_apt_config "$DEST" lifetime "" "$CODENAME" "$APT" '
                '>"$OUT/prepare.txt" 2>"$OUT/prepare.err"\n'
                'printf "PREP_RC=%s\\n" "$?" >"$OUT/prep"\n'
                'stat -c %a "$DEST/apt.conf" >"$OUT/mode"\n'
                'printf "%s\\n" \'APT::Sandbox::User "root";\' >>"$DEST/apt.conf"\n'
                "export RELEASE_APT_CONFIG=\"$DEST\"\n"
                "set +e\n"
                'env PLEBIAN_OS_RELEASE_MODE=1 PLEBIAN_OS_RELEASE_APT_CONFIG="$DEST" '
                'PLEBIAN_OS_DPKG_STATUS="$STATUS" PLEBIAN_OS_APT_EXTENDED_STATES="$EXTENDED" '
                'PLEBIAN_OS_APT_SOURCES_ROOT="$APT" DEBIAN_FRONTEND=noninteractive '
                'bash "$DEPS" >"$OUT/deps.txt" 2>"$OUT/deps.err"\n'
                'printf "DEPS_RC=%s\\n" "$?" >"$OUT/deps.rc"\n'
                '( warm_release_apt_indexes >"$OUT/warm.txt" 2>"$OUT/warm.err" )\n'
                'printf "WARM_RC=%s\\n" "$?" >"$OUT/warm.rc"\n'
            )
            probe_sh.chmod(0o755)
            ran = subprocess.run(
                ["unshare", "-rm", "bash", str(probe_sh)],
                env={
                    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                    "HOSTILE": str(hostile),
                    "EMPTY_PLEB": str(tmp / "empty-pleb"),
                    "STATE": str(tmp / "state"),
                    "STATUS": str(status),
                    "EXTENDED": str(extended),
                    "UPDATE": str(UPDATE),
                    "DEPS": str(DEPS),
                    "DEST": str(dest),
                    "APT": str(apt),
                    "OUT": str(out),
                    "CODENAME": suite,
                    "HOME": str(tmp / "home"),
                    "LC_ALL": "C",
                },
                text=True, capture_output=True, check=False, timeout=120,
            )
            detail = ran.stdout + ran.stderr
            prep_err = (out / "prepare.err").read_text() if (out / "prepare.err").exists() else ""
            deps_out = (out / "deps.txt").read_text() if (out / "deps.txt").exists() else ""
            deps_err = (out / "deps.err").read_text() if (out / "deps.err").exists() else ""
            warm_out = (out / "warm.txt").read_text() if (out / "warm.txt").exists() else ""
            warm_err = (out / "warm.err").read_text() if (out / "warm.err").exists() else ""
            logged = "\n".join((detail, prep_err, deps_out, deps_err, warm_out, warm_err))
            self.assertEqual(ran.returncode, 0, logged)
            self.assertIn("PREP_RC=0", (out / "prep").read_text(), prep_err)
            self.assertEqual((out / "mode").read_text().strip(), "600", prep_err)
            phrase = "could not reach the Debian archive; check the network connection and the apt proxy"
            for name, text, rc_name in (
                ("deps", deps_err, "deps.rc"),
                ("warm", warm_err, "warm.rc"),
            ):
                rc = (out / rc_name).read_text()
                self.assertNotIn("=0", rc, name + "\n" + logged)
                self.assertIn(phrase, text, name + "\n" + logged)
                self.assertTrue(
                    "Failed to fetch" in text or "Unable to connect" in text or "Could not connect" in text,
                    name + "\n" + logged)
            self.assertNotIn("s3cret-token", logged)
            self.assertNotIn("s3cret", prep_err)

    def test_a_non_proxy_acquire_key_with_a_url_is_not_carried(self):
        """A URL value does not make an arbitrary Acquire key a proxy.

        Acquire::http::Proxy-Auto-Detect set to http://x matches the proxy
        URL rule. The key check is what drops it. The real prepare function
        is what this runs.
        """
        if shutil.which("unshare") is None:
            self.skipTest("unshare is not available")
        probe = subprocess.run(["unshare", "-rm", "true"], capture_output=True)
        if probe.returncode != 0:
            self.skipTest("unshare -rm is not available")
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            suite = codename()
            apt = write_apt(tmp, {"debian.sources": debian_sources(suite)})
            hostile = tmp / "hostile-apt"
            (hostile / "apt.conf.d").mkdir(parents=True)
            (hostile / "sources.list.d").mkdir()
            (hostile / "sources.list").write_text("")
            (hostile / "apt.conf").write_text(
                'Acquire::http::Proxy "http://proxy.example:3128";\n'
                'Acquire::http::Proxy-Auto-Detect "http://x";\n'
                'Acquire::https::Timeout "http://x";\n'
            )
            dest = tmp / "dest"
            dest.mkdir()
            out = tmp / "out"
            out.mkdir()
            probe_sh = tmp / "probe.sh"
            probe_sh.write_text(
                "#!/bin/bash\n"
                "set -u\n"
                'mount --bind "$HOSTILE" /etc/apt || { echo MOUNT_FAILED >&2; exit 97; }\n'
                'mkdir -p "$EMPTY_PLEB"\n'
                'mount --bind "$EMPTY_PLEB" /etc/pleb || { echo MOUNT_PLEB_FAILED >&2; exit 97; }\n'
                "export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1\n"
                'export PLEB_STATE_HOME="$STATE"\n'
                'source "$UPDATE"\n'
                "LC_ALL=C env -u APT_CONFIG apt-config dump --no-empty "
                "--format '%f%N%v%n' >\"$OUT/dump.txt\"\n"
                'mkdir -p "$DEST"\n'
                'prepare_release_apt_config "$DEST" lifetime "" "$CODENAME" "$APT" '
                '>"$OUT/prepare.txt" 2>"$OUT/prepare.err"\n'
                'printf "PREP_RC=%s\\n" "$?" >"$OUT/prep"\n'
            )
            probe_sh.chmod(0o755)
            ran = subprocess.run(
                ["unshare", "-rm", "bash", str(probe_sh)],
                env={
                    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                    "HOSTILE": str(hostile),
                    "STATE": str(tmp / "state"),
                    "UPDATE": str(UPDATE),
                    "DEST": str(dest),
                    "APT": str(apt),
                    "OUT": str(out),
                    "EMPTY_PLEB": str(tmp / "empty-pleb"),
                    "CODENAME": suite,
                    "HOME": str(tmp / "home"),
                    "LC_ALL": "C",
                },
                text=True, capture_output=True, check=False, timeout=90,
            )
            detail = ran.stdout + ran.stderr
            prep_err = (out / "prepare.err").read_text() if (out / "prepare.err").exists() else ""
            self.assertEqual(ran.returncode, 0, detail + prep_err)
            self.assertIn("PREP_RC=0", (out / "prep").read_text(), prep_err)
            dump = (out / "dump.txt").read_text()
            self.assertIn("Acquire::http::Proxy-Auto-Detect", dump)
            self.assertIn("http://x", dump)
            conf = (dest / "apt.conf").read_text()
            self.assertIn('Acquire::http::Proxy "http://proxy.example:3128";', conf)
            self.assertNotIn("Proxy-Auto-Detect", conf)
            self.assertNotIn("Timeout", conf)
            self.assertNotIn("http://x", conf)

    def test_qt_verify_fails_unprivileged_and_passes_when_elevated(self):
        """The real helper reads a root-only state directory.

        The state path is the helper's own hardcoded directory. An unprivileged
        uid gets EACCES. Namespace root, which is what elevation is inside
        this user namespace, verifies the same directory. The helper is the
        provision script, copied only so that uid can execute it.
        """
        if shutil.which("unshare") is None or shutil.which("setpriv") is None:
            self.skipTest("unshare and setpriv are required")
        probe = subprocess.run(
            ["unshare", "--map-auto", "--map-root-user", "-m", "true"],
            capture_output=True,
        )
        if probe.returncode != 0:
            self.skipTest("unshare --map-auto is not available")
        architecture = subprocess.run(
            ["/usr/bin/dpkg", "--print-architecture"],
            text=True, capture_output=True, check=True,
        ).stdout.strip()
        triplet = {"amd64": "x86_64-linux-gnu", "arm64": "aarch64-linux-gnu"}.get(architecture)
        if triplet is None:
            self.skipTest(f"no Qt runtime paths for {architecture}")
        packages = {"libqt5gui5t64": "5.15.15", "libqt6gui6": "6.8.2"}
        library_paths = []
        for name, qt in packages.items():
            major = qt.split(".")[0]
            library_paths.extend([
                f"/usr/lib/{triplet}/libQt{major}Gui.so.{qt}",
                f"/usr/lib/{triplet}/libQt{major}XcbQpa.so.{qt}",
                f"/usr/lib/{triplet}/qt{major}/plugins/platforms/libqxcb.so",
            ])
        if any(not Path(path).is_file() for path in library_paths):
            self.skipTest("selected Qt libraries are not installed")
        if not Path("/usr/bin/dpkg-query").exists():
            self.skipTest("dpkg-query is required")
        if not Path("/etc/apt/preferences.d/plebian-os-qt-runtime").exists():
            self.skipTest("the Qt preference path is not present to mount over")
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            os.chmod(tmp, 0o755)
            helper = tmp / "plebian-os-qt-runtime"
            helper.write_bytes((ROOT / "provision" / "plebian-os-qt-runtime").read_bytes())
            helper.chmod(0o755)
            records = []
            mounts = []
            for name, qt in packages.items():
                major = qt.split(".")[0]
                version = qt + "+dfsg-1+plebianrc6.1"
                files = []
                for relative in (
                    f"/usr/lib/{triplet}/libQt{major}Gui.so.{qt}",
                    f"/usr/lib/{triplet}/libQt{major}XcbQpa.so.{qt}",
                    f"/usr/lib/{triplet}/qt{major}/plugins/platforms/libqxcb.so",
                ):
                    data = f"fixture:{relative}".encode()
                    source = tmp / "files" / relative.lstrip("/")
                    source.parent.mkdir(parents=True, exist_ok=True)
                    source.write_bytes(data)
                    source.chmod(0o644)
                    files.append({
                        "path": relative,
                        "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    })
                    mounts.append((source, relative))
                records.append({
                    "Package": name,
                    "Version": version,
                    "Architecture": architecture,
                    "qt": qt,
                    "path": f"{name}.deb",
                    "bytes": 4,
                    "sha256": hashlib.sha256(b"deb" + name.encode()).hexdigest(),
                    "files": files,
                })
            for path in tmp.rglob("*"):
                if path.is_dir():
                    path.chmod(0o755)
            pin = tmp / "pin"
            pin.write_text("".join(
                f"Package: {record['Package']}\nPin: version {record['Version']}\n"
                f"Pin-Priority: 1001\n\n"
                for record in records
            ))
            pin.chmod(0o644)
            state = tmp / "state"
            state.mkdir()
            (state / "RUNTIME.json").write_text(json.dumps(records))
            (state / "RUNTIME.json").chmod(0o644)
            state.chmod(0o700)
            stub = tmp / "dpkg-query"
            cases = "\n".join(
                f"  {record['Package']}) printf 'installed\\n{record['Version']}' ;;"
                for record in records
            )
            stub.write_text(
                "#!/bin/sh\n"
                "pkg=\n"
                "for arg in \"$@\"; do pkg=$arg; done\n"
                "case \"$pkg\" in\n"
                f"{cases}\n"
                "  *) echo unknown >&2; exit 1 ;;\n"
                "esac\n"
            )
            stub.chmod(0o755)
            lines = [
                "#!/bin/bash",
                "set -u",
                f"mount --bind {shlex.quote(str(state))} /var/lib/plebian-os/qt-runtime"
                " || { echo MOUNT_STATE >&2; exit 97; }",
                f"mount --bind {shlex.quote(str(pin))} /etc/apt/preferences.d/plebian-os-qt-runtime"
                " || { echo MOUNT_PIN >&2; exit 97; }",
                f"mount --bind {shlex.quote(str(stub))} /usr/bin/dpkg-query"
                " || { echo MOUNT_DPKG >&2; exit 97; }",
            ]
            for source, target in mounts:
                lines.append(
                    f"mount --bind {shlex.quote(str(source))} {shlex.quote(target)}"
                    " || { echo MOUNT_FILE >&2; exit 97; }"
                )
            lines.append(
                f"{shlex.quote(str(helper))} --verify >{shlex.quote(str(tmp / 'elev.out'))}"
                f" 2>{shlex.quote(str(tmp / 'elev.err'))}; echo elev_rc=$?"
            )
            lines.append(
                "setpriv --reuid=1 --regid=1 --clear-groups --inh-caps=-all "
                f"{shlex.quote(str(helper))} --verify >{shlex.quote(str(tmp / 'user.out'))}"
                f" 2>{shlex.quote(str(tmp / 'user.err'))}; echo user_rc=$?"
            )
            script = tmp / "run.sh"
            script.write_text("\n".join(lines) + "\n")
            script.chmod(0o755)
            ran = subprocess.run(
                ["unshare", "--map-auto", "--map-root-user", "-m", "bash", str(script)],
                text=True, capture_output=True, check=False, timeout=60,
            )
            detail = ran.stdout + ran.stderr
            self.assertEqual(ran.returncode, 0, detail)
            self.assertIn("elev_rc=0", ran.stdout, detail)
            self.assertIn("user_rc=1", ran.stdout, detail)
            self.assertIn(
                "Plebian-OS selected Qt runtime verified",
                (tmp / "elev.out").read_text(),
            )
            user_err = (tmp / "user.err").read_text()
            self.assertIn("Permission denied", user_err)
            self.assertIn("/var/lib/plebian-os/qt-runtime/RUNTIME.json", user_err)
            self.assertNotIn("verified", (tmp / "user.out").read_text())

    def test_the_private_qt_pin_is_copied_again_after_it_changes(self):
        """A Qt hop rewrites the operator pin. The private copy follows it.

        The same owner and mode checks apply. A group-writable pin, a pin
        owned by another uid, a symlink, and an absent pin are not copied.
        A qualifying pin that cannot be copied fails the stage.
        """
        if shutil.which("unshare") is None:
            self.skipTest("unshare is not available")
        probe = subprocess.run(
            ["unshare", "--map-auto", "--map-root-user", "-m", "true"],
            capture_output=True,
        )
        if probe.returncode != 0:
            self.skipTest("unshare --map-auto is not available")
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            apt = tmp / "apt"
            (apt / "preferences.d").mkdir(parents=True)
            (apt / "apt.conf.d").mkdir()
            dest = tmp / "dest"
            (dest / "preferences.d").mkdir(parents=True)
            out = tmp / "out"
            out.mkdir()
            probe_sh = tmp / "probe.sh"
            probe_sh.write_text(r"""#!/bin/bash
set -u
mkdir -p "$EMPTY_PLEB"
mount --bind "$EMPTY_PLEB" /etc/pleb || { echo MOUNT_PLEB_FAILED >&2; exit 97; }
export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1
export PLEB_STATE_HOME="$STATE"
source "$UPDATE"
rc=0
env -u RELEASE_APT_CONFIG PLEBIAN_OS_RELEASE_MODE=1 refresh_release_qt_pin || rc=$?
printf '%s\n' "$rc" >"$OUT/missing-config"
export PLEBIAN_OS_RELEASE_MODE=1
export RELEASE_APT_CONFIG="$DEST"
export PLEBIAN_OS_APT_SOURCES_ROOT="$APT"
write_pin() {
  local text="$1" mode="$2"
  printf '%s\n' "$text" >"$APT/preferences.d/plebian-os-qt-runtime"
  chmod "$mode" "$APT/preferences.d/plebian-os-qt-runtime"
}
snap() {
  cp -a -- "$DEST/preferences.d/plebian-os-qt-runtime" "$OUT/$1"
}
write_pin $'Package: libqt\nPin: version 1.0+plebian\nPin-Priority: 1001' 644
refresh_release_qt_pin || { echo FIRST_COPY_FAILED >&2; exit 1; }
snap first
write_pin $'Package: libqt\nPin: version 1.0+plebian2\nPin-Priority: 1001' 644
refresh_release_qt_pin || { echo RECOPY_FAILED >&2; exit 1; }
snap rewrite
write_pin $'Package: libqt\nPin: version 1.0+plebian3\nPin-Priority: 1001' 664
refresh_release_qt_pin || { echo GROUP_FAILED >&2; exit 1; }
snap group
write_pin $'Package: libqt\nPin: version 1.0+plebian4\nPin-Priority: 1001' 644
chown 1:1 "$APT/preferences.d/plebian-os-qt-runtime" || { echo CHOWN_FAILED >&2; exit 1; }
refresh_release_qt_pin || { echo OWNER_FAILED >&2; exit 1; }
snap owner
printf '%s\n' 'Package: libqt' 'Pin: version 1.0+plebian5' >"$APT/real-pin"
chmod 644 "$APT/real-pin"
rm -f -- "$APT/preferences.d/plebian-os-qt-runtime"
ln -s "$APT/real-pin" "$APT/preferences.d/plebian-os-qt-runtime"
refresh_release_qt_pin || { echo LINK_FAILED >&2; exit 1; }
snap link
rm -f -- "$APT/preferences.d/plebian-os-qt-runtime"
refresh_release_qt_pin || { echo ABSENT_FAILED >&2; exit 1; }
snap absent
printf '%s\n' 'operator pin' >"$APT/preferences.d/operator-pin"
chmod 644 "$APT/preferences.d/operator-pin"
printf '%s\n' 'hook' >"$APT/apt.conf.d/93plebian-os-qt-runtime"
chmod 644 "$APT/apt.conf.d/93plebian-os-qt-runtime"
write_pin $'Package: libqt\nPin: version 1.0+plebian6\nPin-Priority: 1001' 644
refresh_release_qt_pin || { echo LAST_COPY_FAILED >&2; exit 1; }
if [ -e "$DEST/preferences.d/operator-pin" ] || [ -e "$DEST/apt.conf.d/93plebian-os-qt-runtime" ]; then
  echo EXTRA_COPIED >&2
  exit 1
fi
snap last
rm -rf -- "$DEST/preferences.d"
printf '%s\n' 'not a directory' >"$DEST/preferences.d"
rc=0
refresh_release_qt_pin || rc=$?
printf '%s\n' "$rc" >"$OUT/fail-rc"
""")
            probe_sh.chmod(0o755)
            ran = subprocess.run(
                ["unshare", "--map-auto", "--map-root-user", "-m", "bash", str(probe_sh)],
                env={
                    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                    "HOME": str(tmp / "home"),
                    "LC_ALL": "C",
                    "UPDATE": str(UPDATE),
                    "EMPTY_PLEB": str(tmp / "empty-pleb"),
                    "STATE": str(tmp / "state"),
                    "APT": str(apt),
                    "DEST": str(dest),
                    "OUT": str(out),
                },
                text=True, capture_output=True, check=False, timeout=60,
            )
            detail = ran.stdout + ran.stderr
            self.assertEqual(ran.returncode, 0, detail)
            self.assertNotEqual((out / "missing-config").read_text().strip(), "0", detail)
            self.assertIn("1.0+plebian\n", (out / "first").read_text())
            self.assertNotIn("plebian2", (out / "first").read_text())
            self.assertIn("1.0+plebian2", (out / "rewrite").read_text())
            self.assertEqual((out / "rewrite").read_text(), (out / "group").read_text())
            self.assertEqual((out / "rewrite").read_text(), (out / "owner").read_text())
            self.assertEqual((out / "rewrite").read_text(), (out / "link").read_text())
            self.assertEqual((out / "rewrite").read_text(), (out / "absent").read_text())
            self.assertIn("1.0+plebian6", (out / "last").read_text())
            self.assertNotEqual((out / "fail-rc").read_text().strip(), "0")
            self.assertEqual(oct((out / "rewrite").stat().st_mode & 0o777), "0o644")


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
        self.assertIn('Dir::Etc::main "/dev/null";', ssh)
        self.assertIn('Dir::Etc::Parts "', ssh)
        self.assertIn('env["APT_CONFIG"]', ssh)
        self.assertIn("Dir::Etc::SourceList=/dev/null", ssh)
        firstboot = (ROOT / "provision" / "plebian-os-firstboot-attempt").read_text()
        self.assertIn('Dir::Etc::main "/dev/null";', firstboot)
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
        self.assertIn("declare -f copy_release_qt_pin", runner)
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
        for name in ("qt_runtime_command", "mpv_runtime_command"):
            body = shell_function(updater, name)
            self.assertIn(
                'prefix=(env "PLEBIAN_OS_RELEASE_MODE=1" '
                '"PLEBIAN_OS_RELEASE_APT_CONFIG=$RELEASE_APT_CONFIG")',
                body)
            self.assertIn("refusing the system apt configuration", body)
        refresh = shell_function(updater, "refresh_os_dependencies")
        self.assertIn(
            '${PLEBIAN_OS_RELEASE_APT_CONFIG:+"PLEBIAN_OS_RELEASE_APT_CONFIG=$PLEBIAN_OS_RELEASE_APT_CONFIG"}',
            refresh)
        elevated = '"${elevate[@]}" $PLEBIAN_OS_SBINDIR/plebian-os-qt-runtime --verify'
        self.assertIn(elevated, refresh)
        self.assertLess(refresh.index("run_package_step_in_its_own_session"), refresh.index(elevated))
        self.assertNotIn("if ! $PLEBIAN_OS_SBINDIR/plebian-os-qt-runtime --verify", refresh)
        qt_done = updater.index('die "selected Qt runtime could not be installed/verified"')
        before_deps = updater[qt_done:updater.index("\nrefresh_os_dependencies\n", qt_done)]
        self.assertIn("refresh_release_qt_pin", before_deps)
        self.assertNotIn("prepare_release_apt_config", before_deps)
        prepared = shell_function(updater, "prepare_release_apt_config")
        self.assertIn('Dir::Etc::main "/dev/null";', prepared)
        self.assertIn('Dir::Etc::Parts \\"$dest/apt.conf.d\\"', prepared)
        self.assertIn("copy_release_qt_pin", prepared)
        self.assertNotIn("apt.conf.d/*", prepared)
        self.assertNotIn("93plebian-os-qt-runtime", prepared)
        pin_copy = shell_function(updater, "copy_release_qt_pin")
        self.assertIn("preferences.d/plebian-os-qt-runtime", pin_copy)
        self.assertIn("8#$qt_mode", pin_copy)
        self.assertNotIn("93plebian-os-qt-runtime", pin_copy)
        for name in ("copy_release_qt_pin", "prepare_release_apt_config"):
            bodies = [
                shell_function((ROOT / "provision" / script).read_text(), name)
                for script in ("install-deps.sh", "plebian-os-update.sh", "plebian-os-provision.sh")
            ]
            self.assertEqual(bodies[0], bodies[1], name)
            self.assertEqual(bodies[0], bodies[2], name)
        self.assertIn("apt-config dump", prepared)
        self.assertIn("dropping proxy setting", prepared)
        self.assertNotIn("Proxy-Auto-Detect", prepared)
        self.assertNotIn("ProxyAutoDetect", prepared)
        self.assertIn("([A-Za-z0-9._~%!$&()*+,=:-]+@)?", prepared)
        self.assertIn("--error-on=any", shell_function(updater, "warm_release_apt_indexes"))
        self.assertIn(
            "could not reach the Debian archive; check the network connection and the apt proxy",
            shell_function(updater, "warm_release_apt_indexes"))
        deps = (ROOT / "provision" / "install-deps.sh").read_text()
        self.assertIn("--error-on=any", deps)
        self.assertIn(
            "could not reach the Debian archive; check the network connection and the apt proxy",
            deps)
        provision = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
        self.assertNotIn('release_apt_get "$PROVISION_RELEASE_APT_CONFIG" update', provision)
        self.assertNotIn("release_apt_get \"$RELEASE_APT_CONFIG\" update", provision)

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
