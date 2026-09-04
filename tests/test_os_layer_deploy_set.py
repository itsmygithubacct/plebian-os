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
import subprocess
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
        invocation. Lifting it means these tests measure the shipped code."""
        body = function_body("deploy_staged_os_layer", self.text)
        return "guard_only() {\n" + body.split('    if [ "$EUID"')[0] + "\n}\n"

    def _run(self, count, hashes):
        script = ('set -euo pipefail\n'
                  'die() { printf \'DIE: %s\\n\' "$*" >&2; exit 1; }\n'
                  + self._guard()
                  + f'guard_only "/nonexistent-stage" "{count}" '
                  + " ".join(["a" * 64] * hashes) + "\necho GUARD-PASSED\n")
        return subprocess.run(["bash", "-c", script], capture_output=True,
                              text=True, check=False)

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


if __name__ == "__main__":
    unittest.main()
