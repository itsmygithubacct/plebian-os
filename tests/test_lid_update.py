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


OLD = b'if [ -z "${PLEB_IDLE_LOCK_SECONDS+x}" ]; then PLEB_IDLE_LOCK_SECONDS=600; fi\n'
NEWB = OLD.replace(b"=600;", b"=0;")
OLD_IDLE, NEW_IDLE = OLD.decode(), NEWB.decode()
BASEB = (b'if [ -z "${PLEB_WM+x}" ]; then PLEB_WM=openbox; fi\n'
         b'if [ -z "${KILIX_RUN_ALIASES+x}" ]; then KILIX_RUN_ALIASES=1; fi\n')
NOTE = b"plebian-os-update: NOTE: "


class IdleLockMigration(unittest.TestCase):
    """migrate_pleb_session_env: a whole-file grammar gate on raw bytes decides.

    Passing file: the exact generated 600 line becomes 0, a missing name gets its
    default, an operator assignment is left alone. Anything outside the grammar the
    provisioner renders: the file is not written at all and one NOTE says so.
    """

    def setUp(self):
        self.fx = Fixture(self)
        self.env_path = self.fx.root / "etc/pleb/session.env"

    def migrate(self, data: bytes):
        self.env_path.write_bytes(data)
        self.env_path.chmod(0o644)
        script = as_user(under(session_env_script(), self.fx.root))
        r = subprocess.run(["bash", "-s", "--", str(self.env_path)], input=script.encode(), capture_output=True,
                           env={"PATH": "/usr/bin:/bin", "HOME": str(self.fx.tmp)})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.out, self.err = r.stdout, r.stderr
        return self.env_path.read_bytes()

    def effective(self, data: bytes):
        self.env_path.write_bytes(data)
        r = subprocess.run(["bash", "-c", f'unset PLEB_IDLE_LOCK_SECONDS; . {self.env_path}; echo "${{PLEB_IDLE_LOCK_SECONDS:-600}}"'],
                           capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})
        return r.stdout.strip()

    # ---- what migrates -------------------------------------------------------
    GATE_OK = (
        ("bare export", b"export PLEB_IDLE_LOCK_SECONDS\n"),
        ("bare export with spaces", b"  export PLEB_IDLE_LOCK_SECONDS  \n"),
        ("multi-name export (as rendered)", b"export KILIX_CONFIG_HOME PLEB_IDLE_LOCK_SECONDS\n"),
        ("comment", b"# PLEB_IDLE_LOCK_SECONDS=123\n"),
        ("indented comment", b"   # note\n"),
        ("comment holding code", b'# if [ "$PLEB_IDLE_LOCK_SECONDS" = 600 ]; then PLEB_IDLE_LOCK_SECONDS=123; fi\n'),
        ("auto-lock opt-in", b"PLEB_AUTO_LOCK=on\n"),
        ("kiosk line with a trailing comment", b"PLEB_RESPAWN=1   # hard kiosk: respawn kilix if it exits (set by --kiosk)\n"),
        ("blank lines", b"\n\n"),
        ("odd comment bytes are NOT ok", None),
    )

    def test_gate_passing_files_migrate_the_inherited_line(self):
        for label, extra in self.GATE_OK:
            if extra is None:
                continue
            for position in ("after", "before"):
                with self.subTest(label, position=position):
                    before = BASEB + OLD + extra if position == "after" else BASEB + extra + OLD
                    after = self.migrate(before)
                    self.assertEqual(after, before.replace(OLD, NEWB))
                    self.assertNotIn(NOTE, self.err)
                    self.assertIn(b"600 -> 0", self.out)
                    self.assertEqual(self.migrate(after), after)
                    self.assertEqual(self.out, b"")
                    self.assertEqual(self.effective(after), "0")

    def test_missing_entry_is_appended_and_a_comment_mention_does_not_count(self):
        for before in (BASEB, BASEB + b"# PLEB_IDLE_LOCK_SECONDS is documented here\n", b""):
            with self.subTest(before=before):
                after = self.migrate(before)
                self.assertTrue(after.endswith(NEWB))
                self.assertTrue(after.startswith(before))
                self.assertEqual(self.migrate(after), after)

    def test_success_output_lists_every_added_name(self):
        self.migrate(b"")
        self.assertIn(b"added PLEB_WM KILIX_RUN_ALIASES PLEB_IDLE_LOCK_SECONDS to", self.out)

    def test_unterminated_final_inherited_line_is_migrated_and_stays_unterminated(self):
        before = BASEB + OLD.rstrip(b"\n")
        after = self.migrate(before)
        self.assertEqual(after, BASEB + NEWB.rstrip(b"\n"))
        self.assertIn(b"600 -> 0", self.out)
        self.assertEqual(self.migrate(after), after)

    # ---- operator choices (certain: kept silently) ---------------------------
    OPERATOR = (
        b"PLEB_IDLE_LOCK_SECONDS=123\n", b"export PLEB_IDLE_LOCK_SECONDS=123\n",
        b"PLEB_IDLE_LOCK_SECONDS=600\n", b"PLEB_IDLE_LOCK_SECONDS='45'\n", b'PLEB_IDLE_LOCK_SECONDS="45"\n',
        b"PLEB_IDLE_LOCK_SECONDS=0\n", b"PLEB_IDLE_LOCK_SECONDS=123 # mine\n",
        b'if [ -z "${PLEB_IDLE_LOCK_SECONDS+x}" ]; then PLEB_IDLE_LOCK_SECONDS=900; fi\n',
    )

    def test_a_certain_operator_assignment_keeps_the_file_byte_identical(self):
        for extra in self.OPERATOR:
            for position in ("after", "before"):
                with self.subTest(extra=extra, position=position):
                    before = BASEB + OLD + extra if position == "after" else BASEB + extra + OLD
                    self.assertEqual(self.migrate(before), before)
                    self.assertEqual(self.out, b"")
                    self.assertNotIn(NOTE, self.err)

    # ---- uncertain files: nothing written, one NOTE --------------------------
    UNCERTAIN = (
        ("arithmetic", b"((PLEB_IDLE_LOCK_SECONDS += 1))\n"),
        ("arithmetic increment", b"((PLEB_IDLE_LOCK_SECONDS++))\n"),
        ("array element", b"PLEB_IDLE_LOCK_SECONDS[0]=123\n"),
        ("array append", b"PLEB_IDLE_LOCK_SECONDS[0]+=1\n"),
        ("append", b"PLEB_IDLE_LOCK_SECONDS+=1\n"),
        ("default form", b': "${PLEB_IDLE_LOCK_SECONDS:=123}"\n'),
        ("readonly", b"readonly PLEB_IDLE_LOCK_SECONDS=123\n"),
        ("read", b"read -r PLEB_IDLE_LOCK_SECONDS <<<'123'\n"),
        ("printf -v", b"printf -v PLEB_IDLE_LOCK_SECONDS '%s' 123\n"),
        ("indirect eval", b'name=PLEB_IDLE_LOCK_SECONDS\neval "$name+=1"\n'),
        ("read-only reference", b'printf "%s\\n" "$PLEB_IDLE_LOCK_SECONDS" >/dev/null\n'),
        ("quoted example", b"printf '%s\\n' 'PLEB_IDLE_LOCK_SECONDS=123' >/dev/null\n"),
        ("here-doc example", b"cat <<'TEXT' >/dev/null\nPLEB_IDLE_LOCK_SECONDS=123\nTEXT\n"),
        ("hash before the assignment", b"note='#'; PLEB_IDLE_LOCK_SECONDS+=1\n"),
        ("continued name", b"PLEB_IDLE_LOCK_\\\nSECONDS+=1\n"),
        ("continued operator", b"PLEB_IDLE_LOCK_SECONDS\\\n+=1\n"),
        ("continued export", b"export PLEB_IDLE_LOCK_\\\nSECONDS\n"),
        ("empty continuation", b"\\\n"),
        ("comment ending in a backslash hides a choice", b"# operator note \\\nPLEB_IDLE_LOCK_SECONDS=123\n"),
        ("indented comment backslash", b"   # note \\\nPLEB_IDLE_LOCK_SECONDS=123\n"),
        ("trailing comment ending in a backslash", b"PLEB_IDLE_LOCK_SECONDS=123 # mine \\\n"),
        ("multiline quote with a hash line", b'note="\n# $((PLEB_IDLE_LOCK_SECONDS += 1))\n"\n'),
        ("test of the name", b'[ -n "${PLEB_IDLE_LOCK_SECONDS+x}" ] && :\n'),
        ("command", b"touch /nonexistent-marker\n"),
        ("sourcing", b". /etc/other.env\n"),
        ("semicolon list", b"A=1; B=2\n"),
        ("command substitution", b"A=$(id -u)\n"),
        ("backtick", b"A=`id -u`\n"),
        ("double quote with a dollar", b'A="$B"\n'),
        ("CRLF", b"A=1\r\n"),
        ("CR inside a comment", b"# a\rb\n"),
        ("NUL inside a comment", b"# a\x00b\n"),
        ("NUL", b"A=a\x00b\n"),
        ("non-UTF-8 comment", b"# \xff\xfe\x80\n"),
        ("control character before export", b"\x0bexport PLEB_IDLE_LOCK_SECONDS\n"),
        ("unterminated unrelated final line", b"FOO=last"),
        ("unknown name", b"PLEB_IDLE_LOCK_MINUTES=1\n"),
        ("special variable OPTIND", b"OPTIND=PLEB_IDLE_LOCK_SECONDS+=1\n"),
        ("quoted special variable", b"SECONDS='PLEB_IDLE_LOCK_SECONDS+=1'\n"),
        ("RANDOM", b"RANDOM=1\n"), ("LINENO", b"LINENO=1\n"), ("BASH_ENV", b"BASH_ENV=/tmp/x\n"),
        ("HISTSIZE", b"HISTSIZE=1\n"), ("IFS", b"IFS=x\n"), ("PATH", b"PATH=/tmp\n"),
        ("special in a guard", b'if [ -z "${OPTIND+x}" ]; then OPTIND=1; fi\n'),
        ("special in an export", b"export OPTIND\n"),
        ("lowercase name", b"foo=1\n"),
        ("ANSI-C with an unknown escape", b"KILIX_DESKTOP_COMMAND=$'a\\xzzb'\n"),
        ("ANSI-C with an expansion-looking escape", b"KILIX_DESKTOP_COMMAND=$'a\\u00e9'\n"),
        ("ANSI-C unterminated", b"KILIX_DESKTOP_COMMAND=$'a\n"),
        ("ANSI-C NUL escape", b"KILIX_DESKTOP_COMMAND=$'a\\000b\\t'\n"),
        ("ANSI-C octal for a printable byte", b"KILIX_DESKTOP_COMMAND=$'a\\101\\t'\n"),
        ("ANSI-C octal for a byte with a named escape", b"KILIX_DESKTOP_COMMAND=$'a\\011'\n"),
        ("ANSI-C octal for ESC", b"KILIX_DESKTOP_COMMAND=$'a\\033'\n"),
        ("ANSI-C without any control escape", b"KILIX_DESKTOP_COMMAND=$'plain text'\n"),
        ("ANSI-C with only backslash escapes", b"KILIX_DESKTOP_COMMAND=$'a\\\\b'\n"),
        ("ANSI-C octal above 377", b"KILIX_DESKTOP_COMMAND=$'a\\400\\t'\n"),
        ("ANSI-C raw control byte", b"KILIX_DESKTOP_COMMAND=$'a\x01b'\n"),
        ("ANSI-C in a guard, non-canonical", b'if [ -z "${KILIX_DESKTOP_COMMAND+x}" ]; then KILIX_DESKTOP_COMMAND=$\'a\\101\\t\'; fi\n'),
    )

    def test_anything_outside_the_grammar_is_not_written_and_is_reported(self):
        for label, extra in self.UNCERTAIN:
            for position in ("after", "before"):
                with self.subTest(label, position=position):
                    before = BASEB + OLD + extra if position == "after" else BASEB + extra + OLD
                    self.assertEqual(self.migrate(before), before)
                    self.assertIn(NOTE + str(self.env_path).encode(), self.err)
                    self.assertIn(b"PLEB_IDLE_LOCK_SECONDS=0", self.err)
                    self.assertEqual(self.out, b"", "no success output for an unchanged file")
                    self.assertEqual(self.migrate(before), before)

    def test_an_uncertain_file_gains_no_defaults_and_no_comment(self):
        for label, extra in self.UNCERTAIN:
            with self.subTest(label):
                before = extra  # no WM, aliases or idle default present at all
                self.assertEqual(self.migrate(before), before)
                self.assertIn(NOTE, self.err)

    def test_the_note_names_the_offending_lines(self):
        before = BASEB + OLD + b"FOO=1\n((PLEB_IDLE_LOCK_SECONDS += 1))\n"
        self.migrate(before)
        self.assertIn(b"5", self.err.split(b"\n")[0])
        self.assertIn(str(self.env_path).encode(), self.err)

    def test_the_inherited_line_inside_a_continuation_or_heredoc_is_not_migrated(self):
        for before in (BASEB + OLD.replace(b"then ", b"then \\\n"),
                       BASEB + b"cat <<'TEXT' >/dev/null\n" + OLD + b"TEXT\n",
                       BASEB + b"\\\n" + OLD):
            with self.subTest(before=before):
                self.assertEqual(self.migrate(before), before)
                self.assertIn(NOTE, self.err)

    def test_operator_text_is_never_executed(self):
        marker = self.fx.tmp / "ran"
        before = BASEB + OLD + f"touch {marker}\n".encode()
        self.assertEqual(self.migrate(before), before)
        self.assertFalse(marker.exists())

    # ---- final newline with additions ----------------------------------------
    def test_additions_keep_the_end_of_the_file_in_its_original_state(self):
        guard = lambda n, v: f'if [ -z "${{{n}+x}}" ]; then {n}={v}; fi'.encode()
        wm, al = guard("PLEB_WM", "openbox"), guard("KILIX_RUN_ALIASES", "1")
        for label, present in (("neither", b""), ("wm only", wm + b"\n"), ("aliases only", al + b"\n")):
            for terminated in (False, True):
                with self.subTest(label, terminated=terminated):
                    before = present + OLD.rstrip(b"\n") + (b"\n" if terminated else b"")
                    after = self.migrate(before)
                    self.assertEqual(after.endswith(b"\n"), terminated, after[-60:])
                    self.assertNotIn(NOTE, self.err)
                    self.assertTrue(after.startswith(present))
                    self.assertIn(NEWB.rstrip(b"\n"), after)
                    # shell needs the newline between the old last line and the additions
                    self.assertNotIn(b"fi#", after)
                    self.assertNotIn(b"fiif", after)
                    self.assertEqual(self.migrate(after), after, "repeat")
                    self.assertEqual(self.effective(after), "0")

    def test_unterminated_file_with_only_missing_defaults_added_stays_unterminated(self):
        before = BASEB.replace(b"KILIX_RUN_ALIASES", b"KILIX_RUN_ALIASES").rstrip(b"\n") + b"\n" + NEWB.rstrip(b"\n")
        after = self.migrate(before)
        self.assertEqual(after, before)

    # ---- names ---------------------------------------------------------------
    def test_the_allowlist_covers_everything_the_provisioner_and_pleb_session_define(self):
        text = UPDATE.read_text()
        listed = set(re.search(r'NAMES = frozenset\("""\n(.*?)\n""".split\(\)\)', text, re.S).group(1).split())
        prov = PROVISION.read_text()
        rendered = set(re.findall(r"write_session_default ([A-Z_][A-Z0-9_]*)", prov[prov.index("PLEB_ENV=/etc/pleb/session.env"):]))
        for line in re.findall(r"printf '%s\\n' 'export ([^']*)'", prov):
            rendered |= set(line.split())
        pleb_session = ROOT.parent / "rc6-lid-pleb" / "bin" / "pleb-session"
        if pleb_session.exists():
            src = pleb_session.read_text()
            for block in re.findall(r'_pleb_(?:release_)?vars="([^"]*)"', src):
                rendered |= {w for w in block.split() if re.fullmatch(r"[A-Z][A-Z0-9_]*", w)}
        rendered |= {"PLEB_RESPAWN", "PLEB_WM", "KILIX_RUN_ALIASES", "PLEB_IDLE_LOCK_SECONDS", "PLEB_AUTO_LOCK"}
        self.assertEqual(sorted(rendered - listed), [])
        for special in ("OPTIND", "RANDOM", "SECONDS", "LINENO", "IFS", "PATH", "BASH_ENV", "HISTSIZE", "HOME"):
            self.assertNotIn(special, listed)

    # ---- durable record: the system journal ----------------------------------
    def journal_stubs(self, *tools):
        """PATH stubs that record their arguments and stdin; returns (bin dir, call log)."""
        stubs = self.fx.tmp / "jbin"
        stubs.mkdir(exist_ok=True)
        calls = self.fx.tmp / "journal-calls"
        for tool in tools:
            (stubs / tool).write_text(f'#!/bin/sh\n{{ echo "{tool} $*"; cat 2>/dev/null; }} >> {calls}\n')
            (stubs / tool).chmod(0o755)
        return stubs, calls

    def migrate_with_path(self, data, stubs, base="/usr/bin:/bin"):
        self.env_path.write_bytes(data)
        self.env_path.chmod(0o644)
        script = as_user(under(session_env_script(), self.fx.root))
        r = subprocess.run(["bash", "-s", "--", str(self.env_path)], input=script.encode(), capture_output=True,
                           env={"PATH": f"{stubs}:{base}", "HOME": str(self.fx.tmp)})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.out, self.err = r.stdout, r.stderr
        return self.env_path.read_bytes()

    def test_the_note_goes_to_the_journal_via_logger_with_a_bounded_message(self):
        stubs, calls = self.journal_stubs("logger")
        before = BASEB + OLD + b"FOO=1\n((PLEB_IDLE_LOCK_SECONDS += 1))\n"
        self.assertEqual(self.migrate_with_path(before, stubs), before)
        line = calls.read_text().splitlines()[0]
        self.assertTrue(line.startswith("logger -t plebian-os-update -p user.notice -- "), line)
        self.assertIn(str(self.env_path), line)
        self.assertIn("line 5: outside the session.env grammar", line)
        self.assertLessEqual(len(line.split("-- ", 1)[1].encode()), 1024)
        self.assertIn(b"recorded in the system journal", self.err)
        self.assertFalse((self.fx.root / "var/lib/plebian-os/session-env-migration.log").exists())

    def test_the_journal_message_is_bounded_whatever_the_file_holds(self):
        stubs, calls = self.journal_stubs("logger")
        many = b"".join(b"((X%d))\n" % i for i in range(60))
        long_name = b"A" * 5000 + b"=1\n"
        self.migrate_with_path(BASEB + OLD + many + long_name, stubs)
        message = calls.read_text().splitlines()[0].split("-- ", 1)[1]
        self.assertLessEqual(len(message.encode()), 1024)
        self.assertIn("more", message)                      # at most 8 problems listed, the rest counted
        self.assertEqual(message.count("line "), 8)
        self.assertLessEqual(max(len(w) for w in message.split()), 120)
        self.migrate_with_path(BASEB + OLD + b"A" * 5000 + b"=1\n", stubs)
        self.assertLessEqual(max(len(w) for w in calls.read_text().split()), 120)

    def test_systemd_cat_is_used_when_logger_is_missing_and_stderr_alone_when_neither_exists(self):
        stubs, calls = self.journal_stubs("systemd-cat")
        before = BASEB + OLD + b"((X))\n"
        # logger may exist on the host: shadow it with a failing stub
        (stubs / "logger").write_text("#!/bin/sh\nexit 1\n")
        (stubs / "logger").chmod(0o755)
        self.migrate_with_path(before, stubs)
        text = calls.read_text()
        self.assertIn("systemd-cat -t plebian-os-update -p notice", text)
        self.assertIn(str(self.env_path), text)
        none = self.fx.tmp / "nobin"
        none.mkdir()
        for name in ("logger", "systemd-cat"):
            (none / name).write_text("#!/bin/sh\nexit 127\n")
            (none / name).chmod(0o755)
        self.migrate_with_path(before, none)
        self.assertIn(b"NOTE:", self.err)
        self.assertIn(b"not recorded anywhere else", self.err)

    def test_a_certain_file_makes_no_journal_entry_and_no_file_is_written_in_var_lib(self):
        stubs, calls = self.journal_stubs("logger", "systemd-cat")
        self.migrate_with_path(BASEB + OLD, stubs)
        self.assertFalse(calls.exists())
        d = self.fx.root / "var/lib/plebian-os"
        self.assertEqual(sorted(p.name for p in d.iterdir()), [])

    def test_the_removed_log_file_is_gone_from_the_sources(self):
        for path in ("provision/plebian-os-update.sh", "provision/plebian-os-provision.sh"):
            self.assertNotIn("session-env-migration", (ROOT / path).read_text())

    def test_raw_byte_problems_give_the_byte_offset_and_the_line(self):
        stubs, calls = self.journal_stubs("logger")
        for label, data, expect in (("NUL", BASEB + b"# a\x00b\n", "line 3: NUL byte at byte offset %d" % (len(BASEB) + 3)),
                                    ("CR", BASEB + b"# a\rb\n", "line 3: carriage return at byte offset %d" % (len(BASEB) + 3)),
                                    ("non-UTF-8", BASEB + b"# \xff\n", "line 3: not UTF-8 at byte offset %d" % (len(BASEB) + 2))):
            with self.subTest(label):
                calls.unlink(missing_ok=True)
                self.migrate_with_path(data, stubs)
                self.assertIn(expect.encode(), self.err)
                self.assertIn(expect, calls.read_text())

    # ---- every file the provisioner renders passes the gate -------------------
    def test_every_provisioner_rendered_shape_passes_the_gate(self):
        text = PROVISION.read_text()
        fn = re.search(r"^write_session_default\(\) \{\n.*?^\}\n", text, re.M | re.S).group(0)
        values = ["", "0", "600", "openbox", "xterm\t-e bash", "tab\there", "line\nbreak", "cr\rhere", "bell\a\b\f\v",
                  "esc\x1b[0m", "ctl\x01\x7f", "it's\ttab", "back\\slash\tx", "a\\nb", 'q"uote\t', "$HOME\tdollar",
                  "xterm -T caf\u00e9\t-e", "/home/releaseci/.local/gpu_terminal/sources", "git://10.0.2.2/pleb.git",
                  "https://example.org/a/libkilix_0.1.5+git320ce.d9a1_amd64.deb", "20260727T000000Z",
                  "a b", "it's", 'say "hi"', "$HOME", "`id`", "tilde~", "café /hôme", "a;b", "a&b", "a(b)", "a=b"]
        lines = [f'write_session_default {REAL_NAMES[i % len(REAL_NAMES)]} {shlex_quote(v)}' for i, v in enumerate(values)]
        script = fn + "\n" + "\n".join(lines) + "\nprintf '%s\\n' 'export GPU_TERMINAL_SETTINGS_FILE'\n" \
            "printf '%s\\n' 'export KILIX_CONFIG_HOME KILIX_STATE_DIRECTORY KILIX_CACHE_HOME'\n" \
            "printf '%s\\n' 'PLEB_RESPAWN=1   # hard kiosk: respawn kilix if it exits (set by --kiosk)'\n" \
            "write_session_default PLEB_IDLE_LOCK_SECONDS 0\n"
        rendered = subprocess.run(["bash", "-c", script], capture_output=True, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C.UTF-8"})
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        before = rendered.stdout
        after = self.migrate(before)
        self.assertNotIn(NOTE, self.err, self.err)
        # only the missing window-manager defaults are appended; nothing is rewritten
        self.assertTrue(after.startswith(before))
        self.assertEqual(self.migrate(after), after)
        # the same shapes with the inherited 600 default migrate
        old = before.replace(b"PLEB_IDLE_LOCK_SECONDS=0", b"PLEB_IDLE_LOCK_SECONDS=600")
        migrated = self.migrate(old)
        self.assertNotIn(NOTE, self.err, self.err)
        self.assertTrue(migrated.startswith(before))
        self.assertIn(b"600 -> 0", self.out)

    def test_every_canonical_printf_q_ansi_c_form_passes(self):
        # the real printf %q over every byte 1-255 in both locales, forced into $'...' by a tab
        for locale in ("C", "C.UTF-8"):
            for byte in range(1, 256):
                with self.subTest(locale=locale, byte=byte):
                    r = subprocess.run(["bash", "-c", 'printf "%q" "$(printf "x\\t\\\\x%02x" ' + str(byte) + ')y"'],
                                       capture_output=True, env={"PATH": "/usr/bin:/bin", "LC_ALL": locale})
                    quoted = r.stdout
                    if r.returncode or not quoted.startswith(b"$'"):
                        continue
                    before = BASEB + OLD + b"KILIX_DESKTOP_COMMAND=" + quoted + b"\n"
                    self.assertEqual(self.migrate(before), before.replace(OLD, NEWB))
                    self.assertNotIn(NOTE, self.err)

    def test_values_the_provisioner_could_only_render_as_ansi_c_quoting_are_uncertain(self):
        before = BASEB + OLD + b"A=$'a\\nb'\n"
        self.assertEqual(self.migrate(before), before)
        self.assertIn(NOTE, self.err)

    def test_a_real_installed_session_env_passes_the_gate(self):
        sample = ROOT.parent.parent.parent / "research/gpu_terminal/0.2.2-rc6/lid-default/vm/update-logs/session.env.before"
        if not sample.exists():
            self.skipTest("the VM sample is not on this machine")
        before = sample.read_bytes()
        self.assertEqual(self.migrate(before), before.replace(OLD, NEWB))
        self.assertNotIn(NOTE, self.err)

    # ---- transaction ---------------------------------------------------------
    def test_rollback_after_migration_restores_the_old_file(self):
        before = BASEB + OLD
        self.env_path.write_bytes(before)
        self.env_path.chmod(0o644)
        snap, rest = scripts()
        snap, rest = as_user(under(snap, self.fx.root)), as_user(under(rest, self.fx.root))
        env = {"PATH": "/usr/bin:/bin", "HOME": str(self.fx.tmp)}
        txn = subprocess.run(["bash", "-c", "set -euo pipefail\n" + snap], env=env, capture_output=True, text=True)
        self.assertEqual(txn.returncode, 0, txn.stderr)
        self.assertEqual(self.migrate(before), BASEB + NEWB)
        r = subprocess.run(["bash", "-s", "--", txn.stdout.strip().splitlines()[-1]],
                           input="systemctl() { :; }\nset -euo pipefail\n" + rest, env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.env_path.read_bytes(), before)

    def test_a_failed_write_never_reports_success(self):
        before = BASEB + OLD
        self.env_path.write_bytes(before)
        script = as_user(under(session_env_script(), self.fx.root))
        stubs = self.fx.tmp / "bin"
        stubs.mkdir(exist_ok=True)
        (stubs / "mv").write_text("#!/bin/sh\nexit 1\n")
        (stubs / "mv").chmod(0o755)
        r = subprocess.run(["bash", "-s", "--", str(self.env_path)], input=script.encode(), capture_output=True,
                           env={"PATH": f"{stubs}:/usr/bin:/bin", "HOME": str(self.fx.tmp)})
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn(b"600 -> 0", r.stdout)
        self.assertEqual(self.env_path.read_bytes(), before)
        self.assertEqual([p.name for p in self.env_path.parent.iterdir()], ["session.env"])

    def test_an_installed_file_that_does_not_match_is_never_reported_as_success(self):
        before = BASEB + OLD
        self.env_path.write_bytes(before)
        script = as_user(under(session_env_script(), self.fx.root))
        stubs = self.fx.tmp / "bin"
        stubs.mkdir(exist_ok=True)
        (stubs / "mv").write_text('#!/bin/sh\nprintf corrupted > "$4"\n')
        (stubs / "mv").chmod(0o755)
        r = subprocess.run(["bash", "-s", "--", str(self.env_path)], input=script.encode(), capture_output=True,
                           env={"PATH": f"{stubs}:/usr/bin:/bin", "HOME": str(self.fx.tmp)})
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn(b"600 -> 0", r.stdout)
        self.assertIn(b"does not match", r.stderr)

    def test_migration_runs_inside_the_update_transaction(self):
        text = UPDATE.read_text()
        self.assertIn("/etc/pleb/session.env\n", text[text.index("paths=("):text.index("managed_dirs=(")])
        main = text[text.index("    reapply_lid_defaults\n    test_fail_after_boundary lid-defaults"):]
        self.assertLess(main.index("migrate_pleb_session_env"), main.index("write_final_provenance"))

    def test_provisioner_default_is_zero_and_the_old_line_is_the_migrated_shape(self):
        self.assertIn("write_session_default PLEB_IDLE_LOCK_SECONDS 0\n", PROVISION.read_text())
        self.assertIn("OLD = guard(IDLE, '600')", UPDATE.read_text())


REAL_NAMES = ["KILIX_DESKTOP_COMMAND", "PLEB_WM", "PLEB_DIR", "KILIX_DESKTOP_NAME", "GPU_TERMINAL_HOME", "PLEB_CONFIG_HOME",
              "KILIX_DESKTOP_PROVIDER", "KILIX95_DIR", "PLEB_STATE_HOME", "KILIX_DIR"]


def shlex_quote(v: str) -> str:
    import shlex
    return shlex.quote(v)


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
