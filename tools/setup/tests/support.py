"""Shared test scaffolding: paths to the packet and to Track D's candidate."""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from typing import Any

PACKET_ROOT = Path(__file__).resolve().parents[1]
SRC = PACKET_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

#: Track D's reviewable R2 candidate. Referenced, never copied, so a byte
#: change in the candidate breaks these tests loudly instead of silently
#: leaving them green against a stale copy — and so this packet never carries a
#: second copy of another stream's bytes that could drift from theirs.
#:
#: The candidate is research-side material and lives in no repository, so its
#: location is supplied rather than assumed. Set ``F107B_CANDIDATE_ROOT`` to
#: point at it; the default is the sibling layout this packet was built in.
DEFAULT_CANDIDATE_ROOT = PACKET_ROOT.parent / "track-d-p1-candidate"
CANDIDATE_ROOT = Path(
    os.environ.get("F107B_CANDIDATE_ROOT", str(DEFAULT_CANDIDATE_ROOT))
).expanduser()
REPLAY_BIN = CANDIDATE_ROOT / "tools" / "replay-bin"
CANDIDATE_RESPONSES = CANDIDATE_ROOT / "fixtures" / "responses"

#: The exact manifest digest the R2 handoff binds. Recorded here so the suite
#: states which bytes it was run against.
CANDIDATE_MANIFEST_SHA256 = (
    "2341c763c4ee7958387335f01a5274155311239e3c82572b1855521dc85d37f4"
)

SCHEMAS = PACKET_ROOT / "schemas"
FIXTURES = PACKET_ROOT / "fixtures"
OPTIONAL_COMPONENT_SCHEMA = SCHEMAS / "plebian.setup.optional-component-v1.schema.json"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def response_data(name: str) -> dict[str, Any]:
    """The ``data`` member of one candidate response fixture."""

    return load_json(CANDIDATE_RESPONSES / name)["data"]


#: Whether the candidate is reachable. Tests that need it skip with a reason
#: naming the variable to set, rather than erroring or — worse — passing.
CANDIDATE_AVAILABLE = REPLAY_BIN.is_dir() and CANDIDATE_RESPONSES.is_dir()
CANDIDATE_REASON = (
    f"Track D's R2 candidate is not at {CANDIDATE_ROOT}; "
    "set F107B_CANDIDATE_ROOT to the candidate root "
    f"(manifest {CANDIDATE_MANIFEST_SHA256})"
)
requires_candidate = unittest.skipUnless(CANDIDATE_AVAILABLE, CANDIDATE_REASON)
