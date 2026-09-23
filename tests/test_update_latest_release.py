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

    def _candidate_fixture(self, base: Path, annotated=True):
        repo = base / "candidate"
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "test"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.invalid"], check=True)
        (repo / "VERSION").write_text("0.2.2\n")
        (repo / "releases").mkdir()
        (repo / "provision").mkdir()
        manifest = "PLEBIAN_OS_VERSION=0.2.2\nPLEBIAN_OS_RELEASE=0.2.2\nPLEBIAN_OS_RELEASE_MODE=1\nPLEBIAN_OS_REF=v0.2.2\n"
        (repo / "releases/0.2.2.env").write_text(manifest)
        selector = (repo / "provision/plebian-os-select-closure.sh")
        selector.write_text(
            "#!/bin/bash\n"
            "echo '  PLEBIAN_OS_VERSION=0.2.2'\n"
            "echo '  PLEBIAN_OS_RELEASE=0.2.2'\n"
            "echo '  PLEBIAN_OS_RELEASE_MODE=1'\n"
            "printf '  PLEBIAN_OS_REF=%s\\n' \"${PLEBIAN_OS_REF:-v0.2.2}\"\n"
        )
        updater = (repo / "provision/plebian-os-update.sh")
        updater.write_text("candidate updater bytes\n")
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "candidate"], check=True)
        command = ["git", "-C", str(repo), "tag"]
        command += ["-a", "v0.2.2", "-m", "candidate"] if annotated else ["v0.2.2"]
        subprocess.run(command, check=True)
        (repo / "later-change").write_text("head may advance\n")
        subprocess.run(["git", "-C", str(repo), "add", "later-change"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "later change"], check=True)
        installed_selector = base / "installed-selector"
        installed_updater = base / "installed-updater"
        installed_selector.write_bytes(selector.read_bytes())
        installed_selector.chmod(0o700)
        installed_updater.write_bytes(updater.read_bytes())
        return repo, installed_selector, installed_updater

    def _candidate_result(self, repo: Path, selector: Path, updater: Path, overrides=()):
        env = os.environ.copy()
        env.update({"PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY": "1", "PLEBIAN_OS_DIR": str(repo),
                    "PLEBIAN_OS_RELEASE_MODE": "1", "PLEBIAN_OS_RELEASE": "0.2.2",
                    "PLEBIAN_OS_VERSION": "0.2.2", "PLEBIAN_OS_REF": "v0.2.2",
                    "PLEBIAN_OS_INSTALLED_SELECTOR": str(selector),
                    "PLEBIAN_OS_INSTALLED_UPDATER": str(updater)})
        env.update(dict(overrides))
        return subprocess.run(["bash", "-c", 'update_path=$1; set --; source "$update_path"; local_candidate_matches_selected_closure 0.2.2',
                               "bash", str(UPDATE)], env=env, text=True, capture_output=True)

    def test_unpublished_annotated_candidate_is_accepted_without_head_check(self):
        with tempfile.TemporaryDirectory() as td:
            repo, selector, updater = self._candidate_fixture(Path(td))
            # _candidate_fixture leaves HEAD one commit beyond the tag. The
            # selector contract reads the tag object without moving checkout.
            self.assertNotEqual(
                subprocess.run(
                    ["git", "-C", str(repo), "rev-parse", "HEAD"],
                    text=True, capture_output=True, check=True,
                ).stdout,
                subprocess.run(
                    ["git", "-C", str(repo), "rev-parse", "v0.2.2^{commit}"],
                    text=True, capture_output=True, check=True,
                ).stdout,
            )
            result = self._candidate_result(repo, selector, updater)
            self.assertEqual(result.returncode, 0, result.stderr)

            resolved = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "v0.2.2^{commit}"],
                text=True, capture_output=True, check=True,
            ).stdout.strip()
            result = self._candidate_result(
                repo, selector, updater, (("PLEBIAN_OS_REF", resolved),)
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_plain_restart_uses_exact_unpublished_candidate_when_remote_is_older(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo, selector, updater = self._candidate_fixture(base)
            published = self._repo_with_tags(base / "published")
            env = os.environ.copy()
            env.update({
                "PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY": "1",
                "PLEBIAN_OS_DIR": str(repo),
                "PLEBIAN_OS_REPO": str(published),
                "PLEBIAN_OS_RELEASE_MODE": "1",
                "PLEBIAN_OS_RELEASE": "0.2.2",
                "PLEBIAN_OS_VERSION": "0.2.2",
                "PLEBIAN_OS_REF": "v0.2.2",
                "PLEBIAN_OS_INSTALLED_SELECTOR": str(selector),
                "PLEBIAN_OS_INSTALLED_UPDATER": str(updater),
            })
            command = (
                'update_path=$1; set --; source "$update_path"; '
                'restart_arg=--restart; select_latest_release_if_needed'
            )
            result = subprocess.run(
                ["bash", "-c", command, "bash", str(UPDATE)], env=env,
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("unpublished candidate v0.2.2 matches", result.stdout)

            refused = subprocess.run(
                ["bash", "-c", command.replace(
                    "restart_arg=--restart", "restart_arg=--no-restart"
                ), "bash", str(UPDATE)], env=env,
                text=True, capture_output=True, check=False,
            )
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("refusing an implicit downgrade", refused.stderr)

    def test_validated_unpublished_candidate_completes_os_checkout_without_remote_tag(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo, selector, updater = self._candidate_fixture(base)
            published = self._repo_with_tags(base / "published")
            subprocess.run(
                ["git", "-C", str(repo), "remote", "add", "origin", str(published)],
                check=True,
            )
            candidate = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "v0.2.2^{commit}"],
                text=True, capture_output=True, check=True,
            ).stdout.strip()
            self.assertNotEqual(
                subprocess.run(
                    ["git", "-C", str(repo), "rev-parse", "HEAD"],
                    text=True, capture_output=True, check=True,
                ).stdout.strip(),
                candidate,
            )
            env = os.environ.copy()
            env.update({
                "PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY": "1",
                "PLEBIAN_OS_DIR": str(repo),
                "PLEBIAN_OS_REPO": str(published),
                "PLEBIAN_OS_RELEASE_MODE": "1",
                "PLEBIAN_OS_RELEASE": "0.2.2",
                "PLEBIAN_OS_VERSION": "0.2.2",
                "PLEBIAN_OS_REF": candidate,
                "PLEBIAN_OS_INSTALLED_SELECTOR": str(selector),
                "PLEBIAN_OS_INSTALLED_UPDATER": str(updater),
            })
            command = (
                'update_path=$1; set --; source "$update_path"; '
                'local_candidate_matches_selected_closure 0.2.2; '
                'update_os_checkout'
            )
            result = subprocess.run(
                ["bash", "-c", command, "bash", str(UPDATE)], env=env,
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("using already-validated unpublished", result.stdout)
            self.assertEqual(
                subprocess.run(
                    ["git", "-C", str(repo), "rev-parse", "HEAD"],
                    text=True, capture_output=True, check=True,
                ).stdout.strip(),
                candidate,
            )
            # The configured origin has no v0.2.2 tag. Success therefore came
            # from the validated local annotated tag, not a hidden fetch.
            missing = subprocess.run(
                ["git", "-C", str(published), "rev-parse", "--verify", "v0.2.2"],
                text=True, capture_output=True, check=False,
            )
            self.assertNotEqual(missing.returncode, 0)

    def test_candidate_checkout_exception_does_not_apply_to_component_refs(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            os_repo, selector, updater = self._candidate_fixture(base)
            published = self._repo_with_tags(base / "published")
            subprocess.run(
                ["git", "-C", str(os_repo), "remote", "add", "origin", str(published)],
                check=True,
            )
            component = base / "component"
            subprocess.run(["git", "init", "-q", str(component)], check=True)
            subprocess.run(
                ["git", "-C", str(component), "config", "user.name", "test"], check=True,
            )
            subprocess.run(
                ["git", "-C", str(component), "config", "user.email", "test@example.invalid"], check=True,
            )
            (component / "local").write_text("local\n")
            subprocess.run(["git", "-C", str(component), "add", "local"], check=True)
            subprocess.run(["git", "-C", str(component), "commit", "-qm", "local"], check=True)
            subprocess.run(
                ["git", "-C", str(component), "remote", "add", "origin", str(published)],
                check=True,
            )
            remote_commit = subprocess.run(
                ["git", "-C", str(published), "rev-parse", "HEAD"],
                text=True, capture_output=True, check=True,
            ).stdout.strip()
            env = os.environ.copy()
            env.update({
                "PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY": "1",
                "PLEBIAN_OS_DIR": str(os_repo),
                "PLEBIAN_OS_REPO": str(published),
                "PLEBIAN_OS_RELEASE_MODE": "1",
                "PLEBIAN_OS_RELEASE": "0.2.2",
                "PLEBIAN_OS_VERSION": "0.2.2",
                "PLEBIAN_OS_REF": "v0.2.2",
                "PLEBIAN_OS_INSTALLED_SELECTOR": str(selector),
                "PLEBIAN_OS_INSTALLED_UPDATER": str(updater),
            })
            command = (
                'update_path=$1; component=$2; ref=$3; set --; source "$update_path"; '
                'local_candidate_matches_selected_closure 0.2.2; '
                'checkout_pinned_ref "$component" "$ref" pleb'
            )
            result = subprocess.run(
                ["bash", "-c", command, "bash", str(UPDATE), str(component), remote_commit],
                env=env, text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("already-validated unpublished", result.stdout)
            self.assertEqual(
                subprocess.run(
                    ["git", "-C", str(component), "rev-parse", "FETCH_HEAD"],
                    text=True, capture_output=True, check=True,
                ).stdout.strip(),
                remote_commit,
            )
            self.assertEqual(
                subprocess.run(
                    ["git", "-C", str(component), "rev-parse", "HEAD"],
                    text=True, capture_output=True, check=True,
                ).stdout.strip(),
                remote_commit,
            )

    def test_candidate_gate_refuses_lightweight_tag_and_mismatched_installed_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            repo, selector, updater = self._candidate_fixture(Path(td), annotated=False)
            self.assertNotEqual(self._candidate_result(repo, selector, updater).returncode, 0)
        with tempfile.TemporaryDirectory() as td:
            repo, selector, updater = self._candidate_fixture(Path(td))
            updater.write_text("changed updater\n")
            self.assertNotEqual(self._candidate_result(repo, selector, updater).returncode, 0)

    def test_candidate_gate_refuses_wrong_ref_or_development_mode(self):
        with tempfile.TemporaryDirectory() as td:
            repo, selector, updater = self._candidate_fixture(Path(td))
            self.assertNotEqual(self._candidate_result(repo, selector, updater,
                (("PLEBIAN_OS_REF", "deadbeef"),)).returncode, 0)
            self.assertNotEqual(self._candidate_result(repo, selector, updater,
                (("PLEBIAN_OS_REF", "0" * 40),)).returncode, 0)
            self.assertNotEqual(self._candidate_result(repo, selector, updater,
                (("PLEBIAN_OS_RELEASE_MODE", "0"),)).returncode, 0)

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
