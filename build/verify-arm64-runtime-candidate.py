#!/usr/bin/env python3
"""Verify unselected ARM64 voice and upstream Kitty fallback bytes.

This checks software identity only. It cannot approve a model carrier, model
runability, installed OS, or a release. The selected AMD64 pins are untouched.
"""

import argparse
import hashlib
import json
import re
import struct
import tarfile
import zipfile
from pathlib import Path
from urllib.parse import urlsplit


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def exact_keys(value, keys, label):
    require(isinstance(value, dict) and set(value) == set(keys),
            f"{label} fields are missing or unexpected")


def artifact(value, keys, suffix, label):
    exact_keys(value, keys, label)
    url = urlsplit(value["url"])
    require(url.scheme == "https" and url.netloc and not url.username and
            not url.password and not url.query and not url.fragment and
            url.path.endswith(suffix), f"{label} URL is not the expected HTTPS artifact")
    require(isinstance(value["bytes"], int) and value["bytes"] > 0,
            f"{label} byte count is invalid")
    require(isinstance(value["sha256"], str) and
            re.fullmatch(r"[0-9a-f]{64}", value["sha256"]) is not None,
            f"{label} SHA256 is invalid")


def validate_metadata(candidate):
    exact_keys(candidate, ("schema", "release_id", "architecture", "selection",
                           "carrier_acceptance", "voice", "upstream_kitty_fallback",
                           "unchanged_authority", "model_runtime_review"), "candidate")
    require(candidate["schema"] == "plebian-os.arm64-runtime-candidate/v1" and
            candidate["release_id"] == "0.2.2" and
            candidate["architecture"] == "arm64" and
            candidate["selection"] == "unselected" and
            candidate["carrier_acceptance"] == "pending-independent-arm64-review",
            "candidate must remain unselected and unaccepted ARM64 data")
    voice = candidate["voice"]
    artifact(voice, ("version", "url", "bytes", "sha256", "wheel_tag",
                     "library_member", "library_bytes", "library_sha256", "elf_machine"),
             "-manylinux2014_aarch64.whl", "voice")
    require(voice["version"] == "0.3.45" and
            voice["wheel_tag"] == "py3-none-manylinux2014_aarch64" and
            voice["library_member"] == "vosk/libvosk.so" and
            voice["elf_machine"] == 183 and
            isinstance(voice["library_bytes"], int) and voice["library_bytes"] > 0 and
            re.fullmatch(r"[0-9a-f]{64}", voice["library_sha256"]) is not None,
            "voice architecture/member binding is missing or foreign")
    kitty = candidate["upstream_kitty_fallback"]
    artifact(kitty, ("version", "url", "bytes", "sha256", "bootstrap_executable",
                     "bootstrap_executable_sha256", "elf_machine", "role"),
             "-arm64.txz", "kitty")
    require(kitty["version"] == "0.48.2" and
            kitty["url"].endswith("/v0.48.2/kitty-0.48.2-arm64.txz") and
            kitty["bootstrap_executable"] == "bin/kitty" and
            kitty["elf_machine"] == 183 and
            kitty["role"] == "upstream-fallback-only; not the selected patched engine" and
            re.fullmatch(r"[0-9a-f]{64}", kitty["bootstrap_executable_sha256"]) is not None,
            "kitty fallback architecture/layout binding is missing or foreign")
    authority = candidate["unchanged_authority"]
    exact_keys(authority, ("model_catalog_ref", "license_ref", "voice_ref",
                           "model_download"), "authority")
    require(all(re.fullmatch(r"[0-9a-f]{40}", authority[k]) for k in
                ("model_catalog_ref", "license_ref", "voice_ref")) and
            authority["model_download"] == "first-use-only-with-existing-consent-and-receipt-gates",
            "existing source/consent authority is not bound")
    models = candidate["model_runtime_review"]
    require(isinstance(models, list) and len(models) == 6 and
            {m.get("model") for m in models if isinstance(m, dict)} ==
            {"small-en-us", "lgraph-en-us", "vibevoice-asr-bitnet",
             "whisper-small-en", "whistle", "kilix-diarization-cpu"},
            "ARM model review must cover every carrier model")
    for model in models:
        exact_keys(model, ("model", "provider", "arm64_runnable", "remaining"),
                   "model review")
        require(model["arm64_runnable"] is None and model["provider"] and
                model["remaining"], "unverified ARM model cannot claim runability")


def verify_file(path, meta, label):
    require(path.stat().st_size == meta["bytes"], f"{label} byte count mismatch")
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    require(h.hexdigest() == meta["sha256"], f"{label} SHA256 mismatch")


def check_elf(data, machine, label):
    require(len(data) >= 20 and data[:6] == b"\x7fELF\x02\x01" and
            struct.unpack_from("<H", data, 18)[0] == machine,
            f"{label} is not the selected little-endian ELF64 machine")


def verify_archives(candidate, wheel_path, kitty_path):
    voice = candidate["voice"]
    kitty = candidate["upstream_kitty_fallback"]
    verify_file(wheel_path, voice, "voice wheel")
    with zipfile.ZipFile(wheel_path) as archive:
        members = [x for x in archive.infolist() if x.filename == voice["library_member"]]
        require(len(members) == 1 and members[0].file_size == voice["library_bytes"],
                "wheel has no single exact library member")
        data = archive.read(members[0])
        require(digest(data) == voice["library_sha256"], "wheel library SHA256 mismatch")
        check_elf(data, voice["elf_machine"], "wheel library")
        tags = archive.read("vosk-0.3.45.dist-info/WHEEL").decode("utf-8")
        require(f"Tag: {voice['wheel_tag']}\n" in tags,
                "wheel tag does not name ARM64")
    verify_file(kitty_path, kitty, "kitty fallback")
    with tarfile.open(kitty_path, "r:xz") as archive:
        member = archive.getmember(kitty["bootstrap_executable"])
        require(member.isfile() and member.mode & 0o111 and member.size < 16 * 1024 * 1024,
                "kitty bootstrap executable is absent or not executable")
        data = archive.extractfile(member).read()
        require(digest(data) == kitty["bootstrap_executable_sha256"],
                "kitty bootstrap executable SHA256 mismatch")
        check_elf(data, kitty["elf_machine"], "kitty bootstrap executable")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--kitty-bundle", type=Path, required=True)
    args = parser.parse_args()
    candidate = json.loads(args.candidate.read_text())
    validate_metadata(candidate)
    verify_archives(candidate, args.wheel, args.kitty_bundle)
    print("unselected ARM64 runtime candidate: archive and architecture bindings verified")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, zipfile.BadZipFile, tarfile.TarError) as error:
        raise SystemExit(str(error)) from error
