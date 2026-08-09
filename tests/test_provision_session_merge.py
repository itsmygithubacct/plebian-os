"""What a re-provision is not allowed to throw away.

`eaca706` stopped `sudo plebian-os-provision` resetting the pins in
/etc/pleb/session.env, by reading the release closure back before the run
rewrote the file. It rewrote the file all the same, and everything on the other
side of that classification went with it: the three optional-desktop
`*_AUTO_INSTALL` switches an operator had turned off came back on, and a block
they had appended — a comment, a `PLEB_RESPAWN` they wanted, and a key nothing
in the stack has ever heard of — was simply not written back out.

There is no list of operator keys that could have fixed that, because an
operator may put anything in the file. So the run's render is merged into the
file the machine already has: the keys this run owns are rewritten, and every
other line is carried through exactly as it stands. What a release owns is
plebian-os-select-closure's classification (test_provision_pin_integrity.py
holds the two declarations together); what this run owns is the storage layout
it just created, plus anything it was handed explicitly.
"""

import hashlib
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
# These fixtures model root-owned system configuration, which is world readable
# even when the suite is launched from a Kilix shell with umask 077.
os.umask(0o022)
PROVISION = ROOT / "provision" / "plebian-os-provision.sh"

MANAGED = 'if [ -z "${%s+x}" ]; then %s=%s; fi'

# An installed machine's file, in the order the provisioner writes it: a header
# comment, the storage layout, the release closure, the desktop selection, the
# optional-component switches, the export block. Values are shaped like the real
# ones so a rendered line and an installed line differ only where they should.
INSTALLED_HEADER = [
    "# Managed by plebian-os-provision — Plebian-OS Pleb session config.",
    "# pleb-session documents the other knobs.",
]

INSTALLED_KEYS = [
    ("GPU_TERMINAL_SOURCE_HOME", "/home/pleb/.local/gpu_terminal/sources"),
    ("GPU_TERMINAL_HOME", "/home/pleb/.local/gpu_terminal"),
    ("PLEBIAN_OS_MANAGED_INSTALL", "1"),
    ("PLEB_DIR", "/home/pleb/.local/gpu_terminal/sources/pleb"),
    ("PLEB_REPO", "https://github.com/itsmygithubacct/pleb.git"),
    ("PLEB_REF", "2" * 40),
    ("KILIX_REPO", "https://github.com/itsmygithubacct/kilix.git"),
    ("KILIX_REF", "3" * 40),
    ("KILIX_PREBUILT_VERSION", "0.47.3"),
    ("KILIX_VOICE_LIB_VERSION", "0.3.45"),
    ("PLEBIAN_OS_KILIX_GO_VERSION", "go1.26.5"),
    ("PLEB_DESKTOP", "1"),
    ("PLEB_WM", "openbox"),
    ("KILIX_DESKTOP_PROVIDER", "external"),
    ("KILIX_DESKTOP_FLAVOR", "95"),
    # The operator's half: three switches turned off on this machine.
    ("KILIX_CAP_AUTO_INSTALL", "0"),
    ("KILIX_CAP_DIR", "/home/pleb/.local/gpu_terminal/sources/kilix-desktops/kilix-cap"),
    ("KILIX_TUI_UTILS_AUTO_INSTALL", "0"),
    ("KILIX_LAND_DESKTOP_AUTO_INSTALL", "0"),
    ("KILIX95_AUTO_INSTALL", "1"),
    ("PLEBIAN_OS_VERSION", "0.1.8"),
    ("PLEBIAN_OS_REF", "1" * 40),
    ("PLEBIAN_OS_APT_SNAPSHOT", "20260727T000000Z"),
]

INSTALLED_EXPORTS = [
    "export GPU_TERMINAL_SETTINGS_FILE",
    "export KILIX_DESKTOP_PROVIDER KILIX_DESKTOP_COMMAND KILIX_DESKTOP_NAME",
]

# What the operator appended after the provisioner's last line: a comment, a
# key the provisioner writes only for a kiosk, and one it has never heard of.
INSTALLED_OPERATOR_BLOCK = [
    "# -- operator additions (candidate-2 acceptance) --",
    MANAGED % ("PLEB_RESPAWN", "PLEB_RESPAWN", "0"),
    MANAGED % ("PLEBIAN_OS_C2_OPERATOR_NOTE", "PLEBIAN_OS_C2_OPERATOR_NOTE",
               "'candidate-2-sentinel'"),
]

# What a bare `sudo plebian-os-provision` renders on that machine: the closure
# restored (eaca706), the layout re-derived to the same paths — and every
# built-in default back in place for everything neither of those covers.
RENDER_DEFAULTS = {
    "KILIX_CAP_AUTO_INSTALL": "1",
    "KILIX_TUI_UTILS_AUTO_INSTALL": "1",
    "KILIX_LAND_DESKTOP_AUTO_INSTALL": "1",
}


def installed_text() -> str:
    lines = list(INSTALLED_HEADER)
    lines += [MANAGED % (key, key, value or "''") for key, value in INSTALLED_KEYS]
    lines += INSTALLED_EXPORTS
    lines += INSTALLED_OPERATOR_BLOCK
    return "".join(line + "\n" for line in lines)


def rendered_text(**overrides: str) -> str:
    """The template a run writes, with no idea the machine has a file already."""
    lines = list(INSTALLED_HEADER)
    for key, value in INSTALLED_KEYS:
        value = overrides.get(key, RENDER_DEFAULTS.get(key, value))
        lines.append(MANAGED % (key, key, value or "''"))
    lines += INSTALLED_EXPORTS
    return "".join(line + "\n" for line in lines)


def clean_env(**overrides: str) -> dict[str, str]:
    """An environment that has told the provisioner nothing.

    Same reasoning as test_provision_pin_integrity: these tests turn on the
    difference between "the operator asked for this" and "this is a built-in
    default", and a Kilix shell exports enough of both namespaces to blur it.
    """
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("KILIX_", "KILIX95_", "PLEB_", "PLEBIAN_OS_",
                                  "GPU_TERMINAL_"))}
    env.update(overrides)
    return env


def merge_files(rendered: str, installed: str, extra: str = "",
                env: dict[str, str] | None = None, flags: str = ""):
    """Run merge_session_env + verify_merged_session_env over two files.

    `flags` runs after the script is sourced, which is where the command line
    raises `KIOSK_EXPLICIT` and friends: the config block would overwrite
    anything set before it from the environment instead.
    """
    with tempfile.TemporaryDirectory() as td:
        directory = Path(td)
        (directory / "rendered.env").write_text(rendered)
        (directory / "installed.env").write_text(installed)
        script = (
            "set -euo pipefail\n"
            "export PLEBIAN_OS_PROVISION_LIB_ONLY=1\n"
            f"{extra}"
            f'. "{PROVISION}"\n'
            f"{flags}"
            f"cd {str(directory)!r}\n"
            "merge_session_env rendered.env installed.env merged.env\n"
            "verify_merged_session_env rendered.env installed.env merged.env\n"
        )
        result = subprocess.run(["bash", "-c", script],
                                env=env if env is not None else clean_env(),
                                text=True, capture_output=True, check=False)
        merged = directory / "merged.env"
        return result, (merged.read_text() if merged.exists() else None), \
            (directory / "installed.env").read_text()


class MergedSessionConfigTests(unittest.TestCase):
    """The file a re-provision leaves behind on a customized machine."""

    _merge = staticmethod(merge_files)

    def test_a_reprovision_leaves_a_customized_file_byte_identical(self):
        installed = installed_text()
        result, merged, _ = self._merge(rendered_text(), installed)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(merged, installed)
        self.assertEqual(len(merged.splitlines()), len(installed.splitlines()))
        self.assertEqual(hashlib.sha256(merged.encode()).hexdigest(),
                         hashlib.sha256(installed.encode()).hexdigest())

    def test_the_optional_desktop_switches_keep_the_operator_value(self):
        result, merged, _ = self._merge(rendered_text(), installed_text())
        self.assertEqual(result.returncode, 0, result.stderr)
        for key in ("KILIX_CAP_AUTO_INSTALL", "KILIX_TUI_UTILS_AUTO_INSTALL",
                    "KILIX_LAND_DESKTOP_AUTO_INSTALL"):
            with self.subTest(key=key):
                self.assertIn(MANAGED % (key, key, "0"), merged)
                self.assertNotIn(MANAGED % (key, key, "1"), merged)

    def test_the_appended_operator_block_survives_intact(self):
        result, merged, _ = self._merge(rendered_text(), installed_text())
        self.assertEqual(result.returncode, 0, result.stderr)
        # Comment, kiosk-only key and unknown key, in that order, at the end.
        self.assertTrue(merged.endswith(
            "".join(line + "\n" for line in INSTALLED_OPERATOR_BLOCK)))

    def test_a_release_controlled_key_the_run_defaulted_is_not_reset(self):
        # eaca706 restores these into the run, so the render usually already
        # carries them. The merge must not be the thing that puts them back if
        # that restore ever fails to reach one — same rule, second lock.
        blanked = rendered_text(KILIX_VOICE_LIB_VERSION="",
                                PLEBIAN_OS_KILIX_GO_VERSION="",
                                KILIX_DESKTOP_PROVIDER="auto")
        result, merged, _ = self._merge(blanked, installed_text())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(MANAGED % ("KILIX_VOICE_LIB_VERSION",
                                 "KILIX_VOICE_LIB_VERSION", "0.3.45"), merged)
        self.assertIn(MANAGED % ("PLEBIAN_OS_KILIX_GO_VERSION",
                                 "PLEBIAN_OS_KILIX_GO_VERSION", "go1.26.5"), merged)
        self.assertIn(MANAGED % ("KILIX_DESKTOP_PROVIDER",
                                 "KILIX_DESKTOP_PROVIDER", "external"), merged)

    def test_an_explicit_value_still_outranks_the_installed_file(self):
        # How a switch is deliberately changed: name it, and this run owns it.
        rendered = rendered_text(KILIX_CAP_AUTO_INSTALL="1",
                                 KILIX_DESKTOP_PROVIDER="cap")
        result, merged, _ = self._merge(
            rendered, installed_text(),
            env=clean_env(KILIX_CAP_AUTO_INSTALL="1", KILIX_DESKTOP_PROVIDER="cap"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(MANAGED % ("KILIX_CAP_AUTO_INSTALL",
                                 "KILIX_CAP_AUTO_INSTALL", "1"), merged)
        self.assertIn(MANAGED % ("KILIX_DESKTOP_PROVIDER",
                                 "KILIX_DESKTOP_PROVIDER", "cap"), merged)
        # And the keys nobody named are still the machine's own.
        self.assertIn(MANAGED % ("KILIX_TUI_UTILS_AUTO_INSTALL",
                                 "KILIX_TUI_UTILS_AUTO_INSTALL", "0"), merged)

    def test_the_storage_layout_is_this_runs_to_rewrite(self):
        # `--user` moves every one of these at once, and the run has just built
        # the directories it named; the file has to describe what is on disk.
        moved = rendered_text(
            PLEB_DIR="/home/other/.local/gpu_terminal/sources/pleb",
            GPU_TERMINAL_HOME="/home/other/.local/gpu_terminal")
        result, merged, _ = self._merge(moved, installed_text())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PLEB_DIR=/home/other/.local/gpu_terminal/sources/pleb", merged)
        self.assertIn("GPU_TERMINAL_HOME=/home/other/.local/gpu_terminal", merged)

    def test_a_key_the_release_introduces_is_appended_not_lost(self):
        rendered = rendered_text() + (
            MANAGED % ("KILIX_NEW_PIN", "KILIX_NEW_PIN", "'v1'") + "\n")
        result, merged, _ = self._merge(rendered, installed_text())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(MANAGED % ("KILIX_NEW_PIN", "KILIX_NEW_PIN", "'v1'"), merged)
        self.assertIn("Added by plebian-os-provision", merged)
        # The operator's block is still there, and still whole.
        for line in INSTALLED_OPERATOR_BLOCK:
            self.assertIn(line, merged)

    def test_a_hand_edited_assignment_is_left_exactly_where_it_is(self):
        # `KILIX_CAP_AUTO_INSTALL=0` on its own line is not the shape this
        # script writes, but it is what a login shell resolves, and it is the
        # operator's answer. Keep it, and do not write a competing line.
        installed = installed_text() + "KILIX95_AUTO_INSTALL=0\n"
        result, merged, _ = self._merge(rendered_text(), installed)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(merged, installed)

    def test_a_line_in_no_shape_this_script_knows_is_kept_and_still_wins(self):
        # Valid shell, and not the shape this script writes: an extra space at
        # the end of a managed line is enough. The line stays, what it resolves
        # to stays, and the verification pass does not mistake it for a loss.
        edited = installed_text().replace(
            MANAGED % ("KILIX_CAP_AUTO_INSTALL", "KILIX_CAP_AUTO_INSTALL", "0"),
            MANAGED % ("KILIX_CAP_AUTO_INSTALL", "KILIX_CAP_AUTO_INSTALL", "0") + " ")
        result, merged, _ = self._merge(rendered_text(), edited)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(merged, edited)
        self.assertNotIn("KILIX_CAP_AUTO_INSTALL=1", merged)

    def test_the_kiosk_respawn_line_defers_to_an_operator_who_disabled_it(self):
        # The one line the template writes outside the managed shape. A kiosk
        # machine whose operator turned respawn off keeps it off, unless this
        # run was handed --kiosk.
        kiosk_line = ("PLEB_RESPAWN=1   # hard kiosk: respawn kilix if it exits"
                      " (set by --kiosk)")
        rendered = rendered_text() + kiosk_line + "\n"
        result, merged, installed = self._merge(rendered, installed_text())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(merged, installed)

        result, merged, _ = self._merge(rendered, installed_text(),
                                        flags="KIOSK_EXPLICIT=1\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(kiosk_line, merged)
        self.assertNotIn(MANAGED % ("PLEB_RESPAWN", "PLEB_RESPAWN", "0"), merged)

    def test_an_unparseable_installed_file_is_refused_not_overwritten(self):
        # A line hand-edited into something bash cannot read is a line nothing
        # here can reason about. Nothing is written, and the file stays put.
        installed = installed_text() + 'if [ -z "${BROKEN+x}\n'
        result, merged, after = self._merge(rendered_text(), installed)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not parse", result.stderr)
        self.assertEqual(after, installed)
        self.assertIn(merged, (None, ""))

    def test_a_merge_that_would_change_an_operator_value_is_refused(self):
        # The verification pass, proved by aiming at it: a candidate whose
        # operator half does not read back as the machine's own is not written.
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            (directory / "rendered.env").write_text(rendered_text())
            (directory / "installed.env").write_text(installed_text())
            (directory / "merged.env").write_text(
                rendered_text())  # what the wholesale rewrite used to produce
            script = (
                "set -euo pipefail\n"
                "export PLEBIAN_OS_PROVISION_LIB_ONLY=1\n"
                f'. "{PROVISION}"\n'
                f"cd {str(directory)!r}\n"
                "verify_merged_session_env rendered.env installed.env merged.env\n"
            )
            result = subprocess.run(["bash", "-c", script], env=clean_env(),
                                    text=True, capture_output=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertRegex(result.stderr,
                         r"would (drop|read) (KILIX_CAP_AUTO_INSTALL"
                         r"|PLEB_RESPAWN|PLEBIAN_OS_C2_OPERATOR_NOTE)")


class RunOwnedClassificationTests(unittest.TestCase):
    """Which keys a re-provision may rewrite, and how that set is bounded."""

    def test_every_layout_key_is_one_the_template_writes(self):
        layout = bash_array("SESSION_LAYOUT_KEYS")
        template = template_keys()
        # The anchors `--user` moves; a layout that lost them would be a layout
        # that freezes a machine's paths at whatever account installed it.
        for key in ("GPU_TERMINAL_HOME", "PLEB_DIR", "KILIX_DIR",
                    "KILIX95_DIR", "PLEBIAN_OS_DIR"):
            self.assertIn(key, layout)
        for key in layout:
            with self.subTest(key=key):
                self.assertIn(key, template)

    def test_the_layout_never_claims_a_release_controlled_key(self):
        # PLEBIAN_OS_VERSION is the one key a release controls and this run
        # answers for, and it is declared where that reason is written down.
        release = set(bash_array("RELEASE_CONTROLLED_KEYS"))
        layout = bash_array("SESSION_LAYOUT_KEYS")
        self.assertTrue(layout)
        for key in layout:
            with self.subTest(key=key):
                self.assertNotIn(key, release)
        self.assertEqual(bash_array("PROVISION_OWNED_KEYS"), ["PLEBIAN_OS_VERSION"])

    def test_an_unclassified_key_falls_to_the_operator(self):
        # The safe direction, and the one that makes the merge correct for keys
        # nothing in this repo has ever named.
        template = template_keys()
        for key in ("KILIX_CAP_AUTO_INSTALL", "KILIX_TUI_UTILS_AUTO_INSTALL",
                    "KILIX_LAND_DESKTOP_AUTO_INSTALL"):
            # The three the candidate-3 run found reset: still written by the
            # template, so this is still the switch an operator sees.
            self.assertIn(key, template)
        owned = run_owned([
            "KILIX_CAP_AUTO_INSTALL", "KILIX_TUI_UTILS_AUTO_INSTALL",
            "KILIX_LAND_DESKTOP_AUTO_INSTALL", "KILIX95_AUTO_INSTALL",
            "KILIX_DESKTOP_PROVIDER", "KILIX_LAND_DESKTOP_ASSETS",
            "PLEB_RESPAWN", "PLEBIAN_OS_C2_OPERATOR_NOTE", "PLEB_DESKTOP",
            "PLEB_DIR", "GPU_TERMINAL_HOME", "PLEBIAN_OS_VERSION",
        ])
        self.assertEqual(owned, {
            "KILIX_CAP_AUTO_INSTALL": False,
            "KILIX_TUI_UTILS_AUTO_INSTALL": False,
            "KILIX_LAND_DESKTOP_AUTO_INSTALL": False,
            "KILIX95_AUTO_INSTALL": False,
            "KILIX_DESKTOP_PROVIDER": False,
            "KILIX_LAND_DESKTOP_ASSETS": False,
            "PLEB_RESPAWN": False,
            "PLEBIAN_OS_C2_OPERATOR_NOTE": False,
            "PLEB_DESKTOP": False,
            "PLEB_DIR": True,
            "GPU_TERMINAL_HOME": True,
            "PLEBIAN_OS_VERSION": True,
        })

    def test_the_kiosk_and_desktop_flags_claim_their_own_key(self):
        # These two are not set by their session.env name, so the flags the
        # command line raises are what makes them this run's.
        self.assertEqual(
            run_owned(["PLEB_RESPAWN", "PLEB_DESKTOP"],
                      extra="KIOSK_EXPLICIT=1\nDESKTOP_EXPLICIT=1\n"),
            {"PLEB_RESPAWN": True, "PLEB_DESKTOP": True})


class FirstProvisionTests(unittest.TestCase):
    """A machine with no session config still gets the whole template."""

    def test_the_write_is_only_merged_when_a_plain_root_file_is_there(self):
        text = PROVISION.read_text()
        self.assertIn(
            'if [ -f "$PLEB_ENV" ] && [ ! -L "$PLEB_ENV" ]'
            ' && root_config_safe_to_source "$PLEB_ENV"; then', text)
        self.assertIn("merge_session_env \"$PLEB_ENV_TMP\" \"$PLEB_ENV\"", text)
        # And the template render itself is unconditional: no file, no merge,
        # the full template lands.
        self.assertIn('PLEB_ENV_TMP="$(mktemp /etc/pleb/.session.env.XXXXXX)"', text)

    def test_nothing_installed_yet_merges_to_the_whole_template(self):
        # The other end of the same guard: even asked to merge into an empty
        # file, every rendered key lands, in the order the template writes it.
        rendered = rendered_text()
        result, merged, _ = merge_files(rendered, "")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([line for line in merged.splitlines() if "=" in line],
                         [line for line in rendered.splitlines() if "=" in line])


def bash_array(name: str) -> list[str]:
    """Read one array declaration out of the provisioner, by running it."""
    result = subprocess.run(
        ["bash", "-c", f'. "{PROVISION}"\nprintf "%s\\n" "${{{name}[@]}}"'],
        env=clean_env(PLEBIAN_OS_PROVISION_LIB_ONLY="1"),
        text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(f"could not read {name}: {result.stderr}")
    return [line for line in result.stdout.splitlines() if line]


def run_owned(keys: list[str], extra: str = "") -> dict[str, bool]:
    """Ask the provisioner which of these keys this run is the authority for."""
    body = "".join(
        f'if session_key_is_run_owned {key}; then echo "{key}=1"; '
        f'else echo "{key}=0"; fi\n'
        for key in keys)
    result = subprocess.run(
        ["bash", "-c",
         "set -uo pipefail\n"
         f'. "{PROVISION}"\n{extra}{body}'],
        env=clean_env(PLEBIAN_OS_PROVISION_LIB_ONLY="1"),
        text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(f"session_key_is_run_owned failed: {result.stderr}")
    answers = dict(line.split("=", 1) for line in result.stdout.splitlines()
                   if "=" in line)
    return {key: answers[key] == "1" for key in keys}


def template_keys() -> list[str]:
    """Every key step 5 writes, read out of the provisioner's own template."""
    keys = re.findall(r'^\s*write_session_default (\S+) ',
                      PROVISION.read_text(), re.M)
    if len(keys) < 50:
        raise AssertionError(f"only found {len(keys)} template keys")
    return keys


if __name__ == "__main__":
    unittest.main()
