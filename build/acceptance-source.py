#!/usr/bin/env python3
"""Run bounded install/update source controls; this never qualifies an ISO or VM."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SUITES = (
    "test_provision_transaction",
    "test_interrupted_update",
    "test_native_transaction",
    "test_closure_selection",
    "test_f109_release_hop_acceptance",
    "test_build_vm_image",
    "test_release_versioning",
)


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path,
                        help="new evidence directory outside the source checkout")
    parser.add_argument("--timeout", type=int, default=300,
                        help="maximum seconds per suite (default: 300)")
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error("timeout must be positive")
    report = args.report.resolve()
    if report.is_relative_to(ROOT):
        parser.error("evidence must be outside the source checkout")
    if git("status", "--porcelain", "--untracked-files=normal"):
        parser.error("a clean source checkout is required")
    report.mkdir(mode=0o700, parents=True, exist_ok=False)
    head = git("rev-parse", "HEAD")
    result = {
        "schema": "plebian-os.source-acceptance/v1",
        "status": "running",
        "source_head": head,
        "source_tree": git("rev-parse", "HEAD^{tree}"),
        "artifact_acceptance": False,
        "limitations": [
            "Source controls only; no firmware installation or adjacent release hop.",
            "Native transaction tests use a synthetic package backend.",
            "Final frozen closure and exact artifact acceptance remain separate gates.",
        ],
        "commands": [],
    }
    def save():
        temporary = report / "report.json.tmp"
        temporary.write_text(json.dumps(result, indent=2) + "\n")
        temporary.replace(report / "report.json")
    save()
    env = os.environ.copy()
    env.update(PYTHONPATH=str(ROOT / "tests"), PYTHONDONTWRITEBYTECODE="1",
               GIT_AUTHOR_NAME="itsmygithubacct",
               GIT_AUTHOR_EMAIL="itsmygithubacct@users.noreply.github.com",
               GIT_COMMITTER_NAME="itsmygithubacct",
               GIT_COMMITTER_EMAIL="itsmygithubacct@users.noreply.github.com")
    for suite in SUITES:
        command = [sys.executable, "-m", "unittest", suite, "-v"]
        log = report / (suite + ".log")
        started = time.monotonic()
        timed_out = False
        with log.open("xb") as output:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=output,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = process.wait(timeout=args.timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
                code = 124
        text = log.read_text(errors="replace")
        count = re.search(r"^Ran (\d+) tests? in ", text, re.MULTILINE)
        tests = int(count[1]) if count else 0
        skipped = re.search(r"^(?:OK|FAILED) \(.*skipped=(\d+)", text, re.MULTILINE)
        result["commands"].append({
            "argv": command, "exit": code, "timed_out": timed_out,
            "tests": tests, "skipped": int(skipped[1]) if skipped else 0,
            "seconds": round(time.monotonic() - started, 3),
            "log": log.name, "sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
        })
        save()
        print(f"{suite}: exit={code}, tests={tests}", flush=True)
    result["source_unchanged"] = (git("rev-parse", "HEAD") == head and not
                                   git("status", "--porcelain", "--untracked-files=normal"))
    passed = result["source_unchanged"] and all(
        row["exit"] == 0 and row["tests"] > 0 for row in result["commands"])
    result["status"] = "passed-source-controls" if passed else "failed-source-controls"
    save()
    files = sorted(report.iterdir())
    (report / "SHA256SUMS").write_text("".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in files))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
