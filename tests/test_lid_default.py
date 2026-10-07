"""Lid close does nothing by default when no session policy is running.

Owner answer 17 (2026-10-07). The drop-in has a distinct name so an owner's
own logind drop-ins are never touched; a Pleb session's xfce4-power-manager
holds the lid inhibitor and decides for itself (see pleb's lid-default tests).
"""
from __future__ import annotations

import configparser
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVISION = ROOT / "provision" / "plebian-os-provision.sh"
PRESEED = ROOT / "preseed" / "preseed.cfg"
NAME = "50-plebian-lid.conf"
EXPECTED = {
    "HandleLidSwitch": "ignore",
    "HandleLidSwitchExternalPower": "ignore",
    "HandleLidSwitchDocked": "ignore",
}


def parse(text):
    cp = configparser.ConfigParser(interpolation=None, strict=True)
    cp.optionxform = str
    cp.read_string(text)
    return {s: dict(cp[s]) for s in cp.sections()}


class LidDefault(unittest.TestCase):
    def run_install(self, root, dry=False):
        src = PROVISION.read_text()
        body = re.search(r"^install_lid_defaults\(\) \{\n.*?^\}\n", src, re.S | re.M)
        self.assertTrue(body, "install_lid_defaults is missing")
        fn = body.group(0).replace("/etc/systemd", f"{root}/etc/systemd")
        script = ("set -euo pipefail\nlog() { :; }\nDRY_RUN=%d\n%s\ninstall_lid_defaults\n"
                  % (1 if dry else 0, fn))
        return subprocess.run(["env", "-i", "PATH=/usr/bin:/bin", "bash", "-c", script],
                              capture_output=True, text=True)

    def test_provisioner_writes_exact_keys_and_values(self):
        with tempfile.TemporaryDirectory() as d:
            r = self.run_install(d)
            self.assertEqual(r.returncode, 0, r.stderr)
            conf = Path(d, "etc/systemd/logind.conf.d", NAME)
            self.assertEqual(parse(conf.read_text()), {"Login": EXPECTED})

    def test_other_dropins_are_untouched_and_rerun_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            dd = Path(d, "etc/systemd/logind.conf.d")
            dd.mkdir(parents=True)
            owner = dd / "10-no-sleep-on-ac.conf"
            owner.write_text("[Login]\nHandleLidSwitch=ignore\n")
            other = dd / "20-else.conf"
            other.write_text("[Login]\nIdleAction=lock\n")
            before = (owner.read_bytes(), other.read_bytes())
            self.assertEqual(self.run_install(d).returncode, 0)
            first = (dd / NAME).read_bytes()
            self.assertEqual(self.run_install(d).returncode, 0)
            self.assertEqual((dd / NAME).read_bytes(), first)
            self.assertEqual((owner.read_bytes(), other.read_bytes()), before)
            self.assertEqual(sorted(p.name for p in dd.iterdir()),
                             ["10-no-sleep-on-ac.conf", "20-else.conf", NAME])

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.run_install(d, dry=True).returncode, 0)
            self.assertFalse(Path(d, "etc").exists())

    def test_provision_runs_it_inside_the_root_transaction(self):
        src = PROVISION.read_text()
        self.assertLess(src.index("\nbegin_provision_root_transaction\n"),
                        src.index("\ninstall_lid_defaults\n"))
        paths = src[src.index("PROVISION_ROOT_TRANSACTION_PATHS=("):]
        self.assertIn("/etc/systemd/logind.conf.d/" + NAME, paths)

    def test_preseed_installs_the_same_values(self):
        text = PRESEED.read_text()
        self.assertIn("/target/etc/systemd/logind.conf.d/" + NAME, text)
        line = next(l for l in text.splitlines() if "printf" in l and "HandleLidSwitch=" in l)
        values = dict(re.findall(r"'(HandleLidSwitch\w*)=(\w+)'", line))
        self.assertEqual(values, EXPECTED)
        self.assertIn("'[Login]'", line)
        self.assertIn("chmod 0644 /target/etc/systemd/logind.conf.d/" + NAME, text)
        self.assertNotIn("10-no-sleep-on-ac", text + PROVISION.read_text())

    def test_logind_is_not_restarted(self):
        src = PROVISION.read_text()
        self.assertNotRegex(src, r"systemctl\s+(try-)?(restart|reload)\s+systemd-logind")
        self.assertNotRegex(src, r"kill\s+-HUP.*logind")


if __name__ == "__main__":
    unittest.main()
