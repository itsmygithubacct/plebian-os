"""An operator apt source does not block a release update.

The lifetime gate used to list every configured index, so a CUDA repository
refused the update before anything was installed. Release apt operations now
use a private configuration that contains only Debian source files. A host
whose release sources are themselves outside the archive is still refused,
and that refusal still happens before the update changes the installed stack.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPDATE_PATH = ROOT / "provision" / "plebian-os-update.sh"


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


CUDA_LIST = (
    "deb [signed-by=/usr/share/keyrings/cuda-archive-keyring.gpg] "
    "https://developer.download.nvidia.com/compute/cuda/repos/debian13/x86_64/ /\n"
)


def write_apt(tmp: Path, parts: dict[str, str]) -> Path:
    apt = tmp / "apt"
    (apt / "sources.list.d").mkdir(parents=True)
    (apt / "sources.list").write_text("")
    for name, text in parts.items():
        (apt / "sources.list.d" / name).write_text(text)
    return apt


class AptProvenanceGuidanceTests(unittest.TestCase):
    def _run(self, tmp: Path, body: str, release_mode: str, path_prefix: Path | None = None):
        env = {k: v for k, v in os.environ.items() if not k.startswith("PLEBIAN_OS_")}
        path = os.environ.get("PATH", "/usr/bin:/bin")
        if path_prefix is not None:
            path = f"{path_prefix}:{path}"
        env.update({
            "HOME": str(tmp / "home"),
            "PATH": path,
            "TMPDIR": str(tmp),
            "PLEBIAN_OS_APT_SOURCES_ROOT": str(tmp / "apt"),
            "PLEBIAN_OS_RELEASE_MODE": release_mode,
            "PLEBIAN_OS_APT_SNAPSHOT": "",
        })
        script = (
            "set -euo pipefail\n"
            "export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1\n"
            f"PLEB_STATE_HOME={str(tmp / 'state')!r}\n"
            f"source {str(UPDATE_PATH)!r}\n"
            f"PLEBIAN_OS_RELEASE_MODE={release_mode}\n"
            + body
        )
        return subprocess.run(
            ["bash", "-c", script], env=env, text=True, capture_output=True, check=False,
        )

    def test_cuda_source_does_not_block_the_preflight(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            apt = write_apt(tmp, {
                "debian.sources": debian_sources(codename()),
                "cuda-debian13-x86_64.list": CUDA_LIST,
            })
            before = (apt / "sources.list.d" / "cuda-debian13-x86_64.list").read_bytes()
            result = self._run(tmp, "preflight_release_apt_provenance\necho passed\n", "1")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("passed", result.stdout)
            self.assertIn(
                "cuda-debian13-x86_64.list is left unchanged and is not used "
                "to install release packages",
                result.stdout,
            )
            self.assertNotIn("disable each source above", result.stderr)
            self.assertNotIn("re-enable the source afterwards", result.stderr)
            self.assertNotIn("outside the Debian archive", result.stderr)
            self.assertEqual(
                (apt / "sources.list.d" / "cuda-debian13-x86_64.list").read_bytes(),
                before,
            )

    def test_debian_only_indexes_pass_the_preflight(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            write_apt(tmp, {"debian.sources": debian_sources(codename())})
            result = self._run(tmp, "preflight_release_apt_provenance\necho passed\n", "1")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("passed", result.stdout)
            self.assertNotIn("left unchanged", result.stdout)

    def test_development_closures_are_not_preflighted(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            write_apt(tmp, {"cuda-debian13-x86_64.list": CUDA_LIST})
            bindir = tmp / "bin"
            bindir.mkdir()
            marker = tmp / "apt-called"
            (bindir / "apt-get").write_text(
                "#!/bin/sh\nprintf '%s\\n' called >> " + repr(str(marker)) + "\nexit 99\n"
            )
            (bindir / "apt-get").chmod(0o755)
            result = self._run(
                tmp, "preflight_release_apt_provenance\necho passed\n", "0", bindir,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("passed", result.stdout)
            self.assertFalse(marker.exists())

    def test_a_host_with_no_debian_source_is_still_refused(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            write_apt(tmp, {"cuda-debian13-x86_64.list": CUDA_LIST})
            result = self._run(tmp, "preflight_release_apt_provenance\necho passed\n", "1")
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("passed", result.stdout)
            self.assertIn(
                "release apt provenance contains an index outside the Debian archive",
                result.stderr,
            )
            self.assertIn("developer.download.nvidia.com", result.stderr)
            self.assertNotIn("disable each source above", result.stderr)
            self.assertNotIn("re-enable the source afterwards", result.stderr)

    def test_a_non_debian_suite_is_still_refused(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            write_apt(tmp, {
                "sid.list": "deb https://deb.debian.org/debian sid main\n",
            })
            result = self._run(tmp, "preflight_release_apt_provenance\necho passed\n", "1")
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("passed", result.stdout)
            self.assertIn("sid", result.stderr)
            self.assertIn(
                "release apt provenance contains an index outside the Debian archive",
                result.stderr,
            )

    def test_the_preflight_runs_before_anything_changes(self):
        text = UPDATE_PATH.read_text()
        main = text.index('if [ "${PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY:-0}" = 1 ]; then\n    return 0')
        preflight = text.index("\npreflight_release_apt_provenance\n", main)
        self.assertLess(preflight, text.index("\nselect_latest_release_if_needed\n", main))
        self.assertLess(preflight, text.index("\nbegin_stack_transaction\n", main))


if __name__ == "__main__":
    unittest.main()
