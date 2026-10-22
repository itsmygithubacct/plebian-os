"""The staged-deploy sets must agree with themselves, at source level.

`self_update_os_layer` stages a list of files and hands their hashes to
`deploy_staged_os_layer`, which passes them to a root block carrying parallel
lists of destinations, modes and size ceilings. Nothing in the suite executed
that path: every assertion about it was a substring match on the script's text,
including three that asserted the literal value of the guard that had drifted
from the list it guards. A staged set of 15 files met a guard demanding exactly
13, so `plebian-os-update` died before deploying anything -- in its normal and
its --revalidate-current mode alike, on every machine.

These tests read the lists out of the script and compare them to each other, so
adding a file to one list and not another fails here instead of on a user's
machine in the middle of an upgrade.
"""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPDATE = ROOT / "provision" / "plebian-os-update.sh"


def root_block(text):
    """The root deploy heredoc of deploy_staged_os_layer. The script declares
    `names=(` three times -- an empty one, this one, and the provenance one --
    so every lookup below is scoped to this region rather than taking whichever
    comes first."""
    start = text.index("deploy_staged_os_layer() {")
    opener = "<<'ROOT_DEPLOY'"
    body = text.index(opener, start) + len(opener)
    return text[start:text.index("\nROOT_DEPLOY", body)]


def array(name, text):
    """Entries of a `name=( ... )` shell array, one line or many, indented or
    not. Raises when the array is absent or empty, so a rename cannot quietly
    turn one of these assertions into a comparison of two empty lists."""
    match = re.search(rf"^[ \t]*{name}=\((?P<body>.*?)\)[ \t]*$", text,
                      flags=re.MULTILINE | re.DOTALL)
    if match is None:
        raise AssertionError(f"{name}=( ) not found in {UPDATE.name}")
    entries = re.sub(r"#.*", "", match.group("body")).split()
    if not entries:
        raise AssertionError(f"{name}=( ) is empty in {UPDATE.name}")
    return entries


def function_body(name, text):
    match = re.search(rf"^{name}\(\) \{{\n(?P<body>.*?)^\}}", text,
                      flags=re.MULTILINE | re.DOTALL)
    if match is None:
        raise AssertionError(f"{name}() not found in {UPDATE.name}")
    return match.group("body")


class OsLayerDeploySetTests(unittest.TestCase):
    def setUp(self):
        self.text = UPDATE.read_text()

    def test_every_parallel_os_layer_list_has_the_same_length(self):
        block = root_block(self.text)
        staged = array("stage_names", self.text)
        names = array("names", block)
        self.assertEqual(len(names), len(staged))
        for label in ("dests", "modes", "max_sizes"):
            self.assertEqual(len(array(label, block)), len(names), label)

    def test_each_staged_name_is_the_basename_of_its_destination(self):
        renamed = {"desktop-wallpaper.png": "plebian-os.png",
                   "lightdm-gtk-greeter.conf": "50-plebian-os.conf"}
        for name, dest in zip(array("stage_names", self.text),
                              array("dests", root_block(self.text))):
            self.assertEqual(Path(dest).name, renamed.get(name, name))

    def test_the_os_layer_guard_is_not_a_hand_typed_number(self):
        body = function_body("deploy_staged_os_layer", self.text)
        self.assertNotRegex(
            body, r'\[ "\$\{#expected_hashes\[@\]\}" -eq [0-9]+ \]',
            "the OS-layer hash-count guard must derive from the staged list, "
            "not a literal: a literal drifts silently and kills every update")

    def test_the_provenance_guard_matches_its_own_file_list(self):
        # This one still carries a literal. It is correct today; assert that,
        # so the drift that hit the OS layer cannot happen here unnoticed.
        body = function_body("deploy_staged_provenance", self.text)
        literal = re.search(r'\[ "\$\{#expected_hashes\[@\]\}" -eq (\d+) \]',
                            body)
        self.assertIsNotNone(literal, "provenance guard not found")
        caller = re.search(r"local -a names=\((?P<body>[^)]*)\)",
                           function_body("write_final_provenance", self.text))
        self.assertIsNotNone(caller, "provenance caller list not found")
        self.assertEqual(int(literal.group(1)),
                         len(caller.group("body").split()))

    def _guard(self):
        """The real guard, lifted verbatim from the function up to the root
        invocation. Lifting it means these tests measure the shipped code.

        The split marker is asserted: if the function is reformatted so the
        marker no longer matches, this must say so rather than lift the entire
        function -- which would run the real `sudo bash -s` from a unit test."""
        body = function_body("deploy_staged_os_layer", self.text)
        marker = '    if [ "$EUID"'
        self.assertIn(marker, body,
                      "cannot find where the guard ends; refusing to lift the "
                      "whole function, which would invoke sudo from a test")
        lifted = body.split(marker)[0]
        self.assertNotIn("sudo", lifted)
        self.assertIn("expected_hashes", lifted)
        return "guard_only() {\n" + lifted + "\n}\n"

    def _run(self, count, hashes):
        script = ('set -euo pipefail\n'
                  'die() { printf \'DIE: %s\\n\' "$*" >&2; exit 1; }\n'
                  + self._guard()
                  + f'guard_only "/nonexistent-stage" "{count}" '
                  + " ".join(["a" * 64] * hashes) + "\necho GUARD-PASSED\n")
        return subprocess.run(["bash", "-c", script], capture_output=True,
                              text=True, check=False)

    def test_the_call_site_passes_the_count_before_the_hashes(self):
        """The guard reads $2 as the count. If the call site ever passes the
        hashes first, or omits the count, the guard compares a hash against a
        number -- the same class of failure as the 15-against-13 literal, and
        the argv the tests below build would not notice it."""
        self.assertIn(
            'deploy_staged_os_layer "$stage" "${#stage_names[@]}" '
            '"${stage_hashes[@]}"', self.text)

    def test_the_guard_accepts_the_count_the_caller_actually_passes(self):
        staged = len(array("stage_names", self.text))
        result = self._run(staged, staged)
        self.assertIn("GUARD-PASSED", result.stdout, result.stderr)

    def test_the_guard_refuses_a_mismatched_count(self):
        staged = len(array("stage_names", self.text))
        result = self._run(staged, staged - 1)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("GUARD-PASSED", result.stdout)
        self.assertIn("one expected hash per staged file", result.stderr)


class OsLayerSyntaxValidationTests(unittest.TestCase):
    def setUp(self):
        self.text = UPDATE.read_text()
        block = root_block(self.text)
        self.names = array("names", block)
        start = block.index("# Recheck executable syntax before")
        end = block.index("# Validate service and other data formats separately.", start)
        self.root_syntax = block[start:end]
        # Never execute the privileged deployment around this read-only check.
        self.assertNotIn("sudo", self.root_syntax)
        self.assertNotIn("mv ", self.root_syntax)
        staging = function_body("stage_and_validate_os_layer", self.text)
        start = staging.index('    for file in "$stage/plebian-os-provision"')
        end = staging.index('    python3 - "$stage/plebian-os-qt-runtime"', start)
        self.staging_shell_syntax = staging[start:end]

    def _stage(self, stage):
        aliases = {
            "plebian-os-provision": "provision/plebian-os-provision.sh",
            "plebian-os-install-deps": "provision/install-deps.sh",
            "plebian-os-update": "provision/plebian-os-update.sh",
            "plebian-os-select-closure": "provision/plebian-os-select-closure.sh",
            "VERSION": "VERSION",
            "desktop-wallpaper.png": "assets/desktop/plebian-os.png",
            "ATTRIBUTION.md": "assets/installer/ATTRIBUTION.md",
            "COPYING.GPL-2": "assets/COPYING.GPL-2",
        }
        for name in self.names:
            shutil.copyfile(ROOT / aliases.get(name, "provision/" + name), stage / name)

    def _run(self, stage, *, root=True):
        prelude = ('set -euo pipefail\nstage="$1"\n'
                   'die() { printf "%s\\n" "$*" >&2; exit 1; }\n')
        if root:
            prelude += 'new_paths=()\n'
            prelude += ''.join(f'new_paths+=("$stage/{name}")\n' for name in self.names)
        return subprocess.run(
            ["bash", "-c", prelude + (self.root_syntax if root else self.staging_shell_syntax),
             "syntax-check", str(stage)], capture_output=True, text=True, check=False,
        )

    def test_actual_deploy_payload_uses_the_correct_interpreters(self):
        with tempfile.TemporaryDirectory() as td:
            stage = Path(td)
            self._stage(stage)
            result = self._run(stage)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = self._run(stage, root=False)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_every_relevant_nonfirst_script_is_really_checked(self):
        for name, invalid in (
            ("plebian-os-native-runtime", "#!/bin/sh\nif then\n"),
            ("plebian-os-update", "#!/bin/bash\nif then\n"),
            ("plebian-os-nvidia-driver", "#!/bin/bash\nif then\n"),
            ("plebian-os-install-kilix-ollama-runtime", "def broken(\n"),
            ("plebian-os-qt-runtime", "def broken(\n"),
            ("plebian-os-mpv-runtime", "def broken(\n"),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as td:
                stage = Path(td)
                self._stage(stage)
                (stage / name).write_text(invalid)
                result = self._run(stage)
                self.assertNotEqual(result.returncode, 0, name)
                self.assertIn(name, result.stderr)
                if name in ("plebian-os-native-runtime", "plebian-os-update", "plebian-os-nvidia-driver"):
                    self.assertNotEqual(self._run(stage, root=False).returncode, 0, name)


if __name__ == "__main__":
    unittest.main()


class ReleaseHopSplitStateTests(unittest.TestCase):
    """The closure hop commits before any rollback boundary exists, so a later
    failure leaves the machine pinned to the target with the previous release
    installed. Two mechanisms report that, and neither had a test: an EXIT trap
    covering the window before the target updater takes over, and a marker
    carried across the exec so the relaunched updater's rollback can name it.
    """

    def setUp(self):
        self.text = UPDATE.read_text()

    def _reporting_tail(self):
        body = function_body("rollback_stack_transaction", self.text)
        marker = '    if [ "$failed" = 0 ]; then'
        self.assertIn(marker, body)
        return marker + body.split(marker, 1)[1]

    def _run(self, snippet, **env):
        prelude = ('set -uo pipefail\n'
                   'log()  { printf "LOG %s\\n" "$*"; }\n'
                   'warn() { printf "WARN %s\\n" "$*"; }\n')
        return subprocess.run(["bash", "-c", prelude + snippet],
                              capture_output=True, text=True, check=False,
                              env={"PATH": "/usr/bin:/bin", **env})

    def test_a_clean_rollback_after_a_hop_still_names_the_split_state(self):
        tail = "failed=0\n" + self._reporting_tail()
        out = self._run(tail, PLEBIAN_OS_RELEASE_HOP_FROM="0.2.1").stdout
        self.assertIn("LOG restored", out)
        self.assertIn("0.2.1", out)
        self.assertIn("plebian-os-select-closure --rollback", out)

    def test_a_clean_rollback_without_a_hop_stays_quiet(self):
        tail = "failed=0\n" + self._reporting_tail()
        out = self._run(tail).stdout
        self.assertIn("LOG restored", out)
        self.assertNotIn("plebian-os-select-closure --rollback", out)

    def test_the_marker_is_appended_after_every_unset_so_it_survives_exec(self):
        body = function_body("select_latest_release_if_needed", self.text)
        assign = body.index('relaunch_env+=("PLEBIAN_OS_RELEASE_HOP_FROM=')
        unset = body.rindex('relaunch_env+=(-u "$key")')
        self.assertLess(unset, assign,
                        "the marker assignment must come after the -u flags, "
                        "or env unsets it again")
        # env applies unsets before assignments, so this really does survive.
        out = self._run('env -u M M=kept bash -c \'echo "M=[${M:-UNSET}]"\'')
        self.assertIn("M=[kept]", out.stdout)

    def test_a_failure_between_selection_and_relaunch_warns(self):
        source = function_body("warn_release_hop_split_state", self.text)
        script = ("warn_release_hop_split_state() {\n" + source + "\n}\n"
                  '_RELEASE_HOP_FROM=0.2.1; _RELEASE_HOP_TO=0.2.2\n'
                  "trap 'warn_release_hop_split_state $?' EXIT\n"
                  'exit 1\n')
        result = self._run(script)
        self.assertEqual(result.returncode, 1)
        self.assertIn("0.2.1 -> 0.2.2", result.stdout)
        self.assertIn("plebian-os-select-closure --rollback", result.stdout)

    def test_that_warning_is_silent_on_a_successful_hop(self):
        source = function_body("warn_release_hop_split_state", self.text)
        script = ("warn_release_hop_split_state() {\n" + source + "\n}\n"
                  '_RELEASE_HOP_FROM=0.2.1; _RELEASE_HOP_TO=0.2.2\n'
                  "trap 'warn_release_hop_split_state $?' EXIT\n"
                  'exit 0\n')
        result = self._run(script)
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("rollback", result.stdout)

    def test_the_trap_is_armed_only_after_the_closure_is_committed(self):
        body = function_body("select_latest_release_if_needed", self.text)
        commit = body.index('"$selector" "$latest" --source')
        armed = body.index("trap 'warn_release_hop_split_state")
        self.assertLess(commit, armed)
        self.assertLess(armed, body.index('exec "${relaunch_env[@]}"'))
