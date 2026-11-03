#!/usr/bin/env python3
"""Check an unselected model-consumer closure without installing or running it.

All paths are relative to an explicitly supplied evidence root. The manifest is
an integrity contract, not a signature, license receipt issuer, or release vote.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
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
    # Status must not refresh/write the caller's index during a read-only audit.
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_NO_REPLACE_OBJECTS="1")
    result = subprocess.run(["git", "-c", "core.fsmonitor=false", "-C", str(path), *args], check=False,
                            capture_output=True, text=True, timeout=60, env=env)
    require(result.returncode == 0, f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def worktree_entries(path, key):
    """Compare raw worktree bytes/modes with HEAD, independent of Git stat caches.

    Never invoke clean filters or filesystem-monitor helpers. Canonicalized or
    transformed checkouts are not exact source-byte identities for this audit.
    """
    links = {}
    for record in git(path, "ls-tree", "-r", "-z", "HEAD").split("\0"):
        if not record:
            continue
        metadata, name = record.split("\t", 1)
        mode, kind, expected = metadata.split()
        if mode == "160000":
            links[name] = expected
            continue
        item = path / name
        require(item.parent.resolve().is_relative_to(path.resolve()),
                f"{key}: tracked parent escapes source")
        info = item.lstat()
        digest = hashlib.sha1()
        if mode == "120000":
            require(stat.S_ISLNK(info.st_mode), f"{key}: dirty source (symlink type)")
            target = os.fsencode(os.readlink(item))
            digest.update(f"blob {len(target)}\0".encode())
            digest.update(target)
        else:
            require(mode in ("100644", "100755") and stat.S_ISREG(info.st_mode),
                    f"{key}: dirty source (file type)")
            require(bool(info.st_mode & stat.S_IXUSR) == (mode == "100755"),
                    f"{key}: dirty source (executable mode)")
            digest.update(f"blob {info.st_size}\0".encode())
            with item.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        require(digest.hexdigest() == expected, f"{key}: dirty source (raw blob identity)")
    return links


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
    require(isinstance(manifest, dict), "manifest must be an object")
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
        require(Path(git(path, "rev-parse", "--show-toplevel")).resolve() == path.resolve(),
                f"{key}: declared source is not the Git worktree")
        require(git(path, "rev-parse", "HEAD") == entry["head"], f"{key}: HEAD mismatch")
        require(git(path, "rev-parse", "HEAD^{tree}") == entry["tree"], f"{key}: tree mismatch")
        common = Path(git(path, "rev-parse", "--path-format=absolute", "--git-common-dir"))
        require(common.resolve() == (path / ".git").resolve() and (path / ".git").is_dir()
                and not (path / ".git").is_symlink() and common.resolve().is_relative_to(root.resolve()),
                f"{key}: source must own its Git directory")
        require(not (common / "objects/info/alternates").exists(), f"{key}: object alternates")
        require(git(path, "rev-parse", "--is-shallow-repository") == "false", f"{key}: shallow history")
        git(path, "fsck", "--connectivity-only", "--no-dangling")
        # Git status intentionally trusts these index flags and may hide changed
        # tracked bytes. A complete source audit cannot use that shortcut.
        flags = git(path, "ls-files", "-v", "-z").split("\0")
        require(all(not row or (row[0] != "S" and not row[0].islower()) for row in flags),
                f"{key}: assume-unchanged or skip-worktree index entries")
        links = worktree_entries(path, key)
        require(not git(path, "diff-index", "--cached", "--no-ext-diff", "--no-textconv",
                        "--ignore-submodules=none", "--name-only", "HEAD", "--"),
                f"{key}: dirty source (index)")
        require(not git(path, "ls-files", "--others", "--exclude-standard", "-z"),
                f"{key}: dirty source (untracked files)")
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
