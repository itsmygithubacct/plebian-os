"""Focused tests for the updater's default latest-release resolution."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UPDATE = ROOT / "provision" / "plebian-os-update.sh"


class LatestReleaseUpdateTests(unittest.TestCase):
    def _repo_with_tags(self, base: Path) -> Path:
        repo = base / "releases"
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.name", "test"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"],
            check=True,
        )
        (repo / "VERSION").write_text("0.2.1\n")
        subprocess.run(["git", "-C", str(repo), "add", "VERSION"], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-qm", "fixture"],
            check=True,
        )
        for tag in (
            "v0.1.9",
            "v0.2.0",
            "v0.2.1",
            "v0.2.1-rc1",
            "media-v1",
            "vgarbage",
        ):
            subprocess.run(["git", "-C", str(repo), "tag", tag], check=True)
        return repo

    def _source_and_run(self, command: str, repo: Path) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env.update(
            {
                "PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY": "1",
                "PLEBIAN_OS_REPO": str(repo),
            }
        )
        return subprocess.run(
            [
                "bash",
                "-c",
                'update_path=$1; command=$2; set --; source "$update_path"; eval "$command"',
                "bash",
                str(UPDATE),
                command,
            ],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_highest_stable_semantic_tag_is_selected(self):
        with tempfile.TemporaryDirectory() as td:
            repo = self._repo_with_tags(Path(td))
            result = self._source_and_run("latest_published_release", repo)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "0.2.1\n")

    def test_version_comparison_only_accepts_a_strict_upgrade(self):
        with tempfile.TemporaryDirectory() as td:
            repo = self._repo_with_tags(Path(td))
            result = self._source_and_run(
                "release_is_newer 0.2.1 0.2.0"
                " && ! release_is_newer 0.2.0 0.2.0"
                " && ! release_is_newer 0.1.9 0.2.0",
                repo,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_release_query_failure_is_not_reported_as_up_to_date(self):
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "missing"
            result = self._source_and_run("latest_published_release", missing)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("could not query published", result.stderr)

    def test_relaunch_drops_every_target_release_key_from_an_old_pane(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = self._repo_with_tags(root)
            selector = root / "selector"
            selector.write_text(
                "#!/bin/sh\n"
                "cat <<'EOF'\n"
                "[plebian-os] release-controlled keys currently selected:\n"
                "  PLEBIAN_OS_VERSION=0.2.1\n"
                "  KILIX95_REF=target-ref\n"
                "  KILIX_VOICE_REF (not set)\n"
                "EOF\n"
            )
            selector.chmod(0o700)
            result = self._source_and_run(
                f"selected_release_environment_keys {selector}", repo
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                result.stdout.splitlines(),
                ["PLEBIAN_OS_VERSION", "KILIX95_REF", "KILIX_VOICE_REF"],
            )

        source = UPDATE.read_text()
        self.assertIn('relaunch_env+=(-u "$key")', source)
        self.assertIn(
            'exec "${relaunch_env[@]}" /usr/local/bin/plebian-os-update',
            source,
        )


if __name__ == "__main__":
    unittest.main()
