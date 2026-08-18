import os
import shlex
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD_LIB = ROOT / "build" / "lib.sh"
INSTALL_DEPS = ROOT / "provision" / "install-deps.sh"


class DownloadLimitTests(unittest.TestCase):
    @staticmethod
    def _executable_curl_lines(path):
        command = re.compile(
            r"(?:^|[;&|()]|\b(?:if|then|elif|while|until|do)|!)\s*curl\s"
        )
        return [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if command.search(line) and not line.lstrip().startswith("#")
        ]

    def test_build_download_passes_time_and_size_limits_to_curl(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            args_file = root / "args"
            fake_curl = root / "curl"
            fake_curl.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' \"$@\" > \"$CURL_ARGS_FILE\"\n"
                "while [ $# -gt 0 ]; do\n"
                "  if [ \"$1\" = -o ]; then shift; : > \"$1\"; fi\n"
                "  shift\n"
                "done\n",
                encoding="utf-8",
            )
            fake_curl.chmod(0o755)
            output = root / "result"
            command = (
                f"source {shlex.quote(str(BUILD_LIB))}; "
                f"_bounded_download 1234 56 {shlex.quote(str(output))} "
                "-fsSL https://example.invalid/file"
            )
            env = dict(os.environ)
            env.update(
                PATH=f"{root}:{env['PATH']}",
                CURL_ARGS_FILE=str(args_file),
                PLEBIAN_OS_DOWNLOAD_CONNECT_TIMEOUT="7",
            )
            subprocess.run(["bash", "-c", command], env=env, check=True)
            args = args_file.read_text(encoding="utf-8").splitlines()
            self.assertIn("--connect-timeout", args)
            self.assertIn("7", args)
            self.assertIn("--max-time", args)
            self.assertIn("56", args)
            self.assertIn("--max-filesize", args)
            self.assertIn("1234", args)

    def test_build_download_removes_oversized_chunked_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake_curl = root / "curl"
            fake_curl.write_text(
                "#!/bin/sh\n"
                "while [ $# -gt 0 ]; do\n"
                "  if [ \"$1\" = -o ]; then shift; printf 12345 > \"$1\"; fi\n"
                "  shift\n"
                "done\n",
                encoding="utf-8",
            )
            fake_curl.chmod(0o755)
            output = root / "result"
            command = (
                f"source {shlex.quote(str(BUILD_LIB))}; "
                f"_bounded_download 4 56 {shlex.quote(str(output))} "
                "https://example.invalid/file"
            )
            env = dict(os.environ)
            env["PATH"] = f"{root}:{env['PATH']}"
            result = subprocess.run(["bash", "-c", command], env=env)
            self.assertEqual(result.returncode, 63)
            self.assertFalse(output.exists())

    def test_every_release_download_uses_the_bounded_helpers(self):
        build = BUILD_LIB.read_text(encoding="utf-8")
        deps = INSTALL_DEPS.read_text(encoding="utf-8")
        self.assertEqual(
            self._executable_curl_lines(BUILD_LIB),
            ['curl --connect-timeout "$connect_time" --max-time "$max_time" \\'],
        )
        self.assertEqual(
            self._executable_curl_lines(INSTALL_DEPS),
            ['curl --connect-timeout "$connect_time" --max-time "$max_time" \\'],
        )
        self.assertIn("_bounded_download", build)
        self.assertIn("bounded_curl \"$uv_tmp\"", deps)
        self.assertIn("PLEBIAN_OS_UV_INSTALLER_MAX_BYTES", deps)


if __name__ == "__main__":
    unittest.main()
