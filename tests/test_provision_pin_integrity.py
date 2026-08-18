"""What a re-provision is not allowed to reset.

`sudo plebian-os-provision` rewrites /etc/pleb/session.env wholesale at the end
of every run, and that file is where an installed machine keeps its release
closure. Once the provisioner started reaching its end on a pinned install
instead of failing early on the detached checkout, everything it did not read
back first was rewritten to a built-in default: the desktop provider fell from
`external` to `auto`, and the pinned Kilix Voice library and model URLs, their
checksums and the Go toolchain version and per-architecture hashes were blanked.
The machine still booted, and the next update still exited 0 — with the voice
media and the Go toolchain no longer pinned to anything.

The classification of what a release controls is not invented here. It is
plebian-os-select-closure.sh's, read out of that tool through its own `--show`
interface, so a key added to the closure is covered by these tests the day it is
added.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
# These fixtures model root-owned system configuration, which is world readable
# even when the suite is launched from a Kilix shell with umask 077.
os.umask(0o022)
PROVISION = ROOT / "provision" / "plebian-os-provision.sh"
SELECT = ROOT / "provision" / "plebian-os-select-closure.sh"

# A machine pinned to a complete closure. Shapes match a real installed
# session.env: exact commits, exact archive checksums, exact URLs.
INSTALLED_CLOSURE = {
    "PLEBIAN_OS_VERSION": "0.2.0",
    "PLEBIAN_OS_RELEASE": "0.2.0",
    "PLEBIAN_OS_RELEASE_MODE": "1",
    "PLEBIAN_OS_REPO": "https://github.com/itsmygithubacct/plebian-os.git",
    "PLEBIAN_OS_BRANCH": "",
    "PLEBIAN_OS_REF": "1" * 40,
    "PLEB_REPO": "https://github.com/itsmygithubacct/pleb.git",
    "PLEB_BRANCH": "",
    "PLEB_REF": "2" * 40,
    "KILIX_REPO": "https://github.com/itsmygithubacct/kilix.git",
    "KILIX_BRANCH": "",
    "KILIX_REF": "3" * 40,
    "KILIX95_REPO": "https://github.com/itsmygithubacct/kilix-95.git",
    "KILIX95_BRANCH": "",
    "KILIX95_REF": "4" * 40,
    "PLEBIAN_OS_APT_SNAPSHOT": "20260727T000000Z",
    "PLEBIAN_OS_INSTALL_UV": "1",
    "PLEBIAN_OS_UV_VERSION": "0.12.3",
    "PLEBIAN_OS_UV_INSTALLER_SHA256": "b" * 64,
    "KILIX_PREBUILT_VERSION": "0.47.3",
    "KILIX_PREBUILT_SHA256": "5" * 64,
    "PLEBIAN_OS_BUILD_KILIX_FORK": "0",
    "PLEBIAN_OS_KILIX_GO_MIN_VERSION": "1.25",
    "PLEBIAN_OS_KILIX_GO_VERSION": "go1.26.5",
    "PLEBIAN_OS_KILIX_GO_SHA256_AMD64": "6" * 64,
    "PLEBIAN_OS_KILIX_GO_SHA256_ARM64": "7" * 64,
    "PLEBIAN_OS_INSTALL_VOICE_MODEL": "1",
    "KILIX_VOICE_REF": "8" * 40,
    "KILIX_VOICE_LIB_VERSION": "0.3.45",
    "KILIX_VOICE_LIB_URL": "https://files.pythonhosted.org/packages/fc/vosk.whl",
    "KILIX_VOICE_LIB_SHA256": "9" * 64,
    "KILIX_VOICE_MODEL_URL":
        "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
    "KILIX_VOICE_MODEL_SHA256": "a" * 64,
    "PLEBIAN_OS_INSTALL_WAYDROID": "1",
    "PLEBIAN_OS_WAYDROID_CLOSURE_SHA256": "b" * 64,
}

# The desktop selection. The selector preserves these as operator-controlled;
# the release image pins them (0.1.8 ships KILIX_DESKTOP_PROVIDER=external), and
# a re-provision reset the provider to `auto` on exactly that machine.
INSTALLED_SELECTION = {
    "KILIX_DESKTOP_PROVIDER": "external",
    "KILIX_DESKTOP_COMMAND": "",
    "KILIX_DESKTOP_NAME": "desktop",
    "KILIX_DESKTOP_FLAVOR": "95",
}

# Optional desktop-provider checkouts. A release closure does not pin them, and
# an image that ships none still records them — empty, but recorded.
INSTALLED_PROVIDER_PINS = {
    "KILIX_CAP_REF": "",
    "KILIX_TUI_UTILS_REF": "",
    "KILIX_LAND_DESKTOP_REF": "",
}

INSTALLED_OPTIONAL_DESKTOP_POLICY = {
    "KILIX_CAP_AUTO_INSTALL": "0",
    "KILIX_TUI_UTILS_AUTO_INSTALL": "0",
    "KILIX_LAND_DESKTOP_AUTO_INSTALL": "0",
}

# Storage paths and install policy, which a re-provision resolves for itself
# from the target user and /etc/default/plebian-os. They are in the fixture to
# prove the restore does not drag them in.
UNRELATED = {
    "PLEB_DIR": "/somewhere/else/pleb",
    "PLEBIAN_OS_KIOSK": "1",
    "PLEB_WM": "none",
}


def clean_env(**overrides: str) -> dict[str, str]:
    """An environment that has told the provisioner nothing.

    The suite is meant to be launched with `env -i`, but these tests are about
    the difference between "the operator asked for this" and "this is a built-in
    default", and a Kilix shell exports enough of both namespaces to blur it.
    """
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("KILIX_", "KILIX95_", "PLEB_", "PLEBIAN_OS_"))}
    env.update(overrides)
    return env


def session_env_text(values: dict[str, str]) -> str:
    # Exactly what write_session_default emits.
    return "".join(
        'if [ -z "${%s+x}" ]; then %s=%s; fi\n' % (key, key, value or "''")
        for key, value in values.items()
    )


class ReleaseControlledClassificationTests(unittest.TestCase):
    """One classification, declared in two places that cannot read each other.

    plebian-os-provision is installed as a single file in /usr/local/sbin (the
    preseed's late_command and the updater's OS layer copy exactly that file,
    with no sibling to source), and UPGRADING.md has the operator run the
    selector as a standalone file extracted straight out of the target release's
    tag. So both carry the list — and this test refuses to pass unless the two
    are identical, which is what keeps a third hand-maintained list from drifting
    the way the pin-integrity defect drifted.
    """

    def test_the_provisioner_and_the_selector_agree_on_what_a_release_controls(self):
        self.assertEqual(selector_release_keys(), provisioner_release_keys())

    def test_the_provisioner_owns_only_the_version_marker(self):
        # PLEBIAN_OS_VERSION is release-controlled but comes from the VERSION
        # marker deployed beside this script: reading it back out of session.env
        # would pin a machine to the version it already had.
        self.assertEqual(bash_array(PROVISION, "PROVISION_OWNED_KEYS"),
                         ["PLEBIAN_OS_VERSION"])
        restored = bash_array(PROVISION, "PERSISTED_SESSION_KEYS")
        self.assertNotIn("PLEBIAN_OS_VERSION", restored)
        for key in selector_release_keys():
            if key == "PLEBIAN_OS_VERSION":
                continue
            with self.subTest(key=key):
                self.assertIn(key, restored)

    def test_each_key_is_written_back_from_the_variable_it_is_restored_into(self):
        # Closes the loop the defect opened: restore fills a variable, step 5
        # writes session.env from a variable, and if those are not the same
        # variable the key is reset no matter how faithfully it was read.
        text = PROVISION.read_text()
        for key in selector_release_keys() + bash_array(
                PROVISION, "SESSION_SELECTION_KEYS"):
            with self.subTest(key=key):
                var = provisioner_key_variable(key)
                self.assertIn(f'write_session_default {key} "${var}"\n', text)


class ReprovisionPinIntegrityTests(unittest.TestCase):
    """A re-provision on a pinned install must move nothing it was not asked to."""

    def _run(self, session_env: Path, body: str, extra: str = ""):
        script = (
            "set -euo pipefail\n"
            "export PLEBIAN_OS_PROVISION_LIB_ONLY=1\n"
            f"export PLEBIAN_OS_SESSION_ENV={str(session_env)!r}\n"
            f"{extra}"
            f'. "{PROVISION}"\n'
            f"{body}"
        )
        return subprocess.run(["bash", "-c", script], env=clean_env(),
                              text=True, capture_output=True, check=False)

    @staticmethod
    def _report(keys) -> str:
        return "".join(
            'printf "%s=%s\\n" {key} "${var}"\n'.format(
                key=key, var=provisioner_key_variable(key))
            for key in keys
        )

    def _pinned_session_env(self, directory: Path) -> Path:
        session_env = directory / "session.env"
        session_env.write_text(session_env_text(
            {**INSTALLED_CLOSURE, **INSTALLED_SELECTION,
             **INSTALLED_PROVIDER_PINS, **INSTALLED_OPTIONAL_DESKTOP_POLICY,
             **UNRELATED}))
        return session_env

    def test_every_release_controlled_key_survives_a_reprovision(self):
        keys = selector_release_keys()
        with tempfile.TemporaryDirectory() as td:
            session_env = self._pinned_session_env(Path(td))
            result = self._run(
                session_env, "restore_installed_closure\n" + self._report(keys))
            self.assertEqual(result.returncode, 0, result.stderr)
            reported = dict(
                line.split("=", 1) for line in result.stdout.splitlines()
                if "=" in line and line.split("=", 1)[0] in INSTALLED_CLOSURE)
            for key in keys:
                with self.subTest(key=key):
                    if key == "PLEBIAN_OS_VERSION":
                        # The deployed VERSION marker answers for this one, and
                        # the checkout under test has its own VERSION file.
                        continue
                    self.assertEqual(reported.get(key), INSTALLED_CLOSURE[key])

    def test_the_desktop_selection_survives_a_reprovision(self):
        keys = bash_array(PROVISION, "SESSION_SELECTION_KEYS")
        self.assertIn("KILIX_DESKTOP_PROVIDER", keys)
        with tempfile.TemporaryDirectory() as td:
            session_env = self._pinned_session_env(Path(td))
            result = self._run(
                session_env, "restore_installed_closure\n" + self._report(keys))
            self.assertEqual(result.returncode, 0, result.stderr)
            for key in keys:
                with self.subTest(key=key):
                    self.assertIn(f"{key}={INSTALLED_SELECTION[key]}",
                                  result.stdout)

    def test_optional_desktop_switches_drive_the_reprovision_run(self):
        keys = bash_array(PROVISION, "OPTIONAL_DESKTOP_AUTO_INSTALL_KEYS")
        self.assertEqual(keys, [
            "KILIX_CAP_AUTO_INSTALL",
            "KILIX_TUI_UTILS_AUTO_INSTALL",
            "KILIX_LAND_DESKTOP_AUTO_INSTALL",
        ])
        provision = PROVISION.read_text()
        for key in keys:
            self.assertIn(f'"{key}=${key}"', provision)
            for installed in ("0", "1"):
                with self.subTest(key=key, installed=installed):
                    with tempfile.TemporaryDirectory() as td:
                        session_env = Path(td) / "session.env"
                        session_env.write_text(session_env_text({key: installed}))
                        result = self._run(
                            session_env,
                            "restore_installed_closure\n"
                            f'printf "{key}=%s\\n" "${key}"\n')
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn(f"{key}={installed}\n", result.stdout)

    def test_explicit_optional_desktop_switch_outranks_the_installed_value(self):
        keys = bash_array(PROVISION, "OPTIONAL_DESKTOP_AUTO_INSTALL_KEYS")
        for key in keys:
            with self.subTest(key=key):
                with tempfile.TemporaryDirectory() as td:
                    session_env = Path(td) / "session.env"
                    session_env.write_text(session_env_text({key: "0"}))
                    result = self._run(
                        session_env,
                        "restore_installed_closure\n"
                        f'printf "{key}=%s\\n" "${key}"\n',
                        extra=f"export {key}=1\n")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"{key}=1\n", result.stdout)

    def test_the_restore_leaves_paths_and_policy_to_the_run_itself(self):
        with tempfile.TemporaryDirectory() as td:
            session_env = self._pinned_session_env(Path(td))
            result = self._run(
                session_env,
                "restore_installed_closure\n"
                'printf "PLEB_DIR=%s\\n" "$PLEB_DIR"\n'
                'printf "KIOSK=%s\\n" "$KIOSK"\n'
                'printf "PLEB_WM=%s\\n" "$PLEB_WM"\n')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("PLEB_DIR=\n", result.stdout)
            self.assertIn("KIOSK=0\n", result.stdout)
            self.assertIn("PLEB_WM=\n", result.stdout)

    def test_an_explicit_value_still_outranks_the_installed_closure(self):
        # Every one of these has a non-empty built-in default, so "did the
        # operator ask for this?" cannot be answered by looking at the variable
        # after the config block has run.
        with tempfile.TemporaryDirectory() as td:
            session_env = self._pinned_session_env(Path(td))
            result = self._run(
                session_env,
                "restore_installed_closure\n" + self._report([
                    "KILIX_DESKTOP_PROVIDER", "PLEBIAN_OS_KILIX_GO_VERSION",
                    "KILIX_PREBUILT_VERSION", "PLEBIAN_OS_BUILD_KILIX_FORK",
                    "KILIX_VOICE_MODEL_URL"]),
                extra=("export KILIX_DESKTOP_PROVIDER=cap\n"
                       "export PLEBIAN_OS_KILIX_GO_VERSION=go1.27.0\n"
                       "export PLEBIAN_OS_BUILD_KILIX_FORK=1\n"))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("KILIX_DESKTOP_PROVIDER=cap\n", result.stdout)
            self.assertIn("PLEBIAN_OS_KILIX_GO_VERSION=go1.27.0\n", result.stdout)
            self.assertIn("PLEBIAN_OS_BUILD_KILIX_FORK=1\n", result.stdout)
            # Untouched by the environment: still the machine's own values.
            self.assertIn("KILIX_PREBUILT_VERSION=0.47.3\n", result.stdout)
            self.assertIn(
                f"KILIX_VOICE_MODEL_URL={INSTALLED_CLOSURE['KILIX_VOICE_MODEL_URL']}\n",
                result.stdout)

    def test_a_key_the_machine_does_not_record_is_named_not_defaulted(self):
        with tempfile.TemporaryDirectory() as td:
            values = {**INSTALLED_CLOSURE, **INSTALLED_SELECTION,
                      **INSTALLED_PROVIDER_PINS,
                      **INSTALLED_OPTIONAL_DESKTOP_POLICY}
            del values["PLEBIAN_OS_KILIX_GO_VERSION"]
            del values["KILIX_VOICE_MODEL_SHA256"]
            session_env = Path(td) / "session.env"
            session_env.write_text(session_env_text(values))
            result = self._run(
                session_env,
                "restore_installed_closure\n"
                + self._report(["PLEBIAN_OS_KILIX_GO_VERSION", "KILIX_VOICE_REF"]))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("records no value for 2 key(s)", result.stderr)
            self.assertIn("PLEBIAN_OS_KILIX_GO_VERSION", result.stderr)
            self.assertIn("KILIX_VOICE_MODEL_SHA256", result.stderr)
            # Reported, and the rest of the closure still restored.
            self.assertIn("PLEBIAN_OS_KILIX_GO_VERSION=\n", result.stdout)
            self.assertIn(f"KILIX_VOICE_REF={INSTALLED_CLOSURE['KILIX_VOICE_REF']}\n",
                          result.stdout)

    def test_a_restored_release_mode_is_honoured_not_just_recorded(self):
        # PLEBIAN_OS_RELEASE_MODE is release-controlled too, and a re-provision
        # that read it back as 0 checked none of the release contract before
        # writing the machine's closure out again.
        with tempfile.TemporaryDirectory() as td:
            session_env = self._pinned_session_env(Path(td))
            ok = self._run(session_env, "restore_installed_closure\n"
                                        "validate_release_inputs\n"
                                        'printf "RELEASE_MODE=%s\\n" "$PLEBIAN_OS_RELEASE_MODE"\n')
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertIn("RELEASE_MODE=1\n", ok.stdout)

            # And a release machine that no longer records its Go pin is a
            # release machine that cannot be re-provisioned as one.
            values = {**INSTALLED_CLOSURE, **INSTALLED_SELECTION,
                      **INSTALLED_PROVIDER_PINS,
                      **INSTALLED_OPTIONAL_DESKTOP_POLICY}
            del values["PLEBIAN_OS_KILIX_GO_VERSION"]
            depinned = Path(td) / "depinned.env"
            depinned.write_text(session_env_text(values))
            refused = self._run(depinned, "restore_installed_closure\n"
                                          "validate_release_inputs\n")
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("records no value for 1 key(s)", refused.stderr)
            self.assertIn("PLEBIAN_OS_KILIX_GO_VERSION", refused.stderr)

    def test_the_installed_closure_outranks_the_install_record(self):
        # /etc/default/plebian-os records the install and is never rewritten by
        # a closure selection, so for the two keys that are both release-
        # controlled and install policy, session.env is the current answer.
        with tempfile.TemporaryDirectory() as td:
            session_env = self._pinned_session_env(Path(td))
            firstboot = Path(td) / "plebian-os"
            firstboot.write_text(
                'PLEBIAN_OS_APT_SNAPSHOT="20260712T000000Z"\n'
                'PLEBIAN_OS_INSTALL_VOICE_MODEL="0"\n'
                'PLEBIAN_OS_KIOSK="1"\n'
                'PLEBIAN_OS_NOPASSWD_SUDO="1"\n')
            result = self._run(
                session_env,
                "restore_installed_closure\n"
                "restore_persisted_policy\n"
                'printf "APT=%s\\n" "$PLEBIAN_OS_APT_SNAPSHOT"\n'
                'printf "VOICE=%s\\n" "$INSTALL_VOICE_MODEL"\n'
                'printf "KIOSK=%s\\n" "$KIOSK"\n'
                'printf "NOPASSWD_SUDO=%s\\n" "$NOPASSWD_SUDO"\n',
                extra=f"export PLEBIAN_OS_FIRSTBOOT_ENV={str(firstboot)!r}\n")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("APT=20260727T000000Z\n", result.stdout)
            self.assertIn("VOICE=1\n", result.stdout)
            # Policy the closure says nothing about still comes from the install.
            self.assertIn("KIOSK=1\n", result.stdout)
            self.assertIn("NOPASSWD_SUDO=1\n", result.stdout)


def bash_array(script: Path, name: str) -> list[str]:
    """Read one array declaration out of the provisioner, by running it."""
    result = subprocess.run(
        ["bash", "-c", f'. "{script}"\nprintf "%s\\n" "${{{name}[@]}}"'],
        env=clean_env(PLEBIAN_OS_PROVISION_LIB_ONLY="1"),
        text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(f"could not read {name}: {result.stderr}")
    return [line for line in result.stdout.splitlines() if line]


def provisioner_release_keys() -> list[str]:
    return bash_array(PROVISION, "RELEASE_CONTROLLED_KEYS")


def provisioner_key_variable(key: str) -> str:
    """The variable the provisioner keeps one session.env key in."""
    result = subprocess.run(
        ["bash", "-c",
         f'. "{PROVISION}"\nprintf "%s" "${{PERSISTED_KEY_VARS[{key}]:-{key}}}"'],
        env=clean_env(PLEBIAN_OS_PROVISION_LIB_ONLY="1"),
        text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(f"could not map {key}: {result.stderr}")
    return result.stdout.strip()


def selector_release_keys() -> list[str]:
    """Ask plebian-os-select-closure what a release controls, through --show.

    --show lists every release-controlled key an installed machine has, and
    names the ones it does not, so an empty session.env makes it print the whole
    classification and nothing else.
    """
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "etc" / "pleb").mkdir(parents=True)
        (root / "etc" / "pleb" / "session.env").write_text("")
        result = subprocess.run(
            [str(SELECT), "--show"],
            env=clean_env(PLEBIAN_OS_CLOSURE_TEST_ROOT=str(root)),
            text=True, capture_output=True, check=False)
        if result.returncode != 0:
            raise AssertionError(f"--show failed: {result.stderr}")
        keys = []
        for line in result.stdout.splitlines():
            if not line.startswith("  "):
                continue
            keys.append(line.strip().split(" ", 1)[0].split("=", 1)[0])
        if not keys:
            raise AssertionError(f"--show listed no keys: {result.stdout}")
        return keys


if __name__ == "__main__":
    unittest.main()
