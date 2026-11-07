#!/usr/bin/env python3
"""Generate the release model compliance carrier (F100 / OD-BA / OD-BB / OD-BC).

The carrier is the "accepted F100 compliance-carrier interface and receipt"
that `build/remaster-iso.sh` requires before a release may advertise a speech
model (PLEBIAN_OS_INSTALL_VOICE_MODEL=1). Its design is
F100-CARRIER-DESIGN.md §5 in the owner's research records.

Nothing here is typed by hand. Every value is read from:
  * this repository: `releases/<version>.env` (pins) and the speech-model
    catalog `provision/plebian-os-provision.sh` enforces (the advertised set);
  * kilix-content at `PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF`: the `kilix.content.asset/v3`
    records, digested by kilix-content's own `AssetSpec`;
  * kilix-license at `KILIX_LICENSE_REF`: the `kilix.license.record/v1`
    records (digested by kilix-license's own `LicenseRecord`) and the licence
    texts it stores by digest;
  * owner determination files and independent seat records, passed as
    arguments and copied verbatim.

Re-running with the same inputs reproduces every byte (AC-1).

Usage:
  generate-model-compliance.py --content-repo DIR --license-repo DIR \
      --determination MODEL=FILE [...] [--seat FILE ...] [--out DIR] [--check]
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
CARRIER_SCHEMA = "plebian-os.release-model-compliance/v1"
ACCEPTANCE_SCHEMA = "plebian-os.release-model-compliance-acceptance/v1"
DELIVERY_MODE = "first-use-upstream-download"
# The ids of the acceptance lines, each one test in
# tests/test_model_compliance_carrier.py (F100-CARRIER-DESIGN.md §7.3).
QUALIFICATION = (
    ("AC-1", "test_carrier_regenerates_byte_identically"),
    ("AC-2", "test_carrier_env_is_a_faithful_projection_of_carrier_json"),
    ("AC-3", "test_carrier_licence_records_match_kilix_license"),
    ("AC-4", "test_carrier_artifact_records_match_kilix_content"),
    ("AC-5", "test_carrier_covers_every_advertised_model"),
    ("AC-6", "test_acceptance_receipt_names_the_real_determinations"),
    ("AC-7", "test_acceptance_receipt_names_two_independent_seats"),
    ("AC-8", "test_delivery_statement_is_true_of_this_image"),
    ("AC-9", "test_guard_refuses_without_a_carrier"),
    ("AC-10", "test_guard_accepts_the_verified_carrier"),
    ("AC-11", "test_guard_refuses_every_planted_carrier_defect"),
    ("AC-12", "test_release_requirements_pin_the_carrier"),
)
# Owner decisions the determinations rest on (F100-CARRIER-DESIGN.md §5.2.5).
DECISIONS = ("OD-S", "OD-U", "OD-AB", "OD-AI", "OD-AJ", "OD-AQ", "OD-BA", "OD-BB", "OD-BC")


def canonical(value) -> bytes:
    """Sorted-key compact UTF-8 JSON, the form kilix-content digests."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def env_key(model: str) -> str:
    return "m_" + re.sub(r"[^a-z0-9]", "_", model)


def read_manifest(version: str, path: Path | None = None) -> dict[str, str]:
    values = {}
    path = path or ROOT / "releases" / f"{version}.env"
    for line in path.read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


# Licence records are keyed by the speech catalog id, except where the record
# names the upstream artifact: whisper-small-en runs the faster-whisper
# conversion, whose record is faster-whisper-small-en.
LICENCE_RECORD_IDS = {"whisper-small-en": "faster-whisper-small-en"}
# Models whose only download route is the model catalog itself: `kilix stt
# --install` runs `kilix models install`, the licence screen, and fetches
# nothing on its own, so there is no separate receipt check to cite.
CATALOG_INSTALLED_MODELS = frozenset({"whisper-small-en", "whistle"})


def licence_record_id(model: str) -> str:
    return LICENCE_RECORD_IDS.get(model, model)


def advertised_models() -> list[tuple[str, bool]]:
    """(model, runnable) in the order the provisioner's catalog check enforces."""
    source = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
    start = source.index("validate_voice_model_catalog() {")
    block = source[start:source.index("\n}\n", start)]
    found = re.findall(r'\(\s*"([a-z0-9.-]+)", "[a-z]+", (True|False), \d+,', block)
    if not found:
        raise SystemExit("could not read the advertised speech-model catalog")
    # Diarization uses the generic Content catalog, not the dictation protocol.
    return [(name, flag == "True") for name, flag in found] + [
        ("kilix-diarization-cpu", True),
    ]


def extract(repo: Path, ref: str, dest: Path) -> None:
    """The tree of `ref`, exactly; the working tree of `repo` is never read."""
    archive = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", ref],
                             check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(dest, filter="data")


def load_module(src: Path, name: str):
    """Import `name` from `src` alone: kilix-content vendors its own copy of
    kilix-license, which must never stand in for the pinned one."""
    top = name.split(".")[0]
    for loaded in [m for m in sys.modules if m == top or m.startswith(top + ".")]:
        del sys.modules[loaded]
    sys.path.insert(0, str(src))
    try:
        module = importlib.import_module(name)
    finally:
        sys.path.remove(str(src))
    if not Path(module.__file__).resolve().is_relative_to(src.resolve()):
        raise SystemExit(f"{name} was not loaded from {src}")
    return module


def delivery_text(model: str, host: str, runnable: bool, voice_ref: str,
                  *, bundled: bool = False, command_archive: bool = False) -> str:
    # Every sentence here is a claim tests/test_model_compliance_carrier.py
    # checks (AC-8): delivery matches the exact default bundle inventory and
    # deferred downloads remain digest-verified and licence-receipt gated.
    if command_archive:
        return "\n".join([
            "mode: bundled-command-model-archive",
            "Installation media includes this model in a separately checksummed command-model archive.",
            "Provisioning stages it offline; upgrades acquire the pinned archive in their admin context.",
            "Original licence documents are available under /usr/local/share/doc/plebian-os/models/.",
            "Provisioning and upgrades install it and record a notice receipt for the exact licence record and member manifest.",
            "By the owner's 2026-11-07 determination its custom terms, including the commercial-use limitation, are a notice:",
            "they are shipped and not waived, and no agreement is recorded.",
            "Terms that need a typed agreement are never answered by the image.",
            "Content verifies every member before use; explicit model choices and older versions are retained.",
            f"Artifact provenance: {host}.",
        ]) + "\n"
    if bundled:
        return "\n".join([
            "mode: bundled-default-model",
            "This model is included in the checksummed default model bundle on installation media.",
            "Provisioning installs the supplied bytes offline; upgrades may acquire the same pinned bundle.",
            "Original licence documents accompany the model, and installation verifies every catalogued file.",
            "Installation creates local standard-policy receipts; build-time receipts are never distributed.",
            "Existing model selections are preserved. Bundling does not prove runtime quality or activation.",
            f"Upstream artifact provenance: {host}.",
        ]) + "\n"
    lines = [
        f"mode: {DELIVERY_MODE}",
        "This model's weights are not present in the image or downloaded by provisioning.",
        f"{model} reaches a machine only when a user installs it; it is downloaded from",
        f"{host} and verified against the pinned digests before installation.",
        "No install route downloads it until a kilix-license receipt covers it:",
        "The model catalog validates the determined licence and records the receipt, and",
    ]
    if model == "kilix-diarization-cpu":
        lines += [
            "The generic model catalog downloads pinned upstream inputs and converts them locally.",
            "Transcribe checks the covering receipt and installed manifest before diarization.",
            "Conversion software is installed separately; no model is selected by default.",
        ]
    elif model in CATALOG_INSTALLED_MODELS:
        lines += [
            "The speech install command hands the download to that model catalog",
            f"and fetches no weights itself (kilix-voice {voice_ref}).",
        ]
    else:
        lines += [
            "The speech install command, voice installer and Bonsai pull command first ask",
            f"`kilix-stt --check-licence` (kilix-voice {voice_ref}).",
        ]
    if not runnable:
        lines.append(f"{model} is installable in this release but not runnable: the "
                     "speech runtime does not yet support it.")
    return "\n".join(lines) + "\n"


def notice_text(model: str, entry: dict, determination: str) -> str:
    lines = [
        f"Plebian-OS {entry['release_id']} conveyance notice for {model}.",
        "This file is written by Plebian-OS. It is not an upstream NOTICE file.",
        ("Plebian-OS distributes these model bytes in a verified archive on installation media."
         if entry["delivery"] in ("bundled-default-model", "bundled-command-model-archive")
         else "Plebian-OS does not distribute these model bytes."),
        "",
        f"Artifact: {entry['artifact_id']} (provider {entry['provider']}, version {entry['version']})",
        f"Source: {entry['source_url']}",
        f"Upstream host: {entry['upstream_host']}",
        f"Download size: {entry['download_bytes']} bytes",
    ]
    if entry.get("archive_sha256"):
        lines.append(f"Archive sha256: {entry['archive_sha256']}")
    lines += [
        f"Installed member manifest digest: {entry['manifest_digest']}",
        f"Licence(s): {', '.join(entry['licence_ids'])}",
        f"Licensor(s): {'; '.join(entry['licensors'])}",
        "Licence, advisory and attribution texts: " + ", ".join(f"licence-texts/{d}.txt" for d in entry["licence_text_sha256s"]),
        f"Owner determination: {determination}",
    ]
    return "\n".join(lines) + "\n"


def build(args) -> dict[str, bytes]:
    version = (ROOT / "VERSION").read_text().strip()
    pins = read_manifest(version, getattr(args, "manifest", None))
    if pins.get("PLEBIAN_OS_VERSION") != version:
        raise SystemExit("manifest version differs from VERSION")
    content_ref = pins["PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF"]
    license_ref = pins["KILIX_LICENSE_REF"]
    models = advertised_models()
    determinations = {}
    for item in args.determination:
        model, _, path = item.partition("=")
        determinations.setdefault(model, []).append(Path(path))
    files: dict[str, bytes] = {}
    bundle_path = ROOT / "provision" / "default-models.json"
    bundle = json.loads(bundle_path.read_bytes()) if bundle_path.exists() else None
    command_path = ROOT / "provision" / "command-model.json"
    command = json.loads(command_path.read_bytes()) if command_path.exists() else None
    if command is not None:
        if (command.get("schema") != "plebian-os.command-model-archive/v1"
                or command.get("asset_id") != "lfm2-kilix-commands"):
            raise SystemExit("invalid command-model archive selection")
        models.append((command["asset_id"], True))
        files["COMMAND-MODEL.json"] = canonical(command) + b"\n"
    if bundle is not None:
        if (bundle.get("schema") != "plebian-os.default-models-archive/v1"
                or not isinstance(bundle.get("assets"), dict) or not bundle["assets"]
                or not re.fullmatch(r"[0-9a-f]{64}", bundle.get("sha256", ""))
                or type(bundle.get("bytes")) is not int or bundle["bytes"] <= 0
                or not bundle.get("url", "").startswith("https://")):
            raise SystemExit("default bundle has no exact archive and asset inventory")
        files["DEFAULT-MODELS.json"] = canonical(bundle) + b"\n"

    with tempfile.TemporaryDirectory() as scratch:
        scratch = Path(scratch)
        extract(args.content_repo, content_ref, scratch / "content")
        extract(args.license_repo, license_ref, scratch / "license")
        license_catalog = load_module(scratch / "license" / "src", "kilix_license.catalog")
        policy = importlib.import_module("kilix_license.standard_policy")
        content_model = load_module(scratch / "content" / "src", "kilix_content.model")
        catalog = json.loads((scratch / "content" / "src" / "kilix_content" / "catalog"
                              / "plebian.json").read_text())
        assets = [content_model.AssetSpec.from_mapping(raw) for raw in catalog["assets"]]
        records = license_catalog.load_determined_records(scratch / "license")
        if command is not None:
            selected = next((a for a in assets if a.asset_id == command["asset_id"]), None)
            if (selected is None or selected.archive_sha256 != command["sha256"]
                    or selected.archive_bytes != command["bytes"]
                    or selected.source_url != command["url"]
                    or selected.version != command["version"] or selected.root != command["root"]
                    or selected.manifest_digest != command["manifest_digest"]):
                raise SystemExit("command archive differs from the selected catalog asset")
            documents = {f.path: {"bytes": f.bytes, "sha256": f.sha256}
                         for f in selected.files if f.path.startswith("notices/")}
            if documents != command["documents"]:
                raise SystemExit("command archive licence documents differ from the catalog")
        if bundle is not None:
            by_id = {asset.asset_id: asset for asset in assets}
            for asset_id, digest in bundle["assets"].items():
                if asset_id not in by_id or by_id[asset_id].manifest_digest != digest:
                    raise SystemExit(f"default bundle differs from the selected asset: {asset_id}")
                for licence in by_id[asset_id].licenses:
                    if not policy.standard_policy_eligible(records.by_digest(licence.record_digest)):
                        raise SystemExit(f"{asset_id}: default delivery requires a standard-policy eligible record")
        texts = scratch / "license" / "src" / "kilix_license" / "data" / "texts"
        schema_bytes = (scratch / "content" / "contracts" / "kilix.content.asset-v3.schema.json").read_bytes()

        entries = {}
        for model, runnable in models:
            record = records.by_id(licence_record_id(model))
            matches = [a for a in assets
                       if any(item.record_digest == record.digest for item in a.licenses)]
            if len(matches) != 1:
                raise SystemExit(f"{model}: expected one asset record bound to licence "
                                 f"record {record.digest}, found {len(matches)}")
            asset = matches[0]
            bundled = bundle is not None and asset.asset_id in bundle["assets"]
            command_archive = command is not None and asset.asset_id == command["asset_id"]
            if bundled:
                if not policy.standard_policy_eligible(record):
                    raise SystemExit(f"{model}: default delivery requires a standard-policy eligible record")
            mapping = asset.to_mapping()
            source = mapping["source"]
            record_file = license_catalog.record_path(licence_record_id(model), scratch / "license")
            digests = [record.text_sha256] + [
                component.exception_text_sha256 for component in record.components
                if getattr(component, "exception_text_sha256", None)]
            digests += [item.text_sha256 for item in record.advisories]
            digests += [item.text_sha256 for item in record.statements]
            if model == "kilix-diarization-cpu":
                authority = json.loads((scratch / "license" / "src" / "kilix_license"
                                        / "data" / "determinations-diarization.json").read_bytes())
                digests.append(authority["authority"]["native_software_notice_sha256"])
            licence_ids = [item.license_id for item in asset.licenses]
            licensors = []
            for item in asset.licenses:
                for name in item.licensors:
                    if name not in licensors:
                        licensors.append(name)
            entry = {
                "artifact_id": asset.asset_id,
                "artifact_record_sha256": asset.digest,
                "decision": record.decision_class,
                "delivery": ("bundled-command-model-archive" if command_archive else
                             "bundled-default-model" if bundled else DELIVERY_MODE),
                "download_bytes": asset.download_bytes,
                "licence_ids": licence_ids,
                "licence_record_digest": record.digest,
                "licence_record_file_sha256": sha256(record_file.read_bytes()),
                "licence_text_sha256s": digests,
                "licensors": licensors,
                "manifest_digest": asset.manifest_digest,
                "provider": asset.provider,
                "release_id": version,
                "runnable": runnable,
                "source_mode": source["mode"],
                "source_url": asset.source_url,
                "upstream_host": asset.source_host,
                "version": asset.version,
            }
            if source["mode"] == "upstream-archive":
                entry["archive_bytes"] = source["archive_bytes"]
                entry["archive_sha256"] = source["archive_sha256"]
            entries[model] = entry
            base = f"{model}/"
            files[base + "ARTIFACT.json"] = canonical(mapping)
            files[base + "LICENCE-RECORD.json"] = record_file.read_bytes()
            for digest in digests:
                data = (texts / digest).read_bytes()
                if sha256(data) != digest:
                    raise SystemExit(f"{model}: licence text {digest} does not match its digest")
                files[f"licence-texts/{digest}.txt"] = data
            paths = determinations.get(model)
            if not paths:
                raise SystemExit(f"{model}: no owner determination was given")
            names = []
            for path in paths:
                name = f"determinations/{model}/{path.name}"
                files[name] = path.read_bytes()
                names.append(name)
            files[base + "NOTICE"] = notice_text(model, entry, ", ".join(names)).encode()
            files[base + "DELIVERY"] = delivery_text(
                model, entry["upstream_host"], runnable, pins["KILIX_VOICE_REF"],
                bundled=bundled, command_archive=command_archive).encode()

        # The advertised dictation model is the one the release pins.
        dictation = [m for m, e in entries.items()
                     if e.get("archive_sha256") == pins["KILIX_VOICE_MODEL_SHA256"]]
        if len(dictation) != 1:
            raise SystemExit("the pinned KILIX_VOICE_MODEL_SHA256 names no single carried model")
        carrier = {
            "dictation_model": dictation[0],
            "interface_content_ref": content_ref,
            "interface_content_schema_sha256": sha256(schema_bytes),
            "interface_licence_ref": license_ref,
            "library_wheel_sha256": pins["KILIX_VOICE_LIB_SHA256"],
            "library_wheel_url": pins["KILIX_VOICE_LIB_URL"],
            "model_order": [model for model, _ in models],
            "models": entries,
            "release_id": version,
            "schema": CARRIER_SCHEMA,
            "voice_ref": pins["KILIX_VOICE_REF"],
        }
    # Every generated file is bound to the pinned CARRIER.json through
    # BINDINGS.sha256, so nothing the shell validator reads can change without
    # moving PLEBIAN_OS_VOICE_CARRIER_SHA256. Seat records join later and are
    # bound by the separately pinned ACCEPTANCE.json.
    files["CARRIER.env"] = project_env(carrier).encode()
    files["BINDINGS.sha256"] = "".join(
        f"{sha256(files[name])}  {name}\n" for name in sorted(files)).encode()
    carrier["bindings_sha256"] = sha256(files["BINDINGS.sha256"])
    carrier_bytes = canonical(carrier) + b"\n"
    files["CARRIER.json"] = carrier_bytes

    seats = []
    for path in args.seat:
        name = f"seats/{path.name}"
        if name in files:
            raise SystemExit(f"two seat records are named {path.name}")
        files[name] = path.read_bytes()
        seats.append({"path": name, "sha256": sha256(files[name]), "source": path.name})
    if args.seat:
        acceptance = {
            "carrier_sha256": sha256(carrier_bytes),
            "decisions": list(DECISIONS),
            "determinations": [
                {"model": model, "path": name, "sha256": sha256(files[name])}
                for model in entries for name in sorted(files)
                if name.startswith(f"determinations/{model}/")],
            "interface": {
                "kilix-content": {"commit": content_ref,
                                  "schema": "contracts/kilix.content.asset-v3.schema.json",
                                  "schema_sha256": carrier["interface_content_schema_sha256"]},
                "kilix-license": {"commit": license_ref,
                                  "records": {m: e["licence_record_file_sha256"] for m, e in entries.items()}},
            },
            "qualification": [{"id": ac, "test": f"tests/test_model_compliance_carrier.py::{name}"}
                              for ac, name in QUALIFICATION],
            "release_id": carrier["release_id"],
            "schema": ACCEPTANCE_SCHEMA,
            "seats": seats,
            "seat_scope": "Reviews cover only the exact source and delivery scope stated in each attached record.",
        }
        files["ACCEPTANCE.json"] = canonical(acceptance) + b"\n"
    listing = "".join(f"{sha256(files[name])}  {name}\n" for name in sorted(files))
    files["SHA256SUMS"] = listing.encode()
    return files


def project_env(carrier: dict) -> str:
    """The shell projection of CARRIER.json: strict KEY=VALUE, no quoting."""
    lines = [
        f"schema={carrier['schema']}",
        f"release_id={carrier['release_id']}",
        f"models={' '.join(carrier['model_order'])}",
        f"dictation_model={carrier['dictation_model']}",
        f"library_wheel_url={carrier['library_wheel_url']}",
        f"library_wheel_sha256={carrier['library_wheel_sha256']}",
        f"interface_content_ref={carrier['interface_content_ref']}",
        f"interface_content_schema_sha256={carrier['interface_content_schema_sha256']}",
        f"interface_licence_ref={carrier['interface_licence_ref']}",
        f"voice_ref={carrier['voice_ref']}",
    ]
    for model in carrier["model_order"]:
        entry = carrier["models"][model]
        key = env_key(model)
        lines += [
            f"{key}_artifact_id={entry['artifact_id']}",
            f"{key}_source_url={entry['source_url']}",
            f"{key}_upstream_host={entry['upstream_host']}",
            f"{key}_manifest_digest={entry['manifest_digest']}",
            f"{key}_artifact_record_sha256={entry['artifact_record_sha256']}",
            f"{key}_licence_record_digest={entry['licence_record_digest']}",
            f"{key}_licence_text_sha256s={' '.join(entry['licence_text_sha256s'])}",
            f"{key}_licensors={'; '.join(entry['licensors'])}",
            f"{key}_decision={entry['decision']}",
            f"{key}_delivery={entry['delivery']}",
            f"{key}_runnable={'yes' if entry['runnable'] else 'no'}",
        ]
        if "archive_sha256" in entry:
            lines += [f"{key}_archive_sha256={entry['archive_sha256']}",
                      f"{key}_archive_bytes={entry['archive_bytes']}"]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--content-repo", type=Path, required=True)
    parser.add_argument("--license-repo", type=Path, required=True)
    parser.add_argument("--manifest", type=Path,
                        help="explicit candidate pins for review before the release manifest is finalized")
    parser.add_argument("--determination", action="append", default=[],
                        metavar="MODEL=FILE")
    parser.add_argument("--seat", action="append", default=[], type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--check", action="store_true",
                        help="compare with --out instead of writing it")
    args = parser.parse_args()
    version = (ROOT / "VERSION").read_text().strip()
    out = args.out or ROOT / "releases" / f"{version}-model-compliance"
    files = build(args)
    if args.check:
        on_disk = {str(p.relative_to(out)): p.read_bytes()
                   for p in sorted(out.rglob("*")) if p.is_file()}
        if on_disk != files:
            differ = sorted(set(on_disk) ^ set(files)) or sorted(
                k for k in files if on_disk.get(k) != files[k])
            print("carrier differs: " + ", ".join(differ), file=sys.stderr)
            return 1
        return 0
    if out.exists():
        shutil.rmtree(out)
    for name, data in files.items():
        path = out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(0o644)
    print(f"wrote {len(files)} files to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
