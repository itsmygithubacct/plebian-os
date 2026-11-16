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
            plans = [line for line in result.stdout.splitlines() if "+ apt-get" in line]
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


def _deb(path: Path, name: str, version: str, arch: str) -> None:
    root = path.parent / "build" / f"{name}_{version}"
    debian = root / "DEBIAN"
    debian.mkdir(parents=True)
    os.chmod(debian, 0o755)
    (debian / "control").write_text(
        f"Package: {name}\n"
        f"Version: {version}\n"
        f"Architecture: {arch}\n"
        "Maintainer: Plebian OS <release@example.invalid>\n"
        "Section: misc\n"
        "Priority: optional\n"
        "Description: fixture\n"
    )
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
            ["dpkg-deb", "-f", str(target), "Package", "Version", "Architecture"],
            check=True, text=True, capture_output=True,
        ).stdout.splitlines()
        fields = dict(line.split(": ", 1) for line in info)
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
            "Description: fixture\n"
        )
    (repo / "Packages").write_text("\n".join(stanzas) + "\n")


def _config(path: Path, sources: dict[str, str]) -> None:
    (path / "sources.list.d").mkdir(parents=True)
    (path / "lists" / "partial").mkdir(parents=True)
    (path / "archives" / "partial").mkdir(parents=True)
    (path / "cache").mkdir()
    (path / "preferences.d").mkdir()
    (path / "sources.list").write_text(sources.pop("sources.list", ""))
    (path / "preferences").write_text("")
    for name, text in sources.items():
        (path / "sources.list.d" / name).write_text(text)


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


if __name__ == "__main__":
    unittest.main()
