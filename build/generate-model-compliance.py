#!/usr/bin/env python3
"""Generate the release model compliance carrier (F100 / OD-BA / OD-BB / OD-BC).

The carrier is the "accepted F100 compliance-carrier interface and receipt"
that `build/remaster-iso.sh` requires before a release may advertise a speech
model (PLEBIAN_OS_INSTALL_VOICE_MODEL=1). Its design is
F100-CARRIER-DESIGN.md §5 in the owner's research records.

Nothing here is typed by hand. Every value is read from:
  * this repository: `releases/<version>.env` (pins) and the speech-model
    catalog `provision/plebian-os-provision.sh` enforces (the advertised set);
  * kilix-content at `PLEBIAN_OS_NATIVE_CONTENT_REF`: the `kilix.content.asset/v3`
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


def read_manifest(version: str) -> dict[str, str]:
    values = {}
    for line in (ROOT / "releases" / f"{version}.env").read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def advertised_models() -> list[tuple[str, bool]]:
    """(model, runnable) in the order the provisioner's catalog check enforces."""
    source = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
    start = source.index("validate_voice_model_catalog() {")
    block = source[start:source.index("\n}\n", start)]
    found = re.findall(r'\(\s*"([a-z0-9.-]+)", "[a-z]+", (True|False), \d+,', block)
    if not found:
        raise SystemExit("could not read the advertised speech-model catalog")
    return [(name, flag == "True") for name, flag in found]


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


def delivery_text(model: str, host: str, runnable: bool, voice_ref: str) -> str:
    # Every sentence here is a claim tests/test_model_compliance_carrier.py
    # checks (AC-8): no weights in the image or fetched by provisioning, the
    # download is digest-verified, and kilix-voice refuses the weights without
    # a covering licence receipt.
    lines = [
        f"mode: {DELIVERY_MODE}",
        "No model weights are present in this image, and provisioning downloads none.",
        f"{model} reaches a machine only when a user installs it; it is downloaded from",
        f"{host} and verified against the pinned digests before installation.",
        "No install route downloads it until a kilix-license receipt covers it:",
        "The model catalog shows the licence and records the receipt, and",
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
        "Plebian-OS does not distribute these model bytes.",
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
    pins = read_manifest(version)
    content_ref = pins["PLEBIAN_OS_NATIVE_CONTENT_REF"]
    license_ref = pins["KILIX_LICENSE_REF"]
    models = advertised_models()
    determinations = {}
    for item in args.determination:
        model, _, path = item.partition("=")
        determinations.setdefault(model, []).append(Path(path))
    files: dict[str, bytes] = {}

    with tempfile.TemporaryDirectory() as scratch:
        scratch = Path(scratch)
        extract(args.content_repo, content_ref, scratch / "content")
        extract(args.license_repo, license_ref, scratch / "license")
        license_catalog = load_module(scratch / "license" / "src", "kilix_license.catalog")
        content_model = load_module(scratch / "content" / "src", "kilix_content.model")
        catalog = json.loads((scratch / "content" / "src" / "kilix_content" / "catalog"
                              / "plebian.json").read_text())
        assets = [content_model.AssetSpec.from_mapping(raw) for raw in catalog["assets"]]
        records = license_catalog.load_determined_records(scratch / "license")
        texts = scratch / "license" / "src" / "kilix_license" / "data" / "texts"
        schema_bytes = (scratch / "content" / "contracts" / "kilix.content.asset-v3.schema.json").read_bytes()

        entries = {}
        for model, runnable in models:
            record = records.by_id(model)
            matches = [a for a in assets
                       if any(item.record_digest == record.digest for item in a.licenses)]
            if len(matches) != 1:
                raise SystemExit(f"{model}: expected one asset record bound to licence "
                                 f"record {record.digest}, found {len(matches)}")
            asset = matches[0]
            mapping = asset.to_mapping()
            source = mapping["source"]
            record_file = license_catalog.record_path(model, scratch / "license")
            digests = [record.text_sha256] + [
                component.exception_text_sha256 for component in record.components
                if getattr(component, "exception_text_sha256", None)]
            digests += [item.text_sha256 for item in record.advisories]
            digests += [item.text_sha256 for item in record.statements]
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
                "delivery": DELIVERY_MODE,
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
                model, entry["upstream_host"], runnable, pins["KILIX_VOICE_REF"]).encode()

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
