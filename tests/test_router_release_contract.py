"""The selected release must carry routing, not merely repositories that do."""
import json
import re
import unittest
from pathlib import Path

from test_voice_release_contract import (
    _git, _manifest, _repo_candidates, kilix_content_repo_candidates,
    kilix_repo_candidates, repo_holding,
)

ROOT = Path(__file__).resolve().parents[1]


class RouterReleaseContractTests(unittest.TestCase):
    def test_selected_host_and_catalog_deliver_the_router(self):
        pins = _manifest(ROOT / "releases" / "0.2.2.env")
        host_ref = pins["KILIX_REF"]
        host = repo_holding(kilix_repo_candidates(), host_ref)
        self.assertIsNotNone(host, "fetch the selected Kilix source for release checks")
        launcher = _git(host, "show", host_ref + ":kilix")
        self.assertIsNotNone(launcher)
        # Without this dispatch, `ask` reaches Kitty's unrelated input dialog.
        self.assertIsNotNone(re.search(r"(?m)^  ask\)$", launcher),
                             "selected Kilix has no job-router dispatch")
        self.assertTrue("ask --interactive" in launcher,
                        "selected Kilix does not invoke Needle's interactive router")

        content_ref = _git(host, "rev-parse", host_ref + ":third_party/kilix-content").strip()
        content = repo_holding(kilix_content_repo_candidates(), content_ref)
        self.assertIsNotNone(content, "fetch the host's selected Content commit")
        catalog = json.loads(_git(content, "show", content_ref +
                                  ":src/kilix_content/catalog/plebian.json"))
        needle_ref = next(row["source"]["ref"] for row in catalog["content"]
                          if row["id"] == "kilix-needle")
        candidates = _repo_candidates("PLEBIAN_OS_NEEDLE_REPO", ("kilix-needle",),
                                      ("kilix-apps", "kilix-needle"))
        needle = repo_holding(candidates, needle_ref)
        self.assertIsNotNone(needle, "fetch the catalog's selected Needle commit")
        for path in ("ask.py", "router.py", "router-model/router.json"):
            self.assertIsNotNone(_git(needle, "show", needle_ref + ":" + path), path)
        dispatch = _git(needle, "show", needle_ref + ":needle_cli.py")
        self.assertIsNotNone(dispatch)
        self.assertTrue("return ask.main(argv[1:])" in dispatch,
                        "selected Needle has no ask command")


if __name__ == "__main__":
    unittest.main()
