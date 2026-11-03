#!/usr/bin/env python3
"""Check an unselected model-consumer closure without installing or running it.

All paths are relative to an explicitly supplied evidence root. The manifest is
an integrity contract, not a signature, license receipt issuer, or release vote.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess


class Invalid(ValueError):
    pass


def require(value, message):
    if not value:
        raise Invalid(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)


def exact(value, size, label):
    require(isinstance(value, str) and re.fullmatch(f"[0-9a-f]{{{size}}}", value),
            f"invalid {label}")


def local(root, value):
    require(isinstance(value, str) and value and "\\" not in value,
            "path must be a nonempty POSIX relative path")
    parts = PurePosixPath(value).parts
    require(not value.startswith("/") and ".." not in parts,
            f"path escapes evidence root: {value}")
    path = root.joinpath(*parts)
    require(path.resolve().is_relative_to(root.resolve()),
            f"symlink escapes evidence root: {value}")
    return path


def git(path, *args):
    result = subprocess.run(["git", "-C", str(path), *args], check=False,
                            capture_output=True, text=True, timeout=60)
    require(result.returncode == 0, f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def indexed(rows, label):
    require(isinstance(rows, list) and rows, f"{label} must be a nonempty list")
    result = {}
    for row in rows:
        require(isinstance(row, dict), f"invalid {label} record")
        key = row.get("id")
        require(isinstance(key, str) and re.fullmatch(r"[A-Za-z0-9_.-]+", key),
                f"invalid {label} id")
        require(key not in result, f"duplicate {label} id: {key}")
        result[key] = row
    return result


def verify(manifest, root):
    require(manifest.get("schema") == "plebian-os.model-integration/v1", "unknown schema")
    require(manifest.get("selection") == "unselected", "proposal must remain unselected")
    require(manifest.get("release_accepted") is False, "identity cannot claim release acceptance")
    files = indexed(manifest["files"], "file")
    sources = indexed(manifest["sources"], "source")
    profiles = indexed(manifest["profiles"], "profile")
    gaps = []
    for key, entry in files.items():
        exact(entry["sha256"], 64, f"{key} SHA256")
        require(type(entry["bytes"]) is int and entry["bytes"] >= 0, f"{key}: invalid size")
        path = local(root, entry["path"])
        require(path.is_file() and not path.is_symlink(), f"{key}: missing regular file")
        with path.open("rb") as stream:
            require(path.stat().st_size == entry["bytes"] and
                    hashlib.file_digest(stream, "sha256").hexdigest() == entry["sha256"],
                    f"{key}: file identity mismatch")
    source_directories = set()
    for key, entry in sources.items():
        exact(entry["head"], 40, f"{key} commit")
        exact(entry["tree"], 40, f"{key} tree")
        path = local(root, entry["path"])
        require(path.resolve() not in source_directories, f"{key}: duplicate source directory")
        source_directories.add(path.resolve())
        require(git(path, "rev-parse", "HEAD") == entry["head"], f"{key}: HEAD mismatch")
        require(git(path, "rev-parse", "HEAD^{tree}") == entry["tree"], f"{key}: tree mismatch")
        common = Path(git(path, "rev-parse", "--path-format=absolute", "--git-common-dir"))
        require(common.resolve() == (path / ".git").resolve() and (path / ".git").is_dir()
                and not (path / ".git").is_symlink() and common.resolve().is_relative_to(root.resolve()),
                f"{key}: source must own its Git directory")
        require(not (common / "objects/info/alternates").exists(), f"{key}: object alternates")
        require(git(path, "rev-parse", "--is-shallow-repository") == "false", f"{key}: shallow history")
        git(path, "fsck", "--connectivity-only", "--no-dangling")
        require(not git(path, "status", "--porcelain", "--untracked-files=all",
                        "--ignore-submodules=none"), f"{key}: dirty source")
        links = {}
        for line in git(path, "ls-tree", "-r", "HEAD").splitlines():
            metadata, name = line.split("\t", 1)
            mode, kind, sha = metadata.split()
            if mode == "160000":
                links[name] = sha
        declared = entry["gitlinks"]
        require(isinstance(declared, dict) and declared == links, f"{key}: gitlink inventory mismatch")
        for name, sha in links.items():
            if not any(s["head"] == sha and
                       local(root, s["path"]).resolve() == (path / name).resolve()
                       for s in sources.values()):
                gaps.append(f"{key}: unverified submodule {name}@{sha}")
    for key, entry in profiles.items():
        for field, inventory in (("sources", sources), ("files", files)):
            require(isinstance(entry[field], list) and entry[field] and
                    all(x in inventory for x in entry[field]), f"{key}: unresolved {field}")
        for field in ("abi", "cpu", "install", "relocation", "rollback"):
            require(isinstance(entry[field], str) and entry[field].strip(), f"{key}: missing {field}")
        # Status assertions alone are insufficient: a complete public handoff
        # must bind the exact source heads and its independently frozen verdict.
        review = entry["review"]
        require(review["state"] in ("pending", "failed", "complete"), f"{key}: invalid review state")
        if review["state"] != "complete":
            gaps.append(f"{key}: independent review {review['state']}")
        else:
            require(review["file"] in files, f"{key}: missing review binding")
            receipt = read_json(local(root, files[review["file"]]["path"]))
            require(receipt["complete"] is True and receipt["source_heads"] ==
                    {s: sources[s]["head"] for s in entry["sources"]}, f"{key}: stale review receipt")
            require(receipt["original_verdict"] in ("pass", "fail"), f"{key}: missing original verdict")
            if receipt["original_verdict"] == "fail":
                require(receipt.get("repair_independent_review") == "pass",
                        f"{key}: failed original review needs independent repair review")
        for field, allowed, ready in (
            ("license", ("existing-binding", "missing", "pending"), "existing-binding"),
            ("packaging", ("verified", "pending"), "verified"),
            ("quality", ("qualified", "pending", "no-go"), "qualified"),
            ("admission", ("admitted", "pending", "no-go"), "admitted"),
        ):
            require(entry[field] in allowed, f"{key}: invalid {field}")
            if entry[field] != ready:
                gaps.append(f"{key}: {field} {entry[field]}")
        binding = entry["license_evidence"]
        require(isinstance(binding, list) and all(x in files for x in binding),
                f"{key}: unresolved license evidence")
        require(entry["license"] != "existing-binding" or binding,
                f"{key}: existing license needs evidence")
    return {"identity": "verified", "files": len(files), "sources": len(sources),
            "profiles": len(profiles), "gaps": sorted(set(gaps)),
            "selection": "unselected", "release_accepted": False,
            "scope": "local bytes and declared public evidence; no execution or qualification"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--require-complete", action="store_true",
                        help="also refuse every recorded integration/qualification gap")
    args = parser.parse_args()
    result = verify(read_json(args.manifest), args.root.resolve())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if args.require_complete and result["gaps"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        raise SystemExit(f"model integration refused: {error}") from error
