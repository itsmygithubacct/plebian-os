"""The selected closure records its exact release tag, and only a recorded
candidate moves to its published final. Disposable Git fixtures only; no ISO,
VM, installed updater or release acceptance is produced."""
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

import test_closure_selection as closure_fixtures

ROOT = Path(__file__).resolve().parents[1]
UPDATE = ROOT / "provision" / "plebian-os-update.sh"
PROVISION = ROOT / "provision" / "plebian-os-provision.sh"
REMASTER = ROOT / "build" / "remaster-iso.sh"
IDENTITY = ("PLEBIAN_OS_RELEASE_TAG", "PLEBIAN_OS_RELEASE_TAG_OBJECT")


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def shell_function(path: Path, name: str) -> str:
    return re.search(rf"^{name}\(\) \{{.*?^\}}", path.read_text(), re.S | re.M)[0]


class SelectorRecordsReleaseTagTests(unittest.TestCase):
    def setUp(self):
        self.fx = closure_fixtures.ClosureSelectionTests()

    def _rc_then_final(self, base: Path):
        """A 0.2.1 source with v0.2.1-rc1 and, one commit later, v0.2.1."""
        requirements = (ROOT / "releases/0.2.1.requirements").read_text()
        rc_commit = self.fx._source(
            base, self.fx._f120_manifest_text(PLEBIAN_OS_REF="v0.2.1-rc1"),
            version="0.2.1", release="0.2.1", tag="v0.2.1-rc1",
            requirements_text=requirements)
        src = base / "src"
        (src / "releases/0.2.1.env").write_text(self.fx._f120_manifest_text())
        git(src, "commit", "-qam", "final")
        git(src, "tag", "-a", "v0.2.1", "-m", "v0.2.1")
        return {
            "rc": git(src, "rev-parse", "refs/tags/v0.2.1-rc1"),
            "final": git(src, "rev-parse", "refs/tags/v0.2.1"),
            "rc_commit": rc_commit,
            "final_commit": git(src, "rev-parse", "HEAD"),
        }

    def _select_rc(self, base, ids):
        r = self.fx._run(base, "0.2.1", "--release-tag", "v0.2.1-rc1", "--offline",
                         env_extra={"PLEBIAN_OS_TRUSTED_TAG_OBJECT_SHA": ids["rc"]},
                         trust_tag=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def _pair(self, base):
        etc = base / "root/etc/pleb"
        return ((etc / "session.env").read_bytes(), (etc / "closure.env").read_bytes())

    def test_selection_records_tag_and_object_and_rollback_restores_the_record(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self.fx._machine(base)
            ids = self._rc_then_final(base)
            self._select_rc(base, ids)
            closure = (base / "root/etc/pleb/closure.env").read_text()
            self.assertIn("PLEBIAN_OS_RELEASE_TAG=v0.2.1-rc1\n", closure)
            self.assertIn(f"PLEBIAN_OS_RELEASE_TAG_OBJECT={ids['rc']}\n", closure)
            values = self.fx._values(base / "root/etc/pleb/session.env")
            self.assertEqual(values["PLEBIAN_OS_VERSION"], "0.2.1")
            self.assertEqual(values["PLEBIAN_OS_REF"], ids["rc_commit"])
            show = self.fx._run(base, "--show")
            self.assertIn("  PLEBIAN_OS_RELEASE_TAG=v0.2.1-rc1\n", show.stdout)
            after_rc = self._pair(base)
            first, = self.fx._recovery_records(base)

            final = self.fx._run(base, "0.2.1", "--offline")
            self.assertEqual(final.returncode, 0, final.stdout + final.stderr)
            self.assertIn("closure: v0.2.1-rc1 -> v0.2.1 (same VERSION 0.2.1", final.stdout)
            values = self.fx._values(base / "root/etc/pleb/session.env")
            self.assertEqual(values["PLEBIAN_OS_RELEASE_TAG"], "v0.2.1")
            self.assertEqual(values["PLEBIAN_OS_RELEASE_TAG_OBJECT"], ids["final"])
            self.assertEqual(values["PLEBIAN_OS_REF"], ids["final_commit"])

            # Reproduce two snapshots in one second with their random suffixes
            # in reverse order. The second selection must roll back to the RC.
            second, = set(self.fx._recovery_records(base)) - {first}
            for number, (record, suffix) in enumerate(((first, "zzzzzz"), (second, "aaaaaa"))):
                record = record.rename(record.with_name("closure-rollback.20261116T000000Z." + suffix))
                stamp = 1_794_787_200_000_000_000 + number * 100_000_000
                os.utime(record / "meta", ns=(stamp, stamp))

            back = self.fx._run(base, "--rollback")
            self.assertEqual(back.returncode, 0, back.stdout + back.stderr)
            self.assertEqual(self._pair(base), after_rc)

    def test_failed_final_apply_leaves_the_candidate_closure_and_record(self):
        for boundary in ("session", "closure", "selector", "updater"):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                self.fx._machine(base)
                ids = self._rc_then_final(base)
                self._select_rc(base, ids)
                after_rc = self._pair(base)
                failed = self.fx._run(base, "0.2.1", "--offline", fail_after=boundary)
                self.assertNotEqual(failed.returncode, 0, failed.stdout)
                self.assertEqual(self._pair(base), after_rc)
                self.assertIn("PLEBIAN_OS_RELEASE_TAG=v0.2.1-rc1\n",
                              (base / "root/etc/pleb/closure.env").read_text())

    def test_unrecorded_machine_gains_the_record_and_rolls_back_to_none(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            session = self.fx._machine(base)
            before = session.read_bytes()
            ids = self._rc_then_final(base)
            self._select_rc(base, ids)
            self.assertEqual(self.fx._run(base, "--rollback").returncode, 0)
            self.assertEqual(session.read_bytes(), before)
            values = self.fx._values(session)
            for key in IDENTITY:
                self.assertNotIn(key, values)

    def test_a_manifest_cannot_pin_the_recorded_identity(self):
        for key in IDENTITY:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                self.fx._machine(base)
                self.fx._source(base, self.fx._manifest_text(**{key: "v0.1.8"}))
                r = self.fx._run(base, "0.1.8", "--offline", "--dry-run")
                self.assertNotEqual(r.returncode, 0)
                self.assertIn(f"{key} is recorded by the selection", r.stderr)

    def test_development_selection_records_no_release_tag(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self.fx._machine(base)
            ids = self._rc_then_final(base)
            self._select_rc(base, ids)
            dev = self.fx._run(base, "0.2.1", "--development-commit", ids["final_commit"],
                               "--offline", trust_tag=False)
            self.assertEqual(dev.returncode, 0, dev.stdout + dev.stderr)
            values = self.fx._values(base / "root/etc/pleb/session.env")
            self.assertEqual(values["PLEBIAN_OS_RELEASE_TAG"], "")
            self.assertEqual(values["PLEBIAN_OS_RELEASE_TAG_OBJECT"], "")


class UpdaterMovesRecordedCandidateTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="release-tag-record-")
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        # Never read this host's /etc/pleb configuration.
        self.update = self.base / "update.sh"
        self.update.write_text(UPDATE.read_text().replace(
            "/etc/pleb/session.env", str(self.base / "session.env")).replace(
            "/etc/pleb/closure.env", str(self.base / "closure.env")))
        self.log = self.base / "selector.log"

    def _published(self, tags):
        repo = self.base / "published"
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        git(repo, "config", "user.name", "test")
        git(repo, "config", "user.email", "test@example.invalid")
        (repo / "provision").mkdir()
        for version, tag in tags:
            (repo / "VERSION").write_text(version + "\n")
            selector = repo / "provision/plebian-os-select-closure.sh"
            # Each tag's selector names itself, then stops the hop before the
            # updater relaunch so no installed tool is needed.
            selector.write_text(
                "#!/bin/bash\n"
                f"printf '{tag} %s\\n' \"$*\" >>{str(self.log)!r}\n"
                "exit 5\n")
            git(repo, "add", "-A")
            git(repo, "commit", "-qm", tag)
            git(repo, "tag", "-a", tag, "-m", tag)
        checkout = self.base / "checkout"
        subprocess.run(["git", "clone", "-q", str(repo), str(checkout)], check=True)
        return repo, checkout

    def _object(self, tag):
        return git(self.base / "published", "rev-parse", f"refs/tags/{tag}")

    def _select_latest(self, repo, checkout, **identity):
        env = os.environ.copy()
        for key in IDENTITY:
            env.pop(key, None)
        env.update({
            "PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY": "1",
            "PLEBIAN_OS_REPO": str(repo),
            "PLEBIAN_OS_DIR": str(checkout),
            "PLEBIAN_OS_VERSION": "0.2.1",
            **identity,
        })
        command = ('update_path=$1; set --; source "$update_path"; '
                   'select_latest_release=1; restart_arg=--no-restart; '
                   'select_latest_release_if_needed')
        return subprocess.run(["bash", "-c", command, "bash", str(self.update)],
                              env=env, text=True, capture_output=True, check=False)

    def _calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    FINAL = (("0.2.0", "v0.2.0"), ("0.2.1", "v0.2.1-rc1"), ("0.2.1", "v0.2.1"))

    def test_recorded_candidate_selects_the_published_final_through_its_selector(self):
        repo, checkout = self._published(self.FINAL)
        r = self._select_latest(repo, checkout, PLEBIAN_OS_RELEASE_TAG="v0.2.1-rc1",
                                PLEBIAN_OS_RELEASE_TAG_OBJECT=self._object("v0.2.1-rc1"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("release candidate v0.2.1-rc1 is selected and final release "
                      "v0.2.1 is published", r.stdout)
        self.assertIn("new published release found: v0.2.1-rc1 -> v0.2.1", r.stdout)
        self.assertIn("target release 0.2.1 closure selection failed (status 5)", r.stderr)
        self.assertEqual(self._calls(), [f"v0.2.1 0.2.1 --source {checkout}"])

    def test_final_or_unrecorded_closure_is_left_as_the_latest(self):
        repo, checkout = self._published(self.FINAL)
        for identity in ({"PLEBIAN_OS_RELEASE_TAG": "v0.2.1",
                          "PLEBIAN_OS_RELEASE_TAG_OBJECT": self._object("v0.2.1")},
                         {},
                         {"PLEBIAN_OS_RELEASE_TAG": "v0.2.1-rc1",
                          "PLEBIAN_OS_RELEASE_TAG_OBJECT": "not-an-object"},
                         {"PLEBIAN_OS_RELEASE_TAG": "v0.2.0-rc1",
                          "PLEBIAN_OS_RELEASE_TAG_OBJECT": "a" * 40}):
            with self.subTest(identity=identity):
                r = self._select_latest(repo, checkout, **identity)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn("Plebian-OS 0.2.1 is the latest published release", r.stdout)
                self.assertEqual(self._calls(), [])
                if (identity.get("PLEBIAN_OS_RELEASE_TAG_OBJECT") == "not-an-object"
                        or identity.get("PLEBIAN_OS_RELEASE_TAG") == "v0.2.0-rc1"):
                    self.assertIn("ignoring recorded release tag", r.stderr)

    def test_recorded_candidate_with_only_candidates_published_does_not_move(self):
        repo, checkout = self._published(
            (("0.2.0", "v0.2.0"), ("0.2.1", "v0.2.1-rc1"), ("0.2.1", "v0.2.1-rc2")))
        r = self._select_latest(repo, checkout, PLEBIAN_OS_RELEASE_TAG="v0.2.1-rc1",
                                PLEBIAN_OS_RELEASE_TAG_OBJECT=self._object("v0.2.1-rc1"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("refusing an implicit downgrade", r.stderr)
        self.assertEqual(self._calls(), [])

    def test_local_candidate_gate_ignores_the_recorded_identity_keys(self):
        repo = self.base / "candidate"
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        git(repo, "config", "user.name", "test")
        git(repo, "config", "user.email", "test@example.invalid")
        (repo / "VERSION").write_text("0.2.2\n")
        (repo / "releases").mkdir()
        (repo / "provision").mkdir()
        (repo / "releases/0.2.2.env").write_text(
            "PLEBIAN_OS_VERSION=0.2.2\nPLEBIAN_OS_RELEASE_MODE=1\nPLEBIAN_OS_REF=v0.2.2-rc1\n")
        selector = repo / "provision/plebian-os-select-closure.sh"
        selector.write_text(
            "#!/bin/bash\n"
            "echo '  PLEBIAN_OS_VERSION=0.2.2'\n"
            "echo '  PLEBIAN_OS_RELEASE=0.2.2'\n"
            "echo '  PLEBIAN_OS_RELEASE_MODE=1'\n"
            "printf '  PLEBIAN_OS_REF=%s\\n' \"$PLEBIAN_OS_REF\"\n"
            "printf '  PLEBIAN_OS_RELEASE_TAG=%s\\n' \"$PLEBIAN_OS_RELEASE_TAG\"\n"
            "printf '  PLEBIAN_OS_RELEASE_TAG_OBJECT=%s\\n' \"$PLEBIAN_OS_RELEASE_TAG_OBJECT\"\n")
        (repo / "provision/plebian-os-update.sh").write_text("candidate updater bytes\n")
        git(repo, "add", ".")
        git(repo, "commit", "-qm", "candidate")
        git(repo, "tag", "-a", "v0.2.2-rc1", "-m", "candidate")
        installed_selector = self.base / "installed-selector"
        installed_selector.write_bytes(selector.read_bytes())
        installed_selector.chmod(0o700)
        installed_updater = self.base / "installed-updater"
        installed_updater.write_bytes((repo / "provision/plebian-os-update.sh").read_bytes())
        env = dict(os.environ, PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY="1", PLEBIAN_OS_DIR=str(repo),
                   PLEBIAN_OS_RELEASE_MODE="1", PLEBIAN_OS_RELEASE="0.2.2",
                   PLEBIAN_OS_VERSION="0.2.2", PLEBIAN_OS_REF=git(repo, "rev-parse", "HEAD"),
                   PLEBIAN_OS_RELEASE_TAG="v0.2.2-rc1",
                   PLEBIAN_OS_RELEASE_TAG_OBJECT=git(repo, "rev-parse", "refs/tags/v0.2.2-rc1"),
                   PLEBIAN_OS_INSTALLED_SELECTOR=str(installed_selector),
                   PLEBIAN_OS_INSTALLED_UPDATER=str(installed_updater))
        r = subprocess.run(["bash", "-c", 'update_path=$1; set --; source "$update_path"; '
                            'local_candidate_matches_selected_closure 0.2.2',
                            "bash", str(self.update)], env=env, text=True, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_session_gate_admits_the_identity_names(self):
        source = UPDATE.read_text()
        names = source.split('NAMES = frozenset("""', 1)[1].split('""")', 1)[0].split()
        for key in IDENTITY:
            self.assertIn(key, names)


class ImagesRecordTheirTagTests(unittest.TestCase):
    def _repo(self, base: Path, tag: str, annotated=True):
        repo = base / "repo"
        repo.mkdir()
        (repo / "VERSION").write_text("0.2.3\n")
        git(repo, "init", "-q")
        git(repo, "config", "user.name", "fixture")
        git(repo, "config", "user.email", "fixture@example.invalid")
        git(repo, "add", ".")
        git(repo, "commit", "-qm", "fixture")
        git(repo, "tag", *(["-a", tag, "-m", tag] if annotated else [tag]))
        return repo

    def _identity(self, repo: Path, **env):
        script = shell_function(REMASTER, "firstboot_release_identity") + "\nfirstboot_release_identity"
        full = {"PATH": os.environ["PATH"], "HERE": str(repo), "PLEBIAN_OS_VERSION": "0.2.3",
                "PLEBIAN_OS_RELEASE_MODE": "1", **env}
        return subprocess.run(["bash", "-c", script], env=full, text=True, capture_output=True)

    def test_release_image_records_its_candidate_or_final_tag_object(self):
        for tag in ("v0.2.3-rc1", "v0.2.3"):
            with self.subTest(tag=tag), tempfile.TemporaryDirectory() as td:
                repo = self._repo(Path(td), tag)
                r = self._identity(repo, PLEBIAN_OS_REF=tag)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(r.stdout, f"{tag} {git(repo, 'rev-parse', f'refs/tags/{tag}')}\n")

    def test_other_builds_record_nothing_and_a_moved_tag_refuses(self):
        with tempfile.TemporaryDirectory() as td:
            repo = self._repo(Path(td), "v0.2.3-rc1")
            commit = git(repo, "rev-parse", "HEAD")
            for env in ({"PLEBIAN_OS_REF": commit},
                        {"PLEBIAN_OS_REF": "v0.2.3-rc1", "PLEBIAN_OS_RELEASE_MODE": "0"},
                        {"PLEBIAN_OS_REF": "v0.2.3-beta1"},
                        {"PLEBIAN_OS_REF": "v0.2.4-rc1"}):
                with self.subTest(env=env):
                    r = self._identity(repo, **env)
                    self.assertEqual((r.returncode, r.stdout), (0, ""), r.stderr)
            (repo / "later").write_text("later\n")
            git(repo, "add", ".")
            git(repo, "commit", "-qm", "later")
            r = self._identity(repo, PLEBIAN_OS_REF="v0.2.3-rc1")
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("does not name the checked-out commit", r.stderr)

    def test_firstboot_env_and_provision_carry_the_identity(self):
        remaster = REMASTER.read_text()
        firstboot = shell_function(REMASTER, "write_firstboot_env")
        self.assertIn('BUILD_RELEASE_IDENTITY="$(firstboot_release_identity)" || exit 1', remaster)
        builder = shell_function(REMASTER, "write_build_info")
        provision = PROVISION.read_text()
        for key in IDENTITY:
            self.assertIn(f'env_kv {key} "$', firstboot)
            self.assertIn(f'manifest_kv {key} "$', builder)
            self.assertIn(f'write_session_default {key} "${key}"', provision)
        # Resolved after the release checks, before either writer runs.
        resolved = remaster.index('BUILD_RELEASE_IDENTITY="$(firstboot_release_identity)"')
        self.assertLess(remaster.index("\nrelease_mode_check\n"), resolved)
        self.assertLess(resolved, remaster.index('write_build_info "$EXTRACT'))
        self.assertLess(resolved, remaster.index('write_firstboot_env "$EXTRACT'))

    def test_provision_accepts_only_a_coherent_identity(self):
        function = shell_function(PROVISION, "validate_release_identity")
        prelude = 'die() { printf "%s\\n" "$*" >&2; exit 1; }\n'
        obj = "a" * 40
        for tag, value, ok in (("", "", True), ("v0.2.3", obj, True), ("v0.2.3-rc9", obj, True),
                               ("v0.2.3-rc9", "", False), ("", obj, False),
                               ("v0.2.4-rc1", obj, False), ("v0.2.3-rc0", obj, False),
                               ("v0.2.3", "A" * 40, False)):
            with self.subTest(tag=tag, value=value):
                env = {"PATH": os.environ["PATH"], "PLEBIAN_OS_VERSION": "0.2.3",
                       "PLEBIAN_OS_RELEASE_TAG": tag, "PLEBIAN_OS_RELEASE_TAG_OBJECT": value}
                r = subprocess.run(["bash", "-c", prelude + function + "\nvalidate_release_identity"],
                                   env=env, text=True, capture_output=True)
                self.assertEqual(r.returncode == 0, ok, r.stderr)


if __name__ == "__main__":
    unittest.main()
