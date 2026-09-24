"""A third-party apt source is refused before the update, and says what to do.

The lifetime gate once ran only when the final provenance was written, after
the whole stack had been rebuilt, so a configured CUDA repository rolled back a
complete update and the refusal did not say which file to set aside.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPDATE_PATH = ROOT / "provision" / "plebian-os-update.sh"

CUDA = ("https://developer.download.nvidia.com/compute/cuda/repos/debian13/x86_64"
        "  $(COMPONENT) $(ARCHITECTURE)")


def codename() -> str:
    return subprocess.run(
        ["bash", "-c", '. /etc/os-release 2>/dev/null; printf %s "${VERSION_CODENAME:-trixie}"'],
        text=True, capture_output=True, check=True,
    ).stdout


class AptProvenanceGuidanceTests(unittest.TestCase):
    def _apt_root(self, tmp: Path) -> Path:
        apt = tmp / "apt"
        (apt / "sources.list.d").mkdir(parents=True)
        (apt / "sources.list").write_text("")
        (apt / "sources.list.d" / "debian.sources").write_text(
            "Types: deb\nURIs: http://deb.debian.org/debian\n")
        (apt / "sources.list.d" / "cuda-debian13-x86_64.list").write_text(
            "deb [signed-by=/usr/share/keyrings/cuda.gpg] "
            "https://developer.download.nvidia.com/compute/cuda/repos/debian13/x86_64/ /\n")
        return apt

    def _run(self, tmp: Path, body: str, indexes: list[str], release_mode: str):
        bindir = tmp / "bin"
        bindir.mkdir()
        listing = tmp / "indextargets"
        listing.write_text("".join(f"{line}\n" for line in indexes))
        stub = bindir / "apt-get"
        stub.write_text(
            "#!/bin/sh\n"
            f'[ "$1" = indextargets ] && exec cat {str(listing)!r}\n'
            "exit 99\n")
        stub.chmod(0o755)
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("PLEBIAN_OS_")}
        env.update({
            "HOME": str(tmp / "home"),
            "PATH": f"{bindir}:{os.environ['PATH']}",
            "PLEBIAN_OS_APT_SOURCES_ROOT": str(self._apt_root(tmp)),
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
        return subprocess.run(["bash", "-c", script], env=env, text=True,
                              capture_output=True, check=False)

    def test_refusal_names_the_source_file_and_the_way_through(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            result = self._run(
                tmp, "preflight_release_apt_provenance\necho passed\n",
                [CUDA, f"http://deb.debian.org/debian {codename()} main amd64"],
                "1")
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("passed", result.stdout)
            self.assertIn("apt index outside the Debian archive", result.stderr)
            self.assertIn(
                "is configured in "
                f"{tmp / 'apt/sources.list.d/cuda-debian13-x86_64.list'}",
                result.stderr)
            self.assertNotIn("debian.sources", result.stderr)
            self.assertIn("disable each source above for this run",
                          result.stderr)
            self.assertIn("re-enable the source afterwards", result.stderr)

    def test_debian_only_indexes_pass_the_preflight(self):
        with tempfile.TemporaryDirectory() as td:
            result = self._run(
                Path(td), "preflight_release_apt_provenance\necho passed\n",
                [f"http://deb.debian.org/debian {codename()} main amd64"], "1")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("passed", result.stdout)

    def test_development_closures_are_not_preflighted(self):
        # The final gate only applies in release mode; so does the preflight.
        with tempfile.TemporaryDirectory() as td:
            result = self._run(
                Path(td), "preflight_release_apt_provenance\necho passed\n",
                [CUDA], "0")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("passed", result.stdout)

    def test_the_preflight_runs_before_anything_changes(self):
        text = UPDATE_PATH.read_text()
        main = text.index('if [ "${PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY:-0}" = 1 ]; then\n    return 0')
        preflight = text.index("\npreflight_release_apt_provenance\n", main)
        self.assertLess(preflight,
                        text.index("\nselect_latest_release_if_needed\n", main))
        self.assertLess(preflight, text.index("\nbegin_stack_transaction\n", main))


if __name__ == "__main__":
    unittest.main()
