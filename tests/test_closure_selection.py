"""Release-closure selection: the mechanism UPGRADING.md's operator procedure
requires every release after 0.1.7 to ship.

The updater deliberately revalidates the installed release. These tests cover
the other half — validating a target release's complete closure and moving all
of its release-controlled keys into /etc/pleb/session.env as one unit, without
touching a single operator-controlled choice.
"""

import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
# The fixtures model root-owned system configuration, which is world readable
# even when the suite is launched from a Kilix shell with umask 077.
os.umask(0o022)
SELECT = ROOT / "provision" / "plebian-os-select-closure.sh"
UPDATE = ROOT / "provision" / "plebian-os-update.sh"
MANIFEST = ROOT / "releases" / "0.1.8.env"
UPGRADING = ROOT / "UPGRADING.md"
RELEASING = ROOT / "RELEASING.md"
NOTES = ROOT / "releases" / "0.1.8-notes.md"

# What a 0.1.7 image left in /etc/pleb/session.env. Every one of these is
# release-controlled and must move together.
INSTALLED_RELEASE_VALUES = [
    ("PLEB_REPO", "https://github.com/itsmygithubacct/pleb.git"),
    ("PLEB_BRANCH", ""),
    ("PLEB_REF", "0d860da201fbc0e75dfc1ed3eaebe3388e7fd570"),
    ("KILIX_REPO", "https://github.com/itsmygithubacct/kilix.git"),
    ("KILIX_BRANCH", ""),
    ("KILIX_REF", "6913364fe5f9eaa61258c0752b6ef12f55e49bc9"),
    ("KILIX_PREBUILT_VERSION", "0.47.4"),
    ("KILIX_PREBUILT_SHA256", "bc230142b2bd27f2a4bf1b1b67575f3d397a4ea2cc83f4ac2b912c306a939693"),
    ("KILIX_VOICE_REF", "f05b64a7b2bc25fa9a7e2c3ae1e0b848f04a23f6"),
    ("KILIX_VOICE_LIB_VERSION", "0.3.45"),
    ("KILIX_VOICE_LIB_URL", "https://files.pythonhosted.org/packages/fc/vosk.whl"),
    ("KILIX_VOICE_LIB_SHA256", "25e025093c4399d7278f543568ed8cc5460ac3a4bf48c23673ace1e25d26619f"),
    ("KILIX_VOICE_MODEL_URL", "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"),
    ("KILIX_VOICE_MODEL_SHA256", "30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498"),
    ("PLEBIAN_OS_INSTALL_VOICE_MODEL", "1"),
    ("PLEBIAN_OS_BUILD_KILIX_FORK", "1"),
    ("PLEBIAN_OS_KILIX_GO_MIN_VERSION", "1.26"),
    ("PLEBIAN_OS_KILIX_GO_VERSION", "go1.26.4"),
    ("PLEBIAN_OS_KILIX_GO_SHA256_AMD64", "a" * 64),
    ("PLEBIAN_OS_KILIX_GO_SHA256_ARM64", "b" * 64),
    ("KILIX95_REPO", "https://github.com/itsmygithubacct/kilix-95.git"),
    ("KILIX95_BRANCH", ""),
    ("KILIX95_REF", "cdc6d073d62e5929f14cd294f68a18eb1291b1da"),
    ("PLEBIAN_OS_VERSION", "0.1.7"),
    ("PLEBIAN_OS_RELEASE", "0.1.7"),
    ("PLEBIAN_OS_RELEASE_MODE", "1"),
    ("PLEBIAN_OS_REPO", "https://github.com/itsmygithubacct/plebian-os.git"),
    ("PLEBIAN_OS_BRANCH", ""),
    ("PLEBIAN_OS_REF", "1" * 40),
    ("PLEBIAN_OS_APT_SNAPSHOT", "20260712T000000Z"),
]

# Session, provider, storage, kiosk and layout choices. UPGRADING.md promises
# an upgrade preserves every one of them.
OPERATOR_VALUES = [
    ("PLEBIAN_OS_MANAGED_INSTALL", "1"),
    ("PLEB_DESKTOP", "1"),
    ("PLEB_WM", "none"),
    ("KILIX_RUN_ALIASES", "0"),
    ("KILIX_DESKTOP_PROVIDER", "cap"),
    ("KILIX_DESKTOP_FLAVOR", "xp"),
    ("KILIX95_AUTO_INSTALL", "0"),
    ("KILIX_CAP_AUTO_INSTALL", "1"),
]


def guarded(name: str, value: str) -> str:
    """The provisioner's exact write_session_default line shape."""
    return 'if [ -z "${%s+x}" ]; then %s=%s; fi' % (name, name, shlex.quote(value))


class ClosureSelectionTests(unittest.TestCase):
    # ── fixtures ────────────────────────────────────────────────────────────
    def _machine(self, base: Path, release=None, operator=None, extra_lines=()):
        """A provisioned machine: root-owned session config plus a data root."""
        release = INSTALLED_RELEASE_VALUES if release is None else release
        operator = OPERATOR_VALUES if operator is None else operator
        etc = base / "root" / "etc" / "pleb"
        etc.mkdir(parents=True)
        (base / "root" / "var" / "lib").mkdir(parents=True)
        home = base / "home" / ".local" / "gpu_terminal" / "sources"
        lines = ["# Managed by plebian-os-provision — Plebian-OS Pleb session config."]
        lines.append(guarded("GPU_TERMINAL_SOURCE_HOME", str(home)))
        lines.append(guarded("PLEBIAN_OS_DIR", str(base / "src")))
        lines.append(guarded("PLEB_DIR", str(home / "pleb")))
        lines.append(guarded("KILIX_DIR", str(home / "kilix")))
        for name, value in release:
            lines.append(guarded(name, value))
        for name, value in operator:
            lines.append(guarded(name, value))
        lines.append("export KILIX_DESKTOP_PROVIDER KILIX_DESKTOP_FLAVOR")
        lines.append("PLEB_RESPAWN=0   # operator note, deliberately unguarded")
        lines.extend(extra_lines)
        env = etc / "session.env"
        env.write_text("\n".join(lines) + "\n")
        env.chmod(0o644)
        return env

    def _manifest_text(self, drop=(), raw_lines=(), **changes) -> str:
        """The real 0.1.8 closure, optionally mutated key by key."""
        out, seen = [], set()
        for line in MANIFEST.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key = line.split("=", 1)[0]
                if key in drop:
                    continue
                if key in changes:
                    seen.add(key)
                    line = f"{key}={changes[key]}"
            out.append(line)
        for key, value in changes.items():
            if key not in seen:
                out.append(f"{key}={value}")
        out.extend(raw_lines)
        return "\n".join(out) + "\n"

    def _source(self, base: Path, manifest_text=None, version="0.1.8",
                release="0.1.8", tag="v0.1.8") -> str:
        """A Plebian-OS checkout carrying the published release tag."""
        src = base / "src"
        (src / "releases").mkdir(parents=True)
        (src / "VERSION").write_text(version + "\n")
        (src / "releases" / f"{release}.env").write_text(
            self._manifest_text() if manifest_text is None else manifest_text)
        git = ["git", "-C", str(src)]
        subprocess.run(git + ["init", "-q"], check=True)
        subprocess.run(git + ["config", "user.email", "t@example.invalid"], check=True)
        subprocess.run(git + ["config", "user.name", "t"], check=True)
        subprocess.run(
            git + ["remote", "add", "origin",
                   "https://github.com/itsmygithubacct/plebian-os.git"], check=True)
        subprocess.run(git + ["add", "-A"], check=True)
        subprocess.run(git + ["commit", "-qm", "release"], check=True)
        subprocess.run(git + ["tag", "-a", tag, "-m", tag], check=True)
        return subprocess.run(
            git + ["rev-parse", f"{tag}^{{commit}}"],
            capture_output=True, text=True, check=True).stdout.strip()

    def _run(self, base: Path, *args, fail_after=None):
        env = {
            "HOME": str(base / "home"),
            "PATH": os.environ["PATH"],
            "LANG": "C",
            "PLEBIAN_OS_CLOSURE_TEST_ROOT": str(base / "root"),
        }
        if fail_after is not None:
            env["PLEBIAN_OS_SELECT_TEST_FAIL_AFTER"] = fail_after
        return subprocess.run([str(SELECT), *args], env=env, text=True,
                              capture_output=True, check=False)

    @staticmethod
    def _values(env_path: Path) -> dict:
        """Read the file the way pleb-session does — by sourcing it."""
        script = (
            'set -e\n'
            'pre=" $(compgen -v | tr "\\n" " ") "\n'
            '. "$1"\n'
            'for n in $(compgen -v); do\n'
            '  case "$pre" in *" $n "*) continue ;; esac\n'
            '  case "$n" in pre|n) continue ;; esac\n'
            '  printf "%s=%s\\n" "$n" "${!n}"\n'
            'done\n'
        )
        out = subprocess.run(
            ["env", "-i", "bash", "--noprofile", "--norc", "-c", script,
             "bash", str(env_path)],
            capture_output=True, text=True, check=True).stdout
        return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)

    def _recovery_records(self, base: Path):
        recovery = base / "root" / "var" / "lib" / "plebian-os"
        if not recovery.is_dir():
            return []
        return sorted(p for p in recovery.iterdir()
                      if p.name.startswith("closure-rollback."))

    # ── a complete closure selects ──────────────────────────────────────────
    def test_complete_closure_selects_every_release_controlled_key(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base)
            commit = self._source(base)
            result = self._run(base, "0.1.8", "--offline")
            self.assertEqual(result.returncode, 0, result.stderr)
            after = self._values(env)
            manifest = dict(
                line.split("=", 1) for line in MANIFEST.read_text().splitlines()
                if "=" in line and not line.lstrip().startswith("#"))
            for key in ("PLEB_REF", "KILIX_REF", "KILIX95_REF", "KILIX_VOICE_REF",
                        "PLEBIAN_OS_APT_SNAPSHOT", "KILIX_PREBUILT_VERSION",
                        "KILIX_PREBUILT_SHA256", "PLEBIAN_OS_KILIX_GO_VERSION",
                        "PLEBIAN_OS_KILIX_GO_SHA256_AMD64",
                        "PLEBIAN_OS_KILIX_GO_SHA256_ARM64",
                        "KILIX_VOICE_LIB_URL", "KILIX_VOICE_MODEL_SHA256",
                        "PLEBIAN_OS_INSTALL_VOICE_MODEL"):
                self.assertEqual(after[key], manifest[key], key)
            self.assertEqual(after["PLEBIAN_OS_VERSION"], "0.1.8")
            self.assertEqual(after["PLEBIAN_OS_RELEASE"], "0.1.8")
            # The manifest names the movable tag; the machine keeps the commit.
            self.assertEqual(manifest["PLEBIAN_OS_REF"], "v0.1.8")
            self.assertEqual(after["PLEBIAN_OS_REF"], commit)
            self.assertIn("plebian-os-update --restart", result.stdout)
            self.assertIn("Do not run plebian-os-provision", result.stdout)

    def test_selection_adds_a_pin_the_installed_release_never_had(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            without_voice = [(k, v) for k, v in INSTALLED_RELEASE_VALUES
                             if not k.startswith("KILIX_VOICE_")]
            env = self._machine(base, release=without_voice)
            self._source(base)
            result = self._run(base, "0.1.8", "--offline")
            self.assertEqual(result.returncode, 0, result.stderr)
            after = self._values(env)
            self.assertEqual(after["KILIX_VOICE_REF"],
                             "eda9ca90eed677fa4fca383e7b8ad2fc85e54b0e")
            self.assertIn("closure adds 6 key(s) this release introduces", result.stdout)

    # ── operator-controlled keys survive ────────────────────────────────────
    def test_operator_controlled_choices_survive_selection(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base)
            before_lines = env.read_text().splitlines()
            self._source(base)
            self.assertEqual(self._run(base, "0.1.8", "--offline").returncode, 0)
            after = self._values(env)
            for name, value in OPERATOR_VALUES:
                self.assertEqual(after[name], value, name)
            after_lines = env.read_text().splitlines()
            release_names = {name for name, _ in INSTALLED_RELEASE_VALUES}
            release_names |= {"PLEBIAN_OS_RELEASE"}
            kept_before = [line for line in before_lines
                           if not any(f"${{{n}+x}}" in line for n in release_names)]
            kept_after = [line for line in after_lines
                          if not any(f"${{{n}+x}}" in line for n in release_names)]
            self.assertEqual(kept_before, kept_after)
            self.assertIn("PLEB_RESPAWN=0   # operator note, deliberately unguarded",
                          after_lines)

    # ── an incomplete or malformed closure is refused, by name ──────────────
    def _refuses(self, base: Path, expected: str, *args):
        env = base / "root" / "etc" / "pleb" / "session.env"
        before = env.read_bytes()
        result = self._run(base, "0.1.8", "--offline", *args)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(expected, result.stderr)
        self.assertEqual(env.read_bytes(), before)
        self.assertEqual(self._recovery_records(base), [])
        return result

    def test_incomplete_closure_is_refused_and_names_the_missing_pins(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(base, self._manifest_text(drop=("KILIX_REF", "PLEB_REF")))
            result = self._refuses(base, "incomplete closure")
            self.assertIn("KILIX_REF", result.stderr)
            self.assertIn("PLEB_REF", result.stderr)

    def test_undeclared_branch_key_is_refused_by_name(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(base, self._manifest_text(drop=("KILIX95_BRANCH",)))
            self._refuses(base, "these must be declared, even empty: KILIX95_BRANCH")

    def test_branch_pin_in_a_release_closure_is_refused_by_name(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(base, self._manifest_text(PLEB_BRANCH="main"))
            self._refuses(base, "PLEB_BRANCH must be empty in a release closure")

    def test_malformed_manifest_line_is_refused_by_name(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(base, self._manifest_text(raw_lines=("KILIX_REF_WITHOUT_VALUE",)))
            self._refuses(base, "invalid manifest line: KILIX_REF_WITHOUT_VALUE")

    def test_duplicate_manifest_key_is_refused_by_name(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(base, self._manifest_text(raw_lines=("KILIX_REF=" + "c" * 40,)))
            self._refuses(base, "duplicate manifest key: KILIX_REF")

    def test_placeholder_pin_is_refused_by_name(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(base, self._manifest_text(KILIX95_REF="REPLACE_ME"))
            self._refuses(base, "KILIX95_REF is still REPLACE_ME")

    def test_short_commit_pin_is_refused_by_name(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(base, self._manifest_text(KILIX_REF="df641fb"))
            self._refuses(base, "KILIX_REF must be a full 40-character lowercase commit SHA")

    def test_half_pinned_optional_closure_is_refused_by_name(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(base, self._manifest_text(drop=("KILIX_VOICE_MODEL_SHA256",)))
            self._refuses(base, "PLEBIAN_OS_INSTALL_VOICE_MODEL=1 needs pinned values for")

    # ── a closure whose version disagrees with the artifact is refused ──────
    def test_manifest_version_disagreeing_with_the_release_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(base, self._manifest_text(PLEBIAN_OS_VERSION="0.1.7"))
            self._refuses(base, "PLEBIAN_OS_VERSION is '0.1.7', not 0.1.8")

    def test_manifest_version_disagreeing_with_the_artifact_VERSION_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(base, version="0.1.9")
            self._refuses(base, "the release commit's VERSION reads '0.1.9', not 0.1.8")

    def test_release_mode_must_be_declared(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(base, self._manifest_text(PLEBIAN_OS_RELEASE_MODE="0"))
            self._refuses(base, "PLEBIAN_OS_RELEASE_MODE must be 1")

    def test_os_ref_naming_another_release_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(base, self._manifest_text(PLEBIAN_OS_REF="v0.1.7"))
            self._refuses(base, "PLEBIAN_OS_REF must be v0.1.8")

    def test_missing_release_tag_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(base, tag="v0.1.7", release="0.1.8")
            result = self._refuses(base, "release tag v0.1.8 is not in")
            self.assertIn("--offline forbids fetching it", result.stderr)

    # ── a hand edit outside the managed form is refused ─────────────────────
    def test_unmanaged_release_key_edit_is_refused_by_name(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base, extra_lines=("KILIX_REF=" + "d" * 40,))
            self._source(base)
            self._refuses(base, "sets the release-controlled key KILIX_REF outside the managed form")

    # ── a failure mid-write leaves the previous closure intact ──────────────
    def _fails_intact(self, base: Path, boundary: str, expected: str):
        env = base / "root" / "etc" / "pleb" / "session.env"
        before = env.read_bytes()
        result = self._run(base, "0.1.8", "--offline", fail_after=boundary)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(expected, result.stderr)
        self.assertEqual(env.read_bytes(), before)
        leftovers = list((base / "root" / "etc" / "pleb").glob(".session.env.*"))
        self.assertEqual(leftovers, [])
        return result

    def test_failure_before_the_write_leaves_the_previous_closure_intact(self):
        for boundary in ("render", "verify"):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                self._machine(base)
                self._source(base)
                self._fails_intact(
                    base, boundary,
                    f"injected closure selection failure after {boundary}")
                self.assertEqual(self._recovery_records(base), [])

    def test_failure_mid_write_leaves_the_previous_closure_intact(self):
        for boundary in ("backup", "stage"):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                self._machine(base)
                self._source(base)
                self._fails_intact(
                    base, boundary,
                    "the previous closure is still selected")
                # A half-finished selection leaves no recovery record claiming
                # to hold a closure that was never replaced.
                self.assertEqual(self._recovery_records(base), [])

    def test_a_failed_selection_can_be_retried_and_then_succeeds(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base)
            self._source(base)
            self._fails_intact(base, "stage", "the previous closure is still selected")
            self.assertEqual(self._run(base, "0.1.8", "--offline").returncode, 0)
            self.assertEqual(self._values(env)["PLEBIAN_OS_VERSION"], "0.1.8")

    # ── a backwards selection is announced ──────────────────────────────────
    def test_backwards_selection_is_announced_as_a_downgrade(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            newer = [(k, "0.1.9" if k in ("PLEBIAN_OS_VERSION", "PLEBIAN_OS_RELEASE") else v)
                     for k, v in INSTALLED_RELEASE_VALUES]
            self._machine(base, release=newer)
            self._source(base)
            result = self._run(base, "0.1.8", "--offline")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("closure: 0.1.9 -> 0.1.8 (DOWNGRADE, pinned by releases/0.1.8.env@",
                          result.stderr)
            self.assertIn("the installed release was newer", result.stderr)

    def test_forward_selection_is_not_announced_as_a_downgrade(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(base)
            result = self._run(base, "0.1.8", "--offline")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("DOWNGRADE", result.stderr)
            self.assertIn("closure: 0.1.7 -> 0.1.8 (pinned by releases/0.1.8.env@",
                          result.stdout)

    # ── the previous closure is recoverable ─────────────────────────────────
    def test_rollback_restores_the_previous_closure_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base)
            before = env.read_bytes()
            self._source(base)
            self.assertEqual(self._run(base, "0.1.8", "--offline").returncode, 0)
            self.assertNotEqual(env.read_bytes(), before)
            records = self._recovery_records(base)
            self.assertEqual(len(records), 1)
            self.assertEqual((records[0] / "session.env").read_bytes(), before)
            self.assertIn("to=0.1.8", (records[0] / "meta").read_text())
            result = self._run(base, "--rollback")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(env.read_bytes(), before)
            # One record is one undo; a second call has nothing left to restore.
            again = self._run(base, "--rollback")
            self.assertNotEqual(again.returncode, 0)
            self.assertIn("no closure to roll back to", again.stderr)

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base)
            before = env.read_bytes()
            self._source(base)
            result = self._run(base, "0.1.8", "--offline", "--dry-run")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("nothing was written", result.stdout)
            self.assertEqual(env.read_bytes(), before)
            self.assertEqual(self._recovery_records(base), [])

    def test_show_reports_the_installed_closure(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            result = self._run(base, "--show")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("PLEBIAN_OS_VERSION=0.1.7", result.stdout)
            self.assertIn("KILIX_REF=6913364fe5f9eaa61258c0752b6ef12f55e49bc9",
                          result.stdout)


class ClosureSelectionContractTests(unittest.TestCase):
    """The selector is an operator tool with a privilege boundary and a
    documented place in the upgrade order."""

    def test_selector_refuses_to_run_as_root_like_the_updater(self):
        source = SELECT.read_text()
        self.assertIn("require_unprivileged_selector", source)
        self.assertIn(
            "run plebian-os-select-closure without sudo (it elevates only bounded system steps)",
            source)
        # The updater's own guard is untouched.
        self.assertIn(
            "run plebian-os-update without sudo (it elevates only bounded system steps)",
            UPDATE.read_text())

    def test_the_write_is_one_rename_after_a_backup(self):
        source = SELECT.read_text()
        self.assertIn("mv -fT -- \"$tmp\" \"$env_path\"", source)
        self.assertIn('cp -a -- "$env_path" "$record/session.env"', source)
        self.assertLess(source.index('cp -a -- "$env_path" "$record/session.env"'),
                        source.index('mv -fT -- "$tmp" "$env_path"'))
        # Nothing is written before the rendered file has been verified.
        self.assertLess(source.index("verify_candidate_closure "),
                        source.index("apply_selected_closure\n"))

    def test_upgrade_policy_names_the_concrete_command(self):
        text = UPGRADING.read_text()
        self.assertIn("plebian-os-select-closure", text)
        self.assertLess(text.index("plebian-os-select-closure"),
                        text.index("plebian-os-update --restart"))

    def test_release_procedure_requires_a_selection_mechanism_per_release(self):
        text = RELEASING.read_text()
        self.assertIn("plebian-os-select-closure", text)

    def test_target_release_notes_name_the_operator_command(self):
        text = NOTES.read_text()
        self.assertIn("plebian-os-select-closure", text)
        self.assertIn("provision/plebian-os-select-closure.sh", text)


if __name__ == "__main__":
    unittest.main()
