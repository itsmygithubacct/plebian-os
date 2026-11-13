"""Exercise the log reader selected by the release, independently of installed tools."""
import hashlib
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
    def test_selected_reader_preserves_full_history_paging_and_session_discovery(self):
        version = (ROOT / "VERSION").read_text().strip()
        pins = _manifest(ROOT / "releases" / (version + ".env"))
        host_ref = pins["KILIX_REF"]
        host = repo_holding(kilix_repo_candidates(), host_ref)
        self.assertIsNotNone(host, "fetch the selected Kilix source")
        content_ref = _git(host, "rev-parse", host_ref + ":third_party/kilix-content").strip()
        requirements = _manifest(ROOT / "releases" / (version + ".requirements"))
        self.assertEqual(pins["PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF"], content_ref)
        for key in ("PLEBIAN_OS_VOICE_CARRIER_CONTENT_REF", "PLEBIAN_OS_VOICE_CARRIER_SHA256"):
            self.assertEqual(requirements[key], pins[key], key)
        carrier = ROOT / pins["PLEBIAN_OS_VOICE_CARRIER_DIR"] / "CARRIER.json"
        self.assertEqual(hashlib.sha256(carrier.read_bytes()).hexdigest(),
                         pins["PLEBIAN_OS_VOICE_CARRIER_SHA256"])
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
            adapter.with_name("inventory.py").write_text(
                _git(toolkit, "show", toolkit_ref + ":src/kilix_rollout/inventory.py"))
            host_root = root / "host"
            for name in ("kilix", "VERSION", "config/agent_capabilities.py", "config/agent_actions.py",
                         "config/agent_control.py", "config/kilix_sdk/panes.py", "config/content_models.py",
                         "config/agent_skills.py", "config/tmux_control.py"):
                target = host_root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(_git(host, "show", host_ref + ":" + name))
            probe = '''
import importlib.util
import json
import os
from pathlib import Path
from needle_logs.sources import read_source
from needle_logs.normalize import pointer_value
from needle_logs.cli import read
from needle_logs.library import inventory_module
from needle_logs.library_cli import read as library_read
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
with path.open("ab") as stream:
    padding = (json.dumps({"type": "custom", "data": "x" * 1024 * 1024}) + "\\n").encode()
    for _ in range(34):
        stream.write(padding)
    stream.write((json.dumps({"type": "message", "message": {"role": "assistant", "content": "Full history marker"}}) + "\\n").encode())
indexed = library_read({"operation": "index", "file": str(path), "provider": "qwen", "cache_path": "cache/index.sqlite3"})
assert indexed["status"] == "ok", indexed
for term in ("Newest reply", "Full history marker"):
    found = library_read({"operation": "search", "query": term, "cached": True, "cache_path": "cache/index.sqlite3"})
    assert found["status"] == "ok", found
    assert found["rank"] == "bm25" and len(found["matches"]) == 1, found
    record = library_read({"operation": "show", "record_id": found["matches"][0]["record_id"], "cache_path": "cache/index.sqlite3"})
    origin = record["record"]["origin"]
    with path.open("rb") as source:
        source.seek(origin["byte_start"])
        row = json.loads(source.read(origin["byte_end"] - origin["byte_start"]))
    assert pointer_value(row, origin["json_pointer"]) == record["text"]
listing = library_read({"operation": "list", "cached": True, "cache_path": "cache/index.sqlite3"})
assert listing["sessions"][0]["coverage"]["window"] == "full", listing
assert listing["sessions"][0]["coverage"]["window_start"] == 0, listing
fork = Path("fork.jsonl")
fork.write_text("".join(json.dumps(row) + "\\n" for row in (
    {"type": "session_meta", "payload": {"id": "child", "forked_from_id": "parent"}},
    {"type": "session_meta", "payload": {"id": "parent"}},
    {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Inherited request"}]}})))
forked = library_read({"operation": "index", "file": str(fork), "provider": "codex", "cache_path": "cache/index.sqlite3"})
assert forked["status"] == "ok", forked
forks = library_read({"operation": "list", "provider": "codex", "cached": True, "cache_path": "cache/index.sqlite3"})
assert forks["sessions"][0]["session_id"] == "child", forks
transcripts = Path("transcripts")
for number, (folder, name) in enumerate((("", "live.log"), ("recent", "recent.log.zst"), ("archive", "older.log.zst"))):
    directory = transcripts / folder
    directory.mkdir(parents=True, exist_ok=True)
    recording = directory / name
    recording.touch()
    os.utime(recording, (number + 1, number + 1))
(transcripts / "recent.meta").write_text("cwd=/project\\ncmd=agent\\n")
tiers = inventory_module().raw_entries(transcripts)
assert [row["tier"] for row in tiers] == ["archived", "recent", "live"], tiers
assert tiers[1]["title"] == "project · agent", tiers

# A single large event must not block pagination or lose exact source text.
large = Path("large.jsonl")
messages = [("é雪🐈" + chr(34) + chr(92) + chr(10)) * 9000,
            "following marker", "latest " + "large " * 10000]
large.write_text("".join(json.dumps(row) + "\\n" for row in (
    [{"type": "session", "id": "large-session"}] +
    [{"type": "message", "message": {"role": "user", "content": text}} for text in messages])))
arguments = {"file": str(large), "provider": "omp", "cache_path": "cache/large.sqlite3", "limit": 1}
def bounded(result):
    assert result["status"] == "ok", result.get("errors")
    assert len(json.dumps(result, ensure_ascii=False).encode()) <= 32768
    return result
cursor, ids = None, []
for text in messages:
    page = bounded(read(dict(arguments, operation="events", **({"since_cursor": cursor} if cursor else {}))))
    assert len(page["events"]) == 1
    event = page["events"][0]
    ids.append(event["event_id"])
    evidence = event["evidence"][0]
    if "quote" in evidence:
        assert evidence["quote"] == text[evidence["start"]:evidence["end"]]
    else:
        assert evidence["quote_omitted"]
        assert evidence["excerpt"] == text[evidence["start"]:evidence["excerpt_end"]]
    parts, source_cursor = [], None
    for _ in range(100):
        source = bounded(read({"operation": "source", "event_id": event["event_id"],
                               "cache_path": arguments["cache_path"],
                               **({"since_cursor": source_cursor} if source_cursor else {})}))
        for record in source["records"]:
            if "text" in record:
                assert not parts
                parts.append(record["text"])
            else:
                assert record["chunk_start"] == sum(map(len, parts))
                parts.append(record["chunk"])
                assert record["chunk_end"] == sum(map(len, parts))
        if not source.get("has_more"):
            break
        assert source["next_cursor"] and source["next_cursor"] != source_cursor
        source_cursor = source["next_cursor"]
    else:
        raise AssertionError("source cursor did not terminate")
    assert "".join(parts) == text
    assert page["next_cursor"] != cursor
    cursor = page["next_cursor"]
assert len(set(ids)) == len(messages) and not page["has_more"]
latest = bounded(read(dict(arguments, operation="brief")))
assert latest["events"][0]["event_id"] == ids[-1]

# Nested OMP children are distinct, named and readable through the Qwen alias.
omp = Path("omp")
for number, (relative, agent) in enumerate((("project/session/Child.jsonl", "mapper"),
                                           ("project/session/Child/Grand.jsonl", "reviewer"))):
    child = omp / relative
    child.parent.mkdir(parents=True, exist_ok=True)
    child.write_text("".join(json.dumps(row) + "\\n" for row in (
        {"type": "session", "id": "child-" + str(number)},
        {"type": "session_init", "agent": agent, "task": "Inspect the fixture", "systemPrompt": "Fixture"},
        {"type": "message", "message": {"role": "user", "content": "Inspect the fixture"}})))
    os.utime(child, (number + 10, number + 10))
    bounded(read({"operation": "events", "file": str(child), "provider": "qwen",
                  "cache_path": "cache/children.sqlite3"}))
discovered = inventory_module().discover("qwen", locations={"omp": [omp]})
assert discovered["complete"] and not discovered["errors"], discovered
assert [row["session_id"] for row in discovered["sessions"]] == ["child-1", "child-0"]
assert [row["title"] for row in discovered["sessions"]] == ["Grand · reviewer", "Child · mapper"]
assert not inventory_module().discover("omp", locations={"omp": [omp]}, max_entries=1)["complete"]

# Inspect the selected real launcher and action metadata without executing them.
host = Path("host").resolve()
spec = importlib.util.spec_from_file_location("selected_capabilities", host / "config/agent_capabilities.py")
capabilities = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capabilities)
component = capabilities._component(host)
assert component["status"] == "observed", component
assert component["version"] == (host / "VERSION").read_text().strip()
assert set(component["commands_present"]) == set(capabilities.COMMAND_FILES), component
assert component["action_backend"]["status"] == "observed", component
assert {"agent.launch", "agent.deliver", "pane.open", "operation.status"} <= set(
    component["action_backend"]["operations"])
'''
            result = subprocess.run([sys.executable, "-B", "-c", probe], cwd=root,
                                    capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
