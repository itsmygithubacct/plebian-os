"""plebian-os-update refuses a per-user session.env that moves the source tree.

The login session loads the per-user Pleb session.env after the system one,
but the updater hands pleb its own paths. A developer layout there once made a
bare-metal update install into one tree while the desktop ran another, and the
install stopped part-way on the other tree's links.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPDATE_PATH = ROOT / "provision" / "plebian-os-update.sh"

LAYOUT_KEYS = (
    "GPU_TERMINAL_SOURCE_HOME", "PLEB_DIR", "PLEBIAN_OS_DIR", "KILIX_DIR",
    "KILIX95_DIR", "KILIX_CAP_DIR", "KILIX_TUI_UTILS_DIR",
    "KILIX_LAND_DESKTOP_DIR", "PLEB_ENV_USER", "KILIX",
)


class PerUserLayoutOverrideTests(unittest.TestCase):
    def _run(self, home: Path, session_env: str | None, body: str):
        config = home / ".local/gpu_terminal/pleb/config"
        config.mkdir(parents=True)
        if session_env is not None:
            (config / "session.env").write_text(session_env)
        env = {k: v for k, v in os.environ.items() if k not in LAYOUT_KEYS}
        sources = home / ".local/gpu_terminal/sources"
        # Explicit, so an installed /etc/pleb/session.env cannot supply them.
        env.update({
            "HOME": str(home),
            "GPU_TERMINAL_HOME": str(home / ".local/gpu_terminal"),
            "GPU_TERMINAL_SOURCE_HOME": str(sources),
            "PLEB_CONFIG_HOME": str(config),
            "PLEB_DIR": str(sources / "pleb"),
            "PLEBIAN_OS_DIR": str(sources / "plebian-os"),
            "KILIX_DIR": str(sources / "kilix"),
            "KILIX": str(sources / "kilix" / "kilix"),
            "KILIX95_DIR": str(sources / "kilix-desktops/kilix-95"),
            "KILIX_CAP_DIR": str(sources / "kilix-desktops/kilix-cap"),
            "KILIX_TUI_UTILS_DIR": str(sources / "kilix-desktops/kilix-tui-utils"),
            "KILIX_LAND_DESKTOP_DIR":
                str(sources / "kilix-desktops/kilix-land-desktop"),
        })
        script = (
            "set -euo pipefail\n"
            "export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1\n"
            f"PLEB_STATE_HOME={str(home / 'state')!r}\n"
            f"source {str(UPDATE_PATH)!r}\n"
            + body
        )
        return subprocess.run(["bash", "-c", script], env=env, text=True,
                              capture_output=True, check=False)

    def _refuse(self, home: Path, session_env: str | None):
        return self._run(home, session_env,
                         "refuse_per_user_source_layout\necho passed\n")

    def test_developer_layout_override_is_refused_by_name(self):
        # The exact override this machine carried from 2026-08-15.
        developer = (
            "# Per-user Pleb login-session selection.\n"
            'GPU_TERMINAL_SOURCE_HOME="$HOME/gpu_terminal"\n'
            'KILIX_DIR="$GPU_TERMINAL_SOURCE_HOME/kilix"\n'
            'KILIX="$KILIX_DIR/kilix"\n'
            "PLEB_DESKTOP=1\n"
            "KILIX_DESKTOP_PROVIDER=external\n"
            'KILIX95_DIR="$GPU_TERMINAL_SOURCE_HOME/kilix-desktops/kilix-95"\n'
        )
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            result = self._refuse(home, developer)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("passed", result.stdout)
            self.assertIn("per-user session.env overrides the source layout",
                          result.stderr)
            for key, theirs in (
                    ("GPU_TERMINAL_SOURCE_HOME", home / "gpu_terminal"),
                    ("KILIX_DIR", home / "gpu_terminal/kilix"),
                    ("KILIX95_DIR",
                     home / "gpu_terminal/kilix-desktops/kilix-95")):
                self.assertIn(f"{key}: the session uses {theirs};",
                              result.stderr)
            self.assertNotIn("PLEB_DIR:", result.stderr)
            self.assertIn("move", result.stderr)
            self.assertIn("pleb update", result.stderr)

    def test_absent_or_unrelated_user_settings_pass(self):
        for session_env in (None, "PLEB_DESKTOP=1\nPLEB_WM=openbox\n", ""):
            with self.subTest(session_env=session_env), \
                    tempfile.TemporaryDirectory() as td:
                result = self._refuse(Path(td), session_env)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("passed", result.stdout)

    def test_a_path_naming_the_same_directory_passes(self):
        # A stock path reached through a symlink is the same checkout.
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            sources = home / ".local/gpu_terminal/sources"
            (sources / "kilix").mkdir(parents=True)
            (home / "alias").symlink_to(sources, target_is_directory=True)
            result = self._refuse(
                home,
                f'GPU_TERMINAL_SOURCE_HOME="{home}/alias"\n'
                'KILIX_DIR="$GPU_TERMINAL_SOURCE_HOME/kilix"\n'
                'KILIX_DIR="$KILIX_DIR/"\n',
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_an_engine_override_alone_is_refused(self):
        # The session launches $KILIX, which pleb defaults from KILIX_DIR.
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            result = self._refuse(home, 'KILIX="$HOME/dev/kilix/kilix"\n')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                f"KILIX: the session uses {home}/dev/kilix/kilix; this update "
                f"would update {home}/.local/gpu_terminal/sources/kilix/kilix",
                result.stderr)

    def test_unset_or_empty_paths_are_rederived_not_moved(self):
        # Pleb derives unset paths after loading, so the session agrees.
        for session_env in ("unset KILIX_DIR\n", 'KILIX_DIR=""\n',
                            "unset GPU_TERMINAL_SOURCE_HOME KILIX PLEB_DIR\n"):
            with self.subTest(session_env=session_env), \
                    tempfile.TemporaryDirectory() as td:
                result = self._refuse(Path(td), session_env)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")

    def test_sourcing_the_user_file_changes_nothing_in_the_updater(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            result = self._run(
                home,
                'PLEB_LAYOUT_TEST_MARK=set\necho noisy\nset -u\nfalse\n',
                "refuse_per_user_source_layout\n"
                'printf "mark=%s\\n" "${PLEB_LAYOUT_TEST_MARK-unset}"\n',
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("noisy", result.stdout + result.stderr)
            self.assertIn("mark=unset", result.stdout)

    def test_the_refusal_runs_before_the_release_hop(self):
        text = UPDATE_PATH.read_text()
        main = text.index('if [ "${PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY:-0}" = 1 ]; then\n    return 0')
        refuse = text.index("\nrefuse_per_user_source_layout\n", main)
        self.assertLess(refuse, text.index("\nselect_latest_release_if_needed\n", main))
        self.assertLess(refuse, text.index("\nbegin_stack_transaction\n", main))


if __name__ == "__main__":
    unittest.main()
