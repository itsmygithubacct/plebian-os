"""The release model compliance carrier: acceptance lines AC-1..AC-12.

The carrier (releases/<version>-model-compliance) is what lets a release
advertise speech models while build/remaster-iso.sh keeps F107-A's fail-closed
refusal for every input without it (OD-BA). Each acceptance line below is one
test; AC-11 plants each defect of F100-CARRIER-DESIGN.md §6 and requires the
validator to refuse it for its own reason.

AC-1, AC-3 and AC-4 read kilix-content at PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF and
kilix-license at KILIX_LICENSE_REF from sibling checkouts (CI fetches exactly
those commits), or from PLEBIAN_OS_KILIX_CONTENT_REPO / PLEBIAN_OS_KILIX_LICENSE_REPO.
AC-8 also reads the kilix-needle the catalog selects, and the kilix-content it
vendors, from sibling checkouts or PLEBIAN_OS_KILIX_NEEDLE_REPO.
A missing checkout is a failure, never a skip: an unprovable binding is worth
exactly as much as an absent one.
"""

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_voice_release_contract as voice_contract  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
# The speech models whose licence records name their upstream artifact rather
# than the catalog id; spelled here, not imported from the generator it checks.
LICENCE_RECORD_IDS = {"whisper-small-en": "faster-whisper-small-en",
                      "whisper-medium-en": "faster-whisper-medium-en"}
# Whistle's pinned authority is an application record; its release inclusion
# is separately bound by this carrier's owner determination and review seats.
LICENCE_RECORD_DIRS = {"whistle": "app-records", "kilix-diarization-cpu": "diarization-records",
                       "lfm2-kilix-commands": "lfm2-records",
                       "whisper-medium-en": "whisper-medium-records",
                       "paradee-8m-v1.2": "paradee-records",
                       "en-core-web-sm-3.8.0": "en-core-web-sm-records"}


DISTRIBUTION_HEADING = "# Owner distribution decision"


def determination_gaps(model: str, text: str, entry: dict) -> list[str]:
    if model == "lfm2-kilix-commands":
        # Reuse the pinned project determination, without inventing user consent.
        try:
            determination = json.loads(text)
        except ValueError:
            return ["command-model determination is not the pinned JSON authority"]
        expected = ROOT / 'provision/command-model-determination.json'
        return [] if determination == json.loads(expected.read_bytes()) else [
            "command-model determination differs from the recorded authority"]
    if model == "kilix-diarization-cpu":
        # Existing digest-specific determination; do not invent an owner signature.
        expected = "54b36539688fe450074a0105a2e43719837c321e4cf0eff8d7884a2d92ad21ad"
        return [] if hashlib.sha256(text.encode()).hexdigest() == expected else [
            "diarization checkpoint determination differs from the recorded authority"]
    if model != "whistle":
        if text.startswith(DISTRIBUTION_HEADING):
            # A distribution decision changes how the model reaches a machine,
            # not its terms; the model's determination is carried beside it.
            return [] if "| Decided by | The owner" in text else ["missing owner decision"]
        return [] if "Determined by | The owner" in text else ["missing owner determination"]
    # The owner authorized this optional engine's RC6 integration. Licence
    # identity comes from the pinned upstream declaration, not an invented
    # owner statement accepting a licence. First-use agreement stays separate.
    required = (
        "Owner request on 2026-10-08, verbatim:",
        "> should we integrat this optional engine into rc6 now and push following rules at ~/research/github/README.md ?",
        "Licence: Apache-2.0. Licensor: Cactus Compute, Inc.",
        "This record is not end-user licence acceptance or final image qualification.",
        entry["licence_text_sha256s"][0],
    )
    gaps = ["missing Whistle authorization/evidence: " + value for value in required if value not in text]
    if entry["licence_ids"] != ["apache-2.0"] or entry["licensors"] != ["Cactus Compute, Inc."]:
        gaps.append("Whistle upstream licence identity differs from the authorization record")
    return gaps


VERSION = (ROOT / "VERSION").read_text().strip()
CARRIER = ROOT / "releases" / f"{VERSION}-model-compliance"
GENERATOR = ROOT / "build" / "generate-model-compliance.py"
REFUSAL = (f"Plebian-OS {VERSION} release mode refuses "
           "PLEBIAN_OS_INSTALL_VOICE_MODEL=1 until an accepted F100 "
           "compliance-carrier interface and receipt are present\n")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def manifest(name: str) -> dict[str, str]:
    values = {}
    for line in (ROOT / "releases" / name).read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def carrier_env(root: Path = CARRIER) -> dict[str, str]:
    return dict(line.split("=", 1) for line in
                (root / "CARRIER.env").read_text().splitlines())


def repo_holding(env_var: str, name: str, commit: str) -> Path | None:
    return voice_contract.repo_holding(
        voice_contract._repo_candidates(env_var, (name,)), commit)


def release_env(carrier: Path = CARRIER, **overrides: str) -> dict[str, str]:
    pins = manifest(f"{VERSION}.env")
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HERE": str(ROOT)}
    for key in ("PLEBIAN_OS_VERSION", "PLEBIAN_OS_RELEASE_MODE",
                "PLEBIAN_OS_INSTALL_VOICE_MODEL", "KILIX_VOICE_REF",
                "KILIX_VOICE_LIB_VERSION", "KILIX_VOICE_LIB_URL",
                "KILIX_VOICE_LIB_SHA256", "KILIX_VOICE_MODEL_URL",
                "KILIX_VOICE_MODEL_SHA256", "PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF",
                "KILIX_LICENSE_REF", "PLEBIAN_OS_VOICE_CARRIER_SHA256",
                "PLEBIAN_OS_VOICE_CARRIER_RECEIPT_SHA256"):
        env[key] = pins[key]
    # The guard reads KILIX_REF's content gitlink from the pinned Kilix tree;
    # a local clone that holds KILIX_REF stands in for the remote.
    kilix = repo_holding("PLEBIAN_OS_KILIX_REPO", "kilix", pins["KILIX_REF"])
    env["KILIX_REF"] = pins["KILIX_REF"]
    env["KILIX_REPO"] = str(kilix) if kilix else pins["KILIX_REPO"]
    env["PLEBIAN_OS_VOICE_CARRIER_DIR"] = str(carrier)
    env.update(overrides)
    return env


def run_guard(env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", "set -u\n" + voice_contract._voice_validator_source()
         + "\nvalidate_voice_release_closure"],
        env=env, text=True, capture_output=True)


def regenerate(content: Path, license_: Path, out: Path,
               source: Path = CARRIER) -> subprocess.CompletedProcess:
    args = [sys.executable, str(GENERATOR), "--content-repo", str(content),
            "--license-repo", str(license_), "--out", str(out)]
    for determination in sorted((source / "determinations").glob("*/*")):
        args += ["--determination", f"{determination.parent.name}={determination}"]
    for seat in sorted((source / "seats").glob("*")):
        args += ["--seat", str(seat)]
    return subprocess.run(args, text=True, capture_output=True)


def image_offline_inventory() -> dict[str, str]:
    """asset id -> manifest digest for models the image installs offline."""
    found = {}
    for filename in ("paradee-model.json", "en-core-web-sm-model.json"):
        pin = json.loads((ROOT / "provision" / filename).read_bytes())
        found[pin["asset_id"]] = pin["manifest_digest"]
    return found


def advertised_models(provision: str) -> list[tuple[str, bool]]:
    block = provision[provision.index("validate_voice_model_catalog() {"):]
    block = block[:block.index("\n}\n")]
    models = [(name, flag == "True") for name, flag in re.findall(
        r'\(\s*"([a-z0-9.-]+)", "[a-z]+", (True|False),', block)] + [
            ("kilix-diarization-cpu", True)]
    command_path = ROOT / 'provision/command-model.json'
    if command_path.exists():
        models.append((json.loads(command_path.read_bytes())['asset_id'], True))
    models.extend((asset_id, True) for asset_id in image_offline_inventory())
    return models


def coverage_gaps(provision: str, root: Path = CARRIER) -> list[str]:
    """AC-5: the carrier covers exactly the advertised models, in order."""
    advertised = advertised_models(provision)
    carrier = json.loads((root / "CARRIER.json").read_bytes())
    gaps = []
    if not advertised:
        gaps.append("the provisioner advertises no models")
    if carrier_env(root)["models"].split() != [name for name, _ in advertised]:
        gaps.append("carried models differ from the advertised catalog")
    for name, runnable in advertised:
        entry = carrier["models"].get(name)
        if entry is None or entry["runnable"] != runnable:
            gaps.append(f"{name} is not carried as advertised")
    return gaps


def artifact_gaps(catalog: dict, pins: dict, root: Path = CARRIER) -> list[str]:
    """AC-4: each ARTIFACT.json is the pinned content's asset record."""
    by_id = {asset["id"]: asset for asset in catalog["assets"]}
    carrier = json.loads((root / "CARRIER.json").read_bytes())
    env = carrier_env(root)
    gaps = []
    for model, entry in carrier["models"].items():
        artifact = json.loads((root / model / "ARTIFACT.json").read_bytes())
        if artifact != by_id.get(entry["artifact_id"]):
            gaps.append(f"{model}: ARTIFACT.json is not the pinned asset record")
        prefix = "m_" + re.sub(r"[^a-z0-9]", "_", model) + "_"
        archive = artifact["source"].get("archive_sha256")
        if archive and env.get(prefix + "archive_sha256") != archive:
            gaps.append(f"{model}: CARRIER.env archive digest is not the asset's")
    dictation = carrier_env(root)["dictation_model"]
    if carrier["models"][dictation].get("archive_sha256") != pins["KILIX_VOICE_MODEL_SHA256"]:
        gaps.append("the dictation model is not the pinned KILIX_VOICE_MODEL_SHA256")
    return gaps


def delivery_gaps(provision: str, root: Path = CARRIER) -> list[str]:
    """AC-8: the DELIVERY statements are true of this image."""
    gaps = []
    if "readonly PROVISION_VOICE_WEIGHTS=0" not in provision:
        gaps.append("provisioning may install model weights")
    carrier = json.loads((root / "CARRIER.json").read_bytes())
    voice_ref = carrier["voice_ref"]
    bundle = json.loads((ROOT / "provision/default-models.json").read_bytes())
    if json.loads((root / "DEFAULT-MODELS.json").read_bytes()) != bundle:
        gaps.append("carried default inventory differs from provisioning")
    command_path = ROOT / 'provision/command-model.json'
    command = json.loads(command_path.read_bytes()) if command_path.exists() else None
    if command and (not (root / 'COMMAND-MODEL.json').is_file()
                    or json.loads((root / 'COMMAND-MODEL.json').read_bytes()) != command):
        gaps.append("carried command archive differs from provisioning")
    playalong = json.loads((ROOT / "provision/playalong-models.json").read_bytes())
    if (not (root / "PLAYALONG-MODELS.json").is_file()
            or json.loads((root / "PLAYALONG-MODELS.json").read_bytes()) != playalong):
        gaps.append("carried Playalong defaults differ from provisioning")
    online = {asset: item["manifest_digest"] for asset, item in playalong["assets"].items()
              if item["delivery"] == "online"}
    image = image_offline_inventory()
    for model, entry in carrier["models"].items():
        delivery = (root / model / "DELIVERY").read_text()
        bundled = entry["artifact_id"] in bundle["assets"]
        is_command = command is not None and entry['artifact_id'] == command['asset_id']
        playalong_default = entry["artifact_id"] in online
        image_offline = entry["artifact_id"] in image
        mode = ("bundled-command-model-archive" if is_command else
                "bundled-default-model" if bundled else
                "playalong-default-upstream-download" if playalong_default else
                "image-offline-model" if image_offline else
                "first-use-upstream-download")
        if entry["delivery"] != mode:
            gaps.append(f"{model}: delivery differs from the pinned bundle")
        if playalong_default and entry["manifest_digest"] != online[entry["artifact_id"]]:
            gaps.append(f"{model}: Playalong default manifest differs")
        if is_command:
            if any(entry[k] != command[v] for k, v in (
                    ('archive_sha256', 'sha256'), ('archive_bytes', 'bytes'),
                    ('version', 'version'), ('manifest_digest', 'manifest_digest'))):
                gaps.append(f"{model}: command archive binding differs")
            for claim in ('mode: bundled-command-model-archive', 'stages it offline',
                          'record a notice receipt', 'custom terms', 'are a notice',
                          'not waived', 'no agreement is recorded',
                          'never answered by the image', 'verifies every member'):
                if claim not in delivery:
                    gaps.append(f"{model}: DELIVERY lacks {claim!r}")
            continue
        if bundled:
            if bundle["assets"][entry["artifact_id"]] != entry["manifest_digest"]:
                gaps.append(f"{model}: bundled manifest differs")
            for claim in ("mode: bundled-default-model", "installs the supplied bytes offline",
                          "local standard-policy receipts", "build-time receipts are never distributed"):
                if claim not in delivery:
                    gaps.append(f"{model}: DELIVERY lacks {claim!r}")
            continue
        if image_offline:
            if entry["manifest_digest"] != image[entry["artifact_id"]]:
                gaps.append(f"{model}: image archive manifest differs")
            notice = (root / model / "NOTICE").read_text()
            if "Plebian-OS distributes these model bytes" not in notice:
                gaps.append(f"{model}: NOTICE does not say the image distributes the bytes")
            if "does not distribute these model bytes" in notice:
                gaps.append(f"{model}: NOTICE says the image omits an offline model")
            for claim in (
                    "mode: image-offline-model",
                    "Installation media includes this model.",
                    "installs the supplied bytes offline and does not download them.",
                    "An online install uses the same image archive. A fresh install without it is an error.",
                    "An online upgrade of a machine installed without that archive downloads the pinned files",
                    "builds the same archive, and checks it against the image pin before installation.",
                    "A failed download installs nothing, and the next upgrade tries again.",
                    "Original licence documents accompany the model, and installation verifies every catalogued file.",
                    "creates a local standard-policy receipt",
                    "build-time receipts are never distributed.",
                    "An existing voice selection is left unchanged.",
                    "Female-02 stays installed and selectable.",
                    "This bundling does not remove it.",
                    f"Upstream artifact provenance: {entry['upstream_host']}.",
            ):
                if claim not in delivery:
                    gaps.append(f"{model}: DELIVERY lacks {claim!r}")
            if "This model's weights are not present in the image" in delivery:
                gaps.append(f"{model}: DELIVERY says the image omits an offline model")
            continue
        # Whisper and Whistle installation hands off to the model catalog (the licence screen)
        # rather than asking the receipt check itself; say so, and nothing more.
        route = (f"hands the download to that model catalog\nand fetches no weights "
                 f"itself (kilix-voice {voice_ref})." if model in {"whisper-small-en", "whisper-medium-en", "whistle"}
                 else f"`kilix-stt --check-licence` (kilix-voice {voice_ref}).")
        if model == "kilix-diarization-cpu":
            route = "Transcribe checks the covering receipt and installed manifest before diarization."
            if "--check-licence" in delivery or "kilix-voice" in delivery:
                gaps.append("diarization DELIVERY names the unrelated dictation install route")
        if model in {"whisper-small-en", "whisper-medium-en", "whistle"} and "--check-licence" in delivery:
            gaps.append(f"{model}: DELIVERY claims a receipt check its install does not make")
        # Medium's catalog entry is not in kilix-voice; Kilix's patcher adds it. The route
        # the statement cites exists only through that patcher, so it must name it.
        if model == "whisper-medium-en" and (
                "kilix-voice itself has no whisper-medium-en entry" not in delivery
                or "scripts/patch-whisper-medium-model.py at the release's KILIX_REF." not in delivery):
            gaps.append(f"{model}: DELIVERY does not name the Kilix patcher its route depends on")
        claims = ["This model's weights are not present in the image or downloaded by provisioning.",
                  "No install route downloads it until a kilix-license receipt covers it:",
                  route]
        if playalong_default:
            # An online upgrade installs it unless the machine declined Playalong's models.
            claims += ["mode: playalong-default-upstream-download",
                       "installs it by default for Kilix Playalong",
                       "verifies it against the pinned digests before installation.",
                       "records a local standard-policy receipt",
                       "kilix-playalong page was answered no",
                       "KILIX_PLAYALONG_MODELS=0 is set in the shared settings file",
                       "the next upgrade tries again."]
            if "reaches a machine only when a user installs it" in delivery:
                gaps.append(f"{model}: DELIVERY says only a user installs a Playalong default")
        else:
            claims.append("mode: first-use-upstream-download")
        for claim in claims:
            if claim not in delivery:
                gaps.append(f"{model}: DELIVERY lacks {claim!r}")
        if ("not runnable" in delivery) == entry["runnable"]:
            gaps.append(f"{model}: DELIVERY misstates runnability")
    return gaps


def image_offline_installer_gaps(installer: str) -> list[str]:
    """AC-8: Paradee and en_core_web_sm install from the image, with a copied interpreter."""
    gaps = []
    if "'--copies'" not in installer:
        gaps.append("the Paradee runtime venv is not created with --copies")
    for function in ("def verify_paradee_runtime(", "def stage_paradee_runtime("):
        body = installer.split(function, 1)[1].split("\ndef ", 1)[0] if function in installer else ""
        if "for name in PARADEE_FILES:" not in body:
            gaps.append("runtime staging omits the Apache-2.0 text")
    for claim in ("the installation media did not supply the Paradee model",
                  "the installation media did not supply the en_core_web_sm model"):
        if claim not in installer:
            gaps.append("a missing image archive is not an error: " + claim)
    paradee = installer.split("def install_paradee(", 1)[1].split("def install_spacy(", 1)[0]
    spacy = installer.split("def install_spacy(", 1)[1].split("def install_whisper_medium(", 1)[0]
    if "fetch_default" in paradee or "fetch_default" in spacy:
        gaps.append("an image-offline install can download weights")
    # Only Playalong's online defaults and page OCR fetch through the catalog.
    callers = set()
    for function in ast.walk(ast.parse(installer)):
        if isinstance(function, ast.FunctionDef):
            for node in ast.walk(function):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == "fetch_default"):
                    callers.add(function.name)
    if not callers <= {"install_demucs", "install_whisper_medium", "install_pp_ocr"}:
        gaps.append("an image-offline install can download weights through the catalog")
    # The upgrade download (DELIVERY) builds the image's archives with the
    # image's own checked builders and places nothing it has not verified.
    fetch = installer.split("def fetch_paradee_media(", 1)[1].split("\ndef ", 1)[0]
    for call in ("build_paradee_archive(", "build_spacy_archive(", "verify_paradee_wheels(",
                 "_place_shared_archive("):
        if call not in fetch:
            gaps.append("the upgrade download skips " + call.rstrip("("))
    place = installer.split("def _place_shared_archive(", 1)[1].split("\ndef ", 1)[0]
    if place.find("verify(staged, pin)") < 0 or place.find("verify(staged, pin)") > place.find("os.link("):
        gaps.append("an upgrade archive is placed before it is checked")
    root = installer.split("def install_paradee_runtime(", 1)[1].split("\ndef ", 1)[0]
    if "if offline or" not in root or "the next upgrade tries again" not in root:
        gaps.append("the root step can download on a fresh install, or fails an upgrade on a download")
    return gaps


def command_installer_gaps(installer: str) -> list[str]:
    """AC-8: the command model DELIVERY is true of provision/install-image-models.py.

    The image records the notice terms and never types an agreement answer,
    and it stops rather than answer terms that need one.
    """
    gaps = []
    tree = ast.parse(installer)
    captures = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute) and node.func.attr == "capture_agreement"]
    if not captures:
        gaps.append("the image installer records no command model receipt")
    if any(len(node.args) != 1 or node.keywords for node in captures):
        gaps.append("the image installer types an agreement answer")
    if not any(isinstance(node, ast.If)
               and ast.unparse(node.test) == "record.expected_decision != 'record'"
               and any(isinstance(statement, ast.Raise) for statement in node.body)
               for node in ast.walk(tree)):
        gaps.append("the image installer does not refuse terms that need agreement")
    return gaps


def playalong_installer_gaps(installer: str) -> list[str]:
    """AC-8: the Playalong DELIVERY is true of provision/install-image-models.py.

    The machine's answer is read before any Playalong model is installed, every
    Playalong install sits under "not declined", an offline run downloads
    nothing, the standard-policy receipt is written before the download, and
    the run after a failed download tries again: that run finds the receipt
    without the files, which must read as "not installed", never as an error.
    """
    gaps = []
    tree = ast.parse(installer)
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    main = functions.get("main")
    playalong_calls = ("install_basic_pitch", "install_demucs", "install_whisper_medium")
    if main is None:
        return ["the image installer has no main"]

    def called(node, name):
        return [call for call in ast.walk(node) if isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name) and call.func.id == name]

    guarded = set()
    for node in ast.walk(main):
        if isinstance(node, ast.If) and ast.unparse(node.test) == "declined is None":
            for statement in node.body:
                guarded.update(id(call) for name in playalong_calls for call in called(statement, name))
    for name in playalong_calls:
        calls = called(main, name)
        if not calls:
            gaps.append(f"the image installer never calls {name}")
        if any(id(call) not in guarded for call in calls):
            gaps.append(f"{name} runs even when the machine declined Playalong's models")
    answer = called(main, "playalong_declined")
    if not answer or any(call.lineno > min(c.lineno for name in playalong_calls for c in called(main, name))
                         for call in answer):
        gaps.append("the image installer installs before it reads the machine's answer")
    for name in ("install_demucs", "install_whisper_medium"):
        function = functions.get(name)
        if function is None:
            gaps.append(f"the image installer has no {name}")
            continue
        for node in ast.walk(function):
            if (isinstance(node, ast.If) and ast.unparse(node.test) == "offline"
                    and any(called(statement, "fetch_default") for statement in node.body)):
                gaps.append(f"{name} downloads in an offline run")
        if not any(isinstance(node, ast.If) and ast.unparse(node.test) == "offline"
                   for node in ast.walk(function)):
            gaps.append(f"{name} does not tell an offline run apart")
    fetch = functions.get("fetch_default")
    order = [] if fetch is None else sorted(
        (call.lineno, call.func.attr) for call in ast.walk(fetch) if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr in ("authorize", "ensure_upstream_asset"))
    if [name for _, name in order] != ["authorize", "ensure_upstream_asset"]:
        gaps.append("the Playalong download is not preceded by its standard-policy receipt")
    for name in ("_install_from_image", "install_demucs", "install_whisper_medium"):
        function = functions.get(name)
        if function is None or called(function, "_installed") or not called(function, "_playalong_installed"):
            gaps.append(f"{name} does not retry an install a failed download left incomplete")
    retry = functions.get("_playalong_installed")
    handlers = [] if retry is None else [node for node in ast.walk(retry) if isinstance(node, ast.ExceptHandler)]
    if not any(handler.type is not None and ast.unparse(handler.type) == "cm._api().InstallError"
               and any(isinstance(node, ast.Return) and isinstance(node.value, ast.Constant)
                       and node.value.value is False for node in handler.body)
               for handler in handlers):
        gaps.append("an install a failed download left incomplete stops the next upgrade")
    return gaps


def needle_vendor_gaps(vendored_catalog: dict, vendored_record: bytes,
                       commands_model: dict, root: Path = CARRIER) -> list[str]:
    """AC-8: the Needle the catalog selects serves the carried command model terms.

    kilix-needle reads the catalog and licence records from its own vendored
    kilix-content, not from KILIX_REF's, so that copy must carry the carried
    asset record and licence record, and its commands-model.json must describe
    that asset. Otherwise `install --commands` asks for terms the image's
    receipt does not cover."""
    carrier = json.loads((root / "CARRIER.json").read_bytes())
    gaps = []
    for model, entry in carrier["models"].items():
        if entry["provider"] != "kilix-needle":
            continue
        artifact = json.loads((root / model / "ARTIFACT.json").read_bytes())
        served = {asset["id"]: asset for asset in vendored_catalog["assets"]}
        if served.get(entry["artifact_id"]) != artifact:
            gaps.append(f"{model}: Needle's vendored asset record is not the carried one")
        if sha256(vendored_record) != entry["licence_record_file_sha256"]:
            gaps.append(f"{model}: Needle's vendored licence record is not the carried one")
        files = {item["path"]: {"bytes": item["bytes"], "sha256": item["sha256"]}
                 for item in artifact["files"]}
        if (commands_model.get("version") != entry["version"]
                or commands_model.get("files") != files):
            gaps.append(f"{model}: Needle's commands-model.json does not describe the carried asset")
    return gaps


def kilix_show(kilix: Path, ref: str, path: str) -> str:
    return subprocess.run(["git", "-C", str(kilix), "--no-replace-objects", "show",
                           f"{ref}:{path}"], capture_output=True, text=True,
                          check=True).stdout


def kilix_gate_gaps(voice_installer: str) -> list[str]:
    """`kilix voice install` asks the receipt gate before it fetches a model."""
    gaps = []
    gate = voice_installer.find('require_dictation_receipt "')
    fetch = voice_installer.find('fetch_verified "$KILIX_VOICE_MODEL_URL"')
    if gate < 0 or fetch < 0 or gate > fetch:
        gaps.append("`kilix voice install` can fetch a model before asking the receipt gate")
    if 'check-licence "$model_id"' not in voice_installer:
        gaps.append("`kilix voice install` does not ask about the selected model")
    return gaps


def bonsai_gate_gaps(model_json: str, main_py: str, pull_sh: str, model: str) -> list[str]:
    """kilix-bonsai's pull.sh, which every bonsai download route runs (CLI, TUI,
    `kilix bonsai pull`, `kilix stt --install`), asks the receipt gate for a model
    whose MODEL.json names it, before it downloads anything."""
    gaps = []
    if json.loads(model_json).get("licence_gate") != model:
        gaps.append(f"{model}: MODEL.json names no licence_gate")
    if 'print(f"LICENCE_GATE\\t{model.licence_gate}"' not in main_py:
        gaps.append("the bonsai plan does not report the licence gate")
    if 'licence_gate="$(field LICENCE_GATE)"' not in pull_sh:
        gaps.append("pull.sh does not read the licence gate")
    gate = pull_sh.find('"$gate_tool" --check-licence "$licence_gate"')
    fetch = pull_sh.find('case "$downloader" in')
    link = pull_sh.find('ln -f -- "$FROM/$path"')
    if gate < 0 or fetch < 0 or link < 0 or gate > min(fetch, link):
        gaps.append("pull.sh can fetch a gated model before asking the receipt gate")
    return gaps


def bonsai_ref(bonsai_installer: str) -> str:
    match = re.search(r'^KILIX_BONSAI_REF="\$\{KILIX_BONSAI_REF:-([0-9a-f]{40})\}"$',
                      bonsai_installer, re.M)
    return match.group(1) if match else ""


def gitlink_repo(root: Path, gitlinks: list[str]) -> list[str]:
    """A local Kilix stand-in: one commit per content gitlink, oldest first.

    The guard fetches KILIX_REF from KILIX_REPO; a clone CI makes holds only
    the pinned commit, so a planted older Kilix must come from here, not the
    network. Returns the commit ids."""
    run = lambda *args: subprocess.run(["git", "-C", str(root), *args], check=True,
                                       capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    commits = []
    for gitlink in gitlinks:
        run("update-index", "--add", "--cacheinfo", f"160000,{gitlink},third_party/kilix-content")
        tree = run("write-tree")
        parent = ["-p", commits[-1]] if commits else []
        commits.append(subprocess.run(
            ["git", "-C", str(root), "commit-tree", tree, *parent, "-m", "kilix stand-in"],
            check=True, capture_output=True, text=True,
            env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                 "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}).stdout.strip())
    run("update-ref", "refs/heads/main", commits[-1])
    return commits


def rebind(root: Path) -> dict[str, str]:
    """Re-derive every digest after an edit, as a forger with write access to the
    release env would: BINDINGS, CARRIER.json, the receipt and both pins."""
    unbound = {"CARRIER.json", "BINDINGS.sha256", "ACCEPTANCE.json", "SHA256SUMS"}
    names = sorted(str(p.relative_to(root)) for p in root.rglob("*")
                   if p.is_file() and str(p.relative_to(root)) not in unbound
                   and not str(p.relative_to(root)).startswith("seats/"))
    (root / "BINDINGS.sha256").write_text("".join(
        f"{sha256((root / n).read_bytes())}  {n}\n" for n in names))
    carrier = json.loads((root / "CARRIER.json").read_bytes())
    carrier["bindings_sha256"] = sha256((root / "BINDINGS.sha256").read_bytes())
    (root / "CARRIER.json").write_bytes(json.dumps(
        carrier, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    receipt = json.loads((root / "ACCEPTANCE.json").read_bytes())
    receipt["carrier_sha256"] = sha256((root / "CARRIER.json").read_bytes())
    (root / "ACCEPTANCE.json").write_bytes(json.dumps(
        receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    resum(root)
    return {"PLEBIAN_OS_VOICE_CARRIER_SHA256": sha256((root / "CARRIER.json").read_bytes()),
            "PLEBIAN_OS_VOICE_CARRIER_RECEIPT_SHA256": sha256((root / "ACCEPTANCE.json").read_bytes())}


def resum(root: Path) -> None:
    names = sorted(str(p.relative_to(root)) for p in root.rglob("*")
                   if p.is_file() and p.name != "SHA256SUMS")
    (root / "SHA256SUMS").write_text("".join(
        f"{sha256((root / n).read_bytes())}  {n}\n" for n in names))


def edit_env(root: Path, key: str, value: str) -> None:
    lines = (root / "CARRIER.env").read_text().splitlines()
    lines = [f"{key}={value}" if line.startswith(f"{key}=") else line for line in lines]
    (root / "CARRIER.env").write_text("\n".join(lines) + "\n")


class ModelComplianceCarrierTests(unittest.TestCase):
    def pinned_checkouts(self) -> tuple[Path, Path]:
        pins = manifest(f"{VERSION}.env")
        content = repo_holding("PLEBIAN_OS_KILIX_CONTENT_REPO", "kilix-content",
                               pins["PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF"])
        license_ = repo_holding("PLEBIAN_OS_KILIX_LICENSE_REPO", "kilix-license",
                                pins["KILIX_LICENSE_REF"])
        self.assertIsNotNone(content, "no kilix-content checkout holds "
                             "PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF; set PLEBIAN_OS_KILIX_CONTENT_REPO")
        self.assertIsNotNone(license_, "no kilix-license checkout holds "
                             "KILIX_LICENSE_REF; set PLEBIAN_OS_KILIX_LICENSE_REPO")
        return content, license_

    def test_guard_rejects_parent_content_when_host_is_one_commit_ahead(self):
        content_ref = carrier_env()["interface_content_ref"]
        other_ref = ("0" if content_ref[0] != "0" else "1") + content_ref[1:]
        with tempfile.TemporaryDirectory() as td:
            kilix = Path(td) / "kilix"
            parent, current = gitlink_repo(kilix, [content_ref, other_ref])
            control = run_guard(release_env(KILIX_REF=parent, KILIX_REPO=str(kilix)))
            self.assertEqual(control.returncode, 0, control.stderr)

            # A carrier for the parent's content is stale as soon as the host
            # serves a different gitlink, even with the carrier pins unchanged.
            result = run_guard(release_env(KILIX_REF=current, KILIX_REPO=str(kilix)))
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("is not KILIX_REF's kilix-content gitlink", result.stderr)
            self.assertTrue(result.stderr.endswith(REFUSAL), result.stderr)

    def test_guard_compares_content_gitlink_beyond_a_short_prefix(self):
        content_ref = carrier_env()["interface_content_ref"]
        # Gitlinks can name absent objects, so no hash-collision search or
        # network fixture is needed to exercise a shared seven-hex prefix.
        other_ref = content_ref[:-1] + ("0" if content_ref[-1] != "0" else "1")
        self.assertEqual(other_ref[:7], content_ref[:7])
        self.assertNotEqual(other_ref, content_ref)
        with tempfile.TemporaryDirectory() as td:
            kilix = Path(td) / "kilix"
            served, other = gitlink_repo(kilix, [content_ref, other_ref])
            control = run_guard(release_env(KILIX_REF=served, KILIX_REPO=str(kilix)))
            self.assertEqual(control.returncode, 0, control.stderr)

            result = run_guard(release_env(KILIX_REF=other, KILIX_REPO=str(kilix)))
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("is not KILIX_REF's kilix-content gitlink", result.stderr)
            self.assertTrue(result.stderr.endswith(REFUSAL), result.stderr)

    # AC-1
    def test_carrier_regenerates_byte_identically(self):
        content, license_ = self.pinned_checkouts()
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "carrier"
            result = regenerate(content, license_, out)
            self.assertEqual(result.returncode, 0, result.stderr)
            produced = {str(p.relative_to(out)): p.read_bytes()
                        for p in out.rglob("*") if p.is_file()}
            committed = {str(p.relative_to(CARRIER)): p.read_bytes()
                         for p in CARRIER.rglob("*") if p.is_file()}
            self.assertEqual(sorted(produced), sorted(committed))
            for name in committed:
                self.assertEqual(produced[name], committed[name], name)

    # AC-2
    def test_carrier_env_is_a_faithful_projection_of_carrier_json(self):
        carrier = json.loads((CARRIER / "CARRIER.json").read_bytes())
        env = carrier_env()
        for key in ("schema", "release_id", "dictation_model", "library_wheel_url",
                    "library_wheel_sha256", "interface_content_ref",
                    "interface_content_schema_sha256", "interface_licence_ref",
                    "voice_ref"):
            self.assertEqual(env[key], carrier[key], key)
        self.assertEqual(env["models"].split(), carrier["model_order"])
        self.assertEqual(set(carrier["model_order"]), set(carrier["models"]))
        fixed = {"schema", "release_id", "models", "dictation_model",
                 "library_wheel_url", "library_wheel_sha256", "interface_content_ref",
                 "interface_content_schema_sha256", "interface_licence_ref", "voice_ref"}
        expected = len(fixed)
        for model, entry in carrier["models"].items():
            prefix = "m_" + re.sub(r"[^a-z0-9]", "_", model) + "_"
            projected = {
                "artifact_id": entry["artifact_id"],
                "source_url": entry["source_url"],
                "upstream_host": entry["upstream_host"],
                "manifest_digest": entry["manifest_digest"],
                "artifact_record_sha256": entry["artifact_record_sha256"],
                "licence_record_digest": entry["licence_record_digest"],
                "licence_text_sha256s": " ".join(entry["licence_text_sha256s"]),
                "licensors": "; ".join(entry["licensors"]),
                "decision": entry["decision"],
                "delivery": entry["delivery"],
                "runnable": "yes" if entry["runnable"] else "no",
            }
            if "archive_sha256" in entry:
                projected["archive_sha256"] = entry["archive_sha256"]
                projected["archive_bytes"] = str(entry["archive_bytes"])
            for field, value in projected.items():
                self.assertEqual(env[prefix + field], value, prefix + field)
            expected += len(projected)
        self.assertEqual(len(env), expected, "CARRIER.env has keys CARRIER.json lacks")

    # AC-3
    def test_carrier_licence_records_match_kilix_license(self):
        _, license_ = self.pinned_checkouts()
        ref = manifest(f"{VERSION}.env")["KILIX_LICENSE_REF"]
        carrier = json.loads((CARRIER / "CARRIER.json").read_bytes())
        for model, entry in carrier["models"].items():
            upstream = subprocess.run(
                ["git", "-C", str(license_), "--no-replace-objects", "show",
                 f"{ref}:src/kilix_license/data/{LICENCE_RECORD_DIRS.get(model, 'records')}/{LICENCE_RECORD_IDS.get(model, model)}.json"],
                capture_output=True, check=True).stdout
            self.assertEqual((CARRIER / model / "LICENCE-RECORD.json").read_bytes(),
                             upstream, model)
            self.assertEqual(entry["licence_record_file_sha256"], sha256(upstream))

    # AC-4
    def test_carrier_artifact_records_match_kilix_content(self):
        content, _ = self.pinned_checkouts()
        pins = manifest(f"{VERSION}.env")
        catalog = json.loads(subprocess.run(
            ["git", "-C", str(content), "--no-replace-objects", "show",
             f"{pins['PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF']}:src/kilix_content/catalog/plebian.json"],
            capture_output=True, check=True).stdout)
        self.assertEqual(artifact_gaps(catalog, pins), [])
        # D5b: a digest flipped consistently in the carrier and the release pin,
        # with every carrier digest re-derived, passes the shell guard by
        # construction; the asset record at the content interface still refutes it.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "carrier"
            shutil.copytree(CARRIER, root)
            key = "m_" + re.sub(r"[^a-z0-9]", "_", carrier_env()["dictation_model"]) + "_archive_sha256"
            flipped = ("0" if carrier_env()[key][0] != "0" else "1") + carrier_env()[key][1:]
            edit_env(root, key, flipped)
            carrier = json.loads((root / "CARRIER.json").read_bytes())
            carrier["models"][carrier["dictation_model"]]["archive_sha256"] = flipped
            (root / "CARRIER.json").write_bytes(json.dumps(
                carrier, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode() + b"\n")
            overrides = rebind(root)
            forged = dict(pins, KILIX_VOICE_MODEL_SHA256=flipped)
            self.assertEqual(run_guard(release_env(root, KILIX_VOICE_MODEL_SHA256=flipped,
                                                   **overrides)).returncode, 0)
            self.assertTrue(artifact_gaps(catalog, forged, root))

    def test_carried_records_are_the_ones_the_image_serves(self):
        # The carrier reads asset records at PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF; the
        # image's first-use flow serves KILIX_REF's kilix-content gitlink. A
        # KILIX_REF bump that changed a speech record must fail here.
        pins = manifest(f"{VERSION}.env")
        kilix = repo_holding("PLEBIAN_OS_KILIX_REPO", "kilix", pins["KILIX_REF"])
        self.assertIsNotNone(kilix, "no Kilix checkout holds KILIX_REF")
        gitlink = subprocess.run(
            ["git", "-C", str(kilix), "--no-replace-objects", "rev-parse",
             f"{pins['KILIX_REF']}:third_party/kilix-content"],
            capture_output=True, text=True, check=True).stdout.strip()
        content = repo_holding("PLEBIAN_OS_KILIX_CONTENT_REPO", "kilix-content", gitlink)
        self.assertIsNotNone(content, f"no kilix-content checkout holds {gitlink}")
        catalog = json.loads(subprocess.run(
            ["git", "-C", str(content), "--no-replace-objects", "show",
             f"{gitlink}:src/kilix_content/catalog/plebian.json"],
            capture_output=True, check=True).stdout)
        served = {asset["id"]: asset for asset in catalog["assets"]}
        carrier = json.loads((CARRIER / "CARRIER.json").read_bytes())
        for model, entry in carrier["models"].items():
            artifact = json.loads((CARRIER / model / "ARTIFACT.json").read_bytes())
            self.assertEqual(served.get(entry["artifact_id"]), artifact, model)

    def test_command_model_records_needle_serves_are_the_carried_ones(self):
        # The Ask app installs LFM2 from kilix-needle's own vendored
        # kilix-content. A review found that copy one delivery behind, with the
        # agreement record the image's notice receipt does not cover.
        pins = manifest(f"{VERSION}.env")
        content_ref = pins["PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF"]
        content = repo_holding("PLEBIAN_OS_KILIX_CONTENT_REPO", "kilix-content", content_ref)
        self.assertIsNotNone(content, "no kilix-content checkout holds the carrier content ref")
        show = lambda repo, ref, path: subprocess.run(
            ["git", "-C", str(repo), "--no-replace-objects", "show", f"{ref}:{path}"],
            capture_output=True, check=True).stdout
        catalog = json.loads(show(content, content_ref, "src/kilix_content/catalog/plebian.json"))
        (app,) = [item for item in catalog["content"] if item["id"] == "kilix-needle"]
        ref = app["source"]["ref"]
        needle = repo_holding("PLEBIAN_OS_KILIX_NEEDLE_REPO", "kilix-needle", ref)
        self.assertIsNotNone(needle, f"no kilix-needle checkout holds {ref}; "
                             "set PLEBIAN_OS_KILIX_NEEDLE_REPO")
        vendored = subprocess.run(
            ["git", "-C", str(needle), "--no-replace-objects", "rev-parse",
             f"{ref}:third_party/kilix-content"],
            capture_output=True, text=True, check=True).stdout.strip()
        holder = repo_holding("PLEBIAN_OS_KILIX_CONTENT_REPO", "kilix-content", vendored)
        self.assertIsNotNone(holder, f"no kilix-content checkout holds {vendored}")
        vendored_catalog = json.loads(show(holder, vendored, "src/kilix_content/catalog/plebian.json"))
        record = show(holder, vendored, "third_party/kilix-license/src/kilix_license/data/"
                      "lfm2-records/lfm2-kilix-commands.json")
        commands_model = json.loads(show(needle, ref, "commands-model.json"))
        self.assertEqual(needle_vendor_gaps(vendored_catalog, record, commands_model), [])
        # Planted: the old delivery, the old agreement record, a stale model file.
        stale = json.loads(json.dumps(vendored_catalog))
        (asset,) = [item for item in stale["assets"] if item["id"] == "lfm2-kilix-commands"]
        asset["version"] = "lfm2-kilix-commands-20261104-v8"
        agreement = record.replace(b'"informational"', b'"affirmative"')
        self.assertNotEqual(agreement, record)
        old_model = dict(commands_model, version="lfm2-kilix-commands-20261104-v8")
        for planted in ((stale, record, commands_model), (vendored_catalog, agreement, commands_model),
                        (vendored_catalog, record, old_model)):
            self.assertEqual(len(needle_vendor_gaps(*planted)), 1)

    # AC-5
    def test_carrier_covers_every_advertised_model(self):
        provision = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
        advertised = advertised_models(provision)
        self.assertTrue(advertised)
        # The provisioner's catalog check enforces a fixed record count; the
        # advertised set must be exactly that many models.
        block = provision[provision.index("validate_voice_model_catalog() {"):]
        self.assertIn("len(records) != len(expected)", block)
        self.assertEqual(coverage_gaps(provision), [])
        # D9: an advertised model the carrier does not carry.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "carrier"
            shutil.copytree(CARRIER, root)
            dropped = carrier_env()["models"].split()[-1]
            edit_env(root, "models", " ".join(carrier_env()["models"].split()[:-1]))
            carrier = json.loads((root / "CARRIER.json").read_bytes())
            del carrier["models"][dropped]
            (root / "CARRIER.json").write_bytes(json.dumps(carrier, sort_keys=True).encode())
            self.assertTrue(coverage_gaps(provision, root))

    # AC-6
    def test_acceptance_receipt_names_the_real_determinations(self):
        receipt = json.loads((CARRIER / "ACCEPTANCE.json").read_bytes())
        carrier = json.loads((CARRIER / "CARRIER.json").read_bytes())
        self.assertEqual(receipt["carrier_sha256"], sha256((CARRIER / "CARRIER.json").read_bytes()))
        covered = set()
        for item in receipt["determinations"]:
            path = CARRIER / item["path"]
            self.assertTrue(path.is_file(), item["path"])
            self.assertEqual(sha256(path.read_bytes()), item["sha256"], item["path"])
            text = path.read_text()
            self.assertEqual(determination_gaps(item["model"], text, carrier["models"][item["model"]]),
                             [], item["path"])
            if not text.startswith(DISTRIBUTION_HEADING):
                covered.add(item["model"])
        # Every carried model has a determination; a distribution decision never stands in for one.
        self.assertEqual(covered, set(carrier["models"]))
        planted = "# Owner distribution decision — x\n| Decided by | someone else |\n"
        self.assertEqual(determination_gaps("whisper-medium-en", planted, {}), ["missing owner decision"])

    def test_whistle_authorization_requires_the_real_request_and_upstream_evidence(self):
        carrier = json.loads((CARRIER / "CARRIER.json").read_bytes())
        entry = carrier["models"]["whistle"]
        # The receipt names the accepted record; its file name changes per release.
        receipt = json.loads((CARRIER / "ACCEPTANCE.json").read_bytes())
        paths = [item["path"] for item in receipt["determinations"] if item["model"] == "whistle"]
        self.assertEqual(len(paths), 1, paths)
        text = (CARRIER / paths[0]).read_text()
        self.assertEqual(determination_gaps("whistle", text, entry), [])
        for before, after in (
            ("> should we integrat", "> please inspect"),
            ("Licence: Apache-2.0.", "Licence: MIT."),
            ("Cactus Compute, Inc.", "Another licensor"),
            (entry["licence_text_sha256s"][0], "0" * 64),
            ("This record is not end-user licence acceptance", "This record is end-user licence acceptance"),
        ):
            with self.subTest(changed=before):
                self.assertNotEqual(text.replace(before, after), text)
                self.assertTrue(determination_gaps("whistle", text.replace(before, after), entry))
        self.assertTrue(determination_gaps("small-en-us", text, entry))

    # AC-7
    def test_acceptance_receipt_names_two_independent_seats(self):
        receipt = json.loads((CARRIER / "ACCEPTANCE.json").read_bytes())
        self.assertEqual(len(receipt["seats"]), 2)
        self.assertEqual(len({seat["sha256"] for seat in receipt["seats"]}), 2)
        for seat in receipt["seats"]:
            path = CARRIER / seat["path"]
            self.assertEqual(sha256(path.read_bytes()), seat["sha256"], seat["path"])
            text = path.read_text()
            self.assertRegex(text, r"(?i)did not author")
            self.assertRegex(text, r"(?m)^VERDICT: ship( with known issues)?\s*$")
            self.assertIn(receipt["carrier_sha256"], text)
            bundle = json.loads((CARRIER / "DEFAULT-MODELS.json").read_bytes())
            self.assertIn(bundle["sha256"], text)

    # AC-8
    def test_delivery_statement_is_true_of_this_image(self):
        provision = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
        pins = manifest(f"{VERSION}.env")
        self.assertEqual(delivery_gaps(provision), [])
        # The command model DELIVERY describes what the image installer does.
        installer = (ROOT / "provision" / "install-image-models.py").read_text()
        self.assertEqual(command_installer_gaps(installer), [])
        self.assertEqual(image_offline_installer_gaps(installer), [])
        for planted in (
                installer.replace("'--copies'", "'--symlinks'"),
                installer.replace("for name in PARADEE_FILES:",
                                  "for name in (PARADEE_ONNX, PARADEE_CONFIG):", 1),
                installer.replace("    for name in PARADEE_FILES:\n        target = root / name",
                                  "    for name in (PARADEE_ONNX, PARADEE_CONFIG):\n        target = root / name"),
                installer.replace("the installation media did not supply the Paradee model",
                                  "the installation media will download the Paradee model"),
                installer.replace("        build_spacy_archive(scratch / SPACY_WHEEL, output, spacy_pin)\n",
                                  "        output.write_bytes((scratch / SPACY_WHEEL).read_bytes())\n"),
                installer.replace("        verify_paradee_wheels(wheelhouse, lock)\n    placed",
                                  "    placed"),
                installer.replace("        verify(staged, pin)\n        staged.chmod", "        staged.chmod"),
                installer.replace("        if offline or (archive", "        if (archive"),
                installer.replace("    install_paradee(args.kilix, resolve_paradee(args.paradee), paradee_pin, offline=args.offline)",
                                  "    install_paradee(args.kilix, resolve_paradee(args.paradee), paradee_pin, offline=args.offline)\n"
                                  "    fetch_default(args.kilix, paradee_pin['asset_id'], 'Paradee', paradee_pin['manifest_digest'])")):
            self.assertNotEqual(planted, installer)
            self.assertTrue(image_offline_installer_gaps(planted))
        # ...and the Playalong default DELIVERY too, with each claim it rests on planted false.
        self.assertEqual(playalong_installer_gaps(installer), [])
        for planted in (installer.replace("    if declined is None:\n        install_whisper_medium",
                                          "    if True:\n        install_whisper_medium"),
                        installer.replace("    declined = playalong_declined(args.kilix)\n",
                                          "    declined = None\n"),
                        installer.replace("    elif offline:\n        print('Whisper medium.en is not in the image",
                                          "    elif offline:\n        fetch_default(kilix, WHISPER_MEDIUM, 'x', manifest_digest)\n"
                                          "        print('Whisper medium.en is not in the image"),
                        installer.replace("        defaults.authorize(lic, spec, records, store)\n"
                                          "        installer = api.Installer(_apps_root())\n        try:",
                                          "        installer = api.Installer(_apps_root())\n        try:"),
                        installer.replace("    if _playalong_installed(cm, WHISPER_MEDIUM):",
                                          "    if _installed(cm, WHISPER_MEDIUM):"),
                        installer.replace("    except cm._api().InstallError as error:",
                                          "    except cm.SetupError as error:")):
            self.assertNotEqual(planted, installer)
            self.assertTrue(playalong_installer_gaps(planted))
        for planted in (installer.replace("lic.capture_agreement(record)",
                                          "lic.capture_agreement(record, 'yes')"),
                        installer.replace("lic.capture_agreement(record)",
                                          "lic.capture_agreement(record, typed='yes')"),
                        installer.replace("if record.expected_decision != 'record':", "if False:")):
            self.assertNotEqual(planted, installer)
            self.assertTrue(command_installer_gaps(planted))
        # The download is digest-verified and receipt-gated at the pinned refs.
        self.assertIsNone(voice_contract.content_chain_gap(pins["KILIX_REF"]))
        self.assertIsNone(voice_contract.receipt_gate_gap(pins["KILIX_VOICE_REF"]))
        # Every Kilix route, at the pinned KILIX_REF, asks that gate first.
        kilix = repo_holding("PLEBIAN_OS_KILIX_REPO", "kilix", pins["KILIX_REF"])
        self.assertIsNotNone(kilix, "no Kilix checkout holds KILIX_REF; set PLEBIAN_OS_KILIX_REPO")
        installer = kilix_show(kilix, pins["KILIX_REF"], "scripts/install-kilix-voice.sh")
        self.assertEqual(kilix_gate_gaps(installer), [])
        self.assertTrue(kilix_gate_gaps(installer.replace('require_dictation_receipt "', 'true "')))
        # The patcher the medium DELIVERY names exists at KILIX_REF, the voice installer runs
        # it, and a DELIVERY that drops it is caught.
        self.assertIn("patch-whisper-medium-model.py", installer)
        self.assertIn("whisper-medium-en", kilix_show(
            kilix, pins["KILIX_REF"], "scripts/patch-whisper-medium-model.py"))
        with tempfile.TemporaryDirectory() as scratch:
            planted = Path(scratch) / "carrier"
            shutil.copytree(CARRIER, planted)
            medium = planted / "whisper-medium-en" / "DELIVERY"
            text = medium.read_text()
            stripped = "".join(line for line in text.splitlines(keepends=True)
                               if "patch-whisper-medium-model.py" not in line)
            self.assertNotEqual(stripped, text)
            medium.write_text(stripped)
            self.assertIn("whisper-medium-en: DELIVERY does not name the Kilix patcher its route depends on",
                          delivery_gaps(provision, planted))
        # ...and so does the kilix-bonsai that KILIX_REF installs.
        ref = bonsai_ref(kilix_show(kilix, pins["KILIX_REF"], "scripts/install-kilix-bonsai.sh"))
        self.assertRegex(ref, r"^[0-9a-f]{40}$", "KILIX_REF pins no kilix-bonsai commit")
        bonsai = repo_holding("PLEBIAN_OS_KILIX_BONSAI_REPO", "kilix-bonsai", ref)
        self.assertIsNotNone(bonsai, f"no kilix-bonsai checkout holds {ref}; "
                             "set PLEBIAN_OS_KILIX_BONSAI_REPO")
        model_json, main_py, pull_sh = (kilix_show(bonsai, ref, path) for path in (
            "models/vibevoice-asr-bitnet/MODEL.json", "tools/kilix-bonsai/main.py",
            "models/_shared/pull.sh"))
        model = "vibevoice-asr-bitnet"
        self.assertEqual(bonsai_gate_gaps(model_json, main_py, pull_sh, model), [])
        self.assertTrue(bonsai_gate_gaps(
            model_json.replace('"licence_gate"', '"no_gate"'), main_py, pull_sh, model))
        self.assertTrue(bonsai_gate_gaps(model_json, main_py, pull_sh.replace(
            '"$gate_tool" --check-licence "$licence_gate"', "true"), model))
        # D6: the same DELIVERY statement is false of an image that provisions weights.
        self.assertTrue(delivery_gaps(provision.replace(
            "readonly PROVISION_VOICE_WEIGHTS=0", "readonly PROVISION_VOICE_WEIGHTS=1")))

    # AC-9
    def test_guard_refuses_without_a_carrier(self):
        for overrides in ({"PLEBIAN_OS_VOICE_CARRIER_DIR": ""},
                          {"PLEBIAN_OS_VOICE_CARRIER_DIR": "",
                           "PLEBIAN_OS_VOICE_CARRIER_SHA256": ""}):
            result = run_guard(release_env(**overrides))
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stderr, REFUSAL)

    # AC-10
    def test_guard_accepts_the_verified_carrier(self):
        result = run_guard(release_env())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")

    # AC-11
    def test_guard_refuses_every_planted_carrier_defect(self):
        env0 = carrier_env()
        dictation = "m_" + re.sub(r"[^a-z0-9]", "_", env0["dictation_model"])
        text = env0[f"{dictation}_licence_text_sha256s"].split()[0]

        def flip(value):
            return ("0" if value[0] != "0" else "1") + value[1:]

        # Unpinned tampering: bytes change, only SHA256SUMS is recomputed.
        # Each must stop at the bindings, whatever the edit claims.
        unpinned = [
            ("seat scenario: false licensor",
             lambda r: edit_env(r, "m_lgraph_en_us_licensors", "Fictitious Licensor")),
            ("D5 bound digest differs",
             lambda r: edit_env(r, f"{dictation}_archive_sha256",
                                flip(env0[f"{dictation}_archive_sha256"]))),
            ("D7 borrowed licence text",
             lambda r: (r / "licence-texts" / f"{text}.txt").write_bytes(
                 (r / "licence-texts" / f"{text}.txt").read_bytes().replace(b"\n", b"\r\n"))),
            ("false NOTICE", lambda r: (r / env0["dictation_model"] / "NOTICE").write_text("forged\n")),
        ]
        for label, plant in unpinned:
            with self.subTest(defect=label), tempfile.TemporaryDirectory() as td:
                root = Path(td) / "carrier"
                shutil.copytree(CARRIER, root)
                plant(root)
                resum(root)
                result = run_guard(release_env(root))
                self.assertEqual(result.returncode, 1, label)
                self.assertIn("a bound file does not match BINDINGS.sha256", result.stderr, label)
                self.assertTrue(result.stderr.endswith(REFUSAL), label)

        # Fully re-pinned forgeries: every digest and both pins re-derived.
        # The validator's own checks must still refuse each for its reason.
        def remove_notice(r): (r / env0["dictation_model"] / "NOTICE").unlink()
        def add_key(r):
            with open(r / "CARRIER.env", "a") as fh:
                fh.write("sneaky=1\n")
        repinned = [
            ("D4 wrong release", lambda r: edit_env(r, "release_id", "0.2.1"), {}, "carrier is for release 0.2.1"),
            ("D5 archive differs from the release pin",
             lambda r: edit_env(r, f"{dictation}_archive_sha256", flip(env0[f"{dictation}_archive_sha256"])),
             {}, "is not KILIX_VOICE_MODEL_URL/SHA256"),
            ("D11 placeholder value", lambda r: edit_env(r, f"{dictation}_licensors", "REPLACE_ME"), {},
             "is empty or a placeholder"),
            ("unknown key", add_key, {}, "unknown key sneaky"),
            ("missing notice", remove_notice, {}, "NOTICE is missing"),
            ("other content interface", lambda r: edit_env(r, "interface_content_ref", "f" * 40), {},
             "producing interfaces"),
            ("false delivery mode", lambda r: edit_env(r, f"{dictation}_delivery", "provisioned"), {},
             "delivery differs from the default inventory"),
            ("undecided licence", lambda r: edit_env(r, f"{dictation}_decision", "pending"), {},
             "decision is not affirmative or informational"),
            ("unknown licence decision", lambda r: edit_env(r, f"{dictation}_decision", "record"), {},
             "decision is not affirmative or informational"),
            ("foreign upstream host", lambda r: edit_env(r, f"{dictation}_upstream_host", "example.invalid"), {},
             "upstream host does not match its source"),
            ("D4b wrong release inputs", lambda r: None,
             {"KILIX_VOICE_MODEL_SHA256": flip(env0[f"{dictation}_archive_sha256"])},
             "is not KILIX_VOICE_MODEL_URL/SHA256"),
            ("other speech library", lambda r: None, {"KILIX_VOICE_LIB_SHA256": "c" * 64},
             "different speech library"),
            ("other licence interface", lambda r: None, {"KILIX_LICENSE_REF": "d" * 40},
             "producing interfaces"),
            # Carrier interface and release pin moved together to that older
            # content: consistent with each other, not with what Kilix serves.
            ("carrier and pin agree on unserved content",
             lambda r: edit_env(r, "interface_content_ref", "6b29514655ce5653153dd6a8852636e46907ac8c"),
             {"PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF": "6b29514655ce5653153dd6a8852636e46907ac8c"},
             "is not KILIX_REF's kilix-content gitlink"),
            ("unreadable host tree", lambda r: None, {"KILIX_REPO": "/nonexistent/kilix"},
             "KILIX_REF cannot be read"),
        ]
        # The seat's attack, hermetic: a Kilix whose content gitlink is not the
        # carrier's, as its parent commit (the older Kilix) in a local repo.
        with tempfile.TemporaryDirectory() as td:
            older, served = gitlink_repo(Path(td) / "kilix", [
                "6b29514655ce5653153dd6a8852636e46907ac8c", env0["interface_content_ref"]])
            kilix = {"KILIX_REPO": str(Path(td) / "kilix")}
            with self.subTest(defect="control: the stand-in serving the carrier's content"):
                self.assertEqual(run_guard(release_env(KILIX_REF=served, **kilix)).returncode, 0)
            with self.subTest(defect="host serves other content"):
                result = run_guard(release_env(KILIX_REF=older, **kilix))
                self.assertEqual(result.returncode, 1)
                self.assertIn("is not KILIX_REF's kilix-content gitlink", result.stderr)
                self.assertTrue(result.stderr.endswith(REFUSAL))
        for label, plant, release, reason in repinned:
            with self.subTest(defect=label), tempfile.TemporaryDirectory() as td:
                root = Path(td) / "carrier"
                shutil.copytree(CARRIER, root)
                plant(root)
                result = run_guard(release_env(root, **rebind(root), **release))
                self.assertEqual(result.returncode, 1, label)
                self.assertIn(reason, result.stderr, label)
                self.assertTrue(result.stderr.endswith(REFUSAL), label)

        # Structural defects.
        def empty(r):
            shutil.rmtree(r)
            r.mkdir()
        def forged_receipt(r):
            (r / "ACCEPTANCE.json").write_text('{"seats":["fictitious"]}\n')
        def extra(r): (r / "EXTRA").write_text("x\n")
        def extra_seat(r): (r / "seats" / "forged.md").write_text("VERDICT: ship\n")
        def missing_seat(r):
            sorted((r / "seats").iterdir())[0].unlink()
            resum(r)
        def no_seats(r):
            shutil.rmtree(r / "seats")
            resum(r)
        structural = [
            ("D2 empty carrier", empty, lambda r: {}, "CARRIER.json is missing"),
            ("D3 forged receipt", forged_receipt, lambda r: {},
             "does not match PLEBIAN_OS_VOICE_CARRIER_RECEIPT_SHA256"),
            ("D3b consistently forged receipt", forged_receipt,
             lambda r: {"PLEBIAN_OS_VOICE_CARRIER_RECEIPT_SHA256": sha256((r / "ACCEPTANCE.json").read_bytes())},
             "is not the receipt for this carrier"),
            ("D8 unlisted extra file", extra, lambda r: {}, "bound by neither pin"),
            ("unlisted seat record", extra_seat, lambda r: {}, "bound by neither pin"),
            ("seat record deleted", missing_seat, lambda r: {}, "is missing or is not the record"),
            ("all seat records deleted", no_seats, lambda r: {}, "is missing or is not the record"),
        ]
        for label, plant, overrides, reason in structural:
            with self.subTest(defect=label), tempfile.TemporaryDirectory() as td:
                root = Path(td) / "carrier"
                shutil.copytree(CARRIER, root)
                plant(root)
                result = run_guard(release_env(root, **overrides(root)))
                self.assertEqual(result.returncode, 1, label)
                self.assertIn(reason, result.stderr, label)
                self.assertTrue(result.stderr.endswith(REFUSAL), label)
        # D10: a symlinked carrier.
        with tempfile.TemporaryDirectory() as td:
            link = Path(td) / "link"
            link.symlink_to(CARRIER, target_is_directory=True)
            result = run_guard(release_env(link))
            self.assertEqual(result.returncode, 1)
            self.assertIn("is not a real directory", result.stderr)
        # D1 (no carrier) is AC-9. D3c/D5b (fully re-pinned forgeries of
        # the evidence itself) pass the shell guard by construction and are
        # refuted by AC-1, AC-4, AC-6 and AC-7 plus review of the pin diff.

    # AC-12
    def test_release_requirements_pin_the_carrier(self):
        env = manifest(f"{VERSION}.env")
        requirements = manifest(f"{VERSION}.requirements")
        for key in ("PLEBIAN_OS_VOICE_CARRIER_DIR", "PLEBIAN_OS_VOICE_CARRIER_SHA256",
                    "PLEBIAN_OS_VOICE_CARRIER_RECEIPT_SHA256", "PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF",
                    "KILIX_LICENSE_REF"):
            self.assertIn(key, requirements)
            self.assertEqual(requirements[key], env[key], key)
        self.assertEqual(env["PLEBIAN_OS_VOICE_CARRIER_DIR"],
                         f"releases/{VERSION}-model-compliance")
        self.assertEqual(env["PLEBIAN_OS_VOICE_CARRIER_SHA256"],
                         sha256((CARRIER / "CARRIER.json").read_bytes()))
        self.assertEqual(env["PLEBIAN_OS_VOICE_CARRIER_RECEIPT_SHA256"],
                         sha256((CARRIER / "ACCEPTANCE.json").read_bytes()))


if __name__ == "__main__":
    unittest.main()
