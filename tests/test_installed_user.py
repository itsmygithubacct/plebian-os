import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECORDER = ROOT / "provision" / "plebian-os-record-installed-user"


class InstalledUserRecordTests(unittest.TestCase):
    def run_recorder(self, passwd_lines, homes):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / "target"
        (root / "etc/plebian-os").mkdir(parents=True)
        (root / "etc/passwd").write_text("".join(passwd_lines))
        for home in homes:
            root.joinpath(home.lstrip("/")).mkdir(parents=True)

        # The real installer runs as root. Stub only chown so this behavioral
        # fixture can exercise selection and atomic output unprivileged.
        tools = Path(temp.name) / "tools"
        tools.mkdir()
        chown = tools / "chown"
        chown.write_text("#!/bin/sh\nexit 0\n")
        chown.chmod(0o755)
        env = dict(os.environ)
        env["PATH"] = f"{tools}:/usr/bin:/bin"
        result = subprocess.run(
            [str(RECORDER), str(root)], text=True, capture_output=True, env=env,
        )
        return result, root / "etc/plebian-os/installed-user"

    def test_records_one_boundary_length_nondefault_account(self):
        username = "a" + "b" * 31
        result, record = self.run_recorder(
            [
                "root:x:0:0:root:/root:/bin/bash\n",
                f"{username}:x:1234:1234:Operator:/home/{username}:/bin/bash\n",
            ],
            [f"/home/{username}"],
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(record.read_text(), username + "\n")
        self.assertEqual(stat.S_IMODE(record.stat().st_mode), 0o644)

    def test_refuses_multiple_eligible_accounts_instead_of_guessing(self):
        first = "first"
        second = "second"
        result, record = self.run_recorder(
            [
                "root:x:0:0:root:/root:/bin/bash\n",
                f"{first}:x:1000:1000:First:/home/{first}:/bin/bash\n",
                f"{second}:x:1001:1001:Second:/home/{second}:/bin/bash\n",
            ],
            [f"/home/{first}", f"/home/{second}"],
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expected exactly one", result.stderr)
        self.assertFalse(record.exists())

    def test_rejects_name_outside_debian_policy(self):
        result, record = self.run_recorder(
            ["Upper:x:1000:1000:Bad:/home/Upper:/bin/bash\n"],
            ["/home/Upper"],
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(record.exists())

    def test_rejects_noncanonical_home_path(self):
        result, record = self.run_recorder(
            ["operator:x:1000:1000:Operator:/home/../etc:/bin/bash\n"],
            [],
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(record.exists())

    def test_media_records_before_firstboot_and_provisioner_prefers_record(self):
        preseed = (ROOT / "preseed" / "preseed.cfg").read_text()
        remaster = (ROOT / "build" / "remaster-iso.sh").read_text()
        provision = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
        self.assertIn("plebian-os-record-installed-user", remaster)
        stage = preseed.index(
            "cp /cdrom/plebian-os/plebian-os-record-installed-user "
            "/target/etc/plebian-os/.record-installed-user"
        )
        recorder = preseed.index(
            "in-target /bin/sh /etc/plebian-os/.record-installed-user /"
        )
        cleanup = preseed.index(
            "rm -f /target/etc/plebian-os/.record-installed-user"
        )
        enable = preseed.index("systemctl enable plebian-os-firstboot.service")
        self.assertLess(stage, recorder)
        self.assertLess(recorder, cleanup)
        self.assertLess(cleanup, enable)
        self.assertNotIn(
            "/bin/sh /cdrom/plebian-os/plebian-os-record-installed-user /target",
            preseed,
        )
        recorder_source = RECORDER.read_text()
        self.assertIn('[ "$root_prefix" != / ] || root_prefix=', recorder_source)
        self.assertIn("read_recorded_user()", provision)
        self.assertIn("root-owned mode 0644 with one link", provision)
        self.assertIn("multiple eligible regular users found; refusing to guess", provision)
        self.assertIn("sole eligible user is uid $uid, not fallback uid 1000", provision)
        self.assertIn("^[a-z][-a-z0-9_]{0,31}$", provision)


if __name__ == "__main__":
    unittest.main()
