"""Tests for the private-build-path leak detector.

`0.2.1-F120-CONVERGENCE-AND-CLOSURE-STATE-R1.md` section 5.2.1 calls this
detector "the point of F120": it is what stops a staged artifact carrying the
absolute path of the machine that built it. It shipped with **no tests**. An
independent review seat hard-wired `_contains_private_path` to `return False`
and the release gate still returned `rc 0`, `61/61 OK`, outcome "accepted" --
the gate could not see its own detector removed.

These tests exist so that stubbing the detector FAILS. A control observed only
passing is indistinguishable from one that cannot fail, so each case here is
paired: the needle is found when present and absent when not.

The chunk-boundary case is the one an untested implementation gets wrong. The
detector reads in 1 MiB blocks and keeps a `tail` of `max(len(needle)) - 1`
bytes precisely so a needle split across two reads is still seen. Nothing
exercised that until now.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kilix_f120.build_cache import _contains_private_path

CHUNK = 1024 * 1024


class PrivatePathDetectorTest(unittest.TestCase):
    def _write(self, data: bytes) -> Path:
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.write(data)
        handle.close()
        path = Path(handle.name)
        self.addCleanup(path.unlink)
        return path

    # --- present / absent, the basic pair ---------------------------------

    def test_finds_a_needle_that_is_present(self):
        path = self._write(b"prefix/home/builder/work/libfoo.a suffix")
        self.assertTrue(
            _contains_private_path(path, [b"/home/builder/work"]))

    def test_reports_absent_when_the_needle_is_not_there(self):
        path = self._write(b"no private path in this artifact at all")
        self.assertFalse(
            _contains_private_path(path, [b"/home/builder/work"]))

    # --- the case the tail/overlap logic exists for -----------------------

    def test_finds_a_needle_split_across_a_chunk_boundary(self):
        needle = b"/home/builder/private-build-root"
        # Place the needle so it straddles the 1 MiB read boundary: half in the
        # first chunk, half in the second. A naive per-chunk scan misses this.
        head = b"\x00" * (CHUNK - (len(needle) // 2))
        path = self._write(head + needle + b"\x00" * 4096)
        self.assertTrue(
            _contains_private_path(path, [needle]),
            "a needle spanning two reads must still be detected")

    def test_absent_needle_is_not_invented_across_a_boundary(self):
        # Same shape as above, but the bytes never spell the needle. Guards
        # against the tail logic manufacturing a match by re-scanning overlap.
        needle = b"/home/builder/private-build-root"
        path = self._write(b"\x00" * (CHUNK + 4096))
        self.assertFalse(_contains_private_path(path, [needle]))

    # --- degenerate inputs must not produce false positives ---------------

    def test_no_needles_means_no_leak(self):
        path = self._write(b"/home/builder/work/libfoo.a")
        self.assertFalse(_contains_private_path(path, []))

    def test_empty_needle_is_ignored_rather_than_matching_everything(self):
        # `any(needle and needle in data ...)` guards this; without the
        # truthiness check an empty needle matches every artifact.
        path = self._write(b"harmless bytes")
        self.assertFalse(_contains_private_path(path, [b""]))

    # --- several needles, which is what the caller actually passes --------

    def test_finds_the_second_of_several_needles(self):
        path = self._write(b"only /home/second/root appears here")
        self.assertTrue(
            _contains_private_path(
                path, [b"/home/first/root", b"/home/second/root"]))

    def test_empty_file_has_no_leak(self):
        self.assertFalse(
            _contains_private_path(self._write(b""), [b"/home/builder"]))


if __name__ == "__main__":
    unittest.main()
