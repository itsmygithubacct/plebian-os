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
                  "etc/pleb", "etc/systemd", "var", "var/lib", "var/lib/plebian-os"):
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


def session_env_script():
    text = UPDATE.read_text()
    return text[text.index("<<'ROOT_SESSION_ENV'") + len("<<'ROOT_SESSION_ENV'\n"):text.index("\nROOT_SESSION_ENV")]


def scripts():
    text = UPDATE.read_text()
    snap = text[text.index("<<'ROOT_SNAPSHOT'") + len("<<'ROOT_SNAPSHOT'\n"):text.index("\nROOT_SNAPSHOT")]
    rest = text[text.index("<<'ROOT_RESTORE'") + len("<<'ROOT_RESTORE'\n"):text.index("\nROOT_RESTORE")]
    return snap, rest


def as_user(text: str) -> str:
    # The scripts demand root ownership; the scratch tree is owned by the suite's user.
    text = text.replace('"$owner" = 0 ]', '"$owner" = "$(id -u)" ]')
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


OLD_IDLE = 'if [ -z "${PLEB_IDLE_LOCK_SECONDS+x}" ]; then PLEB_IDLE_LOCK_SECONDS=600; fi\n'
NEW_IDLE = 'if [ -z "${PLEB_IDLE_LOCK_SECONDS+x}" ]; then PLEB_IDLE_LOCK_SECONDS=0; fi\n'
BASE = ('if [ -z "${PLEB_WM+x}" ]; then PLEB_WM=openbox; fi\n'
        'if [ -z "${KILIX_RUN_ALIASES+x}" ]; then KILIX_RUN_ALIASES=1; fi\n')


class IdleLockMigration(unittest.TestCase):
    """migrate_pleb_session_env: the former generated 600 becomes 0; choices stay."""

    def setUp(self):
        self.fx = Fixture(self)
        self.env_path = self.fx.root / "etc/pleb/session.env"

    def migrate(self, text):
        self.env_path.write_text(text)
        self.env_path.chmod(0o644)
        script = as_user(under(session_env_script(), self.fx.root))
        r = subprocess.run(["bash", "-s", "--", str(self.env_path)], input=script, capture_output=True, text=True,
                           env={"PATH": "/usr/bin:/bin", "HOME": str(self.fx.tmp)})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.stderr = r.stderr
        return self.env_path.read_text()

    def effective(self, text):
        r = subprocess.run(["bash", "-c", f'set -e; unset PLEB_IDLE_LOCK_SECONDS; . {self.env_path}; echo "${{PLEB_IDLE_LOCK_SECONDS:-600}}"'],
                           capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})
        return r.stdout.strip()

    def test_old_generated_default_becomes_zero_and_other_lines_are_kept(self):
        before = "# operator comment\n" + BASE + OLD_IDLE + 'FOO=bar\n'
        after = self.migrate(before)
        self.assertEqual(after, "# operator comment\n" + BASE + NEW_IDLE + 'FOO=bar\n')
        self.assertEqual(self.effective(after), "0")

    def test_missing_entry_gets_the_new_default(self):
        after = self.migrate(BASE)
        self.assertIn(NEW_IDLE, after)
        self.assertEqual(self.effective(after), "0")

    def test_explicit_values_are_preserved(self):
        for label, line in (("explicit zero", "PLEB_IDLE_LOCK_SECONDS=0\n"),
                            ("explicit nonzero opt-in", "PLEB_IDLE_LOCK_SECONDS=123\n"),
                            ("operator wrote 600", "PLEB_IDLE_LOCK_SECONDS=600\n"),
                            ("exported", "export PLEB_IDLE_LOCK_SECONDS=300\n"),
                            ("other guarded value", 'if [ -z "${PLEB_IDLE_LOCK_SECONDS+x}" ]; then PLEB_IDLE_LOCK_SECONDS=900; fi\n')):
            with self.subTest(label):
                before = BASE + line
                self.assertEqual(self.migrate(before), before)

    NOTE = "plebian-os-update: NOTE: "

    def test_harmless_export_and_comments_do_not_block_the_migration(self):
        for label, extra in (("bare export", "export PLEB_IDLE_LOCK_SECONDS\n"),
                             ("bare export with spaces", "  export PLEB_IDLE_LOCK_SECONDS  \n"),
                             ("a comment", "# PLEB_IDLE_LOCK_SECONDS controls auto locking\n"),
                             ("an indented comment", "   # PLEB_IDLE_LOCK_SECONDS=123\n"),
                             ("the auto-lock opt-in", "PLEB_AUTO_LOCK=on\n"),
                             ("a longer unrelated name", "PLEB_IDLE_LOCK_MINUTES=1\n")):
            for position in ("after", "before"):
                with self.subTest(label, position=position):
                    before = (BASE + OLD_IDLE + extra) if position == "after" else (BASE + extra + OLD_IDLE)
                    after = self.migrate(before)
                    self.assertEqual(after, before.replace(OLD_IDLE, NEW_IDLE))
                    self.assertNotIn(self.NOTE, self.stderr)
                    self.assertEqual(self.migrate(after), after)
                    self.assertEqual(self.effective(after), "0")

    UNCERTAIN = (
        ("plain assignment", "PLEB_IDLE_LOCK_SECONDS=123\n"),
        ("export assignment", "export PLEB_IDLE_LOCK_SECONDS=123\n"),
        ("readonly", "readonly PLEB_IDLE_LOCK_SECONDS=123\n"),
        ("default form", ': "${PLEB_IDLE_LOCK_SECONDS:=123}"\n'),
        ("append", "PLEB_IDLE_LOCK_SECONDS+=1\n"),
        ("array element", "PLEB_IDLE_LOCK_SECONDS[0]=123\n"),
        ("arithmetic", "((PLEB_IDLE_LOCK_SECONDS += 1))\n"),
        ("read", "read -r PLEB_IDLE_LOCK_SECONDS <<<'123'\n"),
        ("printf -v", "printf -v PLEB_IDLE_LOCK_SECONDS '%s' 123\n"),
        ("indirect eval", "name=PLEB_IDLE_LOCK_SECONDS\neval \"$name+=1\"\n"),
        ("read-only reference", 'printf "%s\\n" "$PLEB_IDLE_LOCK_SECONDS" >/dev/null\n'),
        ("quoted example", "printf '%s\\n' 'PLEB_IDLE_LOCK_SECONDS=123' >/dev/null\n"),
        ("here-doc example", "cat <<'TEXT' >/dev/null\nPLEB_IDLE_LOCK_SECONDS=123\nTEXT\n"),
        ("hash before the assignment", "note='#'; PLEB_IDLE_LOCK_SECONDS+=1\n"),
        ("continued name", "PLEB_IDLE_LOCK_\\\nSECONDS+=1\n"),
        ("continued operator", "PLEB_IDLE_LOCK_SECONDS\\\n+=1\n"),
        ("guarded other value", 'if [ -z "${PLEB_IDLE_LOCK_SECONDS+x}" ]; then PLEB_IDLE_LOCK_SECONDS=900; fi\n'),
        ("test of it", '[ -n "${PLEB_IDLE_LOCK_SECONDS+x}" ] && :\n'),
        ("trailing comment", "PLEB_IDLE_LOCK_SECONDS=123 # mine\n"),
    )

    def test_anything_else_mentioning_the_name_is_preserved_and_reported(self):
        for label, extra in self.UNCERTAIN:
            for position in ("after", "before"):
                with self.subTest(label, position=position):
                    before = (BASE + OLD_IDLE + extra) if position == "after" else (BASE + extra + OLD_IDLE)
                    after = self.migrate(before)
                    self.assertEqual(after, before)
                    self.assertIn(self.NOTE, self.stderr)
                    self.assertIn(str(self.env_path), self.stderr)
                    self.assertIn("PLEB_IDLE_LOCK_SECONDS=0", self.stderr)
                    self.assertEqual(self.migrate(after), after)

    def test_the_report_names_the_offending_line_numbers(self):
        before = BASE + OLD_IDLE + "FOO=1\nPLEB_IDLE_LOCK_SECONDS=123\n"
        self.migrate(before)
        self.assertIn("line(s) 5 mention PLEB_IDLE_LOCK_SECONDS in a form this update does not rewrite", self.stderr)

    def test_unrelated_final_line_without_a_newline_stays_without_one(self):
        before = BASE + OLD_IDLE + "# last line, no newline"
        after = self.migrate(before)
        self.assertEqual(after, before.replace(OLD_IDLE, NEW_IDLE))
        self.assertFalse(after.endswith("\n"))

    def test_a_missing_entry_is_appended_after_an_unterminated_file(self):
        after = self.migrate(BASE.rstrip("\n"))
        self.assertTrue(after.startswith(BASE.rstrip("\n") + "\n"))
        self.assertIn(NEW_IDLE, after)

    def test_migration_never_sources_operator_text(self):
        marker = self.fx.tmp / "ran"
        before = BASE + OLD_IDLE + f"touch {marker}\n"
        self.migrate(before)
        self.assertFalse(marker.exists())

    def test_rollback_after_a_migration_that_follows_a_reference(self):
        before = BASE + OLD_IDLE + "export PLEB_IDLE_LOCK_SECONDS\n"
        self.env_path.write_text(before)
        self.env_path.chmod(0o644)
        snap, rest = scripts()
        snap, rest = as_user(under(snap, self.fx.root)), as_user(under(rest, self.fx.root))
        env = {"PATH": "/usr/bin:/bin", "HOME": str(self.fx.tmp)}
        txn = subprocess.run(["bash", "-c", "set -euo pipefail\n" + snap], env=env, capture_output=True, text=True)
        self.assertEqual(txn.returncode, 0, txn.stderr)
        self.assertEqual(self.migrate(before), before.replace(OLD_IDLE, NEW_IDLE))
        r = subprocess.run(["bash", "-s", "--", txn.stdout.strip().splitlines()[-1]],
                           input="systemctl() { :; }\nset -euo pipefail\n" + rest, env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.env_path.read_text(), before)

    def test_old_default_plus_an_operator_assignment_is_left_alone(self):
        before = BASE + "PLEB_IDLE_LOCK_SECONDS=300\n" + OLD_IDLE
        self.assertEqual(self.migrate(before), before)

    def test_commented_old_default_is_not_the_setting(self):
        before = BASE + "# " + OLD_IDLE
        after = self.migrate(before)
        self.assertIn(NEW_IDLE, after)
        self.assertIn("# " + OLD_IDLE, after)

    def test_repeated_updates_are_idempotent(self):
        once = self.migrate(BASE + OLD_IDLE)
        self.assertEqual(self.migrate(once), once)
        missing = self.migrate(BASE)
        self.assertEqual(self.migrate(missing), missing)

    def test_rollback_after_migration_restores_the_old_file(self):
        before = BASE + OLD_IDLE
        self.env_path.write_text(before)
        self.env_path.chmod(0o644)
        snap, rest = scripts()
        snap, rest = as_user(under(snap, self.fx.root)), as_user(under(rest, self.fx.root))
        env = {"PATH": "/usr/bin:/bin", "HOME": str(self.fx.tmp)}
        txn = subprocess.run(["bash", "-c", "set -euo pipefail\n" + snap], env=env, capture_output=True, text=True)
        self.assertEqual(txn.returncode, 0, txn.stderr)
        self.assertEqual(self.migrate(before), BASE + NEW_IDLE)
        self.env_path.write_text(BASE + NEW_IDLE)
        r = subprocess.run(["bash", "-s", "--", txn.stdout.strip().splitlines()[-1]],
                           input="systemctl() { :; }\nset -euo pipefail\n" + rest, env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.env_path.read_text(), before)

    def test_migration_runs_inside_the_update_transaction(self):
        text = UPDATE.read_text()
        self.assertIn("/etc/pleb/session.env\n", text[text.index("paths=("):text.index("managed_dirs=(")])
        main = text[text.index("    reapply_lid_defaults\n    test_fail_after_boundary lid-defaults"):]
        self.assertLess(main.index("migrate_pleb_session_env"), main.index("write_final_provenance"))

    def test_provisioner_default_is_zero_and_the_old_line_is_the_migrated_shape(self):
        self.assertIn("write_session_default PLEB_IDLE_LOCK_SECONDS 0\n", PROVISION.read_text())
        self.assertIn(OLD_IDLE.strip(), UPDATE.read_text())


class InterruptedWrite(unittest.TestCase):
    """SIGTERM between staging and rename: the real restore leaves nothing behind."""

    def run_interrupted(self, fx, existing):
        import signal, time
        if existing:
            fx.mkdd()
            (fx.dd / "10-no-sleep-on-ac.conf").write_bytes(OWNER)
            fx.conf.write_text("old\n")
            fx.conf.chmod(0o640)
        snap, rest = scripts()
        snap, rest = as_user(under(snap, fx.root)), as_user(under(rest, fx.root))
        env = {"PATH": "/usr/bin:/bin", "HOME": str(fx.tmp)}
        txn = subprocess.run(["bash", "-c", "set -euo pipefail\n" + snap], env=env, capture_output=True, text=True)
        self.assertEqual(txn.returncode, 0, txn.stderr)
        fx.install_provisioner()
        stubs = fx.tmp / "bin"
        stubs.mkdir()
        (stubs / "mv").write_text(f"#!/bin/sh\n: > {fx.tmp}/at-mv\nexec sleep 30\n")
        (stubs / "mv").chmod(0o755)
        p = subprocess.Popen(["bash", "-c", "set -euo pipefail\nexport PLEBIAN_OS_PROVISION_LIB_ONLY=1\n"
                              f"source {fx.prov}\nDRY_RUN=0\ninstall_lid_defaults\n"],
                             env={**env, "PATH": f"{stubs}:/usr/bin:/bin"}, start_new_session=True)
        for _ in range(100):
            if (fx.tmp / "at-mv").exists():
                break
            time.sleep(.1)
        self.assertTrue((fx.tmp / "at-mv").exists())
        self.assertTrue((fx.dd / ".50-plebian-lid.conf.stage").exists(), "the stage should exist before the rename")
        os.killpg(p.pid, signal.SIGTERM)
        p.wait(timeout=10)
        r = subprocess.run(["bash", "-s", "--", txn.stdout.strip().splitlines()[-1]],
                           input="systemctl() { :; }\nset -euo pipefail\n" + rest, env=env, capture_output=True, text=True)
        return r

    def test_new_directory_is_removed_completely(self):
        fx = Fixture(self)
        r = self.run_interrupted(fx, existing=False)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(fx.dd.exists())

    def test_existing_directory_keeps_only_its_original_files(self):
        fx = Fixture(self)
        r = self.run_interrupted(fx, existing=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sorted(p.name for p in fx.dd.iterdir()), ["10-no-sleep-on-ac.conf", NAME])
        self.assertEqual(fx.conf.read_text(), "old\n")
        self.assertEqual(stat.S_IMODE(fx.conf.stat().st_mode), 0o640)
        self.assertEqual((fx.dd / "10-no-sleep-on-ac.conf").read_bytes(), OWNER)

    def test_stage_is_in_every_inventory_and_stale_stages_are_replaced(self):
        stage = "/etc/systemd/logind.conf.d/.50-plebian-lid.conf.stage"
        self.assertEqual(UPDATE.read_text().count(stage + "\n"), 2)
        self.assertEqual(PROVISION.read_text().count(stage + "\n"), 1)
        fx = Fixture(self)
        fx.mkdd()
        (fx.dd / ".50-plebian-lid.conf.stage").write_text("stale\n")
        fx.install_provisioner()
        r = subprocess.run(["bash", "-c", "set -euo pipefail\nexport PLEBIAN_OS_PROVISION_LIB_ONLY=1\n"
                            f"source {fx.prov}\nDRY_RUN=0\ninstall_lid_defaults\n"],
                           env={"PATH": "/usr/bin:/bin", "HOME": str(fx.tmp)}, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([p.name for p in fx.dd.iterdir()], [NAME])


if __name__ == "__main__":
    unittest.main()
