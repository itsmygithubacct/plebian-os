"""The first-standalone-selection fix reaches machines running published Pleb.

The selector is extracted from the TARGET tag, so its fix applies whatever
Pleb invokes it. These tests take `lib/closure.sh` from published Pleb commits
and let it fetch, record, invoke, and roll back this selector exactly as it
would on a standalone machine that has never selected a release.
"""

import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

import test_closure_selection as closure_tests

ROOT = closure_tests.ROOT
PLEB_REPO = Path(os.environ.get(
    "PLEBIAN_OS_PLEB_REPO", str(Path(__file__).resolve().parents[2] / "pleb")))
# Published Pleb whose `pleb update --to` can drive a standalone selection.
PUBLISHED_PLEB = {
    "v0.2.2": "2dd44b003b1d0d0ca4b06aa2721467590b5f71f7",
    "v0.2.3-rc8": "49fc7554a01b30e33fd1a8f12e038906830bc7fe",
    "v0.2.3-rc9": "57683ebf8ac88ccbf7f160c4f7c6e0cc25936488",
}

# The old module's own functions, in the order its pleb_release_hop calls them.
DRIVER = textwrap.dedent("""\
    set -euo pipefail
    die() { printf '%s\\n' "$*" >&2; exit 1; }
    log() { printf '%s\\n' "$*"; }
    warn() { printf '%s\\n' "$*" >&2; }
    err() { printf '%s\\n' "$*" >&2; }
    ensure_pleb_private_storage() { mkdir -p -- "$PLEB_CACHE_HOME" "$PLEB_STATE_HOME"; }
    . "$1/lib/closure.sh"
    case "$2" in
        select)
            _pleb_prepare_target_selector "$3" 0 "v$3"
            _pleb_record_active_selector selecting
            _pleb_selector_env "$_PLEB_HOP_SELECTOR" "$3" --source "$_PLEB_HOP_REPO"
            _pleb_set_active_phase selected
            ;;
        rollback)
            _pleb_load_active_selector
            _pleb_selector_env "$_PLEB_HOP_SELECTOR" --rollback
            ;;
    esac
    """)


class PublishedPlebReachTests(unittest.TestCase):
    def setUp(self):
        if not (PLEB_REPO / ".git").exists() and not (PLEB_REPO / "HEAD").exists():
            self.skipTest(f"no Pleb repository at {PLEB_REPO} (set PLEBIAN_OS_PLEB_REPO)")

    def _old_pleb(self, base: Path, commit: str) -> Path:
        dest = base / "old-pleb"
        archive = subprocess.run(
            ["git", "-C", str(PLEB_REPO), "archive", commit, "lib/closure.sh"],
            capture_output=True, check=True)
        dest.mkdir()
        subprocess.run(["tar", "-x", "-C", str(dest)], input=archive.stdout, check=True)
        return dest

    def _machine(self, base: Path, session_text):
        helper = closure_tests.ClosureSelectionTests(
            "test_first_standalone_selection_records_an_unselected_machine")
        user_env, recovery, _ = helper._unselected_standalone(base, session_text)
        storage = base / "home/.local/gpu_terminal/pleb"
        env = {
            "HOME": str(base / "home"), "PATH": os.environ["PATH"], "LANG": "C",
            "TMPDIR": str(base),
            "GPU_TERMINAL_SOURCE_HOME": str(base / "home/.local/gpu_terminal/sources"),
            "PLEB_STATE_HOME": str(storage / "state"),
            "PLEB_CACHE_HOME": str(storage / "cache"),
            "PLEB_ENV_USER": str(user_env),
            "PLEB_CLOSURE_USER": str(user_env.with_name("closure.env")),
            "PLEB_ROOT": str(base / "pleb-checkout"),
            "KILIX_DIR": str(base / "kilix"), "KILIX95_DIR": str(base / "kilix95"),
            "PLEBIAN_OS_REPO": str(base / "src"),
            "PLEBIAN_OS_MANAGED_INSTALL": "0",
            "PLEBIAN_OS_CLOSURE_TEST_ROOT": str(base / "root"),
            "PLEBIAN_OS_SELECT_TEST_SKIP_COMPONENT_ANCESTRY": "1",
        }
        return user_env, env

    def test_published_pleb_selects_first_and_rolls_back_to_no_closure(self):
        for tag, commit in PUBLISHED_PLEB.items():
            for name, text in closure_tests.ClosureSelectionTests.UNSELECTED_SESSIONS.items():
                with self.subTest(pleb=tag, session=name), tempfile.TemporaryDirectory() as td:
                    base = Path(td)
                    user_env, env = self._machine(base, text)
                    closure = user_env.with_name("closure.env")
                    before = (user_env.read_bytes() if user_env.exists() else None)
                    root = self._old_pleb(base, commit)
                    driver = base / "driver.sh"
                    driver.write_text(DRIVER)
                    selected = subprocess.run(["bash", str(driver), str(root), "select", "0.2.2"],
                                              env=env, capture_output=True, text=True)
                    self.assertEqual(selected.returncode, 0, selected.stderr)
                    self.assertNotIn("status 6", selected.stderr)
                    self.assertIn("treating 0.2.2 as a first selection", selected.stderr)
                    self.assertTrue(closure.is_file())
                    rolled = subprocess.run(["bash", str(driver), str(root), "rollback"],
                                            env=env, capture_output=True, text=True)
                    self.assertEqual(rolled.returncode, 0, rolled.stderr)
                    self.assertFalse(closure.exists())
                    self.assertEqual(user_env.read_bytes() if user_env.exists() else None, before)


if __name__ == "__main__":
    unittest.main()
