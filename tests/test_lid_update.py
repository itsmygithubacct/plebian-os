"""The update reaches the lid default on machines provisioned before it.

Review finding P1: the updater deployed the provisioner without running it, so an
existing install never got 50-plebian-lid.conf (firstboot does not rerun, and the
managed `pleb install` leaves logind to this layer). These tests drive the real
`reapply_lid_defaults`, and the real root snapshot/restore scripts, against a
scratch root: every absolute path is rewritten under it and nothing outside it is
touched. logind is never restarted or signalled.
"""
from __future__ import annotations

import os
import re
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPDATE = ROOT / "provision" / "plebian-os-update.sh"
PROVISION = ROOT / "provision" / "plebian-os-provision.sh"
NAME = "50-plebian-lid.conf"
OWNER = b"[Login]\nHandleLidSwitch=ignore\nIdleAction=ignore\n"


def under(text: str, root: Path) -> str:
    """Rewrite absolute filesystem paths in shell text to live under root."""
    def sub(m):
        return m.group(1) + (str(root) if m.group(2) == "/" else str(root) + m.group(2))
    return re.sub(r'(^|[\s(="\'])(/(?:etc|usr|var|run|opt|srv)(?:/[^\s"\'):;|&<>`$]*)?|/(?=[\s"\']))', sub, text, flags=re.M)


class Fixture:
    def __init__(self, tc: unittest.TestCase):
        self.tmp = Path(tempfile.mkdtemp())
        tc.addCleanup(subprocess.run, ["rm", "-rf", str(self.tmp)])
        self.root = self.tmp / "root"
        for d in ("", "usr", "usr/local", "usr/local/share", "usr/local/sbin", "etc", "etc/lightdm",
                  "etc/systemd", "var", "var/lib", "var/lib/plebian-os"):
            (self.root / d).mkdir(parents=True, exist_ok=True)
            (self.root / d).chmod(0o755)
        self.dd = self.root / "etc/systemd/logind.conf.d"
        self.conf = self.dd / NAME
        self.prov = self.root / "usr/local/sbin/plebian-os-provision"

    def mkdd(self):
        self.dd.mkdir(parents=True)
        self.dd.chmod(0o755)

    def install_provisioner(self, text=None):
        text = text if text is not None else under(PROVISION.read_text(), self.root)
        self.prov.write_text(text)
        self.prov.chmod(0o755)

    def tree(self):
        return {str(p.relative_to(self.root)): (p.is_symlink(), os.readlink(p) if p.is_symlink() else
                (p.read_bytes() if p.is_file() else None), stat.S_IMODE(p.lstat().st_mode))
                for p in sorted(self.root.rglob("*"))}


def scripts():
    text = UPDATE.read_text()
    snap = text[text.index("<<'ROOT_SNAPSHOT'") + len("<<'ROOT_SNAPSHOT'\n"):text.index("\nROOT_SNAPSHOT")]
    rest = text[text.index("<<'ROOT_RESTORE'") + len("<<'ROOT_RESTORE'\n"):text.index("\nROOT_RESTORE")]
    return snap, rest


def as_user(text: str) -> str:
    # The scripts demand root ownership; the scratch tree is owned by the suite's user.
    return re.sub(r"(%u' [^\n]*?\)\")\s*= 0", r'\1 = "$(id -u)"', text)


class ReapplyLidDefaults(unittest.TestCase):
    def run_update_fn(self, fx, *, self_update="1", extra=""):
        sudo = fx.tmp / "bin"
        sudo.mkdir(exist_ok=True)
        (sudo / "sudo").write_text('#!/bin/sh\nexec "$@"\n')
        (sudo / "sudo").chmod(0o755)
        script = ("set -euo pipefail\nexport PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1\n"
                  f"export PLEBIAN_OS_UPDATE_TEST_PROVISION_SCRIPT={fx.prov}\n"
                  f"export PLEBIAN_OS_SELF_UPDATE={self_update}\n"
                  f"source {UPDATE}\nreapply_lid_defaults\n" + extra)
        env = {"PATH": f"{sudo}:/usr/bin:/bin", "HOME": str(fx.tmp)}
        return subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True, timeout=60)

    def test_provisioned_machine_without_the_dropin_gets_it_on_update(self):
        fx = Fixture(self)
        fx.install_provisioner()
        fx.mkdd()
        (fx.dd / "10-no-sleep-on-ac.conf").write_bytes(OWNER)
        (fx.dd / "20-else.conf").write_text("[Login]\nIdleAction=lock\n")
        before = fx.tree()
        r = self.run_update_fn(fx)
        self.assertEqual(r.returncode, 0, r.stderr)
        after = fx.tree()
        added = set(after) - set(before)
        self.assertEqual(added, {"etc/systemd/logind.conf.d/" + NAME})
        for k, v in before.items():
            self.assertEqual(after[k], v, k)
        body = fx.conf.read_text()
        for line in ("HandleLidSwitch=ignore", "HandleLidSwitchExternalPower=ignore", "HandleLidSwitchDocked=ignore"):
            self.assertIn(line + "\n", body)
        self.assertEqual(stat.S_IMODE(fx.conf.stat().st_mode), 0o644)

    def test_missing_directory_is_created_and_repeat_updates_are_idempotent(self):
        fx = Fixture(self)
        fx.install_provisioner()
        self.assertEqual(self.run_update_fn(fx).returncode, 0)
        first = fx.tree()
        self.assertEqual(self.run_update_fn(fx).returncode, 0)
        self.assertEqual(fx.tree(), first)
        self.assertEqual(sorted(p.name for p in fx.dd.iterdir()), [NAME])

    def test_logind_is_never_restarted_or_signalled(self):
        fx = Fixture(self)
        fx.install_provisioner()
        stubs = fx.tmp / "bin"
        stubs.mkdir(exist_ok=True)
        log = fx.tmp / "calls"
        for tool in ("systemctl", "kill", "pkill", "loginctl"):
            (stubs / tool).write_text(f'#!/bin/sh\necho "{tool} $*" >> {log}\n')
            (stubs / tool).chmod(0o755)
        self.assertEqual(self.run_update_fn(fx).returncode, 0)
        self.assertFalse(log.exists(), log.read_text() if log.exists() else "")

    def test_provisioner_without_the_function_fails_unless_self_update_is_off(self):
        fx = Fixture(self)
        old = under(PROVISION.read_text(), fx.root).replace("install_lid_defaults() {", "renamed_lid_defaults() {")
        fx.install_provisioner(old)
        r = self.run_update_fn(fx)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(fx.conf.exists())
        r = self.run_update_fn(fx, self_update="0")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("predates the lid default", r.stderr)
        self.assertFalse(fx.conf.exists())

    def test_unsafe_provisioner_is_refused(self):
        fx = Fixture(self)
        fx.install_provisioner()
        fx.prov.chmod(0o777)
        self.assertNotEqual(self.run_update_fn(fx).returncode, 0)
        self.assertFalse(fx.conf.exists())

    def test_main_update_applies_it_after_the_installs_and_inside_the_transaction(self):
        text = UPDATE.read_text()
        main = text[text.index("reapply_audio_holdoff\n    test_fail_after_boundary audio-holdoff"):]
        self.assertLess(main.index("reapply_lid_defaults\n    test_fail_after_boundary lid-defaults"),
                        main.index("migrate_pleb_session_env"))
        self.assertLess(text.index('"$PLEB_DIR/bin/pleb" install'), text.index("    reapply_lid_defaults\n"))


class UpdateTransactionRollback(unittest.TestCase):
    """Run the real root snapshot and restore scripts around the real writer."""

    def cycle(self, fx, *, fail_after_write=True):
        snap, rest = scripts()
        snap, rest = as_user(under(snap, fx.root)), as_user(under(rest, fx.root))
        stubs = "systemctl() { :; }\n"
        env = {"PATH": "/usr/bin:/bin", "HOME": str(fx.tmp)}
        taken = subprocess.run(["bash", "-c", "set -euo pipefail\n" + snap], env=env, capture_output=True, text=True)
        self.assertEqual(taken.returncode, 0, taken.stderr)
        txn = taken.stdout.strip().splitlines()[-1]
        fx.install_provisioner()
        w = subprocess.run(["bash", "-c", "set -euo pipefail\nexport PLEBIAN_OS_PROVISION_LIB_ONLY=1\n"
                            f"source {fx.prov}\nDRY_RUN=0\ninstall_lid_defaults\n"], env=env, capture_output=True, text=True)
        self.assertEqual(w.returncode, 0, w.stderr)
        self.assertTrue(fx.conf.exists())
        restored = subprocess.run(["bash", "-s", "--", txn], input=stubs + "set -euo pipefail\n" + rest, env=env,
                                  capture_output=True, text=True)
        self.assertEqual(restored.returncode, 0, restored.stderr)

    def test_failure_after_the_write_removes_the_file_and_the_directory_it_created(self):
        fx = Fixture(self)
        before = fx.tree()
        self.cycle(fx)
        after = fx.tree()
        self.assertFalse(fx.dd.exists())
        self.assertEqual({k: v for k, v in after.items() if not k.startswith("var/lib/plebian-os/update-rollback")},
                         {k: v for k, v in before.items() if not k.startswith("var/lib/plebian-os/update-rollback")})

    def test_rollback_restores_an_existing_dropin_and_leaves_others(self):
        fx = Fixture(self)
        fx.mkdd()
        (fx.dd / "10-no-sleep-on-ac.conf").write_bytes(OWNER)
        fx.conf.write_text("old\n")
        fx.conf.chmod(0o640)
        self.cycle(fx)
        self.assertEqual(fx.conf.read_text(), "old\n")
        self.assertEqual(stat.S_IMODE(fx.conf.stat().st_mode), 0o640)
        self.assertEqual((fx.dd / "10-no-sleep-on-ac.conf").read_bytes(), OWNER)

    def test_linked_destination_is_replaced_not_followed_and_restored_as_the_link(self):
        fx = Fixture(self)
        fx.mkdd()
        owner = fx.dd / "10-no-sleep-on-ac.conf"
        owner.write_bytes(OWNER)
        fx.conf.symlink_to(owner.name)
        self.cycle(fx)
        self.assertTrue(fx.conf.is_symlink())
        self.assertEqual(os.readlink(fx.conf), owner.name)
        self.assertEqual(owner.read_bytes(), OWNER)


class LinkedDestinationWrite(unittest.TestCase):
    def write(self, fx):
        fx.install_provisioner()
        return subprocess.run(["bash", "-c", "set -euo pipefail\nexport PLEBIAN_OS_PROVISION_LIB_ONLY=1\n"
                               f"source {fx.prov}\nDRY_RUN=0\ninstall_lid_defaults\n"],
                              env={"PATH": "/usr/bin:/bin", "HOME": str(fx.tmp)}, capture_output=True, text=True)

    def test_success_never_changes_the_file_a_link_pointed_at(self):
        fx = Fixture(self)
        fx.mkdd()
        owner = fx.dd / "10-no-sleep-on-ac.conf"
        owner.write_bytes(OWNER)
        fx.conf.symlink_to(owner.name)
        r = self.write(fx)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(owner.read_bytes(), OWNER)
        self.assertFalse(fx.conf.is_symlink())
        self.assertIn("HandleLidSwitch=ignore", fx.conf.read_text())
        self.assertEqual(stat.S_IMODE(fx.conf.stat().st_mode), 0o644)

    def test_dangling_link_and_leftover_staging_files(self):
        fx = Fixture(self)
        fx.mkdd()
        fx.conf.symlink_to("does-not-exist")
        self.assertEqual(self.write(fx).returncode, 0)
        self.assertTrue(fx.conf.is_file() and not fx.conf.is_symlink())
        self.assertEqual([p.name for p in fx.dd.iterdir()], [NAME])

    def test_failed_publish_leaves_the_destination_and_no_staging_file(self):
        fx = Fixture(self)
        fx.mkdd()
        fx.conf.write_text("old\n")
        fx.install_provisioner()
        stubs = fx.tmp / "bin"
        stubs.mkdir()
        (stubs / "mv").write_text("#!/bin/sh\nexit 1\n")
        (stubs / "mv").chmod(0o755)
        r = subprocess.run(["bash", "-c", "set -euo pipefail\nexport PLEBIAN_OS_PROVISION_LIB_ONLY=1\n"
                            f"source {fx.prov}\nDRY_RUN=0\ninstall_lid_defaults\n"],
                           env={"PATH": f"{stubs}:/usr/bin:/bin", "HOME": str(fx.tmp)}, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(fx.conf.read_text(), "old\n")
        self.assertEqual([p.name for p in fx.dd.iterdir()], [NAME])

    def test_preseed_publishes_by_rename_not_redirection(self):
        text = (ROOT / "preseed" / "preseed.cfg").read_text()
        self.assertNotRegex(text, r"> /target/etc/systemd/logind\.conf\.d/50-plebian-lid\.conf")
        self.assertIn("mv -f /target/etc/systemd/logind.conf.d/.50-plebian-lid.conf.new "
                      "/target/etc/systemd/logind.conf.d/50-plebian-lid.conf", text)
        self.assertIn("chown root:root /target/etc/systemd/logind.conf.d/.50-plebian-lid.conf.new", text)


if __name__ == "__main__":
    unittest.main()
