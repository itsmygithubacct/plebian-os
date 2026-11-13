import os
import pwd
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
# Permission fixtures assume conventional public modes even when the suite is
# launched from a shell with umask 077.
os.umask(0o022)
PROVISION = ROOT / "provision" / "plebian-os-provision.sh"
README = ROOT / "README.md"

ALIAS_LINE = "alias ask='kilix ask'"
ALIAS_COMMENT = "# ask: kilix ask (added by plebian-os-provision)"
# A PATH with no `ask` on it, for probes that must see an unprovisioned shell.
BARE_PATH = "/usr/bin:/bin"


def _seeder_body(source: str) -> str:
    return source.split("install_ask_shell_alias() {", 1)[1].split("\n}", 1)[0]


class AskAliasContractTests(unittest.TestCase):
    def test_provisioner_declares_and_calls_the_alias_seeder(self):
        source = PROVISION.read_text()
        self.assertIn("install_ask_shell_alias() {", source)
        self.assertRegex(source, r"(?m)^install_ask_shell_alias$")
        body = _seeder_body(source)
        # The no-clobber guard interrogates the target user's own interactive
        # shell, so an existing command, alias, or function all count.
        self.assertIn("command -v ask", body)
        self.assertIn("already resolves", body)
        # ~/.bash_aliases is user-controlled: written as the user via the safe
        # embedded writer, atomically, and never chowned or redirected to by
        # root (same rules as the tb alias writer).
        self.assertIn("as_user bash -c", body)
        self.assertIn("mv -fT", body)
        self.assertNotIn('> "$aliases"', body)
        self.assertNotRegex(body, r"(?m)^\s*chown\b")
        # The alias is the kilix command on PATH. A checkout path would differ
        # per machine.
        self.assertIn(ALIAS_LINE, source)
        self.assertNotIn("/kilix ask", body)
        self.assertNotRegex(body, r"\.local/gpu_terminal")

    def test_alias_seeder_runs_before_pleb_publishes_commands(self):
        # Seeding precedes `pleb install`, matching the tb alias. Once a
        # command named ask is on PATH, the no-clobber guard would decline
        # forever after.
        source = PROVISION.read_text()
        call = re.search(r"(?m)^install_ask_shell_alias$", source)
        self.assertIsNotNone(call)
        publish = source.index('"$PLEB_DIR/bin/pleb" install')
        self.assertLess(call.start(), publish)

    def test_readme_documents_the_ask_alias_and_its_guard(self):
        readme = README.read_text()
        self.assertIn("`ask` alias for `kilix ask`", readme)
        self.assertIn("0.2.3 rc5", readme)
        self.assertIn("already resolves", readme)


class AskAliasWriterTests(unittest.TestCase):
    """Exercise the exact unprivileged writer embedded in the provisioner."""

    def _writer(self) -> str:
        body = _seeder_body(PROVISION.read_text())
        match = re.search(
            r"as_user bash -c (?P<literal>'\n.*?\n') "
            r"plebian-os-ask-alias-writer \"\$aliases\"",
            body,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(match, "safe ask alias writer shell literal not found")
        return match.group("literal")

    def _run_writer(self, aliases: Path) -> subprocess.CompletedProcess:
        command = (
            f"writer={self._writer()}\n"
            'bash -c "$writer" plebian-os-ask-alias-writer "$1"'
        )
        return subprocess.run(
            ["bash", "-c", command, "ask-alias-test", str(aliases)],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_writer_creates_a_fresh_file_with_open_mode(self):
        with tempfile.TemporaryDirectory() as td:
            aliases = Path(td) / ".bash_aliases"
            result = self._run_writer(aliases)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                aliases.read_text(), f"{ALIAS_COMMENT}\n{ALIAS_LINE}\n"
            )
            self.assertEqual(stat.S_IMODE(aliases.stat().st_mode), 0o644)

    def test_writer_appends_and_preserves_content_and_mode(self):
        with tempfile.TemporaryDirectory() as td:
            aliases = Path(td) / ".bash_aliases"
            aliases.write_text("alias ll='ls -l'\n")
            aliases.chmod(0o600)
            result = self._run_writer(aliases)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                aliases.read_text(),
                f"alias ll='ls -l'\n{ALIAS_COMMENT}\n{ALIAS_LINE}\n",
            )
            self.assertEqual(stat.S_IMODE(aliases.stat().st_mode), 0o600)
            self.assertEqual(list(Path(td).iterdir()), [aliases])

    def test_writer_declines_a_symlinked_aliases_file(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            victim = home / "dotfiles-aliases"
            victim.write_text("# operator-managed\n")
            aliases = home / ".bash_aliases"
            aliases.symlink_to(victim)
            result = self._run_writer(aliases)
            self.assertEqual(result.returncode, 3, result.stderr)
            self.assertTrue(aliases.is_symlink())
            self.assertEqual(victim.read_text(), "# operator-managed\n")


class AskAliasBehaviorTests(unittest.TestCase):
    def _run_library(self, body: str):
        env = {**os.environ, "PLEBIAN_OS_PROVISION_LIB_ONLY": "1"}
        return subprocess.run(
            ["bash", "-c", f'. "{PROVISION}"\n{body}'],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def _seed_body(self, home: Path, path: str = BARE_PATH,
                   dry_run: int = 0, runs: int = 1) -> str:
        user = pwd.getpwuid(os.getuid())
        return (
            f"TARGET_USER={user.pw_name!r}\n"
            f"TARGET_UID={user.pw_uid}\nTARGET_GID={user.pw_gid}\n"
            f"DRY_RUN={dry_run}\n"
            "as_user() { \"$@\"; }\n"
            f"USER_HOME={str(home)!r}\n"
            f"export HOME={str(home)!r}\n"
            f"export PATH={path!r}\n"
            + "install_ask_shell_alias\n" * runs
        )

    @staticmethod
    def _debian_style_bashrc(home: Path) -> None:
        (home / ".bashrc").write_text(
            "if [ -f ~/.bash_aliases ]; then\n"
            "    . ~/.bash_aliases\n"
            "fi\n"
        )

    def setUp(self):
        if shutil.which("ask", path=BARE_PATH):
            self.skipTest(f"a system ask command shadows the probe on {BARE_PATH}")

    def test_seeds_a_fresh_home_and_the_alias_runs_kilix_ask(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            self._debian_style_bashrc(home)
            bindir = home / "bin"
            bindir.mkdir()
            kilix = bindir / "kilix"
            kilix.write_text("#!/bin/sh\nprintf '%s\\n' \"$*\"\n")
            kilix.chmod(0o755)
            result = self._run_library(self._seed_body(home))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("ask alias installed", result.stdout)
            aliases = home / ".bash_aliases"
            self.assertEqual(
                aliases.read_text(), f"{ALIAS_COMMENT}\n{ALIAS_LINE}\n"
            )
            probe = subprocess.run(
                ["bash", "-ic", "command -v ask; ask 'what version is kilix?'; ask what version is kilix?"],
                env={
                    **os.environ,
                    "HOME": str(home),
                    "PATH": f"{bindir}:{BARE_PATH}",
                },
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(probe.returncode, 0, probe.stderr)
            self.assertIn("alias ask='kilix ask'", probe.stdout)
            self.assertEqual(probe.stdout.splitlines().count("ask what version is kilix?"), 2)

    def test_reprovision_notes_the_existing_alias_and_keeps_one_line(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            self._debian_style_bashrc(home)
            result = self._run_library(self._seed_body(home, runs=2))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("already resolves", result.stdout)
            content = (home / ".bash_aliases").read_text()
            self.assertEqual(content.count(ALIAS_LINE), 1)

    def test_skips_when_ask_already_resolves_on_path(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            home.mkdir()
            bindir = Path(td) / "bin"
            bindir.mkdir()
            stub = bindir / "ask"
            stub.write_text("#!/bin/sh\nexit 0\n")
            stub.chmod(0o755)
            body = self._seed_body(home, path=f"{bindir}:{BARE_PATH}")
            result = self._run_library(body)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("already resolves", result.stdout)
            self.assertIn(str(stub), result.stdout)
            self.assertFalse((home / ".bash_aliases").exists())

    def test_dry_run_prints_the_plan_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            result = self._run_library(self._seed_body(home, dry_run=1))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("skip if ask already resolves", result.stdout)
            self.assertFalse((home / ".bash_aliases").exists())


if __name__ == "__main__":
    unittest.main()
