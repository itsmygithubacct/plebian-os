"""Firstboot must be able to fetch a locally tagged release candidate."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RemasterRemoteRefTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.checkout = self.root / "checkout"
        self.remote = self.root / "origin.git"
        self.output = self.root / "firstboot.env"
        self.env = {
            "PATH": os.environ["PATH"], "HOME": str(self.root),
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "/bin/true",
            "HERE": str(self.checkout), "PLEBIAN_OS_RELEASE_MODE": "1",
            "PLEBIAN_OS_REF": "v9.8.7", "PLEBIAN_OS_VERSION": "9.8.7",
            "PLEBIAN_OS_REPO": self.remote.as_uri(),
            "PLEBIAN_OS_IDENTITY_PROFILE": "interactive",
        }
        self.git("init", "-q", "--bare", str(self.remote), cwd=self.root)
        self.git("init", "-q", str(self.checkout), cwd=self.root)
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "commit", "-qm", "Fixture", "--allow-empty")
        self.published = self.git("rev-parse", "HEAD").stdout.strip()
        self.git("push", "-q", self.remote.as_uri(), "HEAD:refs/heads/candidate")
        self.git("tag", "v9.8.7")
        source = (ROOT / "build/remaster-iso.sh").read_text()
        self.functions = []
        for name in ("is_hex_len", "firstboot_source_ref", "env_kv",
                     "validate_release_refs_resolve_on_their_remotes",
                     "validate_release_submodule_gitlinks_resolve", "write_firstboot_env"):
            marker = f"{name}() {{\n"
            if marker in source:
                start = source.index(marker)
                end = source.index("\n}\n", start) + 3
                self.functions.append(source[start:end])

    def git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd or self.checkout,
                              env=self.env, text=True, capture_output=True, check=True)

    def run_guard(self, *, submodules=False):
        harness = "set -euo pipefail\n" + "\n".join(self.functions)
        harness += '\nwrite_firstboot_env "$1"\n'
        harness += "validate_release_refs_resolve_on_their_remotes\n"
        if submodules:
            harness += "validate_release_submodule_gitlinks_resolve\n"
        return subprocess.run(["bash", "-c", harness, "ref-fixture", str(self.output)],
                              env=self.env, text=True, capture_output=True, timeout=20)

    def test_local_tag_with_published_commit_can_build(self):
        self.assertEqual(self.git("ls-remote", self.remote.as_uri(), "v9.8.7").stdout, "")
        result = self.run_guard(submodules=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f'PLEBIAN_OS_REF="{self.published}"\n', self.output.read_text())

    def test_unpublished_release_commit_is_rejected(self):
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "commit", "-qm", "Unpublished", "--allow-empty")
        unpublished = self.git("rev-parse", "HEAD").stdout.strip()
        self.git("tag", "-f", "v9.8.7")
        result = self.run_guard()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"PLEBIAN_OS_REF={unpublished} is not fetchable", result.stderr)

    def test_other_missing_component_is_rejected(self):
        self.env.update(KILIX_REF="1" * 40, KILIX_REPO=self.remote.as_uri())
        result = self.run_guard()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("KILIX_REF=" + "1" * 40 + " is not fetchable", result.stderr)
        self.assertNotIn("PLEBIAN_OS_REF=", result.stderr)

    def test_development_image_still_checks_its_named_ref(self):
        self.env["PLEBIAN_OS_RELEASE_MODE"] = "0"
        result = self.run_guard()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PLEBIAN_OS_REF=v9.8.7 does not exist", result.stderr)
        self.assertIn('PLEBIAN_OS_REF="v9.8.7"\n', self.output.read_text())

    def test_unresolvable_checkout_is_rejected(self):
        self.env["HERE"] = str(self.root / "absent")
        result = self.run_guard()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("could not resolve release checkout commit", result.stderr)

    def test_candidate_commit_submodules_are_checked_without_public_tag(self):
        child = self.root / "child.git"
        self.git("init", "-q", "--bare", str(child))
        (self.checkout / ".gitmodules").write_text(
            '[submodule "nested"]\n\tpath = nested\n'
            '\turl = https://fixture.invalid/module.git\n')
        self.git("add", ".gitmodules")
        self.git("update-index", "--add", "--cacheinfo", "160000," + "2" * 40 + ",nested")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "commit", "-qm", "Missing submodule fixture")
        self.git("push", "-q", self.remote.as_uri(), "HEAD:refs/heads/candidate")
        self.git("tag", "-f", "v9.8.7")
        # Keep the production HTTPS-only submodule policy while using only
        # local fixture repositories; no network access is needed by the test.
        self.env.update(GIT_CONFIG_COUNT="1",
                        GIT_CONFIG_KEY_0=f"url.{child.as_uri()}.insteadOf",
                        GIT_CONFIG_VALUE_0="https://fixture.invalid/module.git")
        result = self.run_guard(submodules=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PLEBIAN_OS_REF -> nested gitlink", result.stderr)


if __name__ == "__main__":
    unittest.main()
