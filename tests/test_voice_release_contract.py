import ast
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# ── the first-use route, as a capability probe rather than as pin values ─────
#
# OS-V-VERIFY F1/F2 are held open by the deliberately failing test below. Its
# first version compared two pins against two known-bad values, and
# OS-V-FIX-VERIFY V1 showed that was the wrong thing to assert: its mutant
# MV-02 advanced both pins to two other *real* commits that carry neither the
# first-use flow nor the receipt gate, and the test went green with the gap
# entirely untouched; MV-04 deleted one of the two requirements outright and
# nothing in the suite noticed. Pin equality is bookkeeping. What the documents
# promise is a capability, so the capability is what is checked here:
#
#   * whatever KILIX_REF is, the Kilix commit it names must pin a
#     `third_party/kilix-content` commit that carries the first-use flow AND an
#     asset record for vosk-model-small-en-us-0.15 — that submodule is what the
#     image serves kilix_content from;
#   * whatever KILIX_VOICE_REF is, the kilix-voice tree it names must carry the
#     covering-receipt gate on the install route the catalog row advertises,
#     and the exit code its refusal uses.
#
# Neither probe compares a SHA with anything. A pin bump that lands the route
# passes; a pin bump that does not, fails — with a message about what is
# missing rather than about which SHA it is.
CONTENT_GITLINK_PATH = "third_party/kilix-content"
CONTENT_FIRST_USE_PATH = "src/kilix_content/first_use.py"
CONTENT_CATALOG_PATH = "src/kilix_content/catalog/plebian.json"
REQUIRED_MODEL_RECORD = "vosk-model-small-en-us-0.15"
RECEIPT_GATE_SYMBOL = "require_covering_receipt"
RECEIPT_GATE_ROUTE = "kilix-stt"
LICENCE_REFUSED_SYMBOL = "LICENCE_REFUSED_EXIT"
LICENCE_REFUSED_VALUE = 3
LICENCE_REFUSED_DEFINITION = (
    f"{LICENCE_REFUSED_SYMBOL} = {LICENCE_REFUSED_VALUE}")

# The two commits that do carry these things today, on branches that have not
# been merged or released. They are fixtures for the probes' pass path — the
# release pins neither, and nothing here compares a pinned ref against them.
CONTENT_REF_WITH_FIRST_USE = "7543aa30bd0c7ff60b7d7953e3290b87da10583c"
VOICE_REF_WITH_RECEIPT_GATE = "dacfcaa98e58faffef8876873e7cb5b306890eec"

# The words every instructing document has to carry while that is true.
GAP_STATEMENT = "not reachable on a 0.2.2 image"

# OS-V-FIX-VERIFY V6. Every shipped surface a provisioning or build path can
# run from — not the four files the item-6 test used to name. `--install` alone
# is not the signal (plebian-os-nvidia-driver has its own `--install` mode, and
# native_runtime.py runs `dpkg --install`); `--install` on a line that also
# names the speech tool is.
SHIPPED_SURFACE_DIRECTORIES = ("provision", "build", "preseed", "tools")
SHIPPED_SURFACE_FILES = ("bootstrap.sh",)
SPEECH_TOOL_PATTERN = re.compile(r"\bstt\b")

# The kilix-stt flags a provisioning or build path may run. Every one of them
# reports; none of them changes installed or default state. Widening this to
# admit the install action is the whole of what item 6 forbids, so the set is
# named here and its read-only-ness asserted, not just its membership.
READ_ONLY_STT_FLAGS = ("--version", "--print", "--models")


def _git(repo, *args):
    """Read-only git plumbing; stdout, or None when the command failed.

    Only object-store reads are used, never a command that touches an index or
    a working tree: kilix, kilix-content and kilix-voice are read-only to this
    repository's tests.

    `--no-replace-objects` is not decoration. OS-V-FIX2-VERIFY VF7 showed that
    a `refs/replace/<sha>` entry in whichever sibling checkout the probes
    happen to find rewrites what a pinned SHA resolves to, so a checkout this
    repository does not control could turn a gap into a pass while the pins
    stayed exactly as they are. These probes must answer for the commit the
    release pins, not for whatever a local ref says should stand in for it.
    `test_a_replacement_object_cannot_green_the_content_probe` proves the flag
    is what closes that, with a control showing the replacement really does
    redirect when git is allowed to honour it.
    """
    try:
        done = subprocess.run(
            ("git", "-C", str(repo), "--no-replace-objects") + tuple(args),
            capture_output=True, text=True, timeout=120, check=False)
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError):
        return None
    if done.returncode != 0:
        return None
    return done.stdout


def _sibling_roots():
    """Directories that may hold checkouts of the read-only sibling repos.

    The sibling repositories sit beside the *primary* clone, and this suite
    runs from linked worktrees at least as often as from that clone, so
    `ROOT.parent` alone is not enough. `--git-common-dir` resolves to the
    primary `.git` from either.
    """
    roots = [ROOT.parent]
    common = _git(ROOT, "rev-parse", "--git-common-dir")
    if common and common.strip():
        git_dir = Path(common.strip())
        if not git_dir.is_absolute():
            git_dir = ROOT / git_dir
        roots.append(git_dir.resolve().parent.parent)
    ordered = []
    for root in roots:
        if root not in ordered:
            ordered.append(root)
    return ordered


def _repo_candidates(env_var, *relatives):
    candidates = [
        Path(raw.strip())
        for raw in os.environ.get(env_var, "").split(os.pathsep)
        if raw.strip()
    ]
    for root in _sibling_roots():
        for relative in relatives:
            candidates.append(root.joinpath(*relative))
    ordered = []
    for path in candidates:
        if path not in ordered:
            ordered.append(path)
    return ordered


def kilix_repo_candidates():
    return _repo_candidates("PLEBIAN_OS_KILIX_REPO", ("kilix",))


def kilix_content_repo_candidates():
    return _repo_candidates(
        "PLEBIAN_OS_KILIX_CONTENT_REPO",
        ("kilix-modules", "kilix-content"),
        ("kilix", "third_party", "kilix-content"),
        ("kilix-content",),
    )


def kilix_voice_repo_candidates():
    return _repo_candidates(
        "PLEBIAN_OS_KILIX_VOICE_REPO",
        ("kilix-apps", "kilix-voice"),
        ("kilix-voice",),
    )


def repo_holding(candidates, commit):
    """The first candidate checkout whose object store has `commit`."""
    if not re.fullmatch(r"[0-9a-f]{40}", commit or ""):
        return None
    for repo in candidates:
        if not (repo / ".git").exists():
            continue
        if _git(repo, "cat-file", "-e", commit + "^{commit}") is not None:
            return repo
    return None


def _searched(candidates):
    return ", ".join(str(path) for path in candidates)


def _catalog_records_the_model(repo, commit):
    blob = _git(repo, "show", f"{commit}:{CONTENT_CATALOG_PATH}")
    if blob is None:
        return False
    try:
        document = json.loads(blob)
    except ValueError:
        return False
    records = document.get("assets") if isinstance(document, dict) else None
    if not isinstance(records, list):
        return False
    return any(
        isinstance(record, dict) and record.get("id") == REQUIRED_MODEL_RECORD
        for record in records
    )


def content_chain_gap(kilix_ref, *, kilix_repos=None, content_repos=None):
    """What the Kilix closure `kilix_ref` still lacks, or None if it lacks none.

    Resolves the ref's own `third_party/kilix-content` gitlink and looks in
    *that* commit for the first-use flow and the small-en-us asset record. A
    ref that cannot be resolved counts as a gap, not as a pass: an unprovable
    capability is worth exactly as much as an absent one, and treating it as a
    pass would let this check be greened by deleting a checkout.
    """
    if kilix_repos is None:
        kilix_repos = kilix_repo_candidates()
    if content_repos is None:
        content_repos = kilix_content_repo_candidates()
    if not re.fullmatch(r"[0-9a-f]{40}", kilix_ref or ""):
        return (f"KILIX_REF {kilix_ref!r} is not a 40-character commit id, so "
                "the pinned closure cannot be resolved at all")
    kilix = repo_holding(kilix_repos, kilix_ref)
    if kilix is None:
        return (f"no Kilix checkout holding {kilix_ref} was found, so the "
                "pinned closure cannot be shown to carry the first-use flow "
                f"(searched {_searched(kilix_repos)}; set PLEBIAN_OS_KILIX_REPO "
                "to a checkout that has the commit)")
    gitlink = _git(kilix, "rev-parse", f"{kilix_ref}:{CONTENT_GITLINK_PATH}")
    content_ref = (gitlink or "").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", content_ref):
        return (f"Kilix {kilix_ref[:8]} has no {CONTENT_GITLINK_PATH} gitlink, "
                "so an image built from it serves no kilix_content at all")
    content = repo_holding(content_repos, content_ref)
    if content is None:
        return (f"Kilix {kilix_ref[:8]} pins kilix-content {content_ref[:8]}, "
                "but no kilix-content checkout holding it was found "
                f"(searched {_searched(content_repos)}; set "
                "PLEBIAN_OS_KILIX_CONTENT_REPO to a checkout that has it)")
    missing = []
    if _git(content, "cat-file", "-e",
            f"{content_ref}:{CONTENT_FIRST_USE_PATH}") is None:
        missing.append(CONTENT_FIRST_USE_PATH)
    if not _catalog_records_the_model(content, content_ref):
        missing.append(
            f"{REQUIRED_MODEL_RECORD} record in {CONTENT_CATALOG_PATH}")
    if missing:
        return (f"Kilix {kilix_ref[:8]} pins kilix-content {content_ref[:8]}, "
                "which carries no " + ", and no ".join(missing))
    return None


def _paths_mentioning(repo, commit, needle, *pathspec):
    """Tracked paths at `commit` whose content mentions `needle`.

    A cheap narrowing pass: the parse below is the thing that decides, and it
    only has to look at files that contain the word at all.
    """
    found = _git(repo, "grep", "-l", "-F", "-e", needle, commit, "--",
                 *pathspec)
    if found is None:
        return []
    prefix = commit + ":"
    return [line[len(prefix):] for line in found.splitlines()
            if line.startswith(prefix)]


def _parsed_source(repo, commit, path):
    """`path` at `commit` parsed as a Python module, or None if it is not one."""
    blob = _git(repo, "show", f"{commit}:{path}")
    if blob is None:
        return None
    try:
        return ast.parse(blob)
    except (SyntaxError, ValueError):
        return None


def _called_name(call):
    """The bare name a Call node invokes: `f()` and `m.f()` both give `f`."""
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _route_calls_the_gate(repo, commit):
    """Does something under the advertised route really *call* the gate?

    OS-V-FIX2-VERIFY VF3: the old check was `git grep -F
    require_covering_receipt -- kilix-stt`, which a tree satisfies with the
    comment `# require_covering_receipt is NOT called here` sitting above an
    ungated `install(model)`. A string is not a call, so the candidate files
    are parsed and a real `ast.Call` node is required. A mention in a comment,
    in a docstring or in any other string literal is invisible to the parser,
    which is exactly the point.

    The route may be the `kilix-stt` file or a `kilix-stt/` package directory —
    OS-V-FIX2-VERIFY's V7 judged the directory shape correctly *present*, and
    the pathspec keeps treating it that way. A route whose files do not parse
    as Python is reported as a gap: the call cannot be shown, and an unprovable
    capability is worth exactly what an absent one is.
    """
    for path in _paths_mentioning(repo, commit, RECEIPT_GATE_SYMBOL,
                                  RECEIPT_GATE_ROUTE):
        module = _parsed_source(repo, commit, path)
        if module is None:
            continue
        for node in ast.walk(module):
            if (isinstance(node, ast.Call)
                    and _called_name(node) == RECEIPT_GATE_SYMBOL):
                return True
    return False


def _defines_the_refusal_exit(repo, commit):
    """Does a Python module really *define* LICENCE_REFUSED_EXIT = 3?

    OS-V-FIX2-VERIFY VF3 again: `git grep -F 'LICENCE_REFUSED_EXIT = 3'` over
    the whole tree was satisfied by the line "Someday LICENCE_REFUSED_EXIT = 3"
    in a Markdown design note. What the probe's docstring promises is the
    *definition* of the refusal exit code, so the constant is required from a
    `.py` module that parses, as a binding of the name to the value — not as a
    sentence somewhere that happens to contain those characters.
    """
    for path in _paths_mentioning(repo, commit, LICENCE_REFUSED_SYMBOL):
        if not path.endswith(".py"):
            continue
        module = _parsed_source(repo, commit, path)
        if module is None:
            continue
        for node in ast.walk(module):
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            else:
                continue
            if not any(isinstance(target, ast.Name)
                       and target.id == LICENCE_REFUSED_SYMBOL
                       for target in targets):
                continue
            value = node.value
            if (isinstance(value, ast.Constant)
                    and value.value == LICENCE_REFUSED_VALUE):
                return True
    return False


def receipt_gate_gap(voice_ref, *, voice_repos=None):
    """What the pinned kilix-voice tree still lacks, or None if it lacks none.

    The gate has to be on the route the catalog row advertises, so the
    `require_covering_receipt` call is required in `kilix-stt` itself and not
    merely somewhere in the tree, and the refusal's exit code has to be defined.
    Both are read as code and not as text: see `_route_calls_the_gate` and
    `_defines_the_refusal_exit` for why a substring was not enough.
    """
    if voice_repos is None:
        voice_repos = kilix_voice_repo_candidates()
    if not re.fullmatch(r"[0-9a-f]{40}", voice_ref or ""):
        return (f"KILIX_VOICE_REF {voice_ref!r} is not a 40-character commit "
                "id, so the pinned tree cannot be resolved at all")
    voice = repo_holding(voice_repos, voice_ref)
    if voice is None:
        return (f"no kilix-voice checkout holding {voice_ref} was found, so "
                "the pinned tree cannot be shown to gate the advertised "
                f"install action (searched {_searched(voice_repos)}; set "
                "PLEBIAN_OS_KILIX_VOICE_REPO to a checkout that has it)")
    missing = []
    if not _route_calls_the_gate(voice, voice_ref):
        missing.append(
            f"{RECEIPT_GATE_SYMBOL} call in {RECEIPT_GATE_ROUTE}, the route "
            "the catalog row's own action runs")
    if not _defines_the_refusal_exit(voice, voice_ref):
        missing.append(
            f"definition of the refusal exit code "
            f"({LICENCE_REFUSED_DEFINITION})")
    if missing:
        return (f"kilix-voice {voice_ref[:8]} carries no "
                + ", and no ".join(missing))
    return None


_CONTENT_CHAIN_OWED = (
    "   The image serves kilix_content from exactly that submodule\n"
    "   (build/build_vm_image.py, $KILIX_DIR/third_party/kilix-content/src),\n"
    "   so on a 0.2.2 image\n"
    "   `kilix models install vosk-model-small-en-us-0.15` cannot resolve the\n"
    "   asset and no licence screen exists to show.\n"
    "   WHAT MUST LAND: kilix-content's first-use flow and the vosk record are\n"
    "   merged and released (they exist today on the unmerged\n"
    "   work/0.2.2-c1-first-use, at 7543aa30); a Kilix commit advances\n"
    "   third_party/kilix-content to a commit carrying both; and KILIX_REF here\n"
    "   advances to that Kilix commit. Only the last of those three is an edit\n"
    "   to this repository."
)

_RECEIPT_GATE_OWED = (
    "   Without that gate the catalog row action this repository *requires*\n"
    "   every row to carry, `kilix stt --install M --default M`, still reaches\n"
    "   a 39.3 MiB download with no licence shown and no receipt written.\n"
    "   OD-BB's 'the licence is shown and accepted before any fetch' is false\n"
    "   on the surface users reach while that is the pin.\n"
    "   WHAT MUST LAND: KILIX_VOICE_REF advances to a kilix-voice commit whose\n"
    "   install routes call require_covering_receipt first and exit 3\n"
    "   (LICENCE_REFUSED_EXIT) without one — the V-ACC work, at dacfcaa9 on\n"
    "   work/0.2.2-v-acc. Only that pin advance is an edit to this repository."
)

# The two halves of the route, as a table the deliberate test iterates over.
# Both must be here: OS-V-FIX-VERIFY's MV-04 deleted one of them and the suite
# stayed silent because the other was still failing. The table's shape is
# asserted by test_the_gap_test_requires_both_halves_of_the_route, which also
# runs each probe against a tree lacking precisely that probe's own half.
#
# That guard test binds its probes **out of this table**, by key, and never by
# the module-level names below. OS-V-FIX2-IMPL.md §2 claimed an entry could not
# become a no-op, and OS-V-FIX2-VERIFY VF1 showed that claim was false: its
# mutants MU-12 and MU-13 replaced one entry with `lambda ref, **kw: None`,
# left the key and the module-level function untouched, and survived the whole
# suite with the failing set, the test count and the skip count all unchanged;
# doing it to both entries greened the deliberate failure outright. The guard
# test asserted the table's keys and then called the functions, so the table
# and the code it was supposed to guard could drift apart. Binding from the
# table is what makes the claim true.
FIRST_USE_REQUIREMENTS = (
    ("1. THE CONTENT CHAIN", "KILIX_REF", content_chain_gap,
     _CONTENT_CHAIN_OWED),
    ("2. THE RECEIPT GATE ON THE ADVERTISED ACTION", "KILIX_VOICE_REF",
     receipt_gate_gap, _RECEIPT_GATE_OWED),
)

# OS-V-VERIFY F6. (document, a sentence that really was removed, the sentence
# that replaced it). The first four were removed by the OS-V commit from the
# base at 139de5be; the last four by this one, from OS-V's own text.
REWRITTEN_CLAIMS = (
    (
        "RELEASING.md",
        "require `kilix-stt --print` to report `dictation=ready`",
        "require `kilix-stt --print` to produce a dictation report",
    ),
    (
        "RELEASING.md",
        "Both installed Vosk assets must retain readable upstream provenance "
        "and Apache-2.0 license material",
        "these pins are the advertised identity",
    ),
    (
        "RELEASING.md",
        "Require the device-free acceptance smoke to synthesize a phrase with "
        "real espeak, load the pinned Vosk library/model, and recognize "
        "nonempty text",
        "**Require the guest to hold no speech-model weights**",
    ),
    (
        "RELEASING.md",
        "Verify the installed library/model match the exact release stamp",
        "A model present on a fresh image is a release failure",
    ),
    (
        "RELEASING.md",
        "Then acquire the model the way a user does: run `kilix models "
        "install vosk-model-small-en-us-0.15`",
        "The first-use acceptance leg is deferred and must not be attempted "
        "on a 0.2.2 image",
    ),
    (
        "releases/0.2.2-notes.md",
        "The first time you ask for dictation, Kilix shows the model's "
        "identity",
        "on a 0.2.2 image dictation is neither installed nor acquirable "
        "through the documented route",
    ),
    (
        "UPGRADING.md",
        "The first time dictation is wanted, Kilix shows the model, its "
        "upstream source",
        "it cannot acquire one at all",
    ),
    (
        "CHANGELOG.md",
        "dictation model is acquired the first time it is wanted",
        "dictation model is to be acquired the first time it is wanted",
    ),
)


def _manifest(path):
    values = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


class VoiceReleaseContractTests(unittest.TestCase):
    def test_unpinned_install_defaults_to_read_aloud_only(self):
        remaster = (ROOT / "build" / "remaster-iso.sh").read_text()
        provision = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
        update = (ROOT / "provision" / "plebian-os-update.sh").read_text()
        self.assertGreaterEqual(
            remaster.count('${PLEBIAN_OS_INSTALL_VOICE_MODEL:-0}'), 2)
        self.assertNotIn('${PLEBIAN_OS_INSTALL_VOICE_MODEL:-1}', remaster)
        self.assertIn('${PLEBIAN_OS_INSTALL_VOICE_MODEL:-0}', provision)
        self.assertIn('${PLEBIAN_OS_INSTALL_VOICE_MODEL:-0}', update)

    def test_release_manifests_use_the_runtime_checksum_names(self):
        for path in sorted((ROOT / "releases").glob("*.env")):
            text = path.read_text(encoding="utf-8")
            with self.subTest(manifest=path.name):
                self.assertNotRegex(
                    text, r"(?m)^KILIX_VOICE_(?:LIB|MODEL)_SHA=")

    def test_dictation_policy_requires_a_complete_explicit_closure(self):
        for path in sorted((ROOT / "releases").glob("*.env")):
            values = _manifest(path)
            if values.get("PLEBIAN_OS_INSTALL_VOICE_MODEL") != "1":
                continue
            with self.subTest(manifest=path.name):
                self.assertRegex(
                    values.get("KILIX_VOICE_REF", ""), r"^[0-9a-f]{40}$"
                )
                self.assertRegex(
                    values.get("KILIX_VOICE_LIB_VERSION", ""),
                    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$",
                )
                self.assertRegex(
                    values.get("KILIX_VOICE_LIB_URL", ""), r"^https://"
                )
                self.assertRegex(
                    values.get("KILIX_VOICE_LIB_SHA256", ""),
                    r"^[0-9a-f]{64}$",
                )
                self.assertRegex(
                    values.get("KILIX_VOICE_MODEL_URL", ""), r"^https://")
                self.assertRegex(
                    values.get("KILIX_VOICE_MODEL_SHA256", ""),
                    r"^[0-9a-f]{64}$",
                )

    def test_0_1_7_pins_the_published_offline_dictation_closure(self):
        values = _manifest(ROOT / "releases" / "0.1.7.env")
        self.assertEqual(values["PLEBIAN_OS_INSTALL_VOICE_MODEL"], "1")
        self.assertEqual(
            values["KILIX_VOICE_REF"],
            "f05b64a7b2bc25fa9a7e2c3ae1e0b848f04a23f6",
        )
        self.assertEqual(values["KILIX_VOICE_LIB_VERSION"], "0.3.45")
        self.assertEqual(
            values["KILIX_VOICE_LIB_URL"],
            "https://files.pythonhosted.org/packages/fc/ca/83398cfcd557360a3d7b2d732aee1c5f6999f68618d1645f38d53e14c9ff/vosk-0.3.45-py3-none-manylinux_2_12_x86_64.manylinux2010_x86_64.whl",
        )
        self.assertEqual(
            values["KILIX_VOICE_LIB_SHA256"],
            "25e025093c4399d7278f543568ed8cc5460ac3a4bf48c23673ace1e25d26619f",
        )
        self.assertEqual(
            values["KILIX_VOICE_MODEL_URL"],
            "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
        )
        self.assertEqual(
            values["KILIX_VOICE_MODEL_SHA256"],
            "30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498",
        )

    def test_firstboot_smoke_is_read_aloud_only_and_loads_no_model(self):
        """Read-aloud still works out of the box; recognition is not smoked.

        Recognition cannot be smoke-tested at firstboot any more, because under
        OD-BB the image holds no acoustic model. Keeping the Vosk half would
        mean either an honest image that fails its own acceptance, or a green
        image that still downloads weights unattended. So the smoke proves what
        is really provisioned, and is asserted never to reach for a model.
        """
        provision = (
            ROOT / "provision" / "plebian-os-provision.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("run_voice_read_aloud_smoke", provision)
        self.assertNotIn("run_voice_functional_smoke", provision)
        self.assertIn('EspeakTts(voice="en-us", rate=135)', provision)
        self.assertIn("kilix voice is working", provision)
        self.assertIn("espeak produced no PCM", provision)
        for forbidden in (
            "from voicelib.stt import VoskStt",
            "recognizer.start_utterance()",
            "recognizer.end_utterance().strip()",
            "lib_path=library_path",
            "model_path=model_path",
            'voice/models/small-en-us"',
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, provision)

    def test_no_provisioning_path_asks_for_model_weights(self):
        """The image's only lever on the weights is the `pleb` handoff.

        `pleb install` reads PLEB_INSTALL_VOICE_MODEL: 1 downloads and installs
        the whole dictation closure, 0 takes the read-aloud-only leg. Both
        provisioning entrypoints must hand over a literal 0. Forwarding the
        release flag — which is what they used to do — is exactly the
        unattended firstboot download OD-BB removed.
        """
        for name in (
            "provision/plebian-os-provision.sh",
            "provision/plebian-os-update.sh",
        ):
            text = (ROOT / name).read_text(encoding="utf-8")
            with self.subTest(script=name):
                self.assertEqual(
                    text.count("PLEB_INSTALL_VOICE_MODEL="), 1, name)
                self.assertNotIn(
                    "PLEB_INSTALL_VOICE_MODEL=$INSTALL_VOICE_MODEL", text)
                self.assertNotIn(
                    "PLEB_INSTALL_VOICE_MODEL=$PLEBIAN_OS_INSTALL_VOICE_MODEL",
                    text,
                )
                self.assertNotIn("PLEB_INSTALL_VOICE_MODEL=1", text)
        provision = (
            ROOT / "provision" / "plebian-os-provision.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("readonly PROVISION_VOICE_WEIGHTS=0", provision)
        self.assertIn(
            '"PLEB_INSTALL_VOICE_MODEL=$PROVISION_VOICE_WEIGHTS"', provision)
        self.assertIn('"PLEB_INSTALL_VOICE_MODEL=0"', (
            ROOT / "provision" / "plebian-os-update.sh"
        ).read_text(encoding="utf-8"))

    def test_no_model_weight_path_is_written_during_provisioning(self):
        """Provisioning verification asserts the weights are absent.

        The old verifier required the promoted `small-en-us` symlink, its
        immutable generation, `libvosk.so` and their provenance files. Every
        one of those is now a refusal instead.
        """
        provision = (
            ROOT / "provision" / "plebian-os-provision.sh"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "provisioning left speech-model weights on the image", provision)
        self.assertIn('for entry in "$models_root"/vosk-model-*', provision)
        self.assertIn(
            "provisioning installed the Vosk dictation library", provision)
        self.assertIn(
            "provisioning did not record the skipped Vosk model", provision)
        for forbidden in (
            "verified Vosk small-en-us model is missing",
            "Vosk model small-en-us path is not a generation symlink",
            "Vosk library current path is not a generation symlink",
            "verified Vosk library is missing",
            "kilix-stt did not report dictation=ready",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, provision)

    def test_documents_describe_the_first_use_route_the_code_takes(self):
        """The documents must describe acquisition, not provisioning.

        A document that still says the image installs the model would be the
        false-delivery failure the carrier design calls D6, so each document is
        checked for the route it must describe and against the claim it must no
        longer make. The advertised identity is compared against
        `releases/0.2.2.env` rather than retyped, so the two cannot drift.
        """
        manifest = _manifest(ROOT / "releases" / "0.2.2.env")
        self.assertEqual(manifest["PLEBIAN_OS_INSTALL_VOICE_MODEL"], "1")
        documents = {
            name: (ROOT / name).read_text(encoding="utf-8")
            for name in (
                "CHANGELOG.md",
                "UPGRADING.md",
                "releases/0.2.2-notes.md",
                "RELEASING.md",
                "build/build_vm_image.md",
            )
        }
        for name, text in documents.items():
            with self.subTest(document=name, requirement="first-use route"):
                self.assertIn("first-use", text)
                self.assertIn("advertis", text)
        # OS-V-VERIFY F1. The route these documents name is not in the closure
        # this release pins, so a document may name the command only as part of
        # saying that it cannot be run here. Any document that mentions it must
        # carry the gap statement, in those words, in the same file.
        for name, text in documents.items():
            collapsed = " ".join(text.split())
            with self.subTest(document=name, requirement="the honest gap"):
                self.assertIn(GAP_STATEMENT, collapsed)
                if "kilix models install vosk-model-small-en-us-0.15" in (
                        collapsed):
                    self.assertIn(
                        "0.2.2 image", collapsed,
                        "a document naming the command must say where it does "
                        "not run",
                    )
        for name in ("CHANGELOG.md", "releases/0.2.2-notes.md"):
            with self.subTest(document=name, requirement="acceptance first"):
                collapsed = " ".join(documents[name].split())
                self.assertIn("licence", collapsed)
                self.assertIn("licensor", collapsed)
                self.assertIn("before", collapsed)
                self.assertIn("no unattended model download", collapsed)

        # The notes carry the advertised identity; the manifest is the source.
        notes = documents["releases/0.2.2-notes.md"]
        for key in ("KILIX_VOICE_MODEL_URL", "KILIX_VOICE_MODEL_SHA256"):
            with self.subTest(pin=key):
                self.assertIn(manifest[key], notes)
        self.assertIn("vosk-model-small-en-us-0.15", notes)
        self.assertIn(
            "vosk-model-small-en-us-0.15.zip", manifest["KILIX_VOICE_MODEL_URL"])

        # And the claims that are now false.
        #
        # OS-V-VERIFY F6: the three strings that used to be checked here had
        # never appeared in any of these documents, at any ref, so the block
        # could not catch a document reverted to claim provisioning — it was
        # decorative. Each entry below is a sentence that really was in the
        # file and really was taken out, paired with the sentence that replaced
        # it. Asserting both halves is what gives the assertion bite: a revert
        # of that edit restores the first string and destroys the second, so it
        # fails twice and for the right reason, and a pair whose "removed" half
        # never existed would fail the moment it was written.
        for name, removed, replacement in REWRITTEN_CLAIMS:
            collapsed = " ".join(documents[name].split())
            with self.subTest(document=name, removed=removed[:48]):
                self.assertNotIn(removed, collapsed)
                self.assertIn(
                    replacement, collapsed,
                    "the sentence that replaced it must be here, or this "
                    "assertion is about nothing",
                )
                self.assertNotIn(
                    removed, replacement,
                    "a replacement containing the removed text is not a "
                    "replacement",
                )


    def test_the_pinned_closure_can_acquire_the_model_with_acceptance(self):
        """DELIBERATELY FAILING — OS-V-VERIFY F1 (Critical), and F2 (High).

        This test does not describe a defect in this repository's code. It
        holds open a gap between what 0.2.2's documents describe and what the
        closure 0.2.2 pins can do, so that the gap cannot be closed by
        forgetting about it. It fails today, on purpose, and the message says
        exactly what has to land for it to pass. **Do not weaken it to make the
        suite green**: weakening it would restore the false-delivery shape the
        carrier design calls D6, which is the thing OD-BB exists to prevent.

        It asserts the capability, not the pins. Its first version asserted
        that two pins still equalled two known-bad values, and OS-V-FIX-VERIFY
        V1 greened it by advancing both to two other real commits that carry
        neither half of the route: the tripwire was gone and the gap was not.
        Each requirement now resolves what the pin actually points at and looks
        for the thing itself, so advancing the pins without landing the flow
        does not green this test — it fails with a different message.

        plebian-os cannot fix this from inside plebian-os. The acquisition flow
        lives in kilix-content and reaches the image only through Kilix's
        `third_party/kilix-content` submodule, and the receipt gate that stops
        the catalog row's own action from fetching unconsented lives in
        kilix-voice. Both arrive here as ref advances in `releases/0.2.2.env`.
        """
        manifest = _manifest(ROOT / "releases" / "0.2.2.env")
        owed = []
        for heading, key, probe, what_must_land in FIRST_USE_REQUIREMENTS:
            gap = probe(manifest.get(key, ""))
            if gap is not None:
                owed.append(
                    f"{heading}. releases/0.2.2.env pins\n"
                    f"   {key}={manifest.get(key, '<unset>')}.\n"
                    f"   WHAT IS MISSING: {gap}.\n"
                    + what_must_land)
        if owed:
            self.fail(
                "0.2.2 advertises a first-use acquisition route its own\n"
                "pinned closure cannot run. This failure is deliberate and\n"
                "recorded (OS-V-VERIFY F1/F2, OS-V-FIX-IMPL.md,\n"
                "OS-V-FIX2-IMPL.md); it is the only failure in this suite\n"
                "besides the sanctioned undated 0.2.2 CHANGELOG heading.\n"
                "What is owed:\n\n"
                + "\n\n".join(owed)
                + "\n\nThis test is satisfied by the route existing, not by\n"
                "either pin having a particular value: advancing the pins to\n"
                "commits that still lack the flow or the gate fails it again\n"
                "rather than greening it. When the route really lands, it\n"
                "passes with no edit to it, and the cross-repo equality\n"
                "OS-V-VERIFY F7 defers becomes writable at the same moment,\n"
                "because the release then pins a kilix-content ref to test\n"
                "against.")

    # ── the pass path, and the bite of each half ─────────────────────────────
    #
    # The test above must fail today, so its pass path can never be exercised
    # by the release's own pins. OS-V-FIX-VERIFY V1's point was that an
    # assertion whose pass path is never run is not known to have one. These
    # two tests run both directions of both probes against trees built for the
    # purpose, so "fails while either half is missing, passes only when both
    # are really there" is a demonstrated property rather than a claim.

    @staticmethod
    def _git_init(path):
        path.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", str(path)],
                       check=True, capture_output=True, text=True)
        return path

    @staticmethod
    def _commit_worktree(repo, message="synthetic"):
        identity = ["-c", "user.name=t", "-c", "user.email=t@example.invalid"]
        subprocess.run(["git", "-C", str(repo), "add", "-A"],
                       check=True, capture_output=True, text=True)
        subprocess.run(
            ["git", "-C", str(repo)] + identity + ["commit", "-q", "-m",
                                                   message],
            check=True, capture_output=True, text=True)
        return subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True).stdout.strip()

    def _kilix_pinning(self, base, content_ref):
        """A Kilix commit whose third_party/kilix-content gitlink is given.

        A gitlink is a tree entry, not a reachable object, so this needs no
        copy of kilix-content and touches no real repository.
        """
        repo = self._git_init(base)
        subprocess.run(
            ["git", "-C", str(repo), "update-index", "--add", "--cacheinfo",
             f"160000,{content_ref},{CONTENT_GITLINK_PATH}"],
            check=True, capture_output=True, text=True)
        tree = subprocess.run(
            ["git", "-C", str(repo), "write-tree"],
            check=True, capture_output=True, text=True).stdout.strip()
        commit = subprocess.run(
            ["git", "-C", str(repo), "-c", "user.name=t",
             "-c", "user.email=t@example.invalid", "commit-tree", tree,
             "-m", "synthetic"],
            check=True, capture_output=True, text=True, input="").stdout.strip()
        return repo, commit

    def _kilix_content(self, base, *, first_use=True, record=True):
        repo = self._git_init(base)
        package = repo / "src" / "kilix_content"
        (package / "catalog").mkdir(parents=True)
        (package / "__init__.py").write_text("")
        if first_use:
            (package / "first_use.py").write_text(
                "def show_licence_and_accept():\n    raise NotImplementedError\n")
        assets = [{"id": "piper-en-us-kristin-medium"}]
        if record:
            assets.append({"id": REQUIRED_MODEL_RECORD})
        (package / "catalog" / "plebian.json").write_text(
            json.dumps({"schema_version": 3, "assets": assets}))
        return repo, self._commit_worktree(repo)

    def _kilix_voice(self, base, *, gate=True, exit_code=True, route="file"):
        """A synthetic kilix-voice tree.

        `gate` is True (a real call on the route), False (no mention at all),
        `"comment"` (the symbol named in a comment above an ungated install —
        OS-V-FIX2-VERIFY VF3's V5), `"referenced"` (the symbol bound to a name
        on the route but never called) or `"elsewhere"` (a real call, but in
        another file: the gate exists and the advertised route does not reach
        it). `exit_code` is True, False, or `"doc"` (the constant only in a
        design note — VF3's V6; written so that it *would* satisfy a parser,
        which is why the probe also requires a `.py` module). `route` is
        `"file"` or `"dir"`, the `kilix-stt` package directory the verifier's
        V7 judged, correctly, to be the route.
        """
        repo = self._git_init(base)
        (repo / "voicelib").mkdir()
        (repo / "voicelib" / "licensing.py").write_text(
            (f"{LICENCE_REFUSED_DEFINITION}\n" if exit_code is True else "")
            + f"def {RECEIPT_GATE_SYMBOL}(model):\n    return None\n"
        )
        if exit_code == "doc":
            (repo / "docs").mkdir()
            # A design note that a bare parse would accept: the heading reads
            # as a Python comment and the line below it as a real binding. Only
            # "the definition lives in a .py module" rejects this.
            (repo / "docs" / "NOTES.md").write_text(
                "# Design note: someday the refusal exit code\n"
                f"{LICENCE_REFUSED_DEFINITION}\n")
        if gate == "elsewhere":
            (repo / "voicelib" / "other_route.py").write_text(
                "import licensing\n\n\n"
                "def install_from_somewhere_else(model):\n"
                f"    licensing.{RECEIPT_GATE_SYMBOL}(model)\n")
        if gate is True:
            body = f"licensing.{RECEIPT_GATE_SYMBOL}(model)\n"
        elif gate == "comment":
            body = (f"# {RECEIPT_GATE_SYMBOL} is NOT called here\n"
                    "install(model)\n")
        elif gate == "referenced":
            body = (f"_gate = licensing.{RECEIPT_GATE_SYMBOL}\n"
                    "install(model)\n")
        else:
            body = "install(model)\n"
        source = "#!/usr/bin/env python3\n" + body
        if route == "dir":
            (repo / RECEIPT_GATE_ROUTE).mkdir()
            (repo / RECEIPT_GATE_ROUTE / "__init__.py").write_text(source)
        else:
            (repo / RECEIPT_GATE_ROUTE).write_text(source)
        return repo, self._commit_worktree(repo)

    def _one_commit_repo(self, base, marker):
        """A git repository holding exactly one commit, unique to `marker`.

        Distinct content and a distinct message, so two of these can never
        collide on a commit id however fast they are built in succession.
        """
        repo = self._git_init(base)
        (repo / "MARKER").write_text(marker + "\n")
        return repo, self._commit_worktree(repo, message=marker)

    @staticmethod
    def _requirement_probes():
        """The probes the deliberate gap test will actually call, by pin key.

        OS-V-FIX2-VERIFY VF1. Reading them out of FIRST_USE_REQUIREMENTS rather
        than closing over the module-level `content_chain_gap` and
        `receipt_gate_gap` is the whole of that fix: MU-12 and MU-13 replaced a
        table entry with a no-op and left the module-level function alone, and
        every test that mattered went on exercising the function nobody was
        going to run.
        """
        return {key: probe
                for _heading, key, probe, _owed in FIRST_USE_REQUIREMENTS}

    def test_the_gap_test_requires_both_halves_of_the_route(self):
        """OS-V-FIX-VERIFY V1 / MV-04, and OS-V-FIX2-VERIFY VF1 / MU-12, MU-13.

        MV-04 removed the receipt-gate requirement from the gap test and
        survived the whole suite, because the other requirement was still
        failing and the failing set did not change. The two halves are now a
        named table, and this test asserts both that the table names both pins
        and that neither entry is a no-op: each probe is run against a tree
        that lacks precisely its own half and is required to report it.

        The probes under test are taken **from the table**, by key. The first
        version of this test asserted the table's keys and then called
        `content_chain_gap` and `receipt_gate_gap` by their module-level names,
        so the table and the functions could drift: MU-12 and MU-13 swapped one
        entry for `lambda ref, **kw: None`, the deliberate test stopped
        checking that half, and nothing anywhere objected.
        """
        table = self._requirement_probes()
        self.assertEqual(
            set(table),
            {"KILIX_REF", "KILIX_VOICE_REF"},
            "the route has two halves and both must be checked: deleting one "
            "is what MV-04 did, and it went unnoticed",
        )
        self.assertEqual(
            len(table), len(FIRST_USE_REQUIREMENTS),
            "two requirements sharing one pin key would hide one of them",
        )
        content_probe = table["KILIX_REF"]
        voice_probe = table["KILIX_VOICE_REF"]
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            for label, first_use, record, wanted in (
                ("no first_use.py", False, True, CONTENT_FIRST_USE_PATH),
                ("no asset record", True, False, REQUIRED_MODEL_RECORD),
                ("neither", False, False, CONTENT_FIRST_USE_PATH),
            ):
                with self.subTest(content=label):
                    content, content_ref = self._kilix_content(
                        base / f"content-{first_use}-{record}",
                        first_use=first_use, record=record)
                    kilix, kilix_ref = self._kilix_pinning(
                        base / f"kilix-{first_use}-{record}", content_ref)
                    gap = content_probe(
                        kilix_ref, kilix_repos=[kilix],
                        content_repos=[content])
                    self.assertIsNotNone(
                        gap, "a closure missing the flow must be reported")
                    self.assertIn(wanted, gap)
            # OS-V-FIX2-VERIFY VF2 / mutant MU-05: the third of the probe's
            # three lookups — "the gitlink names a kilix-content commit no
            # checkout holds" — had no arm, because every fixture above is
            # found. Turning that branch into a pass survived the whole suite.
            with self.subTest(content="gitlink nobody holds"):
                held, held_ref = self._kilix_content(base / "content-unheld")
                kilix, kilix_ref = self._kilix_pinning(
                    base / "kilix-unheld", held_ref)
                gap = content_probe(
                    kilix_ref, kilix_repos=[kilix], content_repos=[])
                self.assertIsNotNone(
                    gap,
                    "a gitlink no checkout holds is an unprovable capability, "
                    "which this probe must report as a gap and not as a pass")
                self.assertIn(held_ref[:8], gap)
                self.assertIn("no kilix-content checkout holding it", gap)
                # …and the control: with the checkout present, the same
                # gitlink is a pass, so the arm above is about the lookup and
                # not about the fixture being broken.
                self.assertIsNone(
                    content_probe(kilix_ref, kilix_repos=[kilix],
                                  content_repos=[held]))
            for label, gate, exit_code, route, wanted in (
                ("no gate", False, True, "file", RECEIPT_GATE_SYMBOL),
                ("no exit code", True, False, "file",
                 LICENCE_REFUSED_DEFINITION),
                # OS-V-FIX2-VERIFY VF3: the two shapes a substring probe
                # accepted. A comment naming the symbol is not a call, and a
                # design note quoting the constant is not a definition.
                ("gate named only in a comment", "comment", True, "file",
                 RECEIPT_GATE_SYMBOL),
                ("exit code only in a design note", True, "doc", "file",
                 LICENCE_REFUSED_DEFINITION),
                # Bound to a name and never invoked. A reference is no more
                # the mechanism than a comment is, and it is what a check
                # that accepted any mention of the symbol would fall for.
                ("gate referenced but never called", "referenced", True,
                 "file", RECEIPT_GATE_SYMBOL),
                # The gate exists, and the advertised route does not reach it.
                # This is what keeps the `-- kilix-stt` pathspec load-bearing
                # now that the check parses rather than greps: a `def
                # require_covering_receipt` elsewhere in the tree is not a
                # call, so without this arm dropping the pathspec would have
                # stopped being detectable.
                ("gate called only off the route", "elsewhere", True, "file",
                 RECEIPT_GATE_SYMBOL),
            ):
                with self.subTest(voice=label):
                    voice, voice_ref = self._kilix_voice(
                        base / f"voice-{gate}-{exit_code}",
                        gate=gate, exit_code=exit_code, route=route)
                    gap = voice_probe(voice_ref, voice_repos=[voice])
                    self.assertIsNotNone(
                        gap, "a tree missing the gate must be reported")
                    self.assertIn(wanted, gap)
            # An unresolvable ref is a gap, never a pass: otherwise the gap
            # test could be greened by removing a checkout.
            self.assertIsNotNone(content_probe(
                "0" * 40, kilix_repos=[], content_repos=[]))
            self.assertIsNotNone(voice_probe("0" * 40, voice_repos=[]))
            self.assertIsNotNone(content_probe(
                "", kilix_repos=[], content_repos=[]))
            self.assertIsNotNone(voice_probe("", voice_repos=[]))

    PASS_PATH_ARMS = ("synthetic", "real-trees")

    @staticmethod
    def _assert_every_pass_path_arm_accounted_for(ran):
        """Every arm of the pass-path test must have run or declared itself.

        OS-V-FIX2-VERIFY VF4 / mutant MU-16: a `return` inserted before the
        real-trees arm deleted it, and `Ran 694`, `failures=2` and `skipped=4`
        were all *identical* to the baseline. OS-V-FIX2-IMPL.md §2 offered
        "skipped=4 is unchanged" as the evidence that the arm ran; that
        evidence cannot tell a run from a deletion, because an arm that never
        executes neither fails nor skips.

        So the arms keep a ledger, and this is registered with `addCleanup`
        before the first one starts. A cleanup runs even when the test body
        returns early or skips, so deleting an arm — by a `return`, by an
        excision, by any edit that stops it executing — now raises here.
        """
        for arm in VoiceReleaseContractTests.PASS_PATH_ARMS:
            if arm in ran or f"{arm}:unavailable" in ran:
                continue
            raise AssertionError(
                f"the {arm!r} arm of the pass-path test neither ran nor "
                f"reported itself unavailable (ledger: {sorted(ran)}). An "
                "arm that quietly stops executing leaves the failing set, "
                "the test count and the skip count all unchanged, which is "
                "exactly how OS-V-FIX2-VERIFY's MU-16 survived.")

    def test_the_gap_test_passes_when_the_route_is_really_there(self):
        """The pass path, exercised — the release's own pins never reach it.

        Arm 1 is synthetic and always runs: a kilix-content tree carrying the
        flow and the record, pinned by a Kilix commit's gitlink, and a
        kilix-voice tree carrying the gate and the exit code. Arm 2 uses the
        real trees that carry these things today — kilix-content 7543aa30 on
        the unmerged work/0.2.2-c1-first-use, and kilix-voice dacfcaa9 on
        work/0.2.2-v-acc — so the probe is also known to accept the actual
        commits this release is waiting for. Arm 2 is skipped, and only arm 2,
        where those read-only checkouts are not present.

        Both arms record themselves in `ran`, and the cleanup registered
        before either of them starts requires both to be accounted for: see
        `_assert_every_pass_path_arm_accounted_for` for why "skipped=4 is
        unchanged" was not evidence that arm 2 ran.
        """
        ran = set()
        self.addCleanup(self._assert_every_pass_path_arm_accounted_for, ran)
        table = self._requirement_probes()
        content_probe = table["KILIX_REF"]
        voice_probe = table["KILIX_VOICE_REF"]
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            content, content_ref = self._kilix_content(base / "content")
            kilix, kilix_ref = self._kilix_pinning(base / "kilix", content_ref)
            self.assertIsNone(
                content_probe(kilix_ref, kilix_repos=[kilix],
                              content_repos=[content]),
                "a closure that carries the flow and the record must pass")
            voice, voice_ref = self._kilix_voice(base / "voice")
            self.assertIsNone(
                voice_probe(voice_ref, voice_repos=[voice]),
                "a tree that carries the gate and the exit code must pass")
            # OS-V-FIX2-VERIFY's V7, kept deliberately: a `kilix-stt` package
            # directory with the call inside it is still the advertised route,
            # and git's pathspec matching is right to accept it.
            package, package_ref = self._kilix_voice(
                base / "voice-package", route="dir")
            self.assertIsNone(
                voice_probe(package_ref, voice_repos=[package]),
                "a kilix-stt package directory carrying the call is the route "
                "just as much as a kilix-stt file is")
            ran.add("synthetic")

            real_content = repo_holding(
                kilix_content_repo_candidates(), CONTENT_REF_WITH_FIRST_USE)
            real_voice = repo_holding(
                kilix_voice_repo_candidates(), VOICE_REF_WITH_RECEIPT_GATE)
            if real_content is None or real_voice is None:
                ran.add("real-trees:unavailable")
                self.skipTest(
                    "no read-only checkout holding kilix-content "
                    f"{CONTENT_REF_WITH_FIRST_USE[:8]} and kilix-voice "
                    f"{VOICE_REF_WITH_RECEIPT_GATE[:8]} is present; the "
                    "synthetic arm above still ran")
            real_kilix, real_kilix_ref = self._kilix_pinning(
                base / "kilix-real", CONTENT_REF_WITH_FIRST_USE)
            self.assertIsNone(
                content_probe(real_kilix_ref, kilix_repos=[real_kilix],
                              content_repos=[real_content]),
                f"kilix-content {CONTENT_REF_WITH_FIRST_USE[:8]} carries the "
                "flow and the record, so a Kilix pinning it must pass")
            self.assertIsNone(
                voice_probe(VOICE_REF_WITH_RECEIPT_GATE,
                            voice_repos=[real_voice]),
                f"kilix-voice {VOICE_REF_WITH_RECEIPT_GATE[:8]} carries the "
                "gate, so it must pass")
            ran.add("real-trees")
        self._assert_every_pass_path_arm_accounted_for(ran)

    def test_repo_holding_returns_a_checkout_that_really_holds_the_commit(self):
        """OS-V-FIX2-VERIFY VF5 / mutant MU-11: the contract was untested.

        `repo_holding` promises "the first candidate checkout whose object
        store has `commit`". MU-11 made it return the first candidate that had
        a `.git` at all, without checking, and survived the whole suite: the
        consequence was fail-safe (the next read fails and the probe reports a
        gap), but a contract nothing tests is a contract that can change
        without anyone deciding to change it.
        """
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            stranger, stranger_ref = self._one_commit_repo(
                base / "stranger", "a repository that holds something else")
            wanted, wanted_ref = self._one_commit_repo(
                base / "wanted", "the repository that holds the commit")
            self.assertNotEqual(stranger_ref, wanted_ref)
            not_a_repo = base / "not-a-repo"
            not_a_repo.mkdir()
            self.assertEqual(
                repo_holding([stranger, wanted], wanted_ref), wanted,
                "a checkout that does not hold the commit must be passed "
                "over, not returned because it happens to be a git repository")
            self.assertEqual(
                repo_holding([not_a_repo, wanted], wanted_ref), wanted,
                "a directory that is not a checkout is skipped")
            self.assertEqual(
                repo_holding([wanted, stranger], wanted_ref), wanted)
            self.assertIsNone(
                repo_holding([stranger], wanted_ref),
                "no candidate holds it, so there is no checkout to name")
            self.assertIsNone(repo_holding([], wanted_ref))
            for malformed in (None, "", "HEAD", wanted_ref[:39],
                              wanted_ref.upper(), wanted_ref + "0"):
                with self.subTest(commit=malformed):
                    self.assertIsNone(
                        repo_holding([wanted], malformed),
                        "only a 40-character object id names a pinned commit")

    def test_a_replacement_object_cannot_green_the_content_probe(self):
        """OS-V-FIX2-VERIFY VF7: `refs/replace` redirected the probes.

        The probes read sibling checkouts this repository does not control. A
        `refs/replace/<sha>` entry in one of them rewrites what a pinned SHA
        resolves to, so a tree that lacks the route could answer for one that
        has it while `releases/0.2.2.env` stayed exactly as it is. `_git` now
        passes `--no-replace-objects`, and this is the proof: the same
        replacement that makes plain git report the good tree leaves the probe
        reporting the gap.
        """
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            content, without_route = self._kilix_content(
                base / "content", first_use=False, record=False)
            package = content / "src" / "kilix_content"
            (package / "first_use.py").write_text(
                "def show_licence_and_accept():\n    raise NotImplementedError\n")
            (package / "catalog" / "plebian.json").write_text(json.dumps(
                {"schema_version": 3,
                 "assets": [{"id": REQUIRED_MODEL_RECORD}]}))
            with_route = self._commit_worktree(content, "the route landed")
            kilix, kilix_ref = self._kilix_pinning(
                base / "kilix", without_route)
            table = self._requirement_probes()
            content_probe = table["KILIX_REF"]
            self.assertIsNotNone(
                content_probe(kilix_ref, kilix_repos=[kilix],
                              content_repos=[content]),
                "the pinned gitlink names the commit without the route")
            subprocess.run(
                ["git", "-C", str(content), "replace", "-f", without_route,
                 with_route],
                check=True, capture_output=True, text=True)
            # The control: without the flag git really does redirect, so this
            # test is about --no-replace-objects and not about a replacement
            # that never took effect.
            redirected = subprocess.run(
                ["git", "-C", str(content), "cat-file", "-e",
                 f"{without_route}:{CONTENT_FIRST_USE_PATH}"],
                capture_output=True, text=True).returncode
            self.assertEqual(
                redirected, 0,
                "control: with replacement honoured, the commit without the "
                "flow answers with the tree that has it")
            self.assertIsNotNone(
                content_probe(kilix_ref, kilix_repos=[kilix],
                              content_repos=[content]),
                "a refs/replace entry in a checkout this repository does not "
                "control must not turn the gap into a pass")

    def test_the_carried_over_allowance_claims_no_acceptance_it_cannot_see(
            self):
        """OS-V-FIX-VERIFY V4: the words were false on every upgraded machine.

        The re-provision allowance used to describe a carried-over asset as
        "the user's, acquired through the first-use licence flow". 0.2.1 set
        PLEBIAN_OS_INSTALL_VOICE_MODEL=1 and its firstboot fetched small-en-us
        with no acceptance step, and the completion marker predates this wave,
        so a machine upgraded from 0.2.1 carries both and is accepted by that
        allowance. The behaviour is right and owner-sanctioned; the attribution
        was not, and a carrier attests from words.
        """
        provision = (
            ROOT / "provision" / "plebian-os-provision.sh"
        ).read_text(encoding="utf-8")
        self.assertNotIn("acquired through the first-use licence flow",
                         provision)
        self.assertIn("came from\n#      the machine's own history", provision)
        self.assertIn("releases/0.2.1.env", provision)
        upgrading = " ".join(
            (ROOT / "UPGRADING.md").read_text(encoding="utf-8").split())
        self.assertNotIn(
            "Re-provisioning a machine whose user accepted a model is "
            "supported", upgrading)
        self.assertIn(
            "whether its user accepted that model at first use or 0.2.1's "
            "firstboot fetched it before the upgrade", upgrading)
        # OS-V-FIX2-VERIFY VF6: two lines further down the same paragraph, the
        # rollback sentence still asserted flatly that a model could be "an
        # accepted model installed under 0.2.2" — eight lines after the same
        # paragraph says 0.2.2 cannot acquire one at all. It is the same
        # overclaim the sentence above was rewritten to remove, so it is
        # removed the same way: by naming what the check can see (a model the
        # machine carries) instead of who consented to it.
        self.assertNotIn("an accepted model installed under 0.2.2", upgrading)
        self.assertIn(
            "a model the machine already carries — whichever release put it "
            "there — satisfies 0.2.1's firstboot check", upgrading)
        self.assertIn(
            "It cannot be a model 0.2.2 installed: 0.2.2 installs none",
            upgrading)

    @staticmethod
    def _shipped_surface_files():
        """Every file on a provisioning or build surface, as relative paths.

        Enumerated from the tree rather than listed, because OS-V-FIX-VERIFY's
        MV-15 added a caller to a file the list did not name and survived.
        """
        found = []
        for name in SHIPPED_SURFACE_FILES:
            if (ROOT / name).is_file():
                found.append(name)
        for directory in SHIPPED_SURFACE_DIRECTORIES:
            root = ROOT / directory
            if not root.is_dir():
                continue
            for path in root.rglob("*"):
                if not path.is_file() or path.is_symlink():
                    continue
                if any(part == ".git" or part == "__pycache__"
                       for part in path.parts):
                    continue
                found.append(str(path.relative_to(ROOT)))
        return sorted(found)

    def test_the_shipped_surface_enumeration_sees_the_files_it_must(self):
        """A scan that sees nothing proves nothing (see the item-6 test).

        The enumeration above is what makes MV-15 catchable, so it is checked
        against files known to be on each surface before it is trusted to say
        an action is absent.
        """
        surface = set(self._shipped_surface_files())
        for name in (
            "bootstrap.sh",
            "provision/plebian-os-provision.sh",
            "provision/plebian-os-update.sh",
            "provision/plebian-os-firstboot.service",
            "build/build_vm_image.py",
            "build/remaster-iso.sh",
        ):
            with self.subTest(path=name):
                self.assertIn(name, surface)
        self.assertGreater(len(surface), len(SHIPPED_SURFACE_FILES) + 6)

    def test_no_provisioning_path_runs_the_advertised_install_action(self):
        """The row is required; running it is not this image's business.

        `validate_voice_model_catalog` requires every catalog row to carry
        `kilix stt --install M --default M`, because that is the one shared
        install contract the model-management surfaces publish. Requiring a row
        to *carry* an action and *running* it are different things, and the
        difference now matters: with kilix-voice's weights gate that action
        exits 3 (LICENCE_REFUSED_EXIT) on a machine with no covering receipt,
        which every freshly provisioned 0.2.2 image is. A provisioning or
        verification path that ran it would therefore either fail the image on
        a refusal that is correct, or — before that gate — fetch the weights
        OD-BB removed. Neither may happen: the only kilix-stt invocations on
        these paths are read-only reports.
        """
        contract = '"kilix", "stt", "--install", model, "--default", model'
        # The two files that require the row carry `--install` exactly once,
        # and that once is the comparison itself. Any second occurrence would
        # be something this image does with the action rather than something it
        # requires of the row, so counting is the whole check.
        for name in ("provision/plebian-os-provision.sh",
                     "build/build_vm_image.py"):
            text = (ROOT / name).read_text(encoding="utf-8")
            with self.subTest(script=name):
                self.assertIn(contract, text)
                self.assertEqual(
                    text.count("--install"), 1,
                    f"{name} may require the install action, never run it")
        for name in ("provision/plebian-os-update.sh",
                     "build/remaster-iso.sh"):
            text = (ROOT / name).read_text(encoding="utf-8")
            with self.subTest(script=name):
                self.assertNotIn("--install", text)
        # OS-V-FIX-VERIFY V6 / mutant MV-15: this used to name four files, and
        # a caller added to a fifth — bootstrap.sh — survived the whole suite.
        # The fact item 6 asserts is about the tree, so the check is now about
        # the tree. Every shipped line that mentions `--install` anywhere under
        # the provisioning and build surfaces is enumerated, and any of them
        # that also names the speech tool must be one of the two contract
        # comparisons above. (`--install` by itself is not the signal:
        # plebian-os-nvidia-driver's own mode flag and native_runtime's
        # `dpkg --install` are unrelated and must stay allowed.)
        speech_install_lines = []
        for path in self._shipped_surface_files():
            text = (ROOT / path).read_text(encoding="utf-8", errors="replace")
            for number, line in enumerate(text.splitlines(), start=1):
                if "--install" in line and SPEECH_TOOL_PATTERN.search(line):
                    speech_install_lines.append((path, number, line.strip()))
        self.assertEqual(
            sorted(entry[0] for entry in speech_install_lines),
            ["build/build_vm_image.py", "provision/plebian-os-provision.sh"],
            "the only speech-model install action on any shipped path must be "
            f"the contract comparison: {speech_install_lines}")
        for path, _number, line in speech_install_lines:
            with self.subTest(occurrence=path):
                self.assertIn(contract, line)
        # `kilix models install` / `kilix voice install` carry no `--install`,
        # so they are scanned separately: on a shipped path they may be
        # discussed in a comment and never run.
        for path in self._shipped_surface_files():
            text = (ROOT / path).read_text(encoding="utf-8", errors="replace")
            for number, line in enumerate(text.splitlines(), start=1):
                if re.search(r"kilix (models|voice|stt) install", line):
                    with self.subTest(mention=f"{path}:{number}"):
                        self.assertTrue(
                            line.lstrip().startswith("#"),
                            f"{path}:{number} runs an install action: {line!r}")
        # …and every kilix-stt these paths actually run is a read-only report.
        for name in ("provision/plebian-os-provision.sh",
                     "build/build_vm_image.py"):
            text = (ROOT / name).read_text(encoding="utf-8")
            invocations = re.findall(r'kilix-stt"? +(--[a-z-]+)', text)
            with self.subTest(script=name, requirement="read-only only"):
                self.assertTrue(invocations)
                for flag in sorted(set(invocations)):
                    self.assertIn(flag, READ_ONLY_STT_FLAGS)
        # OS-V-FIX-VERIFY's MV-19 widened that set to admit `--install` and
        # survived. The set is read-only by definition, so say so: a widening
        # now fails here whether or not a caller has been added yet.
        self.assertNotIn("--install", READ_ONLY_STT_FLAGS)
        for flag in READ_ONLY_STT_FLAGS:
            with self.subTest(flag=flag):
                self.assertNotIn("install", flag)

    def test_the_stamp_assertions_are_anchored_to_whole_lines(self):
        """OS-V-VERIFY F4: mutant MU-09 unanchored these and survived.

        A stamp reading `libvosk=skipped` beside an installed
        `model-small-en-us=<sha>` satisfies an unanchored `grep -q skipped`
        twice over. The behavioural kill is
        test_release_voice_verification_refuses_a_planted_firstboot_model's
        `plant_half_skipped_stamp` arm; this pins the shape of the check so the
        weakening is also visible in the diff.
        """
        provision = (
            ROOT / "provision" / "plebian-os-provision.sh"
        ).read_text(encoding="utf-8")
        for anchored in (
            """grep -Fqx -- 'libvosk=skipped' "$stamp\"""",
            """grep -Fqx -- 'model-small-en-us=skipped' "$stamp\"""",
        ):
            with self.subTest(assertion=anchored):
                self.assertIn(anchored, provision)
        self.assertNotIn("""grep -q -- 'skipped'""", provision)
        self.assertNotIn("""grep -q 'skipped'""", provision)
        # The guest acceptance command is anchored the same way.
        builder = (ROOT / "build" / "build_vm_image.py").read_text(
            encoding="utf-8")
        self.assertIn("grep -Fqx 'libvosk=skipped'", builder)
        self.assertIn("grep -Fqx 'model-small-en-us=skipped'", builder)

    def test_the_completion_marker_is_authenticated_like_the_stamp(self):
        """OS-V-FIX-VERIFY V3, and V2's mutant MV-09.

        The marker is the hinge of the re-provision allowance, and it used to
        be checked for existence and shape and nothing else while the install
        stamp in the same function was checked with stat(1). All four guards
        are pinned here, for two reasons. The first is the ordinary one: the
        weakening should be visible in the diff, the way the stamp's anchoring
        already is. The second is specific. Adding the mode check made the
        `! -L` guard behaviourally redundant — a symlink's own mode is 0777 on
        Linux and GNU stat does not dereference, so a symlinked marker is
        refused by the mode check even with `! -L` removed (MV-09 is now an
        equivalent mutant, and the whole suite is unchanged under it). The
        behavioural refusal is proved by
        test_a_symlinked_completion_marker_is_not_a_completed_run; this keeps
        the explicit guard from being deleted as dead code, which it is not:
        it is what makes the refusal legible, and the order of the two checks
        is what keeps the refusal's reason right.
        """
        provision = (
            ROOT / "provision" / "plebian-os-provision.sh"
        ).read_text(encoding="utf-8")
        for guard in (
            'machine_already_provisioned() {',
            '    [ -f "$marker" ] && [ ! -L "$marker" ] || return 1',
            '''    metadata="$(stat -c '%u:%a' -- "$marker" 2>/dev/null)" '''
            '''|| return 1''',
            '    [ "${metadata%%:*}" = "$EUID" ] || return 1',
            '    (( (8#$mode & 8#22) == 0 )) || return 1',
        ):
            with self.subTest(guard=guard.strip()):
                self.assertIn(guard, provision)
        # And it is still not seedable from the environment.
        self.assertIn("PROVISION_COMPLETED_MARKER=/var/lib/plebian-os/"
                      "provisioned", provision)
        self.assertNotIn("PROVISION_COMPLETED_MARKER=${", provision)

    def test_the_advertised_digest_check_is_present_in_the_verifier(self):
        """OS-V-VERIFY F5: mutant MU-15 deleted this and survived.

        The behavioural kill is
        test_release_voice_verification_requires_a_well_formed_advertisement;
        this pins the refusal's presence and its wording, because the wording
        is what that behavioural test matches on.
        """
        provision = (
            ROOT / "provision" / "plebian-os-provision.sh"
        ).read_text(encoding="utf-8")
        self.assertIn(
            '[[ "$KILIX_VOICE_MODEL_SHA256" =~ ^[0-9a-fA-F]{64}$ ]]',
            provision)
        self.assertIn(
            "the advertised first-use model digest must be a full SHA-256",
            provision)
        self.assertIn(
            '[[ "$KILIX_VOICE_MODEL_URL" == https://* ]]', provision)
        self.assertIn(
            "the advertised first-use model source must be an HTTPS upstream "
            "URL", provision)

    def test_provisioning_censuses_dictation_assets_before_it_installs(self):
        """OS-V-VERIFY F3: the discriminator must be taken, and taken first.

        The refusal can only tell an image-shipped model from one the user
        accepted if the census is recorded *before* the one step that could
        install anything. A census taken after `pleb install` would call a
        fetch pre-existing and pass it.
        """
        provision = (
            ROOT / "provision" / "plebian-os-provision.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("record_voice_dictation_census() {", provision)
        self.assertIn(
            "\nrecord_voice_dictation_census\n", provision,
            "the census function must be defined and also called")
        # OS-V-FIX-VERIFY V5 / mutant MV-18. record_voice_dictation_census
        # guards its enumeration with `[ -n "${KILIX_DATA_HOME:-}" ]`, so a
        # call placed above the assignment takes an *empty* census under
        # `set -u` and still sets PROVISION_VOICE_CENSUS_TAKEN=1. Every
        # carried-over asset is then classified as installed-this-run, and a
        # legitimate re-provision is refused with provisioning blamed for a
        # fetch that never happened (the verifier's S10 and S11, rc 1 each).
        # MV-18 moved the call above the assignment and survived, because the
        # three orderings below did not include this one.
        data_home = provision.index(
            '\nKILIX_DATA_HOME="${KILIX_DATA_HOME:-')
        census = provision.index("\nrecord_voice_dictation_census\n")
        install = provision.index('"$PLEB_DIR/bin/pleb" install')
        verify = provision.index("\n    verify_kilix_voice_install\n")
        self.assertLess(
            data_home, census,
            "KILIX_DATA_HOME must be resolved before the census is taken, or "
            "the census is empty and every carried-over asset looks new")
        self.assertLess(census, install, "the census must precede pleb install")
        self.assertLess(install, verify)
        self.assertIn("PROVISION_COMPLETED_MARKER=/var/lib/plebian-os/"
                      "provisioned", provision)
        # Not seeded from the environment: an ambient value must not be able to
        # turn the image's own absence check into a no-op.
        self.assertNotIn("PROVISION_COMPLETED_MARKER=${", provision)
        self.assertIn(
            "provisioning installed speech-model dictation assets during this "
            "run", provision)


if __name__ == "__main__":
    unittest.main()
