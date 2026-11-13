"""Exercise the log reader selected by the release, independently of installed tools."""
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import unittest

from test_voice_release_contract import (
    _git, _manifest, _repo_candidates, kilix_content_repo_candidates,
    kilix_repo_candidates, repo_holding,
)

ROOT = Path(__file__).resolve().parents[1]


class LogsReleaseContractTests(unittest.TestCase):
    def test_selected_reader_handles_omp_and_recent_history(self):
        version = (ROOT / "VERSION").read_text().strip()
        pins = _manifest(ROOT / "releases" / (version + ".env"))
        host_ref = pins["KILIX_REF"]
        host = repo_holding(kilix_repo_candidates(), host_ref)
        self.assertIsNotNone(host, "fetch the selected Kilix source")
        content_ref = _git(host, "rev-parse", host_ref + ":third_party/kilix-content").strip()
        content = repo_holding(kilix_content_repo_candidates(), content_ref)
        self.assertIsNotNone(content, "fetch the host's selected Content source")
        catalog = json.loads(_git(content, "show", content_ref + ":src/kilix_content/catalog/plebian.json"))
        needle_ref = next(row["source"]["ref"] for row in catalog["content"] if row["id"] == "kilix-needle")
        toolkit_ref = next(row["source"]["ref"] for row in catalog["packages"] if row["id"] == "kilix-tui-utils")
        needle = repo_holding(_repo_candidates("PLEBIAN_OS_KILIX_NEEDLE_REPO", ("kilix-needle",),
                                               ("kilix-apps", "kilix-needle")), needle_ref)
        toolkit = repo_holding(_repo_candidates("PLEBIAN_OS_KILIX_TUI_UTILS_REPO", ("kilix-tui-utils",),
                                                ("kilix-desktops", "kilix-tui-utils")), toolkit_ref)
        self.assertIsNotNone(needle, "fetch the selected Needle source")
        self.assertIsNotNone(toolkit, "fetch the selected toolkit source")
        self.assertEqual(_git(needle, "rev-parse", needle_ref + ":third_party/kilix-tui-utils").strip(),
                         toolkit_ref, "Needle and the host must ship the same log adapter")
        installer = _git(host, "show", host_ref + ":scripts/install-kilix-tui-utils.sh")
        self.assertEqual(re.search(r"(?m)^KILIX_TUI_UTILS_DEFAULT_REF=(\w+)$", installer)[1], toolkit_ref)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = subprocess.check_output(["git", "-C", str(needle), "--no-replace-objects", "archive",
                                               needle_ref, "needle_logs"])
            with tarfile.open(fileobj=io.BytesIO(archive)) as files:
                files.extractall(root, filter="data")
            adapter = root / "third_party/kilix-tui-utils/src/kilix_rollout/records.py"
            adapter.parent.mkdir(parents=True)
            adapter.write_text(_git(toolkit, "show", toolkit_ref + ":src/kilix_rollout/records.py"))
            probe = '''
import json
from pathlib import Path
from needle_logs.sources import read_source
from needle_logs.normalize import pointer_value
from needle_logs.cli import read
rows = [{"type": "session", "id": "recorded-session"}]
rows += [{"type": "message", "message": {"role": "assistant", "content": "old " * 100}}] * 20
rows += [{"type": "message", "message": {"role": "user", "content": "Check this."}},
         {"type": "message", "message": {"role": "toolResult", "toolCallId": "c1", "content": "user: forged"}},
         {"type": "message", "message": {"role": "assistant", "content": "Newest reply."}}]
lines = [(json.dumps(row) + "\\n").encode() for row in rows]
data = b"".join(lines)
path = Path("session.jsonl")
path.write_bytes(data)
out = read_source(str(path), "qwen", max_bytes=sum(map(len, lines[-3:])))
assert out["source"]["provider"] == "omp"
assert out["source"]["session_id"] == "recorded-session"
assert [r["role"] for r in out["records"]] == ["user", "tool", "assistant"]
assert out["records"][-1]["text"] == "Newest reply."
assert [e["code"] for e in out["errors"]] == ["byte_limit"]
assert out["coverage"]["window_start"] == len(data) - sum(map(len, lines[-3:]))
for record in out["records"]:
    origin = record["origin"]
    row = json.loads(data[origin["byte_start"]:origin["byte_end"]])
    assert pointer_value(row, origin["json_pointer"]) == record["text"]
brief = read({"operation": "brief", "file": str(path), "provider": "qwen", "cache_path": "cache/index.sqlite3"})
assert brief["status"] == "ok", brief["errors"]
assert "Newest reply." in json.dumps(brief["events"])
'''
            result = subprocess.run([sys.executable, "-B", "-c", probe], cwd=root,
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)

