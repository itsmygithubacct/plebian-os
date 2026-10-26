#!/usr/bin/env python3
"""Verify the unselected ARM64 0.2.2 closure candidate.

The candidate records which ARM64 values would replace architecture-bound
AMD64 release values, where each value comes from, and which inputs and
acceptance gates are still missing. It never selects a release: the companion
manifest it can render is written outside the tree for review and fixtures,
and admission is refused while any input or gate is open.

  verify-arm64-closure-candidate.py verify
  verify-arm64-closure-candidate.py render --out DIR
  verify-arm64-closure-candidate.py admission
  verify-arm64-closure-candidate.py bytes FILE...
"""

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent.parent
CANDIDATE = ROOT / "releases/0.2.2-arm64-closure-candidate.json"
AMD64_ENV = "releases/0.2.2.env"
AMD64_REQUIREMENTS = "releases/0.2.2.requirements"
SHA256 = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")
FOREIGN = re.compile(r"amd64|x86_64|x86-64", re.IGNORECASE)

# Keys whose selected AMD64 value names AMD64 bytes or AMD64 acceptance. Each
# must be replaced, independently confirmed for ARM64, or left unresolved.
ARCHITECTURE_BOUND = (
    "PLEBIAN_OS_NETINST_URL", "PLEBIAN_OS_NETINST_SHA256",
    "PLEBIAN_OS_NETINST_MAX_BYTES",
    "PLEBIAN_OS_QT_RUNTIME_URL", "PLEBIAN_OS_QT_RUNTIME_SHA256",
    "PLEBIAN_OS_QT_RUNTIME_BYTES",
    "PLEBIAN_OS_MPV_URL", "PLEBIAN_OS_MPV_SHA256", "PLEBIAN_OS_MPV_BYTES",
    "PLEBIAN_OS_NATIVE_DEB_URL", "PLEBIAN_OS_NATIVE_DEB_SHA256",
    "PLEBIAN_OS_NATIVE_DEB_BYTES", "PLEBIAN_OS_NATIVE_SOURCE_REF",
    "KILIX_VOICE_LIB_URL", "KILIX_VOICE_LIB_SHA256",
    "KILIX_PREBUILT_VERSION", "KILIX_PREBUILT_SHA256",
    "PLEBIAN_OS_VOICE_CARRIER_DIR", "PLEBIAN_OS_VOICE_CARRIER_SHA256",
    "PLEBIAN_OS_VOICE_CARRIER_RECEIPT_SHA256",
    "PLEBIAN_OS_INSTALL_WAYDROID", "PLEBIAN_OS_WAYDROID_CLOSURE_SHA256",
)
GATES = (
    "arm-closure-review", "arm-installer-media", "arm-engine-bootstrap",
    "arm-voice-carrier", "arm-waydroid-closure", "arm-android-runtime",
    "arm-installed-acceptance", "arm-upgrade-rollback", "arm-physical",
    "arm-tool-admission",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def exact_keys(value, keys, label, optional=()):
    require(isinstance(value, dict) and set(keys) <= set(value) <= set(keys) | set(optional),
            f"{label} fields are missing or unexpected")


def file_digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def https_url(value, label):
    url = urlsplit(value if isinstance(value, str) else "")
    require(url.scheme == "https" and url.netloc and not url.username and
            not url.password and not url.query and not url.fragment and
            url.path not in ("", "/"), f"{label} is not a plain HTTPS URL")


def read_env(path):
    """Strict KEY=VALUE reader with the release loader's rules."""
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        require("=" in line, f"{path.name}: invalid line")
        key, value = line.split("=", 1)
        require(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) is not None,
                f"{path.name}: invalid key {key}")
        require(key not in values, f"{path.name}: duplicate key {key}")
        if len(value) >= 2 and value[0] == value[-1] == '"':
            value = value[1:-1]
        values[key] = value
    return values


def runtime_module():
    spec = importlib.util.spec_from_file_location(
        "arm64_runtime_candidate", ROOT / "build/verify-arm64-runtime-candidate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def artifact(value, label):
    exact_keys(value, ("url", "bytes", "sha256"), label)
    https_url(value["url"], f"{label} URL")
    require(isinstance(value["bytes"], int) and not isinstance(value["bytes"], bool)
            and value["bytes"] > 0, f"{label} byte count is invalid")
    require(isinstance(value["sha256"], str) and SHA256.fullmatch(value["sha256"]),
            f"{label} SHA256 is invalid")
    require(not FOREIGN.search(value["url"]), f"{label} URL names a foreign architecture")


def classification(candidate):
    """Map every classified key to (kind, component)."""
    seen = {}
    for entry in candidate["selected"]:
        for kind in ("values", "confirmed"):
            for key in entry.get(kind, {}):
                require(key not in seen, f"{key} is classified twice")
                seen[key] = (kind, entry["component"])
    for entry in candidate["unresolved"]:
        for key in entry["keys"]:
            require(key not in seen, f"{key} is classified twice")
            seen[key] = ("unresolved", entry["component"])
    for key in candidate["neutral_requirements"]:
        require(key not in seen, f"{key} is classified twice")
        seen[key] = ("neutral", None)
    return seen


def validate(candidate, root=ROOT):
    exact_keys(candidate, ("schema", "release_id", "architecture", "selection",
                           "admission", "base", "companion", "preserved_amd64",
                           "runtime_candidate", "selected", "neutral_requirements",
                           "unresolved", "android", "gates"), "candidate")
    require(candidate["schema"] == "plebian-os.arm64-closure-candidate/v1" and
            candidate["release_id"] == "0.2.2" and
            candidate["architecture"] == "arm64",
            "candidate is not the ARM64 0.2.2 closure")
    require(candidate["selection"] == "unselected" and candidate["admission"] == "closed",
            "candidate must remain unselected with admission closed")
    base = candidate["base"]
    exact_keys(base, ("os", "host"), "base")
    require(all(COMMIT.fullmatch(base[k]) for k in base), "base commits are invalid")

    # The companion name is what the selector reads. It must not exist while
    # the candidate is unselected, whatever the selector would conclude.
    companion = candidate["companion"]
    exact_keys(companion, ("manifest", "requirements"), "companion")
    require(companion == {"manifest": "releases/0.2.2-arm64.env",
                          "requirements": "releases/0.2.2-arm64.requirements"},
            "companion paths are not the selector's ARM64 names")
    for path in companion.values():
        require(not (root / path).exists() and not (root / path).is_symlink(),
                f"{path} exists although the ARM64 closure is unselected")

    preserved = candidate["preserved_amd64"]
    require(isinstance(preserved, dict) and
            {AMD64_ENV, AMD64_REQUIREMENTS} <= set(preserved), "AMD64 pins are not preserved")
    for path, expected in preserved.items():
        target = root / path
        require(target.is_file() and not target.is_symlink() and
                file_digest(target) == expected, f"selected AMD64 file changed: {path}")

    runtime = candidate["runtime_candidate"]
    exact_keys(runtime, ("path", "sha256"), "runtime candidate")
    runtime_path = root / runtime["path"]
    require(runtime_path.is_file() and file_digest(runtime_path) == runtime["sha256"],
            "reviewed runtime candidate changed")
    runtime_module().validate_metadata(json.loads(runtime_path.read_text()))

    amd64 = read_env(root / AMD64_ENV)
    requirements = read_env(root / AMD64_REQUIREMENTS)
    require(isinstance(candidate["selected"], list) and candidate["selected"],
            "no ARM64 inputs are selected")
    for entry in candidate["selected"]:
        exact_keys(entry, ("component", "values", "artifact", "authority",
                           "bytes_verified", "limits"), "selected input", ("confirmed",))
        label = entry["component"]
        require(isinstance(entry["values"], dict) and entry["values"],
                f"{label} replaces nothing")
        artifact(entry["artifact"], label)
        require(isinstance(entry["bytes_verified"], bool), f"{label} byte state is invalid")
        require(isinstance(entry["authority"], str) and entry["authority"] and
                isinstance(entry["limits"], str) and entry["limits"],
                f"{label} has no authority or limits")
        for key, value in entry["values"].items():
            require(key in amd64, f"{label}: {key} is not a release key")
            require(isinstance(value, str) and value and value != amd64[key],
                    f"{label}: {key} keeps the AMD64 value")
            require(not FOREIGN.search(value), f"{label}: {key} names a foreign architecture")
        for key, value in entry.get("confirmed", {}).items():
            require(key in amd64 and value == amd64[key],
                    f"{label}: confirmed {key} differs from the selected release value")
        # A URL/SHA/BYTES triple must be the artifact the record proves.
        values = {**entry.get("confirmed", {}), **entry["values"]}
        sha = [v for k, v in values.items() if k.endswith("SHA256")]
        url = [v for k, v in values.items() if k.endswith("_URL")]
        size = [v for k, v in values.items() if k.endswith(("_BYTES", "_MAX_BYTES"))]
        require(sha == [entry["artifact"]["sha256"]], f"{label}: digest is not its artifact")
        require(url in ([], [entry["artifact"]["url"]]), f"{label}: URL is not its artifact")
        require(size in ([], [str(entry["artifact"]["bytes"])]),
                f"{label}: size is not its artifact")

    neutral = candidate["neutral_requirements"]
    require(isinstance(neutral, dict) and all(
        isinstance(v, str) and v for v in neutral.values()), "neutral reasons are missing")
    for key in neutral:
        require(key in requirements, f"neutral {key} is not a release requirement")
    require(isinstance(candidate["unresolved"], list), "unresolved inputs are invalid")
    for entry in candidate["unresolved"]:
        exact_keys(entry, ("component", "keys", "reason", "required"), "unresolved input")
        require(entry["keys"] and all(k in amd64 for k in entry["keys"]) and
                entry["reason"] and entry["required"],
                f"{entry.get('component')} is not a concrete missing input")

    classified = classification(candidate)
    for key in ARCHITECTURE_BOUND:
        require(classified.get(key, ("neutral",))[0] != "neutral",
                f"architecture-bound {key} is not classified")
    for key in requirements:
        require(key in classified, f"release requirement {key} is not classified")
    for key, value in amd64.items():
        if FOREIGN.search(value):
            require(classified.get(key, ("neutral",))[0] in ("values", "unresolved"),
                    f"{key} carries an AMD64 value but is not replaced")

    validate_android(candidate["android"])
    validate_gates(candidate["gates"])
    return amd64, requirements


def validate_android(android):
    exact_keys(android, ("selected", "system_image", "vendor_image", "image_selection",
                         "packages", "package_authority", "binder",
                         "runtime_prerequisites"), "android")
    require(android["selected"] is False, "Android inputs cannot be selected here")
    for name, flavour in (("system_image", "VANILLA"), ("vendor_image", "MAINLINE")):
        image = android[name]
        exact_keys(image, ("channel", "filename", "url", "bytes", "sha256",
                           "bytes_verified"), name)
        artifact({k: image[k] for k in ("url", "bytes", "sha256")}, name)
        https_url(image["channel"], f"{name} channel")
        require("waydroid_arm64" in image["channel"] and
                image["filename"].endswith(f"-{flavour}-waydroid_arm64-"
                                           f"{name.split('_')[0]}.zip") and
                f"/{image['filename']}/" in image["url"],
                f"{name} is not the ARM64 {flavour} image")
        require(image["bytes_verified"] is False,
                f"{name} bytes cannot be claimed without a recorded download")
    packages = android["packages"]
    require({p.get("package") for p in packages} ==
            {"waydroid", "libglibutil", "libgbinder", "python3-gbinder", "weston"},
            "Android package set is incomplete")
    for package in packages:
        exact_keys(package, ("package", "version", "architecture", "url", "bytes",
                             "sha256", "bytes_verified"), "Android package")
        artifact({k: package[k] for k in ("url", "bytes", "sha256")}, package["package"])
        architecture = package["architecture"]
        require(architecture in ("arm64", "all") and re.search(
                    rf"_{architecture}(_{package['sha256'][:12]})?\.deb$", package["url"]),
                f"{package['package']} is not an ARM64 or architecture-independent package")
    binder = android["binder"]
    exact_keys(binder, ("module", "devices", "debian_arm64_kernel", "kernel_requirements"),
               "binder")
    require(binder["module"] == "binder_linux" and
            binder["devices"] == "binder,hwbinder,vndbinder",
            "Binder requirements differ from the setup helper")
    require(isinstance(android["runtime_prerequisites"], list) and
            android["runtime_prerequisites"], "Android runtime prerequisites are missing")


def validate_gates(gates):
    require(isinstance(gates, list) and [g.get("id") for g in gates] == list(GATES),
            "ARM64 acceptance gates are missing or reordered")
    for gate in gates:
        exact_keys(gate, ("id", "title", "status", "evidence"), "gate")
        require(gate["status"] in ("open", "passed") and gate["title"],
                f"{gate['id']} status is invalid")
        if gate["status"] == "open":
            require(gate["evidence"] is None, f"open {gate['id']} carries evidence")
        else:
            exact_keys(gate["evidence"], ("path", "sha256"), f"{gate['id']} evidence")


def admission_blockers(candidate, root=ROOT):
    """Everything that keeps the ARM64 closure out of a release."""
    blockers = [f"unresolved {e['component']}: {', '.join(e['keys'])}"
                for e in candidate["unresolved"]]
    for entry in candidate["selected"]:
        if not entry["bytes_verified"]:
            blockers.append(f"unverified bytes: {entry['component']}")
    for name in ("system_image", "vendor_image"):
        if not candidate["android"][name]["bytes_verified"]:
            blockers.append(f"unverified bytes: Android {name}")
    for gate in candidate["gates"]:
        if gate["status"] != "passed":
            blockers.append(f"open gate: {gate['id']}")
            continue
        evidence = gate["evidence"]
        path = (root / evidence["path"]).resolve()
        if (not path.is_relative_to(root.resolve()) or not path.is_file() or
                file_digest(path) != evidence["sha256"]):
            blockers.append(f"gate {gate['id']} evidence is absent or altered")
    return blockers


def render(candidate, amd64, requirements):
    """Companion manifest and requirements text, without the unresolved keys."""
    values = {}
    for entry in candidate["selected"]:
        values.update(entry.get("confirmed", {}))
        values.update(entry["values"])
    missing = [k for e in candidate["unresolved"] for k in e["keys"]]
    header = [
        "# Plebian-OS 0.2.2 ARM64 companion: UNSELECTED CANDIDATE.",
        "# Rendered by build/verify-arm64-closure-candidate.py for review and fixtures.",
        "# It is not an admitted release; the selector, provisioner and updater refuse it.",
        "# Unresolved keys are omitted: " + " ".join(missing),
    ]
    env = header + [f"{k}={values.get(k, v)}" for k, v in amd64.items() if k not in missing]
    req = header + [f"{k}={values.get(k, v)}" for k, v in requirements.items()
                    if k not in missing]
    for line in env[len(header):] + req[len(header):]:
        require(not FOREIGN.search(line.split("=", 1)[1]),
                f"rendered {line.split('=', 1)[0]} names a foreign architecture")
    return "\n".join(env) + "\n", "\n".join(req) + "\n"


def match_bytes(candidate, paths):
    records = {e["artifact"]["sha256"]: (e["component"], e["artifact"]["bytes"])
               for e in candidate["selected"]}
    for name in ("system_image", "vendor_image"):
        image = candidate["android"][name]
        records[image["sha256"]] = (f"android {name}", image["bytes"])
    for package in candidate["android"]["packages"]:
        records[package["sha256"]] = (f"android {package['package']}", package["bytes"])
    results = []
    for path in paths:
        digest = file_digest(path)
        label, size = records.get(digest, (None, None))
        results.append((path, label, label is not None and path.stat().st_size == size))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--candidate", type=Path, default=CANDIDATE)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("verify")
    out = commands.add_parser("render")
    out.add_argument("--out", type=Path, required=True)
    commands.add_parser("admission")
    data = commands.add_parser("bytes")
    data.add_argument("files", type=Path, nargs="+")
    args = parser.parse_args()
    candidate = json.loads(args.candidate.read_text())
    amd64, requirements = validate(candidate)
    if args.command == "verify":
        print("unselected ARM64 0.2.2 closure candidate verified; AMD64 pins unchanged")
    elif args.command == "render":
        out_dir = args.out.resolve()
        require(not out_dir.is_relative_to(ROOT.resolve()),
                "render outside the source tree; the companion name is selector input")
        env, req = render(candidate, amd64, requirements)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "0.2.2-arm64.env").write_text(env)
        (out_dir / "0.2.2-arm64.requirements").write_text(req)
        print(f"rendered unselected ARM64 companion into {out_dir}")
    elif args.command == "admission":
        blockers = admission_blockers(candidate)
        for blocker in blockers:
            print(blocker)
        if blockers:
            print(f"ARM64 0.2.2 admission refused: {len(blockers)} blockers", file=sys.stderr)
            return 3
        print("every recorded ARM64 input and gate has evidence; admission still requires review")
    else:
        failed = 0
        for path, label, ok in match_bytes(candidate, args.files):
            print(f"{'match' if ok else 'NO MATCH'}\t{label or '-'}\t{path}")
            failed += not ok
        return 1 if failed else 0
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise SystemExit(str(error)) from error
